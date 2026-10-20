#!/usr/bin/env python3
"""R2-07 -- write the supporting-information tables of the attribution round.

Reads the artifacts of scripts 340-344 (and the earlier mechanism run for the
sensitivity estimators) and writes ``paper/wrr/si_r2_tables.tex``, which the SI
``\\input``s.  Nothing is typed by hand: every cell is a column of a CSV.

Run:

    PYTHONPATH=src python3 scripts/346_wrr_si_tables_r2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

OUT = C.ROOT / "paper" / "wrr" / "si_r2_tables.tex"
MECH14 = C.READY / "major_revision_20261014" / "p1_mechanism_boundary"
SEEDS = (101, 202, 303)

RECON_LABEL = {
    "doy_climatology": "climatology",
    "smooth_climatology": "smoothed",
    "linear_interp": "interpolation",
    "donor_ridge": "donor",
    "air_ridge": "air",
}
SPEC_LABEL = {
    "gap_season": "gap geometry and season coverage",
    "gap_season+donors": "+ donor information",
    "gap_season+donors+residual": "+ reconstruction diagnostics",
    "generic": "all generic features (no support)",
    "generic+support": "+ peak-window share (fitted score)",
    "logit_small": "small logistic, six features",
    "logit_small+support": "small logistic + peak-window share",
    "gap_season+support": "gap and season + peak-window share",
    "gap_season+donors+support": "gap, season, donors + peak-window share",
    "gap_season+donors+residual+support": "gap, season, donors, diagnostics + peak-window share",
    "generic+oracle_support": "generic + TRUE hidden share (not deployable)",
    "peak_overlap_rule": "peak-window rule",
    "length_rule": "gap-length rule",
    "calibrated_bound": "certificate bound",
    "warm_coverage_rule": "warm-season coverage rule",
    "oracle_support_rule": "TRUE-hidden-share rule (not deployable)",
}


CONTRAST_LABEL = {
    "generic+support": "fitted score",
    "generic": "generic, no $\\hat h$",
    "gap_season+donors+residual+support": "gap+season+donors+diag.+$\\hat h$",
    "gap_season+donors+residual": "gap+season+donors+diag.",
    "gap_season+donors+support": "gap+season+donors+$\\hat h$",
    "gap_season+donors": "gap+season+donors",
    "gap_season+support": "gap+season+$\\hat h$",
    "gap_season": "gap+season",
    "logit_small+support": "logistic+$\\hat h$",
    "logit_small": "logistic",
    "peak_overlap_rule": "peak-window rule",
    "calibrated_bound": "certificate bound",
    "oracle_support_rule": "true-share rule",
    "generic+oracle_support": "generic+true share",
}


def f(x, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "---"
    return f"{x:.{nd}f}".replace("-", "$-$")


def pm(x, nd=1):
    """Signed number with a proper minus."""

    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "---"
    text = f"{x:+.{nd}f}"
    return text.replace("-", "$-$")


def ci(point, lo, hi, nd=1, scale=1.0):
    return f"{pm(point * scale, nd)} [{pm(lo * scale, nd)}, {pm(hi * scale, nd)}]"


def table(caption: str, label: str, spec: str, header: list[str], rows: list[list[str]], note: str = "") -> str:
    """A table that cannot run off the page: a leading ``X`` column wraps."""

    wide = len(header) >= 6
    lines = [
        "\\begin{table}",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        "\\tabletext",
        "\\centering",
    ]
    if wide:
        lines.append("\\scriptsize\\setlength{\\tabcolsep}{3pt}")
    use_x = spec.startswith("X")
    env_open = f"\\begin{{tabularx}}{{\\textwidth}}{{{spec}}}" if use_x else f"\\begin{{tabular}}{{{spec}}}"
    env_close = "\\end{tabularx}" if use_x else "\\end{tabular}"
    lines += [env_open, "\\hline", " & ".join(header) + " \\\\", "\\hline"]
    for row in rows:
        lines.append(" & ".join(row) + " \\\\")
    lines += ["\\hline", env_close]
    if note:
        lines.append(note)
    lines.append("\\end{table}")
    return "\n".join(lines)


def main() -> int:
    blocks: list[str] = []

    # ---- S9: what the designs contain ----------------------------------------
    inv = pd.read_csv(C.RUN / "r2_01_design_audit" / "arm_inventory.csv")
    rows = []
    names = {"development": "development", "external": "external", "crossed_mechanism": "crossed (mechanism)"}
    for r in inv.itertuples(index=False):
        rows.append(
            [
                names[r.panel], r.arm, f"{r.n_cases:,}".replace(",", "{,}"),
                f"{r.n_station_years:,}".replace(",", "{,}"), str(r.n_networks),
                f(r.median_longest_run, 0), f(r.mean_n_runs, 2), f(100 * r.share_single_run, 0),
            ]
        )
    blocks.append(
        table(
            "What the designed panels contain. \\emph{Stratified} outages are one contiguous run "
            "placed at a requested overlap with the climatological peak window; \\emph{empirical} "
            "outages transplant real gap lengths and months (one to four runs). Station-years are "
            "physical station-years (the external panel's 1{,}267 label-station-years are 1{,}103 "
            "station-years). Source: \\texttt{r2\\_01\\_design\\_audit/arm\\_inventory.csv}.",
            "tab:si-arms", "llrrrrrr",
            ["panel", "arm", "outages", "station-years", "networks", "median gap (d)", "runs per outage", "single-run (\\%)"],
            rows,
        )
    )

    corr = pd.read_csv(C.RUN / "r2_01_design_audit" / "length_support_correlation.csv")
    corr = corr[corr.pair.isin(["length_vs_true_hidden_share", "length_vs_climatological_overlap"])]
    rows = []
    for r in corr.itertuples(index=False):
        if not np.isfinite(r.pearson):
            continue
        rows.append(
            [
                names.get(r.panel, "real calendar replay"), r.arm,
                "true hidden share" if r.pair.endswith("hidden_share") else "climatological overlap",
                f"{pm(r.pearson, 2)} [{pm(r.lo, 2)}, {pm(r.hi, 2)}]", f"{int(r.n_clusters)}",
            ]
        )
    blocks.append(
        table(
            "Correlation of gap length with hidden support in each design, with network-clustered "
            "95\\% intervals (2{,}000 draws). Only the crossed panel breaks the correlation with the "
            "climatological overlap; the real replay has the strongest. Source: "
            "\\texttt{length\\_support\\_correlation.csv}.",
            "tab:si-corr", "lllrr",
            ["panel", "arm", "hidden support", "Pearson $r$ [95\\% interval]", "networks"],
            rows,
        )
    )

    cells = pd.read_csv(C.RUN / "r2_01_design_audit" / "length_by_overlap_cells.csv")
    cells = cells[(cells.panel != "crossed_mechanism") & (cells.cell_status != "populated")]
    rows = [
        [names[r.panel], str(int(r.target_length)), r.climatological_overlap_class, str(int(r.n_cases)), r.cell_status.replace("_", " ")]
        for r in cells.itertuples(index=False)
    ]
    blocks.append(
        table(
            "Length-by-class cells of the stratified arm that are empty or hold fewer than 100 "
            "outages. A 14-day run cannot cover a 30-day window, and a 270-day run can hardly "
            "avoid it. In the crossed panel every one of the nine cells holds 211 outages, one "
            "per station-year.",
            "tab:si-cells", "llrrl",
            ["panel", "target length (d)", "overlap class", "outages", "status"],
            rows,
        )
    )

    # ---- S10: the ladder with intervals -------------------------------------
    ops = pd.read_csv(C.RUN / "r2_02_same_capacity_ablation" / "ablation_operating_points.csv")
    risk = ops[ops.row_type == "riskcap"]
    order = [
        "length_rule", "peak_overlap_rule", "warm_coverage_rule", "calibrated_bound",
        "gap_season", "gap_season+support", "gap_season+donors", "gap_season+donors+support",
        "gap_season+donors+residual", "gap_season+donors+residual+support", "generic", "generic+support",
        "logit_small", "logit_small+support", "oracle_support_rule", "generic+oracle_support",
    ]
    rows = []
    for name in order:
        cells_ = []
        for panel in ("wave2_confirmation", "development"):
            sub = risk[(risk.panel == panel) & (risk.score == name)]
            cells_ += [f(100 * sub.retention.mean(), 1), f(100 * sub.false_admit_rate.mean(), 1)]
        rows.append([SPEC_LABEL[name]] + cells_)
    blocks.append(
        table(
            "Retention at the 5\\% cap and the failure rate among admitted records for every "
            "specification of the ladder, mean of three fold seeds (\\%). One learner, one "
            "training set, one nested cross-fit and one calibration procedure throughout; the "
            "full specification reproduces the fitted score of the aligned round bit for bit. "
            "Source: \\texttt{ablation\\_operating\\_points.csv}.",
            "tab:si-ladder-levels", "XR{1.6cm}R{1.6cm}R{1.8cm}R{1.8cm}",
            ["specification", "external retention", "external failure", "develop. retention", "develop. failure"],
            rows,
        )
    )

    con = pd.read_csv(C.RUN / "r2_02_same_capacity_ablation" / "ablation_contrasts.csv")
    con = con[con.metric == "retention"]
    pairs = [
        ("generic+support", "generic"),
        ("gap_season+donors+residual+support", "gap_season+donors+residual"),
        ("gap_season+donors+support", "gap_season+donors"),
        ("gap_season+support", "gap_season"),
        ("logit_small+support", "logit_small"),
        ("generic", "peak_overlap_rule"),
        ("generic+support", "peak_overlap_rule"),
        ("gap_season", "peak_overlap_rule"),
        ("logit_small", "peak_overlap_rule"),
        ("gap_season+donors", "gap_season"),
        ("gap_season+donors+residual", "gap_season+donors"),
        ("generic", "gap_season+donors+residual"),
        ("generic", "calibrated_bound"),
        ("generic+support", "calibrated_bound"),
        ("oracle_support_rule", "peak_overlap_rule"),
        ("generic+oracle_support", "generic+support"),
    ]
    for panel, tag, title in (
        ("wave2_confirmation", "ext", "External panel"),
        ("development", "dev", "Development panel"),
    ):
        rows = []
        for left, right in pairs:
            cells_ = []
            for seed in SEEDS:
                r = con[(con.panel == panel) & (con.left == left) & (con.right == right) & (con.fold_seed == seed)]
                if r.empty:
                    cells_.append("---")
                else:
                    r = r.iloc[0]
                    cells_.append(ci(r.point, r.ci_low, r.ci_high, 1, 100))
            rows.append([f"{CONTRAST_LABEL[left]} $-$ {CONTRAST_LABEL[right]}"] + cells_)
        blocks.append(
            table(
                f"{title}: paired retention differences at the 5\\% cap, in points, with "
                "group-clustered 95\\% intervals (2{,}000 draws) at each fold seed. The three seeds "
                "re-split one panel. ``Fitted score'' is the generic model plus $\\hat h$; ``generic'' is "
                "gap, season, donors, diagnostics and history; ``diag.'' is the reconstruction diagnostics. "
                "Source: \\texttt{ablation\\_contrasts.csv}.",
                f"tab:si-ladder-{tag}", "XR{2.5cm}R{2.5cm}R{2.5cm}",
                ["contrast", "seed 101", "seed 202", "seed 303"],
                rows,
            )
        )

    # ---- S11: the two channels ----------------------------------------------
    ch = pd.read_csv(C.RUN / "r2_03_three_windows" / "channels_by_hidden_class.csv")
    rows = []
    for recon in RECON_LABEL:
        for klass in ("none", "partial", "all"):
            r = ch[(ch.reconstructor == recon) & (ch.true_hidden_class == klass)].iloc[0]
            rows.append(
                [
                    RECON_LABEL[recon], {"none": "0", "partial": "(0, 1)", "all": "1"}[klass], str(int(r.n_cases)),
                    f(r.mean_abs_error_C, 3), pm(r.mean_hide_channel_C, 3), pm(r.mean_false_peak_channel_C, 3),
                    f(100 * r.share_false_peak_cases, 0),
                ]
            )
    blocks.append(
        table(
            "The hiding channel $\\bar e_S$ and the false-peak channel $F$ of the identity in Section 3.5 of the article, "
            "by reconstructor and true hidden share of the peak window, crossed panel ($^{\\circ}$C; "
            "means over outages). The identity holds to $2\\times10^{-13}$\\,$^{\\circ}$C on all "
            "9{,}449 finite cases. The last column is the share of outages whose false peak exceeds "
            "0.1\\,$^{\\circ}$C. Source: \\texttt{r2\\_03\\_three\\_windows/channels\\_by\\_hidden\\_class.csv}.",
            "tab:si-channels", "llrrrrr",
            ["reconstructor", "hidden share", "outages", "mean $|$error$|$", "hiding", "false peak", "false peak $>0.1$ (\\%)"],
            rows,
        )
    )

    inter = pd.read_csv(C.RUN / "r2_03_three_windows" / "residual_interventions.csv")
    rows = []
    for recon in RECON_LABEL:
        r = inter[(inter.reconstructor == recon) & (inter.true_hidden_class == "pooled")].iloc[0]
        rows.append(
            [
                RECON_LABEL[recon], f(r.recorded_C, 3),
                ci(r.permuted_minus_recorded_C, r.permuted_minus_recorded_lo, r.permuted_minus_recorded_hi, 3),
                ci(r.mean_removed_minus_recorded_C, r.mean_removed_minus_recorded_lo, r.mean_removed_minus_recorded_hi, 3),
                ci(r.mean_only_minus_recorded_C, r.mean_only_minus_recorded_lo, r.mean_only_minus_recorded_hi, 3),
            ]
        )
    blocks.append(
        table(
            "Interventions on the gap residuals, crossed panel, change in mean absolute error "
            "($^{\\circ}$C) with network-clustered 95\\% intervals. Numerical experiments on "
            "recorded residuals; truth, gap and reconstructor are held fixed. Source: "
            "\\texttt{residual\\_interventions.csv}.",
            "tab:si-interventions", "lrrrr",
            ["reconstructor", "recorded", "residuals permuted", "gap mean removed", "gap mean only"],
            rows,
        )
    )

    mis = pd.read_csv(C.RUN / "r2_03_three_windows" / "misalignment_within_strata.csv")

    def mis_table(strata, header, caption, label):
        rows = []
        for recon in RECON_LABEL:
            cells_ = []
            for stratum in strata:
                r = mis[(mis.reconstructor == recon) & (mis.stratum == stratum)]
                if r.empty or not np.isfinite(r.iloc[0].point_C):
                    cells_.append("---")
                else:
                    r = r.iloc[0]
                    cells_.append(ci(r.point_C, r.lo_C, r.hi_C, 2))
            rows.append([RECON_LABEL[recon]] + cells_)
        return table(caption, label, "l" + "c" * len(strata), ["reconstructor"] + header, rows)

    blocks.append(
        mis_table(
            ("pooled", "clim_class_x_true_class_weighted"),
            ["pooled", "within climatological class $\\times$ true class"],
            "Misaligned minus aligned mean absolute error ($^{\\circ}$C), pooled and within strata of "
            "the climatological class and the true class (weights are the strata's case counts), "
            "with network-clustered 95\\% intervals. Source: \\texttt{misalignment\\_within\\_strata.csv}.",
            "tab:si-misalign",
        )
    )
    blocks.append(
        mis_table(
            ("none", "partial", "all"),
            ["true share 0", "true share (0,1)", "true share 1"],
            "The same contrast within strata of the true hidden share. Where the true window is "
            "observed an aligned outage has zero error by identity, so the first column restates the "
            "size of the false peak; a blank cell means one side of the contrast is empty. Source: "
            "\\texttt{misalignment\\_within\\_strata.csv}.",
            "tab:si-misalign-class",
        )
    )

    # ---- S12: sensitivity estimator and competing peaks ----------------------
    ce = pd.read_csv(MECH14 / "crossed_effects.csv")
    ce = ce[ce.contrast == "long_minus_short_at_fixed_hidden_share"]
    rows = []
    for recon in RECON_LABEL:
        cells_ = []
        for level in ("true_peak_hidden_fraction>=0.9", "true_peak_hidden_fraction>=0.999"):
            for detail in (None, "network_paired_subsets"):
                sub = ce[(ce.reconstructor == recon) & (ce.level == level)]
                sub = sub[sub.design_detail.isna()] if detail is None else sub[sub.design_detail == detail]
                if sub.empty:
                    cells_.append("---")
                else:
                    r = sub.iloc[0]
                    cells_.append(ci(r.point_C, r.ci_low_C, r.ci_high_C, 2))
        rows.append([RECON_LABEL[recon]] + cells_)
    blocks.append(
        table(
            "Length effect (90 minus 30 days, $^{\\circ}$C) at a true hidden share of at least "
            "0.9 and at least 0.999, by estimator. ``Within station-years'' keeps a station-year "
            "only when it holds both lengths above the cut-off (48 and 11 station-years); the "
            "``network subsets'' estimator needs both lengths only somewhere in the same network "
            "and discards the pairing. Source: the 2026-10-14 mechanism run, "
            "\\texttt{crossed\\_effects.csv}.",
            "tab:si-length-estimators", "lcccc",
            ["reconstructor", "$\\geq0.9$, within station-years", "$\\geq0.9$, network subsets",
             "$\\geq0.999$, within station-years", "$\\geq0.999$, network subsets"],
            rows,
        )
    )

    cp = pd.read_csv(MECH14 / "competing_peak.csv")
    cp = cp[(cp.block == "error_by_bin") & (cp.bin_variable == "competing_peak_gap_C")]
    bins = ["[0,0.25)", "[0.25,0.5)", "[0.5,1)", "[1,2)", ">=2"]
    rows = []
    for b in bins:
        cells_ = []
        for recon in RECON_LABEL:
            r = cp[(cp.reconstructor == recon) & (cp.bin == b)]
            cells_.append(f(r.iloc[0].point_C, 2) if len(r) else "---")
        n = cp[(cp.reconstructor == "doy_climatology") & (cp.bin == b)]
        rows.append(["{" + b.replace(">=", "$\\geq$") + "}", str(int(n.iloc[0].n_cases)) if len(n) else "---"] + cells_)
    blocks.append(
        table(
            "Mean absolute error ($^{\\circ}$C) by the temperature gap between the best 30-day "
            "window and the best window disjoint from it, crossed panel. The relation is "
            "non-monotone and flat for donor regression. Source: the 2026-10-14 mechanism run, "
            "\\texttt{competing\\_peak.csv}.",
            "tab:si-competing", "llrrrrr",
            ["gap to second window ($^{\\circ}$C)", "outages"] + [RECON_LABEL[r] for r in RECON_LABEL],
            rows,
        )
    )

    # ---- S13: the screening-need rule ---------------------------------------
    net = pd.read_csv(C.RUN / "r2_05_screening_need" / "real_calendar_by_network.csv")
    pivot = {}
    for level, g in net.groupby("level"):
        pivot[level] = g.set_index("network_id")
    base = pivot["target_only"].sort_values("observed_unscreened_failure", ascending=False)
    rows = []
    for network, r in base.iterrows():
        rows.append(
            [
                network.replace("_", "\\_"), str(int(r.n_groups)), str(int(r.n_target_station_years)),
                f(100 * r.share_overlap_gt_half, 0), f(r.median_longest_run, 0),
                f(100 * r.predicted_unscreened_failure, 1),
                f(100 * pivot["target_only"].loc[network].observed_unscreened_failure, 1),
                f(100 * pivot["partial_donor_failure"].loc[network].observed_unscreened_failure, 1),
                f(100 * pivot["all_donor_failure"].loc[network].observed_unscreened_failure, 1),
            ]
        )
    blocks.append(
        table(
            "The composition rule and the realised unscreened failure rate in each real-calendar "
            "network (\\%). The prediction uses designed outages only; the three observed columns "
            "are the target-only, partial and all-donor failure scenarios. A network exceeds the "
            "5\\% cap in two scenarios (the first two rows) and in four at the all-donor level. "
            "Source: \\texttt{r2\\_05\\_screening\\_need/real\\_calendar\\_by\\_network.csv}.",
            "tab:si-need", "lrrrrrrrr",
            ["network", "groups", "target station-years", "overlap $>0.5$ (\\%)", "median gap (d)",
             "predicted", "observed, target only", "observed, partial", "observed, all donors"],
            rows,
        )
    )
    conf = pd.read_csv(C.RUN / "r2_05_screening_need" / "real_calendar_rule_confusion.csv")
    rows = [
        [
            r.level.replace("_", " "), str(int(r.n_networks)), str(int(r.n_networks_needing_screen)),
            str(int(r.screen_needed_but_not_advised)), str(int(r.no_screen_needed_but_screen_advised)),
            f"{100 * r.accuracy:.0f} [{100 * r.accuracy_ci_low_exact:.0f}, {100 * r.accuracy_ci_high_exact:.1f}]",
        ]
        for r in conf.itertuples(index=False)
    ]
    blocks.append(
        table(
            "The rule's decisions over the 14 networks, by failure scenario, with an exact binomial "
            "95\\% interval for accuracy. ``Missed'' counts networks that needed a screen and were "
            "told they did not. Source: \\texttt{real\\_calendar\\_rule\\_confusion.csv}.",
            "tab:si-confusion", "lrrrrr",
            ["scenario", "networks", "needing a screen", "missed", "screened unnecessarily", "accuracy (\\%) [95\\% interval]"],
            rows,
        )
    )

    # ---- S14: hot years against the null, and break-even costs -----------------
    hot = pd.read_csv(C.RUN / "r2_04_hot_year_null" / "hot_year_selection_null.csv")
    hot = hot[(hot.population == "designed") & (hot.hot_c == 20.0) & (hot.arm != "reconstruct_all")]
    arm_label = {
        "fitted_risk": "fitted risk", "generic": "same model, no support", "calibrated_bound": "certificate bound",
        "peak_overlap_rule": "peak-window rule", "length_rule": "gap-length rule",
    }
    rows_a, rows_b = [], []
    for panel, plabel in (("wave2_confirmation", "external"), ("development", "development")):
        for arm in arm_label:
            cells_ = []
            for seed in SEEDS:
                r = hot[(hot.panel == panel) & (hot.arm == arm) & (hot.fold_seed == seed)].iloc[0]
                cells_.append(ci(r.excess_hot_refusal, r.excess_ci_low, r.excess_ci_high, 1, 100))
            r1 = hot[(hot.panel == panel) & (hot.arm == arm) & (hot.fold_seed == 101)].iloc[0]
            rows_a.append([plabel, arm_label[arm]] + cells_)
            rows_b.append(
                [
                    plabel, arm_label[arm], f(100 * r1.retention, 1), f(100 * r1.refused_hot_share, 1),
                    f(100 * r1.wrong_judgement_rate, 2), f(r1.breakeven_abstention_cost_rho1, 3),
                    f(r1.breakeven_abstention_cost_rho5, 3), f(r1.breakeven_abstention_cost_rho10, 3),
                ]
            )
    blocks.append(
        table(
            "Excess refusal of true hot years (20\\,$^{\\circ}$C) over the hot-year-blind null: "
            "retention of all records minus retention of true hot years, in points, with "
            "group-clustered 95\\% intervals at each fold seed. Negative means hot years are refused "
            "less often than records in general. Source: "
            "\\texttt{r2\\_04\\_hot\\_year\\_null/hot\\_year\\_selection\\_null.csv}.",
            "tab:si-hotnull", "llrrr",
            ["panel", "rule", "seed 101", "seed 202", "seed 303"],
            rows_a,
        )
    )
    blocks.append(
        table(
            "Retention, refusal of true hot years, wrong hot-year judgements (\\% of candidates) and the "
            "break-even abstention cost $c_{\\mathrm A}^\\ast$ at $\\rho=1,5,10$ (the cost of a missed "
            "hot year relative to a false alarm), fold seed 101, 20\\,$^{\\circ}$C. A screen beats "
            "reconstructing everything only if one abstention costs less than $c_{\\mathrm A}^\\ast$ "
            "wrong judgements.",
            "tab:si-hotcost", "llrrrrrr",
            ["panel", "rule", "retention (\\%)", "hot refused (\\%)", "wrong (\\%)",
             "$c_{\\mathrm A}^\\ast$, $\\rho=1$", "$\\rho=5$", "$\\rho=10$"],
            rows_b,
        )
    )

    text = (
        "%% Generated by scripts/346_wrr_si_tables_r2.py from the artifacts of scripts 340-344.\n"
        "%% Do not edit by hand.\n\n" + "\n\n".join(blocks) + "\n"
    )
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(C.ROOT)} with {len(blocks)} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
