"""Information-condition factorial: donors × right boundary, plus air-only models.

The current freeze rejects every recoverer when the right boundary is missing.
That is a task restriction until this factorial shows which methods actually
need the right flank. Donor-only is the negative control: masking only the
target's right observation must not change its prediction.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.features import base_feature_frame
from stream_recoverability.experiments.wrr_revision.recoverers import FittedRecoverer
from stream_recoverability.experiments.wrr_revision.score import daily_mae, score_gap

INFORMATION_CELLS = (
    ("donors_and_right", True, True),
    ("donors_no_right", True, False),
    ("no_donors_right", False, True),
    ("no_donors_no_right", False, False),
)

FACTORIAL_RECOVERERS = (
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_only_ridge",
    "air_ridge",
    "air_lag_ridge",
    "air2stream3",
)


def mask_right_boundary(target: pd.Series, start: int, gap_length: int) -> pd.Series:
    """Hide the first observation after the gap. Do not impute it."""

    out = target.copy()
    right = int(start) + int(gap_length)
    if 0 <= right < len(out):
        out.iloc[right] = np.nan
    return out


def mask_donors_in_gap(
    panel: pd.DataFrame,
    donors: Sequence[str],
    start: int,
    gap_length: int,
) -> pd.DataFrame:
    out = panel.copy()
    for donor in donors:
        if donor in out.columns:
            out.iloc[int(start) : int(start) + int(gap_length), out.columns.get_loc(donor)] = np.nan
    return out


def mask_partial_donors(
    panel: pd.DataFrame,
    donors: Sequence[str],
    start: int,
    gap_length: int,
    *,
    keep: Sequence[str],
) -> pd.DataFrame:
    hide = [name for name in donors if name not in set(keep)]
    return mask_donors_in_gap(panel, hide, start, gap_length)


WEAK_CORR_THRESHOLD = 0.3

QUALITY_CELLS = (
    "partial_half_donors",
    "weak_donors_only",
    "strong_donors_only",
)


def keep_half_donors(donors: Sequence[str]) -> tuple[str, ...]:
    """Deterministic half of the donor roster. Empty if fewer than two donors."""

    ordered = tuple(sorted(str(name) for name in donors))
    if len(ordered) < 2:
        return ()
    n_keep = max(1, len(ordered) // 2)
    return ordered[:n_keep]


def deseasonalized_donor_correlation(
    panel: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    train_mask: pd.Series,
) -> pd.Series:
    """Training-period Pearson correlation of DOY residuals. Visible at decision time."""

    target = pd.to_numeric(panel[target_station], errors="coerce")
    doy = pd.Series(target.index.dayofyear, index=target.index)
    train = train_mask.reindex(target.index).fillna(False).astype(bool)
    target_train = target.loc[train]
    if target_train.notna().sum() < 40:
        return pd.Series(dtype=float)
    clim = target_train.groupby(doy.loc[train]).transform("mean")
    residual = target_train - clim
    rows = {}
    for donor in donors:
        series = pd.to_numeric(panel[donor], errors="coerce").loc[train]
        donor_clim = series.groupby(doy.loc[train]).transform("mean")
        donor_residual = series - donor_clim
        aligned = pd.concat([residual, donor_residual], axis=1, keys=["t", "d"]).dropna()
        if len(aligned) < 40:
            rows[str(donor)] = float("nan")
        else:
            rows[str(donor)] = float(aligned["t"].corr(aligned["d"]))
    return pd.Series(rows)


def split_donors_by_correlation(
    correlations: pd.Series,
    *,
    threshold: float = WEAK_CORR_THRESHOLD,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Strong donors have |r| >= threshold. NaN correlations are dropped."""

    finite = correlations.dropna()
    strong = tuple(sorted(str(name) for name, value in finite.items() if abs(float(value)) >= float(threshold)))
    weak = tuple(sorted(str(name) for name, value in finite.items() if abs(float(value)) < float(threshold)))
    return strong, weak


def information_conditioned_recoverer(
    *,
    donors_observed: bool,
    right_present: bool,
    air_present: bool,
    gap_length: int,
) -> str:
    """Development simple policy from the Step-4 factorial. Not a confirmation result."""

    if donors_observed:
        return "donor_only_ridge"
    if int(gap_length) <= 30 and right_present:
        return "linear_interp"
    if air_present:
        return "air_ridge"
    return "smooth_climatology"


def recoverer_supported(
    recoverer: FittedRecoverer,
    *,
    donors_present: bool,
    right_present: bool,
    air_present: bool,
) -> bool:
    """Support is about the method's actual inputs, not a blanket right-boundary rule."""

    if recoverer.uses_donors and not donors_present:
        return False
    if recoverer.uses_boundary and not right_present:
        return False
    if recoverer.uses_air and not air_present:
        return False
    return True


