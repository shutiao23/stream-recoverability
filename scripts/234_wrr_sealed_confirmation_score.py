#!/usr/bin/env python3
"""P0-07: single sealed score of the frozen Certificate on never-used USGS networks.

Verifies confirmation_seal.json + confirmation_inputs_manifest.csv, builds cases
from sealed daily panels only, applies the frozen v17 certificate once, and
writes a verdict. Refuses if already scored or if seal hashes drifted.
"""

from __future__ import annotations

import argparse
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

READY = ROOT / "results" / "wrr_submission_ready"
SEAL = READY / "confirmation_seal.json"
MANIFEST = READY / "confirmation_inputs_manifest.csv"
OUT = READY / "p0_07_sealed_confirmation"
PRIMARY_RETENTION = 0.70


def _load_sealed_panel(network_id: str, source_root: str) -> pd.DataFrame:
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


def _complete_years_from_series(series: pd.Series) -> list[int]:
    s = pd.to_numeric(series, errors="coerce")
    years = []
    for year, block in s.groupby(s.index.year):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(int(year))
    return years


def verify_seal() -> dict:
    if not SEAL.is_file() or not MANIFEST.is_file():
        raise FileNotFoundError("missing confirmation seal or manifest")
    sealed = json.loads(SEAL.read_text())
    if sealed.get("scored"):
        raise RuntimeError("confirmation already scored; refuse to re-score")
    if sha256_file(MANIFEST) != sealed["manifest_sha256"]:
        raise RuntimeError("manifest sha256 drift")
    freeze = READY / "P0_06_method_freeze.json"
    if sha256_file(freeze) != sealed["freeze_sha256"]:
        raise RuntimeError("freeze sha256 drift")
    if int(sealed.get("n_networks", 0)) < 30:
        raise RuntimeError("sealed panel below design floor of 30 networks")
    return sealed


def build_cases() -> pd.DataFrame:
    import stream_recoverability.experiments.v17_fitness.cases as cases_mod

    cases_mod.load_network_panel = _load_sealed_panel  # type: ignore[attr-defined]
    manifest = pd.read_csv(MANIFEST)
    frames = []
    for row in manifest.itertuples():
        panel = _load_sealed_panel(str(row.network_id), "confirmation_external")
        for station_id in str(row.station_ids_ge4).split(";"):
            if not station_id or station_id not in panel.columns:
                continue
            years = _complete_years_from_series(pd.to_numeric(panel[station_id], errors="coerce"))
            if len(years) < 4:
                continue
            job = {
                "network_id": str(row.network_id),
                "station_id": station_id,
                "provider": "usgs",
                "source_root": "confirmation_external",
                "split_role": "sealed_confirmation",
                "regulation_status": "unknown",
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
            }
            frame = build_station_cases(job)
            if not frame.empty:
                frames.append(frame)
                print(row.network_id, station_id, len(frame), flush=True)
    if not frames:
        raise RuntimeError("no cases built from sealed panel")
    return pd.concat(frames, ignore_index=True)


def score(directory: Path, manifest) -> list[Path]:
    sealed = verify_seal()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    cases = attach_policy_errors(cases)
    cases_path = OUT / "sealed_cases.parquet"
    cases.to_parquet(cases_path, index=False)

    model = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(cases)
    cert_path = OUT / "sealed_certificates.parquet"
    certificates.to_parquet(cert_path, index=False)

    frontiers = all_frontiers(cases, certificates)
    frontiers.to_csv(OUT / "frontiers.csv", index=False)
    contrast = operating_point_contrast(cases, certificates, retention=PRIMARY_RETENTION, seed=0)
    by_arm = {}
    for arm, block in cases.groupby("arm"):
        sub = certificates.loc[block.index]
        if len(block) < 200:
            continue
        by_arm[str(arm)] = operating_point_contrast(
            block.reset_index(drop=True),
            sub.reset_index(drop=True),
            retention=PRIMARY_RETENTION,
            seed=0,
            draws=800,
        )

    verdict = {
        "panel": "sealed_never_used_usgs_huc4_networks",
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases": int(len(cases)),
        "n_huc2_contexts": int(sealed.get("n_huc2_contexts", 0)),
        "retention": PRIMARY_RETENTION,
        "tolerance_C": PRIMARY_TOLERANCE_C,
        "contrast_points": float(contrast["point"] * 100),
        "ci_low_points": float(contrast["low"] * 100),
        "ci_high_points": float(contrast["high"] * 100),
        "by_arm_points": {
            arm: {
                "contrast_points": float(val["point"] * 100),
                "ci_low_points": float(val["low"] * 100),
                "ci_high_points": float(val["high"] * 100),
            }
            for arm, val in by_arm.items()
        },
        "freeze_certificate": str((STEP9_FREEZE / "certificate.joblib").relative_to(ROOT)),
        "scored_once": True,
        "evidence_type": "sealed_confirmation_single_provider_usgs",
        "limitations": [
            "USGS-only; multi-agency contexts still pending",
            "Provisional HUC4 networks, not agency-defined river systems",
            "Do not retune thresholds after this score",
        ],
    }
    verdict_path = OUT / "verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2) + "\n")

    sealed["scored"] = True
    sealed["score_artifact"] = str(verdict_path.relative_to(ROOT))
    SEAL.write_text(json.dumps(sealed, indent=2) + "\n")

    # claim registry note
    for path in (cases_path, cert_path, verdict_path, OUT / "frontiers.csv"):
        (directory / path.name).write_bytes(path.read_bytes())
    print(json.dumps(verdict, indent=2))
    return [directory / p.name for p in (cases_path, cert_path, verdict_path)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unseal-score", action="store_true", help="run the single sealed score")
    args = parser.parse_args()
    if not args.unseal_score:
        raise SystemExit("refusing to score without --unseal-score")
    run_fail_closed(
        "P0-07 sealed confirmation single score",
        score,
        inputs=[SEAL, MANIFEST, STEP9_FREEZE / "certificate.joblib"],
    )


if __name__ == "__main__":
    main()
