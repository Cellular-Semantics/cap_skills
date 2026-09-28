"""Live smoke test. Excluded from CI (-m 'not live').

Needs a URL to read, since no public h5ad is stable enough to hard-code:

    H5AD_OBS_LIVE_URL=https://... pytest -m live
"""
import os

import pytest
from h5ad_obs import read_obs
from h5ad_obs.reader import check_range_support, list_columns

pytestmark = pytest.mark.live

URL = os.environ.get("H5AD_OBS_LIVE_URL")
needs_url = pytest.mark.skipif(not URL, reason="set H5AD_OBS_LIVE_URL to run")


@needs_url
def test_host_honours_ranges():
    assert check_range_support(URL) > 0


@needs_url
def test_columns_then_one_column():
    cols, stats = list_columns(URL)
    assert cols and stats.requests > 0
    name = cols[0]["name"]
    df, _skipped, read_stats = read_obs(URL, columns=[name])
    assert df.shape[0] > 0
    # The whole claim of this package: a fraction of the file, not the file.
    assert read_stats.bytes < (read_stats.total_bytes or float("inf"))
