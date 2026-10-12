#!/usr/bin/env python3
"""Run the v14 P0 differential stress test on both scored panels.

The experiment answers whether a fitting-period "incremental benefit"
curve -- benefit = MAE(default handling) - MAE(model), built and scored
strictly inside the fitting years -- ranks which data gaps are worth
reconstructing when applied forward to the outer evaluation years.

Archived inputs (no model refits are needed):
  * fitting-period model losses (inner year split), placement-level:
      first  panel: results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv
      second panel: results/revision_v12/t02_support_hierarchy/agent_a/second_fit_losses.csv
  * outer evaluation placements with realized model and climatology MAE:
      results/development_v11/route_a_confirmation/placement_losses.csv
      results/development_v11/second_confirmation/scoring/placement_losses.csv
  * daily temperature panels per network.

The default handlers (climatology, linear interpolation) are scored by
replaying the archived inner-fit geometry, so model and default sides are
paired by construction.  G1-G4 verdicts follow paper_archived/v14_plan/PLAN.md §3.4
and are frozen here; no thresholds are relaxed after the fact.

Outputs (results/v14/p0_differential/):
  differential_fitting_losses_{first,second}.csv   (benefit frame, climatology default)
  differential_fitting_losses_{first,second}_{handler}.csv
  placement_predictions_{first,second}.csv
  unit_predictions_{first,second}.csv
  metrics_by_horizon.csv
  paired_bootstrap.csv
  budget_curve.csv
  gates.json
  REPORT.md
"""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    read_temperature_panel,
)
from stream_recoverability.experiments.differential_stress import (  # noqa: E402
    DEFAULT_HANDLERS,
    default_handling_losses_from_fit_rows,
    differential_fitting_losses,
    r6_differential_predictions,
)
from stream_recoverability.experiments.recovery_roster import (  # noqa: E402
    empirical_transfer_predictions,
    season_label,
)

OUTPUT = ROOT / "results" / "v14" / "p0_differential"
DIRECT_GAPS = (7, 14, 30, 60, 90, 180)  # round-2 revision: 14/60 d fitted (W2-A)
BOOTSTRAP_REPEATS = 2000
BOOTSTRAP_SEED = 20260903

FIRST_MODEL_LOSSES = (
    ROOT
    / "results"
    / "v14"
    / "p0_differential"
    / "fit_losses_extended_first.csv"
)
SECOND_MODEL_LOSSES = (
    ROOT
    / "results"
    / "v14"
    / "p0_differential"
    / "fit_losses_extended_second.csv"
)
FIRST_PLACEMENTS = (
    ROOT / "results" / "development_v11" / "route_a_confirmation" / "placement_losses.csv"
)
SECOND_PLACEMENTS = (
    ROOT
    / "results"
    / "development_v11"
    / "second_confirmation"
    / "scoring"
    / "placement_losses.csv"
)
FIRST_PANEL_DIR = (
    ROOT / "results" / "development_v11" / "confirmation_daily_qc" / "networks"
)
SECOND_PANEL_DIR = (
    ROOT / "results" / "development_v11" / "second_confirmation" / "daily_qc" / "networks"
)

_CONTEXT: dict[str, object] = {}


def panel_path_for(network_id: str) -> Path | None:
    first = FIRST_PANEL_DIR / network_id / "daily_wide_temperature.csv"
    if first.is_file():
        return first
    second = SECOND_PANEL_DIR / network_id / "daily_wide_temperature.csv"
    if second.is_file():
        return second
    return None


def _network_panel(network_id: str) -> pd.DataFrame:
    path = panel_path_for(network_id)
    if path is None:
        raise FileNotFoundError(f"no temperature panel for {network_id}")
    return read_temperature_panel(str(path))


def _worker_default_losses(network_id: str) -> dict[str, pd.DataFrame]:
    panel = _network_panel(str(network_id))
    fit = _CONTEXT["fit_losses"]
    return {
        handler: default_handling_losses_from_fit_rows(
            str(network_id), panel, fit, handler=handler
        )
        for handler in DEFAULT_HANDLERS
    }


def _mean_rho(a: pd.Series, b: pd.Series) -> float:
    mask = a.notna() & b.notna()
    if int(mask.sum()) < 3:
        return float("nan")
    statistic = spearmanr(a[mask], b[mask]).statistic
    return float(statistic)


