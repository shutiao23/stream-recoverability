#!/usr/bin/env python3
"""Redraw the study-station locator map with Natural Earth country outlines.

The input station roster is read-only. Country outlines are Natural Earth
1:50m admin-0 polygons (public domain), projected to ETRS89-LAEA for Europe
and Albers Equal Area for the United States. Run from the repository root:

    python paper/ems/figures/make_sample_map.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ROSTER = ROOT / "results/wrr_process_revision_20261029/station_roster.csv"
CACHE = Path("/tmp/kilo/ne/ne_50m_admin_0_countries.geojson")
URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)

LAND = "#f5f3ed"
COAST = "#8f9296"
SEA = "#e8f0f6"
GRID = "#d6dee6"
BAVARIA = "#c85b1b"
SWISS = "#2b6f9e"
FINLAND = "#2f855a"
US = "#6b4c9a"


def load_countries() -> list[list[tuple[float, float]]]:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, CACHE)
    data = json.loads(CACHE.read_text())
    rings: list[list[tuple[float, float]]] = []
    for feature in data["features"]:
        geom = feature.get("geometry") or {}
        kind = geom.get("type")
        coords = geom.get("coordinates") or []
        if kind == "Polygon":
            polygons = [coords]
        elif kind == "MultiPolygon":
            polygons = coords
        else:
            continue
        for polygon in polygons:
            if not polygon:
                continue
            ring = np.asarray(polygon[0], dtype=float)
            if ring.shape[0] >= 4:
                rings.append(ring)
    return rings


def projected_bounds(
    transformer: Transformer,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
) -> tuple[float, float, float, float]:
    lons = np.linspace(lon_min, lon_max, 200)
    lats = np.linspace(lat_min, lat_max, 200)
    edge_lons = np.concatenate(
        [lons, lons, np.full_like(lats, lon_min), np.full_like(lats, lon_max)]
    )
    edge_lats = np.concatenate(
        [np.full_like(lons, lat_min), np.full_like(lons, lat_max), lats, lats]
    )
    xs, ys = transformer.transform(edge_lons, edge_lats)
    return float(np.min(xs)), float(np.max(xs)), float(np.min(ys)), float(np.max(ys))


def draw_land(
    ax: plt.Axes,
    rings: list[list[tuple[float, float]]],
    transformer: Transformer,
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
) -> None:
    for ring in rings:
        lon = ring[:, 0]
        lat = ring[:, 1]
        if (
            lon.max() < lon_min - 2
            or lon.min() > lon_max + 2
            or lat.max() < lat_min - 2
            or lat.min() > lat_max + 2
        ):
            continue
        x, y = transformer.transform(lon, lat)
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            continue
        ax.fill(
            x,
            y,
            facecolor=LAND,
            edgecolor=COAST,
            linewidth=0.32,
            zorder=1,
            antialiased=True,
        )


def panel(
    fig: plt.Figure,
    position: list[float],
    transformer: Transformer,
    rings: list[list[tuple[float, float]]],
    extent: tuple[float, float, float, float],
    title: str,
) -> plt.Axes:
    ax = fig.add_axes(position)
    lon_min, lon_max, lat_min, lat_max = extent
    ax.set_facecolor(SEA)
    x0, x1, y0, y1 = projected_bounds(transformer, lon_min, lon_max, lat_min, lat_max)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    draw_land(ax, rings, transformer, lon_min, lon_max, lat_min, lat_max)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_linewidth(0.65)
        spine.set_color("#6f7377")
    ax.set_title(title, fontsize=9.0, fontweight="semibold", loc="left", pad=3.5)
    return ax


def main() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.titlesize": 9.0,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "figure.facecolor": "white",
        }
    )
    roster = pd.read_csv(ROSTER)
    expected = {
        "gkd_bayern": 24,
        "foen": 10,
        "syke": 1,
        "usgs_huc03": 1,
        "usgs_huc04": 1,
        "usgs_huc10": 2,
        "usgs_huc17": 3,
    }
    counts = roster.groupby("region").size().to_dict()
    if counts != expected:
        raise SystemExit(f"unexpected station counts: {counts!r}")
    if roster[["latitude", "longitude"]].isna().any().any():
        raise SystemExit("missing station coordinates")

    rings = load_countries()
    europe = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
    albers = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    finland = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)

    fig = plt.figure(figsize=(7.05, 3.35))

    # (a) Central Europe: Switzerland and Bavaria.
    ax = panel(
        fig,
        [0.035, 0.075, 0.54, 0.84],
        europe,
        rings,
        (4.8, 16.6, 45.0, 51.4),
        "(a) Central Europe",
    )
    central = roster.loc[roster.region.isin(["foen", "gkd_bayern"])]
    for region, color, marker, size, label in [
        ("gkd_bayern", BAVARIA, "s", 18, "Bavaria (24)"),
        ("foen", SWISS, "o", 22, "Switzerland (10)"),
    ]:
        block = central.loc[central.region.eq(region)]
        x, y = europe.transform(block.longitude.to_numpy(), block.latitude.to_numpy())
        ax.scatter(
            x,
            y,
            s=size,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            zorder=4,
            label=label,
        )
    ax.legend(
        loc="lower left",
        fontsize=7.4,
        frameon=True,
        framealpha=0.92,
        facecolor="white",
        edgecolor="none",
        borderpad=0.35,
        labelspacing=0.3,
        handletextpad=0.4,
    )
    ax.text(
        *europe.transform(13.35, 50.15),
        "Bavaria",
        fontsize=7.4,
        color="#7a3a11",
        ha="left",
        va="bottom",
        zorder=5,
    )
    ax.text(
        *europe.transform(6.55, 46.15),
        "Switzerland",
        fontsize=7.4,
        color="#1f4e6f",
        ha="left",
        va="top",
        zorder=5,
    )

    # (b) United States HUC groups.
    us_ax = panel(
        fig,
        [0.625, 0.505, 0.355, 0.395],
        albers,
        rings,
        (-126.0, -66.0, 24.0, 50.5),
        "(b) United States (inset)",
    )
    us = roster.loc[roster.region.str.startswith("usgs_")]
    us_styles = {
        "usgs_huc03": ("*", 42, "HUC03 (1)"),
        "usgs_huc04": ("s", 20, "HUC04 (1)"),
        "usgs_huc10": ("^", 24, "HUC10 (2)"),
        "usgs_huc17": ("D", 20, "HUC17 (3)"),
    }
    handles = []
    for region in ["usgs_huc03", "usgs_huc04", "usgs_huc10", "usgs_huc17"]:
        block = us.loc[us.region.eq(region)]
        marker, size, label = us_styles[region]
        x, y = albers.transform(block.longitude.to_numpy(), block.latitude.to_numpy())
        us_ax.scatter(
            x,
            y,
            s=size,
            marker=marker,
            color=US,
            edgecolor="white",
            linewidth=0.4,
            zorder=4,
        )
        handles.append(
            Line2D(
                [0],
                [0],
                marker=marker,
                color="none",
                markerfacecolor=US,
                markeredgecolor="white",
                markeredgewidth=0.4,
                markersize=4.2,
                label=label,
            )
        )
    us_ax.legend(
        handles=handles,
        loc="lower left",
        fontsize=6.4,
        frameon=True,
        framealpha=0.92,
        facecolor="white",
        edgecolor="none",
        borderpad=0.25,
        labelspacing=0.22,
        handletextpad=0.35,
    )

    # (c) Finland reference site.
    fi_ax = panel(
        fig,
        [0.71, 0.09, 0.245, 0.315],
        finland,
        rings,
        (15.0, 33.0, 58.0, 67.0),
        "(c) Finland (inset)",
    )
    fi = roster.loc[roster.region.eq("syke")]
    x, y = finland.transform(fi.longitude.to_numpy(), fi.latitude.to_numpy())
    fi_ax.scatter(
        x,
        y,
        s=38,
        marker="D",
        color=FINLAND,
        edgecolor="white",
        linewidth=0.5,
        zorder=4,
    )
    fi_ax.annotate(
        "Finland (n=1)",
        xy=(x[0], y[0]),
        xytext=(-4, 8),
        textcoords="offset points",
        fontsize=6.4,
        color="#1f5c3d",
        ha="right",
        va="bottom",
        zorder=5,
    )

    fig.savefig(OUT / "study_stations.pdf", bbox_inches="tight", pad_inches=0.04)
    fig.savefig(OUT / "study_stations.png", dpi=300, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


if __name__ == "__main__":
    main()
