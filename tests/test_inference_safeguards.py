from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from stream_recoverability.analysis.inference_safeguards import (
    add_guarded_climatology_skill,
    anchor_year_cluster_bootstrap,
    anchor_year_frontier_bootstrap,
    assess_application_boundary,
    audit_mask_anchor_overlap,
    average_training_seeds_by_anchor,
    benjamini_hochberg_by_family,
    raw_and_monotone_frontier,
    resolve_climatology_denominator_threshold,
    weighted_pava,
)


def test_overlap_audit_counts_cells_and_transitive_anchor_clusters() -> None:
    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    first = np.zeros((6, 1, 2), dtype=bool)
    second = np.zeros_like(first)
    third = np.zeros_like(first)
    isolated = np.zeros_like(first)
    first[0:3, 0, 0] = True
    second[2:5, 0, 0] = True
    # Temporal overlap with `second`, but no exact-cell overlap.
    third[4, 0, 1] = True
    isolated[5, 0, 1] = True

    audit = audit_mask_anchor_overlap(
        {
            "third": third,
            "first": first,
            "isolated": isolated,
            "second": second,
        },
        dates=dates,
    )
    pairs = audit.pairwise.set_index(["left_anchor_id", "right_anchor_id"])
    assert pairs.loc[("first", "second"), "temporal_overlap_days"] == 1
    assert pairs.loc[("first", "second"), "cell_overlap_count"] == 1
    assert pairs.loc[("second", "third"), "temporal_overlap_days"] == 1
    assert pairs.loc[("second", "third"), "cell_overlap_count"] == 0
    assert pairs.loc[("first", "second"), "temporal_overlap_start"] == dates[2]
    assert pairs.loc[("first", "second"), "temporal_overlap_start_index"] == 2

    anchors = audit.anchors.set_index("anchor_id")
    assert (
        anchors.loc["first", "overlap_cluster_id"]
        == anchors.loc["second", "overlap_cluster_id"]
        == anchors.loc["third", "overlap_cluster_id"]
    )
    assert anchors.loc["first", "overlap_cluster_size"] == 3
    assert anchors.loc["isolated", "overlap_cluster_size"] == 1
    assert audit.summary["summed_masked_cells"] == 8
    assert audit.summary["effective_unique_masked_cells"] == 7
    assert audit.summary["duplicate_cell_burden"] == 1
    assert np.isclose(anchors["effective_unique_masked_cells"].sum(), 7.0)
    assert "anchors_not_independent" in audit.summary["flags"]
    coverage = audit.unique_date_coverage.set_index("date_index")
    assert coverage.loc[2, "anchors_covering_date"] == 2
    assert coverage.loc[2, "unique_masked_cells"] == 1
    assert coverage.loc[2, "effective_cell_replication"] == 2.0
    assert coverage.loc[2, "year"] == 2020
    assert coverage.loc[2, "season"] == "DJF"
    assert coverage.loc[4, "anchors_covering_date"] == 2
    assert coverage.loc[4, "unique_masked_cells"] == 2
    assert coverage.loc[4, "effective_cell_replication"] == 1.0
    assert set(audit.artifact_frames()) == {
        "pairwise_jaccard.csv",
        "unique_date_coverage.csv",
        "effective_replication_summary.csv",
    }
    assert audit.summary["mean_jaccard"] == pytest.approx(0.2 / 6.0)
    assert audit.summary["max_overlap"] == pytest.approx(1.0 / 3.0)
    assert audit.summary["max_cell_overlap_count"] == 1
    assert audit.summary["max_temporal_overlap_days"] == 1

    repeated = audit_mask_anchor_overlap(
        {
            "isolated": isolated,
            "second": second,
            "first": first,
            "third": third,
        },
        dates=dates,
    )
    pd.testing.assert_frame_equal(audit.pairwise, repeated.pairwise)
    pd.testing.assert_frame_equal(audit.anchors, repeated.anchors)
    pd.testing.assert_frame_equal(audit.clusters, repeated.clusters)
    pd.testing.assert_frame_equal(
        audit.unique_date_coverage, repeated.unique_date_coverage
    )
    pd.testing.assert_frame_equal(
        audit.effective_replication_summary,
        repeated.effective_replication_summary,
    )
    assert audit.summary == repeated.summary

    empty = audit_mask_anchor_overlap({"empty": np.zeros((3, 1), dtype=bool)})
    assert empty.pairwise.empty
    assert "temporal_overlap_days" in empty.pairwise
    assert empty.anchors.loc[0, "empty_mask_flag"]
    assert empty.summary["n_empty_masks"] == 1


