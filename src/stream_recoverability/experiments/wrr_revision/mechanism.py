"""Generative systems that can refute a universal recoverability threshold."""

from __future__ import annotations


import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from stream_recoverability.experiments.wrr_revision.features import (
    attach_gap_boundary,
    base_feature_frame,
    long_block_training_table,
    neighbor_training_table,
    sample_training_blocks,
)
from stream_recoverability.experiments.wrr_revision.paths import GAP_GRID
from stream_recoverability.experiments.wrr_revision.thermal import daily_mae

SCENARIOS: dict[str, dict[str, float | str]] = {
    "high_memory_weak_donor": {
        "rho": 0.92,
        "beta_donor": 0.05,
        "beta_air": 0.0,
        "season_amp": 7.0,
        "donor_noise": 1.5,
        "expect_cross_neighbor": 1.0,
        "expect_cross_struct": 0.0,
        "notes": "Memory-dominated; a well-specified two-sided AR interpolator should not fail like a mismatched neighbor-trained model.",
    },
    "low_memory_strong_donor": {
        "rho": 0.05,
        "beta_donor": 0.85,
        "beta_air": 0.0,
        "season_amp": 6.0,
        "donor_noise": 0.25,
        "expect_cross_neighbor": 0.0,
        "expect_cross_struct": 0.0,
        "notes": "Donor remains informative at long gaps; no crossing should appear for donor models.",
    },
    "air_driven": {
        "rho": 0.2,
        "beta_donor": 0.05,
        "beta_air": 0.8,
        "season_amp": 5.0,
        "donor_noise": 1.2,
        "expect_cross_neighbor": 1.0,
        "expect_cross_struct": 0.0,
        "notes": "Air-driven truth; structurally correct air regression should stay above climatology.",
    },
    "no_information_loss": {
        "rho": 0.0,
        "beta_donor": 0.0,
        "beta_air": 0.0,
        "season_amp": 10.0,
        "donor_noise": 2.0,
        "expect_cross_neighbor": 0.0,
        "expect_cross_struct": 0.0,
        "notes": "Pure season plus noise; climatology is essentially optimal and a nested seasonal model must not cross.",
    },
}


def simulate_system(
    name: str,
    *,
    n_days: int = 365 * 8,
    seed: int = 0,
) -> pd.DataFrame:
    cfg = SCENARIOS[name]
    rng = np.random.default_rng(int(seed))
    index = pd.date_range("2000-01-01", periods=int(n_days), freq="D")
    phase = 2.0 * np.pi * (index.dayofyear.to_numpy(dtype=float) - 1.0) / 365.25
    season = float(cfg["season_amp"]) * np.sin(phase)
    air = season + rng.normal(0.0, 1.0, size=n_days)
    residual = np.zeros(n_days)
    for t in range(1, n_days):
        residual[t] = float(cfg["rho"]) * residual[t - 1] + rng.normal(0.0, 0.7)
    target = season + residual + float(cfg["beta_air"]) * (air - season)
    donor = (
        float(cfg["beta_donor"]) * target
        + (1.0 - float(cfg["beta_donor"])) * season
        + rng.normal(0.0, float(cfg["donor_noise"]), size=n_days)
    )
    return pd.DataFrame(
        {"target": target, "donor_a": donor, "Ta": air},
        index=index,
    )


