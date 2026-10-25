#!/usr/bin/env python3
"""TR2-M1 check: what the hemisphere and season corrections change.

Source: round-1 and round-2 case tables are joined case by case. H30, the
plug-in and the masks should be identical for these Northern Hemisphere
stations; warm-season features, the recovery-law residual moments and the
degree-day target change where a station's five hottest months are not
May-September. Australia: the round-1 sealed cases (calendar years, May-September
seasons) against the round-2 development cases (July-June hot years, station
seasons): year-edge truncation, plug-in failure and bias, and the recovery
law's predicted failure rate (v2 and the peak-conditional v2p). Australia is
an opened development region in round 2; these are post hoc comparisons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e2_definition_check"
KEYS = ["station_key", "network_id", "year", "realization_id"]


def usable(cases: pd.DataFrame) -> pd.DataFrame:
    return cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna()]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tolerance = T.settings()["tolerance_c"]
    columns = KEYS + ["eval_truth_h30", "h30__policy", "mask_runs", "warm_observed_fraction", "law_sigma_r_warm", "law_mu_r_warm", "peak_overlap", "policy_choice"]
    first = pd.read_parquet(T.ROUND1 / "e2_cases/cases.parquet", columns=columns + ["eval_truth_degree_days_jjas"])
    second = pd.read_parquet(T.OUT / "e2_cases/cases.parquet", columns=columns + [f"eval_truth_{T.DEGREE_DAYS}", "warm_months", "dd_months"])
    joined = first.merge(second, on=KEYS, suffixes=("_r1", "_r2"), how="inner")
    rows = [
        {"quantity": "cases joined", "value": len(joined), "of": len(second)},
        {"quantity": "identical masks", "value": float((joined.mask_runs_r1 == joined.mask_runs_r2).mean())},
        {"quantity": "identical true H30", "value": float(np.isclose(joined.eval_truth_h30_r1, joined.eval_truth_h30_r2).mean())},
        {"quantity": "identical plug-in H30", "value": float(np.isclose(joined.h30__policy_r1, joined.h30__policy_r2, equal_nan=True).mean())},
        {"quantity": "identical layer", "value": float((joined.policy_choice_r1 == joined.policy_choice_r2).mean())},
        {"quantity": "stations whose warm season is not May-September", "value": int(second.loc[second.warm_months != "5;6;7;8;9", "station_key"].nunique()), "of": int(second.station_key.nunique())},
        {"quantity": "cases with a changed warm-season observed fraction", "value": float((~np.isclose(joined.warm_observed_fraction_r1, joined.warm_observed_fraction_r2)).mean())},
        {"quantity": "mean absolute change of warm-season observed fraction", "value": float((joined.warm_observed_fraction_r1 - joined.warm_observed_fraction_r2).abs().mean())},
        {"quantity": "median relative change of warm-season residual sd", "value": float(((joined.law_sigma_r_warm_r2 - joined.law_sigma_r_warm_r1) / joined.law_sigma_r_warm_r1).median())},
        {"quantity": "stations whose degree-day months are not June-September", "value": int(second.loc[second.dd_months != "6;7;8;9", "station_key"].nunique()), "of": int(second.station_key.nunique())},
    ]
    source = pd.DataFrame(rows)
    source.to_csv(OUT / "source_differences.csv", index=False)

    au_rows = []
    for label, path in (("round 1 (calendar year, May-Sep)", T.AU_ROUND1 / "cases.parquet"), ("round 2 (July-June hot year, station seasons)", T.OUT / "e7_au_development/cases.parquet")):
        cases = usable(pd.read_parquet(path))
        years = cases.drop_duplicates(["station_key", "year"])
        edge = years.eval_truth_peak_doy.le(16) | years.eval_truth_peak_doy.ge(350)
        error = cases.h30__policy - cases.eval_truth_h30
        for family in ("calendar", "crossed"):
            selected = cases.design_family.eq(family)
            au_rows.append({
                "definition": label, "family": family, "n_cases": int(selected.sum()), "n_station_years": int(len(years)),
                "share_h30_window_at_year_edge": float(edge.mean()), "plug_in_failure": float((error[selected].abs() > tolerance).mean()),
                "plug_in_mean_error": float(error[selected].mean()),
                "plug_in_mean_error_peak_half_hidden": float(error[selected & cases.eval_true_peak_hidden_fraction.ge(0.5)].mean()),
            })
    australia = pd.DataFrame(au_rows)
    laws = {}
    for label, folder in (("round 1", T.ROUND1 / "e7_sealed"), ("round 2", T.OUT / "e7_au_development/law")):
        path = folder / "law_predictions.parquet" if label == "round 2" else None
        if path is not None and path.exists():
            frame = pd.read_parquet(path)
            laws[label] = frame
    if "round 2" in laws:
        frame = laws["round 2"]
        cases = usable(pd.read_parquet(T.OUT / "e7_au_development/cases.parquet"))
        cases = cases.loc[cases.state_h30_q50.notna()].reset_index(drop=True)
        observed = ((cases.h30__policy - cases.eval_truth_h30).abs() > tolerance).astype(float)
        for family in ("calendar", "crossed"):
            selected = cases.design_family.eq(family).to_numpy()
            for column in ("law_pfail_050", "law_v2p_pfail_050", "law_v3_pfail_050"):
                if column in frame:
                    australia.loc[(australia.definition.str.startswith("round 2")) & (australia.family == family), f"predicted_{column}"] = float(frame.loc[selected, column].mean())
            australia.loc[(australia.definition.str.startswith("round 2")) & (australia.family == family), "observed_failure_check"] = float(observed[selected].mean())
    australia.to_csv(OUT / "australia_before_after.csv", index=False)
    print(source.to_string(), flush=True)
    print(australia.round(4).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
