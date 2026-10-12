"""Complete-year thermal B_q decision experiment (Steps 5–6, reused by 9–10).

Recoverers are fit on early complete years. Experimental missingness is placed
onto later complete years. Adopt rules are calibrated on held-out history and
scored only on final test years. The label is calendar-year hottest-30 B_q,
not daily MAE. Candidate-unseen station-years are never used to pick tau.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.recovery_roster import season_label
from stream_recoverability.experiments.wrr_revision.benefit import hierarchical_mean
from stream_recoverability.experiments.wrr_revision.decision import (
    choose_tau,
    policy_metrics,
    same_adoption_rate_random,
    simple_length_season_adopt,
)
from stream_recoverability.experiments.wrr_revision.failures import (
    heat_event_mask,
    heat_event_overlap,
    hide_donors_on_gaps,
    natural_gap_geometry,
    seasonal_threshold_from_training,
    transplant_month_length_pattern,
)
from stream_recoverability.experiments.wrr_revision.information import (
    deseasonalized_donor_correlation,
    information_conditioned_recoverer,
)
from stream_recoverability.experiments.wrr_revision.paths import (
    NON_INFERIORITY_EPSILON_C,
    SEVERE_UNDERESTIMATE_C,
    STEP1_UNIVERSE,
)
from stream_recoverability.experiments.wrr_revision.recoverers import FittedRecoverer, fit_station_recoverers
from stream_recoverability.experiments.wrr_revision.replay import (
    replay_case,
    select_mixed_duration_gaps,
    select_nonoverlapping_gaps,
)
from stream_recoverability.experiments.wrr_revision.score import (
    archived_placements,
    generated_placements,
    load_panel,
    score_gap,
)
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame

SIMPLE_RECOVERERS = (
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_only_ridge",
    "air_ridge",
)
GAP_LENGTHS = (30, 90, 180)
POLICY_ALWAYS = (
    "all_default",
    "always_simple",
    "always_donor_only",
    "always_smooth_climatology",
)


def load_trusted_roster(evidence_use: str | None = "design_development") -> pd.DataFrame:
    frame = pd.read_csv(STEP1_UNIVERSE / "trusted_river_complete_years.csv")
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    frame["year"] = frame["year"].astype(int)
    if evidence_use is not None:
        frame = frame.loc[frame["evidence_use"].eq(evidence_use)].copy()
    return frame


def complete_year_split(years: Sequence[int]) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Fit on early complete years, hist on later training years, eval on the rest."""

    ordered = tuple(int(year) for year in sorted(set(int(value) for value in years)))
    if len(ordered) <= 1:
        return ordered, (), ()
    if len(ordered) == 2:
        return ordered[:1], (), ordered[1:]
    cut = min(len(ordered) - 1, max(1, round(len(ordered) * 0.7)))
    train = ordered[:cut]
    evaluation = ordered[cut:]
    if len(train) >= 4:
        return train[:-2], train[-2:], evaluation
    if len(train) >= 2:
        return train[:-1], train[-1:], evaluation
    return train, (), evaluation


def both_boundaries(series: pd.Series, start: int, length: int) -> bool:
    if start < 1 or start + length >= len(series):
        return False
    left = float(pd.to_numeric(series.iloc[start - 1], errors="coerce"))
    right = float(pd.to_numeric(series.iloc[start + length], errors="coerce"))
    return bool(np.isfinite(left) and np.isfinite(right))


def donors_observed_in_gap(panel: pd.DataFrame, donors: Sequence[str], start: int, length: int) -> bool:
    if not donors:
        return False
    block = panel.loc[:, [name for name in donors if name in panel.columns]].iloc[start : start + length]
    return bool(not block.empty and block.notna().to_numpy().all())


def air_observed_in_gap(air: pd.Series | None, index: pd.DatetimeIndex, start: int, length: int) -> bool:
    if air is None:
        return False
    block = pd.to_numeric(air, errors="coerce").reindex(index).iloc[start : start + length]
    return bool(np.isfinite(block.to_numpy(dtype=float)).all())


