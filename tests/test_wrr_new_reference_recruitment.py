from pathlib import Path
import importlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
N = importlib.import_module("399_wrr_neon_recruitment_feasibility")
A = importlib.import_module("400_wrr_au_metadata_recruitment")
R = importlib.import_module("402_wrr_au_reference_acquisition")
S = importlib.import_module("403_wrr_au_native_support")
G = importlib.import_module("406_wrr_au_network_feasibility")
SETTINGS = json.loads((ROOT / "configs/wrr_au_reference_qualification_20261021.json").read_text())


def native_entry(rows):
    return {"columns": "Timestamp,Value,Quality Code,Aggregation Accuracy", "data": rows}


def test_source_size_gate_agrees_with_the_frozen_risk_rule_not_mask_count():
    from stream_recoverability.experiments.v19_revision.risk import select_group_threshold
    assert N.ideal_group_floor(.05, .005) == 104
    tiny = select_group_threshold(np.zeros(240), np.zeros(240, dtype=bool),
                                  np.repeat(np.arange(24), 10), [0], alpha=.005)
    assert tiny.status == "insufficient_independent_calibration_evidence"
    enough = select_group_threshold(np.zeros(104), np.zeros(104, dtype=bool),
                                    np.arange(104), [0], alpha=.005)
    assert enough.status == "certified"


def test_metadata_role_depends_on_component_members_not_row_order():
    assert A.component_group(["b", "a", "c"]) == A.component_group(["c", "b", "a"]) == "au_a"
    first = A.component_roles(["au_b", "au_a", "au_c"], SETTINGS)
    assert first == A.component_roles(["au_c", "au_b", "au_a", "au_a"], SETTINGS)
    assert set(first) == {"au_a", "au_b", "au_c"}
    assert set(first.values()) <= {"development", "calibration", "test"}


def test_published_wa_daily_label_is_not_assigned_to_the_previous_utc_year():
    entry = native_entry([["2021-01-01T02:00:00+10:00", 20, 10, 100]])
    daily, _ = R.qualified_daily(entry, {"local_standard_offset_hours": 8}, SETTINGS)
    assert daily.index[0] == pd.Timestamp("2021-01-01")
    assert daily.iloc[0] == 20


def test_nonmidnight_source_is_not_silently_redefined_as_a_daily_mean():
    entry = native_entry([["2021-01-01T01:00:00+10:00", 20, 10, 100]])
    with pytest.raises(ValueError, match="local-standard midnights"):
        R.qualified_daily(entry, {"local_standard_offset_hours": 10}, SETTINGS)


def test_estimates_low_coverage_and_sentinels_do_not_become_complete_reference():
    entry = native_entry([
        ["2021-01-01T00:00:00+10:00", 0, 10, 100],
        ["2021-01-02T00:00:00+10:00", 20, 110, 100],
        ["2021-01-03T00:00:00+10:00", 21, 10, 89],
        ["2021-01-04T00:00:00+10:00", -9999, 10, 100],
        ["2021-01-05T00:00:00+10:00", 22, 10, None]])
    daily, _ = R.qualified_daily(entry, {"local_standard_offset_hours": 10}, SETTINGS)
    assert daily.notna().tolist() == [True, False, False, False, True]
    assert daily.iloc[0] == 0


def test_unapproved_duplicate_keeps_good_mean_but_approved_conflict_removes_it():
    rows = [["2021-01-01T00:00:00+10:00", 10, 10, 100],
            ["2021-01-01T00:00:00+10:00", 30, 140, 100]]
    daily, _ = R.qualified_daily(native_entry(rows), {"local_standard_offset_hours": 10}, SETTINGS)
    assert daily.iloc[0] == 10
    rows.append(["2021-01-01T00:00:00+10:00", 11, 10, 100])
    daily, quality = R.qualified_daily(native_entry(rows), {"local_standard_offset_hours": 10}, SETTINGS)
    assert daily.isna().all() and quality["conflicting_approved_days"] == 1


