#!/usr/bin/env python3
"""Write paper/next/results.md from the files we actually have. No invented scores."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "results/framework/public_catalog"
RIVERS = ROOT / "results/framework/public_rivers"
DEST = ROOT / "paper/next/results.md"


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    national = _read_json(CATALOG / "national_catalog.json")
    guessed = pd.read_csv(CATALOG / "river_catalog_summary.csv") if (
        CATALOG / "river_catalog_summary.csv"
    ).is_file() else pd.DataFrame()
    clusters = pd.read_csv(CATALOG / "usgs_river_clusters.csv") if (
        CATALOG / "usgs_river_clusters.csv"
    ).is_file() else pd.DataFrame()
    loire = pd.read_csv(CATALOG / "loire_hubeau_stations.csv") if (
        CATALOG / "loire_hubeau_stations.csv"
    ).is_file() else pd.DataFrame()
    foen = pd.read_csv(CATALOG / "foen_existenz_locations.csv") if (
        CATALOG / "foen_existenz_locations.csv"
    ).is_file() else pd.DataFrame()
    overlap = pd.read_csv(RIVERS / "overlap.csv") if (RIVERS / "overlap.csv").is_file() else pd.DataFrame()
    scores = pd.read_csv(RIVERS / "leave_one_year_scores.csv") if (
        RIVERS / "leave_one_year_scores.csv"
    ).is_file() else pd.DataFrame()
    leave = _read_json(RIVERS / "public_river_check.json")
    reservoir = _read_json(CATALOG / "reservoir_operations_check.json")
    usable = (
        clusters.loc[clusters["enough_overlap_years"].fillna(False)]
        if not clusters.empty and "enough_overlap_years" in clusters
        else clusters
    )
    guessed_ok = (
        guessed.loc[guessed.get("can_use_to_build_method", pd.Series(dtype=bool)).fillna(False)]
        if not guessed.empty
        else guessed
    )
    lines = [
        "# 下一篇目前有的结果",
        "",
        "还没有最后一次检验，所以这不是可以投稿的结果段。下面只写已经算出来的数字。",
        "",
        "## 公开目录（只看站年和同期，不看留到最后的河的水温）",
        "",
    ]
    if national:
        lines.append(
            f"- USGS 日均水温序列 {national.get('n_usgs_daily_series', '—')} 条，"
            f"其中跨度至少八年的 {national.get('n_usgs_series_span_ge_8yr', '—')} 条。"
        )
        lines.append(
            f"- 按河名和分区归组后，至少四站且目录同期够八年的："
            f"{national.get('n_river_groups_eight_year_overlap', '—')} 条。"
        )
        lines.append(
            f"- 法国 Hub'Eau 连续水温站 {national.get('n_hubeau_stations', '—')} 个；"
            f"河名就是卢瓦尔的 {national.get('n_loire_exact_name', '—')} 个。"
        )
    if not guessed.empty:
        lines.append(
            f"- 原先猜的站号里，能用来定方法的只有 "
            f"{int(guessed_ok['network_id'].nunique()) if not guessed_ok.empty else 0} 条河"
            f"（{', '.join(guessed_ok['name'].astype(str)) if not guessed_ok.empty else '无'}）。"
        )
    if not usable.empty:
        lines.append("")
        lines.append("| 河 | 分区 | 站数 | 目录同期（年） |")
        lines.append("| --- | --- | --- | --- |")
        for row in usable.head(25).itertuples(index=False):
            years = row.catalog_overlap_years
            lines.append(
                f"| {row.river_name} | {row.huc2} | {row.n_stations} | "
                f"{years:.1f} |"
            )
    if not loire.empty:
        lines.append("")
        lines.append(
            f"卢瓦尔干流公开站 {int(len(loire))} 个，从 Sainte-Eulalie 到 Montjean-sur-Loire。"
            "目录没有起止年，当作留到最后看，不下载水温。"
        )
    if not foen.empty:
        lines.append(
            f"瑞士公开站名 {int(len(foen))} 个。历史日均要向 FOEN 订，没有下载。"
        )
    lines.extend(["", "## 已经下载、用来定方法的河", ""])
    if overlap.empty:
        lines.append("还没有写完下载后的重叠年表。")
    else:
        for row in overlap.itertuples(index=False):
            lines.append(
                f"- {getattr(row, 'network_id', '')}：{getattr(row, 'n_stations', '')} 站，"
                f"重叠约 {float(getattr(row, 'overlap_years', 0) or 0):.1f} 年，"
                f"同时有足够站的天数 {getattr(row, 'days_with_min_stations', '')}。"
            )
    n_scored = int(scores["network_id"].nunique()) if not scores.empty and "network_id" in scores else 0
    lines.extend(["", "## 整条河留出来检验", ""])
    if n_scored < 3:
        lines.append(
            f"现在能打分的河只有 {n_scored} 条。少于三条就不能做「每次整条河留出来」。"
            "这不是过关，也不要改口。"
        )
    else:
        result = leave.get("leave_one_river") or {}
        lines.append(
            f"打分河 {n_scored} 条。这次整条河留出："
            f"{'过关' if result.get('passed') else '没有过关'}。"
            f"{(' 原因：' + str(result.get('reason'))) if result.get('reason') else ''}"
        )
    lines.extend(["", "## 水库运行记录", ""])
    if reservoir:
        lines.append(reservoir.get("reason") or "没有对齐的下泄温度、出口深度和对照河。")
        lines.append("因此没有建坝前后对照表，也不写水库因果。")
    else:
        lines.append("还没有查完公开的水库运行目录。")
    lines.extend(
        [
            "",
            "## 还不能写进摘要的",
            "",
            "- 「这个方法在没见过的河上成立」",
            "- 「按这个量选备用站已经明显更好」",
            "- 「水库造成了这种记忆」",
            "",
        ]
    )
    DEST.write_text("\n".join(lines), encoding="utf-8")
    print(DEST)


if __name__ == "__main__":
    main()