def placements_for_year(
    daily: pd.DataFrame,
    *,
    network_id: str,
    station_id: str,
    year: int,
    donors: Sequence[str],
    panel_name: str,
) -> pd.DataFrame:
    year_mask = pd.Series(daily.index.year == int(year), index=daily.index)
    if panel_name == "first":
        archived = archived_placements(network_id)
        station_year = archived.loc[
            archived["station_id"].astype(str).eq(str(station_id))
            & (pd.to_datetime(archived["gap_start"]).dt.year == int(year))
            & pd.to_numeric(archived["gap_length"], errors="coerce").isin(GAP_LENGTHS)
        ]
        if not station_year.empty:
            return station_year
    tasks = generated_placements(
        daily,
        target_station=station_id,
        donors=donors,
        evaluation_mask=year_mask,
        gap_lengths=GAP_LENGTHS,
        count=4,
    )
    if not tasks:
        tasks = generated_placements(
            daily,
            target_station=station_id,
            donors=(),
            evaluation_mask=year_mask,
            gap_lengths=GAP_LENGTHS,
            count=4,
        )
    if not tasks:
        return pd.DataFrame()
    return pd.DataFrame(tasks)


def transplanted_gaps_for_year(
    daily: pd.DataFrame,
    *,
    station_id: str,
    year: int,
    fit_mask: pd.Series,
) -> pd.DataFrame:
    """Place historical month/length/count from years before ``year``.

    Geometry is taken from the raw observed record, including incomplete
    years. Complete-year fit masks have no natural gaps by construction.
    """

    prior = pd.to_numeric(daily[station_id], errors="coerce").where(daily.index.year < int(year))
    geometry = natural_gap_geometry(prior)
    if geometry.empty:
        pieces = [geometry]
        for other in daily.columns.astype(str):
            if other == str(station_id):
                continue
            other_prior = pd.to_numeric(daily[other], errors="coerce").where(daily.index.year < int(year))
            pieces.append(natural_gap_geometry(other_prior))
        geometry = pd.concat(pieces, ignore_index=True) if pieces else geometry
    year_index = daily.index[daily.index.year == int(year)]
    transplanted = transplant_month_length_pattern(year_index, geometry, max_gaps=4)
    if transplanted.empty:
        return transplanted
    transplanted["station_id"] = str(station_id)
    transplanted["year"] = int(year)
    return transplanted


def choose_year_gaps(
    daily: pd.DataFrame,
    *,
    network_id: str,
    station_id: str,
    year: int,
    donors: Sequence[str],
    panel_name: str,
    fit_mask: pd.Series,
    failure_mode: str = "archived_or_generated",
) -> pd.DataFrame:
    if failure_mode == "natural_transplant":
        gaps = transplanted_gaps_for_year(daily, station_id=station_id, year=year, fit_mask=fit_mask)
        if gaps.empty:
            gaps = placements_for_year(
                daily,
                network_id=network_id,
                station_id=station_id,
                year=year,
                donors=donors,
                panel_name=panel_name,
            )
            if not gaps.empty:
                gaps = gaps.copy()
                gaps["source"] = "archived_or_generated_fallback"
    else:
        gaps = placements_for_year(
            daily,
            network_id=network_id,
            station_id=station_id,
            year=year,
            donors=donors,
            panel_name=panel_name,
        )
    if gaps.empty:
        return gaps
    gaps = gaps.copy()
    gaps["gap_start"] = pd.to_datetime(gaps["gap_start"])
    gaps["year"] = int(year)
    mixed = select_mixed_duration_gaps(gaps, daily.index)
    if mixed.empty:
        mixed = select_nonoverlapping_gaps(gaps, daily.index)
    return mixed


