"""Read-only preview of what scripts/249 would seal (calls its build_manifest).

Imports the seal module by path and calls build_manifest(), which only reads
files. seal() is never called, so no seal, manifest or run directory is written.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "seal249", ROOT / "scripts" / "249_multi_agency_transport_seal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rows = mod.build_manifest()
per_provider: dict[str, dict[str, object]] = {}
station_years_total = 0
for row in rows:
    panel = pd.read_csv(ROOT / str(row["input_path"]), parse_dates=["date"]).set_index("date")
    panel = panel.apply(pd.to_numeric, errors="coerce")
    years = sum(len(mod.complete_years(panel[s])) for s in str(row["station_ids_ge4"]).split(";"))
    station_years_total += years
    entry = per_provider.setdefault(
        str(row["provider"]),
        {"n_networks": 0, "n_stations_ge4": 0, "station_years": 0,
         "contexts": set(), "strata": set(), "networks": []},
    )
    entry["n_networks"] += 1
    entry["n_stations_ge4"] += int(row["n_stations_ge4"])
    entry["station_years"] += years
    entry["contexts"].add(str(row["context"]))
    entry["strata"].add(str(row["quality_assurance"]))
    entry["networks"].append(
        {"network_id": row["network_id"], "n_stations_ge4": row["n_stations_ge4"],
         "station_years": years, "sha256": str(row["sha256"])[:16]}
    )
for value in per_provider.values():
    value["contexts"] = sorted(value["contexts"])
    value["strata"] = sorted(value["strata"])

preview = {
    "note": "read-only preview; scripts/249.build_manifest() called, seal() not called",
    "n_network_rows": len(rows),
    "n_providers": len(per_provider),
    "n_contexts": len({str(r["context"]) for r in rows}),
    "n_station_years_complete": station_years_total,
    "assurance_strata": sorted({str(r["quality_assurance"]) for r in rows}),
    "per_provider": per_provider,
    "smhi_networks": [
        {k: (str(v)[:16] if k == "sha256" else v) for k, v in r.items()}
        for r in rows if r["provider"] == "smhi"
    ],
}
print(json.dumps(preview, indent=2, ensure_ascii=False, default=str))
(ROOT / "scratch" / "smhi_seal_dryrun_preview.json").write_text(
    json.dumps(preview, indent=2, ensure_ascii=False, default=str) + "\n"
)
