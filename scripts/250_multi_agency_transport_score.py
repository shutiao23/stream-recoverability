#!/usr/bin/env python3
"""P0-07 extension: single sealed score of the frozen Certificate on the
multi-agency transport panel.

Verify the seal, build cases from the sealed daily panels only, apply the frozen
v17 certificate once, evaluate the pre-declared transport rule, write a verdict,
and mark the seal scored. Refuses to run twice or on drifted hashes.
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
SEAL = READY / "multi_agency_seal.json"
MANIFEST = READY / "multi_agency_inputs_manifest.csv"
OUT = READY / "p0_07b_multi_agency_transport"
PRIMARY_RETENTION = 0.70
DELTA_POINTS = -1.0  # pre-declared in MULTI_AGENCY_TRANSPORT_PROTOCOL.md


def _load_sealed_panel(network_id: str, _source_root: str) -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST, dtype=str)
    row = manifest.loc[manifest.network_id.eq(str(network_id))]
    if row.empty:
        raise FileNotFoundError(network_id)
    path = ROOT / str(row.iloc[0].input_path)
    if sha256_file(path) != str(row.iloc[0].sha256):
        raise RuntimeError(f"hash drift for {network_id}")
    panel = read_temperature_panel(str(path))
    panel.columns = [str(c) for c in panel.columns]
    return panel


TEMP_C_MIN = -5.0
TEMP_C_MAX = 50.0
USGS_NODATA = -999999.0


def _complete_years_from_series(series: pd.Series) -> list[int]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    values = np.where(np.isfinite(values) & (values == USGS_NODATA), np.nan, values)
    values = np.where(
        np.isfinite(values) & ((values < TEMP_C_MIN) | (values > TEMP_C_MAX)),
        np.nan,
        values,
    )
    series = pd.Series(values, index=series.index)
    years: list[int] = []
    for year, block in series.groupby(series.index.year):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(int(year))
    return years


def verify_seal() -> dict:
    if not SEAL.is_file() or not MANIFEST.is_file():
        raise FileNotFoundError("missing multi-agency seal or manifest")
    sealed = json.loads(SEAL.read_text())
    if sealed.get("scored"):
        raise RuntimeError("transport panel already scored; refuse to re-score")
    if sha256_file(MANIFEST) != sealed["manifest_sha256"]:
        raise RuntimeError("manifest sha256 drift")
    if sha256_file(READY / "P0_06_method_freeze.json") != sealed["freeze_sha256"]:
        raise RuntimeError("freeze sha256 drift")
    if sha256_file(READY / "MULTI_AGENCY_TRANSPORT_PROTOCOL.md") != sealed["protocol_sha256"]:
        raise RuntimeError("protocol sha256 drift")
    return sealed


def build_cases() -> pd.DataFrame:
    import stream_recoverability.experiments.v17_fitness.cases as cases_mod

    cases_mod.load_network_panel = _load_sealed_panel  # type: ignore[attr-defined]
    manifest = pd.read_csv(MANIFEST, dtype=str)
    frames = []
    for row in manifest.itertuples():
        panel = _load_sealed_panel(str(row.network_id), "multi_agency_transport")
        for station_id in str(row.station_ids_ge4).split(";"):
            if not station_id or station_id not in panel.columns:
                continue
            years = _complete_years_from_series(panel[station_id])
            if len(years) < 4:
                continue
            job = {
                "network_id": str(row.network_id),
                "station_id": station_id,
                "provider": str(row.provider),
                "source_root": "multi_agency_transport",
                "split_role": "sealed_transport",
                "regulation_status": "unknown",
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
            }
            frame = build_station_cases(job)
            if not frame.empty:
                frames.append(frame)
                print(row.network_id, station_id, len(frame), flush=True)
    if not frames:
        raise RuntimeError("no cases built from sealed transport panel")
    return pd.concat(frames, ignore_index=True)


def score(directory: Path, _manifest) -> list[Path]:
    sealed = verify_seal()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    cases = attach_policy_errors(cases)
    cases_path = OUT / "transport_cases.parquet"
    cases.to_parquet(cases_path, index=False)

    model = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(cases)
    cert_path = OUT / "transport_certificates.parquet"
    certificates.to_parquet(cert_path, index=False)

    all_frontiers(cases, certificates).to_csv(OUT / "frontiers.csv", index=False)

    pooled = operating_point_contrast(cases, certificates, retention=PRIMARY_RETENTION, seed=0)
    by_provider = {}
    for provider, block in cases.groupby("provider"):
        sub = certificates.loc[block.index]
        if len(block) < 200:
            continue
        by_provider[str(provider)] = operating_point_contrast(
            block.reset_index(drop=True), sub.reset_index(drop=True), retention=PRIMARY_RETENTION, seed=0, draws=800
        )
    manifest = pd.read_csv(MANIFEST, dtype=str).set_index("network_id")
    by_context_frame = cases.merge(
        manifest[["context"]], left_on="network_id", right_index=True, how="left"
    )
    by_context = {}
    for context, block in by_context_frame.groupby("context"):
        sub = certificates.loc[block.index]
        if len(block) < 200:
            continue
        by_context[str(context)] = operating_point_contrast(
            block.reset_index(drop=True),
            sub.reset_index(drop=True),
            retention=PRIMARY_RETENTION,
            seed=0,
            draws=800,
        )
    by_arm = {}
    for arm, block in cases.groupby("arm"):
        sub = certificates.loc[block.index]
        if len(block) < 200:
            continue
        by_arm[str(arm)] = operating_point_contrast(
            block.reset_index(drop=True), sub.reset_index(drop=True), retention=PRIMARY_RETENTION, seed=0, draws=800
        )

    def _contrast(block: pd.DataFrame) -> dict | None:
        if len(block) < 200:
            return None
        sub = certificates.loc[block.index]
        return operating_point_contrast(
            block.reset_index(drop=True), sub.reset_index(drop=True), retention=PRIMARY_RETENTION, seed=0, draws=800
        )

    # Panel role first (Amendment 2026-10-13 / F03): quality strata are defined
    # inside a single panel. Mixing NVE secondary into quality_checked before
    # splitting primary/secondary invalidates the pre-registered gate.
    roles = manifest["panel_role"].astype(str).rename("panel_role").reset_index()
    cases_role = cases.merge(roles, on="network_id", how="left")
    primary_cases = cases_role.loc[
        cases_role["panel_role"].astype(str).eq("primary_new_agency")
    ].copy()
    secondary_cases = cases_role.loc[
        cases_role["panel_role"].astype(str).eq("secondary_development_provider")
    ].copy()
    primary_contrast = _contrast(primary_cases)
    secondary_contrast = _contrast(secondary_cases)
    extended_contrast = _contrast(cases_role)

    assurance = (
        manifest["quality_assurance"].astype(str).str.split(";").explode().rename("quality_assurance").reset_index()
    )
    assurance = assurance.drop_duplicates("network_id")
    # Assurance contrasts on the primary panel only (protocol gate).
    primary_assurance = primary_cases.merge(assurance, on="network_id", how="left")
    by_assurance = {}
    for stratum, block in primary_assurance.groupby("quality_assurance"):
        value = _contrast(block)
        if value is not None:
            by_assurance[str(stratum)] = value

    quality_checked = primary_assurance.loc[
        primary_assurance["quality_assurance"].astype(str).eq("quality_checked")
    ]
    qc_contrast = _contrast(quality_checked)

    point = float(pooled["point"] * 100)
    low = float(pooled["low"] * 100)
    high = float(pooled["high"] * 100)

    def _rule(value: dict | None) -> bool:
        return bool(
            value is not None
            and float(value["point"] * 100) <= DELTA_POINTS
            and float(value["high"] * 100) < 0
        )

    same_direction = sum(
        1
        for provider, value in by_provider.items()
        if provider not in ("nve", "nve_hydapi") and value["point"] < 0
    )
    primary_point = float(primary_contrast["point"] * 100) if primary_contrast else float("nan")
    primary_high = float(primary_contrast["high"] * 100) if primary_contrast else float("nan")
    pooled_supported = bool(
        primary_contrast is not None
        and primary_point <= DELTA_POINTS
        and primary_high < 0
        and same_direction >= 2
    )
    qc_supported = _rule(qc_contrast)
    # Amendment 2 rule 3: pooled and quality-checked-only verdicts must agree.
    supported = bool(pooled_supported and qc_supported)
    strata_disagree = bool(qc_contrast is not None and pooled_supported != qc_supported)
    verdict = {
        "panel": "sealed_multi_agency_transport",
        "status": "scored_once",
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases": int(len(cases)),
        "n_providers": int(cases["provider"].nunique()),
        "providers": sorted(cases["provider"].unique().tolist()),
        "contexts": sorted(by_context),
        "retention": PRIMARY_RETENTION,
        "tolerance_C": PRIMARY_TOLERANCE_C,
        "contrast_points": point,
        "ci_low_points": low,
        "ci_high_points": high,
        "by_provider_points": {
            provider: {
                "contrast_points": float(value["point"] * 100),
                "ci_low_points": float(value["low"] * 100),
                "ci_high_points": float(value["high"] * 100),
                "n_cases": int(value.get("n", 0)),
            }
            for provider, value in by_provider.items()
        },
        "by_context_points": {
            context: {
                "contrast_points": float(value["point"] * 100),
                "ci_low_points": float(value["low"] * 100),
                "ci_high_points": float(value["high"] * 100),
            }
            for context, value in by_context.items()
        },
        "by_arm_points": {
            arm: {
                "contrast_points": float(value["point"] * 100),
                "ci_low_points": float(value["low"] * 100),
                "ci_high_points": float(value["high"] * 100),
            }
            for arm, value in by_arm.items()
        },
        "primary_panel": {
            "definition": "agencies absent from the v17/v18 development programme (Amendment 1/3)",
            "n_networks": int(primary_cases["network_id"].nunique()) if len(primary_cases) else 0,
            "n_cases": int(len(primary_cases)),
            "contrast_points": primary_point,
            "ci_low_points": float(primary_contrast["low"] * 100) if primary_contrast else None,
            "ci_high_points": primary_high,
        },
        "secondary_panel": {
            "definition": "development provider, individually never-used stations (Amendment 3)",
            "providers": sorted(secondary_cases["provider"].unique().tolist()) if len(secondary_cases) else [],
            "n_networks": int(secondary_cases["network_id"].nunique()) if len(secondary_cases) else 0,
            "n_cases": int(len(secondary_cases)),
            "contrast_points": float(secondary_contrast["point"] * 100) if secondary_contrast else None,
            "ci_low_points": float(secondary_contrast["low"] * 100) if secondary_contrast else None,
            "ci_high_points": float(secondary_contrast["high"] * 100) if secondary_contrast else None,
        },
        "extended_panel_points": (
            {
                "contrast_points": float(extended_contrast["point"] * 100),
                "ci_low_points": float(extended_contrast["low"] * 100),
                "ci_high_points": float(extended_contrast["high"] * 100),
                "n_cases": int(len(cases_role)),
                "caveat": "includes a provider that participated in development; primary panel excludes it",
            }
            if extended_contrast is not None
            else None
        ),
        "by_assurance_points": {
            stratum: {
                "contrast_points": float(value["point"] * 100),
                "ci_low_points": float(value["low"] * 100),
                "ci_high_points": float(value["high"] * 100),
            }
            for stratum, value in by_assurance.items()
        },
        "quality_checked_only_points": (
            {
                "contrast_points": float(qc_contrast["point"] * 100),
                "ci_low_points": float(qc_contrast["low"] * 100),
                "ci_high_points": float(qc_contrast["high"] * 100),
                "n_cases": int(len(quality_checked)),
            }
            if qc_contrast is not None
            else None
        ),
        "predeclared_rule": {
            "delta_points": DELTA_POINTS,
            "requires": (
                "delta <= -1.0 pp, 95% network-clustered CI upper bound < 0, >=2 providers same direction; "
                "pooled and quality-checked-only verdicts must agree (Amendment 2)"
            ),
            "providers_same_direction": int(same_direction),
            "pooled_supported": pooled_supported,
            "quality_checked_only_supported": qc_supported,
            "strata_disagree": strata_disagree,
            "transport_supported": supported,
        },
        "freeze_certificate": str((STEP9_FREEZE / "certificate.joblib").relative_to(ROOT)),
        "evidence_type": "sealed_multi_agency_transport_single_score",
        "ordering_disclosure": (
            "Designed and sealed after the USGS confirmation score; a transport test, not a pristine first confirmation."
        ),
        "limitations": [
            "Provider-daily series with provider-specific QC; comparability documented per station, not instrument-audited",
            "Provisional agency-native networks where the agency does not define basins",
            "Post-USGS ordering disclosed; no threshold retuning after this score",
        ],
    }
    verdict_path = OUT / "verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")

    sealed["scored"] = True
    sealed["score_artifact"] = str(verdict_path.relative_to(ROOT))
    sealed["transport_supported"] = supported
    SEAL.write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n")

    for path in (cases_path, cert_path, verdict_path, OUT / "frontiers.csv"):
        (directory / path.name).write_bytes(path.read_bytes())
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return [directory / p.name for p in (cases_path, cert_path, verdict_path, OUT / "frontiers.csv")]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unseal-score", action="store_true")
    args = parser.parse_args()
    if not args.unseal_score:
        raise SystemExit("refusing to score without --unseal-score")
    run_fail_closed(
        "P0-07 multi-agency transport single score",
        score,
        inputs=[SEAL, MANIFEST, STEP9_FREEZE / "certificate.joblib"],
    )


if __name__ == "__main__":
    main()
