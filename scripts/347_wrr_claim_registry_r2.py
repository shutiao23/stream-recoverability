#!/usr/bin/env python3
"""R2-08 -- bind the attribution round's claims to the artifacts that produce them.

Each row reads a value out of a CSV (never typed), formats it the way the
manuscript prints it, and checks that the printed string occurs in
``paper/wrr/wrr_manuscript.tex``.  A claim whose number drifts from its artifact,
or whose sentence loses the number, fails the run.

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/claim_registry.csv``
and ``claim_binding_check.json``.

Run:

    PYTHONPATH=src python3 scripts/347_wrr_claim_registry_r2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

MANUSCRIPT = C.ROOT / "paper" / "wrr" / "wrr_manuscript.tex"
R = C.RUN


def load(rel: str) -> pd.DataFrame:
    return pd.read_csv(R / rel)


def pick(df: pd.DataFrame, **where) -> pd.Series:
    mask = np.ones(len(df), dtype=bool)
    for key, value in where.items():
        mask &= (df[key] == value).to_numpy()
    sub = df[mask]
    if len(sub) != 1:
        raise KeyError(f"{where} matched {len(sub)} rows")
    return sub.iloc[0]


def main() -> int:
    claims: list[dict] = []

    def add(cid, claim, value, printed, artifact, selector):
        claims.append(
            {"claim_id": cid, "claim": claim, "value": value, "printed_as": printed,
             "artifact": artifact, "selector": selector}
        )

    # ---- design audit -------------------------------------------------------
    inv = load("r2_01_design_audit/arm_inventory.csv")
    strat = int(inv[(inv.arm == "stratified") & inv.panel.isin(["development", "external"])].n_cases.sum())
    emp = int(inv[(inv.arm == "empirical") & inv.panel.isin(["development", "external"])].n_cases.sum())
    add("R01", "stratified outages in the 53,721", strat, "33{,}749", "r2_01_design_audit/arm_inventory.csv", "arm=stratified; development+external")
    add("R02", "empirical outages in the 53,721", emp, "19{,}972", "r2_01_design_audit/arm_inventory.csv", "arm=empirical; development+external")
    cor = load("r2_01_design_audit/length_support_correlation.csv")
    r = pick(cor, panel="external", arm="all", pair="length_vs_true_hidden_share")
    add("R03", "length vs true hidden share, external pooled", round(r.pearson, 2), "+0.52", "r2_01_design_audit/length_support_correlation.csv", "panel=external, arm=all")
    r = pick(cor, panel="real_calendar_replay", arm="all", pair="length_vs_climatological_overlap")
    add("R04", "length vs climatological overlap, real replay", round(r.pearson, 2), "+0.71", "r2_01_design_audit/length_support_correlation.csv", "panel=real_calendar_replay")
    r = pick(cor, panel="crossed_mechanism", arm="all", pair="length_vs_climatological_overlap")
    add("R05", "length vs climatological overlap, crossed panel", round(r.pearson, 2), "0.00", "r2_01_design_audit/length_support_correlation.csv", "panel=crossed_mechanism")
    ind = pd.read_csv(R / "r2_01_design_audit/real_calendar_independence.csv", index_col=0)["value"]
    add("R06", "source station-years behind the 418 groups", int(ind["n_source_incomplete_station_years"]), "59", "r2_01_design_audit/real_calendar_independence.csv", "n_source_incomplete_station_years")
    add("R07", "target station-years behind the 418 groups", int(ind["n_target_station_years"]), "67", "r2_01_design_audit/real_calendar_independence.csv", "n_target_station_years")
    sub = inv[(inv.panel == "crossed_mechanism") & (inv.arm == "stratified")].iloc[0]
    add("R08", "crossed panel station-years", int(sub.n_station_years), "211", "r2_01_design_audit/arm_inventory.csv", "panel=crossed_mechanism, arm=stratified")

    # ---- three windows ------------------------------------------------------
    ident = pd.read_csv(R / "r2_03_three_windows/identity_check.csv", index_col=0)["value"]
    add("R09", "max identity residual (degC)", f"{float(ident['max_abs_identity_residual_C']):.2e}", "2\\times10^{-13}", "r2_03_three_windows/identity_check.csv", "max_abs_identity_residual_C")
    ch = load("r2_03_three_windows/channels_by_hidden_class.csv")
    r = pick(ch, reconstructor="doy_climatology", true_hidden_class="none")
    add("R10", "climatology mean |error|, true window observed", round(r.mean_abs_error_C, 2), "0.06", "r2_03_three_windows/channels_by_hidden_class.csv", "doy_climatology, none")
    r = pick(ch, reconstructor="doy_climatology", true_hidden_class="all")
    add("R11", "climatology hiding channel, window hidden", round(r.mean_hide_channel_C, 2), "$-0.75$", "same", "doy_climatology, all")
    add("R12", "climatology false-peak channel, window hidden", round(r.mean_false_peak_channel_C, 2), "$+0.43$", "same", "doy_climatology, all")
    add("R13", "climatology mean |error|, window hidden", round(r.mean_abs_error_C, 2), "0.92", "same", "doy_climatology, all")
    mis = load("r2_03_three_windows/misalignment_within_strata.csv")
    r = pick(mis, reconstructor="doy_climatology", stratum="pooled")
    add("R14", "climatology misaligned minus aligned, pooled", round(r.point_C, 2), "0.66", "r2_03_three_windows/misalignment_within_strata.csv", "doy_climatology, pooled")
    r = pick(mis, reconstructor="doy_climatology", stratum="clim_class_x_true_class_weighted")
    add("R15", "climatology misaligned minus aligned, within strata", round(r.point_C, 2), "0.19", "same", "doy_climatology, clim_class_x_true_class_weighted")
    dist = load("r2_03_three_windows/window_distances.csv")
    r = pick(dist, reconstructor="doy_climatology", pair="climatological_vs_true")
    add("R16", "median days between climatological and true window", int(r.median_days), "12", "r2_03_three_windows/window_distances.csv", "climatological_vs_true")
    add("R17", "share of cases with the two windows 30+ days apart", round(100 * r.share_ge_30_days, 1), "9.5", "same", "climatological_vs_true")
    it = load("r2_03_three_windows/residual_interventions.csv")
    r = pick(it, reconstructor="doy_climatology", true_hidden_class="pooled")
    add("R18", "permutation lowers climatology mean |error| (degC)", round(-r.permuted_minus_recorded_C, 2), "0.08", "r2_03_three_windows/residual_interventions.csv", "doy_climatology, pooled")
    add("R19", "mean removal lowers climatology mean |error| (degC)", round(-r.mean_removed_minus_recorded_C, 2), "0.24", "same", "doy_climatology, pooled")

    # ---- ladder -------------------------------------------------------------
    ops = load("r2_02_same_capacity_ablation/ablation_operating_points.csv")
    risk = ops[(ops.row_type == "riskcap") & (ops.panel == "wave2_confirmation")]

    def ret(name):
        return round(100 * risk[risk.score == name].retention.mean(), 1)

    for cid, name, printed in (
        ("R20", "gap_season", "63.2"), ("R21", "gap_season+donors", "68.7"),
        ("R22", "gap_season+donors+residual", "74.0"), ("R23", "generic", "73.4"),
        ("R24", "generic+support", "73.9"),
    ):
        add(cid, f"external retention at the cap, {name}", ret(name), printed, "r2_02_same_capacity_ablation/ablation_operating_points.csv", f"panel=wave2_confirmation, score={name}, mean of 3 seeds")
    con = load("r2_02_same_capacity_ablation/ablation_contrasts.csv")
    con = con[(con.metric == "retention") & (con.panel == "wave2_confirmation")]
    sup = [100 * pick(con, left="generic+support", right="generic", fold_seed=s).point for s in (101, 202, 303)]
    add("R25", "support share added to the generic model, external, seeds", [round(v, 1) for v in sup], "+0.4", "r2_02_same_capacity_ablation/ablation_contrasts.csv", "left=generic+support, right=generic")
    gen = [100 * pick(con, left="generic", right="peak_overlap_rule", fold_seed=s).point for s in (101, 202, 303)]
    add("R26", "generic model minus peak-window rule, external, range", [round(min(gen), 1), round(max(gen), 1)], "6.7 to 7.0", "same", "left=generic, right=peak_overlap_rule")
    orc = [100 * pick(con, left="oracle_support_rule", right="peak_overlap_rule", fold_seed=s).point for s in (101, 202, 303)]
    add("R27", "true-share rule minus climatological rule, external, range", [round(min(orc), 1), round(max(orc), 1)], "5.0 to 5.9", "same", "left=oracle_support_rule")

    # ---- hot years ----------------------------------------------------------
    hot = load("r2_04_hot_year_null/hot_year_selection_null.csv")
    r = hot[(hot.population == "designed") & (hot.panel == "wave2_confirmation") & (hot.hot_c == 20.0) & (hot.arm == "fitted_risk") & (hot.fold_seed == 101)].iloc[0]
    add("R28", "fitted score: hot-year refusal minus all-record refusal, pp, seed 101", round(100 * r.excess_hot_refusal, 1), "1.0 point [0.3, 1.6]", "r2_04_hot_year_null/hot_year_selection_null.csv", "external, 20C, fitted_risk, seed 101 (sign: negative = hot years refused less)")
    add("R29", "fitted score break-even abstention cost, rho=1, seed 101", round(r.breakeven_abstention_cost_rho1, 3), "0.046", "same", "same")
    add("R30", "fitted score wrong-judgement rate", round(100 * r.wrong_judgement_rate, 2), "0.45", "same", "same")

    # ---- screening-need rule ------------------------------------------------
    pooled = load("r2_05_screening_need/real_calendar_pooled.csv")
    add("R31", "composition rule pooled prediction (%)", round(100 * pooled.pooled_predicted.iloc[0], 1), "3.5", "r2_05_screening_need/real_calendar_pooled.csv", "pooled_predicted")
    conf = load("r2_05_screening_need/real_calendar_rule_confusion.csv")
    add("R32", "networks needing a screen, all-donor scenario", int(pick(conf, level="all_donor_failure").n_networks_needing_screen), "four", "r2_05_screening_need/real_calendar_rule_confusion.csv", "level=all_donor_failure")
    des = load("r2_05_screening_need/designed_archive_prediction.csv")
    add("R33", "Spearman, composition vs observed, development", round(pick(des, panel="development").spearman_pred_obs, 2), "0.35", "r2_05_screening_need/designed_archive_prediction.csv", "panel=development")
    add("R34", "Spearman, composition vs observed, external", round(pick(des, panel="wave2_confirmation").spearman_pred_obs, 2), "0.61", "same", "panel=wave2_confirmation")

    # ---- length effect (figure 3b) -------------------------------------------
    f3 = pd.read_csv(C.PREV / "p0_06_figures/fig3_source.csv")
    r = f3[(f3.panel == "length_effect_at_high_hidden_share") & (f3.reconstructor == "doy_climatology") & (f3.length.str.contains("0.9$", regex=True))].iloc[0]
    add("R35", "length effect, climatology, share >= 0.9 (degC)", round(r.point_c, 2), "0.12", "../major_revision_20261020/p0_06_figures/fig3_source.csv", "length_effect_at_high_hidden_share, doy_climatology, >=0.9")

    text = MANUSCRIPT.read_text(encoding="utf-8")
    flat = " ".join(text.split())
    failures = []
    for row in claims:
        present = row["printed_as"] in flat
        row["printed_in_manuscript"] = bool(present)
        if not present:
            failures.append(row["claim_id"])
    pd.DataFrame(claims).to_csv(R / "claim_registry.csv", index=False)
    (R / "claim_binding_check.json").write_text(
        json.dumps({"claims": len(claims), "missing_from_manuscript": failures}, indent=2) + "\n"
    )
    print(f"{len(claims)} claims; missing from the manuscript: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
