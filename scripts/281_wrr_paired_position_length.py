#!/usr/bin/env python3
"""P0-05: build a crossed length×overlap development subset and test dominance.

Uses job['cross_overlap']=True on a capped set of development stations so each
(station, year, length) can carry multiple overlap classes. Writes
amendments/position_length_paired/crossed_* artifacts.

Title-grade 'governs' remains withdrawn unless both fixed-length position and
fixed-overlap length contrasts are stable with intervals excluding zero.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import build_station_cases  # noqa: E402
from stream_recoverability.experiments.v17_fitness.panel import load_network_panel  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402

OUT = ROOT / "results" / "wrr_submission_ready" / "amendments" / "position_length_paired"
LENGTHS = (30, 60, 90)
MAX_STATIONS = 24


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    roster = pd.read_csv(ROOT / "results/v17_fitness/step1_panel/station_roster.csv")
    split = pd.read_csv(ROOT / "results/v17_fitness/step1_panel/network_split.csv")
    dev_nets = set(split.loc[split["split_role"].eq("development"), "network_id"].astype(str))
    roster = roster.loc[roster["network_id"].astype(str).isin(dev_nets)].copy()
    # Prefer multi-station networks.
    counts = roster.groupby("network_id")["station_id"].nunique()
    multi = set(counts.loc[counts >= 2].index.astype(str))
    roster = roster.loc[roster["network_id"].astype(str).isin(multi)]
    # Cap for runtime.
    picked = (
        roster.groupby("network_id", group_keys=False)
        .head(2)
        .head(MAX_STATIONS)
        .reset_index(drop=True)
    )

    frames = []
    for row in picked.itertuples():
        # Roster stores span, not the complete-year list; recover from the panel.
        try:
            panel = load_network_panel(str(row.network_id), str(row.source_root))
        except Exception as exc:  # noqa: BLE001
            print("skip panel", row.network_id, exc, flush=True)
            continue
        station_id = str(row.station_id)
        if station_id not in [str(c) for c in panel.columns]:
            continue
        series = pd.to_numeric(panel[station_id], errors="coerce")
        years = []
        for year, block in series.groupby(series.index.year):
            need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
            if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
                years.append(int(year))
        if len(years) < 4:
            continue
        job = {
            "network_id": str(row.network_id),
            "station_id": station_id,
            "provider": str(getattr(row, "provider", "unknown")),
            "source_root": str(getattr(row, "source_root", "first")),
            "split_role": "development",
            "regulation_status": str(getattr(row, "regulation_status", "unknown")),
            "complete_years": years,
            "fit_protocol": "leave_one_year_out",
            "cross_overlap": True,
        }
        try:
            frame = build_station_cases(job)
        except Exception as exc:  # noqa: BLE001
            print("skip", row.network_id, row.station_id, exc, flush=True)
            continue
        if frame.empty:
            continue
        # Keep the designed lengths of interest.
        frame = frame.loc[frame["longest_run"].isin(LENGTHS)]
        frames.append(frame)
        print(row.network_id, row.station_id, len(frame), flush=True)

    if not frames:
        raise RuntimeError("no crossed cases built")
    cases = pd.concat(frames, ignore_index=True)
    cases = attach_policy_errors(cases)
    cases.to_parquet(OUT / "crossed_development_cases.parquet", index=False)

    cases["abserr"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    key = ["network_id", "station_id", "year", "longest_run"]
    n_overlap = cases.groupby(key)["overlap_class"].nunique().rename("n_overlap_class")
    inventory = n_overlap.reset_index()
    inventory.to_csv(OUT / "crossed_feasibility_inventory.csv", index=False)

    multi = inventory.loc[inventory["n_overlap_class"] >= 2]
    paired = cases.merge(multi[key], on=key, how="inner")
    pos = (
        paired.groupby(key + ["overlap_class"], as_index=False)["abserr"]
        .mean()
        .groupby(key)["abserr"]
        .agg(position_range=lambda s: float(s.max() - s.min()), n_classes="count")
        .reset_index()
    )
    pos.to_csv(OUT / "crossed_position_effect_within_length.csv", index=False)

    key_len = ["network_id", "station_id", "year", "overlap_class"]
    n_len = cases.groupby(key_len)["longest_run"].nunique().rename("n_lengths")
    multi_len = n_len.reset_index().loc[lambda d: d["n_lengths"] >= 2]
    paired_len = cases.merge(multi_len[key_len], on=key_len, how="inner")
    length_eff = (
        paired_len.groupby(key_len + ["longest_run"], as_index=False)["abserr"]
        .mean()
        .groupby(key_len)["abserr"]
        .agg(length_range=lambda s: float(s.max() - s.min()), n_lengths="count")
        .reset_index()
    )
    length_eff.to_csv(OUT / "crossed_length_effect_within_overlap.csv", index=False)

    # Network-clustered mean difference: full vs none at length 60, when both exist.
    rows = []
    for length in LENGTHS:
        block = cases.loc[cases["longest_run"].eq(length)]
        wide = block.pivot_table(
            index=["network_id", "station_id", "year"],
            columns="overlap_class",
            values="abserr",
            aggfunc="mean",
        )
        if not {"full", "none"}.issubset(set(wide.columns)):
            continue
        both = wide.dropna(subset=["full", "none"])
        if both.empty:
            continue
        delta = (both["full"] - both["none"]).reset_index()
        delta.columns = ["network_id", "station_id", "year", "delta_full_minus_none"]
        delta["length"] = length
        rows.append(delta)
    if rows:
        deltas = pd.concat(rows, ignore_index=True)
        deltas.to_csv(OUT / "crossed_full_minus_none_by_length.csv", index=False)
        # Cluster means by network
        net = deltas.groupby(["length", "network_id"])["delta_full_minus_none"].mean().reset_index()
        summary_pos = {
            str(int(length)): {
                "n_networks": int(net.loc[net.length.eq(length), "network_id"].nunique()),
                "mean_delta_abserr_C": float(
                    net.loc[net.length.eq(length), "delta_full_minus_none"].mean()
                ),
            }
            for length in net["length"].unique()
        }
    else:
        summary_pos = {}

    summary = {
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "share_station_year_length_with_ge2_overlap": float(
            (inventory["n_overlap_class"] >= 2).mean()
        ),
        "mean_position_range_abserr_C": float(pos["position_range"].mean()) if len(pos) else None,
        "mean_length_range_abserr_C": float(length_eff["length_range"].mean())
        if len(length_eff)
        else None,
        "full_minus_none_by_length": summary_pos,
        "title_claim": (
            "withdraw_governs"
            if not summary_pos
            else "conditional_risk_predictor_only_until_intervals_exclude_zero_for_both_axes"
        ),
        "may_enter_abstract_or_conclusions": False,
    }
    (OUT / "crossed_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
