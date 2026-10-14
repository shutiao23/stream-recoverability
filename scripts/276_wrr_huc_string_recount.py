#!/usr/bin/env python3
"""F08: recount HUC2 contexts using zero-padded string HUC identifiers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "f08_huc_string_recount"


def huc2_from_network_id(network_id: str) -> str | None:
    # usgs_confirm_1801 -> treat trailing digits as HUC4 candidate; pad to 4 then take 2.
    m = re.search(r"(\d+)$", str(network_id))
    if not m:
        return None
    digits = m.group(1)
    huc4 = digits.zfill(4)[-4:]
    return huc4[:2]


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    seal = json.loads((READY / "confirmation_seal.json").read_text())
    historical = sorted(str(x) for x in seal.get("huc2_contexts", []))
    network_ids = [str(x) for x in seal.get("network_ids", [])]
    rows = []
    for nid in network_ids:
        rows.append({"network_id": nid, "huc2_from_id_padded": huc2_from_network_id(nid)})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "network_huc2_from_ids.csv", index=False)

    # Prefer catalog HUC if available.
    catalog_paths = [
        ROOT / "results" / "development_v11" / "usgs_site_catalog.csv",
        ROOT / "configs" / "usgs_sites.csv",
    ]
    catalog_huc2 = None
    for path in catalog_paths:
        if path.is_file():
            cat = pd.read_csv(path, dtype=str)
            huc_col = next((c for c in cat.columns if c.lower() in {"huc", "huc_cd", "huc8"}), None)
            if huc_col:
                cat["huc"] = cat[huc_col].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8)
                cat["huc2"] = cat["huc"].str[:2]
                catalog_huc2 = sorted(cat["huc2"].dropna().unique().tolist())
                break

    recounted = sorted({h for h in table["huc2_from_id_padded"].dropna().astype(str)})
    summary = {
        "historical_n_huc2_contexts": len(historical),
        "historical_huc2_contexts": historical,
        "recounted_from_network_id_n": len(recounted),
        "recounted_from_network_id": recounted,
        "catalog_huc2_available": catalog_huc2 is not None,
        "note": (
            "Historical seal lists values such as 19,20,30 that are not CONUS HUC2 codes; "
            "they likely come from numeric coercion / taking digits from network ids. "
            "Recruitment and reporting must keep HUC fields as zero-padded strings."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
