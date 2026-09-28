"""Writing results out: JSON on stdout for agents, CSV on disk for the record."""
from __future__ import annotations

import csv
import json
import sys


def emit_json(payload: dict, stream=None) -> None:
    json.dump(payload, stream or sys.stdout, indent=2, default=str)
    (stream or sys.stdout).write("\n")


def write_csv(path: str, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
