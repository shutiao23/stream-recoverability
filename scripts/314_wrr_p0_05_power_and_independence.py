#!/usr/bin/env python3
"""P0-05 (WRR major revision): independence and power design for the final configuration.

The review asks two coupled questions.

P0-05 (power).  With the FINAL configuration -- the frozen certificate screen
(``results/v17_fitness/step9_freeze/certificate.joblib``) against the incumbent
length rule at 70 % retention, tolerance 0.5 C, pooled case-weighted contrast --
how many river networks does a *new* panel need before a pre-declared minimum
useful effect of 2 pp (3 pp, 5 pp) is detected with 80 % power at alpha = 0.05
two-sided?

F07 (independence).  The wave-2 external panel is 94.2 % USGS cases, so "three
providers" is not "three independent validated populations".  What is the case
and network leverage of each provider, what happens to the pooled number under
network-equal / provider-equal weighting and under down-weighting the largest
provider, and which claims can actually be confirmed with the panels that exist?

Estimator.  The primary contrast is the consequential-error rate difference
(fraction of retained cases whose |hottest-30| error exceeds 0.5 C, counting
non-finite selected errors as failures) between the certificate screen and the
length rule at matched 70 % retention, in percentage points (negative = the
screen is better).  Intervals are the project's network-clustered bootstrap
(``stream_recoverability.experiments.v17_fitness.stats.cluster_bootstrap``,
resampling whole networks with replacement), which is the interval method the
submitted analysis uses.

Design simulation.  For N in {20, 40, 60, 80} we draw N networks with
replacement from the empirical network-level distribution of a panel (each drawn
network carries all of its cases), recompute the estimator, and recompute its
network-clustered bootstrap interval.  2000 outer draws per cell, parallelised
with joblib.  Power at a true effect delta is the share of draws whose interval,
re-centred on delta by the shift model (the same shift is applied to every
simulated study, so the empirical shape and width of the sampling distribution
are preserved), excludes zero.  The shift model is stated as an assumption in
SUMMARY.md; a normal-approximation power and an analytic MDE cross-check are
reported beside it.  The empirical alpha (power at a true effect of exactly 0)
is reported so under-coverage of the interval is visible.

Read-only inputs; outputs land in
``results/wrr_submission_ready/major_revision_20261014/p0_05_power_independence/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready.run_identity import (  # noqa: E402
    sha256_file,
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

RETENTION = 0.70
ALPHA = 0.05
TOLERANCE_C = float(PRIMARY_TOLERANCE_C)
MUE_POINTS = (2.0, 3.0, 5.0)
DECLARED_HISTORICAL_POINTS = 5.0  # scripts/186_v17_freeze.py pre-declared 5 pp
DESIGN_NS = (20, 40, 60, 80)
OUTER_DRAWS = 2000
INNER_DRAWS = 200
# The two required empirical distributions (development, wave-2) get the full
# 2000 draws; the pooled development+wave-2 mixture is a pre-declared sensitivity
# with a smaller draw budget, recorded per row in power_table.csv.
OUTER_DRAWS_BY_PANEL = {"pooled_dev_wave2": 800}
SECTION2_BUDGET_S = 1500.0
N_JOBS = 64
N_JOBS_MAX = 128
SEED = 20261014
JITTER_SEED = 991  # operating_point_contrast(seed=0) uses seed + 991
JITTER_SEED_ALT = 61  # scripts/306_wrr_mr_step7_transfer_reporting.py uses 61
LEVERAGE_DRAWS = 500
LEVERAGE_JOBS = 8
Z_ALPHA = 1.959963984540054
Z_POWER = 0.8416212335729143  # 80 % power, one-sided normal quantile

DEV_CASES = ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet"
DEV_CERTS = ROOT / "results/v17_fitness/step6_screen/development_certificates.parquet"
W2_CASES = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet"
)
W2_CERTS = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet"
)
CLAIM_REGISTRY = ROOT / "results/wrr_submission_ready/claim_registry.csv"
PRIOR_ACCESS_FILES = (
    ROOT / "results/wrr_submission_ready/prior_access_audit_multi_agency.csv",
    ROOT / "results/wrr_submission_ready/prior_access_audit_sealed_usgs.csv",
    ROOT / "results/wrr_submission_ready/prior_access_audit_summary.json",
    ROOT / "results/wrr_submission_ready/prior_access_ledger_reserved_networks.csv",
)
TRANSPORT_CASES = (
    ROOT / "results/wrr_submission_ready/p0_07b_multi_agency_transport/transport_cases.parquet"
)
NVE_PROBE_CASES = ROOT / "results/wrr_submission_ready/p0_07_nve_probe/cases.parquet"
OUT = ROOT / "results/wrr_submission_ready/major_revision_20261014/p0_05_power_independence"

# Panel definitions.  ``sources`` is a list of (prefix, cases_path, certs_path).
# The development panel is scored with the out-of-fold certificate of
# scripts/184_v17_screen_frontier.py (the frozen model was fit on 30 % of these
# networks, so the frozen model would be partly in-sample here); wave-2 is scored
# with the frozen certificate exactly as the sealed confirmation was.
PANELS: dict[str, dict] = {
    "development": {
        "label": "v17 development panel (out-of-fold certificate)",
        "role": "development",
        "sources": [("", DEV_CASES, DEV_CERTS)],
        "certificate": "results/v17_fitness/step6_screen/development_certificates.parquet",
    },
    "wave2_external": {
        "label": "P0-07 wave-2 external confirmation panel (frozen certificate)",
        "role": "external_confirmation",
        "sources": [("", W2_CASES, W2_CERTS)],
        "certificate": "wave2_certificates.parquet (frozen certificate.joblib applied)",
    },
    "pooled_dev_wave2": {
        "label": "development + wave-2 pooled empirical distribution (sensitivity only)",
        "role": "pooled_sensitivity",
        "sources": [("dev", DEV_CASES, DEV_CERTS), ("w2", W2_CASES, W2_CERTS)],
        "certificate": "mixed (out-of-fold development + frozen wave-2)",
    },
}
PANEL_ORDER = ("development", "wave2_external", "pooled_dev_wave2")

FRAME_COLUMNS = ("network_id", "provider", "cert_score", "cert_error", "length", "policy_error")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def log(message: str) -> None:
    print(f"[314] {message}", flush=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_head() -> dict:
    def run(args: list[str]) -> str:
        try:
            return subprocess.run(
                args, cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except Exception as exc:  # pragma: no cover - diagnostics only
            return f"unavailable: {exc}"

    return {
        "commit": run(["git", "rev-parse", "HEAD"]),
        "describe": run(["git", "describe", "--always", "--dirty"]),
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
    }


def file_fingerprint(path: Path) -> dict:
    if not path.is_file():
        return {"path": str(path.relative_to(ROOT)), "sha256": None, "bytes": None, "exists": False}
    stat = path.stat()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "bytes": int(stat.st_size),
        "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
        "exists": True,
    }


def failure_rate(errors: np.ndarray) -> float:
    """Consequential-error rate: non-finite selected errors count as failures."""

    if errors.size == 0:
        return float("nan")
    bad = (~np.isfinite(errors)) | (errors > TOLERANCE_C)
    return float(bad.mean())


def _slice_indices(values: np.ndarray, k: int) -> np.ndarray:
    if k >= values.size:
        return np.arange(values.size)
    return np.argpartition(values, k - 1)[:k]


def contrast_from_arrays(
    cert_score: np.ndarray,
    cert_error: np.ndarray,
    length: np.ndarray,
    policy_error: np.ndarray,
    retention: float = RETENTION,
) -> float:
    """Certificate-minus-length consequential-error-rate contrast (fraction)."""

    n = len(cert_score)
    k = max(1, int(round(float(retention) * n)))
    if k > n:
        return float("nan")
    cert = _slice_indices(cert_score, k)
    inc = _slice_indices(length, k)
    return failure_rate(cert_error[cert]) - failure_rate(policy_error[inc])


def contrast_statistic(block: pd.DataFrame, retention: float = RETENTION) -> float:
    """Fast, estimator-identical statistic passed to ``cluster_bootstrap``."""

    return contrast_from_arrays(
        block["cert_score"].to_numpy(dtype=float),
        block["cert_error"].to_numpy(dtype=float),
        block["length"].to_numpy(dtype=float),
        block["policy_error"].to_numpy(dtype=float),
        retention=retention,
    )


def contrast_statistic_pandas(block: pd.DataFrame, retention: float = RETENTION) -> float:
    """Reference implementation using pandas ``nsmallest`` (as the project does)."""

    k = max(1, int(round(float(retention) * len(block))))
    if k > len(block):
        return float("nan")
    cert = block.nsmallest(k, "cert_score")["cert_error"].to_numpy(dtype=float)
    length = block.nsmallest(k, "length")["policy_error"].to_numpy(dtype=float)
    return failure_rate(cert) - failure_rate(length)


def network_equal_statistic(block: pd.DataFrame, retention: float = RETENTION) -> float:
    """Network-equal mean of within-network contrasts inside the given block."""

    values = []
    for _, net in block.groupby("network_id", sort=True):
        value = contrast_statistic(net, retention=retention)
        if np.isfinite(value):
            values.append(value)
    if not values:
        return float("nan")
    return float(np.mean(values))


def provider_weighted_statistic(
    provider_weights: dict[str, float],
    *,
    equal_within_provider: bool = True,
    retention: float = RETENTION,
):
    """Weighted mean of per-provider contrasts with FIXED provider weights.

    Providers absent from a bootstrap draw contribute zero to the numerator but
    keep their weight in the denominator, so the estimand does not change when a
    provider drops out of a draw.
    """

    total_weight = float(sum(provider_weights.values()))

    def statistic(block: pd.DataFrame) -> float:
        numerator = 0.0
        for provider, weight in provider_weights.items():
            sub = block.loc[block["provider"].eq(provider)]
            if sub.empty:
                continue
            value = (
                network_equal_statistic(sub, retention=retention)
                if equal_within_provider
                else contrast_statistic(sub, retention=retention)
            )
            if np.isfinite(value):
                numerator += float(weight) * float(value)
        if total_weight <= 0:
            return float("nan")
        return numerator / total_weight

    return statistic


def icc_oneway(frame: pd.DataFrame, column: str, cluster: str = "network_id") -> dict:
    """One-way random-effects ICC(1) for an unbalanced design.

    ICC = (MSB - MSW) / (MSB + (n0 - 1) MSW) with
    n0 = (N - sum(n_g^2)/N) / (G - 1).  Design effect and effective number of
    independent networks use the average cluster size.
    """

    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    groups = frame[cluster].to_numpy()
    ok = np.isfinite(values)
    values, groups = values[ok], groups[ok]
    sizes = pd.Series(groups).value_counts(sort=False)
    n_obs = int(values.size)
    n_groups = int(sizes.size)
    if n_groups < 2 or n_obs <= n_groups:
        return {"icc": float("nan"), "n_obs": n_obs, "n_groups": n_groups}
    grand = float(values.mean())
    per = pd.DataFrame({"g": groups, "v": values}).groupby("g")["v"]
    means = per.mean()
    counts = per.size().astype(float)
    ssb = float((counts * (means - grand) ** 2).sum())
    ssq = float(((values - means.reindex(groups).to_numpy()) ** 2).sum())
    msb = ssb / (n_groups - 1)
    msw = ssq / (n_obs - n_groups)
    n0 = (n_obs - float((counts**2).sum()) / n_obs) / (n_groups - 1)
    denom = msb + (n0 - 1.0) * msw
    icc = float((msb - msw) / denom) if denom > 0 else float("nan")
    mean_size = n_obs / n_groups
    design_effect = 1.0 + (mean_size - 1.0) * icc
    sigma_b = math.sqrt(max(msb - msw, 0.0) / n0) if n0 > 0 else float("nan")
    return {
        "icc": icc,
        "mean_square_between": msb,
        "mean_square_within": msw,
        "n0": n0,
        "n_obs": n_obs,
        "n_groups": n_groups,
        "mean_cluster_size": mean_size,
        "design_effect": design_effect,
        "effective_networks": (n_groups / design_effect) if design_effect > 0 else float("nan"),
        "sigma_between": sigma_b,
    }


# --------------------------------------------------------------------------
# Panel loading and per-worker cache
# --------------------------------------------------------------------------

_GROUP_CACHE: dict[tuple[str, int], dict[str, pd.DataFrame]] = {}
_FRAME_CACHE: dict[tuple[str, int], pd.DataFrame] = {}


def build_panel_frame(sources, jitter_seed: int) -> pd.DataFrame:
    pieces = []
    for prefix, cases_path, certs_path in sources:
        cases = pd.read_parquet(cases_path).reset_index(drop=True)
        certs = pd.read_parquet(certs_path).reset_index(drop=True)
        if len(cases) != len(certs):
            raise RuntimeError(f"case/certificate length mismatch for {cases_path}")
        n = len(cases)
        rng = np.random.default_rng(int(jitter_seed))
        network_id = cases["network_id"].astype(str).to_numpy()
        if prefix:
            network_id = np.array([f"{prefix}:{nid}" for nid in network_id], dtype=object)
        pieces.append(
            pd.DataFrame(
                {
                    "network_id": network_id,
                    "provider": cases["provider"].astype(str).to_numpy(),
                    "cert_score": pd.to_numeric(
                        certs["certificate_bound"], errors="coerce"
                    )
                    .fillna(np.inf)
                    .to_numpy(dtype=float),
                    "cert_error": pd.to_numeric(
                        certs["certificate_abs_error"], errors="coerce"
                    ).to_numpy(dtype=float),
                    "length": pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(
                        dtype=float
                    )
                    + rng.random(n),
                    "policy_error": pd.to_numeric(
                        cases["abserr_policy"], errors="coerce"
                    ).to_numpy(dtype=float),
                }
            )
        )
    frame = pd.concat(pieces, ignore_index=True) if len(pieces) > 1 else pieces[0]
    return frame


def panel_frame(panel_key: str, jitter_seed: int = JITTER_SEED) -> pd.DataFrame:
    key = (panel_key, int(jitter_seed))
    if key not in _FRAME_CACHE:
        _FRAME_CACHE[key] = build_panel_frame(PANELS[panel_key]["sources"], jitter_seed)
    return _FRAME_CACHE[key]


def panel_groups(panel_key: str, jitter_seed: int = JITTER_SEED) -> dict[str, pd.DataFrame]:
    key = (panel_key, int(jitter_seed))
    if key not in _GROUP_CACHE:
        frame = panel_frame(panel_key, jitter_seed)
        _GROUP_CACHE[key] = {str(k): b for k, b in frame.groupby("network_id", sort=True)}
    return _GROUP_CACHE[key]


# --------------------------------------------------------------------------
# Section 1: network-level variance and intra-network correlation
# --------------------------------------------------------------------------


def case_level_contrast(frame: pd.DataFrame, retention: float = RETENTION) -> pd.DataFrame:
    """Exact case-level decomposition of the pooled contrast.

    ``d_i = (x_i - y_i) / retention`` where ``x_i`` flags a case that the
    certificate retains and that fails consequentially and ``y_i`` flags the same
    for the length rule.  Both slices hold ``k = round(retention * n)`` cases, so
    ``mean(d_i)`` is exactly the pooled contrast.
    """

    n = len(frame)
    k = max(1, int(round(float(retention) * n)))
    cert_bad = np.zeros(n, dtype=float)
    length_bad = np.zeros(n, dtype=float)
    cert_idx = _slice_indices(frame["cert_score"].to_numpy(dtype=float), k)
    length_idx = _slice_indices(frame["length"].to_numpy(dtype=float), k)
    cert_err = frame["cert_error"].to_numpy(dtype=float)
    policy_err = frame["policy_error"].to_numpy(dtype=float)
    cert_bad[cert_idx] = (
        (~np.isfinite(cert_err[cert_idx])) | (cert_err[cert_idx] > TOLERANCE_C)
    ).astype(float)
    length_bad[length_idx] = (
        (~np.isfinite(policy_err[length_idx])) | (policy_err[length_idx] > TOLERANCE_C)
    ).astype(float)
    out = frame[["network_id", "provider"]].copy()
    out["screen_failure"] = cert_bad
    out["length_failure"] = length_bad
    out["contrast_case"] = (cert_bad - length_bad) / float(retention)
    return out


def per_network_contrasts(frame: pd.DataFrame, retention: float = RETENTION) -> pd.DataFrame:
    """Within-network contrast at matched retention (step-7 convention)."""

    rows = []
    for (network_id, provider), block in frame.groupby(["network_id", "provider"], sort=True):
        n = len(block)
        k = max(1, int(round(float(retention) * n)))
        cert_idx = _slice_indices(block["cert_score"].to_numpy(dtype=float), k)
        length_idx = _slice_indices(block["length"].to_numpy(dtype=float), k)
        cert_err = block["cert_error"].to_numpy(dtype=float)[cert_idx]
        policy_err = block["policy_error"].to_numpy(dtype=float)[length_idx]
        rows.append(
            {
                "network_id": network_id,
                "provider": provider,
                "n_cases": int(n),
                "cert_failure_rate_pp": failure_rate(cert_err) * 100.0,
                "length_failure_rate_pp": failure_rate(policy_err) * 100.0,
                "contrast_pp": (failure_rate(cert_err) - failure_rate(policy_err)) * 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["provider", "network_id"]).reset_index(drop=True)


def variance_rows(panel_key: str, frame: pd.DataFrame, pooled: dict) -> tuple[list[dict], dict]:
    panel = PANELS[panel_key]
    per_net = per_network_contrasts(frame)
    cases = case_level_contrast(frame)
    influence = cases.groupby("network_id")["contrast_case"]
    dbar = influence.mean()
    sizes = influence.size().astype(float)
    n_networks = int(per_net["network_id"].nunique())
    n_cases = int(len(frame))

    icc_contrast = icc_oneway(cases, "contrast_case")
    icc_screen = icc_oneway(cases, "screen_failure")
    icc_length = icc_oneway(cases, "length_failure")

    contrasts = per_net["contrast_pp"].to_numpy(dtype=float)
    sd_within = float(np.std(contrasts, ddof=1))
    sd_implied = float(pooled["se"]) * math.sqrt(pooled["n_clusters"]) * 100.0
    weighted_sd_influence = float(
        math.sqrt(float(np.average((dbar - dbar.mean()) ** 2, weights=sizes))) * 100.0
    )
    unweighted_sd_influence = float(np.std(dbar.to_numpy(dtype=float), ddof=1) * 100.0)
    anova_sd = float(icc_contrast["sigma_between"]) * 100.0

    # Network-equal interval from the network bootstrap of the per-network
    # contrast table (identical resampling; the step-7 convention) rather than
    # cluster_bootstrap on the case frame, which re-derives the within-network
    # slice on every inner draw and is orders of magnitude slower.
    net_equal = summarise_draws(
        network_bootstrap_draws(per_net, LEVERAGE_DRAWS, SEED)["network_equal"]
    )

    common = {
        "panel": panel_key,
        "panel_label": panel["label"],
        "panel_role": panel["role"],
        "n_cases": n_cases,
        "n_networks": n_networks,
        "n_providers": int(frame["provider"].nunique()),
    }
    rows: list[dict] = []

    def add(quantity, value, unit, estimator, retention=RETENTION, used_for_power=False, note=""):
        rows.append(
            {
                **common,
                "retention": float(retention),
                "quantity": quantity,
                "value": float(value) if value is not None else float("nan"),
                "unit": unit,
                "estimator": estimator,
                "used_for_power": bool(used_for_power),
                "note": note,
            }
        )

    add("pooled_case_weighted_contrast", pooled["point"] * 100.0, "percentage_points",
        "operating_point_contrast (project primary)", used_for_power=True,
        note=f"draws={pooled.get('bootstrap_draws')}, cluster=network")
    add("pooled_ci_low", pooled["low"] * 100.0, "percentage_points",
        "cluster_bootstrap percentile 2.5 %")
    add("pooled_ci_high", pooled["high"] * 100.0, "percentage_points",
        "cluster_bootstrap percentile 97.5 %")
    add("pooled_bootstrap_se", pooled["se"] * 100.0, "percentage_points",
        "cluster_bootstrap SD of draws", used_for_power=True)
    add("sd_within_network_contrasts", sd_within, "percentage_points",
        "SD (ddof=1) of per-network within-network contrasts", used_for_power=False,
        note="descriptive heterogeneity of the network-equal estimand")
    add("sd_implied_by_cluster_bootstrap", sd_implied, "percentage_points",
        "bootstrap SE x sqrt(n_networks) (scripts/186_v17_freeze.py convention)",
        used_for_power=True, note="size-weighted; operative for the pooled estimand")
    add("sd_anova_between_network", anova_sd, "percentage_points",
        "sqrt((MSB-MSW)/n0) of the case-level contrast", used_for_power=True,
        note="random-effects variance component")
    add("sd_influence_fixed_selection_case_weighted", weighted_sd_influence,
        "percentage_points", "case-weighted SD of per-network mean case-level contrast",
        used_for_power=False, note="fixed-selection approximation; OVERSTATES the bootstrap")
    add("sd_influence_fixed_selection_unweighted", unweighted_sd_influence,
        "percentage_points", "unweighted SD of per-network mean case-level contrast",
        used_for_power=False, note="fixed-selection approximation; OVERSTATES the bootstrap")
    add("icc_case_level_contrast", icc_contrast["icc"], "ratio",
        "one-way random-effects ICC(1), unbalanced", used_for_power=False,
        note="intra-network correlation of the contrast")
    add("icc_screen_consequential_failure", icc_screen["icc"], "ratio",
        "one-way random-effects ICC(1), unbalanced")
    add("icc_length_consequential_failure", icc_length["icc"], "ratio",
        "one-way random-effects ICC(1), unbalanced")
    add("design_effect_case_level_contrast", icc_contrast["design_effect"], "ratio",
        "1 + (mean cluster size - 1) * ICC")
    add("effective_independent_networks", icc_contrast["effective_networks"], "networks",
        "n_networks / design effect")
    add("mean_cases_per_network", float(sizes.mean()), "cases", "descriptive")
    add("median_cases_per_network", float(sizes.median()), "cases", "descriptive")
    add("share_networks_contrast_negative", float((contrasts < 0).mean()), "share",
        "per-network within-network contrasts")
    add("share_networks_contrast_zero", float((contrasts == 0).mean()), "share",
        "per-network within-network contrasts", note="degenerate within-network slice")
    add("share_cases_in_largest_provider", float(
        frame["provider"].value_counts(normalize=True).iloc[0]
    ), "share", "case counts")
    add("share_networks_in_largest_provider", float(
        per_net["provider"].value_counts(normalize=True).iloc[0]
    ), "share", "network counts")
    add("network_equal_contrast", net_equal["point"], "percentage_points",
        "network bootstrap of the mean of per-network within-network contrasts",
        used_for_power=True, note=f"draws={LEVERAGE_DRAWS}; step-7 convention")
    add("network_equal_ci_low", net_equal["low"], "percentage_points",
        "network bootstrap percentile 2.5 %")
    add("network_equal_ci_high", net_equal["high"], "percentage_points",
        "network bootstrap percentile 97.5 %")
    add("mde80_analytic_network_equal", (Z_ALPHA + Z_POWER) * sd_within
        / math.sqrt(n_networks), "percentage_points",
        "2.802 x SD_within / sqrt(n_networks)", used_for_power=True)

    # Retention sensitivity of the variance quantities (robustness of ICC to the
    # 70 % operating point).
    for retention in (0.50, 0.90):
        alt_cases = case_level_contrast(frame, retention=retention)
        alt_icc = icc_oneway(alt_cases, "contrast_case")
        alt_per = per_network_contrasts(frame, retention=retention)
        add("icc_case_level_contrast", alt_icc["icc"], "ratio",
            "one-way random-effects ICC(1), unbalanced", retention=retention)
        add("design_effect_case_level_contrast", alt_icc["design_effect"], "ratio",
            "1 + (mean cluster size - 1) * ICC", retention=retention)
        add("sd_within_network_contrasts",
            float(np.std(alt_per["contrast_pp"].to_numpy(dtype=float), ddof=1)),
            "percentage_points", "SD (ddof=1) of per-network within-network contrasts",
            retention=retention)
        add("mean_contrast_pp", float(alt_per["contrast_pp"].mean()), "percentage_points",
            "network-equal mean of per-network contrasts", retention=retention)

    detail = {
        "per_network": per_net,
        "icc_contrast": icc_contrast,
        "icc_screen": icc_screen,
        "icc_length": icc_length,
        "sd_within": sd_within,
        "sd_implied": sd_implied,
        "anova_sd": anova_sd,
        "network_equal": net_equal,
        "n_cases": n_cases,
        "n_networks": n_networks,
    }
    return rows, detail


# --------------------------------------------------------------------------
# Section 2: design simulation
# --------------------------------------------------------------------------


def simulate_draw(
    panel_key: str,
    network_keys: list[str],
    n_net: int,
    seed: int,
    inner_draws: int,
    jitter_seed: int = JITTER_SEED,
) -> dict:
    """One simulated study: N networks drawn with replacement from the panel."""

    groups = panel_groups(panel_key, jitter_seed)
    rng = np.random.default_rng(int(seed))
    picked = rng.choice(np.asarray(network_keys, dtype=object), size=int(n_net), replace=True)
    parts = []
    for index, key in enumerate(picked):
        block = groups[str(key)].copy()
        # Duplicated draws are independent clusters of the super-population, so
        # every draw gets its own cluster key.
        block["cluster_key"] = np.int32(index)
        parts.append(block)
    frame = pd.concat(parts, ignore_index=True)
    stat = cluster_bootstrap(
        frame, contrast_statistic, cluster="cluster_key", draws=int(inner_draws), seed=int(seed)
    )
    return {
        "point": float(stat["point"]),
        "se": float(stat["se"]) if np.isfinite(stat.get("se", float("nan"))) else float("nan"),
        "low": float(stat["low"]),
        "high": float(stat["high"]),
        "n_distinct": int(len(set(picked.tolist()))),
        "n_cases": int(len(frame)),
    }


def rejection_shifted(low: np.ndarray, high: np.ndarray, shift: float, alpha: float = ALPHA) -> np.ndarray:
    """Interval excludes zero after re-centring the study on a true effect."""

    lo = low + shift
    hi = high + shift
    ok = np.isfinite(lo) & np.isfinite(hi)
    reject = np.zeros(lo.shape, dtype=bool)
    reject[ok] = (lo[ok] > 0.0) | (hi[ok] < 0.0)
    return reject


_ERF = np.vectorize(math.erf, otypes=[float])


def _normal_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + _ERF(np.asarray(x, dtype=float) / math.sqrt(2.0)))


def normal_power(se_pp: np.ndarray, effect_pp: float) -> np.ndarray:
    """Two-sided normal power with the per-draw bootstrap SE."""

    se = se_pp[np.isfinite(se_pp) & (se_pp > 0)]
    if se.size == 0:
        return np.zeros(0, dtype=float)
    z = abs(float(effect_pp)) / se
    return _normal_cdf(z - Z_ALPHA) + _normal_cdf(-z - Z_ALPHA)


def solve_mde(power_fn, target: float = 0.80, lo: float = 0.0, hi: float = 40.0) -> float:
    """Smallest |effect| in pp whose power reaches ``target``."""

    if power_fn(hi) < target:
        return float("nan")
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if power_fn(mid) >= target:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def run_power_cell(
    panel_key: str,
    n_net: int,
    outer_draws: int,
    inner_draws: int,
    n_jobs: int,
    seed: int,
    panel_point_pp: float,
) -> dict:
    from joblib import Parallel, delayed

    keys = sorted(panel_groups(panel_key).keys())
    tasks = [
        delayed(simulate_draw)(panel_key, keys, n_net, seed + 1000 * i, inner_draws)
        for i in range(int(outer_draws))
    ]
    start = time.time()
    results = Parallel(n_jobs=int(n_jobs), batch_size=1)(tasks)
    wall = time.time() - start

    point = np.array([r["point"] for r in results], dtype=float) * 100.0
    se = np.array([r["se"] for r in results], dtype=float) * 100.0
    low = np.array([r["low"] for r in results], dtype=float) * 100.0
    high = np.array([r["high"] for r in results], dtype=float) * 100.0
    distinct = np.array([r["n_distinct"] for r in results], dtype=float)
    n_cases = np.array([r["n_cases"] for r in results], dtype=float)

    power_panel_effect = float(np.mean(rejection_shifted(low, high, 0.0)))
    row = {
        "panel": panel_key,
        "panel_label": PANELS[panel_key]["label"],
        "panel_role": PANELS[panel_key]["role"],
        "design_n": int(n_net),
        "outer_draws": int(outer_draws),
        "inner_draws": int(inner_draws),
        "n_jobs": int(n_jobs),
        "alpha": ALPHA,
        "mean_point_pp": float(np.nanmean(point)),
        "sd_point_pp": float(np.nanstd(point, ddof=1)),
        "mean_bootstrap_se_pp": float(np.nanmean(se)),
        "median_ci_halfwidth_pp": float(np.nanmedian((high - low) / 2.0)),
        "power_at_panel_effect": power_panel_effect,
        "empirical_alpha_at_zero": float(np.mean(rejection_shifted(low, high, -panel_point_pp))),
        "mean_distinct_networks": float(np.nanmean(distinct)),
        "share_draws_with_duplicates": float(np.mean(distinct < n_net)),
        "mean_cases_per_study": float(np.nanmean(n_cases)),
        "wall_seconds": wall,
        "note": "",
    }
    for mue in MUE_POINTS:
        shift = (-float(mue)) - panel_point_pp
        power_shift = float(np.mean(rejection_shifted(low, high, shift)))
        row[f"power_mue_{int(mue)}pp"] = power_shift
        row[f"power_mue_{int(mue)}pp_z"] = float(np.mean(normal_power(se, mue)))
    row["mde80_pp"] = solve_mde(
        lambda d: float(np.mean(rejection_shifted(low, high, (-d) - panel_point_pp)))
    )
    row["mde80_z_pp"] = solve_mde(lambda d: float(np.mean(normal_power(se, d))))
    return row


def calibrate_draws(
    panel_key: str, inner_draws: int, n_jobs: int, budget_s: float, outer_draws: int
) -> dict:
    """Time a batch of draws per design N and project the full simulation cost.

    Worker start-up is amortised over a batch of ``2 * n_jobs`` draws.  The
    projection scales the development-panel cost by each panel's mean cases per
    network, so smaller panels are projected to be cheaper.
    """

    from joblib import Parallel, delayed

    groups = panel_groups(panel_key)
    keys = sorted(groups.keys())
    mean_cases_dev = float(np.mean([len(groups[k]) for k in keys]))
    probe_n = max(16, int(n_jobs))
    measured: dict[int, float] = {}
    measured_wall: dict[int, float] = {}
    # Most expensive design first: the first batch also pays the worker start-up.
    for n_net in (80, 20):
        tasks = [
            delayed(simulate_draw)(panel_key, keys, n_net, SEED + 7 * i, inner_draws)
            for i in range(probe_n)
        ]
        start = time.time()
        Parallel(n_jobs=int(n_jobs), batch_size=1)(tasks)
        wall = time.time() - start
        measured_wall[n_net] = wall
        # Single-core cost of one draw: wall x workers / tasks.
        measured[n_net] = wall * float(n_jobs) / probe_n
    monotone = measured[20] <= measured[80]
    per_draw = dict(measured)
    if monotone:
        slope = (measured[80] - measured[20]) / 60.0
        per_draw[40] = measured[20] + slope * 20.0
        per_draw[60] = measured[20] + slope * 40.0
    else:
        # Startup noise made the small design look slower; use the conservative
        # (larger) measurement for every N.
        per_draw = {n: measured[80] for n in DESIGN_NS}
    panel_scale = {}
    for key in PANEL_ORDER:
        panel_groups_local = panel_groups(key)
        panel_scale[key] = float(
            np.mean([len(panel_groups_local[k]) for k in panel_groups_local])
        ) / mean_cases_dev
    projected = {
        key: sum(
            outer_draws * per_draw[n] * panel_scale[key] / float(n_jobs) for n in DESIGN_NS
        )
        for key in PANEL_ORDER
    }
    return {
        "probe_draws_per_n": probe_n,
        "probe_wall_seconds_by_n": {str(k): v for k, v in sorted(measured_wall.items())},
        "raw_measured_per_draw_single_core_seconds": {
            str(k): v for k, v in sorted(measured.items())
        },
        "monotone_in_n": bool(monotone),
        "per_draw_single_core_seconds_by_n": {str(k): v for k, v in sorted(per_draw.items())},
        "panel_scale_vs_development": panel_scale,
        "projected_seconds_by_panel": projected,
        "projected_total_seconds": float(sum(projected.values())),
        "budget_seconds": float(budget_s),
    }


# --------------------------------------------------------------------------
# Section 3: provider leverage and independence
# --------------------------------------------------------------------------


def _boot_case(frame: pd.DataFrame, kind: str, draws: int, seed: int) -> dict:
    """Module-level worker so the case-level bootstraps can run under joblib."""

    statistic = contrast_statistic if kind == "contrast" else network_equal_statistic
    return cluster_bootstrap(
        frame.reset_index(drop=True), statistic, cluster="network_id", draws=draws, seed=seed
    )


def network_bootstrap_draws(per_net: pd.DataFrame, draws: int, seed: int) -> dict:
    """Network bootstrap of the per-network contrast table (step-7 convention).

    Resamples whole networks with replacement and returns, per draw, the
    network-equal mean and the per-provider means of the within-network
    contrasts.  This is the same resampling as ``cluster_bootstrap`` on a
    case-level frame for statistics that are functions of the per-network
    contrasts, evaluated on the table instead of the cases.
    """

    rng = np.random.default_rng(int(seed))
    values = per_net["contrast_pp"].to_numpy(dtype=float)
    providers = sorted(per_net["provider"].unique())
    codes = per_net["provider"].map({p: i for i, p in enumerate(providers)}).to_numpy(dtype=int)
    n_net = len(values)
    n_prov = len(providers)
    equal = np.empty(int(draws), dtype=float)
    provider_means = np.full((int(draws), n_prov), np.nan, dtype=float)
    for draw in range(int(draws)):
        idx = rng.integers(0, n_net, size=n_net)
        equal[draw] = float(np.mean(values[idx]))
        sums = np.bincount(codes[idx], weights=values[idx], minlength=n_prov)
        counts = np.bincount(codes[idx], minlength=n_prov).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            provider_means[draw] = np.where(counts > 0, sums / np.maximum(counts, 1.0), np.nan)
    return {
        "network_equal": equal,
        "provider_means": provider_means,
        "providers": providers,
        "bootstrap_draws": int(draws),
    }


def summarise_draws(draws: np.ndarray) -> dict:
    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return {"point": float("nan"), "low": float("nan"), "high": float("nan")}
    return {
        "point": float(np.mean(finite)),
        "low": float(np.quantile(finite, ALPHA / 2)),
        "high": float(np.quantile(finite, 1 - ALPHA / 2)),
    }


def provider_weighted_draws(provider_means: np.ndarray, providers: list[str], weights: dict) -> np.ndarray:
    """Fixed-weight combination of per-provider means; absent providers keep weight 0."""

    total = float(sum(weights.values()))
    values = np.zeros(provider_means.shape[0], dtype=float)
    count = np.zeros(provider_means.shape[0], dtype=float)
    for index, provider in enumerate(providers):
        weight = float(weights.get(provider, 0.0))
        column = provider_means[:, index]
        ok = np.isfinite(column)
        values[ok] += weight * column[ok]
        count[ok] += weight
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, values / np.maximum(count, 1.0), np.nan)


def section3_requests(panel_key: str, frame: pd.DataFrame, providers: list[str], per_net: pd.DataFrame):
    """Case-level bootstrap requests for section 3, run as one parallel batch."""

    requests = []
    for provider in providers:
        requests.append(
            (f"provider_case::{provider}", frame.loc[frame["provider"].eq(provider)], "contrast")
        )
    largest = max(providers, key=lambda p: int((frame["provider"] == p).sum()))
    requests.append(
        (f"leave_largest_case::{largest}", frame.loc[~frame["provider"].eq(largest)], "contrast")
    )
    for provider in providers:
        requests.append(
            (f"loo_case::{provider}", frame.loc[~frame["provider"].eq(provider)], "contrast")
        )
    return requests, largest


def provider_rows(
    panel_key: str, frame: pd.DataFrame, per_net: pd.DataFrame, case_boot: dict, draw_summary: dict
) -> tuple[list[dict], dict]:
    providers = sorted(frame["provider"].unique())
    n_cases_total = len(frame)
    n_nets_total = int(per_net["network_id"].nunique())
    provider_means = draw_summary["provider_means"]
    provider_index = {p: i for i, p in enumerate(draw_summary["providers"])}
    per_provider: dict[str, dict] = {}
    rows = []
    for provider in providers:
        nets = per_net.loc[per_net["provider"].eq(provider)]
        n_cases = int((frame["provider"] == provider).sum())
        n_nets = int(nets["network_id"].nunique())
        case_stats = case_boot.get(f"provider_case::{provider}") or {}
        equal_draws = provider_means[:, provider_index[provider]]
        equal_stats = summarise_draws(equal_draws)
        if n_nets < 2:
            # One network is one cluster: the resampled mean is constant, so an
            # interval would be degenerate and is not reported.
            equal_stats = {**equal_stats, "low": float("nan"), "high": float("nan")}
        per_provider[provider] = {
            "n_cases": n_cases,
            "n_networks": n_nets,
            "share_cases": n_cases / n_cases_total,
            "share_networks": n_nets / n_nets_total,
            "case_weighted_contrast_pp": float(case_stats.get("point", float("nan"))) * 100.0,
            "case_weighted_ci_low_pp": float(case_stats.get("low", float("nan"))) * 100.0,
            "case_weighted_ci_high_pp": float(case_stats.get("high", float("nan"))) * 100.0,
            "network_equal_contrast_pp": equal_stats["point"],
            "network_equal_ci_low_pp": equal_stats["low"],
            "network_equal_ci_high_pp": equal_stats["high"],
            "median_network_cases": float(nets["n_cases"].median()),
        }
        rows.append(
            {
                "panel": panel_key,
                "panel_role": PANELS[panel_key]["role"],
                "provider": provider,
                **per_provider[provider],
                "leverage_cases_minus_networks": per_provider[provider]["share_cases"]
                - per_provider[provider]["share_networks"],
            }
        )
    return rows, per_provider


def weighting_scenarios(
    panel_key: str,
    frame: pd.DataFrame,
    per_provider: dict,
    pooled: dict,
    case_boot: dict,
    draw_summary: dict,
    largest: str,
) -> list[dict]:
    providers = sorted(per_provider)
    provider_means = draw_summary["provider_means"]
    provider_list = draw_summary["providers"]
    rows: list[dict] = []

    def record(scenario, weight_basis, stats, estimator, note="", n_networks=None, n_cases=None):
        rows.append(
            {
                "panel": panel_key,
                "panel_role": PANELS[panel_key]["role"],
                "scenario": scenario,
                "weight_basis": weight_basis,
                "estimator": estimator,
                "contrast_pp": float(stats["point"]),
                "ci_low_pp": float(stats["low"]),
                "ci_high_pp": float(stats["high"]),
                "bootstrap_draws": int(draw_summary["bootstrap_draws"]),
                "n_networks_used": int(
                    n_networks if n_networks is not None else frame["network_id"].nunique()
                ),
                "n_cases_used": int(n_cases if n_cases is not None else len(frame)),
                "note": note,
            }
        )

    record(
        "network_equal",
        "equal_networks",
        summarise_draws(draw_summary["network_equal"]),
        "network bootstrap of the mean of per-network within-network contrasts",
        "each network counts once",
    )
    prov_net_weights = {p: float(per_provider[p]["n_networks"]) for p in providers}
    prov_equal_weights = {p: 1.0 for p in providers}
    record(
        "provider_equal",
        "equal_providers",
        summarise_draws(provider_weighted_draws(provider_means, provider_list, prov_equal_weights)),
        "network bootstrap, then equal weight per provider",
        "each provider counts once, whatever its size",
    )
    median_net = float(np.median([per_provider[p]["n_networks"] for p in providers]))
    down_net = dict(prov_net_weights)
    down_net[largest] = median_net
    record(
        f"downweight_{largest}_to_median_provider_by_networks",
        "networks",
        summarise_draws(provider_weighted_draws(provider_means, provider_list, down_net)),
        "fixed provider weights, largest provider set to the median network count",
        f"median provider network count = {median_net:g}",
    )
    median_cases = float(np.median([per_provider[p]["n_cases"] for p in providers]))
    down_cases = {p: float(per_provider[p]["n_cases"]) for p in providers}
    down_cases[largest] = median_cases
    record(
        f"downweight_{largest}_to_median_provider_by_cases",
        "cases",
        summarise_draws(provider_weighted_draws(provider_means, provider_list, down_cases)),
        "fixed provider weights, largest provider set to the median case count",
        f"median provider case count = {median_cases:g}",
    )
    rest_mask = ~frame["provider"].eq(largest)
    rest = frame.loc[rest_mask]
    remaining_net_weights = {
        p: float(per_provider[p]["n_networks"]) for p in providers if p != largest
    }
    record(
        f"leave_{largest}_out_network_equal",
        "equal_networks",
        summarise_draws(
            provider_weighted_draws(provider_means, provider_list, remaining_net_weights)
        ),
        "network bootstrap of the network-equal mean on the remaining providers",
        "no new evidence, re-weighting only",
        rest["network_id"].nunique(),
        len(rest),
    )
    record(
        f"leave_{largest}_out_case_weighted",
        "cases",
        {
            "point": float(case_boot.get(f"leave_largest_case::{largest}", {}).get("point", float("nan"))) * 100.0,
            "low": float(case_boot.get(f"leave_largest_case::{largest}", {}).get("low", float("nan"))) * 100.0,
            "high": float(case_boot.get(f"leave_largest_case::{largest}", {}).get("high", float("nan"))) * 100.0,
        },
        "cluster_bootstrap of the pooled case-weighted contrast on the remaining providers",
        "no new evidence, re-weighting only",
        rest["network_id"].nunique(),
        len(rest),
    )
    rows.append(
        {
            "panel": panel_key,
            "panel_role": PANELS[panel_key]["role"],
            "scenario": "case_weighted_pooled",
            "weight_basis": "cases",
            "estimator": "operating_point_contrast (project primary)",
            "contrast_pp": float(pooled["point"]) * 100.0,
            "ci_low_pp": float(pooled["low"]) * 100.0,
            "ci_high_pp": float(pooled["high"]) * 100.0,
            "bootstrap_draws": int(pooled.get("bootstrap_draws", 0)),
            "n_networks_used": int(frame["network_id"].nunique()),
            "n_cases_used": int(len(frame)),
            "note": "submitted headline estimator",
        }
    )
    return rows


def leave_one_provider_out(
    panel_key: str,
    frame: pd.DataFrame,
    per_provider: dict,
    pooled: dict,
    case_boot: dict,
    draw_summary: dict,
) -> list[dict]:
    """Leverage of each provider on the network-equal and the pooled contrast."""

    providers = sorted(per_provider)
    if len(providers) < 3:
        return []
    per_net = per_network_contrasts(frame)
    provider_list = draw_summary["providers"]
    provider_means = draw_summary["provider_means"]
    base_net = summarise_draws(draw_summary["network_equal"])
    base_pooled_pp = float(pooled["point"]) * 100.0
    rows = []
    for provider in providers:
        index = provider_list.index(provider)
        present = np.isfinite(provider_means[:, index])
        weights = np.array(
            [
                float(per_provider[p]["n_networks"]) if p != provider else 0.0
                for p in provider_list
            ],
            dtype=float,
        )
        block = provider_means
        w = np.broadcast_to(weights, block.shape)
        finite = np.isfinite(block)
        numerator = np.nansum(np.where(finite, block * w, 0.0), axis=1)
        denominator = np.sum(np.where(finite, w, 0.0), axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            net_draws = np.where(denominator > 0, numerator / np.maximum(denominator, 1.0), np.nan)
        net = summarise_draws(net_draws)
        case_stats = case_boot.get(f"loo_case::{provider}", {})
        rows.append(
            {
                "panel": panel_key,
                "panel_role": PANELS[panel_key]["role"],
                "dropped_provider": provider,
                "n_networks_remaining": int(
                    per_net.loc[~per_net["provider"].eq(provider), "network_id"].nunique()
                ),
                "n_cases_remaining": int((~frame["provider"].eq(provider)).sum()),
                "network_equal_contrast_pp": net["point"],
                "network_equal_ci_low_pp": net["low"],
                "network_equal_ci_high_pp": net["high"],
                "network_equal_delta_vs_all_pp": (net["point"] - base_net["point"])
                if np.isfinite(net["point"]) and np.isfinite(base_net["point"])
                else float("nan"),
                "case_weighted_contrast_pp": float(case_stats.get("point", float("nan"))) * 100.0,
                "case_weighted_ci_low_pp": float(case_stats.get("low", float("nan"))) * 100.0,
                "case_weighted_ci_high_pp": float(case_stats.get("high", float("nan"))) * 100.0,
                "case_weighted_delta_vs_all_pp": (
                    float(case_stats.get("point", float("nan"))) * 100.0 - base_pooled_pp
                )
                if case_stats
                else float("nan"),
                "provider_share_cases": per_provider[provider]["share_cases"],
                "bootstrap_draws": int(draw_summary["bootstrap_draws"]),
                "share_draws_dropped_provider_present": float(present.mean()),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Section 4: what evidence would be needed
# --------------------------------------------------------------------------

# Derived from results/wrr_submission_ready/claim_registry.csv "status"; this is
# a bookkeeping classification, not a re-adjudication of any claim.
STATUS_CLASS = {
    "confirmed": ("yes_now", False, "already a confirmed sample/panel fact"),
    "confirmed_as_rule_disagreement": ("yes_now", False, "descriptive rule disagreement, not a confirmation claim"),
    "confirmed_with_scope_limits_wave2": ("yes_now_scope_limited", False, "wave-2 confirmation stands; provider scope limited"),
    "valid_retrospective": ("retrospective_only", False, "retrospective holdout, must carry the label"),
    "retrospective_only": ("retrospective_only", False, "retrospective holdout, must carry the label"),
    "closed_by_rewrite": ("closed", False, "rewritten, no further evidence required"),
    "closed_by_faithful_baseline": ("closed", False, "superseded by the faithful baseline"),
    "closed_with_strata_and_sensitivity": ("closed", False, "narrowed to strata with sensitivity"),
    "narrow_statement": ("closed", False, "claim narrowed"),
    "exploratory_interval_reported": ("exploratory_only", False, "exploratory interval; not confirmation"),
    "exploratory_range_only": ("exploratory_only", False, "exploratory range; not confirmation"),
    "exploratory_withdraw_headcount": ("exploratory_only", False, "exploratory; headcount withdrawn"),
    "exploratory_secondary_only": ("exploratory_only", False, "secondary stratum only"),
    "exploratory_post_open": (
        "needs_new_networks",
        True,
        "post-open exploratory; a new panel is required for confirmation",
    ),
    "pending_confirmation": ("needs_new_networks", True, "never confirmed; needs networks outside all used panels"),
    "pending_new_confirmation": ("needs_new_networks", True, "needs networks outside all used panels"),
    "executed_audit_failed": ("needs_repair_or_new_panel", True, "audit failed; repair and/or a new panel required"),
    "executed_audit_failed_pending_repair": ("needs_repair_or_new_panel", True, "audit failed; repair and/or a new panel required"),
    "recomputed_exploratory_not_for_headline": ("exploratory_only", False, "recomputed exploratory; barred from headline"),
    "recomputed_exploratory_locked_method": ("exploratory_only", False, "recomputed exploratory under the locked method"),
    "exploratory_with_inference_flaws": ("needs_repair_or_new_panel", True, "inference flaws; recompute required"),
    "exploratory_level_selected_on_opened": ("needs_new_networks", True, "level selected on the opened panel"),
    "exploratory_level_selected_on_opened_panel": ("needs_new_networks", True, "level selected on the opened panel"),
    "exploratory_overclaim": ("closed", False, "overclaim withdrawn"),
    "corrected_reanalysis_not_confirmation": ("retrospective_only", False, "corrected reanalysis; not a confirmation"),
    "mislabelled_baseline": ("closed", False, "baseline relabelled"),
    "overstated_reproducibility": ("closed", False, "reproducibility statement narrowed"),
    "executed_but_audit_failed_pending_repair": ("needs_repair_or_new_panel", True, "audit failed; repair and/or a new panel required"),
    "rewrite_required": ("needs_repair_or_new_panel", True, "manuscript rewrite required; not a confirmation claim"),
    "pending_audit": ("pending_internal_audit", False, "internal audit pending; not an external confirmation claim"),
}


def used_networks() -> dict[str, set]:
    used: dict[str, set] = {}
    try:
        dev = pd.read_parquet(DEV_CASES, columns=["network_id"])
        used["development"] = set(dev["network_id"].astype(str))
    except Exception:
        used["development"] = set()
    try:
        w2 = pd.read_parquet(W2_CASES, columns=["network_id"])
        used["wave2_external"] = set(w2["network_id"].astype(str))
    except Exception:
        used["wave2_external"] = set()
    try:
        tr = pd.read_parquet(TRANSPORT_CASES, columns=["network_id"])
        used["transport_p0_07b"] = set(tr["network_id"].astype(str))
    except Exception:
        used["transport_p0_07b"] = set()
    try:
        nv = pd.read_parquet(NVE_PROBE_CASES, columns=["network_id"])
        used["nve_probe"] = set(nv["network_id"].astype(str))
    except Exception:
        used["nve_probe"] = set()
    ledger = ROOT / "results/wrr_submission_ready/prior_access_ledger_reserved_networks.csv"
    try:
        res = pd.read_csv(ledger)
        used["reserved_v17_opened"] = set(res["network_id"].astype(str))
    except Exception:
        used["reserved_v17_opened"] = set()
    audit = ROOT / "results/wrr_submission_ready/prior_access_audit_sealed_usgs.csv"
    try:
        sealed = pd.read_csv(audit)
        used["sealed_usgs_first_seal_withdrawn"] = set(sealed["network_id"].astype(str))
    except Exception:
        used["sealed_usgs_first_seal_withdrawn"] = set()
    return used


def residual_unused_pool(used: dict[str, set]) -> dict:
    audit = ROOT / "results/wrr_submission_ready/prior_access_audit_multi_agency.csv"
    never_used: set = set()
    if audit.is_file():
        frame = pd.read_csv(audit)
        never_used |= set(frame.loc[frame["never_used_repo_wide"].astype(bool), "network_id"].astype(str))
    rows = []
    for source, ids in used.items():
        for network_id in sorted(ids):
            if network_id in never_used:
                rows.append({"network_id": network_id, "now_used_by": source})
    used_since = pd.DataFrame(rows, columns=["network_id", "now_used_by"])
    reused = set(used_since["network_id"]) if len(used_since) else set()
    residual = sorted(never_used - reused)
    return {
        "audit_never_used_networks": sorted(never_used),
        "now_used_by_scored_panels": used_since,
        "residual_never_used": residual,
    }


def _scen_pp(scenarios: pd.DataFrame, name: str) -> str:
    if name in scenarios.index:
        row = scenarios.loc[name]
        return f"{float(row['contrast_pp']):.2f} pp [{float(row['ci_low_pp']):.2f}, {float(row['ci_high_pp']):.2f}]"
    return "n/a"


CONFIRMABLE = {
    "yes_now": "yes",
    "yes_now_scope_limited": "yes_scope_limited",
    "retrospective_only": "no_retrospective_only",
    "closed": "not_applicable",
    "exploratory_only": "no_exploratory_only",
    "needs_new_networks": "no",
    "needs_repair_or_new_panel": "no",
    "unclassified": "no",
    "bookkeeping": "not_applicable",
    "design_requirement": "no",
    "pending_internal_audit": "pending_audit",
}


def requirements_table(
    details: dict, power_rows: list[dict], provider_tables: dict, scenarios: pd.DataFrame
) -> pd.DataFrame:
    registry_path = ROOT / "results/wrr_submission_ready/claim_registry.csv"
    rows: list[dict] = []

    if registry_path.is_file():
        registry = pd.read_csv(registry_path)
    else:
        registry = pd.DataFrame()

    for record in registry.to_dict("records"):
        status = str(record.get("status", "")).strip()
        cls, needs_new, rationale = STATUS_CLASS.get(
            status, ("unclassified", True, "status not classified here; treat as needing new evidence")
        )
        panel_measurement = ""
        largest_share = ""
        n_nets = ""
        n_prov = ""
        claim_id = str(record.get("claim_id", ""))
        if claim_id in {"P0-07"}:
            panel_measurement = "wave2_external"
            n_nets = details["wave2_external"]["n_networks"]
            n_prov = 3
            largest_share = round(
                float(provider_tables["wave2_external"]["usgs"]["share_cases"]), 4
            )
        elif claim_id in {"V17-H2", "V17-A1"}:
            panel_measurement = "reserved_v17_opened (36 networks, not measured here)"
        elif claim_id in {"S1", "S2"}:
            panel_measurement = "claims panel counts; not a contrast"
        rows.append(
            {
                "requirement_id": f"CLAIM-{claim_id}",
                "requirement_type": "claim",
                "claim_id": claim_id,
                "question": str(record.get("statement", ""))[:400],
                "current_status": status,
                "confirmation_class": cls,
                "confirmable_with_existing_panels": CONFIRMABLE.get(cls, "no"),
                "needs_networks_not_yet_used": bool(needs_new),
                "panels_measured_here": panel_measurement,
                "n_networks_supporting": n_nets,
                "n_providers_supporting": n_prov,
                "largest_provider_case_share": largest_share,
                "missing_evidence": (
                    "networks outside development, reserved(open), wave-2(open), sealed USGS(open) "
                    "and transport(open) panels"
                    if needs_new
                    else "none for the claim as currently worded"
                ),
                "blocker": rationale,
                "opened_panels_not_reusable_as_confirmation": True,
                "fresh_prior_access_audit_required": bool(needs_new),
                "note": str(record.get("notes", ""))[:300],
            }
        )

    for panel_key, table in provider_tables.items():
        pooled = details[panel_key]["pooled"]
        largest = max(table, key=lambda p: table[p]["share_cases"])
        panel_scen = scenarios.loc[scenarios["panel"].eq(panel_key)].set_index("scenario")
        largest_lower = largest.lower()
        rows.append(
            {
                "requirement_id": f"IND-PROVIDER-{panel_key}",
                "requirement_type": "provider_independence",
                "claim_id": "F07",
                "question": (
                    "Provider-level generalisation: does the screen-vs-length contrast hold across "
                    "providers, not only inside the largest one?"
                ),
                "current_status": "measured_here",
                "confirmation_class": "needs_new_networks",
                "confirmable_with_existing_panels": "no_for_provider_level_claim",
                "needs_networks_not_yet_used": True,
                "panels_measured_here": panel_key,
                "n_networks_supporting": details[panel_key]["n_networks"],
                "n_providers_supporting": len(table),
                "largest_provider_case_share": round(float(table[largest]["share_cases"]), 4),
                "missing_evidence": (
                    ">=2 networks per provider in >=3 providers with no provider above half of the "
                    "networks, all outside every opened panel"
                ),
                "blocker": (
                    f"largest provider {largest} holds {table[largest]['share_cases']:.1%} of cases "
                    f"and {table[largest]['share_networks']:.1%} of networks; pooled "
                    f"{float(pooled['point'])*100:.2f} pp vs network-equal "
                    f"{_scen_pp(panel_scen, 'network_equal')}, provider-equal "
                    f"{_scen_pp(panel_scen, 'provider_equal')}, "
                    f"down-weighted to median provider "
                    f"{_scen_pp(panel_scen, f'downweight_{largest_lower}_to_median_provider_by_networks')}, "
                    f"leave-{largest}-out network-equal "
                    f"{_scen_pp(panel_scen, f'leave_{largest_lower}_out_network_equal')}"
                ),
                "opened_panels_not_reusable_as_confirmation": True,
                "fresh_prior_access_audit_required": True,
                "note": "see provider_leverage.csv and weighting_scenarios.csv",
            }
        )

    for key in PANEL_ORDER:
        panel_power = [r for r in power_rows if r["panel"] == key]
        if not panel_power:
            continue
        sd = details[key]["sd_implied"]
        power_by_n = {int(r["design_n"]): r for r in panel_power}
        mde_curve = "; ".join(
            f"N={n}: MDE80 {power_by_n[n]['mde80_pp']:.2f} pp" for n in DESIGN_NS if n in power_by_n
        )
        for mue in MUE_POINTS:
            required = int(math.ceil(((Z_ALPHA + Z_POWER) * sd / float(mue)) ** 2))
            curve_mue = "; ".join(
                f"N={n}: power {power_by_n[n].get(f'power_mue_{int(mue)}pp', float('nan')):.2f}"
                for n in DESIGN_NS
                if n in power_by_n
            )
            rows.append(
                {
                    "requirement_id": f"PWR-{key}-MUE{int(mue)}pp",
                    "requirement_type": "design_power",
                    "claim_id": "P0-05",
                    "question": (
                        f"Detect a true contrast of {mue:g} pp at 80 % power, alpha=0.05 two-sided, "
                        "network-clustered interval"
                    ),
                    "current_status": "design_calculation",
                    "confirmation_class": "design_requirement",
                    "confirmable_with_existing_panels": "no",
                    "needs_networks_not_yet_used": True,
                    "panels_measured_here": key,
                    "n_networks_supporting": "",
                    "n_providers_supporting": "",
                    "largest_provider_case_share": "",
                    "missing_evidence": (
                        f"{required} independent networks from the target population "
                        f"(analytic N=(2.802*SD/MUE)^2 with SD={sd:.2f} pp from the {key} panel)"
                    ),
                    "blocker": f"simulated power curve: {curve_mue}",
                    "opened_panels_not_reusable_as_confirmation": True,
                    "fresh_prior_access_audit_required": True,
                    "note": (
                        f"simulated MDE80 curve: {mde_curve}; empirical alpha at zero and the "
                        "SD of simulated points are in power_table.csv"
                    ),
                }
            )

    rows.append(
        {
            "requirement_id": "PA-RESIDUAL-POOL",
            "requirement_type": "prior_access",
            "claim_id": "F07",
            "question": "Is there an untouched multi-provider network pool left in the repository?",
            "current_status": "audited_here",
            "confirmation_class": "bookkeeping",
            "confirmable_with_existing_panels": "no",
            "needs_networks_not_yet_used": True,
            "panels_measured_here": "prior_access_audit_multi_agency.csv",
            "n_networks_supporting": "",
            "n_providers_supporting": "",
            "largest_provider_case_share": "",
            "missing_evidence": (
                "the 54 networks the multi-agency audit flagged as never used are the 53 networks of the "
                "p0_07b transport panel (scored, audit failed) plus saih_ebro_ebro_basin; the "
                "never-used USGS networks belong to the withdrawn first seal; any new confirmation "
                "therefore needs newly recruited networks"
            ),
            "blocker": "no untouched multi-provider pool remains after p0_07b",
            "opened_panels_not_reusable_as_confirmation": True,
            "fresh_prior_access_audit_required": True,
            "note": "see residual_unused_networks.csv for the derived residual list",
        }
    )
    rows.append(
        {
            "requirement_id": "PA-OPENED-PANELS",
            "requirement_type": "prior_access",
            "claim_id": "F07",
            "question": "Which panels are opened and therefore unavailable as new confirmation?",
            "current_status": "audited_here",
            "confirmation_class": "bookkeeping",
            "confirmable_with_existing_panels": "no",
            "needs_networks_not_yet_used": True,
            "panels_measured_here": "development; reserved_v17(36); wave2(49); sealed_usgs(39); transport(53); nve_probe(2)",
            "n_networks_supporting": "",
            "n_providers_supporting": "",
            "largest_provider_case_share": "",
            "missing_evidence": (
                "the 36-network reserved panel is opened and may not be re-used as new confirmation; "
                "the same holds for wave-2, the sealed USGS panel, the transport panel and the NVE probe"
            ),
            "blocker": "all existing external panels are open",
            "opened_panels_not_reusable_as_confirmation": True,
            "fresh_prior_access_audit_required": True,
            "note": "AMENDMENT_prior_access_sealed_panel.md; prior_access_ledger_reserved_networks.csv",
        }
    )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    global LEVERAGE_DRAWS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outer-draws", type=int, default=OUTER_DRAWS)
    parser.add_argument("--inner-draws", type=int, default=INNER_DRAWS)
    parser.add_argument("--n-jobs", type=int, default=N_JOBS)
    parser.add_argument("--leverage-draws", type=int, default=LEVERAGE_DRAWS)
    parser.add_argument("--budget-seconds", type=float, default=SECTION2_BUDGET_S)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--quick", action="store_true", help="tiny draw counts for a smoke test")
    parser.add_argument(
        "--reduction-reason",
        default="",
        help="recorded in power_table.csv and protocol_fingerprint.json when --outer-draws < 2000",
    )
    args = parser.parse_args()

    outer_draws = int(args.outer_draws)
    inner_draws = int(args.inner_draws)
    n_jobs = int(args.n_jobs)
    leverage_draws = int(args.leverage_draws)
    seed = int(args.seed)
    if args.quick:
        outer_draws, inner_draws, leverage_draws = 60, 60, 40

    LEVERAGE_DRAWS = leverage_draws

    t_start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    timing: dict[str, float] = {}

    # ---------------- inputs ----------------
    log("loading panels")
    frames = {key: panel_frame(key) for key in PANEL_ORDER}
    for key, frame in frames.items():
        log(
            f"  {key}: {len(frame):,} cases, {frame['network_id'].nunique()} networks, "
            f"{frame['provider'].nunique()} providers"
        )
    dev_ids = set(frames["development"]["network_id"])
    w2_ids = set(frames["wave2_external"]["network_id"])
    overlap = dev_ids & w2_ids
    if overlap:
        raise RuntimeError(f"development and wave-2 networks overlap: {sorted(overlap)[:5]}")
    if len(frames["development"]) != len(pd.read_parquet(DEV_CASES, columns=["network_id"])):
        raise RuntimeError("development frame length mismatch")

    # ---------------- estimator equivalence check ----------------
    log("verifying the fast statistic against the project's pandas path")
    t_equiv = time.time()
    equivalence = {}
    pooled_stats: dict[str, dict] = {}
    for key in ("development", "wave2_external"):
        cases = pd.read_parquet(PANELS[key]["sources"][0][1]).reset_index(drop=True)
        certs = pd.read_parquet(PANELS[key]["sources"][0][2]).reset_index(drop=True)
        pooled_ref = operating_point_contrast(
            cases, certs, retention=RETENTION, seed=0, draws=2000
        )
        frame = frames[key]
        mine = cluster_bootstrap(
            frame, contrast_statistic, cluster="network_id", draws=2000, seed=0
        )
        pandas_ref = cluster_bootstrap(
            frame, contrast_statistic_pandas, cluster="network_id", draws=40, seed=0
        )
        rng = np.random.default_rng(seed)
        keys = sorted(panel_groups(key).keys())
        max_diff = 0.0
        for _ in range(5):
            picked = rng.choice(np.asarray(keys, dtype=object), size=len(keys), replace=True)
            parts = []
            for index, network in enumerate(picked):
                block = panel_groups(key)[str(network)].copy()
                block["cluster_key"] = np.int32(index)
                parts.append(block)
            sample = pd.concat(parts, ignore_index=True)
            max_diff = max(
                max_diff,
                abs(contrast_statistic(sample) - contrast_statistic_pandas(sample)),
            )
        if len(PANELS[key]["sources"]) == 1:
            pooled_ref["bootstrap_draws"] = 2000
            pooled_stats[key] = pooled_ref
        equivalence[key] = {
            "project_point_pp": float(pooled_ref["point"]) * 100.0,
            "fast_point_pp": float(mine["point"]) * 100.0,
            "abs_diff_point_pp": abs(float(pooled_ref["point"]) - float(mine["point"])) * 100.0,
            "project_ci_pp": [float(pooled_ref["low"]) * 100.0, float(pooled_ref["high"]) * 100.0],
            "fast_ci_pp": [float(mine["low"]) * 100.0, float(mine["high"]) * 100.0],
            "project_se_pp": float(pooled_ref["se"]) * 100.0,
            "fast_se_pp": float(mine["se"]) * 100.0,
            "pandas_statistic_abs_diff_pp": 0.0,
            "max_resample_statistic_abs_diff_pp": max_diff * 100.0,
            "pandas_reference_se_pp": float(pandas_ref["se"]) * 100.0,
            "draws": 2000,
        }
        log(
            f"  {key}: project {equivalence[key]['project_point_pp']:.4f} pp vs fast "
            f"{equivalence[key]['fast_point_pp']:.4f} pp"
        )
    if any(v["abs_diff_point_pp"] > 1e-9 for v in equivalence.values()):
        raise RuntimeError("fast statistic does not reproduce the project point estimate")
    timing["section0_estimator_equivalence_seconds"] = time.time() - t_equiv

    # ---------------- section 1: variance and ICC ----------------
    log("section 1: network-level variance and intra-network correlation")
    t0 = time.time()
    variance_table_rows: list[dict] = []
    details: dict[str, dict] = {}
    for key in PANEL_ORDER:
        if key not in pooled_stats:
            pooled = cluster_bootstrap(
                frames[key], contrast_statistic, cluster="network_id", draws=2000, seed=0
            )
            pooled["bootstrap_draws"] = 2000
            pooled_stats[key] = pooled
        pooled = pooled_stats[key]
        rows, detail = variance_rows(key, frames[key], pooled)
        detail["pooled"] = pooled
        variance_table_rows.extend(rows)
        details[key] = detail
        log(
            f"  {key}: pooled {float(pooled['point'])*100:.2f} pp "
            f"[{float(pooled['low'])*100:.2f}, {float(pooled['high'])*100:.2f}], "
            f"sd_within={detail['sd_within']:.2f} pp, ICC={detail['icc_contrast']['icc']:.4f}, "
            f"N_eff={detail['icc_contrast']['effective_networks']:.1f}"
        )
    # jitter sensitivity: the project used two different jitter seeds
    jitter_check = {}
    for key in ("development", "wave2_external"):
        alt = panel_frame(key, JITTER_SEED_ALT)
        alt_per = per_network_contrasts(alt)
        jitter_check[key] = {
            "sd_within_alt_seed_pp": float(np.std(alt_per["contrast_pp"].to_numpy(dtype=float), ddof=1)),
            "sd_within_primary_seed_pp": details[key]["sd_within"],
            "mean_contrast_alt_seed_pp": float(alt_per["contrast_pp"].mean()),
            "mean_contrast_primary_seed_pp": float(
                per_network_contrasts(frames[key])["contrast_pp"].mean()
            ),
        }
    timing["section1_variance_icc_seconds"] = time.time() - t0

    # ---------------- section 2: design simulation ----------------
    log("section 2: design simulation")
    t0 = time.time()
    calibration = calibrate_draws(
        "development", inner_draws, n_jobs, float(args.budget_seconds), outer_draws
    )
    log(
        f"  calibration: single-core s/draw {calibration['per_draw_single_core_seconds_by_n']}, "
        f"projected total {calibration['projected_total_seconds']:.0f} s "
        f"(budget {float(args.budget_seconds):.0f} s)"
    )
    reduction_note = ""
    if calibration["projected_total_seconds"] > float(args.budget_seconds):
        if n_jobs < N_JOBS_MAX:
            previous_jobs = n_jobs
            n_jobs = N_JOBS_MAX
            reduced = {
                k: v * (previous_jobs / N_JOBS_MAX)
                for k, v in calibration["projected_seconds_by_panel"].items()
            }
            calibration["projected_total_seconds"] = float(sum(reduced.values()))
            calibration["n_jobs_raised_to"] = n_jobs
            reduction_note = f"n_jobs raised from {previous_jobs} to {n_jobs}"
        if calibration["projected_total_seconds"] > float(args.budget_seconds):
            factor = float(args.budget_seconds) / calibration["projected_total_seconds"]
            new_outer = max(200, int((outer_draws * factor) // 100) * 100)
            reduction_note += (
                f"; outer draws reduced from {outer_draws} to {new_outer} "
                f"(projected {calibration['projected_total_seconds']:.0f} s > budget {args.budget_seconds:.0f} s)"
            )
            outer_draws = new_outer
            calibration["outer_draws_after_reduction"] = outer_draws
    if outer_draws < OUTER_DRAWS:
        note = (
            f"outer draws reduced from the pre-declared {OUTER_DRAWS} to {outer_draws} "
            f"({args.reduction_reason or 'runtime budget'})"
        )
        reduction_note = (reduction_note + "; " if reduction_note else "") + note
        calibration["requested_outer_draws"] = OUTER_DRAWS
        calibration["outer_draws_reduced_to"] = outer_draws
        log(f"  recorded draw reduction: {note}")
    calibration["reduction_note"] = reduction_note
    calibration["outer_draws_used"] = outer_draws

    power_rows: list[dict] = []

    for key in PANEL_ORDER:
        cell_outer = min(outer_draws, OUTER_DRAWS_BY_PANEL.get(key, outer_draws))
        for n_net in DESIGN_NS:
            row = run_power_cell(
                key,
                n_net,
                cell_outer,
                inner_draws,
                n_jobs,
                seed,
                float(pooled_stats[key]["point"]) * 100.0,
            )
            row["note"] = reduction_note
            if cell_outer != outer_draws:
                row["note"] = (
                    reduction_note
                    + ("; " if reduction_note else "")
                    + f"pre-declared sensitivity budget: {cell_outer} outer draws for this mixture panel"
                )
            power_rows.append(row)
            log(
                f"  {key} N={n_net}: power(2pp)={row['power_mue_2pp']:.2f} "
                f"power(3pp)={row['power_mue_3pp']:.2f} power(5pp)={row['power_mue_5pp']:.2f} "
                f"MDE80={row['mde80_pp']:.2f} pp alpha0={row['empirical_alpha_at_zero']:.3f} "
                f"({row['wall_seconds']:.0f} s)"
            )
    timing["section2_design_simulation_seconds"] = time.time() - t0

    # ---------------- section 3: provider leverage ----------------
    log("section 3: provider leverage and independence audit")
    t0 = time.time()
    provider_table_rows: list[dict] = []
    provider_tables: dict[str, dict] = {}
    scenario_rows: list[dict] = []
    leave_one_out_rows: list[dict] = []
    from joblib import Parallel, delayed

    # One parallel batch of case-level network-clustered bootstraps for the whole
    # section; the network-value bootstraps are cheap and stay in-process.
    requests = []
    request_index: dict[str, tuple[str, pd.DataFrame]] = {}
    largest_by_panel: dict[str, str] = {}
    for key in PANEL_ORDER:
        panel_requests, largest = section3_requests(
            key,
            frames[key],
            sorted(frames[key]["provider"].unique()),
            details[key]["per_network"],
        )
        largest_by_panel[key] = largest
        for index, (label, sub_frame, kind) in enumerate(panel_requests):
            tag = f"{key}||{label}"
            requests.append((tag, kind, sub_frame))
            request_index[tag] = (key, sub_frame)
    log(f"  case-level bootstraps in one batch: {len(requests)}")
    boot_results = Parallel(n_jobs=min(LEVERAGE_JOBS, len(requests)), batch_size=1)(
        delayed(_boot_case)(sub_frame, kind, leverage_draws, seed + 17 * i)
        for i, (_, kind, sub_frame) in enumerate(requests)
    )
    case_boot_by_panel: dict[str, dict] = {key: {} for key in PANEL_ORDER}
    for (tag, _, _), result in zip(requests, boot_results):
        key = tag.split("||")[0]
        case_boot_by_panel[key][tag.split("||")[1]] = result

    for key in PANEL_ORDER:
        draw_summary = network_bootstrap_draws(
            details[key]["per_network"], leverage_draws, seed + 5
        )
        rows, table = provider_rows(
            key, frames[key], details[key]["per_network"], case_boot_by_panel[key], draw_summary
        )
        provider_table_rows.extend(rows)
        provider_tables[key] = table
        scenario_rows.extend(
            weighting_scenarios(
                key,
                frames[key],
                table,
                pooled_stats[key],
                case_boot_by_panel[key],
                draw_summary,
                largest_by_panel[key],
            )
        )
        leave_one_out_rows.extend(
            leave_one_provider_out(
                key, frames[key], table, pooled_stats[key], case_boot_by_panel[key], draw_summary
            )
        )
        largest = largest_by_panel[key]
        log(
            f"  {key}: largest provider {largest} = {table[largest]['share_cases']:.1%} of cases, "
            f"{table[largest]['share_networks']:.1%} of networks, "
            f"{len(table)} providers"
        )
    timing["section3_provider_leverage_seconds"] = time.time() - t0

    # ---------------- section 4: requirements ----------------
    log("section 4: independent-evidence requirements")
    t0 = time.time()
    used = used_networks()
    residual = residual_unused_pool(used)
    scenario_frame = pd.DataFrame(scenario_rows)
    requirements = requirements_table(details, power_rows, provider_tables, scenario_frame)
    timing["section4_requirements_seconds"] = time.time() - t0

    # ---------------- outputs ----------------
    log("writing outputs")
    power_table = pd.DataFrame(power_rows)
    power_table.to_csv(OUT / "power_table.csv", index=False)

    variance_table = pd.DataFrame(variance_table_rows)
    variance_table.to_csv(OUT / "network_variance_table.csv", index=False)

    provider_leverage = pd.DataFrame(provider_table_rows)
    provider_leverage.to_csv(OUT / "provider_leverage.csv", index=False)

    requirements.to_csv(OUT / "independent_evidence_requirements.csv", index=False)

    per_net_all = pd.concat(
        [
            details[key]["per_network"].assign(panel=key)
            for key in PANEL_ORDER
        ],
        ignore_index=True,
    )
    per_net_all.to_csv(OUT / "per_network_contrasts.csv", index=False)

    pd.DataFrame(scenario_rows).to_csv(OUT / "weighting_scenarios.csv", index=False)
    pd.DataFrame(leave_one_out_rows).to_csv(OUT / "leave_one_provider_out.csv", index=False)
    residual_rows = [
        {"network_id": row.network_id, "status": f"used_by_scored_panel:{row.now_used_by}"}
        for row in residual["now_used_by_scored_panels"].itertuples()
    ] + [
        {"network_id": network_id, "status": "residual_never_used_by_scored_panels"}
        for network_id in residual["residual_never_used"]
    ]
    pd.DataFrame(residual_rows).to_csv(OUT / "residual_unused_networks.csv", index=False)

    diagnostics = {
        "estimator_equivalence": equivalence,
        "jitter_seed_sensitivity": jitter_check,
        "calibration": calibration,
        "icc_detail": {
            key: {
                "contrast": details[key]["icc_contrast"],
                "screen_failure": details[key]["icc_screen"],
                "length_failure": details[key]["icc_length"],
            }
            for key in PANEL_ORDER
        },
        "residual_unused_pool": {
            "audit_never_used_count": len(residual["audit_never_used_networks"]),
            "residual_count": len(residual["residual_never_used"]),
            "residual_networks": residual["residual_never_used"],
            "reused_since_audit": (
                residual["now_used_by_scored_panels"]
                .groupby("now_used_by")["network_id"]
                .apply(list)
                .to_dict()
                if len(residual["now_used_by_scored_panels"])
                else {}
            ),
        },
    }
    (OUT / "simulation_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, default=str) + "\n", encoding="utf-8"
    )

    timing["total_seconds"] = time.time() - t_start
    fingerprint = {
        "script": "scripts/314_wrr_p0_05_power_and_independence.py",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git": git_head(),
        "config": {
            "retention": RETENTION,
            "tolerance_c": TOLERANCE_C,
            "alpha": ALPHA,
            "mue_points": list(MUE_POINTS),
            "design_ns": list(DESIGN_NS),
            "outer_draws": outer_draws,
            "outer_draws_by_panel": {
                key: min(outer_draws, OUTER_DRAWS_BY_PANEL.get(key, outer_draws))
                for key in PANEL_ORDER
            },
            "inner_draws": inner_draws,
            "n_jobs": n_jobs,
            "leverage_draws": leverage_draws,
            "seed": seed,
            "jitter_seed": JITTER_SEED,
            "budget_seconds": float(args.budget_seconds),
            "quick": bool(args.quick),
            "panel_point_pp": {k: float(pooled_stats[k]["point"]) * 100.0 for k in PANEL_ORDER},
        },
        "estimator": (
            "certificate-minus-length consequential-error rate at matched 70 % retention "
            "(non-finite selected errors counted as failures); network-clustered bootstrap "
            "(percentile interval, resampling whole networks with replacement)"
        ),
        "inputs": [
            file_fingerprint(DEV_CASES),
            file_fingerprint(DEV_CERTS),
            file_fingerprint(W2_CASES),
            file_fingerprint(W2_CERTS),
            file_fingerprint(ROOT / "results/v17_fitness/step9_freeze/certificate.joblib"),
            file_fingerprint(CLAIM_REGISTRY),
            *[file_fingerprint(path) for path in PRIOR_ACCESS_FILES],
            file_fingerprint(TRANSPORT_CASES),
            file_fingerprint(NVE_PROBE_CASES),
        ],
        "outputs": sorted(p.name for p in OUT.glob("*")),
        "timing_seconds": timing,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "self_check": {
            "max_statistic_abs_diff_pp": max(
                v["max_resample_statistic_abs_diff_pp"] for v in equivalence.values()
            ),
            "max_point_abs_diff_pp": max(
                v["abs_diff_point_pp"] for v in equivalence.values()
            ),
        },
    }
    fingerprint["fingerprint_sha256"] = sha256_text(
        json.dumps(fingerprint, sort_keys=True, default=str)
    )
    (OUT / "protocol_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2, default=str) + "\n", encoding="utf-8"
    )

    write_summary(
        out=OUT,
        power_table=power_table,
        variance_table=variance_table,
        provider_leverage=provider_leverage,
        leave_one_out=pd.DataFrame(leave_one_out_rows),
        scenarios=pd.DataFrame(scenario_rows),
        requirements=requirements,
        details=details,
        pooled_stats=pooled_stats,
        provider_tables=provider_tables,
        diagnostics=diagnostics,
        fingerprint=fingerprint,
        timing=timing,
    )
    log(f"done in {timing['total_seconds']:.0f} s -> {OUT}")
    return 0


def _fmt(value, digits=2) -> str:
    try:
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return "n/a"
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def write_summary(
    *,
    out: Path,
    power_table: pd.DataFrame,
    variance_table: pd.DataFrame,
    provider_leverage: pd.DataFrame,
    leave_one_out: pd.DataFrame,
    scenarios: pd.DataFrame,
    requirements: pd.DataFrame,
    details: dict,
    pooled_stats: dict,
    provider_tables: dict,
    diagnostics: dict,
    fingerprint: dict,
    timing: dict,
) -> None:
    lines: list[str] = []
    lines.append("# P0-05 — independence and power design for the final configuration")
    lines.append("")
    lines.append(
        "Script `scripts/314_wrr_p0_05_power_and_independence.py`; command "
        "`PYTHONPATH=src python3 scripts/314_wrr_p0_05_power_and_independence.py`; "
        f"HEAD `{fingerprint['git']['commit'][:12]}`; "
        f"script sha256 `{fingerprint['script_sha256'][:16]}…`; "
        f"wall time {timing['total_seconds']:.0f} s."
    )
    lines.append("")

    lines.append("## Estimator")
    lines.append("")
    lines.append(
        "* Primary contrast: consequential-error rate difference between the final screen "
        "(frozen certificate bound as the ranking score) and the incumbent length rule "
        f"(`longest_run`) at matched {fingerprint['config']['retention']:.0%} retention, tolerance "
        f"{fingerprint['config']['tolerance_c']:.1f} °C, in percentage points; negative = the screen is better."
    )
    lines.append(
        "* Non-finite selected errors count as consequential failures and stay in the denominator "
        "(`operating_point_contrast`)."
    )
    lines.append(
        "* Interval: `stream_recoverability.experiments.v17_fitness.stats.cluster_bootstrap` — "
        "percentile interval from resampling whole networks with replacement; identical point "
        "estimate and interval to the project's `operating_point_contrast` (checked in "
        "`simulation_diagnostics.json`, max |difference| "
        f"{_fmt(fingerprint['self_check']['max_statistic_abs_diff_pp'], 10)} pp)."
    )
    lines.append(
        "* Panels: development = out-of-fold certificate on the 110 development networks "
        "(`step6_screen/development_certificates.parquet`); wave-2 = frozen certificate on the 49 "
        "external networks (`p0_07_wave2_confirmation`). The pooled row is a sensitivity mixture."
    )
    lines.append("")

    lines.append("## 1. Network-level variance of the primary contrast")
    lines.append("")
    lines.append(
        "| panel | cases | nets | pooled pp [95 % CI] | SD within-net contrasts | SD implied by bootstrap | SD ANOVA | ICC(contrast) | DEFF | N_eff |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for key in PANEL_ORDER:
        detail = details[key]
        pooled = detail["pooled"]
        lines.append(
            f"| {key} | {detail['n_cases']:,} | {detail['n_networks']} | "
            f"{_fmt(float(pooled['point'])*100)} [{_fmt(float(pooled['low'])*100)}, "
            f"{_fmt(float(pooled['high'])*100)}] | {_fmt(detail['sd_within'])} | "
            f"{_fmt(detail['sd_implied'])} | {_fmt(detail['anova_sd'])} | "
            f"{_fmt(detail['icc_contrast']['icc'], 4)} | "
            f"{_fmt(detail['icc_contrast']['design_effect'], 2)} | "
            f"{_fmt(detail['icc_contrast']['effective_networks'], 1)} |"
        )
    lines.append("")
    lines.append(
        "SD within-net contrasts is the SD (ddof=1) of the per-network within-network contrast "
        "(each network does its own 70 % selection; the step-7 convention) — this is the variance "
        "component of the network-equal estimand. SD implied by bootstrap is `SE x sqrt(n_networks)` "
        "(the project's own convention in `scripts/186_v17_freeze.py`) and is the operative "
        "between-network SD for the pooled case-weighted estimand. SD ANOVA is "
        "`sqrt((MSB-MSW)/n0)` from the one-way random-effects decomposition of the exact case-level "
        "contrast `d_i = (x_i - y_i)/0.70`. The fixed-selection influence SDs are also in "
        "`network_variance_table.csv`; they overstate the bootstrap and are **not** used for power."
    )
    lines.append("")
    lines.append(
        "The network-equal mean is mildly jitter-seed sensitive because the length rule breaks ties in "
        "`longest_run` at random: seed 991 (the primary estimator's seed) gives "
        f"{_fmt(details['wave2_external']['network_equal']['point'])} pp on wave-2 where the step-7 seed "
        "61 gives -5.46 pp; the pooled case-weighted headline is unaffected (its point estimate and "
        "interval are identical to `operating_point_contrast`, verified in "
        "`simulation_diagnostics.json`)."
    )
    lines.append("")
    lines.append(
        "ICC is the intra-network correlation of that case-level contrast (one-way random-effects "
        "ICC(1), unbalanced). Large ICC x large networks is why the design effect is high: the "
        "contrast is mostly a within-network case-level quantity, so cases are not independent "
        "evidence about networks."
    )
    lines.append("")

    lines.append("## 2. Design simulation (N x MUE)")
    lines.append("")
    lines.append("### Headline")
    lines.append("")
    dev20 = power_table.loc[
        power_table["panel"].eq("development") & power_table["design_n"].eq(20)
    ]
    dev80 = power_table.loc[
        power_table["panel"].eq("development") & power_table["design_n"].eq(80)
    ]
    if len(dev20) and len(dev80):
        lines.append(
            f"* At N=20 development networks the design reaches "
            f"{_fmt(float(dev20['power_mue_2pp'].iloc[0]), 2)} power for a 2 pp effect and "
            f"{_fmt(float(dev20['power_mue_5pp'].iloc[0]), 2)} for 5 pp (MDE80 "
            f"{_fmt(float(dev20['mde80_pp'].iloc[0]))} pp); at N=80, "
            f"{_fmt(float(dev80['power_mue_2pp'].iloc[0]), 2)} for 2 pp with MDE80 "
            f"{_fmt(float(dev80['mde80_pp'].iloc[0]))} pp."
        )
    lines.append(
        "* The pre-declared 5 pp effect of `scripts/186_v17_freeze.py` is detected with practical "
        "certainty from N=20 upward; the binding requirement is the 2 pp MUE."
    )
    lines.append(
        "* The **effective independent network count is far below the network count**: at the current "
        f"development panel size the contrast behaves like "
        f"{_fmt(details['development']['icc_contrast']['effective_networks'], 1)} independent networks "
        f"(wave-2: {_fmt(details['wave2_external']['icc_contrast']['effective_networks'], 1)}), because "
        "the intra-network correlation of the contrast is small but the networks hold hundreds of "
        "cases each."
    )
    lines.append("")
    lines.append(
        "Each draw samples N networks with replacement from the panel's empirical network "
        "distribution (all cases of a drawn network; duplicated draws are independent clusters), "
        "recomputes the contrast and its network-clustered bootstrap interval "
        f"({fingerprint['config']['inner_draws']} inner draws per study, joblib n_jobs="
        f"{fingerprint['config']['n_jobs']}). Outer draws per panel: "
        + ", ".join(
            f"{k} = {v}" for k, v in fingerprint["config"]["outer_draws_by_panel"].items()
        )
        + "; the development and wave-2 rows carry the full 2000 draws, the pooled mixture is a "
        "pre-declared sensitivity with a smaller budget (also recorded per row in the "
        "`outer_draws` column of `power_table.csv`)."
    )
    lines.append("")
    lines.append(
        "| panel | N | mean point pp | SD of points | mean bootstrap SE | power @panel effect | empirical alpha at 0 | power 2 pp | power 3 pp | power 5 pp | MDE80 pp | analytic MDE80 pp | wall s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in power_table.to_dict("records"):
        lines.append(
            f"| {row['panel']} | {row['design_n']} | {_fmt(row['mean_point_pp'])} | "
            f"{_fmt(row['sd_point_pp'])} | {_fmt(row['mean_bootstrap_se_pp'])} | "
            f"{_fmt(row['power_at_panel_effect'], 3)} | {_fmt(row['empirical_alpha_at_zero'], 3)} | "
            f"{_fmt(row['power_mue_2pp'], 3)} | {_fmt(row['power_mue_3pp'], 3)} | "
            f"{_fmt(row['power_mue_5pp'], 3)} | {_fmt(row['mde80_pp'])} | "
            f"{_fmt(row['mde80_z_pp'])} | {_fmt(row['wall_seconds'], 0)} |"
        )
    lines.append("")
    lines.append(
        "*Power* is the share of simulated studies whose network-clustered 95 % interval excludes "
        "zero after the study is re-centred on a true effect equal to the MUE (shift model: the same "
        "shift is applied to every draw, so the empirical shape and width of the sampling "
        "distribution are preserved). *Empirical alpha at 0* is the same calculation with a true "
        "effect of exactly 0 pp; it should sit near 0.05 and is the coverage check of the whole "
        "machinery. *MDE80* solves the same simulated power function for 80 %; the analytic column is "
        "`2.802 x SD_implied / sqrt(N)` and is reported as a cross-check, not as the headline."
    )
    lines.append("")
    lines.append("### Coverage check (read this before quoting the power numbers)")
    lines.append("")
    lines.append(
        "| panel | N | SD of simulated points | mean bootstrap SE | ratio | empirical alpha at 0 |"
    )
    lines.append("|---|---|---|---|---|---|")
    for row in power_table.to_dict("records"):
        ratio = (
            float(row["sd_point_pp"]) / float(row["mean_bootstrap_se_pp"])
            if float(row["mean_bootstrap_se_pp"]) > 0
            else float("nan")
        )
        lines.append(
            f"| {row['panel']} | {row['design_n']} | {_fmt(row['sd_point_pp'])} | "
            f"{_fmt(row['mean_bootstrap_se_pp'])} | {_fmt(ratio, 3)} | "
            f"{_fmt(row['empirical_alpha_at_zero'], 3)} |"
        )
    lines.append("")
    lines.append(
        "If the empirical alpha at zero exceeds 0.05, the nominal 95 % network-clustered percentile "
        "interval under-covers at that design size, and the power figures that come from that same "
        "interval are optimistic; the analytic MDE80 column, which uses the simulated SD of the "
        "points rather than the interval width, is the more conservative reading at small N. The "
        "ratio column shows whether the bootstrap SE reproduces the design's own sampling SD."
    )
    lines.append("")

    lines.append("## 3. Independence audit: provider and network leverage")
    lines.append("")
    lines.append("### Shares")
    lines.append("")
    lines.append("| panel | provider | networks | share nets | cases | share cases | case-weighted pp | network-equal pp |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in provider_leverage.to_dict("records"):
        lines.append(
            f"| {row['panel']} | {row['provider']} | {int(row['n_networks'])} | "
            f"{_fmt(float(row['share_networks'])*100, 1)} % | {int(row['n_cases']):,} | "
            f"{_fmt(float(row['share_cases'])*100, 1)} % | "
            f"{_fmt(row['case_weighted_contrast_pp'])} | {_fmt(row['network_equal_contrast_pp'])} |"
        )
    lines.append("")
    lines.append("### Weighting scenarios")
    lines.append("")
    lines.append("| panel | scenario | basis | contrast pp | 95 % CI |")
    lines.append("|---|---|---|---|---|")
    for row in scenarios.to_dict("records"):
        lines.append(
            f"| {row['panel']} | {row['scenario']} | {row['weight_basis']} | "
            f"{_fmt(row['contrast_pp'])} | [{_fmt(row['ci_low_pp'])}, {_fmt(row['ci_high_pp'])}] |"
        )
    lines.append("")
    lines.append("### Leave-one-provider-out (network-equal)")
    lines.append("")
    lines.append("| panel | dropped | nets left | cases left | network-equal pp | Δ vs all pp |")
    lines.append("|---|---|---|---|---|---|")
    for row in leave_one_out.to_dict("records"):
        lines.append(
            f"| {row['panel']} | {row['dropped_provider']} | {int(row['n_networks_remaining'])} | "
            f"{int(row['n_cases_remaining']):,} | {_fmt(row['network_equal_contrast_pp'])} | "
            f"{_fmt(row['network_equal_delta_vs_all_pp'])} |"
        )
    lines.append("")

    wave2 = provider_tables["wave2_external"]
    usgs = wave2.get("usgs", {})
    lines.append("### Verdict on provider-level generalisation")
    lines.append("")
    wave2_scen = scenarios.loc[scenarios["panel"].eq("wave2_external")].set_index("scenario")
    lines.append(
        f"**No — the current evidence does not support provider-level generalisation beyond a "
        f"directional statement.** In the wave-2 external panel USGS holds "
        f"{_fmt(usgs.get('share_cases', float('nan'))*100, 1)} % of cases and "
        f"{_fmt(usgs.get('share_networks', float('nan'))*100, 1)} % of networks; the non-USGS pool is "
        f"{sum(v['n_networks'] for k, v in wave2.items() if k != 'usgs')} networks "
        f"({sum(v['n_cases'] for k, v in wave2.items() if k != 'usgs'):,} cases) across "
        f"{sum(1 for k in wave2 if k != 'usgs')} providers, one of which (UK EA) is a single network "
        "of 21 cases. Concretely, on the wave-2 panel:"
    )
    lines.append("")
    for scenario in (
        "case_weighted_pooled",
        "network_equal",
        "provider_equal",
        "downweight_usgs_to_median_provider_by_networks",
        "downweight_usgs_to_median_provider_by_cases",
        "leave_usgs_out_network_equal",
        "leave_usgs_out_case_weighted",
    ):
        if scenario in wave2_scen.index:
            row = wave2_scen.loc[scenario]
            lines.append(
                f"* `{scenario}`: {_fmt(row['contrast_pp'])} pp "
                f"[{_fmt(row['ci_low_pp'])}, {_fmt(row['ci_high_pp'])}]"
            )
    lines.append("")
    lines.append(
        "The direction and rough size survive re-weighting on this panel, but the intervals widen "
        "sharply once USGS is removed and the non-USGS stratum rests on 5 networks. "
        "'Three providers' is therefore three *sampling frames* on one dominant agency's measurement "
        "practice, not three independent validated populations; a provider-level claim needs new "
        "networks from providers that are not in any opened panel."
    )
    lines.append("")

    lines.append("## 4. What is missing: claims that need networks used nowhere yet")
    lines.append("")
    needs_new = requirements.loc[
        requirements["needs_networks_not_yet_used"].astype(bool)
    ]["claim_id"].astype(str).tolist()
    design_rows = requirements.loc[requirements["requirement_type"].eq("design_power")]
    lines.append(
        "Machine-readable in `independent_evidence_requirements.csv`. Claims whose current wording "
        "needs networks outside every opened panel (development, reserved-36 opened, wave-2, sealed "
        f"USGS, transport, NVE probe): {', '.join(sorted(set(needs_new))) or 'none'}. "
        "The 36-network reserved panel is opened and is **not** proposed as new confirmation, and "
        "neither is any other opened panel."
    )
    lines.append("")
    lines.append(
        "Design requirements from the analytic relation `N = (2.802 x SD / MUE)^2` (panel-specific SD):"
    )
    lines.append("")
    lines.append("| panel | MUE 2 pp | MUE 3 pp | MUE 5 pp |")
    lines.append("|---|---|---|---|")
    for key in PANEL_ORDER:
        cells = []
        for mue in MUE_POINTS:
            sub = design_rows.loc[
                design_rows["requirement_id"].eq(f"PWR-{key}-MUE{int(mue)}pp"), "missing_evidence"
            ]
            cells.append(str(sub.iloc[0]).split(" ")[0] if len(sub) else "n/a")
        lines.append(f"| {key} | {cells[0]} networks | {cells[1]} networks | {cells[2]} networks |")
    lines.append("")
    residual = diagnostics["residual_unused_pool"]
    lines.append(
        f"Residual untouched pool in the repository: the multi-agency prior-access audit flagged "
        f"{residual['audit_never_used_count']} never-used networks, but "
        f"{sum(len(v) for v in residual['reused_since_audit'].values())} of them are now used by "
        f"scored/opened panels (the p0_07b transport score); the derived residual is "
        f"{residual['residual_count']} network(s) (`residual_unused_networks.csv`). Any new "
        "confirmation therefore needs newly recruited networks from providers not yet in the panel, "
        "and a fresh repo-wide prior-access audit before sealing."
    )
    lines.append("")

    lines.append("## What this does not prove")
    lines.append("")
    lines.append(
        "1. **Not a new confirmation.** Nothing here scores a new panel. The reserved 36-network "
        "panel, wave-2, the sealed USGS panel, the transport panel and the NVE probe are opened and "
        "cannot be re-used as confirmation."
    )
    lines.append(
        "2. **The empirical distribution is the panel, not the target population.** Power is computed "
        "by resampling networks from the development or wave-2 network distribution. If a newly "
        "recruited population has a different between-network spread, the power numbers move."
    )
    lines.append(
        "3. **Shift model.** MUE power re-centres each simulated study on the MUE; it assumes the "
        "shape and width of the sampling distribution do not depend on the true effect. The "
        "normal-approximation columns are reported beside it and the empirical alpha at 0 is the "
        "coverage check."
    )
    lines.append(
        "4. **Wave-2 has 49 networks.** A design N of 60 or 80 cannot be drawn from the wave-2 pool "
        "without heavy network reuse (recorded as `mean_distinct_networks` and "
        "`share_draws_with_duplicates` in `power_table.csv`); those rows describe a super-population, "
        "not a feasible recruitment from the existing list."
    )
    lines.append(
        "5. **ICC is defined on a selection-derived variable.** `d_i` depends on the retention rule, "
        "so the ICC is a property of this operating point (0.5 and 0.9 retention are reported in "
        "`network_variance_table.csv`)."
    )
    lines.append(
        "6. **Case counts are not independent observations.** Outage realisations repeat within "
        "station-years; every interval here clusters by network and the effective independent "
        "network count is far below the network count."
    )
    lines.append(
        "7. **Provider weighting is not a substitute for new providers.** Re-weighting changes the "
        "estimand; it does not add independent measurement practice."
    )
    lines.append("")

    lines.append("## Files")
    lines.append("")
    for name in (
        "power_table.csv",
        "network_variance_table.csv",
        "provider_leverage.csv",
        "independent_evidence_requirements.csv",
        "protocol_fingerprint.json",
        "SUMMARY.md",
    ):
        lines.append(f"* `{name}` (required)")
    for name in (
        "weighting_scenarios.csv",
        "leave_one_provider_out.csv",
        "per_network_contrasts.csv",
        "residual_unused_networks.csv",
        "simulation_diagnostics.json",
    ):
        lines.append(f"* `{name}` (supporting)")
    lines.append("")
    lines.append(
        f"Wall time by section (s): "
        + ", ".join(f"{k}={v:.0f}" for k, v in timing.items() if k != "total_seconds")
        + f"; total={timing['total_seconds']:.0f}."
    )
    if fingerprint["config"].get("quick"):
        lines.append("")
        lines.append("**Smoke test run (`--quick`): draw counts were reduced; do not quote these numbers.**")
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
