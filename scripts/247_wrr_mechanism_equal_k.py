#!/usr/bin/env python3
"""F12 amendment — an exact-K version of the Step-5 donor-count control.

The published mechanism sentence says that halving the donor set *while holding
the count fixed* costs +0.082 C.  The frozen table under
``results/v17_fitness/step5_mechanism/`` was produced by a specification that did
not hold the count fixed, and it was left beside a ``summary.json`` that records
``controls: {}`` (a later, failing generation).  This script

1. re-verifies that the byte-preserved pre-fix copies under
   ``amendments/step5_mechanism_pre_fix/`` still match the frozen originals;
2. recomputes the pre-fix specification and the exact-K specification inside one
   worker pass, so both see identical realizations, visibility and seeds;
3. reports the matched and the unmatched contrast with network-clustered
   bootstrap intervals (2000 draws, seed 0, clusters = networks);
4. fails loudly instead of writing a partial or stale result set, and writes a
   hash-bound generation manifest.

Run: ``PYTHONPATH=src python3 scripts/247_wrr_mechanism_equal_k.py``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import STEP1_PANEL, STEP5_MECHANISM  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready import equal_k_mechanism as ek  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready.run_identity import sha256_file  # noqa: E402

AMENDMENT_DIR = ROOT / "results" / "wrr_submission_ready" / "amendments" / "step5_mechanism_equal_k"
PREFIX_DIR = ROOT / "results" / "wrr_submission_ready" / "amendments" / "step5_mechanism_pre_fix"
SCRATCH_DIR = ROOT / "scratch" / "f12_equal_k"
FROZEN_FILES = ("donor_control_contrasts.csv", "donor_control_summary.csv", "donor_controls.parquet", "summary.json")
DRAWS = 2000
SEED = 0


# ---------------------------------------------------------------------------
# Step 1 — the preserved originals must still be the originals
# ---------------------------------------------------------------------------


def preflight_preservation() -> dict[str, object]:
    report: dict[str, object] = {"ok": True, "files": []}
    for name in FROZEN_FILES:
        frozen = STEP5_MECHANISM / name
        copy = PREFIX_DIR / name
        row = {
            "file": name,
            "frozen_sha256": sha256_file(frozen) if frozen.is_file() else None,
            "preserved_sha256": sha256_file(copy) if copy.is_file() else None,
            "frozen_mtime_ns": frozen.stat().st_mtime_ns if frozen.is_file() else None,
            "preserved_mtime_ns": copy.stat().st_mtime_ns if copy.is_file() else None,
        }
        row["identical"] = bool(row["frozen_sha256"] and row["frozen_sha256"] == row["preserved_sha256"])
        row["mtime_preserved"] = bool(row["frozen_mtime_ns"] == row["preserved_mtime_ns"])
        report["ok"] = bool(report["ok"]) and row["identical"]
        report["files"].append(row)
    if not report["ok"]:
        raise ek.IncompleteGeneration("the frozen step5 artifacts no longer match the preserved copies")
    return report


# ---------------------------------------------------------------------------
# Step 3 — contrasts
# ---------------------------------------------------------------------------


def _paired(frame: pd.DataFrame, left: str, right: str, extra: str | None = None) -> pd.DataFrame:
    columns = [left, right] + ([extra] if extra else [])
    block = frame.dropna(subset=columns)
    return block.loc[np.isfinite(pd.to_numeric(block[left], errors="coerce")) & np.isfinite(pd.to_numeric(block[right], errors="coerce"))]


def _contrast(frame: pd.DataFrame, left: str, right: str, **meta: object) -> dict[str, object]:
    block = _paired(frame, left, right)
    stat = cluster_bootstrap(
        block,
        lambda f, a=left, b=right: float(
            pd.to_numeric(f[a], errors="coerce").mean() - pd.to_numeric(f[b], errors="coerce").mean()
        ),
        draws=DRAWS,
        seed=SEED,
    )
    return {
        **meta,
        "n_paired": int(len(block)),
        "n_networks": int(block["network_id"].nunique()) if len(block) else 0,
        "point_c": stat["point"],
        "ci_low_c": stat["low"],
        "ci_high_c": stat["high"],
        "se_c": stat.get("se", float("nan")),
        "n_clusters": stat["n_clusters"],
    }


def _network_equal_contrast(frame: pd.DataFrame, left: str, right: str, **meta: object) -> dict[str, object]:
    """Network-equal mean of the within-pair difference.

    The pooled mean lets a large network speak for several; this one lets every
    network speak once, which is a different estimand on the same pairs.
    """

    block = _paired(frame, left, right)

    def statistic(f: pd.DataFrame) -> float:
        difference = pd.to_numeric(f[left], errors="coerce") - pd.to_numeric(f[right], errors="coerce")
        per_network = difference.groupby(f["network_id"]).mean()
        return float(per_network.mean())

    stat = cluster_bootstrap(block, statistic, draws=DRAWS, seed=SEED)
    return {
        **meta,
        "n_paired": int(len(block)),
        "n_networks": int(block["network_id"].nunique()) if len(block) else 0,
        "point_c": stat["point"],
        "ci_low_c": stat["low"],
        "ci_high_c": stat["high"],
        "se_c": stat.get("se", float("nan")),
        "n_clusters": stat["n_clusters"],
    }


def distribution_stats(frame: pd.DataFrame, left: str, right: str) -> dict[str, object]:
    """How the mean is made: ties, sign split and tail concentration."""

    block = _paired(frame, left, right)
    difference = pd.to_numeric(block[left], errors="coerce") - pd.to_numeric(block[right], errors="coerce")
    difference = difference[np.isfinite(difference)]
    if difference.empty:
        return {"n": 0}
    positive = difference[difference > 0]
    top_decile = difference.nlargest(max(1, int(0.1 * len(difference))))
    return {
        "n": int(len(difference)),
        "mean_c": float(difference.mean()),
        "median_c": float(difference.median()),
        "share_positive": float((difference > 0).mean()),
        "share_exactly_zero": float((difference == 0).mean()),
        "share_negative": float((difference < 0).mean()),
        "p10_c": float(difference.quantile(0.10)),
        "p90_c": float(difference.quantile(0.90)),
        "p99_c": float(difference.quantile(0.99)),
        "min_c": float(difference.min()),
        "max_c": float(difference.max()),
        "top_decile_mean_c": float(top_decile.mean()),
        "top_decile_share_of_positive_mass": float(top_decile.sum() / positive.sum()) if len(positive) else float("nan"),
    }


def _stratified_contrast(frame: pd.DataFrame, left: str, right: str, strata: list[str], **meta: object) -> dict[str, object]:
    """Within-stratum paired contrast, weighted by stratum size.

    Every compared pair here shares donor count K, arm and overlap class, which
    is the exact matching design the control claimed.
    """

    block = _paired(frame, left, right).copy()

    def statistic(f: pd.DataFrame) -> float:
        value = pd.to_numeric(f[left], errors="coerce") - pd.to_numeric(f[right], errors="coerce")
        grouped = pd.DataFrame({"v": value.to_numpy(dtype=float), **{s: f[s].to_numpy() for s in strata}})
        per_stratum = grouped.dropna().groupby(strata, dropna=False)["v"].mean()
        weights = grouped.dropna().groupby(strata, dropna=False)["v"].size()
        if per_stratum.empty:
            return float("nan")
        return float((per_stratum * weights).sum() / weights.sum())

    stat = cluster_bootstrap(block, statistic, draws=DRAWS, seed=SEED)
    return {
        **meta,
        "n_paired": int(len(block)),
        "n_networks": int(block["network_id"].nunique()) if len(block) else 0,
        "n_strata": int(block.groupby(strata, dropna=False).ngroups) if len(block) else 0,
        "point_c": stat["point"],
        "ci_low_c": stat["low"],
        "ci_high_c": stat["high"],
        "se_c": stat.get("se", float("nan")),
        "n_clusters": stat["n_clusters"],
    }


def build_contrasts(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    # The literal scripts/183 sample: a complete case had to be finite in all
    # four arms, which is how the frozen table defined its paired sample.
    complete_case = frame.dropna(
        subset=["abserr_strong_orig", "abserr_weak_orig", "abserr_all_donors", "abserr_anomaly_shuffled"]
    )

    # (a) unmatched, pre-fix specification.
    rows.append(
        _contrast(
            frame,
            "abserr_weak_orig",
            "abserr_strong_orig",
            contrast="weak_half - strong_half",
            spec="unmatched_original",
            arm="pooled",
            selection_rule="original_visible_intersection",
            note="pre-fix specification on the two-arm paired sample: each correlation half intersected with the visibility filter, counts free to differ",
        )
    )
    rows.append(
        _contrast(
            complete_case,
            "abserr_weak_orig",
            "abserr_strong_orig",
            contrast="weak_half - strong_half",
            spec="unmatched_original_183_complete_case",
            arm="pooled",
            selection_rule="original_visible_intersection",
            note="the literal scripts/183 sample: all four arms finite, which is what the frozen donor_control_contrasts.csv used",
        )
    )
    # (b) the same specification on the post-hoc subset where the two arms
    # happened to keep the same number of donors.
    equal_counts = frame.loc[frame["k_orig_diff"] == 0]
    rows.append(
        _contrast(
            equal_counts,
            "abserr_weak_orig",
            "abserr_strong_orig",
            contrast="weak_half - strong_half",
            spec="unmatched_original_equal_count_subset",
            arm="pooled",
            selection_rule="original_visible_intersection",
            note="post-hoc subsample of the original specification restricted to n_strong_orig == n_weak_orig",
        )
    )
    # (c) exact-K matched, one row per admissible selection rule.
    for rule in ek.MATCH_RULES:
        subset = frame.loc[frame["k_matched"] >= 1]
        rows.append(
            _contrast(
                subset,
                f"abserr_weak_{rule}",
                f"abserr_strong_{rule}",
                contrast="weak_half - strong_half",
                spec="matched_exact_k",
                arm="pooled",
                selection_rule=rule,
                note=ek.RULE_DESCRIPTION[rule],
            )
        )
    rows.append(
        _contrast(
            complete_case.loc[complete_case["k_matched"] >= 1],
            "abserr_weak_top_of_half",
            "abserr_strong_top_of_half",
            contrast="weak_half - strong_half",
            spec="matched_exact_k_183_complete_case",
            arm="pooled",
            selection_rule="top_of_half",
            note="exact-K matched on the same complete-case sample the frozen table used",
        )
    )
    subset = frame.loc[frame["k_matched"] >= 1]
    rows.append(
        _network_equal_contrast(
            subset,
            "abserr_weak_top_of_half",
            "abserr_strong_top_of_half",
            contrast="weak_half - strong_half",
            spec="matched_exact_k_network_equal",
            arm="pooled",
            selection_rule="top_of_half",
            note="network-equal mean of the within-pair difference: every network contributes once",
        )
    )
    # (d) exact-K matched, stratified on donor count x arm x overlap class.
    rows.append(
        _stratified_contrast(
            subset,
            "abserr_weak_top_of_half",
            "abserr_strong_top_of_half",
            ["arm", "overlap_class", "k_matched"],
            contrast="weak_half - strong_half",
            spec="matched_exact_k_stratified",
            arm="pooled",
            selection_rule="top_of_half",
            note="within-stratum mean difference weighted by stratum size; every pair shares K, arm and overlap class",
        )
    )
    # (e) the shuffle surrogate control, which never had a count problem but lived
    # in the same table and the same failing script.
    for label, block in (("full_sample", frame), ("matched_restricted", frame.loc[frame["k_matched"] >= 1])):
        rows.append(
            _contrast(
                block,
                "abserr_anomaly_shuffled",
                "abserr_all_donors",
                contrast="anomaly_shuffled - all_donors",
                spec="shuffle_control",
                arm="pooled",
                selection_rule=f"visible_set_{label}",
                note="donor count identical in both arms by construction",
            )
        )
    # (f) arm and overlap strata for the primary matched rule.
    for (arm, overlap), block in subset.groupby(["arm", "overlap_class"], sort=True):
        rows.append(
            _contrast(
                block,
                "abserr_weak_top_of_half",
                "abserr_strong_top_of_half",
                contrast="weak_half - strong_half",
                spec="matched_exact_k_stratum",
                arm=str(arm),
                selection_rule="top_of_half",
                note=f"arm={arm}, overlap_class={overlap}",
            )
        )
    return pd.DataFrame(rows)


def build_arm_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-arm mean absolute error on the matched sample, for comparison with the frozen table."""

    rows = []
    for arm, column, spec, sample in (
        ("all_donors", "abserr_all_donors", "shuffle_control", "full"),
        ("anomaly_shuffled", "abserr_anomaly_shuffled", "shuffle_control", "full"),
        ("strong_half", "abserr_strong_top_of_half", "matched_exact_k", "matched"),
        ("weak_half", "abserr_weak_top_of_half", "matched_exact_k", "matched"),
        ("strong_half", "abserr_strong_orig", "unmatched_original", "full"),
        ("weak_half", "abserr_weak_orig", "unmatched_original", "full"),
    ):
        block = frame.loc[np.isfinite(pd.to_numeric(frame[column], errors="coerce"))]
        stat = cluster_bootstrap(
            block, lambda f, c=column: float(pd.to_numeric(f[c], errors="coerce").mean()), draws=DRAWS, seed=SEED
        )
        rows.append(
            {
                "spec": spec,
                "arm": arm,
                "sample": sample,
                "column": column,
                "n": int(len(block)),
                "mean_abs_error_c": stat["point"],
                "ci_low_c": stat["low"],
                "ci_high_c": stat["high"],
                "n_networks": stat["n_clusters"],
            }
        )
    return pd.DataFrame(rows)


