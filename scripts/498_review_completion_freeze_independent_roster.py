#!/usr/bin/env python3
"""Write the metadata-selected cohort and ordinary local measurement plan."""

from __future__ import annotations
import json
from urllib.parse import quote
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed

STUDY = T.ROOT / "results/wrr_review_completion_20261024/independent_study"


def main():
    roster = pd.read_csv(STUDY / "greater_wellington/potential_roster.csv")
    water = T.load_script(
        "cohort_water",
        T.ROOT / "scripts/496_review_completion_independent_acquisition.py",
    )
    forcing = T.load_script(
        "cohort_forcing", T.ROOT / "scripts/497_review_completion_independent_cases.py"
    )
    path = STUDY / "acquisition_plan.json"
    plan = json.loads(path.read_text()) if path.exists() else {}
    roster["station_id"] = roster.site.map(lambda value: "gw_" + quote(value, safe=""))
    roster["station_key"] = "nz_gw|" + roster.station_id
    roster["independence_group"] = roster.conservative_group.map(
        lambda value: "nz_gw_zone_" + quote(value, safe="")
    )
    roster["network_id"] = roster.independence_group
    roster["provider"] = "nz_gw"
    roster = roster.sort_values("station_key")
    roster.to_csv(STUDY / "greater_wellington/cohort_roster.csv", index=False)
    plan.update(
        status="metadata_cohort_selected",
        provider="greater_wellington",
        endpoint=water.ENDPOINT,
        metadata_roster_file="greater_wellington/cohort_roster.csv",
        n_prospective_stations=len(roster),
        n_conservative_groups=int(roster.independence_group.nunique()),
        air_forcing=forcing.AIR_SPEC,
    )
    plan.setdefault("qc_specification", water.QC_SPEC)
    plan.setdefault("native_time_zone", "NZST fixed UTC+12")
    plan.setdefault("observation_end_exclusive", "2026-07-01T00:00:00")
    if "source_decision_hot_cutoff" not in plan:
        model = T.load_script(
            "cohort_source_roles", T.ROOT / "scripts/466_review_completion_refit.py"
        )
        c = pd.read_parquet(
            model.OUT / "cases/leave_one_year_out/seed_00.parquet",
            columns=[
                "region",
                "independence_group",
                "policy_choice",
                "eval_truth_h30",
                "air_warm_z_mean",
            ],
        )
        c = c.loc[
            c.policy_choice.ne("unavailable") & c.eval_truth_h30.notna()
        ].reset_index(drop=True)
        number = sorted(set(c.region.unique()) | {"global_source_candidate"}).index(
            "global_source_candidate"
        )
        _, _, weights = model.roles(
            c, "global_source_candidate", plain_seed(7, 0, number)
        )
        plan["source_decision_hot_cutoff"] = float(
            c.loc[weights["estimator"] > 0, "air_warm_z_mean"].quantile(0.9)
        )
    T.write_json(path, plan)
    print(
        f"{len(roster)} metadata-selected sites; observation quality is assessed after acquisition."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