def _cluster_bootstrap_delta(
    frame: pd.DataFrame,
    networks: pd.Series,
    method_a: str,
    method_b: str | None,
    target: str,
    *,
    repeats: int,
    seed: int,
) -> dict[str, float]:
    """Network-cluster paired bootstrap of rho(method, target) differences.

    Each draw resamples networks with replacement and computes the pooled
    placement-level Spearman for method_a (minus method_b when given) against
    the realized target.
    """

    rng = np.random.default_rng(seed)
    net_ids = networks.to_numpy(dtype=object)
    columns = {name: frame[name].to_numpy(dtype=float) for name in (method_a, target)}
    if method_b is not None:
        columns[method_b] = frame[method_b].to_numpy(dtype=float)
    row_network = frame["network_id"].to_numpy(dtype=object)
    deltas: list[float] = []
    for _ in range(repeats):
        chosen = rng.choice(len(net_ids), size=len(net_ids), replace=True)
        in_draw = np.isin(row_network, net_ids[chosen])
        a = columns[method_a][in_draw]
        t = columns[target][in_draw]
        valid = np.isfinite(a) & np.isfinite(t)
        if int(valid.sum()) < 3:
            continue
        rho_a = float(
            spearmanr(a[valid], t[valid]).statistic
        )
        if method_b is None:
            deltas.append(rho_a)
            continue
        b = columns[method_b][in_draw]
        valid = valid & np.isfinite(b)
        if int(valid.sum()) < 3:
            continue
        rho_b = float(spearmanr(b[valid], t[valid]).statistic)
        deltas.append(rho_a - rho_b)
    deltas = np.asarray(deltas)
    if len(deltas) < 200:
        raise RuntimeError(f"too few valid bootstrap draws ({len(deltas)})")
    return {
        "mean": float(deltas.mean()),
        "ci_lower": float(np.percentile(deltas, 2.5)),
        "ci_upper": float(np.percentile(deltas, 97.5)),
        "frac_gt0": float((deltas > 0).mean()),
        "n_draws": int(len(deltas)),
    }


def _budget_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    budgets = (0.10, 0.20, 0.30)
    predictors = {
        "diff": "diff_prediction",
        "risk": "risk_prediction",
        "duration": "duration_only_prediction",
        "r6_diff": "r6_diff_prediction",
        "default_difficulty": "default_difficulty_prediction",
        "loo_upper": "loo_benefit_upper",
    }
    rng = np.random.default_rng(0)
    total = len(frame)
    panel_mean = float(frame["realized_benefit"].mean())
    for fraction in budgets:
        count = max(1, round(total * fraction))
        for name, column in predictors.items():
            valid = frame.loc[frame[column].notna()]
            if len(valid) < count:
                continue
            selected = valid.nlargest(count, column)
            rows.append(
                {
                    "budget": fraction,
                    "predictor": name,
                    "n": int(len(selected)),
                    "mean_realized_benefit": float(selected["realized_benefit"].mean()),
                    "harmful_rate": float((selected["realized_benefit"] < 0).mean()),
                    "mean_gain_over_panel": float(
                        selected["realized_benefit"].mean() / panel_mean
                    )
                    if panel_mean != 0.0
                    else float("nan"),
                }
            )
        random_means: list[float] = []
        random_harmful: list[float] = []
        for _ in range(100):
            chosen = rng.choice(total, size=count, replace=False)
            sample = frame["realized_benefit"].iloc[chosen]
            random_means.append(float(sample.mean()))
            random_harmful.append(float((sample < 0).mean()))
        rows.append(
            {
                "budget": fraction,
                "predictor": "random",
                "n": count,
                "mean_realized_benefit": float(np.mean(random_means)),
                "harmful_rate": float(np.mean(random_harmful)),
                "mean_gain_over_panel": float(np.mean(random_means) / panel_mean)
                if panel_mean != 0.0
                else float("nan"),
            }
        )
        oracle = frame.nlargest(count, "realized_benefit")
        rows.append(
            {
                "budget": fraction,
                "predictor": "oracle",
                "n": int(len(oracle)),
                "mean_realized_benefit": float(oracle["realized_benefit"].mean()),
                "harmful_rate": float((oracle["realized_benefit"] < 0).mean()),
                "mean_gain_over_panel": float(
                    oracle["realized_benefit"].mean() / panel_mean
                )
                if panel_mean != 0.0
                else float("nan"),
            }
        )
    return rows


