"""Leakage-safe adapters for the v9.1 T2 meteorology and hydraulics inputs.

The adapters are intentionally independent of the T2 runner.  They turn a
provider-audited daily-long table into date-aligned, train-standardised feature
columns which can be joined to a temperature panel.  No temperature value is
ever read by the adapter and missing auxiliary values are never interpolated.

Calendar alignment is explicit: for meteorology, ``lag_days=k`` means that the
source value labelled ``target_date + k`` is attached to ``target_date``.  The
v2 protocol's -1/0/+1 alternatives are therefore separate sensitivity cells,
not a lag selected from held-out performance.  Hydraulics is always joined on
the identical provider day label.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

METEOROLOGY_VARIABLES = ("Ta", "P", "W", "RH", "Rs")
HYDRAULICS_VARIABLES = ("F", "L")
SUPPORTED_CONDITIONS = (
    "B_union_D_union_M",
    "B_union_D_union_M_union_H",
)
ADAPTER_CONTRACT_VERSION = "t2_v91_information_adapter_v1"


def _canonical_sha(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _daily_index(values: Sequence[object] | pd.Index, *, name: str) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(values, errors="raise"))
    if index.tz is not None:
        raise ValueError(f"{name} must use timezone-naive provider day labels")
    if index.has_duplicates:
        raise ValueError(f"{name} contains duplicate day labels")
    if not index.equals(index.normalize()):
        raise ValueError(f"{name} contains sub-daily timestamps")
    if not index.is_monotonic_increasing:
        raise ValueError(f"{name} must be sorted")
    return index


def _training_mask(
    value: Sequence[bool] | pd.Series,
    index: pd.DatetimeIndex,
) -> pd.Series:
    if isinstance(value, pd.Series):
        if not value.index.equals(index):
            raise ValueError("train_mask index must exactly equal target_index")
        mask = value.astype(bool)
    else:
        array = np.asarray(value)
        if array.ndim != 1 or len(array) != len(index):
            raise ValueError("train_mask must have one value per target day")
        if array.dtype.kind != "b":
            raise TypeError("train_mask must be boolean")
        mask = pd.Series(array, index=index, dtype=bool)
    if not bool(mask.any()):
        raise ValueError("train_mask selects no fitting days")
    return mask


def _required_columns() -> set[str]:
    return {
        "date",
        "site_id",
        "variable",
        "value",
        "source",
        "natural_observed",
        "qc_status",
        "approval_status",
        "quality_approved",
    }


def _provider_eligible(rows: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return provider-specific eligibility and an auditable QC basis.

    NASA POWER has no USGS-like approval flag.  Its values are called
    provider-screened non-fill values, never provider-approved observations.
    USGS hydraulics requires an explicit Approved status; approved estimated
    values remain eligible under the frozen external-data quality rule.
    """

    source = rows["source"].astype("string")
    variable = rows["variable"].astype("string")
    finite = np.isfinite(pd.to_numeric(rows["value"], errors="coerce"))
    observed = rows["natural_observed"].fillna(False).astype(bool)
    qc = rows["qc_status"].astype("string")
    approval = rows["approval_status"].astype("string")
    approved = rows["quality_approved"].fillna(False).astype(bool)

    meteorology = variable.isin(METEOROLOGY_VARIABLES)
    hydraulics = variable.isin(HYDRAULICS_VARIABLES)
    met_ok = (
        meteorology
        & source.eq("nasa_power_daily_point")
        & qc.eq("provider_value")
        & observed
        & finite
    )
    hydro_ok = (
        hydraulics
        & source.isin(("usgs_ogc_daily", "usgs_legacy_nwis_dv_rdb"))
        & approval.eq("Approved")
        & approved
        & qc.isin(("approved", "approved_estimated"))
        & observed
        & finite
    )
    basis = pd.Series("rejected_provider_qc", index=rows.index, dtype="string")
    basis.loc[met_ok] = "provider_screened_non_fill_not_provider_approval"
    basis.loc[hydro_ok] = "usgs_approval_status_approved"
    return met_ok | hydro_ok, basis


def _feature_name(site_id: str, variable: str) -> str:
    group = "M" if variable in METEOROLOGY_VARIABLES else "H"
    return f"{site_id}__{group}__{variable}"


@dataclass(frozen=True)
class InformationFeatureBundle:
    """A transformed information matrix and its non-performance audit."""

    features: pd.DataFrame
    audit: Mapping[str, Any]


