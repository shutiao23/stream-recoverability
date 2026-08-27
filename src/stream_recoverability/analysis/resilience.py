"""Monitoring-network failure curves, AUC, and station importance."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from itertools import chain, combinations
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.analysis.evidence_boundaries import (
    MIN_INDEPENDENT_CLUSTERS,
    WITHHELD_STATUS,
    year_block_mean_interval,
)

_trapezoid = getattr(np, "trapezoid", None) or np.trapz
RESILIENCE_EXPERIMENT = "SCI_NET"


def _preserve_optional_text(frame: pd.DataFrame, *columns: str) -> pd.DataFrame:
    """Keep explicit None sentinels that pandas 3 would coerce to NaN."""

    if frame.empty:
        return frame
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            continue
        values = [
            None
            if not isinstance(value, str) and (value is None or pd.isna(value))
            else value
            for value in result[column].tolist()
        ]
        result[column] = pd.Series(values, index=result.index, dtype=object)
    return result


RESILIENCE_NETWORK_SIZE = 3
RESILIENCE_GROUP_COLUMNS = (
    "experiment",
    "mask_type",
    "layout",
    "outage_mode",
    "overlap_ratio",
    "variable_pattern",
    "pattern",
    "window_length",
    "training_protocol",
    "fit_split",
    "tuning_split",
    "evaluation_split",
    "validation_scope",
    "target_station_id",
    "station_id",
    "target",
    "model",
    "gap_length",
)
RESILIENCE_UNIT_COLUMNS = (
    *RESILIENCE_GROUP_COLUMNS,
    "target_gap_id",
    "mask_seed",
    "training_seed",
)


def parse_failed_sites(value: object) -> tuple[str, ...]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "full_network", "[]"}:
            return ()
        if text.startswith("["):
            parsed = json.loads(text)
            tokens = [str(item) for item in parsed]
        else:
            tokens = [item for item in re.split(r"[+,|;/\s]+", text) if item]
    elif isinstance(value, (list, tuple, set, frozenset, np.ndarray)):
        tokens = [str(item) for item in value]
    else:
        tokens = [str(value)]
    return tuple(sorted({token.strip() for token in tokens if token.strip()}))


def _with_failures(
    events: pd.DataFrame,
    failed_sites_col: str,
    total_sites: int | None,
) -> tuple[pd.DataFrame, int, str | None]:
    if failed_sites_col not in events:
        raise ValueError(f"network resilience requires column: {failed_sites_col}")
    data = events.copy()
    data["failed_sites"] = data[failed_sites_col].map(parse_failed_sites)
    data["failed_count"] = data["failed_sites"].map(len).astype(int)
    if total_sites is None:
        if (
            "network_size" in data
            and pd.to_numeric(data["network_size"], errors="coerce").notna().any()
        ):
            total_sites = int(
                pd.to_numeric(data["network_size"], errors="coerce").max()
            )
            reason = None
        else:
            all_sites = (
                set().union(*data["failed_sites"].tolist()) if len(data) else set()
            )
            total_sites = max(
                len(all_sites), int(data["failed_count"].max()) if len(data) else 0
            )
            reason = "network size inferred from observed failed-site labels"
    else:
        reason = None
    if total_sites < 1:
        raise ValueError("total_sites must be positive or inferable")
    if (data["failed_count"] > total_sites).any():
        raise ValueError("a failure set is larger than total_sites")
    data["failure_fraction"] = data["failed_count"] / float(total_sites)
    data["failure_class"] = np.select(
        [
            data["failed_count"].eq(0),
            data["failed_count"].eq(1),
            data["failed_count"].eq(total_sites),
            data["failed_count"].eq(2),
        ],
        ["none", "single", "full_network", "double"],
        default="multiple",
    )
    return data, total_sites, reason


def _failure_powerset(sites: tuple[str, ...]) -> set[tuple[str, ...]]:
    return {
        tuple(subset)
        for subset in chain.from_iterable(
            combinations(sites, size) for size in range(len(sites) + 1)
        )
    }


def _failure_sets_json(values: set[tuple[str, ...]]) -> str:
    return json.dumps([list(value) for value in sorted(values)], separators=(",", ":"))


def complete_resilience_units(
    events: pd.DataFrame,
    *,
    failed_sites_col: str = "failed_stations",
    total_sites: int | None = None,
    unit_cols: Sequence[str] = RESILIENCE_UNIT_COLUMNS,
    value_cols: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep only SCI_NET replicate units containing the full three-site powerset."""

    required = {
        "experiment",
        "station_id",
        "target",
        "target_gap_id",
        "model",
        "gap_length",
        "mask_seed",
        "training_seed",
        failed_sites_col,
        *value_cols,
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"network resilience requires columns: {missing}")
    is_science_network = (
        events["experiment"]
        .astype("string")
        .str.upper()
        .eq(RESILIENCE_EXPERIMENT)
        .fillna(False)
    )
    if events.empty or not is_science_network.all():
        raise ValueError("network resilience accepts only experiment='SCI_NET'")
    if total_sites is not None and total_sites != RESILIENCE_NETWORK_SIZE:
        raise ValueError("SCI_NET resilience requires exactly three network stations")
    if "network_size" in events:
        network_sizes = pd.to_numeric(events["network_size"], errors="coerce").dropna()
        if len(network_sizes) and not network_sizes.eq(RESILIENCE_NETWORK_SIZE).all():
            raise ValueError("SCI_NET rows must declare network_size=3")

    data, _, _ = _with_failures(
        events.reset_index(drop=True), failed_sites_col, RESILIENCE_NETWORK_SIZE
    )
    active_units = [column for column in unit_cols if column in data]
    diagnostics: list[dict[str, Any]] = []
    complete_indices: list[int] = []
    grouped = data.groupby(active_units, dropna=False, observed=True, sort=False)
    for group_key, group in grouped:
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(zip(active_units, group_key, strict=True))
        observed = set(group["failed_sites"])
        station_universe = tuple(sorted(set().union(*observed))) if observed else ()
        expected = (
            _failure_powerset(station_universe)
            if len(station_universe) == RESILIENCE_NETWORK_SIZE
            else set()
        )
        failure_counts = group["failed_sites"].value_counts()
        duplicate_sets = set(failure_counts.loc[failure_counts.gt(1)].index)
        nonfinite_counts = {
            column: int(
                (~np.isfinite(pd.to_numeric(group[column], errors="coerce"))).sum()
            )
            for column in value_cols
        }
        missing_sets = expected - observed
        extra_sets = observed - expected if expected else observed
        if (
            observed == expected
            and len(group) == 2**RESILIENCE_NETWORK_SIZE
            and not duplicate_sets
            and not any(nonfinite_counts.values())
        ):
            complete_indices.extend(group.index.tolist())
            continue
        reasons: list[str] = []
        if len(station_universe) != RESILIENCE_NETWORK_SIZE:
            reasons.append(
                f"failure labels cover {len(station_universe)} stations, expected 3"
            )
        if len(observed) != 2**RESILIENCE_NETWORK_SIZE:
            reasons.append(f"found {len(observed)} unique failure sets, expected 8")
        if duplicate_sets:
            reasons.append(
                f"duplicate failure sets: {_failure_sets_json(duplicate_sets)}"
            )
        for column, count in nonfinite_counts.items():
            if count:
                reasons.append(f"{count} non-finite {column} values")
        if missing_sets:
            reasons.append(f"missing failure sets: {_failure_sets_json(missing_sets)}")
        if extra_sets:
            reasons.append(f"unexpected failure sets: {_failure_sets_json(extra_sets)}")
        diagnostics.append(
            {
                **metadata,
                "n_rows": len(group),
                "n_unique_failure_sets": len(observed),
                "observed_failure_sets": _failure_sets_json(observed),
                "reason": "; ".join(reasons),
            }
        )
    complete = data.loc[complete_indices].reset_index(drop=True)
    return complete, pd.DataFrame(diagnostics)


