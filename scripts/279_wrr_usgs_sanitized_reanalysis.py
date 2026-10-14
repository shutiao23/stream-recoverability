#!/usr/bin/env python3
"""P0-06: rebuild+score USGS confirmation from sanitized daily panels.

Writes amendments/p0_06_corrected_reanalysis/usgs_sanitized_* only.
Does not overwrite p0_07_sealed_confirmation/ or confirmation_seal.json.
Evidence type: corrected_reanalysis_opened_panel (not first confirmation).
"""

from __future__ import annotations

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

READY = ROOT / "results" / "wrr_submission_ready"
MANIFEST = READY / "confirmation_inputs_manifest.csv"
SAN_ROOT = READY / "amendments" / "p0_02_sanitized_panels" / "panels"
OUT = READY / "amendments" / "p0_06_corrected_reanalysis"
PRIMARY_RETENTION = 0.70
TEMP_C_MIN = -5.0
TEMP_C_MAX = 50.0
USGS_NODATA = -999999.0
MIN_STATIONS = 2
MIN_YEARS = 4


def _sanitized_path(input_path: str) -> Path:
    rel = Path(str(input_path))
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "results" and parts[1] == "wrr_submission_ready":
        rel = Path(*parts[2:])
    return SAN_ROOT / rel


def _complete_years(series: pd.Series) -> list[int]:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    values = np.where(np.isfinite(values) & (values == USGS_NODATA), np.nan, values)
    values = np.where(
        np.isfinite(values) & ((values < TEMP_C_MIN) | (values > TEMP_C_MAX)),
        np.nan,
        values,
    )
    s = pd.Series(values, index=series.index)
    years: list[int] = []
    for year, block in s.groupby(s.index.year):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(int(year))
    return years


def _load_panel(network_id: str, source_root: str = "") -> pd.DataFrame:
    manifest = pd.read_csv(MANIFEST)
    row = manifest.loc[manifest.network_id.astype(str).eq(str(network_id))]
    if row.empty:
        raise FileNotFoundError(network_id)
    path = _sanitized_path(str(row.iloc[0].input_path))
    if not path.is_file():
        raise FileNotFoundError(path)
    panel = read_temperature_panel(str(path))
    panel.columns = [str(c) for c in panel.columns]
    # Re-apply quarantine in case sanitize copies drift.
    for col in panel.columns:
        values = pd.to_numeric(panel[col], errors="coerce")
        values = values.mask(values.eq(USGS_NODATA) | (values < TEMP_C_MIN) | (values > TEMP_C_MAX))
        panel[col] = values
    return panel


def build_cases() -> pd.DataFrame:
    import stream_recoverability.experiments.v17_fitness.cases as cases_mod

    cases_mod.load_network_panel = _load_panel  # type: ignore[attr-defined]
    manifest = pd.read_csv(MANIFEST)
    frames: list[pd.DataFrame] = []
    roster_rows: list[dict[str, object]] = []
    for row in manifest.itertuples():
        network_id = str(row.network_id)
        try:
            panel = _load_panel(network_id)
        except FileNotFoundError:
            continue
        eligible_stations: list[str] = []
        for station_id in str(row.station_ids_ge4).split(";"):
            station_id = str(station_id).strip()
            if not station_id or station_id not in panel.columns:
                continue
            years = _complete_years(panel[station_id])
            roster_rows.append(
                {
                    "network_id": network_id,
                    "station_id": station_id,
                    "n_complete_years": len(years),
                    "eligible_ge4": len(years) >= MIN_YEARS,
                }
            )
            if len(years) < MIN_YEARS:
                continue
            eligible_stations.append(station_id)
            job = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": "usgs",
                "source_root": "confirmation_external",
                "split_role": "corrected_reanalysis_sanitized",
                "regulation_status": "unknown",
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
            }
            frame = build_station_cases(job)
            if not frame.empty:
                frames.append(frame)
                print(network_id, station_id, len(frame), flush=True)
        # Networks with <2 eligible stations contribute no donor-capable geometry;
        # keep their cases if already built (single-station networks still have
        # climatology/interp) but flag in roster.
        _ = eligible_stations
    pd.DataFrame(roster_rows).to_csv(OUT / "usgs_rebuild_roster.csv", index=False)
    if not frames:
        raise RuntimeError("no cases built from sanitized USGS panels")
    cases = pd.concat(frames, ignore_index=True)
    # Keep only networks with ≥2 eligible stations (design floor for donors).
    roster = pd.DataFrame(roster_rows)
    ok_nets = (
        roster.loc[roster["eligible_ge4"]]
        .groupby("network_id")["station_id"]
        .nunique()
    )
    ok_nets = set(ok_nets.loc[ok_nets >= MIN_STATIONS].index.astype(str))
    cases = cases.loc[cases["network_id"].astype(str).isin(ok_nets)].reset_index(drop=True)
    return cases


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    cases = attach_policy_errors(cases)
    cases_path = OUT / "usgs_sanitized_cases.parquet"
    cases.to_parquet(cases_path, index=False)

    model = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(cases)
    cert_path = OUT / "usgs_sanitized_certificates.parquet"
    certificates.to_parquet(cert_path, index=False)

    frontiers = all_frontiers(cases, certificates)
    frontiers.to_csv(OUT / "usgs_sanitized_frontiers.csv", index=False)

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

    cert_err = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
    truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce")
    verdict = {
        "panel": "usgs_sanitized_corrected_reanalysis",
        "evidence_type": "corrected_reanalysis_opened_panel",
        "may_enter_abstract_or_conclusions": False,
        "label": "[pending — 探索期数据，不可写入结论]",
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases": int(len(cases)),
        "retention": PRIMARY_RETENTION,
        "tolerance_C": PRIMARY_TOLERANCE_C,
        "contrast_points": float(contrast["point"] * 100),
        "ci_low_points": float(contrast["low"] * 100),
        "ci_high_points": float(contrast["high"] * 100),
        "n_candidate_cases": contrast.get("n_candidate_cases"),
        "n_cert_reconstruction_failures": contrast.get("n_cert_reconstruction_failures"),
        "selected_reconstruction_failure_rate": contrast.get(
            "selected_reconstruction_failure_rate"
        ),
        "n_implausible_truth_remaining": int(
            ((truth < TEMP_C_MIN) | (truth > TEMP_C_MAX) | ~np.isfinite(truth)).sum()
        ),
        "n_cert_error_finite": int(cert_err.notna().sum()),
        "by_arm_points": {
            arm: {
                "contrast_points": float(val["point"] * 100),
                "ci_low_points": float(val["low"] * 100),
                "ci_high_points": float(val["high"] * 100),
            }
            for arm, val in by_arm.items()
        },
        "freeze_certificate": str((STEP9_FREEZE / "certificate.joblib").relative_to(ROOT)),
        "input_panels": str(SAN_ROOT.relative_to(ROOT)),
        "historical_seal_untouched": True,
        "predeclared_gate_delta_le_minus_1_and_ci_high_lt_0": bool(
            float(contrast["point"] * 100) <= -1.0 and float(contrast["high"] * 100) < 0
        ),
        "limitations": [
            "Corrected reanalysis of an opened panel; not a first confirmation",
            "USGS-only; full rebuild from sanitized panels required donor retrain",
            "Do not retune thresholds after this score",
        ],
    }
    verdict_path = OUT / "usgs_sanitized_verdict.json"
    verdict_path.write_text(json.dumps(verdict, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