def _gates(
    second_direct: pd.DataFrame,
    metrics: pd.DataFrame,
    paired: pd.DataFrame,
    budget: pd.DataFrame,
) -> dict[str, object]:
    verdicts: dict[str, object] = {}

    def duration_row(duration: int) -> pd.Series | None:
        match = metrics[
            (metrics["panel"] == "second")
            & (metrics["horizon"] == duration)
            & (metrics["level"] == "placement_pooled")
        ]
        return match.iloc[0] if len(match) else None

    g1_pass_count = 0
    per_duration: dict[str, object] = {}
    for duration in DIRECT_GAPS:
        row = duration_row(int(duration))
        record: dict[str, object] = {
            "rho": None,
            "ci_lower": None,
            "pass_g1": False,
        }
        if row is not None:
            record = {
                "rho": float(row["diff_rho"]),
                "ci_lower": float(row["diff_ci_lower"]),
                "pass_g1": bool(
                    row["diff_rho"] >= 0.35 and row["diff_ci_lower"] > 0.0
                ),
            }
            if record["pass_g1"]:
                g1_pass_count += 1
        per_duration[str(duration)] = record
    verdicts["g4_at_least_two_durations"] = g1_pass_count >= 2
    verdicts["g4_pass_count"] = g1_pass_count

    second_paired = paired[
        (paired["panel"] == "second")
        & (paired["level"] == "placement_pooled")
        & (paired["comparator"] == "risk")
    ]
    verdicts["g2"] = (
        bool(len(second_paired))
        and bool((second_paired["ci_lower"] > 0).iloc[0])
    )
    top20 = budget[
        (budget["panel"] == "second")
        & (budget["predictor"] == "diff")
        & np.isclose(budget["budget"], 0.20)
    ]
    panel_mean = float(second_direct["realized_benefit"].mean())
    if len(top20):
        g3 = bool(
            top20["mean_realized_benefit"].iloc[0] >= 1.3 * panel_mean
            and top20["harmful_rate"].iloc[0] < 0.15
        )
        verdicts["g3"] = g3
        verdicts["g3_mean_realized"] = float(top20["mean_realized_benefit"].iloc[0])
        verdicts["g3_panel_mean"] = panel_mean
        verdicts["g3_gain_over_panel"] = float(
            top20["mean_realized_benefit"].iloc[0] / panel_mean
            if panel_mean != 0.0
            else float("nan")
        )
        verdicts["g3_harmful_rate"] = float(top20["harmful_rate"].iloc[0])
    else:
        verdicts["g3"] = False
    verdicts["per_duration"] = per_duration
    return verdicts


