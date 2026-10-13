#!/usr/bin/env python3
"""Verify the exported schematic PDFs at final (journal column) size.

Checks, per figure:
  1. one page, and the page is the 5.5 in AGU column width;
  2. every font in the PDF is embedded (`pdffonts`);
  3. no word outside the page box (`pdftotext -bbox`);
  4. no two words overlapping (`pdftotext -bbox`);
  5. no word spilling out of the box it belongs to, as measured against the
     .drawio source geometry;
  6. the smallest word height, which equals the smallest type size on the page
     because the PDF is exported at print size.

Usage: python3 scratch/drawio/verify_figures.py
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "drawio_export", ROOT / "scripts" / "205_v17_drawio_export.py"
)
drawio_export = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["drawio_export"] = drawio_export
_spec.loader.exec_module(drawio_export)

FIGURES = [
    "f0_problem_frame",
    "f1_system_architecture",
    "f2_experiment_design",
    "f3_evidence_chain",
    "f4_deployment_workflow",
]
WORD_RE = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>'
)
MIN_TEXT_PT = 5.0


def words(pdf: Path) -> list[tuple[float, float, float, float, str]]:
    out = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    return [
        (float(a), float(b), float(c), float(d), e)
        for a, b, c, d, e in WORD_RE.findall(out)
    ]


def pdfinfo(pdf: Path) -> dict[str, str]:
    out = subprocess.run(["pdfinfo", str(pdf)], check=True, capture_output=True, text=True).stdout
    return dict(
        line.split(":", 1) for line in out.splitlines() if ":" in line
    )


def pdffonts(pdf: Path) -> list[tuple[str, bool]]:
    out = subprocess.run(["pdffonts", str(pdf)], check=True, capture_output=True, text=True).stdout
    fonts = []
    for line in out.splitlines()[2:]:
        if not line.strip():
            continue
        fonts.append((line[:36].strip(), line[71:].split()[0] == "yes"))
    return fonts


def edge_label_boxes(vertices, edges) -> list[tuple[str, str, float, float, float, float]]:
    """The white label boxes the renderer draws under edge labels.

    Returned in the same (name, label, x, y, w, h) layout as a vertex box.
    """
    boxes = []
    for edge in edges:
        if not edge.label:
            continue
        source, target = vertices[edge.source], vertices[edge.target]
        points = edge.waypoints
        start = drawio_export.clip_to_box(source, points[0] if points else (target.cx, target.cy))
        end = drawio_export.clip_to_box(target, points[-1] if points else (source.cx, source.cy))
        path = [start, *points, end]
        mid_index = len(path) // 2
        if len(path) % 2 == 0:
            mx = (path[mid_index - 1][0] + path[mid_index][0]) / 2
            my = (path[mid_index - 1][1] + path[mid_index][1]) / 2
        else:
            mx, my = path[mid_index]
        size = float(edge.style.get("fontSize", 10.5))
        lines = edge.label.count("\n") + 1
        longest = max(len(line) for line in edge.label.split("\n"))
        box_w = longest * size * 0.54 + 6.0
        box_h = size * 1.28 * lines + 3.0
        boxes.append((f"edge:{edge.cell_id}", "edge label", mx - box_w / 2, my - box_h / 2, box_w, box_h))
    return boxes


def check(name: str) -> dict:
    pdf = ROOT / "figures" / "v17" / f"{name}.pdf"
    source = ROOT / "figures" / "v17" / "drawio" / f"{name}.drawio"
    info = pdfinfo(pdf)
    page_w, page_h = (float(v.replace("pts", "").strip()) for v in info["Page size"].split("x"))
    report: dict = {
        "figure": name,
        "pages": int(info["Pages"]),
        "page_in": (round(page_w / 72, 3), round(page_h / 72, 3)),
        "fonts": pdffonts(pdf),
    }
    report["fonts_embedded"] = all(emb for _, emb in report["fonts"])

    # source geometry, exactly as the renderer sees it
    _title, vertices, edges = drawio_export.read_diagram(source)
    margin = 24.0
    xs = [v.x for v in vertices.values()] + [p[0] for e in edges for p in e.waypoints]
    ys = [v.y for v in vertices.values()] + [p[1] for e in edges for p in e.waypoints]
    xe = [v.x + v.width for v in vertices.values()] + [p[0] for e in edges for p in e.waypoints]
    ye = [v.y + v.height for v in vertices.values()] + [p[1] for e in edges for p in e.waypoints]
    min_x, min_y = min(xs), min(ys)
    unit_w, unit_h = max(xe) - min_x + 2 * margin, max(ye) - min_y + 2 * margin
    to_unit = unit_w / page_w  # PDF pt -> drawing units

    ws = words(pdf)
    report["words"] = len(ws)
    report["min_text_pt"] = round(min(w[3] - w[1] for w in ws), 3)
    report["max_text_pt"] = round(max(w[3] - w[1] for w in ws), 3)

    outside = [
        w for w in ws if w[0] < -0.5 or w[1] < -0.5 or w[2] > page_w + 0.5 or w[3] > page_h + 0.5
    ]
    report["words_outside_page"] = len(outside)

    overlaps = []
    for i, a in enumerate(ws):
        for b in ws[i + 1 :]:
            dx = min(a[2], b[2]) - max(a[0], b[0])
            dy = min(a[3], b[3]) - max(a[1], b[1])
            if dx > 0.3 and dy > 0.3:
                overlaps.append((a[4], b[4], round(dx * dy, 2)))
    report["word_overlaps"] = overlaps

    # every word must sit inside the vertex box or edge-label box that holds its centre
    boxes = [
        (v.cell_id, v.label.split("\n")[0][:28], v.x, v.y, v.width, v.height)
        for v in vertices.values()
    ] + edge_label_boxes(vertices, edges)
    spills = []
    for x1, y1, x2, y2, text in ws:
        ux = x1 * to_unit + min_x - margin
        uy = y1 * to_unit + min_y - margin
        ux2 = x2 * to_unit + min_x - margin
        uy2 = y2 * to_unit + min_y - margin
        cx, cy = (ux + ux2) / 2, (uy + uy2) / 2
        host = next(
            (b for b in boxes if b[2] - 1 <= cx <= b[2] + b[4] + 1 and b[3] - 1 <= cy <= b[3] + b[5] + 1),
            None,
        )
        if host is None:
            spills.append((text, "no box", round(ux), round(uy)))
            continue
        left, top, right, bottom = host[2], host[3], host[2] + host[4], host[3] + host[5]
        if ux < left - 2 or ux2 > right + 2 or uy < top - 2 or uy2 > bottom + 2:
            spills.append(
                (
                    text,
                    host[1],
                    f"word {ux:.0f},{uy:.0f}-{ux2:.0f},{uy2:.0f} vs box {left:.0f},{top:.0f}-{right:.0f},{bottom:.0f}",
                )
            )
    report["words_outside_their_box"] = spills
    report["ok"] = (
        report["pages"] == 1
        and abs(page_w - 396) < 1.0
        and report["fonts_embedded"]
        and report["words_outside_page"] == 0
        and not report["word_overlaps"]
        and not spills
        and report["min_text_pt"] >= MIN_TEXT_PT
    )
    return report


def main() -> int:
    failures = 0
    for name in FIGURES:
        r = check(name)
        print(f"\n=== {r['figure']}")
        print(f"  pages={r['pages']}  page={r['page_in'][0]}x{r['page_in'][1]} in")
        print(f"  fonts embedded: {r['fonts_embedded']} ({len(r['fonts'])} faces: "
              f"{', '.join(f for f, _ in r['fonts'])})")
        print(f"  words={r['words']}  min text height={r['min_text_pt']} pt  max={r['max_text_pt']} pt")
        print(f"  words outside page: {r['words_outside_page']}")
        print(f"  overlapping word pairs: {len(r['word_overlaps'])} {r['word_overlaps'][:4]}")
        print(f"  words outside their own box: {len(r['words_outside_their_box'])} "
              f"{r['words_outside_their_box'][:4]}")
        print(f"  PASS: {r['ok']}")
        failures += 0 if r["ok"] else 1
    print(f"\n{len(FIGURES) - failures}/{len(FIGURES)} schematics pass every check")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
