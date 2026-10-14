"""Step 6 — the design: a calibrated usability certificate.

For one station-year with a known outage pattern the certificate does three
things, using only information visible at decision time:

1. predicts, for every *supported* estimator, an upper bound on the absolute
   error the completed year's thermal metric would carry;
2. selects the estimator with the smallest bound, so method selection and
   screening are one object rather than two;
3. emits a conformal prediction interval on the metric and a use/exclude
   decision at a tolerance the analyst names.

Calibration is split-conformal with network-level grouping, so the calibration
set and the test set never share a river network. The Mondrian variant
calibrates within pre-declared strata to obtain conditional coverage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from stream_recoverability.experiments.v17_fitness.paths import NOMINAL_COVERAGE, PRIMARY_TOLERANCE_C

SCREEN_FEATURES = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "peak_overlap",
    "warm_observed_fraction",
    "observed_peak_margin",
    "observed_peak",
    "clim_peak",
    "n_visible_donors",
    "donor_corr_mean",
    "donor_corr_max",
    "donor_corr_min",
    "donor_coverage_mean",
    "train_resid_sd",
    "seasonal_amplitude",
    "train_metric_sd",
    "n_complete_years",
    "record_years",
    "month_sin",
    "month_cos",
    "left_flank",
    "right_flank",
    "has_complete_window",
    "air_available",
)

SCREENED_ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def feature_frame(cases: pd.DataFrame, features: Sequence[str] | None = None) -> pd.DataFrame:
    """Only decision-time-visible quantities. Enforced here, not by convention."""

    names = tuple(SCREEN_FEATURES if features is None else features)
    frame = pd.DataFrame(index=cases.index)
    month = pd.to_numeric(cases["longest_run_month"], errors="coerce").fillna(6)
    frame["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    frame["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    for name in names:
        if name in ("month_sin", "month_cos"):
            continue
        if name not in cases.columns:
            frame[name] = np.nan
            continue
        column = cases[name]
        if column.dtype == bool:
            frame[name] = column.astype(float)
        else:
            frame[name] = pd.to_numeric(column, errors="coerce")
    return frame[list(names)]


def supported(cases: pd.DataFrame, estimator: str) -> np.ndarray:
    """An estimator is supported when its reconstruction contract can be met.

    Decision-time features gate candidates. When a finite ``metric_<estimator>``
    column is already present (designed cases or archive deployment rows), it is
    required as well: selecting a method that cannot return the annual metric is
    not support. Missing metric columns leave the feature gate alone (live
    reconstruction must still verify finiteness before admission).
    """

    if estimator == "donor_ridge":
        visible = pd.to_numeric(cases["n_visible_donors"], errors="coerce").fillna(0) > 0
        if "donor_coverage_mean" in cases.columns:
            coverage = pd.to_numeric(cases["donor_coverage_mean"], errors="coerce")
            # Match usable_donors threshold: at least one donor covering 90% of
            # hidden days on average is necessary but not sufficient; metric
            # finiteness below closes the remaining train/predict failures.
            visible = visible & coverage.fillna(0).ge(0.90)
        mask = visible.to_numpy()
    elif estimator == "air_ridge":
        mask = cases["air_available"].astype(bool).to_numpy()
    elif estimator == "linear_interp":
        mask = (cases["left_flank"].astype(bool) & cases["right_flank"].astype(bool)).to_numpy()
    else:
        mask = np.ones(len(cases), dtype=bool)

    metric_col = f"metric_{estimator}"
    if metric_col in cases.columns:
        finite = pd.to_numeric(cases[metric_col], errors="coerce").to_numpy(dtype=float)
        mask = mask & np.isfinite(finite)
    return mask


@dataclass
class EstimatorHead:
    """Quantile models for one estimator. Calibration lives on the Certificate."""

    estimator: str
    upper: object | None = None
    lo: object | None = None
    hi: object | None = None
    trained: bool = False


def _quantile_model(alpha: float, seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=float(alpha),
        random_state=int(seed),
        max_depth=4,
        max_iter=350,
        learning_rate=0.06,
        min_samples_leaf=40,
    )


EPSILON_C = 0.02


@dataclass
class Certificate:
    """The frozen object: heads per estimator plus selection-conditional calibration.

    Two properties of the calibration matter and were both wrong in the first
    implementation. First, the bound is calibrated *after* the estimator is
    selected, because selecting the smallest of several bounds is a winner's
    curse that a per-estimator calibration cannot see. Second, the conformity
    score is multiplicative rather than additive, because the error scale of
    this problem spans an order of magnitude between an outage that misses the
    peak window and one that covers it; a single additive offset cannot cover
    both.
    """

    heads: dict = field(default_factory=dict)
    coverage: float = NOMINAL_COVERAGE
    stratum_column: str | None = None
    features: tuple = SCREEN_FEATURES
    scale_abs: float = 1.0
    scale_interval: float = 1.0
    strata_scale_abs: dict = field(default_factory=dict)
    cluster_scale_abs: float = 1.0
    cluster_scale_interval: float = 1.0
    cluster_level: float = 0.90
    cluster_quantiles_abs: tuple = ()
    cluster_quantiles_interval: tuple = ()

    # -- training ---------------------------------------------------------
    def fit(
        self,
        fit_cases: pd.DataFrame,
        calibration_cases: pd.DataFrame,
        *,
        estimators: Sequence[str] = SCREENED_ESTIMATORS,
        seed: int = 0,
        stratum_column: str | None = "donor_regime",
    ) -> "Certificate":
        self.stratum_column = stratum_column
        alpha = 1.0 - float(self.coverage)
        for estimator in estimators:
            head = EstimatorHead(estimator=estimator)
            mask = supported(fit_cases, estimator) & fit_cases[f"abserr_{estimator}"].notna().to_numpy()
            if int(mask.sum()) < 400:
                self.heads[estimator] = head
                continue
            X = feature_frame(fit_cases, self.features).loc[mask]
            abs_error = pd.to_numeric(fit_cases.loc[mask, f"abserr_{estimator}"], errors="coerce")
            signed = pd.to_numeric(fit_cases.loc[mask, f"err_{estimator}"], errors="coerce")
            head.upper = _quantile_model(self.coverage, seed).fit(X, abs_error)
            head.lo = _quantile_model(alpha / 2.0, seed).fit(X, signed)
            head.hi = _quantile_model(1.0 - alpha / 2.0, seed).fit(X, signed)
            head.trained = True
            self.heads[estimator] = head

        raw = self._raw(calibration_cases)
        if raw is not None:
            abs_scores = raw["abs_error"].to_numpy() / np.maximum(raw["raw_bound"].to_numpy(), EPSILON_C)
            self.scale_abs = _conformal_quantile(abs_scores, self.coverage)
            width = np.maximum(raw["raw_high"].to_numpy() - raw["raw_low"].to_numpy(), EPSILON_C)
            interval_scores = (
                np.maximum(raw["raw_low"].to_numpy() - raw["signed_error"].to_numpy(),
                           raw["signed_error"].to_numpy() - raw["raw_high"].to_numpy())
                / width
            )
            self.scale_interval = _conformal_quantile(interval_scores, self.coverage)
            # Cluster-aware calibration. Conformal validity assumes
            # exchangeability, which fails between river networks: a pooled
            # quantile gives the right coverage on average over networks and
            # too little inside the hardest ones. Taking a high quantile of the
            # per-network quantiles targets "most networks are covered" instead
            # of "cases are covered on average".
            clusters = calibration_cases.loc[raw.index, "network_id"].astype(str).to_numpy()
            self.cluster_quantiles_abs = _per_cluster_quantiles(abs_scores, clusters, self.coverage)
            self.cluster_quantiles_interval = _per_cluster_quantiles(interval_scores, clusters, self.coverage)
            self.cluster_scale_abs = _cluster_quantile(abs_scores, clusters, self.coverage, self.cluster_level)
            self.cluster_scale_interval = _cluster_quantile(
                interval_scores, clusters, self.coverage, self.cluster_level
            )
            if stratum_column is not None and stratum_column in calibration_cases.columns:
                strata = calibration_cases.loc[raw.index, stratum_column].astype(str).to_numpy()
                for value in np.unique(strata):
                    block = abs_scores[strata == value]
                    if len(block) >= 80:
                        self.strata_scale_abs[str(value)] = _conformal_quantile(block, self.coverage)
        return self

    # -- internals --------------------------------------------------------
    def _predict_raw(self, cases: pd.DataFrame) -> pd.DataFrame | None:
        """Uncalibrated bounds and selection from decision-time features only.

        Never reads truth, err_*, or abserr_*. Supported estimators are scored
        whenever their inputs exist, so real incomplete years can be screened.
        """

        X = feature_frame(cases, self.features)
        n = len(cases)
        bounds = pd.DataFrame(index=cases.index)
        lows = pd.DataFrame(index=cases.index)
        highs = pd.DataFrame(index=cases.index)
        any_trained = False
        for estimator, head in self.heads.items():
            column = np.full(n, np.inf, dtype=float)
            low = np.full(n, np.nan, dtype=float)
            high = np.full(n, np.nan, dtype=float)
            if head.trained:
                any_trained = True
                mask = supported(cases, estimator)
                if mask.any():
                    block = X.loc[mask]
                    column[mask] = np.maximum(head.upper.predict(block), 0.0)
                    low[mask] = head.lo.predict(block)
                    high[mask] = head.hi.predict(block)
            bounds[estimator] = column
            lows[estimator] = low
            highs[estimator] = high
        if not any_trained:
            return None
        # Prefer the lowest bound among estimators that are actually supported
        # (including reconstructability when metric_* is present). Unsupported
        # estimators stay at +inf from the loop above.
        chosen = bounds.idxmin(axis=1)
        raw_bound = bounds.min(axis=1)
        valid = np.isfinite(raw_bound.to_numpy())
        # Abstain when no supported estimator remains (all +inf).
        chosen = chosen.where(valid, other=pd.NA)
        raw_bound = raw_bound.where(valid, other=np.nan)
        frame = pd.DataFrame(index=cases.index)
        frame["chosen"] = chosen
        frame["raw_bound"] = raw_bound
        picked_low = np.full(n, np.nan, dtype=float)
        picked_high = np.full(n, np.nan, dtype=float)
        for estimator in bounds.columns:
            mask = (chosen == estimator).to_numpy() & valid
            if not mask.any():
                continue
            picked_low[mask] = lows[estimator].to_numpy()[mask]
            picked_high[mask] = highs[estimator].to_numpy()[mask]
        frame["raw_low"] = picked_low
        frame["raw_high"] = picked_high
        for estimator in bounds.columns:
            frame[f"bound_{estimator}"] = bounds[estimator]
        keep = frame["raw_bound"].notna() & np.isfinite(frame["raw_bound"])
        return frame.loc[keep]

    @staticmethod
    def _attach_truth(cases: pd.DataFrame, predicted: pd.DataFrame) -> pd.DataFrame:
        """Join realised errors when evaluation columns exist; else leave NaN."""

        frame = predicted.copy()
        n = len(frame)
        abs_error = np.full(n, np.nan, dtype=float)
        signed_error = np.full(n, np.nan, dtype=float)
        metric = np.full(n, np.nan, dtype=float)
        chosen = frame["chosen"].astype(str).to_numpy()
        for estimator in sorted(set(chosen)):
            mask = chosen == estimator
            if not mask.any():
                continue
            abs_col, err_col, metric_col = f"abserr_{estimator}", f"err_{estimator}", f"metric_{estimator}"
            if abs_col in cases.columns:
                abs_error[mask] = pd.to_numeric(cases.loc[frame.index, abs_col], errors="coerce").to_numpy()[mask]
            if err_col in cases.columns:
                signed_error[mask] = pd.to_numeric(cases.loc[frame.index, err_col], errors="coerce").to_numpy()[mask]
            if metric_col in cases.columns:
                metric[mask] = pd.to_numeric(cases.loc[frame.index, metric_col], errors="coerce").to_numpy()[mask]
        frame["abs_error"] = abs_error
        frame["signed_error"] = signed_error
        frame["metric"] = metric
        return frame

    def _raw(self, cases: pd.DataFrame) -> pd.DataFrame | None:
        """Calibration view: predictions restricted to rows with realised absolute error."""

        predicted = self._predict_raw(cases)
        if predicted is None or predicted.empty:
            return None
        scored = self._attach_truth(cases, predicted)
        return scored.loc[scored["abs_error"].notna()]

    # -- application ------------------------------------------------------
    def cluster_scales(self, level: float) -> tuple[float, float]:
        """Calibration scales targeting coverage inside ``level`` of networks."""

        def pick(stored: tuple, fallback: float) -> float:
            values = np.asarray(stored, dtype=float)
            if values.size < 3:
                return float(fallback)
            return float(np.quantile(values, float(level)))

        return pick(self.cluster_quantiles_abs, self.scale_abs), pick(
            self.cluster_quantiles_interval, self.scale_interval
        )

    def _calibrated_frame(
        self,
        raw: pd.DataFrame,
        cases: pd.DataFrame,
        *,
        mondrian: bool,
        cluster_aware: bool,
        cluster_level: float | None,
    ) -> pd.DataFrame:
        if cluster_aware:
            scale, interval_scale = self.cluster_scales(
                self.cluster_level if cluster_level is None else float(cluster_level)
            )
        else:
            scale, interval_scale = self.scale_abs, self.scale_interval
        if mondrian and self.strata_scale_abs and self.stratum_column in cases.columns:
            strata = cases.loc[raw.index, self.stratum_column].astype(str)
            scale = strata.map(lambda value: self.strata_scale_abs.get(value, self.scale_abs)).to_numpy()
        bound = np.maximum(raw["raw_bound"].to_numpy(), EPSILON_C) * scale
        width = np.maximum(raw["raw_high"].to_numpy() - raw["raw_low"].to_numpy(), EPSILON_C)
        low = raw["raw_low"].to_numpy() - interval_scale * width
        high = raw["raw_high"].to_numpy() + interval_scale * width

        frame = pd.DataFrame(index=raw.index)
        frame["certificate_choice"] = raw["chosen"]
        frame["certificate_bound"] = bound
        frame["certificate_raw_bound"] = raw["raw_bound"]
        frame["interval_low"] = low
        frame["interval_high"] = high
        frame["interval_width"] = high - low
        for estimator in self.heads:
            column = f"bound_{estimator}"
            if column in raw.columns:
                frame[column] = raw[column]
        return frame

    def predict(
        self,
        cases: pd.DataFrame,
        *,
        mondrian: bool = False,
        cluster_aware: bool = False,
        cluster_level: float | None = None,
    ) -> pd.DataFrame:
        """Deployment interface: choice, bound and interval without truth columns."""

        raw = self._predict_raw(cases)
        out = pd.DataFrame(index=cases.index)
        if raw is None or raw.empty:
            for column in ("certificate_choice", "certificate_bound", "certificate_raw_bound"):
                out[column] = np.nan
            return out
        frame = self._calibrated_frame(
            raw, cases, mondrian=mondrian, cluster_aware=cluster_aware, cluster_level=cluster_level
        )
        return frame.reindex(cases.index)

    def apply(
        self,
        cases: pd.DataFrame,
        *,
        mondrian: bool = False,
        cluster_aware: bool = False,
        cluster_level: float | None = None,
    ) -> pd.DataFrame:
        """Evaluation interface: predict, then attach realised errors when present.

        Rows without abserr_* remain in the prediction columns but have NaN
        evaluation fields. Calibration training still uses :meth:`_raw`, which
        keeps only scored rows.
        """

        predictions = self.predict(
            cases, mondrian=mondrian, cluster_aware=cluster_aware, cluster_level=cluster_level
        )
        out = predictions.copy()
        if out["certificate_choice"].isna().all():
            for column in ("certificate_abs_error", "certificate_signed_error", "certificate_metric"):
                out[column] = np.nan
            return out
        scored = self._attach_truth(
            cases,
            pd.DataFrame(
                {
                    "chosen": out["certificate_choice"],
                    "raw_bound": out["certificate_raw_bound"],
                },
                index=out.index,
            ).dropna(subset=["chosen"]),
        )
        out["certificate_abs_error"] = scored["abs_error"].reindex(out.index)
        out["certificate_signed_error"] = scored["signed_error"].reindex(out.index)
        out["certificate_metric"] = scored["metric"].reindex(out.index)
        signed = out["certificate_signed_error"].to_numpy(dtype=float)
        abs_err = out["certificate_abs_error"].to_numpy(dtype=float)
        low = out["interval_low"].to_numpy(dtype=float)
        high = out["interval_high"].to_numpy(dtype=float)
        bound = out["certificate_bound"].to_numpy(dtype=float)
        out["covered"] = (signed >= low) & (signed <= high)
        out["bound_covered"] = abs_err <= bound
        return out


def _per_cluster_quantiles(scores: np.ndarray, clusters: np.ndarray, coverage: float) -> tuple:
    finite = np.isfinite(scores)
    scores, clusters = np.asarray(scores, dtype=float)[finite], np.asarray(clusters)[finite]
    out = []
    for value in np.unique(clusters):
        block = scores[clusters == value]
        if block.size >= 30:
            out.append(_conformal_quantile(block, coverage))
    return tuple(out)


def _cluster_quantile(
    scores: np.ndarray, clusters: np.ndarray, coverage: float, cluster_level: float
) -> float:
    """Quantile of the per-cluster conformal quantiles.

    Returns the value that covers ``coverage`` of cases inside at least
    ``cluster_level`` of clusters, rather than ``coverage`` of cases pooled.
    """

    finite = np.isfinite(scores)
    scores, clusters = np.asarray(scores, dtype=float)[finite], np.asarray(clusters)[finite]
    if scores.size == 0:
        return 1.0
    per_cluster = []
    for value in np.unique(clusters):
        block = scores[clusters == value]
        if block.size >= 30:
            per_cluster.append(_conformal_quantile(block, coverage))
    if len(per_cluster) < 3:
        return _conformal_quantile(scores, coverage)
    return float(np.quantile(np.asarray(per_cluster, dtype=float), float(cluster_level)))


def _conformal_quantile(scores: np.ndarray, coverage: float) -> float:
    finite = np.asarray(scores, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 1.0
    n = finite.size
    level = min(1.0, np.ceil((n + 1) * float(coverage)) / n)
    return float(np.quantile(finite, level))


def split_networks(networks: Sequence[str], *, fraction: float, seed: int) -> tuple[set[str], set[str]]:
    unique = sorted({str(value) for value in networks})
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(unique))
    cut = max(1, int(round(len(unique) * float(fraction))))
    calibration = {unique[int(i)] for i in order[:cut]}
    fitting = {value for value in unique if value not in calibration}
    return fitting, calibration


def out_of_fold_certificates(
    cases: pd.DataFrame,
    *,
    n_splits: int = 5,
    calibration_fraction: float = 0.3,
    seed: int = 0,
    coverage: float = NOMINAL_COVERAGE,
    mondrian: bool = False,
    cluster_aware: bool = False,
    features: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Grouped cross-validated certificates: no network is ever in its own fit."""

    networks = sorted(cases["network_id"].astype(str).unique())
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(networks))
    folds = {networks[int(idx)]: int(position % n_splits) for position, idx in enumerate(order)}
    cases = cases.copy()
    cases["_fold"] = cases["network_id"].astype(str).map(folds)
    pieces = []
    for fold in range(int(n_splits)):
        test = cases.loc[cases["_fold"].eq(fold)]
        train = cases.loc[~cases["_fold"].eq(fold)]
        if test.empty or train.empty:
            continue
        fit_ids, cal_ids = split_networks(
            train["network_id"].astype(str).unique(), fraction=calibration_fraction, seed=seed + fold
        )
        fit_cases = train.loc[train["network_id"].astype(str).isin(fit_ids)]
        cal_cases = train.loc[train["network_id"].astype(str).isin(cal_ids)]
        if fit_cases.empty or cal_cases.empty:
            continue
        model = Certificate(
            coverage=coverage, features=tuple(SCREEN_FEATURES if features is None else features)
        ).fit(fit_cases, cal_cases, seed=seed + fold)
        applied = model.apply(test, mondrian=mondrian, cluster_aware=cluster_aware)
        applied["_fold"] = fold
        pieces.append(applied)
    if not pieces:
        return pd.DataFrame(index=cases.index)
    return pd.concat(pieces).reindex(cases.index)


def usable(bound: pd.Series, tolerance: float = PRIMARY_TOLERANCE_C) -> pd.Series:
    return pd.to_numeric(bound, errors="coerce") <= float(tolerance)
