#!/usr/bin/env python3
"""TR-E2: fix target tolerances, populations, primary endpoints and the Australian test.

Tolerances use only complete-year truths of the opened archive (no
reconstruction error): each target's tolerance is the same fraction of its
median interannual standard deviation as 0.5 C is of H30's, with a 0.2 C
sensor floor for temperatures and a 1-day floor for the exceedance count.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e2_prereg"
FLOORS = {"h30": 0.0, "h7": 0.2, "annual_mean": 0.2, "c30": 0.2, "degree_days_jjas": 0.0, "days_above_20": 1.0}

PRIMARY = {
    "P1_E4_bias": {
        "population": "mech", "stratum": "air_ridge layer and true peak window at least half hidden",
        "quantity": "1 - |mean signed H30 error of D2*| / |mean signed H30 error of P0|",
        "success": "reduction >= 0.50 and 90% interval coverage of D2* within 0.85-0.95",
    },
    "P2_E5_retention": {
        "population": "deploy", "quantity": "retention of the target-aware rule minus the best current-practice rule at 5% realised risk",
        "success": ">= 10 percentage points with group-bootstrap lower 95% bound > 0",
    },
    "P3_E7_transfer": {
        "population": "mech + deploy, leave-one-region-out", "quantity": "share of held-out regions with realised admitted risk <= 7% at nominal 5% under information-layer calibration",
        "success": ">= 0.80 and median realised risk <= 0.05; sealed Australia realised risk <= 0.07",
    },
    "P4_E8_trend": {
        "population": "long-record stations, realistic and state-dependent degradation",
        "quantity": "station H30 trend RMSE of target-aware multiple imputation (C) relative to dropping incomplete years (A1), and 95% interval coverage of C",
        "success": "RMSE reduction >= 0.20 versus A1, |bias| no larger than A1 + 0.01 C/decade, coverage of C in 0.90-0.97",
    },
}

GATES = {
    "A": "missingness linked to hot or low-flow states (odds ratio >= 1.2 per SD); failed -> narrative is plug-in bias and wasted records, MNAR kept as a stress test",
    "B": "P1 succeeds; failed -> paper on the limits of recovery quantified by the recovery law",
    "C": "P2 succeeds; failed -> short note that warm-season completeness rules are near the frontier",
    "D": "P3 succeeds; failed -> report the predictive distribution of new-region risk and the local calibration need",
}


def tolerances() -> dict:
    daily = pd.read_parquet(T.SCRATCH / "archive_daily.parquet", columns=["station_key", "date", "water_c"])
    daily["station_key"] = daily.station_key.astype(str)
    rows = []
    for station, block in daily.groupby("station_key"):
        series = block.set_index("date").water_c.astype(float)
        for year, values in series.groupby(series.index.year):
            expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
            if len(values) == expected and values.notna().all():
                stats = T.target_statistics(values.to_numpy(), values.index, T.settings()["exceedance_threshold_c"])
                rows.append({"station_key": station, "year": int(year), **stats})
    frame = pd.DataFrame(rows)
    counts = frame.groupby("station_key").size()
    frame = frame.loc[frame.station_key.isin(counts.index[counts >= 4])]
    sd = frame.groupby("station_key")[[name for name in T.TARGETS if name != "peak_doy"]].std(ddof=1).median()
    scale = 0.5 / sd["h30"]
    tolerance = {name: float(max(FLOORS[name], scale * sd[name])) for name in sd.index}
    tolerance["h30"] = 0.5
    tolerance["peak_doy"] = 7.0
    return {"median_interannual_sd": sd.to_dict(), "tolerance": tolerance, "n_stations": int(frame.station_key.nunique()), "n_station_years": len(frame)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tolerance = tolerances()
    T.write_json(OUT / "target_tolerances.json", tolerance)
    prereg = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "document": "docs/reviews/wrr_target_recovery_20261021/PREREGISTRATION_ZH.md",
        "populations": {"mech": "crossed 30/60/90-day gaps x none/partial/full climatological peak overlap", "deploy": "real incomplete calendars of the same provider, runs jittered <= 15 d, provider mix of the real archive", "mnar1/mnar2/mnar_upper": "deploy x exact onset importance weights at the fitted, doubled and upper-95% E1 effect"},
        "independent_unit": "independence group (record-connected networks); transfer unit: region (agency, or USGS HUC2)",
        "primary_target": "h30", "tolerance": tolerance["tolerance"], "risk_levels": T.settings()["risk_levels"],
        "primary_endpoints": PRIMARY, "multiplicity": "Holm over the four primary endpoints; everything else exploratory",
        "estimator_selection": "D2* = lowest mean quantile CRPS among P3, P3raw, P5a, P5b on source leave-one-region-out predictions; frozen before the Australian test",
        "sealed_test": {"region": "Australia (BoM qualified daily series)", "roster": "results/wrr_target_recovery_20261021/e7_sealed/au_roster.csv", "evaluated_with": "results/wrr_target_recovery_20261021/e2_prereg/frozen/pipeline.json"},
        "gates": GATES, "sensitivity": {"tolerance_c": T.settings()["tolerance_sensitivity_c"], "risk_levels": T.settings()["risk_levels"], "mnar_multipliers": T.settings()["mnar_strength_multipliers"]},
    }
    T.write_json(OUT / "prereg.json", prereg)
    print(tolerance, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
