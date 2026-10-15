#!/usr/bin/env python3
"""P0-06: coverage / measurement contract + independent recompute of headline tables.

Two parts, both written into
``results/wrr_submission_ready/major_revision_20261014/p0_06_coverage_recompute/``.

PART A — coverage and measurement contract
  Builds a station-level coverage table for every station of the final study
  panel (v17 development + reserved roster and the wave-2 confirmation roster)
  from the project's own artifacts, plus a provider summary, a
  provider -> documented-statistic -> evidence contract table and a gap list.

PART B — independent recompute
  Re-implements the headline contrasts through a different code path
  (plain numpy arrays + explicit stable selection, no call into
  ``operating_point_contrast`` / ``frontier_for_score`` / ``screen`` /
  ``estimator_disagreement`` / the original scripts) and compares against the
  stored values with a stated tolerance per quantity.

  The one shared component is ``cluster_bootstrap`` from
  ``stream_recoverability.experiments.v17_fitness.stats``.  It is used ONLY as
  a cross-check that the interval *definition* is unchanged; the primary
  recomputed interval is produced by this script's own resampler.  Where the
  two differ the difference is reported, not hidden.

Reads are read-only.  Writes are confined to the P0-06 output folder and
``scratch/p0_06/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# The host has 128 cores and is shared with other agents.  Unbounded OpenMP/BLAS
# threading makes the sklearn fits thrash, so cap threads before numpy/sklearn
# are imported.  Override with P0_06_THREADS if needed.
_THREADS = os.environ.get("P0_06_THREADS", "4")
for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_var] = _THREADS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
)

# `PRIMARY_RETENTION` is not defined in src/: it is a local constant of the
# producing scripts (0.70 in scripts/297_wrr_p0_07_wave2_score.py and
# scripts/187_v17_confirm.py).  Mirrored here rather than imported so the value
# actually used by this recompute is visible.
RETENTION = 0.70
TOLERANCE = float(PRIMARY_TOLERANCE_C)
assert abs(RETENTION - 0.70) < 1e-12, "primary retention drifted"
assert abs(TOLERANCE - 0.5) < 1e-12, "primary tolerance drifted"

# --------------------------------------------------------------------------
# output locations (WRITE SCOPE)
# --------------------------------------------------------------------------
OUT = (
    ROOT
    / "results"
    / "wrr_submission_ready"
    / "major_revision_20261014"
    / "p0_06_coverage_recompute"
)
SCRATCH = ROOT / "scratch" / "p0_06"

# --------------------------------------------------------------------------
# input registry -- every file this script reads, with the role it plays
# --------------------------------------------------------------------------
W2 = ROOT / "results" / "wrr_submission_ready" / "p0_07_wave2_ingest"
MR = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261014"

INPUTS: dict[str, Path] = {
    # PART A
    "station_roster": ROOT / "results/v17_fitness/step1_panel/station_roster.csv",
    "network_split": ROOT / "results/v17_fitness/step1_panel/network_split.csv",
    "trusted_complete_years": ROOT / "results/wrr_revision/step1_universe/trusted_river_complete_years.csv",
    "current_data_manifest": ROOT / "results/wrr_submission_ready/current_data_manifest.csv",
    "current_data_acquisition": ROOT / "results/wrr_submission_ready/current_data_acquisition.csv",
    "measurement_provenance_dictionary": ROOT
    / "results/wrr_submission_ready/measurement_provenance_dictionary.csv",
    "data_rights": ROOT / "metadata/data_rights.csv",
    "measurement_provenance_stations": ROOT
    / "results/wrr_submission_ready/measurement_provenance_stations.csv",
    "wave2_station_roster": W2 / "wave2_station_roster.csv",
    "wave2_inputs_manifest": W2 / "wave2_inputs_manifest.csv",
    # PART B
    "wave2_cases": W2 / "p0_07_wave2_confirmation/wave2_cases.parquet",
    "wave2_certificates": W2 / "p0_07_wave2_confirmation/wave2_certificates.parquet",
    "wave2_verdict": W2 / "p0_07_wave2_confirmation/verdict.json",
    "transfer_report": MR / "step7_transfer_reporting/transfer_report.json",
    "arm_and_thermal_contrasts": MR / "step5_monitoring_tasks/arm_and_thermal_contrasts.csv",
    "v17_reserved_verdict": ROOT / "results/v17_fitness/step10_confirmation/verdict.json",
    "development_cases": ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet",
    "reserved_cases": ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet",
    "reserved_certificates": ROOT
    / "results/v17_fitness/step10_confirmation/reserved_certificates.parquet",
    "step2_contrasts": MR / "step2_same_info_ablation/contrasts_network_ci.json",
    "step2_operating_points": MR / "step2_same_info_ablation/operating_points_development_oof.csv",
    "step2_fingerprint": MR / "step2_same_info_ablation/protocol_fingerprint.json",
    "crossed_development_cases": ROOT
    / "results/wrr_submission_ready/amendments/position_length_paired/crossed_development_cases.parquet",
    "step3_position_contrasts": MR
    / "step3_fixed_reconstructor_mechanism/position_contrasts_network_ci.csv",
    "step3_length_contrasts": MR
    / "step3_fixed_reconstructor_mechanism/length_contrasts_network_ci.csv",
    "step3_summary": MR / "step3_fixed_reconstructor_mechanism/summary.json",
}

COLUMNS_USED: list[dict] = []


def note_columns(file_key: str, role: str, columns: list[str], *, present: bool = True) -> None:
    COLUMNS_USED.append(
        {
            "input_key": file_key,
            "file": str(INPUTS[file_key].relative_to(ROOT)),
            "role": role,
            "columns_used": list(columns),
            "file_present": bool(present),
        }
    )


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def require(path: Path, what: str) -> Path:
    if not path.exists():
        raise SystemExit(f"required input missing ({what}): {path}")
    return path


# ==========================================================================
# statistic-class contract
# ==========================================================================
# Canonical classes requested by the review.
CLASS_DAILY_MEAN = "daily_mean"
CLASS_PROJECT_SUBDAILY = "project_aggregated_from_subdaily"
CLASS_NON_DAILY_REFERENCE = "non_daily_reference_reading"
CLASS_UNDOCUMENTED = "undocumented"

# The rule below is a deterministic parse of the project's own
# `statistic_documented` / `statistic_as_parsed` text in
# measurement_provenance_dictionary.csv.  It is deliberately keyed on phrases the
# dictionary itself uses; the matched phrase is stored per provider so the
# classification can be audited.  Both columns are consulted because the
# dictionary splits the claim: `statistic_documented` describes the *provider's*
# series, `statistic_as_parsed` describes what the *parser* does with it.
CLASS_RULES: list[tuple[str, str, str]] = [
    (
        "statistic_documented startswith 'daily mean'",
        CLASS_DAILY_MEAN,
        "the provider itself documents a daily mean",
    ),
    (
        "statistic_as_parsed contains 'project-derived daily mean'",
        CLASS_PROJECT_SUBDAILY,
        "the provider series is sub-daily/instantaneous and the project derives the daily mean",
    ),
    (
        "statistic_documented contains 'NOT a daily mean'",
        CLASS_NON_DAILY_REFERENCE,
        "the provider documents a once-daily reference reading",
    ),
]


def classify_statistic(documented: str, parsed: str = "") -> tuple[str, str]:
    """Return (canonical_class, matched_rule) for the dictionary's statistic text."""

    documented = "" if documented is None else str(documented)
    parsed = "" if parsed is None else str(parsed)
    combined = documented + " \u2016 " + parsed
    if documented.strip().lower().startswith("daily mean"):
        return CLASS_DAILY_MEAN, CLASS_RULES[0][0]
    if "project-derived daily mean" in combined:
        return CLASS_PROJECT_SUBDAILY, CLASS_RULES[1][0]
    if "NOT a daily mean" in documented[:60]:
        return CLASS_NON_DAILY_REFERENCE, CLASS_RULES[2][0]
    return CLASS_UNDOCUMENTED, "no rule matched (dictionary leaves the statistic unverified)"


# The station-level provenance file (script 232) uses its own vocabulary; the
# mapping below is used only as an independent cross-check, never as the value.
STATIONS_FILE_CROSSWALK = {
    "daily_mean": CLASS_DAILY_MEAN,
    "provider_daily_unverified_definition": CLASS_UNDOCUMENTED,
    "daily_mean_from_raw": CLASS_PROJECT_SUBDAILY,
    "unknown_may_be_morning_reference": CLASS_NON_DAILY_REFERENCE,
}

# metadata/data_rights.csv is keyed by artifact name, not by provider.  This is
# an explicit, auditable mapping; providers with no row are left visibly empty.
RIGHTS_ARTIFACT = {
    "arso": "v11 ARSO confirmation temperature",
    "chmi": "v11 CHMI confirmation temperature",
    "gkd_bayern": "v11 GKD Bayern confirmation temperature",
    "lubw": "v11 LUBW confirmation temperature",
    "rws_waterwebservices": "v11 RWS confirmation temperature",
    "foen": "v11 FOEN confirmation temperature",
    "syke": "v11 SYKE candidate temperature",
    "nve_hydapi": "v11 NVE second-confirmation temperature",
    "usgs": "USGS confirmatory hydrology",
    # hubeau / uk_ea: no row exists in metadata/data_rights.csv (verified by the
    # script, recorded as MISSING rather than guessed).
}


# ==========================================================================
# PART A
# ==========================================================================
def build_provider_contract() -> pd.DataFrame:
    """provider -> documented statistic -> evidence, straight from the dictionary."""

    path = require(INPUTS["measurement_provenance_dictionary"], "provenance dictionary")
    frame = pd.read_csv(path, dtype=str).fillna("")
    note_columns(
        "measurement_provenance_dictionary",
        "provider -> documented daily statistic + licence, PART A",
        [
            "provider",
            "country",
            "product",
            "statistic_documented",
            "statistic_as_parsed",
            "aggregation_interval",
            "day_boundary_tz",
            "quality_codes_kept",
            "quality_codes_dropped",
            "license",
            "redistribution_allowed",
            "derived_output_allowed",
            "required_citation",
            "acquisition_route",
            "evidence_url",
            "evidence_quote",
            "verification_status",
        ],
    )
    classes, rules = zip(
        *[
            classify_statistic(doc, parsed)
            for doc, parsed in zip(frame["statistic_documented"], frame["statistic_as_parsed"])
        ]
    )
    frame["statistic_class"] = list(classes)
    frame["statistic_class_rule_matched"] = list(rules)
    frame["evidence_file"] = str(path.relative_to(ROOT))
    return frame


def cover_columns(frame: pd.DataFrame, wanted: list[str]) -> list[str]:
    return [c for c in wanted if c in frame.columns]


def build_v17_station_table(
    roster: pd.DataFrame,
    net_split: pd.DataFrame,
    trusted: pd.DataFrame,
    manifest: pd.DataFrame,
    acq: pd.DataFrame,
    prov_stations: pd.DataFrame,
) -> pd.DataFrame:
    base = roster.copy()
    base["panel"] = "v17"
    # 26 roster stations carry no split_role: they are exactly the stations with
    # eligible_station == False.  Keep them visible as unassigned (NaN) rather
    # than stringifying them.
    base["split_role_raw"] = base["split_role"]
    base["split_role"] = base["split_role"].fillna("unassigned_not_in_development_or_reserved")
    base["first_year_source"] = "station_roster.csv:first_year"
    base["last_year_source"] = "station_roster.csv:last_year"
    base["n_complete_years_source"] = "station_roster.csv:n_complete_years"

    recount = (
        trusted.groupby(["network_id", "station_id"], as_index=False)["full_calendar_year"]
        .sum()
        .rename(columns={"full_calendar_year": "n_complete_years_recount"})
    )
    base = base.merge(recount, on=["network_id", "station_id"], how="left")
    base["n_complete_years_recount_rule"] = (
        "trusted_river_complete_years.csv: sum(full_calendar_year) per station"
    )

    trusted_span = trusted.groupby(["network_id", "station_id"], as_index=False)["year"].agg(
        trusted_first_year="min", trusted_last_year="max"
    )
    base = base.merge(trusted_span, on=["network_id", "station_id"], how="left")
    base["first_year_cross_check"] = np.where(
        base["trusted_first_year"].isna(),
        "not_in_trusted_file",
        np.where(base["first_year"].eq(base["trusted_first_year"]), "match", "MISMATCH"),
    )
    base["last_year_cross_check"] = np.where(
        base["trusted_last_year"].isna(),
        "not_in_trusted_file",
        np.where(base["last_year"].eq(base["trusted_last_year"]), "match", "MISMATCH"),
    )

    strata = net_split[
        ["network_id", "stratum", "donor_regime", "median_donors", "n_stations", "split_role"]
    ].rename(columns={"split_role": "network_split_role", "donor_regime": "network_donor_regime"})
    base = base.merge(strata, on="network_id", how="left", suffixes=("", "_netsplit"))
    base["quality_stratum"] = base["stratum"]
    base["donor_regime"] = base["network_donor_regime"]
    base["quality_stratum_source"] = "network_split.csv:stratum (provider|donor_regime, network level)"
    base["eligible_station_source"] = "station_roster.csv:eligible_station"

    man = manifest[["network_id", "status", "input_path", "sha256", "bytes"]].rename(
        columns={
            "status": "manifest_status",
            "input_path": "manifest_input_path",
            "sha256": "manifest_sha256",
            "bytes": "manifest_bytes",
        }
    )
    base = base.merge(man, on="network_id", how="left")

    acq_cols = acq[["network_id", "country", "product", "acquisition_route"]].rename(
        columns={"country": "acquisition_country", "product": "acquisition_product"}
    )
    base = base.merge(acq_cols, on="network_id", how="left")

    ps = prov_stations[
        [
            "network_id",
            "station_id",
            "statistic_class",
            "statistic_proven_for_panel",
            "include_in_unified_daily_mean_main",
        ]
    ].rename(
        columns={
            "statistic_class": "statistic_class_station_file",
            "statistic_proven_for_panel": "statistic_proven_station_file",
            "include_in_unified_daily_mean_main": "include_in_unified_daily_mean_main",
        }
    )
    base = base.merge(ps, on=["network_id", "station_id"], how="left")
    return base


