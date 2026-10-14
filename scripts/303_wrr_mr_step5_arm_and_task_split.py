#!/usr/bin/env python3
"""Major-revision Step 5a: arm-wise effects + anomalous-year strata.

Referee Opinion 5: the pooled designed-panel Δ must not be read as real-fault
benefit. This script:

1. Re-scores wave-2 and reserved panels **by arm** (empirical vs stratified)
   with network-clustered certificate-vs-length contrasts at 70% / 0.5 °C.
2. Stratifies the same contrasts by anomalous thermal years (truth hottest-30
   far above the station's climatological peak) as a first anomalous-year task.
3. Writes a protocol stub for full-year calendar replay and network co-failure
   (heavier rebuilds; not executed here).

Does not retune any threshold.
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
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP10_CONFIRM,
)

OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "step5_monitoring_tasks"
)
WAVE2_CASES = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "p0_07_wave2_ingest"
    / "p0_07_wave2_confirmation"
    / "wave2_cases.parquet"
)
WAVE2_CERT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "p0_07_wave2_ingest"
    / "p0_07_wave2_confirmation"
    / "wave2_certificates.parquet"
)
RETENTION = 0.70
BOOT = 2000
SEED = 31
ANOMALY_Z = 1.0  # station-year truth hottest30 exceeds clim_peak by ≥ this many °C


def _contrast_block(cases: pd.DataFrame, certs: pd.DataFrame, *, label: str, seed: int) -> dict:
    aligned_cert = certs.reindex(cases.index)
    # operating_point_contrast expects positional alignment with cases
    cases = cases.reset_index(drop=True)
    aligned_cert = aligned_cert.reset_index(drop=True)
    stat = operating_point_contrast(
        cases,
        aligned_cert,
        retention=RETENTION,
        tolerance=PRIMARY_TOLERANCE_C,
        seed=seed,
        draws=BOOT,
    )
    return {
        "label": label,
        "n_cases": int(len(cases)),
        "n_networks": int(cases["network_id"].nunique()),
        "n_providers": int(cases["provider"].nunique()) if "provider" in cases.columns else None,
        "contrast_points": float(stat["point"]) * 100,
        "ci_low_points": float(stat["low"]) * 100,
        "ci_high_points": float(stat["high"]) * 100,
        "n_clusters": int(stat["n_clusters"]),
        "n_cert_reconstruction_failures": int(stat["n_cert_reconstruction_failures"]),
        "ci_excludes_zero": bool(
            np.isfinite(stat["low"])
            and np.isfinite(stat["high"])
            and not (stat["low"] <= 0 <= stat["high"])
        ),
        "beneficial": bool(stat["point"] < 0 and stat["high"] < 0),
    }


def anomalous_mask(cases: pd.DataFrame) -> pd.Series:
    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce")
    clim = pd.to_numeric(cases["clim_peak"], errors="coerce")
    return (truth - clim) >= ANOMALY_Z


def score_panel(name: str, cases: pd.DataFrame, certs: pd.DataFrame, *, seed: int) -> list[dict]:
    rows = []
    # Ensure certificates share the case index order
    if not cases.index.equals(certs.index):
        # wave2 / reserved are written in matching row order
        certs = certs.copy()
        certs.index = cases.index
    rows.append(_contrast_block(cases, certs, label=f"{name}|pooled", seed=seed))
    if "arm" in cases.columns:
        for arm, block in cases.groupby("arm", sort=True):
            rows.append(
                _contrast_block(
                    block,
                    certs.loc[block.index],
                    label=f"{name}|arm={arm}",
                    seed=seed + 1,
                )
            )
    if {"truth_hottest30", "clim_peak"}.issubset(cases.columns):
        mask = anomalous_mask(cases)
        for flag, label in ((True, "anomalous_warm"), (False, "typical_or_cool")):
            block = cases.loc[mask.eq(flag)]
            if len(block) < 50 or block["network_id"].nunique() < 5:
                rows.append(
                    {
                        "label": f"{name}|thermal={label}",
                        "n_cases": int(len(block)),
                        "n_networks": int(block["network_id"].nunique()) if len(block) else 0,
                        "skipped": True,
                        "reason": "too few cases/networks",
                    }
                )
                continue
            rows.append(
                _contrast_block(
                    block,
                    certs.loc[block.index],
                    label=f"{name}|thermal={label}",
                    seed=seed + 2,
                )
            )
        # Cross: empirical × anomalous
        if "arm" in cases.columns:
            for arm in ("empirical", "stratified"):
                block = cases.loc[cases["arm"].astype(str).eq(arm) & mask]
                if len(block) < 50 or block["network_id"].nunique() < 5:
                    rows.append(
                        {
                            "label": f"{name}|arm={arm}|thermal=anomalous_warm",
                            "n_cases": int(len(block)),
                            "n_networks": int(block["network_id"].nunique()) if len(block) else 0,
                            "skipped": True,
                        }
                    )
                    continue
                rows.append(
                    _contrast_block(
                        block,
                        certs.loc[block.index],
                        label=f"{name}|arm={arm}|thermal=anomalous_warm",
                        seed=seed + 3,
                    )
                )
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    # Wave-2 sealed confirmation panel (designed missingness; arm split is post-hoc).
    w_cases = pd.read_parquet(WAVE2_CASES)
    w_cert = pd.read_parquet(WAVE2_CERT)
    assert len(w_cases) == len(w_cert)
    w_cases = w_cases.reset_index(drop=True)
    w_cert = w_cert.reset_index(drop=True)
    print("Scoring wave-2 by arm / thermal...", flush=True)
    rows.extend(score_panel("wave2", w_cases, w_cert, seed=SEED))

    # Reserved retrospective
    r_cases = pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True)
    r_cert = pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True)
    print("Scoring reserved by arm / thermal...", flush=True)
    rows.extend(score_panel("reserved_retrospective", r_cases, r_cert, seed=SEED + 100))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "arm_and_thermal_contrasts.csv", index=False)
    (OUT / "arm_and_thermal_contrasts.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )

    protocol = {
        "step": 5,
        "completed_here": [
            "wave2 and reserved arm-wise certificate-vs-length contrasts",
            "anomalous-warm year stratum (truth_hottest30 - clim_peak >= 1C)",
        ],
        "still_required": [
            {
                "task": "full_year_real_mask_replay",
                "description": (
                    "Extract intact annual missingness calendars from real incomplete "
                    "station-years (not resampled gap segments) and transplant onto "
                    "independent complete years; evaluate both years for multi-year faults."
                ),
                "status": "not_executed",
            },
            {
                "task": "network_co_failure",
                "description": (
                    "Simultaneously mask target and a controlled fraction of donors "
                    "under the same event; report when donor-using methods lose benefit "
                    "and whether the screen abstains."
                ),
                "status": "not_executed",
            },
            {
                "task": "anomalous_thermal_years_held_out_train",
                "description": (
                    "Train only on ordinary years; test on warm / peak-shifted years. "
                    "Current stratum uses labels for evaluation only but same LOYO train."
                ),
                "status": "partial_stratum_only",
            },
        ],
        "interpretation_rules": [
            "Pooled wave-2 Δ is a designed-missingness result, not a real-fault expectation.",
            "Empirical-arm CI including zero means archive-repair benefit is unresolved on that arm.",
            "Do not average empirical and stratified into one application claim.",
        ],
    }
    (OUT / "STEP5_PROTOCOL_STATUS.json").write_text(json.dumps(protocol, indent=2) + "\n")

    lines = [
        "# Step 5a — arm-wise and anomalous-year contrasts",
        "",
        "Certificate vs length rule at 70% retention / 0.5 °C (network-clustered).",
        "Wave-2 arm split is a **post-hoc decomposition** of the sealed panel (not a new seal).",
        "",
        table[
            [
                c
                for c in [
                    "label",
                    "n_cases",
                    "n_networks",
                    "contrast_points",
                    "ci_low_points",
                    "ci_high_points",
                    "beneficial",
                    "skipped",
                ]
                if c in table.columns
            ]
        ].to_string(index=False),
        "",
        "## Still required for full Step 5",
        "",
        "- Full-year real missingness calendar replay",
        "- Network co-failure (target + donors)",
        "- Train-on-ordinary / test-on-anomalous (beyond evaluation stratum)",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print((OUT / "SUMMARY.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
