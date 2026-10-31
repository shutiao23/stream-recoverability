#!/usr/bin/env python3
"""Re-evaluate observation-only witnesses against explicit screening rules.

The station-specific five-month warm season is fitted without the evaluated
year, as in the reconstruction workflow. The accepted-record comparison uses
observed window maxima, so it describes reported values and does not identify
the true H30 of accepted incomplete years.
"""
from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.v17_fitness.estimators import StationModels

SOURCE = T.ROOT / "results/wrr_review_completion_20261024/observed_records"
OUT = T.ROOT / "results/wrr_review_response_20261027/rules"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    years = pd.read_parquet(T.E1 / "station_years.parquet")
    years = years.loc[
        ~years.edge_year & years.fully_active & years.year.between(1981, 2025)
    ].drop_duplicates(["station_key", "year"]).copy()
    complete = years.loc[years.complete_year & years.truth_h30.notna()]
    eligible = complete.groupby("station_key").size()
    eligible = eligible[eligible.ge(15)].index.tolist()
    years = years.loc[years.station_key.isin(eligible)].copy()
    daily = pd.read_parquet(
        T.SCRATCH / "archive_daily.parquet",
        columns=["station_key", "date", "water_c"],
        filters=[("station_key", "in", eligible)],
    )
    bounds = pd.read_csv(SOURCE / "all_incomplete_year_bounds.csv")
    years = years.merge(bounds[["station_key", "year", "observed_lower_bound"]],
                        on=["station_key", "year"], how="left", validate="one_to_one")
    years["reported_window"] = np.where(years.complete_year, years.truth_h30,
                                         years.observed_lower_bound)
    station_daily = {key: group.set_index("date").water_c.sort_index()
                     for key, group in daily.groupby("station_key", observed=True)}
    fractions, months = [], []
    for row in years.itertuples(index=False):
        target = station_daily[row.station_key]
        index = pd.date_range(f"{row.year}-01-01", f"{row.year}-12-31")
        train = pd.Series(target.index.year != row.year, index=target.index)
        model = StationModels(target=target, donors=pd.DataFrame(index=target.index),
                              air=None, train_mask=train)
        climate = model.smooth_climatology(index)
        if np.isfinite(climate).sum() < 30:
            fractions.append(np.nan)
            months.append("")
            continue
        warm = T.hottest_months(climate, index.dayofyear.to_numpy(), 5)
        active = index.month.isin(warm)
        values = target.reindex(index).to_numpy(float)
        fractions.append(float(np.isfinite(values[active]).mean()))
        months.append(";".join(map(str, warm)))
    years["train_warm_fraction"] = fractions
    years["train_warm_months"] = months
    rules = {
        "complete_100": years.complete_year,
        "annual_95": years.observed_fraction.ge(0.95),
        "warm_90_station_specific": years.train_warm_fraction.ge(0.90),
        "warm_90_fixed_original": years.warm_observed_fraction.ge(0.90),
        "july_aug_complete": years.julaug_complete.fillna(False),
        # Johnson's annual signal assessment is included as a descriptive
        # seven-week comparison, not a validated H30 record-handling rule.
        "gap_le_49_days_context": years.longest_run.le(49),
    }
    witnesses = pd.read_csv(SOURCE / "observed_record_certificates.csv")
    tagged = witnesses.merge(years, left_on=["station_key", "incomplete_year"],
                             right_on=["station_key", "year"], how="left",
                             validate="one_to_one", suffixes=("", "_archive"))
    rows, details = [], []
    for name, passes in rules.items():
        accepted = years.loc[passes & years.reported_window.notna()]
        maxima = accepted.groupby("station_key").reported_window.max()
        current = tagged.copy()
        lookup = pd.Series(passes.to_numpy(),
                           index=pd.MultiIndex.from_frame(years[["station_key", "year"]]))
        current["passes_rule"] = pd.MultiIndex.from_frame(
            current[["station_key", "year"]]
        ).map(lookup).to_numpy(dtype=bool)
        current["rule"] = name
        current["accepted_observed_record"] = current.station_key.map(maxima)
        current["excluded_exceeds_accepted_observed_record"] = (
            ~current.passes_rule & current.observed_window_mean.gt(
                current.accepted_observed_record + 5e-6
            )
        )
        rows.append(dict(rule=name, witness_years=len(current),
                         admitted_witness_years=int(current.passes_rule.sum()),
                         excluded_witness_years=int((~current.passes_rule).sum()),
                         admitted_witness_stations=int(current.loc[current.passes_rule, "station_key"].nunique()),
                         excluded_exceed_reported_record=int(current.excluded_exceeds_accepted_observed_record.sum()),
                         excluded_exceed_reported_record_stations=int(current.loc[current.excluded_exceeds_accepted_observed_record, "station_key"].nunique())))
        details.append(current)
    pd.DataFrame(rows).to_csv(OUT / "rule_summary.csv", index=False)
    pd.concat(details, ignore_index=True).to_csv(OUT / "witness_rules.csv", index=False)
    years.to_csv(OUT / "eligible_station_years.csv", index=False)
    sensitivity = []
    for threshold in [0, .01, .05, .1, .2, .5, 1.0]:
        above = witnesses.loc[witnesses.record_excess_lower_bound > max(threshold, 5e-6)]
        sensitivity.append(dict(combined_error_margin_c=threshold,
                                station_years=len(above), stations=above.station_key.nunique(),
                                independent_groups=above.group.nunique()))
    pd.DataFrame(sensitivity).to_csv(OUT / "measurement_margin_sensitivity.csv", index=False)
    (OUT / "design.json").write_text(json.dumps({
        "station_count": len(eligible), "witness_count": len(witnesses),
        "warm_definition": "five consecutive months from leave-target-year-out station climatology",
        "reference": "largest fully observed 30-day window among years passing each rule",
        "limits": ["screened incomplete years can have true H30 above their observed bound",
                   "July-August completion is a proxy, not the exact Beaufort procedure",
                   "49-day gap is a contextual Johnson annual-signal criterion, not an H30 rule",
                   "measurement margins are sensitivity assumptions, not quantified sensor errors"],
        "source_johnson": "https://doi.org/10.1016/j.ecolind.2020.107229",
        "source_beaufort": "https://doi.org/10.5194/hess-26-3477-2022"
    }, indent=2) + "\n")
    print(pd.DataFrame(rows).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
