"""Read-only scientific reanalysis of the existing v16 evidence.

Outputs are exploratory reviewer diagnostics, not new confirmation results.
No model is retrained and no original artifact is modified.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RES = ROOT / "results/wrr_revision"
QC = ROOT / "results/development_v11/confirmation_daily_qc/networks"
N_BOOT = 10000
SEED = 20260907
STRATEGIES = ["frozen_rule", "always_switch_gated", "always_donor_gated", "seasonal_le30"]


def main():
    inventory = pd.read_csv(RES / "step8_confirmation/network_inventory.csv")
    inv = inventory.loc[inventory.role.eq("held_out_confirmation_candidate") & inventory.eligible_years.eq(1)].copy()
    qc_rows = []
    for net in inv.network_id:
        q = pd.read_csv(QC / net / "network_qc_summary.csv")
        qc_rows.extend(q.to_dict("records"))
    qc = pd.DataFrame(qc_rows)
    qc.to_csv(OUT / "confirmation_original_qc.csv", index=False)
    reason_col = next(c for c in qc.columns if qc[c].astype(str).str.contains("non_river_domain_excluded").any())
    nonriver = set(qc.loc[qc[reason_col].astype(str).str.contains("non_river_domain_excluded"), "network_id"])

    mean_rows, comparison_rows, harm_rows, completeness_rows, overlap_rows = [], [], [], [], []
    summary = {"status": "exploratory_review_reanalysis", "bootstrap": "percentile, resample network IDs, equal network weights", "bootstrap_replicates": N_BOOT, "seed": SEED, "nonriver_ids_previously_excluded": sorted(nonriver)}
    panels = {}
    for label, folder in [("development", "step6_frozen_replay"), ("confirmation", "step8_frozen_replay")]:
        d = pd.read_csv(RES / folder / "station_year_replay.csv", dtype={"station_id": str})
        panels[label] = d
        for net, group in d.groupby("network_id"):
            raw = pd.read_csv(QC / net / "daily_wide_temperature.csv", parse_dates=["date"]).set_index("date").sort_index()
            for (station, year), cases in group.groupby(["station_id", "year"]):
                s = pd.to_numeric(raw[str(station)], errors="coerce").reindex(pd.date_range(f"{year}-01-01", f"{year}-12-31"))
                completeness_rows.append({"panel": label, "network_id": net, "station_id": station, "year": int(year), "n_cases": len(cases), "expected_days": len(s), "observed_days": int(s.notna().sum()), "missing_days": int(s.isna().sum()), "full_calendar_year": bool(s.notna().all()), "summer_missing_days": int(s.loc[s.index.month.isin([6, 7, 8])].isna().sum())})

        valid = d.dropna(subset=[s + "_hottest_30" for s in STRATEGIES])
        completeness = pd.DataFrame(completeness_rows)
        complete_keys = completeness.loc[completeness.panel.eq(label) & completeness.full_calendar_year, ["network_id", "station_id", "year"]]
        full_year = valid.merge(complete_keys, on=["network_id", "station_id", "year"], how="inner")
        summary[label] = {"n_cases": len(d), "n_finite_cases": len(valid), "n_network_ids": d.network_id.nunique(), "n_station_ids": d.station_id.nunique(), "unique_station_years": len(d[["network_id", "station_id", "year"]].drop_duplicates()), "n_nonriver_cases": int(d.network_id.isin(nonriver).sum()), "zero_donor_cases": int(d.n_donors.eq(0).sum())}
        subsets = {"all_existing_cases": valid, "mixed_patterns": valid.loc[valid.pattern.eq("mixed")], "full_calendar_truth_only": full_year}
        if label == "confirmation":
            subsets["excluding_previously_flagged_nonriver"] = valid.loc[~valid.network_id.isin(nonriver)]
            subsets["full_calendar_truth_excluding_flagged_nonriver"] = full_year.loc[~full_year.network_id.isin(nonriver)]
        for subset, frame in subsets.items():
            cols = [s + "_hottest_30" for s in STRATEGIES]
            net = frame.groupby("network_id")[cols].mean()
            rng = np.random.default_rng(SEED)
            draws = rng.integers(0, len(net), (N_BOOT, len(net)))
            for strategy, col in zip(STRATEGIES, cols):
                x = net[col].to_numpy()
                ci = np.quantile(x[draws].mean(axis=1), [.025, .975])
                mean_rows.append({"panel": label, "subset": subset, "strategy": strategy, "n_cases": len(frame), "n_network_ids": len(net), "case_mean": frame[col].mean(), "network_mean": x.mean(), "network_ci_low": ci[0], "network_ci_high": ci[1]})
                harm = frame[col].lt(-1e-10)
                harm_rows.append({"panel": label, "subset": subset, "strategy": strategy, "n_cases": len(frame), "harm_rate_all_cases": harm.mean(), "severe_harm_count_below_minus1C": int(frame[col].lt(-1.0).sum()), "q05_benefit": frame[col].quantile(.05), "mean_adopt_rate": frame[strategy + "_adopt_rate"].mean()})
            for comparator in STRATEGIES[1:]:
                diff = net.frozen_rule_hottest_30 - net[comparator + "_hottest_30"]
                ci = np.quantile(diff.to_numpy()[draws].mean(axis=1), [.025, .975])
                a = frame.frozen_rule_hottest_30.lt(-1e-10).astype(float)
                b = frame[comparator + "_hottest_30"].lt(-1e-10).astype(float)
                hd = (a - b).groupby(frame.network_id).mean().reindex(net.index).to_numpy()
                hci = np.quantile(hd[draws].mean(axis=1), [.025, .975])
                comparison_rows.append({"panel": label, "subset": subset, "comparator": comparator, "case_mean_difference": (frame.frozen_rule_hottest_30-frame[comparator + "_hottest_30"]).mean(), "network_mean_difference": diff.mean(), "network_ci_low": ci[0], "network_ci_high": ci[1], "network_harm_rate_difference": hd.mean(), "harm_difference_ci_low": hci[0], "harm_difference_ci_high": hci[1]})

    complete = pd.DataFrame(completeness_rows)
    complete.to_csv(OUT / "station_year_truth_completeness.csv", index=False)
    for label, d in panels.items():
        c = complete.loc[complete.panel.eq(label)]
        summary[label]["incomplete_station_years"] = int((~c.full_calendar_year).sum())
        summary[label]["cases_on_incomplete_years"] = int(c.loc[~c.full_calendar_year, "n_cases"].sum())
        summary[label]["years_with_summer_missing"] = int(c.summer_missing_days.gt(0).sum())
        summary[label]["maximum_missing_calendar_days"] = int(c.missing_days.max())

    confirm = panels["confirmation"][["network_id", "station_id"]].drop_duplicates()
    for panel, filename in [("first", "placement_predictions_first.csv"), ("second", "placement_predictions_second.csv")]:
        development = pd.read_csv(ROOT / "results/v14/p0_differential" / filename, usecols=["network_id", "station_id"], dtype=str).drop_duplicates()
        overlap = confirm.merge(development, on="station_id", suffixes=("_confirmation", "_design"))
        overlap["design_panel"] = panel
        overlap_rows.extend(overlap.to_dict("records"))
    pd.DataFrame(overlap_rows, columns=["network_id_confirmation", "station_id", "network_id_design", "design_panel"]).to_csv(OUT / "exact_station_id_overlap.csv", index=False)
    summary["exact_station_id_overlaps"] = len(overlap_rows)
    pd.DataFrame(mean_rows).to_csv(OUT / "replay_means_and_network_intervals.csv", index=False)
    pd.DataFrame(comparison_rows).to_csv(OUT / "paired_policy_comparisons.csv", index=False)
    pd.DataFrame(harm_rows).to_csv(OUT / "policy_harm_diagnostics.csv", index=False)
    (OUT / "audit_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(pd.DataFrame(comparison_rows).to_string(index=False))
    print("Original confirmation QC:")
    print(qc.to_string(index=False))


if __name__ == "__main__":
    main()