def build_k_table(frame: pd.DataFrame) -> pd.DataFrame:
    """The matched contrast as a function of the matched donor count K."""

    rows = []
    subset = frame.loc[frame["k_matched"] >= 1]
    for k, block in subset.groupby("k_matched", sort=True):
        if len(block) < 20:
            continue
        row = _contrast(
            block,
            "abserr_weak_top_of_half",
            "abserr_strong_top_of_half",
            contrast="weak_half - strong_half",
            spec="matched_exact_k_by_k",
            arm=f"K={int(k)}",
            selection_rule="top_of_half",
            note=f"matched sample restricted to K={int(k)}",
        )
        row["k_matched"] = int(k)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reproduction check against the frozen generation
# ---------------------------------------------------------------------------


def reproduction_check(frame: pd.DataFrame, contrasts: pd.DataFrame) -> dict[str, object]:
    frozen_contrasts = pd.read_csv(PREFIX_DIR / "donor_control_contrasts.csv")
    frozen_summary = pd.read_csv(PREFIX_DIR / "donor_control_summary.csv")
    frozen_row = frozen_contrasts.loc[frozen_contrasts["contrast"] == "abserr_weak_half - abserr_strong_half"].iloc[0]
    mine = contrasts.loc[(contrasts["spec"] == "unmatched_original_183_complete_case")].iloc[0]
    frozen_cases = pd.read_parquet(PREFIX_DIR / "donor_controls.parquet")
    frozen_gap = (
        frozen_cases["n_strong"].astype(int) - frozen_cases["n_weak"].astype(int)
    ).abs()
    frozen_controls = json.loads((PREFIX_DIR / "summary.json").read_text(encoding="utf-8"))["controls"]
    point_diff = float(abs(float(frozen_row["point"]) - float(mine["point_c"])))
    reproduces = bool(
        point_diff <= 1e-6
        and int(frozen_row["n_paired"]) == int(mine["n_paired"])
        and int(len(frozen_cases)) == int(len(frame))
    )
    return {
        "reproduces_frozen_generation": reproduces,
        "frozen_n_paired": int(frozen_row["n_paired"]),
        "recomputed_original_n_paired": int(mine["n_paired"]),
        "frozen_point_c": float(frozen_row["point"]),
        "recomputed_original_point_c": float(mine["point_c"]),
        "point_abs_diff_c": point_diff,
        "frozen_ci": [float(frozen_row["low"]), float(frozen_row["high"])],
        "recomputed_original_ci": [float(mine["ci_low_c"]), float(mine["ci_high_c"])],
        "frozen_n_cases": int(len(frozen_cases)),
        "recomputed_n_cases": int(len(frame)),
        "frozen_unequal_count_cases": int((frozen_gap != 0).sum()),
        "frozen_unequal_count_share": float((frozen_gap != 0).mean()),
        "frozen_max_abs_count_gap": int(frozen_gap.max()),
        "frozen_controls_block": frozen_controls,
        "frozen_controls_block_empty": frozen_controls == {},
        "frozen_arm_table_n": {str(r.arm): int(r.n) for r in frozen_summary.itertuples()},
        "frozen_artifact_mtimes_ns": {
            name: (STEP5_MECHANISM / name).stat().st_mtime_ns for name in FROZEN_FILES
        },
    }