def _pseudoreplicated_events(duplicate_each_seed: int = 1) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    anchors = (
        ("A1", "B1", 2019, 1.0),
        ("A2", "B1", 2019, 5.0),
        ("A3", "B1", 2020, 9.0),
        ("A4", "B1", 2020, 13.0),
        ("A5", "S2", 2019, 17.0),
        ("A6", "S2", 2019, 21.0),
    )
    for anchor_id, station_id, year, anchor_value in anchors:
        for training_seed, seed_offset in ((11, -0.5), (22, 0.0), (33, 0.5)):
            for _ in range(duplicate_each_seed):
                rows.append(
                    {
                        "experiment": "SCI_DENSE",
                        "gap_length": 30,
                        "model": "candidate",
                        "anchor_id": anchor_id,
                        "station_id": station_id,
                        "year": year,
                        "training_seed": training_seed,
                        "MAE": anchor_value + seed_offset,
                    }
                )
                rows.append(
                    {
                        "experiment": "SCI_DENSE",
                        "gap_length": 30,
                        "model": "climatology",
                        "anchor_id": anchor_id,
                        "station_id": station_id,
                        "year": year,
                        "training_seed": training_seed,
                        "MAE": anchor_value + 2.0 + seed_offset,
                    }
                )
    return pd.DataFrame(rows)


def test_anchor_bootstrap_averages_seeds_before_resampling_and_ignores_duplicates() -> (
    None
):
    ordinary = anchor_year_cluster_bootstrap(
        _pseudoreplicated_events(),
        value_col="MAE",
        group_cols=("experiment", "gap_length"),
        baseline_model="climatology",
        n_boot=500,
        seed=71,
    )
    duplicated = anchor_year_cluster_bootstrap(
        _pseudoreplicated_events(duplicate_each_seed=8),
        value_col="MAE",
        group_cols=("experiment", "gap_length"),
        baseline_model="climatology",
        n_boot=500,
        seed=71,
    )
    estimate = ordinary.estimates.iloc[0]
    duplicate_estimate = duplicated.estimates.iloc[0]
    assert estimate["estimate"] == pytest.approx(-2.0)
    assert estimate["n_anchor_year_units"] == 6
    assert estimate["n_station_year_strata"] == 3
    assert estimate["n_source_rows"] == 36
    assert duplicate_estimate["n_anchor_year_units"] == 6
    assert duplicate_estimate["n_source_rows"] == 36 * 8
    assert duplicate_estimate["estimate"] == estimate["estimate"]
    assert duplicate_estimate["ci_lower"] == estimate["ci_lower"]
    assert duplicate_estimate["ci_upper"] == estimate["ci_upper"]
    assert len(ordinary.collapsed) == 12  # six anchors x two models, not seeds
    assert ordinary.collapsed["training_seeds_averaged"].all()

    shuffled = anchor_year_cluster_bootstrap(
        _pseudoreplicated_events().sample(frac=1.0, random_state=9),
        value_col="MAE",
        group_cols=("experiment", "gap_length"),
        baseline_model="climatology",
        n_boot=500,
        seed=71,
    )
    pd.testing.assert_frame_equal(ordinary.collapsed, shuffled.collapsed)
    pd.testing.assert_frame_equal(ordinary.estimates, shuffled.estimates)

    unseeded = _pseudoreplicated_events().drop_duplicates(["model", "anchor_id"])
    unseeded["training_seed"] = np.nan
    deterministic = average_training_seeds_by_anchor(unseeded, value_col="MAE")
    assert len(deterministic) == 12
    assert (deterministic["n_training_seeds"] == 0).all()
    assert (deterministic["n_seed_units"] == 1).all()