def condition_features(
    panel: pd.DataFrame,
    *,
    donors: Sequence[str],
    start: int,
    gap_length: int,
    donors_present: bool,
    right_present: bool,
    target_station: str,
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    masked_panel = panel if donors_present else mask_donors_in_gap(panel, donors, start, gap_length)
    target = pd.to_numeric(masked_panel[target_station], errors="coerce")
    if not right_present:
        target = mask_right_boundary(target, start, gap_length)
        masked_panel = masked_panel.copy()
        masked_panel[target_station] = target
    active_donors = donors if donors_present else ()
    features = base_feature_frame(masked_panel, donors=active_donors, air=air, discharge=discharge)
    return masked_panel, target, features


def predict_under_condition(
    recoverer: FittedRecoverer,
    *,
    features: pd.DataFrame,
    target: pd.Series,
    start: int,
    gap_length: int,
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
) -> np.ndarray:
    return np.asarray(
        recoverer.predict_gap(
            features=features,
            target=target,
            start=int(start),
            gap_length=int(gap_length),
            air=air,
            discharge=discharge,
        ),
        dtype=float,
    )


def donor_only_right_boundary_delta(
    recoverer: FittedRecoverer,
    *,
    panel: pd.DataFrame,
    target_station: str,
    donors: Sequence[str],
    start: int,
    gap_length: int,
    air: pd.Series | None = None,
) -> float:
    """Max absolute change in donor-only predictions when only the right flank is hidden."""

    if recoverer.name != "donor_only_ridge":
        raise ValueError("negative control is defined for donor_only_ridge")
    _, target_full, features_full = condition_features(
        panel,
        donors=donors,
        start=start,
        gap_length=gap_length,
        donors_present=True,
        right_present=True,
        target_station=target_station,
        air=air,
    )
    _, target_left, features_left = condition_features(
        panel,
        donors=donors,
        start=start,
        gap_length=gap_length,
        donors_present=True,
        right_present=False,
        target_station=target_station,
        air=air,
    )
    left = predict_under_condition(
        recoverer, features=features_full, target=target_full, start=start, gap_length=gap_length, air=air
    )
    right = predict_under_condition(
        recoverer, features=features_left, target=target_left, start=start, gap_length=gap_length, air=air
    )
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        return float("nan")
    return float(np.max(np.abs(left - right)))


def score_information_cells(
    recoverers: Mapping[str, FittedRecoverer],
    *,
    panel: pd.DataFrame,
    target_station: str,
    donors: Sequence[str],
    start: int,
    gap_length: int,
    default_fill: np.ndarray,
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
    names: Sequence[str] = FACTORIAL_RECOVERERS,
) -> list[dict[str, object]]:
    truth = pd.to_numeric(panel[target_station], errors="coerce")
    observed = truth.iloc[int(start) : int(start) + int(gap_length)].to_numpy(dtype=float)
    if not np.isfinite(observed).all():
        return []
    rows: list[dict[str, object]] = []
    air_present = air is not None and np.isfinite(
        pd.to_numeric(air, errors="coerce").reindex(panel.index).iloc[int(start) : int(start) + int(gap_length)]
    ).all()
    default = np.asarray(default_fill[int(start) : int(start) + int(gap_length)], dtype=float)
    for cell, donors_present, right_present in INFORMATION_CELLS:
        _, masked_target, features = condition_features(
            panel,
            donors=donors,
            start=start,
            gap_length=gap_length,
            donors_present=donors_present,
            right_present=right_present,
            target_station=target_station,
            air=air,
            discharge=discharge,
        )
        for name in names:
            recoverer = recoverers.get(name)
            if recoverer is None:
                continue
            supported = recoverer_supported(
                recoverer,
                donors_present=donors_present,
                right_present=right_present,
                air_present=air_present,
            )
            row: dict[str, object] = {
                "cell": cell,
                "donors_present": donors_present,
                "right_present": right_present,
                "recoverer": name,
                "supported": supported,
                "uses_donors": recoverer.uses_donors,
                "uses_boundary": recoverer.uses_boundary,
                "uses_air": recoverer.uses_air,
            }
            if not supported:
                row["mae_deg_c"] = float(daily_mae(observed, default))
                row["mae_benefit"] = 0.0
                row["action"] = "default"
                rows.append(row)
                continue
            scored = score_gap(
                recoverer,
                features=features,
                target=masked_target,
                start=start,
                gap_length=gap_length,
                default_fill=default_fill,
                air=air,
                discharge=discharge,
            )
            if scored is None:
                row["mae_deg_c"] = float(daily_mae(observed, default))
                row["mae_benefit"] = 0.0
                row["action"] = "failed_to_default"
            else:
                row["mae_deg_c"] = scored["mae_deg_c"]
                row["mae_benefit"] = scored["mae_benefit"]
                row["hottest_30_benefit"] = scored.get("hottest_30_benefit", float("nan"))
                row["action"] = "predict"
            rows.append(row)
    return rows


def best_simple_by_cell(
    scores: pd.DataFrame,
    *,
    extra_keys: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Best supported recoverer in each information cell by mean MAE benefit."""

    if scores.empty:
        return scores
    usable = scores.loc[scores["supported"].eq(True) & scores["action"].eq("predict")]
    if usable.empty:
        return usable
    keys = ["cell", *extra_keys, "recoverer"]
    summary = (
        usable.groupby(keys, as_index=False)
        .agg(
            n=("mae_benefit", "size"),
            mae_benefit_mean=("mae_benefit", "mean"),
            mae_mean=("mae_deg_c", "mean"),
        )
        .sort_values([*keys[:-1], "mae_benefit_mean"], ascending=[True] * (len(keys) - 1) + [False])
    )
    best = summary.groupby(keys[:-1], as_index=False).head(1)
    return best


def quality_kept_sets(
    panel: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    train_mask: pd.Series,
) -> dict[str, tuple[str, ...]]:
    """Decision-time donor subsets for partial-missing and correlation-quality cells."""

    half = keep_half_donors(donors)
    correlations = deseasonalized_donor_correlation(
        panel,
        target_station=target_station,
        donors=donors,
        train_mask=train_mask,
    )
    strong, weak = split_donors_by_correlation(correlations)
    return {
        "partial_half_donors": half,
        "weak_donors_only": weak,
        "strong_donors_only": strong,
        "all_donors": tuple(sorted(str(name) for name in donors)),
    }


def score_quality_cells(
    recoverers: Mapping[str, FittedRecoverer],
    *,
    panel: pd.DataFrame,
    target_station: str,
    donors: Sequence[str],
    start: int,
    gap_length: int,
    default_fill: np.ndarray,
    kept_by_cell: Mapping[str, Sequence[str]],
    air: pd.Series | None = None,
    subset_by_cell: Mapping[str, FittedRecoverer] | None = None,
    names: Sequence[str] = (
        "doy_climatology",
        "smooth_climatology",
        "linear_interp",
        "donor_only_ridge",
        "donor_subset_ridge",
        "air_ridge",
    ),
) -> list[dict[str, object]]:
    """Partial-donor and correlation-quality cells with a correctly trained subset model.

    ``donor_only_ridge`` is the original all-donor model, evaluated with missing
    donor columns imputed. ``donor_subset_ridge`` is trained only on the donors
    that remain visible. ``kept_by_cell`` maps cell name to the visible donors.
    """

    truth = pd.to_numeric(panel[target_station], errors="coerce")
    observed = truth.iloc[int(start) : int(start) + int(gap_length)].to_numpy(dtype=float)
    if not np.isfinite(observed).all():
        return []
    air_present = air is not None and np.isfinite(
        pd.to_numeric(air, errors="coerce").reindex(panel.index).iloc[int(start) : int(start) + int(gap_length)]
    ).all()
    default = np.asarray(default_fill[int(start) : int(start) + int(gap_length)], dtype=float)
    rows: list[dict[str, object]] = []
    for cell, kept in kept_by_cell.items():
        kept_donors = tuple(str(name) for name in kept)
        if not kept_donors:
            continue
        hide = [name for name in donors if str(name) not in set(kept_donors)]
        masked_panel = mask_donors_in_gap(panel, hide, start, gap_length)
        features_full = base_feature_frame(masked_panel, donors=donors, air=air)
        features_subset = base_feature_frame(masked_panel, donors=kept_donors, air=air)
        masked_target = pd.to_numeric(masked_panel[target_station], errors="coerce")
        for name in names:
            if name == "donor_subset_ridge":
                recoverer = (subset_by_cell or {}).get(cell) or recoverers.get(name)
            else:
                recoverer = recoverers.get(name)
            if recoverer is None:
                continue
            if name == "donor_subset_ridge":
                features = features_subset
                donors_present = True
            elif name == "donor_only_ridge":
                features = features_full
                donors_present = True
            else:
                features = features_subset
                donors_present = bool(kept_donors) if recoverer.uses_donors else False
            supported = recoverer_supported(
                recoverer,
                donors_present=donors_present if recoverer.uses_donors else True,
                right_present=True,
                air_present=air_present,
            )
            row: dict[str, object] = {
                "cell": cell,
                "donors_present": True,
                "right_present": True,
                "n_donors_kept": len(kept_donors),
                "n_donors_hidden": len(hide),
                "kept_donors": "|".join(kept_donors),
                "recoverer": name,
                "supported": supported,
                "uses_donors": recoverer.uses_donors,
                "uses_boundary": recoverer.uses_boundary,
                "uses_air": recoverer.uses_air,
            }
            if not supported:
                row["mae_deg_c"] = float(daily_mae(observed, default))
                row["mae_benefit"] = 0.0
                row["action"] = "default"
                rows.append(row)
                continue
            scored = score_gap(
                recoverer,
                features=features,
                target=masked_target,
                start=start,
                gap_length=gap_length,
                default_fill=default_fill,
                air=air,
            )
            if scored is None:
                row["mae_deg_c"] = float(daily_mae(observed, default))
                row["mae_benefit"] = 0.0
                row["action"] = "failed_to_default"
            else:
                row["mae_deg_c"] = scored["mae_deg_c"]
                row["mae_benefit"] = scored["mae_benefit"]
                row["hottest_30_benefit"] = scored.get("hottest_30_benefit", float("nan"))
                row["action"] = "predict"
            rows.append(row)
    return rows
