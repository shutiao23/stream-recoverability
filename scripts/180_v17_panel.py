#!/usr/bin/env python3
"""Step 1 of the v17 programme: population, truth scale, and the declared split.

The split is at the network level and is stratified on provider and donor
regime, so development and reserved networks are exchangeable on the covariate
the design conditions on. v16's reserved pool was not, which is why its
confirmation could not test its rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    declare_split,
    interannual_scale,
    network_strata,
    station_roster,
    trusted_years,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    MIN_COMPLETE_YEARS,
    RESERVED_NETWORK_FRACTION,
    SPLIT_SEED,
    STEP1_PANEL,
)


def main() -> int:
    STEP1_PANEL.mkdir(parents=True, exist_ok=True)
    years = trusted_years()
    roster = station_roster()
    strata = network_strata(roster)
    split = declare_split(strata)
    scale = interannual_scale(roster)

    roles = split.set_index("network_id")["split_role"].to_dict()
    roster["split_role"] = roster["network_id"].map(roles)
    years["split_role"] = years["network_id"].map(roles)

    roster.to_csv(STEP1_PANEL / "station_roster.csv", index=False)
    split.to_csv(STEP1_PANEL / "network_split.csv", index=False)

    eligible = roster.loc[roster["eligible_station"]]
    eligible_years = years.loc[
        years.set_index(["network_id", "station_id"]).index.isin(
            eligible.set_index(["network_id", "station_id"]).index
        )
    ]
    summary = {
        "as_of": "2026-09-23",
        "population": "river waterbodies, fully observed calendar years, reference never imputed",
        "min_complete_years_per_station": MIN_COMPLETE_YEARS,
        "split_seed": SPLIT_SEED,
        "reserved_network_fraction": RESERVED_NETWORK_FRACTION,
        "n_networks_total": int(roster["network_id"].nunique()),
        "n_stations_total": int(len(roster)),
        "n_station_years_total": int(len(years)),
        "n_eligible_stations": int(len(eligible)),
        "n_eligible_networks": int(eligible["network_id"].nunique()),
        "n_eligible_station_years": int(len(eligible_years)),
        "n_development_networks": int((split["split_role"] == "development").sum()),
        "n_reserved_networks": int((split["split_role"] == "reserved").sum()),
        "natural_scale_interannual_sd": scale,
        "donor_regime_networks": split.groupby(["split_role", "donor_regime"]).size().to_dict().__str__(),
    }
    (STEP1_PANEL / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["# Step 1 — population, truth scale, and the declared split", ""]
    lines.append(f"As of 2026-09-23. Seed {SPLIT_SEED}. Reserved fraction {RESERVED_NETWORK_FRACTION}.")
    lines.append("")
    lines.append("## Denominator")
    lines.append("")
    lines.append(f"- Eligible networks: **{summary['n_eligible_networks']}**")
    lines.append(f"- Eligible stations (>= {MIN_COMPLETE_YEARS} complete years): **{summary['n_eligible_stations']}**")
    lines.append(f"- Eligible complete station-years: **{summary['n_eligible_station_years']}**")
    lines.append(
        f"- Development / reserved networks: **{summary['n_development_networks']} / {summary['n_reserved_networks']}**"
    )
    lines.append("")
    lines.append("## Natural scale of the endpoint")
    lines.append("")
    lines.append(
        "Interannual standard deviation of the annual hottest-30 mean, per station: "
        f"mean **{scale['mean_sd_c']:.3f} °C**, median {scale['median_sd_c']:.3f} °C "
        f"(IQR {scale['q25_sd_c']:.3f}–{scale['q75_sd_c']:.3f}), n = {scale['n_stations']} stations."
    )
    lines.append("")
    lines.append("Every tolerance in this study is reported in these units as well as in degrees.")
    lines.append("")
    lines.append("## Split composition (networks)")
    lines.append("")
    table = split.pivot_table(
        index="provider", columns=["split_role", "donor_regime"], values="network_id", aggfunc="count"
    ).fillna(0).astype(int)
    lines.append(table.to_string())
    lines.append("")
    lines.append("## Station-years by split role and donor regime")
    lines.append("")
    joined = eligible.groupby(["split_role", "donor_regime"]).agg(
        networks=("network_id", "nunique"), stations=("station_id", "size"), station_years=("n_complete_years", "sum")
    )
    lines.append(joined.to_string())
    (STEP1_PANEL / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(joined.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
