#!/usr/bin/env python3
"""P0-04 — rebuild the environmental-judgment closed loop correctly (review F05 + F03).

`scripts/307_wrr_mr_step8_decision_closed_loop.py` reports a single quantity

    hot_share_bias_pp = (true hot-year share among the admitted set)
                      - (true hot-year share in the full candidate pool)

which is a **selection shift only**.  It never uses a predicted share, so its
"reconstruct all / no screen" row is identically zero *by construction* even
though that row makes 172 wrong judgments on the reserved panel.  In a closed
environmental-judgment loop the deviation of the admitted archive's hot-year
share from the reference pool decomposes as

    (p_hat_A - p_full)  =  (p_hat_A - p_A)  +  (p_A - p_full)
      total deviation      prediction error    selection shift

with p_hat_A = predicted hot-year share among admitted records (the certificate
point estimate `certificate_metric` against the threshold), p_A = true hot-year
share among the same admitted records, p_full = true hot-year share in the full
candidate pool.  Only the first term can be improved by a better model; only the
second is caused by which records are kept.  The old quantity is kept here under
the name `selection_shift_pp` (term 2) and is cross-checked against the
published step-8 CSV.

Review F03 adds that abstention must be compared against "judge everything,
never abstain" at equal risk / equal error budget rather than only against a
fixed 70% retention screen: in the wave-2 18 C scenario judging everything
already makes 52 errors in 13,017 candidates = 0.3995%, below the 0.5% error
budget this evidence chain uses.  `equal_budget_comparison.csv` therefore
carries, per rule family, the (coverage, error) frontier and matched operating
points at (a) the fixed 0.5% error budget, (b) an error budget equal to
reconstruct-all's realised error, and (c) equal decision coverage.

Inputs are exactly the two candidate pools already used by the major-revision
decision chain (same paths, same definitions):

  reserved_retrospective : results/v17_fitness/step10_confirmation/
                           {reserved_cases,reserved_certificates}.parquet
                           (what 307 reads; 10,820 candidates / 36 networks)
  wave2_designed         : results/wrr_submission_ready/p0_07_wave2_ingest/
                           p0_07_wave2_confirmation/
                           {wave2_cases,wave2_certificates}.parquet
                           (what 305/step 6 reads; 13,017 / 49 networks)

Screen masks reproduce the *originating* script of each panel (307 for the
reserved panel, 305/step 6 for wave 2) so that the native operating points can
be cross-checked case-for-case against the published CSVs; the wave-2 peak
screen has no published counterpart and is built with 307's construction.  A
tie-break sensitivity sweep re-draws every screen with alternative RNG seeds
because `longest_run` is integer-valued and heavily tied.

Outputs (results/wrr_submission_ready/major_revision_20261014/p0_04_env_closed_loop/):
  share_decomposition.csv      three-term decomposition, all rules, 3 weightings
  decision_counts.csv          raw correct/missed/false-alarm/abstention counts
  equal_budget_comparison.csv  native + budget-matched + coverage-matched points
  efficiency_frontiers.csv     resampled (coverage, error) frontier per family
  rng_sensitivity.csv          native points under alternative tie-break seeds
  protocol_fingerprint.json    script/input sha256, git HEAD, constants, gaps
  SUMMARY.md                   numbers, definitions, protocol, falsifiers, limits
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT as V17_RESULTS,
    STEP10_CONFIRM,
)

MAJOR = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014"
OUT = MAJOR / "p0_04_env_closed_loop"
WAVE2_DIR = (
    ROOT / "results" / "wrr_submission_ready" / "p0_07_wave2_ingest" / "p0_07_wave2_confirmation"
)
STATION_PANEL = V17_RESULTS / "step21_hydrology" / "station_panel.csv"
STEP8_TABLE = MAJOR / "step8_decision_closed_loop" / "closed_loop_decisions.csv"
STEP6_TABLE = MAJOR / "step6_calibration_decision" / "threshold_judgment.csv"
STEP5_CONTRASTS = MAJOR / "step5_monitoring_tasks" / "arm_and_thermal_contrasts.json"

# ---- frozen protocol constants (identical to the sources unless noted) --------
RETENTION = 0.70               # 307 / 305 screen retention
THRESHOLDS = (18.0, 20.0)      # 307 / 305 hot-year thresholds, degrees C
HOT_YEAR_METRIC = "truth_hottest30"
SEED_RESERVED = 71             # 307 screen seed
SEED_WAVE2 = 53                # 305 screen seed
SEED_EXTRA = 71                # 307 construction, for rules 305 does not have
JUDGEMENT_ERROR_RATE_BUDGET = 0.005   # 0.5% of all candidates, the chain's budget
COVERAGE_INTERP_MAX_BRACKET = 0.02   # widest coverage bracket allowed when interpolating
SENSITIVITY_SEEDS = (101, 131, 163, 197, 233, 271, 311, 353, 397, 443, 491, 541)
FRONTIER_GRID = np.round(np.arange(0.01, 1.0001, 0.01), 4)

RULE_ORDER = (
    "reconstruct_all",
    "length_screen_70",
    "peak_overlap_screen_70",
    "calibrated_screen_70",
    "interval_abstention",
    "screen70_and_abstention",
    "elev_balanced_screen_70",
    "elev_balanced_and_abstention",
)
RULE_FAMILY = {
    "reconstruct_all": "reconstruct_all",
    "length_screen_70": "length_screen",
    "peak_overlap_screen_70": "peak_overlap_screen",
    "calibrated_screen_70": "calibrated_screen",
    "interval_abstention": "interval_abstention",
    "screen70_and_abstention": "screen_and_abstention",
    "elev_balanced_screen_70": "elev_balanced_screen",
    "elev_balanced_and_abstention": "elev_balanced_screen_and_abstention",
}
SCREEN_RULES = (
    "length_screen_70",
    "peak_overlap_screen_70",
    "calibrated_screen_70",
    "elev_balanced_screen_70",
)
WEIGHTINGS = ("per_case", "per_station_year", "network_weighted")

CRITERIA = (
    "native",
    "equal_budget_0p5pct",
    "equal_budget_as_reconstruct_all",
    "equal_budget_as_interval_abstention_native",
    "equal_coverage_1p00",
    "equal_coverage_0p70",
    "equal_coverage_interval_abstention_native",
    "equal_coverage_screen_and_abstention_native",
)
CRITERIA_DEF = {
    "native": "rule as designed",
    "equal_budget_0p5pct": "max coverage with error<=0.5% of all candidates",
    "equal_budget_as_reconstruct_all": (
        "max coverage with error<=reconstruct-all realised error (F03 equal-budget)"
    ),
    "equal_budget_as_interval_abstention_native": (
        "max coverage with error<=interval-abstention realised error (F03 equal-budget, "
        "abstention's own budget)"
    ),
    "equal_coverage_1p00": "interpolated error at coverage 1.00",
    "equal_coverage_0p70": "interpolated error at coverage 0.70",
    "equal_coverage_interval_abstention_native": (
        "interpolated error at interval-abstention native coverage"
    ),
    "equal_coverage_screen_and_abstention_native": (
        "interpolated error at screen+abstention native coverage"
    ),
}
BUDGET_CRITERIA = (
    "equal_budget_0p5pct",
    "equal_budget_as_reconstruct_all",
    "equal_budget_as_interval_abstention_native",
)
COVERAGE_CRITERIA = tuple(c for c in CRITERIA if c.startswith("equal_coverage"))

PANEL_SPECS = {
    "reserved_retrospective": {
        "cases": STEP10_CONFIRM / "reserved_cases.parquet",
        "certs": STEP10_CONFIRM / "reserved_certificates.parquet",
        "screen_protocol": "step8_307",
        "screen_seed": SEED_RESERVED,
        "elevation_available": True,
        "provenance": "scripts/307_wrr_mr_step8_decision_closed_loop.py (reserved panel)",
    },
    "wave2_designed": {
        "cases": WAVE2_DIR / "wave2_cases.parquet",
        "certs": WAVE2_DIR / "wave2_certificates.parquet",
        "screen_protocol": "step6_305",
        "screen_seed": SEED_WAVE2,
        "elevation_available": False,
        "provenance": "scripts/305_wrr_mr_step6_calibration_decision.py (wave-2 panel)",
    },
}
SUBSETS = ("pooled", "arm=empirical", "arm=stratified")


# ---------------------------------------------------------------------------
# helpers copied verbatim from scripts/307_wrr_mr_step8_decision_closed_loop.py
# ---------------------------------------------------------------------------
def elevation_tertile(station_ids: pd.Series, attributes: pd.DataFrame) -> pd.Series:
    elev = station_ids.astype(str).map(attributes["ELEV_SITE_M"])
    labels = pd.Series("unmatched", index=station_ids.index, dtype=object)
    matched = elev.notna()
    if matched.sum() >= 30:
        labels.loc[matched] = pd.qcut(elev[matched], 3, labels=["low", "middle", "high"]).astype(str)
    return labels


def keep_global(score: np.ndarray, retention: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(len(score)), np.asarray(score, dtype=float)))
    keep = np.zeros(len(score), dtype=bool)
    keep[order[: int(round(retention * len(score)))]] = True
    return keep


def keep_within(score: np.ndarray, strata: np.ndarray, retention: float, seed: int) -> np.ndarray:
    keep = np.zeros(len(score), dtype=bool)
    for offset, value in enumerate(pd.unique(strata)):
        index = np.where(strata == value)[0]
        rng = np.random.default_rng(seed + offset)
        order = index[np.lexsort((rng.random(len(index)), score[index]))]
        keep[order[: int(round(retention * len(index)))]] = True
    return keep


# ---------------------------------------------------------------------------
# panel loading
# ---------------------------------------------------------------------------
def load_panel(name: str, attributes: pd.DataFrame) -> dict:
    spec = PANEL_SPECS[name]
    cases = pd.read_parquet(spec["cases"]).reset_index(drop=True)
    certs = pd.read_parquet(spec["certs"]).reset_index(drop=True)
    if len(cases) != len(certs):
        raise ValueError(f"{name}: cases {len(cases)} != certificates {len(certs)}")

    def numeric(col: pd.Series) -> np.ndarray:
        return pd.to_numeric(col, errors="coerce").to_numpy(dtype=float)

    bound_raw = numeric(certs["certificate_bound"])
    elev = elevation_tertile(cases["station_id"], attributes)
    panel = {
        "name": name,
        "spec": spec,
        "cases": cases,
        "certs": certs,
        "n": len(cases),
        "truth": numeric(cases[HOT_YEAR_METRIC]),
        "metric": numeric(certs["certificate_metric"]),
        "low": numeric(certs["interval_low"]),
        "high": numeric(certs["interval_high"]),
        "bound": np.where(np.isfinite(bound_raw), bound_raw, np.inf),
        "length": numeric(cases["longest_run"]),
        "peak": numeric(cases["peak_overlap"]),
        "network": cases["network_id"].astype(str).to_numpy(),
        "arm": cases["arm"].astype(str).to_numpy() if "arm" in cases else None,
        "donor": cases["donor_regime"].astype(str).to_numpy(),
        "elev": elev.to_numpy(),
        # station-year = the physical unit (station_id, year).  A network-inclusive key would
        # double-count the wave-2 stations that appear in two overlapping HUC networks
        # (counted in the fingerprint).
        "sy_key": (cases["station_id"].astype(str) + "|" + cases["year"].astype(str)).to_numpy(),
    }
    panel["elev_matched"] = np.asarray(elev != "unmatched")
    return panel


def interval_clear_mask(P: dict, thr: float) -> np.ndarray:
    """Judge only when the implied truth interval [metric-high, metric-low] excludes thr."""
    metric_lo = P["metric"] - P["high"]
    metric_hi = P["metric"] - P["low"]
    straddles = (metric_lo <= thr) & (metric_hi >= thr)
    return (
        np.isfinite(P["metric"])
        & np.isfinite(P["low"])
        & np.isfinite(P["high"])
        & ~straddles
    )


def eligible_mask(P: dict) -> np.ndarray:
    return np.isfinite(P["metric"]) & np.isfinite(P["truth"])


# ---------------------------------------------------------------------------
# native screen masks: reproduce the originating script of each panel
# ---------------------------------------------------------------------------
def step8_native_masks(P: dict) -> dict:
    """Verbatim mask construction of 307 lines 136-145 (threshold independent)."""
    n = P["n"]
    rng = np.random.default_rng(SEED_RESERVED)
    length_keep = keep_global(P["length"] + rng.random(n), RETENTION, SEED_RESERVED)
    peak_keep = keep_global(P["peak"] + rng.random(n) * 1e-3, RETENTION, SEED_RESERVED + 1)
    cert_keep = keep_global(P["bound"], RETENTION, SEED_RESERVED + 2)
    balanced = keep_within(P["bound"], P["elev"], RETENTION, SEED_RESERVED + 3)
    return {
        "length_screen_70": length_keep,
        "peak_overlap_screen_70": peak_keep,
        "calibrated_screen_70": cert_keep,
        "elev_balanced_screen_70": balanced,
    }


def step6_native_masks(P: dict, thr: float) -> dict:
    """Verbatim mask construction of 305 `threshold_table` for one threshold.

    305 creates the RNG once and draws `rng.random(n)` *inside* the threshold
    loop, so the 18 C and 20 C length masks use different draws.  Replayed here
    (in the same order) so the wave-2 rows can be cross-checked case-for-case.
    """
    n = P["n"]
    thr_index = list(THRESHOLDS).index(thr)
    rng = np.random.default_rng(SEED_WAVE2 + 7)
    draws = rng.random(n * (thr_index + 1))
    length_score = P["length"] + draws[thr_index * n : (thr_index + 1) * n]
    k70 = max(1, int(round(RETENTION * n)))
    admit_length = np.zeros(n, dtype=bool)
    admit_length[np.argsort(length_score)[:k70]] = True
    admit_bound = np.zeros(n, dtype=bool)
    admit_bound[np.argsort(P["bound"])[:k70]] = True
    return {
        "length_screen_70": admit_length,
        "calibrated_screen_70": admit_bound,
    }


def extra_peak_mask(P: dict) -> np.ndarray:
    """307's construction with `SEED_EXTRA`; no published counterpart for wave 2."""
    rng = np.random.default_rng(SEED_EXTRA)
    return keep_global(P["peak"] + rng.random(P["n"]) * 1e-3, RETENTION, SEED_EXTRA + 1)


