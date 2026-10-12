"""Job list shared by the v18 endpoint scripts.

Kept beside the scripts rather than inside the package because it is a
description of this repository's panel, not part of the method.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.panel import station_roster, trusted_years  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import STEP1_PANEL  # noqa: E402


def endpoint_jobs() -> list[dict]:
    roster = station_roster()
    roster = roster.loc[roster["eligible_station"]]
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    roles = split.set_index(split["network_id"].astype(str))["split_role"].to_dict()
    years = trusted_years()
    grouped = years.groupby(["network_id", "station_id"])["year"].apply(
        lambda s: tuple(sorted(int(v) for v in s))
    )
    out = []
    for row in roster.itertuples():
        complete = grouped.get((str(row.network_id), str(row.station_id)))
        if complete is None or len(complete) < 2:
            continue
        out.append(
            {
                "network_id": str(row.network_id),
                "station_id": str(row.station_id),
                "provider": str(row.provider),
                "source_root": str(row.source_root),
                "split_role": str(roles.get(str(row.network_id), "development")),
                "complete_years": complete,
            }
        )
    return out
