#!/usr/bin/env python3
"""Regenerate the five schematic .drawio sources with a legible geometry.

Why this exists
---------------
The sources under ``figures/v17/drawio/`` are the editable source of truth and
are what gets committed; this script only produced them once, from a spec that
keeps every label next to the manuscript fact it quotes.  It is kept (in
``scratch/``, not in the pipeline) so the geometry can be re-checked: at the AGU
column width of 5.5 in, every label must render at >= 5 pt, which fixes the
ratio of font size to drawing width at

    font_px / width_px >= 5 pt / (5.5 in * 72 pt/in) / 0.75 pt-per-px = 1/79.2

so a drawing 990 px wide can carry fonts no smaller than 12.5 px, and one
988 px wide no smaller than 14 px.

Run ``python3 scratch/drawio/build_sources.py`` to rewrite the sources, then
``python3 scripts/205_v17_drawio_export.py`` to export them.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "v17" / "drawio"

# ---------------------------------------------------------------- palette ----
BLUE = ("#E3F2FD", "#1565C0", "#0D47A1")
PLAIN = ("#FFFFFF", "#37474F", "#102027")
ORANGE = ("#FFF3E0", "#EF6C00", "#E65100")
GREEN = ("#E8F5E9", "#2E7D32", "#1B5E20")
RED = ("#FFEBEE", "#C62828", "#B71C1C")
GREY = ("#ECEFF1", "#546E7A", "#37474F")
NOTE = ("#FFFDE7", "#F9A825", "#795548")

EDGE = "#37474F"
EDGE_DIM = "#90A4AE"
EDGE_RED = "#C62828"
EDGE_GREEN = "#2E7D32"
EDGE_GREY = "#546E7A"


def esc(text: str) -> str:
    """Escape a label for an XML attribute, keeping ``**bold**`` as markup."""
    rich = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return html_escape(rich)


def html_escape(text: str) -> str:
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return out.replace("\n", "&#10;")


def plain(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def width_estimate(line: str, size: float) -> float:
    """Rough advance width of one source line, in drawing units."""
    total = 0.0
    for match in re.finditer(r"\*\*(.+?)\*\*|([^*]+)", line):
        if match.group(1) is not None:
            total += len(match.group(1)) * size * 0.60
        else:
            total += len(match.group(2)) * size * 0.55
    return total


def block_height(lines: list[str], size: float) -> float:
    return size * (0.82 + (len(lines) - 1) * 1.28)


class Figure:
    def __init__(self, diagram_id: str, name: str):
        self.diagram_id = diagram_id
        self.name = name
        self.vertices: list[dict] = []
        self.edges: list[dict] = []

    def box(
        self,
        cid: str,
        x: float,
        y: float,
        w: float,
        h: float,
        lines: str | list[str],
        *,
        size: float = 15.0,
        bold: bool = False,
        palette=PLAIN,
        shape: str = "rounded",
        dashed: bool = False,
        align: str = "center",
        valign: str = "middle",
        font: str | None = None,
        pad: float = 8.0,
    ) -> dict:
        lines = [lines] if isinstance(lines, str) else list(lines)
        fill, stroke, ink = palette
        needed_h = block_height(lines, size) + 2 * 9
        needed_w = max(width_estimate(line, size) for line in lines) + 2 * pad
        if needed_h > h + 0.5:
            print(f"  ! {self.diagram_id}/{cid}: {len(lines)} lines need h>={needed_h:.0f}, have {h:.0f}")
        if needed_w > w + 0.5:
            print(f"  ! {self.diagram_id}/{cid}: widest line needs w>={needed_w:.0f}, have {w:.0f}")
        style = [
            "rounded=1" if shape == "rounded" else "",
            "html=1",
            f"fillColor={fill}",
            f"strokeColor={stroke}",
            f"fontSize={size:g}",
            f"fontColor={font or ink}",
        ]
        if shape == "note":
            style.append("shape=note")
        if bold:
            style.append("fontStyle=1")
        if dashed:
            style.append("dashed=1")
        if valign != "middle":
            style.append(f"verticalAlign={valign}")
        if align != "center":
            style.append(f"align={align}")
        vertex = {
            "id": cid,
            "value": "\n".join(lines),
            "style": ";".join(part for part in style if part),
            "x": x,
            "y": y,
            "w": w,
            "h": h,
        }
        self.vertices.append(vertex)
        return vertex

    def edge(
        self,
        cid: str,
        source: str,
        target: str,
        *,
        label: str = "",
        points: list[tuple[float, float]] | None = None,
        colour: str = EDGE,
        dashed: bool = False,
        arrow: bool = True,
        size: float = 14.0,
        font: str | None = None,
    ) -> dict:
        if label:
            est = width_estimate(label.split("\n")[0], size) * 1.08
            if est > 190:
                print(f"  ! {self.diagram_id}/{cid}: edge label {est:.0f} px wide: {label!r}")
        edge = {
            "id": cid,
            "value": label,
            "source": source,
            "target": target,
            "points": points or [],
            "colour": colour,
            "dashed": dashed,
            "arrow": arrow,
            "size": size,
            "font": font,
        }
        self.edges.append(edge)
        return edge

    # ---------------------------------------------------------------- xml --
    def xml(self) -> str:
        xs = [v["x"] for v in self.vertices] + [p[0] for e in self.edges for p in e["points"]]
        ys = [v["y"] for v in self.vertices] + [p[1] for e in self.edges for p in e["points"]]
        xe = [v["x"] + v["w"] for v in self.vertices] + [p[0] for e in self.edges for p in e["points"]]
        ye = [v["y"] + v["h"] for v in self.vertices] + [p[1] for e in self.edges for p in e["points"]]
        page_w = max(xe) - min(xs) + 48
        page_h = max(ye) - min(ys) + 48
        lines = [
            '<mxfile host="app.diagrams.net" agent="stream-recoverability" version="24.7.17">',
            f'  <diagram id="{self.diagram_id}" name="{html_escape(self.name)}">',
            f'    <mxGraphModel dx="{page_w:.0f}" dy="{page_h:.0f}" grid="1" gridSize="10" page="1" '
            f'pageWidth="{page_w:.0f}" pageHeight="{page_h:.0f}" math="0" shadow="0">',
            "      <root>",
            '        <mxCell id="0"/>',
            '        <mxCell id="1" parent="0"/>',
            "",
        ]
        for v in self.vertices:
            lines.append(
                f'        <mxCell id="{v["id"]}" value="{esc(v["value"])}" '
                f'style="{v["style"]}" vertex="1" parent="1">'
            )
            lines.append(
                f'          <mxGeometry x="{v["x"]:g}" y="{v["y"]:g}" width="{v["w"]:g}" '
                f'height="{v["h"]:g}" as="geometry"/>'
            )
            lines.append("        </mxCell>")
        lines.append("")
        for e in self.edges:
            style = ["edgeStyle=orthogonalEdgeStyle", f"strokeColor={e['colour']}",
                     f"fontSize={e['size']:g}"]
            if e["font"]:
                style.append(f"fontColor={e['font']}")
            if e["dashed"]:
                style.append("dashed=1")
            if not e["arrow"]:
                style.append("endArrow=none")
            lines.append(
                f'        <mxCell id="{e["id"]}" value="{esc(e["value"])}" '
                f'style="{";".join(style)}" edge="1" parent="1" '
                f'source="{e["source"]}" target="{e["target"]}">'
            )
            if e["points"]:
                pts = "".join(f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in e["points"])
                lines.append(
                    f'          <mxGeometry relative="1" as="geometry"><Array as="points">{pts}</Array></mxGeometry>'
                )
            else:
                lines.append('          <mxGeometry relative="1" as="geometry"/>')
            lines.append("        </mxCell>")
        lines += ["      </root>", "    </mxGraphModel>", "  </diagram>", "</mxfile>", ""]
        return "\n".join(lines)


# ------------------------------------------------------------------- f2 -----
def figure_f2() -> Figure:
    """Study design and data flow.  12 boxes, S-shaped flow, no crossings."""
    f = Figure("f2", "Study design and data flow")
    rows = [
        (
            ("L1", 450, 100, ["**Nine national providers**", "ARSO · CHMI · FOEN · GKD Bayern ·", "LUBW · NVE · Rijkswaterstaat · SYKE · USGS"], 15, BLUE),
            ("R1", 430, 128, ["**River-only, complete-year filter**", "lakes, seas, canals, estuaries, deltas out", "a year with any missing day: no truth", "fewer than four complete years: out", "146 networks · 457 stations ·", "5,114 completely observed station-years"], 15, BLUE),
        ),
        (
            ("L2", 450, 96, ["**Split at the network level**", "never at the station-year level;", "stratified on provider × donor regime", "110 development · 36 reserved"], 15, ORANGE),
            ("R2", 430, 96, ["**Reserved panel: retrospective holdout**", "28 of 36 networks have earlier", "programme use; not an unused", "confirmation set for new analyses"], 15, GREY),
        ),
        (
            ("L3", 450, 128, ["**Outages designed, configuration frozen**", "51,524 cases; empirical and stratified arms", "40,704 development · 10,820 reserved", "declared before the reserved panel opened", "matched retention; at least five points;", "a network-clustered interval excluding zero"], 14.5, PLAIN),
            ("R3", 430, 96, ["**Reserved panel opened once**", "9.7% → 2.5% at 70% retention", "−7.13 points [−8.97, −5.36]", "the empirical arm is unresolved"], 15, GREEN),
        ),
        (
            ("L4", 450, 112, ["**Sealed USGS confirmation**", "39 HUC4 networks · 91 stations ·", "8,973 designed cases, outside the", "development programme; scored once", "−7.9 points [−10.2, −5.8]"], 15, PLAIN),
            ("R4", 430, 130, ["**Prior-access audit and clean subset**", "24 of 39 networks appear in earlier work", "15 outcome-clean networks: −9.4 points", "[−12.4, −6.0]; a transparency diagnostic,", "not new confirmation"], 15, PLAIN),
        ),
        (
            ("L5", 450, 128, ["**Pre-registered transport panel**", "SMHI · UK EA · Hub'Eau: 32 primary", "networks across three contexts,", "four assurance strata combinations,", "sealed and scored once: −4.6 points", "[−6.5, −3.3]"], 15, PLAIN),
            ("R5", 430, 112, ["**Primary and secondary strata**", "quality-checked stratum: −6.2 points", "[−8.4, −4.5], agreeing with the pooled", "verdict; NVE secondary stratum,", "21 networks: −6.1 points [−8.7, −4.6]"], 15, PLAIN),
        ),
        (
            ("L6", 450, 96, ["**Truth-free deployment**", "2,422 real incomplete station-years,", "which carry no truth; the frozen", "screen is applied to them unchanged"], 15, GREEN),
            ("R6", 430, 112, ["**Two admission rules compared**", "length rule vs peak-window screening", "disagree on 15.1% of the 2,422 years;", "the certificate instead supports abstention", "where the interval straddles the threshold"], 15, GREEN),
        ),
    ]
    left_x, right_x, gap = 20.0, 510.0, 30.0
    y = 20.0
    for (l_spec, r_spec) in rows:
        h = max(l_spec[2], r_spec[2])
        for cid, w, _h, lines, size, palette in (l_spec, r_spec):
            x = left_x if cid.startswith("L") else right_x
            f.box(cid, x, y, w, h, lines, size=size, palette=palette)
        if y > 20.0:
            pass
        y += h + gap
    # arrows: L -> R inside a row, R -> next L through the inter-row gap
    ids = [row[0][0] for row in rows] + [row[1][0] for row in rows]
    for index, row in enumerate(rows):
        l_spec, r_spec = row
        l_box = next(v for v in f.vertices if v["id"] == l_spec[0])
        r_box = next(v for v in f.vertices if v["id"] == r_spec[0])
        mid_x = (l_box["x"] + l_box["w"] + r_box["x"]) / 2
        y_mid = (l_box["y"] + l_box["h"] / 2 + r_box["y"] + r_box["h"] / 2) / 2
        f.edge(f"a{index * 2 + 1}", l_box["id"], r_box["id"],
               points=[(mid_x, l_box["y"] + l_box["h"] / 2), (mid_x, r_box["y"] + r_box["h"] / 2)])
        if index + 1 < len(rows):
            next_l = next(v for v in f.vertices if v["id"] == rows[index + 1][0][0])
            y_gap = (r_box["y"] + r_box["h"] + next_l["y"]) / 2
            f.edge(f"a{index * 2 + 2}", r_box["id"], next_l["id"],
                   points=[(r_box["x"] + r_box["w"] / 2, y_gap),
                           (next_l["x"] + next_l["w"] / 2, y_gap)])
    return f


# ------------------------------------------------------------------- f3 -----
def figure_f3() -> Figure:
    """Evidence chain: one link per box, question and evidence class named."""
    f = Figure("f3", "Evidence chain and closure")
    boxes = [
        ("c1", ["**Real archive — sample fact**",
                "nine agencies, 146 networks, 457 stations, 5,114 fully observed station-years"],
         PLAIN),
        ("c2", ["**Designed outages — sample fact**",
                "51,524 cases on an empirical and a stratified arm; 40,704 development, 10,820 reserved"],
         PLAIN),
        ("c3", ["**Q1 · which property of a gap governs the error? — sample fact**",
                "an annual mean grows 10.2× along missing days and 1.5× along peak-window overlap;",
                "the hottest 30-day mean reverses both (3.5× and 9.6×)"],
         ORANGE),
        ("c4", ["**Q2 · two regimes or a continuum? — exploratory post-open**",
                "the crossing is an interval, 77 to 107 days; the 90-day point is indistinguishable from zero",
                "the conditioning set is the support dilated by about two location SDs (60 to 90 days)"],
         ORANGE),
        ("c5", ["**Q3 · what does conditioning change? — retrospective holdout**",
                "36 reserved networks opened once: 9.7% → 2.5% at 70% retention, −7.13 points",
                "[−8.97, −5.36]; the empirical arm is unresolved"],
         GREEN),
        ("c6", ["**Sealed confirmation, USGS — sealed confirmation**",
                "39 HUC4 networks, 8,973 cases, scored once: −7.9 points [−10.2, −5.8];",
                "the 15 outcome-clean networks give −9.4 points [−12.4, −6.0]"],
         BLUE),
        ("c7", ["**Multi-agency transport — sealed confirmation**",
                "32 pre-registered primary networks: −4.6 points [−6.5, −3.3]; quality-checked",
                "stratum −6.2 [−8.4, −4.5]; NVE secondary stratum, 21 networks, −6.1 [−8.7, −4.6]"],
         BLUE),
        ("c8", ["**Truth-free deployment — sample fact, no truth read**",
                "2,422 real incomplete station-years: the two admission rules disagree on 15.1%;",
                "wholly hidden climatological peak windows are a proxy (PPV 0.74)"],
         PLAIN),
        ("c9", ["**Consequence — sample fact**",
                "admitting incomplete years raises the archive mean by about 0.5 °C and the four",
                "rules differ by less than 0.1 °C; at the 140-day limit 17 admitted years hide the peak window"],
         GREEN),
    ]
    x, w = 20.0, 900.0
    h, gap = 76.0, 26.0
    for index, (cid, lines, palette) in enumerate(boxes):
        f.box(cid, x, 20.0 + index * (h + gap), w, h, lines, size=15, palette=palette)
    for index in range(len(boxes) - 1):
        f.edge(f"e{index + 1}", boxes[index][0], boxes[index + 1][0])
    # the loop back to the archive, down the right-hand margin
    first = f.vertices[0]
    last = f.vertices[-1]
    f.edge("loop", last["id"], first["id"],
           points=[(935.0, last["y"] + last["h"] / 2), (935.0, first["y"] + first["h"] / 2)],
           colour=EDGE_GREEN)
    f.box("cap", 20.0, 20.0 + len(boxes) * (h + gap) + 6.0, 900.0, 30.0,
          ["**Pooled designed outages close the loop; the empirical arm stays open.**"],
          size=15, palette=GREEN, shape="label")
    return f


# ------------------------------------------------------------------- f0 -----
def figure_f0() -> Figure:
    """Problem frame.  Labels unchanged except the two the manuscript revised."""
    f = Figure("f0", "Problem frame")
    ax, aw = 20.0, 300.0
    cx, cw = 330.0, 290.0
    bx, bw = 640.0, 330.0
    f.box("rec", ax, 20, 950, 76,
          ["A station-year  y = (y\u2081 \u2026 y_T),  T \u2208 {365, 366},  with an outage mask  m \u2208 {0,1}^T",
           "the analyst sees only the days where m_t = 0"],
          size=15, palette=BLUE)
    f.box("qa", ax, 126, aw, 68,
          ["**Estimand A \u2014 annual mean**", "q(y) = (1/T) \u03a3_t y_t"], size=14)
    f.box("qb", bx, 126, bw, 68,
          ["**Estimand B \u2014 hottest 30-day mean**", "q(y) = max_t (1/30) \u03a3_{i=t..t+29} y_i"], size=14)
    f.box("inc", cx, 126, cw, 110,
          ["**Incumbent completeness rule**", "s(m) = 1{ max run(m) \u2264 \u03b8 }",
           "Conditioning set: the size of", "the outage. Applied to every", "estimand alike."], size=15, palette=RED)
    f.box("sa", ax, 220, aw, 68, ["Support: all T days,", "each carrying weight 1/T"], size=14, palette=GREY)
    f.box("sb", bx, 220, bw, 68, ["Support: one 30-day window W_q,", "located by the station's own climatology"],
          size=14, palette=GREY)
    f.box("aa", ax, 310, aw, 68, ["**Governing axis**", "how many days are missing"], size=14, palette=ORANGE)
    f.box("ab", bx, 310, bw, 68, ["**Governing axis**", "how much of W_q is hidden"], size=14, palette=ORANGE)
    f.box("ma", ax, 398, aw, 86,
          ["Measured on 40,704 development cases", "error grows 10.2\u00d7 along missing days",
           "and 1.5\u00d7 along peak-window overlap"], size=14, palette=GREEN)
    f.box("mb", bx, 398, bw, 86,
          ["Measured on the same cases", "error grows 3.5\u00d7 along missing days",
           "and 9.6\u00d7 along peak-window overlap"], size=14, palette=GREEN)
    f.box("law", ax, 514, 950, 100,
          ["**One scale, not two regimes: measure missingness on the support of the estimand.**",
           "\u2018Timing versus length\u2019 is that scale at its two ends; the crossing is an interval, 77 to 107 days.",
           "The conditioning set is the support dilated by the wander of its own location:",
           "one agency window of 60 to 90 days serves every warm-season endpoint."],
          size=15, palette=BLUE)
    f.edge("e1", "rec", "qa", points=[(495.0, 110.0), (170.0, 110.0)])
    f.edge("e2", "rec", "qb", points=[(495.0, 110.0), (805.0, 110.0)])
    f.edge("e3", "qa", "sa")
    f.edge("e4", "qb", "sb")
    f.edge("e5", "sa", "aa")
    f.edge("e6", "sb", "ab")
    f.edge("e7", "aa", "ma")
    f.edge("e8", "ab", "mb")
    f.edge("e9", "inc", "aa", label="conditioning set\nmatches the support",
           points=[(475.0, 300.0), (240.0, 300.0)], colour=EDGE_GREEN, dashed=True, size=13, font="#1B5E20")
    f.edge("e10", "inc", "ab", label="conditioning set\nignores the support",
           points=[(475.0, 300.0), (700.0, 300.0)], colour=EDGE_RED, size=13, font="#B71C1C")
    f.edge("e11", "ma", "law")
    f.edge("e12", "mb", "law")
    return f


# ------------------------------------------------------------------- f1 -----
def figure_f1() -> Figure:
    """Screening system architecture."""
    f = Figure("f1", "Screening system architecture")
    f.box("vis", 20, 20, 430, 336, ["**Visible at decision time**"], size=15, palette=GREY,
          dashed=True, valign="top")
    features = [
        ("f1a", "**Outage geometry**", "longest run, total missing, number of runs"),
        ("f1b", "**Support of the estimand**", "peak-window overlap, warm-season share"),
        ("f1c", "**Constraint from the observed days**", "observed-peak margin, which flanks survived"),
        ("f1d", "**Donor information**", "count, coverage, deseasonalised correlation"),
        ("f1e", "**Station history**", "record length, residual scale, amplitude"),
    ]
    for index, (cid, title, body) in enumerate(features):
        f.box(cid, 36, 62 + index * 54, 398, 48, [title, body], size=14, palette=BLUE)
    f.box("bar", 20, 396, 430, 76,
          ["**Information barrier**", "no feature may read a day the outage hides;",
           "enforced in the feature constructor and by a test"], size=14, palette=RED)
    f.box("est", 490, 20, 470, 110,
          ["**Estimator library — support declared per case**",
           "observed days (current practice) · day-of-year climatology",
           "smoothed climatology · linear interpolation (both flanks",
           "required) · donor ridge (refit on visible donors) ·",
           "air ridge (where forcing exists)"], size=14)
    f.box("risk", 490, 170, 470, 70,
          ["**Risk model**", "predicted upper bound on | q(ŷ) − q(y) |", "for each supported estimator"], size=14, palette=ORANGE)
    f.box("sel", 490, 260, 470, 48, ["**Estimator selection — take the smallest bound**"], size=14, palette=ORANGE)
    f.box("cal", 490, 328, 470, 124,
          ["**Split-conformal calibration**",
           "selection-conditional: calibrated after the estimator",
           "is chosen, because taking the smallest of several",
           "bounds is a winner's curse that per-estimator",
           "calibration cannot see; multiplicative, because the",
           "error scale spans an order of magnitude"], size=14)
    f.box("cert", 490, 468, 470, 76,
          ["**Calibrated certificate for this station-year**",
           "an interval on the completed-year statistic, in °C,",
           "and a risk score"], size=14, palette=GREEN)
    f.box("act1", 20, 560, 430, 96,
          ["**Action space 1 — admission**",
           "retain or exclude the year at a tolerance τ in °C;",
           "decides what enters the archive. Reserved panel at",
           "70% retention: 2.5% against 9.7% for the length rule."], size=14, palette=GREEN)
    f.box("act2", 490, 560, 470, 105,
          ["**Action space 2 — abstention**",
           "keep every year and abstain only where the interval",
           "straddles the threshold; decides what one judgement may",
           "say. Judges 92.7% of years at 0.42% misclassification,",
           "against 67.5% at 0.36% for screening at 0.5 °C."], size=14, palette=GREEN)
    f.box("notes", 20, 690, 940, 90,
          ["**Notes on fitting and evaluation**",
           "Fitted leave-one-year-out within the station; a prior-years-only refit is reported as a sensitivity.",
           "Absent donor columns are never imputed; the model is refit on the visible subset. Fitting, calibration",
           "and test networks are always disjoint, and every interval resamples whole networks."], size=14, palette=NOTE)
    f.edge("d1", "bar", "vis", label="enforced on every feature", colour=EDGE_RED, dashed=True, size=14, font="#B71C1C")
    f.edge("d2", "vis", "est", points=[(470.0, 178.0), (470.0, 90.0)])
    f.edge("d3", "vis", "risk", points=[(470.0, 250.0), (470.0, 208.0)])
    f.edge("d4", "est", "risk", label="completed-year statistic", size=14)
    f.edge("d5", "risk", "sel")
    f.edge("d6", "sel", "cal", label="selection-conditional", size=14)
    f.edge("d7", "cal", "cert")
    f.edge("d8", "cert", "act1", points=[(725.0, 550.0), (235.0, 550.0)], colour=EDGE_GREEN)
    f.edge("d9", "cert", "act2", colour=EDGE_GREEN)
    return f


# ------------------------------------------------------------------- f4 -----
def figure_f4() -> Figure:
    """Agency deployment workflow."""
    f = Figure("f4", "Agency deployment workflow")
    f.box("n0", 20, 20, 540, 52, ["**A station-year with an outage reaches the archive**"], size=15, palette=BLUE)
    f.box("q1", 20, 92, 540, 52, ["**Which statistic will be computed?**"], size=15, palette=ORANGE)
    f.box("n2", 20, 164, 540, 60, ["**A warm-season extreme**", "hottest 7-day or 30-day mean"], size=15)
    f.box("n3", 20, 244, 540, 76,
          ["**Locate the climatological peak window**", "from the station's own complete years;",
           "no data beyond its own record is needed"], size=14.5)
    f.box("n4", 20, 344, 540, 76,
          ["**Three numbers from the outage mask alone**", "peak_overlap · warm_observed_fraction ·",
           "longest_run_days"], size=14.5)
    f.box("n5", 20, 444, 540, 76,
          ["**risk = logistic(−1.302 + 2.070 · peak_overlap**", "**− 2.412 · warm_observed_fraction**",
           "**− 0.00187 · longest_run_days)**"], size=14)
    f.box("n6", 20, 544, 540, 60, ["**Rank by risk and admit to the retention**", "the monitoring programme can afford"],
          size=15)
    f.box("n7", 20, 628, 540, 96,
          ["**Guardrail: check what the rule keeps**", "retention by elevation, slope, donor availability;",
           "if the archived set is not representative, apply", "the threshold within stratum (about 0.3 points)"],
          size=14.5, palette=RED)
    f.box("n8", 20, 748, 540, 96,
          ["**What the substitution buys, at 70% retention**", "on the retrospective 36-network holdout:",
           "9.7% → 2.5% for the calibrated screen;", "the three-variable rule gives 4.2%"], size=14.5, palette=GREEN)
    f.box("ba", 600, 92, 360, 72,
          ["**An average or sine-fit parameter**", "annual mean, coldest 30-day mean,",
           "sine-fit mean, phase, amplitude"], size=14)
    f.box("ba2", 600, 190, 360, 92,
          ["**Keep the length-based rule**", "threshold the number of missing days;",
           "length is the better axis here", "(annual mean AUC 0.845 against 0.672)"], size=14, palette=GREEN)
    f.box("s1", 600, 320, 360, 140,
          ["**For an uncertainty statement in °C**", "run the calibrated screen and report",
           "its interval. A pooled interval speaks", "for a population of networks, not for",
           "one site; cluster calibration stays", "exploratory until it is validated",
           "outside the development programme."], size=14, palette=NOTE)
    f.box("s2", 600, 494, 360, 124,
          ["**For a single threshold judgement**", "do not discard the year: abstaining",
           "where the interval straddles the", "threshold judges 92.7% of years at",
           "0.42%, against 67.5% at 0.36% for", "screening at the same tolerance."], size=14, palette=NOTE)
    f.edge("y1", "n0", "q1")
    f.edge("y2", "q1", "n2")
    f.edge("y3", "q1", "ba", points=[(580.0, 118.0), (580.0, 128.0)])
    for index, (src, dst) in enumerate(
        [("n2", "n3"), ("n3", "n4"), ("n4", "n5"), ("n5", "n6"), ("n6", "n7"), ("n7", "n8")]
    ):
        f.edge(f"y{4 + index}", src, dst, colour=EDGE_RED if src == "n6" else EDGE,
               size=14)
    f.edge("y10", "ba", "ba2")
    f.edge("y11", "s1", "n5", points=[(580.0, 400.0), (580.0, 464.0)], colour="#B0BEC5", dashed=True, arrow=False)
    f.edge("y12", "s2", "n6", points=[(580.0, 556.0), (580.0, 574.0)], colour="#B0BEC5", dashed=True, arrow=False)
    return f


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "f0_problem_frame": figure_f0,
        "f1_system_architecture": figure_f1,
        "f2_experiment_design": figure_f2,
        "f3_evidence_chain": figure_f3,
        "f4_deployment_workflow": figure_f4,
    }
    for name, build in builders.items():
        print(name)
        figure = build()
        path = OUT / f"{name}.drawio"
        path.write_text(figure.xml(), encoding="utf-8")
        xs = [v["x"] for v in figure.vertices] + [p[0] for e in figure.edges for p in e["points"]]
        xe = [v["x"] + v["w"] for v in figure.vertices] + [p[0] for e in figure.edges for p in e["points"]]
        ys = [v["y"] for v in figure.vertices] + [p[1] for e in figure.edges for p in e["points"]]
        ye = [v["y"] + v["h"] for v in figure.vertices] + [p[1] for e in figure.edges for p in e["points"]]
        width = max(xe) - min(xs) + 48
        height = max(ye) - min(ys) + 48
        smallest = min(float(re.search(r"fontSize=([\d.]+)", v["style"]).group(1)) for v in figure.vertices)
        print(f"  {path.relative_to(ROOT)}: page {width:.0f}x{height:.0f} px "
              f"({width / 96:.2f}x{height / 96:.2f} in); smallest font {smallest} px "
              f"-> {smallest * 396 / width:.2f} pt at 5.5 in")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