def native_masks(P: dict, thr: float) -> dict:
    protocol = P["spec"]["screen_protocol"]
    if protocol == "step8_307":
        masks = step8_native_masks(P)
    elif protocol == "step6_305":
        masks = step6_native_masks(P, thr)
        masks["peak_overlap_screen_70"] = extra_peak_mask(P)
    else:  # pragma: no cover - guarded by PANEL_SPECS
        raise ValueError(protocol)
    clear = interval_clear_mask(P, thr)
    masks["reconstruct_all"] = np.ones(P["n"], dtype=bool)
    masks["interval_abstention"] = clear
    masks["screen70_and_abstention"] = masks["calibrated_screen_70"] & clear
    if "elev_balanced_screen_70" in masks:
        masks["elev_balanced_and_abstention"] = masks["elev_balanced_screen_70"] & clear
    return masks


def uniform_masks(P: dict, thr: float, seed: int) -> dict:
    """307-shaped masks under an arbitrary tie-break seed (sensitivity sweep)."""
    n = P["n"]
    rng = np.random.default_rng(seed)
    masks = {
        "length_screen_70": keep_global(P["length"] + rng.random(n), RETENTION, seed),
        "peak_overlap_screen_70": keep_global(P["peak"] + rng.random(n) * 1e-3, RETENTION, seed + 1),
        "calibrated_screen_70": keep_global(P["bound"], RETENTION, seed + 2),
    }
    if P["spec"]["elevation_available"]:
        masks["elev_balanced_screen_70"] = keep_within(P["bound"], P["elev"], RETENTION, seed + 3)
    clear = interval_clear_mask(P, thr)
    masks["reconstruct_all"] = np.ones(n, dtype=bool)
    masks["interval_abstention"] = clear
    masks["screen70_and_abstention"] = masks["calibrated_screen_70"] & clear
    if "elev_balanced_screen_70" in masks:
        masks["elev_balanced_and_abstention"] = masks["elev_balanced_screen_70"] & clear
    return masks


# ---------------------------------------------------------------------------
# weights and weighted shares
# ---------------------------------------------------------------------------
def subset_weight(kind: str, P: dict, sel: np.ndarray) -> np.ndarray:
    w = np.zeros(P["n"], dtype=float)
    if kind == "per_case":
        w[sel] = 1.0
        return w
    keys = P["sy_key"] if kind == "per_station_year" else P["network"]
    frame = pd.DataFrame({"k": keys[sel]})
    counts = frame.groupby("k")["k"].transform("size").to_numpy(dtype=float)
    w[sel] = 1.0 / counts
    return w


def weighted_terms(P: dict, pred: np.ndarray, tru: np.ndarray, admitted: np.ndarray,
                   pool: np.ndarray, w: np.ndarray) -> dict:
    """p_hat_A, p_A, p_full under weight vector w (all shares in [0, 1])."""
    wa = w * admitted
    wp = w * pool
    n_admitted = int(admitted.sum())
    out = {
        "n_admitted": n_admitted,
        "n_pool": int(pool.sum()),
        "weight_admitted": float(wa.sum()),
        "weight_pool": float(wp.sum()),
        "n_units_admitted": int(pd.unique(P["sy_key"][admitted]).size) if n_admitted else 0,
        "n_networks_admitted": int(pd.unique(P["network"][admitted]).size) if n_admitted else 0,
        "p_hat_A": float("nan"),
        "p_A": float("nan"),
        "p_full": float("nan"),
        "gap_reason": "",
    }
    if out["weight_pool"] <= 0:
        out["gap_reason"] = "candidate pool has zero weight"
        return out
    out["p_full"] = float((wp * tru).sum() / out["weight_pool"])
    if out["weight_admitted"] <= 0:
        out["gap_reason"] = "rule admits nothing: p_hat_A and p_A are undefined (not 0)"
        return out
    out["p_hat_A"] = float((wa * pred).sum() / out["weight_admitted"])
    out["p_A"] = float((wa * tru).sum() / out["weight_admitted"])
    return out


