#!/usr/bin/env python3
"""Render the study's draw.io sources to PDF.

The `.drawio` files under `figures/v17/drawio/` are the editable source of
truth for every architecture and system-design figure; they open unchanged in
draw.io / diagrams.net.  Where the draw.io desktop application is installed the
official exporter should be preferred:

    drawio -x -f pdf --crop -o figures/v17/<name>.pdf figures/v17/drawio/<name>.drawio

That application is an Electron binary and cannot be installed in every build
environment, so this script renders the *same* XML through a small mxGraph
subset renderer (SVG, then `rsvg-convert` to PDF).  It supports exactly the
shapes the sources use — rectangles, rounded rectangles, ellipses, notes,
orthogonal edges with explicit waypoints and labels, and `html=1` labels whose
lines carry `<b>` / `<i>` runs — and fails loudly on anything else rather than
silently dropping it, so a figure edited in draw.io cannot quietly stop
matching its PDF.

The PDF is written at the width it will be printed at (`--print-width-in`,
5.5 in by default, the AGU single column), the same rule the analysis figures
follow through `stream_recoverability.plotting.journal`.  A schematic is
therefore never scaled down by the manuscript, and the type size measured in
the PDF is the type size on the page.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "figures" / "v17" / "drawio"
OUTPUT_DIR = ROOT / "figures" / "v17"

FONT_STACK = "Helvetica, Arial, 'Liberation Sans', sans-serif"
SUPPORTED_SHAPES = {"rectangle", "rounded", "ellipse", "note", "label", "hexagon"}

#: Printed width of a schematic, in inches: the AGU single column.
PRINT_WIDTH_IN = 5.5

#: Inline runs of a draw.io ``html=1`` label.
TAG_RE = re.compile(r"</?([bi])>", re.IGNORECASE)


def parse_style(style: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in (style or "").split(";"):
        token = token.strip()
        if not token:
            continue
        key, _, value = token.partition("=")
        parsed[key] = value
    return parsed


@dataclass
class Vertex:
    cell_id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    style: dict[str, str]

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2


@dataclass
class Edge:
    cell_id: str
    label: str
    source: str
    target: str
    style: dict[str, str]
    waypoints: list[tuple[float, float]] = field(default_factory=list)


def read_diagram(path: Path) -> tuple[str, dict[str, Vertex], list[Edge]]:
    root = ET.parse(path).getroot()
    diagram = root if root.tag == "mxGraphModel" else root.find(".//mxGraphModel")
    if diagram is None:
        raise SystemExit(f"{path}: no mxGraphModel; compressed .drawio files are not supported")
    title_node = root.find(".//diagram")
    title = title_node.get("name", path.stem) if title_node is not None else path.stem

    vertices: dict[str, Vertex] = {}
    edges: list[Edge] = []
    for cell in diagram.iter("mxCell"):
        style = parse_style(cell.get("style"))
        label = html.unescape(cell.get("value") or "")
        if cell.get("vertex") == "1":
            geometry = cell.find("mxGeometry")
            if geometry is None:
                continue
            shape = "rounded" if style.get("rounded") == "1" else style.get("shape", "rectangle")
            if style.get("ellipse") is not None:
                shape = "ellipse"
            if shape not in SUPPORTED_SHAPES:
                raise SystemExit(f"{path}: unsupported shape {shape!r} on cell {cell.get('id')}")
            vertices[cell.get("id", "")] = Vertex(
                cell_id=cell.get("id", ""),
                label=label,
                x=float(geometry.get("x", 0)),
                y=float(geometry.get("y", 0)),
                width=float(geometry.get("width", 0)),
                height=float(geometry.get("height", 0)),
                style=style | {"shape": shape},
            )
        elif cell.get("edge") == "1":
            points: list[tuple[float, float]] = []
            for array in cell.iter("Array"):
                if array.get("as") != "points":
                    continue
                for point in array.iter("mxPoint"):
                    points.append((float(point.get("x", 0)), float(point.get("y", 0))))
            edges.append(
                Edge(
                    cell_id=cell.get("id", ""),
                    label=label,
                    source=cell.get("source", ""),
                    target=cell.get("target", ""),
                    style=style,
                    waypoints=points,
                )
            )
    return title, vertices, edges


def clip_to_box(vertex: Vertex, toward: tuple[float, float]) -> tuple[float, float]:
    """Where the segment from the vertex centre toward `toward` leaves the box."""
    dx, dy = toward[0] - vertex.cx, toward[1] - vertex.cy
    if dx == 0 and dy == 0:
        return vertex.cx, vertex.cy
    half_w, half_h = vertex.width / 2 + 1, vertex.height / 2 + 1
    scale_x = half_w / abs(dx) if dx else float("inf")
    scale_y = half_h / abs(dy) if dy else float("inf")
    scale = min(scale_x, scale_y)
    return vertex.cx + dx * scale, vertex.cy + dy * scale


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_runs(line: str, bold: bool) -> list[tuple[str, bool, bool]]:
    """Split one line of a draw.io rich-text label into (text, bold, italic)."""
    runs: list[tuple[str, bool, bool]] = []
    italic = False
    position = 0
    for match in TAG_RE.finditer(line):
        if match.start() > position:
            runs.append((line[position : match.start()], bold, italic))
        closing = match.group(0).startswith("</")
        if match.group(1).lower() == "b":
            bold = not closing
        else:
            italic = not closing
        position = match.end()
    if position < len(line):
        runs.append((line[position:], bold, italic))
    if not runs:
        runs.append((line, bold, False))
    return runs


def text_block(
    label: str,
    cx: float,
    top: float,
    size: float,
    colour: str,
    bold: bool,
    anchor: str = "middle",
    line_height: float = 1.28,
    rich: bool = False,
) -> list[str]:
    lines = label.split("\n")
    out = []
    for index, line in enumerate(lines):
        baseline = top + size * (0.82 + index * line_height)
        head = (
            f'<text x="{cx:.1f}" y="{baseline:.1f}" font-family="{FONT_STACK}" '
            f'font-size="{size:.1f}" fill="{colour}" text-anchor="{anchor}"'
        )
        runs = inline_runs(line, bold) if rich else [(line, bold, False)]
        if len(runs) == 1 and not runs[0][2]:
            weight = ' font-weight="600"' if runs[0][1] else ""
            out.append(f"{head}{weight} xml:space=\"preserve\">{escape(runs[0][0])}</text>")
            continue
        spans = []
        for text, run_bold, run_italic in runs:
            if not text:
                continue
            weight = ' font-weight="600"' if run_bold else ""
            style = ' font-style="italic"' if run_italic else ""
            spans.append(f"<tspan{weight}{style}>{escape(text)}</tspan>")
        out.append(f'{head} xml:space="preserve">{"".join(spans)}</text>')
    return out


def render_svg(
    title: str,
    vertices: dict[str, Vertex],
    edges: list[Edge],
    print_width_in: float = PRINT_WIDTH_IN,
) -> str:
    margin = 24.0
    xs = [v.x for v in vertices.values()] + [p[0] for e in edges for p in e.waypoints]
    ys = [v.y for v in vertices.values()] + [p[1] for e in edges for p in e.waypoints]
    xe = [v.x + v.width for v in vertices.values()] + [p[0] for e in edges for p in e.waypoints]
    ye = [v.y + v.height for v in vertices.values()] + [p[1] for e in edges for p in e.waypoints]
    min_x, min_y, max_x, max_y = min(xs), min(ys), max(xe), max(ye)
    width, height = max_x - min_x + 2 * margin, max_y - min_y + 2 * margin
    shift_x, shift_y = margin - min_x, margin - min_y
    print_height_in = height * print_width_in / width

    body: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{print_width_in:.3f}in" '
        f'height="{print_height_in:.3f}in" viewBox="0 0 {width:.0f} {height:.0f}">',
        f"<title>{escape(title)}</title>",
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#37474f"/></marker>'
        '<marker id="arrowdim" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#90a4ae"/></marker></defs>',
        f'<g transform="translate({shift_x:.1f},{shift_y:.1f})">',
    ]

    # containers first so their children draw on top
    order = sorted(vertices.values(), key=lambda v: -(v.width * v.height))
    for vertex in order:
        style = vertex.style
        fill = style.get("fillColor", "#ffffff")
        stroke = style.get("strokeColor", "#37474f")
        dash = ' stroke-dasharray="6 4"' if style.get("dashed") == "1" else ""
        stroke_width = style.get("strokeWidth", "1.4")
        if fill == "none":
            fill = "none"
        if vertex.style["shape"] == "ellipse":
            body.append(
                f'<ellipse cx="{vertex.cx:.1f}" cy="{vertex.cy:.1f}" rx="{vertex.width/2:.1f}" '
                f'ry="{vertex.height/2:.1f}" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{stroke_width}"{dash}/>'
            )
        elif vertex.style["shape"] == "label":
            pass
        else:
            radius = 10 if vertex.style["shape"] in {"rounded", "note"} else 0
            body.append(
                f'<rect x="{vertex.x:.1f}" y="{vertex.y:.1f}" width="{vertex.width:.1f}" '
                f'height="{vertex.height:.1f}" rx="{radius}" ry="{radius}" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="{stroke_width}"{dash}/>'
            )
        if not vertex.label:
            continue
        size = float(style.get("fontSize", 12))
        colour = style.get("fontColor", "#102027")
        bold = style.get("fontStyle") in {"1", "3"}
        lines = vertex.label.count("\n") + 1
        vertical = style.get("verticalAlign", "middle")
        align = style.get("align", "center")
        block_height = size * (0.82 + (lines - 1) * 1.28)
        if vertical == "top":
            top = vertex.y + 9
        else:
            top = vertex.cy - block_height / 2
        if align == "left":
            anchor, cx = "start", vertex.x + 12
        elif align == "right":
            anchor, cx = "end", vertex.x + vertex.width - 12
        else:
            anchor, cx = "middle", vertex.cx
        body.extend(
            text_block(
                vertex.label,
                cx,
                top,
                size,
                colour,
                bold,
                anchor,
                rich=style.get("html") == "1",
            )
        )

    for edge in edges:
        source, target = vertices.get(edge.source), vertices.get(edge.target)
        if source is None or target is None:
            raise SystemExit(f"edge {edge.cell_id} has a dangling endpoint")
        points = edge.waypoints
        start = clip_to_box(source, points[0] if points else (target.cx, target.cy))
        end = clip_to_box(target, points[-1] if points else (source.cx, source.cy))
        path = [start, *points, end]
        dim = edge.style.get("strokeColor", "#37474f") in {"#90a4ae", "#b0bec5"}
        stroke = edge.style.get("strokeColor", "#37474f")
        dash = ' stroke-dasharray="6 4"' if edge.style.get("dashed") == "1" else ""
        marker = "arrowdim" if dim else "arrow"
        head = "" if edge.style.get("endArrow") == "none" else f' marker-end="url(#{marker})"'
        points_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in path)
        body.append(
            f'<polyline points="{points_text}" fill="none" stroke="{stroke}" '
            f'stroke-width="{edge.style.get("strokeWidth", "1.4")}"{dash}{head}/>'
        )
        if edge.label:
            mid_index = len(path) // 2
            if len(path) % 2 == 0:
                mx = (path[mid_index - 1][0] + path[mid_index][0]) / 2
                my = (path[mid_index - 1][1] + path[mid_index][1]) / 2
            else:
                mx, my = path[mid_index]
            size = float(edge.style.get("fontSize", 10.5))
            lines = edge.label.count("\n") + 1
            colour = edge.style.get("fontColor", "#455a64")
            pad = 3.0
            longest = max(len(line) for line in edge.label.split("\n"))
            box_w = longest * size * 0.54 + 2 * pad
            box_h = size * 1.28 * lines + pad
            body.append(
                f'<rect x="{mx - box_w/2:.1f}" y="{my - box_h/2:.1f}" width="{box_w:.1f}" '
                f'height="{box_h:.1f}" fill="#ffffff" stroke="none"/>'
            )
            body.extend(text_block(edge.label, mx, my - box_h / 2 + pad / 2, size, colour, False))

    body.append("</g></svg>")
    return "\n".join(body)


def export(path: Path, print_width_in: float = PRINT_WIDTH_IN) -> Path:
    title, vertices, edges = read_diagram(path)
    svg = render_svg(title, vertices, edges, print_width_in)
    svg_path = OUTPUT_DIR / f"{path.stem}.svg"
    pdf_path = OUTPUT_DIR / f"{path.stem}.pdf"
    svg_path.write_text(svg, encoding="utf-8")
    if shutil.which("rsvg-convert") is None:
        raise SystemExit("rsvg-convert is required to produce PDF; install librsvg2-bin")
    subprocess.run(
        ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
        check=True,
    )
    return pdf_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--print-width-in",
        type=float,
        default=PRINT_WIDTH_IN,
        help=f"printed width of the exported PDF in inches (default {PRINT_WIDTH_IN})",
    )
    parser.add_argument("sources", nargs="*", help=".drawio files (default: every source)")
    args = parser.parse_args(argv[1:])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sources = [Path(a).resolve() for a in args.sources] or sorted(SOURCE_DIR.glob("*.drawio"))
    if not sources:
        raise SystemExit(f"no .drawio sources under {SOURCE_DIR}")
    for source in sources:
        pdf = export(source, args.print_width_in)
        print(f"{source.relative_to(ROOT)} -> {pdf.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
