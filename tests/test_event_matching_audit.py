from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.event_matching_audit import (
    MATCHING_RULE,
    audit_event_matching,
    load_event_audit_json,
    write_event_matching_audit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_CATALOG = PROJECT_ROOT / "metadata" / "event_episode_catalog.csv"
EVENT_AUDIT_JSON = PROJECT_ROOT / "metadata" / "event_episode_catalog.audit.json"


def _synthetic_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": [
                "M7BEVENT-OVERLAP-A",
                "M7BEVENT-OVERLAP-B",
                "M7BEVENT-ISOLATED",
                "M7BEVENT-OTHER-STATION",
            ],
            "pair_id": [
                "M7BPAIR-1",
                "M7BPAIR-2",
                "M7BPAIR-3",
                "M7BPAIR-4",
            ],
            "anchor_id": [
                "M7BANCHOR-1",
                "M7BANCHOR-2",
                "M7BANCHOR-3",
                "M7BANCHOR-4",
            ],
            "control_id": [
                "M7BCONTROL-1",
                "M7BCONTROL-2",
                "M7BCONTROL-3",
                "M7BCONTROL-4",
            ],
            "station_id": ["B1", "B1", "B1", "S2"],
            "event_type": ["flood", "flood", "flood", "flood"],
            "season": ["MAM", "MAM", "JJA", "MAM"],
            "episode_length": [15, 15, 15, 15],
            "window_start_date": [
                "2018-05-01",
                "2018-05-10",
                "2018-07-01",
                "2018-05-01",
            ],
            "window_end_date": [
                "2018-05-15",
                "2018-05-24",
                "2018-07-15",
                "2018-05-15",
            ],
            "analysis_eligible": [True, True, True, False],
            "control_match_year_distance": [0, 0, 1, 0],
            "control_match_day_of_year_distance": [15, 16, 20, 12],
        }
    )


def test_overlapping_dates_share_a_cluster_and_isolated_episode_does_not() -> None:
    audit = audit_event_matching(_synthetic_events())
    clusters = audit.cluster_id.set_index("event_id")
    assert (
        clusters.loc["M7BEVENT-OVERLAP-A", "cluster_id"]
        == clusters.loc["M7BEVENT-OVERLAP-B", "cluster_id"]
        == clusters.loc["M7BEVENT-OTHER-STATION", "cluster_id"]
    )
    assert (
        clusters.loc["M7BEVENT-ISOLATED", "cluster_id"]
        != clusters.loc["M7BEVENT-OVERLAP-A", "cluster_id"]
    )
    assert clusters.loc["M7BEVENT-OVERLAP-A", "cluster_size"] == 3
    assert clusters.loc["M7BEVENT-ISOLATED", "cluster_size"] == 1
    assert (
        clusters.loc["M7BEVENT-OVERLAP-A", "station_cluster_id"]
        == clusters.loc["M7BEVENT-OVERLAP-B", "station_cluster_id"]
    )
    assert (
        clusters.loc["M7BEVENT-OVERLAP-A", "station_cluster_id"]
        != clusters.loc["M7BEVENT-OTHER-STATION", "station_cluster_id"]
    )
    graph = audit.overlap_graph
    assert len(graph) == 3
    assert graph["jaccard"].between(0.0, 1.0).all()
    assert np.isfinite(graph["jaccard"]).all()
    overlap_ab = graph.loc[
        graph["left_event_id"].eq("M7BEVENT-OVERLAP-A")
        & graph["right_event_id"].eq("M7BEVENT-OVERLAP-B")
    ].iloc[0]
    assert overlap_ab["overlap_days"] == 6
    assert overlap_ab["jaccard"] == pytest.approx(6 / 24)


def test_n_less_than_five_strata_are_descriptive_only() -> None:
    audit = audit_event_matching(_synthetic_events())
    season = audit.control_balance.loc[
        audit.control_balance["stratum_grain"].eq("station_event_season")
    ]
    b1_mam = season.loc[
        season["station_id"].eq("B1")
        & season["event_type"].eq("flood")
        & season["season"].eq("MAM")
    ].iloc[0]
    assert int(b1_mam["n_pairs"]) == 2
    assert b1_mam["inference_status"] == "descriptive_only"
    assert b1_mam["matching_rule"] == MATCHING_RULE
    assert b1_mam["covariate_status"] == "not_in_catalog"
    assert pd.isna(b1_mam["smd_T"])
    assert pd.isna(b1_mam["smd_F"])
    assert pd.isna(b1_mam["smd_Ta"])
    assert audit.summary["smallest_station_event_season_n"] == 1
    overall = audit.effective_sample_size.loc[
        audit.effective_sample_size["scope"].eq("overall_date_overlap_clusters")
    ].iloc[0]
    assert int(overall["n_episodes"]) == 4
    assert int(overall["effective_n"]) == 2
    assert int(overall["n_clusters"]) == 2


