#!/usr/bin/env python3
"""One-time P0-07 wave-2 confirmation score (requires --unseal-score).

Refuses unless floors_met, prior-access clean, seal scored=false, and method
hashes match P0_07_NEW_CONFIRMATION_SEAL.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.development_recovery import read_temperature_panel  # noqa: E402
from stream_recoverability.experiments.v17_fitness.cases import build_station_cases  # noqa: E402
from stream_recoverability.experiments.v17_fitness.frontier import (  # noqa: E402
    all_frontiers,
    operating_point_contrast,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP9_FREEZE,
)
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready.run_identity import (  # noqa: E402
    run_fail_closed,
    sha256_file,
)

READY = ROOT / "results/wrr_submission_ready"
WAVE = READY / "p0_07_wave2_ingest"
SEAL = READY / "P0_07_NEW_CONFIRMATION_SEAL.json"
MANIFEST = WAVE / "wave2_inputs_manifest.csv"
PRIOR = WAVE / "wave2_prior_access_summary.json"
FLOOR = WAVE / "floor_status.json"
OUT = WAVE / "p0_07_wave2_confirmation"
PRIMARY_RETENTION = 0.70
TEMP_C_MIN, TEMP_C_MAX = -5.0, 45.0


def _complete_years(series: pd.Series) -> list[int]:
    s = pd.to_numeric(series, errors="coerce")
    values = s.to_numpy(dtype=float)
    values = np.where(
        np.isfinite(values) & ((values < TEMP_C_MIN) | (values > TEMP_C_MAX)),
        np.nan,
        values,
    )
    s = pd.Series(values, index=s.index)
    years = []
    for year, block in s.groupby(s.index.year):
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        finite = block.dropna()
        if len(finite) >= expected - 1 and np.isfinite(finite.to_numpy(dtype=float)).all():
            years.append(int(year))
    return years


def _load_panel(network_id: str, source_root: str) -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST)
    row = manifest.loc[manifest.network_id.astype(str).eq(str(network_id))]
    if row.empty:
        raise FileNotFoundError(network_id)
    path = ROOT / str(row.iloc[0].input_path)
    digest = sha256_file(path)
    if digest != str(row.iloc[0].sha256):
        raise RuntimeError(f"hash drift for {network_id}")
    panel = read_temperature_panel(str(path))
    panel.columns = [str(c) for c in panel.columns]
    return panel


def verify_gates() -> dict:
    if not SEAL.is_file() or not MANIFEST.is_file():
        raise FileNotFoundError("missing seal or wave2 manifest")
    sealed = json.loads(SEAL.read_text())
    if sealed.get("scored"):
        raise RuntimeError("new confirmation already scored; refuse to re-score")
    floor = json.loads(FLOOR.read_text()) if FLOOR.is_file() else {}
    prior = json.loads(PRIOR.read_text()) if PRIOR.is_file() else {}
    man_sum = json.loads((WAVE / "wave2_manifest_summary.json").read_text())
    if not man_sum.get("floors_met") and not floor.get("floors_met"):
        raise RuntimeError("floors not met")
    if not prior.get("clean"):
        raise RuntimeError("prior-access gate not clean; see wave2_prior_access_hits.csv")
    # method hashes must still match seal
    for item in sealed.get("method_hashes") or []:
        path = ROOT / item["path"]
        if not path.is_file():
            raise RuntimeError(f"missing hashed method file {item['path']}")
        digest = sha256_file(path)
        if digest != item["sha256"]:
            raise RuntimeError(f"method hash drift: {item['path']}")
    if int(man_sum.get("n_networks") or 0) < 30:
        raise RuntimeError("manifest below 30 networks")
    if int(man_sum.get("n_providers") or 0) < 3:
        raise RuntimeError("manifest below 3 providers")
    return sealed


def build_cases() -> pd.DataFrame:
    import stream_recoverability.experiments.v17_fitness.cases as cases_mod

    cases_mod.load_network_panel = _load_panel  # type: ignore[attr-defined]
    manifest = pd.read_csv(MANIFEST)
    frames = []
    for row in manifest.itertuples():
        panel = _load_panel(str(row.network_id), "wave2_confirmation")
        for station_id in str(row.station_ids_ge4).split(";"):
            if not station_id or station_id not in panel.columns:
                continue
            years = _complete_years(pd.to_numeric(panel[station_id], errors="coerce"))
            if len(years) < 4:
                continue
            job = {
                "network_id": str(row.network_id),
                "station_id": station_id,
                "provider": str(row.provider),
                "source_root": "wave2_confirmation",
                "split_role": "wave2_confirmation",
                "regulation_status": "unknown",
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
            }
            frame = build_station_cases(job)
            if not frame.empty:
                frames.append(frame)
                print(row.network_id, station_id, len(frame), flush=True)
    if not frames:
        raise RuntimeError("no cases built from wave-2 panel")
    return pd.concat(frames, ignore_index=True)


def score(directory: Path, manifest) -> list[Path]:
    sealed = verify_gates()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    cases = attach_policy_errors(cases)
    cases_path = OUT / "wave2_cases.parquet"
    cases.to_parquet(cases_path, index=False)

    model = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(cases)
    cert_path = OUT / "wave2_certificates.parquet"
    certificates.to_parquet(cert_path, index=False)

    frontiers = all_frontiers(cases, certificates)
    frontiers.to_csv(OUT / "wave2_frontiers.csv", index=False)
    contrast = operating_point_contrast(cases, certificates, retention=PRIMARY_RETENTION, seed=0)

    by_provider = {}
    for provider, block in cases.groupby("provider"):
        sub = certificates.loc[block.index]
        if len(block) < 100:
            continue
        by_provider[str(provider)] = operating_point_contrast(
            block.reset_index(drop=True),
            sub.reset_index(drop=True),
            retention=PRIMARY_RETENTION,
            seed=0,
            draws=800,
        )

    man = pd.read_csv(MANIFEST)
    primary = man.loc[man["panel_role"].astype(str).eq("primary_new_agency")]
    gate_delta = float(contrast["point"] * 100)
    gate_hi = float(contrast["high"] * 100)
    same_dir = sum(
        1 for v in by_provider.values() if float(v["point"]) < 0
    )
    hard_ok = (
        gate_delta <= -1.0
        and gate_hi < 0
        and same_dir >= 2
        and int(contrast.get("n_cert_reconstruction_failures") or 0) == 0
    )
    verdict = {
        "panel": "p0_07_wave2_independent_confirmation",
        "evidence_type": "sealed_wave2_multi_provider_confirmation",
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases": int(len(cases)),
        "n_providers": int(cases["provider"].nunique()),
        "providers": sorted(cases["provider"].astype(str).unique()),
        "n_contexts_manifest": int(man["context"].nunique()),
        "retention": PRIMARY_RETENTION,
        "tolerance_C": PRIMARY_TOLERANCE_C,
        "contrast_points": gate_delta,
        "ci_low_points": float(contrast["low"] * 100),
        "ci_high_points": gate_hi,
        "n_candidate_cases": contrast.get("n_candidate_cases"),
        "n_cert_reconstruction_failures": contrast.get("n_cert_reconstruction_failures"),
        "selected_reconstruction_failure_rate": contrast.get(
            "selected_reconstruction_failure_rate"
        ),
        "by_provider_points": {
            p: {
                "contrast_points": float(v["point"] * 100),
                "ci_low_points": float(v["low"] * 100),
                "ci_high_points": float(v["high"] * 100),
            }
            for p, v in by_provider.items()
        },
        "providers_same_direction_negative": int(same_dir),
        "predeclared_success_rule_met": bool(hard_ok),
        "freeze_certificate": str((STEP9_FREEZE / "certificate.joblib").relative_to(ROOT)),
        "manifest_sha256": sha256_file(MANIFEST),
        "scored_once": True,
        "n_primary_manifest_networks": int(len(primary)),
        "limitations": [
            "Wave-2 independent confirmation under repaired QA/reconstructability",
            "Do not retune thresholds after this score",
            "Leftover opened-wave ingest was not scored",
        ],
    }
    verdict_path = OUT / "verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2) + "\n")

    sealed["scored"] = True
    sealed["floors_currently_met"] = True
    sealed["score_artifact"] = str(verdict_path.relative_to(ROOT))
    sealed["wave2_manifest_sha256"] = sha256_file(MANIFEST)
    SEAL.write_text(json.dumps(sealed, indent=2) + "\n")

    print(json.dumps(verdict, indent=2))
    return [cases_path, cert_path, verdict_path, OUT / "wave2_frontiers.csv"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unseal-score", action="store_true")
    args = parser.parse_args()
    if not args.unseal_score:
        raise SystemExit("refusing to score without --unseal-score")
    run_fail_closed(
        "P0-07 wave-2 independent confirmation single score",
        score,
        inputs=[SEAL, MANIFEST, STEP9_FREEZE / "certificate.joblib"],
    )


if __name__ == "__main__":
    main()
