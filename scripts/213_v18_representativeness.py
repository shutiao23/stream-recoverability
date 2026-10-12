#!/usr/bin/env python3
"""E4 — what does the screen keep, and what does representativeness cost?

Section 5.3 of the v17 manuscript asks whether basin attributes predict how
much the screen *gains*, and correctly reports that none does. That is not the
question an agency asks. The question is which stations the screen *keeps*,
because a rule that lowers the average error by preferentially discarding hard
sites has bought accuracy with representativeness -- and in this application
the hard sites are high-elevation, steep, donor-poor catchments, which are the
cold-water headwaters the summer endpoint exists to describe.

The script measures the distortion, and then prices removing it. A screening
rule for a public archive has two objectives, and the trade-off between them is
a curve rather than a verdict.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT as V17_RESULTS,
    STEP3_CASES,
    STEP6_SCREEN,
    STEP10_CONFIRM,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E4_REPRESENTATIVENESS,
    RETENTION,
)

ATTRIBUTES = ("ELEV_SITE_M", "SLOPE_PCT", "BFI_AVE", "log_area")
STRATIFIERS = ("donor_regime", "elevation_tertile", "donor_and_elevation")
RETENTION_GRID = (0.5, 0.6, 0.7, 0.8, 0.9)


def load_scored(split: str) -> pd.DataFrame:
    if split == "development":
        cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
        cases = cases.loc[cases["split_role"] == "development"].reset_index(drop=True)
        certificates = pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet")
    else:
        cases = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
        certificates = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet")
    frame = cases.join(certificates[["certificate_bound", "certificate_abs_error"]])
    frame["station_id"] = frame["station_id"].astype(str)
    return frame


def basin_attributes() -> pd.DataFrame:
    panel = pd.read_csv(V17_RESULTS / "step21_hydrology" / "station_panel.csv", dtype={"station_id": str})
    return panel.set_index("station_id")[list(ATTRIBUTES)]


def keep_global(score: np.ndarray, retention: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(int(seed))
    order = np.lexsort((rng.random(len(score)), np.asarray(score, dtype=float)))
    keep = np.zeros(len(score), dtype=bool)
    keep[order[: int(round(float(retention) * len(score)))]] = True
    return keep


def keep_within(score: np.ndarray, strata: np.ndarray, retention: float, seed: int) -> np.ndarray:
    """Equal retention inside every stratum instead of globally."""

    keep = np.zeros(len(score), dtype=bool)
    for offset, value in enumerate(pd.unique(strata)):
        index = np.where(strata == value)[0]
        rng = np.random.default_rng(int(seed) + offset)
        order = index[np.lexsort((rng.random(len(index)), np.asarray(score, dtype=float)[index]))]
        keep[order[: int(round(float(retention) * len(index)))]] = True
    return keep


def elevation_tertile(frame: pd.DataFrame, attributes: pd.DataFrame) -> np.ndarray:
    """A stratifier an agency can compute, with a declared bucket for the unmatched.

    Only the United States subset carries GAGES-II elevation. Stations without
    it form their own stratum rather than being dropped, because a stratified
    rule that silently excluded eight agencies would not be deployable.
    """

    elevation = frame["station_id"].map(attributes["ELEV_SITE_M"])
    labels = pd.Series("unmatched", index=frame.index, dtype=object)
    matched = elevation.notna()
    if matched.any():
        labels.loc[matched] = pd.qcut(elevation[matched], 3, labels=["low", "middle", "high"]).astype(str)
    return labels.to_numpy()


def distortion(frame: pd.DataFrame, keep: np.ndarray, attributes: pd.DataFrame) -> dict:
    """How far the retained archive has moved from the archive it was drawn from."""

    per_station = pd.Series(keep, index=frame.index).groupby(frame["station_id"]).mean()
    matched = per_station.to_frame("retention").join(attributes, how="inner")
    out: dict[str, float] = {
        "retention": float(keep.mean()),
        "n_stations_matched": int(len(matched)),
        "station_retention_sd": float(per_station.std()),
        "worst_station_retention": float(per_station.min()),
        "stations_below_quarter_retention_pct": float((per_station < 0.25).mean() * 100),
    }
    for attribute in ATTRIBUTES:
        test = stats.spearmanr(matched[attribute], matched["retention"])
        out[f"rho_{attribute}"] = float(test.statistic)
        out[f"p_{attribute}"] = float(test.pvalue)
    out["max_abs_rho"] = float(max(abs(out[f"rho_{a}"]) for a in ATTRIBUTES))
    for regime, value in pd.Series(keep, index=frame.index).groupby(frame["donor_regime"]).mean().items():
        out[f"retention_{regime}"] = float(value)
    out["donor_regime_spread_points"] = (
        max(out.get(f"retention_{r}", np.nan) for r in ("none", "sparse", "rich"))
        - min(out.get(f"retention_{r}", np.nan) for r in ("none", "sparse", "rich"))
    ) * 100
    # Selection-induced shift in the quantity the archive exists to report.
    out["retained_mean_peak_c"] = float(frame.loc[keep, "truth_hottest30"].mean())
    out["peak_shift_c"] = float(frame.loc[keep, "truth_hottest30"].mean() - frame["truth_hottest30"].mean())
    return out


def rule_table(frame: pd.DataFrame, attributes: pd.DataFrame, retention: float) -> pd.DataFrame:
    consequential = frame["certificate_abs_error"].to_numpy() > PRIMARY_TOLERANCE_C
    elevation = elevation_tertile(frame, attributes)
    strata = {
        "donor_regime": frame["donor_regime"].to_numpy(),
        "elevation_tertile": elevation,
        "donor_and_elevation": np.char.add(
            frame["donor_regime"].to_numpy().astype(str), np.char.add("|", elevation.astype(str))
        ),
    }
    rules: dict[str, np.ndarray] = {
        "length rule (incumbent)": keep_global(frame["longest_run"].to_numpy(), retention, 1),
        "peak-overlap rule": keep_global(frame["peak_overlap"].to_numpy(), retention, 3),
        "calibrated screen, global threshold": keep_global(
            frame["certificate_bound"].to_numpy(), retention, 2
        ),
    }
    for name in STRATIFIERS:
        rules[f"calibrated screen, balanced within {name}"] = keep_within(
            frame["certificate_bound"].to_numpy(), strata[name], retention, 2
        )
    rows = []
    for name, keep in rules.items():
        row = {"rule": name, "retention_target": retention}
        row.update(distortion(frame, keep, attributes))
        row["error_rate_pct"] = float(consequential[keep].mean() * 100)
        rows.append(row)
    frame_out = pd.DataFrame(rows)
    baseline = float(
        frame_out.loc[frame_out["rule"] == "calibrated screen, global threshold", "error_rate_pct"].iloc[0]
    )
    frame_out["points_vs_global_screen"] = frame_out["error_rate_pct"] - baseline
    return frame_out


def elevation_contrast(frame: pd.DataFrame, attributes: pd.DataFrame) -> pd.DataFrame:
    """Retention of the highest elevation tertile against the lowest, by rule."""

    elevation = pd.Series(elevation_tertile(frame, attributes), index=frame.index)
    consequential = frame["certificate_abs_error"].to_numpy() > PRIMARY_TOLERANCE_C
    rules = {
        "length rule (incumbent)": keep_global(frame["longest_run"].to_numpy(), RETENTION, 1),
        "calibrated screen, global threshold": keep_global(
            frame["certificate_bound"].to_numpy(), RETENTION, 2
        ),
        "calibrated screen, balanced within elevation_tertile": keep_within(
            frame["certificate_bound"].to_numpy(), elevation.to_numpy(), RETENTION, 2
        ),
    }
    rows = []
    for name, keep in rules.items():
        block = pd.DataFrame({"tertile": elevation, "keep": keep, "bad": consequential})
        table = block.groupby("tertile").agg(retention=("keep", "mean"), n=("keep", "size"))
        row = {"rule": name}
        for tertile in ("low", "middle", "high", "unmatched"):
            if tertile in table.index:
                row[f"retention_{tertile}"] = float(table.loc[tertile, "retention"])
        if "high" in table.index and "low" in table.index:
            row["high_minus_low_points"] = (
                float(table.loc["high", "retention"] - table.loc["low", "retention"]) * 100
            )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    E4_REPRESENTATIVENESS.mkdir(parents=True, exist_ok=True)
    attributes = basin_attributes()
    tables, contrasts = [], []
    for split in ("development", "reserved"):
        frame = load_scored(split)
        for retention in RETENTION_GRID:
            block = rule_table(frame, attributes, retention)
            block.insert(0, "split", split)
            tables.append(block)
        contrast = elevation_contrast(frame, attributes)
        contrast.insert(0, "split", split)
        contrasts.append(contrast)
    frontier = pd.concat(tables, ignore_index=True)
    frontier.to_csv(E4_REPRESENTATIVENESS / "representativeness_frontier.csv", index=False)
    elevation = pd.concat(contrasts, ignore_index=True)
    elevation.to_csv(E4_REPRESENTATIVENESS / "elevation_retention.csv", index=False)

    headline = frontier.loc[frontier["retention_target"] == RETENTION]
    reserved = load_scored("reserved")
    reserved_elev = pd.Series(elevation_tertile(reserved, attributes), index=reserved.index)
    per_station = (
        pd.Series(keep_global(reserved["certificate_bound"].to_numpy(), RETENTION, 2), index=reserved.index)
        .groupby(reserved["station_id"])
        .mean()
        .to_frame("retention")
        .join(attributes, how="inner")
    )
    interval = cluster_bootstrap(
        reserved.assign(
            keep=keep_global(reserved["certificate_bound"].to_numpy(), RETENTION, 2).astype(float),
            high=(reserved_elev == "high").astype(float),
            low=(reserved_elev == "low").astype(float),
        ),
        lambda block: float(
            block.loc[block["high"] > 0, "keep"].mean() - block.loc[block["low"] > 0, "keep"].mean()
        )
        if (block["high"] > 0).any() and (block["low"] > 0).any()
        else float("nan"),
        seed=20260924,
    )

    global_row = headline.loc[
        (headline["split"] == "development")
        & (headline["rule"] == "calibrated screen, global threshold")
    ].iloc[0]
    balanced_row = headline.loc[
        (headline["split"] == "development")
        & (headline["rule"] == "calibrated screen, balanced within donor_and_elevation")
    ].iloc[0]
    summary = {
        "prediction": (
            "the calibrated screen retains high-elevation and donor-poor station-years "
            "less often than the incumbent length rule, because it is selecting on "
            "difficulty and difficulty tracks catchment type"
        ),
        "development_global_screen_elevation_rho": float(global_row["rho_ELEV_SITE_M"]),
        "development_global_screen_elevation_p": float(global_row["p_ELEV_SITE_M"]),
        "development_global_screen_donor_spread_points": float(global_row["donor_regime_spread_points"]),
        "reserved_high_minus_low_elevation_retention": interval,
        "price_of_balancing_points": float(
            balanced_row["error_rate_pct"] - global_row["error_rate_pct"]
        ),
        "n_stations_with_attributes": int(len(per_station)),
    }
    (E4_REPRESENTATIVENESS / "summary.json").write_text(
        json.dumps(summary, indent=2, default=float), encoding="utf-8"
    )

    columns = [
        "split",
        "rule",
        "error_rate_pct",
        "points_vs_global_screen",
        "rho_ELEV_SITE_M",
        "donor_regime_spread_points",
        "station_retention_sd",
        "peak_shift_c",
    ]
    lines = ["# E4 — representativeness of the retained archive", ""]
    lines.append(f"At {RETENTION:.0%} retention.")
    lines.append("")
    lines.append(headline[columns].to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## Retention by elevation tertile")
    lines.append("")
    lines.append(elevation.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## The price of balancing")
    lines.append("")
    lines.append(
        f"Balancing the screen within donor regime and elevation tertile costs "
        f"{summary['price_of_balancing_points']:+.2f} points of consequential-error rate "
        f"on development cases and removes the donor-regime spread of "
        f"{summary['development_global_screen_donor_spread_points']:.1f} points."
    )
    (E4_REPRESENTATIVENESS / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
