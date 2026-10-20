#!/usr/bin/env python3
"""R2-05 (review op. 6, 2026-10-20b) -- can an archive tell, from its gap calendar,
that it needs no screen?

The manuscript advised an agency to read the gap-length distribution and the
climatological peak-window overlap *before looking at any label* and to skip
screening when the peak is rarely hidden.  That is an upper-level decision rule.
This script states it explicitly and tests it where a test is possible.

Rule under test (nothing fitted on real calendars)
    1. Observable composition of the archive: the share of its records in each
       cell of (longest gap) x (climatological peak overlap ``peak_overlap``).
    2. Class-conditional failure rates of the *unscreened* policy reconstruction,
       estimated on designed outages only (empirical arm, which transplants real
       gap geometry; both designed panels pooled).
    3. Predicted unscreened failure rate of the archive = composition x rates.
       Decision: "no screen needed" when the prediction is at most the 5 % cap.

Two tests
    A. Transport to real calendars: the same rule, with rates from designed
       outages only, applied to the 14 networks of the real-calendar replay and
       compared with the realised failure rate of each.  This is out-of-domain
       by construction, so there is nothing to tune and nothing to leak.
    B. Within the designed panels: rates estimated on the other shared-station
       groups predict each held-out group's failure rate (does composition
       explain between-archive variation at all?).

The evidence is thin by design -- the real replay rests on a small number of
independent station-years -- and the output says how thin.

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/r2_05_screening_need/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

OUT = C.RUN / "r2_05_screening_need"
CAP = 0.05
LEN_EDGES = [0, 14, 30, 90, 10_000]
LEN_LABELS = ["<=14", "15-30", "31-90", ">90"]
H_EDGES = [-1e-9, 1e-9, 0.5, 1.0 + 1e-9]
H_LABELS = ["0", "(0,0.5]", ">0.5"]
MIN_CELL = 30
DRAWS = 4000


def add_cells(frame: pd.DataFrame, length: str = "longest_run", overlap: str = "peak_overlap") -> pd.DataFrame:
    out = frame.copy()
    out["len_cell"] = pd.cut(out[length], LEN_EDGES, labels=LEN_LABELS)
    out["h_cell"] = pd.cut(out[overlap], H_EDGES, labels=H_LABELS)
    out["cell"] = out["len_cell"].astype(str) + "|" + out["h_cell"].astype(str)
    return out


def cell_rates(train: pd.DataFrame, bad: str) -> tuple[pd.Series, float]:
    """Failure rate by cell with a pooled fallback for sparse cells."""

    overall = float(train[bad].mean())
    g = train.groupby("cell")[bad].agg(["mean", "size"])
    rates = g["mean"].where(g["size"] >= MIN_CELL)
    # sparse cells fall back to their overlap class, then to the pooled rate
    by_h = train.groupby("h_cell", observed=True)[bad].mean()
    fallback = {cell: float(by_h.get(cell.split("|")[1], overall)) for cell in g.index}
    rates = pd.Series({cell: (rates[cell] if np.isfinite(rates[cell]) else fallback[cell]) for cell in g.index})
    return rates, overall


def predict_archive(frame: pd.DataFrame, rates: pd.Series, overall: float) -> float:
    return float(frame["cell"].map(rates).fillna(overall).mean())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    M330 = C.load_script("wrr330", C.ROOT / "scripts" / "330_wrr_aligned_policy_admission.py")

    designed = []
    for panel, spec in M330.PANELS.items():
        cases = pd.read_parquet(spec["cases"]).reset_index(drop=True)
        certs = pd.read_parquet(spec["certificates"]).reset_index(drop=True)
        table = M330.independence_table(cases)
        group_of = dict(zip(table["network_id"].astype(str), table["independence_group"].astype(str)))
        target = M330.policy_target(cases, certs)
        block = pd.DataFrame(
            {
                "panel": panel,
                "group": cases["network_id"].astype(str).map(group_of).to_numpy(),
                "arm": cases["arm"].astype(str).to_numpy(),
                "longest_run": pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(),
                "peak_overlap": pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy(),
                "bad": target["bad"].astype(float),
            }
        )
        designed.append(block)
    designed = add_cells(pd.concat(designed, ignore_index=True))

    # ---- A. transport to the real calendars ---------------------------------
    emp = designed[designed.arm.eq("empirical")]
    rates_emp, overall_emp = cell_rates(emp, "bad")
    rates_all, overall_all = cell_rates(designed, "bad")
    pd.DataFrame(
        {
            "cell": rates_emp.index,
            "failure_rate_empirical_arm": rates_emp.values,
            "n_empirical": [int((emp.cell == c).sum()) for c in rates_emp.index],
            "failure_rate_all_designed": [float(rates_all.get(c, np.nan)) for c in rates_emp.index],
            "n_all_designed": [int((designed.cell == c).sum()) for c in rates_emp.index],
        }
    ).to_csv(OUT / "designed_cell_failure_rates.csv", index=False)

    replay = pd.read_parquet(C.REPLAY_CASES)
    replay = replay[replay.seed == 101].copy()
    replay["bad"] = replay["policy_bad"].astype(float)
    rows, net_rows = [], []
    for level, block in replay.groupby("level"):
        block = add_cells(block)
        for network, g in block.groupby("network_id"):
            pred = predict_archive(g, rates_emp, overall_emp)
            obs = float(g["bad"].mean())
            net_rows.append(
                {
                    "level": level,
                    "network_id": network,
                    "n_groups": len(g),
                    "n_stations": int(g.station_id.nunique()),
                    "n_target_station_years": int(g[["station_id", "eval_year"]].drop_duplicates().shape[0]),
                    "share_overlap_gt_half": float((g.peak_overlap > 0.5).mean()),
                    "share_any_overlap": float((g.peak_overlap > 0).mean()),
                    "median_longest_run": float(g.longest_run.median()),
                    "predicted_unscreened_failure": pred,
                    "observed_unscreened_failure": obs,
                    "needs_screen_observed": bool(obs > CAP),
                    "rule_says_no_screen": bool(pred <= CAP),
                    "rule_correct": bool((pred <= CAP) == (obs <= CAP)),
                }
            )
        pooled_pred = predict_archive(block, rates_emp, overall_emp)
        pooled_obs = float(block["bad"].mean())
        # network-clustered interval for the pooled observed rate
        parts = [(g["bad"].sum(), len(g)) for _, g in block.groupby("network_id")]

        def stat(chosen):
            return sum(p[0] for p in chosen) / sum(p[1] for p in chosen)

        point, lo, hi = C.cluster_bootstrap(parts, stat, draws=DRAWS, seed=19)
        rows.append(
            {
                "level": level,
                "n_groups": len(block),
                "n_networks": block.network_id.nunique(),
                "n_target_station_years": int(block[["station_id", "eval_year"]].drop_duplicates().shape[0]),
                "pooled_predicted": pooled_pred,
                "pooled_observed": pooled_obs,
                "pooled_observed_ci_low": lo,
                "pooled_observed_ci_high": hi,
                "networks_needing_screen": int(sum(1 for r in net_rows if r["level"] == level and r["needs_screen_observed"])),
            }
        )
    pooled_table = pd.DataFrame(rows)
    net = pd.DataFrame(net_rows)
    pooled_table.to_csv(OUT / "real_calendar_pooled.csv", index=False)
    net.to_csv(OUT / "real_calendar_by_network.csv", index=False)

    # confusion matrix of the rule over networks, with exact binomial intervals
    conf = []
    for level, g in net.groupby("level"):
        tp = int(((~g.rule_says_no_screen) & g.needs_screen_observed).sum())  # screen advised, needed
        fn = int((g.rule_says_no_screen & g.needs_screen_observed).sum())  # said no screen, needed one
        fp = int(((~g.rule_says_no_screen) & (~g.needs_screen_observed)).sum())
        tn = int((g.rule_says_no_screen & (~g.needs_screen_observed)).sum())
        k = int(g.rule_correct.sum())
        n = len(g)
        lo, hi = stats.beta.ppf(0.025, k, n - k + 1) if k > 0 else 0.0, stats.beta.ppf(0.975, k + 1, n - k) if k < n else 1.0
        conf.append(
            {
                "level": level,
                "n_networks": n,
                "screen_needed_and_advised": tp,
                "screen_needed_but_not_advised": fn,
                "no_screen_needed_but_screen_advised": fp,
                "no_screen_needed_and_not_advised": tn,
                "accuracy": k / n,
                "accuracy_ci_low_exact": float(lo),
                "accuracy_ci_high_exact": float(hi),
                "n_networks_needing_screen": tp + fn,
            }
        )
    pd.DataFrame(conf).to_csv(OUT / "real_calendar_rule_confusion.csv", index=False)

    # ---- B. composition explains between-archive variation? ------------------
    groups = sorted(designed.group.unique())
    rng = np.random.default_rng(5)
    order = rng.permutation(len(groups))
    fold_of = {groups[int(i)]: pos % 5 for pos, i in enumerate(order)}
    designed["fold"] = designed.group.map(fold_of)
    pred_rows = []
    for fold in range(5):
        train = designed[designed.fold != fold]
        rates, overall = cell_rates(train, "bad")
        for (panel, group), g in designed[designed.fold == fold].groupby(["panel", "group"]):
            pred_rows.append(
                {
                    "panel": panel,
                    "group": group,
                    "n_cases": len(g),
                    "predicted": predict_archive(g, rates, overall),
                    "observed": float(g.bad.mean()),
                    "pooled_rate_baseline": overall,
                }
            )
    within = pd.DataFrame(pred_rows)
    summary = []
    for panel, g in within.groupby("panel"):
        rho = stats.spearmanr(g.predicted, g.observed)
        summary.append(
            {
                "panel": panel,
                "n_archives": len(g),
                "spearman_pred_obs": float(rho.statistic),
                "mae_composition_rule": float((g.predicted - g.observed).abs().mean()),
                "mae_pooled_rate_baseline": float((g.pooled_rate_baseline - g.observed).abs().mean()),
                "share_archives_observed_above_cap": float((g.observed > CAP).mean()),
                "share_archives_rule_says_no_screen": float((g.predicted <= CAP).mean()),
                "min_observed": float(g.observed.min()),
            }
        )
    pd.DataFrame(summary).to_csv(OUT / "designed_archive_prediction.csv", index=False)
    within.to_csv(OUT / "designed_archive_prediction_by_group.csv", index=False)

    write_summary(pooled_table, net, pd.DataFrame(conf), pd.DataFrame(summary))
    C.write_fingerprint(
        OUT,
        "scripts/344_wrr_screening_need_rule.py",
        {
            "development": M330.PANELS["development"]["cases"],
            "external": M330.PANELS["wave2_confirmation"]["cases"],
            "replay": C.REPLAY_CASES,
        },
    )
    print((OUT / "SUMMARY.md").read_text())
    return 0


def write_summary(pooled, net, conf, within) -> None:
    lines = ["# R2-05 does the gap calendar say whether to screen?", ""]
    lines += ["## Pooled real-calendar replay", "", pooled.round(4).to_string(index=False), ""]
    lines += ["## Rule vs realised failure, by network (seed 101; cases are identical across seeds)", ""]
    lines += [net.round(3).to_string(index=False), ""]
    lines += ["## Confusion matrix of the rule over networks", "", conf.round(3).to_string(index=False), ""]
    lines += ["## Does composition explain variation among designed archives?", "", within.round(3).to_string(index=False), ""]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
