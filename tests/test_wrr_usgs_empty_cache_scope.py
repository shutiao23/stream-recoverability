from pathlib import Path
import importlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
S = importlib.import_module("420_wrr_usgs_empty_cache_scope")


def test_a_valid_header_is_not_a_temperature_observation():
    assert S.cache_row_state(b"site_id,date,temperature_c,qualifier\n") == ("header_only_no_retained_observation_rows", 0)
    assert S.cache_row_state(b"site_id,date,temperature_c,qualifier\n\n") == ("header_only_no_retained_observation_rows", 0)


def test_a_dated_missing_value_or_zero_cannot_be_discarded_as_an_empty_cache():
    for value in [b"", b"0"]:
        payload = b"site_id,date,temperature_c,qualifier\n12345678,2000-01-01," + value + b",A\n"
        assert S.cache_row_state(payload) == ("cache_contains_rows", 1)


def test_a_truncated_or_unverified_schema_is_pending_not_proof_of_no_rows():
    assert S.cache_row_state(b"") == ("unverified_cache_schema", None)
    assert S.cache_row_state(b"date,value\n") == ("unverified_cache_schema", None)