@dataclass(frozen=True)
class FittedT2InformationAdapter:
    """Train-fitted M/H adapter whose transform cannot consume temperature."""

    condition: str
    site_ids: tuple[str, ...]
    variables: tuple[str, ...]
    meteorology_lag_days: int
    target_index: tuple[str, ...]
    train_day_sha256: str
    centers: Mapping[str, float | None]
    scales: Mapping[str, float | None]
    train_counts: Mapping[str, int]
    fit_qc_audit: Mapping[str, Any]
    contract_version: str = ADAPTER_CONTRACT_VERSION

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(
            _feature_name(site, variable)
            for site in self.site_ids
            for variable in self.variables
        )

    def transform(self, daily_long: pd.DataFrame) -> InformationFeatureBundle:
        index = _daily_index(self.target_index, name="fitted target_index")
        matrix, audit = _materialize_raw(
            daily_long,
            target_index=index,
            site_ids=self.site_ids,
            variables=self.variables,
            meteorology_lag_days=self.meteorology_lag_days,
        )
        standardised = matrix.copy()
        for column in self.feature_names:
            center = self.centers[column]
            scale = self.scales[column]
            if center is None or scale is None:
                standardised[column] = np.nan
            else:
                standardised[column] = (matrix[column] - center) / scale
        standardised.attrs.update(
            {
                "adapter_contract_version": self.contract_version,
                "condition": self.condition,
                "meteorology_lag_semantics": (
                    "source_date_equals_target_date_plus_lag_days"
                ),
                "meteorology_lag_days": self.meteorology_lag_days,
                "standardization": "mean_and_population_sd_fit_on_train_days_only",
                "missing_value_policy": "preserve_na_no_interpolation",
            }
        )
        return InformationFeatureBundle(
            features=standardised,
            audit={
                **audit,
                "contract_version": self.contract_version,
                "condition": self.condition,
                "fit_train_day_sha256": self.train_day_sha256,
                "fit_train_counts": dict(self.train_counts),
                "temperature_columns_consumed": 0,
            },
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "condition": self.condition,
            "site_ids": list(self.site_ids),
            "variables": list(self.variables),
            "feature_names": list(self.feature_names),
            "meteorology_lag_days": self.meteorology_lag_days,
            "meteorology_lag_semantics": "source_date_equals_target_date_plus_lag_days",
            "hydraulics_alignment": "same_provider_calendar_day_label",
            "fit_train_day_sha256": self.train_day_sha256,
            "fit_train_counts": dict(self.train_counts),
            "centers": dict(self.centers),
            "scales": dict(self.scales),
            "fit_qc_audit": dict(self.fit_qc_audit),
            "leakage_boundary": {
                "fit_statistics": "train_days_only",
                "target_temperature_consumed": False,
                "gap_auxiliary_values": "allowed_only_as_declared_information_condition",
                "future_temperature_boundary": "owned_by_B_adapter_not_this_module",
                "missing_auxiliary_values": "preserved_as_na_no_fill",
                "lag_selection_from_heldout_skill": False,
            },
        }