def resilience_curve(
    events: pd.DataFrame,
    *,
    skill_col: str = "skill",
    failed_sites_col: str = "failed_stations",
    total_sites: int | None = None,
    group_cols: Sequence[str] = RESILIENCE_GROUP_COLUMNS,
) -> pd.DataFrame:
    """Compute relative skill as a function of failed-node fraction."""

    if skill_col not in events:
        raise ValueError(f"network resilience requires column: {skill_col}")
    events, exclusions = complete_resilience_units(
        events,
        failed_sites_col=failed_sites_col,
        total_sites=total_sites,
        value_cols=(skill_col,),
    )
    if events.empty:
        reason = (
            exclusions["reason"].iloc[0]
            if not exclusions.empty
            else "no complete SCI_NET resilience units"
        )
        raise ValueError(f"no complete SCI_NET resilience units: {reason}")
    data, total_sites, inference_reason = _with_failures(
        events, failed_sites_col, RESILIENCE_NETWORK_SIZE
    )
    data[skill_col] = pd.to_numeric(data[skill_col], errors="coerce")
    active_groups = [column for column in group_cols if column in data]
    aggregation_cols = [
        *active_groups,
        "failed_count",
        "failure_fraction",
        "failure_class",
    ]
    curve = (
        data.dropna(subset=[skill_col])
        .groupby(aggregation_cols, dropna=False, observed=True)[skill_col]
        .agg([("mean_skill", "mean"), ("n_events", "size")])
        .reset_index()
    )
    if curve.empty:
        return curve
    if active_groups:
        full_lookup = (
            curve.loc[curve["failed_count"].eq(0)]
            .set_index(active_groups)["mean_skill"]
            .to_dict()
        )
        keys = curve[active_groups].apply(tuple, axis=1)
        if len(active_groups) == 1:
            keys = curve[active_groups[0]]
        curve["full_network_skill"] = keys.map(full_lookup)
    else:
        full_rows = curve.loc[curve["failed_count"].eq(0), "mean_skill"]
        curve["full_network_skill"] = full_rows.iloc[0] if len(full_rows) else np.nan
    denominator = curve["full_network_skill"].where(curve["full_network_skill"] > 0)
    curve["relative_skill"] = curve["mean_skill"] / denominator
    curve["network_size"] = total_sites
    curve["reason"] = inference_reason
    missing_full = curve["full_network_skill"].isna()
    curve.loc[missing_full, "reason"] = "no zero-failure full-network reference"
    nonpositive_full = curve["full_network_skill"].le(0)
    curve.loc[nonpositive_full, "reason"] = "full-network skill is not positive"
    return curve


