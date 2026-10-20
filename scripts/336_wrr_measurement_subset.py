#!/usr/bin/env python3
"""P1 (review F10, 2026-10-20) — does the aligned advantage survive the measurement stratum?

The article's admission numbers pool providers whose published daily value is a
documented daily mean with providers whose value is a project aggregate or an
unstated statistic.  The 2026-10-14 round measured a provider-contract
sensitivity for the certificate contrast but never for the aligned rules.  This
script re-selects the thresholds and re-evaluates admission on the documented-
daily-mean subset alone:

* development: USGS, GKD Bayern, FOEN, NVE and LUBW (30,289 of 40,704 cases);
* external: USGS and the UK Environment Agency (12,282 of 13,017 cases).

Nothing is refitted: the scores and the per-fold calibration arrays are the ones
the aligned run stored, and only the calibration/test rows are restricted.  The
select rule, the risk cap and the tie rule are imported from `scripts/330`, so
the procedure cannot drift.

Output: ``p1_measurement_subset/`` under `major_revision_20261020/`.

Run:

    PYTHONPATH=src python3 scripts/336_wrr_measurement_subset.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "aligned330", ROOT / "scripts" / "330_wrr_aligned_policy_admission.py"
)
M330 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M330)

from stream_recoverability.experiments.v17_fitness.paths import stable_seed  # noqa: E402

RUN = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261020"
ALIGNED = RUN / "p0_01_aligned_policy_admission"
OUT = RUN / "p1_measurement_subset"
SEEDS = (101, 202, 303)
SCORES = ("fitted_risk", "peak_overlap_rule", "calibrated_bound", "length_rule")
DOCUMENTED = {
    "development": {"usgs", "gkd_bayern", "foen", "nve_hydapi", "lubw"},
    "wave2_confirmation": {"usgs", "uk_ea"},
}
DRAWS_SELECT = 1000
DRAWS_EVAL = 4000


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    contrasts = []
    coverage = []
    for panel, providers in DOCUMENTED.items():
        cases = pd.read_parquet(ALIGNED / f"case_level_admissions_{panel}.parquet")
        for seed in SEEDS:
            block = cases[cases.fold_seed.eq(seed)].reset_index(drop=True)
            cal_arrays = np.load(ALIGNED / f"calibration_scores_{panel}_seed{seed}.npz")[
                "cal_score_by_fold"
            ]
            documented = block["provider"].astype(str).isin(providers).to_numpy()
            groups = block["independence_group"].astype(str).to_numpy()
            group_index, n_groups = M330.M311.factorize_networks(groups)
            folds = block["fold"].to_numpy(dtype=int)
            bad = block["policy_bad"].to_numpy(dtype=bool).astype(float)
            coverage.append(
                {
                    "panel": panel,
                    "fold_seed": int(seed),
                    "n_cases": int(len(block)),
                    "n_documented": int(documented.sum()),
                    "share_documented": float(documented.mean()),
                    "n_groups_documented": int(pd.Series(groups[documented]).nunique()),
                    "documented_bad_rate": float(bad[documented].mean()),
                    "all_bad_rate": float(bad.mean()),
                }
            )
            admit = {}
            for name in SCORES:
                flags = np.zeros(len(block), dtype=bool)
                for fold in range(5):
                    test_mask = (folds == fold) & documented
                    cal_mask = (folds != fold) & documented
                    if not test_mask.any() or not cal_mask.any():
                        continue
                    if name == "fitted_risk":
                        cal_score = np.asarray(cal_arrays[fold])[cal_mask]
                    else:
                        cal_score = block[f"score_{name}"].to_numpy(dtype=float)[cal_mask]
                    selection = M330.select_threshold(
                        cal_score,
                        bad[cal_mask],
                        groups[cal_mask],
                        risk_cap=0.05,
                        draws=DRAWS_SELECT,
                        seed=stable_seed("subset-select", panel, seed, fold, name),
                    )
                    flags[test_mask] = (
                        block[f"score_{name}"].to_numpy(dtype=float)[test_mask]
                        <= selection["threshold"]
                    )
                admit[name] = flags
                evaluated = flags & documented
                rows.append(
                    {
                        "panel": panel,
                        "fold_seed": int(seed),
                        "score": name,
                        "n_documented": int(documented.sum()),
                        "n_admitted": int(evaluated.sum()),
                        "retention_documented": (
                            float(evaluated.sum() / documented.sum()) if documented.sum() else np.nan
                        ),
                        "false_admit_rate": (
                            float(bad[evaluated].mean()) if evaluated.any() else np.nan
                        ),
                    }
                )
            # paired contrast on the documented subset, group-clustered.  The
            # group codes must be re-derived for the subset: passing the full
            # panel's codes would index past the resampled group vector.
            mask = documented
            subset_index, subset_groups = M330.M311.factorize_networks(groups[mask])
            for left, right in (
                ("fitted_risk", "peak_overlap_rule"),
                ("fitted_risk", "calibrated_bound"),
                ("fitted_risk", "length_rule"),
            ):
                values = M330.clustered_contrast(
                    admit[left][mask].astype(float),
                    admit[right][mask].astype(float),
                    subset_index,
                    subset_groups,
                    metric="retention",
                    error=block["policy_error"].to_numpy(dtype=float)[mask],
                    draws=DRAWS_EVAL,
                    seed=stable_seed("subset-contrast", panel, seed, left, right),
                )
                contrasts.append(
                    {
                        "panel": panel,
                        "fold_seed": int(seed),
                        "left": left,
                        "right": right,
                        **values,
                    }
                )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "subset_admission.csv", index=False)
    contrast_table = pd.DataFrame(contrasts)
    contrast_table.to_csv(OUT / "subset_contrasts.csv", index=False)
    coverage_table = pd.DataFrame(coverage)
    coverage_table.to_csv(OUT / "subset_coverage.csv", index=False)

    lines = [
        "# The aligned rules on the documented-daily-mean subset",
        "",
        "Generated by `scripts/336_wrr_measurement_subset.py`. Thresholds are",
        "re-selected inside the subset only; scores and per-fold calibration arrays are",
        "the ones the aligned run stored. Retention is relative to the subset, so it is",
        "not comparable to the full-panel retention in the article.",
        "",
        "| panel | seed | cases | documented share | documented failure rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in coverage_table.itertuples(index=False):
        lines.append(
            f"| {row.panel} | {row.fold_seed} | {row.n_cases} | {row.share_documented:.3f} | "
            f"{row.documented_bad_rate:.3f} |"
        )
    lines.extend(
        [
            "",
            "| panel | rule | retention (mean of seeds) | failure rate among admitted |",
            "|---|---|---:|---:|",
        ]
    )
    for panel in table.panel.unique():
        for name in SCORES:
            block = table[table.panel.eq(panel) & table.score.eq(name)]
            lines.append(
                f"| {panel} | {name} | {block.retention_documented.mean():.3f} | "
                f"{block.false_admit_rate.mean():.3f} |"
            )
    lines.extend(
        [
            "",
            "| panel | seed | contrast | point (pp) | 95% interval | excludes 0 |",
            "|---|---:|---|---:|---|---|",
        ]
    )
    for row in contrast_table.itertuples(index=False):
        lines.append(
            f"| {row.panel} | {row.fold_seed} | {row.left} minus {row.right} | "
            f"{100 * row.point:+.1f} | [{100 * row.ci_low:+.1f}, {100 * row.ci_high:+.1f}] | "
            f"{'yes' if row.ci_excludes_zero else 'no'} |"
        )
    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    metadata = {
        "documented_daily_mean_providers": {k: sorted(v) for k, v in DOCUMENTED.items()},
        "select_draws": DRAWS_SELECT,
        "eval_draws": DRAWS_EVAL,
        "note": (
            "thresholds re-selected on the documented subset; fitted-risk calibration uses "
            "the stored per-outer-fold inner out-of-fold scores restricted to the subset"
        ),
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
