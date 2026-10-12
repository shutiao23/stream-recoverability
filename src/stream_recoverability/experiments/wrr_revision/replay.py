"""Station-year replay: multiple gaps, one completed record, one thermal loss."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.recovery_roster import season_label
from stream_recoverability.experiments.wrr_revision.recoverers import FittedRecoverer
from stream_recoverability.experiments.wrr_revision.thermal import series_losses


def select_nonoverlapping_gaps(
    gaps: pd.DataFrame,
    index: pd.DatetimeIndex,
    *,
    sort_by: Sequence[str] = ("gap_start", "gap_length"),
) -> pd.DataFrame:
    """Keep a feasible outage pattern: later experimental gaps may not overwrite earlier days."""

    if gaps.empty:
        return gaps.iloc[0:0].copy()
    ordered = gaps.sort_values(list(sort_by))
    occupied = np.zeros(len(index), dtype=bool)
    keep: list[object] = []
    for loc in ordered.index:
        row = ordered.loc[loc]
        start = int(index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        if start < 1 or start + length > len(index):
            continue
        if occupied[start : start + length].any():
            continue
        occupied[start : start + length] = True
        keep.append(loc)
    return ordered.loc[keep]


def select_mixed_duration_gaps(gaps: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """One gap per start date, cycling 30/90/180 when those lengths exist, then drop overlaps."""

    if gaps.empty:
        return gaps.iloc[0:0].copy()
    cycle = (30, 90, 180)
    starts = pd.to_datetime(gaps["gap_start"])
    chosen_locs: list[object] = []
    for i, start in enumerate(sorted(starts.unique())):
        group = gaps.loc[starts.eq(start)]
        lengths = group["gap_length"].astype(int)
        want = cycle[i % len(cycle)]
        if (lengths == want).any():
            chosen_locs.append(group.index[lengths.to_numpy() == want][0])
        else:
            chosen_locs.append((lengths - want).abs().idxmin())
    return select_nonoverlapping_gaps(gaps.loc[chosen_locs], index)


def year_gaps(
    placements: pd.DataFrame,
    *,
    station_id: str,
    year: int,
) -> pd.DataFrame:
    frame = placements.copy()
    frame["gap_start"] = pd.to_datetime(frame["gap_start"])
    return frame.loc[
        frame["station_id"].astype(str).eq(str(station_id)) & (frame["gap_start"].dt.year == int(year))
    ].sort_values(["gap_start", "gap_length"])


def hide_gap_interiors(
    truth: pd.Series,
    gaps: pd.DataFrame,
) -> pd.Series:
    """Replace every gap interior with NA so adjacent outages cannot supply boundaries."""

    masked = truth.copy()
    if gaps.empty:
        return masked
    for row in gaps.itertuples(index=False):
        start = int(truth.index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        if start < 0 or start + length > len(masked):
            continue
        masked.iloc[start : start + length] = np.nan
    return masked


def apply_fills(
    truth: pd.Series,
    gaps: Sequence[tuple[int, int, np.ndarray]],
) -> pd.Series:
    series = truth.copy()
    for start, length, values in gaps:
        series.iloc[int(start) : int(start) + int(length)] = values
    return series


def replay_case(
    truth: pd.Series,
    *,
    default_fill: np.ndarray,
    recoverers: Mapping[str, FittedRecoverer],
    features: pd.DataFrame,
    gaps: pd.DataFrame,
    predicted_benefit: pd.Series,
    adopt: pd.Series,
    chosen_recoverer: str | Sequence[str],
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
) -> dict[str, float]:
    """Hide every gap, apply the action vector, then score the completed year once."""

    index = truth.index
    year_mask = pd.Series(True, index=index)
    if "year" in gaps.columns:
        year_mask = index.year == int(gaps["year"].iloc[0])
    default_series = truth.copy()
    all_recon = truth.copy()
    chosen = truth.copy()
    n_adopted = 0
    n_gaps = 0
    pred_values = np.asarray(predicted_benefit)
    actions = np.asarray(adopt, dtype=bool)
    if len(pred_values) != len(gaps) or len(actions) != len(gaps):
        raise ValueError("predicted_benefit and adopt must be aligned with gaps rows")
    recoverer_names: Sequence[str] | str = chosen_recoverer
    if isinstance(recoverer_names, str):
        names = [recoverer_names] * len(gaps)
    else:
        names = [str(name) for name in recoverer_names]
        if len(names) != len(gaps):
            raise ValueError("chosen_recoverer series must align with gaps")
    masked_target = hide_gap_interiors(truth, gaps)
    for row, action, rec_name in zip(gaps.itertuples(index=False), actions, names):
        start = int(truth.index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        n_gaps += 1
        if start < 1 or start + length > len(truth):
            continue
        default_values = np.asarray(default_fill[start : start + length], dtype=float)
        rec = recoverers.get(rec_name) or recoverers.get("doy_climatology")
        try:
            recon = np.asarray(
                rec.predict_gap(
                    features=features,
                    target=masked_target,
                    start=start,
                    gap_length=length,
                    air=air,
                    discharge=discharge,
                ),
                dtype=float,
            )
        except Exception:
            recon = default_values
        if recon.shape != default_values.shape or not np.isfinite(recon).all():
            recon = default_values
        default_series.iloc[start : start + length] = default_values
        all_recon.iloc[start : start + length] = recon
        if bool(action):
            chosen.iloc[start : start + length] = recon
            n_adopted += 1
        else:
            chosen.iloc[start : start + length] = default_values
    year_truth = truth.loc[year_mask]
    losses_default = series_losses(year_truth, year_truth, default_series.loc[year_mask])
    # series_losses(truth, default, alternative) — compare strategies vs default
    vs_chosen = series_losses(year_truth, default_series.loc[year_mask], chosen.loc[year_mask])
    vs_all = series_losses(year_truth, default_series.loc[year_mask], all_recon.loc[year_mask])
    return {
        "n_gaps": float(n_gaps),
        "n_adopted": float(n_adopted),
        "adopt_rate": float(n_adopted / n_gaps) if n_gaps else float("nan"),
        "hottest_30_benefit": vs_chosen["hottest_30_benefit"],
        "exceed_days_20_benefit": vs_chosen["exceed_days_20_benefit"],
        "mae_benefit": vs_chosen["mae_benefit"],
        "hottest_30_benefit_all_reconstruct": vs_all["hottest_30_benefit"],
        "mae_benefit_all_reconstruct": vs_all["mae_benefit"],
        "hottest_30_truth": vs_chosen["hottest_30_truth"],
        "hottest_30_default": vs_chosen["hottest_30_default"],
        "hottest_30_policy": vs_chosen["hottest_30_alternative"],
        "hottest_30_default_loss": vs_chosen["hottest_30_default_loss"],
        "hottest_30_chosen_loss": vs_chosen["hottest_30_alternative_loss"],
        "hottest_30_policy_minus_truth": (
            float(vs_chosen["hottest_30_alternative"] - vs_chosen["hottest_30_truth"])
            if np.isfinite(vs_chosen["hottest_30_alternative"]) and np.isfinite(vs_chosen["hottest_30_truth"])
            else float("nan")
        ),
        "underestimate": float(
            vs_chosen["hottest_30_alternative"] < vs_chosen["hottest_30_truth"]
        )
        if np.isfinite(vs_chosen["hottest_30_alternative"]) and np.isfinite(vs_chosen["hottest_30_truth"])
        else float("nan"),
        "severe_underestimate": float(
            (vs_chosen["hottest_30_truth"] - vs_chosen["hottest_30_alternative"]) > 1.0
        )
        if np.isfinite(vs_chosen["hottest_30_alternative"]) and np.isfinite(vs_chosen["hottest_30_truth"])
        else float("nan"),
        "unused_default_is_zero": 1.0 if n_adopted == 0 else 0.0,
        "n_year_days": float(len(year_truth)),
        "default_mae_vs_truth": losses_default["mae_alternative"],
    }


def seasonal_rule_adopt(
    gaps: pd.DataFrame,
    *,
    max_length: int = 30,
    seasons: Sequence[str] = ("JJA",),
) -> pd.Series:
    labels = season_label(pd.to_datetime(gaps["gap_start"]))
    return pd.Series(
        (gaps["gap_length"].to_numpy(dtype=int) <= int(max_length))
        & np.isin(np.asarray(labels, dtype=object), list(seasons)),
        index=gaps.index,
    )