def run_panel(
    panel: str,
    output: Path,
    *,
    workers: int,
    write_intermediates: bool,
) -> pd.DataFrame:
    model_losses_path = FIRST_MODEL_LOSSES if panel == "first" else SECOND_MODEL_LOSSES
    placements_path = FIRST_PLACEMENTS if panel == "first" else SECOND_PLACEMENTS
    # Station ids may carry leading zeros (e.g. USGS 01425000): read as
    # strings or int coercion silently drops them and stations fail to join
    # their daily panels.
    id_dtype = {"network_id": str, "station_id": str}
    fit_losses = pd.read_csv(model_losses_path, dtype=id_dtype)
    placements = pd.read_csv(
        placements_path, dtype=id_dtype, parse_dates=["gap_start"]
    )
    placements = placements.loc[
        placements["information_condition"].eq("B_union_D")
    ].copy()
    _CONTEXT["fit_losses"] = fit_losses

    networks = sorted(fit_losses["network_id"].astype(str).unique())
    missing = [n for n in networks if panel_path_for(n) is None]
    if missing:
        raise FileNotFoundError(f"missing panels for {len(missing)} networks: {missing[:5]}")

    default_frames: dict[str, pd.DataFrame] = {h: [] for h in DEFAULT_HANDLERS}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for network_id, result in zip(
            networks, pool.map(_worker_default_losses, networks)
        ):
            for handler in DEFAULT_HANDLERS:
                frame = result[handler]
                print(
                    f"[{panel}] {network_id}: default_{handler} rows {len(frame)}",
                    flush=True,
                )
                default_frames[handler].append(frame)
    for handler in DEFAULT_HANDLERS:
        default_frames[handler] = pd.concat(default_frames[handler], ignore_index=True)

    differential = differential_fitting_losses(fit_losses, default_frames["climatology"])
    print(
        f"[{panel}] differential rows {len(differential)} of {len(fit_losses)} model rows",
        flush=True,
    )
    if write_intermediates:
        for handler in DEFAULT_HANDLERS:
            path = output / f"differential_fitting_losses_{panel}_{handler}.csv"
            default_frames[handler].to_csv(path, index=False)
        differential.to_csv(output / f"differential_fitting_losses_{panel}.csv", index=False)

    evaluations = placements.copy()
    evaluations["season"] = season_label(evaluations["gap_start"])
    evaluations["realized_benefit"] = (
        evaluations["climatology_mae_deg_c"] - evaluations["mae_deg_c"]
    )
    evaluations = evaluations.merge(
        empirical_transfer_predictions(differential, evaluations)[
            [
                "network_id",
                "station_id",
                "gap_length",
                "placement",
                "empirical_transfer_prediction",
                "empirical_transfer_source",
                "empirical_transfer_supported",
            ]
        ].rename(
            columns={
                "empirical_transfer_prediction": "diff_prediction",
                "empirical_transfer_source": "diff_source",
                "empirical_transfer_supported": "diff_supported",
            }
        ),
        on=["network_id", "station_id", "gap_length", "placement"],
        how="left",
    )
    evaluations = evaluations.merge(
        empirical_transfer_predictions(fit_losses, evaluations)[
            [
                "network_id",
                "station_id",
                "gap_length",
                "placement",
                "empirical_transfer_prediction",
            ]
        ].rename(columns={"empirical_transfer_prediction": "risk_prediction"}),
        on=["network_id", "station_id", "gap_length", "placement"],
        how="left",
    )
    evaluations = evaluations.merge(
        empirical_transfer_predictions(default_frames["climatology"], evaluations)[
            [
                "network_id",
                "station_id",
                "gap_length",
                "placement",
                "empirical_transfer_prediction",
            ]
        ].rename(
            columns={"empirical_transfer_prediction": "default_difficulty_prediction"}
        ),
        on=["network_id", "station_id", "gap_length", "placement"],
        how="left",
    )
    evaluations = r6_differential_predictions(differential, evaluations)

    duration_curve = (
        differential.groupby("gap_length", as_index=False)["mae_deg_c"]
        .mean()
        .rename(columns={"mae_deg_c": "duration_mean"})
    )
    evaluations["gap_length_int"] = evaluations["gap_length"].astype(int)
    evaluations = evaluations.merge(
        duration_curve.rename(columns={"gap_length": "gap_length_int"}),
        on="gap_length_int",
        how="left",
    )
    evaluations["duration_only_prediction"] = evaluations["duration_mean"]
    evaluations = evaluations.drop(columns=["gap_length_int", "duration_mean"])

    loo_key = ["station_id", "gap_length"]
    group = evaluations.groupby(loo_key)["realized_benefit"]
    evaluations["loo_benefit_upper"] = (group.transform("sum") - evaluations["realized_benefit"]) / (
        group.transform("count") - 1
    )
    evaluations["loo_benefit_upper"] = evaluations["loo_benefit_upper"].replace(
        [np.inf, -np.inf], np.nan
    )
    evaluations["direct"] = evaluations["gap_length"].isin(DIRECT_GAPS)

    placements_out = evaluations[
        [
            "network_id",
            "station_id",
            "gap_length",
            "season",
            "placement",
            "gap_start",
            "direct",
            "realized_benefit",
            "diff_prediction",
            "risk_prediction",
            "duration_only_prediction",
            "r6_diff_prediction",
            "default_difficulty_prediction",
            "loo_benefit_upper",
            "diff_source",
            "diff_supported",
        ]
    ].copy()
    placements_out.to_csv(output / f"placement_predictions_{panel}.csv", index=False)

    unit = (
        placements_out.groupby(
            ["network_id", "station_id", "gap_length"], as_index=False
        )
        .agg(
            n_placements=("placement", "size"),
            direct=("direct", "first"),
            realized_benefit=("realized_benefit", "mean"),
            diff_prediction=("diff_prediction", "mean"),
            risk_prediction=("risk_prediction", "mean"),
            duration_only_prediction=("duration_only_prediction", "mean"),
            r6_diff_prediction=("r6_diff_prediction", "mean"),
            default_difficulty_prediction=("default_difficulty_prediction", "mean"),
            loo_benefit_upper=("loo_benefit_upper", "mean"),
            diff_supported=("diff_supported", "first"),
        )
        .reset_index(drop=True)
    )
    unit.to_csv(output / f"unit_predictions_{panel}.csv", index=False)
    return placements_out


