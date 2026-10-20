#!/usr/bin/env python3
"""Build and export the two draw.io schematics.

The 2026-10-20 brief is explicit: architecture and system-design diagrams are
edited and exported in draw.io, not drawn in matplotlib.  This script holds the
layout as data, writes the `.drawio` sources to ``figures/wrr/drawio/`` and calls
the official draw.io desktop exporter in headless mode:

    drawio --no-sandbox --disable-gpu --ozone-platform=headless \
        -x -f pdf --crop -o figures/wrr/<name>.pdf figures/wrr/drawio/<name>.drawio

The AppImage is not vendored (145 MB).  Set ``DRAWIO_BIN`` to the extracted
``drawio`` executable, or let the script find a system install.  If neither is
available it falls back to the repository's XML renderer
(``scripts/205_v17_drawio_export.py``) and says so, so a build without the
desktop app still produces a PDF from the same source.

Outputs (PDF and PNG at the printed width, 5.5 in):

* ``f2_system_design``  -- main-text Figure 2, how a record is admitted
* ``s1_study_design``   -- SI Figure S1, the evidence chain with its counts

Run:

    python3 scripts/337_wrr_drawio_figures.py
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "figures" / "wrr" / "drawio"
OUT_DIRS = [ROOT / "figures" / "wrr", ROOT / "paper" / "wrr" / "figures"]

FONT = "Helvetica"
BODY = 10
HEAD = 11
SMALL = 9
FILL = "#eef2f7"
STROKE = "#7f8ea3"
ACCENT_FILL = "#f7f4ee"
ACCENT_STROKE = "#a89c86"
INK = "#111111"


@dataclass
class Box:
    ident: str
    x: float
    y: float
    w: float
    h: float
    text: str
    fill: str = FILL
    stroke: str = STROKE
    size: int = BODY
    bold: bool = False
    rounded: bool = False


@dataclass
class Band:
    ident: str
    x: float
    y: float
    w: float
    h: float
    label: str
    fill: str = "#faf9f6"
    stroke: str = "#e6e3dc"


@dataclass
class Text:
    ident: str
    x: float
    y: float
    w: float
    h: float
    text: str
    size: int = SMALL
    bold: bool = True
    align: str = "left"


@dataclass
class Edge:
    ident: str
    source: str
    target: str
    label: str = ""
    exit_xy: tuple[float, float] | None = None
    entry_xy: tuple[float, float] | None = None
    points: list[tuple[float, float]] = field(default_factory=list)
    dashed: bool = False
    straight: bool = False


@dataclass
class Diagram:
    ident: str
    width: int
    height: int
    boxes: list[Box]
    edges: list[Edge]
    bands: list[Band] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)


def _esc(text: str) -> str:
    """draw.io stores line breaks as &#10; and escapes XML metacharacters."""

    return html.escape(text, quote=True).replace("\n", "&#10;")


def _style(box: Box) -> str:
    return (
        f"rounded={1 if box.rounded else 0};whiteSpace=wrap;html=1;"
        f"fillColor={box.fill};strokeColor={box.stroke};strokeWidth=1;"
        f"fontFamily={FONT};fontSize={box.size};"
        f"fontStyle={1 if box.bold else 0};fontColor={INK};"
        f"verticalAlign=middle;align=center;spacing=4;"
    )


def _edge_style(edge: Edge) -> str:
    base = "edgeStyle=none;" if edge.straight else "edgeStyle=orthogonalEdgeStyle;"
    style = (
        base + "rounded=0;html=1;"
        f"strokeColor={INK};strokeWidth=1;endArrow=block;endFill=1;endSize=4;"
        f"fontFamily={FONT};fontSize={SMALL};fontColor={INK};labelBackgroundColor=#fcfcfb;"
    )
    if edge.dashed:
        style += "dashed=1;"
    if edge.exit_xy:
        style += f"exitX={edge.exit_xy[0]};exitY={edge.exit_xy[1]};exitDx=0;exitDy=0;"
    if edge.entry_xy:
        style += f"entryX={edge.entry_xy[0]};entryY={edge.entry_xy[1]};entryDx=0;entryDy=0;"
    return style


