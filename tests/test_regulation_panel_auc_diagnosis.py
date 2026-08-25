import hashlib
import json
import runpy
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
    DIAGNOSIS_LABEL,
    DOES_NOT_REOPEN_FREEZE,
    FROZEN_PRIMARY_POOLED_AUC,
    MECHANISM,
    assert_matches_frozen_primary_pooled_auc,
    diagnose_loeo_auc,
    fold_auc_table,
    pooled_oof_auc,
    within_fold_auc,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_PANEL = ROOT / "results/regulation_panel_v1_legacy_transport"
FROZEN_PREDICTIONS = FROZEN_PANEL / "leave_ecoregion_out_predictions.csv"
FROZEN_MANIFEST = FROZEN_PANEL / "artifact_manifest.json"

EXPECTED_MEAN_WITHIN_FOLD_AUC = 0.5256536889168535
EXPECTED_MEDIAN_WITHIN_FOLD_AUC = 0.5132377275234418
EXPECTED_MIN_WITHIN_FOLD_AUC = 0.13205645161290322
EXPECTED_MAX_WITHIN_FOLD_AUC = 0.7546296296296297
EXPECTED_BASE_RATE_MEDIAN_CORR = -0.6709991179809832


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _synthetic_calibration_drift_predictions() -> pd.DataFrame:
    rows = []
    for index, probability in enumerate((0.10, 0.18)):
        rows.append(
            {
                "station_id": f"A0{index}",
                "AGGECOREGION": "HighPrev",
                "upstream_major_dam_2009": 0,
                "oof_probability": probability,
                "held_out_ecoregion": "HighPrev",
            }
        )
    high_prev_positives = (0.30, 0.34, 0.38, 0.42, 0.44, 0.48, 0.50, 0.54)
    for index, probability in enumerate(high_prev_positives):
        rows.append(
            {
                "station_id": f"A1{index}",
                "AGGECOREGION": "HighPrev",
                "upstream_major_dam_2009": 1,
                "oof_probability": probability,
                "held_out_ecoregion": "HighPrev",
            }
        )
    low_prev_negatives = (0.60, 0.64, 0.68, 0.70, 0.72, 0.74, 0.76, 0.78)
    for index, probability in enumerate(low_prev_negatives):
        rows.append(
            {
                "station_id": f"B0{index}",
                "AGGECOREGION": "LowPrev",
                "upstream_major_dam_2009": 0,
                "oof_probability": probability,
                "held_out_ecoregion": "LowPrev",
            }
        )
    for index, probability in enumerate((0.82, 0.90)):
        rows.append(
            {
                "station_id": f"B1{index}",
                "AGGECOREGION": "LowPrev",
                "upstream_major_dam_2009": 1,
                "oof_probability": probability,
                "held_out_ecoregion": "LowPrev",
            }
        )
    return pd.DataFrame(rows)


def test_frozen_predictions_match_verified_loeo_auc_diagnosis() -> None:
    predictions = pd.read_csv(FROZEN_PREDICTIONS)
    assert len(predictions) == 335
    folds = fold_auc_table(predictions)
    assert len(folds) == 10
    alaska = folds.loc[folds["held_out_ecoregion"].eq("Alaska")].iloc[0]
    assert pd.isna(alaska["within_fold_auc"])
    assert folds.iloc[-1]["held_out_ecoregion"] == "Alaska"
    diagnosis = diagnose_loeo_auc(predictions, require_frozen_primary=True)
    summary = diagnosis["summary"]
    post_hoc = diagnosis["post_hoc"]
    assert diagnosis["diagnosis"] == DIAGNOSIS_LABEL
    assert diagnosis["does_not_reopen_freeze"] is DOES_NOT_REOPEN_FREEZE
    assert diagnosis["evidence_role"] == "post_hoc"
    assert diagnosis["formal_evidence"] is False
    assert diagnosis["mechanism"] == MECHANISM
    assert diagnosis["frozen_primary_pooled_auc"] == FROZEN_PRIMARY_POOLED_AUC
    assert summary["n"] == 335
    assert summary["n_folds"] == 10
    assert summary["n_defined_within_fold_auc"] == 9
    assert summary["pooled_oof_auc"] == FROZEN_PRIMARY_POOLED_AUC
    assert summary["pooled_oof_auc_matches_frozen_primary"] is True
    assert pooled_oof_auc(predictions) == FROZEN_PRIMARY_POOLED_AUC
    assert post_hoc["mean_within_fold_auc"] == pytest.approx(
        EXPECTED_MEAN_WITHIN_FOLD_AUC
    )
    assert post_hoc["median_within_fold_auc"] == pytest.approx(
        EXPECTED_MEDIAN_WITHIN_FOLD_AUC
    )
    assert post_hoc["min_within_fold_auc"] == pytest.approx(
        EXPECTED_MIN_WITHIN_FOLD_AUC
    )
    assert post_hoc["max_within_fold_auc"] == pytest.approx(
        EXPECTED_MAX_WITHIN_FOLD_AUC
    )
    assert post_hoc["min_within_fold_ecoregion"] == "SEPlains"
    assert post_hoc["max_within_fold_ecoregion"] == "NorthEast"
    assert post_hoc["base_rate_vs_oof_probability_median_pearson_r"] == pytest.approx(
        EXPECTED_BASE_RATE_MEDIAN_CORR
    )
    assert (
        round(post_hoc["base_rate_vs_oof_probability_median_pearson_r"], 3) == -0.671
    )
    assert post_hoc["highest_oof_probability_median_ecoregion"] == "Alaska"
    assert post_hoc["lowest_oof_probability_median_ecoregion"] == "WestPlains"


