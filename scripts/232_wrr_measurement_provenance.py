#!/usr/bin/env python3
"""P0-02/F09: build station-level measurement provenance from parser contracts.

Does not invent sensor protocols. Marks each station with what the acquisition
code actually requests, and flags providers where daily mean is unproven.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.wrr_submission_ready.run_identity import (  # noqa: E402
    run_fail_closed,
)

OUT = ROOT / "results" / "wrr_submission_ready"
ROSTER = ROOT / "results" / "v17_fitness" / "step1_panel" / "station_roster.csv"

# Evidence is the acquisition contract in src/stream_recoverability/data/.
PROVIDER_CONTRACT = {
    "usgs": {
        "native_statistic_requested": "NWIS DV parameterCd=00010 statCd=00003 (daily mean)",
        "statistic_class": "daily_mean",
        "statistic_proven_for_panel": "true_by_request_contract",
        "day_boundary": "USGS NWIS local site day (provider)",
        "qa_retained": "approval_status filtered in confirmatory pipelines; panel CSV may be pre-aggregated",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/nwis_temperature.py",
    },
    "nve_hydapi": {
        "native_statistic_requested": "HydAPI Parameter 1003, resTime=1440 measured river series",
        "statistic_class": "daily_mean",
        "statistic_proven_for_panel": "true_by_request_contract",
        "day_boundary": "NVE series timestamps (provider)",
        "qa_retained": "quality 2/3 correction 0 only per data_rights note",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/nve_water_temperature.py",
    },
    "rws_waterwebservices": {
        "native_statistic_requested": "raw observations aggregated to daily mean in project parser",
        "statistic_class": "daily_mean_from_raw",
        "statistic_proven_for_panel": "true_by_parser_aggregation",
        "day_boundary": "parser calendar day (verify timezone)",
        "qa_retained": "location catalog filters; raw qualifiers partially retained",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/rws_temperature.py",
    },
    "syke": {
        "native_statistic_requested": "OData LampoPintavesi Arvo; grouped mean per timestamp date",
        "statistic_class": "unknown_may_be_morning_reference",
        "statistic_proven_for_panel": "false",
        "day_boundary": "naive date from Aika timestamp",
        "qa_retained": "published_no_flag_field",
        "include_in_unified_daily_mean_main": False,
        "source_module": "src/stream_recoverability/data/syke_surface_temperature.py",
        "notes": (
            "Vesi.fi documents a morning nearshore reference reading for lake/river "
            "day values; do not pool SYKE as proven 24h means without station proof."
        ),
    },
    "arso": {
        "native_statistic_requested": "ARSO HIDARHIV daily river archive values as ingested",
        "statistic_class": "provider_daily_unverified_definition",
        "statistic_proven_for_panel": "unverified",
        "day_boundary": "unverified",
        "qa_retained": "provider publication; redistribution terms unverified",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/arso_temperature.py",
        "notes": "Kept in main analysis pending product-code audit; flagged unverified.",
    },
    "chmi": {
        "native_statistic_requested": "CHMI hydrological temperature tables as ingested",
        "statistic_class": "provider_daily_unverified_definition",
        "statistic_proven_for_panel": "unverified",
        "day_boundary": "unverified",
        "qa_retained": "provider publication; redistribution terms unverified",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/chmi_temperature.py",
    },
    "foen": {
        "native_statistic_requested": "FOEN water-observation service as ingested",
        "statistic_class": "provider_daily_unverified_definition",
        "statistic_proven_for_panel": "unverified",
        "day_boundary": "unverified",
        "qa_retained": "provider publication; redistribution terms unverified",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/foen_sealed_corpus.py",
    },
    "gkd_bayern": {
        "native_statistic_requested": "GKD Bayern official downloads as ingested",
        "statistic_class": "provider_daily_unverified_definition",
        "statistic_proven_for_panel": "unverified",
        "day_boundary": "unverified",
        "qa_retained": "provider publication; redistribution terms unverified",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/gkd_bayern_temperature.py",
    },
    "lubw": {
        "native_statistic_requested": "LUBW session workbook values as ingested",
        "statistic_class": "provider_daily_unverified_definition",
        "statistic_proven_for_panel": "unverified",
        "day_boundary": "unverified",
        "qa_retained": "provider publication; redistribution terms unverified",
        "include_in_unified_daily_mean_main": True,
        "source_module": "src/stream_recoverability/data/lubw_temperature.py",
    },
}


def work(directory: Path, manifest) -> list[Path]:
    roster = pd.read_csv(ROSTER)
    rows = []
    for r in roster.itertuples():
        contract = PROVIDER_CONTRACT.get(
            str(r.provider),
            {
                "native_statistic_requested": "unknown",
                "statistic_class": "unknown",
                "statistic_proven_for_panel": "unverified",
                "day_boundary": "unverified",
                "qa_retained": "unknown",
                "include_in_unified_daily_mean_main": False,
                "source_module": "",
            },
        )
        rows.append(
            {
                "network_id": r.network_id,
                "station_id": r.station_id,
                "provider": r.provider,
                "split_role": r.split_role,
                **contract,
            }
        )
    frame = pd.DataFrame(rows)
    station_path = OUT / "measurement_provenance_stations.csv"
    provider_path = OUT / "measurement_provenance.csv"
    frame.to_csv(station_path, index=False)

    provider = (
        frame.groupby("provider", as_index=False)
        .agg(
            n_stations=("station_id", "nunique"),
            n_networks=("network_id", "nunique"),
            statistic_class=("statistic_class", "first"),
            statistic_proven_for_panel=("statistic_proven_for_panel", "first"),
            include_in_unified_daily_mean_main=("include_in_unified_daily_mean_main", "first"),
            native_statistic_requested=("native_statistic_requested", "first"),
        )
    )
    provider.to_csv(provider_path, index=False)

    excluded = frame.loc[~frame["include_in_unified_daily_mean_main"]]
    summary = {
        "n_stations": int(len(frame)),
        "n_excluded_from_unified_daily_mean_main": int(excluded["station_id"].nunique()),
        "excluded_providers": sorted(excluded["provider"].unique().tolist()),
        "failure_shoukou": (
            "SYKE stations must not remain in a unified daily-mean main analysis "
            "until station-level proof exists; manuscript Methods should state the "
            "exclusion or sensitivity stratum."
        ),
    }
    summary_path = OUT / "measurement_provenance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    for path in (station_path, provider_path, summary_path):
        (directory / path.name).write_bytes(path.read_bytes())
    print(json.dumps(summary, indent=2))
    return [directory / p.name for p in (station_path, provider_path, summary_path)]


def main() -> None:
    run_fail_closed("P0-02/F09 measurement provenance", work, inputs=[ROSTER])


if __name__ == "__main__":
    main()
