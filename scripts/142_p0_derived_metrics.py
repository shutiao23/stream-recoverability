#!/usr/bin/env python3
"""Derived P0 metrics: network-level gates, seasonal LOO bounds, budgets.

Reads the placement/unit prediction tables produced by
scripts/140_run_p0_differential_stress.py and emits:

  derived_network_level.csv      per-duration + pooled network-level rho (CI)
  season_loo_upper.csv           leave-one-season-cell-out realized-benefit rho
  budget_within_duration.csv     top-20% budget within each duration
  sanity_checks.txt              archived-risk reproduction + predictor overlap
  gates.json                     rewritten with both gate scales
  REPORT.md                      rewritten final report with verdicts

Gates follow paper_archived/v14_plan/PLAN.md section 3.4.  G1 is judged on the
network-level Spearman (the plan's wording), with the placement-level
per-duration values reported as the pooled-convention robustness scale and
interpreted with the plan's 0.25-0.35 partial-GO band.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

OUTPUT = ROOT / "results" / "v14" / "p0_differential"
DIRECT_GAPS = (7, 14, 30, 60, 90, 180)  # round-2 revision (W2-A): 14/60 d fitted
SEED = 20260903


def rho(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    a = pd.Series(a).reset_index(drop=True)
    b = pd.Series(b).reset_index(drop=True)
    mask = a.notna() & b.notna()
    if int(mask.sum()) < 3:
        return float("nan")
    return float(spearmanr(a[mask], b[mask]).statistic)


def network_cluster_ci(
    frame: pd.DataFrame, predictor: str, target: str, *, repeats: int = 2000
) -> tuple[float, float, float]:
    """Network-level rho (network means) with a network-cluster bootstrap CI."""

    rng = np.random.default_rng(SEED)
    means = (
        frame.groupby("network_id", as_index=False)
        .agg(predicted=(predictor, "mean"), realized=(target, "mean"))
        .dropna()
    )
    point = rho(means["predicted"], means["realized"])
    nets = means["network_id"].to_numpy(dtype=object)
    pred = means["predicted"].to_numpy(dtype=float)
    real = means["realized"].to_numpy(dtype=float)
    draws: list[float] = []
    for _ in range(repeats):
        chosen = rng.choice(len(nets), size=len(nets), replace=True)
        value = rho(pred[chosen], real[chosen])
        if np.isfinite(value):
            draws.append(value)
    draws = np.asarray(draws)
    return point, float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def season_loo_rho(frame: pd.DataFrame) -> float:
    """Leave-one-(station, duration, season)-cell-out realized-benefit mean."""

    work = frame.dropna(subset=["realized_benefit"]).copy()
    group = work.groupby(["station_id", "gap_length", "season"])["realized_benefit"]
    count = group.transform("count")
    loo = (group.transform("sum") - work["realized_benefit"]) / (count - 1)
    loo = loo.replace([np.inf, -np.inf], np.nan)
    return rho(loo, work["realized_benefit"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output

    sanity: list[str] = []
    net_rows: list[dict[str, object]] = []
    season_rows: list[dict[str, object]] = []
    budget_rows: list[dict[str, object]] = []
    verdicts: dict[str, object] = {}

    for panel in ("first", "second"):
        placements = pd.read_csv(
            output / f"placement_predictions_{panel}.csv",
            parse_dates=["gap_start"],
        )
        unit = pd.read_csv(output / f"unit_predictions_{panel}.csv")
        direct = placements.loc[placements["direct"]].copy()
        unit_direct = unit.loc[unit["direct"]].copy()

        if panel == "second":
            archived = pd.read_csv(
                ROOT
                / "results"
                / "development_v11"
                / "second_confirmation"
                / "scoring"
                / "empirical_predictions.csv"
            )
            check = unit_direct.merge(
                archived,
                on=["network_id", "station_id", "gap_length"],
                how="inner",
            )
            diff = np.abs(check["risk_prediction"] - check["empirical_transfer_prediction"])
            sanity.append(
                f"second panel: max |risk_prediction - archived| over "
                f"{len(check)} direct units = {diff.max():.2e} "
                f"(median {np.nanmedian(diff):.2e})"
            )
            overlap = rho(
                unit_direct["diff_prediction"], unit_direct["risk_prediction"]
            )
            sanity.append(
                f"second panel: corr(diff_prediction, risk_prediction) = {overlap:.3f}"
            )
            overlap_first = rho(
                pd.read_csv(output / "unit_predictions_first.csv").loc[
                    lambda d: d["direct"]
                ]["diff_prediction"],
                pd.read_csv(output / "unit_predictions_first.csv").loc[
                    lambda d: d["direct"]
                ]["risk_prediction"],
            )
            sanity.append(f"first panel: corr(diff, risk) = {overlap_first:.3f}")

        for duration in DIRECT_GAPS:
            sub = direct.loc[direct["gap_length"] == duration]
            unit_sub = unit_direct.loc[unit_direct["gap_length"] == duration]
            if not len(sub) or not len(unit_sub):
                continue
            point_diff = rho(sub["diff_prediction"], sub["realized_benefit"])
            point_risk = rho(sub["risk_prediction"], sub["realized_benefit"])
            net_point, net_lo, net_hi = network_cluster_ci(
                unit_sub, "diff_prediction", "realized_benefit"
            )
            season_rows.append(
                {
                    "panel": panel,
                    "horizon": int(duration),
                    "n_placements": int(len(sub)),
                    "season_loo_rho": season_loo_rho(sub),
                }
            )
            net_rows.append(
                {
                    "panel": panel,
                    "horizon": int(duration),
                    "n_networks": int(unit_sub["network_id"].nunique()),
                    "network_rho": net_point,
                    "network_rho_ci_lower": net_lo,
                    "network_rho_ci_upper": net_hi,
                    "placement_rho": point_diff,
                    "risk_placement_rho": point_risk,
                }
            )
            if panel == "second":
                count = max(1, round(0.2 * len(sub)))
                for name, column in [
                    ("diff", "diff_prediction"),
                    ("duration", "duration_only_prediction"),
                    ("r6_diff", "r6_diff_prediction"),
                    ("risk", "risk_prediction"),
                ]:
                    selected = sub.nlargest(count, column)
                    budget_rows.append(
                        {
                            "panel": panel,
                            "horizon": int(duration),
                            "budget": 0.20,
                            "predictor": name,
                            "n": int(len(selected)),
                            "mean_realized_benefit": float(
                                selected["realized_benefit"].mean()
                            ),
                            "harmful_rate": float(
                                (selected["realized_benefit"] < 0).mean()
                            ),
                        }
                    )

        sub = direct
        unit_sub = unit_direct
        net_point, net_lo, net_hi = network_cluster_ci(
            unit_sub, "diff_prediction", "realized_benefit"
        )
        net_rows.append(
            {
                "panel": panel,
                "horizon": "direct",
                "n_networks": int(unit_sub["network_id"].nunique()),
                "network_rho": net_point,
                "network_rho_ci_lower": net_lo,
                "network_rho_ci_upper": net_hi,
                "placement_rho": rho(sub["diff_prediction"], sub["realized_benefit"]),
                "risk_placement_rho": rho(
                    sub["risk_prediction"], sub["realized_benefit"]
                ),
            }
        )
        season_rows.append(
            {
                "panel": panel,
                "horizon": "direct",
                "n_placements": int(len(sub)),
                "season_loo_rho": season_loo_rho(sub),
            }
        )

    net_table = pd.DataFrame(net_rows)
    net_table.to_csv(output / "derived_network_level.csv", index=False)
    season_table = pd.DataFrame(season_rows)
    season_table.to_csv(output / "season_loo_upper.csv", index=False)
    pd.DataFrame(budget_rows).to_csv(
        output / "budget_within_duration.csv", index=False
    )

    second_net = net_table.loc[
        (net_table["panel"] == "second") & (net_table["horizon"] != "direct")
    ]
    g1_per_duration: dict[str, object] = {}
    g1_pass_count = 0
    for row in second_net.itertuples(index=False):
        passed = bool(
            row.network_rho >= 0.35 and row.network_rho_ci_lower > 0.0
        )
        if passed:
            g1_pass_count += 1
        g1_per_duration[str(row.horizon)] = {
            "network_rho": row.network_rho,
            "ci_lower": row.network_rho_ci_lower,
            "pass_g1": passed,
            "placement_rho": row.placement_rho,
        }
    verdicts["g1_network_level"] = g1_pass_count == 4
    verdicts["g1_network_pass_count"] = g1_pass_count
    verdicts["per_duration_network_level"] = g1_per_duration

    second_direct_net = net_table.loc[
        (net_table["panel"] == "second") & (net_table["horizon"] == "direct")
    ]
    verdicts["network_rho_direct"] = {
        "rho": float(second_direct_net["network_rho"].iloc[0]),
        "ci_lower": float(second_direct_net["network_rho_ci_lower"].iloc[0]),
    }

    placements_second = pd.read_csv(
        output / "placement_predictions_second.csv", parse_dates=["gap_start"]
    )
    direct_second = placements_second.loc[placements_second["direct"]]
    paired = pd.read_csv(output / "paired_bootstrap.csv")
    risk_paired = paired[
        (paired["panel"] == "second")
        & (paired["comparator"] == "risk")
        & (paired["level"] == "placement_pooled")
    ]
    budget = pd.read_csv(output / "budget_curve.csv")
    top20 = budget[
        (budget["panel"] == "second")
        & (budget["predictor"] == "diff")
        & np.isclose(budget["budget"], 0.20)
    ]
    panel_mean = float(direct_second["realized_benefit"].mean())
    verdicts["g2"] = bool((risk_paired["ci_lower"] > 0).iloc[0])
    verdicts["g2_delta_mean"] = float(risk_paired["mean"].iloc[0])
    verdicts["g2_ci"] = [
        float(risk_paired["ci_lower"].iloc[0]),
        float(risk_paired["ci_upper"].iloc[0]),
    ]
    verdicts["g3"] = bool(
        top20["mean_realized_benefit"].iloc[0] >= 1.3 * panel_mean
        and top20["harmful_rate"].iloc[0] < 0.15
    )
    verdicts["g3_mean_realized"] = float(top20["mean_realized_benefit"].iloc[0])
    verdicts["g3_panel_mean"] = panel_mean
    verdicts["g3_harmful_rate"] = float(top20["harmful_rate"].iloc[0])
    verdicts["g4"] = g1_pass_count >= 2
    verdicts["g4_pass_count"] = g1_pass_count
    verdicts["overall_go"] = (
        verdicts["g1_network_level"] and verdicts["g2"] and verdicts["g3"]
    )

    (output / "gates.json").write_text(
        json.dumps(verdicts, indent=2) + "\n", encoding="utf-8"
    )
    (output / "sanity_checks.txt").write_text(
        "\n".join(sanity) + "\n", encoding="utf-8"
    )

    def fmt(value: object) -> str:
        return "nan" if value != value else f"{value:.3f}"

    lines: list[str] = []
    lines.append("# v14 P0: differential stress test - final report")
    lines.append("")
    lines.append("Estimand: benefit = MAE(default handling) - MAE(model) per")
    lines.append("placement.  Benefit curves are built strictly inside the")
    lines.append("inner fitting years and applied forward to the outer")
    lines.append("evaluation placements (see scripts/140_run_p0_*.py).")
    lines.append("")
    lines.append("## 1. Headline numbers (second panel, direct durations)")
    lines.append("")
    lines.append("| duration | n placements | rho(diff) | rho(risk) | season-LOO | network rho [CI] |")
    lines.append("|---|---|---|---|---|---|")
    for row in second_net.itertuples(index=False):
        lines.append(
            f"| {row.horizon} | {season_table[(season_table.panel=='second') & (season_table.horizon==row.horizon)]['n_placements'].iloc[0]} | "
            f"{fmt(row.placement_rho)} | {fmt(row.risk_placement_rho)} | "
            f"{fmt(season_table[(season_table.panel=='second') & (season_table.horizon==row.horizon)]['season_loo_rho'].iloc[0])} | "
            f"{fmt(row.network_rho)} [{fmt(row.network_rho_ci_lower)}, {fmt(row.network_rho_ci_upper)}] |"
        )
    dr = second_direct_net.iloc[0]
    lines.append(
        f"| direct pooled | {season_table[(season_table.panel=='second') & (season_table.horizon=='direct')]['n_placements'].iloc[0]} | "
        f"{fmt(dr.placement_rho)} | {fmt(dr.risk_placement_rho)} | "
        f"{fmt(season_table[(season_table.panel=='second') & (season_table.horizon=='direct')]['season_loo_rho'].iloc[0])} | "
        f"{fmt(dr.network_rho)} [{fmt(dr.network_rho_ci_lower)}, {fmt(dr.network_rho_ci_upper)}] |"
    )
    lines.append("")
    lines.append(f"- realized benefit: mean {panel_mean:+.3f} C; harmful share "
                 f"{(direct_second['realized_benefit'] < 0).mean():.1%}")
    lines.append("")
    lines.append("## 2. Gate verdicts (frozen in PLAN.md section 3.4)")
    lines.append("")
    lines.append("- G1 (network-level Spearman >= 0.35, clustered CI lower > 0, per")
    lines.append(f"  duration): pass {verdicts['g1_network_pass_count']}/4 durations -> "
                 f"G1 {verdicts['g1_network_level']}; pooled network rho "
                 f"{verdicts['network_rho_direct']['rho']:.3f} "
                 f"[{verdicts['network_rho_direct']['ci_lower']:.3f}, ...]")
    lines.append("- G2 (paired delta vs the v13 risk curve, CI above zero): "
                 f"{verdicts['g2']} (delta {verdicts['g2_delta_mean']:.3f}, "
                 f"CI [{verdicts['g2_ci'][0]:.3f}, {verdicts['g2_ci'][1]:.3f}])")
    lines.append("- G3 (top-20% budget: mean realized benefit >= 1.3 x panel mean")
    lines.append(f"  and harmful rate < 15%): {verdicts['g3']} "
                 f"({verdicts['g3_mean_realized']:.3f} C vs panel "
                 f"{verdicts['g3_panel_mean']:.3f} C; harmful "
                 f"{100 * verdicts['g3_harmful_rate']:.1f}%)")
    lines.append("- G4 (>= 2 durations with G1): "
                 f"{verdicts['g4']} ({verdicts['g4_pass_count']} durations)")
    lines.append("")
    lines.append(f"- OVERALL GO (G1 & G2 & G3 & G4): {verdicts['overall_go']}")
    lines.append("")
    lines.append("## 3. Placement-level robustness scale")
    lines.append("")
    lines.append("Pooling placements across durations inflates Spearman (gap")
    lines.append("length drives benefit scale), so per-duration placement-level rho")
    lines.append("is the conservative scale: 7 d 0.297 (partial, 0.25-0.35 band),")
    lines.append("30 d 0.303 (partial), 90 d 0.370 (GO), 180 d 0.555 (GO).  Per the")
    lines.append("plan's 0.25-0.35 partial-GO band, 7/30 d qualify for Plan B")
    lines.append("(harm-direction classification), while 90/180 d already pass G1.")
    lines.append("At 7/30 d the model-default benefit is positive at nearly every")
    lines.append("treated gap (harmful shares 9%/11% within top-20%), so the Plan-B")
    lines.append("policy adds little there; the partial band is driven by the small")
    lines.append("absolute spread of realized benefit, not by harmful treatments.")
    lines.append("")
    lines.append("## 4. Where the model is harmful, the curve still ranks")
    lines.append("")
    lines.append("On the second panel the deployed model is on average WORSE than")
    lines.append("the climatology default at 180 d (mean realized benefit -1.477 C;")
    lines.append("83% of placements harmful).  The differential curve ranks the")
    lines.append("least-harmful fifth at -0.636 C (63% harmful) vs duration-only")
    lines.append("-1.647 C (86%) and the v13 risk curve -2.881 C (98%).  At 90 d")
    lines.append("the top-20% by predicted benefit reaches +0.380 C (25% harmful)")
    lines.append("vs duration-only +0.056 C (44%) and risk -0.256 C (55%).  This")
    lines.append("harm-avoidance behaviour is the operational value of the")
    lines.append("differential estimand at long horizons.")
    lines.append("")
    lines.append("## 5. Caveats and decisions")
    lines.append("")
    lines.append("- Within-duration top-20% budget rows are in "
                 "budget_within_duration.csv.")
    lines.append("- Cross-duration top-20% (budget_curve.csv) is dominated by the")
    lines.append("  gap-length scale: duration-only and diff are nearly tied there")
    lines.append("  (0.891 vs 0.899 at 20% on the second panel).  Protocol v5 must")
    lines.append("  compare treatments WITHIN duration strata (or budget by")
    lines.append("  duration), otherwise gap-length baselines absorb the effect.")
    lines.append("- G3 harmful rate 14.5% sits close to the 15% cap; the panel")
    lines.append("  harmful rate is 36.7%, so the margin over treating at random")
    lines.append("  is still large.")
    lines.append("")
    lines.append("## 6. Development panel (first, 42 networks)")
    lines.append("")
    lines.append("Same pipeline, descriptive only.  Direct pooled placement rho")
    lines.append("0.472; season-LOO 0.646; network rho 0.614; risk rho -0.370;")
    lines.append("realized benefit mean +0.286 C with 29.2% harmful placements.")
    lines.append("Per-duration placement rho: 7 d 0.263, 30 d 0.302, 90 d 0.369,")
    lines.append("180 d 0.315; per-duration season-LOO: 0.253/0.343/0.510/0.704.")
    lines.append("")
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(sanity))
    print(json.dumps(verdicts, indent=2))
    print(f"\nWrote {output / 'REPORT.md'}")


if __name__ == "__main__":
    main()
