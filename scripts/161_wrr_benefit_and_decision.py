#!/usr/bin/env python3
"""Steps 3–4: benefit predictors and calibrated adopt/reject vs all-default.

Runs immediately on archived v14 P0 tables (current recoverer) and, when
present, on Step-2 fair-recovery scores for each new recoverer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.recovery_roster import season_label  # noqa: E402
from stream_recoverability.experiments.wrr_revision.benefit import (  # noqa: E402
    apply_switch,
    attach_component_predictors,
    difference_identity_gap,
    history_switch_rule,
    predictor_columns,
    ridge_benefit_predictor,
)
from stream_recoverability.experiments.wrr_revision.decision import (  # noqa: E402
    cell_lower_quantile,
    choose_tau,
    evaluate_rules,
    reliability_table,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_FIT_LOSSES,
    P0_FIRST,
    P0_SECOND,
    RESULTS_ROOT,
)

OUTPUT = RESULTS_ROOT / "step3_4_decision"
HIST_FIRST = ROOT / "results" / "v14" / "p0_differential" / "differential_fitting_losses_first.csv"
HIST_SECOND = ROOT / "results" / "v14" / "p0_differential" / "differential_fitting_losses_second.csv"


def normalize_loss_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "model_mae_deg_c" in out.columns:
        out["mae_deg_c"] = out["model_mae_deg_c"]
    if "default_mae_deg_c" in out.columns:
        out["climatology_mae_deg_c"] = out["default_mae_deg_c"]
    if (
        "realized_benefit" not in out.columns
        and "mae_deg_c" in out.columns
        and "climatology_mae_deg_c" in out.columns
    ):
        out["realized_benefit"] = out["climatology_mae_deg_c"] - out["mae_deg_c"]
    if "season" not in out.columns and "gap_start" in out.columns:
        out["season"] = season_label(out["gap_start"])
    return out


def _load_p0(path: Path, panel: str) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["gap_start"])
    frame["panel"] = panel
    return normalize_loss_frame(frame)


def _history(panel: str) -> pd.DataFrame:
    path = HIST_FIRST if panel == "first" else HIST_SECOND
    if path.exists():
        return normalize_loss_frame(pd.read_csv(path, parse_dates=["gap_start"]))
    return normalize_loss_frame(pd.read_csv(FIRST_FIT_LOSSES, parse_dates=["gap_start"]))


def _ensure_realized(frame: pd.DataFrame, realized_col: str = "realized_benefit") -> pd.DataFrame:
    out = normalize_loss_frame(frame)
    if realized_col in out.columns and realized_col != "realized_benefit":
        out["realized_benefit"] = out[realized_col]
    if "realized_benefit" not in out.columns:
        out["realized_benefit"] = out["climatology_mae_deg_c"] - out["mae_deg_c"]
    return out


def _supported_col(predictor: str) -> str | None:
    if predictor in {"diff_prediction", "seasonal_empirical"}:
        return "seasonal_empirical_supported"
    if predictor == "r6_diff_prediction":
        return "r6_diff_prediction_supported"
    return None


def attach_deployable_predictors(
    history: pd.DataFrame,
    target: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit predictors and the duration switch on history; score `target`."""

    hist = _ensure_realized(history)
    evaluation = _ensure_realized(target)
    attached = attach_component_predictors(hist, evaluation)
    attached["realized_benefit"] = evaluation["realized_benefit"].to_numpy()
    switch = history_switch_rule(hist)
    attached["switch_prediction"] = apply_switch(attached, switch)
    attached["ridge_covariate_prediction"] = ridge_benefit_predictor(hist, attached)
    return attached, switch


