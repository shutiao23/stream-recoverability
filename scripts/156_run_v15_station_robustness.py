#!/usr/bin/env python3
"""v15/W2.2: robustness of the station-level crossing analysis
(WORKPLAN_v15.md Step 2.2).

Three questions about `results/v14/p5_mechanism/station_crossings.csv`
(scripts/152, which kept only stations with b[0] > 0 and b[-1] < 0):

  A. Exclusions: how many stations were excluded, and where did they go
     (starts negative / never crosses by 365 d / other), plus how many
     *included* stations re-cross positive after their first negative (a
     multi-crossing curve) — the strict single-crossing subset is re-scored.
  B. Provider stratification: the crossing Spearman per provider, so the
     pooled result cannot be a single-provider artifact.
  C. Confounding: rank-based partial correlations of crossing day with the
     station's climatology MAE controlling for the station's signal
     amplitude and residual SD (P1 proxy_values.csv).

Outputs: results/v15/station_robustness/{station_classification.csv,
provider_strata.csv, partial_correlations.csv, README.md}

Run: PYTHONPATH=$PWD/src python3 scripts/156_run_v15_station_robustness.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/v15/station_robustness"
PANEL_LOSSES = {
    "first": ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv",
    "second": ROOT / "results/development_v11/second_confirmation/scoring/placement_losses.csv",
}
ROSTER = {
    "first": ROOT / "results/development_v11/route_a_confirmation/qualified_panel.csv",
    "second": ROOT / "results/development_v11/second_confirmation/frozen_scoring_roster_v2.csv",
}
PROXIES = ROOT / "results/v14/p1_baselines/proxy_values.csv"


def station_curves(panel: str) -> pd.DataFrame:
    p = pd.read_csv(
        PANEL_LOSSES[panel],
        usecols=["network_id", "station_id", "gap_length",
                 "mae_deg_c", "climatology_mae_deg_c"],
    )
    st = (
        p.groupby(["network_id", "station_id", "gap_length"])
        .agg(model=("mae_deg_c", "mean"), clim=("climatology_mae_deg_c", "mean"))
        .reset_index()
    )
    st["benefit"] = st.clim - st.model
    return st


def classify(st: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (net, sta), g in st.groupby(["network_id", "station_id"]):
        g = g.sort_values("gap_length")
        b = g.benefit.to_numpy(float)
        d = g.gap_length.to_numpy(float)
        clim_mae = float(g.clim.mean())
        n_pts = len(b)
        if b[0] <= 0:
            rows.append({"network_id": net, "station_id": sta,
                         "class": "excluded_starts_negative",
                         "crossing_days": np.nan, "n_pts": n_pts,
                         "station_clim_mae": clim_mae})
            continue
        if b[-1] >= 0:
            rows.append({"network_id": net, "station_id": sta,
                         "class": "excluded_never_crosses",
                         "crossing_days": np.nan, "n_pts": n_pts,
                         "station_clim_mae": clim_mae})
            continue
        neg = np.where(b < 0)[0]
        i = int(neg[0])
        x0, x1 = np.log10(d[i - 1]), np.log10(d[i])
        y0, y1 = b[i - 1], b[i]
        crossing = 10 ** (x0 + (x1 - x0) * y0 / (y0 - y1))
        multi = bool((b[i + 1:] >= 0).any()) if i + 1 < len(b) else False
        rows.append({"network_id": net, "station_id": sta,
                     "class": "included_multiple_crossings" if multi
                     else "included_single_crossing",
                     "crossing_days": crossing, "n_pts": n_pts,
                     "station_clim_mae": clim_mae})
    return pd.DataFrame(rows)


def rank_partial(a: np.ndarray, b: np.ndarray,
                 covars: np.ndarray) -> tuple[float, float]:
    """Spearman partial correlation of a and b given covars (regression on ranks)."""
    ra = rankdata(a)
    rb = rankdata(b)
    rc = np.column_stack([np.ones(len(a))] + [rankdata(c) for c in covars.T])
    res_a = ra - rc @ np.linalg.lstsq(rc, ra, rcond=None)[0]
    res_b = rb - rc @ np.linalg.lstsq(rc, rb, rcond=None)[0]
    r = spearmanr(res_a, res_b)
    return float(r.statistic), float(r.pvalue)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    proxies = pd.read_csv(PROXIES)
    class_rows, provider_rows, partial_rows = [], [], []
    for panel in ("first", "second"):
        st = station_curves(panel)
        roster = pd.read_csv(ROSTER[panel], usecols=["network_id", "provider"])
        st = st.merge(roster, on="network_id", how="left", validate="many_to_one")
        assert st["provider"].notna().all(), f"{panel}: missing provider"
        cl = classify(st)
        cl = cl.merge(
            roster.drop_duplicates("network_id"),
            on="network_id", how="left", validate="many_to_one",
        )
        assert cl["provider"].notna().all(), f"{panel}: missing provider"
        n_stations = len(cl)
        inc = cl.loc[cl["class"].str.startswith("included")].copy()

        # A. exclusions
        counts = cl["class"].value_counts().to_dict()
        for cls, cnt in counts.items():
            class_rows.append({"panel": panel, "class": cls, "n": cnt,
                               "share": cnt / n_stations})
        for subset, label in (
            (inc, "included_all"),
            (inc.loc[inc["class"] == "included_single_crossing"],
             "included_single_crossing"),
        ):
            if len(subset) > 3:
                r = spearmanr(subset["station_clim_mae"],
                              np.log10(subset["crossing_days"]))
                class_rows.append({"panel": panel, "class": f"spearman_{label}",
                                   "n": len(subset),
                                   "share": float(r.statistic),
                                   "p": float(r.pvalue)})

        # B. provider stratification
        for prov, g in inc.groupby("provider"):
            if len(g) > 3:
                r = spearmanr(g["station_clim_mae"],
                              np.log10(g["crossing_days"]))
                provider_rows.append({"panel": panel, "provider": prov,
                                      "n": len(g), "spearman": float(r.statistic),
                                      "p": float(r.pvalue)})
        # pooled comparison for the record
        r = spearmanr(inc["station_clim_mae"], np.log10(inc["crossing_days"]))
        provider_rows.append({"panel": panel, "provider": "pooled",
                              "n": len(inc), "spearman": float(r.statistic),
                              "p": float(r.pvalue)})

        # C. partial correlations with station covariates
        prx = proxies.loc[proxies["panel"] == panel].copy()
        inc2 = inc.merge(
            prx[["network_id", "station_id", "amplitude", "sd"]],
            on=["network_id", "station_id"], how="left",
        )
        with_cov = inc2.dropna(subset=["amplitude", "sd"]).copy()
        y = np.log10(with_cov["crossing_days"].to_numpy(float))
        x = with_cov["station_clim_mae"].to_numpy(float)
        for name, cov in (
            ("amplitude", with_cov["amplitude"].to_numpy(float)[:, None]),
            ("sd", with_cov["sd"].to_numpy(float)[:, None]),
            ("amplitude_and_sd", with_cov[["amplitude", "sd"]].to_numpy(float)),
        ):
            rho, p = rank_partial(x, y, cov)
            partial_rows.append({"panel": panel, "control": name,
                                 "n": len(with_cov), "spearman_partial": rho,
                                 "p": p})
        # zero-order on the covariate-complete subset for comparability
        rho0, p0 = spearmanr(x, y)
        partial_rows.append({"panel": panel, "control": "none_zero_order",
                             "n": len(with_cov), "spearman_partial": rho0,
                             "p": p0})

    classes = pd.DataFrame(class_rows)
    providers = pd.DataFrame(provider_rows)
    partials = pd.DataFrame(partial_rows)
    classes.to_csv(OUT / "station_classification.csv", index=False)
    providers.to_csv(OUT / "provider_strata.csv", index=False)
    partials.to_csv(OUT / "partial_correlations.csv", index=False)

    print("A. Station classification (counts and destinations)")
    print(classes.to_string(index=False), "\n")
    print("B. Provider stratification of the crossing Spearman")
    print(providers.round(3).to_string(index=False), "\n")
    print("C. Rank-based partial correlations (crossing vs clim MAE)")
    print(partials.round(3).to_string(index=False))
    print(f"\nWrote 3 CSVs to {OUT}")


if __name__ == "__main__":
    main()