def test_malformed_aggregation_accuracy_is_not_treated_as_missing_metadata():
    entry = native_entry([["2021-01-01T00:00:00+10:00", 20, 10, "unparsed"]])
    with pytest.raises(ValueError, match="aggregation-accuracy"):
        R.qualified_daily(entry, {"local_standard_offset_hours": 10}, SETTINGS)


def test_native_percent_suffix_cannot_hide_insufficient_daily_support():
    entry = {"columns": "Timestamp,Value,Quality Code,Aggregation Accuracy %",
             "data": [["2021-01-01T00:00:00+10:00", 20, 10, 89],
                      ["2021-01-02T00:00:00+10:00", 21, 10, 90]]}
    daily, _ = R.qualified_daily(entry, {"local_standard_offset_hours": 10}, SETTINGS)
    assert daily.notna().tolist() == [False, True]


def test_calendar_reference_requires_leap_day_and_strictly_prior_history():
    complete = pd.Series(20., index=pd.date_range("2020-01-01", "2020-12-31"))
    assert R.complete_years(complete) == [2020]
    assert R.complete_years(complete.drop(pd.Timestamp("2020-02-29"))) == []
    assert not R.metadata_can_support({"from": "2021-01-02", "to": "2024-12-31"}, 2024)
    assert R.metadata_can_support({"from": "2021-01-01", "to": "2024-12-31"}, 2024)


def test_many_native_samples_in_a_short_burst_cannot_certify_a_daily_reference():
    times = pd.date_range("2024-01-01T00:00:00+10:00", periods=96, freq="min")
    entry = {"columns": "Timestamp,Value,Quality Code",
             "data": [[t.isoformat(), 20, 10] for t in times]}
    support = S.native_support(entry, 10, 2024)
    assert not support.native_support.any()
    assert support.occupied_hours.iloc[0] == 2


def test_native_support_requires_both_distinct_hours_and_twenty_hour_span():
    times = pd.date_range("2024-01-01T00:00:00+10:00", periods=20, freq="h")
    entry = {"columns": "Timestamp,Value,Quality Code",
             "data": [[t.isoformat(), 20, 10] for t in times]}
    assert not S.native_support(entry, 10, 2024).native_support.iloc[0]
    entry["data"].append(["2024-01-01T20:00:00+10:00", 20, 10])
    support = S.native_support(entry, 10, 2024)
    assert support.native_support.iloc[0] and len(support) == 366


def test_approved_native_conflicts_remove_hour_support_instead_of_averaging():
    times = pd.date_range("2024-01-01T00:00:00+10:00", periods=24, freq="h")
    rows = [[t.isoformat(), 20, 10] for t in times]
    rows += [[t.isoformat(), 22, 10] for t in times[:5]]
    entry = {"columns": "Timestamp,Value,Quality Code", "data": rows}
    assert not S.native_support(entry, 10, 2024).native_support.iloc[0]


def test_native_quarter_retry_keeps_the_full_leap_year_and_original_offset():
    params = {"from": "2024-01-01T00:00:00+09:30", "to": "2024-12-31T23:59:59+09:30", "ts_id": "1"}
    quarters = S.quarterly_parameters(params, 2024)
    assert quarters[0]["from"] == params["from"] and quarters[-1]["to"] == params["to"]
    for left, right in zip(quarters, quarters[1:]):
        assert pd.Timestamp(right["from"]) - pd.Timestamp(left["to"]) == pd.Timedelta(seconds=1)
    assert pd.Timestamp(quarters[0]["to"]).month == 3
    assert params["from"] == "2024-01-01T00:00:00+09:30"


