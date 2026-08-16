from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.anchor_independence import (
    IID_WARNING,
    JACCARD_HIGH_THRESHOLD,
    NEARBY_CENTER_DAYS,
    PENDING_RANKING_REASON,
    audit_validation_anchor_independence,
    write_anchor_independence_audit,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ANCHORS = PROJECT_ROOT / "metadata" / "validation_anchors.csv"


def _synthetic_anchors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "anchor_id": [
                "VAL-B1-DEC02",
                "VAL-B1-DEC19",
                "VAL-B1-JUL",
                "VAL-S2-MAM08",
                "VAL-S2-MAM27",
                "VAL-P3-DEC02",
            ],
            "station_id": ["B1", "B1", "B1", "S2", "S2", "P3"],
            "center_date": [
                "2016-12-02",
                "2016-12-19",
                "2017-07-13",
                "2017-03-08",
                "2017-03-27",
                "2016-12-02",
            ],
            "season": ["DJF", "DJF", "JJA", "MAM", "MAM", "DJF"],
            "year": [2016, 2016, 2017, 2017, 2017, 2016],
            "max_supported_length": [180, 180, 180, 180, 180, 180],
        }
    )


def test_synthetic_same_station_jaccard_and_named_flags() -> None:
    audit = audit_validation_anchor_independence(_synthetic_anchors())
    pairs = audit.pairwise.set_index(["left_anchor_id", "right_anchor_id"])
    b1_dec = pairs.loc[("VAL-B1-DEC02", "VAL-B1-DEC19")]
    assert b1_dec["overlap_days"] == 163
    assert b1_dec["union_days"] == 197
    assert b1_dec["jaccard"] == pytest.approx(163 / 197)
    assert bool(b1_dec["flag_b1_december_2016_pair"])
    assert bool(b1_dec["same_station"])
    assert np.isfinite(b1_dec["jaccard"])

    s2_mam = pairs.loc[("VAL-S2-MAM08", "VAL-S2-MAM27")]
    assert bool(s2_mam["flag_s2_mam_pair"])
    assert s2_mam["center_date_distance_days"] == 19
    assert s2_mam["jaccard"] == pytest.approx(161 / 199)

    cross = pairs.loc[("VAL-B1-DEC02", "VAL-P3-DEC02")]
    assert not bool(cross["same_station"])
    assert bool(cross["flag_same_center_date_cross_station"])
    assert cross["jaccard"] == pytest.approx(1.0)

    isolated = pairs.loc[("VAL-B1-DEC02", "VAL-B1-JUL")]
    assert isolated["jaccard"] == 0.0
    assert not bool(isolated["has_temporal_overlap"])


def test_overlap_components_separate_nonoverlapping_same_station_windows() -> None:
    audit = audit_validation_anchor_independence(_synthetic_anchors())
    same_station = audit.overlap_components.loc[
        audit.overlap_components["graph_scope"].eq("same_station")
    ]
    assert audit.overlap_components["overlap_component_id"].is_unique
    b1 = same_station.loc[same_station["station_id"].eq("B1")]
    assert set(b1["anchor_count"]) == {2, 1}
    overlapping = b1.loc[b1["has_overlap"]]
    assert len(overlapping) == 1
    assert "VAL-B1-DEC02" in overlapping.iloc[0]["anchor_ids"]
    assert "VAL-B1-DEC19" in overlapping.iloc[0]["anchor_ids"]
    assert "VAL-B1-JUL" not in overlapping.iloc[0]["anchor_ids"]
    assert audit.summary["n_same_station_overlap_components"] == 2


def test_unique_date_coverage_marks_shared_and_exclusive_days() -> None:
    audit = audit_validation_anchor_independence(_synthetic_anchors())
    coverage = audit.unique_date_coverage
    assert coverage["anchors_covering_date"].ge(1).all()
    shared = coverage.loc[coverage["date"].eq("2016-12-02")]
    assert len(shared) == 1
    assert shared.iloc[0]["stations_covering_date"] == 2
    assert bool(shared.iloc[0]["cross_station_coverage"])
    assert "VAL-B1-DEC02" in shared.iloc[0]["anchor_ids"]
    assert "VAL-P3-DEC02" in shared.iloc[0]["anchor_ids"]


def test_ranking_placeholders_are_pending_and_unranked() -> None:
    audit = audit_validation_anchor_independence(_synthetic_anchors())
    for frame in (
        audit.leave_one_anchor_out_ranking,
        audit.leave_one_station_out_ranking,
        audit.bootstrap_rank_probabilities,
    ):
        assert len(frame) == 1
        assert bool(frame.iloc[0]["pending_validation_results"])
        assert frame.iloc[0]["reason"] == PENDING_RANKING_REASON
        assert frame["rank"].isna().all()
    assert audit.summary["pending_validation_results"] is True
    assert audit.summary["performance_evidence"] is False


