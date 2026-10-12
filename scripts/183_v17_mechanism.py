#!/usr/bin/env python3
"""Step 5 of the v17 programme: mechanism (H1) and the donor controls."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import argparse  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.mechanism import (  # noqa: E402
    donor_control_experiment,
    grouped_importance,
    length_by_overlap_table,
    marginal_separation,
    nested_model_gain,
)
from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    STEP1_PANEL,
    STEP4_CEILING,
    STEP5_MECHANISM,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=96)
    args = parser.parse_args()

    STEP5_MECHANISM.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP4_CEILING / "development_cases.parquet")

    length_overlap = length_by_overlap_table(cases)
    separation = marginal_separation(cases)
    importance, importance_summary = grouped_importance(cases)
    nested = nested_model_gain(cases)

    length_overlap.to_csv(STEP5_MECHANISM / "length_by_overlap.csv", index=False)
    separation.to_csv(STEP5_MECHANISM / "marginal_separation.csv", index=False)
    importance.to_csv(STEP5_MECHANISM / "permutation_importance.csv", index=False)
    nested.to_csv(STEP5_MECHANISM / "nested_feature_sets.csv", index=False)

    # Controlled donor experiments on development networks with >= 4 donors.
    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = [job for job in station_jobs(roster, split, split_role="development")]
    frames = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(donor_control_experiment, job) for job in jobs]
        for future in as_completed(futures):
            try:
                frame = future.result()
            except Exception:  # noqa: BLE001
                frame = pd.DataFrame()
            if not frame.empty:
                frames.append(frame)
    controls = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    control_summary = {}
    if not controls.empty:
        controls.to_parquet(STEP5_MECHANISM / "donor_controls.parquet", index=False)
        arms = ["all_donors", "strong_half", "weak_half", "anomaly_shuffled"]
        rows = []
        for arm in arms:
            column = f"abserr_{arm}"
            block = controls.loc[controls[column].notna()]
            stat = cluster_bootstrap(block, lambda f, c=column: float(pd.to_numeric(f[c], errors="coerce").mean()))
            rows.append(
                {
                    "arm": arm,
                    "n": int(len(block)),
                    "mean_abs_error_c": stat["point"],
                    "ci_low": stat["low"],
                    "ci_high": stat["high"],
                    "n_networks": stat["n_clusters"],
                }
            )
        control_table = pd.DataFrame(rows)
        control_table.to_csv(STEP5_MECHANISM / "donor_control_summary.csv", index=False)
        paired = controls.dropna(subset=["abserr_strong_half", "abserr_weak_half", "abserr_all_donors", "abserr_anomaly_shuffled"])
        contrasts = []
        for left, right in [
            ("abserr_weak_half", "abserr_strong_half"),
            ("abserr_anomaly_shuffled", "abserr_all_donors"),
        ]:
            stat = cluster_bootstrap(
                paired,
                lambda f, a=left, b=right: float(
                    pd.to_numeric(f[a], errors="coerce").mean() - pd.to_numeric(f[b], errors="coerce").mean()
                ),
            )
            contrasts.append({"contrast": f"{left} - {right}", "n_paired": int(len(paired)), **stat})
        contrast_table = pd.DataFrame(contrasts)
        contrast_table.to_csv(STEP5_MECHANISM / "donor_control_contrasts.csv", index=False)
        control_summary = {
            "n_cases": int(len(controls)),
            "n_networks": int(controls["network_id"].nunique()),
            "n_stations": int(controls.groupby(["network_id", "station_id"]).ngroups),
        }
    else:
        control_table = pd.DataFrame()
        contrast_table = pd.DataFrame()

    summary = {"importance": importance_summary, "controls": control_summary}
    (STEP5_MECHANISM / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Step 5 — mechanism (H1)", ""]
    lines.append("## Outage length is a weak axis once peak-window overlap is conditioned on")
    lines.append("")
    lines.append(length_overlap.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Single-variable discrimination of a consequential error (> 0.5 °C)")
    lines.append("")
    lines.append(separation.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Nested feature sets, grouped five-fold CV clustered by network")
    lines.append("")
    lines.append(nested.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Permutation importance on out-of-fold predictions")
    lines.append("")
    lines.append(f"Out-of-fold R² = {importance_summary['out_of_fold_r2']:.4f} "
                 f"(n = {importance_summary['n']:,}, {importance_summary['n_networks']} networks)")
    lines.append("")
    lines.append(importance.round(4).to_string(index=False))
    if not control_table.empty:
        lines.append("")
        lines.append("## Controlled donor experiments")
        lines.append("")
        lines.append("Outage, station, year and training data are identical across arms; only the")
        lines.append("donor property named by the arm changes.")
        lines.append("")
        lines.append(control_table.round(4).to_string(index=False))
        lines.append("")
        lines.append(contrast_table.round(4).to_string(index=False))
    (STEP5_MECHANISM / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(length_overlap.round(4).to_string(index=False))
    print()
    print(separation.round(4).to_string(index=False))
    print()
    print(nested.round(4).to_string(index=False))
    print()
    print(f"OOF R2 = {importance_summary['out_of_fold_r2']:.4f}")
    print(importance.round(4).to_string(index=False))
    if not control_table.empty:
        print()
        print(control_table.round(4).to_string(index=False))
        print()
        print(contrast_table.round(4).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
