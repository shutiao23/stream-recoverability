"""Network-level confirmation model and v9 locked success checks (E3)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from stream_recoverability.analysis.study_freeze import load_study_freeze


def network_blocked_spearman(
    frame: pd.DataFrame,
    *,
    predicted: str = "predicted_conditional_risk",
    observed: str = "observed_recovery_loss",
    network: str = "network_id",
) -> dict[str, float]:
    """Spearman correlation after averaging to the network.

    The extrapolation unit is the river network.  Mask placements are not
    independent samples.
    """

    grouped = frame.groupby(network, sort=False)[[predicted, observed]].mean()
    if len(grouped) < 3:
        return {
            "n_networks": float(len(grouped)),
            "spearman": float("nan"),
            "reason": "fewer_than_three_networks",
        }
    rho, _ = spearmanr(grouped[predicted], grouped[observed])
    return {
        "n_networks": float(len(grouped)),
        "spearman": float(rho),
        "reason": "",
    }


def network_bootstrap_spearman(
    frame: pd.DataFrame,
    *,
    predicted: str = "predicted_conditional_risk",
    observed: str = "observed_recovery_loss",
    network: str = "network_id",
    n_boot: int = 400,
    seed: int = 0,
) -> dict[str, float | str]:
    grouped = frame.groupby(network, sort=False)[[predicted, observed]].mean()
    networks = list(grouped.index)
    point = network_blocked_spearman(
        frame, predicted=predicted, observed=observed, network=network
    )
    if len(networks) < 5:
        return {
            **point,
            "ci_lower": float("nan"),
            "ci_upper": float("nan"),
            "inference_status": "withheld_insufficient_independent_clusters",
        }
    rng = np.random.default_rng(seed)
    draws = []
    values = grouped.to_numpy(dtype=float)
    for _ in range(n_boot):
        index = rng.integers(0, len(values), size=len(values))
        sample = values[index]
        if np.std(sample[:, 0]) == 0 or np.std(sample[:, 1]) == 0:
            continue
        rho, _ = spearmanr(sample[:, 0], sample[:, 1])
        if np.isfinite(rho):
            draws.append(float(rho))
    if len(draws) < 20:
        lower = upper = float("nan")
        status = "withheld_unstable_bootstrap"
    else:
        lower, upper = np.quantile(draws, [0.025, 0.975])
        status = "tested"
    return {
        **point,
        "ci_lower": float(lower),
        "ci_upper": float(upper),
        "inference_status": status,
    }


def leave_one_network_out_slopes(
    frame: pd.DataFrame,
    *,
    predicted: str = "predicted_conditional_risk",
    observed: str = "observed_recovery_loss",
    network: str = "network_id",
) -> pd.DataFrame:
    rows = []
    networks = list(pd.unique(frame[network]))
    for held in networks:
        train = frame.loc[~frame[network].eq(held)]
        x = train[predicted].to_numpy(dtype=float)
        y = train[observed].to_numpy(dtype=float)
        valid = np.isfinite(x) & np.isfinite(y)
        if int(valid.sum()) < 3 or float(np.var(x[valid])) == 0:
            slope = float("nan")
        else:
            design = np.column_stack([np.ones(int(valid.sum())), x[valid]])
            slope = float(np.linalg.lstsq(design, y[valid], rcond=None)[0][1])
        rows.append({"held_out_network": held, "slope": slope, "sign": np.sign(slope)})
    return pd.DataFrame(rows)


def jackknife_network_driver(
    frame: pd.DataFrame,
    *,
    predicted: str = "predicted_conditional_risk",
    observed: str = "observed_recovery_loss",
    network: str = "network_id",
) -> dict[str, float | str | bool]:
    """True if dropping one network flips the Spearman sign or nulls it."""

    full = network_blocked_spearman(
        frame, predicted=predicted, observed=observed, network=network
    )
    flips = []
    for held in pd.unique(frame[network]):
        subset = frame.loc[~frame[network].eq(held)]
        rho = network_blocked_spearman(
            subset, predicted=predicted, observed=observed, network=network
        )["spearman"]
        flips.append(
            {
                "held_out_network": held,
                "spearman": rho,
                "sign_flip": np.isfinite(full["spearman"])
                and np.isfinite(rho)
                and np.sign(rho) != np.sign(full["spearman"]),
            }
        )
    table = pd.DataFrame(flips)
    return {
        "full_spearman": full["spearman"],
        "n_sign_flips": float(table["sign_flip"].sum()) if not table.empty else 0.0,
        "single_network_drives": bool(table["sign_flip"].any()) if not table.empty else True,
        "worst_holdout_network": (
            str(table.loc[table["spearman"].abs().idxmin(), "held_out_network"])
            if not table.empty
            else ""
        ),
    }


def evaluate_success(
    frame: pd.DataFrame,
    *,
    predicted: str = "predicted_conditional_risk",
    observed: str = "observed_recovery_loss",
    network: str = "network_id",
    spearman_min: float | None = None,
    lower_bound_min: float | None = None,
    same_sign_majority: bool = True,
) -> dict[str, object]:
    """Apply the v9 locked confirmatory rule. Floors may only be raised."""

    freeze = load_study_freeze()
    locked = freeze.get("locked_success_criterion") or {}
    t2 = locked.get("t2_large_sample_primary") or {}
    locked_spearman = float(t2.get("out_of_network_spearman_min", 0.60))
    locked_lower = float(t2.get("network_bootstrap_lower_bound_min", 0.40))
    spearman_min = locked_spearman if spearman_min is None else max(float(spearman_min), locked_spearman)
    lower_bound_min = locked_lower if lower_bound_min is None else max(float(lower_bound_min), locked_lower)
    thresholds_locked = str(locked.get("status", "")).startswith("locked")

    spearman = network_bootstrap_spearman(
        frame, predicted=predicted, observed=observed, network=network
    )
    slopes = leave_one_network_out_slopes(
        frame, predicted=predicted, observed=observed, network=network
    )
    driver = jackknife_network_driver(
        frame, predicted=predicted, observed=observed, network=network
    )
    finite_slopes = slopes.loc[np.isfinite(slopes["slope"])]
    same_sign = (
        bool((finite_slopes["sign"] > 0).mean() > 0.5)
        if not finite_slopes.empty
        else False
    )
    numeric_floors_passed = bool(
        np.isfinite(spearman["spearman"])
        and spearman["spearman"] >= spearman_min
        and (
            spearman["inference_status"] != "tested"
            or (
                np.isfinite(spearman["ci_lower"])
                and spearman["ci_lower"] > lower_bound_min
            )
        )
        and (same_sign if same_sign_majority else True)
        and not driver["single_network_drives"]
    )
    n_networks = int(spearman.get("n_networks") or 0)
    n_min = int((locked.get("inference") or {}).get("n_networks_min", 100))
    confirmatory_eligible = n_networks >= n_min
    passed = bool(numeric_floors_passed and confirmatory_eligible)
    return {
        "passed": passed,
        "passed_numeric_floors": numeric_floors_passed,
        "confirmatory_eligible": confirmatory_eligible,
        "n_networks_min": n_min,
        "thresholds_locked": thresholds_locked,
        "spearman": spearman,
        "same_sign_majority": same_sign,
        "leave_one_network_out": slopes,
        "jackknife": driver,
    }


def simulate_confirmation_panel(
    n_networks: int = 8,
    stations_per_network: int = 4,
    *,
    slope: float = 1.0,
    noise: float = 0.15,
    seed: int = 0,
) -> pd.DataFrame:
    """Synthetic panel used to test the confirmation machinery, not a result."""

    rng = np.random.default_rng(seed)
    rows = []
    for network in range(n_networks):
        intercept = rng.normal(0.0, 0.05)
        for station in range(stations_per_network):
            risk = rng.uniform(0.2, 1.2)
            loss = intercept + slope * risk + rng.normal(0.0, noise)
            rows.append(
                {
                    "network_id": f"net{network}",
                    "station_id": f"s{station}",
                    "predicted_conditional_risk": risk,
                    "observed_recovery_loss": loss,
                }
            )
    return pd.DataFrame(rows)


__all__ = [
    "evaluate_success",
    "jackknife_network_driver",
    "leave_one_network_out_slopes",
    "network_blocked_spearman",
    "network_bootstrap_spearman",
    "simulate_confirmation_panel",
]
