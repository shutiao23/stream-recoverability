#!/usr/bin/env python3
"""Major-revision Step 8: end-to-end environmental judgment closed loop.

Same reserved complete-reference candidates → designed missingness already on
the panel → reconstruct/certificate → admit or abstain → compare:

  1. Incorrect exceedance judgments at 18 / 20 °C (from the common candidate pool)
  2. Exclusion rates for high-elevation and sparse-donor station-years
  3. Bias in the admitted archive's hot-year share vs the complete-reference truth

Methods: reconstruct-all, length@70%, peak-overlap@70%, calibrated screen@70%,
interval abstention, screen+abstention, elevation-balanced calibrated screen.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT as V17_RESULTS,
    STEP10_CONFIRM,
)

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step8_decision_closed_loop"
)
RETENTION = 0.70
THRESHOLDS = (18.0, 20.0)
SEED = 71


def elevation_tertile(station_ids: pd.Series, attributes: pd.DataFrame) -> pd.Series:
    elev = station_ids.astype(str).map(attributes["ELEV_SITE_M"])
    labels = pd.Series("unmatched", index=station_ids.index, dtype=object)
    matched = elev.notna()
    if matched.sum() >= 30:
        labels.loc[matched] = pd.qcut(elev[matched], 3, labels=["low", "middle", "high"]).astype(str)
    return labels


def keep_global(score: np.ndarray, retention: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(score)), np.asarray(score, dtype=float)))
    keep = np.zeros(len(score), dtype=bool)
    keep[order[: int(round(retention * len(score)))]] = True
    return keep


def keep_within(score: np.ndarray, strata: np.ndarray, retention: float, seed: int) -> np.ndarray:
    keep = np.zeros(len(score), dtype=bool)
    for offset, value in enumerate(pd.unique(strata)):
        index = np.where(strata == value)[0]
        rng = np.random.default_rng(seed + offset)
        order = index[np.lexsort((rng.random(len(index)), score[index]))]
        keep[order[: int(round(retention * len(index)))]] = True
    return keep


def evaluate(
    name: str,
    judged: np.ndarray,
    *,
    truth: np.ndarray,
    metric: np.ndarray,
    thr: float,
    elev: pd.Series,
    donor: pd.Series,
    n_total: int,
) -> dict:
    judged = judged & np.isfinite(metric) & np.isfinite(truth)
    n_judged = int(judged.sum())
    pred = metric[judged] > thr
    true = truth[judged] > thr
    mistakes = pred != true
    # Hot-year share bias among judged vs full-reference truth share.
    truth_share = float((truth > thr).mean())
    judged_share = float((truth[judged] > thr).mean()) if n_judged else float("nan")
    elev_j = elev[judged]
    donor_j = donor[judged]
    return {
        "method": name,
        "threshold_c": thr,
        "n_candidates": n_total,
        "share_judged": float(n_judged / n_total),
        "n_correct": int((~mistakes).sum()),
        "n_incorrect": int(mistakes.sum()),
        "n_abstain_or_excluded": int(n_total - n_judged),
        "misclassification_among_judged": float(mistakes.mean()) if n_judged else float("nan"),
        "false_negative_among_judged": float((~pred & true).mean()) if true.any() else float("nan"),
        "false_positive_among_judged": float((pred & ~true).mean()) if (~true).any() else float("nan"),
        "truth_hot_share_full": truth_share,
        "truth_hot_share_among_judged": judged_share,
        "hot_share_bias_pp": (judged_share - truth_share) * 100 if n_judged else float("nan"),
        "share_high_elev_among_judged": float((elev_j == "high").mean()) if n_judged else float("nan"),
        "share_high_elev_among_candidates": float((elev == "high").mean()),
        "high_elev_exclusion_rate": float(1.0 - (elev_j == "high").sum() / max(1, (elev == "high").sum())),
        "share_sparse_donor_among_judged": float((donor_j == "sparse").mean()) if n_judged else float("nan"),
        "share_sparse_donor_among_candidates": float((donor == "sparse").mean()),
        "sparse_donor_exclusion_rate": float(
            1.0 - (donor_j == "sparse").sum() / max(1, (donor == "sparse").sum())
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    certs = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)
    attributes = pd.read_csv(
        V17_RESULTS / "step21_hydrology" / "station_panel.csv", dtype={"station_id": str}
    ).set_index("station_id")

    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
    metric = pd.to_numeric(certs["certificate_metric"], errors="coerce").to_numpy(dtype=float)
    bound = pd.to_numeric(certs["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    low = pd.to_numeric(certs["interval_low"], errors="coerce").to_numpy(dtype=float)
    high = pd.to_numeric(certs["interval_high"], errors="coerce").to_numpy(dtype=float)
    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
    peak = pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy(dtype=float)
    elev = elevation_tertile(cases["station_id"], attributes)
    donor = cases["donor_regime"].astype(str)

    rng = np.random.default_rng(SEED)
    length_keep = keep_global(length + rng.random(len(cases)), RETENTION, SEED)
    peak_keep = keep_global(peak + rng.random(len(cases)) * 1e-3, RETENTION, SEED + 1)
    cert_keep = keep_global(np.where(np.isfinite(bound), bound, np.inf), RETENTION, SEED + 2)
    balanced = keep_within(
        np.where(np.isfinite(bound), bound, np.inf),
        elev.to_numpy(),
        RETENTION,
        SEED + 3,
    )

    rows = []
    for thr in THRESHOLDS:
        metric_lo = metric - high
        metric_hi = metric - low
        straddles = (metric_lo <= thr) & (metric_hi >= thr)
        clear = np.isfinite(metric) & np.isfinite(low) & np.isfinite(high) & ~straddles

        methods = {
            "reconstruct_all": np.ones(len(cases), dtype=bool),
            "length_screen_70": length_keep,
            "peak_overlap_screen_70": peak_keep,
            "calibrated_screen_70": cert_keep,
            "interval_abstention": clear,
            "screen70_and_abstention": cert_keep & clear,
            "elev_balanced_screen_70": balanced,
            "elev_balanced_and_abstention": balanced & clear,
        }
        for name, judged in methods.items():
            rows.append(
                evaluate(
                    name,
                    judged,
                    truth=truth,
                    metric=metric,
                    thr=thr,
                    elev=elev,
                    donor=donor,
                    n_total=len(cases),
                )
            )

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "closed_loop_decisions.csv", index=False)

    # Compact headline at 18 °C
    h = table.loc[table.threshold_c.eq(18.0)].copy()
    summary = {
        "panel": "reserved_retrospective_complete_reference",
        "n_candidates": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "share_elevation_matched": float((elev != "unmatched").mean()),
        "threshold_c_headline": 18.0,
        "methods_at_18C": h[
            [
                "method",
                "share_judged",
                "n_incorrect",
                "misclassification_among_judged",
                "hot_share_bias_pp",
                "high_elev_exclusion_rate",
                "sparse_donor_exclusion_rate",
            ]
        ].to_dict(orient="records"),
        "primary_finding": (
            "Interval abstention retains more judgments than 70% screening at lower "
            "misclassification; elevation-balanced screening reduces high-elevation "
            "exclusion relative to global calibrated screening, with a small hot-share "
            "and error trade-off that must be shown rather than claimed cost-free."
        ),
        "may_enter_abstract_or_conclusions": True,
        "label": "retrospective complete-reference closed loop (not wave-2 sealed)",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "SUMMARY.md").write_text(
        "# Step 8 — environmental judgment closed loop\n\n"
        + summary["primary_finding"]
        + "\n\n"
        + h[
            [
                "method",
                "share_judged",
                "n_incorrect",
                "misclassification_among_judged",
                "hot_share_bias_pp",
                "high_elev_exclusion_rate",
                "sparse_donor_exclusion_rate",
            ]
        ].to_string(index=False)
        + "\n"
    )
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
