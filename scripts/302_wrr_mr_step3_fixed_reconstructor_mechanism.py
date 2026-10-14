#!/usr/bin/env python3
"""Major-revision Step 3: fixed-reconstructor crossed position×length mechanism.

Uses the existing crossed development panel from scripts/281 (12 nets / 24
stations). Reports network-clustered intervals for:
  - fixed length: full-overlap vs none-overlap error (°C)
  - fixed overlap class: longest vs shortest available length (°C)
separately for each fixed reconstructor (policy mixture is NOT used).

Also labels three failure modes requested by the revision brief.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

SRC = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "amendments"
    / "position_length_paired"
    / "crossed_development_cases.parquet"
)
OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step3_fixed_reconstructor_mechanism"
)

# Air-ridge is unavailable on this crossed panel (air_available==0). Keep the
# requested strong reconstructors that actually exist here.
RECONSTRUCTORS = (
    "doy_climatology",
    "smooth_climatology",
    "donor_ridge",
    "linear_interp",
)
LENGTHS = (30, 60, 90)
BOOT_DRAWS = 2000
SEED = 23
TOL = 0.5


def _station_year_mean(cases: pd.DataFrame, value: str) -> pd.DataFrame:
    """One row per station-year-length-overlap before network aggregation."""

    return (
        cases.groupby(
            ["network_id", "station_id", "year", "longest_run", "overlap_class"],
            as_index=False,
        )[value]
        .mean()
        .rename(columns={value: "abserr"})
    )


def position_deltas(cases: pd.DataFrame, abserr_col: str) -> pd.DataFrame:
    """full − none at fixed length, station-year equal weight."""

    sy = _station_year_mean(cases, abserr_col)
    rows = []
    for length in LENGTHS:
        block = sy.loc[sy["longest_run"].eq(length)]
        wide = block.pivot_table(
            index=["network_id", "station_id", "year"],
            columns="overlap_class",
            values="abserr",
            aggfunc="mean",
        )
        if not {"full", "none"}.issubset(set(map(str, wide.columns))):
            continue
        both = wide.dropna(subset=["full", "none"]).reset_index()
        if both.empty:
            continue
        both = both.rename(columns={"full": "err_full", "none": "err_none"})
        both["delta_full_minus_none"] = both["err_full"] - both["err_none"]
        both["length"] = int(length)
        rows.append(both[["network_id", "station_id", "year", "length", "delta_full_minus_none", "err_full", "err_none"]])
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def length_deltas(cases: pd.DataFrame, abserr_col: str) -> pd.DataFrame:
    """max_length − min_length at fixed overlap class, station-year equal weight."""

    sy = _station_year_mean(cases, abserr_col)
    rows = []
    for overlap in ("none", "partial", "full"):
        block = sy.loc[sy["overlap_class"].astype(str).eq(overlap)]
        wide = block.pivot_table(
            index=["network_id", "station_id", "year"],
            columns="longest_run",
            values="abserr",
            aggfunc="mean",
        )
        if wide.shape[1] < 2:
            continue
        # Use 30 vs 90 when both exist; otherwise max−min among available.
        available = [c for c in LENGTHS if c in wide.columns]
        if len(available) < 2:
            continue
        lo, hi = available[0], available[-1]
        both = wide.dropna(subset=[lo, hi]).reset_index()
        if both.empty:
            continue
        both["delta_long_minus_short"] = both[hi] - both[lo]
        both["overlap_class"] = overlap
        both["short_length"] = lo
        both["long_length"] = hi
        rows.append(
            both[
                [
                    "network_id",
                    "station_id",
                    "year",
                    "overlap_class",
                    "short_length",
                    "long_length",
                    "delta_long_minus_short",
                ]
            ]
        )
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def network_ci(deltas: pd.DataFrame, value: str, *, by: list[str], seed: int) -> pd.DataFrame:
    rows = []
    if deltas.empty:
        return pd.DataFrame()
    for keys, block in deltas.groupby(by, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)

        def statistic(frame: pd.DataFrame) -> float:
            # Equal network weight: mean within network, then mean across nets in sample.
            return float(frame.groupby("network_id")[value].mean().mean())

        # Point on original networks (equal weight).
        point = float(block.groupby("network_id")[value].mean().mean())
        boot = cluster_bootstrap(block, statistic, draws=BOOT_DRAWS, seed=seed)
        row = {name: key for name, key in zip(by, keys)}
        row.update(
            {
                "point_C": point,
                "ci_low_C": boot["low"],
                "ci_high_C": boot["high"],
                "n_networks": int(block["network_id"].nunique()),
                "n_station_years": int(len(block)),
                "ci_excludes_zero": bool(
                    np.isfinite(boot["low"])
                    and np.isfinite(boot["high"])
                    and not (boot["low"] <= 0 <= boot["high"])
                ),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def failure_modes(cases: pd.DataFrame, abserr_col: str) -> pd.DataFrame:
    """Label revision-brief failure modes on crossed cases."""

    err = pd.to_numeric(cases[abserr_col], errors="coerce")
    true_hide = pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce")
    peak_ov = pd.to_numeric(cases["peak_overlap"], errors="coerce")
    margin = pd.to_numeric(cases.get("observed_peak_margin"), errors="coerce")

    # 1) False peak: realised peak largely visible, yet large reconstruction error.
    false_peak = (true_hide.fillna(1) <= 0.1) & (err > TOL)
    # 2) Climate-window mismatch: climatological support heavily hit, realised peak not.
    clim_miss = (peak_ov.fillna(0) >= 0.7) & (true_hide.fillna(1) <= 0.3)
    # 3) Competing peaks proxy: observed peak already near climatology (small margin)
    #    while error remains large under partial hide — ambiguous which window wins.
    competing = (margin.abs() <= 0.5) & (err > TOL) & (true_hide.between(0.2, 0.8))

    frame = cases[
        ["network_id", "station_id", "year", "longest_run", "overlap_class", "peak_overlap", "true_peak_hidden_fraction"]
    ].copy()
    frame["abserr"] = err
    frame["reconstructor"] = abserr_col.replace("abserr_", "")
    frame["failure_false_peak"] = false_peak.fillna(False)
    frame["failure_climate_mismatch"] = clim_miss.fillna(False)
    frame["failure_competing_peaks_proxy"] = competing.fillna(False)
    frame["any_labelled_failure"] = (
        frame["failure_false_peak"]
        | frame["failure_climate_mismatch"]
        | frame["failure_competing_peaks_proxy"]
    )
    return frame


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(SRC)
    # Restrict to designed crossed classes.
    cases = cases.loc[cases["overlap_class"].astype(str).isin(["none", "partial", "full"])].copy()

    pos_tables = []
    len_tables = []
    fail_summary = []
    all_failures = []

    for recon in RECONSTRUCTORS:
        col = f"abserr_{recon}"
        if col not in cases.columns:
            continue
        usable = cases.loc[pd.to_numeric(cases[col], errors="coerce").notna()].copy()
        if usable.empty:
            continue
        print(f"Reconstructor {recon}: n={len(usable)}", flush=True)
        pos = position_deltas(usable, col)
        leng = length_deltas(usable, col)
        if not pos.empty:
            pos["reconstructor"] = recon
            pos.to_csv(OUT / f"position_deltas_{recon}.csv", index=False)
            ci = network_ci(pos, "delta_full_minus_none", by=["length"], seed=SEED)
            ci["reconstructor"] = recon
            ci["contrast"] = "full_minus_none_at_fixed_length"
            pos_tables.append(ci)
        if not leng.empty:
            leng["reconstructor"] = recon
            leng.to_csv(OUT / f"length_deltas_{recon}.csv", index=False)
            ci = network_ci(leng, "delta_long_minus_short", by=["overlap_class"], seed=SEED + 7)
            ci["reconstructor"] = recon
            ci["contrast"] = "long_minus_short_at_fixed_overlap"
            len_tables.append(ci)

        fails = failure_modes(usable, col)
        all_failures.append(fails)
        fail_summary.append(
            {
                "reconstructor": recon,
                "n_cases": int(len(fails)),
                "rate_false_peak": float(fails["failure_false_peak"].mean()),
                "rate_climate_mismatch": float(fails["failure_climate_mismatch"].mean()),
                "rate_competing_peaks_proxy": float(fails["failure_competing_peaks_proxy"].mean()),
                "rate_any_labelled": float(fails["any_labelled_failure"].mean()),
                "mean_abserr_when_false_peak": float(
                    fails.loc[fails["failure_false_peak"], "abserr"].mean()
                )
                if fails["failure_false_peak"].any()
                else None,
            }
        )

    position_ci = pd.concat(pos_tables, ignore_index=True) if pos_tables else pd.DataFrame()
    length_ci = pd.concat(len_tables, ignore_index=True) if len_tables else pd.DataFrame()
    position_ci.to_csv(OUT / "position_contrasts_network_ci.csv", index=False)
    length_ci.to_csv(OUT / "length_contrasts_network_ci.csv", index=False)
    pd.DataFrame(fail_summary).to_csv(OUT / "failure_mode_rates.csv", index=False)
    if all_failures:
        fail_cat = pd.concat(all_failures, ignore_index=True)
        fail_cat.loc[fail_cat["any_labelled_failure"]].to_csv(
            OUT / "failure_mode_cases.csv", index=False
        )

    # Cross-reconstructor stability: does position effect sign agree?
    stability = {}
    if not position_ci.empty:
        for length, block in position_ci.groupby("length"):
            signs = np.sign(block["point_C"].to_numpy())
            stability[f"length_{int(length)}"] = {
                "n_reconstructors": int(len(block)),
                "all_positive_full_worse": bool((block["point_C"] > 0).all()),
                "all_ci_exclude_zero": bool(block["ci_excludes_zero"].all()),
                "points_C": {
                    str(r.reconstructor): float(r.point_C) for r in block.itertuples()
                },
            }

    summary = {
        "source_cases": str(SRC.relative_to(ROOT)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases_crossed_classes": int(len(cases)),
        "reconstructors": list(RECONSTRUCTORS),
        "air_ridge_note": "air_available==0 on this panel; air_ridge omitted",
        "position_contrasts": position_ci.to_dict(orient="records") if not position_ci.empty else [],
        "length_contrasts": length_ci.to_dict(orient="records") if not length_ci.empty else [],
        "failure_mode_rates": fail_summary,
        "cross_reconstructor_position_stability": stability,
        "claim_status": (
            "conditional_mechanism_with_network_intervals; "
            "not a universal position-dominates-length law"
        ),
        "may_enter_abstract_or_conclusions": False,
        "interpretation_gate": (
            "Enter discussion as conditional evidence if position CIs exclude 0 "
            "for climatology and donor; length effects reported separately in °C; "
            "failure modes must be discussed when rates are non-trivial."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "# Step 3 — fixed-reconstructor crossed mechanism",
        "",
        f"Panel: {summary['n_networks']} networks, {summary['n_stations']} stations, "
        f"{summary['n_cases_crossed_classes']} crossed-class cases.",
        f"Note: {summary['air_ridge_note']}.",
        "",
        "## Position contrasts (full − none °C) with network CIs",
        "",
        position_ci.to_string(index=False) if not position_ci.empty else "(none)",
        "",
        "## Length contrasts (long − short °C) with network CIs",
        "",
        length_ci.to_string(index=False) if not length_ci.empty else "(none)",
        "",
        "## Failure-mode rates",
        "",
        pd.DataFrame(fail_summary).to_string(index=False),
        "",
        "## Stability across reconstructors",
        "",
        json.dumps(stability, indent=2),
        "",
        "Claim status: conditional risk / mechanism evidence only — not a dominance law.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
