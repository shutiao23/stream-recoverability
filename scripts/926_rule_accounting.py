#!/usr/bin/env python3
"""Account for every eligible station-year under the compared completeness rules.

The output is descriptive.  A reported observed window is not the true H30 of an
incomplete year, and an accepted incomplete year can contain an unobserved
higher peak.  The script therefore compares reported windows and separately
marks the two witnesses whose window exceeds the rule-accepted record.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

RULES = T.ROOT / "results/wrr_review_response_20261027/rules"
OUT = T.ROOT / "results/wrr_adversarial_review_20261027/rule_accounting"
TOL = 5e-6

RULE_DEFINITIONS = {
    "complete_100": "complete_year",
    "annual_95": "observed_fraction >= 0.95",
    "warm_90_station_specific": "train_warm_fraction >= 0.90",
    "warm_90_fixed_original": "warm_observed_fraction >= 0.90",
    "july_aug_complete": "julaug_complete",
    "gap_le_49_days_context": "longest_run <= 49",
}


def rule_mask(frame: pd.DataFrame, rule: str) -> pd.Series:
    if rule == "complete_100":
        return frame.complete_year.fillna(False).astype(bool)
    if rule == "annual_95":
        return frame.observed_fraction.ge(0.95)
    if rule == "warm_90_station_specific":
        return frame.train_warm_fraction.ge(0.90)
    if rule == "warm_90_fixed_original":
        return frame.warm_observed_fraction.ge(0.90)
    if rule == "july_aug_complete":
        return frame.julaug_complete.fillna(False).astype(bool)
    if rule == "gap_le_49_days_context":
        return frame.longest_run.le(49)
    raise KeyError(rule)


def leave_one_out_record(frame: pd.DataFrame) -> pd.Series:
    """Maximum reported window among accepted years other than the current year."""
    accepted = frame.loc[frame.passes_rule & frame.reported_window.notna()]
    result = pd.Series(np.nan, index=frame.index, dtype=float)
    for station, block in accepted.groupby("station_key", sort=False):
        values = block.reported_window.to_numpy(float)
        years = block.year.to_numpy(int)
        if not len(values):
            continue
        order = np.argsort(values)
        for i, year in enumerate(frame.loc[frame.station_key.eq(station), "year"]):
            keep = years != year
            result.loc[frame.index[frame.station_key.eq(station)][i]] = (
                float(values[keep].max()) if keep.any() else np.nan
            )
    return result


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    years = pd.read_csv(RULES / "eligible_station_years.csv")
    years["reported_window"] = years.reported_window.astype(float)
    years["observed_lower_bound"] = years.observed_lower_bound.astype(float)
    summary_rows = []
    detail_parts = []
    increment_rows = []
    for rule in RULE_DEFINITIONS:
        frame = years.copy()
        frame["rule"] = rule
        frame["passes_rule"] = rule_mask(frame, rule)
        frame["complete"] = frame.complete_year.fillna(False).astype(bool)
        frame["has_bound"] = frame.observed_lower_bound.notna()
        frame["has_number"] = frame.complete & frame.truth_h30.notna()
        frame["state"] = np.select(
            [frame.has_number, frame.has_bound],
            ["number", "bound"],
            default="unknown",
        )
        frame["accepted_record_other_years"] = leave_one_out_record(frame)
        frame["new_window_fact"] = (
            frame.passes_rule
            & ~frame.complete
            & frame.has_bound
            & frame.observed_lower_bound.gt(
                frame.accepted_record_other_years + TOL
            )
        )
        frame["new_window_excess"] = np.where(
            frame.new_window_fact,
            frame.observed_lower_bound - frame.accepted_record_other_years,
            np.nan,
        )
        frame["excluded_window_fact"] = (
            ~frame.passes_rule
            & ~frame.complete
            & frame.has_bound
            & frame.observed_lower_bound.gt(
                frame.accepted_record_other_years + TOL
            )
        )
        frame["excluded_window_excess"] = np.where(
            frame.excluded_window_fact,
            frame.observed_lower_bound - frame.accepted_record_other_years,
            np.nan,
        )
        detail_parts.append(frame)

        admitted = frame.loc[frame.passes_rule]
        excluded = frame.loc[~frame.passes_rule]
        summary_rows.append(
            {
                "rule": rule,
                "definition": RULE_DEFINITIONS[rule],
                "eligible_station_years": len(frame),
                "eligible_stations": frame.station_key.nunique(),
                "eligible_groups": frame.independence_group.nunique(),
                "admitted": len(admitted),
                "admitted_complete_number": int(
                    admitted.state.eq("number").sum()
                ),
                "admitted_observed_bound": int(admitted.state.eq("bound").sum()),
                "admitted_unknown": int(admitted.state.eq("unknown").sum()),
                "excluded": len(excluded),
                "excluded_complete_number": int(
                    excluded.state.eq("number").sum()
                ),
                "excluded_observed_bound": int(excluded.state.eq("bound").sum()),
                "excluded_unknown": int(excluded.state.eq("unknown").sum()),
                "admitted_new_window_facts": int(frame.new_window_fact.sum()),
                "admitted_new_window_stations": int(
                    frame.loc[frame.new_window_fact, "station_key"].nunique()
                ),
                "excluded_new_window_facts": int(
                    frame.excluded_window_fact.sum()
                ),
                "excluded_new_window_stations": int(
                    frame.loc[frame.excluded_window_fact, "station_key"].nunique()
                ),
            }
        )
        for row in frame.loc[
            frame.new_window_fact | frame.excluded_window_fact
        ].itertuples(index=False):
            increment_rows.append(
                {
                    "rule": rule,
                    "station_key": row.station_key,
                    "year": int(row.year),
                    "provider": row.provider,
                    "region": row.provider,
                    "independence_group": row.independence_group,
                    "state": row.state,
                    "admitted": bool(row.passes_rule),
                    "observed_window": float(row.observed_lower_bound),
                    "accepted_record_other_years": float(
                        row.accepted_record_other_years
                    ),
                    "excess_over_accepted_record": float(
                        row.observed_lower_bound
                        - row.accepted_record_other_years
                    ),
                }
            )

    summary = pd.DataFrame(summary_rows)
    detail = pd.concat(detail_parts, ignore_index=True)
    increments = pd.DataFrame(increment_rows)
    summary.to_csv(OUT / "rule_accounting_summary.csv", index=False)
    increments.to_csv(OUT / "rule_accounting_increments.csv", index=False)
    detail.to_csv(OUT / "rule_accounting_cases.csv.gz", index=False, compression="gzip")

    # Measurement-margin sensitivity for the actually admitted new facts and for
    # the two excluded witnesses.  A window ordering is not resolved unless the
    # reported difference exceeds twice the assumed absolute error bound.
    margin_rows = []
    for margin in [0.0, 0.01, 0.05, 0.10, 0.20, 0.50]:
        for rule in RULE_DEFINITIONS:
            block = increments.loc[increments.rule.eq(rule)]
            for admitted, label in [(True, "admitted"), (False, "excluded")]:
                selected = block.loc[block.admitted.eq(admitted)]
                below = selected.loc[selected.excess_over_accepted_record.le(2 * margin + TOL)]
                margin_rows.append(
                    {
                        "assumed_absolute_error_c": margin,
                        "rule": rule,
                        "status": label,
                        "facts": len(selected),
                        "facts_resolved_above_2epsilon": len(selected) - len(below),
                        "facts_not_resolved": len(below),
                        "stations_resolved": selected.loc[
                            selected.excess_over_accepted_record.gt(2 * margin + TOL),
                            "station_key",
                        ].nunique(),
                    }
                )
    margins = pd.DataFrame(margin_rows)
    margins.to_csv(OUT / "rule_accounting_measurement_margins.csv", index=False)

    # The two excluded witnesses of the station-specific warm-season rule are
    # the only ones whose practical incremental value is at issue.
    warm = increments.loc[
        increments.rule.eq("warm_90_station_specific") & ~increments.admitted
    ].copy()
    warm = warm.sort_values("excess_over_accepted_record", ascending=False)
    warm.to_csv(OUT / "warm90_excluded_increments.csv", index=False)

    report = {
        "scope": "all eligible station-years under explicit completeness rules",
        "eligible_station_years": len(years),
        "eligible_stations": int(years.station_key.nunique()),
        "eligible_groups": int(years.independence_group.nunique()),
        "providers": years.provider.value_counts().to_dict(),
        "rules": RULE_DEFINITIONS,
        "tolerance_c": TOL,
        "warm90_excluded_increment_values_c": warm.excess_over_accepted_record.tolist(),
        "warm90_excluded_cases": warm[
            ["station_key", "year", "observed_window", "accepted_record_other_years"]
        ].to_dict("records"),
        "limits": [
            "reported windows are not true incomplete-year H30 values",
            "accepted incomplete years can contain an unobserved higher peak",
            "station-years are repeated masks only where noted; these are archive records, not independent climates",
            "measurement margins are assumptions, not sensor error estimates",
        ],
    }
    (OUT / "rule_accounting_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(summary.to_string(index=False), flush=True)
    print(warm.to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