def gap_decision_rows(
    daily: pd.DataFrame,
    *,
    network_id: str,
    station_id: str,
    year: int,
    split: str,
    donors: Sequence[str],
    recoverers: Mapping[str, FittedRecoverer],
    features: pd.DataFrame,
    default_fill: np.ndarray,
    gaps: pd.DataFrame,
    air: pd.Series | None,
    heat_overlap: pd.Series | None = None,
) -> pd.DataFrame:
    truth = pd.to_numeric(daily[station_id], errors="coerce")
    rows: list[dict[str, object]] = []
    for i, row in enumerate(gaps.itertuples(index=False)):
        start = int(daily.index.get_indexer([pd.Timestamp(row.gap_start)])[0])
        length = int(row.gap_length)
        donors_present = donors_observed_in_gap(daily, donors, start, length)
        right_present = both_boundaries(truth, start, length)
        air_present = air_observed_in_gap(air, daily.index, start, length)
        chosen = information_conditioned_recoverer(
            donors_observed=donors_present,
            right_present=right_present,
            air_present=air_present,
            gap_length=length,
        )
        recoverer = recoverers.get(chosen) or recoverers["doy_climatology"]
        scored = score_gap(
            recoverer,
            features=features,
            target=truth,
            start=start,
            gap_length=length,
            default_fill=default_fill,
            air=air,
        )
        donor_scored = None
        if "donor_only_ridge" in recoverers and donors_present:
            donor_scored = score_gap(
                recoverers["donor_only_ridge"],
                features=features,
                target=truth,
                start=start,
                gap_length=length,
                default_fill=default_fill,
                air=air,
            )
        rows.append(
            {
                "network_id": network_id,
                "station_id": station_id,
                "year": int(year),
                "split": split,
                "gap_start": pd.Timestamp(row.gap_start),
                "gap_length": length,
                "season": str(season_label(pd.DatetimeIndex([pd.Timestamp(row.gap_start)]))[0]),
                "donors_present": donors_present,
                "right_present": right_present,
                "air_present": air_present,
                "chosen_recoverer": chosen,
                "mae_benefit_simple": float("nan") if scored is None else scored["mae_benefit"],
                "mae_benefit_donor": float("nan") if donor_scored is None else donor_scored["mae_benefit"],
                "heat_event_overlap": bool(heat_overlap.iloc[i]) if heat_overlap is not None else False,
            }
        )
    return pd.DataFrame(rows)


def _replay(
    truth: pd.Series,
    *,
    default_fill: np.ndarray,
    recoverers: Mapping[str, FittedRecoverer],
    features: pd.DataFrame,
    gaps: pd.DataFrame,
    adopt: pd.Series,
    chosen: Sequence[str],
    air: pd.Series | None,
) -> dict[str, float]:
    predicted = pd.Series(np.zeros(len(gaps), dtype=float), index=gaps.index)
    return replay_case(
        truth,
        default_fill=default_fill,
        recoverers=recoverers,
        features=features,
        gaps=gaps,
        predicted_benefit=predicted,
        adopt=adopt,
        chosen_recoverer=list(chosen),
        air=air,
    )