def test_pre_event_smd_is_computed_only_when_paired_columns_exist() -> None:
    frame = _synthetic_events()
    frame["pre_event_T"] = [10.0, 12.0, 11.0, 9.0]
    frame["control_pre_event_T"] = [10.2, 11.5, 10.8, 9.1]
    audit = audit_event_matching(frame)
    overall = audit.control_balance.loc[
        audit.control_balance["stratum_grain"].eq("overall")
    ].iloc[0]
    assert overall["covariate_status"] == "computed_from_catalog"
    assert np.isfinite(overall["smd_T"])
    assert pd.isna(overall["smd_F"])
    assert pd.isna(overall["smd_Ta"])


def test_mixing_m7a_and_m7b_fails_closed() -> None:
    mixed = _synthetic_events()
    mixed.loc[0, "event_id"] = "M7A-STRESS-B1-FLOOD"
    with pytest.raises(ValueError, match="mix M7a and M7b"):
        audit_event_matching(mixed)
    unlabeled = _synthetic_events()
    unlabeled["event_id"] = ["E1", "E2", "E3", "E4"]
    unlabeled["pair_id"] = ["P1", "P2", "P3", "P4"]
    unlabeled["anchor_id"] = ["A1", "A2", "A3", "A4"]
    unlabeled["control_id"] = ["C1", "C2", "C3", "C4"]
    with pytest.raises(ValueError, match="cannot determine M7a/M7b"):
        audit_event_matching(unlabeled)


def test_write_artifacts_and_missing_columns(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires columns"):
        audit_event_matching(pd.DataFrame({"event_id": ["M7BEVENT-1"]}))
    audit = write_event_matching_audit(_synthetic_events(), tmp_path)
    expected = {
        "event_overlap_graph.csv",
        "event_cluster_id.csv",
        "event_control_balance.csv",
        "event_effective_sample_size.csv",
        "event_n_lt5_strata.csv",
        "event_missing_strata.csv",
        "event_flood_same_type_overlaps.csv",
        "event_named_findings.csv",
    }
    assert set(audit.artifact_frames()) == expected
    for name in expected:
        assert (tmp_path / name).is_file()


def test_real_event_catalog_produces_finite_outputs() -> None:
    catalog = pd.read_csv(EVENT_CATALOG)
    audit_json = load_event_audit_json(EVENT_AUDIT_JSON)
    audit = audit_event_matching(
        catalog, audit_json=audit_json, catalog_path=EVENT_CATALOG
    )
    assert audit.summary["experiment_family"] == "M7b"
    assert audit.summary["m7a_mixed"] is False
    assert audit.summary["n_episodes"] == len(catalog)
    if len(audit.overlap_graph):
        assert np.isfinite(audit.overlap_graph["jaccard"]).all()
        assert audit.overlap_graph["jaccard"].between(0.0, 1.0).all()
    assert audit.cluster_id["cluster_size"].ge(1).all()
    assert np.isfinite(audit.effective_sample_size["effective_n"]).all()
    assert audit.summary["smallest_station_event_season_n"] >= 1
    season = audit.control_balance.loc[
        audit.control_balance["stratum_grain"].eq("station_event_season")
    ]
    assert (season["n_pairs"] < 5).any()
    assert season.loc[season["n_pairs"] < 5, "inference_status"].eq(
        "descriptive_only"
    ).all()
    assert (audit.control_balance["covariate_status"] == "not_in_catalog").all()
    assert audit.control_balance["smd_T"].isna().all()
    assert audit.control_balance["smd_F"].isna().all()
    assert audit.control_balance["smd_Ta"].isna().all()
    assert audit.summary["performance_evidence"] is False
    assert audit.summary["matching_rule"] == MATCHING_RULE
    assert audit.summary["abutting_fraction"] == pytest.approx(296 / 355)
    assert int(audit.summary["n_descriptive_only_season_strata"]) == 20
    assert len(audit.n_lt5_strata) == 20
    assert audit.n_lt5_strata["inference_status"].eq("descriptive_only").all()
    assert int(audit.summary["n_missing_season_strata"]) == 7
    assert len(audit.missing_strata) == 7
    missing = set(
        zip(
            audit.missing_strata["station_id"],
            audit.missing_strata["event_type"],
            audit.missing_strata["season"],
            strict=True,
        )
    )
    assert missing == {
        ("B1", "low_flow", "DJF"),
        ("P3", "high_temperature", "MAM"),
        ("P3", "high_temperature", "JJA"),
        ("P3", "low_flow", "DJF"),
        ("P3", "low_flow", "MAM"),
        ("S2", "low_flow", "DJF"),
        ("S2", "low_flow", "MAM"),
    }
    assert len(audit.flood_same_type_overlaps) == 12
    assert audit.flood_same_type_overlaps["overlap_class"].eq("same_type_flood").all()
    findings = audit.named_findings.set_index("finding_id")
    assert "station, season, and exact window length only" in str(
        findings.loc["control_rule_station_season_length_only", "statement"]
    )
    assert findings.loc["pre_event_covariates", "statement"].startswith(
        "covariate_status=not_in_catalog"
    )
    assert int(findings.loc["same_type_flood_window_overlaps", "n_value"]) == 12
    assert int(findings.loc["cross_type_window_overlaps", "n_value"]) == 139
    assert int(findings.loc["cluster_effective_n", "n_value"]) == 80
    assert audit.summary["m7a_mixed"] is False
    json.dumps(audit.summary)