def test_frozen_panel_artifact_hashes_match_on_disk_files() -> None:
    manifest = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
    for record in manifest["artifacts"]:
        path = ROOT / record["path"]
        assert path.is_file(), path
        assert path.stat().st_size == record["bytes"], path
        assert _sha256(path) == record["sha256"], path


def test_synthetic_two_group_case_shows_pooled_auc_defect() -> None:
    predictions = _synthetic_calibration_drift_predictions()
    folds = fold_auc_table(predictions)
    assert (folds["within_fold_auc"] > 0.6).all()
    pooled = pooled_oof_auc(predictions)
    assert pooled < 0.5
    diagnosis = diagnose_loeo_auc(predictions)
    assert diagnosis["summary"]["pooled_oof_auc"] == pytest.approx(pooled)
    assert diagnosis["summary"]["pooled_oof_auc_matches_frozen_primary"] is False
    with pytest.raises(ValueError, match="differs from frozen primary"):
        diagnose_loeo_auc(predictions, require_frozen_primary=True)


def test_single_class_fold_returns_undefined_auc_without_crashing() -> None:
    predictions = pd.DataFrame(
        {
            "station_id": ["A1", "A2", "B1", "B2", "B3"],
            "AGGECOREGION": ["A", "A", "B", "B", "B"],
            "upstream_major_dam_2009": [0, 0, 0, 1, 1],
            "oof_probability": [0.2, 0.3, 0.1, 0.8, 0.9],
            "held_out_ecoregion": ["A", "A", "B", "B", "B"],
        }
    )
    assert pd.isna(within_fold_auc([0, 0], [0.2, 0.3]))
    folds = fold_auc_table(predictions)
    single = folds.loc[folds["held_out_ecoregion"].eq("A")].iloc[0]
    defined = folds.loc[folds["held_out_ecoregion"].eq("B")].iloc[0]
    assert pd.isna(single["within_fold_auc"])
    assert defined["within_fold_auc"] == pytest.approx(1.0)
    diagnosis = diagnose_loeo_auc(predictions)
    assert diagnosis["summary"]["n_defined_within_fold_auc"] == 1
    assert diagnosis["summary"]["pooled_oof_auc"] == pytest.approx(
        pooled_oof_auc(predictions)
    )
    assert_matches_frozen_primary_pooled_auc(FROZEN_PRIMARY_POOLED_AUC)


def test_script_writes_revision_artifacts_and_rejects_frozen_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = ROOT / "scripts/41_diagnose_regulation_panel_auc.py"
    output_dir = tmp_path / "revision"
    monkeypatch.setattr(
        "sys.argv",
        [
            str(script),
            "--predictions",
            str(FROZEN_PREDICTIONS),
            "--output-dir",
            str(output_dir),
        ],
    )
    runpy.run_path(str(script), run_name="__main__")
    folds = pd.read_csv(output_dir / "loeo_within_fold_auc.csv")
    payload = json.loads(
        (output_dir / "loeo_auc_metric_diagnosis.json").read_text(encoding="utf-8")
    )
    assert len(folds) == 10
    assert payload["summary"]["pooled_oof_auc"] == FROZEN_PRIMARY_POOLED_AUC
    assert payload["formal_evidence"] is False
    assert payload["does_not_reopen_freeze"] is True
    namespace = runpy.run_path(str(script))
    with pytest.raises(ValueError, match="frozen regulation-panel directory"):
        namespace["write_diagnosis"](FROZEN_PREDICTIONS, FROZEN_PANEL)