def year_policy_rows(
    daily: pd.DataFrame,
    *,
    network_id: str,
    station_id: str,
    year: int,
    split: str,
    recoverers: Mapping[str, FittedRecoverer],
    features: pd.DataFrame,
    default_fill: np.ndarray,
    gaps: pd.DataFrame,
    gap_rows: pd.DataFrame,
    air: pd.Series | None,
    regulation_status: str = "unknown",
    n_donors: int = 0,
    mean_donor_corr: float = float("nan"),
) -> pd.DataFrame:
    truth = pd.to_numeric(daily[station_id], errors="coerce")
    chosen = gap_rows["chosen_recoverer"].astype(str).tolist()
    donor_names = [
        "donor_only_ridge" if bool(flag) and "donor_only_ridge" in recoverers else "doy_climatology"
        for flag in gap_rows["donors_present"].tolist()
    ]
    adopt_donor = pd.Series([name == "donor_only_ridge" for name in donor_names], index=gaps.index)
    smooth_names = ["smooth_climatology"] * len(gaps)
    adopt_all = pd.Series(True, index=gaps.index)
    adopt_none = pd.Series(False, index=gaps.index)
    adopt_short = simple_length_season_adopt(gaps)
    policies = {
        "all_default": (adopt_none, chosen),
        "always_simple": (adopt_all, chosen),
        "always_donor_only": (adopt_donor, donor_names),
        "always_smooth_climatology": (adopt_all, smooth_names),
        "simple_length_season": (adopt_short, chosen),
    }
    rows: list[dict[str, object]] = []
    shared = {
        "network_id": network_id,
        "station_id": station_id,
        "year": int(year),
        "split": split,
        "n_gaps": int(len(gaps)),
        "mean_gap_length": float(pd.to_numeric(gaps["gap_length"], errors="coerce").mean()) if len(gaps) else float("nan"),
        "max_gap_length": float(pd.to_numeric(gaps["gap_length"], errors="coerce").max()) if len(gaps) else float("nan"),
        "season_longest": (
            str(
                season_label(
                    pd.DatetimeIndex(
                        [gaps.loc[pd.to_numeric(gaps["gap_length"], errors="coerce").idxmax(), "gap_start"]]
                    )
                )[0]
            )
            if len(gaps)
            else "none"
        ),
        "donors_any": bool(gap_rows["donors_present"].any()) if len(gap_rows) else False,
        "air_any": bool(gap_rows["air_present"].any()) if len(gap_rows) else False,
        "heat_event_any": bool(gap_rows["heat_event_overlap"].any()) if "heat_event_overlap" in gap_rows else False,
        "regulation_status": regulation_status,
        "n_donors": int(n_donors),
        "mean_donor_corr": float(mean_donor_corr),
        "mae_benefit_simple_mean": float(pd.to_numeric(gap_rows["mae_benefit_simple"], errors="coerce").mean())
        if len(gap_rows)
        else float("nan"),
    }
    for name, (adopt, recoverer_names) in policies.items():
        scored = _replay(
            truth,
            default_fill=default_fill,
            recoverers=recoverers,
            features=features,
            gaps=gaps,
            adopt=pd.Series(np.asarray(adopt, dtype=bool), index=gaps.index),
            chosen=recoverer_names,
            air=air,
        )
        row = dict(shared)
        row.update(scored)
        row["policy"] = name
        row["realized_benefit"] = scored["hottest_30_benefit"]
        row["reject_reason"] = "all_default" if name == "all_default" else "none"
        rows.append(row)
    simple_b = next(item["realized_benefit"] for item in rows if item["policy"] == "always_simple")
    oracle_adopt = pd.Series(bool(np.isfinite(simple_b) and simple_b > 0), index=gaps.index)
    if bool(oracle_adopt.iloc[0]) if len(oracle_adopt) else False:
        oracle = next(item for item in rows if item["policy"] == "always_simple").copy()
    else:
        oracle = next(item for item in rows if item["policy"] == "all_default").copy()
    oracle["policy"] = "oracle_year_adopt"
    oracle["reject_reason"] = "oracle_truth" if oracle["policy"] else "oracle_truth"
    oracle["reject_reason"] = "none" if bool(np.isfinite(simple_b) and simple_b > 0) else "oracle_nonpositive"
    rows.append(oracle)
    return pd.DataFrame(rows)