def test_missing_columns_and_duplicate_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="requires columns"):
        audit_validation_anchor_independence(pd.DataFrame({"anchor_id": ["A"]}))
    broken = _synthetic_anchors()
    broken.loc[1, "anchor_id"] = broken.loc[0, "anchor_id"]
    with pytest.raises(ValueError, match="unique"):
        audit_validation_anchor_independence(broken)
    empty = _synthetic_anchors().iloc[0:0]
    with pytest.raises(ValueError, match="empty"):
        audit_validation_anchor_independence(empty)


def test_write_artifacts_include_required_names(tmp_path: Path) -> None:
    audit = write_anchor_independence_audit(_synthetic_anchors(), tmp_path)
    expected = {
        "anchor_pairwise_jaccard.csv",
        "anchor_same_station_pairwise_jaccard.csv",
        "anchor_overlap_components.csv",
        "anchor_unique_date_coverage.csv",
        "anchor_year_coverage.csv",
        "anchor_station_effective_n.csv",
        "anchor_named_findings.csv",
        "leave_one_anchor_out_ranking.csv",
        "leave_one_station_out_ranking.csv",
        "bootstrap_rank_probabilities.csv",
    }
    assert set(audit.artifact_frames()) == expected
    for name in expected:
        assert (tmp_path / name).is_file()
    ranking = pd.read_csv(tmp_path / "leave_one_anchor_out_ranking.csv")
    assert ranking.iloc[0]["pending_validation_results"] in {True, "True", "true"}


def test_real_validation_catalog_produces_finite_outputs() -> None:
    catalog = pd.read_csv(VALIDATION_ANCHORS)
    audit = audit_validation_anchor_independence(catalog)
    assert len(catalog) == 15
    assert np.isfinite(audit.pairwise["jaccard"]).all()
    assert audit.pairwise["jaccard"].between(0.0, 1.0).all()
    same_station = audit.pairwise.loc[audit.pairwise["same_station"]]
    assert len(same_station) == 30
    assert audit.summary["max_same_station_jaccard"] == pytest.approx(
        float(same_station["jaccard"].max())
    )
    assert audit.summary["n_same_station_overlap_components"] >= 1
    assert audit.summary["n_unique_covered_dates"] > 0
    assert audit.unique_date_coverage["anchors_covering_date"].ge(1).all()
    b1_dec = same_station.loc[same_station["flag_b1_december_2016_pair"]]
    assert len(b1_dec) == 1
    assert int(b1_dec.iloc[0]["overlap_days"]) == 163
    assert float(b1_dec.iloc[0]["jaccard"]) == pytest.approx(163 / 197)
    assert float(b1_dec.iloc[0]["jaccard"]) == pytest.approx(0.827, abs=0.001)
    named = audit.named_findings.set_index("finding_id")
    b1_named = named.loc["b1_december_2016_double_anchor"]
    assert b1_named["left_anchor_label"] == "B1-R0105"
    assert b1_named["right_anchor_label"] == "B1-R0101"
    assert b1_named["left_center_date"] == "2016-12-02"
    assert b1_named["right_center_date"] == "2016-12-19"
    assert int(b1_named["overlap_days"]) == 163
    assert float(b1_named["jaccard"]) == pytest.approx(0.827, abs=0.001)
    assert "B1-R0105" in str(b1_named["finding_name"])
    assert len(audit.same_station_pairwise) == 30
    assert int(audit.same_station_pairwise["flag_jaccard_ge_0_5"].sum()) == 7
    assert JACCARD_HIGH_THRESHOLD == 0.5
    years = set(audit.year_coverage["unique_years"])
    assert years == {"2016|2017"}
    assert audit.year_coverage["n_years"].eq(2).all()
    assert audit.year_coverage["n_anchors"].eq(5).all()
    assert (~audit.year_coverage["years_equal_n_anchors"]).all()
    ess = audit.station_effective_n.set_index("station_id")
    assert ess.loc["B1", "effective_n"] == pytest.approx(422 / 180)
    assert ess.loc["S2", "effective_n"] == pytest.approx(448 / 180)
    assert ess.loc["P3", "effective_n"] == pytest.approx(534 / 180)
    identical = named.loc["cross_station_identical_center"]
    if isinstance(identical, pd.DataFrame):
        identical = identical.iloc[0]
    assert {identical["left_anchor_label"], identical["right_anchor_label"]} == {
        "B1-R0102",
        "S2-R0105",
    }
    assert identical["left_center_date"] == "2017-03-27"
    assert "105" in named.loc["validation_units_not_iid", "statement"]
    assert IID_WARNING in audit.summary["iid_warning"]
    assert audit.summary["must_not_treat_units_as_iid"] is True
    s2_mam = same_station.loc[same_station["flag_s2_mam_pair"]]
    assert len(s2_mam) == 1
    cross_same = audit.pairwise.loc[
        audit.pairwise["flag_same_center_date_cross_station"]
    ]
    assert not cross_same.empty
    assert NEARBY_CENTER_DAYS == 14
    assert bool(audit.leave_one_anchor_out_ranking.iloc[0]["pending_validation_results"])
    json.dumps(audit.summary)
