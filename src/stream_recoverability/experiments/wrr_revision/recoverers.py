"""Recovery methods with an explicit training protocol and information source."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from stream_recoverability.experiments.air2stream_equivalent import (
    fit_air2stream8,
    simulate_air2stream8,
)
from stream_recoverability.experiments.development_recovery import (
    XGBOOST_PARAMETERS,
    _climatology_prediction,
)
from stream_recoverability.experiments.wrr_revision.features import (
    MIN_BLOCK_TRAIN_ROWS,
    attach_gap_boundary,
    long_block_training_table,
    neighbor_training_table,
    sample_training_blocks,
)
from stream_recoverability.models.baselines import ClimatologyBaseline

RIDGE_MIN_ROWS = 40


@dataclass
class FittedRecoverer:
    name: str
    family: str
    training_protocol: str
    uses_boundary: bool
    uses_donors: bool
    uses_air: bool
    uses_flow: bool
    information_group: str
    n_train_rows: int
    extra: dict[str, object]

    def predict_gap(
        self,
        *,
        features: pd.DataFrame,
        target: pd.Series,
        start: int,
        gap_length: int,
        air: pd.Series | None = None,
        discharge: pd.Series | None = None,
    ) -> np.ndarray:
        raise NotImplementedError


class ConstantRecoverer(FittedRecoverer):
    def predict_gap(
        self,
        *,
        features: pd.DataFrame,
        target: pd.Series,
        start: int,
        gap_length: int,
        air: pd.Series | None = None,
        discharge: pd.Series | None = None,
    ) -> np.ndarray:
        values = np.asarray(self.extra["values"], dtype=float)
        return values[int(start) : int(start) + int(gap_length)]


class LinearInterpRecoverer(FittedRecoverer):
    def predict_gap(
        self,
        *,
        features: pd.DataFrame,
        target: pd.Series,
        start: int,
        gap_length: int,
        air: pd.Series | None = None,
        discharge: pd.Series | None = None,
    ) -> np.ndarray:
        from stream_recoverability.experiments.wrr_revision.features import (
            gap_interpolated_boundary,
        )

        return gap_interpolated_boundary(target, start, gap_length)


class SklearnRecoverer(FittedRecoverer):
    def predict_gap(
        self,
        *,
        features: pd.DataFrame,
        target: pd.Series,
        start: int,
        gap_length: int,
        air: pd.Series | None = None,
        discharge: pd.Series | None = None,
    ) -> np.ndarray:
        if self.uses_boundary:
            frame = attach_gap_boundary(features, target, start, gap_length)
        else:
            frame = features.iloc[int(start) : int(start) + int(gap_length)].copy()
        columns = list(self.extra["columns"])
        frame = frame.reindex(columns=columns)
        return np.asarray(self.extra["model"].predict(frame), dtype=float)


class Air2StreamRecoverer(FittedRecoverer):
    def predict_gap(
        self,
        *,
        features: pd.DataFrame,
        target: pd.Series,
        start: int,
        gap_length: int,
        air: pd.Series | None = None,
        discharge: pd.Series | None = None,
    ) -> np.ndarray:
        if air is None or discharge is None:
            return np.full(int(gap_length), np.nan)
        simulated = np.asarray(self.extra["simulated"], dtype=float)
        return simulated[int(start) : int(start) + int(gap_length)]


def _ridge() -> object:
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


def _xgboost(parameters: Mapping[str, object] | None = None) -> XGBRegressor:
    return XGBRegressor(**dict(parameters or XGBOOST_PARAMETERS))


def _fit_sklearn(
    name: str,
    family: str,
    training_protocol: str,
    *,
    x: pd.DataFrame,
    y: pd.Series,
    uses_boundary: bool,
    uses_donors: bool,
    uses_air: bool,
    uses_flow: bool,
    information_group: str,
    xgboost: bool,
    parameters: Mapping[str, object] | None = None,
) -> FittedRecoverer | None:
    if len(x) < (RIDGE_MIN_ROWS if not xgboost else 80):
        return None
    model = _xgboost(parameters) if xgboost else _ridge()
    model.fit(x, y.to_numpy(dtype=float))
    return SklearnRecoverer(
        name=name,
        family=family,
        training_protocol=training_protocol,
        uses_boundary=uses_boundary,
        uses_donors=uses_donors,
        uses_air=uses_air,
        uses_flow=uses_flow,
        information_group=information_group,
        n_train_rows=int(len(x)),
        extra={"model": model, "columns": tuple(x.columns)},
    )


def _climatology_values(target: pd.Series, train_mask: pd.Series, *, window: int) -> np.ndarray:
    if window <= 0:
        return _climatology_prediction(target, train_mask, target.index)
    data = target.to_frame(name="target")
    data["date"] = target.index
    model = ClimatologyBaseline(target_col="target", window=int(window), date_col="date")
    model.fit(data, "target", train_mask=train_mask)
    return model.predict(data).to_numpy(dtype=float)


def fit_station_recoverers(
    panel: pd.DataFrame,
    *,
    target_station: str,
    donors: Sequence[str],
    train_mask: pd.Series,
    features: pd.DataFrame,
    air: pd.Series | None = None,
    discharge: pd.Series | None = None,
    xgboost_parameters: Mapping[str, object] | None = None,
    include_external: bool = True,
    include_names: Sequence[str] | None = None,
) -> dict[str, FittedRecoverer]:
    """Fit the same-information roster, plus external models when forcing exists."""

    target = pd.to_numeric(panel[target_station], errors="coerce")
    fitted: dict[str, FittedRecoverer] = {}
    doy = _climatology_values(target, train_mask, window=0)
    smooth = _climatology_values(target, train_mask, window=7)
    fitted["doy_climatology"] = ConstantRecoverer(
        name="doy_climatology",
        family="climatology",
        training_protocol="none",
        uses_boundary=False,
        uses_donors=False,
        uses_air=False,
        uses_flow=False,
        information_group="default",
        n_train_rows=int((train_mask & target.notna()).sum()),
        extra={"values": doy},
    )
    fitted["smooth_climatology"] = ConstantRecoverer(
        name="smooth_climatology",
        family="climatology",
        training_protocol="none",
        uses_boundary=False,
        uses_donors=False,
        uses_air=False,
        uses_flow=False,
        information_group="time_neighbor",
        n_train_rows=int((train_mask & target.notna()).sum()),
        extra={"values": smooth},
    )
    fitted["linear_interp"] = LinearInterpRecoverer(
        name="linear_interp",
        family="interpolator",
        training_protocol="none",
        uses_boundary=True,
        uses_donors=False,
        uses_air=False,
        uses_flow=False,
        information_group="time_neighbor",
        n_train_rows=0,
        extra={},
    )

    donor_features = features[
        [column for column in features.columns if column.startswith("doy_") or column.startswith("D__")]
    ]
    needs_blocks = any(
        (include_names is None or name in include_names) and not neighbor
        for name, neighbor, _ub, _ux, _g in (
            ("xgb_neighbor_boundary", True, True, True, "time_neighbor"),
            ("xgb_neighbor_noboundary", True, False, True, "donor"),
            ("xgb_longblock_boundary", False, True, True, "time_neighbor"),
            ("xgb_longblock_noboundary", False, False, True, "donor"),
            ("ridge_neighbor_boundary", True, True, False, "time_neighbor"),
            ("donor_only_ridge", True, False, False, "donor"),
        )
    )
    blocks = (
        sample_training_blocks(
            panel,
            target_station=target_station,
            donors=donors,
            train_mask=train_mask,
        )
        if needs_blocks
        else []
    )
    specs = (
        ("xgb_neighbor_boundary", True, True, True, "time_neighbor"),
        ("xgb_neighbor_noboundary", True, False, True, "donor"),
        ("xgb_longblock_boundary", False, True, True, "time_neighbor"),
        ("xgb_longblock_noboundary", False, False, True, "donor"),
        ("ridge_neighbor_boundary", True, True, False, "time_neighbor"),
        ("donor_only_ridge", True, False, False, "donor"),
    )
    for name, neighbor, use_boundary, use_xgb, group in specs:
        if include_names is not None and name not in include_names:
            continue
        has_donors = any(column.startswith("D__") for column in donor_features.columns)
        if not has_donors and not use_boundary:
            continue
        if neighbor:
            x, y = neighbor_training_table(
                donor_features,
                target,
                train_mask,
                include_boundary=use_boundary,
            )
            protocol = "neighbor"
        else:
            x, y = long_block_training_table(
                panel,
                donor_features,
                target_station=target_station,
                blocks=blocks,
                include_boundary=use_boundary,
            )
            protocol = "long_block"
            if len(x) < MIN_BLOCK_TRAIN_ROWS:
                continue
        model = _fit_sklearn(
            name,
            "xgboost" if use_xgb else "ridge",
            protocol,
            x=x,
            y=y,
            uses_boundary=use_boundary,
            uses_donors=has_donors,
            uses_air=False,
            uses_flow=False,
            information_group=group,
            xgboost=use_xgb,
            parameters=xgboost_parameters,
        )
        if model is not None:
            fitted[name] = model

    if include_external and air is not None:
        air_frame = features[[column for column in features.columns if column.startswith("doy_")]].copy()
        air_frame["M__Ta"] = pd.to_numeric(air, errors="coerce")
        x, y = neighbor_training_table(air_frame, target, train_mask, include_boundary=False)
        model = _fit_sklearn(
            "air_ridge",
            "ridge",
            "neighbor",
            x=x,
            y=y,
            uses_boundary=False,
            uses_donors=False,
            uses_air=True,
            uses_flow=False,
            information_group="external",
            xgboost=False,
        )
        if model is not None:
            fitted["air_ridge"] = model
        if discharge is not None:
            flow_frame = air_frame.copy()
            flow_frame["H__F"] = pd.to_numeric(discharge, errors="coerce")
            x, y = neighbor_training_table(flow_frame, target, train_mask, include_boundary=False)
            model = _fit_sklearn(
                "air_flow_ridge",
                "ridge",
                "neighbor",
                x=x,
                y=y,
                uses_boundary=False,
                uses_donors=False,
                uses_air=True,
                uses_flow=True,
                information_group="external",
                xgboost=False,
            )
            if model is not None:
                fitted["air_flow_ridge"] = model
            air2 = _fit_air2stream(target, train_mask, air, discharge)
            if air2 is not None:
                fitted["air2stream"] = air2
    return fitted


def _fit_air2stream(
    target: pd.Series,
    train_mask: pd.Series,
    air: pd.Series,
    discharge: pd.Series,
) -> FittedRecoverer | None:
    water = pd.to_numeric(target, errors="coerce").to_numpy(dtype=float)
    ta = pd.to_numeric(air, errors="coerce").reindex(target.index).to_numpy(dtype=float)
    q = pd.to_numeric(discharge, errors="coerce").reindex(target.index).to_numpy(dtype=float)
    fit_water = np.where(train_mask.to_numpy(dtype=bool), water, np.nan)
    if not (np.isfinite(ta).all() and np.isfinite(q).all() and np.isfinite(fit_water).sum() >= 800):
        return None
    q = np.maximum(q, 1e-3)
    try:
        fit = fit_air2stream8(
            target.index,
            fit_water,
            ta,
            q,
            minimum_training_observations=365,
            warmup_days=180,
            max_nfev=200,
        )
        initial = float(np.nanmean(fit_water[np.isfinite(fit_water)][:30]))
        simulated = simulate_air2stream8(
            target.index,
            ta,
            q,
            fit.parameters,
            initial_water_temperature_c=initial,
            discharge_reference=fit.discharge_reference,
        )
    except (ValueError, RuntimeError):
        return None
    return Air2StreamRecoverer(
        name="air2stream",
        family="process",
        training_protocol="state_equation",
        uses_boundary=False,
        uses_donors=False,
        uses_air=True,
        uses_flow=True,
        information_group="external",
        n_train_rows=int(np.isfinite(fit_water).sum()),
        extra={"simulated": simulated, "parameters": fit.parameters},
    )
