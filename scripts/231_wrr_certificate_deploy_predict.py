#!/usr/bin/env python3
"""P0-05/F03: apply the frozen Certificate.predict path to real incomplete years.

Uses only decision-time features. Drops any truth/err/abserr columns before
predict. Writes an amendment under results/wrr_submission_ready/ so the historical
overlap-rule E2 artifacts remain unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP9_FREEZE,
)
from stream_recoverability.experiments.v18_closure.paths import E2_DEPLOYMENT  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready.run_identity import (  # noqa: E402
    run_fail_closed,
)

OUT = ROOT / "results" / "wrr_submission_ready" / "e2_certificate_predict"
CERT_PATH = STEP9_FREEZE / "certificate.joblib"
YEARS_PATH = E2_DEPLOYMENT / "real_station_years.parquet"
TRUTHISH_PREFIXES = ("abserr_", "err_", "metric_", "truth_", "covered", "bound_covered")


def _strip_truth(frame: pd.DataFrame) -> pd.DataFrame:
    drop = [
        c
        for c in frame.columns
        if c.startswith(TRUTHISH_PREFIXES) or c in {"certificate_abs_error", "signed_error"}
    ]
    return frame.drop(columns=drop, errors="ignore")


def work(directory: Path, manifest) -> list[Path]:
    if not YEARS_PATH.is_file():
        raise FileNotFoundError(
            f"missing {YEARS_PATH}; run scripts/211_v18_archive_deployment.py first"
        )
    if not CERT_PATH.is_file():
        raise FileNotFoundError(CERT_PATH)

    years = pd.read_parquet(YEARS_PATH)
    incomplete = years.loc[~years["complete"]].copy()
    features_only = _strip_truth(incomplete)
    model = joblib.load(CERT_PATH)
    if not hasattr(model, "predict"):
        raise RuntimeError("frozen certificate lacks predict(); rebuild screen.py first")

    # Invariance check on a copy with dummy truth columns injected then stripped.
    injected = features_only.copy()
    injected["abserr_doy_climatology"] = 0.0
    injected["err_doy_climatology"] = 0.0
    pred = model.predict(features_only)
    pred_injected = model.predict(_strip_truth(injected))
    if not pred["certificate_choice"].fillna("__na__").equals(
        pred_injected["certificate_choice"].fillna("__na__")
    ):
        raise AssertionError("predict changed when truth-like columns were present then stripped")
    if not pred["certificate_bound"].fillna(-1).equals(pred_injected["certificate_bound"].fillna(-1)):
        raise AssertionError("certificate_bound changed under truth-column injection")

    OUT.mkdir(parents=True, exist_ok=True)
    result = incomplete[
        [c for c in ("network_id", "station_id", "year", "provider", "longest_run", "peak_overlap") if c in incomplete.columns]
    ].copy()
    result["certificate_choice"] = pred["certificate_choice"].to_numpy()
    result["certificate_bound"] = pred["certificate_bound"].to_numpy()
    result["interval_low"] = pred["interval_low"].to_numpy()
    result["interval_high"] = pred["interval_high"].to_numpy()
    # Admission requires a finite reconstructed annual metric (F02). When the
    # archive row already carries metric_<choice>, enforce reconstructability.
    chosen_metric = np.full(len(result), np.nan, dtype=float)
    choices = result["certificate_choice"].astype(str).to_numpy()
    for estimator in sorted(set(choices)):
        if estimator in {"", "nan", "None"}:
            continue
        col = f"metric_{estimator}"
        if col not in incomplete.columns:
            continue
        mask = choices == estimator
        chosen_metric[mask] = pd.to_numeric(incomplete[col], errors="coerce").to_numpy()[mask]
    result["certificate_metric"] = chosen_metric
    result["reconstruction_ok"] = np.isfinite(chosen_metric)
    result["would_admit_at_0.5C"] = (
        (result["certificate_bound"] <= PRIMARY_TOLERANCE_C) & result["reconstruction_ok"]
    )
    result["abstain_reason"] = np.where(
        result["certificate_choice"].isna(),
        "no_supported_estimator",
        np.where(~result["reconstruction_ok"], "chosen_estimator_no_metric", ""),
    )
    result["rule_family"] = "frozen_v17_certificate_predict"
    result["truth_required"] = False

    out_parquet = OUT / "incomplete_certificate_predictions.parquet"
    out_csv = OUT / "incomplete_certificate_predictions_head.csv"
    summary_path = OUT / "summary.json"
    note_path = OUT / "NOTE.md"
    result.to_parquet(out_parquet)
    result.head(50).to_csv(out_csv, index=False)

    n = len(result)
    n_decided = int(result["certificate_choice"].notna().sum())
    summary = {
        "n_incomplete_rows": n,
        "n_with_certificate_choice": n_decided,
        "n_reconstruction_ok": int(result["reconstruction_ok"].sum()),
        "n_admit_with_finite_metric": int(result["would_admit_at_0.5C"].sum()),
        "n_abstain_no_metric": int((result["abstain_reason"] == "chosen_estimator_no_metric").sum()),
        "share_would_admit_at_0.5C": float(result["would_admit_at_0.5C"].mean()) if n else None,
        "certificate_path": str(CERT_PATH.relative_to(ROOT)),
        "identity": (
            "frozen Certificate.predict; no truth/err/abserr used for scoring; "
            "admission requires finite chosen metric (F02)"
        ),
        "vs_e2_overlap_rules": (
            "Historical E2 artifacts use peak-overlap / length thresholds and a separate "
            "risk classifier. This amendment is the verified-model deployment interface."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    note_path.write_text(
        "# Certificate predict deployment amendment\n\n"
        "Generated by `scripts/231_wrr_certificate_deploy_predict.py`.\n"
        "Does not overwrite `results/v18_closure/e2_archive_deployment/`.\n"
        "Report Certificate admissions separately from overlap-rule disagreements.\n"
    )
    # also copy into run directory
    for path in (out_parquet, summary_path, note_path):
        target = directory / path.name
        target.write_bytes(path.read_bytes())
    print(json.dumps(summary, indent=2))
    return [directory / out_parquet.name, directory / summary_path.name]


def main() -> None:
    run_fail_closed(
        "P0-05 Certificate.predict on real incomplete years",
        work,
        inputs=[CERT_PATH, YEARS_PATH],
    )


if __name__ == "__main__":
    main()