def resilience_auc(
    curve: pd.DataFrame,
    *,
    group_cols: Sequence[str] = RESILIENCE_GROUP_COLUMNS,
) -> pd.DataFrame:
    """Integrate relative skill over failed fraction, requiring coverage 0..1."""

    required = {"failure_fraction", "relative_skill"}
    missing = sorted(required - set(curve.columns))
    if missing:
        raise ValueError(f"resilience AUC requires columns: {missing}")
    if (
        "experiment" not in curve
        or not curve["experiment"]
        .astype(str)
        .str.upper()
        .eq(RESILIENCE_EXPERIMENT)
        .all()
    ):
        raise ValueError("resilience AUC accepts only experiment='SCI_NET'")
    active_groups = [column for column in group_cols if column in curve]
    grouped = (
        curve.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), curve)]
    )
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        points = (
            group[["failure_fraction", "relative_skill"]]
            .dropna()
            .groupby("failure_fraction", as_index=False)["relative_skill"]
            .mean()
            .sort_values("failure_fraction")
        )
        spans_full_range = (
            len(points) >= 2
            and np.isclose(points["failure_fraction"].iloc[0], 0.0)
            and np.isclose(points["failure_fraction"].iloc[-1], 1.0)
        )
        if spans_full_range:
            auc = float(
                _trapezoid(points["relative_skill"], points["failure_fraction"])
            )
            reason = None
        else:
            auc = np.nan
            reason = "resilience curve must span failed fractions 0 and 1"
        rows.append(
            {
                **metadata,
                "resilience_auc": auc,
                "n_failure_levels": len(points),
                "reason": reason,
            }
        )
    return _preserve_optional_text(pd.DataFrame(rows), "reason")


