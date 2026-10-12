#!/usr/bin/env python3
"""F07 bridge: does "climatological peak window wholly hidden" mean the realised
annual peak was unobserved?

The manuscript's real-archive count (17 station-years under the Johnson
imputation limit) is computed from the *climatological* peak window, which is a
decision-time proxy: for a real incomplete year the realised peak is unknown by
construction. This script measures the proxy's misclassification rate on
populations where the realised peak IS known (designed cases on development,
reserved and the sealed never-used USGS networks) and transports that rate to
the real-archive count.

Writes results/wrr_submission_ready/amendments/peak_proxy_bridge/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = ROOT / "results" / "wrr_submission_ready" / "amendments" / "peak_proxy_bridge"
READY = ROOT / "results" / "wrr_submission_ready"
TRUE_HIDDEN = 1.0
PROXY_HIDDEN = 1.0


def load_populations() -> dict[str, pd.DataFrame]:
    populations = {
        "development_designed": pd.read_parquet(
            ROOT / "results/v17_fitness/step3_cases/cases.parquet"
        ),
        "reserved_designed": pd.read_parquet(
            ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet"
        ),
        "sealed_usgs_designed": pd.read_parquet(
            READY / "p0_07_sealed_confirmation/sealed_cases.parquet"
        ),
    }
    return populations


def bridge(frame: pd.DataFrame) -> dict:
    proxy = pd.to_numeric(frame["peak_overlap"], errors="coerce") >= PROXY_HIDDEN
    truth_hidden_fraction = pd.to_numeric(frame["true_peak_hidden_fraction"], errors="coerce")
    truth = truth_hidden_fraction >= TRUE_HIDDEN
    usable = proxy.notna() & truth_hidden_fraction.notna()
    proxy, truth = proxy[usable], truth[usable]

    tp = int((proxy & truth).sum())
    fp = int((proxy & ~truth).sum())
    fn = int((~proxy & truth).sum())
    tn = int((~proxy & ~truth).sum())
    sensitivity = tp / (tp + fn) if (tp + fn) else float("nan")
    ppv = tp / (tp + fp) if (tp + fp) else float("nan")
    npv = tn / (tn + fn) if (tn + fn) else float("nan")

    return {
        "n_cases": int(usable.sum()),
        "proxy_flagged": int(proxy.sum()),
        "truth_peak_hidden": int(truth.sum()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "sensitivity_proxy_given_true_hidden": sensitivity,
        "ppv_true_hidden_given_proxy": ppv,
        "npv_true_observed_given_proxy_clear": npv,
        "spearman_peak_overlap_vs_true_peak_hidden": float(
            pd.Series(proxy.astype(float)).corr(
                truth_hidden_fraction[usable].rank(), method="spearman"
            )
            if usable.sum() > 2
            else float("nan")
        ),
        "share_true_peak_hidden_when_proxy_clear": float(fn / (tn + fn)) if (tn + fn) else float("nan"),
    }


def clustered_ppv(frame: pd.DataFrame, draws: int = 1000, seed: int = 0) -> dict:
    """Network-clustered bootstrap of PPV = P(true peak hidden | proxy flag)."""

    proxy = pd.to_numeric(frame["peak_overlap"], errors="coerce") >= PROXY_HIDDEN
    truth = pd.to_numeric(frame["true_peak_hidden_fraction"], errors="coerce") >= TRUE_HIDDEN
    usable = proxy.notna() & pd.to_numeric(frame["true_peak_hidden_fraction"], errors="coerce").notna()
    work = frame.loc[usable, ["network_id"]].copy()
    work["proxy"] = proxy[usable].astype(bool)
    work["truth"] = truth[usable].astype(bool)
    flagged = work.loc[work["proxy"]]
    if flagged.empty:
        return {"point": float("nan"), "low": float("nan"), "high": float("nan")}
    networks = flagged["network_id"].astype(str).unique()
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(draws):
        picked = rng.choice(networks, size=len(networks), replace=True)
        sample = pd.concat([flagged.loc[flagged["network_id"].astype(str).eq(net)] for net in picked])
        if len(sample):
            values.append(float(sample["truth"].mean()))
    values = np.asarray(values, dtype=float)
    return {
        "point": float(flagged["truth"].mean()),
        "low": float(np.nanpercentile(values, 2.5)),
        "high": float(np.nanpercentile(values, 97.5)),
        "draws": int(draws),
        "n_networks_flagged": int(len(networks)),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    populations = load_populations()
    rows = []
    payload: dict[str, object] = {"proxy_rule": "climatological peak window wholly hidden (peak_overlap >= 1.0)"}
    for name, frame in populations.items():
        summary = bridge(frame)
        summary["population"] = name
        if name in ("reserved_designed", "sealed_usgs_designed"):
            summary["ppv_clustered"] = clustered_ppv(frame)
        rows.append(summary)
        payload[name] = summary

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "proxy_bridge_by_population.csv", index=False)

    # Transport the sealed-network PPV to the real-archive count of 17.
    consequence = pd.read_csv(ROOT / "results/v18_closure/e2_archive_deployment/archive_consequence.csv")
    johnson = consequence.loc[
        consequence["rule"].astype(str).str.contains("Johnson with imputation", na=False)
    ].iloc[0]
    admitted_flagged = int(johnson["admitted_with_peak_window_wholly_hidden"])
    sealed = payload["sealed_usgs_designed"]
    ppv = sealed["ppv_clustered"]
    expected = float(admitted_flagged) * float(ppv["point"])
    low = float(admitted_flagged) * float(ppv["low"])
    high = float(admitted_flagged) * float(ppv["high"])
    payload["real_archive_transport"] = {
        "rule": str(johnson["rule"]),
        "station_years_admitted": int(johnson["incomplete_years_admitted"]),
        "proxy_flagged_peak_wholly_hidden": admitted_flagged,
        "ppv_used": ppv,
        "expected_true_peak_hidden": expected,
        "expected_true_peak_hidden_ci": [low, high],
        "caveat": (
            "Real incomplete years have no truth by construction. This expectation transports the "
            "proxy's positive predictive value measured on sealed never-used designed cases; it is an "
            "estimate about proxy quality, not an observation of the real years."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
