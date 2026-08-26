#!/usr/bin/env python3
"""Count public USGS river networks with a largest-subset overlap rule.

Reads catalog start/end dates already on disk. Does not download daily
temperature values. Does not open sealed temperatures. Loire and Swiss
Aare-Rhine are not counted toward T8 or non-NA sealed.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.public_river_inventory import (
    cluster_rivers_from_catalog,
    cluster_rivers_from_catalog_v2,
)

OUTPUT = ROOT / "results/framework/public_catalog"
SERIES = OUTPUT / "usgs_daily_temperature_series.csv"
LOCATIONS = OUTPUT / "usgs_long_temperature_locations.csv"
FREEZE = ROOT / "configs/design_freeze_v9.yaml"
CANDIDATES = ROOT / "configs/network_catalog_v2_candidates.yaml"

HUC_CLIMATE = {
    "01": "humid_continental",
    "02": "humid_continental",
    "03": "humid_subtropical",
    "04": "humid_continental",
    "05": "humid_continental",
    "06": "humid_subtropical",
    "07": "humid_continental",
    "10": "cold_semiarid",
    "11": "humid_subtropical",
    "12": "subtropical_semiarid",
    "13": "cold_arid_highland",
    "14": "cold_arid_highland",
    "15": "hot_arid",
    "16": "cold_semiarid",
    "17": "marine_west_coast",
    "18": "mediterranean",
    "19": "subarctic",
    "20": "humid_continental",
}

NEVER_SEALED_NAME_TOKENS = (
    "jinsha",
    "chattahoochee",
    "delaware river",
    "willamette river",
    "suwannee river",
    "yellowstone river",
    "rio grande",
    "madison river",
    "cahaba river",
    "mckenzie river",
    "mahoning river",
    "roanoke river",
    "santa fe river",
    "clearwater river",
)


def _read_catalog(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"site_id": str, "huc": str, "name": str})


def _count(frame: pd.DataFrame, grouping: str, min_stations: int, overlap: float) -> int:
    if frame.empty:
        return 0
    keep = (
        frame["grouping"].eq(grouping)
        & frame["min_stations"].eq(min_stations)
        & frame["min_overlap_years"].eq(overlap)
        & frame["enough_overlap_years"].fillna(False)
    )
    return int(frame.loc[keep, "network_id"].nunique())


def _is_never_sealed(river_name: str) -> bool:
    text = str(river_name or "").lower()
    return any(token in text for token in NEVER_SEALED_NAME_TOKENS)


def _regime(name: str) -> str:
    text = name.lower()
    if any(key in text for key in ("suwannee", "deschutes", "platte", "snake")):
        return "groundwater_dominated"
    if any(key in text for key in ("colorado", "tennessee", "columbia", "sacramento", "missouri")):
        return "regulated"
    if any(key in text for key in ("mississippi", "ohio", "delaware", "yellowstone")):
        return "large_river"
    return "atmospheric"


class _QuotedSiteId(str):
    """Keep USGS site numbers as quoted strings so leading zeros survive YAML."""


def _quoted_site_representer(dumper: yaml.Dumper, data: _QuotedSiteId) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="'")


class _CandidateDumper(yaml.SafeDumper):
    pass


_CandidateDumper.add_representer(_QuotedSiteId, _quoted_site_representer)


def _write_feasibility(counts: dict, extra: dict, v1_n: int, honest: int) -> str:
    below_100 = honest < 100
    lines = [
        "# Catalog v2 feasibility (metadata only)",
        "",
        "This is a station-year inventory, not a recovery score. Daily temperature",
        "values were not downloaded. Sealed temperatures were not opened. The 12",
        "already-downloaded rivers and Jinsha / Chattahoochee were not remapped",
        "into sealed. Loire and Swiss Aare-Rhine are **not** counted toward T8 or",
        "the non-North-America sealed floor; no European daily years were invented.",
        "",
        "v1 grouped by river name + raw HUC prefix and required **every** listed",
        "station to share one window. One short or shifted station killed the",
        f"cluster. That rule still yields **{v1_n}** networks at 4 stations / 8 years.",
        "",
        "v2 keeps stream sites with catalog span ≥ 6 years, then takes the largest",
        "subset whose interval intersection is at least T years. Candidate starts",
        "are station begin dates. Official USGS HUC prefixes are used (a missing",
        "leading zero on 7/9/11-digit codes is restored). `grouping=huc8_only`",
        "ignores exact river-name match and is **not** mixed into name-based counts.",
        "",
        f"- Target independent networks remains **150**. That target is not met.",
        f"- Best honest public-USGS count (name+HUC2, 3 stations, 8-year subset): **{honest}**.",
    ]
    if below_100:
        lines.append(
            f"- That honest count is still **below 100**. Do not paper over the gap with Loire or FOEN."
        )
    else:
        lines.append(
            "- The honest name+HUC2 3st/8y count is ≥ 100 but still below the 150 target."
        )
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- v1-style 4 stations / 8 years (whole-group overlap): {counts['v1_style_4st_8y']}",
            f"- v2 name+HUC2 3 stations / 8 years: {counts['v2_name_huc2_3st_8y']}",
            f"- v2 name+HUC2 3 stations / 6 years: {counts['v2_name_huc2_3st_6y']}",
            f"- v2 name+HUC4 3 stations / 8 years: {counts['v2_name_huc4_3st_8y']}",
            f"- v2 HUC8-only 3 stations / 8 years (exploratory, not name-based): {counts['v2_huc8_only_3st_8y']}",
            "",
            "## Sensitivity (not the honest headline)",
            "",
            f"- v2 name+HUC2 4 stations / 8 years: {extra.get('v2_name_huc2_4st_8y', 'n/a')}",
            f"- v2 name+HUC8 3 stations / 8 years: {extra.get('v2_name_huc8_3st_8y', 'n/a')}",
            "- name+HUC8 is a stricter same-watershed name match; it is still public USGS only.",
            "",
            "## What is not a network",
            "",
            "- HUC8-only groups can mix differently named streams in one watershed.",
            "- Common river names inside one official HUC2 can still collide.",
            "- Catalog overlap is not concurrent daily completeness.",
            "- Loire Hub'Eau names and Swiss FOEN locations have no public daily-year span here.",
            "",
        ]
    )
    return "\n".join(lines)


def _candidate_entry(row: pd.Series) -> dict:
    site_ids = [_QuotedSiteId(item) for item in str(row.site_ids).split(",") if item]
    never_sealed = _is_never_sealed(str(row.river_name))
    historical = "chattahoochee" in str(row.river_name).lower() or "jinsha" in str(
        row.river_name
    ).lower()
    return {
        "network_id": str(row.network_id),
        "display_name": f"{row.river_name} (HUC2 {row.huc2})",
        "split_role": "historical" if historical else "catalog_candidate",
        "historical_seen": bool(historical),
        "never_sealed": bool(never_sealed or historical),
        "regime": _regime(str(row.river_name)),
        "climate_or_ecoregion": HUC_CLIMATE.get(str(row.huc2), "unspecified"),
        "candidate_station_ids": site_ids,
        "temperature_record_unverified": True,
        "sealed_outcomes_opened": False,
        "feasibility_status": "catalog_v2_subset_overlap_only",
        "use": "already_used" if historical else "catalog_v2_candidate",
        "grouping": "name_huc2",
        "notes": (
            f"Largest concurrent subset: {int(row.n_stations)} stations, "
            f"catalog overlap about {float(row.catalog_overlap_years):.1f} years. "
            "Metadata only. Temperatures not downloaded."
            + (" Never sealed." if never_sealed or historical else "")
        ),
    }


def main() -> None:
    if not SERIES.is_file() or not LOCATIONS.is_file():
        raise SystemExit("need on-disk USGS catalog CSVs; do not download values here")
    series = _read_catalog(SERIES)
    locations = _read_catalog(LOCATIONS)
    freeze = yaml.safe_load(FREEZE.read_text(encoding="utf-8"))
    never_sealed = list(
        (freeze.get("split_rule") or {}).get("never_sealed_networks") or []
    )
    not_countable = list(
        (freeze.get("split_rule") or {}).get(
            "not_countable_as_public_daily_or_non_na_sealed_until_daily_history_is_public"
        )
        or []
    )

    v1 = cluster_rivers_from_catalog(series, locations)
    v1_ok = (
        v1.loc[v1["enough_overlap_years"].fillna(False)] if not v1.empty else v1
    )
    v1_n = int(len(v1_ok))

    chunks = []
    for min_stations in (3, 4):
        for overlap, span in ((8.0, 8.0), (6.0, 6.0)):
            chunk = cluster_rivers_from_catalog_v2(
                series,
                locations,
                min_stations=min_stations,
                min_overlap_years=overlap,
                min_span_years=span,
            )
            if not chunk.empty:
                chunks.append(chunk)
    clusters = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clusters.to_csv(OUTPUT / "usgs_river_clusters_v2.csv", index=False)

    counts = {
        "v1_style_4st_8y": v1_n,
        "v2_name_huc2_3st_8y": _count(clusters, "name_huc2", 3, 8.0),
        "v2_name_huc2_3st_6y": _count(clusters, "name_huc2", 3, 6.0),
        "v2_name_huc4_3st_8y": _count(clusters, "name_huc4", 3, 8.0),
        "v2_huc8_only_3st_8y": _count(clusters, "huc8_only", 3, 8.0),
    }
    extra = {
        "v2_name_huc2_4st_8y": _count(clusters, "name_huc2", 4, 8.0),
        "v2_name_huc2_4st_6y": _count(clusters, "name_huc2", 4, 6.0),
        "v2_name_huc8_3st_8y": _count(clusters, "name_huc8", 3, 8.0),
        "v2_name_huc4_3st_6y": _count(clusters, "name_huc4", 3, 6.0),
        "v2_huc8_only_3st_6y": _count(clusters, "huc8_only", 3, 6.0),
    }
    honest = counts["v2_name_huc2_3st_8y"]
    manifest = {
        "what_this_is": (
            "Metadata-only v2 public USGS catalog counts using the largest "
            "overlapping station subset."
        ),
        "what_this_is_not": (
            "Not a recovery score. Daily temperature values were not downloaded. "
            "Sealed temperatures were not opened. Loire and Swiss Aare-Rhine are "
            "not counted toward T8 or non-NA sealed."
        ),
        "temperatures_downloaded": False,
        "sealed_outcomes_opened": False,
        "loire_counted_toward_t8": False,
        "swiss_aar_rhine_counted_toward_t8": False,
        "europe_daily_years_invented": False,
        "design_freeze_v4_touched": False,
        "network_catalog_v1_rewritten": False,
        "target_independent_networks": 150,
        "counts": counts,
        "sensitivity_counts": extra,
        "best_honest_public_usgs_count": honest,
        "best_honest_definition": (
            "v2 name+official HUC2, at least 3 stream stations, largest subset "
            "with at least 8 overlapping catalog years. HUC8-only is exploratory "
            "and excluded. 6-year overlap is a documented relaxation, not the "
            "honest T2 count."
        ),
        "best_honest_still_below_100": bool(honest < 100),
        "best_honest_still_below_150": bool(honest < 150),
        "huc2_rule": (
            "Official USGS HUC2 after restoring a missing leading zero on "
            "odd-length codes. Not v1's raw first-two-character prefix."
        ),
        "never_sealed_networks_not_remapped": never_sealed,
        "not_countable_as_public_daily_or_non_na_sealed": not_countable,
        "n_usgs_daily_series": int(len(series)),
        "n_usgs_series_span_ge_6yr": int(pd.to_numeric(series["span_years"], errors="coerce").ge(6).sum()),
        "n_usgs_series_span_ge_8yr": int(pd.to_numeric(series["span_years"], errors="coerce").ge(8).sum()),
    }
    (OUTPUT / "catalog_v2_counts.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUTPUT / "catalog_v2_feasibility.md").write_text(
        _write_feasibility(counts, extra, v1_n, honest), encoding="utf-8"
    )

    name_huc2 = pd.DataFrame()
    if not clusters.empty:
        name_huc2 = clusters.loc[
            clusters["grouping"].eq("name_huc2")
            & clusters["min_stations"].eq(3)
            & clusters["min_overlap_years"].eq(8.0)
            & clusters["enough_overlap_years"].fillna(False)
        ].copy()
    document = {
        "catalog_id": "network_catalog_v2_candidates",
        "status": "metadata_only_candidates",
        "frozen_on": "2026-08-26",
        "sealed_outcomes_opened": False,
        "temperature_records_unverified": True,
        "note": (
            "Metadata-only v2 candidates from public USGS catalog dates. "
            "Not a remapping of network_catalog_v1. Sealed outcomes are unopened. "
            "Jinsha, Chattahoochee, and the 12 burned rivers are never sealed. "
            "Loire and Swiss Aare-Rhine are omitted and do not count toward T8."
        ),
        "target_independent_networks": 150,
        "best_honest_public_usgs_count": honest,
        "networks": [_candidate_entry(row) for row in name_huc2.itertuples(index=False)]
        if not name_huc2.empty
        else [],
    }
    if any(item.get("sealed_outcomes_opened") for item in document["networks"]):
        raise SystemExit("refusing to write opened sealed flags")
    if any(item.get("temperature_record_unverified") is not True for item in document["networks"]):
        raise SystemExit("every new network must stay temperature-unverified")
    if any(item.get("split_role") == "sealed" for item in document["networks"]):
        raise SystemExit("refusing to assign sealed roles in v2 candidates")
    CANDIDATES.write_text(
        yaml.dump(document, Dumper=_CandidateDumper, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(json.dumps(counts, indent=2))
    print("best_honest_public_usgs_count", honest)
    print("wrote", OUTPUT / "usgs_river_clusters_v2.csv")
    print("wrote", OUTPUT / "catalog_v2_counts.json")
    print("wrote", OUTPUT / "catalog_v2_feasibility.md")
    print("wrote", CANDIDATES, "n", len(document["networks"]))


if __name__ == "__main__":
    main()
