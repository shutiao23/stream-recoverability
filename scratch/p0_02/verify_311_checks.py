#!/usr/bin/env python3
"""Independent re-implementation checks for script 311 (scratch, not a deliverable).

Three checks:
  A. naive grid selection (explicit network-block resampling) reproduces the
     frozen threshold of one (panel, score, fold) cell;
  B. the fast clustered bootstrap CI matches the shared
     stream_recoverability...stats.cluster_bootstrap on the pooled admitted set;
  C. re-running the analysis section twice gives identical thresholds.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "m311", ROOT / "scripts" / "311_wrr_p0_02_frozen_risk_thresholds.py"
)
m311 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m311)
m311.M301 = m311.load_script_module(
    "m301", ROOT / "scripts" / "301_wrr_mr_step2_same_info_ablation.py"
)
m311.M305 = m311.load_script_module(
    "m305", ROOT / "scripts" / "305_wrr_mr_step6_calibration_decision.py"
)

PANEL = "wave2_confirmation"
SEED = 101
SCORE = "length_rule"
FOLD = 0
DRAWS = 400

OUT = ROOT / "results/wrr_submission_ready/major_revision_20261014/p0_02_frozen_risk_thresholds"

cases = pd.read_parquet(m311.PANELS[PANEL]["cases"]).reset_index(drop=True)
certs = pd.read_parquet(m311.PANELS[PANEL]["certificates"]).reset_index(drop=True)
target = m311.build_target(cases, certs)
bad = target["bad"]
scores = m311.build_scores(cases, certs, panel=PANEL, fold_seed=SEED)
score = scores[SCORE]
nets = cases["network_id"].astype(str).to_numpy()
folds = m311.assign_folds(nets, m311.N_SPLITS, SEED)
fold_ids = np.array([folds[n] for n in nets])
net_index, n_net = m311.factorize_networks(cases["network_id"])

test_mask = fold_ids == FOLD
cal_mask = ~test_mask
cal_score = score[cal_mask]
cal_bad = bad[cal_mask].astype(float)
cal_net = net_index[cal_mask]
cal_net_ids = nets[cal_mask]

# ---------------------------------------------------------------- check A
grid = np.asarray(m311.RETENTION_GRID)
order = np.argsort(cal_score, kind="mergesort")
s_sorted = cal_score[order]
b_sorted = cal_bad[order]
n = len(order)
k = np.maximum(1, np.ceil(grid * n).astype(int))
thresholds = s_sorted[k - 1]
point_rate = np.cumsum(b_sorted)[k - 1] / k

groups = {key: np.where(cal_net_ids == key)[0] for key in np.unique(cal_net_ids)}
keys = list(groups)
rng = np.random.default_rng(12345)  # different RNG than the script on purpose
upper = np.full(grid.size, np.nan)
draws_rates = np.full((DRAWS, grid.size), np.nan)
for draw in range(DRAWS):
    picked = rng.integers(0, len(keys), size=len(keys))
    idx = np.concatenate([groups[keys[int(i)]] for i in picked])
    sub_score = cal_score[idx]
    sub_bad = cal_bad[idx]
    for column, thr in enumerate(thresholds):
        admitted = sub_score <= thr
        if admitted.any():
            draws_rates[draw, column] = sub_bad[admitted].mean()
upper = np.nanquantile(draws_rates, 1 - m311.ALPHA, axis=0)
ok = np.where(upper <= m311.RISK_CAP)[0]
naive_choice = int(ok.max()) if ok.size else None
naive_threshold = float(thresholds[naive_choice]) if naive_choice is not None else -np.inf

table = pd.read_csv(OUT / "crossfit_risk_cap_table.csv")
row = table.loc[
    table.panel.eq(PANEL)
    & table.score.eq(SCORE)
    & table.row_type.eq("fold")
    & table.fold_seed.eq(SEED)
    & table.fold.eq(float(FOLD))
].iloc[0]
print("check A (naive re-implementation of the selection rule)")
print(f"  script threshold      : {row['threshold']!r}")
print(f"  naive  threshold      : {naive_threshold!r}")
print(f"  script cal retention  : {row['calibration_retention']!r}")
print(f"  naive  cal retention  : {grid[naive_choice] if naive_choice is not None else 0.0:.4f}")
print(f"  script upper bound    : {row['calibration_upper_bound_95_clustered']!r}")
print(f"  naive  upper bound    : {upper[naive_choice] if naive_choice is not None else float('nan'):.6f}")
print(f"  script point rate     : {row['calibration_false_admit_rate']!r}")
print(f"  naive  point rate     : {point_rate[naive_choice] if naive_choice is not None else float('nan'):.6f}")
assert naive_choice == int(round(row["calibration_retention"] * n)) - 1 or abs(
    naive_threshold - float(row["threshold"])
) < 1e-9, "threshold mismatch"
assert abs(upper[naive_choice] - float(row["calibration_upper_bound_95_clustered"])) < 0.01, (
    "clustered upper bound mismatch"
)

# ---------------------------------------------------------------- check B
admit = pd.read_parquet(OUT / f"case_level_admissions_{PANEL}.parquet")
admit = admit.loc[:, ["network_id", "consequential_error", f"admit_riskcap_{SCORE}_seed{SEED}"]]
admit = admit.rename(columns={f"admit_riskcap_{SCORE}_seed{SEED}": "admit"})
admit["error"] = admit["consequential_error"].astype(float)


def statistic(block: pd.DataFrame) -> float:
    selected = block.loc[block["admit"]]
    if selected.empty:
        return float("nan")
    return float(selected["error"].mean())


shared = cluster_bootstrap(admit, statistic, draws=DRAWS, seed=7)
mine = table.loc[
    table.panel.eq(PANEL)
    & table.score.eq(SCORE)
    & table.row_type.eq("pooled_risk_cap")
    & table.fold_seed.eq(SEED)
].iloc[0]
print()
print("check B (fast bootstrap vs the shared cluster_bootstrap, 400 draws each)")
print(
    f"  point     script={mine['test_false_admit_rate']:.6f} shared={shared['point']:.6f}"
)
print(
    f"  CI low    script={mine['test_false_admit_ci95_low']:.6f} shared={shared['low']:.6f}"
)
print(
    f"  CI high   script={mine['test_false_admit_ci95_high']:.6f} shared={shared['high']:.6f}"
)
assert abs(float(mine["test_false_admit_rate"]) - shared["point"]) < 1e-9, "point mismatch"
assert abs(float(mine["test_false_admit_ci95_low"]) - shared["low"]) < 0.004, "CI low mismatch"
assert abs(float(mine["test_false_admit_ci95_high"]) - shared["high"]) < 0.004, "CI high mismatch"

# ---------------------------------------------------------------- check C
payload_a = m311.select_frozen_threshold(
    score[cal_mask], bad[cal_mask], net_index[cal_mask], draws=150, seed=99
)
payload_b = m311.select_frozen_threshold(
    score[cal_mask], bad[cal_mask], net_index[cal_mask], draws=150, seed=99
)
print()
print("check C (determinism of select_frozen_threshold)")
print(f"  run1 threshold={payload_a['chosen_threshold']!r} run2={payload_b['chosen_threshold']!r}")
assert payload_a["chosen_threshold"] == payload_b["chosen_threshold"]
print()
print("ALL CHECKS PASSED")