def to_drawio(diagram: Diagram) -> str:
    lines = [
        '<mxfile host="app.diagrams.net" type="device">',
        f'  <diagram id="{diagram.ident}" name="Page-1">',
        (
            f'    <mxGraphModel dx="{diagram.width}" dy="{diagram.height}" grid="0" '
            'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
            f'page="1" pageScale="1" pageWidth="{diagram.width}" '
            f'pageHeight="{diagram.height}" math="0" shadow="0">'
        ),
        "      <root>",
        '        <mxCell id="0"/>',
        '        <mxCell id="1" parent="0"/>',
        # A page-sized white rectangle keeps --crop from trimming the margins,
        # so the exported PDF is exactly the printed width (528 px = 5.5 in).
        (
            f'        <mxCell id="page" value="" style="rounded=0;whiteSpace=wrap;html=1;'
            f'fillColor=#ffffff;strokeColor=none;" vertex="1" parent="1">'
        ),
        (
            f'          <mxGeometry x="0" y="0" width="{diagram.width}" '
            f'height="{diagram.height}" as="geometry"/>'
        ),
        "        </mxCell>",
    ]
    for band in diagram.bands:
        lines.append(
            f'        <mxCell id="{band.ident}" value="" style="rounded=0;whiteSpace=wrap;html=1;'
            f'fillColor={band.fill};strokeColor={band.stroke};strokeWidth=1;" vertex="1" parent="1">'
        )
        lines.append(
            f'          <mxGeometry x="{band.x:g}" y="{band.y:g}" width="{band.w:g}" '
            f'height="{band.h:g}" as="geometry"/>'
        )
        lines.append("        </mxCell>")
    for text in diagram.texts:
        style = (
            "text;html=1;align=" + text.align + ";verticalAlign=middle;"
            f"fontFamily={FONT};fontSize={text.size};"
            f"fontStyle={1 if text.bold else 0};fontColor={INK};spacing=0;"
        )
        lines.append(
            f'        <mxCell id="{text.ident}" value="{_esc(text.text)}" style="{style}" '
            'vertex="1" parent="1">'
        )
        lines.append(
            f'          <mxGeometry x="{text.x:g}" y="{text.y:g}" width="{text.w:g}" '
            f'height="{text.h:g}" as="geometry"/>'
        )
        lines.append("        </mxCell>")
    for box in diagram.boxes:
        lines.append(
            f'        <mxCell id="{box.ident}" value="{_esc(box.text)}" style="{_style(box)}" '
            'vertex="1" parent="1">'
        )
        lines.append(
            f'          <mxGeometry x="{box.x:g}" y="{box.y:g}" width="{box.w:g}" '
            f'height="{box.h:g}" as="geometry"/>'
        )
        lines.append("        </mxCell>")
    for edge in diagram.edges:
        lines.append(
            f'        <mxCell id="{edge.ident}" value="{_esc(edge.label)}" '
            f'style="{_edge_style(edge)}" edge="1" parent="1" source="{edge.source}" '
            f'target="{edge.target}">'
        )
        if edge.points:
            lines.append('          <mxGeometry relative="1" as="geometry">')
            lines.append('            <Array as="points">')
            for x, y in edge.points:
                lines.append(f'              <mxPoint x="{x:g}" y="{y:g}"/>')
            lines.append("            </Array>")
            lines.append("          </mxGeometry>")
        else:
            lines.append('          <mxGeometry relative="1" as="geometry"/>')
        lines.append("        </mxCell>")
    lines.extend(["      </root>", "    </mxGraphModel>", "  </diagram>", "</mxfile>"])
    return "\n".join(lines) + "\n"