def attach_calibrated_policies(
    year_table: pd.DataFrame,
    *,
    epsilon: float = NON_INFERIORITY_EPSILON_C,
    seed: int = 0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Calibrate year-level and MAE-label rules on hist; score eval only for comparison."""

    wide = year_table.loc[year_table["policy"].eq("always_simple")].copy().reset_index(drop=True)
    if wide.empty:
        return year_table, {"tau_thermal": 0.0, "tau_mae": 0.0}
    wide["gap_length"] = wide["max_gap_length"].round().astype("Int64")
    wide["season"] = wide["season_longest"]
    hist = wide.loc[wide["split"].eq("hist")].copy()
    ev = wide.loc[wide["split"].eq("eval")].copy()
    if hist.empty:
        wide["pred_thermal"] = 0.0
        wide["pred_mae"] = wide["mae_benefit_simple_mean"]
        freeze = {"tau_thermal": 0.0, "tau_mae": 0.0, "n_hist": 0}
    else:
        thermal_pred = hierarchical_mean(hist, wide, value_col="realized_benefit", name="pred_thermal")
        mae_hist = hist.copy()
        mae_hist["realized_benefit"] = mae_hist["mae_benefit_simple_mean"]
        mae_pred = hierarchical_mean(mae_hist, wide, value_col="realized_benefit", name="pred_mae")
        wide = wide.copy()
        wide["pred_thermal"] = thermal_pred["pred_thermal"]
        wide["pred_mae"] = mae_pred["pred_mae"]
        hist_idx = wide["split"].eq("hist")
        tau_thermal = choose_tau(wide.loc[hist_idx, "pred_thermal"], wide.loc[hist_idx, "realized_benefit"])
        tau_mae = choose_tau(wide.loc[hist_idx, "pred_mae"], wide.loc[hist_idx, "mae_benefit_simple_mean"])
        freeze = {
            "tau_thermal": float(tau_thermal["tau"]),
            "tau_mae": float(tau_mae["tau"]),
            "n_hist": int(hist_idx.sum()),
            "hist_net_thermal": float(tau_thermal["net_benefit_all_cases"]),
        }
    wide["adopt_thermal"] = pd.to_numeric(wide["pred_thermal"], errors="coerce") > freeze["tau_thermal"]
    wide["adopt_mae"] = pd.to_numeric(wide["pred_mae"], errors="coerce") > freeze["tau_mae"]
    rng = np.random.default_rng(int(seed))
    wide["adopt_random"] = same_adoption_rate_random(wide["adopt_thermal"], rng=rng)

    lookup = year_table.set_index(["network_id", "station_id", "year", "policy"])

    def _row(key: tuple[object, object, int, str]) -> dict[str, object]:
        item = lookup.loc[key]
        if isinstance(item, pd.DataFrame):
            item = item.iloc[0]
        row = item.to_dict()
        row["network_id"] = key[0]
        row["station_id"] = key[1]
        row["year"] = key[2]
        row["policy"] = key[3]
        return row

    extra_rows: list[pd.DataFrame] = []
    for _, case in wide.iterrows():
        key = (case["network_id"], case["station_id"], int(case["year"]))
        simple = _row((*key, "always_simple"))
        default = _row((*key, "all_default"))
        for policy, adopt_flag, reason in (
            ("year_thermal_tau", bool(case["adopt_thermal"]), "predicted_Bq_le_tau"),
            ("gap_mae_tau_yearproxy", bool(case["adopt_mae"]), "predicted_mae_le_tau"),
            ("random_same_rate", bool(case["adopt_random"]), "random_reject"),
        ):
            source = simple if adopt_flag else default
            row = dict(source)
            row["policy"] = policy
            row["predicted_benefit"] = float(case["pred_thermal"] if policy != "gap_mae_tau_yearproxy" else case["pred_mae"])
            row["reject_reason"] = "none" if adopt_flag else reason
            extra_rows.append(pd.DataFrame([row]))
    calibrated = pd.concat(extra_rows, ignore_index=True) if extra_rows else pd.DataFrame()
    out = pd.concat([year_table, calibrated], ignore_index=True)
    freeze["epsilon_C"] = float(epsilon)
    freeze["severe_underestimate_C"] = float(SEVERE_UNDERESTIMATE_C)
    freeze["eval_n"] = int(ev.shape[0])
    return out, freeze


def network_equal_stats(frame: pd.DataFrame, value_col: str, *, n_boot: int = 2000, seed: int = 0) -> dict[str, float]:
    values = pd.to_numeric(frame[value_col], errors="coerce")
    usable = frame.loc[values.notna(), ["network_id"]].copy()
    usable[value_col] = values.loc[values.notna()]
    if usable.empty:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n_networks": 0, "n_station_years": 0}
    per_net = usable.groupby("network_id")[value_col].mean().dropna()
    if per_net.empty:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "n_networks": 0, "n_station_years": int(len(usable))}
    mean = float(per_net.mean())
    rng = np.random.default_rng(int(seed))
    arr = per_net.to_numpy(dtype=float)
    if len(arr) == 1:
        return {
            "mean": mean,
            "ci_lo": mean,
            "ci_hi": mean,
            "n_networks": 1,
            "n_station_years": int(len(usable)),
        }
    boots = np.array([arr[rng.integers(0, len(arr), len(arr))].mean() for _ in range(int(n_boot))])
    return {
        "mean": mean,
        "ci_lo": float(np.quantile(boots, 0.025)),
        "ci_hi": float(np.quantile(boots, 0.975)),
        "n_networks": int(len(per_net)),
        "n_station_years": int(len(usable)),
    }


def compare_eval_policies(year_table: pd.DataFrame) -> pd.DataFrame:
    ev = year_table.loc[year_table["split"].eq("eval")].copy()
    rows = []
    simple = ev.loc[ev["policy"].eq("always_simple")]
    simple_stats = network_equal_stats(simple, "realized_benefit")
    simple_harm = float((pd.to_numeric(simple["realized_benefit"], errors="coerce") < 0).mean()) if len(simple) else float("nan")
    for policy, group in ev.groupby("policy"):
        stats = network_equal_stats(group, "realized_benefit")
        harm = float((pd.to_numeric(group["realized_benefit"], errors="coerce") < 0).mean())
        severe = float(pd.to_numeric(group.get("severe_underestimate", pd.Series(dtype=float)), errors="coerce").mean())
        abs_default = float(pd.to_numeric(group.get("hottest_30_default_loss", pd.Series(dtype=float)), errors="coerce").mean())
        abs_policy = float(pd.to_numeric(group.get("hottest_30_chosen_loss", pd.Series(dtype=float)), errors="coerce").mean())
        over = float(pd.to_numeric(group.get("hottest_30_policy_minus_truth", pd.Series(dtype=float)), errors="coerce").gt(0).mean())
        under = float(pd.to_numeric(group.get("underestimate", pd.Series(dtype=float)), errors="coerce").mean())
        delta = stats["mean"] - simple_stats["mean"] if np.isfinite(stats["mean"]) and np.isfinite(simple_stats["mean"]) else float("nan")
        rows.append(
            {
                "policy": policy,
                "n_station_years": stats["n_station_years"],
                "n_networks": stats["n_networks"],
                "network_equal_Bq": stats["mean"],
                "ci_lo": stats["ci_lo"],
                "ci_hi": stats["ci_hi"],
                "delta_vs_always_simple": delta,
                "noninferior_eps_0_05": (
                    float(delta >= -NON_INFERIORITY_EPSILON_C) if np.isfinite(delta) else float("nan")
                ),
                "beats_simple_mean": float(delta > 0) if np.isfinite(delta) else float("nan"),
                "harm_rate": harm,
                "harm_rate_simple": simple_harm,
                "harm_reduced": float(harm < simple_harm) if np.isfinite(harm) and np.isfinite(simple_harm) else float("nan"),
                "severe_underestimate_rate": severe,
                "mean_abs_default_error": abs_default,
                "mean_abs_policy_error": abs_policy,
                "overestimate_rate": over,
                "underestimate_rate": under,
                "adopt_rate": float(pd.to_numeric(group.get("adopt_rate", pd.Series(dtype=float)), errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("network_equal_Bq", ascending=False)


def apply_frozen_year_policy(
    year_table: pd.DataFrame,
    freeze: Mapping[str, float],
    *,
    history: pd.DataFrame,
) -> pd.DataFrame:
    """Apply a previously frozen tau and development history. Does not retune."""

    labeled = year_table.copy()
    hist = history.loc[history["policy"].eq("always_simple") & history["split"].eq("hist")].copy()
    simple = labeled.loc[labeled["policy"].eq("always_simple")].copy()
    for frame in (hist, simple):
        frame["gap_length"] = pd.to_numeric(frame.get("max_gap_length", frame.get("gap_length")), errors="coerce").round()
        frame["season"] = frame.get("season_longest", frame.get("season"))
    if hist.empty or simple.empty:
        simple["pred_thermal"] = 0.0
    else:
        pred = hierarchical_mean(hist, simple, value_col="realized_benefit", name="pred_thermal")
        simple = simple.copy()
        simple["pred_thermal"] = pred["pred_thermal"]
    tau = float(freeze.get("tau_thermal", 0.0))
    simple["adopt_thermal"] = pd.to_numeric(simple["pred_thermal"], errors="coerce") > tau
    lookup = labeled.set_index(["network_id", "station_id", "year", "policy"])
    rows = []
    for _, case in simple.iterrows():
        key = (case["network_id"], case["station_id"], int(case["year"]))
        item = lookup.loc[(*key, "always_simple" if bool(case["adopt_thermal"]) else "all_default")]
        if isinstance(item, pd.DataFrame):
            item = item.iloc[0]
        row = item.to_dict()
        row["network_id"] = key[0]
        row["station_id"] = key[1]
        row["year"] = key[2]
        row["policy"] = "year_thermal_tau_frozen"
        row["predicted_benefit"] = float(case["pred_thermal"])
        row["reject_reason"] = "none" if bool(case["adopt_thermal"]) else "predicted_Bq_le_tau"
        rows.append(row)
    return pd.concat([labeled, pd.DataFrame(rows)], ignore_index=True)


def score_co_missing_year(
    daily: pd.DataFrame,
    *,
    network_id: str,
    station_id: str,
    year: int,
    split: str,
    donors: Sequence[str],
    recoverers: Mapping[str, FittedRecoverer],
    default_fill: np.ndarray,
    gaps: pd.DataFrame,
    air: pd.Series | None,
    regulation_status: str,
    n_donors: int,
    mean_donor_corr: float,
    heat_overlap: pd.Series | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Same gaps with donors hidden: tests the no-donor branch of the simple policy."""

    from stream_recoverability.experiments.wrr_revision.features import base_feature_frame

    masked = hide_donors_on_gaps(daily, donors, gaps)
    features = base_feature_frame(masked, donors=donors, air=air)
    gap_rows = gap_decision_rows(
        masked,
        network_id=network_id,
        station_id=station_id,
        year=year,
        split=split,
        donors=donors,
        recoverers=recoverers,
        features=features,
        default_fill=default_fill,
        gaps=gaps,
        air=air,
        heat_overlap=heat_overlap,
    )
    years = year_policy_rows(
        masked,
        network_id=network_id,
        station_id=station_id,
        year=year,
        split=split,
        recoverers=recoverers,
        features=features,
        default_fill=default_fill,
        gaps=gaps,
        gap_rows=gap_rows,
        air=air,
        regulation_status=regulation_status,
        n_donors=n_donors,
        mean_donor_corr=mean_donor_corr,
    )
    gap_rows["failure_mode"] = "co_missing_donors"
    years["failure_mode"] = "co_missing_donors"
    return gap_rows, years


def training_heat_overlap(daily: pd.DataFrame, station_id: str, fit_mask: pd.Series, gaps: pd.DataFrame) -> pd.Series:
    series = pd.to_numeric(daily[station_id], errors="coerce")
    threshold = seasonal_threshold_from_training(series, fit_mask)
    events = heat_event_mask(series, threshold, min_duration=3)
    return heat_event_overlap(gaps, events)


def score_network_complete_years(
    network_id: str,
    roster: pd.DataFrame,
    *,
    air_by_station: Mapping[str, pd.Series] | None = None,
    failure_mode: str = "archived_or_generated",
    include_co_missing: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit on early complete years and replay later complete years for one network."""

    from stream_recoverability.experiments.development_data import joint_complete_feature_rosters

    subset = roster.loc[roster["network_id"].astype(str).eq(str(network_id))].copy()
    if subset.empty:
        return pd.DataFrame(), pd.DataFrame()
    panel_name = "second" if str(subset["source_root"].iloc[0]) == "second" else "first"
    daily = load_panel(network_id, panel_name).copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    air_by_station = air_by_station or {}
    gap_frames: list[pd.DataFrame] = []
    year_frames: list[pd.DataFrame] = []
    for station in subset["station_id"].astype(str).unique():
        if station not in daily.columns:
            continue
        years = tuple(int(value) for value in sorted(subset.loc[subset["station_id"].eq(station), "year"]))
        fit_years, hist_years, eval_years = complete_year_split(years)
        if not eval_years and not hist_years:
            continue
        fit_mask = pd.Series(daily.index.year.isin(fit_years), index=daily.index)
        if int((fit_mask & daily[station].notna()).sum()) < 40:
            continue
        donors, _, _ = joint_complete_feature_rosters(
            daily.loc[fit_mask],
            target=station,
            donor_candidates=tuple(col for col in daily.columns if col != station),
            meteorology_candidates=(),
            hydraulics_candidates=(),
        )
        later = pd.Series(daily.index.year.isin(hist_years + eval_years), index=daily.index)
        donors = tuple(donor for donor in donors if int((later & daily[donor].notna()).sum()) >= 30)
        air = air_by_station.get(station)
        features = base_feature_frame(daily, donors=donors, air=air)
        include = tuple(name for name in SIMPLE_RECOVERERS if name != "air_ridge" or air is not None)
        try:
            recoverers = fit_station_recoverers(
                daily,
                target_station=station,
                donors=donors,
                train_mask=fit_mask,
                features=features,
                air=air,
                include_external=air is not None,
                include_names=include,
            )
        except ValueError:
            continue
        if "doy_climatology" not in recoverers:
            continue
        default_fill = np.asarray(recoverers["doy_climatology"].extra["values"], dtype=float)
        corr = deseasonalized_donor_correlation(
            daily,
            target_station=station,
            donors=donors,
            train_mask=fit_mask,
        )
        mean_corr = float(corr.abs().mean()) if not corr.empty else float("nan")
        regulation = str(subset["regulation_status"].iloc[0]) if "regulation_status" in subset else "unknown"
        split_map = {year: "hist" for year in hist_years}
        split_map.update({year: "eval" for year in eval_years})
        for year, split in split_map.items():
            year_index = daily.index[daily.index.year == int(year)]
            if len(year_index) < 365:
                continue
            if not pd.to_numeric(daily.loc[year_index, station], errors="coerce").notna().all():
                continue
            gaps = choose_year_gaps(
                daily,
                network_id=network_id,
                station_id=station,
                year=year,
                donors=donors,
                panel_name=panel_name,
                fit_mask=fit_mask,
                failure_mode=failure_mode,
            )
            if gaps.empty:
                continue
            heat = training_heat_overlap(daily, station, fit_mask, gaps)
            gap_rows = gap_decision_rows(
                daily,
                network_id=network_id,
                station_id=station,
                year=year,
                split=split,
                donors=donors,
                recoverers=recoverers,
                features=features,
                default_fill=default_fill,
                gaps=gaps,
                air=air,
                heat_overlap=heat,
            )
            years_out = year_policy_rows(
                daily,
                network_id=network_id,
                station_id=station,
                year=year,
                split=split,
                recoverers=recoverers,
                features=features,
                default_fill=default_fill,
                gaps=gaps,
                gap_rows=gap_rows,
                air=air,
                regulation_status=regulation,
                n_donors=len(donors),
                mean_donor_corr=mean_corr,
            )
            gap_rows["failure_mode"] = failure_mode
            years_out["failure_mode"] = failure_mode
            gap_frames.append(gap_rows)
            year_frames.append(years_out)
            if include_co_missing and donors:
                g2, y2 = score_co_missing_year(
                    daily,
                    network_id=network_id,
                    station_id=station,
                    year=year,
                    split=split,
                    donors=donors,
                    recoverers=recoverers,
                    default_fill=default_fill,
                    gaps=gaps,
                    air=air,
                    regulation_status=regulation,
                    n_donors=len(donors),
                    mean_donor_corr=mean_corr,
                    heat_overlap=heat,
                )
                gap_frames.append(g2)
                year_frames.append(y2)
    gaps_out = pd.concat(gap_frames, ignore_index=True) if gap_frames else pd.DataFrame()
    years_out = pd.concat(year_frames, ignore_index=True) if year_frames else pd.DataFrame()
    return gaps_out, years_out

