#!/usr/bin/env python3
"""P1 alignment check and P2 boundary note. Does not refit the learning curves."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.independence import (  # noqa: E402
    eligibility_row,
    independence_table,
    overlap_pairs,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    STEP4_CEILING,
    STEP10_CONFIRM,
)

OUT = ROOT / "results" / "wrr_submission_ready" / "major_revision_20261019" / "p1_p2_boundaries"


def _ids(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path, columns=["network_id", "station_id", "year"])
    frame["network_id"] = frame["network_id"].astype(str)
    frame["station_id"] = frame["station_id"].astype(str)
    return frame


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dev = _ids(STEP4_CEILING / "development_cases.parquet")
    reserved = _ids(STEP10_CONFIRM / "reserved_cases.parquet")
    dev_table = independence_table(dev)
    reserved_table = independence_table(reserved)
    dev_stations = set(dev["station_id"])
    reserved_stations = set(reserved["station_id"])
    shared_stations = sorted(dev_stations & reserved_stations)
    dev_pairs = overlap_pairs(dev_table)
    reserved_pairs = overlap_pairs(reserved_table)
    payload = {
        "development": eligibility_row("development", dev, dev_table),
        "reserved": eligibility_row("reserved", reserved, reserved_table),
        "stations_shared_by_development_and_reserved": shared_stations,
        "n_development_overlap_pairs": int(len(dev_pairs)),
        "n_reserved_overlap_pairs": int(len(reserved_pairs)),
        "learning_curves": (
            "scripts/316 repeats training-network draws on development network labels. "
            "Those draws are not independence groups, and the interval across draws is "
            "training-sample variation on a fixed test panel, not a new-basin interval."
        ),
        "phase_residuals": (
            "scripts/317 scores the phase and air-temperature boundary on development "
            "networks. It remains a mechanism check for the hottest-30 endpoint. It is "
            "not evidence that the fitted risk score is necessary, and it is not recomputed "
            "here."
        ),
    }
    (OUT / "p1_alignment.json").write_text(json.dumps(payload, indent=2) + "\n")
    dev_table.to_csv(OUT / "development_independence_groups.csv", index=False)
    reserved_table.to_csv(OUT / "reserved_independence_groups.csv", index=False)
    lines = [
        "# P1 — what the finished side analyses are, and are not",
        "",
        "The repeated learning curves and the phase/air-temperature checks stay in the paper. "
        "They are not rerun. They do not become confirmation of the locked admission rule.",
        "",
        f"- Development cases: {payload['development']['n_cases']}; "
        f"network labels {payload['development']['n_network_labels']}; "
        f"unique stations {payload['development']['n_unique_stations']}; "
        f"independence groups {payload['development']['n_independence_groups']}; "
        f"within-panel station-overlap pairs {payload['n_development_overlap_pairs']}.",
        f"- Reserved cases: {payload['reserved']['n_cases']}; "
        f"network labels {payload['reserved']['n_network_labels']}; "
        f"unique stations {payload['reserved']['n_unique_stations']}; "
        f"independence groups {payload['reserved']['n_independence_groups']}; "
        f"within-panel station-overlap pairs {payload['n_reserved_overlap_pairs']}.",
        f"- Stations present in both development and reserved cases: {len(shared_stations)}.",
        "",
        payload["learning_curves"],
        "",
        payload["phase_residuals"],
        "",
        "Three uncertainties stay separate: variation across training subsets, uncertainty on the "
        "fixed test panel, and uncertainty for a basin that shares no station with the fit.",
        "",
        "# P2 — extensions that are not results of this revision",
        "",
        "An agency case with a fault log, a second temperature sensor, or an independent reference "
        "observation would measure changed admission decisions, abstentions, and manual checks. "
        "This archive does not contain that log. No maintenance saving and no ecological recovery "
        "is claimed.",
        "",
        "A later basin test is informative only when it changes the mechanism boundary already "
        "named: a warm season that does not match the historical peak window, a regulated or "
        "groundwater-dominated thermal regime, a short history, a weak donor, or a gap that "
        "persists across years. Adding another country without one of those contrasts does not "
        "strengthen the admission claim.",
        "",
        "The primary endpoint remains the hottest 30-day mean. Annual means, cold extremes, and "
        "phase are boundary checks. They are not additional primary claims.",
        "",
        "A dataset or dashboard, if released, has to carry this method config, the measurement "
        "contract, and the evidence label of each number. Policy text does not add a universal "
        "risk guarantee.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines))
    print(json.dumps({k: payload[k] for k in (
        "n_development_overlap_pairs",
        "n_reserved_overlap_pairs",
        "stations_shared_by_development_and_reserved",
    )}, indent=2))
    print("development groups", payload["development"]["n_independence_groups"])
    print("reserved groups", payload["reserved"]["n_independence_groups"])


if __name__ == "__main__":
    main()
