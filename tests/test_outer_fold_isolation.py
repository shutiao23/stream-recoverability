"""Outer-fold calibration scores must not depend on that fold's labels."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.independence import (
    independence_table,
    shared_station_years_across_folds,
    shared_stations_across_folds,
)
from stream_recoverability.experiments.v17_fitness.paths import stable_seed

ROOT = Path(__file__).resolve().parents[1]


def _load_311():
    path = ROOT / "scripts" / "311_wrr_p0_02_frozen_risk_thresholds.py"
    spec = importlib.util.spec_from_file_location("p0_02_isolated", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_mean_model(module):
    def fit_predict_risk(train, test, features, target, *, seed):
        y = pd.to_numeric(train[target], errors="coerce").to_numpy(dtype=float)
        return np.full(len(test), float(np.nanmean(y)))

    def fit_risk_model(train, features, target, *, seed):
        y = pd.to_numeric(train[target], errors="coerce").to_numpy(dtype=float)
        return {"mean": float(np.nanmean(y))}

    def predict_risk(model, frame, features):
        return np.full(len(frame), float(model["mean"]))

    module.fit_predict_risk = fit_predict_risk
    module.fit_risk_model = fit_risk_model
    module.predict_risk = predict_risk


def _frame(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for group in range(10):
        for case in range(6):
            rows.append(
                {
                    "network_id": f"net{group}",
                    "independence_group": f"g{group:04d}",
                    "abserr_policy": float(rng.normal()),
                }
            )
    return pd.DataFrame(rows)


def test_held_out_labels_do_not_change_that_folds_threshold_inputs():
    module = _load_311()
    _patch_mean_model(module)
    frame = _frame()
    payload = {
        "panel": "synthetic",
        "fold_seed": 101,
        "target": "abserr_policy",
        "frame": frame,
        "features": (),
        "n_splits": 5,
        "n_inner_splits": 4,
    }
    original = module.crossfit_task(payload)
    units = frame["independence_group"].astype(str).to_numpy()
    folds = module.assign_folds(units, 5, 101)
    fold_ids = np.array([folds[unit] for unit in units], dtype=int)
    perturbed = frame.copy()
    perturbed.loc[fold_ids == 0, "abserr_policy"] += 1000.0
    payload["frame"] = perturbed
    changed = module.crossfit_task(payload)
    # Fold 0 calibration scores and fold 0 model are fit without fold 0 labels.
    np.testing.assert_allclose(
        original["cal_score_by_fold"][0], changed["cal_score_by_fold"][0], equal_nan=True
    )
    assert original["models"][0]["mean"] == changed["models"][0]["mean"]
    # The leakage the old shared array had: fold 0 labels move some other fold's
    # calibration scores, and therefore would move fold 0's threshold if those
    # scores were reused. They must move a fold that trains on fold 0.
    assert not np.allclose(
        original["cal_score_by_fold"][1], changed["cal_score_by_fold"][1], equal_nan=True
    )


def test_shared_stations_stay_in_one_fold():
    cases = pd.DataFrame(
        {
            "network_id": ["usgs_wave2_2070", "usgs_wave2_2070", "usgs_wave2_huc6_020700", "usgs_wave2_huc6_020700", "other"],
            "station_id": ["01610400", "01649500", "01610400", "01649500", "99999999"],
            "year": [2020, 2020, 2020, 2020, 2020],
        }
    )
    table = independence_table(cases)
    grouped = set(table.loc[table.network_id.isin(["usgs_wave2_2070", "usgs_wave2_huc6_020700"]), "independence_group"])
    assert len(grouped) == 1
    assert table.loc[table.network_id.eq("other"), "independence_group"].iloc[0] not in grouped

    def assign(units, n_splits, seed):
        ordered = sorted(set(map(str, units)))
        return {name: index % n_splits for index, name in enumerate(ordered)}

    from stream_recoverability.experiments.v17_fitness.independence import group_fold_map

    fold_of = group_fold_map(table, 5, stable_seed("t"), assign)
    assert fold_of["usgs_wave2_2070"] == fold_of["usgs_wave2_huc6_020700"]
    assert shared_stations_across_folds(cases, table, fold_of) == 0
    assert shared_station_years_across_folds(cases, fold_of) == 0
