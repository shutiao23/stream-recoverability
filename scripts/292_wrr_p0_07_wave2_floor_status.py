#!/usr/bin/env python3
"""Aggregate wave-2 provider floors for P0-07 (does not score)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest"


def main() -> int:
    usgs = json.loads((OUT / "summary.json").read_text()) if (OUT / "summary.json").is_file() else {}
    providers = {}
    for name in ("usgs", "smhi", "hubeau", "uk_ea", "nve", "eccc_automated"):
        if name == "usgs":
            providers[name] = {
                "n_ready": int(usgs.get("n_ready_ge2_stations_ge4_years") or 0),
                "ids": usgs.get("ready_network_ids") or [],
            }
            continue
        # ECCC lives under eccc/; others under their provider key
        sub = "eccc" if name == "eccc_automated" else name
        path = OUT / sub / "summary.json"
        if path.is_file():
            block = json.loads(path.read_text())
            providers[name] = {
                "n_ready": int(block.get("n_ready_networks") or 0),
                "ids": block.get("ready_network_ids") or [],
            }
        else:
            providers[name] = {"n_ready": 0, "ids": []}

    n_nets = sum(p["n_ready"] for p in providers.values())
    n_providers = sum(1 for p in providers.values() if p["n_ready"] > 0)
    # crude context: USGS HUC2 diversity + non-USGS countries
    contexts = set()
    for nid in providers["usgs"]["ids"]:
        digits = "".join(ch for ch in str(nid) if ch.isdigit())
        if len(digits) >= 2:
            contexts.add(f"usgs_huc2_{digits[:2]}")
    if providers["smhi"]["n_ready"]:
        contexts.add("sweden")
    if providers["hubeau"]["n_ready"]:
        contexts.add("france")
    if providers["uk_ea"]["n_ready"]:
        contexts.add("uk")
    if providers["nve"]["n_ready"]:
        contexts.add("norway_secondary_only")
    if providers["eccc_automated"]["n_ready"]:
        contexts.add("canada")

    floors = {
        "min_networks": 30,
        "min_providers": 3,
        "min_contexts": 3,
        "n_networks": n_nets,
        "n_providers_with_ready_nets": n_providers,
        "n_contexts_proxy": len(contexts),
        "contexts_proxy": sorted(contexts),
        "providers": {k: {"n_ready": v["n_ready"], "n_ids": len(v["ids"])} for k, v in providers.items()},
        "floors_met": n_nets >= 30 and n_providers >= 3 and len(contexts) >= 3,
        "scored": False,
        "score_forbidden_until_floors_met": True,
    }
    (OUT / "floor_status.json").write_text(json.dumps(floors, indent=2) + "\n")
    print(json.dumps(floors, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
