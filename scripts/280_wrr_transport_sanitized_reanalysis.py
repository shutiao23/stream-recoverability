#!/usr/bin/env python3
"""P0-06: rebuild+score primary transport panel from sanitized networks_qc panels.

Writes amendments/p0_06_corrected_reanalysis/transport_* only.
Does not overwrite p0_07b_multi_agency_transport/ or multi_agency_seal.json.
Quality-checked gate is computed inside the primary panel only (F03).
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
from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP9_FREEZE,
)
from stream_recoverability.experiments.v17_fitness.policies import attach_policy_errors  # noqa: E402

READY = ROOT / "results" / "wrr_submission_ready"
MANIFEST = READY / "multi_agency_inputs_manifest.csv"
SAN_ROOT = READY / "amendments" / "p0_02_sanitized_panels" / "panels"
OUT = READY / "amendments" / "p0_06_corrected_reanalysis"
PRIMARY_RETENTION = 0.70
TEMP_C_MIN, TEMP_C_MAX = -5.0, 50.0
USGS_NODATA = -999999.0
MIN_STATIONS, MIN_YEARS = 2, 4
DELTA_POINTS = -1.0


def _sanitized_path(input_path: str) -> Path:
    rel = Path(str(input_path))
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "results" and parts[1] == "wrr_submission_ready":
        rel = Path(*parts[2:])
    path = SAN_ROOT / rel
    if path.is_file():
        return path
    # Fallback to original path with inline quarantine.
    return ROOT / str(input_path)


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


def _quarantine(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for col in out.columns:
        values = pd.to_numeric(out[col], errors="coerce")
        values = values.mask(values.eq(USGS_NODATA) | (values < TEMP_C_MIN) | (values > TEMP_C_MAX))
        out[col] = values
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(MANIFEST)
    primary = manifest.loc[manifest["panel_role"].astype(str).eq("primary_new_agency")].copy()

    import stream_recoverability.experiments.v17_fitness.cases as cases_mod

    panels: dict[str, pd.DataFrame] = {}

    def load(network_id: str, source_root: str = "") -> pd.DataFrame:
        if network_id in panels:
            return panels[network_id]
        row = primary.loc[primary.network_id.astype(str).eq(str(network_id))]
        if row.empty:
            raise FileNotFoundError(network_id)
        path = _sanitized_path(str(row.iloc[0].input_path))
        panel = _quarantine(read_temperature_panel(str(path)))
        panel.columns = [str(c) for c in panel.columns]
        panels[network_id] = panel
        return panel

    cases_mod.load_network_panel = load  # type: ignore[attr-defined]

    frames: list[pd.DataFrame] = []
    meta_rows: list[dict[str, object]] = []
    for row in primary.itertuples():
        network_id = str(row.network_id)
        try:
            panel = load(network_id)
        except FileNotFoundError:
            continue
        eligible: list[str] = []
        for station_id in str(row.station_ids_ge4).split(";"):
            station_id = str(station_id).strip()
            if not station_id or station_id not in panel.columns:
                continue
            years = _complete_years(panel[station_id])
            meta_rows.append(
                {
                    "network_id": network_id,
                    "provider": str(row.provider),
                    "station_id": station_id,
                    "quality_assurance": str(row.quality_assurance),
                    "n_complete_years": len(years),
                    "eligible_ge4": len(years) >= MIN_YEARS,
                }
            )
            if len(years) < MIN_YEARS:
                continue
            eligible.append(station_id)
            job = {
                "network_id": network_id,
                "station_id": station_id,
                "provider": str(row.provider),
                "source_root": "transport_sanitized",
                "split_role": "corrected_reanalysis_sanitized",
                "regulation_status": "unknown",
                "complete_years": years,
                "fit_protocol": "leave_one_year_out",
            }
            frame = build_station_cases(job)
            if not frame.empty:
                frame["quality_assurance"] = str(row.quality_assurance)
                frames.append(frame)
                print(network_id, station_id, len(frame), flush=True)
        _ = eligible

    roster = pd.DataFrame(meta_rows)
    roster.to_csv(OUT / "transport_rebuild_roster.csv", index=False)
    ok_nets = set(
        roster.loc[roster["eligible_ge4"]]
        .groupby("network_id")["station_id"]
        .nunique()
        .loc[lambda s: s >= MIN_STATIONS]
        .index.astype(str)
    )
    if not frames:
        raise RuntimeError("no transport cases built")
    cases = pd.concat(frames, ignore_index=True)
    cases = cases.loc[cases["network_id"].astype(str).isin(ok_nets)].reset_index(drop=True)
    cases = attach_policy_errors(cases)
    cases.to_parquet(OUT / "transport_sanitized_cases.parquet", index=False)

    model = joblib.load(STEP9_FREEZE / "certificate.joblib")
    certificates = model.apply(cases)
    certificates.to_parquet(OUT / "transport_sanitized_certificates.parquet", index=False)

    def contrast(mask: pd.Series) -> dict | None:
        block = cases.loc[mask]
        if len(block) < 200:
            return {
                "n_cases": int(len(block)),
                "n_networks": int(block["network_id"].nunique()),
                "below_floor": True,
            }
        sub = certificates.loc[block.index]
        stat = operating_point_contrast(
            block.reset_index(drop=True),
            sub.reset_index(drop=True),
            retention=PRIMARY_RETENTION,
            seed=0,
            draws=800,
        )
        return {
            "n_cases": int(len(block)),
            "n_networks": int(block["network_id"].nunique()),
            "n_stations": int(block["station_id"].nunique()),
            "contrast_points": float(stat["point"] * 100),
            "ci_low_points": float(stat["low"] * 100),
            "ci_high_points": float(stat["high"] * 100),
            "n_cert_reconstruction_failures": stat.get("n_cert_reconstruction_failures"),
            "selected_reconstruction_failure_rate": stat.get("selected_reconstruction_failure_rate"),
            "below_floor": False,
        }

    pooled = contrast(pd.Series(True, index=cases.index))
    qc = contrast(cases["quality_assurance"].astype(str).eq("quality_checked"))
    by_provider = {
        str(provider): contrast(cases["provider"].astype(str).eq(str(provider)))
        for provider in sorted(cases["provider"].astype(str).unique())
    }

    def gate(block: dict | None) -> bool:
        return bool(
            block
            and not block.get("below_floor")
            and float(block["contrast_points"]) <= DELTA_POINTS
            and float(block["ci_high_points"]) < 0
        )

    same_direction = sum(
        1
        for provider, block in by_provider.items()
        if block and not block.get("below_floor") and float(block["contrast_points"]) < 0
    )
    supported = bool(gate(pooled) and gate(qc) and same_direction >= 2)

    verdict = {
        "panel": "transport_primary_sanitized_corrected_reanalysis",
        "evidence_type": "corrected_reanalysis_opened_panel",
        "may_enter_abstract_or_conclusions": False,
        "label": "[pending — 探索期数据，不可写入结论]",
        "primary_only": True,
        "n_networks": int(cases["network_id"].nunique()),
        "n_stations": int(cases["station_id"].nunique()),
        "n_cases": int(len(cases)),
        "retention": PRIMARY_RETENTION,
        "tolerance_C": PRIMARY_TOLERANCE_C,
        "pooled_primary": pooled,
        "quality_checked_primary_only": qc,
        "by_provider": by_provider,
        "providers_same_direction": same_direction,
        "predeclared_transport_supported": supported,
        "historical_seal_untouched": True,
        "freeze_certificate": str((STEP9_FREEZE / "certificate.joblib").relative_to(ROOT)),
        "note": (
            "Secondary NVE excluded. Quality-checked stratum is primary-panel only. "
            "Not a first confirmation."
        ),
    }
    (OUT / "transport_sanitized_verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