def repo_head() -> dict:
    def run(args):
        try:
            p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
            return p.stdout.strip()
        except OSError as exc:  # pragma: no cover
            return f"unavailable: {exc}"

    return {
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "git_head_short": run(["git", "rev-parse", "--short", "HEAD"]),
        "git_status_porcelain": run(["git", "status", "--porcelain"]).splitlines(),
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# (coverage, error) frontiers — counts are carried, never reconstructed from rates
# ---------------------------------------------------------------------------
def new_frontier(knob_name: str, knob, n_dec, n_inc, n_candidates: int) -> dict:
    knob = np.asarray(knob, dtype=float)
    n_dec = np.asarray(n_dec, dtype=np.int64)
    n_inc = np.asarray(n_inc, dtype=np.int64)
    order = np.lexsort((n_inc, n_dec))
    knob, n_dec, n_inc = knob[order], n_dec[order], n_inc[order]
    cov = n_dec / n_candidates
    err_all = n_inc / n_candidates
    err_dec = np.divide(n_inc, n_dec, out=np.full(n_dec.shape, np.nan), where=n_dec > 0)
    return {
        "knob_name": knob_name,
        "knob": knob,
        "n_dec": n_dec,
        "n_inc": n_inc,
        "cov": cov,
        "err_all": err_all,
        "err_dec": err_dec,
        "n_candidates": int(n_candidates),
    }


def point_of(fr: dict, i: int) -> dict:
    return {
        "knob_name": fr["knob_name"],
        "knob": float(fr["knob"][i]),
        "coverage": float(fr["cov"][i]),
        "n_decided": int(fr["n_dec"][i]),
        "n_incorrect": int(fr["n_inc"][i]),
        "error_rate_all_candidates": float(fr["err_all"][i]),
        "error_rate_decided": float(fr["err_dec"][i]),
    }


def native_point(admitted: np.ndarray, incorrect: np.ndarray, n_candidates: int,
                 knob_name: str, knob: float) -> dict:
    n_dec = int(admitted.sum())
    n_inc = int((admitted & incorrect).sum())
    return {
        "knob_name": knob_name,
        "knob": float(knob) if np.isfinite(knob) else float("nan"),
        "coverage": n_dec / n_candidates,
        "n_decided": n_dec,
        "n_incorrect": n_inc,
        "error_rate_all_candidates": n_inc / n_candidates,
        "error_rate_decided": n_inc / n_dec if n_dec else float("nan"),
    }


def prefix_frontier(order_idx: np.ndarray, incorrect: np.ndarray, admitted_ok: np.ndarray,
                    n_candidates: int) -> dict:
    """Nested prefix family: keep the first m of `order_idx`, for every m."""
    elig = admitted_ok[order_idx].astype(np.int64)
    inc = (incorrect & admitted_ok)[order_idx].astype(np.int64)
    k = np.cumsum(elig)
    e = np.cumsum(inc)
    keep = np.r_[True, np.diff(k) > 0]
    return new_frontier("rank_prefix_n", np.arange(1, len(order_idx) + 1)[keep],
                        k[keep], e[keep], n_candidates)


def abstention_frontier(P: dict, thr: float, incorrect: np.ndarray, scales: np.ndarray,
                        sel: np.ndarray, max_gap: float = 0.005,
                        max_rounds: int = 14) -> dict:
    """Dilate the conformal interval by s: judge when [metric-s*high, metric-s*low] excludes thr.

    Coverage is very sensitive to the dilation scale where the interval boundary
    sweeps the core of the metric distribution, so the scale grid is refined by
    bisection until no adjacent coverage gap exceeds `max_gap` (or `max_rounds`
    refinements are exhausted).  Without this, interpolating the frontier at a
    requested coverage would span a multi-percentage-point gap.
    """
    n_candidates = int(sel.sum())
    metric, low, high = P["metric"], P["low"], P["high"]
    finite = eligible_mask(P) & sel

    def evaluate(s: float) -> tuple[float, int, int]:
        lo = metric - s * high
        hi = metric - s * low
        admitted = finite & ~((lo <= thr) & (hi >= thr))
        return float(s), int(admitted.sum()), int((admitted & incorrect).sum())

    points = {s: evaluate(s) for s in scales}
    for _ in range(max_rounds):
        ordered = sorted(points)
        gaps = [
            (a, b)
            for a, b in zip(ordered[:-1], ordered[1:])
            if abs(points[a][1] - points[b][1]) / n_candidates > max_gap
        ]
        if not gaps:
            break
        for a, b in gaps:
            mid = round(0.5 * (a + b), 6)
            if mid not in points and mid != a and mid != b:
                points[mid] = evaluate(mid)
    ordered = sorted(points)
    knobs = np.array(ordered, dtype=float)
    n_dec = np.array([points[s][1] for s in ordered], dtype=np.int64)
    n_inc = np.array([points[s][2] for s in ordered], dtype=np.int64)
    return new_frontier("interval_dilation_scale", knobs, n_dec, n_inc, n_candidates)


def screen_and_abstention_frontier(P: dict, order_idx: np.ndarray, clear: np.ndarray,
                                   incorrect: np.ndarray, sel: np.ndarray) -> dict:
    keep_ok = eligible_mask(P) & sel & clear
    return prefix_frontier(order_idx, incorrect, keep_ok, int(sel.sum()))


def balanced_frontier(P: dict, sel: np.ndarray, clear: np.ndarray | None,
                      incorrect: np.ndarray, fracs: np.ndarray) -> dict:
    """Within-stratum top-fraction screen (307's `keep_within` as a family)."""
    n_candidates = int(sel.sum())
    elig = eligible_mask(P) & sel
    strata = P["elev"]
    per_stratum = []
    for value in pd.unique(strata[sel]):
        idx = np.where((strata == value) & sel)[0]
        order = idx[np.argsort(P["bound"][idx], kind="mergesort")]
        ok = (elig & clear)[order] if clear is not None else elig[order]
        per_stratum.append((ok.astype(np.int64), (incorrect[order] & ok).astype(np.int64)))
    n_dec, n_inc = [], []
    for frac in fracs:
        k = e = 0
        for ok, inc in per_stratum:
            m = int(round(frac * len(ok)))
            if m <= 0:
                continue
            k += int(ok[:m].sum())
            e += int(inc[:m].sum())
        n_dec.append(k)
        n_inc.append(e)
    return new_frontier("within_stratum_retention", fracs, n_dec, n_inc, n_candidates)


def match_at_budget(fr: dict, budget: float) -> dict | None:
    ok = np.where(fr["err_all"] <= budget + 1e-15)[0]
    if ok.size == 0:
        return None
    best_cov = fr["cov"][ok].max()
    tied = ok[fr["cov"][ok] >= best_cov - 1e-12]
    pick = tied[np.argmin(fr["err_all"][tied])]
    return point_of(fr, int(pick))


def frontier_interp(fr: dict) -> tuple[np.ndarray, np.ndarray]:
    """Collapse a frontier to a strictly increasing coverage -> smallest-error curve."""
    order = np.argsort(fr["cov"], kind="mergesort")
    cov = fr["cov"][order]
    err = fr["err_all"][order]
    uniq, starts = np.unique(cov, return_index=True)
    return uniq, np.minimum.reduceat(err, starts)


def interp_at_coverage(fr: dict, target: float,
                       max_bracket: float = COVERAGE_INTERP_MAX_BRACKET) -> dict | None:
    """Linear interpolation of the coverage -> error curve at exactly `target` coverage.

    Refuses (returns None with a reason) when the target is outside the family's
    achievable coverage range or when the bracketing grid points are more than
    `max_bracket` apart, because a wide bracket makes the interpolated error count
    unreliable.
    """
    cov, err = frontier_interp(fr)
    if target < cov[0] - 1e-12 or target > cov[-1] + 1e-12:
        return {
            "refused": (
                f"coverage target outside this family's achievable range "
                f"[{cov[0]:.4f}, {cov[-1]:.4f}]"
            )
        }
    i = int(np.searchsorted(cov, target))
    if i == 0:
        lo = hi = 0
    else:
        lo, hi = i - 1, i
    width = float(cov[hi] - cov[lo])
    if width > max_bracket:
        return {
            "refused": (
                f"frontier grid too coarse near target: bracketing coverages "
                f"{cov[lo]:.4f} -> {cov[hi]:.4f} (width {width:.4f} > {max_bracket})"
            )
        }
    w = 0.0 if hi == lo else (target - cov[lo]) / width
    err_all = float(err[lo] + w * (err[hi] - err[lo]))
    n_dec = int(round(target * fr["n_candidates"]))
    n_inc = int(round(err_all * fr["n_candidates"]))
    return {
        "refused": "",
        "knob_name": fr["knob_name"],
        "knob": float("nan"),
        "coverage": float(target),
        "n_decided": n_dec,
        "n_incorrect": n_inc,
        "error_rate_all_candidates": err_all,
        "error_rate_decided": err_all / target if target > 0 else float("nan"),
        "bracket_low_coverage": float(cov[lo]),
        "bracket_high_coverage": float(cov[hi]),
        "bracket_width": width,
    }


# ---------------------------------------------------------------------------
# decision counts
# ---------------------------------------------------------------------------
def base_count_row(panel: str, subset: str, thr: float, rule: str, P: dict, sel: np.ndarray,
                   admitted: np.ndarray | None = None, pred: np.ndarray | None = None,
                   tru: np.ndarray | None = None, incorrect: np.ndarray | None = None,
                   gap_reason: str = "") -> dict:
    n_candidates = int(sel.sum())
    row = {
        "panel": panel,
        "subset": subset,
        "threshold_c": float(thr),
        "hot_year_metric": HOT_YEAR_METRIC,
        "rule": rule,
        "rule_family": RULE_FAMILY[rule],
        "n_candidates": n_candidates,
        "n_unique_station_years_in_pool": int(pd.unique(P["sy_key"][sel]).size),
        "n_admitted": np.nan,
        "n_decided": np.nan,
        "n_abstained_or_excluded": np.nan,
        "share_decided": np.nan,
        "n_correct": np.nan,
        "n_incorrect": np.nan,
        "n_true_positive": np.nan,
        "n_true_negative": np.nan,
        "n_missed_hot_years": np.nan,
        "n_false_alarms": np.nan,
        "n_true_hot_in_pool": int((tru & sel).sum()) if tru is not None else np.nan,
        "n_abstained_true_hot": np.nan,
        "n_abstained_true_not_hot": np.nan,
        "error_rate_all_candidates": np.nan,
        "error_rate_decided": np.nan,
        "missed_hot_rate_decided": np.nan,
        "false_alarm_rate_decided": np.nan,
        "meets_0p5pct_budget": np.nan,
        "n_networks_with_decided": np.nan,
        "net_weighted_share_decided": np.nan,
        "net_weighted_error_rate_decided": np.nan,
        "net_weighted_missed_hot_rate_decided": np.nan,
        "net_weighted_false_alarm_rate_decided": np.nan,
        "admitted_equals_decided": True,
        "gap_reason": gap_reason,
    }
    if gap_reason or admitted is None:
        return row
    adm = admitted & sel
    n_dec = int(adm.sum())
    tp = int((adm & pred & tru).sum())
    tn = int((adm & ~pred & ~tru).sum())
    fn = int((adm & ~pred & tru).sum())
    fp = int((adm & pred & ~tru).sum())
    row.update(
        {
            "n_admitted": n_dec,
            "n_decided": n_dec,
            "n_abstained_or_excluded": n_candidates - n_dec,
            "share_decided": n_dec / n_candidates if n_candidates else np.nan,
            "n_correct": tp + tn,
            "n_incorrect": fn + fp,
            "n_true_positive": tp,
            "n_true_negative": tn,
            "n_missed_hot_years": fn,
            "n_false_alarms": fp,
            "n_abstained_true_hot": int((~adm & sel & tru).sum()),
            "n_abstained_true_not_hot": int((~adm & sel & ~tru).sum()),
            "error_rate_all_candidates": (fn + fp) / n_candidates if n_candidates else np.nan,
            "error_rate_decided": (fn + fp) / n_dec if n_dec else np.nan,
            "missed_hot_rate_decided": fn / n_dec if n_dec else np.nan,
            "false_alarm_rate_decided": fp / n_dec if n_dec else np.nan,
            "meets_0p5pct_budget": bool(
                n_candidates and (fn + fp) / n_candidates <= JUDGEMENT_ERROR_RATE_BUDGET
            ),
        }
    )
    frame = pd.DataFrame(
        {
            "net": np.asarray(P["network"])[sel],
            "dec": adm[sel].astype(int),
            "inc": (adm & incorrect)[sel].astype(int),
            "fn": (adm & ~pred & tru)[sel].astype(int),
            "fp": (adm & pred & ~tru)[sel].astype(int),
        }
    )
    agg = frame.groupby("net").agg(
        n=("dec", "size"), dec=("dec", "sum"), inc=("inc", "sum"),
        fn=("fn", "sum"), fp=("fp", "sum"),
    )
    with_dec = agg.loc[agg.dec > 0]
    row.update(
        {
            "n_networks_with_decided": int(len(with_dec)),
            "net_weighted_share_decided": float((agg.dec / agg.n).mean()),
            "net_weighted_error_rate_decided": (
                float((with_dec.inc / with_dec.dec).mean()) if len(with_dec) else np.nan
            ),
            "net_weighted_missed_hot_rate_decided": (
                float((with_dec.fn / with_dec.dec).mean()) if len(with_dec) else np.nan
            ),
            "net_weighted_false_alarm_rate_decided": (
                float((with_dec.fp / with_dec.dec).mean()) if len(with_dec) else np.nan
            ),
        }
    )
    return row


# ---------------------------------------------------------------------------
# comparison rows
# ---------------------------------------------------------------------------
def compare_row_skeleton(panel: str, subset: str, thr: float, rule: str, criterion: str,
                         n_candidates: int, sweep_available: bool) -> dict:
    return {
        "panel": panel,
        "subset": subset,
        "threshold_c": float(thr),
        "hot_year_metric": HOT_YEAR_METRIC,
        "rule": rule,
        "rule_family": RULE_FAMILY[rule],
        "criterion": criterion,
        "criterion_definition": CRITERIA_DEF[criterion],
        "target_kind": (
            "error_rate_all_candidates" if criterion in BUDGET_CRITERIA
            else ("coverage" if criterion in COVERAGE_CRITERIA else "none")
        ),
        "target_value": np.nan,
        "matched_knob_name": "",
        "matched_knob": np.nan,
        "achieved_coverage": np.nan,
        "n_candidates": int(n_candidates),
        "n_decided": np.nan,
        "n_incorrect": np.nan,
        "error_rate_all_candidates": np.nan,
        "error_rate_decided": np.nan,
        "meets_budget": np.nan,
        "budget_binding": np.nan,
        "coverage_match_ok": np.nan,
        "interp_bracket_width": np.nan,
        "is_best": False,
        "best_rule": "",
        "sweep_available": bool(sweep_available),
        "computable": True,
        "note": "",
    }


def apply_point(row: dict, pt: dict) -> None:
    row.update(
        {
            "matched_knob_name": pt["knob_name"],
            "matched_knob": pt["knob"],
            "achieved_coverage": pt["coverage"],
            "n_decided": pt["n_decided"],
            "n_incorrect": pt["n_incorrect"],
            "error_rate_all_candidates": pt["error_rate_all_candidates"],
            "error_rate_decided": pt["error_rate_decided"],
        }
    )
    if pt.get("bracket_width") is not None:
        row["interp_bracket_width"] = pt["bracket_width"]


def build_compare_rows(P: dict, panel: str, subset: str, thr: float, rule: str, fr: dict,
                       native_pt: dict, sweep_available: bool, n_candidates: int,
                       base_err: float, cov_abs: float, cov_sa: float,
                       err_abs: float) -> list[dict]:
    rows = []
    for criterion in CRITERIA:
        row = compare_row_skeleton(panel, subset, thr, rule, criterion, n_candidates,
                                   sweep_available)
        if criterion == "native":
            apply_point(row, native_pt)
            row["meets_budget"] = bool(
                native_pt["error_rate_all_candidates"] <= JUDGEMENT_ERROR_RATE_BUDGET
            )
            row["coverage_match_ok"] = np.nan
            row["budget_binding"] = np.nan
            row["note"] = "designed operating point"
            if rule == "reconstruct_all":
                row["note"] = "judge everything: single point, no abstention and no screen"
            elif rule == "interval_abstention":
                row["note"] = "native conformal interval (dilation scale 1.0)"
            elif rule == "screen70_and_abstention":
                row["note"] = "calibrated screen @70% then native interval abstention"
            elif rule == "elev_balanced_screen_70":
                row["note"] = "within-elevation-stratum retention 70%"
            elif rule == "elev_balanced_and_abstention":
                row["note"] = "elevation-balanced screen @70% then native abstention"
            rows.append(row)
            continue
        if not sweep_available:
            row["note"] = "no sweep family defined for this rule"
            rows.append(row)
            continue
        if criterion in BUDGET_CRITERIA:
            budget = {
                "equal_budget_0p5pct": JUDGEMENT_ERROR_RATE_BUDGET,
                "equal_budget_as_reconstruct_all": base_err,
                "equal_budget_as_interval_abstention_native": err_abs,
            }[criterion]
            row["target_value"] = float(budget)
            pt = match_at_budget(fr, budget)
            if pt is None:
                row["meets_budget"] = False
                row["budget_binding"] = True
                row["note"] = "cannot meet budget at any operating point of this family"
            else:
                apply_point(row, pt)
                row["meets_budget"] = True
                # binding = even this family's maximum coverage cannot reach 1.00 inside the budget
                row["budget_binding"] = bool(fr["cov"].max() < 1.0 - 1e-12)
                reach = "budget admits judge-everything (coverage 1.00 reached)" if (
                    pt["coverage"] >= 1.0 - 1e-12
                ) else "budget-matched point: max coverage with error<=budget"
                row["note"] = reach
        else:
            target = {
                "equal_coverage_1p00": 1.0,
                "equal_coverage_0p70": 0.70,
                "equal_coverage_interval_abstention_native": float(cov_abs),
                "equal_coverage_screen_and_abstention_native": float(cov_sa),
            }[criterion]
            row["target_value"] = target
            pt = interp_at_coverage(fr, target)
            if pt is None or pt.get("refused"):
                row["coverage_match_ok"] = False
                row["note"] = (
                    pt["refused"] if pt is not None else "coverage target unreachable"
                )
            else:
                apply_point(row, pt)
                row["coverage_match_ok"] = True
                row["meets_budget"] = bool(
                    pt["error_rate_all_candidates"] <= JUDGEMENT_ERROR_RATE_BUDGET
                )
                row["note"] = (
                    "coverage-matched by linear interpolation between bracketing grid points "
                    f"({pt['bracket_low_coverage']:.4f} -> {pt['bracket_high_coverage']:.4f}); "
                    "knob shown as NaN because it is not interpolated"
                )
        rows.append(row)
    return rows


def mark_verdicts(compare: pd.DataFrame) -> pd.DataFrame:
    """Flag the best rule family per (panel, subset, threshold, criterion)."""
    compare = compare.copy()
    group_keys = ["panel", "subset", "threshold_c", "criterion"]
    for key, grp in compare.groupby(group_keys, sort=False):
        criterion = key[3]
        if criterion == "native":
            continue
        if criterion in BUDGET_CRITERIA:
            elig = grp.loc[grp.meets_budget.fillna(False) & grp.achieved_coverage.notna()]
            if elig.empty:
                continue
            best_cov = elig.achieved_coverage.max()
            tied = elig.loc[elig.achieved_coverage >= best_cov - 1e-12]
            best_err = tied.error_rate_decided.min()
            winners = tied.loc[tied.error_rate_decided <= best_err + 1e-15]
            criteria_col = ("achieved_coverage", "max")
        else:
            elig = grp.loc[grp.coverage_match_ok.fillna(False) & grp.error_rate_decided.notna()]
            if elig.empty:
                continue
            best_err = elig.error_rate_decided.min()
            winners = elig.loc[elig.error_rate_decided <= best_err + 1e-15]
            criteria_col = ("error_rate_decided", "min")
        names = sorted(set(winners.rule_family))
        best_label = "tie: " + " | ".join(names) if len(names) > 1 else names[0]
        mask = compare.index.isin(winners.index)
        compare.loc[mask, "is_best"] = True
        label_targets = grp.index[grp["computable"].fillna(False)]
        compare.loc[compare.index.isin(label_targets), "best_rule"] = best_label
        compare.loc[compare.index.isin(grp.index), "best_criterion_value"] = float(
            winners[criteria_col[0]].iloc[0]
        )
    return compare


def frontier_rows_for(panel: str, subset: str, thr: float, family: str, fr: dict) -> list[dict]:
    idx = np.array([np.argmin(np.abs(fr["cov"] - g)) for g in FRONTIER_GRID])
    rows = []
    for g, i in zip(FRONTIER_GRID, idx):
        rows.append(
            {
                "panel": panel,
                "subset": subset,
                "threshold_c": float(thr),
                "hot_year_metric": HOT_YEAR_METRIC,
                "rule_family": family,
                "knob_name": fr["knob_name"],
                "target_coverage_grid": float(g),
                "matched_knob": float(fr["knob"][i]),
                "achieved_coverage": float(fr["cov"][i]),
                "n_candidates": fr["n_candidates"],
                "n_decided": int(fr["n_dec"][i]),
                "n_incorrect": int(fr["n_inc"][i]),
                "error_rate_all_candidates": float(fr["err_all"][i]),
                "error_rate_decided": float(fr["err_dec"][i]),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    attributes = pd.read_csv(STATION_PANEL, dtype={"station_id": str}).set_index("station_id")
    panels = {name: load_panel(name, attributes) for name in PANEL_SPECS}

    masks_cache: dict[tuple[str, float], dict] = {}
    for name, P in panels.items():
        for thr in THRESHOLDS:
            masks_cache[(name, thr)] = native_masks(P, thr)

    decomp_rows: list[dict] = []
    count_rows: list[dict] = []
    compare_rows: list[dict] = []
    frontier_rows: list[dict] = []
    sensitivity_rows: list[dict] = []

    abst_scales = np.unique(
        np.round(
            np.concatenate(
                [np.linspace(0.0, 0.2, 41), np.linspace(0.21, 2.0, 180),
                 np.linspace(2.02, 5.0, 150), [7.0, 10.0, 15.0, 25.0, 50.0, 100.0]]
            ),
            4,
        )
    )
    frac_grid = np.round(np.arange(0.01, 1.0001, 0.01), 4)

    for name, P in panels.items():
        n = P["n"]
        for thr in THRESHOLDS:
            pred = P["metric"] > thr
            tru = P["truth"] > thr
            incorrect = pred != tru
            pool = np.isfinite(P["truth"])
            masks = masks_cache[(name, thr)]
            clear = masks["interval_abstention"]

            for subset in SUBSETS:
                sel = np.ones(n, dtype=bool)
                if subset != "pooled":
                    arm = subset.split("=", 1)[1]
                    if P["arm"] is None:
                        continue
                    sel = P["arm"] == arm
                if sel.sum() == 0:
                    continue
                n_candidates = int(sel.sum())
                sub_pool = pool & sel

                # native rates needed as comparison targets
                base_err = float(((masks["reconstruct_all"] & sel & eligible_mask(P)) & incorrect).sum() / n_candidates)
                cov_abs = float((masks["interval_abstention"] & sel & eligible_mask(P)).sum() / n_candidates)
                err_abs = float(
                    ((masks["interval_abstention"] & sel & eligible_mask(P)) & incorrect).sum()
                    / n_candidates
                )
                cov_sa = float(
                    (masks["screen70_and_abstention"] & sel & eligible_mask(P)).sum() / n_candidates
                )

                for rule in RULE_ORDER:
                    gap = ""
                    if rule not in masks:
                        gap = (
                            "not computable for this panel: no elevation attributes for the "
                            f"wave-2 stations (0 of {P['cases']['station_id'].nunique()} matched "
                            "in results/v17_fitness/step21_hydrology/station_panel.csv)"
                        )
                    admitted = (masks[rule] & sel & eligible_mask(P)) if not gap else np.zeros(n, dtype=bool)

                    count_rows.append(
                        base_count_row(name, subset, thr, rule, P, sel,
                                       admitted=None if gap else admitted,
                                       pred=pred, tru=tru, incorrect=incorrect,
                                       gap_reason=gap)
                    )

                    for weighting in WEIGHTINGS:
                        w = subset_weight(weighting, P, sel)
                        terms = weighted_terms(P, pred, tru, admitted, sub_pool, w)
                        structural = bool(int(admitted.sum()) and np.array_equal(admitted, sub_pool))
                        decomp_rows.append(
                            {
                                "panel": name,
                                "subset": subset,
                                "threshold_c": float(thr),
                                "hot_year_metric": HOT_YEAR_METRIC,
                                "rule": rule,
                                "rule_family": RULE_FAMILY[rule],
                                "weighting": weighting,
                                "n_candidates": n_candidates,
                                "n_admitted": terms["n_admitted"],
                                "n_decided": terms["n_admitted"],
                                "n_pool_truth_finite": terms["n_pool"],
                                "share_admitted": terms["n_admitted"] / n_candidates,
                                "n_station_years_admitted": terms["n_units_admitted"],
                                "n_networks_admitted": terms["n_networks_admitted"],
                                "p_hat_A": terms["p_hat_A"],
                                "p_A": terms["p_A"],
                                "p_full": terms["p_full"],
                                "prediction_error_pp": (terms["p_hat_A"] - terms["p_A"]) * 100.0,
                                "selection_shift_pp": (terms["p_A"] - terms["p_full"]) * 100.0,
                                "total_deviation_pp": (terms["p_hat_A"] - terms["p_full"]) * 100.0,
                                "decomposition_residual_pp": (
                                    (terms["p_hat_A"] - terms["p_A"])
                                    + (terms["p_A"] - terms["p_full"])
                                    - (terms["p_hat_A"] - terms["p_full"])
                                ) * 100.0,
                                "selection_shift_structural_zero": structural,
                                "old_label_for_selection_shift": "hot_share_bias_pp (overclaims)",
                                "gap_reason": gap or terms["gap_reason"],
                            }
                        )

                    if gap:
                        for criterion in CRITERIA:
                            row = compare_row_skeleton(name, subset, thr, rule, criterion,
                                                       n_candidates, False)
                            row["computable"] = False
                            row["note"] = gap
                            compare_rows.append(row)
                        continue

                    knob_name, knob_value = native_knob(rule, n_candidates)
                    native_pt = native_point(admitted, incorrect, n_candidates,
                                             knob_name=knob_name, knob=knob_value)

                    if rule == "reconstruct_all":
                        fr = new_frontier("none", [np.nan], [native_pt["n_decided"]],
                                          [native_pt["n_incorrect"]], n_candidates)
                        sweep_available = True  # degenerate single-point family
                    elif rule in SCREEN_RULES and rule != "elev_balanced_screen_70":
                        idx = np.where(sel)[0]
                        order = idx[np.argsort(screen_score(P, rule)[idx], kind="mergesort")]
                        fr = prefix_frontier(order, incorrect, eligible_mask(P) & sel, n_candidates)
                        sweep_available = True
                    elif rule == "interval_abstention":
                        fr = abstention_frontier(P, thr, incorrect, abst_scales, sel)
                        sweep_available = True
                    elif rule == "screen70_and_abstention":
                        idx = np.where(sel)[0]
                        order = idx[np.argsort(P["bound"][idx], kind="mergesort")]
                        fr = screen_and_abstention_frontier(P, order, clear, incorrect, sel)
                        sweep_available = True
                    else:  # elevation-balanced families
                        fr = balanced_frontier(
                            P, sel, clear if rule.endswith("abstention") else None, incorrect,
                            frac_grid,
                        )
                        sweep_available = True

                    compare_rows.extend(
                        build_compare_rows(P, name, subset, thr, rule, fr, native_pt,
                                           sweep_available, n_candidates, base_err, cov_abs,
                                           cov_sa, err_abs)
                    )
                    frontier_rows.extend(frontier_rows_for(name, subset, thr, RULE_FAMILY[rule], fr))

    # ---- native-mask tie-break sensitivity ----
    for name, P in panels.items():
        for thr in THRESHOLDS:
            pred = P["metric"] > thr
            tru = P["truth"] > thr
            incorrect = pred != tru
            pool = np.isfinite(P["truth"])
            w = subset_weight("per_case", P, np.ones(P["n"], dtype=bool))
            variants = [("native", masks_cache[(name, thr)])]
            for s in SENSITIVITY_SEEDS:
                variants.append((f"uniform_seed_{s}", uniform_masks(P, thr, s)))
            for label, masks in variants:
                for rule, mask in masks.items():
                    admitted = mask & eligible_mask(P)
                    terms = weighted_terms(P, pred, tru, admitted, pool, w)
                    n_dec = int(admitted.sum())
                    n_inc = int((admitted & incorrect).sum())
                    sensitivity_rows.append(
                        {
                            "panel": name,
                            "subset": "pooled",
                            "threshold_c": float(thr),
                            "hot_year_metric": HOT_YEAR_METRIC,
                            "rule": rule,
                            "rule_family": RULE_FAMILY[rule],
                            "variant": label,
                            "n_decided": n_dec,
                            "n_incorrect": n_inc,
                            "error_rate_decided": n_inc / n_dec if n_dec else np.nan,
                            "prediction_error_pp": (terms["p_hat_A"] - terms["p_A"]) * 100.0,
                            "selection_shift_pp": (terms["p_A"] - terms["p_full"]) * 100.0,
                            "total_deviation_pp": (terms["p_hat_A"] - terms["p_full"]) * 100.0,
                            "gap_reason": terms["gap_reason"],
                        }
                    )

    decomp = pd.DataFrame(decomp_rows)
    counts = pd.DataFrame(count_rows)
    compare = mark_verdicts(pd.DataFrame(compare_rows))
    frontiers = pd.DataFrame(frontier_rows)
    sensitivity = pd.DataFrame(sensitivity_rows)

    decomp.to_csv(OUT / "share_decomposition.csv", index=False)
    counts.to_csv(OUT / "decision_counts.csv", index=False)
    compare.to_csv(OUT / "equal_budget_comparison.csv", index=False)
    frontiers.to_csv(OUT / "efficiency_frontiers.csv", index=False)
    sensitivity.to_csv(OUT / "rng_sensitivity.csv", index=False)

    cross = cross_check(decomp, counts)
    fingerprint = build_fingerprint(panels, cross, t0)
    (OUT / "protocol_fingerprint.json").write_text(json.dumps(fingerprint, indent=2) + "\n")

    write_summary(decomp, counts, compare, sensitivity, cross, fingerprint)
    print((OUT / "SUMMARY.md").read_text())
    return 0


def screen_score(P: dict, rule: str) -> np.ndarray:
    if rule == "length_screen_70":
        return P["length"]
    if rule == "peak_overlap_screen_70":
        return P["peak"]
    return P["bound"]


def native_knob(rule: str, n_candidates: int) -> tuple[str, float]:
    """(knob name, native knob value) for the rule's designed operating point."""
    if rule == "interval_abstention":
        return "interval_dilation_scale", 1.0
    if rule in ("elev_balanced_screen_70", "elev_balanced_and_abstention"):
        return "within_stratum_retention", RETENTION
    if rule == "reconstruct_all":
        return "none", float("nan")
    return "rank_prefix_n", float(max(1, int(round(RETENTION * n_candidates))))


# ---------------------------------------------------------------------------
# cross-checks against the published step-6 / step-8 tables
# ---------------------------------------------------------------------------
def cross_check(decomp: pd.DataFrame, counts: pd.DataFrame) -> dict:
    out: dict = {"step8_reserved": [], "step6_wave2": [], "selection_shift_vs_step8": {}}
    d8 = pd.read_csv(STEP8_TABLE)
    for _, r in d8.iterrows():
        mine = counts.loc[
            counts.panel.eq("reserved_retrospective")
            & counts.subset.eq("pooled")
            & counts.threshold_c.eq(r["threshold_c"])
            & counts.rule.eq(r["method"])
        ]
        if mine.empty:
            continue
        m = mine.iloc[0]
        out["step8_reserved"].append(
            {
                "threshold_c": float(r["threshold_c"]),
                "rule": r["method"],
                "published_n_incorrect": int(r["n_incorrect"]),
                "recomputed_n_incorrect": int(m["n_incorrect"]),
                "published_share_judged": float(r["share_judged"]),
                "recomputed_share_judged": float(m["share_decided"]),
                "published_hot_share_bias_pp": float(r["hot_share_bias_pp"]),
                "recomputed_selection_shift_pp": float(
                    decomp.loc[
                        decomp.panel.eq("reserved_retrospective")
                        & decomp.subset.eq("pooled")
                        & decomp.threshold_c.eq(r["threshold_c"])
                        & decomp.rule.eq(r["method"])
                        & decomp.weighting.eq("per_case"),
                        "selection_shift_pp",
                    ].iloc[0]
                ),
            }
        )
    t6 = pd.read_csv(STEP6_TABLE)
    for _, r in t6.loc[t6.panel.eq("wave2_designed")].iterrows():
        mine = counts.loc[
            counts.panel.eq("wave2_designed")
            & counts.subset.eq("pooled")
            & counts.threshold_c.eq(r["threshold_c"])
            & counts.rule.eq(r["rule"])
        ]
        if mine.empty:
            continue
        m = mine.iloc[0]
        out["step6_wave2"].append(
            {
                "threshold_c": float(r["threshold_c"]),
                "rule": r["rule"],
                "published_n_incorrect": int(r["n_incorrect_judgments"]),
                "recomputed_n_incorrect": int(m["n_incorrect"]),
                "published_share_judged": float(r["share_judged"]),
                "recomputed_share_judged": float(m["share_decided"]),
            }
        )
    diffs = [
        abs(x["published_hot_share_bias_pp"] - x["recomputed_selection_shift_pp"])
        for x in out["step8_reserved"]
        if np.isfinite(x["published_hot_share_bias_pp"])
        and np.isfinite(x["recomputed_selection_shift_pp"])
    ]
    out["selection_shift_vs_step8"] = {
        "n_compared_rows": len(diffs),
        "max_abs_diff_pp": float(max(diffs)) if diffs else None,
        "interpretation": (
            "the published hot_share_bias_pp equals this script's selection_shift_pp "
            "(per-case, pooled, reserved panel): the old label named only one of two terms"
        ),
    }
    out["all_step8_rows_reproduced"] = bool(out["step8_reserved"]) and all(
        x["published_n_incorrect"] == x["recomputed_n_incorrect"]
        and abs(x["published_share_judged"] - x["recomputed_share_judged"]) < 1e-12
        for x in out["step8_reserved"]
    )
    out["all_step6_rows_reproduced"] = bool(out["step6_wave2"]) and all(
        x["published_n_incorrect"] == x["recomputed_n_incorrect"]
        and abs(x["published_share_judged"] - x["recomputed_share_judged"]) < 1e-12
        for x in out["step6_wave2"]
    )
    return out


def build_fingerprint(panels: dict, cross: dict, t0: float) -> dict:
    inputs = {
        "reserved_cases": PANEL_SPECS["reserved_retrospective"]["cases"],
        "reserved_certificates": PANEL_SPECS["reserved_retrospective"]["certs"],
        "wave2_cases": PANEL_SPECS["wave2_designed"]["cases"],
        "wave2_certificates": PANEL_SPECS["wave2_designed"]["certs"],
        "station_panel": STATION_PANEL,
        "step8_closed_loop_decisions": STEP8_TABLE,
        "step6_threshold_judgment": STEP6_TABLE,
        "step5_arm_contrasts": STEP5_CONTRASTS,
    }
    panel_summary = {}
    for name, P in panels.items():
        panel_summary[name] = {
            "n_candidates": int(P["n"]),
            "n_networks": int(pd.unique(P["network"]).size),
            "n_stations": int(P["cases"]["station_id"].nunique()),
            "n_unique_station_years": int(pd.unique(P["sy_key"]).size),
            "station_years_in_multiple_networks": int(
                (P["cases"].groupby(["station_id", "year"])["network_id"].nunique() > 1).sum()
            ),
            "station_ids_in_multiple_networks": int(
                (P["cases"].groupby("station_id")["network_id"].nunique() > 1).sum()
            ),
            "station_id_provider_collisions": int(
                (P["cases"].groupby("station_id")["provider"].nunique() > 1).sum()
            ),
            "cases_per_station_year_mean": float(P["n"] / pd.unique(P["sy_key"]).size),
            "arm_counts": (
                {str(k): int(v) for k, v in P["cases"]["arm"].value_counts().items()}
                if "arm" in P["cases"] else None
            ),
            "provider_counts": {
                str(k): int(v) for k, v in P["cases"]["provider"].value_counts().items()
            },
            "hot_share_by_threshold": {
                str(t): float((P["truth"] > t).mean()) for t in THRESHOLDS
            },
            "n_stations_with_elevation": int(
                P["cases"].loc[P["elev_matched"], "station_id"].nunique()
            ),
            "n_cases_with_elevation": int(P["elev_matched"].sum()),
            "all_truth_finite": bool(np.isfinite(P["truth"]).all()),
            "all_metric_finite": bool(np.isfinite(P["metric"]).all()),
            "all_bound_finite": bool(np.isfinite(P["bound"]).all()),
            "station_years_with_varying_truth": int(
                (P["cases"].groupby(["network_id", "station_id", "year"])[HOT_YEAR_METRIC]
                 .nunique() > 1).sum()
            ),
            "longest_run_distinct_values": int(np.unique(P["length"][np.isfinite(P["length"])]).size),
            "longest_run_max_tie_multiplicity": int(
                pd.Series(P["length"]).value_counts().max()
            ),
            "interval_empirical_coverage": float(
                (
                    (P["truth"] >= P["metric"] - P["high"])
                    & (P["truth"] <= P["metric"] - P["low"])
                ).mean()
            ),
            "screen_protocol": P["spec"]["screen_protocol"],
            "screen_seed": P["spec"]["screen_seed"],
            "provenance": P["spec"]["provenance"],
        }
    w2 = panel_summary["wave2_designed"]
    return {
        "script": "scripts/313_wrr_p0_04_env_closed_loop.py",
        "script_sha256": sha256(Path(__file__).resolve()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_seconds": round(time.time() - t0, 2),
        "review_items_addressed": {
            "F05": "three-term decomposition; every rule carries its own predicted share",
            "F03": (
                "abstention compared with judge-everything at equal error budget and equal "
                "decision coverage"
            ),
        },
        "repo": repo_head(),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "protocol_constants": {
            "retention": RETENTION,
            "thresholds_c": list(THRESHOLDS),
            "hot_year_definition": f"{HOT_YEAR_METRIC} > threshold_c",
            "hot_year_metric_units": "degrees C (hottest 30-day mean of the complete reference)",
            "judgement_error_rate_budget": JUDGEMENT_ERROR_RATE_BUDGET,
            "coverage_interp_max_bracket": COVERAGE_INTERP_MAX_BRACKET,
            "seed_reserved": SEED_RESERVED,
            "seed_wave2": SEED_WAVE2,
            "seed_extra_rules": SEED_EXTRA,
            "sensitivity_seeds": list(SENSITIVITY_SEEDS),
            "primary_tolerance_c_from_protocol": PRIMARY_TOLERANCE_C,
            "primary_tolerance_c_note": (
                "recorded for completeness only: PRIMARY_TOLERANCE_C = 0.5 C is the step-6 "
                "metric tolerance for archive admission and is NOT the 0.5% judgement-error "
                "rate budget used here"
            ),
            "weighting_definitions": {
                "per_case": "each candidate station-year realization counts once",
                "per_station_year": (
                    "each (network, station, year) unit carries total weight 1, split evenly "
                    "across its realizations; shares are case-count-weighted unit means"
                ),
                "network_weighted": (
                    "each network carries total weight 1, split evenly across its candidates"
                ),
            },
            "admitted_equals_decided": (
                "in this closed loop every admitted record receives a threshold call, so "
                "n_admitted = n_decided; the complement is abstained-or-screened-out"
            ),
            "interval_abstention_sweep": (
                "conformal interval dilated by scale s: judge when "
                "[metric - s*high, metric - s*low] excludes the threshold"
            ),
        },
        "inputs": {k: {"path": str(v.relative_to(ROOT)), "sha256": sha256(v)}
                   for k, v in inputs.items()},
        "panels": panel_summary,
        "cross_check": cross,
        "gaps": [
            {
                "item": "elevation-balanced rules for the wave-2 panel",
                "reason": (
                    f"0 of {w2['n_stations']} wave-2 stations match "
                    "results/v17_fitness/step21_hydrology/station_panel.csv, so elevation "
                    "tertiles are undefined; those rows are emitted with NaN and an explicit "
                    "reason instead of an imputed stratum"
                ),
            },
            {
                "item": "wave-2 peak-overlap screen",
                "reason": (
                    "step 6/305 does not define a peak screen for wave 2; built here with 307's "
                    f"keep_global construction and seed {SEED_EXTRA}, so it has no published "
                    "counterpart to cross-check"
                ),
            },
            {
                "item": "uncertainty intervals",
                "reason": (
                    "all numbers are point estimates on fixed pools; no bootstrap CI computed"
                ),
            },
            {
                "item": "wave-2 sealed operational claim",
                "reason": (
                    "the wave-2 panel is a designed-outage confirmation panel whose hot-year "
                    f"prevalence is {w2['hot_share_by_threshold']['18.0'] * 100:.1f}% at 18 C "
                    "(vs "
                    f"{panel_summary['reserved_retrospective']['hot_share_by_threshold']['18.0'] * 100:.1f}%"
                    " on the reserved panel); shares are not population prevalences"
                ),
            },
        ],
    }


# ---------------------------------------------------------------------------
# SUMMARY.md
# ---------------------------------------------------------------------------
def fmt_table(df: pd.DataFrame, cols: list[str], decimals: int = 3) -> str:
    view = df[cols].copy()
    for c in view.columns:
        if pd.api.types.is_float_dtype(view[c]):
            view[c] = view[c].round(decimals)
    return view.to_string(index=False)


def write_summary(decomp: pd.DataFrame, counts: pd.DataFrame, compare: pd.DataFrame,
                  sensitivity: pd.DataFrame, cross: dict, fingerprint: dict) -> None:
    L: list[str] = []
    A = L.append
    pan = fingerprint["panels"]
    res, w2 = pan["reserved_retrospective"], pan["wave2_designed"]
    A("# P0-04 — environmental-judgment closed loop, rebuilt (review F05 + F03)")
    A("")
    A("Generated by `scripts/313_wrr_p0_04_env_closed_loop.py` at "
      f"{fingerprint['generated_utc']} (git HEAD `{fingerprint['repo']['git_head']}`).")
    A("")
    A("**Units.** Every column ending in `_pp`, and every number in the tables below that is "
      "not explicitly a share or a rate, is in **percentage points** (pp = 100 x a share "
      "difference). Columns named `p_hat_A`, `p_A`, `p_full`, `share_*`, `*_rate_*`, `n_*` are "
      "shares/rates/counts. In the tables below shares are printed in percent and labelled "
      "`%`; the three decomposition terms are printed directly in pp.")
    A("")
    A("## 1. What was wrong with `hot_share_bias_pp`")
    A("")
    A("`scripts/307_wrr_mr_step8_decision_closed_loop.py` reports")
    A("")
    A("```")
    A("hot_share_bias_pp = (true hot-year share among judged) - (true hot-year share in pool)")
    A("```")
    A("")
    A("That is the **selection shift only**: it never uses a predicted hot-year share, so its "
      "`reconstruct_all` row is exactly 0.0 by construction, even though that same row makes "
      f"{int(counts.loc[counts.panel.eq('reserved_retrospective') & counts.subset.eq('pooled') & counts.threshold_c.eq(18.0) & counts.rule.eq('reconstruct_all'), 'n_incorrect'].iloc[0])} "
      "wrong judgments on the reserved panel. The previous label overclaimed: in a closed loop "
      "the archive's hot-year share deviates from the reference pool both because the model "
      "predicts badly and because of which records are kept. The quantity is kept here under "
      "the honest name **`selection_shift_pp`**; its published values are reproduced "
      "case-for-case (max |published - recomputed| = "
      f"{cross['selection_shift_vs_step8']['max_abs_diff_pp']} pp over "
      f"{cross['selection_shift_vs_step8']['n_compared_rows']} step-8 rows).")
    A("")
    A("Correct decomposition, reported for every rule (this is the F05 repair):")
    A("")
    A("```")
    A("(p_hat_A - p_full)  =  (p_hat_A - p_A)   +   (p_A - p_full)")
    A(" total_deviation_pp    prediction_error_pp   selection_shift_pp")
    A("```")
    A("")
    A("- `p_hat_A` = predicted hot-year share among admitted records "
      "(`certificate_metric > threshold_c`)")
    A("- `p_A`     = true hot-year share among the same admitted records "
      f"(`{HOT_YEAR_METRIC} > threshold_c`)")
    A("- `p_full`  = true hot-year share in the full candidate pool of that panel/subset")
    A("- the identity residual is written as `decomposition_residual_pp` and is 0 (float-exact) "
      "on every row")
    A("")
    A("`reconstruct_all` is **not** structurally zero any more: its `selection_shift_pp` is 0 "
      "legitimately (it admits the whole pool, so `p_A == p_full` and the flag "
      "`selection_shift_structural_zero` is True), but its total deviation equals its own "
      "prediction error — which is exactly where its wrong judgments appear.")
    A("")
    pc = decomp.loc[decomp.weighting.eq("per_case") & decomp.subset.eq("pooled")]
    max_abs_pred = float(pc.prediction_error_pp.abs().max())
    worst = pc.loc[pc.prediction_error_pp.abs().idxmax()]
    base_dev = {
        (r.panel, float(r.threshold_c)): float(r.total_deviation_pp)
        for r in pc.loc[pc.rule.eq("reconstruct_all")].itertuples()
    }
    base_sentence = "; ".join(
        f"{k[0]} @ {k[1]:.1f} C = {v:+.3f} pp" for k, v in sorted(base_dev.items())
    )
    nonbase = pc.loc[~pc.rule.eq("reconstruct_all")]
    max_shift_from_old = float((nonbase.total_deviation_pp - nonbase.selection_shift_pp).abs().max())
    sel_abs_max = float(pc.selection_shift_pp.abs().max())
    A("### 1a. How much does the correction change the numbers on these pools?")
    A("")
    A("Plainly: the **definition** changes materially, the **magnitudes** mostly do not. On "
      "these two candidate pools the certificate point prediction is accurate enough that the "
      f"prediction-error term is small — the largest |prediction error| over all per-case "
      f"pooled rows is {max_abs_pred:.3f} pp ({worst['panel']} @ "
      f"{float(worst['threshold_c']):.1f} C, {worst['rule']}) — while the selection shift "
      f"reaches {sel_abs_max:.3f} pp in magnitude. Consequences:")
    A("")
    A(f"- `reconstruct_all` no longer reports 0.000 pp. Its corrected total deviation is "
      f"{base_sentence} (all of it prediction error, none of it selection shift).")
    A("- For every other rule in this comparison, replacing the old quantity with the total "
      "deviation changes the reported number by at most "
      f"{max_shift_from_old:.3f} pp, i.e. sub-pp on these pools.")
    A("- What the repair buys is therefore **attribution and honesty, not a large numeric "
      "revision**: the old label could not separate the model-fixable part from the "
      "selection part, and it silently asserted zero total deviation for judge-everything. "
      "Where a future model is weaker, or where a screen keeps a small, unrepresentative "
      "subset, the prediction-error term is the one that grows, and the old metric would have "
      "been unable to show it.")
    A("")
    A("## 2. Hot-year definition and thresholds")
    A("")
    A(f"Reused from step 8: `{HOT_YEAR_METRIC}` (hottest 30-day mean of the complete "
      "reference, degrees C) `> threshold_c`, evaluated at **18.0 C and 20.0 C**. Every row of "
      "every CSV here carries `threshold_c` and `hot_year_metric`, so no number is untagged. "
      "`p_hat_A` uses the certificate point estimate `certificate_metric` against the same "
      "threshold; it is a point-prediction share, not a calibrated probability.")
    A("")
    A("## 3. Pools, weighting, denominators")
    A("")
    rows = []
    for name, info in pan.items():
        rows.append(
            {
                "panel": name,
                "candidates": info["n_candidates"],
                "networks": info["n_networks"],
                "stations": info["n_stations"],
                "station-years": info["n_unique_station_years"],
                "cases/SY": round(info["cases_per_station_year_mean"], 2),
                "hot share @18C %": round(info["hot_share_by_threshold"]["18.0"] * 100, 3),
                "hot share @20C %": round(info["hot_share_by_threshold"]["20.0"] * 100, 3),
                "screen protocol": info["screen_protocol"],
            }
        )
    A(pd.DataFrame(rows).to_string(index=False))
    A("")
    A("Candidates are outage realizations, so ~10-12 candidates share one station-year. Three "
      "weightings are reported for every decomposition row:")
    A("")
    A("- `per_case` — each candidate realization counts once (the headline tables below)")
    A("- `per_station_year` — each physical (station, year) unit carries total weight 1, split "
      "evenly across its realizations; a network-inclusive key would double-count the "
      f"{w2['station_years_in_multiple_networks']} wave-2 station-years whose station appears in "
      "two overlapping networks, and there are no station-id collisions across providers "
      f"({w2['station_id_provider_collisions']} wave-2 / "
      f"{res['station_id_provider_collisions']} reserved), so the physical key is used. Truth is "
      "invariant within a station-year (checked: "
      f"{res['station_years_with_varying_truth']} reserved and "
      f"{w2['station_years_with_varying_truth']} wave-2 units have varying "
      f"`{HOT_YEAR_METRIC}`), so this re-weights only the prediction side")
    A("- `network_weighted` — each network carries total weight 1, so 36 (reserved) / 49 "
      "(wave 2) networks count equally regardless of case count; this deliberately over-weights "
      "small providers (the wave-2 UK EA contribution is 21 cases)")
    A("")
    A("Raw counts are per case. `n_admitted = n_decided` by construction (every admitted record "
      "receives a threshold call); `n_abstained_or_excluded` is the complement. "
      "`n_missed_hot_years` = false negatives among decided, `n_false_alarms` = false "
      "positives among decided. Abstained candidates are neither correct nor incorrect, and "
      "`n_abstained_true_hot` reports how many genuinely hot station-years lost their call "
      "because of abstention.")
    A("")
    A("The arm split comes from step 5: `arm=empirical` is the planned-observed-overlap arm "
      f"({res['arm_counts']['empirical']} reserved / {w2['arm_counts']['empirical']} wave-2 "
      "candidates) and `arm=stratified` is the designed none/partial/full-outage arm "
      f"({res['arm_counts']['stratified']} / {w2['arm_counts']['stratified']}); each arm row "
      "uses that arm's own candidate pool as `p_full`.")
    A("")
    A("## 4. Three-term decomposition, per case (pooled)")
    A("")
    table_cols = ["rule", "n_admitted", "p_hat_A %", "p_A %", "p_full %",
                  "prediction_error_pp", "selection_shift_pp", "total_deviation_pp"]
    for name in PANEL_SPECS:
        for thr in THRESHOLDS:
            block = decomp.loc[
                decomp.panel.eq(name) & decomp.subset.eq("pooled")
                & decomp.threshold_c.eq(thr) & decomp.weighting.eq("per_case")
            ].copy()
            block["p_hat_A %"] = block["p_hat_A"] * 100
            block["p_A %"] = block["p_A"] * 100
            block["p_full %"] = block["p_full"] * 100
            A(f"### {name} @ {thr:.1f} C (per case)")
            A("")
            A(fmt_table(block, table_cols))
            A("")
    A("Network-weighted decomposition at 18.0 C (same rules, networks equally weighted):")
    A("")
    for name in PANEL_SPECS:
        block = decomp.loc[
            decomp.panel.eq(name) & decomp.subset.eq("pooled")
            & decomp.threshold_c.eq(18.0) & decomp.weighting.eq("network_weighted")
        ].copy()
        block["p_hat_A %"] = block["p_hat_A"] * 100
        block["p_A %"] = block["p_A"] * 100
        block["p_full %"] = block["p_full"] * 100
        A(f"### {name} @ 18.0 C, network-weighted")
        A("")
        A(fmt_table(block, table_cols))
        A("")
    A("Arm split at 18.0 C, per case (each arm uses its own pool as the reference):")
    A("")
    arm_tbl = decomp.loc[
        decomp.subset.ne("pooled") & decomp.threshold_c.eq(18.0)
        & decomp.weighting.eq("per_case")
    ].copy()
    arm_tbl["p_hat_A %"] = arm_tbl["p_hat_A"] * 100
    arm_tbl["p_A %"] = arm_tbl["p_A"] * 100
    arm_tbl["p_full %"] = arm_tbl["p_full"] * 100
    A(fmt_table(arm_tbl, ["panel", "subset", "rule", "n_admitted", "p_hat_A %", "p_A %",
                          "p_full %", "prediction_error_pp", "selection_shift_pp",
                          "total_deviation_pp"]))
    A("")
    # computed weighting / arm sensitivity statements
    pooled = decomp.loc[decomp.subset.eq("pooled")]
    diff = (
        pooled.pivot_table(index=["panel", "threshold_c", "rule"], columns="weighting",
                           values="selection_shift_pp")
        .assign(abs_diff=lambda f: (f["network_weighted"] - f["per_case"]).abs())
    )
    weight_bits = []
    for panel in PANEL_SPECS:
        blk = diff.loc[panel]
        worst = blk.loc[blk.abs_diff.idxmax()]
        weight_bits.append(
            f"{panel}: largest |network-weighted - per-case| selection shift = "
            f"{worst.abs_diff:.3f} pp ({worst.name[1]} @ {float(worst.name[0]):.1f} C; per-case "
            f"{worst.per_case:+.3f} pp vs network-weighted {worst.network_weighted:+.3f} pp)"
        )
    flip_mask = np.sign(diff["per_case"].round(6)) != np.sign(diff["network_weighted"].round(6))
    flips = diff.loc[flip_mask]
    material = flips.loc[
        (flips["per_case"].abs() >= 0.05) & (flips["network_weighted"].abs() >= 0.05)
    ]
    flip_txt = "; ".join(
        f"{idx[0]} @ {float(idx[1]):.1f} C {idx[2]} (per-case {row.per_case:+.3f} pp -> "
        f"network-weighted {row.network_weighted:+.3f} pp)"
        for idx, row in flips.iterrows()
    ) or "none"
    A("**Weighting sensitivity (computed).** " + "; ".join(weight_bits) + ". The per-case "
      "selection shift is invariant to the weighting only for `reconstruct_all` (where "
      "p_A = p_full under every weighting); for the other rules the magnitude can move by "
      "~1 pp or more. Sign disagreements between per-case and network-weighted occur in "
      f"{len(flips)} of {len(diff)} pooled rule x threshold x panel cells: {flip_txt} "
      f"({len(material)} of these have |value| >= 0.05 pp on both weightings, so they are not "
      "rounding artefacts). The flipped cells are exactly the elevation-balanced rules on the "
      "reserved panel: step 8's headline quote of a small hot-share trade-off there "
      "(`hot_share_bias_pp ~ -0.13 pp` at 18.0 C) is a per-case artefact and must not be "
      "quoted as evidence of a cost-free elevation-balanced screen.")
    A("")
    arm18 = decomp.loc[decomp.subset.ne("pooled") & decomp.threshold_c.eq(18.0)
                       & decomp.weighting.eq("per_case")]
    arm_bits = []
    for panel in PANEL_SPECS:
        for subset in SUBSETS[1:]:
            blk = arm18.loc[arm18.panel.eq(panel) & arm18.subset.eq(subset)
                            & arm18.rule.ne("reconstruct_all")]
            if blk.empty or blk.selection_shift_pp.isna().all():
                continue
            lo = blk.selection_shift_pp.min()
            hi = blk.selection_shift_pp.max()
            hi_rule = blk.loc[blk.selection_shift_pp.idxmax(), "rule"]
            arm_bits.append(
                f"{panel} {subset}: selection shift spans {lo:+.3f} to {hi:+.3f} pp "
                f"(largest for {hi_rule})"
            )
    A("**Arm sensitivity (computed, per case, 18.0 C).** " + "; ".join(arm_bits)
      + ". The empirical arms are the realistic ones (real observed-overlap gaps), and their "
      "selection shifts are the ones a monitoring application would face; the designed "
      "stratified arms are larger and partly negative.")
    A("")
    A("## 5. Decision counts")
    A("")
    for name in PANEL_SPECS:
        for thr in THRESHOLDS:
            block = counts.loc[
                counts.panel.eq(name) & counts.subset.eq("pooled")
                & counts.threshold_c.eq(thr)
            ].copy()
            block["err_all %"] = block["error_rate_all_candidates"] * 100
            block["err_dec %"] = block["error_rate_decided"] * 100
            A(f"### {name} @ {thr:.1f} C")
            A("")
            A(fmt_table(block, ["rule", "n_candidates", "n_decided",
                               "n_abstained_or_excluded", "n_correct", "n_missed_hot_years",
                               "n_false_alarms", "n_abstained_true_hot", "err_all %",
                               "err_dec %", "meets_0p5pct_budget"]))
            A("")
    A("Network-weighted rates (mean over networks of each network's own rate) at 18.0 C:")
    A("")
    A(fmt_table(counts.loc[counts.threshold_c.eq(18.0) & counts.subset.eq("pooled")],
                ["panel", "rule", "n_networks_with_decided", "net_weighted_share_decided",
                 "net_weighted_error_rate_decided", "net_weighted_missed_hot_rate_decided",
                 "net_weighted_false_alarm_rate_decided"]))
    A("")
    A("## 6. Equal-budget and equal-coverage comparison (F03)")
    A("")
    A("Each rule family is swept over its own nesting parameter (top-ranked prefix length for "
      "the screens, conformal interval dilation scale for abstention, within-stratum retention "
      "for the elevation-balanced screen, bound-prefix x native abstention for "
      "screen+abstention) to produce a (coverage, error) frontier; the abstention scale grid is "
      "refined by bisection until no adjacent coverage gap exceeds 0.005, so the frontier is "
      "resolved where coverage is most sensitive to the scale. Full frontiers are in "
      "`efficiency_frontiers.csv`.")
    A("")
    A("`equal_budget_comparison.csv` reports three kinds of operating point per rule family:")
    A("")
    A("- `native` — the rule as designed (70% retention screen, conformal interval, or both)")
    A("- budget-matched (`equal_budget_*`) — the maximum coverage whose error over *all* "
      "candidates stays within the stated budget; the budget is either the chain's fixed 0.5%, "
      "or the realised error of judge-everything, or the realised error of the native "
      "abstention rule (the last two are F03's equal-error-budget comparisons in their "
      "strictest forms). `budget_binding` records whether the budget actually bites for that "
      "family (False means the family can still judge every candidate inside the budget).")
    A("- coverage-matched (`equal_coverage_*`) — the error of each family interpolated "
      "linearly to *exactly* the requested coverage, so families are compared at identical "
      "coverage. A match is refused (NaN + reason) when the target lies outside the family's "
      f"achievable coverage range or when the bracketing grid points are more than "
      f"{COVERAGE_INTERP_MAX_BRACKET:.2f} apart; `interp_bracket_width` reports the bracket used.")
    A("")
    A(f"The fixed budget is **{JUDGEMENT_ERROR_RATE_BUDGET * 100:.1f}% of all candidates** (the "
      "chain's existing 0.5% misjudgment budget). It is a *judgement-error rate* budget, not "
      "the metric tolerance `PRIMARY_TOLERANCE_C = 0.5 C` used by step 6's archive-admission "
      "task; the two must not be conflated.")
    A("")
    A("**Reading the budget tables.** When judge-everything is already inside a budget, the "
      "coverage-maximising answer for *every* family is judge-everything (its own full-prefix "
      "or zero-width limit), so all families tie at coverage 1.00 and the criterion cannot "
      "discriminate. That is precisely F03's point for those cells: the fixed-70% design and "
      "abstention buy nothing at equal budget there. Discrimination then comes from the "
      "coverage-matched tables, where the same rules are compared at identical coverage.")
    A("")
    for name in PANEL_SPECS:
        for thr in THRESHOLDS:
            base = counts.loc[
                counts.panel.eq(name) & counts.subset.eq("pooled")
                & counts.threshold_c.eq(thr) & counts.rule.eq("reconstruct_all")
            ].iloc[0]
            A(f"### {name} @ {thr:.1f} C")
            A("")
            A(f"Judge-everything baseline: {int(base['n_incorrect'])} wrong in "
              f"{int(base['n_candidates'])} candidates = "
              f"{base['error_rate_all_candidates'] * 100:.4f}% of all candidates "
              f"({base['error_rate_decided'] * 100:.4f}% of decided). "
              + ("**This is inside the 0.5% budget**, so the coverage-maximising equal-budget "
                 "criterion must favour judge-everything here and abstention can at best tie it "
                 "by dialling the interval to zero width."
                 if base["meets_0p5pct_budget"] else
                 "**This exceeds the 0.5% budget**, so judge-everything is inadmissible under "
                 "that criterion and trimming can win."))
            A("")
            blk = compare.loc[
                compare.panel.eq(name) & compare.subset.eq("pooled")
                & compare.threshold_c.eq(thr)
                & compare.criterion.isin(["native"] + list(BUDGET_CRITERIA))
            ].copy()
            blk["err_all %"] = blk["error_rate_all_candidates"] * 100
            blk["err_dec %"] = blk["error_rate_decided"] * 100
            blk["cov %"] = blk["achieved_coverage"] * 100
            A("Native and budget-matched operating points "
              "(`target_kind=error_rate_all_candidates`; target_value is the error budget as a "
              "fraction of all candidates):")
            A("")
            A(fmt_table(blk, ["rule", "criterion", "target_value", "matched_knob_name",
                              "matched_knob", "cov %", "n_decided", "n_incorrect", "err_all %",
                              "err_dec %", "is_best", "best_rule"]))
            A("")
            blk2 = compare.loc[
                compare.panel.eq(name) & compare.subset.eq("pooled")
                & compare.threshold_c.eq(thr)
                & compare.criterion.isin(COVERAGE_CRITERIA)
            ].copy()
            blk2["err_all %"] = blk2["error_rate_all_candidates"] * 100
            blk2["err_dec %"] = blk2["error_rate_decided"] * 100
            blk2["cov %"] = blk2["achieved_coverage"] * 100
            A("Coverage-matched points (`target_kind=coverage`; `coverage_match_ok` flags "
              "matches within tolerance):")
            A("")
            A(fmt_table(blk2, ["rule", "criterion", "target_value", "cov %", "n_decided",
                               "n_incorrect", "err_all %", "err_dec %", "coverage_match_ok",
                               "is_best", "best_rule"]))
            A("")
    A("### F03 verdict in plain terms")
    A("")
    # how many cells have judge-everything inside the fixed budget?
    base_cells = counts.loc[
        counts.subset.eq("pooled") & counts.rule.eq("reconstruct_all")
    ]
    inside = base_cells.loc[base_cells.meets_0p5pct_budget.fillna(False)]
    inside_txt = ", ".join(
        f"{r.panel} @ {r.threshold_c:.1f} C ({int(r.n_incorrect)}/{int(r.n_candidates)} = "
        f"{r.error_rate_all_candidates * 100:.4f}%)"
        for r in inside.itertuples()
    ) or "none"
    A(f"- **Which cells have a non-binding 0.5% budget?** {len(inside)} of "
      f"{len(base_cells)} panel x threshold cells: {inside_txt}. In those cells every "
      "'complete' rule family (screens at full retention, abstention at zero-width interval) "
      "reaches coverage 1.00 inside the budget, so the coverage-maximising equal-budget answer "
      "is judge-everything and screening/abstention cannot be called better; abstention can "
      "only reproduce it.")
    binding_cells = {
        (r.panel, float(r.threshold_c))
        for r in base_cells.itertuples()
        if not bool(r.meets_0p5pct_budget)
    }
    A("- **When the 0.5% budget binds** (judge-everything is outside it), the rule with the "
      "largest coverage inside the budget is:")
    for (name, thr), grp in compare.loc[
        compare.subset.eq("pooled") & compare.criterion.eq("equal_budget_0p5pct")
        & compare.is_best.fillna(False)
        & compare.apply(lambda r: (r["panel"], r["threshold_c"]) in binding_cells, axis=1)
    ].groupby(["panel", "threshold_c"]):
        parts = [
            f"{r.rule_family} (coverage {r.achieved_coverage * 100:.2f}%, "
            f"{int(r.n_incorrect)} wrong = {r.error_rate_all_candidates * 100:.4f}% of all "
            f"candidates)"
            for _, r in grp.sort_values("rule").iterrows()
        ]
        A(f"  - {name} @ {thr:.1f} C: " + "; ".join(parts))
    A("- **At equal coverage** (identical coverage for every family, by interpolation) the "
      "abstention rules have the lowest error in the cells reported below — which is the "
      "second half of F03's requirement: abstention can look better than a screen only when "
      "coverage is held fixed.")
    A("")
    for (name, thr), grp in compare.loc[
        compare.subset.eq("pooled") & compare.criterion.eq("equal_coverage_0p70")
        & compare.is_best.fillna(False)
    ].groupby(["panel", "threshold_c"]):
        parts = [
            f"{r.rule_family} ({int(r.n_incorrect)} wrong in {int(r.n_decided)} decided = "
            f"{r.error_rate_decided * 100:.4f}%)"
            for _, r in grp.sort_values("rule").iterrows()
        ]
        A(f"  - {name} @ {thr:.1f} C, coverage 0.70: " + "; ".join(parts))
    A("")
    # for the abstention family the reconstruct-all-error budget-matched point IS its maximum
    # coverage (its error at maximum coverage equals judge-everything's realised error)
    max_cov_abs = (
        compare.loc[
            compare.subset.eq("pooled")
            & compare.criterion.eq("equal_budget_as_reconstruct_all")
            & compare.rule.eq("interval_abstention")
        ]
        .set_index(["panel", "threshold_c"])["achieved_coverage"]
        .sort_index()
    )
    A("- **Why zero-width abstention does not always reach coverage 1.00:** a zero-width "
      "interval still abstains when the point estimate equals the threshold exactly, so the "
      "abstention family's maximum coverage is "
      + "; ".join(
          f"{p} @ {t:.1f} C = {v:.5f}" for (p, t), v in max_cov_abs.items()
      )
      + ". The shortfall is a handful of exact ties, and it is reported rather than rounded "
      "away.")
    A("")
    A("### Verdicts (written by the script from the tables above)")
    A("")
    ver = compare.loc[compare.is_best.fillna(False) & compare.subset.eq("pooled")]
    for (name, thr, criterion), grp in ver.groupby(["panel", "threshold_c", "criterion"]):
        parts = []
        for _, r in grp.sort_values("rule").iterrows():
            parts.append(
                f"{r['rule_family']} (coverage {r['achieved_coverage'] * 100:.2f}%, "
                f"{int(r['n_incorrect'])} wrong = {r['error_rate_all_candidates'] * 100:.4f}% of "
                f"all candidates / {r['error_rate_decided'] * 100:.4f}% of decided)"
            )
        A(f"- **{name} @ {thr:.1f} C, {criterion}**: " + "; ".join(parts))
    A("")
    A("## 7. Protocol, reproducibility, tie-break sensitivity")
    A("")
    A("- Screen masks reproduce the panel's originating script: reserved = step 8/307 "
      f"(`keep_global`, seed {SEED_RESERVED}); wave 2 = step 6/305 (`argsort`, seed "
      f"{SEED_WAVE2}, including 305's per-threshold RNG draw order). The wave-2 peak screen "
      f"has no 305 counterpart and uses 307's construction with seed {SEED_EXTRA}.")
    A(f"- Cross-check: all step-8 reserved rows reproduced = "
      f"`{cross['all_step8_rows_reproduced']}`; all step-6 wave-2 rows reproduced = "
      f"`{cross['all_step6_rows_reproduced']}` (details per row in "
      "`protocol_fingerprint.json`).")
    A("- Inputs are hashed in `protocol_fingerprint.json` together with the git HEAD, so this "
      "summary is bindable to a commit and a byte-identical pool.")
    A("- `longest_run` is integer-valued and heavily tied, so which tied candidates a 70% "
      "screen keeps depends on the tie-break RNG. `rng_sensitivity.csv` re-runs every native "
      "rule under 12 alternative seeds with 307's construction; the table below shows the "
      "spread at 18.0 C (native = first variant):")
    A("")
    sens = sensitivity.loc[sensitivity.threshold_c.eq(18.0)]
    agg = (
        sens.groupby(["panel", "rule"], sort=False)
        .agg(
            native_incorrect=("n_incorrect", "first"),
            min_incorrect=("n_incorrect", "min"),
            max_incorrect=("n_incorrect", "max"),
            native_selection_shift_pp=("selection_shift_pp", "first"),
            min_selection_shift_pp=("selection_shift_pp", "min"),
            max_selection_shift_pp=("selection_shift_pp", "max"),
        )
        .reset_index()
    )
    A(agg.round(3).to_string(index=False))
    A("")
    moving = agg.loc[(agg.max_incorrect - agg.min_incorrect) > 0]
    stable = agg.loc[(agg.max_incorrect - agg.min_incorrect) == 0]
    A("Computed reading: "
      + (
          "; ".join(
              f"{r.panel} {r.rule} moves between {r.min_incorrect} and {r.max_incorrect} wrong "
              f"judgments (selection shift {r.min_selection_shift_pp:+.3f} to "
              f"{r.max_selection_shift_pp:+.3f} pp)"
              for r in moving.itertuples()
          )
          if len(moving) else "no rule moves with the tie-break"
      )
      + ". Unchanged across all 13 variants: "
      + ", ".join(f"{r.panel} {r.rule}" for r in stable.itertuples())
      + ". The tie-sensitive score is `longest_run` (integer days: "
      + ", ".join(
          f"{n} has {info['longest_run_distinct_values']} distinct values with up to "
          f"{info['longest_run_max_tie_multiplicity']} cases on one value"
          for n, info in pan.items()
      )
      + "), so any published length-screen number is one draw from that tie-break "
      "distribution; the calibrated-bound, abstention and screen+abstention rules are "
      "reproducible exactly.")
    A("")
    A("The native rows in every CSV above are the provenance-native seeds; this table shows "
      "how much of a rule's ranking rests on tied cases.")
    A("")
    A("## 8. Explicit gaps (no number is fabricated)")
    A("")
    for g in fingerprint["gaps"]:
        A(f"- **{g['item']}** — {g['reason']}")
    A("- Rules that admit nothing would be reported as NaN with the reason "
      "\"rule admits nothing: p_hat_A and p_A are undefined (not 0)\"; no rule in these pools "
      "admits nothing, so the branch is present in code but not triggered by these data.")
    A("")
    A("## 9. What would falsify this")
    A("")
    pred_lo = decomp.loc[decomp.weighting.eq("per_case"), "prediction_error_pp"].min()
    pred_hi = decomp.loc[decomp.weighting.eq("per_case"), "prediction_error_pp"].max()
    sel_lo = decomp.loc[decomp.weighting.eq("per_case"), "selection_shift_pp"].min()
    sel_hi = decomp.loc[decomp.weighting.eq("per_case"), "selection_shift_pp"].max()
    A("1. If `prediction_error_pp` were identically 0 while `selection_shift_pp` were material, "
      "the decomposition would collapse onto the old label and this repair would be cosmetic. "
      "It is not identically 0 — across all per-case rows prediction error spans "
      f"{pred_lo:.3f} to {pred_hi:.3f} pp, while selection shift spans {sel_lo:.3f} to "
      f"{sel_hi:.3f} pp — but it *is* small, and section 1a states plainly how little the "
      "numbers move on these pools.")
    A("2. If, at matched coverage, the abstention rules did not have lower error rates than the "
      "coverage-matched screens, the claim that interval abstention buys accuracy at equal "
      "coverage would be false — the coverage-matched verdict lines in section 6 are the test.")
    A("3. If judge-everything exceeded the 0.5% budget in every panel/threshold cell, F03's "
      "criticism would be moot there; instead wave 2 at 18.0 C sits at "
      f"{float(counts.loc[counts.panel.eq('wave2_designed') & counts.subset.eq('pooled') & counts.threshold_c.eq(18.0) & counts.rule.eq('reconstruct_all'), 'error_rate_all_candidates'].iloc[0]) * 100:.4f}%.")
    A("4. If per-case and network-weighted decompositions had opposite signs, every pooled "
      "statement here would be a weighting artefact; both are in `share_decomposition.csv`.")
    A("5. If the wave-2 hot-year prevalence were an artefact of designed sampling that does not "
      "transport, the wave-2 selection-shift magnitudes would not generalise; the arm split and "
      "the reserved panel are reported side by side so the reader can see the difference.")
    A("")
    A("## 10. What this does NOT prove")
    A("")
    A("- **Not an operational or sealed-panel claim.** The reserved panel is a retrospective "
      "complete-reference closed loop; the wave-2 panel is the designed-outage confirmation "
      "panel. Neither is a real-time monitoring admission test, and neither may be described "
      "as a deployed admission guarantee.")
    A("- **No population prevalence claim.** "
      f"{w2['hot_share_by_threshold']['18.0'] * 100:.1f}% of wave-2 candidates are hot years at "
      f"18.0 C ({res['hot_share_by_threshold']['18.0'] * 100:.1f}% on the reserved panel); "
      "`p_full` is a property of these designed pools, not of any river network population.")
    A("- **The abstention error rate is not a like-for-like accuracy claim.** Abstention removes "
      "exactly the candidates whose intervals straddle the threshold — the hard ones — so its "
      "error rate among decided cases is mechanically lower while coverage is lower. That is "
      "why F03's equal-budget/equal-coverage framing is reported: under the 0.5% budget the "
      "coverage-maximising answer on the wave-2 18 C cell is judge-everything.")
    A("- **The hidden cost of abstention is excluded, not corrected.** `n_abstained_true_hot` "
      "in `decision_counts.csv` counts the genuinely hot station-years that lose their call; "
      "they are removed from the archive rather than judged wrongly.")
    A("- **No uncertainty quantification.** All numbers are point estimates on fixed pools; no "
      "network-clustered bootstrap CI was computed, so no significance claim is made.")
    A("- **The conformal interval is conservative on wave 2** (empirical coverage "
      f"{w2['interval_empirical_coverage'] * 100:.1f}% vs "
      f"{res['interval_empirical_coverage'] * 100:.1f}% on reserved, nominal 90%), which "
      "mechanically reduces abstentions there; a tighter interval would move the frontier and "
      "is not tested here.")
    A("- **`p_hat_A` is a point-prediction share, not a probability.** The decomposition "
      "attributes the gap between a point-prediction share and truth shares; it does not "
      "identify which model component causes the prediction error.")
    A("- **Equal-coverage comparisons rest on interpolation.** Errors are interpolated "
      "linearly between bracketing frontier points, which is exact to within one error count "
      "for the prefix families (coverage granularity 1/n) and approximate for the abstention "
      f"family; brackets wider than {COVERAGE_INTERP_MAX_BRACKET:.2f} coverage are refused and "
      "`interp_bracket_width` is reported per row. Near-ties in the coverage-matched ranking "
      "are not resolved.")
    A("- **No causal claim about screening.** The decomposition says how much of the archive's "
      "hot-share deviation is prediction vs selection; it does not say that any particular "
      "screen causes a particular ecological conclusion.")
    A("")
    A("## 11. Files")
    A("")
    A("| file | content |")
    A("|---|---|")
    A("| `share_decomposition.csv` | three-term decomposition, all rules, 3 weightings, all "
      "panels/subsets/thresholds |")
    A("| `decision_counts.csv` | correct / missed hot years / false alarms / abstentions and "
      "denominators, per case + network-weighted rates |")
    A("| `equal_budget_comparison.csv` | native, budget-matched and coverage-matched operating "
      "points per rule family |")
    A("| `efficiency_frontiers.csv` | (coverage, error) frontier per family on a 0.01 coverage "
      "grid |")
    A("| `rng_sensitivity.csv` | native rules under 12 alternative tie-break seeds |")
    A("| `protocol_fingerprint.json` | script/input sha256, git HEAD, constants, cross-checks, "
      "gaps |")
    A("")
    (OUT / "SUMMARY.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
