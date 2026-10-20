"""Matched-capacity risk models and training/calibration/test group separation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler

from stream_recoverability.experiments.v17_fitness.paths import donor_regime
from stream_recoverability.experiments.v17_fitness.screen import Certificate, SCREEN_FEATURES, SCREENED_ESTIMATORS

GENERIC = (
    "longest_run", "total_missing", "missing_fraction", "n_runs", "warm_observed_fraction",
    "month_sin", "month_cos", "n_visible_donors", "donor_corr_mean", "donor_corr_max",
    "donor_corr_min", "donor_coverage_mean", "train_resid_sd", "seasonal_amplitude",
    "train_metric_sd", "n_complete_years", "record_years", "left_flank", "right_flank",
    "air_available", "estimator_disagreement",
)
DIRECT_UNCERTAINTY = ("h30_draw_sd_C", "h30_interval_width_C", "direct_h30_uncertainty")
WINDOW_INFORMATION = (
    "probabilistic_hidden_support", "hidden_support_sd", "hidden_support_upper90",
    "peak_start_sd_days", "peak_start_entropy", "peak_competition_margin_C",
    "support_uncertainty_interaction",
)
SMALL = ("longest_run", "warm_observed_fraction", "n_visible_donors", "donor_corr_mean", "train_resid_sd", "estimator_disagreement")
DONORS = ("n_visible_donors", "donor_corr_mean", "donor_corr_max", "donor_corr_min", "donor_coverage_mean", "air_available")


def specifications() -> dict[str, tuple[tuple[str, ...], str]]:
    full = GENERIC + DIRECT_UNCERTAINTY + WINDOW_INFORMATION
    return {
        "certificate": (tuple(SCREEN_FEATURES), "certificate"),
        "policy_certificate": (tuple(SCREEN_FEATURES), "policy_certificate"),
        "generic_target_disagreement": (GENERIC, "gbr"),
        "generic_daily_disagreement": (tuple(name for name in GENERIC if name != "estimator_disagreement") + ("daily_estimator_disagreement",), "gbr"),
        "generic_both_diagnostics": (GENERIC + ("daily_estimator_disagreement", "reconstructor_oof_daily_sd"), "gbr"),
        "complete_diagnostic_model": (GENERIC + ("daily_estimator_disagreement", "reconstructor_oof_daily_sd", "reconstructor_oof_daily_bias", "reconstructor_oof_daily_abs90", "reconstructor_oof_lag1", "historical_mask_h30_abs90", "historical_mask_h30_bias", "n_historical_mask_errors", "observed_peak", "observed_peak_margin", "clim_peak", "has_complete_window", "peak_overlap"), "gbr"),
        "generic_plus_climatological_support": (GENERIC + ("peak_overlap",), "gbr"),
        "generic_direct_h30_uncertainty": (GENERIC + DIRECT_UNCERTAINTY, "gbr"),
        "uncertain_support": (full, "gbr"),
        "uncertain_support_no_competition": (tuple(name for name in full if name != "peak_competition_margin_C"), "gbr"),
        "uncertain_support_no_window_uncertainty": (tuple(name for name in full if name not in {"hidden_support_sd", "hidden_support_upper90", "peak_start_sd_days", "peak_start_entropy"}), "gbr"),
        "uncertain_support_no_donor_features": (tuple(name for name in full if name not in DONORS), "gbr"),
        "small_logit": (SMALL, "logit"),
        "small_logit_plus_support": (SMALL + ("peak_overlap",), "logit"),
        "season_spline": (SMALL + ("month_sin", "month_cos"), "spline"),
        "season_spline_plus_support": (SMALL + ("month_sin", "month_cos", "peak_overlap"), "spline"),
    }


def group_roles(groups: np.ndarray, seed: int, outer_fold: int) -> dict[str, str]:
    units = np.array(sorted(set(np.asarray(groups).astype(str))))
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(units)
    folds = {group: index % 5 for index, group in enumerate(shuffled)}
    non_test = np.array(sorted(group for group in units if folds[group] != outer_fold))
    calibration = set(rng.permutation(non_test)[::4])
    return {group: "test" if folds[group] == outer_fold else ("calibration" if group in calibration else "train") for group in units}


def feature_matrix(frame: pd.DataFrame, features: tuple[str, ...]) -> pd.DataFrame:
    forbidden = {"truth_hottest30", "true_peak_hidden_fraction", "abserr_policy", "policy_bad", "truth_local_hot", "n_truth_event_days", "n_hidden_event_days"}
    if forbidden.intersection(features):
        raise ValueError("Truth or realised error cannot enter a deployment-time model")
    return frame.loc[:, list(features)].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)


@dataclass
class ConstantProbability:
    probability: float

    def predict_proba(self, matrix):
        value = np.full(len(matrix), self.probability)
        return np.column_stack([1 - value, value])


def fit_score(frame: pd.DataFrame, features: tuple[str, ...], kind: str, *, seed: int):
    available = np.isfinite(pd.to_numeric(frame.abserr_policy, errors="coerce"))
    train = frame.loc[available]
    if train.empty:
        raise ValueError("No finite training reconstruction errors")
    if kind in {"certificate", "policy_certificate", "certificate_joint"}:
        units = np.array(sorted(train.independence_group.astype(str).unique()))
        calibration_units = set(np.random.default_rng(seed).permutation(units)[::5])
        head_rows = ~train.independence_group.astype(str).isin(calibration_units)
        certificate = Certificate(features=features)
        return certificate.fit(certificate_frame(train.loc[head_rows], labels=True), certificate_frame(train.loc[~head_rows], labels=True), seed=seed)
    matrix = feature_matrix(train, features)
    if kind == "gbr":
        model = HistGradientBoostingRegressor(loss="quantile", quantile=0.9, max_depth=4, max_iter=350, learning_rate=0.06, min_samples_leaf=40, random_state=seed)
        return model.fit(matrix, train.abserr_policy.to_numpy(dtype=float))
    response = train.policy_bad.astype(int).to_numpy()
    if np.unique(response).size == 1:
        return ConstantProbability(float(response[0]))
    transforms = [SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)]
    if kind == "spline":
        transforms.append(SplineTransformer(n_knots=5, degree=3, include_bias=False))
    transforms.extend([StandardScaler(), LogisticRegression(C=1, max_iter=2000, random_state=seed)])
    model = make_pipeline(*transforms)
    return model.fit(matrix, response)


def predict_score(model, frame: pd.DataFrame, features: tuple[str, ...], kind: str) -> np.ndarray:
    if kind in {"certificate", "policy_certificate", "certificate_joint"}:
        if kind == "policy_certificate":
            raw = model._predict_raw(certificate_frame(frame, labels=False))
            prediction = np.full(len(frame), np.inf)
            if raw is not None:
                raw = raw.reindex(frame.index)
                for method in SCREENED_ESTIMATORS:
                    selected = frame.policy_choice.astype(str).eq(method).to_numpy()
                    column = f"bound_{method}"
                    if column in raw:
                        prediction[selected] = pd.to_numeric(raw[column], errors="coerce").to_numpy()[selected]
            return np.where(np.isfinite(frame.policy_metric) & np.isfinite(prediction), prediction, np.inf)
        result = model.predict(certificate_frame(frame, labels=False))
        prediction = pd.to_numeric(result.certificate_bound, errors="coerce").to_numpy()
        available = np.isfinite(pd.to_numeric(frame.policy_metric, errors="coerce").to_numpy())
        return np.where(available & np.isfinite(prediction), prediction, np.inf)
    matrix = feature_matrix(frame, features)
    prediction = model.predict(matrix) if kind == "gbr" else model.predict_proba(matrix)[:, 1]
    available = np.isfinite(pd.to_numeric(frame.policy_metric, errors="coerce").to_numpy())
    return np.where(available & np.isfinite(prediction), prediction, np.inf)


def certificate_delivery(model, frame: pd.DataFrame) -> pd.DataFrame:
    result = model.predict(certificate_frame(frame, labels=False))
    delivered = frame.copy()
    delivered["policy_choice"] = result.certificate_choice
    point = np.full(len(frame), np.nan)
    for method in SCREENED_ESTIMATORS:
        selected = result.certificate_choice.astype(str).eq(method).to_numpy()
        point[selected] = frame[f"hottest30_{method}"].to_numpy(dtype=float)[selected]
    delivered["policy_metric"] = point
    if "truth_hottest30" in frame:
        delivered["abserr_policy"] = np.abs(point - frame.truth_hottest30.to_numpy())
        delivered["policy_bad"] = ~np.isfinite(point) | (delivered.abserr_policy > 0.5)
    return delivered


def certificate_frame(frame: pd.DataFrame, *, labels: bool) -> pd.DataFrame:
    columns = list(dict.fromkeys(["network_id", "longest_run_month", "n_visible_donors", "donor_coverage_mean", "air_available", "left_flank", "right_flank", *SCREEN_FEATURES]))
    view = frame.loc[:, columns].copy()
    view["donor_regime"] = frame.n_visible_donors.map(donor_regime)
    for method in SCREENED_ESTIMATORS:
        view[f"metric_{method}"] = frame[f"hottest30_{method}"]
        if labels:
            view[f"err_{method}"] = frame[f"hottest30_{method}"] - frame.truth_hottest30
            view[f"abserr_{method}"] = view[f"err_{method}"].abs()
    return view


def empirical_threshold(scores: np.ndarray, failures: np.ndarray, groups: np.ndarray, candidates: np.ndarray, *, seed: int, draws: int = 1000, risk_cap: float = 0.05, alpha: float = 0.05) -> dict:
    groups, group_index = np.unique(np.asarray(groups).astype(str), return_inverse=True)
    admitted = np.array([np.bincount(group_index, weights=np.isfinite(scores) & (scores <= threshold), minlength=len(groups)) for threshold in candidates]).T
    bad = np.array([np.bincount(group_index, weights=(np.isfinite(scores) & (scores <= threshold)) * failures, minlength=len(groups)) for threshold in candidates]).T
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(len(groups), np.full(len(groups), 1 / len(groups)), size=draws)
    accepted = weights @ admitted
    failed = weights @ bad
    rates = np.divide(failed, accepted, out=np.ones_like(failed), where=accepted > 0)
    upper = np.quantile(rates, 1 - alpha / len(candidates), axis=0)
    acceptable = np.flatnonzero((upper <= risk_cap) & (admitted.sum(axis=0) > 0))
    chosen = int(acceptable[-1]) if len(acceptable) else None
    return {
        "threshold": float(candidates[chosen]) if chosen is not None else -float("inf"),
        "upper": float(upper[chosen]) if chosen is not None else None,
        "status": "empirical_threshold_selected" if chosen is not None else "no_empirical_threshold",
        "interpretation": "descriptive clustered-bootstrap selection; no finite-sample guarantee",
    }
