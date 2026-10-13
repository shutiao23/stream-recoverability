"""Step 5 — what actually makes a completed station-year unusable.

H1: at fixed outage length, the error of the annual thermal metric is governed
by the overlap between the outage and the station's climatological peak window,
by the margin with which the observed days already constrain the annual
maximum, and by the *quality* rather than the presence of synchronous donor
information. Outage length is a weak proxy for all three, which is why the
published guideline's length axis separates so little.

Two controlled experiments accompany the observational decomposition:
donor-quality subsetting at fixed donor count, and an anomaly-shuffle surrogate
that keeps each donor's seasonal cycle but destroys its synchrony with the
target.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from stream_recoverability.experiments.v17_fitness.cases import deseasonalized_correlations
from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    hottest_window_mean,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window,
    design_for_year,
)
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel
from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C

MECHANISM_FEATURES = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "peak_overlap",
    "warm_observed_fraction",
    "observed_peak_margin",
    "n_visible_donors",
    "donor_corr_mean",
    "donor_corr_max",
    "donor_coverage_mean",
    "train_resid_sd",
    "seasonal_amplitude",
    "train_metric_sd",
)


def length_by_overlap_table(cases: pd.DataFrame, error_column: str = "abserr_policy") -> pd.DataFrame:
    """The central H1 table: length is weak once peak overlap is conditioned on."""

    frame = cases.copy()
    frame["length_bucket"] = pd.cut(
        pd.to_numeric(frame["longest_run"], errors="coerce"),
        [0, 30, 60, 120, 200, 400],
        labels=["1-30", "31-60", "61-120", "121-200", "201+"],
    )
    frame["overlap_bucket"] = pd.cut(
        pd.to_numeric(frame["peak_overlap"], errors="coerce"),
        [-0.001, 0.001, 0.5, 0.999, 1.001],
        labels=["0", "0-0.5", "0.5-1", "1"],
    )
    grouped = (
        frame.groupby(["length_bucket", "overlap_bucket"], observed=True)
        .agg(
            n=(error_column, "size"),
            mean_abs_error=(error_column, "mean"),
            rate_above_tolerance=(error_column, lambda s: float((pd.to_numeric(s, errors="coerce") > PRIMARY_TOLERANCE_C).mean())),
        )
        .reset_index()
    )
    return grouped


def marginal_separation(cases: pd.DataFrame, error_column: str = "abserr_policy") -> pd.DataFrame:
    """Single-variable discrimination of a consequential error, out of the box."""

    label = (pd.to_numeric(cases[error_column], errors="coerce") > PRIMARY_TOLERANCE_C).astype(int)
    rows = []
    for name in MECHANISM_FEATURES:
        values = pd.to_numeric(cases[name], errors="coerce")
        good = values.notna() & label.notna()
        if good.sum() < 100 or label[good].nunique() < 2:
            continue
        auc = roc_auc_score(label[good], values[good])
        rows.append(
            {
                "feature": name,
                "auc": float(max(auc, 1 - auc)),
                "direction": "higher is worse" if auc >= 0.5 else "lower is worse",
                "n": int(good.sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("auc", ascending=False).reset_index(drop=True)


def grouped_importance(
    cases: pd.DataFrame,
    *,
    error_column: str = "abserr_policy",
    seed: int = 0,
    n_splits: int = 5,
) -> tuple[pd.DataFrame, dict]:
    """Out-of-fold R^2 and permutation importance, clustered by network."""

    frame = cases.copy()
    X = frame[list(MECHANISM_FEATURES)].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(frame[error_column], errors="coerce")
    good = y.notna()
    X, y = X.loc[good], y.loc[good]
    groups = frame.loc[good, "network_id"].to_numpy()
    oof = np.full(len(y), np.nan)
    importances = np.zeros(len(MECHANISM_FEATURES))
    folds = 0
    for train_idx, test_idx in GroupKFold(n_splits=n_splits).split(X, y, groups):
        model = HistGradientBoostingRegressor(random_state=seed, max_depth=4, max_iter=300, learning_rate=0.06)
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        oof[test_idx] = model.predict(X.iloc[test_idx])
        result = permutation_importance(
            model, X.iloc[test_idx], y.iloc[test_idx], n_repeats=3, random_state=seed, scoring="r2"
        )
        importances += result.importances_mean
        folds += 1
    importances /= max(1, folds)
    table = pd.DataFrame({"feature": list(MECHANISM_FEATURES), "permutation_r2_drop": importances})
    table = table.sort_values("permutation_r2_drop", ascending=False).reset_index(drop=True)
    summary = {
        "out_of_fold_r2": float(r2_score(y, oof)),
        "n": int(len(y)),
        "n_networks": int(pd.Series(groups).nunique()),
        "error_column": error_column,
    }
    return table, summary


def nested_model_gain(cases: pd.DataFrame, *, error_column: str = "abserr_policy", seed: int = 0) -> pd.DataFrame:
    """Does each information layer add discrimination beyond the length axis?"""

    label = (pd.to_numeric(cases[error_column], errors="coerce") > PRIMARY_TOLERANCE_C).astype(int)
    groups = cases["network_id"].to_numpy()
    layers = {
        "length only": ["longest_run", "total_missing"],
        "+ timing": ["longest_run", "total_missing", "peak_overlap", "warm_observed_fraction"],
        "+ observed-peak margin": [
            "longest_run",
            "total_missing",
            "peak_overlap",
            "warm_observed_fraction",
            "observed_peak_margin",
        ],
        "+ donor quality": list(MECHANISM_FEATURES),
    }
    rows = []
    for name, columns in layers.items():
        X = cases[columns].apply(pd.to_numeric, errors="coerce")
        oof = np.full(len(label), np.nan)
        for train_idx, test_idx in GroupKFold(n_splits=5).split(X, label, groups):
            model = HistGradientBoostingRegressor(random_state=seed, max_depth=4, max_iter=300, learning_rate=0.06)
            model.fit(X.iloc[train_idx], label.iloc[train_idx])
            oof[test_idx] = model.predict(X.iloc[test_idx])
        rows.append({"feature_set": name, "n_features": len(columns), "grouped_cv_auc": float(roc_auc_score(label, oof))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Controlled donor experiments
# --------------------------------------------------------------------------


def _phase_shuffled_donors(donors: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Keep each donor's seasonal cycle, destroy its synchrony with the target."""

    out = {}
    for name in donors.columns:
        series = pd.to_numeric(donors[name], errors="coerce")
        doy = pd.Series(series.index.dayofyear, index=series.index)
        climatology = series.groupby(doy).transform("mean")
        anomaly = series - climatology
        shift = int(rng.integers(120, max(121, len(series) - 120)))
        shuffled = pd.Series(np.roll(anomaly.to_numpy(dtype=float), shift), index=series.index)
        out[name] = climatology + shuffled
    return pd.DataFrame(out, index=donors.index)


