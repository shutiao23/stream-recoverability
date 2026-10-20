#!/usr/bin/env python3
"""P0-04 (review F05, 2026-10-20) — the environmental judgement, closed.

`scripts/324_..._hotyear.py` reported a signed, case-weighted deviation for one
fold seed and two hot thresholds.  A small signed deviation can hide two large
opposite errors, and a smaller error rate among admitted records can be bought by
refusing the hard years.  This script reports, for every pre-declared fold seed:

* the prediction term, the selection term and the total, with network-clustered
  intervals;
* the confusion matrix of the hot-year judgement on the admitted archive:
  correct hot, correct cool, false hot, missed hot;
* the records refused while true-hot (the abstention cost) and the share of all
  true hot years that survive into the archive;
* the same quantities under a unique-station-year weighting, so a station-year
  with many outage realisations cannot outvote one with few.

Population choice: the case-weighted estimate is primary (it is the archive the
agency actually holds under this monitoring design); the unique-station-year
estimate is the pre-declared sensitivity.  Both are reported for every arm.

Outputs
``results/wrr_submission_ready/major_revision_20261020/p0_04_hot_year_closure/``.

Run:

    PYTHONPATH=src python3 scripts/333_wrr_aligned_hot_year_closure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020"
ALIGNED = RUN / "p0_01_aligned_policy_admission"
REPLAY_DETAIL = RUN / "p0_03_real_calendar_adoption" / "replay_case_decisions.parquet"
OUT = RUN / "p0_04_hot_year_closure"

TOL = 0.5
SEEDS = (101, 202, 303)
ARMS = ("fitted_risk", "calibrated_bound", "peak_overlap_rule", "length_rule", "reconstruct_all")
HOT_LEVELS = (18.0, 20.0)
DRAWS = 4000
PANEL_CASES = {
    "development": ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet",
    "wave2_confirmation": ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet",
}
ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def _policy_prediction(cases: pd.DataFrame) -> np.ndarray:
    choice = cases["policy_choice"].astype(str).to_numpy()
    pred = np.full(len(cases), np.nan)
    for name in ESTIMATORS:
        mask = choice == name
        column = f"hottest30_{name}"
        if column not in cases.columns or not mask.any():
            continue
        pred[mask] = pd.to_numeric(cases.loc[mask, column], errors="coerce").to_numpy(dtype=float)
    return pred


def _station_year_weights(cases: pd.DataFrame) -> np.ndarray:
    key = cases["station_id"].astype(str) + "|" + cases["year"].astype(str)
    counts = key.map(key.value_counts()).to_numpy(dtype=float)
    return 1.0 / np.maximum(counts, 1.0)


def _per_group_sums(
    values: list[np.ndarray],
    weights: np.ndarray,
    group_codes: np.ndarray,
    n_groups: int,
) -> np.ndarray:
    return np.column_stack(
        [np.bincount(group_codes, weights=weights * value, minlength=n_groups) for value in values]
    )


def _shared_resamples(n_groups: int, *, draws: int, seed: int) -> np.ndarray:
    """One set of group resamples shared by every ratio in a row.

    Using independent draws per ratio would break the pairing between the
    admitted set and the full pool and inflate the interval of their difference.
    """

    rng = np.random.default_rng(int(seed))
    return rng.integers(0, int(n_groups), size=(int(draws), int(n_groups)))


def _ratio_draws(
    per_group_num: np.ndarray,
    per_group_den: np.ndarray,
    resamples: np.ndarray,
) -> np.ndarray:
    numerator = per_group_num[resamples].sum(axis=1)
    denominator = per_group_den[resamples].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denominator > 0, numerator / np.maximum(denominator, 1e-12), np.nan)


def _interval(values: np.ndarray) -> tuple:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def _confusion_block(
    truth_hot: np.ndarray,
    pred_hot: np.ndarray,
    admit: np.ndarray,
    usable: np.ndarray,
    weights: np.ndarray,
    group_codes: np.ndarray,
    n_groups: int,
    *,
    draws: int,
    seed: int,
) -> dict:
    """Compose one row: shares, terms, confusion counts, and intervals."""

    admit = admit & usable
    judged = admit & usable & np.isfinite(pred_hot)

    n_all = weights.sum()
    n_admitted = weights[judged].sum()
    if n_admitted <= 0:
        return {}

    true_hot_admitted = judged & truth_hot
    false_hot = judged & (~truth_hot) & pred_hot
    missed_hot = judged & truth_hot & (~pred_hot)
    correct_hot = judged & truth_hot & pred_hot
    correct_cool = judged & (~truth_hot) & (~pred_hot)
    abstained_hot = (~admit) & truth_hot

    p_full = float(weights[truth_hot].sum() / n_all)
    p_a = float(weights[true_hot_admitted].sum() / n_admitted)
    p_hat = float(weights[judged & pred_hot].sum() / n_admitted)
    p_fn = float(weights[missed_hot].sum() / n_admitted)
    p_fp = float(weights[false_hot].sum() / n_admitted)
    p_correct = float(weights[correct_hot | correct_cool].sum() / n_admitted)
    recall_hot = float(
        weights[correct_hot | missed_hot].sum() / max(weights[truth_hot].sum(), 1e-12)
    )

    terms = {
        "total_bias": weights[judged & pred_hot].sum() / n_admitted - p_full,
        "prediction_error": p_hat - p_a,
        "selection_shift": p_a - p_full,
        "correct_share": p_correct,
        "false_hot_share": p_fp,
        "missed_hot_share": p_fn,
        "true_hot_share_admitted": p_a,
        "predicted_hot_share_admitted": p_hat,
        "abstained_hot_share": float(weights[abstained_hot].sum() / max(weights[truth_hot].sum(), 1e-12)),
        "recall_hot": recall_hot,
    }

    # per-group numerators/denominators for the interval of each term
    judge = judged.astype(float)
    pred = pred_hot.astype(float)
    truth = truth_hot.astype(float)
    numer = {
        "p_hat_A": (weights * judge * pred, weights * judge),
        "p_full": (weights * truth, weights),
        "prediction_error_a": (weights * judge * pred, weights * judge),
        "prediction_error_b": (weights * judge * truth, weights * judge),
        "selection_shift_a": (weights * judge * truth, weights * judge),
        "selection_shift_b": (weights * truth, weights),
        "correct_share": (weights * judge * (pred == truth), weights * judge),
        "false_hot_share": (weights * judge * (~truth_hot & pred_hot), weights * judge),
        "missed_hot_share": (weights * judge * (truth_hot & ~pred_hot), weights * judge),
        "recall_hot": (weights * judge * truth * pred, weights * truth),
        "abstained_hot": (weights * (~admit) * truth, weights * truth),
    }
    resamples = _shared_resamples(n_groups, draws=draws, seed=seed)
    draws_table = {}
    for name, (num, den) in numer.items():
        per_num = np.bincount(group_codes, weights=num, minlength=n_groups)
        per_den = np.bincount(group_codes, weights=den, minlength=n_groups)
        draws_table[name] = _ratio_draws(per_num, per_den, resamples)
    draws_table["total_bias"] = draws_table["p_hat_A"] - draws_table["p_full"]
    for name in ("total_bias", "correct_share", "false_hot_share", "missed_hot_share", "recall_hot", "abstained_hot"):
        low, high = _interval(draws_table[name])
        terms[f"{name}_ci_low"] = low
        terms[f"{name}_ci_high"] = high
    low, high = _interval(draws_table["prediction_error_a"] - draws_table["prediction_error_b"])
    terms["prediction_error_ci_low"], terms["prediction_error_ci_high"] = low, high
    low, high = _interval(draws_table["selection_shift_a"] - draws_table["selection_shift_b"])
    terms["selection_shift_ci_low"], terms["selection_shift_ci_high"] = low, high

    return {
        "n_cases": int(admit.size),
        "n_admitted": int(judged.sum()),
        "admitted_share": float(judged.sum() / admit.size),
        "p_full": p_full,
        "p_A": p_a,
        "p_hat_A": p_hat,
        "n_true_hot_total": int(truth_hot.sum()),
        "n_correct_hot": int(correct_hot.sum()),
        "n_correct_cool": int(correct_cool.sum()),
        "n_false_hot": int(false_hot.sum()),
        "n_missed_hot": int(missed_hot.sum()),
        "n_abstained_hot": int(abstained_hot.sum()),
        **terms,
    }


def designed_panels() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for panel, path in PANEL_CASES.items():
        cases = pd.read_parquet(path).reset_index(drop=True)
        admissions_all = pd.read_parquet(
            ALIGNED / f"case_level_admissions_{panel}.parquet"
        )
        truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
        pred = _policy_prediction(cases)
        usable = np.isfinite(truth) & np.isfinite(pred)
        groups = admissions_all.loc[
            admissions_all.fold_seed.eq(SEEDS[0]), "independence_group"
        ].astype(str).to_numpy()
        units = sorted(set(groups))
        code = {unit: i for i, unit in enumerate(units)}
        group_codes = np.array([code[g] for g in groups], dtype=np.int64)
        n_groups = len(units)
        weight_sets = {
            "case": np.ones(len(cases)),
            "station_year": _station_year_weights(cases),
        }
        for seed in SEEDS:
            block = admissions_all[admissions_all.fold_seed.eq(seed)].reset_index(drop=True)
            if len(block) != len(cases):
                raise RuntimeError(f"{panel}: admissions for seed {seed} are not row-aligned")
            if not cases["network_id"].astype(str).equals(block["network_id"].astype(str)):
                raise RuntimeError(f"{panel}: admissions for seed {seed} are not row-aligned")
            for hot in HOT_LEVELS:
                truth_hot = truth > hot
                pred_hot = pred > hot
                for arm in ARMS:
                    column = f"admit_riskcap_{arm}"
                    if column not in block.columns:
                        continue
                    admit = block[column].to_numpy(dtype=bool)
                    for weighting, weights in weight_sets.items():
                        values = _confusion_block(
                            truth_hot,
                            pred_hot,
                            admit,
                            usable,
                            weights,
                            group_codes,
                            n_groups,
                            draws=DRAWS,
                            seed=17 + seed + int(hot) * 31 + len(arm) * 7 + (weighting == "case"),
                        )
                        if not values:
                            continue
                        rows.append(
                            {
                                "panel": panel,
                                "hot_c": float(hot),
                                "fold_seed": int(seed),
                                "arm": arm,
                                "weighting": weighting,
                                **values,
                            }
                        )
    return pd.DataFrame(rows), pd.DataFrame()


def replay_panel() -> pd.DataFrame:
    detail = pd.read_parquet(REPLAY_DETAIL)
    rows = []
    for (level, seed), block in detail.groupby(["level", "seed"]):
        truth = pd.to_numeric(block["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
        pred = pd.to_numeric(block["policy_metric"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(pred).any():
            raise RuntimeError("replay detail lacks the policy reconstruction")
        usable = np.isfinite(truth) & np.isfinite(pred)
        groups = block["network_id"].astype(str).to_numpy()
        units = sorted(set(groups))
        code = {unit: i for i, unit in enumerate(units)}
        group_codes = np.array([code[g] for g in groups], dtype=np.int64)
        n_groups = len(units)
        for hot in HOT_LEVELS:
            truth_hot = truth > hot
            pred_hot = pred > hot
            for arm in ARMS:
                column = f"admit_{arm}"
                if column not in block.columns:
                    continue
                admit = block[column].to_numpy(dtype=bool)
                values = _confusion_block(
                    truth_hot,
                    pred_hot,
                    admit,
                    usable,
                    np.ones(len(block)),
                    group_codes,
                    n_groups,
                    draws=DRAWS,
                    seed=5 + int(seed) + int(hot) * 13 + len(arm),
                )
                if not values:
                    continue
                rows.append(
                    {
                        "panel": f"replay_{level}",
                        "hot_c": float(hot),
                        "fold_seed": int(seed),
                        "arm": arm,
                        "weighting": "case",
                        **values,
                    }
                )
    return pd.DataFrame(rows)


def write_summary(designed: pd.DataFrame, replay: pd.DataFrame) -> None:
    lines = [
        "# The environmental judgement, closed",
        "",
        "Generated by `scripts/333_wrr_aligned_hot_year_closure.py` from the aligned",
        "admissions of `p0_01` and the aligned replay of `p0_03`. Shares are fractions;",
        "multiply by 100 for percentage points. `p_full` is the true hot-year share of the",
        "whole candidate pool, `p_A` the true share among admitted records, `p_hat_A` the",
        "share the reconstruction would report. `total = prediction + selection`.",
        "",
        "## Designed panels, case-weighted, all fold seeds",
        "",
        "| panel | hot °C | seed | arm | admitted | p_full | p_A | p_hat_A | prediction | selection | total (95%) | false hot | missed hot | refused hot |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    block = designed[designed.weighting.eq("case")]
    for panel in ("wave2_confirmation", "development"):
        for row in block[block.panel.eq(panel)].itertuples(index=False):
            lines.append(
                f"| {panel} | {row.hot_c:.0f} | {row.fold_seed} | {row.arm} | "
                f"{row.admitted_share:.3f} | {row.p_full:.3f} | {row.p_A:.3f} | {row.p_hat_A:.3f} | "
                f"{row.prediction_error:+.4f} | {row.selection_shift:+.4f} | "
                f"{row.total_bias:+.4f} [{row.total_bias_ci_low:+.4f}, {row.total_bias_ci_high:+.4f}] | "
                f"{row.n_false_hot} | {row.n_missed_hot} | {row.n_abstained_hot} |"
            )
    lines.extend(
        [
            "",
            "## Unique-station-year sensitivity (wave-2, 20 °C)",
            "",
            "| seed | arm | p_A | selection | total | false hot | missed hot |",
            "|---:|---|---:|---:|---|---:|---:|",
        ]
    )
    sensitivity = designed[
        designed.weighting.eq("station_year")
        & designed.panel.eq("wave2_confirmation")
        & designed.hot_c.eq(20.0)
    ]
    for row in sensitivity.itertuples(index=False):
        lines.append(
            f"| {row.fold_seed} | {row.arm} | {row.p_A:.3f} | {row.selection_shift:+.4f} | "
            f"{row.total_bias:+.4f} | {row.n_false_hot} | {row.n_missed_hot} |"
        )
    if not replay.empty:
        lines.extend(
            [
                "",
                "## Real-calendar replay",
                "",
                "| panel | hot °C | seed | arm | admitted | p_A | p_hat_A | total | false hot | refused hot |",
                "|---|---:|---:|---|---:|---:|---:|---|---:|---:|",
            ]
        )
        for row in replay.itertuples(index=False):
            lines.append(
                f"| {row.panel} | {row.hot_c:.0f} | {row.fold_seed} | {row.arm} | "
                f"{row.admitted_share:.3f} | {row.p_A:.3f} | {row.p_hat_A:.3f} | "
                f"{row.total_bias:+.4f} | {row.n_false_hot} | {row.n_abstained_hot} |"
            )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- A near-zero signed total is compatible with a large false-hot and a large",
            "  missed-hot count that cancel. The confusion columns are the part of the",
            "  table that cannot cancel.",
            "- `refused hot` is the abstention cost: years that were hot but left the",
            "  archive. A screen that lowers the error rate among admitted records while",
            "  raising this column has bought precision with coverage of the very years",
            "  the analysis is about.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    designed, _ = designed_panels()
    replay = replay_panel()
    designed.to_csv(OUT / "hot_year_designed.csv", index=False)
    replay.to_csv(OUT / "hot_year_replay.csv", index=False)
    write_summary(designed, replay)
    metadata = {
        "hot_levels_c": list(HOT_LEVELS),
        "fold_seeds": list(SEEDS),
        "arms": list(ARMS),
        "bootstrap_draws": DRAWS,
        "primary_population": "case-weighted",
        "sensitivity_population": "unique station-year (each station-year total weight 1)",
        "confusion_definition": (
            "judgement = admitted AND reconstructed hottest-30 > hot threshold; "
            "false hot = judged hot but true cool; missed hot = judged cool but true hot; "
            "refused hot = not admitted and true hot"
        ),
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
