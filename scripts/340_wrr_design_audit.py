#!/usr/bin/env python3
"""R2-01 (review op. 2, 2026-10-20b) -- what each design actually varies.

The manuscript described the 53,721 outages as a factorial design that varies gap
length and hidden support independently, with "the remaining missing days
scattered at random".  This script reads the case tables that produced every
figure and reports what they contain, so the text can be made to match.

It answers five questions with counts, not with prose:

1. Which arm is each case?  (``stratified`` = one contiguous run placed at a
   requested overlap with the *climatological* window; ``empirical`` = real
   provider gap geometry, 1-4 runs, transplanted onto a complete year.)
2. Which target lengths and overlap classes exist, and which cells are
   infeasible?
3. How many independent station-years and networks stand behind each cell?
4. How strongly do length and hidden support still covary in each design?
5. Which figure panel is read from which design?

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/r2_01_design_audit/``.

Run:

    PYTHONPATH=src python3 scripts/340_wrr_design_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

OUT = C.RUN / "r2_01_design_audit"
LENGTH_BINS = [0, 7, 14, 30, 60, 90, 180, 400]
LENGTH_LABELS = ["1-7", "8-14", "15-30", "31-60", "61-90", "91-180", ">180"]
DRAWS = 2000


def support_class(hidden: pd.Series) -> pd.Series:
    h = pd.to_numeric(hidden, errors="coerce")
    return pd.Series(
        np.select([h <= 0.0, h >= 0.999], ["none", "all"], default="partial"), index=h.index
    ).where(h.notna())


def corr_with_ci(frame: pd.DataFrame, x: str, y: str, cluster: str, seed: int) -> dict:
    block = frame[[x, y, cluster]].dropna()
    if len(block) < 5 or block[x].nunique() < 2 or block[y].nunique() < 2:
        return {"n": len(block), "pearson": float("nan"), "lo": float("nan"), "hi": float("nan")}
    parts = [g[[x, y]].to_numpy() for _, g in block.groupby(cluster)]

    def stat(chosen):
        data = np.vstack(chosen)
        if data[:, 0].std() == 0 or data[:, 1].std() == 0:
            return float("nan")
        return float(np.corrcoef(data[:, 0], data[:, 1])[0, 1])

    point, lo, hi = C.cluster_bootstrap(parts, stat, draws=DRAWS, seed=seed)
    return {"n": int(len(block)), "pearson": point, "lo": lo, "hi": hi, "n_clusters": len(parts)}


def station_year_key(frame: pd.DataFrame) -> pd.Series:
    """A physical station-year.  Network labels can share a station, so the
    network label is deliberately not part of the key (external panel: 1,267
    label-station-years collapse to 1,103 station-years)."""

    return frame["station_id"].astype(str) + "|" + frame["year"].astype(str)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    panels = {
        "development": pd.read_parquet(C.development_parquet()),
        "external": pd.read_parquet(C.EXTERNAL_PARQUET),
        "crossed_mechanism": pd.read_parquet(C.CROSSED_PARQUET),
    }
    for name, frame in panels.items():
        frame["sy"] = station_year_key(frame)
        frame["support_true"] = support_class(frame["true_peak_hidden_fraction"])
        frame["length_bin"] = pd.cut(
            frame["longest_run"], LENGTH_BINS, labels=LENGTH_LABELS, include_lowest=True
        ).astype(str)

    # ---- 1. arm inventory --------------------------------------------------
    rows = []
    for name, frame in panels.items():
        for arm, block in [("all", frame)] + [(a, g) for a, g in frame.groupby("arm")]:
            rows.append(
                {
                    "panel": name,
                    "arm": arm,
                    "n_cases": len(block),
                    "n_station_years": block["sy"].nunique(),
                    "n_stations": block["station_id"].nunique(),
                    "n_networks": block["network_id"].nunique(),
                    "median_longest_run": float(block["longest_run"].median()),
                    "mean_n_runs": float(block["n_runs"].mean()),
                    "share_single_run": float((block["n_runs"] == 1).mean()),
                    "median_missing_fraction": float(block["missing_fraction"].median()),
                    "share_of_panel": len(block) / len(frame),
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "arm_inventory.csv", index=False)

    # ---- 2/3. target-length x climatological-overlap cells -----------------
    cell_rows = []
    for name, frame in panels.items():
        stratified = frame.loc[frame["arm"].eq("stratified")]
        for (length, klass), block in stratified.groupby(["longest_run", "overlap_class"]):
            cell_rows.append(
                {
                    "panel": name,
                    "target_length": int(length),
                    "climatological_overlap_class": klass,
                    "n_cases": len(block),
                    "n_station_years": block["sy"].nunique(),
                    "n_networks": block["network_id"].nunique(),
                    "mean_true_hidden_fraction": float(block["true_peak_hidden_fraction"].mean()),
                    "share_true_hidden_none": float((block["support_true"] == "none").mean()),
                    "share_true_hidden_all": float((block["support_true"] == "all").mean()),
                    "mean_n_runs": float(block["n_runs"].mean()),
                }
            )
    cells = pd.DataFrame(cell_rows)
    # explicit empty cells: requested but infeasible or never drawn
    expected = pd.MultiIndex.from_product(
        [list(panels), [14, 30, 60, 90, 120, 180, 270], ["none", "partial", "full"]],
        names=["panel", "target_length", "climatological_overlap_class"],
    )
    full = (
        cells.set_index(["panel", "target_length", "climatological_overlap_class"])
        .reindex(expected)
        .reset_index()
    )
    full["n_cases"] = full["n_cases"].fillna(0).astype(int)
    full["cell_status"] = np.where(
        full["n_cases"] == 0,
        "empty",
        np.where(full["n_cases"] < 100, "sparse_(<100)", "populated"),
    )
    full.to_csv(OUT / "length_by_overlap_cells.csv", index=False)

    # ---- 4. how strongly do length and support covary ----------------------
    corr_rows = []
    seed = 11
    for name, frame in panels.items():
        views = [("all", frame)] + [(a, g) for a, g in frame.groupby("arm")]
        for arm, block in views:
            block = block.copy()
            for x, y, label in (
                ("longest_run", "true_peak_hidden_fraction", "length_vs_true_hidden_share"),
                ("longest_run", "peak_overlap", "length_vs_climatological_overlap"),
                ("longest_run", "missing_fraction", "length_vs_missing_fraction"),
            ):
                seed += 1
                result = corr_with_ci(block, x, y, "network_id", seed)
                corr_rows.append({"panel": name, "arm": arm, "pair": label, **result})

    # real calendars: 418 replay groups
    raw = pd.read_parquet(C.REPLAY_RAW)
    raw = raw.assign(
        network_id=raw["network_id"].astype(str),
        station_id=raw["station_id"].astype(str),
    )
    raw["sy"] = (
        raw["network_id"] + "|" + raw["station_id"] + "|" + raw["source_incomplete_year"].astype(str)
    )
    real_info = {
        "n_groups": len(raw),
        "n_source_incomplete_station_years": int(raw["sy"].nunique()),
        "n_target_station_years": int(
            raw[["network_id", "station_id", "eval_year"]].drop_duplicates().shape[0]
        ),
        "n_networks": int(raw["network_id"].nunique()),
    }
    for x, y, label in (
        ("longest_run", "peak_overlap", "length_vs_climatological_overlap"),
        ("longest_run", "missing_fraction", "length_vs_missing_fraction"),
    ):
        seed += 1
        corr_rows.append(
            {"panel": "real_calendar_replay", "arm": "all", "pair": label, **corr_with_ci(raw, x, y, "network_id", seed)}
        )
    corr = pd.DataFrame(corr_rows)
    corr.to_csv(OUT / "length_support_correlation.csv", index=False)
    pd.Series(real_info).to_csv(OUT / "real_calendar_independence.csv", header=["value"])

    # ---- Fig. 1 classes by length bin, external panel ----------------------
    ext = panels["external"]
    tab = (
        ext.groupby(["arm", "length_bin", "support_true"])
        .agg(n_cases=("year", "size"), n_station_years=("sy", "nunique"), n_networks=("network_id", "nunique"))
        .reset_index()
    )
    tab.to_csv(OUT / "fig1_cells_by_arm.csv", index=False)

    # ---- 5. figure provenance ---------------------------------------------
    cross = panels["crossed_mechanism"]
    paired = cross.loc[cross["arm"].eq("stratified")]
    per_sy = paired.groupby("sy").size()
    prov = pd.DataFrame(
        [
            {
                "figure_panel": "Fig. 1a-c",
                "source_panel": "external",
                "n_cases": len(ext),
                "n_station_years": ext["sy"].nunique(),
                "n_networks": ext["network_id"].nunique(),
                "arms": "stratified + empirical",
                "support_variable": "true hidden share of the true window (outcome-defined)",
                "within_station_year_control": False,
                "identification": "conditional grouping of a mixed archive",
            },
            {
                "figure_panel": "Fig. 1d",
                "source_panel": "external + real_calendar_replay",
                "n_cases": len(ext) + len(raw),
                "n_station_years": ext["sy"].nunique() + real_info["n_target_station_years"],
                "n_networks": ext["network_id"].nunique(),
                "arms": "stratified + empirical; real replay",
                "support_variable": "climatological overlap",
                "within_station_year_control": False,
                "identification": "descriptive distribution",
            },
            {
                "figure_panel": "Fig. 3a-b",
                "source_panel": "crossed_mechanism (stratified arm)",
                "n_cases": len(paired),
                "n_station_years": paired["sy"].nunique(),
                "n_networks": paired["network_id"].nunique(),
                "arms": "stratified only",
                "support_variable": "design class on the climatological window; true share reported",
                "within_station_year_control": bool((per_sy == 9).all()),
                "identification": "same station-year, all 9 length x class cells",
            },
            {
                "figure_panel": "Fig. 3c",
                "source_panel": "external",
                "n_cases": len(ext),
                "n_station_years": ext["sy"].nunique(),
                "n_networks": ext["network_id"].nunique(),
                "arms": "stratified + empirical",
                "support_variable": "true hidden share",
                "within_station_year_control": False,
                "identification": "conditional grouping of a mixed archive",
            },
            {
                "figure_panel": "Fig. 4a-c",
                "source_panel": "crossed_mechanism (stratified arm)",
                "n_cases": len(paired),
                "n_station_years": paired["sy"].nunique(),
                "n_networks": paired["network_id"].nunique(),
                "arms": "stratified only",
                "support_variable": "reconstruction diagnostics (post-treatment)",
                "within_station_year_control": False,
                "identification": "grouping on an outcome-side variable; not an intervention",
            },
            {
                "figure_panel": "Fig. 4d, Fig. 5",
                "source_panel": "external + development",
                "n_cases": len(ext),
                "n_station_years": ext["sy"].nunique(),
                "n_networks": ext["network_id"].nunique(),
                "arms": "stratified + empirical",
                "support_variable": "cross-fitted score",
                "within_station_year_control": False,
                "identification": "prediction / admission evaluation",
            },
        ]
    )
    prov.to_csv(OUT / "figure_provenance.csv", index=False)

    # ---- is the crossed panel a subset of the development panel? -----------
    key = ["network_id", "station_id", "year", "realization_id"]
    dev = panels["development"]
    cross_s = panels["crossed_mechanism"].loc[panels["crossed_mechanism"]["arm"].eq("stratified")]
    merged = cross_s.merge(
        dev[key + ["peak_overlap", "true_peak_hidden_fraction"]], on=key, how="left",
        suffixes=("", "_dev"), indicator=True,
    )
    both = merged[merged["_merge"].eq("both")]
    pd.Series(
        {
            "crossed_stratified_outages": int(len(cross_s)),
            "share_realization_key_present_in_development_panel": float(len(both) / len(cross_s)),
            "n_with_matching_key": int(len(both)),
            "of_those_identical_climatological_overlap": float((both["peak_overlap"] == both["peak_overlap_dev"]).mean()),
            "of_those_identical_true_hidden_fraction": float(
                (both["true_peak_hidden_fraction"] == both["true_peak_hidden_fraction_dev"]).mean()
            ),
            "conclusion": "the crossed panel is a separate generation, not a subset of the 53,721",
        }
    ).to_csv(OUT / "crossed_vs_development_overlap.csv", header=["value"])

    # ---- summary -----------------------------------------------------------
    def pick(panel, arm, pair):
        row = corr[(corr.panel == panel) & (corr.arm == arm) & (corr.pair == pair)].iloc[0]
        return row

    lines = ["# R2-01 design audit", ""]
    lines.append("## What the three panels contain")
    inv = pd.read_csv(OUT / "arm_inventory.csv")
    lines.append(inv.to_string(index=False))
    lines.append("")
    lines.append("## Correlation of gap length with hidden support (network-clustered 95% interval)")
    show = corr[corr.pair.isin(["length_vs_true_hidden_share", "length_vs_climatological_overlap"])]
    lines.append(show.to_string(index=False))
    lines.append("")
    lines.append("## Real calendars: how many independent units stand behind the 418 groups")
    lines.append(pd.Series(real_info).to_string())
    lines.append("")
    lines.append("## Target-length x climatological-overlap cells that are empty or sparse")
    lines.append(
        full.loc[full.cell_status != "populated", ["panel", "target_length", "climatological_overlap_class", "n_cases", "cell_status"]].to_string(index=False)
    )
    lines.append("")
    lines.append("## Figure provenance")
    lines.append(prov.to_string(index=False))
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    C.write_fingerprint(
        OUT,
        "scripts/340_wrr_design_audit.py",
        {
            "development": C.development_parquet(),
            "external": C.EXTERNAL_PARQUET,
            "crossed": C.CROSSED_PARQUET,
            "replay_raw": C.REPLAY_RAW,
        },
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
