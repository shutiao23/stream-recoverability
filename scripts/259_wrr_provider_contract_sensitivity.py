#!/usr/bin/env python3
"""F09/P0-02 executable sensitivity: does the conclusion depend on providers whose
daily value is not a documented provider daily mean?

`measurement_provenance_dictionary.csv` stratifies the twelve providers by what
their daily value actually is. Six of them (chmi, rws_waterwebservices, syke,
hubeau, arso, smhi) are not a documented provider daily mean: chmi and rws are
project-derived means of provider sub-daily values, syke is a fixed morning
reading, arso's statistic is undocumented, smhi's aggregation is undocumented,
and hubeau is a continuous chronicle. The study's Methods sentence "daily mean
water temperature" is therefore a contract that holds for part of the panel.

This script recomputes the headline contrast on the subset of networks whose
provider documents a daily mean, and on the complement, using the stored case
tables. It does not re-ingest anything and does not touch frozen artifacts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.frontier import operating_point_contrast  # noqa: E402

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "provider_contract_sensitivity"
RETENTION = 0.70

DAILY_MEAN_DOCUMENTED = {"usgs", "foen", "gkd_bayern", "nve_hydapi", "lubw"}
PROJECT_DERIVED_DAILY = {"chmi", "rws_waterwebservices"}
NON_DAILY = {"syke"}
UNDOCUMENTED = {"arso"}


def load() -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    pops = {}
    pops["development_retrospective"] = (
        pd.read_parquet(ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet").reset_index(drop=True),
        pd.read_parquet(
            ROOT / "results/v17_fitness/step6_screen/development_certificates.parquet"
        ).reset_index(drop=True),
    )
    pops["reserved_retrospective"] = (
        pd.read_parquet(ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet").reset_index(
            drop=True
        ),
        pd.read_parquet(
            ROOT / "results/v17_fitness/step10_confirmation/reserved_certificates.parquet"
        ).reset_index(drop=True),
    )
    pops["sealed_usgs"] = (
        pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_cases.parquet").reset_index(drop=True),
        pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_certificates.parquet").reset_index(drop=True),
    )
    return pops


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, (cases, certificates) in load().items():
        cases = cases.reset_index(drop=True)
        certificates = certificates.reset_index(drop=True)
        provider = cases["provider"].astype(str)
        subsets = {
            "all_providers": provider.notna(),
            "documented_daily_mean_only": provider.isin(DAILY_MEAN_DOCUMENTED),
            "project_derived_or_non_daily": provider.isin(
                PROJECT_DERIVED_DAILY | NON_DAILY | UNDOCUMENTED
            ),
        }
        for subset_name, mask in subsets.items():
            block = cases.loc[mask].reset_index(drop=True)
            sub_cert = certificates.loc[mask].reset_index(drop=True)
            if len(block) < 200:
                rows.append(
                    {
                        "population": name,
                        "subset": subset_name,
                        "n_cases": int(len(block)),
                        "note": "below 200 cases; not scored",
                    }
                )
                continue
            contrast = operating_point_contrast(block, sub_cert, retention=RETENTION, seed=0, draws=1200)
            rows.append(
                {
                    "population": name,
                    "subset": subset_name,
                    "n_cases": int(len(block)),
                    "n_networks": int(block["network_id"].nunique()),
                    "providers": ";".join(sorted(block["provider"].astype(str).unique())),
                    "contrast_points": float(contrast["point"] * 100),
                    "ci_low_points": float(contrast["low"] * 100),
                    "ci_high_points": float(contrast["high"] * 100),
                }
            )
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "provider_contract_contrasts.csv", index=False)
    payload = {
        "question": (
            "Does the screening contrast depend on providers whose daily value is not a "
            "documented provider daily mean?"
        ),
        "strata": {
            "documented_daily_mean": sorted(DAILY_MEAN_DOCUMENTED),
            "project_derived_daily_mean": sorted(PROJECT_DERIVED_DAILY),
            "non_daily_provider_statistic": sorted(NON_DAILY),
            "undocumented_statistic": sorted(UNDOCUMENTED),
        },
        "retention": RETENTION,
        "rows": rows,
        "source": "results/wrr_submission_ready/measurement_provenance_dictionary.csv",
    }
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
