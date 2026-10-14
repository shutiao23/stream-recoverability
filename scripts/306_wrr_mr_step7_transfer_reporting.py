#!/usr/bin/env python3
"""Major-revision Step 7: transfer reporting beyond provider headcount.

Reports wave-2 certificate-vs-length contrasts with:
  - case-weighted pooled (existing seal)
  - network-equal mean of per-network contrasts
  - provider-separate
  - strata by donor scarcity and anomalous-warm years

Does not recruit new networks or retune thresholds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.paths import PRIMARY_TOLERANCE_C  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step7_transfer_reporting"
)
CASES = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_cases.parquet"
)
CERTS = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/wave2_certificates.parquet"
)
SEAL = (
    ROOT
    / "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/verdict.json"
)
RETENTION = 0.7
SEED = 61
BOOT = 1500


def per_network_contrast(cases: pd.DataFrame, certs: pd.DataFrame) -> pd.DataFrame:
    frame = cases[["network_id", "provider"]].copy()
    frame["cert_score"] = pd.to_numeric(certs["certificate_bound"], errors="coerce").fillna(np.inf)
    frame["cert_error"] = pd.to_numeric(certs["certificate_abs_error"], errors="coerce")
    rng = np.random.default_rng(SEED)
    frame["length"] = pd.to_numeric(cases["longest_run"], errors="coerce") + rng.random(len(cases))
    frame["policy_error"] = pd.to_numeric(cases["abserr_policy"], errors="coerce")

    rows = []
    for (network_id, provider), block in frame.groupby(["network_id", "provider"]):
        k = max(1, int(round(RETENTION * len(block))))
        if k > len(block):
            continue
        cert = block.nsmallest(k, "cert_score")["cert_error"].to_numpy(dtype=float)
        length = block.nsmallest(k, "length")["policy_error"].to_numpy(dtype=float)

        def fail(err: np.ndarray) -> float:
            return float(((~np.isfinite(err)) | (err > PRIMARY_TOLERANCE_C)).mean())

        rows.append(
            {
                "network_id": network_id,
                "provider": provider,
                "n_cases": int(len(block)),
                "contrast_points": (fail(cert) - fail(length)) * 100,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(CASES).reset_index(drop=True)
    certs = pd.read_parquet(CERTS).reset_index(drop=True)
    seal = json.loads(SEAL.read_text())

    per_net = per_network_contrast(cases, certs)
    per_net.to_csv(OUT / "per_network_contrasts.csv", index=False)

    # Network-equal mean with cluster bootstrap over networks.
    def net_equal(block: pd.DataFrame) -> float:
        return float(block.groupby("network_id")["contrast_points"].mean().mean())

    # Rebuild a frame for bootstrapping network equal mean of contrasts:
    # bootstrap networks from per_net table.
    def boot_net_equal() -> dict:
        keys = per_net["network_id"].tolist()
        values = per_net.set_index("network_id")["contrast_points"].to_dict()
        rng = np.random.default_rng(SEED)
        point = float(np.mean([values[k] for k in keys]))
        draws = []
        for _ in range(BOOT):
            picked = rng.choice(keys, size=len(keys), replace=True)
            draws.append(float(np.mean([values[k] for k in picked])))
        arr = np.asarray(draws, dtype=float)
        return {
            "point_pp": point,
            "ci_low_pp": float(np.quantile(arr, 0.025)),
            "ci_high_pp": float(np.quantile(arr, 0.975)),
            "n_networks": int(len(keys)),
        }

    network_equal = boot_net_equal()

    # Provider shares and contrasts (reuse seal where available).
    provider_rows = []
    for provider, block in cases.groupby("provider"):
        share = len(block) / len(cases)
        sealed = seal.get("by_provider_points", {}).get(provider, {})
        provider_rows.append(
            {
                "provider": provider,
                "n_cases": int(len(block)),
                "share_of_cases": float(share),
                "n_networks": int(block["network_id"].nunique()),
                "sealed_contrast_points": sealed.get("contrast_points"),
                "sealed_ci_low_points": sealed.get("ci_low_points"),
                "sealed_ci_high_points": sealed.get("ci_high_points"),
                "network_equal_contrast_points": float(
                    per_net.loc[per_net.provider.eq(provider), "contrast_points"].mean()
                )
                if (per_net.provider == provider).any()
                else None,
            }
        )
    providers = pd.DataFrame(provider_rows).sort_values("n_cases", ascending=False)
    providers.to_csv(OUT / "provider_weights.csv", index=False)

    # Donor scarcity stratum
    regime = cases["donor_regime"].astype(str) if "donor_regime" in cases.columns else None
    strata_rows = []
    if regime is not None:
        for value, block in cases.groupby(regime):
            if block["network_id"].nunique() < 5 or len(block) < 100:
                strata_rows.append(
                    {
                        "stratum": f"donor_regime={value}",
                        "n_cases": int(len(block)),
                        "n_networks": int(block["network_id"].nunique()),
                        "skipped": True,
                    }
                )
                continue
            stat = operating_point_contrast(
                block.reset_index(drop=True),
                certs.loc[block.index].reset_index(drop=True),
                retention=RETENTION,
                seed=SEED,
                draws=BOOT,
            )
            strata_rows.append(
                {
                    "stratum": f"donor_regime={value}",
                    "n_cases": int(len(block)),
                    "n_networks": int(block["network_id"].nunique()),
                    "contrast_points": float(stat["point"]) * 100,
                    "ci_low_points": float(stat["low"]) * 100,
                    "ci_high_points": float(stat["high"]) * 100,
                    "skipped": False,
                }
            )

    # Non-USGS pooled
    non = cases.loc[~cases["provider"].astype(str).eq("usgs")]
    if len(non) and non["network_id"].nunique() >= 3:
        stat = operating_point_contrast(
            non.reset_index(drop=True),
            certs.loc[non.index].reset_index(drop=True),
            retention=RETENTION,
            seed=SEED + 3,
            draws=BOOT,
        )
        non_usgs = {
            "n_cases": int(len(non)),
            "n_networks": int(non["network_id"].nunique()),
            "share_of_cases": float(len(non) / len(cases)),
            "contrast_points": float(stat["point"]) * 100,
            "ci_low_points": float(stat["low"]) * 100,
            "ci_high_points": float(stat["high"]) * 100,
        }
    else:
        non_usgs = {"skipped": True}

    report = {
        "sealed_pooled_case_weighted_pp": seal["contrast_points"],
        "sealed_ci": [seal["ci_low_points"], seal["ci_high_points"]],
        "network_equal_pp": network_equal,
        "usgs_case_share": float((cases.provider.astype(str) == "usgs").mean()),
        "providers": providers.to_dict(orient="records"),
        "donor_regime_strata": strata_rows,
        "non_usgs_pooled": non_usgs,
        "scope_sentence": (
            "Wave-2 is a USGS-majority designed-missingness confirmation "
            f"({100*(cases.provider.astype(str)=='usgs').mean():.1f}% of cases); "
            "network-equal and non-USGS pooled results are reported separately and "
            "must not be replaced by the case-weighted pooled headline alone."
        ),
        "may_enter_abstract_or_conclusions": True,
        "label_required": "USGS-majority designed confirmation with smaller Hub'Eau / UK EA support",
    }
    pd.DataFrame(strata_rows).to_csv(OUT / "donor_regime_strata.csv", index=False)
    (OUT / "transfer_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "SUMMARY.md").write_text(
        "# Step 7 — transfer reporting\n\n"
        + report["scope_sentence"]
        + "\n\n"
        + f"- Sealed case-weighted: {report['sealed_pooled_case_weighted_pp']:.2f} pp "
        + f"[{report['sealed_ci'][0]:.2f}, {report['sealed_ci'][1]:.2f}]\n"
        + f"- Network-equal: {network_equal['point_pp']:.2f} pp "
        + f"[{network_equal['ci_low_pp']:.2f}, {network_equal['ci_high_pp']:.2f}]\n"
        + f"- USGS case share: {100*report['usgs_case_share']:.1f}%\n"
        + f"- Non-USGS pooled: {json.dumps(non_usgs)}\n\n"
        + providers.to_string(index=False)
        + "\n"
    )
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
