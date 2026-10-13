"""Refresh INGEST_STATUS.json: preserve the strict-gate record, add the emitted stratum."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi"
ing = json.loads((OUT / "ingest.json").read_text())
verify = json.loads((ROOT / "scratch/smhi_verify_emitted_report.json").read_text())
prior = json.loads((ROOT / "scratch/smhi_prior_use_scan.json").read_text())
old = json.loads((OUT / "INGEST_STATUS.json").read_text()) if (OUT / "INGEST_STATUS.json").is_file() else {}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

strict = old.get("strict_gate", {k: old.get(k) for k in (
    "retrieval_utc", "n_downloaded", "n_stations_with_accepted_G_or_Y_days",
    "n_stations_with_ge_4_complete_years", "n_networks", "n_station_years_complete",
    "quality_code_rows", "cause", "not_substituted")})
strict["record_file"] = "QC_AND_ELIGIBILITY_FAILURE.md (retained unchanged)"

notice = {
    "provider": "smhi",
    "status": "EMITTED_UNDER_AMENDMENT_2_STRATUM",
    "qc_stratum": ing["qc_stratum"],
    "retrieval_utc": ing["retrieval_utc"],
    "command": ing["command"],
    "strict_gate": strict,
    "amended_stratum": {
        "name": ing["qc_stratum"],
        "accepted_quality_codes": ing["qc"]["accepted_quality_codes"],
        "amendment": ing["stratum_provenance"]["amendment"],
        "n_catalog_stations": ing["n_catalog_stations"],
        "n_downloaded": ing["n_downloaded"],
        "n_download_failures": ing["n_download_failures"],
        "n_networks": ing["n_networks"],
        "n_stations_emitted": ing["n_stations_emitted"],
        "n_stations_emitted_ge_4_complete_years": ing["n_stations_emitted_ge_4_complete_years"],
        "n_stations_ge_4_complete_years_provider_wide": ing["n_stations"],
        "n_complete_station_years": ing["n_complete_station_years"],
        "n_complete_station_years_stations_ge_4_years": ing["n_complete_station_years_stations_ge_4_years"],
        "n_complete_station_years_in_emitted_networks": ing["n_complete_station_years_in_emitted_networks"],
        "n_stations_ge_4_years_not_in_emitted_networks": ing["n_stations_ge_4_years_not_in_emitted_networks"],
        "n_complete_station_years_not_in_emitted_networks": ing["n_complete_station_years_not_in_emitted_networks"],
        "n_rows_parsed": ing["counts"]["n_rows_parsed"],
        "n_rows_accepted": ing["counts"]["n_rows_accepted"],
        "n_rows_dropped": ing["counts"]["n_rows_dropped"],
    },
    "independent_verification": {
        "strict_gate_script": "scratch/smhi_verify_smhi_ingest.py",
        "strict_gate_report": "scratch/smhi_verify_report.json",
        "emitted_panel_script": "scratch/smhi_verify_emitted_panels.py",
        "emitted_panel_report": "scratch/smhi_verify_emitted_report.json",
        "emitted_panels_ok": verify["ok"],
        "problems": verify["problems"],
        "claim_vs_recomputed_mismatches": verify["claim_vs_recomputed"]["mismatches"],
        "stations_csv_sha256": verify["stations_csv"]["sha256"],
    },
    "prior_use_scan": {
        "scope": "repo-wide scan of CSVs with a station_id column under results/ and metadata/ "
                 "(excluding multi_agency_ingest and run dirs); scripts/245 remains authoritative",
        **prior,
    },
    "artifacts_retained": [
        "QC_AND_ELIGIBILITY_FAILURE.md", "QC_legend_verbatim.json", "networks_not_eligible.csv",
        "raw_cache_manifest.csv", "stations_all.csv", "station_years.csv", "README.md", "ingest.json",
    ],
}
(OUT / "INGEST_STATUS.json").write_text(json.dumps(notice, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(notice["amended_stratum"], indent=2, ensure_ascii=False))
print("stations.csv sha256:", notice["independent_verification"]["stations_csv_sha256"])
