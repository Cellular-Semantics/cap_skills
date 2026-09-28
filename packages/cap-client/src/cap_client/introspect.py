"""Dump a GraphQL input or enum type from CAP's endpoint.

Introspection is enabled, so an options shape can be checked rather than guessed.
"""
from __future__ import annotations

import json
import sys
import urllib.request

from .transport import CLIENT_EXTENSIONS, GRAPHQL_URL, ssl_context

_QUERY = """query I($n:String!){ __type(name:$n){ name kind inputFields{ name defaultValue type{...T} } enumValues{name} } }
fragment T on __Type { kind name ofType{ kind name ofType{ kind name ofType{ kind name } } } }"""


def _render(t: dict | None) -> str:
    if not t:
        return ""
    if t["kind"] == "NON_NULL":
        return _render(t["ofType"]) + "!"
    if t["kind"] == "LIST":
        return "[" + _render(t["ofType"]) + "]"
    return t["name"]


def introspect(names: list[str], stream=None) -> int:
    stream = stream or sys.stdout
    ctx = ssl_context()
    for n in names:
        body = {"query": _QUERY, "variables": {"n": n}, "extensions": CLIENT_EXTENSIONS}
        req = urllib.request.Request(GRAPHQL_URL, data=json.dumps(body).encode(),
                                    headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            d = json.load(r)["data"]["__type"]
        if not d:
            print(f"{n}: NOT FOUND", file=stream)
            continue
        print(f"--- {n} ({d['kind']})", file=stream)
        for f in d.get("inputFields") or []:
            default = f"  = {f['defaultValue']}" if f.get("defaultValue") else ""
            print(f"    {f['name']}: {_render(f['type'])}{default}", file=stream)
        for e in d.get("enumValues") or []:
            print(f"    | {e['name']}", file=stream)
    return 0
