#!/usr/bin/env python3
"""P0-07: discover external confirmation candidates not used in the current programme.

Default mode is offline+catalog: list HUC/networks absent from the v17 panel and
write a recruitment worksheet. Optional --pilot-fetch downloads one USGS site
group to prove the empty-cache path (network I/O).
"""

from __future__ import annotations

import argparse
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
SPLIT = ROOT / "results" / "v17_fitness" / "step1_panel" / "network_split.csv"
ROSTER = ROOT / "results" / "wrr_revision" / "step1_universe" / "network_roster.csv"
TRUSTED = ROOT / "results" / "wrr_revision" / "step1_universe" / "trusted_river_complete_years.csv"


def build_worksheet(directory: Path, manifest) -> list[Path]:
    split = pd.read_csv(SPLIT)
    roster = pd.read_csv(ROSTER)
    used = set(split.network_id.astype(str))
    # Outside panel, river, with some eligible years, not previously confirmation-scored
    outside = roster.loc[~roster.network_id.astype(str).isin(used)].copy()
    if "waterbody_family" in outside.columns:
        outside = outside.loc[outside["waterbody_family"].astype(str).eq("river")]
    if "v16_role" in outside.columns:
        # Prefer never-scored; still require later complete-year audit after fetch
        outside = outside.loc[
            ~outside["v16_role"].astype(str).isin(["v16_confirmation_scored", "first_panel_development"])
        ]
    cols = [
        c
        for c in (
            "network_id",
            "provider",
            "v16_role",
            "n_stations",
            "n_eligible_annual_station_years",
            "source_root",
            "waterbody_family",
        )
        if c in outside.columns
    ]
    worksheet = outside[cols].sort_values(
        by=[c for c in ("n_eligible_annual_station_years", "n_stations") if c in cols],
        ascending=False,
    )
    path = OUT / "confirmation_external_worksheet.csv"
    worksheet.to_csv(path, index=False)

    # Parser readiness for true external agencies
    parsers = {
        "usgs": "src/stream_recoverability/data/nwis_temperature.py",
        "nve_hydapi": "src/stream_recoverability/data/nve_water_temperature.py",
        "hubeau": "src/stream_recoverability/data/hubeau_temperature.py",
        "uk_ea": "src/stream_recoverability/data/uk_ea_temperature.py",
        "smhi": "src/stream_recoverability/data/smhi_water_temperature.py",
        "ehyd": "src/stream_recoverability/data/ehyd_temperature.py",
        "eccc_automated": "src/stream_recoverability/data/eccc_automated_temperature.py",
    }
    summary = {
        "n_outside_river_networks_in_roster": int(len(worksheet)),
        "n_with_any_eligible_years": int(
            (worksheet["n_eligible_annual_station_years"] > 0).sum()
            if "n_eligible_annual_station_years" in worksheet.columns
            else 0
        ),
        "n_meeting_design_floor_already": 0,
        "design_floor_networks": 30,
        "parsers_ready": parsers,
        "next_human_or_agent_action": (
            "Fetch ≥30 new river networks with ≥4 complete years/station from USGS/NVE/"
            "Hub'Eau/UK EA/SMHI into a sealed root outside development_v11 confirmation "
            "paths; write confirmation_inputs_manifest.csv; then unseal once."
        ),
    }
    summary_path = OUT / "confirmation_external_worksheet_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    for p in (path, summary_path):
        (directory / p.name).write_bytes(p.read_bytes())
    print(json.dumps(summary, indent=2))
    return [directory / path.name, directory / summary_path.name]


def pilot_fetch_usgs(directory: Path) -> list[Path]:
    """Download one unused USGS HUC network as a path proof (network I/O)."""

    from stream_recoverability.data.nwis_temperature import download_daily_means  # type: ignore

    worksheet = pd.read_csv(OUT / "confirmation_external_worksheet.csv")
    usgs = worksheet.loc[worksheet["provider"].astype(str).eq("usgs")]
    if usgs.empty:
        raise RuntimeError("no USGS rows in external worksheet")
    # Prefer networks that already show some eligible years in the old roster audit
    row = usgs.iloc[0]
    network_id = str(row.network_id)
    pilot_root = OUT / "confirmation_pilot_inputs" / network_id
    pilot_root.mkdir(parents=True, exist_ok=True)
    note = pilot_root / "PILOT_NOTE.md"
    note.write_text(
        f"# Pilot fetch placeholder for `{network_id}`\n\n"
        "This entry records intent. Full multi-station NWIS pulls should use the "
        "project's confirmation acquisition scripts with request hashing, not an "
        "ad-hoc one-off, before unseal.\n"
    )
    # Do not invent site lists here; require an explicit site file if present.
    sites_file = OUT / "confirmation_pilot_site_lists" / f"{network_id}.txt"
    if not sites_file.is_file():
        (directory / "pilot_skipped.json").write_text(
            json.dumps(
                {
                    "skipped": True,
                    "reason": f"missing site list {sites_file}",
                    "network_id": network_id,
                },
                indent=2,
            )
            + "\n"
        )
        return [directory / "pilot_skipped.json", note]
    site_ids = [line.strip() for line in sites_file.read_text().splitlines() if line.strip()]
    frames = {}
    for site_id in site_ids:
        frames[site_id] = download_daily_means(site_id)
    wide = pd.DataFrame({sid: df.set_index("date")["temperature_c"] for sid, df in frames.items() if len(df)})
    out_csv = pilot_root / "daily_wide_temperature.csv"
    wide.sort_index().to_csv(out_csv)
    meta = {
        "network_id": network_id,
        "n_sites_requested": len(site_ids),
        "n_sites_with_data": int(wide.shape[1]),
        "n_days": int(len(wide)),
    }
    (pilot_root / "pilot_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    (directory / "pilot_summary.json").write_text(json.dumps(meta, indent=2) + "\n")
    return [out_csv, directory / "pilot_summary.json"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-fetch", action="store_true")
    args = parser.parse_args()

    def work(directory: Path, manifest):
        outputs = build_worksheet(directory, manifest)
        if args.pilot_fetch:
            outputs.extend(pilot_fetch_usgs(directory))
        return outputs

    run_fail_closed("P0-07 external confirmation recruitment worksheet", work, inputs=[SPLIT, ROSTER])


if __name__ == "__main__":
    main()
