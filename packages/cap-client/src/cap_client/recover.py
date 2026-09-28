"""Recover CAP's persisted GraphQL query bodies from the client JS bundle.

Run this when a call starts failing with QUERY_NOT_IN_SAFELIST: CAP has
redeployed and the bodies in queries.py no longer match what the server accepts.

How it works: the raw GraphQL sources are string literals in the page's JS
chunks. Apollo sends print(addTypename(parse(src))) -- dedent by two spaces and
append __typename as the last field of every selection set except the operation
root. That transform is validated here against DEGenes and GeneralDE, whose
expected output is known from queries.py; if those two do not reproduce exactly,
the transform is wrong and nothing else it emits should be trusted.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

from .errors import CapError
from .queries import Q_DE_GENES, Q_GENERAL_DE
from .transport import ssl_context

DEFAULT_PAGE = "https://celltype.info/project/1030/dataset/3400"
_UA = {"user-agent": "Mozilla/5.0"}

#: The control: the transform must reproduce these exactly.
KNOWN = {"DEGenes": Q_DE_GENES, "GeneralDE": Q_GENERAL_DE}


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, context=ssl_context(), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def bundle_text(page_url: str) -> str:
    """Concatenate every JS chunk the dataset page references."""
    html = _fetch(page_url)
    chunks = sorted(set(re.findall(r"/_next/static/chunks/[A-Za-z0-9_.-]*\.js", html)))
    if not chunks:
        raise CapError("No JS chunks found on the page -- CAP's build layout may have changed.")
    print(f"{len(chunks)} chunks", file=sys.stderr)
    return "".join(_fetch("https://celltype.info" + c) for c in chunks)


def raw_source(js: str, op: str) -> str | None:
    r"""Pull the raw `\n  query Op(...)` string literal out of the bundle."""
    m = re.search(r'"\\n\s*(?:query|mutation)\s+' + re.escape(op) + r"\(", js)
    if not m:
        return None
    i = m.start()
    j = i + 1
    while j < len(js):  # walk to the closing quote, honouring escapes
        if js[j] == "\\":
            j += 2
            continue
        if js[j] == '"':
            break
        j += 1
    return json.loads(js[i:j + 1])


def apollo_print(raw: str) -> str:
    """print(addTypename(parse(src))): dedent 2, add __typename to every non-root set."""
    lines = [line.removeprefix("  ") for line in raw.split("\n") if line.strip()]
    out = []
    for line in lines:
        ind = len(line) - len(line.lstrip())
        if line.strip() == "}" and ind > 0:
            out.append(" " * (ind + 2) + "__typename")
        out.append(line)
    return "\n".join(out)


def const_name(op: str) -> str:
    return "Q_" + re.sub(r"(?<!^)(?=[A-Z])", "_", op).upper()


def recover(page_url: str, ops: list[str], stream=None) -> int:
    stream = stream or sys.stdout
    js = bundle_text(page_url)

    ok = True
    for op, expected in KNOWN.items():
        raw = raw_source(js, op)
        if raw is None:
            print(f"CONTROL {op}: not found in bundle", file=sys.stderr)
            ok = False
            continue
        match = apollo_print(raw) == expected
        print(f"CONTROL {op}: {'match' if match else 'MISMATCH'}", file=sys.stderr)
        ok = ok and match
    if not ok:
        raise CapError(
            "Control queries did not reproduce. The transform no longer matches what "
            "Apollo sends; do not trust any output it would emit. Re-capture from "
            "browser devtools instead (Network -> graphql -> request payload).")

    print("", file=sys.stderr)
    for op in ops:
        raw = raw_source(js, op)
        if raw is None:
            print(f"# {op}: NOT FOUND", file=sys.stderr)
            continue
        print(f"{const_name(op)} = {json.dumps(apollo_print(raw))}\n", file=stream)
    return 0
