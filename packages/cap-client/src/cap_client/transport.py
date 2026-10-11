"""GraphQL transport for celltype.info: pacing, retries, and error surfacing.

Every request in this package goes through GraphQLClient.call, so the minimum
interval set here paces all code paths. That matters because the on-demand DE
path issues three calls per cell type rather than one.

Requests are deliberately serial. These are unauthenticated public endpoints;
do not add concurrency.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.request

import certifi

from .errors import CapError

GRAPHQL_URL = "https://celltype.info/graphql"

#: Identifies us the way CAP's own web client does. The safelist check keys off
#: the query body, not these headers, but sending what the client sends keeps us
#: on the path CAP actually tests.
CLIENT_EXTENSIONS = {"clientLibrary": {"name": "@apollo/client", "version": "4.1.6"}}

RETRY_CODES = (429, 500, 502, 503, 504)


def fetch_page(url: str, timeout: float = 60.0) -> str:
    """GET a celltype.info page as text.

    Two of CAP's structures -- labelsets and per-label feedback -- have no
    safelisted GraphQL operation and are only readable from the page's embedded
    Next.js payload, so page fetching is a first-class need rather than a
    workaround local to one module.
    """
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ssl_context(), timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise CapError(f"HTTP {e.code} fetching {url} (dataset may be private)") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise CapError(f"Could not fetch {url}: {e}") from e


def ssl_context() -> ssl.SSLContext:
    """certifi rather than the system store: aiohttp and some CI images cannot
    read the macOS keychain, and GCS/S3 then fail with CERTIFICATE_VERIFY_FAILED."""
    return ssl.create_default_context(cafile=certifi.where())


class GraphQLClient:
    """Paced, retrying client for CAP's GraphQL endpoint.

    Tests substitute a stub with the same `call(op, variables, query)` signature.
    """

    def __init__(self, url: str = GRAPHQL_URL, min_interval: float = 0.5,
                 timeout: float = 180.0, attempts: int = 4, log=None):
        self.url = url
        self.min_interval = min_interval
        self.timeout = timeout
        self.attempts = attempts
        self.log = log if log is not None else (lambda msg: print(msg, file=sys.stderr))
        self._ctx = ssl_context()
        self._last_call = 0.0
        self.n_requests = 0

    def _wait(self) -> None:
        gap = self.min_interval - (time.monotonic() - self._last_call)
        if gap > 0:
            time.sleep(gap)
        self._last_call = time.monotonic()

    def call(self, op: str, variables: dict, query: str) -> dict:
        """POST one operation and return the decoded payload, errors included.

        GraphQL-level errors are returned in the payload, not raised: several
        callers treat them as signal (a missing precomputed DE, the obs-column
        probe) rather than as failure. Transport-level failures raise CapError.
        """
        self._wait()
        self.n_requests += 1
        body = {"operationName": op, "variables": variables,
                "extensions": CLIENT_EXTENSIONS, "query": query}
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(),
            headers={"content-type": "application/json",
                     "apollographql-client-name": "web",
                     "accept": "application/graphql-response+json,application/json;q=0.9"})
        for attempt in range(self.attempts):
            last = attempt == self.attempts - 1
            try:
                with urllib.request.urlopen(req, context=self._ctx, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                # Back off on rate limiting and transient server errors rather
                # than retrying immediately or bailing out mid-run.
                if e.code in RETRY_CODES and not last:
                    backoff = float(e.headers.get("retry-after") or 0) or 2 ** attempt * 2
                    self.log(f"  HTTP {e.code} on {op}, retrying in {backoff:.0f}s")
                    time.sleep(backoff)
                    self._last_call = time.monotonic()
                    continue
                detail = e.read()[:300].decode(errors="replace")
                raise CapError(f"HTTP {e.code} from CAP GraphQL: {detail}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if not last:
                    self.log(f"  {e} on {op}, retrying")
                    time.sleep(2 ** attempt * 2)
                    continue
                raise CapError(f"Network error talking to CAP GraphQL: {e}") from e
        raise CapError(f"{op} exhausted {self.attempts} attempts")  # pragma: no cover


def first_error(payload: dict, prefix: str = "", limit: int = 120) -> str | None:
    """The first GraphQL error message in a payload, truncated, or None."""
    errors = payload.get("errors")
    if not errors:
        return None
    msg = (errors[0] or {}).get("message", "")[:limit]
    return f"{prefix}: {msg}" if prefix else msg
