"""Calibrated adopt/reject rules. All-default is the required competitor."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def reliability_table(
    predicted: pd.Series,
    realized: pd.Series,
    *,
    n_bins: int = 10,
) -> pd.DataFrame:
    frame = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if frame.empty:
        return pd.DataFrame()
    try:
        frame["bin"] = pd.qcut(frame["predicted"], q=n_bins, duplicates="drop")
    except ValueError:
        frame["bin"] = pd.cut(frame["predicted"], bins=min(n_bins, max(2, frame["predicted"].nunique())))
    rows = []
    for bin_id, group in frame.groupby("bin", observed=True):
        rows.append(
            {
                "bin": str(bin_id),
                "n": int(len(group)),
                "predicted_mean": float(group["predicted"].mean()),
                "realized_mean": float(group["realized"].mean()),
                "positive_rate": float((group["realized"] > 0).mean()),
                "predicted_positive_rate": float((group["predicted"] > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def policy_metrics(
    realized_benefit: pd.Series,
    adopt: pd.Series,
    *,
    all_default_benefit: float = 0.0,
) -> dict[str, float]:
    realized = pd.to_numeric(realized_benefit, errors="coerce")
    action = adopt.astype(bool) & realized.notna()
    n = int(realized.notna().sum())
    if n == 0:
        return {
            "n": 0.0,
            "adopt_rate": float("nan"),
            "selected_mean_benefit": float("nan"),
            "harmful_rate_among_adopted": float("nan"),
            "net_benefit_all_cases": float("nan"),
            "beats_all_default": 0.0,
        }
    adopted = realized.loc[action]
    net = realized.where(action, 0.0).mean()
    return {
        "n": float(n),
        "adopt_rate": float(action.mean()),
        "n_adopted": float(action.sum()),
        "selected_mean_benefit": float(adopted.mean()) if len(adopted) else float("nan"),
        "harmful_rate_among_adopted": float((adopted < 0).mean()) if len(adopted) else float("nan"),
        "net_benefit_all_cases": float(net),
        "all_reconstruct_net": float(realized.mean()),
        "all_default_net": float(all_default_benefit),
        "beats_all_default": float(net > all_default_benefit),
        "severe_harm_rate": float((adopted < -1.0).mean()) if len(adopted) else float("nan"),
    }


def adopt_mean_threshold(
    predicted: pd.Series,
    *,
    tau: float = 0.0,
    supported: pd.Series | None = None,
) -> pd.Series:
    action = pd.to_numeric(predicted, errors="coerce") > float(tau)
    if supported is not None:
        action = action & supported.astype(bool)
    return action.fillna(False)


def cell_lower_quantile(
    history: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    benefit_col: str = "realized_benefit",
    q: float = 0.2,
) -> pd.Series:
    hist = history.copy()
    ev = evaluation.copy()
    for frame in (hist, ev):
        frame["network_id"] = frame["network_id"].astype(str)
        frame["station_id"] = frame["station_id"].astype(str)
        frame["gap_length"] = frame["gap_length"].astype(int)
    keys = ["network_id", "station_id", "gap_length", "season"]
    quantiles = hist.groupby(keys)[benefit_col].quantile(q).rename("lower_q")
    merged = ev.merge(quantiles, on=keys, how="left")
    fallback = hist.groupby(["network_id", "station_id", "gap_length"])[benefit_col].quantile(q)
    missing = merged["lower_q"].isna()
    if missing.any():
        idx = pd.MultiIndex.from_frame(merged.loc[missing, ["network_id", "station_id", "gap_length"]])
        merged.loc[missing, "lower_q"] = fallback.reindex(idx).to_numpy()
    return merged["lower_q"].reindex(ev.index)


def choose_tau(
    predicted: pd.Series,
    realized: pd.Series,
    *,
    supported: pd.Series | None = None,
    candidates: Sequence[float] | None = None,
) -> dict[str, float]:
    """Pick a threshold on historical validation to maximise net benefit vs all-default."""

    grid = (
        tuple(candidates)
        if candidates is not None
        else tuple(np.round(np.linspace(-1.0, 1.5, 26), 3))
    )
    best = {"tau": 0.0, "net_benefit_all_cases": -np.inf}
    for tau in grid:
        action = adopt_mean_threshold(predicted, tau=float(tau), supported=supported)
        metrics = policy_metrics(realized, action)
        if metrics["net_benefit_all_cases"] > best["net_benefit_all_cases"]:
            best = {"tau": float(tau), **metrics}
    return best


def evaluate_rules(
    evaluation: pd.DataFrame,
    *,
    predicted_col: str,
    realized_col: str = "realized_benefit",
    supported_col: str | None = None,
    tau: float = 0.0,
    quantile: pd.Series | None = None,
) -> pd.DataFrame:
    predicted = evaluation[predicted_col]
    realized = evaluation[realized_col]
    supported = evaluation[supported_col] if supported_col and supported_col in evaluation else None
    rows = []
    rules = {
        "all_default": pd.Series(False, index=evaluation.index),
        "all_reconstruct": pd.Series(True, index=evaluation.index),
        "mean_gt_tau": adopt_mean_threshold(predicted, tau=tau, supported=None),
        "mean_gt_tau_supported_only": adopt_mean_threshold(
            predicted, tau=tau, supported=supported
        ),
    }
    if quantile is not None:
        rules["conservative_quantile"] = (quantile > 0) & (
            supported.astype(bool) if supported is not None else True
        )
    for name, action in rules.items():
        metrics = policy_metrics(realized, action)
        metrics["rule"] = name
        metrics["predictor"] = predicted_col
        metrics["tau"] = float(tau)
        rows.append(metrics)
    return pd.DataFrame(rows)
