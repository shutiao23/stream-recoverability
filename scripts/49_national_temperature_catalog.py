#!/usr/bin/env python3
"""Public catalog only: which rivers have several long daily temperature stations.

Looks at station names and catalog start/end dates. Does not download temperature
values for rivers saved for the last check. Does not score recovery.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.network_catalog import load_network_catalog
from stream_recoverability.data.nwis_temperature import (
    nwis_national_daily_temperature_catalog,
)
from stream_recoverability.data.public_river_inventory import (
    cluster_rivers_from_catalog,
    inventory_foen_temperature_stations,
    inventory_hubeau_stations,
    inventory_loire_hubeau,
)

OUTPUT = ROOT / "results/framework/public_catalog"
LAST_CHECK_NAMES = {
    "colorado river",
    "columbia river",
    "ohio river",
    "deschutes river",
}
ALREADY_USED_NAMES = {
    "chattahoochee river",
}


def _write_plain_decision(
    clusters: pd.DataFrame,
    loire: pd.DataFrame,
    foen: pd.DataFrame,
    hubeau_n: int,
) -> str:
    usable = clusters.loc[clusters["enough_overlap_years"].fillna(False)] if not clusters.empty else clusters
    build = []
    last_check = []
    already = []
    for row in usable.itertuples(index=False) if not usable.empty else []:
        name = str(row.river_name).lower()
        if name in ALREADY_USED_NAMES:
            already.append(row)
        elif name in LAST_CHECK_NAMES:
            last_check.append(row)
        else:
            build.append(row)
    lines = [
        "# 公开目录查完以后，哪些河能用来定方法",
        "",
        "只查了站名和目录上的起止年。没有用「留到最后看」的河的水温给方法打分。",
        "",
        f"- USGS 日均水温、同期够八年、至少四站的河：{0 if usable.empty else int(len(usable))} 条。",
        f"- 其中已经用过（Chattahoochee）：{len(already)} 条，不能再当最后检验。",
        f"- 名单里留到最后看的同名大河：{len(last_check)} 条，这次仍然只记目录，不下载水温。",
        f"- 可以考虑用来定方法或锁设定的：{len(build)} 条。",
        f"- 法国 Hub'Eau 连续水温站一共 {hubeau_n} 个；河名就是卢瓦尔本身的：{int(len(loire))} 个。",
        f"- 瑞士公开查询返回站名 {int(len(foen))} 条。历史日均文件仍要另订，这次没有日均水温。",
        "",
    ]
    if len(build) < 8:
        lines.append(
            "还凑不齐十几条独立的、同期够八年的河。缺的不是再猜三个站号，而是公开日均水温本身不够密。"
        )
    else:
        lines.append("定方法用的河从下面「可以用来定方法」里按气候和河类挑，不要事后把检验河加进来凑数。")
    lines.extend(["", "## 可以考虑用来定方法或锁设定", ""])
    if not build:
        lines.append("没有。")
    else:
        lines.append("| 河 | 分区 | 站数 | 目录同期（年） | 站号 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in build[:30]:
            lines.append(
                f"| {row.river_name} | {row.huc2} | {row.n_stations} | "
                f"{row.catalog_overlap_years:.1f} | `{row.site_ids}` |"
            )
    lines.extend(["", "## 留到最后看（只记目录）", ""])
    if not last_check:
        lines.append("全国目录里，和预留大河同名且同期够八年的组还没有，或不够四站。")
    else:
        for row in last_check:
            lines.append(
                f"- {row.river_name}（分区 {row.huc2}）：{row.n_stations} 站，"
                f"目录同期约 {row.catalog_overlap_years:.1f} 年。不下载水温。"
            )
    lines.extend(["", "## 卢瓦尔和瑞士", ""])
    if loire.empty:
        lines.append("Hub'Eau 里没有河名正好是卢瓦尔的站。之前用「Loire」模糊搜索会搜到别的小河，作废。")
    else:
        lines.append("卢瓦尔干流站（只记目录，不下载水温）：")
        for row in loire.itertuples(index=False):
            lines.append(f"- `{row.site_id}` {row.name}（{row.begin}–{row.end}）")
    if foen.empty:
        lines.append("瑞士这次没有拿到可用的历史日均目录。现场值在 LINDAS，历史序列仍要向 FOEN 订。")
    else:
        lines.append("瑞士查询只返回了站名，没有可公开拉的历史日均起止年。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    hubeau = inventory_hubeau_stations()
    hubeau.to_csv(OUTPUT / "hubeau_all_stations.csv", index=False)
    loire = inventory_loire_hubeau()
    loire.to_csv(OUTPUT / "loire_hubeau_stations.csv", index=False)
    foen = inventory_foen_temperature_stations()
    foen.to_csv(OUTPUT / "foen_lindas_stations.csv", index=False)
    print("hubeau", len(hubeau), "loire_exact", len(loire), "foen", len(foen), flush=True)

    series = nwis_national_daily_temperature_catalog()
    series.to_csv(OUTPUT / "usgs_daily_temperature_series.csv", index=False)
    long_series = series.loc[series["span_years"].ge(8)].copy() if not series.empty else series
    print("usgs_daily_series", len(series), "span_ge_8", len(long_series), flush=True)

    locations = pd.DataFrame()
    clusters = pd.DataFrame()
    if not long_series.empty:
        locations = long_series[
            ["site_id", "name", "latitude", "longitude", "huc", "site_type", "found"]
        ].copy()
        locations.to_csv(OUTPUT / "usgs_long_temperature_locations.csv", index=False)
        clusters = cluster_rivers_from_catalog(long_series, locations)
        clusters.to_csv(OUTPUT / "usgs_river_clusters.csv", index=False)

    usable = (
        clusters.loc[clusters["enough_overlap_years"].fillna(False)]
        if not clusters.empty
        else clusters
    )
    text = _write_plain_decision(clusters, loire, foen, int(len(hubeau)))
    (OUTPUT / "feasibility_decision.md").write_text(text, encoding="utf-8")
    catalog = load_network_catalog()
    manifest = {
        "what_this_is": "Public catalog of daily temperature station years and river groups.",
        "what_this_is_not": "Not a recovery score. Last-check river temperatures were not downloaded.",
        "n_usgs_daily_series": int(len(series)),
        "n_usgs_series_span_ge_8yr": int(len(long_series)) if not long_series.empty else 0,
        "n_river_groups_four_stations": int(len(clusters)) if not clusters.empty else 0,
        "n_river_groups_eight_year_overlap": int(len(usable)) if not usable.empty else 0,
        "n_hubeau_stations": int(len(hubeau)),
        "n_loire_exact_name": int(len(loire)),
        "n_foen_names": int(len(foen)),
        "catalog_networks_listed": len(catalog["networks"]),
        "last_check_temperatures_opened": False,
    }
    (OUTPUT / "national_catalog.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(text)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