def test_weighted_pava_preserves_raw_frontier_and_marks_adjustments() -> None:
    values = np.array([0.8, 0.4, 0.6, -0.2])
    weights = np.array([1.0, 1.0, 3.0, 1.0])
    fitted, blocks = weighted_pava(values, weights)
    assert fitted == pytest.approx([0.8, 0.55, 0.55, -0.2])
    assert blocks.tolist() == [1, 2, 2, 3]

    source = pd.DataFrame(
        {
            "station_id": ["B1"] * 4 + ["S2"] * 4,
            "target": ["T"] * 8,
            "model": ["candidate"] * 8,
            "gap_length": [10, 30, 90, 180] * 2,
            "mean_skill": [0.8, 0.4, 0.6, -0.2, 0.9, 0.7, 0.3, 0.1],
            "anchor_count": [1, 1, 3, 1, 2, 2, 2, 2],
            "note": list("abcdefgh"),
        }
    )
    result = raw_and_monotone_frontier(source, weight_col="anchor_count", threshold=0.0)
    pd.testing.assert_series_equal(
        result.curve["raw_frontier_value"],
        source["mean_skill"].rename("raw_frontier_value"),
    )
    assert result.curve.loc[:3, "monotone_frontier_value"].tolist() == pytest.approx(
        [0.8, 0.55, 0.55, -0.2]
    )
    assert result.curve.loc[:3, "frontier_adjusted"].tolist() == [
        False,
        True,
        True,
        False,
    ]
    assert result.curve["note"].tolist() == list("abcdefgh")
    summary = result.summary.set_index("station_id")
    assert summary.loc["B1", "n_adjusted_gap_lengths"] == 2
    assert summary.loc["S2", "n_adjusted_gap_lengths"] == 0
    assert summary.loc["S2", "monotone_frontier_censoring"] == "right"


def test_frontier_bootstrap_reuses_one_cluster_draw_for_the_complete_curve() -> None:
    anchor_curves = {
        "A1": ("C1", {10: 0.9, 30: 0.4, 90: -0.1}),
        "A2": ("C1", {10: 0.8, 30: 0.6, 90: -0.2}),
        "A3": ("C2", {10: 0.7, 30: 0.2, 90: 0.1}),
        "A4": ("C3", {10: 1.0, 30: 0.1, 90: -0.4}),
        "A5": ("C4", {10: 0.6, 30: 0.3}),  # incomplete as a whole unit
    }
    rows: list[dict[str, object]] = []
    for anchor_id, (cluster_id, values) in anchor_curves.items():
        for gap, value in values.items():
            for training_seed, offset in ((11, -0.01), (22, 0.01)):
                rows.append(
                    {
                        "station_id": "B1",
                        "target": "T",
                        "model": "candidate",
                        "anchor_id": anchor_id,
                        "overlap_cluster_id": cluster_id,
                        "year": 2020,
                        "gap_length": gap,
                        "training_seed": training_seed,
                        "skill": value + offset,
                    }
                )
    result = anchor_year_frontier_bootstrap(
        pd.DataFrame(rows),
        overlap_cluster_col="overlap_cluster_id",
        required_gap_lengths=(10, 30, 90),
        n_boot=40,
        seed=19,
    )
    summary = result.summary.iloc[0]
    assert summary["n_complete_anchor_curves"] == 4
    assert summary["n_incomplete_anchor_curves_excluded"] == 1
    assert summary["n_bootstrap_clusters"] == 3
    assert summary["n_bootstrap_samples"] == 40
    assert result.collapsed["frontier_complete_curve"].sum() == 12
    assert len(result.samples) == 40 * 3
    assert set(result.artifact_frames()) == {"frontier_bootstrap_samples.parquet"}

    complete_values = {
        anchor: values
        for anchor, (_, values) in anchor_curves.items()
        if set(values) == {10, 30, 90}
    }
    for _, sample in result.samples.groupby("bootstrap_id", sort=True):
        assert sample["gap_length"].tolist() == [10.0, 30.0, 90.0]
        assert sample["sampled_anchor_ids"].nunique() == 1
        assert sample["sampled_cluster_ids"].nunique() == 1
        sampled_anchors = sample.iloc[0]["sampled_anchor_ids"]
        expected = [
            np.mean([complete_values[anchor][gap] for anchor in sampled_anchors])
            for gap in (10, 30, 90)
        ]
        assert sample["bootstrap_raw_value"].tolist() == pytest.approx(expected)
        assert sample["complete_cross_gap_curve"].all()
        assert sample["joint_cross_gap_resampling"].all()