def donor_control_experiment(job: dict) -> pd.DataFrame:
    """Fix the donor count and vary donor quality; and shuffle donor anomalies.

    Both controls hold the outage, the station, the year and the training data
    fixed, so any change in the completed-year error is attributable to the
    manipulated donor property alone.
    """

    network_id, station_id = str(job["network_id"]), str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame()
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    if donors.shape[1] < 4:
        return pd.DataFrame()
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)
    rows: list[dict] = []

    for year in (int(value) for value in job["complete_years"]):
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        truth_metric = hottest_window_mean(truth)
        train_mask = pd.Series(~year_mask, index=daily.index)
        correlations = deseasonalized_correlations(target, donors, train_mask).dropna()
        if len(correlations) < 4:
            continue
        ordered = correlations.sort_values(ascending=False)
        k = len(ordered) // 2
        strong = tuple(ordered.index[:k])
        weak = tuple(ordered.index[-k:])

        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), "ctrl"))
        shuffled_donors = _phase_shuffled_donors(donors, rng)

        base_models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        shuffled_models = StationModels(target=target, donors=shuffled_donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(target, exclude_year=int(year))
        realizations = design_for_year(year_index, peak_doys, pool, rng=rng, n_empirical=1)

        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            visible = set(usable_donors(donors, year_index, mask))
            arms = {
                "all_donors": (base_models, tuple(sorted(visible))),
                "strong_half": (base_models, tuple(sorted(visible & set(strong)))),
                "weak_half": (base_models, tuple(sorted(visible & set(weak)))),
                "anomaly_shuffled": (shuffled_models, tuple(sorted(visible))),
            }
            row = {
                "network_id": network_id,
                "station_id": station_id,
                "year": int(year),
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "overlap_class": realization.overlap_class,
                "longest_run": int(realization.longest_run),
                "n_strong": len(visible & set(strong)),
                "n_weak": len(visible & set(weak)),
                "corr_strong_mean": float(correlations.reindex(list(visible & set(strong))).mean()) if visible & set(strong) else float("nan"),
                "corr_weak_mean": float(correlations.reindex(list(visible & set(weak))).mean()) if visible & set(weak) else float("nan"),
                "truth_metric": float(truth_metric),
            }
            for label, (models, subset) in arms.items():
                if not subset:
                    row[f"abserr_{label}"] = float("nan")
                    continue
                fitted = models.donor_ridge(subset)
                if fitted is None:
                    row[f"abserr_{label}"] = float("nan")
                    continue
                prediction = models.donor_predict(fitted, year_index)
                completed = observed.copy()
                completed[mask] = prediction[mask]
                if not np.isfinite(completed).all():
                    row[f"abserr_{label}"] = float("nan")
                    continue
                row[f"abserr_{label}"] = float(abs(hottest_window_mean(completed) - truth_metric))
            rows.append(row)
    return pd.DataFrame(rows)