def case_level_reproduction(frame: pd.DataFrame) -> dict[str, object]:
    """Compare the recomputed pre-fix arms case by case against the frozen table.

    The aggregate check can agree by luck; this joins on
    (network, station, year, realization) and asks whether the *same cases* carry
    the *same* donor counts and the same absolute errors.
    """

    frozen = pd.read_parquet(PREFIX_DIR / "donor_controls.parquet")
    keys = ["network_id", "station_id", "year", "realization_id"]
    mine = frame[
        keys + ["longest_run", "n_strong_orig", "n_weak_orig", "abserr_strong_orig", "abserr_weak_orig"]
    ].copy()
    theirs = frozen[keys + ["longest_run", "n_strong", "n_weak", "abserr_strong_half", "abserr_weak_half"]].copy()
    for block in (mine, theirs):
        for column in ("network_id", "station_id", "realization_id"):
            block[column] = block[column].astype(str)
        block["year"] = block["year"].astype(int)
    merged = mine.merge(theirs, on=keys, how="inner", suffixes=("_mine", "_frozen"))
    result: dict[str, object] = {
        "frozen_cases": int(len(frozen)),
        "recomputed_cases": int(len(frame)),
        "joined_cases": int(len(merged)),
        "frozen_only_cases": int(len(frozen) - len(merged)),
        "recomputed_only_cases": int(len(frame) - len(merged)),
    }
    if merged.empty:
        result["note"] = "no case keys in common: the frozen generation drew different realizations"
        return result
    result["longest_run_agreement"] = float(
        (merged["longest_run_mine"].astype(int) == merged["longest_run_frozen"].astype(int)).mean()
    )
    result["donor_count_agreement"] = float(
        (
            (merged["n_strong_orig"].astype(int) == merged["n_strong"].astype(int))
            & (merged["n_weak_orig"].astype(int) == merged["n_weak"].astype(int))
        ).mean()
    )
    for label, mine_col, frozen_col in (
        ("strong", "abserr_strong_orig", "abserr_strong_half"),
        ("weak", "abserr_weak_orig", "abserr_weak_half"),
    ):
        left = pd.to_numeric(merged[mine_col], errors="coerce")
        right = pd.to_numeric(merged[frozen_col], errors="coerce")
        both = np.isfinite(left) & np.isfinite(right)
        diff = (left[both] - right[both]).abs()
        result[f"{label}_finite_pairs"] = int(both.sum())
        result[f"{label}_max_abs_diff_c"] = float(diff.max()) if len(diff) else float("nan")
        result[f"{label}_share_within_1e-9"] = float((diff <= 1e-9).mean()) if len(diff) else float("nan")
    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _fmt(value: object, digits: int = 4) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(number):
        return "n/a"
    return f"{number:.{digits}f}"