def _climatology(train: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    tmp = pd.DataFrame({"doy": train.index.dayofyear, "value": train.to_numpy(dtype=float)})
    means = tmp.groupby("doy")["value"].median()
    fallback = float(tmp["value"].median())
    return means.reindex(index.dayofyear).fillna(fallback).to_numpy(dtype=float)


def ar1_bridge(left_resid: float, right_resid: float, length: int, rho: float) -> np.ndarray:
    """Conditional mean of a zero-mean AR(1) given both gap boundaries."""

    t = np.arange(1, int(length) + 1, dtype=float)
    span = float(length) + 1.0
    rho = float(np.clip(rho, -0.999, 0.999))
    denom = 1.0 - rho ** (2.0 * span)
    if abs(denom) < 1e-12:
        w_right = t / span
        return (1.0 - w_right) * left_resid + w_right * right_resid
    left_w = (rho ** t) * (1.0 - rho ** (2.0 * (span - t))) / denom
    right_w = (rho ** (span - t)) * (1.0 - rho ** (2.0 * t)) / denom
    return left_w * float(left_resid) + right_w * float(right_resid)


def _season(index: pd.DatetimeIndex, amp: float) -> np.ndarray:
    phase = 2.0 * np.pi * (index.dayofyear.to_numpy(dtype=float) - 1.0) / 365.25
    return float(amp) * np.sin(phase)


def _structurally_correct(name: str, panel: pd.DataFrame, train_mask: pd.Series):
    y = panel["target"]
    if name == "air_driven":
        x = np.column_stack(
            [
                np.sin(2 * np.pi * panel.index.dayofyear / 365.25),
                np.cos(2 * np.pi * panel.index.dayofyear / 365.25),
                panel["Ta"].to_numpy(dtype=float),
            ]
        )
    elif name == "low_memory_strong_donor":
        x = np.column_stack(
            [
                np.sin(2 * np.pi * panel.index.dayofyear / 365.25),
                np.cos(2 * np.pi * panel.index.dayofyear / 365.25),
                panel["donor_a"].to_numpy(dtype=float),
            ]
        )
    elif name == "no_information_loss":
        x = np.column_stack(
            [
                np.sin(2 * np.pi * panel.index.dayofyear / 365.25),
                np.cos(2 * np.pi * panel.index.dayofyear / 365.25),
            ]
        )
    else:
        return "ar1_bridge"
    model = Ridge(alpha=0.1)
    ok = train_mask.to_numpy(dtype=bool) & np.isfinite(y.to_numpy(dtype=float))
    model.fit(x[ok], y.to_numpy(dtype=float)[ok])
    return model, x


def score_scenario(name: str, *, seed: int = 0) -> pd.DataFrame:
    panel = simulate_system(name, seed=seed)
    train_mask = pd.Series(panel.index.year < 2006, index=panel.index)
    features = base_feature_frame(panel, donors=("donor_a",), air=panel["Ta"])
    donor_features = features[[c for c in features.columns if c.startswith("doy_") or c.startswith("D__")]]
    x_nb, y_nb = neighbor_training_table(
        donor_features, panel["target"], train_mask, include_boundary=True
    )
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    neighbor_model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    neighbor_model.fit(x_nb, y_nb)
    blocks = sample_training_blocks(
        panel,
        target_station="target",
        donors=("donor_a",),
        train_mask=train_mask,
        gap_lengths=(7, 30, 90, 180),
        blocks_per_length=12,
    )
    x_lb, y_lb = long_block_training_table(
        panel,
        donor_features,
        target_station="target",
        blocks=blocks,
        include_boundary=True,
    )
    long_model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if len(x_lb) >= 80:
        long_model.fit(x_lb, y_lb)
        has_long = True
    else:
        has_long = False
    climate = _climatology(panel.loc[train_mask, "target"], panel.index)
    struct = _structurally_correct(name, panel, train_mask)
    eval_mask = ~train_mask
    rows: list[dict[str, object]] = []
    empty = pd.DataFrame(index=panel.index)
    from stream_recoverability.experiments.development_recovery import (
        _boundary_values,
        _candidate_starts,
        select_placements,
    )

    for gap in GAP_GRID:
        starts = _candidate_starts(
            panel,
            empty,
            target_station="target",
            donors=("donor_a",),
            meteorology=(),
            hydraulics=(),
            evaluation_mask=eval_mask,
            gap_length=int(gap),
        )
        for start in select_placements(starts, count=8):
            truth = panel["target"].iloc[int(start) : int(start) + int(gap)].to_numpy(dtype=float)
            clim = climate[int(start) : int(start) + int(gap)]
            nb_frame = attach_gap_boundary(donor_features, panel["target"], int(start), int(gap))
            neighbor_hat = neighbor_model.predict(nb_frame)
            long_hat = long_model.predict(nb_frame) if has_long else np.full(int(gap), np.nan)
            interp = _boundary_values(panel["target"], int(start), int(gap))
            if struct == "ar1_bridge":
                rho = float(SCENARIOS[name]["rho"])
                amp = float(SCENARIOS[name]["season_amp"])
                season = _season(panel.index, amp)
                left = float(panel["target"].iloc[int(start) - 1] - season[int(start) - 1])
                right = float(
                    panel["target"].iloc[int(start) + int(gap)] - season[int(start) + int(gap)]
                )
                resid = ar1_bridge(left, right, int(gap), rho)
                struct_hat = resid + season[int(start) : int(start) + int(gap)]
            elif struct == "linear_interp":
                struct_hat = interp
            else:
                model, x = struct
                struct_hat = model.predict(x[int(start) : int(start) + int(gap)])
            for recoverer, hat in (
                ("neighbor_ridge", neighbor_hat),
                ("longblock_ridge", long_hat),
                ("linear_interp", interp),
                ("structurally_correct", struct_hat),
                ("climatology", clim),
            ):
                mae = daily_mae(truth, hat)
                clim_mae = daily_mae(truth, clim)
                rows.append(
                    {
                        "scenario": name,
                        "gap_length": int(gap),
                        "recoverer": recoverer,
                        "mae_deg_c": mae,
                        "climatology_mae_deg_c": clim_mae,
                        "mae_benefit": clim_mae - mae,
                        "expect_cross_neighbor": float(SCENARIOS[name]["expect_cross_neighbor"]),
                        "expect_cross_struct": float(SCENARIOS[name]["expect_cross_struct"]),
                    }
                )
    return pd.DataFrame(rows)


def scenario_verdict(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario, group in scores.groupby("scenario"):
        for recoverer in ("neighbor_ridge", "longblock_ridge", "structurally_correct"):
            means = group.loc[group["recoverer"].eq(recoverer)].groupby("gap_length")["mae_benefit"].mean()
            crossed = bool((means <= 0).any()) if len(means) else False
            expect = float(group[f"expect_cross_{'neighbor' if recoverer == 'neighbor_ridge' else 'struct'}"].iloc[0])
            if recoverer == "longblock_ridge":
                expect = float("nan")
            rows.append(
                {
                    "scenario": scenario,
                    "recoverer": recoverer,
                    "crossed": crossed,
                    "min_benefit": float(means.min()) if len(means) else float("nan"),
                    "expected_cross": expect,
                    "matches_predeclaration": (
                        bool(crossed) == bool(expect)
                        if recoverer != "longblock_ridge" and np.isfinite(expect)
                        else float("nan")
                    ),
                }
            )
    return pd.DataFrame(rows)
