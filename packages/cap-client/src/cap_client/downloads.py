"""Download URLs for a CAP dataset, including the underlying h5ad."""
from __future__ import annotations

import json
import re

from .errors import CapError
from .queries import Q_DOWNLOAD_URLS

_DATASET_RE = re.compile(r"celltype\.info/project/\d+/dataset/(\d+)")


def download_urls(client, dataset_id: str) -> dict:
    r = client.call("DownloadUrls", {"datasetId": dataset_id}, Q_DOWNLOAD_URLS)
    if r.get("errors"):
        raise CapError(f"CAP DownloadUrls failed: {json.dumps(r['errors'])[:300]}")
    return r["data"]["downloadUrls"]


def resolve_h5ad_url(client, target: str, log=lambda m: None) -> str:
    """Turn a celltype.info dataset URL into its underlying h5ad URL.

    Anything that is not a CAP dataset URL is passed through unchanged, so
    callers can accept either.
    """
    m = _DATASET_RE.search(target)
    if not m:
        return target
    dataset_id = m.group(1)
    urls = download_urls(client, dataset_id)
    url = urls.get("annDataUrl")
    if not url:
        raise CapError(f"CAP dataset {dataset_id} exposes no annDataUrl (may be private).")
    if urls.get("isAnnDataUrlUpToDate") is False:
        log("  warning: CAP reports this h5ad is not up to date with the dataset")
    log(f"Resolved CAP dataset {dataset_id} ->\n  {url}")
    return url
