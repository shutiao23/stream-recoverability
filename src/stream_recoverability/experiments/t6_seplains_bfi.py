"""T6 post-hoc mechanism slice: SEPlains reversal × GAGES-II BFI.

Uses the frozen regulation-panel station table and leave-one-ecoregion-out
predictions.  This is a preregistered v9 ``t6_honest_boundary`` analysis, not a
passed confirmatory endpoint and not a causal groundwater claim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from stream_recoverability.analysis.regulation_panel import load_gages_ii_bfi
from stream_recoverability.analysis.regulation_panel_auc_diagnosis import (
    within_fold_auc,
)

SEPLAINS = "SEPlains"
FROZEN_SEPLAINS_BASELINE_AUC = 0.13205645161290322


def _zscore_train_apply(
    train_x: np.ndarray, test_x: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0, ddof=0)
    if np.any(scale <= 0):
        raise ValueError("zero-variance feature in training fold")
    return (train_x - mean) / scale, (test_x - mean) / scale


def leave_ecoregion_out_with_features(
    metrics: pd.DataFrame,
    feature_columns: list[str],
    *,
    label_col: str = "upstream_major_dam_2009",
    region_col: str = "AGGECOREGION",
    station_col: str = "station_id",
) -> pd.DataFrame:
    """LOEO logistic scores on z-scored ``feature_columns`` within each fold."""

    required = [station_col, region_col, label_col, *feature_columns]
    missing = [column for column in required if column not in metrics.columns]
    if missing:
        raise ValueError(f"metrics missing columns: {missing}")
    data = metrics.dropna(subset=required).copy()
    predictions: list[pd.DataFrame] = []
    for region in sorted(data[region_col].astype(str).unique()):
        test = data[region_col].astype(str).eq(region)
        train = ~test
        train_labels = data.loc[train, label_col]
        if train_labels.nunique() < 2:
            raise RuntimeError(f"invalid leave-ecoregion-out training fold: {region}")
        train_x = data.loc[train, feature_columns].to_numpy(dtype=float)
        test_x = data.loc[test, feature_columns].to_numpy(dtype=float)
        train_z, test_z = _zscore_train_apply(train_x, test_x)
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=10000)
        model.fit(train_z, train_labels.astype(int))
        fold = data.loc[test, [station_col, region_col, label_col]].copy()
        fold["oof_probability"] = model.predict_proba(test_z)[:, 1]
        fold["held_out_ecoregion"] = region
        predictions.append(fold)
    return pd.concat(predictions, ignore_index=True)


def fold_auc_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for region, fold in predictions.groupby("held_out_ecoregion", observed=True):
        labels = pd.to_numeric(fold["upstream_major_dam_2009"], errors="coerce")
        scores = pd.to_numeric(fold["oof_probability"], errors="coerce")
        rows.append(
            {
                "held_out_ecoregion": str(region),
                "n": int(len(fold)),
                "base_rate": float(labels.mean()) if len(labels) else float("nan"),
                "within_fold_auc": within_fold_auc(labels, scores),
            }
        )
    return pd.DataFrame(rows).sort_values("held_out_ecoregion", kind="mergesort")


def partial_correlation(
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    control_cols: list[str],
) -> dict[str, float]:
    """Pearson partial correlation of ``x_col`` and ``y_col`` given ``control_cols``."""

    work = frame[[x_col, y_col, *control_cols]].dropna().copy()
    if len(work) < len(control_cols) + 3:
        return {"n": float(len(work)), "partial_r": float("nan"), "p_value": float("nan")}
  # Residualize x and y on controls.
    controls = work[control_cols].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(work)), controls])
    x = work[x_col].to_numpy(dtype=float)
    y = work[y_col].to_numpy(dtype=float)
    x_resid = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
    y_resid = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    if np.std(x_resid) <= 0 or np.std(y_resid) <= 0:
        return {"n": float(len(work)), "partial_r": float("nan"), "p_value": float("nan")}
    r, p_value = stats.pearsonr(x_resid, y_resid)
    return {"n": float(len(work)), "partial_r": float(r), "p_value": float(p_value)}


def bfi_stratified_memory_direction(frame: pd.DataFrame) -> dict[str, Any]:
    """Sign of memory–range index vs dam label within BFI tertiles."""

    work = frame.dropna(
        subset=["BFI_AVE", "memory_range_index_per_degC", "upstream_major_dam_2009"]
    ).copy()
    if work.empty:
        return {"n": 0, "strata": [], "direction_consistent": False}
    work["bfi_tertile"] = pd.qcut(
        work["BFI_AVE"], q=3, labels=["low", "mid", "high"], duplicates="drop"
    )
    strata: list[dict[str, Any]] = []
    for label, piece in work.groupby("bfi_tertile", observed=True):
        if piece["upstream_major_dam_2009"].nunique() < 2:
            direction = float("nan")
            auc = float("nan")
        else:
            auc = float(
                roc_auc_score(
                    piece["upstream_major_dam_2009"],
                    piece["memory_range_index_per_degC"],
                )
            )
            direction = float(auc - 0.5)
        strata.append(
            {
                "bfi_tertile": str(label),
                "n": int(len(piece)),
                "rank_auc_memory_vs_dam": auc,
                "direction_above_chance": bool(np.isfinite(auc) and auc > 0.5),
            }
        )
    finite = [row for row in strata if np.isfinite(row["rank_auc_memory_vs_dam"])]
    signs = {bool(row["direction_above_chance"]) for row in finite}
    return {
        "n": int(len(work)),
        "strata": strata,
        "direction_consistent": len(signs) <= 1 and bool(finite),
    }


def prepare_metrics_with_bfi(
    station_metrics_path: Path,
    *,
    config_path: Path,
    cache_dir: Path,
) -> pd.DataFrame:
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(station_metrics_path, dtype={"station_id": str})
    metrics["station_id"] = metrics["station_id"].astype(str).str.zfill(8)
    bfi = load_gages_ii_bfi(config, cache_dir, offline=True)
    if bfi.empty:
        raise RuntimeError("GAGES-II BFI table is empty")
    bfi["STAID"] = bfi["STAID"].astype(str).str.zfill(8)
    merged = metrics.merge(
        bfi.rename(columns={"STAID": "station_id"}),
        on="station_id",
        how="left",
        validate="m:1",
    )
    for column, source in (
        ("z_memory_range_index", "memory_range_index_per_degC"),
        ("z_log1p_drainage_area", "DRAIN_SQKM"),
        ("z_bfi", "BFI_AVE"),
    ):
        values = pd.to_numeric(merged[source], errors="coerce")
        if source == "DRAIN_SQKM":
            values = np.log1p(values)
        merged[column] = (values - values.mean()) / values.std(ddof=0)
    return merged


def run_t6_seplains_bfi_analysis(
    *,
    station_metrics_path: Path,
    frozen_predictions_path: Path,
    config_path: Path,
    cache_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = prepare_metrics_with_bfi(
        station_metrics_path,
        config_path=config_path,
        cache_dir=cache_dir,
    )
    n_with_bfi = int(metrics["BFI_AVE"].notna().sum())
    memory_only = leave_ecoregion_out_with_features(
        metrics, ["memory_range_index_per_degC"]
    )
    memory_bfi = leave_ecoregion_out_with_features(
        metrics, ["memory_range_index_per_degC", "BFI_AVE"]
    )
    fold_memory = fold_auc_summary(memory_only)
    fold_memory_bfi = fold_auc_summary(memory_bfi)
    seplains_row = fold_memory.loc[
        fold_memory["held_out_ecoregion"].eq(SEPLAINS)
    ]
    seplains_bfi_row = fold_memory_bfi.loc[
        fold_memory_bfi["held_out_ecoregion"].eq(SEPLAINS)
    ]
    seplains_auc_memory = (
        float(seplains_row["within_fold_auc"].iloc[0]) if not seplains_row.empty else float("nan")
    )
    seplains_auc_memory_bfi = (
        float(seplains_bfi_row["within_fold_auc"].iloc[0])
        if not seplains_bfi_row.empty
        else float("nan")
    )
    eco = pd.get_dummies(metrics["AGGECOREGION"].astype(str), drop_first=True)
    partial_eco = partial_correlation(
        pd.concat([metrics, eco], axis=1),
        "memory_range_index_per_degC",
        "BFI_AVE",
        ["DRAIN_SQKM", *eco.columns.tolist()],
    )
    stratified = bfi_stratified_memory_direction(metrics)
    fold_memory.to_csv(output_dir / "fold_auc_memory_only.csv", index=False)
    fold_memory_bfi.to_csv(output_dir / "fold_auc_memory_plus_bfi.csv", index=False)
    manifest: dict[str, Any] = {
        "experiment": "T6_SEPlains_BFI_mechanism",
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "t6_passed": False,
        "post_hoc": True,
        "preregistered_in": "design_freeze_v9.yaml:t6_honest_boundary",
        "n_stations_with_bfi": n_with_bfi,
        "seplains_within_fold_auc_memory_only": seplains_auc_memory,
        "seplains_within_fold_auc_memory_plus_bfi": seplains_auc_memory_bfi,
        "seplains_auc_delta_with_bfi": float(seplains_auc_memory_bfi - seplains_auc_memory)
        if np.isfinite(seplains_auc_memory) and np.isfinite(seplains_auc_memory_bfi)
        else float("nan"),
        "frozen_seplains_baseline_auc": FROZEN_SEPLAINS_BASELINE_AUC,
        "seplains_recovered_above_0_5_with_bfi": bool(
            np.isfinite(seplains_auc_memory_bfi) and seplains_auc_memory_bfi >= 0.5
        ),
        "bfi_memory_partial_r_controlling_drainage_and_ecoregion": partial_eco,
        "bfi_stratified_memory_direction": stratified,
        "what_this_is": (
            "Post-hoc LOEO re-score asking whether BFI explains the SEPlains "
            "memory-range reversal alongside drainage and ecoregion."
        ),
        "what_this_is_not": (
            "Not T6 passed. Not causal proof. Not a license to reopen the "
            "regulation-panel freeze or claim reservoir identification."
        ),
    }
    frozen = pd.read_csv(frozen_predictions_path, dtype={"station_id": str})
    frozen_seplains = frozen.loc[frozen["held_out_ecoregion"].eq(SEPLAINS)]
    if not frozen_seplains.empty:
        manifest["frozen_seplains_oof_auc_check"] = float(
            roc_auc_score(
                frozen_seplains["upstream_major_dam_2009"],
                frozen_seplains["oof_probability"],
            )
        )
    (output_dir / "t6_seplains_bfi_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "FROZEN_SEPLAINS_BASELINE_AUC",
    "bfi_stratified_memory_direction",
    "fold_auc_summary",
    "leave_ecoregion_out_with_features",
    "partial_correlation",
    "prepare_metrics_with_bfi",
    "run_t6_seplains_bfi_analysis",
]
