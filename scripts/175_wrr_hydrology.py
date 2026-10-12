#!/usr/bin/env python3
"""Step 8: hydrological hypotheses on the complete-year B_q table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.hydrology import (  # noqa: E402
    donor_synchrony_stability,
    historical_calibration_break,
    regulation_regime_contrast,
    thermal_response_bins,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    STEP5_THERMAL_DECISION,
    STEP8_HYDROLOGY,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year-policies", default=str(STEP5_THERMAL_DECISION / "year_policies.csv"))
    args = parser.parse_args()
    path = Path(args.year_policies)
    if not path.exists():
        raise SystemExit(f"missing {path}; run 173 first")
    table = pd.read_csv(path)
    STEP8_HYDROLOGY.mkdir(parents=True, exist_ok=True)
    sync = donor_synchrony_stability(table)
    reg = regulation_regime_contrast(table)
    brk = historical_calibration_break(table)
    resp = thermal_response_bins(table)
    sync.to_csv(STEP8_HYDROLOGY / "donor_synchrony_stability.csv", index=False)
    reg.to_csv(STEP8_HYDROLOGY / "regulation_regime.csv", index=False)
    brk.to_csv(STEP8_HYDROLOGY / "regime_change_break.csv", index=False)
    resp.to_csv(STEP8_HYDROLOGY / "thermal_response_bins.csv", index=False)
    verdict = {
        "donor_synchrony": getattr(sync, "attrs", {}).get("verdict", {}),
        "n_networks_breaking_hist": int(brk["breaks_epsilon"].sum()) if not brk.empty else 0,
        "n_networks_compared": int(len(brk)),
        "regulation_rows": int(len(reg)),
        "response_rows": int(len(resp)),
        "notes": "Synthetic mechanism scenarios remain in step7_mechanism/; these tables are the hydrologic counterparts on complete river years.",
    }
    (STEP8_HYDROLOGY / "summary.json").write_text(json.dumps(verdict, indent=2, default=str))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main()