def compute_metrics(
    panel: str, placements_out: pd.DataFrame, output: Path
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    direct = placements_out.loc[placements_out["direct"]]
    unit = pd.read_csv(output / f"unit_predictions_{panel}.csv")
    unit_direct = unit.loc[unit["direct"]]

    for duration in DIRECT_GAPS:
        per_duration = direct.loc[direct["gap_length"] == duration]
        unit_duration = unit_direct.loc[unit_direct["gap_length"] == duration]
        if not len(per_duration):
            continue
        boot = _cluster_bootstrap_delta(
            per_duration,
            per_duration["network_id"].drop_duplicates(),
            "diff_prediction",
            None,
            "realized_benefit",
            repeats=BOOTSTRAP_REPEATS,
            seed=BOOTSTRAP_SEED,
        )
        rho_risk = _mean_rho(per_duration["risk_prediction"], per_duration["realized_benefit"])
        rho_unit = _mean_rho(unit_duration["diff_prediction"], unit_duration["realized_benefit"])
        rows.append(
            {
                "panel": panel,
                "horizon": int(duration),
                "level": "placement_pooled",
                "n_placements": int(len(per_duration)),
                "n_units": int(len(unit_duration)),
                "diff_rho": float(boot["mean"]),
                "diff_ci_lower": float(boot["ci_lower"]),
                "diff_ci_upper": float(boot["ci_upper"]),
                "risk_rho": rho_risk,
                "unit_pooled_rho": rho_unit,
            }
        )

    direct_boot = _cluster_bootstrap_delta(
        direct,
        direct["network_id"].drop_duplicates(),
        "diff_prediction",
        None,
        "realized_benefit",
        repeats=BOOTSTRAP_REPEATS,
        seed=BOOTSTRAP_SEED,
    )
    net_means = (
        direct.groupby("network_id", as_index=False)
        .agg(
            predicted=("diff_prediction", "mean"),
            realized=("realized_benefit", "mean"),
        )
        .dropna()
    )
    network_rho = _mean_rho(net_means["predicted"], net_means["realized"])
    rows.append(
        {
            "panel": panel,
            "horizon": "direct",
            "level": "placement_pooled",
            "n_placements": int(len(direct)),
            "n_units": int(len(unit_direct)),
            "diff_rho": float(direct_boot["mean"]),
            "diff_ci_lower": float(direct_boot["ci_lower"]),
            "diff_ci_upper": float(direct_boot["ci_upper"]),
            "risk_rho": _mean_rho(direct["risk_prediction"], direct["realized_benefit"]),
            "unit_pooled_rho": _mean_rho(
                unit_direct["diff_prediction"], unit_direct["realized_benefit"]
            ),
            "network_rho": network_rho,
        }
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--panels", default="first,second", help="comma-separated: first,second"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--bootstrap-repeats", type=int, default=BOOTSTRAP_REPEATS)
    parser.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    placement_tables: dict[str, pd.DataFrame] = {}
    for panel in (value.strip() for value in args.panels.split(",")):
        done_marker = output / f"placement_predictions_{panel}.csv"
        if args.skip_existing and done_marker.is_file():
            print(f"[{panel}] outputs exist; skipping (--skip-existing)", flush=True)
            placement_tables[panel] = pd.read_csv(
                done_marker, parse_dates=["gap_start"]
            )
            continue
        placement_tables[panel] = run_panel(
            panel,
            output,
            workers=args.workers,
            write_intermediates=True,
        )

    metric_rows: list[dict[str, object]] = []
    for panel, placements_out in placement_tables.items():
        metric_rows.extend(compute_metrics(panel, placements_out, output))
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(output / "metrics_by_horizon.csv", index=False)

    bootstrap_rows: list[dict[str, object]] = []
    for panel, placements_out in placement_tables.items():
        direct = placements_out.loc[placements_out["direct"]]
        for comparator in [
            "risk_prediction",
            "duration_only_prediction",
            "r6_diff_prediction",
            "default_difficulty_prediction",
        ]:
            boot = _cluster_bootstrap_delta(
                direct,
                direct["network_id"].drop_duplicates(),
                "diff_prediction",
                comparator,
                "realized_benefit",
                repeats=args.bootstrap_repeats,
                seed=args.seed + 1,
            )
            bootstrap_rows.append(
                {
                    "panel": panel,
                    "level": "placement_pooled",
                    "comparator": comparator.removesuffix("_prediction"),
                    **boot,
                }
            )
    paired = pd.DataFrame(bootstrap_rows)
    paired.to_csv(output / "paired_bootstrap.csv", index=False)

    budget_rows: list[dict[str, object]] = []
    for panel, placements_out in placement_tables.items():
        direct = placements_out.loc[placements_out["direct"]]
        for row in _budget_rows(direct):
            budget_rows.append({"panel": panel, **row})
    budget = pd.DataFrame(budget_rows)
    budget.to_csv(output / "budget_curve.csv", index=False)

    if "second" in placement_tables:
        second_direct = placement_tables["second"].loc[
            placement_tables["second"]["direct"]
        ]
        gates = _gates(second_direct, metrics, paired, budget)
    else:
        gates = {}
    (output / "gates.json").write_text(
        json.dumps(gates, indent=2, default=str) + "\n", encoding="utf-8"
    )

    report_path = output / "REPORT.md"
    lines = [
        "# v14 P0: differential stress test",
        "",
        "## Setup",
        "",
        "Benefit = MAE(default handling) - MAE(model), per placement.  The",
        "benefit curve is built exclusively inside the inner fitting years",
        "(station x duration x season means with the standard four-level",
        "fallback) and applied forward to the outer evaluation placements.",
        "Realized benefit on evaluation placements uses the climatology",
        "default estimated on the outer training years (archived placement",
        "tables).  Gates follow paper_archived/v14_plan/PLAN.md section 3.4; all",
        "thresholds were frozen before this run.",
        "",
    ]
    for panel in placement_tables:
        table = placement_tables[panel].loc[placement_tables[panel]["direct"]]
        unit = pd.read_csv(output / f"unit_predictions_{panel}.csv")
        lines.append(f"## Panel {panel}")
        lines.append("")
        lines.append(
            f"- direct placements: {len(table)}; networks: "
            f"{table['network_id'].nunique()}; direct units: "
            f"{int((unit['direct']).sum())}"
        )
        lines.append(
            f"- pooled placement rho(diff, realized): "
            f"{_mean_rho(table['diff_prediction'], table['realized_benefit']):.3f} "
            f"(LOO upper bound: "
            f"{_mean_rho(table['loo_benefit_upper'], table['realized_benefit']):.3f})"
        )
        lines.append(
            f"- pooled placement rho(risk, realized): "
            f"{_mean_rho(table['risk_prediction'], table['realized_benefit']):.3f}"
        )
        lines.append(
            f"- realized benefit: mean {table['realized_benefit'].mean():+.3f} C, "
            f"harmful share {(table['realized_benefit'] < 0).mean():.1%}"
        )
        lines.append("")
    lines.append("## Gate verdicts (second panel, direct durations 7/14/30/60/90/180)")
    lines.append("")
    if gates:
        lines.append("G1 (per-duration placement-level rho >= 0.35 with clustered")
        lines.append("CI lower bound > 0) and G4 (>= 2 durations) are judged from")
        lines.append("the metrics table; G2 uses the paired risk delta; G3 uses")
        lines.append("the top-20% budget row.")
        lines.append("")
        for key in ("g2", "g3", "g4_at_least_two_durations"):
            lines.append(f"- {key}: {gates.get(key)}")
        per = gates.get("per_duration", {})
        lines.append("")
        lines.append("| duration | rho | CI lower | G1 pass |")
        lines.append("|---|---|---|---|")
        for duration, record in per.items():
            lines.append(
                f"| {duration} | {record.get('rho'):.3f} | "
                f"{record.get('ci_lower'):.3f} | {record.get('pass_g1')} |"
            )
        lines.append("")
        lines.append("Interpretation per PLAN.md section 3.5: rho >= 0.35 with CI")
        lines.append("lower bound above zero = GO on that duration; 0.25-0.35 =")
        lines.append("partial GO (Plan B: harm-direction classification).")
    else:
        lines.append("second panel not run; no gates evaluated.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {report_path}", flush=True)
    print((output / "gates.json").read_text(), flush=True)
    manifest_path = output / "run_manifest.json"
    if manifest_path.is_file():
        manifest_path.unlink()
    shutil.copy(Path(__file__), output / "run_script_140.py")
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