def run_panel(
    evaluation: pd.DataFrame,
    history: pd.DataFrame,
    *,
    label: str,
    realized_col: str = "realized_benefit",
) -> dict[str, object]:
    hist = _ensure_realized(history, realized_col)
    evaluation = _ensure_realized(evaluation, realized_col)
    # In-sample history scores are used only to freeze tau; evaluation is untouched.
    hist_scored, switch = attach_deployable_predictors(hist, hist)
    attached, _ = attach_deployable_predictors(hist, evaluation)
    construction_gap = difference_identity_gap(attached)
    empirical_gap = float((attached["diff_prediction"] - attached["seasonal_empirical"]).abs().max())
    attached.to_csv(OUTPUT / f"placement_predictions_{label}.csv", index=False)
    switch.to_csv(OUTPUT / f"switch_rule_{label}.csv", index=False)
    tau_rows = []
    rule_rows = []
    reliability_rows = []
    quantile = cell_lower_quantile(hist, attached)
    for predictor in predictor_columns():
        if predictor not in attached.columns:
            continue
        supported_col = _supported_col(predictor)
        hist_supported = hist_scored[supported_col] if supported_col else None
        chosen = choose_tau(
            hist_scored[predictor],
            hist_scored["realized_benefit"],
            supported=hist_supported,
        )
        chosen.update({"predictor": predictor, "panel": label, "selection": "history_max_net"})
        tau_rows.append(chosen)
        rules = evaluate_rules(
            attached,
            predicted_col=predictor,
            realized_col="realized_benefit",
            supported_col=supported_col,
            tau=float(chosen["tau"]),
            quantile=quantile,
        )
        rules["panel"] = label
        rule_rows.append(rules)
        rel = reliability_table(attached[predictor], attached["realized_benefit"])
        rel["predictor"] = predictor
        rel["panel"] = label
        reliability_rows.append(rel)
    rules_all = pd.concat(rule_rows, ignore_index=True)
    rules_all.to_csv(OUTPUT / f"policy_metrics_{label}.csv", index=False)
    pd.DataFrame(tau_rows).to_csv(OUTPUT / f"chosen_tau_{label}.csv", index=False)
    pd.concat(reliability_rows, ignore_index=True).to_csv(
        OUTPUT / f"reliability_{label}.csv", index=False
    )
    beats = rules_all.loc[
        rules_all["rule"].eq("mean_gt_tau_supported_only")
        & rules_all["predictor"].eq("diff_prediction")
    ]
    return {
        "panel": label,
        "n_eval": int(len(attached)),
        "n_history": int(len(hist_scored)),
        "diff_equals_empirical_max_abs": empirical_gap,
        "diff_construction_identity_max_abs": construction_gap,
        "diff_policy_beats_all_default": (
            float(beats["beats_all_default"].iloc[0]) if len(beats) else float("nan")
        ),
        "diff_policy_net": float(beats["net_benefit_all_cases"].iloc[0]) if len(beats) else float("nan"),
        "all_reconstruct_net": float(
            rules_all.loc[rules_all["rule"].eq("all_reconstruct"), "all_reconstruct_net"].iloc[0]
        ),
    }


def run_step2_recoverers(step2_path: Path) -> list[dict[str, object]]:
    if not step2_path.exists():
        return []
    scores = pd.read_csv(step2_path, parse_dates=["gap_start"])
    out = []
    for recoverer, group in scores.groupby("recoverer"):
        if recoverer == "doy_climatology":
            continue
        group = group.copy()
        group["realized_benefit"] = group["mae_benefit"]
        hist = group.loc[group["placement"].mod(2).eq(0)]
        ev = group.loc[group["placement"].mod(2).eq(1)]
        if hist.empty or ev.empty:
            continue
        summary = run_panel(ev, hist, label=f"step2_{recoverer}")
        summary["recoverer"] = str(recoverer)
        out.append(summary)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--step2",
        default=str(RESULTS_ROOT / "step2_fair_recovery" / "placement_scores.csv"),
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summaries = []
    if P0_FIRST.exists():
        summaries.append(
            run_panel(_load_p0(P0_FIRST, "first"), _history("first"), label="p0_first")
        )
    if P0_SECOND.exists():
        summaries.append(
            run_panel(_load_p0(P0_SECOND, "second"), _history("second"), label="p0_second")
        )
    summaries.extend(run_step2_recoverers(Path(args.step2)))
    (OUTPUT / "summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