def system_design() -> Diagram:
    """Main-text Figure 2: how one station-year is admitted, and what it changes."""

    W, H = 528, 258
    bands = [
        Band("b1", 6, 4, 516, 76, "1  data and reconstruction"),
        Band("b2", 6, 86, 516, 80, "2  admission rule"),
        Band("b3", 6, 172, 516, 80, "3  what it changes"),
    ]
    texts = [
        Text("t1", 14, 6, 300, 14, "1  data and reconstruction"),
        Text("t2", 14, 88, 300, 14, "2  admission rule"),
        Text("t3", 14, 174, 300, 14, "3  what it changes"),
    ]
    boxes = [
        Box("truth", 16, 24, 108, 48, "Reference truth\n5,114 station-years", size=SMALL),
        Box("outage", 142, 24, 108, 48, "Designed outages\n33,749 single-run\n19,972 transplanted", size=SMALL),
        Box("recon", 268, 24, 124, 48, "Reconstruction policy\n5 methods, leave-one-\nyear-out", size=SMALL),
        Box("object", 410, 24, 96, 48, "Admitted object\nerror e; fail if\ne > 0.5 °C", size=SMALL),
        Box("features", 16, 106, 108, 52, "Decision-time features\n22; no hidden day", size=SMALL),
        Box("scores", 142, 106, 108, 52, "Scores\nℓ, ĥ, b, fitted q0.9", size=SMALL),
        Box("calib", 268, 106, 124, 52, "Calibration\n5 folds × 3 seeds\nclustered 5% band", size=SMALL),
        Box("decide", 410, 106, 96, 52, "Decision\ns ≤ τ: admit\nelse abstain", fill=ACCENT_FILL, stroke=ACCENT_STROKE, size=SMALL),
        Box("error", 16, 192, 150, 52, "Error and retention\namong admitted years", size=SMALL),
        Box("hot", 184, 192, 150, 52, "Hot-year composition\nadmitted, refused, missed", size=SMALL),
        Box("regime", 352, 192, 154, 52, "Regime check\nshare of peak hidden?\nscreen only if large", size=SMALL),
    ]
    edges = [
        Edge("e1", "truth", "outage"),
        Edge("e2", "outage", "recon"),
        Edge("e3", "recon", "object"),
        Edge("e4", "object", "decide", exit_xy=(0.5, 1), entry_xy=(0.5, 0), label="failure event"),
        Edge("e5", "features", "scores"),
        Edge("e6", "scores", "calib"),
        Edge("e7", "calib", "decide"),
        Edge("e8", "recon", "calib", exit_xy=(0.5, 1), entry_xy=(0.5, 0), dashed=True,
             label="labels for calibration"),
        Edge("e9", "decide", "error", straight=True),
        Edge("e10", "decide", "hot", straight=True),
        Edge("e11", "decide", "regime", straight=True),
    ]
    return Diagram("f2_system_design", W, H, boxes, edges, bands, texts)


