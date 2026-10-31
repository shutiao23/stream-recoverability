from pathlib import Path
from datetime import datetime, timedelta, timezone
import importlib
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
R = importlib.import_module("413_wrr_usgs_network_resume")


def test_retry_after_respects_observed_response_delay_bound_and_server_interval():
    start = datetime(2026, 10, 21, 9, 23, 25, tzinfo=timezone.utc)
    observed = start + timedelta(seconds=2)
    record = {"http_status": 429, "retry_after": "3601", "acquired_at_utc": start.isoformat(), "response_observed_at_utc": observed.isoformat()}
    assert R.retry_deadline(record) == observed + timedelta(seconds=3601 + 5)


def test_total_transfer_longer_than_a_read_timeout_never_advances_the_server_wait():
    start = datetime(2026, 10, 21, 9, 23, 25, tzinfo=timezone.utc)
    observed = start + timedelta(seconds=120)
    record = {"http_status": 429, "retry_after": "3601", "acquired_at_utc": start.isoformat(), "response_observed_at_utc": observed.isoformat()}
    assert R.retry_deadline(record, timeout_seconds=45) == observed + timedelta(seconds=3606)


def test_absolute_retry_time_is_timezone_aware_and_not_replaced_by_local_time():
    record = {"http_status": 429, "retry_after": "Wed, 21 Oct 2026 10:23:26 GMT", "acquired_at_utc": "2026-10-21T09:23:25+00:00"}
    assert R.retry_deadline(record) == datetime(2026, 10, 21, 10, 23, 31, tzinfo=timezone.utc)


@pytest.mark.parametrize("record", [
    {"http_status": 403, "retry_after": "3600"},
    {"http_status": 429, "retry_after": None},
    {"http_status": 429, "retry_after": "unparsed"},
    {"http_status": 429, "retry_after": "30", "acquired_at_utc": "2026-10-21T09:23:25", "response_observed_at_utc": "2026-10-21T09:23:26"},
])
def test_access_denial_or_unverified_retry_time_never_authorizes_a_retry(record):
    with pytest.raises(ValueError):
        R.retry_deadline(record)