def node_importance(
    events: pd.DataFrame,
    *,
    value_col: str = "MAE",
    failed_sites_col: str = "failed_stations",
    group_cols: Sequence[str] = RESILIENCE_GROUP_COLUMNS,
    baseline_model: str = "climatology",
) -> pd.DataFrame:
    """Estimate the loss of *achievable* performance after one node fails.

    The estimand is evaluated within each matched target-gap unit before any
    averaging::

        min(MAE of all available methods after failure, climatology MAE)
        - min(MAE of all available methods with the full network,
              climatology MAE)

    This differs deliberately from damaging one fitted model and measuring how
    badly that implementation extrapolates with missing inputs.  Including the
    climatology row in each minimum is the declared hard error cap.  Negative
    impacts are retained: they indicate that the best observed method in a
    failed-network condition happened to outperform the best full-network
    method on the same matched units, not that a failed sensor creates physical
    information.
    """

    if value_col not in events:
        raise ValueError(f"node importance requires column: {value_col}")
    events, exclusions = complete_resilience_units(
        events,
        failed_sites_col=failed_sites_col,
        value_cols=(value_col,),
    )
    if events.empty:
        reason = (
            exclusions["reason"].iloc[0]
            if not exclusions.empty
            else "no complete SCI_NET resilience units"
        )
        raise ValueError(f"no complete SCI_NET resilience units: {reason}")
    data, _, _ = _with_failures(events, failed_sites_col, total_sites=None)
    retained = list(
        dict.fromkeys(
            [
                *group_cols,
                "target_gap_id",
                "mask_seed",
                "model",
                value_col,
                "failed_sites",
                "failed_count",
            ]
        )
    )
    data = data.loc[:, [column for column in retained if column in data]].copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    if "model" not in data:
        raise ValueError("node importance requires a model column")
    if baseline_model not in set(data["model"].dropna().astype(str)):
        raise ValueError(f"node importance requires hard-cap model {baseline_model!r}")
    data["_baseline_tie_order"] = (
        ~data["model"].astype(str).eq(baseline_model)
    ).astype(int)

    # A network-level importance has one row per design/target/gap/failed node,
    # not one row per model.  Model identity is reported for the selected best
    # full and failed alternatives instead.
    active_groups = [
        column for column in group_cols if column in data and column != "model"
    ]
    grouped = (
        data.groupby(active_groups, dropna=False, observed=True)
        if active_groups
        else [((), data)]
    )
    rows: list[dict[str, Any]] = []
    for group_key, group in grouped:
        if active_groups and not isinstance(group_key, tuple):
            group_key = (group_key,)
        metadata = dict(
            zip(active_groups, group_key if active_groups else (), strict=True)
        )
        unit_columns = [
            column for column in ("target_gap_id", "mask_seed") if column in group
        ]
        if not unit_columns:
            raise ValueError(
                "node importance requires target_gap_id or mask_seed for pairing"
            )
        full = group.loc[group["failed_count"].eq(0)].copy()
        singleton = group.loc[group["failed_count"].eq(1)].copy()
        if full.empty:
            raise ValueError("node importance has no zero-failure reference")
        full_best = (
            full.sort_values(
                [*unit_columns, value_col, "_baseline_tie_order", "model"],
                kind="mergesort",
            )
            .groupby(unit_columns, dropna=False, observed=True, as_index=False)
            .first()
            .loc[:, [*unit_columns, value_col, "model"]]
            .rename(
                columns={
                    value_col: "full_network_value",
                    "model": "full_network_best_model",
                }
            )
        )
        full_climatology = (
            full.loc[full["model"].astype(str).eq(baseline_model)]
            .groupby(unit_columns, dropna=False, observed=True, as_index=False)[
                value_col
            ]
            .mean()
            .rename(columns={value_col: "full_network_climatology_value"})
        )
        full_best = full_best.merge(
            full_climatology,
            on=unit_columns,
            how="left",
            validate="one_to_one",
        )
        if full_best["full_network_climatology_value"].isna().any():
            raise ValueError("node importance lacks a paired full-network climatology")

        for sites, values in singleton.groupby("failed_sites", observed=True):
            failed_best = (
                values.sort_values(
                    [*unit_columns, value_col, "_baseline_tie_order", "model"],
                    kind="mergesort",
                )
                .groupby(unit_columns, dropna=False, observed=True, as_index=False)
                .first()
                .loc[:, [*unit_columns, value_col, "model"]]
                .rename(
                    columns={
                        value_col: "failed_value",
                        "model": "failed_best_model",
                    }
                )
            )
            failed_climatology = (
                values.loc[values["model"].astype(str).eq(baseline_model)]
                .groupby(unit_columns, dropna=False, observed=True, as_index=False)[
                    value_col
                ]
                .mean()
                .rename(columns={value_col: "failed_climatology_value"})
            )
            paired = failed_best.merge(
                failed_climatology,
                on=unit_columns,
                how="left",
                validate="one_to_one",
            ).merge(
                full_best,
                on=unit_columns,
                how="inner",
                validate="one_to_one",
            )
            if paired.empty or paired["failed_climatology_value"].isna().any():
                raise ValueError(
                    "node importance lacks paired full/failed climatology units"
                )
            paired["unit_impact"] = (
                paired["failed_value"] - paired["full_network_value"]
            )
            full_model_counts = (
                paired["full_network_best_model"].astype(str).value_counts()
            )
            failed_model_counts = paired["failed_best_model"].astype(str).value_counts()
            rows.append(
                {
                    **metadata,
                    "model": "best_available",
                    "target_station_id": metadata.get(
                        "target_station_id", metadata.get("station_id")
                    ),
                    "failed_station_id": sites[0],
                    "full_network_value": float(paired["full_network_value"].mean()),
                    "failed_value": float(paired["failed_value"].mean()),
                    "full_network_climatology_value": float(
                        paired["full_network_climatology_value"].mean()
                    ),
                    "failed_climatology_value": float(
                        paired["failed_climatology_value"].mean()
                    ),
                    "full_network_best_model": str(full_model_counts.index[0]),
                    "failed_best_model": str(failed_model_counts.index[0]),
                    "full_network_best_model_counts": json.dumps(
                        full_model_counts.sort_index().to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "failed_best_model_counts": json.dumps(
                        failed_model_counts.sort_index().to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "impact": float(paired["unit_impact"].mean()),
                    "value_metric": value_col,
                    "impact_definition": (
                        "best_available_failed_minus_best_available_full_"
                        "with_climatology_hard_cap"
                    ),
                    "hard_cap_model": baseline_model,
                    "n_events": len(paired),
                    "reason": None,
                }
            )
    return pd.DataFrame(rows)


def _stratified_mean_interval(
    frame: pd.DataFrame,
    value_col: str,
    *,
    strata_col: str,
    n_boot: int,
    seed: int,
) -> tuple[float, float]:
    """Bootstrap a mean while retaining the declared temporal strata."""

    strata = [
        group[value_col].to_numpy(dtype=float)
        for _, group in frame.groupby(
            strata_col, dropna=False, observed=True, sort=True
        )
    ]
    if not strata or any(len(values) == 0 for values in strata):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    draws = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        sampled = [
            values[rng.integers(0, len(values), size=len(values))] for values in strata
        ]
        draws[index] = float(np.mean(np.concatenate(sampled)))
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def cross_fitted_node_importance(
    events: pd.DataFrame,
    *,
    value_col: str = "MAE",
    failed_sites_col: str = "failed_stations",
    group_cols: Sequence[str] = RESILIENCE_GROUP_COLUMNS,
    baseline_model: str = "climatology",
    n_boot: int = 2000,
    seed: int = 20260825,
) -> pd.DataFrame:
    """Estimate node importance without choosing a model on its scored event.

    For every target, gap length, and failure set, the policy selects the model
    with the lowest mean error in all *other* evaluation years.  That model is
    then scored on the held-out year's matched events.  Full- and failed-network
    policies are paired on the same target-gap unit before aggregation.  The
    climatology is an ordinary candidate in the cross-fit rather than an
    event-wise oracle cap.

    This is a post-hoc non-oracle sensitivity because model selection still
    uses folds of the development-evaluation population.  It is not an unseen
    confirmatory estimate, but unlike :func:`node_importance` it never chooses
    the minimum error on the event being scored.
    """

    required = {
        value_col,
        failed_sites_col,
        "model",
        "gap_length",
        "target_gap_id",
        "mask_seed",
        "anchor_year",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise ValueError(
            "cross-fitted node importance requires columns: " + ", ".join(missing)
        )
    complete, exclusions = complete_resilience_units(
        events,
        failed_sites_col=failed_sites_col,
        value_cols=(value_col,),
    )
    if complete.empty:
        reason = (
            exclusions["reason"].iloc[0]
            if not exclusions.empty
            else "no complete SCI_NET resilience units"
        )
        raise ValueError(f"no complete SCI_NET resilience units: {reason}")
    data, _, _ = _with_failures(complete, failed_sites_col, total_sites=None)
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data["anchor_year"] = pd.to_numeric(data["anchor_year"], errors="coerce")
    if data[[value_col, "anchor_year"]].isna().any().any():
        raise ValueError(
            "cross-fitted node importance requires finite values and years"
        )
    if baseline_model not in set(data["model"].dropna().astype(str)):
        raise ValueError(
            f"cross-fitted node importance requires candidate {baseline_model!r}"
        )

    output_groups = [
        column
        for column in group_cols
        if column in data and column not in {"model", "gap_length"}
    ]
    selection_groups = [*output_groups, "gap_length", "failed_sites"]
    unit_groups = [
        *selection_groups,
        "target_gap_id",
        "mask_seed",
        "anchor_year",
        "model",
    ]
    collapsed = (
        data.groupby(unit_groups, dropna=False, observed=True, as_index=False)[
            value_col
        ]
        .mean()
        .copy()
    )
    collapsed["_baseline_tie_order"] = (
        ~collapsed["model"].astype(str).eq(baseline_model)
    ).astype(int)

    scored_rows: list[dict[str, Any]] = []
    for selection_key, condition in collapsed.groupby(
        selection_groups, dropna=False, observed=True, sort=True
    ):
        if not isinstance(selection_key, tuple):
            selection_key = (selection_key,)
        selection_metadata = dict(zip(selection_groups, selection_key, strict=True))
        years = sorted(condition["anchor_year"].unique())
        if len(years) < 2:
            raise ValueError(
                "cross-fitted node importance needs at least two anchor years"
            )
        for held_out_year in years:
            training = condition.loc[condition["anchor_year"].ne(held_out_year)]
            ranking = (
                training.groupby(
                    ["model", "_baseline_tie_order"],
                    as_index=False,
                    observed=True,
                )[value_col]
                .mean()
                .sort_values(
                    [value_col, "_baseline_tie_order", "model"],
                    kind="mergesort",
                )
            )
            if ranking.empty:
                raise ValueError("cross-fit training fold contains no candidate model")
            selected_model = str(ranking.iloc[0]["model"])
            held_out = condition.loc[
                condition["anchor_year"].eq(held_out_year)
                & condition["model"].astype(str).eq(selected_model)
            ]
            if held_out.empty:
                raise ValueError("selected model is absent from a held-out fold")
            for row in held_out.itertuples(index=False):
                scored_rows.append(
                    {
                        **selection_metadata,
                        "target_gap_id": row.target_gap_id,
                        "mask_seed": row.mask_seed,
                        "anchor_year": held_out_year,
                        "selected_model": selected_model,
                        "selected_value": float(getattr(row, value_col)),
                    }
                )
    scored = pd.DataFrame(scored_rows)

    result_rows: list[dict[str, Any]] = []
    grouped = (
        scored.groupby(output_groups, dropna=False, observed=True, sort=True)
        if output_groups
        else [((), scored)]
    )
    for group_offset, (output_key, group) in enumerate(grouped):
        if output_groups and not isinstance(output_key, tuple):
            output_key = (output_key,)
        metadata = dict(
            zip(output_groups, output_key if output_groups else (), strict=True)
        )
        pair_keys = [
            "gap_length",
            "target_gap_id",
            "mask_seed",
            "anchor_year",
        ]
        full = group.loc[group["failed_sites"].map(len).eq(0)].rename(
            columns={
                "selected_model": "full_network_selected_model",
                "selected_value": "full_network_value",
            }
        )
        full = full[
            [
                *pair_keys,
                "full_network_selected_model",
                "full_network_value",
            ]
        ]
        if full.empty or full.duplicated(pair_keys).any():
            raise ValueError("cross-fit lacks a unique full-network scored policy")
        singleton = group.loc[group["failed_sites"].map(len).eq(1)].copy()
        for site_offset, (sites, failed) in enumerate(
            singleton.groupby("failed_sites", observed=True, sort=True)
        ):
            paired = failed.merge(
                full,
                on=pair_keys,
                how="inner",
                validate="one_to_one",
            )
            if len(paired) != len(full):
                raise ValueError("cross-fit full/failed policy units are incomplete")
            paired["unit_impact"] = (
                paired["selected_value"] - paired["full_network_value"]
            )
            n_years = int(paired["anchor_year"].nunique())
            lower, upper = year_block_mean_interval(
                paired,
                "unit_impact",
                year_col="anchor_year",
                n_boot=n_boot,
                seed=seed + group_offset * 101 + site_offset,
            )
            full_counts = (
                paired["full_network_selected_model"].astype(str).value_counts()
            )
            failed_counts = paired["selected_model"].astype(str).value_counts()
            result_rows.append(
                {
                    **metadata,
                    "model": "cross_fitted_policy",
                    "target_station_id": metadata.get(
                        "target_station_id", metadata.get("station_id")
                    ),
                    "failed_station_id": sites[0],
                    "full_network_value": float(paired["full_network_value"].mean()),
                    "failed_value": float(paired["selected_value"].mean()),
                    "impact": float(paired["unit_impact"].mean()),
                    "impact_ci_lower": lower,
                    "impact_ci_upper": upper,
                    "value_metric": value_col,
                    "impact_definition": (
                        "leave_one_anchor_year_out_cross_fitted_failed_minus_full"
                    ),
                    "selection_population": "development_evaluation_cross_fit",
                    "evidence_role": "post_hoc_non_oracle_sensitivity",
                    "formal_evidence": False,
                    "eventwise_oracle_selection": False,
                    "full_network_selected_model_counts": json.dumps(
                        full_counts.sort_index().to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "failed_selected_model_counts": json.dumps(
                        failed_counts.sort_index().to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "n_gap_lengths": int(paired["gap_length"].nunique()),
                    "n_anchor_years": n_years,
                    "n_independent_clusters": n_years,
                    "minimum_independent_clusters": MIN_INDEPENDENT_CLUSTERS,
                    "inference_status": (
                        "tested"
                        if n_years >= MIN_INDEPENDENT_CLUSTERS
                        else WITHHELD_STATUS
                    ),
                    "inference_claim_allowed": n_years >= MIN_INDEPENDENT_CLUSTERS,
                    "n_events": len(paired),
                    "reason": (
                        None
                        if n_years >= MIN_INDEPENDENT_CLUSTERS
                        else (
                            "year/overlap clusters below the predeclared floor; "
                            "CIs withheld"
                        )
                    ),
                }
            )
    return pd.DataFrame(result_rows)


def analyze_resilience(
    events: pd.DataFrame,
    **kwargs: Any,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    curve = resilience_curve(events, **kwargs)
    auc = resilience_auc(curve)
    importance = node_importance(
        events,
        value_col=kwargs.get("value_col", "MAE"),
        failed_sites_col=kwargs.get("failed_sites_col", "failed_stations"),
    )
    return curve, auc, importance


__all__ = [
    "RESILIENCE_EXPERIMENT",
    "RESILIENCE_GROUP_COLUMNS",
    "RESILIENCE_NETWORK_SIZE",
    "RESILIENCE_UNIT_COLUMNS",
    "analyze_resilience",
    "complete_resilience_units",
    "cross_fitted_node_importance",
    "node_importance",
    "parse_failed_sites",
    "resilience_auc",
    "resilience_curve",
]