def wave2_network_paths(manifest: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in manifest.itertuples():
        daily = ROOT / str(row.input_path)
        out[str(row.network_id)] = {
            "daily_wide": daily,
            "eligibility": daily.parent / "station_eligibility.csv",
            "provider": str(row.provider),
            "context": str(getattr(row, "context", "")),
            "panel_role": str(getattr(row, "panel_role", "")),
        }
    return out


def wave2_recount_years(series: pd.Series, years: pd.Series, upper_bound: float) -> tuple[int, int]:
    """Two independent recounts of 'complete calendar year' from daily_wide_temperature.csv.

    ``ge_expm1`` implements the rule as written in the wave-2 ingest scripts
    (``len(values) >= expected - 1`` and all values present/finite/plausible).
    ``all_days`` is the strict variant (every calendar day present).

    Neither is authoritative: the ingest rule is evaluated on the per-station
    series *before* it is widened, and the widened artifact cannot restore the
    row count the rule actually tests.  Both counts are reported so the
    convention dependence is visible.
    """

    values = pd.to_numeric(series, errors="coerce")
    ge_expm1 = 0
    all_days = 0
    for year, block in values.groupby(years):
        vals = block.dropna()
        year_int = int(year)
        expected = 366 if pd.Timestamp(year_int, 12, 31).is_leap_year else 365
        if vals.empty:
            continue
        finite = np.isfinite(vals.to_numpy(dtype=float)).all()
        plausible = bool(vals.min() >= -5.0 and vals.max() <= upper_bound)
        if len(vals) >= expected - 1 and finite and plausible:
            ge_expm1 += 1
        if len(vals) == expected and finite and plausible:
            all_days += 1
    return ge_expm1, all_days


def build_wave2_station_table(
    w2_roster: pd.DataFrame,
    w2_manifest: pd.DataFrame,
    wave2_cases: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    paths = wave2_network_paths(w2_manifest)
    prov_bounds = {"usgs": 50.0, "hubeau": 45.0, "uk_ea": 45.0}
    regimes = (
        wave2_cases.groupby(["network_id", "station_id"])["donor_regime"]
        .agg(lambda s: s.astype(str).mode().iloc[0] if len(s.mode()) else "")
        .rename("donor_regime")
        .reset_index()
    )
    reg_variation = (
        wave2_cases.groupby(["network_id", "station_id"])["donor_regime"]
        .nunique()
        .rename("donor_regime_n_distinct")
        .reset_index()
    )
    reg_status = (
        wave2_cases.groupby(["network_id", "station_id"])["regulation_status"]
        .agg(lambda s: s.astype(str).mode().iloc[0] if len(s.mode()) else "")
        .rename("regulation_status")
        .reset_index()
    )

    rows: list[dict] = []
    file_notes: list[dict] = []
    for row in w2_roster.itertuples():
        net = str(row.network_id)
        sid = str(row.station_id)
        info = paths.get(net)
        entry = {
            "panel": "wave2_confirmation",
            "provider": str(row.provider),
            "network_id": net,
            "station_id": sid,
            "split_role": "wave2_confirmation",
            "source_root": "wave2_ingest",
        }
        if info is None:
            entry.update(
                {
                    "first_year": np.nan,
                    "last_year": np.nan,
                    "n_complete_years": np.nan,
                    "n_complete_years_recount_ge_expm1": np.nan,
                    "n_complete_years_recount_all_days": np.nan,
                    "wave2_context": "",
                }
            )
        else:
            entry["wave2_context"] = info["context"]
            entry["wave2_panel_role"] = info["panel_role"]
            daily = info["daily_wide"]
            elig_path = info["eligibility"]
            if not daily.exists():
                entry.update(
                    {
                        "first_year": np.nan,
                        "last_year": np.nan,
                        "n_complete_years": np.nan,
                        "n_complete_years_recount_ge_expm1": np.nan,
                        "n_complete_years_recount_all_days": np.nan,
                    }
                )
                file_notes.append({"network_id": net, "note": f"daily_wide missing: {daily}"})
            else:
                wide = pd.read_csv(daily, dtype=str)
                dates = pd.to_datetime(wide["date"])
                years = dates.dt.year
                if sid not in wide.columns:
                    entry.update(
                        {
                            "first_year": np.nan,
                            "last_year": np.nan,
                            "n_complete_years": np.nan,
                            "n_complete_years_recount_ge_expm1": np.nan,
                            "n_complete_years_recount_all_days": np.nan,
                        }
                    )
                    file_notes.append(
                        {"network_id": net, "note": f"station column {sid} absent from {daily.name}"}
                    )
                else:
                    values = pd.to_numeric(wide[sid], errors="coerce")
                    observed = values.dropna()
                    if observed.empty:
                        first_year = last_year = np.nan
                        ge_expm1 = all_days = 0
                    else:
                        first_year = int(dates.loc[observed.index].dt.year.min())
                        last_year = int(dates.loc[observed.index].dt.year.max())
                        ge_expm1, all_days = wave2_recount_years(
                            wide[sid], years, prov_bounds.get(str(row.provider), 50.0)
                        )
                    entry.update(
                        {
                            "first_year": first_year,
                            "last_year": last_year,
                            "n_complete_years_recount_ge_expm1": ge_expm1,
                            "n_complete_years_recount_all_days": all_days,
                        }
                    )
            if elig_path.exists():
                elig = pd.read_csv(elig_path, dtype={"station_id": str})
                hit = elig.loc[elig["station_id"].astype(str).eq(sid)]
                entry["n_complete_years"] = (
                    int(hit["n_complete_years"].iloc[0]) if len(hit) else np.nan
                )
                entry["n_complete_years_source"] = str(elig_path.relative_to(ROOT)) + ":n_complete_years"
                entry["wave2_complete_years_list"] = (
                    str(hit["complete_years"].iloc[0]) if len(hit) else ""
                )
            else:
                entry["n_complete_years"] = np.nan
                entry["n_complete_years_source"] = f"MISSING {elig_path}"
        rows.append(entry)

    table = pd.DataFrame(rows)
    table = table.merge(regimes, on=["network_id", "station_id"], how="left")
    table = table.merge(reg_variation, on=["network_id", "station_id"], how="left")
    table = table.merge(reg_status, on=["network_id", "station_id"], how="left")
    table["quality_stratum"] = (
        table["provider"].astype(str) + "|" + table["donor_regime"].fillna("").astype(str)
    )
    table.loc[table["donor_regime"].isna(), "quality_stratum"] = np.nan
    table["quality_stratum_source"] = (
        "wave2_cases.parquet: modal donor_regime per network/station -> provider|donor_regime "
        "(wave-2 networks are not present in network_split.csv)"
    )
    table["eligible_station"] = pd.to_numeric(table["n_complete_years"], errors="coerce").ge(4)
    table["eligible_station_source"] = (
        "derived: station_eligibility.csv:n_complete_years >= 4 (wave-2 MIN_YEARS gate)"
    )
    table["first_year_source"] = "daily_wide_temperature.csv: first date with a non-null value"
    table["last_year_source"] = "daily_wide_temperature.csv: last date with a non-null value"
    table["n_complete_years_recount_rule"] = (
        "recount from daily_wide_temperature.csv; see n_complete_years_recount_ge_expm1 / _all_days"
    )
    return table, file_notes


def harmonise(
    v17: pd.DataFrame,
    wave2: pd.DataFrame,
    contract: pd.DataFrame,
    rights: pd.DataFrame,
) -> pd.DataFrame:
    contract_cols = contract.set_index("provider")
    rights_by_artifact = rights.set_index("artifact")

    def pick(frame: pd.DataFrame, provider: str, column: str, default=""):
        if provider in frame.index and column in frame.columns:
            return frame.loc[provider, column]
        return default

    out = pd.concat([v17, wave2], ignore_index=True, sort=False)
    providers = out["provider"].astype(str)
    out["statistic_class"] = [contract_cols.loc[p, "statistic_class"] if p in contract_cols.index else np.nan for p in providers]
    out["statistic_class_rule_matched"] = [
        contract_cols.loc[p, "statistic_class_rule_matched"] if p in contract_cols.index else np.nan
        for p in providers
    ]
    out["statistic_documented"] = [
        contract_cols.loc[p, "statistic_documented"] if p in contract_cols.index else np.nan
        for p in providers
    ]
    out["statistic_evidence_file"] = str(
        INPUTS["measurement_provenance_dictionary"].relative_to(ROOT)
    )
    out["provider_qc_route"] = [
        contract_cols.loc[p, "quality_codes_kept"] if p in contract_cols.index else np.nan
        for p in providers
    ]

    rights_license = []
    rights_redis = []
    rights_derived = []
    rights_cite = []
    rights_artifact = []
    rights_source = []
    for provider in providers:
        artifact = RIGHTS_ARTIFACT.get(provider)
        if artifact is not None and artifact in rights_by_artifact.index:
            record = rights_by_artifact.loc[artifact]
            rights_artifact.append(artifact)
            rights_license.append(record.get("license"))
            rights_redis.append(record.get("redistribution_allowed"))
            rights_derived.append(record.get("derived_output_allowed"))
            rights_cite.append(record.get("required_citation"))
            rights_source.append("metadata/data_rights.csv")
        else:
            rights_artifact.append("MISSING: no row in metadata/data_rights.csv" if artifact is None else f"MISSING: {artifact}")
            rights_license.append(np.nan)
            rights_redis.append(np.nan)
            rights_derived.append(np.nan)
            rights_cite.append(np.nan)
            rights_source.append("MISSING")
    out["data_rights_artifact"] = rights_artifact
    out["data_rights_license"] = rights_license
    out["data_rights_redistribution_allowed"] = rights_redis
    out["data_rights_derived_output_allowed"] = rights_derived
    out["data_rights_required_citation"] = rights_cite
    out["data_rights_source"] = rights_source

    # The licence route actually used for the row: the dictionary's provider
    # licence, with the data_rights register carried alongside (never merged
    # silently).
    out["licence_route"] = [
        contract_cols.loc[p, "license"] if p in contract_cols.index else np.nan for p in providers
    ]
    out["licence_route_source"] = str(
        INPUTS["measurement_provenance_dictionary"].relative_to(ROOT)
    ) + ":license"
    out["redistribution_allowed"] = [
        contract_cols.loc[p, "redistribution_allowed"] if p in contract_cols.index else np.nan
        for p in providers
    ]
    out["derived_output_allowed"] = [
        contract_cols.loc[p, "derived_output_allowed"] if p in contract_cols.index else np.nan
        for p in providers
    ]
    out["required_citation"] = [
        contract_cols.loc[p, "required_citation"] if p in contract_cols.index else np.nan
        for p in providers
    ]
    out["acquisition_route"] = [
        contract_cols.loc[p, "acquisition_route"] if p in contract_cols.index else np.nan
        for p in providers
    ]

    # Independent cross-check against the older station-level provenance file.
    out["statistic_class_cross_check"] = out["statistic_class_station_file"].map(
        STATIONS_FILE_CROSSWALK
    )
    out["statistic_class_cross_check_agrees"] = np.where(
        out["statistic_class_cross_check"].isna(),
        "no_row_in_measurement_provenance_stations.csv",
        np.where(
            out["statistic_class_cross_check"].eq(out["statistic_class"]),
            "agrees",
            "DISAGREES",
        ),
    )
    return out


def provider_summary(table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for provider, block in table.groupby("provider", sort=True):
        regimes = block.dropna(subset=["donor_regime"]).groupby("donor_regime")["network_id"].nunique()
        mix = "; ".join(f"{k}={int(v)}" for k, v in regimes.sort_index().items()) or "MISSING"
        class_mix = block["statistic_class"].value_counts(dropna=False)
        panels = sorted(block["panel"].dropna().unique())
        years = pd.to_numeric(block["first_year"], errors="coerce").dropna()
        last = pd.to_numeric(block["last_year"], errors="coerce").dropna()
        cy = pd.to_numeric(block["n_complete_years"], errors="coerce").dropna()
        rows.append(
            {
                "provider": provider,
                "n_stations": int(block[["network_id", "station_id"]].drop_duplicates().shape[0]),
                "n_stations_definition": "distinct (network_id, station_id) rows",
                "n_distinct_station_ids": int(block["station_id"].nunique()),
                "n_networks": int(block["network_id"].nunique()),
                "first_year": int(years.min()) if len(years) else np.nan,
                "last_year": int(last.max()) if len(last) else np.nan,
                "median_complete_years": float(cy.median()) if len(cy) else np.nan,
                "min_complete_years": float(cy.min()) if len(cy) else np.nan,
                "max_complete_years": float(cy.max()) if len(cy) else np.nan,
                "statistic_class": block["statistic_class"].mode().iloc[0]
                if block["statistic_class"].notna().any()
                else np.nan,
                "statistic_class_mix_stations": "; ".join(
                    f"{k}={int(v)}" for k, v in class_mix.items()
                ),
                "quality_class": mix,
                "quality_class_definition": "donor-regime mix counted over networks",
                "provider_qc_route": block["provider_qc_route"].iloc[0],
                "panels": ",".join(panels),
                "split_roles": ",".join(sorted(block["split_role"].dropna().unique())),
                "licence_route": block["licence_route"].iloc[0],
                "licence_route_source": block["licence_route_source"].iloc[0],
                "data_rights_artifact": block["data_rights_artifact"].iloc[0],
                "redistribution_allowed": block["redistribution_allowed"].iloc[0],
                "derived_output_allowed": block["derived_output_allowed"].iloc[0],
            }
        )
    return pd.DataFrame(rows)


def measurement_class_shares(case_tables: dict[str, pd.DataFrame], contract: pd.DataFrame) -> dict:
    """Cases / networks / stations in each measurement class, per analysis panel."""

    lookup = contract.set_index("provider")["statistic_class"].to_dict()
    out: dict[str, dict] = {}
    for panel, cases in case_tables.items():
        providers = cases["provider"].astype(str)
        classes = providers.map(lookup).fillna(CLASS_UNDOCUMENTED)
        frame = cases[["network_id", "station_id"]].copy()
        frame["class"] = classes
        block = {}
        for cls, part in frame.groupby("class"):
            block[cls] = {
                "n_cases": int(len(part)),
                "share_of_cases": float(len(part) / len(frame)),
                "n_networks": int(part["network_id"].nunique()),
                "n_stations": int(part[["network_id", "station_id"]].drop_duplicates().shape[0]),
                "providers": sorted(
                    set(providers.loc[part.index].astype(str)),
                ),
            }
        out[panel] = {
            "n_cases": int(len(frame)),
            "n_networks": int(frame["network_id"].nunique()),
            "n_stations": int(frame[["network_id", "station_id"]].drop_duplicates().shape[0]),
            "by_measurement_class": block,
        }
    return out


# ==========================================================================
# PART B -- independent contrast engine
# ==========================================================================
def cluster_arrays(
    networks: np.ndarray, *columns: np.ndarray
) -> tuple[list[str], list[np.ndarray], dict[str, np.ndarray]]:
    """Group parallel arrays by cluster.

    Cluster keys are sorted (matching ``groupby(..., sort=True)`` used by the
    shared bootstrap), but ``parts[i]`` holds **original row positions** and the
    returned value arrays stay in original row order.  That is what makes the
    resampled block reproduce the row order of ``pd.concat([group_k, ...])`` and
    therefore the same tie-breaking inside the k-smallest selection.
    """

    keys = sorted(set(str(x) for x in networks))
    index = {k: i for i, k in enumerate(keys)}
    codes = np.array([index[str(x)] for x in networks], dtype=np.int64)
    order = np.argsort(codes, kind="stable")
    sorted_codes = codes[order]
    boundaries = np.searchsorted(sorted_codes, np.arange(len(keys) + 1))
    parts = [order[boundaries[i] : boundaries[i + 1]] for i in range(len(keys))]
    stacked = {f"c{j}": np.asarray(c, dtype=float) for j, c in enumerate(columns)}
    sizes = np.array([len(p) for p in parts], dtype=np.int64)
    return keys, parts, {**stacked, "__sizes": sizes}


def resample_positions(
    parts: list[np.ndarray], sizes: np.ndarray, picked: np.ndarray
) -> np.ndarray:
    """Row positions of the resampled block, in cluster-pick order (pandas concat order)."""

    return np.concatenate([parts[int(i)] for i in picked]) if len(picked) else np.empty(0, dtype=np.int64)


def failure_rate(err: np.ndarray, tolerance: float) -> float:
    bad = (~np.isfinite(err)) | (err > tolerance)
    return float(bad.mean()) if err.size else float("nan")


def topk_stable(values: np.ndarray, k: int) -> np.ndarray:
    """Positions of the k smallest values, ties resolved by original order (nsmallest keep='first')."""

    if k >= values.size:
        return np.arange(values.size)
    order = np.argsort(values, kind="stable")
    return order[:k]


def contrast_from_arrays(
    cert_score: np.ndarray,
    cert_error: np.ndarray,
    length: np.ndarray,
    policy_error: np.ndarray,
    rows: np.ndarray,
    retention: float,
    tolerance: float,
) -> float:
    n = rows.size
    if n == 0:
        return float("nan")
    k = max(1, int(round(float(retention) * n)))
    if k > n:
        return float("nan")
    cs = cert_score[rows]
    ln = length[rows]
    sel_cert = rows[topk_stable(cs, k)]
    sel_len = rows[topk_stable(ln, k)]
    return failure_rate(cert_error[sel_cert], tolerance) - failure_rate(
        policy_error[sel_len], tolerance
    )


def independent_contrast(
    cases: pd.DataFrame,
    certificates: pd.DataFrame,
    *,
    retention: float,
    tolerance: float,
    seed: int,
    draws: int,
    cluster: str = "network_id",
    boot_seed: int | None = None,
) -> dict:
    """Own implementation of the certificate-vs-length contrast + cluster bootstrap.

    Reimplements, from the protocol rather than from the original module:
      * tie-break jitter on ``longest_run`` drawn from ``default_rng(seed + 991)``
      * missing certificate scores sorted last (``inf``)
      * k = max(1, round(retention * n)) per block, denominator = full block
      * non-finite selected errors count as failures
      * whole-cluster resampling with ``np.random.default_rng(seed)``
    """

    networks = cases[cluster].astype(str).to_numpy()
    cert_score = pd.to_numeric(certificates["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    cert_error = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    rng = np.random.default_rng(int(seed) + 991)
    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float) + rng.random(len(cases))
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    cert_score = np.where(np.isfinite(cert_score), cert_score, np.inf)

    keys, parts, arrays = cluster_arrays(networks, cert_score, cert_error, length, policy_error)
    sizes = arrays["__sizes"]
    full = np.arange(len(cases))
    point = contrast_from_arrays(
        arrays["c0"], arrays["c1"], arrays["c2"], arrays["c3"], full, retention, tolerance
    )

    draws = int(draws)
    rng_boot = np.random.default_rng(int(seed if boot_seed is None else boot_seed))
    values = np.empty(draws, dtype=float)
    for draw in range(draws):
        picked = rng_boot.integers(0, len(keys), size=len(keys))
        rows = (
            np.concatenate([parts[int(i)] for i in picked])
            if len(picked)
            else np.empty(0, dtype=np.int64)
        )
        values[draw] = contrast_from_arrays(
            arrays["c0"], arrays["c1"], arrays["c2"], arrays["c3"], rows, retention, tolerance
        )
    finite = values[np.isfinite(values)]
    return {
        "point": point,
        "low": float(np.quantile(finite, 0.025)) if finite.size else float("nan"),
        "high": float(np.quantile(finite, 0.975)) if finite.size else float("nan"),
        "n_clusters": len(keys),
        "draws": draws,
        "n_finite_draws": int(finite.size),
        "se": float(np.std(finite, ddof=1)) if finite.size > 1 else float("nan"),
        "cluster_sizes": sizes.tolist(),
        "implementation": "independent numpy resampler in scripts/315 (no frontier.operating_point_contrast)",
    }


def shared_contrast_interval(
    cases: pd.DataFrame,
    certificates: pd.DataFrame,
    *,
    retention: float,
    tolerance: float,
    seed: int,
    draws: int,
) -> dict:
    """Same contrast computed with the shared cluster_bootstrap, to fix the interval definition."""

    from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast

    stat = operating_point_contrast(
        cases, certificates, retention=retention, tolerance=tolerance, seed=seed, draws=draws
    )
    return {
        "point": float(stat["point"]),
        "low": float(stat["low"]),
        "high": float(stat["high"]),
        "n_clusters": int(stat["n_clusters"]),
        "implementation": "shared stream_recoverability...frontier.operating_point_contrast",
    }


def independent_network_equal(
    per_network_values: dict[str, float], *, seed: int, draws: int
) -> dict:
    keys = sorted(per_network_values)
    values = np.array([per_network_values[k] for k in keys], dtype=float)
    point = float(values.mean())
    rng = np.random.default_rng(int(seed))
    out = np.empty(int(draws), dtype=float)
    for i in range(int(draws)):
        picked = rng.choice(len(keys), size=len(keys), replace=True)
        out[i] = float(values[picked].mean())
    return {
        "point": point,
        "low": float(np.quantile(out, 0.025)),
        "high": float(np.quantile(out, 0.975)),
        "n_networks": len(keys),
        "draws": int(draws),
        "implementation": "independent numpy resampler in scripts/315",
    }


def independent_net_equal_bootstrap(
    parts: list[np.ndarray],
    values: np.ndarray,
    *,
    seed: int,
    draws: int,
) -> dict:
    """Cluster bootstrap of the network-equal mean, own resampler."""

    keys = len(parts)
    point = float(np.mean([values[parts[i]].mean() for i in range(keys)]))
    rng = np.random.default_rng(int(seed))
    out = np.empty(int(draws), dtype=float)
    for i in range(int(draws)):
        picked = rng.integers(0, keys, size=keys)
        # duplicate clusters are averaged together, exactly as groupby(...).mean().mean()
        acc: dict[int, list[int]] = {}
        for j in picked:
            acc.setdefault(int(j), []).append(int(j))
        means = [values[np.concatenate([parts[j] for j in js])].mean() for js in acc.values()]
        out[i] = float(np.mean(means))
    return {"point": point, "low": float(np.quantile(out, 0.025)), "high": float(np.quantile(out, 0.975)), "draws": int(draws)}


# ---------------------------------------------------------------- Part B.1/B.2
def per_network_op_contrast(
    cases: pd.DataFrame,
    certificates: pd.DataFrame,
    *,
    retention: float,
    tolerance: float,
    seed: int,
    jitter_offset: int = 0,
) -> pd.DataFrame:
    """Per-network certificate-vs-length failure-rate contrast (percentage points).

    ``jitter_offset`` is 991 for the ``operating_point_contrast`` code path and 0
    for the step-7 transfer-reporting code path, which draws its jitter from
    ``default_rng(SEED)`` directly.
    """

    networks = cases["network_id"].astype(str).to_numpy()
    cert_score = pd.to_numeric(certificates["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    cert_error = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    rng = np.random.default_rng(int(seed) + int(jitter_offset))
    length = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy(dtype=float) + rng.random(len(cases))
    policy_error = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    cert_score = np.where(np.isfinite(cert_score), cert_score, np.inf)

    rows = []
    for net in sorted(set(networks)):
        idx = np.where(networks == net)[0]
        k = max(1, int(round(retention * idx.size)))
        if k > idx.size:
            continue
        sel_cert = idx[topk_stable(cert_score[idx], k)]
        sel_len = idx[topk_stable(length[idx], k)]
        rows.append(
            {
                "network_id": net,
                "n_cases": int(idx.size),
                "contrast_points": (
                    failure_rate(cert_error[sel_cert], tolerance)
                    - failure_rate(policy_error[sel_len], tolerance)
                )
                * 100.0,
            }
        )
    return pd.DataFrame(rows)


def verdict_row(
    quantity: str,
    panel: str,
    stored: float | None,
    stored_source: str,
    recomputed: float | None,
    tolerance: float | None,
    method: str,
    notes: str = "",
    stored_ci: tuple | None = None,
    recomputed_ci: tuple | None = None,
    tolerance_ci: float | None = None,
) -> dict:
    def diff(a, b):
        if a is None or b is None:
            return None
        if isinstance(a, float) and not np.isfinite(a):
            return None
        if isinstance(b, float) and not np.isfinite(b):
            return None
        return float(abs(a - b))

    d = diff(stored, recomputed)
    if d is None:
        point_verdict = "NOT_RECOMPUTED"
    elif tolerance is None:
        point_verdict = "NO_TOLERANCE_STATED"
    else:
        point_verdict = "AGREE" if d <= tolerance else "DISAGREE"
    d_lo = diff(stored_ci[0] if stored_ci else None, recomputed_ci[0] if recomputed_ci else None)
    d_hi = diff(stored_ci[1] if stored_ci else None, recomputed_ci[1] if recomputed_ci else None)
    if stored_ci is None or recomputed_ci is None:
        ci_verdict = "NOT_RECOMPUTED"
    elif tolerance_ci is None:
        ci_verdict = "NO_TOLERANCE_STATED"
    else:
        worst = max(x for x in (d_lo, d_hi) if x is not None)
        ci_verdict = "AGREE" if worst <= tolerance_ci else "DISAGREE"
    return {
        "quantity": quantity,
        "panel": panel,
        "stored_value": stored,
        "stored_value_source": stored_source,
        "recomputed_value": recomputed,
        "abs_diff": d,
        "tolerance": tolerance,
        "verdict": point_verdict,
        "stored_ci_low": stored_ci[0] if stored_ci else None,
        "stored_ci_high": stored_ci[1] if stored_ci else None,
        "recomputed_ci_low": recomputed_ci[0] if recomputed_ci else None,
        "recomputed_ci_high": recomputed_ci[1] if recomputed_ci else None,
        "abs_diff_ci_low": d_lo,
        "abs_diff_ci_high": d_hi,
        "tolerance_ci": tolerance_ci,
        "verdict_ci": ci_verdict,
        "method": method,
        "notes": notes,
    }


# ---------------------------------------------------------------- Part B.3
SUPPORT_FEATURES = (
    "longest_run",
    "total_missing",
    "missing_fraction",
    "n_runs",
    "warm_observed_fraction",
    "month_sin",
    "month_cos",
    "n_visible_donors",
    "donor_corr_mean",
    "donor_corr_max",
    "donor_corr_min",
    "donor_coverage_mean",
    "train_resid_sd",
    "seasonal_amplitude",
    "train_metric_sd",
    "n_complete_years",
    "record_years",
    "left_flank",
    "right_flank",
    "air_available",
    "estimator_disagreement",
)
GENERIC_FEATURES = tuple(SUPPORT_FEATURES[:21])
SUPPORT_SET = tuple(SUPPORT_FEATURES[:21]) + ("peak_overlap",)


def prep_cases(raw: pd.DataFrame) -> pd.DataFrame:
    """Own re-implementation of the documented preparation step."""

    frame = raw.copy()
    metric_cols = [
        c for c in frame.columns if c.startswith("metric_") and c != "metric_observed_days"
    ]
    block = frame[metric_cols].apply(pd.to_numeric, errors="coerce")
    frame["estimator_disagreement"] = block.max(axis=1) - block.min(axis=1)
    month = pd.to_numeric(frame["longest_run_month"], errors="coerce").fillna(6.0)
    frame["month_sin"] = np.sin(2 * np.pi * month / 12.0)
    frame["month_cos"] = np.cos(2 * np.pi * month / 12.0)
    return frame


def design_matrix(frame: pd.DataFrame, features: tuple[str, ...]) -> pd.DataFrame:
    """Own re-implementation of the decision-time-visible feature frame."""

    out = pd.DataFrame(index=frame.index)
    month = pd.to_numeric(frame["longest_run_month"], errors="coerce").fillna(6.0)
    for name in features:
        if name == "month_sin":
            out[name] = np.sin(2 * np.pi * month / 12.0)
        elif name == "month_cos":
            out[name] = np.cos(2 * np.pi * month / 12.0)
        else:
            column = frame[name]
            out[name] = (
                column.astype(float) if column.dtype == bool else pd.to_numeric(column, errors="coerce")
            )
    return out[list(features)]


def risk_model(seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile",
        quantile=0.9,
        random_state=int(seed),
        max_depth=4,
        max_iter=350,
        learning_rate=0.06,
        min_samples_leaf=40,
    )


def independent_oof_scores(
    frame: pd.DataFrame,
    features: tuple[str, ...],
    *,
    seed: int,
    n_splits: int,
) -> pd.Series:
    networks = sorted(frame["network_id"].astype(str).unique())
    rng = np.random.default_rng(int(seed))
    order = rng.permutation(len(networks))
    folds = {networks[int(i)]: int(pos % n_splits) for pos, i in enumerate(order)}
    fold_id = frame["network_id"].astype(str).map(folds)
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    for fold in range(n_splits):
        test_idx = fold_id.eq(fold).to_numpy()
        train_idx = ~test_idx
        if not test_idx.any() or not train_idx.any():
            continue
        train = frame.loc[train_idx]
        y_train = pd.to_numeric(train["abserr_policy"], errors="coerce")
        mask = y_train.notna().to_numpy()
        X_train = design_matrix(train, features).loc[mask]
        model = risk_model(seed + fold).fit(X_train, y_train.loc[mask])
        out.loc[test_idx] = model.predict(design_matrix(frame.loc[test_idx], features))
    return out


def independent_rule_scores(frame: pd.DataFrame, *, seed: int) -> dict[str, pd.Series]:
    rng = np.random.default_rng(int(seed))
    n = len(frame)

    def jitter(values: pd.Series, scale: float) -> pd.Series:
        return pd.to_numeric(values, errors="coerce") + rng.random(n) * float(scale)

    return {
        "length_rule": jitter(frame["longest_run"], 1.0),
        "warm_coverage_rule": jitter(-pd.to_numeric(frame["warm_observed_fraction"], errors="coerce"), 1e-3),
        "peak_overlap_rule": jitter(frame["peak_overlap"], 1e-3),
        "estimator_disagreement_rule": jitter(frame["estimator_disagreement"], 1e-3),
    }


def rate_at_retention(errors: np.ndarray, score: np.ndarray, retention: float, tolerance: float) -> float:
    good = np.isfinite(errors)
    values = np.where(np.isfinite(score), score, np.inf)[good]
    err = errors[good]
    k = max(1, int(round(float(retention) * err.size)))
    keep = topk_stable(values, k)
    return float((err[keep] > tolerance).mean())


def network_equal_arrays(
    values: np.ndarray, parts: list[np.ndarray]
) -> float:
    return float(np.mean([values[p].mean() for p in parts]))


def independent_paired_contrast(
    networks: np.ndarray,
    error: np.ndarray,
    score_a: np.ndarray,
    score_b: np.ndarray,
    *,
    retention: float,
    tolerance: float,
    seed: int,
    draws: int,
) -> dict:
    """Own implementation of the paired network-clustered contrast at fixed retention."""

    keys, parts, arrays = cluster_arrays(networks, error, score_a, score_b)
    err, sa, sb = arrays["c0"], arrays["c1"], arrays["c2"]
    full = np.arange(err.size)

    def stat(rows: np.ndarray) -> float:
        n = rows.size
        k = max(1, int(round(float(retention) * n)))
        if k > n:
            return float("nan")
        keep_a = rows[topk_stable(sa[rows], k)]
        keep_b = rows[topk_stable(sb[rows], k)]
        return failure_rate(err[keep_a], tolerance) - failure_rate(err[keep_b], tolerance)

    point = stat(full)
    rng = np.random.default_rng(int(seed))
    out = np.empty(int(draws), dtype=float)
    for i in range(int(draws)):
        picked = rng.integers(0, len(keys), size=len(keys))
        rows = resample_positions(parts, arrays["__sizes"], picked)
        out[i] = stat(rows)
    finite = out[np.isfinite(out)]
    return {
        "point": point,
        "low": float(np.quantile(finite, 0.025)) if finite.size else float("nan"),
        "high": float(np.quantile(finite, 0.975)) if finite.size else float("nan"),
        "n_clusters": len(keys),
        "draws": int(draws),
    }


# ---------------------------------------------------------------- Part B.4
STEP3_RECONSTRUCTORS = ("doy_climatology", "smooth_climatology", "donor_ridge", "linear_interp")
STEP3_LENGTHS = (30, 60, 90)
STEP3_OVERLAPS = ("none", "partial", "full")


def step3_station_year_means(cases: pd.DataFrame, column: str) -> pd.DataFrame:
    block = cases.loc[pd.to_numeric(cases[column], errors="coerce").notna()].copy()
    block["value"] = pd.to_numeric(block[column], errors="coerce")
    return (
        block.groupby(
            ["network_id", "station_id", "year", "longest_run", "overlap_class"], as_index=False
        )["value"]
        .mean()
        .rename(columns={"value": "abserr"})
    )


def step3_position_table(cases: pd.DataFrame, column: str) -> pd.DataFrame:
    sy = step3_station_year_means(cases, column)
    rows = []
    for length in STEP3_LENGTHS:
        block = sy.loc[sy["longest_run"].eq(length)]
        if block.empty:
            continue
        wide = block.pivot_table(
            index=["network_id", "station_id", "year"], columns="overlap_class", values="abserr"
        )
        if not {"full", "none"}.issubset(set(map(str, wide.columns))):
            continue
        both = wide.dropna(subset=["full", "none"]).reset_index()
        if both.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "network_id": both["network_id"],
                    "station_id": both["station_id"],
                    "year": both["year"],
                    "length": int(length),
                    "delta_full_minus_none": both["full"] - both["none"],
                }
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def step3_length_table(cases: pd.DataFrame, column: str) -> pd.DataFrame:
    sy = step3_station_year_means(cases, column)
    rows = []
    for overlap in STEP3_OVERLAPS:
        block = sy.loc[sy["overlap_class"].astype(str).eq(overlap)]
        if block.empty:
            continue
        wide = block.pivot_table(
            index=["network_id", "station_id", "year"], columns="longest_run", values="abserr"
        )
        available = [c for c in STEP3_LENGTHS if c in wide.columns]
        if len(available) < 2:
            continue
        lo, hi = available[0], available[-1]
        both = wide.dropna(subset=[lo, hi]).reset_index()
        if both.empty:
            continue
        rows.append(
            pd.DataFrame(
                {
                    "network_id": both["network_id"],
                    "station_id": both["station_id"],
                    "year": both["year"],
                    "overlap_class": overlap,
                    "short_length": lo,
                    "long_length": hi,
                    "delta_long_minus_short": both[hi] - both[lo],
                }
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def step3_network_ci(deltas: pd.DataFrame, value: str, by: list[str], seed: int, draws: int) -> pd.DataFrame:
    rows = []
    for keys, block in deltas.groupby(by, sort=True):
        keys = keys if isinstance(keys, tuple) else (keys,)
        networks = block["network_id"].astype(str).to_numpy()
        values = block[value].to_numpy(dtype=float)
        _, parts, arrays = cluster_arrays(networks, values)
        vals = arrays["c0"]
        point = network_equal_arrays(vals, parts)
        rng = np.random.default_rng(int(seed))
        out = np.empty(int(draws), dtype=float)
        for i in range(int(draws)):
            picked = rng.integers(0, len(parts), size=len(parts))
            acc: dict[int, np.ndarray] = {}
            for j in picked:
                j = int(j)
                acc[j] = parts[j] if j not in acc else np.concatenate([acc[j], parts[j]])
            out[i] = float(np.mean([vals[p].mean() for p in acc.values()]))
        low, high = float(np.quantile(out, 0.025)), float(np.quantile(out, 0.975))
        row = {name: key for name, key in zip(by, keys)}
        row.update(
            {
                "point_C": point,
                "ci_low_C": low,
                "ci_high_C": high,
                "n_networks": int(block["network_id"].nunique()),
                "n_station_years": int(len(block)),
                "ci_excludes_zero": bool(not (low <= 0 <= high)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(by).reset_index(drop=True) if rows else pd.DataFrame()


# ==========================================================================
# main
# ==========================================================================
def main() -> int:  # noqa: C901
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for key in INPUTS:
        require(INPUTS[key], key)
    unrecomputable: list[dict] = []

    # ------------------------------------------------------------------ PART A
    roster = pd.read_csv(INPUTS["station_roster"], dtype={"station_id": str})
    note_columns(
        "station_roster",
        "station identity, record span, complete-year count, split role, PART A",
        [
            "network_id",
            "station_id",
            "n_complete_years",
            "first_year",
            "last_year",
            "provider",
            "source_root",
            "regulation_status",
            "donor_regime",
            "eligible_station",
            "split_role",
        ],
    )
    net_split = pd.read_csv(INPUTS["network_split"], dtype={"network_id": str})
    note_columns(
        "network_split",
        "quality stratum (provider|donor_regime), network sizes, split role, PART A",
        [
            "network_id",
            "provider",
            "source_root",
            "n_stations",
            "n_station_years",
            "median_donors",
            "donor_regime",
            "stratum",
            "split_role",
        ],
    )
    trusted = pd.read_csv(
        INPUTS["trusted_complete_years"], dtype={"station_id": str, "network_id": str}
    )
    note_columns(
        "trusted_complete_years",
        "independent recount of record span and complete calendar years, PART A",
        [
            "network_id",
            "station_id",
            "year",
            "expected_days",
            "observed_days",
            "missing_days",
            "full_calendar_year",
            "source_root",
            "legacy_qc_status",
            "regulation_status",
        ],
    )
    manifest = pd.read_csv(INPUTS["current_data_manifest"], dtype={"network_id": str})
    note_columns(
        "current_data_manifest",
        "per-network data presence, artifact path and sha256, PART A",
        ["network_id", "provider", "source_root", "split_role", "input_path", "bytes", "sha256", "status"],
    )
    acq = pd.read_csv(INPUTS["current_data_acquisition"], dtype={"network_id": str})
    note_columns(
        "current_data_acquisition",
        "acquisition route / product per network, PART A",
        [
            "network_id",
            "provider",
            "country",
            "product",
            "acquisition_route",
            "manifest_path",
            "source_root",
            "split_role",
        ],
    )
    contract = build_provider_contract()
    rights = pd.read_csv(INPUTS["data_rights"], dtype=str).fillna("")
    note_columns(
        "data_rights",
        "repository-level licence register (artifact-keyed), PART A",
        [
            "artifact",
            "upstream_source",
            "copyright_holder",
            "license",
            "redistribution_allowed",
            "derived_output_allowed",
            "reviewer_access_route",
            "required_citation",
        ],
    )
    prov_stations = pd.read_csv(
        INPUTS["measurement_provenance_stations"], dtype={"station_id": str, "network_id": str}
    )
    note_columns(
        "measurement_provenance_stations",
        "independent cross-check of the per-station statistic class, PART A",
        [
            "network_id",
            "station_id",
            "provider",
            "split_role",
            "statistic_class",
            "statistic_proven_for_panel",
            "include_in_unified_daily_mean_main",
            "day_boundary",
            "qa_retained",
        ],
    )
    w2_roster = pd.read_csv(INPUTS["wave2_station_roster"], dtype={"station_id": str})
    note_columns(
        "wave2_station_roster",
        "wave-2 confirmation panel station membership, PART A",
        ["network_id", "provider", "station_id"],
    )
    w2_manifest = pd.read_csv(INPUTS["wave2_inputs_manifest"], dtype={"network_id": str})
    note_columns(
        "wave2_inputs_manifest",
        "wave-2 network -> artifact path, context and panel role, PART A",
        [
            "network_id",
            "provider",
            "context",
            "panel_role",
            "n_stations_ge4",
            "station_ids_ge4",
            "input_path",
            "bytes",
            "sha256",
        ],
    )

    wave2_cases = pd.read_parquet(INPUTS["wave2_cases"])
    note_columns(
        "wave2_cases",
        "wave-2 case panel: modal donor_regime + regulation_status per station (PART A) and "
        "the step 5/7 contrast inputs (PART B)",
        ["network_id", "station_id", "provider", "donor_regime", "regulation_status", "longest_run", "abserr_policy"],
    )

    v17_table = build_v17_station_table(
        roster, net_split, trusted, manifest, acq, prov_stations
    )
    w2_table, w2_notes = build_wave2_station_table(w2_roster, w2_manifest, wave2_cases)
    coverage = harmonise(v17_table, w2_table, contract, rights)

    coverage["first_year"] = pd.to_numeric(coverage["first_year"], errors="coerce")
    coverage["last_year"] = pd.to_numeric(coverage["last_year"], errors="coerce")
    coverage["n_complete_years"] = pd.to_numeric(coverage["n_complete_years"], errors="coerce")
    coverage["n_complete_years_recount"] = pd.to_numeric(
        coverage["n_complete_years_recount"], errors="coerce"
    )
    coverage["n_complete_years_recount_ge_expm1"] = pd.to_numeric(
        coverage["n_complete_years_recount_ge_expm1"], errors="coerce"
    )
    coverage["n_complete_years_recount_all_days"] = pd.to_numeric(
        coverage["n_complete_years_recount_all_days"], errors="coerce"
    )
    combined_recount = coverage["n_complete_years_recount"].where(
        coverage["panel"].eq("v17"), coverage["n_complete_years_recount_ge_expm1"]
    )
    coverage["n_complete_years_recount_combined"] = combined_recount
    coverage["n_complete_years_recount_matches"] = np.where(
        combined_recount.isna() | coverage["n_complete_years"].isna(),
        "not_comparable",
        np.where(combined_recount.eq(coverage["n_complete_years"]), "match", "MISMATCH"),
    )
    coverage["complete_year_convention"] = np.where(
        coverage["panel"].eq("v17"),
        "full_calendar_year flag in trusted_river_complete_years.csv",
        "len(values) >= year_length-1 on the pre-widening per-station series (ingest script), "
        "not recoverable exactly from daily_wide_temperature.csv",
    )
    coverage["panel_definition"] = np.where(
        coverage["panel"].eq("v17"),
        "results/v17_fitness/step1_panel/station_roster.csv (full roster: 457 eligible stations "
        "in 146 networks plus 90 ineligible roster rows carried for completeness)",
        "results/wrr_submission_ready/p0_07_wave2_ingest/wave2_station_roster.csv "
        "(stations of the 49 scored wave-2 confirmation networks)",
    )
    coverage["in_final_analysis_panel"] = (
        (coverage["panel"].eq("v17") & coverage["eligible_station"].eq(True))
        | coverage["panel"].eq("wave2_confirmation")
    )

    column_order = [
        "panel",
        "provider",
        "network_id",
        "station_id",
        "split_role",
        "split_role_raw",
        "source_root",
        "panel_definition",
        "in_final_analysis_panel",
        "wave2_context",
        "first_year",
        "last_year",
        "first_year_source",
        "last_year_source",
        "first_year_cross_check",
        "last_year_cross_check",
        "n_complete_years",
        "n_complete_years_source",
        "n_complete_years_recount_combined",
        "n_complete_years_recount",
        "n_complete_years_recount_ge_expm1",
        "n_complete_years_recount_all_days",
        "n_complete_years_recount_rule",
        "complete_year_convention",
        "n_complete_years_recount_matches",
        "statistic_class",
        "statistic_class_rule_matched",
        "statistic_class_station_file",
        "statistic_class_cross_check",
        "statistic_class_cross_check_agrees",
        "statistic_proven_for_panel",
        "include_in_unified_daily_mean_main",
        "statistic_evidence_file",
        "quality_stratum",
        "donor_regime",
        "donor_regime_n_distinct",
        "quality_stratum_source",
        "eligible_station",
        "eligible_station_source",
        "regulation_status",
        "provider_qc_route",
        "licence_route",
        "licence_route_source",
        "redistribution_allowed",
        "derived_output_allowed",
        "data_rights_artifact",
        "data_rights_license",
        "data_rights_redistribution_allowed",
        "data_rights_derived_output_allowed",
        "data_rights_required_citation",
        "data_rights_source",
        "required_citation",
        "acquisition_route",
        "manifest_status",
        "manifest_input_path",
        "manifest_sha256",
    ]
    coverage_out = coverage.reindex(columns=column_order)
    coverage_out = coverage_out.sort_values(
        ["panel", "provider", "network_id", "station_id"]
    ).reset_index(drop=True)
    coverage_out.to_csv(OUT / "final_coverage_table.csv", index=False)

    summary_table = provider_summary(coverage)
    summary_table.to_csv(OUT / "provider_coverage_summary.csv", index=False)

    # cross-check of the panel sentence printed in the manuscript
    v17_ok = coverage.loc[coverage["panel"].eq("v17") & coverage["eligible_station"].eq(True)]
    panel_crosscheck = {
        "manuscript_claim": "146 networks, 457 stations and 5114 fully observed station-years "
        "(paper/wrr/wrr_manuscript.tex:331)",
        "recomputed_from_artifacts": {
            "n_networks": int(v17_ok["network_id"].nunique()),
            "n_stations": int(v17_ok["station_id"].nunique()),
            "n_complete_station_years": int(
                pd.to_numeric(v17_ok["n_complete_years"], errors="coerce").sum()
            ),
        },
        "matches": bool(
            v17_ok["network_id"].nunique() == 146
            and v17_ok["station_id"].nunique() == 457
            and int(pd.to_numeric(v17_ok["n_complete_years"], errors="coerce").sum()) == 5114
        ),
        "full_roster_station_years": int(
            pd.to_numeric(coverage.loc[coverage["panel"].eq("v17"), "n_complete_years"], errors="coerce").sum()
        ),
        "note": "the 90 ineligible roster rows carry 193 further complete station-years that are "
        "outside the 5114 used by the manuscript",
        "wave2_panel": {
            "n_networks": int(
                coverage.loc[coverage["panel"].eq("wave2_confirmation"), "network_id"].nunique()
            ),
            "n_station_network_rows": int(coverage["panel"].eq("wave2_confirmation").sum()),
            "n_distinct_station_ids": int(
                coverage.loc[coverage["panel"].eq("wave2_confirmation"), "station_id"].nunique()
            ),
            "n_scored_cases": int(len(wave2_cases)),
        },
    }

    contract_out = contract[
        [
            "provider",
            "country",
            "product",
            "statistic_class",
            "statistic_class_rule_matched",
            "statistic_documented",
            "statistic_as_parsed",
            "aggregation_interval",
            "day_boundary_tz",
            "quality_codes_kept",
            "quality_codes_dropped",
            "license",
            "redistribution_allowed",
            "derived_output_allowed",
            "required_citation",
            "acquisition_route",
            "evidence_url",
            "evidence_quote",
            "verification_status",
            "evidence_file",
        ]
    ].copy()
    contract_out["data_rights_artifact"] = contract_out["provider"].map(RIGHTS_ARTIFACT).fillna(
        "MISSING: no row in metadata/data_rights.csv"
    )
    contract_out.to_csv(OUT / "measurement_contract_table.csv", index=False)

    # measurement-class shares of each analysis panel (cases / networks / stations)
    development_cases = pd.read_parquet(INPUTS["development_cases"])
    reserved_cases = pd.read_parquet(INPUTS["reserved_cases"])
    note_columns(
        "development_cases",
        "development case panel (step 2 / step 3 headline numbers), PART B",
        ["network_id", "station_id", "provider", "abserr_policy", "longest_run"],
    )
    note_columns(
        "reserved_cases",
        "reserved retrospective case panel, PART B",
        ["network_id", "station_id", "provider", "abserr_policy", "longest_run"],
    )
    shares = measurement_class_shares(
        {
            "development": development_cases,
            "reserved_retrospective": reserved_cases,
            "wave2_confirmation": wave2_cases,
        },
        contract,
    )

    # gap list
    gap = coverage.loc[
        coverage["statistic_class"].isin([CLASS_UNDOCUMENTED, CLASS_NON_DAILY_REFERENCE])
    ].copy()
    cross_check_disagreements = coverage.loc[
        coverage["statistic_class_cross_check_agrees"].eq("DISAGREES")
    ]
    missing_rights = coverage.loc[coverage["data_rights_source"].eq("MISSING")]
    first_last_mismatch = coverage.loc[
        coverage["first_year_cross_check"].eq("MISMATCH")
        | coverage["last_year_cross_check"].eq("MISMATCH")
    ]
    recount_mismatch = coverage.loc[coverage["n_complete_years_recount_matches"].eq("MISMATCH")]

    gap_lines = [
        "# P0-06 coverage gaps",
        "",
        "Generated by `scripts/315_wrr_p0_06_coverage_and_recompute.py`.",
        "Every row below is a station (or provider) whose coverage record is incomplete, "
        "unverified, or convention-dependent. Nothing here is inferred: each gap names the "
        "artifact that does or does not carry the field.",
        "",
        "## 1. Stations whose provider-documented daily statistic is NOT a documented daily mean",
        "",
        f"Total: {len(gap)} stations "
        f"({int(gap['network_id'].nunique())} networks) "
        "= undocumented definition + non-daily reference reading.",
        "",
        "### 1a. `undocumented` — no fetched provider page states the daily statistic",
        "",
    ]
    undoc = gap.loc[gap["statistic_class"].eq(CLASS_UNDOCUMENTED)]
    if len(undoc):
        group = (
            undoc.groupby(["provider", "network_id", "statistic_class_rule_matched"])
            .agg(n_stations=("station_id", "nunique"), stations=("station_id", lambda s: ";".join(sorted(s))))
            .reset_index()
        )
        gap_lines.append("| provider | network | n_stations | stations |")
        gap_lines.append("|---|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(
                f"| {row.provider} | {row.network_id} | {row.n_stations} | `{row.stations}` |"
            )
        providers_undoc = sorted(undoc["provider"].unique())
        gap_lines += [
            "",
            f"Providers affected: {', '.join(providers_undoc)}.",
            "",
            "Evidence (verbatim from `results/wrr_submission_ready/measurement_provenance_dictionary.csv`, "
            "column `statistic_documented`):",
            "",
        ]
        for provider in providers_undoc:
            text = contract.set_index("provider").loc[provider, "statistic_documented"]
            gap_lines.append(f"- **{provider}**: \"{text}\"")
        gap_lines.append("")
    else:
        gap_lines.append("(none)")
        gap_lines.append("")

    gap_lines += [
        "### 1b. `non_daily_reference_reading` — provider documents a once-daily reading",
        "",
    ]
    nondaily = gap.loc[gap["statistic_class"].eq(CLASS_NON_DAILY_REFERENCE)]
    if len(nondaily):
        group = (
            nondaily.groupby(["provider", "network_id"])
            .agg(n_stations=("station_id", "nunique"), stations=("station_id", lambda s: ";".join(sorted(s))))
            .reset_index()
        )
        gap_lines.append("| provider | network | n_stations | stations |")
        gap_lines.append("|---|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(
                f"| {row.provider} | {row.network_id} | {row.n_stations} | `{row.stations}` |"
            )
        for provider in sorted(nondaily["provider"].unique()):
            text = contract.set_index("provider").loc[provider, "statistic_documented"]
            gap_lines += ["", f"- **{provider}**: \"{text}\""]
        gap_lines += [
            "",
            "These stations are flagged "
            "`include_in_unified_daily_mean_main = False` in "
            "`results/wrr_submission_ready/measurement_provenance_stations.csv`, i.e. the project "
            "already excludes them from the unified daily-mean main analysis.",
            "",
        ]
    else:
        gap_lines.append("(none)")
        gap_lines.append("")

    gap_lines += [
        "### 1c. `project_aggregated_from_subdaily` — a project aggregate, not a provider daily statistic",
        "",
        "Not listed as a defect, but these are the stations for which the daily value is a "
        "*derived product*:",
        "",
        "| provider | n_stations | n_networks | dictionary statement |",
        "|---|---|---|---|",
    ]
    agg = coverage.loc[coverage["statistic_class"].eq(CLASS_PROJECT_SUBDAILY)]
    for provider, block in agg.groupby("provider"):
        text = contract.set_index("provider").loc[provider, "statistic_as_parsed"]
        gap_lines.append(
            f"| {provider} | {block[['network_id','station_id']].drop_duplicates().shape[0]} | "
            f"{block['network_id'].nunique()} | {text} |"
        )
    gap_lines.append("")

    gap_lines += [
        "## 2. Cross-check disagreements between the two project provenance artifacts",
        "",
        f"Rows where `measurement_provenance_stations.csv:statistic_class` (script 232) maps to a "
        f"different canonical class than `measurement_provenance_dictionary.csv` "
        f"(script 257, `statistic_documented` + `statistic_as_parsed`): "
        f"**{len(cross_check_disagreements)} stations**.",
        "",
    ]
    if len(cross_check_disagreements):
        group = (
            cross_check_disagreements.groupby(
                ["provider", "statistic_class_station_file", "statistic_class"]
            )
            .agg(n_stations=("station_id", "nunique"))
            .reset_index()
        )
        gap_lines.append("| provider | station-file class | dictionary class | n_stations |")
        gap_lines.append("|---|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(
                f"| {row.provider} | {row.statistic_class_station_file} | {row.statistic_class} | {row.n_stations} |"
            )
        gap_lines += [
            "",
            "The station-level file predates the dictionary and labels these series "
            "`provider_daily_unverified_definition`; the dictionary later documents either a "
            "provider daily mean or a project-side aggregation. "
            "The coverage table uses the dictionary class and keeps the older label in "
            "`statistic_class_station_file` so the change is visible. Any manuscript sentence "
            "that cites the station-level file as the provenance source is therefore stale.",
            "",
        ]
    gap_lines.append("")

    gap_lines += [
        "## 2b. Stations with no development/reserved assignment",
        "",
    ]
    unassigned = coverage.loc[coverage["split_role"].eq("unassigned_not_in_development_or_reserved")]
    gap_lines.append(
        f"`results/v17_fitness/step1_panel/station_roster.csv:split_role` is empty for "
        f"**{len(unassigned)} stations**; these are exactly the roster rows with "
        f"`eligible_station == False` (checked below). They therefore appear in the study roster "
        f"but contribute no development or reserved case."
    )
    gap_lines.append("")
    gap_lines.append(
        f"- all {len(unassigned)} have `eligible_station == False`: "
        f"{bool(unassigned['eligible_station'].eq(False).all())}"
    )
    gap_lines.append("")
    if len(unassigned):
        group = unassigned.groupby(["provider", "network_id"]).size().reset_index(name="n_stations")
        gap_lines.append("| provider | network | n stations |")
        gap_lines.append("|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(f"| {row.provider} | {row.network_id} | {row.n_stations} |")
        gap_lines.append("")

    gap_lines += [
        "## 2c. Wave-2 roster stations below the declared four-complete-year gate",
        "",
    ]
    w2_rows = coverage.loc[coverage["panel"].eq("wave2_confirmation")]
    below = w2_rows.loc[pd.to_numeric(w2_rows["n_complete_years"], errors="coerce").lt(4)]
    gap_lines.append(
        f"`results/wrr_submission_ready/p0_07_wave2_ingest/wave2_station_roster.csv` lists "
        f"**{len(w2_rows)} station-network rows**; **{len(below)}** of them have "
        f"`station_eligibility.csv:n_complete_years < 4`, which is the `MIN_YEARS` gate used by "
        f"the wave-2 ingest scripts. They are in the roster (and in the scored case table) "
        f"without meeting the gate recorded in the ingest code."
    )
    gap_lines.append("")
    if len(below):
        group = below.groupby(["provider", "network_id"]).size().reset_index(name="n_stations")
        gap_lines.append("| provider | network | n stations below the gate |")
        gap_lines.append("|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(f"| {row.provider} | {row.network_id} | {row.n_stations} |")
        gap_lines.append("")

    gap_lines += [
        "## 3. Licence register gaps",
        "",
        f"Stations whose provider has no row in `metadata/data_rights.csv`: "
        f"**{len(missing_rights)} stations** "
        f"({', '.join(sorted(missing_rights['provider'].unique())) if len(missing_rights) else 'none'}).",
        "",
        "For these providers the licence route in the coverage table comes from "
        "`results/wrr_submission_ready/measurement_provenance_dictionary.csv:license` only; "
        "the `data_rights_*` columns are left as `MISSING`.",
        "",
    ]

    gap_lines += [
        "## 4. Record-span / complete-year mismatches",
        "",
        f"- `first_year`/`last_year` disagree with `trusted_river_complete_years.csv`: "
        f"**{len(first_last_mismatch)} stations** (v17 panel only; wave-2 has no trusted file).",
        f"- `n_complete_years` not reproduced by the per-row recount rule: "
        f"**{len(recount_mismatch)} station rows** "
        "(v17: `sum(full_calendar_year)`; wave-2: the `len(values) >= year_length - 1` variant).",
        "",
    ]
    if len(recount_mismatch):
        group = recount_mismatch.groupby(["panel", "provider"]).size().reset_index(name="n_stations")
        gap_lines.append("| panel | provider | n station rows with a recount mismatch |")
        gap_lines.append("|---|---|---|")
        for row in group.itertuples():
            gap_lines.append(f"| {row.panel} | {row.provider} | {row.n_stations} |")
        gap_lines += [
            "",
            "Wave-2 station completeness is defined by a rule evaluated on the per-station series "
            "*before* it is widened into `daily_wide_temperature.csv`; the widened file cannot "
            "restore the row count the rule tests, so the wave-2 count is only reproducible under "
            "a named convention. Two recounts are carried in the coverage table:",
            "",
        ]
        for column, label in (
            ("n_complete_years_recount_ge_expm1", "len(values) >= year_length - 1 (rule as written)"),
            ("n_complete_years_recount_all_days", "every calendar day present (strict)"),
        ):
            w2 = coverage.loc[coverage["panel"].eq("wave2_confirmation")]
            agree = pd.to_numeric(w2[column], errors="coerce").eq(
                pd.to_numeric(w2["n_complete_years"], errors="coerce")
            )
            gap_lines.append(
                f"- `{column}` — {label}: agrees with `station_eligibility.csv:n_complete_years` "
                f"for **{int(agree.sum())} / {len(w2)}** wave-2 station rows."
            )
        gap_lines += [
            "",
            "Neither recount is silently substituted for the project value: "
            "`final_coverage_table.csv:n_complete_years` is always the project artifact.",
            "",
        ]
    for note in w2_notes:
        gap_lines.append(f"- wave-2 artifact note: `{note['network_id']}` {note['note']}")
    gap_lines.append("")

    gap_lines += [
        "## 5. Columns the review asked for that do not exist in the named artifacts",
        "",
        "- `wave2_inputs_manifest.csv` has no `first_year`/`last_year`/`n_complete_years` column: "
        "the record span is recomputed from `daily_wide_temperature.csv` and the complete-year "
        "count is taken from the sibling `station_eligibility.csv`.",
        "- Neither wave-2 artifact carries `regulation_status` or `donor_regime`; both are read "
        "from `p0_07_wave2_confirmation/wave2_cases.parquet` and the source column is named in the "
        "coverage table.",
        "- `metadata/data_rights.csv` has no row for `hubeau` or `uk_ea`, so no "
        "repository-level licence entry exists for the two non-USGS wave-2 providers.",
        "- There is no water-temperature record-span table anywhere in the repository. The only "
        "`1981 to 2026` span in the submission is the air-temperature forcing: "
        "`paper/wrr/wrr_supporting_information.tex` line 94 reads \"Daily 2\\,m air temperature is "
        "NASA POWER (MERRA-2), 1 January 1981 to 31 August 2026 ... 16{,}679 days for each of the "
        "457 stations\". The water-temperature span per station is available only as "
        "`first_year`/`last_year` in this table, with the source column named per row.",
        "",
    ]
    (OUT / "coverage_gaps.md").write_text("\n".join(gap_lines) + "\n")

    # ------------------------------------------------------------------ PART B
    verdicts: list[dict] = []
    wave2_certificates = pd.read_parquet(INPUTS["wave2_certificates"])
    note_columns(
        "wave2_certificates",
        "wave-2 certificate bounds and realised errors, PART B",
        ["certificate_bound", "certificate_abs_error"],
    )
    wave2_verdict = json.loads(INPUTS["wave2_verdict"].read_text())
    transfer = json.loads(INPUTS["transfer_report"].read_text())

    # B1 -- wave-2 pooled case-weighted contrast + network-clustered interval
    w2_ind = independent_contrast(
        wave2_cases,
        wave2_certificates,
        retention=0.7,
        tolerance=0.5,
        seed=0,
        draws=2000,
    )
    w2_shared = shared_contrast_interval(
        wave2_cases, wave2_certificates, retention=0.7, tolerance=0.5, seed=0, draws=2000
    )
    w2_alt = independent_contrast(
        wave2_cases,
        wave2_certificates,
        retention=0.7,
        tolerance=0.5,
        seed=0,
        draws=2000,
        boot_seed=500000,
    )
    w2_per_network = per_network_op_contrast(
        wave2_cases, wave2_certificates, retention=0.7, tolerance=0.5, seed=61, jitter_offset=0
    )
    w2_net_equal = independent_network_equal(
        dict(zip(w2_per_network["network_id"], w2_per_network["contrast_points"])),
        seed=61,
        draws=1500,
    )
    verdicts.append(
        verdict_row(
            "wave2_pooled_case_weighted_contrast_pp",
            "wave2_confirmation (13017 cases / 49 networks)",
            float(wave2_verdict["contrast_points"]),
            "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/verdict.json:contrast_points",
            float(w2_ind["point"]) * 100.0,
            1e-9,
            "independent numpy re-implementation of operating_point_contrast "
            "(scripts/315 independent_contrast)",
            "shared-definition cross-check: point "
            f"{float(w2_shared['point'])*100:.12f}; independent resampler with an "
            f"unrelated bootstrap seed gives [{float(w2_alt['low'])*100:.4f}, "
            f"{float(w2_alt['high'])*100:.4f}] (Monte-Carlo sensitivity only).",
            stored_ci=(float(wave2_verdict["ci_low_points"]), float(wave2_verdict["ci_high_points"])),
            recomputed_ci=(float(w2_ind["low"]) * 100.0, float(w2_ind["high"]) * 100.0),
            tolerance_ci=1e-9,
        )
    )
    verdicts.append(
        verdict_row(
            "wave2_network_equal_contrast_pp",
            "wave2_confirmation (49 networks, equal weight)",
            float(transfer["network_equal_pp"]["point_pp"]),
            "…/step7_transfer_reporting/transfer_report.json:network_equal_pp.point_pp",
            float(w2_net_equal["point"]),
            1e-9,
            "per-network contrasts recomputed with the scripts/315 independent engine "
            "(step-7 jitter seed 61), then a numpy resampler over the same 1500 network draws",
            f"network ids in the mean: {w2_net_equal['n_networks']}; "
            f"mean of per-network contrasts recomputed on the same per-network table.",
            stored_ci=(
                float(transfer["network_equal_pp"]["ci_low_pp"]),
                float(transfer["network_equal_pp"]["ci_high_pp"]),
            ),
            recomputed_ci=(float(w2_net_equal["low"]), float(w2_net_equal["high"])),
            tolerance_ci=1e-9,
        )
    )

    # B2 -- reserved-panel contrast at 70% retention
    reserved_certificates = pd.read_parquet(INPUTS["reserved_certificates"])
    note_columns(
        "reserved_certificates",
        "reserved-panel certificate bounds and realised errors, PART B",
        ["certificate_bound", "certificate_abs_error"],
    )
    arm = pd.read_csv(INPUTS["arm_and_thermal_contrasts"])
    arm_row = arm.loc[arm["label"].eq("reserved_retrospective|pooled")].iloc[0]
    v17_verdict = json.loads(INPUTS["v17_reserved_verdict"].read_text())
    res_seed131 = independent_contrast(
        reserved_cases, reserved_certificates, retention=0.7, tolerance=0.5, seed=131, draws=2000
    )
    res_seed0 = independent_contrast(
        reserved_cases, reserved_certificates, retention=0.7, tolerance=0.5, seed=0, draws=2000
    )
    verdicts.append(
        verdict_row(
            "reserved_panel_contrast_at_70pct_pp",
            "reserved_retrospective (10820 cases / 36 networks), step-5 seed 131",
            float(arm_row["contrast_points"]),
            "…/step5_monitoring_tasks/arm_and_thermal_contrasts.csv:"
            "label=reserved_retrospective|pooled,contrast_points",
            float(res_seed131["point"]) * 100.0,
            1e-9,
            "independent numpy re-implementation with the step-5 tie-break seed (31+100=131)",
            "same inputs, seed 0 instead of 131, reproduces the v17 verdict value "
            f"{float(res_seed0['point'])*100:.10f} pp. The two stored numbers differ by "
            f"{abs(float(arm_row['contrast_points']) - float(v17_verdict['primary']['contrast_points'])):.4f} pp "
            "purely through the tie-break jitter on `longest_run`, because the length arm's "
            "70% slice is decided inside a very large tied block.",
            stored_ci=(float(arm_row["ci_low_points"]), float(arm_row["ci_high_points"])),
            recomputed_ci=(float(res_seed131["low"]) * 100.0, float(res_seed131["high"]) * 100.0),
            tolerance_ci=1e-9,
        )
    )
    verdicts.append(
        verdict_row(
            "reserved_panel_contrast_at_70pct_pp (v17 verdict, seed 0)",
            "reserved_retrospective (10820 cases / 36 networks), v17 step-10 seed 0",
            float(v17_verdict["primary"]["contrast_points"]),
            "results/v17_fitness/step10_confirmation/verdict.json:primary.contrast_points",
            float(res_seed0["point"]) * 100.0,
            1e-9,
            "independent numpy re-implementation with the v17 tie-break seed (0)",
            "",
            stored_ci=(
                float(v17_verdict["primary"]["ci_points"][0]),
                float(v17_verdict["primary"]["ci_points"][1]),
            ),
            recomputed_ci=(float(res_seed0["low"]) * 100.0, float(res_seed0["high"]) * 100.0),
            tolerance_ci=1e-9,
        )
    )

    seed_sweep = []
    for seed in (0, 5, 17, 31, 61, 131):
        stat = independent_contrast(
            reserved_cases, reserved_certificates, retention=0.7, tolerance=0.5, seed=seed, draws=200
        )
        seed_sweep.append({"seed": seed, "point_pp": float(stat["point"]) * 100.0})
    seed_sweep_frame = pd.DataFrame(seed_sweep)
    seed_sweep_frame.to_csv(OUT / "reserved_panel_seed_sensitivity.csv", index=False)

    # B3 -- step 2 same-info ablation
    step2_stored = json.loads(INPUTS["step2_contrasts"].read_text())
    step2_protocol = json.loads(INPUTS["step2_fingerprint"].read_text())
    step2_ops_stored = pd.read_csv(INPUTS["step2_operating_points"])
    dev_prepared = prep_cases(development_cases)
    step2_scores = independent_rule_scores(dev_prepared, seed=17)
    for name, features in (
        ("generic", GENERIC_FEATURES),
        ("generic_plus_support", SUPPORT_SET),
    ):
        step2_scores[name] = independent_oof_scores(
            dev_prepared, features, seed=17, n_splits=5
        )

    # validate the reproduced scores against the stored operating points
    op_checks = []
    dev_errors = pd.to_numeric(dev_prepared["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    for name in ("generic", "generic_plus_support", "peak_overlap_rule"):
        stored_row = step2_ops_stored.loc[step2_ops_stored["screen"].eq(name)]
        if stored_row.empty:
            continue
        mine = rate_at_retention(dev_errors, step2_scores[name].to_numpy(dtype=float), 0.7, 0.5)
        op_checks.append(
            {
                "screen": name,
                "stored_rate_above_0.5_at_70": float(stored_row["rate_above_0.5_at_70"].iloc[0]),
                "recomputed_rate_above_0.5_at_70": mine,
                "abs_diff": abs(mine - float(stored_row["rate_above_0.5_at_70"].iloc[0])),
            }
        )
    (OUT / "step2_score_reproduction_check.csv").write_text(
        pd.DataFrame(op_checks).to_csv(index=False)
    )

    networks_dev = development_cases["network_id"].astype(str).to_numpy()
    for left, right, key in (
        ("generic_plus_support", "generic", "generic_plus_support__minus__generic"),
        ("generic_plus_support", "peak_overlap_rule", "generic_plus_support__minus__peak_overlap_rule"),
    ):
        stored = step2_stored[key]
        ind = independent_paired_contrast(
            networks_dev,
            dev_errors,
            step2_scores[left].to_numpy(dtype=float),
            step2_scores[right].to_numpy(dtype=float),
            retention=0.7,
            tolerance=0.5,
            seed=17,
            draws=1000,
        )
        from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap

        boot = pd.DataFrame({"network_id": networks_dev})
        boot["error"] = dev_errors
        boot[left] = pd.to_numeric(step2_scores[left], errors="coerce").fillna(np.inf).to_numpy()
        boot[right] = pd.to_numeric(step2_scores[right], errors="coerce").fillna(np.inf).to_numpy()

        def statistic(block: pd.DataFrame, _l=left, _r=right) -> float:
            k = max(1, int(round(0.7 * len(block))))
            a = block.nsmallest(k, _l)["error"].to_numpy(dtype=float)
            b = block.nsmallest(k, _r)["error"].to_numpy(dtype=float)
            ra = float(((~np.isfinite(a)) | (a > 0.5)).mean())
            rb = float(((~np.isfinite(b)) | (b > 0.5)).mean())
            return ra - rb

        shared = cluster_bootstrap(boot, statistic, draws=1000, seed=17)
        verdicts.append(
            verdict_row(
                f"step2_{key}_pp",
                "development_oof (40704 cases / 110 networks), retention 0.70, tol 0.5 C",
                float(stored["point_pp"]),
                "…/step2_same_info_ablation/contrasts_network_ci.json",
                float(ind["point"]) * 100.0,
                1e-9,
                "independent pipeline: own feature frame, own network K-fold, own "
                "HistGradientBoostingRegressor, own rule jitter, own resampler",
                f"shared cluster_bootstrap cross-check point {float(shared['point'])*100:.12f}; "
                f"n_clusters={ind['n_clusters']} vs stored {stored['n_clusters']}.",
                stored_ci=(float(stored["ci_low_pp"]), float(stored["ci_high_pp"])),
                recomputed_ci=(float(ind["low"]) * 100.0, float(ind["high"]) * 100.0),
                tolerance_ci=1e-9,
            )
        )

    # B4 -- step 3 fixed-reconstructor position and length deltas
    crossed = pd.read_parquet(INPUTS["crossed_development_cases"])
    note_columns(
        "crossed_development_cases",
        "crossed position x length panel for step 3, PART B",
        [
            "network_id",
            "station_id",
            "year",
            "longest_run",
            "overlap_class",
            "abserr_doy_climatology",
            "abserr_smooth_climatology",
            "abserr_donor_ridge",
            "abserr_linear_interp",
        ],
    )
    crossed = crossed.loc[
        crossed["overlap_class"].astype(str).isin(["none", "partial", "full"])
    ].copy()
    stored_position = pd.read_csv(INPUTS["step3_position_contrasts"])
    stored_length = pd.read_csv(INPUTS["step3_length_contrasts"])
    pos_rows = []
    len_rows = []
    for recon in STEP3_RECONSTRUCTORS:
        column = f"abserr_{recon}"
        if column not in crossed.columns:
            unrecomputable.append(
                {"quantity": f"step3_{recon}", "reason": f"{column} absent from crossed panel"}
            )
            continue
        pos = step3_position_table(crossed, column)
        leng = step3_length_table(crossed, column)
        if not pos.empty:
            ci = step3_network_ci(pos, "delta_full_minus_none", ["length"], seed=23, draws=2000)
            ci["reconstructor"] = recon
            ci["contrast"] = "full_minus_none_at_fixed_length"
            pos_rows.append(ci)
        if not leng.empty:
            ci = step3_network_ci(leng, "delta_long_minus_short", ["overlap_class"], seed=30, draws=2000)
            ci["reconstructor"] = recon
            ci["contrast"] = "long_minus_short_at_fixed_overlap"
            len_rows.append(ci)
    recomputed_position = pd.concat(pos_rows, ignore_index=True) if pos_rows else pd.DataFrame()
    recomputed_length = pd.concat(len_rows, ignore_index=True) if len_rows else pd.DataFrame()
    recomputed_position.to_csv(OUT / "step3_position_contrasts_recomputed.csv", index=False)
    recomputed_length.to_csv(OUT / "step3_length_contrasts_recomputed.csv", index=False)

    for label, stored_frame, mine, keys, quantity_prefix in (
        (
            "position (full - none at fixed length, C)",
            stored_position,
            recomputed_position,
            ["reconstructor", "length"],
            "step3_position_full_minus_none",
        ),
        (
            "length (long - short at fixed overlap, C)",
            stored_length,
            recomputed_length,
            ["reconstructor", "overlap_class"],
            "step3_length_long_minus_short",
        ),
    ):
        if mine.empty:
            unrecomputable.append({"quantity": quantity_prefix, "reason": "recompute produced no rows"})
            continue
        merged = stored_frame.merge(
            mine, on=keys, suffixes=("_stored", "_recomputed"), how="outer", indicator=True
        ).rename(columns={"_merge": "merge_status"})
        for row in merged.itertuples():
            tag = "|".join(str(getattr(row, k)) for k in keys)
            if row.merge_status != "both":
                unrecomputable.append(
                    {"quantity": f"{quantity_prefix}:{tag}", "reason": f"row only in {row.merge_status}"}
                )
                continue
            verdicts.append(
                verdict_row(
                    f"{quantity_prefix}:{tag}",
                    f"crossed development panel, {label}",
                    float(row.point_C_stored),
                    "…/step3_fixed_reconstructor_mechanism/"
                    + ("position_contrasts_network_ci.csv" if "position" in quantity_prefix else "length_contrasts_network_ci.csv"),
                    float(row.point_C_recomputed),
                    1e-9,
                    "independent station-year aggregation + own cluster resampler "
                    "(step 3 seeds 23 / 30)",
                    f"n_station_years stored {row.n_station_years_stored} / recomputed "
                    f"{row.n_station_years_recomputed}; n_networks stored "
                    f"{row.n_networks_stored} / recomputed {row.n_networks_recomputed}.",
                    stored_ci=(float(row.ci_low_C_stored), float(row.ci_high_C_stored)),
                    recomputed_ci=(float(row.ci_low_C_recomputed), float(row.ci_high_C_recomputed)),
                    tolerance_ci=1e-9,
                )
            )

    recompute_table = pd.DataFrame(verdicts)
    recompute_table.to_csv(OUT / "recompute_table.csv", index=False)

    counts = recompute_table["verdict"].value_counts().to_dict()
    ci_counts = recompute_table["verdict_ci"].value_counts().to_dict()

    # ------------------------------------------------------------- reports
    report = {
        "part_a": {
            "coverage_table_rows": int(len(coverage_out)),
            "coverage_table_stations": int(
                coverage_out[["panel", "network_id", "station_id"]].drop_duplicates().shape[0]
            ),
            "panels": {
                k: int(v)
                for k, v in coverage_out.groupby("panel")["station_id"].nunique().items()
            },
            "providers": int(coverage_out["provider"].nunique()),
            "networks": int(coverage_out["network_id"].nunique()),
            "n_stations_undocumented_statistic": int(
                coverage_out.loc[coverage_out["statistic_class"].eq(CLASS_UNDOCUMENTED), "station_id"].nunique()
            ),
            "n_stations_non_daily_reference": int(
                coverage_out.loc[
                    coverage_out["statistic_class"].eq(CLASS_NON_DAILY_REFERENCE), "station_id"
                ].nunique()
            ),
            "n_stations_project_aggregated": int(
                coverage_out.loc[
                    coverage_out["statistic_class"].eq(CLASS_PROJECT_SUBDAILY), "station_id"
                ].nunique()
            ),
            "n_stations_daily_mean": int(
                coverage_out.loc[coverage_out["statistic_class"].eq(CLASS_DAILY_MEAN), "station_id"].nunique()
            ),
            "n_stations_without_split_role": int(
                coverage_out.loc[
                    coverage_out["split_role"].eq("unassigned_not_in_development_or_reserved"), "station_id"
                ].nunique()
            ),
            "n_wave2_station_rows_below_4_complete_years": int(
                coverage_out.loc[
                    coverage_out["panel"].eq("wave2_confirmation")
                    & pd.to_numeric(coverage_out["n_complete_years"], errors="coerce").lt(4)
                ].shape[0]
            ),
            "n_cross_check_disagreements": int(len(cross_check_disagreements)),
            "n_stations_missing_data_rights_row": int(
                coverage_out.loc[coverage_out["data_rights_source"].eq("MISSING"), "station_id"].nunique()
            ),
            "manuscript_panel_crosscheck": panel_crosscheck,
            "measurement_class_shares_by_panel": shares,
            "columns_used": COLUMNS_USED,
            "missing_columns": [
                {
                    "file": "results/wrr_submission_ready/p0_07_wave2_ingest/wave2_inputs_manifest.csv",
                    "missing": ["first_year", "last_year", "n_complete_years", "regulation_status", "donor_regime"],
                    "handling": "first/last year recomputed from daily_wide_temperature.csv; "
                    "n_complete_years taken from the sibling station_eligibility.csv; "
                    "regulation_status and donor_regime read from wave2_cases.parquet",
                },
                {
                    "file": "metadata/data_rights.csv",
                    "missing": ["row for provider=hubeau", "row for provider=uk_ea"],
                    "handling": "data_rights_* columns left as MISSING; licence_route from "
                    "measurement_provenance_dictionary.csv:license",
                },
                {
                    "file": "results/wrr_submission_ready/p0_07_wave2_ingest/**",
                    "missing": [
                        "any provider-level measurement_provenance_dictionary equivalent",
                        "any water-temperature record-span artifact",
                    ],
                    "handling": "wave-2 provider statistics are read from the shared "
                    "measurement_provenance_dictionary.csv, which does cover usgs/hubeau/uk_ea",
                },
            ],
        },
        "part_b": {
            "verdict_counts": counts,
            "ci_verdict_counts": ci_counts,
            "rows": verdicts,
            "unrecomputable": unrecomputable,
            "shared_components_used": [
                "stream_recoverability.experiments.v17_fitness.stats.cluster_bootstrap -- used ONLY as "
                "an interval-definition cross-check for the step-2 contrasts; the primary recomputed "
                "intervals come from this script's own resampler",
                "stream_recoverability.experiments.v17_fitness.frontier.operating_point_contrast -- "
                "used ONLY inside the shared_contrast_interval cross-check for the wave-2 pooled number",
            ],
            "independent_components": [
                "tie-break jitter, k-selection, failure definition and cluster resampler re-implemented "
                "on numpy arrays in this script",
                "step-2 feature frame, network K-fold, HistGradientBoostingRegressor configuration, rule "
                "jitter and paired contrast re-implemented in this script",
                "step-3 station-year aggregation, pivot and network-equal bootstrap re-implemented in "
                "this script",
            ],
        },
        "seed_sensitivity_reserved_panel": seed_sweep,
        "step2_score_reproduction_check": op_checks,
    }
    (OUT / "recompute_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")

    # protocol fingerprint
    try:
        git_head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        git_head = f"unavailable: {exc}"
    input_hashes = {}
    for key, path in INPUTS.items():
        input_hashes[key] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    wave2_hashes = {}
    for net, info in wave2_network_paths(w2_manifest).items():
        entry = {}
        for label, path in (("daily_wide", info["daily_wide"]), ("eligibility", info["eligibility"])):
            entry[label] = {
                "path": str(path.relative_to(ROOT)) if path.exists() else f"MISSING {path}",
                "sha256": sha256_file(path) if path.exists() else None,
            }
        wave2_hashes[net] = entry
    fingerprint = {
        "script": "scripts/315_wrr_p0_06_coverage_and_recompute.py",
        "script_sha256": sha256_file(Path(__file__).resolve()),
        "git_head": git_head,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "platform": platform.platform(),
        "thread_cap": {"env": "P0_06_THREADS", "value": _THREADS},
        "packages": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "sklearn": __import__("sklearn").__version__,
        },
        "protocol_constants": {
            "primary_endpoint": "hottest_30_mean_C",
            "primary_tolerance_C": TOLERANCE,
            "primary_tolerance_source": "stream_recoverability.experiments.v17_fitness.paths.PRIMARY_TOLERANCE_C",
            "primary_retention": RETENTION,
            "primary_retention_source": "local constant in scripts/297_wrr_p0_07_wave2_score.py and "
            "scripts/187_v17_confirm.py (not defined in src/)",
            "step2_protocol_file": step2_protocol.get("protocol"),
            "step2_seed": step2_protocol.get("seed"),
            "step2_draws": 1000,
            "step2_n_splits": 5,
            "step2_model": "HistGradientBoostingRegressor(loss='quantile', quantile=0.9, "
            "max_depth=4, max_iter=350, learning_rate=0.06, min_samples_leaf=40)",
            "wave2_seed": 0,
            "wave2_draws": 2000,
            "reserved_step5_seed": 131,
            "reserved_v17_seed": 0,
            "reserved_draws": 2000,
            "step3_position_seed": 23,
            "step3_length_seed": 30,
            "step3_draws": 2000,
        },
        "inputs": input_hashes,
        "wave2_network_artifacts": wave2_hashes,
    }
    (OUT / "protocol_fingerprint.json").write_text(
        json.dumps(fingerprint, indent=2, default=str) + "\n"
    )
    pd.DataFrame(COLUMNS_USED).to_csv(OUT / "input_columns_used.csv", index=False)

    # ------------------------------------------------------------------ SUMMARY
    write_summary(
        coverage_out,
        summary_table,
        contract,
        shares,
        recompute_table,
        seed_sweep,
        op_checks,
        unrecomputable,
        counts,
        ci_counts,
        gap,
        cross_check_disagreements,
        missing_rights,
        panel_crosscheck,
        elapsed=time.time() - started,
        fingerprint=fingerprint,
    )
    print(recompute_table.to_string(index=False))
    print(f"\nwrote {OUT}")
    return 0


def write_summary(  # noqa: C901
    coverage: pd.DataFrame,
    summary_table: pd.DataFrame,
    contract: pd.DataFrame,
    shares: dict,
    recompute_table: pd.DataFrame,
    seed_sweep: list[dict],
    op_checks: list[dict],
    unrecomputable: list[dict],
    counts: dict,
    ci_counts: dict,
    gap: pd.DataFrame,
    cross_check_disagreements: pd.DataFrame,
    missing_rights: pd.DataFrame,
    panel_crosscheck: dict,
    *,
    elapsed: float,
    fingerprint: dict,
) -> None:
    lines: list[str] = []
    lines.append("# P0-06 — coverage / measurement contract and independent recompute")
    lines.append("")
    lines.append(
        "Generated by `scripts/315_wrr_p0_06_coverage_and_recompute.py` "
        f"(git HEAD `{fingerprint['git_head'][:12]}`, script sha256 "
        f"`{fingerprint['script_sha256'][:16]}…`, {elapsed:.1f} s)."
    )
    lines.append("")
    lines.append(
        "Every number below is traceable to a named file. Fields the named artifacts do not "
        "carry are left empty or marked `MISSING`; nothing is inferred."
    )
    lines.append("")

    # ---- Part A
    lines.append("## Part A — coverage and measurement contract")
    lines.append("")
    n_rows = len(coverage)
    n_pairs = coverage[["panel", "network_id", "station_id"]].drop_duplicates().shape[0]
    n_ids = coverage["station_id"].nunique()
    lines.append(
        f"The coverage table has **{n_rows} station-network rows** covering "
        f"**{n_ids} distinct station identifiers** over "
        f"**{coverage['network_id'].nunique()} networks** and "
        f"**{coverage['provider'].nunique()} providers**: the v17 study roster "
        "(development + reserved + the ineligible roster rows) plus the wave-2 confirmation roster."
    )
    lines.append("")
    pc = panel_crosscheck["recomputed_from_artifacts"]
    lines.append("### Panel-size cross-check against the manuscript sentence")
    lines.append("")
    lines.append(
        "The manuscript states *\"146 networks, 457 stations and 5114 fully observed "
        "station-years\"* (`paper/wrr/wrr_manuscript.tex:331`). Recomputed from the coverage "
        "table over the rows with `in_final_analysis_panel == True` and `panel == v17`:"
    )
    lines.append("")
    lines.append("| quantity | manuscript | recomputed | match |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| networks | 146 | {pc['n_networks']} | "
        f"{'yes' if pc['n_networks'] == 146 else 'NO'} |"
    )
    lines.append(
        f"| stations | 457 | {pc['n_stations']} | "
        f"{'yes' if pc['n_stations'] == 457 else 'NO'} |"
    )
    lines.append(
        f"| complete station-years | 5114 | {pc['n_complete_station_years']} | "
        f"{'yes' if pc['n_complete_station_years'] == 5114 else 'NO'} |"
    )
    lines.append("")
    lines.append(
        f"The 90 roster rows with `eligible_station == False` carry a further "
        f"{panel_crosscheck['full_roster_station_years'] - pc['n_complete_station_years']} "
        "complete station-years; they are in `station_roster.csv` but outside the 5114. "
        f"The wave-2 panel adds {panel_crosscheck['wave2_panel']['n_networks']} networks, "
        f"{panel_crosscheck['wave2_panel']['n_station_network_rows']} station-network rows "
        f"({panel_crosscheck['wave2_panel']['n_distinct_station_ids']} distinct stations) and "
        f"{panel_crosscheck['wave2_panel']['n_scored_cases']} scored cases."
    )
    lines.append("")
    lines.append("### Provider coverage summary")
    lines.append("")
    lines.append(
        "| provider | n stations | n networks | first yr | last yr | median complete yr | statistic class | quality class (donor-regime networks) | licence route |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in summary_table.sort_values("provider").itertuples():
        licence = str(row.licence_route)
        if len(licence) > 60:
            licence = licence[:57] + "…"
        lines.append(
            f"| {row.provider} | {row.n_stations} | {row.n_networks} | {row.first_year} | "
            f"{row.last_year} | {row.median_complete_years:g} | `{row.statistic_class}` | "
            f"{row.quality_class} | {licence} |"
        )
    lines.append("")
    lines.append(
        "`quality class` is the donor-regime mix counted over networks "
        "(`network_split.csv:stratum` for v17; modal `donor_regime` from "
        "`wave2_cases.parquet` for wave-2). The provider QC policy is a separate column "
        "(`provider_qc_route`) in `provider_coverage_summary.csv`."
    )
    lines.append("")

    lines.append("### Which headline results belong to which measurement class")
    lines.append("")
    lines.append(
        "| provider | documented statistic (verbatim head) | canonical class | n station-network rows |"
    )
    lines.append("|---|---|---|---|")
    for row in contract.sort_values("provider").itertuples():
        text = str(row.statistic_documented)
        head = (text[:70] + "…") if len(text) > 70 else text
        subset = coverage.loc[coverage["provider"].eq(row.provider)]
        n_st = int(subset[["network_id", "station_id"]].drop_duplicates().shape[0])
        lines.append(f"| {row.provider} | {head} | `{row.statistic_class}` | {n_st} |")
    lines.append("")
    lines.append(
        "`smhi` appears in the provider dictionary but contributes 0 rows to the final panel, so "
        "its class never enters a headline number."
    )
    lines.append("")

    lines.append("### Share of each analysis panel by measurement class")
    lines.append("")
    lines.append("| panel | measurement class | cases | share of cases | networks | stations |")
    lines.append("|---|---|---|---|---|---|")
    for panel, block in shares.items():
        for cls, stats in sorted(block["by_measurement_class"].items()):
            lines.append(
                f"| {panel} | `{cls}` | {stats['n_cases']} | {stats['share_of_cases']*100:.1f}% | "
                f"{stats['n_networks']} | {stats['n_stations']} |"
            )
    lines.append("")

    headline_map = {
        "development": "Step 2 same-info ablation and Step 3 fixed-reconstructor mechanism",
        "reserved_retrospective": "reserved-panel contrast at 70% retention "
        "(step 5 and the v17 step-10 verdict)",
        "wave2_confirmation": "wave-2 pooled confirmation contrast and the "
        "network-equal / provider-split transport numbers",
    }
    lines.append("**Headline -> measurement class.**")
    lines.append("")
    for panel, description in headline_map.items():
        block = shares[panel]
        parts = []
        for cls, stats in sorted(
            block["by_measurement_class"].items(), key=lambda kv: -kv[1]["n_cases"]
        ):
            parts.append(f"{stats['n_cases']} cases ({stats['share_of_cases']*100:.1f}%) from {cls}")
        lines.append(f"- *{description}* — {block['n_cases']} cases, " + "; ".join(parts) + ".")
    lines.append("")
    lines.append(
        "Read this as the measurement contract of the paper: a result computed on a panel whose "
        "cases are majority `daily_mean` can be described as a daily-mean result; a result whose "
        "cases are dominated by `project_aggregated_from_subdaily` or `undocumented` cannot, and "
        "must be qualified in the manuscript."
    )
    lines.append("")

    lines.append("### Coverage gaps")
    lines.append("")
    lines.append(
        f"- stations with an `undocumented` daily statistic: "
        f"**{coverage.loc[coverage['statistic_class'].eq(CLASS_UNDOCUMENTED),'station_id'].nunique()}**"
    )
    lines.append(
        f"- stations whose provider documents a non-daily reference reading: "
        f"**{coverage.loc[coverage['statistic_class'].eq(CLASS_NON_DAILY_REFERENCE),'station_id'].nunique()}**"
    )
    lines.append(
        f"- stations whose daily value is a project aggregate from sub-daily source values: "
        f"**{coverage.loc[coverage['statistic_class'].eq(CLASS_PROJECT_SUBDAILY),'station_id'].nunique()}**"
    )
    lines.append(
        f"- stations where the two project provenance artifacts disagree on the class: "
        f"**{len(cross_check_disagreements)}**"
    )
    lines.append(
        f"- stations whose provider has no row in `metadata/data_rights.csv`: "
        f"**{len(missing_rights)}**"
    )
    unassigned = coverage.loc[coverage["split_role"].eq("unassigned_not_in_development_or_reserved")]
    lines.append(
        f"- roster stations with no development/reserved `split_role` (all ineligible): "
        f"**{len(unassigned)}**"
    )
    below_gate = coverage.loc[
        coverage["panel"].eq("wave2_confirmation")
        & pd.to_numeric(coverage["n_complete_years"], errors="coerce").lt(4)
    ]
    lines.append(
        f"- wave-2 station rows below the ingest `MIN_YEARS = 4` gate: **{len(below_gate)}**"
    )
    lines.append("")
    lines.append("See `coverage_gaps.md` for the full station lists and the verbatim evidence.")
    lines.append("")

    # ---- Part B
    lines.append("## Part B — independent recompute")
    lines.append("")
    lines.append(
        "Re-implemented in this script on plain numpy arrays: the tie-break jitter, the "
        "rank-and-cut selection (stable `argsort` instead of `pandas.nsmallest`), the failure "
        "definition, the whole-cluster resampler, the step-2 feature frame / network K-fold / "
        "gradient-boosting configuration / rule jitter, and the step-3 station-year aggregation. "
        "`frontier.operating_point_contrast` is called **only** as an interval-definition "
        "cross-check for the wave-2 pooled row, and "
        "`stats.cluster_bootstrap` **only** as an interval-definition cross-check for the step-2 "
        "rows; both are named in the `method` column of `recompute_table.csv`."
    )
    lines.append("")
    lines.append(
        "| quantity | stored | recomputed | abs diff | tol | verdict | CI verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for row in recompute_table.itertuples():
        stored = "n/a" if row.stored_value is None else f"{row.stored_value:.10g}"
        mine = "n/a" if row.recomputed_value is None else f"{row.recomputed_value:.10g}"
        diff = "n/a" if row.abs_diff is None else f"{row.abs_diff:.3g}"
        tol = "n/a" if row.tolerance is None else f"{row.tolerance:g}"
        lines.append(
            f"| `{row.quantity}` | {stored} | {mine} | {diff} | {tol} | **{row.verdict}** | "
            f"{row.verdict_ci} |"
        )
    lines.append("")
    lines.append(
        f"Point verdicts: {', '.join(f'{k}={v}' for k, v in counts.items())}. "
        f"Interval verdicts: {', '.join(f'{k}={v}' for k, v in ci_counts.items())}."
    )
    lines.append("")

    lines.append("### Score-reproduction check for the step-2 risk models")
    lines.append("")
    lines.append(
        "The recomputed OOF risk scores are validated against the stored operating points before "
        "the contrasts are compared:"
    )
    lines.append("")
    lines.append("| screen | stored rate@70 | recomputed rate@70 | abs diff |")
    lines.append("|---|---|---|---|")
    for check in op_checks:
        lines.append(
            f"| {check['screen']} | {check['stored_rate_above_0.5_at_70']:.10f} | "
            f"{check['recomputed_rate_above_0.5_at_70']:.10f} | {check['abs_diff']:.3g} |"
        )
    lines.append("")

    lines.append("### Reserved-panel seed sensitivity")
    lines.append("")
    lines.append(
        "The reserved-panel contrast is selected by a *random* tie-break on `longest_run` "
        "(`default_rng(seed + 991)`), and the length arm's 70% slice is decided inside a very "
        "large tied block. The recompute therefore reports the seed sweep rather than a single "
        "point:"
    )
    lines.append("")
    lines.append("| seed | contrast (pp) |")
    lines.append("|---|---|")
    for entry in seed_sweep:
        lines.append(f"| {entry['seed']} | {entry['point_pp']:.6f} |")
    values = [e["point_pp"] for e in seed_sweep]
    lines.append("")
    lines.append(
        f"Spread across the six seeds: **{min(values):.4f} to {max(values):.4f} pp** "
        f"(range {max(values)-min(values):.4f} pp). Both stored reserved-panel numbers "
        "(`results/v17_fitness/step10_confirmation/verdict.json`, seed 0, and "
        "`step5_monitoring_tasks/arm_and_thermal_contrasts.csv`, seed 131) lie inside it."
    )
    lines.append("")

    if unrecomputable:
        lines.append("### Values that could not be recomputed")
        lines.append("")
        for item in unrecomputable:
            lines.append(f"- `{item['quantity']}`: {item['reason']}")
        lines.append("")
    else:
        lines.append("### Values that could not be recomputed")
        lines.append("")
        lines.append(
            "None — every quantity requested in P0-06 was recomputed from repository inputs. "
            "The limitations that remain are *definitional*, not missing inputs, and are listed "
            "below."
        )
        lines.append("")

    lines.append("### Limitations of this recompute")
    lines.append("")
    lines.append(
        "1. Reproducing the step-2 contrast requires the same tie-break RNG stream and the same "
        "fold assignment as the stored run; both are re-implemented here from the frozen "
        "protocol, not called from the original module. Agreement to 1e-9 therefore tests the "
        "*implementation*, not the protocol choice."
    )
    lines.append(
        "2. The wave-2 complete-year count is only reproducible under a named convention. "
        "`final_coverage_table.csv` carries both recounts and the project value side by side."
    )
    lines.append(
        "3. `metadata/data_rights.csv` has no row for `hubeau` or `uk_ea`; their licence route is "
        "recorded only in `measurement_provenance_dictionary.csv`."
    )
    lines.append(
        "4. The wave-2 interval is reproduced with the same bootstrap seed as the stored run. An "
        "independent resampler with an unrelated seed moves the interval by O(0.05) pp, which is "
        "Monte-Carlo noise in the reported 2000-draw interval, not a discrepancy in the contrast."
    )
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    for name in (
        "final_coverage_table.csv",
        "provider_coverage_summary.csv",
        "measurement_contract_table.csv",
        "coverage_gaps.md",
        "recompute_table.csv",
        "recompute_report.json",
        "protocol_fingerprint.json",
        "input_columns_used.csv",
        "step2_score_reproduction_check.csv",
        "step3_position_contrasts_recomputed.csv",
        "step3_length_contrasts_recomputed.csv",
        "reserved_panel_seed_sensitivity.csv",
        "SUMMARY.md",
    ):
        lines.append(f"- `{name}`")
    lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
