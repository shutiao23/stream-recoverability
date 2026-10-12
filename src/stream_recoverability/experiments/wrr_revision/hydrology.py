"""Falsifiable hydrological hypotheses on complete-year B_q (Step 8).

Synthetic mechanism results need real hydrologic counterparts. Grouping uses
decision-time or independent station attributes, never evaluation thermal labels
as deployment inputs.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.paths import NON_INFERIORITY_EPSILON_C
from stream_recoverability.experiments.wrr_revision.thermal_decision import network_equal_stats


def donor_synchrony_stability(
    year_table: pd.DataFrame,
    *,
    policy: str = "always_donor_only",
    split: str = "eval",
    corr_cut: float = 0.5,
    short: float = 45.0,
    long: float = 120.0,
) -> pd.DataFrame:
    """Deseasonalized donor |r| vs long-gap benefit stability.

    Hypothesis: high training synchrony keeps donor-only B_q from collapsing
    as max gap length grows; low synchrony does not.
    """

    frame = year_table.loc[year_table["policy"].eq(policy) & year_table["split"].eq(split)].copy()
    if frame.empty:
        return pd.DataFrame()
    corr = pd.to_numeric(frame["mean_donor_corr"], errors="coerce")
    length = pd.to_numeric(frame["max_gap_length"], errors="coerce")
    frame["synchrony"] = np.where(corr >= float(corr_cut), "high", np.where(corr.notna(), "low", "unknown"))
    frame["length_bin"] = np.where(length >= float(long), "long", np.where(length <= float(short), "short", "mid"))
    rows = []
    for (synchrony, length_bin), group in frame.groupby(["synchrony", "length_bin"]):
        stats = network_equal_stats(group, "realized_benefit")
        rows.append(
            {
                "hypothesis": "donor_synchrony_stability",
                "synchrony": synchrony,
                "length_bin": length_bin,
                "n_station_years": stats["n_station_years"],
                "n_networks": stats["n_networks"],
                "network_equal_Bq": stats["mean"],
                "ci_lo": stats["ci_lo"],
                "ci_hi": stats["ci_hi"],
                "harm_rate": float((pd.to_numeric(group["realized_benefit"], errors="coerce") < 0).mean()),
            }
        )
    out = pd.DataFrame(rows)
    high_long = out.loc[out["synchrony"].eq("high") & out["length_bin"].eq("long"), "network_equal_Bq"]
    low_long = out.loc[out["synchrony"].eq("low") & out["length_bin"].eq("long"), "network_equal_Bq"]
    if len(high_long) and len(low_long):
        out.attrs["verdict"] = {
            "high_long_Bq": float(high_long.iloc[0]),
            "low_long_Bq": float(low_long.iloc[0]),
            "hypothesis_supported": bool(float(high_long.iloc[0]) > float(low_long.iloc[0]) + 0.05),
            "notes": "Supported if long-gap donor-only B_q is higher under high training synchrony than under low.",
        }
    return out


def regulation_regime_contrast(
    year_table: pd.DataFrame,
    *,
    policy: str = "always_simple",
    split: str = "eval",
) -> pd.DataFrame:
    """Borrowing across regulation classes is not assumed to transfer."""

    frame = year_table.loc[year_table["policy"].eq(policy) & year_table["split"].eq(split)].copy()
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for status, group in frame.groupby(frame["regulation_status"].fillna("unknown")):
        stats = network_equal_stats(group, "realized_benefit")
        rows.append(
            {
                "hypothesis": "regulation_regime",
                "regulation_status": status,
                "n_station_years": stats["n_station_years"],
                "n_networks": stats["n_networks"],
                "network_equal_Bq": stats["mean"],
                "ci_lo": stats["ci_lo"],
                "ci_hi": stats["ci_hi"],
                "harm_rate": float((pd.to_numeric(group["realized_benefit"], errors="coerce") < 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def historical_calibration_break(
    year_table: pd.DataFrame,
    *,
    policy: str = "always_simple",
    epsilon: float = NON_INFERIORITY_EPSILON_C,
) -> pd.DataFrame:
    """Regime-change check: hist vs eval mean B_q of the same simple policy.

    Hypothesis: a hydrologic/regulation shift large enough to matter will move
    eval B_q more than epsilon below hist B_q on the same networks.
    """

    frame = year_table.loc[year_table["policy"].eq(policy)].copy()
    rows = []
    for network_id, group in frame.groupby("network_id"):
        hist = group.loc[group["split"].eq("hist"), "realized_benefit"]
        ev = group.loc[group["split"].eq("eval"), "realized_benefit"]
        if hist.notna().sum() == 0 or ev.notna().sum() == 0:
            continue
        hist_mean = float(hist.mean())
        eval_mean = float(ev.mean())
        rows.append(
            {
                "hypothesis": "regime_change_break",
                "network_id": network_id,
                "n_hist": int(hist.notna().sum()),
                "n_eval": int(ev.notna().sum()),
                "hist_Bq": hist_mean,
                "eval_Bq": eval_mean,
                "eval_minus_hist": eval_mean - hist_mean,
                "breaks_epsilon": bool((eval_mean - hist_mean) < -float(epsilon)),
                "regulation_status": str(group["regulation_status"].iloc[0]) if "regulation_status" in group else "unknown",
            }
        )
    return pd.DataFrame(rows)


def thermal_response_bins(
    year_table: pd.DataFrame,
    *,
    policy: str = "always_simple",
    split: str = "eval",
    quantiles: Sequence[float] = (0.33, 0.67),
) -> pd.DataFrame:
    """Group stations by historical mean B_q tercile, then score eval.

    Historical diagnostic only: terciles are cut on hist years, applied to eval.
    """

    simple = year_table.loc[year_table["policy"].eq(policy)].copy()
    hist_mean = (
        simple.loc[simple["split"].eq("hist")]
        .groupby(["network_id", "station_id"])["realized_benefit"]
        .mean()
        .rename("hist_Bq")
    )
    if hist_mean.dropna().empty:
        return pd.DataFrame()
    cuts = hist_mean.quantile(list(quantiles))
    def _bin(value: float) -> str:
        if not np.isfinite(value):
            return "unknown"
        if value <= float(cuts.iloc[0]):
            return "low_hist_benefit"
        if value <= float(cuts.iloc[1]):
            return "mid_hist_benefit"
        return "high_hist_benefit"

    labels = hist_mean.map(_bin).rename("response_bin")
    ev = simple.loc[simple["split"].eq(split)].merge(
        hist_mean.reset_index(),
        on=["network_id", "station_id"],
        how="left",
    ).merge(labels.reset_index(), on=["network_id", "station_id"], how="left")
    ev["response_bin"] = ev["response_bin"].fillna("unknown")
    rows = []
    for bin_name, group in ev.groupby("response_bin"):
        stats = network_equal_stats(group, "realized_benefit")
        rows.append(
            {
                "hypothesis": "thermal_response_type",
                "response_bin": bin_name,
                "n_station_years": stats["n_station_years"],
                "n_networks": stats["n_networks"],
                "network_equal_Bq": stats["mean"],
                "ci_lo": stats["ci_lo"],
                "ci_hi": stats["ci_hi"],
                "harm_rate": float((pd.to_numeric(group["realized_benefit"], errors="coerce") < 0).mean()),
            }
        )
    return pd.DataFrame(rows)