def test_quarter_transport_merge_does_not_synthesize_missing_observations():
    entries = [{"ts_id": "1", "columns": "Timestamp,Value,Quality Code",
                "data": [[f"2024-{month:02d}-01T00:00:00+10:00", 0, 10]] if month != 4 else []}
               for month in [1, 4, 7, 10]]
    merged = S.merge_native_parts(entries)
    assert merged["data"] == [entries[0]["data"][0], entries[2]["data"][0], entries[3]["data"][0]]
    assert merged["rows"] == "3"
    with pytest.raises(ValueError, match="all four"):
        S.merge_native_parts(entries[:3])


def test_month_retry_keeps_original_values_and_distinguishes_composite_from_raw(tmp_path, monkeypatch):
    import gzip
    from types import SimpleNamespace
    monkeypatch.setattr(S, "DIRECTORY", tmp_path)
    monkeypatch.setattr(S.C, "ROOT", tmp_path)
    requested = []
    def get(endpoint, *, params, timeout):
        requested.append(params)
        value = int(params["from"][5:7])
        payload = [{"ts_id": "1", "columns": "Timestamp,Value,Quality Code",
                    "data": [[params["from"], value, 10]]}]
        body = json.dumps(payload).encode()
        return SimpleNamespace(status_code=200, content=body, json=lambda: payload)
    monkeypatch.setattr(S.requests, "get", get)
    params = {"from": "2024-01-01T00:00:00+09:30", "to": "2024-03-31T23:59:59+09:30"}
    path = tmp_path / "quarter.json.gz"
    assert S.acquire_months({"station_id": "site", "native_ts_id": "1", "year": 2024}, params, path) is None
    with gzip.open(path, "rt") as file:
        rows = json.load(file)[0]["data"]
    assert [row[1] for row in rows] == [1, 2, 3]
    assert requested[1]["to"] == "2024-02-29T23:59:59+09:30"
    ledger = json.loads(path.with_suffix(".request.json").read_text())
    assert ledger["source_mode"] == "lossless_value_merge_of_three_provider_months"
    assert "raw_response_bytes" not in ledger
    assert len(ledger["source_parts"]) == 3
    assert all(part["raw_response_bytes"] > 0 for part in ledger["source_parts"])


def test_quarter_access_denial_stays_pending_without_monthly_fallback(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(S, "DIRECTORY", tmp_path)
    monkeypatch.setattr(S.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=403))
    def unexpected(*args):
        raise AssertionError("An access denial is not a gateway-size failure")
    monkeypatch.setattr(S, "acquire_months", unexpected)
    row = S.acquire_quarters({"station_id": "1", "year": 2024},
                             {"from": "2024-01-01T00:00:00+10:00", "to": "2024-12-31T23:59:59+10:00"})
    assert row["status"] == "pending_quarter_access" and row["http_status"] == 403


def test_all_downstream_branches_and_shared_attachments_remain_one_dependent_unit():
    anchors = {"a": 1, "alias": 1, "b": 3, "c": 4, "independent": 9}
    graph = {1: [2], 2: [3, 4], 3: [-1], 4: [-1], 9: [-1]}
    links, pending = G.downstream_station_links(anchors, graph)
    assert ("a", "alias") in links and ("a", "b") in links and ("a", "c") in links
    assert all("independent" not in pair for pair in links)
    assert not pending


def test_missing_topology_is_pending_and_a_cycle_cannot_create_independent_groups():
    graph = {1: [2], 2: [1, 3], 3: [-1], 5: [6]}
    links, pending = G.downstream_station_links({"a": 1, "b": 3, "unknown": 5}, graph)
    assert links == {("a", "b")} and pending == {"unknown"}


def test_ghosts_attach_to_the_physical_graph_even_if_their_own_edge_is_present():
    graph = {1: [3], 2: [3], 3: [-1]}
    assert G.graph_attachment({"hydroid": 1, "ahgfftype": 8, "nextdownid": 3}, graph) == 3
    assert G.graph_attachment({"hydroid": 2, "ahgfftype": 4, "nextdownid": 3}, graph) == 2
