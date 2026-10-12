#!/usr/bin/env python3
"""Which rivers are hard? Catchment attribution of the screening problem.

The mechanism established elsewhere is about estimators and estimands and would
hold for any time series. This asks the hydrological question instead. Signs
are declared in `basins.EXPECTED_SIGNS` before the regressions are run, and the
headline test is the one the standing guidance already asserts: Johnson et al.
(2021) report that filling can harm groundwater-influenced sites.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from stream_recoverability.experiments.v17_fitness.basins import (  # noqa: E402
    EXPECTED_SIGNS,
    match_stations,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP1_PANEL,
    STEP4_CEILING,
    STEP6_SCREEN,
)

STEP21 = RESULTS_ROOT / "step21_hydrology"
RETENTION = 0.70
PREDICTORS = ["BFI_AVE", "CONTACT", "log_storage", "log_area", "ELEV_SITE_M", "SLOPE_PCT"]


def station_outcomes(cases: pd.DataFrame, certificates: pd.DataFrame | None) -> pd.DataFrame:
    """Per-station synchrony, difficulty and screening benefit."""

    frame = cases[["network_id", "station_id", "provider", "donor_corr_mean", "n_visible_donors"]].copy()
    frame["abserr_policy"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")
    frame["consequential"] = (frame["abserr_policy"] > PRIMARY_TOLERANCE_C).astype(float)
    frame["longest_run"] = pd.to_numeric(cases["longest_run"], errors="coerce")
    if certificates is not None:
        frame["cert_score"] = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
        frame["cert_error"] = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
    grouped = frame.groupby(["network_id", "station_id"], as_index=False).agg(
        provider=("provider", "first"),
        n_cases=("abserr_policy", "size"),
        donor_synchrony=("donor_corr_mean", "mean"),
        n_donors=("n_visible_donors", "mean"),
        mean_abs_error=("abserr_policy", "mean"),
        consequential_rate=("consequential", "mean"),
    )
    # The magnitude and interannual spread of the target itself. A damped
    # thermal regime is a smaller thing to get wrong, so these are needed to
    # separate "the donors are worse" from "the target is easier".
    truth = (
        cases.groupby(["network_id", "station_id", "year"])["truth_hottest30"].first().reset_index()
    )
    per_station = truth.groupby(["network_id", "station_id"])["truth_hottest30"].agg(
        peak_magnitude_c="mean", peak_interannual_sd_c="std"
    ).reset_index()
    grouped = grouped.merge(per_station, on=["network_id", "station_id"], how="left")
    if certificates is not None:
        rng = np.random.default_rng(57)
        frame["length_jitter"] = frame["longest_run"] + rng.random(len(frame))
        rows = []
        for (network_id, station_id), block in frame.groupby(["network_id", "station_id"]):
            block = block.dropna(subset=["cert_error", "abserr_policy"])
            if len(block) < 20:
                continue
            k = max(1, int(round(RETENTION * len(block))))
            cert = block.nsmallest(k, "cert_score")["cert_error"].to_numpy()
            length = block.nsmallest(k, "length_jitter")["abserr_policy"].to_numpy()
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "screening_gain_points": float(
                        ((length > PRIMARY_TOLERANCE_C).mean() - (cert > PRIMARY_TOLERANCE_C).mean()) * 100
                    ),
                }
            )
        if rows:
            grouped = grouped.merge(pd.DataFrame(rows), on=["network_id", "station_id"], how="left")
    return grouped


def correlations(panel: pd.DataFrame, target: str) -> pd.DataFrame:
    rows = []
    for name in PREDICTORS:
        block = panel[[name, target, "network_id"]].dropna()
        if len(block) < 30:
            continue
        rho, p_value = spearmanr(block[name], block[target])
        stat = cluster_bootstrap(
            block,
            lambda f, a=name, b=target: float(spearmanr(f[a], f[b]).statistic),
            draws=1500,
            seed=0,
        )
        rows.append(
            {
                "predictor": name,
                "target": target,
                "n_stations": int(len(block)),
                "spearman_rho": float(rho),
                "ci_low": stat["low"],
                "ci_high": stat["high"],
                "p_value": float(p_value),
                "excludes_zero": bool(stat["low"] * stat["high"] > 0),
                "expected_sign": EXPECTED_SIGNS.get(name, "none declared"),
            }
        )
    return pd.DataFrame(rows)


def multivariate(panel: pd.DataFrame, target: str) -> pd.DataFrame:
    block = panel[PREDICTORS + [target]].dropna()
    if len(block) < 40:
        return pd.DataFrame()
    X = StandardScaler().fit_transform(block[PREDICTORS])
    model = LinearRegression().fit(X, block[target])
    predicted = model.predict(X)
    r2 = float(1 - np.sum((block[target] - predicted) ** 2) / np.sum((block[target] - block[target].mean()) ** 2))
    return pd.DataFrame(
        [
            {"predictor": name, "standardised_coefficient": float(coef), "target": target, "r2": r2, "n": int(len(block))}
            for name, coef in zip(PREDICTORS, model.coef_)
        ]
    )


def by_stratum(panel: pd.DataFrame, column: str, labels=("low", "middle", "high")) -> pd.DataFrame:
    block = panel.dropna(subset=[column]).copy()
    block["stratum"] = pd.qcut(block[column], 3, labels=list(labels), duplicates="drop")
    aggregated = block.groupby("stratum", observed=True).agg(
        n_stations=("station_id", "size"),
        median_value=(column, "median"),
        donor_synchrony=("donor_synchrony", "mean"),
        mean_abs_error=("mean_abs_error", "mean"),
        consequential_rate=("consequential_rate", "mean"),
        peak_magnitude_c=("peak_magnitude_c", "mean"),
        peak_interannual_sd_c=("peak_interannual_sd_c", "mean"),
    )
    if "screening_gain_points" in block.columns:
        aggregated["screening_gain_points"] = block.groupby("stratum", observed=True)["screening_gain_points"].mean()
    return aggregated.reset_index().assign(variable=column)


def main() -> int:
    STEP21.mkdir(parents=True, exist_ok=True)
    roster = pd.read_csv(STEP1_PANEL / "station_roster.csv", dtype={"station_id": str})
    roster = roster.loc[roster["eligible_station"]]
    attributes = match_stations(roster)
    if attributes.empty:
        print("no GAGES-II matches; nothing to do")
        return 1

    development = pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True)
    dev_cert = pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet").reset_index(drop=True)
    reserved = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    res_cert = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)
    outcomes = pd.concat(
        [station_outcomes(development, dev_cert), station_outcomes(reserved, res_cert)], ignore_index=True
    )

    attributes["station_id"] = attributes["station_id"].astype(str)
    outcomes["station_id"] = outcomes["station_id"].astype(str)
    panel = outcomes.merge(
        attributes[["network_id", "station_id"] + PREDICTORS + ["CLASS", "AGGECOREGION", "HYDRO_DISTURB_INDX"]],
        on=["network_id", "station_id"],
        how="inner",
    )
    panel.to_csv(STEP21 / "station_panel.csv", index=False)

    correlation_frames = [
        correlations(panel, target)
        for target in ("donor_synchrony", "mean_abs_error", "consequential_rate", "peak_magnitude_c")
    ]
    if "screening_gain_points" in panel.columns:
        correlation_frames.append(correlations(panel.dropna(subset=["screening_gain_points"]), "screening_gain_points"))
    correlation_table = pd.concat([f for f in correlation_frames if not f.empty], ignore_index=True)
    correlation_table.to_csv(STEP21 / "correlations.csv", index=False)

    regression = pd.concat(
        [multivariate(panel, target) for target in ("donor_synchrony", "mean_abs_error")], ignore_index=True
    )
    regression.to_csv(STEP21 / "regression.csv", index=False)

    strata = pd.concat([by_stratum(panel, column) for column in ("BFI_AVE", "log_storage", "log_area")], ignore_index=True)
    strata.to_csv(STEP21 / "strata.csv", index=False)

    # The Johnson test, stated as a directional hypothesis before it was run.
    bfi = panel.dropna(subset=["BFI_AVE", "mean_abs_error"]).copy()
    bfi["high_bfi"] = bfi["BFI_AVE"] > bfi["BFI_AVE"].median()
    johnson = cluster_bootstrap(
        bfi,
        lambda f: float(
            f.loc[f["high_bfi"], "mean_abs_error"].mean() - f.loc[~f["high_bfi"], "mean_abs_error"].mean()
        ),
        draws=2000,
        seed=0,
    )
    reference = panel.dropna(subset=["CLASS", "mean_abs_error"])
    reference_test = cluster_bootstrap(
        reference,
        lambda f: float(
            f.loc[f["CLASS"].eq("Ref"), "mean_abs_error"].mean() - f.loc[f["CLASS"].eq("Non-ref"), "mean_abs_error"].mean()
        ),
        draws=2000,
        seed=0,
    )

    verdict = {
        "n_stations": int(len(panel)),
        "n_networks": int(panel["network_id"].nunique()),
        "johnson_groundwater_test": {
            "statement": "Johnson et al. (2021) report that filling can harm groundwater-influenced sites. Directional prediction: high baseflow index implies larger completed-year error.",
            "difference_high_minus_low_bfi_c": johnson["point"],
            "ci": [johnson["low"], johnson["high"]],
            "supported": bool(johnson["low"] > 0),
        },
        "reference_versus_disturbed": {
            "statement": "Directional prediction: reference basins are easier than disturbed ones.",
            "difference_ref_minus_nonref_c": reference_test["point"],
            "ci": [reference_test["low"], reference_test["high"]],
            "supported": bool(reference_test["high"] < 0),
        },
        "expected_signs": EXPECTED_SIGNS,
    }
    (STEP21 / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    lines = ["# Step 21 — which rivers are hard?", ""]
    lines.append(
        f"United States stations matched to GAGES-II basin characteristics: **{len(panel)}** stations "
        f"on **{panel['network_id'].nunique()}** networks. Signs were declared before the regressions were run."
    )
    lines.append("")
    lines.append("## Rank correlations, network-clustered intervals")
    lines.append("")
    lines.append(correlation_table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Standardised multivariate coefficients")
    lines.append("")
    lines.append(regression.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Outcomes by stratum")
    lines.append("")
    lines.append(strata.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Directional tests from the literature")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2))
    lines.append("```")
    (STEP21 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(correlation_table.round(4).to_string(index=False))
    print()
    print(strata.round(4).to_string(index=False))
    print()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