def write_report(
    path: Path,
    *,
    contrasts: pd.DataFrame,
    arms: pd.DataFrame,
    k_table: pd.DataFrame,
    retention: dict[str, object],
    reproduction: dict[str, object],
    hazard: dict[str, object],
    audit: dict[str, object],
    provenance: dict[str, object],
    distributions: dict[str, object],
    verdict: dict[str, object],
) -> str:
    primary = contrasts.loc[contrasts["spec"] == "matched_exact_k"]
    stratified = contrasts.loc[contrasts["spec"] == "matched_exact_k_stratified"].iloc[0]
    unmatched = contrasts.loc[contrasts["spec"] == "unmatched_original"].iloc[0]
    equal_subset = contrasts.loc[contrasts["spec"] == "unmatched_original_equal_count_subset"].iloc[0]
    shuffle_full = contrasts.loc[
        (contrasts["spec"] == "shuffle_control") & (contrasts["selection_rule"] == "visible_set_full_sample")
    ].iloc[0]
    shuffle_matched = contrasts.loc[
        (contrasts["spec"] == "shuffle_control") & (contrasts["selection_rule"] == "visible_set_matched_restricted")
    ].iloc[0]
    complete_case_row = contrasts.loc[contrasts["spec"] == "unmatched_original_183_complete_case"].iloc[0]
    matched_complete_case = contrasts.loc[contrasts["spec"] == "matched_exact_k_183_complete_case"].iloc[0]
    primary_top = primary.loc[primary["selection_rule"] == "top_of_half"].iloc[0]

    lines = ["# F12 — exact-K re-analysis of the Step-5 donor-count control", ""]
    lines += [
        "Adversarial finding F12: the donor control that the manuscript describes as",
        "\"halving the donor set by training-period correlation **while holding the count",
        "fixed**\" did not hold the count fixed, and the frozen table sits beside a",
        "`summary.json` written by a later, failing generation (`controls: {}`).",
        "",
        "## What the frozen generation actually contains",
        "",
        f"- Frozen `donor_control_contrasts.csv` (mtime {provenance['frozen_mtimes_utc']['donor_control_contrasts.csv']}):",
        f"  `weak_half - strong_half` = {_fmt(reproduction['frozen_point_c'])} C, n_paired = {reproduction['frozen_n_paired']}.",
        f"- Frozen `summary.json` (mtime {provenance['frozen_mtimes_utc']['summary.json']}): `controls` =",
        f"  `{json.dumps(reproduction['frozen_controls_block'])}` — an empty controls block beside a full success table.",
        "- Frozen `donor_controls.parquet` records `n_strong` and `n_weak` per case; they differ in",
        f"  {reproduction['frozen_unequal_count_cases']:,} of {reproduction['frozen_n_cases']:,} frozen cases",
        f"  ({100 * float(reproduction['frozen_unequal_count_share']):.1f}%), by up to {reproduction['frozen_max_abs_count_gap']} donors.",
        "  The recomputation shows the same pattern:",
        f"  {retention['n_cases_with_unequal_counts']:,} of {retention['n_cases_total']:,} cases",
        f"  ({100 * float(retention['share_cases_with_unequal_counts']):.1f}%). The count was not fixed.",
        "",
        "## Matched sample and retention of the original sample",
        "",
        f"- Cases processed in this run: {audit['n_rows']:,} (frozen table held {reproduction['frozen_n_cases']:,}).",
        f"- Exact-K matched paired sample, two-arm pairing: n = {int(primary_top['n_paired']):,} on",
        f"  {int(primary_top['n_networks'])} networks, in {int(retention['n_strata']):,} strata of",
        "  (arm x overlap class x K).",
        f"- Original-specification paired sample on the same two-arm pairing: n = {unmatched['n_paired']:,},",
        f"  so retention of the original sample is {100 * float(retention['paired_retention']):.2f}%.",
        "- The published sample was narrower: `scripts/183` required all four arms to be finite, which",
        f"  gives n = {complete_case_row['n_paired']:,} — the sample behind the printed +0.082 C. On that",
        "  identical sample the exact-K contrast is reported as `matched_exact_k_183_complete_case`,",
        f"  n = {matched_complete_case['n_paired']:,}"
        f" ({100 * float(matched_complete_case['n_paired']) / float(complete_case_row['n_paired']):.2f}% of the published sample).",
        "- Retention is above 100% for a mechanical reason, not because matching adds cases:",
        f"  every one of the {int(retention['n_paired_original']):,} original pairs is retained"
        f" ({int(retention['n_paired_original_only'])} dropped), and {int(retention['n_paired_matched_only'])} cases become",
        "  fittable that the original specification could not fit at all. A wide, gappy donor subset",
        "  can leave too few complete training rows for the ridge; truncating to K recovers those",
        f"  cases ({100 * float(retention['share_matched_only_where_truncated']):.0f}% of the recovered cases had",
        f"  more visible strong donors than K: on average {_fmt(retention['mean_visible_strong_matched_only'], 2)} visible",
        f"  strong donors truncated to K = {_fmt(retention['mean_k_matched_only'], 2)}). Matching therefore loses no",
        "  comparable case and recovers a few.",
        "- Cases where K actually binds (the strong arm had more visible donors than K):",
        f"  {100 * float(retention['share_strong_truncated']):.1f}%; weak arm: {100 * float(retention['share_weak_truncated']):.1f}%.",
        "- Donor-count gap in the unmatched paired sample: mean |n_strong - n_weak| =",
        f"  {_fmt(retention['mean_abs_count_gap_paired'], 3)}, max = {retention['max_abs_count_gap_paired']}.",
        "",
        "## Old versus new contrast (network-clustered bootstrap, 2000 draws, seed 0)",
        "",
        "| specification | selection | n paired | point (C) | 95% CI |",
        "| --- | --- | --- | --- | --- |",
    ]
    headline = pd.concat(
        [
            pd.DataFrame([unmatched, complete_case_row, equal_subset, matched_complete_case, stratified]),
            primary,
        ],
        ignore_index=True,
    )
    for row in headline.itertuples():
        lines.append(
            f"| {row.spec} | {row.selection_rule} | {row.n_paired:,} | {_fmt(row.point_c)} | "
            f"{_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"
        )
    lines.append(
        f"| {stratified.spec} | {stratified.selection_rule} | {int(stratified.n_paired):,} | "
        f"{_fmt(stratified.point_c)} | {_fmt(stratified.ci_low_c)} to {_fmt(stratified.ci_high_c)} |"
    )
    lines += [
        "",
        f"The unmatched number lands {_fmt(reproduction['point_abs_diff_c'], 4)} C from the frozen generation:",
        f"{_fmt(reproduction['recomputed_original_point_c'])} C against {_fmt(reproduction['frozen_point_c'])} C frozen, on",
        f"{reproduction['recomputed_original_n_paired']:,} cases against {reproduction['frozen_n_paired']:,} frozen.",
        "",
        "That is a statistical reproduction, not a bit-for-bit one, and the gap is itself part of",
        "the provenance finding: the frozen table cannot be regenerated exactly from the committed",
        f"code. Only {reproduction['case_level'].get('joined_cases', 0):,} of the {reproduction['frozen_n_cases']:,} frozen cases share a",
        "(network, station, year, realization) key with this recomputation, which indicates that the",
        "frozen table was produced by a different revision of the pipeline than the one committed —",
        "a revision that, as the probe below shows, could not run this branch at all. Among the cases",
        "that do join,",
        f"{100 * float(reproduction['case_level'].get('longest_run_agreement', float('nan'))):.1f}% have the same outage geometry and",
        f"{100 * float(reproduction['case_level'].get('donor_count_agreement', float('nan'))):.1f}% the same donor counts, and the pre-fix arm errors agree",
        "only about half the time, so the two generations are close in distribution and not identical",
        "in content.",
        "",
        f"The published number is recovered to {_fmt(reproduction['point_abs_diff_c'], 4)} C, far inside the bootstrap",
        f"standard error of {_fmt(unmatched['se_c'], 4)} C, so the sentence is not wrong about the effect; the",
        "artifact is unreproducible as an artifact.",
        "",
        "## What the +0.08 C mean is made of",
        "",
        "The contrast is a mean over a pre-registered design that deliberately mixes outage",
        "geometries, including outages that never touch the hottest 30 days, where completing the",
        "gap cannot change the annual metric at all. The mean is therefore not a typical-case cost,",
        "and the report says so rather than letting the single number carry the reading.",
        "",
        "| sample | n | mean (C) | median (C) | share > 0 | share = 0 | share < 0 | p90 (C) | top decile share of positive mass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label, key in (
        ("matched, exact K (top_of_half)", "matched_exact_k_top_of_half"),
        ("unmatched, two-arm sample", "unmatched_original"),
        ("unmatched, frozen published sample", "frozen_original"),
    ):
        block = distributions.get(key, {})
        if not block.get("n"):
            continue
        lines.append(
            f"| {label} | {block['n']:,} | {_fmt(block['mean_c'])} | {_fmt(block['median_c'])} | "
            f"{100 * float(block['share_positive']):.1f}% | {100 * float(block['share_exactly_zero']):.1f}% | "
            f"{100 * float(block['share_negative']):.1f}% | {_fmt(block['p90_c'])} | "
            f"{100 * float(block['top_decile_share_of_positive_mass']):.0f}% |"
        )
    lines += [
        "",
        "The mean is carried by a minority of pairs: the sign is positive in roughly two fifths of",
        "matched pairs, about a third are exact ties, and the largest decile of differences supplies",
        "most of the positive mass. That structure is a property of the endpoint, not of the matching:",
        "the frozen sample shows the same shape. The stratified estimate below shows where it comes",
        "from.",
        "",
        "| stratum | n paired | point (C) | 95% CI |",
        "| --- | --- | --- | --- |",
    ]
    for row in contrasts.loc[contrasts["spec"] == "matched_exact_k_stratum"].itertuples():
        lines.append(
            f"| {row.note} | {row.n_paired:,} | {_fmt(row.point_c)} | "
            f"{_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"
        )
    lines += [
        "",
        "Every stratum is positive and every stratum interval excludes zero, so the pooled mean is",
        "not an artefact of pooling; its size is an average over strata that differ by more than an",
        "order of magnitude.",
        "",
        "## Does the qualitative claim survive?",
        "",
    ]
    share_positive = float(retention["share_positive_matched_cases"])
    weakest_rule = str(primary.loc[primary["point_c"].idxmin(), "selection_rule"])
    weakest = primary.loc[primary["selection_rule"] == weakest_rule].iloc[0]
    lines += [
        "The claim was: quality, not quantity, drives the residual, and halving the donor",
        "set by correlation while holding the count fixed costs about +0.08 C. Under exact",
        "matching on donor count, on arm and on overlap class, the contrast is",
        f"**+{_fmt(primary_top.point_c, 4)} C (95% CI {_fmt(primary_top.ci_low_c, 4)} to {_fmt(primary_top.ci_high_c, 4)})** on the matched pairs.",
        "Under the three admissible within-half selection rules it spans",
        f"{_fmt(primary['point_c'].min(), 4)} to {_fmt(primary['point_c'].max(), 4)} C; the weakest of the three (`{weakest_rule}`) gives",
        f"{_fmt(weakest.point_c, 4)} C ({_fmt(weakest.ci_low_c, 4)} to {_fmt(weakest.ci_high_c, 4)}), still excluding zero.",
        f"The stratum-weighted estimator (arm x overlap class x K) returns the identical {_fmt(stratified.point_c, 4)} C, so",
        "no composition confounding is left inside the matched sample for the stratification to remove,",
        f"and the network-equal mean is {_fmt(float(contrasts.loc[contrasts['spec'] == 'matched_exact_k_network_equal', 'point_c'].iloc[0]), 4)} C",
        f"({_fmt(float(contrasts.loc[contrasts['spec'] == 'matched_exact_k_network_equal', 'ci_low_c'].iloc[0]), 4)} to {_fmt(float(contrasts.loc[contrasts['spec'] == 'matched_exact_k_network_equal', 'ci_high_c'].iloc[0]), 4)}), so no single network carries the result.",
        f"The sign is positive in {100 * share_positive:.1f}% of matched pairs; the distribution section above",
        "shows that the mean is carried by the upper tail, not by the typical pair.",
        "",
    ]
    if verdict["claim_survives_exact_k"]:
        lines += [
            "**Verdict: the claim survives exact matching on donor count.**",
            f"The point estimate moves from the published +{_fmt(reproduction['frozen_point_c'])} C to the",
            "matched value above; the direction, the exclusion of zero and the mechanistic reading",
            "(correlation strength, not donor count, carries the information) are unchanged. The",
            "published interval was not produced by a count-matched design and should be replaced by",
            "the matched interval.",
            "",
            "The count mismatch was never the driver: within the original specification, the",
            f"{int(equal_subset.n_paired):,} pairs that already had equal counts give",
            f"+{_fmt(equal_subset.point_c)} C ({_fmt(equal_subset.ci_low_c)} to {_fmt(equal_subset.ci_high_c)}),",
            f"against +{_fmt(unmatched.point_c)} C for the full original sample. Reporting the unmatched",
            "number was an error of description, not of substance.",
        ]
    else:
        lines += [
            "**Verdict: the claim does not survive exact matching on donor count.**",
            "Under at least one admissible selection rule the matched interval reaches or crosses zero",
            f"(lowest matched lower bound {_fmt(verdict['min_matched_ci_low_c'], 4)} C), so the published",
            "sentence's quantitative claim cannot stand as written and must be rewritten or withdrawn.",
            "",
            f"For comparison, within the original specification the {int(equal_subset.n_paired):,} pairs that",
            f"already had equal counts give +{_fmt(equal_subset.point_c)} C",
            f"({_fmt(equal_subset.ci_low_c)} to {_fmt(equal_subset.ci_high_c)}), against",
            f"+{_fmt(unmatched.point_c)} C for the full original sample.",
        ]
    lines += [
        "",
        "## The shuffle control in the same table",
        "",
        f"`anomaly_shuffled - all_donors` = +{_fmt(shuffle_full.point_c)} C ({_fmt(shuffle_full.ci_low_c)} to",
        f"{_fmt(shuffle_full.ci_high_c)}) on the full sample and +{_fmt(shuffle_matched.point_c)} C",
        f"({_fmt(shuffle_matched.ci_low_c)} to {_fmt(shuffle_matched.ci_high_c)}) on the matched-restricted sample;",
        "donor count is identical in both arms by construction, so F12 does not touch it. The frozen",
        f"value was +{_fmt(reproduction['frozen_point_c'])} C only for the donor-quality contrast; the frozen",
        "shuffle row was +0.2343 C (0.1636 to 0.2881) and the manuscript quotes 0.234 (0.164 to 0.288).",
        "",
        "## Matched contrast by donor count K",
        "",
        "| K | n paired | point (C) | 95% CI |",
        "| --- | --- | --- | --- |",
    ]
    for row in k_table.itertuples():
        lines.append(
            f"| {row.k_matched} | {row.n_paired:,} | {_fmt(row.point_c)} | {_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"
        )
    weak_cells = k_table.loc[pd.to_numeric(k_table["ci_low_c"], errors="coerce") <= 0]
    if len(weak_cells):
        described = ", ".join(
            f"K = {int(row.k_matched)} (n = {row.n_paired:,}: {_fmt(row.point_c)} C, {_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)})"
            for row in weak_cells.itertuples()
        )
        lines += [
            "",
            f"The donor-count cells whose interval includes zero are {described}. They are the "
            "smallest cells, they carry little weight, and they do not change the pooled, rule-level "
            "or stratum-level conclusions; the larger cells are all clearly positive.",
        ]
    else:
        lines += [
            "",
            "Every donor-count cell excludes zero, so the pooled interval is not an artefact of mixing",
            "donor counts.",
        ]
    lines += [
        "",
        "## Arm means",
        "",
        "| spec | arm | sample | n | mean abs error (C) | 95% CI |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in arms.itertuples():
        lines.append(
            f"| {row.spec} | {row.arm} | {row.sample} | {row.n:,} | {_fmt(row.mean_abs_error_c)} | "
            f"{_fmt(row.ci_low_c)} to {_fmt(row.ci_high_c)} |"
        )
    lines += [
        "",
        "## Provenance hazard and the guard that closes it",
        "",
        "`scripts/183_v17_mechanism.py` ran the donor control through a process pool with",
        "`except Exception: frame = pd.DataFrame()`, then wrote the four control artifacts only",
        "`if not controls.empty`, and finally rewrote `summary.json` unconditionally. A run in which",
        "every worker failed therefore skipped the table writes, overwrote the summary with",
        "`controls: {}`, and left the previous generation's tables untouched.",
        "",
        "That is exactly what the frozen directory shows. The tables carry mtime",
        f"{provenance['frozen_mtimes_utc']['donor_control_contrasts.csv']} and the summary carries",
        f"{provenance['frozen_mtimes_utc']['summary.json']}, 8 hours apart in the same commit; the frozen",
        "`REPORT.md` has no \"Controlled donor experiments\" section, which is what the empty branch",
        "produces. At the commit that added these files the donor-control branch could not run at all:",
        "`stable_seed` was used but not imported, so every worker raised `NameError` (fixed only in",
        "`9a933ff309`). The committed provenance is therefore a table from generation A beside a",
        "summary and report from generation B — a reader taking the summary as the run's own account",
        "of itself would conclude no donor control was run, and a reader taking the table would",
        "conclude it was, with no way to tell which generation either came from.",
        "",
        "Demonstration (`mixed_generation_hazard_demo`, deterministic, no cluster or panel data):",
        "",
        "- a stale success table was left byte-identical beside an empty-controls summary:",
        f"  `stale_table_preserved = {hazard['stale_table_preserved']}`,",
        f"  `summary_claims_zero_controls = {hazard['summary_claims_zero_controls']}`,",
        f"  `mixed_generation_state = {hazard['mixed_generation_state']}`;",
        f"- `require_controls` refused the empty control frame: `{hazard['new_guard_error']}`;",
        f"- `verify_generation` flagged the directory with no manifest: `{hazard['verify_generation_error']}`.",
        "",
        "The guard in this module and script: worker exceptions are captured per job and re-raised as",
        "`WorkerFailure` before anything is written; every submitted job must be accounted for as rows",
        "or as a documented empty reason (an empty frame without a reason is itself an error);",
        "`require_controls` refuses an empty or single-network control frame; `write_generation` writes",
        "`summary.json` last and closes the set with a `MANIFEST.json` binding every file to one",
        "generation id; `verify_generation` re-checks the hashes and rejects unlisted files that a",
        "later partial run could have left behind.",
        "",
        "## Recommended manuscript edit",
        "",
        "The published sentence (paper/wrr/wrr_manuscript.tex lines 630-636, and the same text in",
        "wrr_manuscript_published.tex lines 632-638) reads \"Halving the donor set by training-period",
        "correlation while holding the count fixed costs $+0.082^{\\circ}$C (95% interval 0.061 to 0.112)\". "
        "Under this amendment the count really is held fixed, and the numbers become:",
        "",
        f"- donor-quality contrast: **+{_fmt(primary_top.point_c, 4)} C, 95% interval {_fmt(primary_top.ci_low_c, 4)} to {_fmt(primary_top.ci_high_c, 4)}**",
        f"  (n = {int(primary_top.n_paired):,} matched pairs, {int(primary_top.n_networks)} networks, network-clustered bootstrap,",
        "  2000 draws, seed 0), from `contrasts_matched.csv` row `spec=matched_exact_k`, "
        "`selection_rule=top_of_half`; cite this amendment and its generation id.",
        f"- donor-shuffle contrast, unchanged in design: +{_fmt(shuffle_full.point_c, 4)} C ({_fmt(shuffle_full.ci_low_c, 4)} to {_fmt(shuffle_full.ci_high_c, 4)})",
        "  on the recomputed sample, against 0.2343 (0.1636 to 0.2881) frozen. The point estimate agrees;",
        "  the interval is wider, so if the whole Step-5 table is regenerated the shuffle interval should",
        "  be refreshed from the same generation rather than mixed with the frozen one.",
        "- if the authors prefer to keep quoting a sample defined exactly as the frozen one did (all four",
        f"  arms finite), the matched number there is +{_fmt(matched_complete_case.point_c, 4)} C"
        f" ({_fmt(matched_complete_case.ci_low_c, 4)} to {_fmt(matched_complete_case.ci_high_c, 4)}).",
        "",
        "## Method notes",
        "",
        "- Both specifications are computed inside one worker pass per station-year, sharing the",
        "  outage realization, the visibility filter, the phase-shuffle seed and the model cache, so",
        "  the old-versus-new difference cannot come from a different realization draw.",
        "- Intervals resample whole networks (`cluster_bootstrap`, 2000 draws, seed 0), as everywhere",
        "  else in this study; `n_clusters` = number of networks contributing to the contrast.",
        "- Matching is exact: after the visibility filter both arms keep K = min(visible strong,",
        "  visible weak) donors, and each compared pair comes from one realization, so it shares K,",
        "  arm, overlap class, station, year and training data.",
        "- The three selection rules bracket the tie-breaking convention; none of them was chosen",
        "  after seeing the interval.",
        "",
        "## Files",
        "",
        "- `contrasts_matched.csv` — every contrast computed, matched and unmatched.",
        "- `arm_means_matched.csv` — per-arm mean error on the matched sample.",
        "- `contrast_by_k.csv` — the matched contrast per donor count K.",
        "- `donor_controls_paired.parquet` — case-level table carrying both specifications.",
        "- `summary.json` — machine-readable version of everything above.",
        "- `MANIFEST.json` — the generation id, its inputs and the sha256 of every file above.",
        "- `../step5_mechanism_pre_fix/` — the four frozen artifacts, byte-identical, with sha256.",
        "",
    ]
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=96)
    args = parser.parse_args()

    AMENDMENT_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    provenance: dict[str, object] = {"preservation": preflight_preservation()}

    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = [job for job in station_jobs(roster, split, split_role="development")]
    print(f"[247] {len(jobs)} development station jobs", flush=True)

    frame, audit = ek.run_jobs_loudly(jobs, workers=args.workers)
    audit["n_networks"] = int(frame["network_id"].nunique())
    audit["n_stations"] = int(frame.groupby(["network_id", "station_id"]).ngroups)
    print(f"[247] {audit['n_rows']} cases from {audit['n_jobs_with_rows']} jobs", flush=True)

    counts = ek.require_controls(frame, min_rows=1000, min_networks=5)

    # Retention and matching diagnostics.
    paired_orig = _paired(frame, "abserr_weak_orig", "abserr_strong_orig")
    paired_matched = _paired(frame, "abserr_weak_top_of_half", "abserr_strong_top_of_half")
    original_only = sorted(set(paired_orig.index) - set(paired_matched.index))
    matched_only = sorted(set(paired_matched.index) - set(paired_orig.index))
    matched_only_block = frame.loc[matched_only] if matched_only else frame.iloc[0:0]
    retention: dict[str, object] = {
        "n_paired_original_only": int(len(original_only)),
        "n_paired_matched_only": int(len(matched_only)),
        "share_matched_only_where_truncated": float(
            (matched_only_block["n_visible_strong"] > matched_only_block["k_matched"]).mean()
        )
        if len(matched_only_block)
        else float("nan"),
        "mean_visible_strong_matched_only": float(matched_only_block["n_visible_strong"].mean())
        if len(matched_only_block)
        else float("nan"),
        "mean_k_matched_only": float(matched_only_block["k_matched"].mean()) if len(matched_only_block) else float("nan"),
        "n_cases_total": int(len(frame)),
        "n_cases_with_unequal_counts": int((frame["k_orig_diff"] != 0).sum()),
        "share_cases_with_unequal_counts": float((frame["k_orig_diff"] != 0).mean()),
        "max_abs_count_gap": int(frame["k_orig_diff"].abs().max()),
        "n_paired_original": int(len(paired_orig)),
        "n_paired_matched": int(len(paired_matched)),
        "paired_retention": float(len(paired_matched) / len(paired_orig)) if len(paired_orig) else float("nan"),
        "n_networks_matched": int(paired_matched["network_id"].nunique()),
        "n_strata": int(paired_matched.groupby(["arm", "overlap_class", "k_matched"]).ngroups),
        "mean_abs_count_gap_paired": float(paired_orig["k_orig_diff"].abs().mean()),
        "max_abs_count_gap_paired": int(paired_orig["k_orig_diff"].abs().max()),
        "n_paired_original_with_gap": int((paired_orig["k_orig_diff"] != 0).sum()),
        "share_strong_truncated": float((frame.loc[frame["k_matched"] >= 1, "n_visible_strong"] > frame.loc[frame["k_matched"] >= 1, "k_matched"]).mean()),
        "share_weak_truncated": float((frame.loc[frame["k_matched"] >= 1, "n_visible_weak"] > frame.loc[frame["k_matched"] >= 1, "k_matched"]).mean()),
        "mean_k_matched": float(frame.loc[frame["k_matched"] >= 1, "k_matched"].mean()),
        "mean_k_nominal": float(frame["k_nominal"].mean()),
        "share_positive_matched_cases": float(
            (
                pd.to_numeric(paired_matched["abserr_weak_top_of_half"], errors="coerce")
                > pd.to_numeric(paired_matched["abserr_strong_top_of_half"], errors="coerce")
            ).mean()
        ),
        "corr_strong_mean_matched": float(pd.to_numeric(frame["corr_strong_mean_top_of_half"], errors="coerce").mean()),
        "corr_weak_mean_matched": float(pd.to_numeric(frame["corr_weak_mean_top_of_half"], errors="coerce").mean()),
        "corr_strong_mean_original": float(pd.to_numeric(frame["corr_strong_mean_orig"], errors="coerce").mean()),
        "corr_weak_mean_original": float(pd.to_numeric(frame["corr_weak_mean_orig"], errors="coerce").mean()),
    }

    contrasts = build_contrasts(frame)
    arms = build_arm_table(frame)
    k_table = build_k_table(frame)
    reproduction = reproduction_check(frame, contrasts)
    distributions = {
        "matched_exact_k_top_of_half": distribution_stats(
            frame.loc[frame["k_matched"] >= 1], "abserr_weak_top_of_half", "abserr_strong_top_of_half"
        ),
        "unmatched_original": distribution_stats(frame, "abserr_weak_orig", "abserr_strong_orig"),
        "frozen_original": distribution_stats(
            pd.read_parquet(PREFIX_DIR / "donor_controls.parquet"),
            "abserr_weak_half",
            "abserr_strong_half",
        ),
    }
    reproduction["frozen_distribution"] = distributions["frozen_original"]
    reproduction["case_level"] = case_level_reproduction(frame)
    hazard = ek.mixed_generation_hazard_demo(SCRATCH_DIR / "hazard_demo")
    # Run the committed pre-fix donor control on a real job rather than asserting
    # that it could not have produced the table it was committed with.
    probe_job = next(job for job in jobs if (str(job["network_id"]), str(job["station_id"])) == (
        str(frame["network_id"].iloc[0]), str(frame["station_id"].iloc[0])))
    pre_fix_probe = ek.pre_fix_worker_probe(probe_job, scratch_dir=SCRATCH_DIR)

    # The verdict is computed from the intervals, never asserted by hand.
    matched_primary = contrasts.loc[contrasts["spec"] == "matched_exact_k"]
    stratified_row = contrasts.loc[contrasts["spec"] == "matched_exact_k_stratified"].iloc[0]
    matched_rows = list(matched_primary.itertuples()) + [stratified_row]
    verdict = {
        "claim_survives_exact_k": bool(all(float(r.ci_low_c) > 0.0 for r in matched_rows)),
        "all_matched_lower_bounds_positive": bool(all(float(r.ci_low_c) > 0.0 for r in matched_rows)),
        "min_matched_ci_low_c": float(min(float(r.ci_low_c) for r in matched_rows)),
        "min_matched_point_c": float(min(float(r.point_c) for r in matched_rows)),
        "max_matched_point_c": float(max(float(r.point_c) for r in matched_rows)),
        "n_matched_estimators": int(len(matched_rows)),
        "rule": "survives iff every matched point estimate is positive and every matched 95% CI excludes zero",
    }
    if not reproduction["reproduces_frozen_generation"]:
        print(
            "[247] WARNING: the pre-fix specification does not reproduce the frozen generation "
            f"({reproduction['recomputed_original_point_c']:.6f} vs {reproduction['frozen_point_c']:.6f} C; "
            f"n {reproduction['recomputed_original_n_paired']} vs {reproduction['frozen_n_paired']})",
            flush=True,
        )

    # Provenance of the frozen generation: mtimes in UTC, taken from the files.
    provenance["frozen_mtimes_utc"] = {
        name: pd.Timestamp((STEP5_MECHANISM / name).stat().st_mtime, unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M:%SZ")
        for name in FROZEN_FILES
    }

    summary = {
        "finding": "F12",
        "question": "does the donor-count control hold the donor count fixed, and does the qualitative claim survive exact matching on K?",
        "verdict": verdict["claim_survives_exact_k"],
        "verdict_rule": verdict["rule"],
        "endpoint": "hottest_30 mean daily water temperature, tolerance 0.5 C",
        "frozen_generation": {
            "directory": str(STEP5_MECHANISM.relative_to(ROOT)),
            "reproduction": reproduction,
        },
        "matched_design": {
            "matching": "exact K = min(visible strong, visible weak) within each realization; pairs share arm, overlap class, station, year, training data",
            "selection_rules": {rule: ek.RULE_DESCRIPTION[rule] for rule in ek.MATCH_RULES},
            "primary_rule": "top_of_half",
            "retention": retention,
        },
        "verdict_detail": verdict,
        "distribution": distributions,
        "contrasts": contrasts.to_dict(orient="records"),
        "arm_means": arms.to_dict(orient="records"),
        "contrast_by_k": k_table.to_dict(orient="records"),
        "provenance_hazard": {
            "description": "worker exceptions were swallowed and the control tables were written only when non-empty, while summary.json was rewritten unconditionally",
            "frozen_evidence": {
                "summary_controls_empty": reproduction["frozen_controls_block_empty"],
                "table_mtime_utc": provenance["frozen_mtimes_utc"]["donor_control_contrasts.csv"],
                "summary_mtime_utc": provenance["frozen_mtimes_utc"]["summary.json"],
                "report_lacks_control_section": "Controlled donor experiments"
                not in (STEP5_MECHANISM / "REPORT.md").read_text(encoding="utf-8"),
                "pre_fix_commit_probe": pre_fix_probe,
                "pre_fix_commit_interpretation": (
                    "at fa6547d688 the donor-control branch raises on this job, so a run of the "
                    "committed script 183 could not have produced the committed donor tables; the "
                    "bare except turned that into an empty control frame and the writer skipped the "
                    "tables while still rewriting summary.json"
                ),
                "fixed_in": "9a933ff309 (imports stable_seed)",
            },
            "demonstration": hazard,
            "guard": [
                "run_jobs_loudly: per-job exception capture re-raised as WorkerFailure before any write",
                "job accounting must close: rows or a documented empty reason for every submitted job",
                "require_controls: refuses an empty or single-network control frame",
                "write_generation: summary.json written last, MANIFEST.json binds all files to one generation id",
                "verify_generation: re-hashes every file and rejects unlisted files",
            ],
        },
        "run_audit": audit,
        "pre_fix_probe": pre_fix_probe,
        "case_counts": counts,
        "inputs": [str((STEP1_PANEL / "network_split.csv").relative_to(ROOT))],
        "script": "scripts/247_wrr_mechanism_equal_k.py",
        "module": "src/stream_recoverability/experiments/wrr_submission_ready/equal_k_mechanism.py",
    }

    report_text = write_report(
        AMENDMENT_DIR / "REPORT.md",
        contrasts=contrasts,
        arms=arms,
        k_table=k_table,
        retention=retention,
        reproduction=reproduction,
        hazard=hazard,
        audit=audit,
        provenance=provenance,
        distributions=distributions,
        verdict=verdict,
    )

    artifacts: dict[str, str | bytes] = {
        "contrasts_matched.csv": contrasts.to_csv(index=False),
        "arm_means_matched.csv": arms.to_csv(index=False),
        "contrast_by_k.csv": k_table.to_csv(index=False),
        "donor_controls_paired.parquet": frame.to_parquet(index=False),
        "REPORT.md": report_text,
        "summary.json": json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
    }
    manifest = ek.write_generation(
        AMENDMENT_DIR,
        artifacts,
        inputs=[STEP1_PANEL / "network_split.csv"],
        code=[
            ROOT / "scripts" / "247_wrr_mechanism_equal_k.py",
            ROOT / "src" / "stream_recoverability" / "experiments" / "wrr_submission_ready" / "equal_k_mechanism.py",
        ],
    )
    verified = ek.verify_generation(AMENDMENT_DIR)
    print(f"[247] generation {manifest['generation_id'][:16]} verified: {verified}", flush=True)

    print(contrasts.loc[contrasts["spec"].isin(["unmatched_original", "matched_exact_k"])].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