def test_climatology_guard_and_absent_application_threshold_withhold_boundaries() -> (
    None
):
    errors = pd.DataFrame(
        {
            "model_mae": [0.5, 0.1, 0.2, np.nan],
            "climatology_mae": [1.0, 1e-8, 0.0, 1.0],
        }
    )
    undeclared = add_guarded_climatology_skill(errors, near_zero_threshold=None)
    assert undeclared["skill"].isna().all()
    assert set(undeclared["climatology_denominator_status"]) == {
        "threshold_not_declared"
    }

    guarded = add_guarded_climatology_skill(errors, near_zero_threshold=1e-6)
    assert guarded.loc[0, "skill"] == pytest.approx(0.5)
    assert guarded.loc[1, "climatology_denominator_status"] == (
        "near_zero_climatology_error"
    )
    assert guarded.loc[2, "climatology_denominator_status"] == (
        "near_zero_climatology_error"
    )
    assert guarded.loc[3, "climatology_denominator_status"] == ("nonfinite_model_error")
    assert guarded.loc[1:, "skill"].isna().all()

    design = yaml.safe_load(
        Path("configs/design_freeze_v1.yaml").read_text(encoding="utf-8")
    )
    declaration = design["statistics"]["climatology_denominator_guard"]
    assert resolve_climatology_denominator_threshold(declaration, "T") == 0.05
    assert resolve_climatology_denominator_threshold(declaration, "B1_F") == 0.5
    assert resolve_climatology_denominator_threshold(declaration, "L") == 0.005
    with pytest.raises(ValueError, match="no predeclared"):
        resolve_climatology_denominator_threshold(declaration, "Ta")

    absent = assess_application_boundary(
        pd.DataFrame({"gap_length": [10, 30], "MAE": [0.2, 0.4]}), None
    )
    assert absent["application_threshold_status"] == "not_declared"
    assert np.isnan(absent["operational_boundary_days"])
    assert absent["operational_boundary_claim_allowed"] is False

    declared = assess_application_boundary(
        pd.DataFrame({"gap_length": [10, 30, 90], "MAE": [0.2, 0.4, 0.8]}),
        {"MAE": ("<=", 0.5)},
    )
    assert declared["application_threshold_status"] == "declared"
    assert declared["operational_boundary_days"] == 30
    assert declared["operational_boundary_upper_days"] == 90


def test_bh_is_applied_within_named_families_only() -> None:
    hypotheses = pd.DataFrame(
        {
            "hypothesis_family": ["frontier", "frontier", "resilience", "resilience"],
            "hypothesis": ["f1", "f2", "r1", "r2"],
            "p_value": [0.01, 0.04, 0.03, np.nan],
        }
    )
    adjusted = benjamini_hochberg_by_family(hypotheses)
    assert adjusted["p_bh"].tolist()[:3] == pytest.approx([0.02, 0.04, 0.03])
    assert np.isnan(adjusted.loc[3, "p_bh"])
    assert adjusted.loc[0, "bh_finite_hypotheses"] == 2
    assert adjusted.loc[2, "bh_finite_hypotheses"] == 1
    assert set(adjusted["bh_scope"]) == {"within_named_hypothesis_family"}

    unnamed = hypotheses.copy()
    unnamed.loc[0, "hypothesis_family"] = ""
    with pytest.raises(ValueError, match="non-empty named family"):
        benjamini_hochberg_by_family(unnamed)
