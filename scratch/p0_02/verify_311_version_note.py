#!/usr/bin/env python3
"""Version-note evidence for script 311 (scratch only, not a deliverable).

Reproduces the FIRST-pass `length_rule` behaviour, which used a jitter scaled by
the score spread (`longest_run + U[0, spread)` = `longest_run + U[0, 301)` days),
and contrasts it with the corrected score (`longest_run + U[0, 1)` day, exactly as
scripts 301/305 build it).  Also prints the orientation evidence: admitted share
and false-admit rate as a function of the raw gap-length cut-off, for both sort
directions.

Writes scratch/p0_02/version_note_evidence.json.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location(
    "m311", ROOT / "scripts" / "311_wrr_p0_02_frozen_risk_thresholds.py"
)
m311 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m311)
m311.M301 = m311.load_script_module("m301", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py")
m311.M305 = m311.load_script_module("m305", ROOT / "scripts" / "305_wrr_mr_step6_calibration_decision.py")

PANEL = "wave2_confirmation"
SEED = 101
DRAWS = 200  # the first pass used 200 draws

cases = pd.read_parquet(m311.PANELS[PANEL]["cases"]).reset_index(drop=True)
certs = pd.read_parquet(m311.PANELS[PANEL]["certificates"]).reset_index(drop=True)
bad = m311.build_target(cases, certs)["bad"]
nets = cases["network_id"].astype(str).to_numpy()
net_index, n_net = m311.factorize_networks(cases["network_id"])
raw_length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float)
spread = float(np.nanmax(raw_length) - np.nanmin(raw_length))

rng_seed = m311.stable_seed(PANEL, "length", SEED)
noise_seed = m311.stable_seed(PANEL, "length", SEED)

# FIRST pass: jitter = U[0,1) * scale(1.0) * spread(301)
rng = np.random.default_rng(int(rng_seed))
buggy = raw_length + rng.random(len(cases)) * 1.0 * spread
# CURRENT: jitter = U[0,1) days
fixed = raw_length + m311.jitter_noise(len(cases), 1.0, noise_seed)

folds = m311.assign_folds(nets, m311.N_SPLITS, SEED)
fold_ids = np.array([folds[n] for n in nets])


def honest_run(score: np.ndarray) -> dict:
    admit = np.zeros(len(cases), dtype=bool)
    per_fold = []
    for fold in range(m311.N_SPLITS):
        test_mask = fold_ids == fold
        cal_mask = ~test_mask
        selection = m311.select_frozen_threshold(
            score[cal_mask],
            bad[cal_mask],
            net_index[cal_mask],
            risk_cap=m311.RISK_CAP,
            draws=DRAWS,
            seed=m311.stable_seed("select", PANEL, SEED, fold, "length_rule"),
        )
        admit[test_mask] = score[test_mask] <= selection["chosen_threshold"]
        test_net = fold_ids[test_mask]
        summary = m311.clustered_summary(
            {"s": admit[test_mask]},
            bad[test_mask],
            np.zeros(int(test_mask.sum()), dtype=int),
            1,
            draws=DRAWS,
            seed=0,
        )["s"]
        per_fold.append(
            {
                "fold": fold,
                "threshold": selection["chosen_threshold"],
                "calibration_retention": selection["chosen_retention"],
                "calibration_false_admit": selection["chosen_calibration_rate"],
                "calibration_upper_bound": selection["chosen_upper"],
                "selection_status": selection["selection_status"],
                "test_retention": float(admit[test_mask].mean()),
                "test_n_admitted": int(admit[test_mask].sum()),
                "test_false_admit": (
                    float(bad[test_mask][admit[test_mask]].mean())
                    if admit[test_mask].any()
                    else float("nan")
                ),
                "test_n_networks": int(len(np.unique(test_net))),
            }
        )
    pooled = m311.clustered_summary(
        {"s": admit}, bad, net_index, n_net, draws=DRAWS, seed=12345
    )["s"]
    return {
        "pooled_retention": pooled["retention"],
        "pooled_false_admit": pooled["false_admit_rate"],
        "pooled_n_admitted": pooled["n_admitted"],
        "n_folds_admitting_nothing": int(sum(1 for f in per_fold if f["selection_status"] != "grid_point_found")),
        "folds": per_fold,
    }


buggy_result = honest_run(buggy)
fixed_result = honest_run(fixed)

print("=== FIRST-pass jitter (longest_run + U[0, spread) with spread=%.0f) ===" % spread)
print(json.dumps(buggy_result, indent=1, default=float))
print()
print("=== CURRENT jitter (longest_run + U[0, 1) day) ===")
print(json.dumps(fixed_result, indent=1, default=float))
print()

# ---------------------------------------------------------------- orientation
def curve(score: np.ndarray, cutoffs) -> list:
    """Admitted share and false-admit rate at raw gap-length cut-offs."""

    rows = []
    for cutoff in cutoffs:
        admitted_raw = raw_length <= cutoff
        rows.append(
            {
                "raw_longest_run_le_days": float(cutoff),
                "admitted_share": float(admitted_raw.mean()),
                "false_admit_rate_among_admitted": float(bad[admitted_raw].mean()),
            }
        )
    return rows


cutoffs = [7, 14, 21, 30, 45, 60, 90, 120, 140, 180, 270, 304]
by_raw = curve(raw_length, cutoffs)

order_asc = np.argsort(fixed, kind="mergesort")          # shortest gap first (correct)
order_desc = np.argsort(-fixed, kind="mergesort")        # longest gap first (inverted)


def topk(score_order, retention):
    k = max(1, int(round(retention * len(bad))))
    mask = np.zeros(len(bad), dtype=bool)
    mask[score_order[:k]] = True
    return {
        "retention": float(k / len(bad)),
        "false_admit_rate": float(bad[mask].mean()),
        "mean_longest_run_admitted": float(raw_length[mask].mean()),
    }


orientation = {
    "ascending_shortest_first": {str(r): topk(order_asc, r) for r in (0.10, 0.30, 0.50, 0.70, 0.90)},
    "descending_longest_first": {str(r): topk(order_desc, r) for r in (0.10, 0.30, 0.50, 0.70, 0.90)},
}

def block_monotone(score: np.ndarray) -> bool:
    """True iff the score never reorders cases with different raw longest_run."""

    order = np.argsort(score, kind="mergesort")
    return bool(np.all(np.diff(raw_length[order]) >= 0))


def tie_block_preserved(score: np.ndarray) -> bool:
    """True iff cases with equal raw longest_run stay inside their own block."""

    order = np.argsort(score, kind="mergesort")
    blocks = raw_length[order]
    return bool(np.all(np.diff(blocks[blocks != np.roll(blocks, 1)]) >= 0)) if blocks.size else True


spearman = {
    "buggy_score_vs_raw_longest_run_pearson_of_ranks": float(
        pd.Series(buggy).rank().corr(pd.Series(raw_length).rank())
    ),
    "current_score_vs_raw_longest_run_pearson_of_ranks": float(
        pd.Series(fixed).rank().corr(pd.Series(raw_length).rank())
    ),
    "note_on_rank_correlation": (
        "raw longest_run is integer days with many ties, so its rank() is the average "
        "rank inside a tie block while the jittered score assigns distinct ranks there; "
        "the block-monotonicity flags below are the exact orientation test"
    ),
    "raw_longest_run_spread_days": spread,
    "raw_longest_run_min_gap_days": float(np.min(np.diff(np.sort(np.unique(raw_length))))),
    "current_score_never_reorders_distinct_values": block_monotone(fixed),
    "buggy_score_never_reorders_distinct_values": block_monotone(buggy),
    "current_score_keeps_tie_blocks_intact": tie_block_preserved(fixed),
}

print("=== orientation: ascending (correct) vs descending (inverted) ===")
print(json.dumps(orientation, indent=1))
print()
print("=== Spearman rank correlation with raw longest_run ===")
print(json.dumps(spearman, indent=1))
print()
print("=== admitted share / false-admit vs raw gap-length cut-off (no jitter) ===")
print(pd.DataFrame(by_raw).to_string(index=False))

evidence = {
    "first_pass_reproduced_with_buggy_jitter": buggy_result,
    "current_fixed_jitter": fixed_result,
    "jitter_diagnosis": {
        "first_pass_formula": "longest_run + U[0,1) * 1.0 * (max-min) = longest_run + U[0, %.0f) days" % spread,
        "current_formula": "longest_run + U[0,1) day (identical to scripts 301/305)",
        "spearman": spearman,
    },
    "orientation": orientation,
    "raw_cutoff_curve": by_raw,
    "recorded_first_pass_numbers": {
        "source": "crossfit_risk_cap_table.csv written 09:56 local (overwritten since)",
        "length_rule_pooled_retention": 0.017208,
        "length_rule_pooled_false_admit": 0.09375,
        "length_rule_folds_admitting_nothing": 4,
        "fold4_threshold": 73.009935,
        "fold4_test_retention": 0.103848,
        "fold4_test_n_admitted": 224,
    },
}
out = ROOT / "scratch" / "p0_02" / "version_note_evidence.json"
out.write_text(json.dumps(evidence, indent=2, default=float) + "\n")
print()
print("wrote", out)
