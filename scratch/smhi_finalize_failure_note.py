"""Write the loud, machine-readable failure notice into the ingest root."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi"
ing = json.loads((OUT / "ingest.json").read_text())
verify = json.loads((ROOT / "scratch/smhi_verify_report.json").read_text())
cf = verify["counterfactual_if_uncontrolled_O_were_accepted"]

notice = {
    "provider": "smhi",
    "status": "FAILED_QC_NO_ELIGIBLE_STATIONS",
    "retrieval_utc": ing["retrieval_utc"],
    "n_catalog_stations": ing["n_catalog_stations"],
    "n_downloaded": ing["n_downloaded"],
    "n_download_failures": ing["n_download_failures"],
    "n_stations_with_accepted_G_or_Y_days": ing["n_stations_with_accepted_days"],
    "n_stations_with_ge_4_complete_years": ing["n_stations"],
    "n_networks": ing["n_networks"],
    "n_station_years_complete": ing["n_station_years_complete"],
    "quality_code_rows": ing["qc"]["quality_code_distribution_rows_parsed"],
    "accepted_quality_codes_requested": ing["qc"]["accepted_quality_codes"],
    "loss_fraction": ing["qc"]["loss_fraction_of_parsed_rows"],
    "cause": ing["failure"]["cause"],
    "not_substituted": ing["failure"]["not_substituted"],
    "diagnostic_only_if_O_were_accepted": {
        "note": cf["label"],
        "n_stations_with_ge_4_complete_years": cf["n_stations_with_ge_4_complete_years"],
        "n_networks_with_ge_2_such_stations": cf["n_networks_with_ge_2_such_stations"],
        "n_complete_station_years": cf["n_complete_station_years"],
        "evidence_paths": [
            "scratch/smhi_verify_counterfactual_station_years.csv",
            "scratch/smhi_verify_counterfactual_networks.csv",
        ],
        "requires": "explicit coordinator decision to change the QC rule; the ingest script "
                    "has no flag for it and the frozen protocol/minimum-year rules are untouched",
    },
    "independent_verification": {
        "script": "scratch/smhi_verify_smhi_ingest.py",
        "report": "scratch/smhi_verify_report.json",
        "cross_check_mismatches": verify["cross_check_mismatches"],
        "n_stations_with_bad_sha256": verify["n_stations_with_bad_sha256"],
        "rescan_quality_codes": verify["independent_rescan"]["quality_code_counts"],
        "rescan_rows": verify["independent_rescan"]["n_rows_total"],
        "rescan_earliest": verify["independent_rescan"]["earliest_date_seen"],
        "rescan_latest": verify["independent_rescan"]["latest_date_seen"],
    },
}
(OUT / "INGEST_STATUS.json").write_text(json.dumps(notice, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(notice, indent=2, ensure_ascii=False))