def study_design() -> Diagram:
    """SI Figure S1: the evidence chain, with the counts it rests on."""

    W, H = 528, 176
    bands = [
        Band("b1", 6, 4, 516, 82, "reference truth and designed outages"),
        Band("b2", 6, 94, 516, 76, "real gap calendars and what they can carry"),
    ]
    texts = [
        Text("t1", 14, 6, 330, 13, "reference truth and designed outages"),
        Text("t2", 14, 96, 330, 13, "real gap calendars and what they can carry"),
    ]
    boxes = [
        Box("truth", 16, 24, 112, 50, "Complete reference\n5,114 station-years\n146 networks", size=SMALL),
        Box("designed", 144, 24, 100, 50, "Designed outages\n53,721 cases\n2 designs", size=SMALL),
        Box("dev", 260, 20, 116, 24, "Development\n40,704 / 110 groups", size=SMALL),
        Box("ext", 260, 50, 116, 24, "External\n13,017 / 41 groups", size=SMALL),
        Box("compare", 392, 20, 118, 54, "Admission comparison\n5% cap, group cross-fit", size=SMALL),
        Box("archive", 16, 112, 112, 40, "Real archive\n2,422 incomplete years", size=SMALL),
        Box("calendar", 144, 108, 100, 50, "Real calendars\n418 groups, 59 gaps\n14 networks", size=SMALL),
        Box("probe", 392, 108, 118, 44, "Deployment probe\nwhat screening does\non real calendars", size=SMALL),
    ]
    edges = [
        Edge("e1", "truth", "designed"),
        Edge("e2", "designed", "dev", exit_xy=(1, 0.4), entry_xy=(0, 0.5),
             points=[(252, 44), (252, 32)]),
        Edge("e3", "designed", "ext", exit_xy=(1, 0.6), entry_xy=(0, 0.5),
             points=[(252, 54), (252, 62)]),
        Edge("e4", "dev", "compare", exit_xy=(1, 0.5), entry_xy=(0, 0.25), points=[(384, 32), (384, 33)]),
        Edge("e5", "ext", "compare", exit_xy=(1, 0.5), entry_xy=(0, 0.75), points=[(384, 62), (384, 60)]),
        Edge("e6", "archive", "calendar"),
        Edge("e7", "calendar", "probe", exit_xy=(1, 0.5), entry_xy=(0, 0.5)),
    ]
    return Diagram("s1_study_design", W, H, boxes, edges, bands, texts)


def find_drawio(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() else None
    candidate = os.environ.get("DRAWIO_BIN")
    if candidate and Path(candidate).exists():
        return candidate
    for name in ("drawio", "draw.io"):
        found = shutil.which(name)
        if found:
            return found
    # common extracted-AppImage location used by the 2026-10-20 run
    for path in (Path("/tmp/squashfs-root/drawio"), Path.home() / "drawio/drawio"):
        if path.exists():
            return str(path)
    return None


def export(diagram: Diagram, binary: str | None) -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    source = SOURCE_DIR / f"{diagram.ident}.drawio"
    source.write_text(to_drawio(diagram))
    for out_dir in OUT_DIRS:
        out_dir.mkdir(parents=True, exist_ok=True)
    if binary:
        for fmt in ("pdf", "png"):
            for out_dir in OUT_DIRS:
                target = out_dir / f"{diagram.ident}.{fmt}"
                command = [
                    binary,
                    "--no-sandbox",
                    "--disable-gpu",
                    "--ozone-platform=headless",
                    "-x",
                    "-f",
                    fmt,
                    "--crop",
                    "-b",
                    "0",
                    "--scale",
                    "3" if fmt == "png" else "1",
                    "-o",
                    str(target),
                    str(source),
                ]
                result = subprocess.run(command, capture_output=True, text=True)
                if result.returncode != 0 or not target.exists():
                    sys.stderr.write(result.stdout + result.stderr)
                    raise SystemExit(f"draw.io export failed for {target}")
                print(f"[drawio] {source.name} -> {target.relative_to(ROOT)}")
        return
    # Fallback: the repository renderer, same XML.
    renderer = ROOT / "scripts" / "205_v17_drawio_export.py"
    print(f"[drawio] desktop exporter not found; using {renderer.name} on the same XML")
    shutil.copy2(source, ROOT / "figures" / "v17" / "drawio" / source.name)
    subprocess.run(
        [sys.executable, str(renderer), "--name", diagram.ident, "--print-width-in", "5.5"],
        check=False,
    )
    for out_dir in OUT_DIRS:
        candidate = ROOT / "figures" / "v17" / f"{diagram.ident}.pdf"
        if candidate.exists():
            shutil.copy2(candidate, out_dir / f"{diagram.ident}.pdf")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawio", default=None, help="path to the draw.io executable")
    args = parser.parse_args()
    binary = find_drawio(args.drawio)
    if binary:
        print(f"[drawio] using {binary}")
    for diagram in (system_design(), study_design()):
        export(diagram, binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