def _materialize_raw(
    daily_long: pd.DataFrame,
    *,
    target_index: pd.DatetimeIndex,
    site_ids: Sequence[str],
    variables: Sequence[str],
    meteorology_lag_days: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing = sorted(_required_columns() - set(daily_long.columns))
    if missing:
        raise ValueError(f"daily_long lacks provider-audit columns: {missing}")
    selected = daily_long.loc[
        daily_long["site_id"].astype(str).isin(site_ids)
        & daily_long["variable"].astype(str).isin(variables)
    ].copy()
    dates = pd.DatetimeIndex(pd.to_datetime(selected["date"], errors="raise"))
    if dates.tz is not None or not dates.equals(dates.normalize()):
        raise ValueError("daily_long auxiliary dates must be timezone-naive day labels")
    selected["date"] = dates
    duplicate = selected.duplicated(["date", "site_id", "variable"], keep=False)
    if bool(duplicate.any()):
        raise ValueError("daily_long contains duplicate site-day-variable auxiliaries")
    eligible, basis = _provider_eligible(selected)
    selected["provider_eligible"] = eligible
    selected["provider_qc_basis"] = basis
    selected["aligned_date"] = selected["date"]
    is_met = selected["variable"].isin(METEOROLOGY_VARIABLES)
    selected.loc[is_met, "aligned_date"] = (
        selected.loc[is_met, "date"]
        - pd.to_timedelta(int(meteorology_lag_days), unit="D")
    )
    selected["feature"] = [
        _feature_name(str(site), str(variable))
        for site, variable in zip(
            selected["site_id"], selected["variable"], strict=True
        )
    ]
    selected["eligible_value"] = pd.to_numeric(
        selected["value"], errors="coerce"
    ).where(selected["provider_eligible"])
    expected = [
        _feature_name(str(site), str(variable))
        for site in site_ids
        for variable in variables
    ]
    if selected.empty:
        matrix = pd.DataFrame(index=target_index, columns=expected, dtype=float)
    else:
        matrix = selected.pivot(
            index="aligned_date", columns="feature", values="eligible_value"
        ).reindex(index=target_index, columns=expected)
        matrix.columns.name = None
        matrix.index.name = "date"
    counts = selected.groupby("provider_qc_basis", dropna=False).size().to_dict()
    audit = {
        "n_input_auxiliary_rows": len(selected),
        "n_provider_eligible_rows": int(selected["provider_eligible"].sum()),
        "n_provider_rejected_rows": int((~selected["provider_eligible"]).sum()),
        "provider_qc_basis_counts": {str(key): int(value) for key, value in counts.items()},
        "date_alignment": "exact_daily_label_no_resampling",
        "meteorology_source_date_equals_target_date_plus_lag_days": int(
            meteorology_lag_days
        ),
        "hydraulics_lag_days": 0,
        "missing_value_policy": "preserve_na_no_interpolation",
    }
    return matrix.astype(float), audit


def fit_t2_information_adapter(
    daily_long: pd.DataFrame,
    *,
    target_index: Sequence[object] | pd.Index,
    train_mask: Sequence[bool] | pd.Series,
    site_ids: Sequence[str],
    condition: str,
    meteorology_lag_days: int = 0,
) -> FittedT2InformationAdapter:
    """Fit train-only standardisation for one frozen nested condition."""

    if condition not in SUPPORTED_CONDITIONS:
        raise ValueError(f"unsupported v9.1 information condition: {condition}")
    if int(meteorology_lag_days) not in (-1, 0, 1):
        raise ValueError("meteorology lag must be one of the predeclared -1/0/+1 days")
    sites = tuple(str(value) for value in site_ids)
    if not sites or len(set(sites)) != len(sites):
        raise ValueError("site_ids must be non-empty and unique")
    index = _daily_index(target_index, name="target_index")
    fitting = _training_mask(train_mask, index)
    variables = METEOROLOGY_VARIABLES + (
        HYDRAULICS_VARIABLES
        if condition == "B_union_D_union_M_union_H"
        else ()
    )
    raw, qc_audit = _materialize_raw(
        daily_long,
        target_index=index,
        site_ids=sites,
        variables=variables,
        meteorology_lag_days=int(meteorology_lag_days),
    )
    train = raw.loc[fitting]
    centers: dict[str, float | None] = {}
    scales: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    for column in raw.columns:
        values = train[column].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        counts[column] = int(finite.size)
        if finite.size == 0:
            centers[column] = None
            scales[column] = None
            continue
        center = float(np.mean(finite))
        scale = float(np.std(finite, ddof=0))
        centers[column] = center
        scales[column] = scale if scale > 0.0 else 1.0
    train_days = [value.strftime("%Y-%m-%d") for value in index[fitting.to_numpy()]]
    return FittedT2InformationAdapter(
        condition=condition,
        site_ids=sites,
        variables=variables,
        meteorology_lag_days=int(meteorology_lag_days),
        target_index=tuple(value.strftime("%Y-%m-%d") for value in index),
        train_day_sha256=_canonical_sha(train_days),
        centers=centers,
        scales=scales,
        train_counts=counts,
        fit_qc_audit=qc_audit,
    )


def attach_information_features(
    temperature_panel: pd.DataFrame,
    bundle: InformationFeatureBundle,
) -> pd.DataFrame:
    """Join adapter output without changing or inspecting temperature values."""

    if not isinstance(temperature_panel.index, pd.DatetimeIndex):
        raise TypeError("temperature_panel must use a DatetimeIndex")
    if not temperature_panel.index.equals(bundle.features.index):
        raise ValueError("temperature panel and information features are not date-aligned")
    overlap = sorted(set(temperature_panel.columns) & set(bundle.features.columns))
    if overlap:
        raise ValueError(f"information feature names collide with panel: {overlap}")
    return temperature_panel.join(bundle.features, how="left", validate="one_to_one")


__all__ = [
    "ADAPTER_CONTRACT_VERSION",
    "HYDRAULICS_VARIABLES",
    "METEOROLOGY_VARIABLES",
    "FittedT2InformationAdapter",
    "InformationFeatureBundle",
    "attach_information_features",
    "fit_t2_information_adapter",
]
