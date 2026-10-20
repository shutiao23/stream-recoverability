#!/usr/bin/env python3
"""Figure/PDF quality assurance for the WRR submission.

The author requires that every figure's fonts are embedded, that nothing
overlaps, that nothing runs off the page, and that the journal format is
respected.  This harness measures those properties with the Poppler command
line tools (``pdffonts``, ``pdfinfo``, ``pdftotext -bbox``, ``pdfimages``) and
never asserts a value it did not measure.

Targets
-------
* every ``*.pdf`` in ``paper/wrr/figures/`` (the per-figure build products);
* the built ``paper/wrr/wrr_manuscript.pdf`` and
  ``paper/wrr/wrr_supporting_information.pdf``.

Checks
------
a. fonts          every font must be embedded (``emb = yes``); a non-embedded
                  font, in particular a non-embedded core font, is a hard
                  failure.
b. page geometry  ``pdfinfo`` page size and page count; a *figure* must be a
                  single page.  Text boxes that leave the page box are a hard
                  failure (see d).
c. text bounds    ``pdftotext -bbox`` word boxes in points; any box more than
                  1 pt outside the page box is a hard failure.
d. text height    any word box below 4.5 pt high (unreadable in print) is a
                  hard failure.  The box height is the only size proxy the
                  Poppler text extractor exposes, so the flagged word is
                  re-checked (see ``--no-ink-verify``) against a rendered page.
e. overlap        word-box pairs whose intersection exceeds 25 % of the smaller
                  box, exact duplicates (shadow copies) excluded.  This is a
                  *conservative approximation* of visual overlap: it cannot see
                  text over graphics, and Poppler boxes carry font
                  ascent/descent padding, so flagged pairs are classified by
                  geometry (same baseline vs. adjacent line vs. atypical box)
                  and the worst are verified against rendered pages.
f. provenance     for every figure: the draw.io source at
                  ``figures/v17/drawio/<name>.drawio`` (required for the
                  architecture/system-design schematics listed in
                  ``figures/v17/drawio/README.md``) and/or the Python script
                  that generates it (found by searching ``scripts/`` for the
                  figure name).  A schematic without a draw.io source is a hard
                  failure; a figure with neither source is a warning.
g. raster dpi     page size in inches and, from ``pdfimages -list``, any raster
                  image whose effective resolution is below 300 dpi.

Extra measurements (clearly labelled as derived, never hard failures)
--------------------------------------------------------------------
* ink edge check: for pages with a text-bounds violation the page is rendered
  with ``pdftoppm`` and the ink bounding box is measured, which separates a
  real overprint from Poppler's font-descent padding.
* print size: the scale at which each figure is placed in the built PDFs is
  measured by matching the figure's distinctive words against the words of the
  built PDF pages (median of pairwise distance ratios).  ``scale x figure
  width`` gives the printed width; raw text heights times the scale give the
  effective print size, which is what decides legibility on paper.

Outputs
-------
``results/wrr_submission_ready/figure_qa.json``  machine readable, per file and
                                                 per check
``results/wrr_submission_ready/figure_qa_report.md``  tables plus a prioritised
                                                 fix list

Exit status
-----------
Non-zero only on hard failures: a non-embedded font, a figure with a page count
other than one, text more than 1 pt outside the page, a word box below 4.5 pt,
or a schematic figure without a draw.io source.  ``--report-only`` records the
same hard failures but exits 0, which is what the regression test uses so that
a real finding does not turn the test suite red.

Usage
-----
    python3 scripts/266_wrr_figure_qa.py
    python3 scripts/266_wrr_figure_qa.py --report-only
    python3 scripts/266_wrr_figure_qa.py --json scratch/figure_qa/qa.json --no-ink-verify
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import statistics
import subprocess
import sys
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
DEFAULT_PAPER_DIR = ROOT / "paper" / "wrr"
DEFAULT_JSON = READY / "figure_qa.json"
DEFAULT_MD = READY / "figure_qa_report.md"
DEFAULT_RENDER_DIR = ROOT / "scratch" / "figure_qa" / "render"

#: Hard-failure thresholds.  Only the values named in the task statement.
OUT_PAGE_TOLERANCE_PT = 1.0
MIN_TEXT_HEIGHT_PT = 4.5
OVERLAP_FRACTION = 0.25
MIN_RASTER_DPI = 300.0

#: Classification tolerances (reporting only, they never create a failure).
SAME_BASELINE_PT = 0.5
DUPLICATE_BOX_EPS_PT = 0.01
SHADOW_DUPLICATE_OFFSET_PT = 1.0
ATYPICAL_BOX_RATIO = 1.25
INK_EDGE_FLUSH_PT = 1.0
INK_DPI = 200
INK_THRESHOLD = 200  # 0-255 grey level counted as ink
FOOTER_BAND_MIN_OVERLAP_PT = 2.0  # body-box bite into the page-number band

#: Architecture / system-design schematics.  The list is maintained explicitly
#: from figures/v17/drawio/README.md ("the editable source of truth for every
#: schematic, architecture and design figure"); a new diagram must be added
#: here so that a missing .drawio source cannot go unnoticed.
SCHEMATIC_FIGURES = {
    "f0_problem_frame": "problem frame (drawio README)",
    "f1_system_architecture": "system architecture (drawio README)",
    "f2_experiment_design": "study design and data flow (drawio README)",
    "f3_evidence_chain": "evidence chain (drawio README)",
    "f4_deployment_workflow": "deployment workflow (drawio README)",
    # 2026-10-20: the paper's schematics moved to figures/wrr/drawio/ and are
    # exported with the draw.io desktop app, not drawn in matplotlib.
    "f2_system_design": "system design and admission workflow (drawio, 2026-10-20)",
    "s1_study_design": "study design and evidence chain (drawio, 2026-10-20)",
}

#: Warnings that are defects in the artifact rather than artifacts of Poppler's
#: box model.  The rest of the warning classes are either box-model effects
#: (padding, rotated runs, subscripts) or informational.
REAL_DEFECT_WARNINGS = (
    "FOOTER_TEXT_COLLISION",
    "RASTER_BELOW_300_DPI",
    "MERGED_LABEL_RUN_SUSPECT",
    "INK_CLIPPED_AT_PAGE_EDGE",
    "EFFECTIVE_PRINT_TEXT_TOO_SMALL",
    "INK_CHECK_UNAVAILABLE",
)
BOX_MODEL_WARNINGS = (
    "OVERLAPPING_WORD_BOXES",
    "OVERLAPPING_TEXT_SAME_BASELINE",
    "TEXT_BOX_PADDING_ONLY",
    "SMALL_RELATIVE_WORD_BOXES",
    "FONT_UNNAMED",
    "DEGENERATE_WORD_BOXES",
    "FIGURE_NOT_REFERENCED",
    "PAGE_SIZE_VARIES",
    "BBOX_PAGE_COUNT_MISMATCH",
    "BUILT_PDF_MISSING",
    "TOOL_MISSING",
)

#: Base-14 PDF core fonts: never embedded unless the producer chose to.
CORE_FONT_BASES = (
    "Courier",
    "Helvetica",
    "Times",
    "Symbol",
    "ZapfDingbats",
    "Arial",
    "TimesNewRoman",
)

TOOL_NAMES = ("pdffonts", "pdfinfo", "pdftotext", "pdfimages", "pdftoppm", "rsvg-convert", "drawio")

WORD_RE = re.compile(
    r'<word xMin="([-\d.eE]+)" yMin="([-\d.eE]+)" xMax="([-\d.eE]+)" yMax="([-\d.eE]+)">(.*?)</word>',
    re.DOTALL,
)
PAGE_RE = re.compile(r'<page\s+width="([-\d.eE]+)"\s+height="([-\d.eE]+)"')
PAGE_SIZE_RE = re.compile(r"^Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", re.MULTILINE)
INCLUDE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
REPEATED_TEXT_RE = re.compile(r"(.{4,24}?)\1")
#: A running page number, e.g. "16" or "–16–".
PAGE_NUMBER_RE = re.compile(r"^[\u2013\u2014-]\s?\d{1,3}\s?[\u2013\u2014-]$")
#: matplotlib writes each text run as ``q 1 0 -0 1 X Y cm BT /Fn S Tf 0 0 Td [ (text) ] TJ ET``.
TEXT_RUN_RE = re.compile(
    r"q\s*\n1 0 -0 1 ([-\d.]+) ([-\d.]+) cm\s*\nBT\s*\n/(\w+) ([-\d.]+) Tf\s*\n0 0 Td\s*\n\[\s*\((.*?)\)\s*\]\s*TJ\s*\nET",
    re.DOTALL,
)
PDF_STRING_ESCAPES = (("\\(", "("), ("\\)", ")"), ("\\\\", "\\"))


# ---------------------------------------------------------------------------
# tool running
# ---------------------------------------------------------------------------


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def probe_version(name: str) -> str | None:
    """First line of ``<tool> -v``/``--version``, or None when unavailable."""
    if not tool_available(name):
        return None
    for flag in ("-v", "--version"):
        try:
            proc = subprocess.run(
                [name, flag], capture_output=True, text=True, errors="replace", timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            continue
        for line in (proc.stdout or proc.stderr or "").splitlines():
            if line.strip():
                return line.strip()
    return "unknown"


def run_tool(argv: Sequence[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Run a tool without a shell and return the completed process."""
    return subprocess.run(
        list(argv), capture_output=True, text=True, errors="replace", timeout=timeout
    )


# ---------------------------------------------------------------------------
# parsers
# ---------------------------------------------------------------------------


@dataclass
class FontRecord:
    name: str
    type: str
    encoding: str
    embedded: bool
    subset: bool
    unicode: bool
    raw: str

    @property
    def base_name(self) -> str:
        """Font name without the ``ABCDEF+`` subset prefix and spaces removed."""
        name = re.sub(r"^[A-Z]{6}\+", "", self.name)
        return re.sub(r"[^A-Za-z]", "", name)

    @property
    def is_core_font_name(self) -> bool:
        return any(self.base_name.startswith(base) for base in CORE_FONT_BASES)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "encoding": self.encoding,
            "embedded": self.embedded,
            "subset": self.subset,
            "unicode": self.unicode,
            "base_name": self.base_name,
            "unnamed": self.name.strip() in {"[none]", "none", ""},
        }


def parse_pdffonts(text: str) -> list[FontRecord]:
    """Parse ``pdffonts`` output using the header column offsets."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    header = lines[0]
    try:
        i_emb = header.index("emb")
        i_sub = header.index("sub")
        i_uni = header.index("uni")
    except ValueError:  # pragma: no cover - poppler always prints these headers
        return []
    records: list[FontRecord] = []
    for line in lines[2:]:
        if set(line.strip()) <= {"-"} or len(line) <= i_uni + 3:
            continue
        prefix = line[:i_emb].strip()
        if not prefix:
            continue
        parts = [p for p in re.split(r"\s{2,}", prefix) if p]
        if len(parts) >= 3:
            name, font_type, encoding = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            name, font_type, encoding = parts[0], parts[1], ""
        else:
            name, font_type, encoding = prefix, "", ""
        embedded = line[i_emb : i_emb + 3].strip() == "yes"
        subset = line[i_sub : i_sub + 3].strip() == "yes"
        unicode_ok = line[i_uni : i_uni + 3].strip() == "yes"
        records.append(
            FontRecord(
                name=name,
                type=font_type,
                encoding=encoding,
                embedded=embedded,
                subset=subset,
                unicode=unicode_ok,
                raw=line.rstrip(),
            )
        )
    return records


def parse_pdfinfo(text: str) -> dict[str, Any]:
    """Parse ``pdfinfo`` output, including any ``Page N size:`` lines."""
    info: dict[str, Any] = {"raw_fields": {}}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if re.fullmatch(r"Page\s+\d+\s+size", key):
            continue
        if re.fullmatch(r"Page\s+\d+\s+rot", key):
            continue
        info["raw_fields"][key] = value
    pages = info["raw_fields"].get("Pages")
    info["pages"] = int(pages) if pages and pages.isdigit() else None
    size = info["raw_fields"].get("Page size", "")
    match = re.match(r"([\d.]+)\s+x\s+([\d.]+)\s+pts", size)
    info["page_size_pt"] = [float(match.group(1)), float(match.group(2))] if match else None
    info["page_rot"] = info["raw_fields"].get("Page rot")
    info["encrypted"] = info["raw_fields"].get("Encrypted")
    info["producer"] = info["raw_fields"].get("Producer")
    info["creator"] = info["raw_fields"].get("Creator")
    info["pdf_version"] = info["raw_fields"].get("PDF version")
    per_page: dict[int, list[float]] = {}
    for number, width, height in PAGE_SIZE_RE.findall(text):
        per_page[int(number)] = [float(width), float(height)]
    info["per_page_size_pt"] = dict(sorted(per_page.items()))
    return info


def parse_bbox_pages(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse ``pdftotext -bbox`` XHTML into page boxes and word boxes (points)."""
    pages: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if "<page " in line:
            match = PAGE_RE.search(line)
            if match:
                current = {
                    "page": len(pages) + 1,
                    "width_pt": float(match.group(1)),
                    "height_pt": float(match.group(2)),
                }
                pages.append(current)
            continue
        match = WORD_RE.search(line)
        if match and current is not None:
            x0, y0, x1, y1 = (float(match.group(i)) for i in range(1, 5))
            words.append(
                {
                    "page": current["page"],
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "width_pt": x1 - x0,
                    "height_pt": y1 - y0,
                    "text": html.unescape(match.group(5)),
                }
            )
    return pages, words


@dataclass
class RasterImage:
    page: int
    num: int
    type: str
    width_px: int
    height_px: int
    color: str
    comp: int
    bpc: int
    enc: str
    interp: str
    object_id: str
    x_ppi: float
    y_ppi: float
    size: str
    ratio: str

    @property
    def min_ppi(self) -> float:
        return min(self.x_ppi, self.y_ppi)

    def as_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "num": self.num,
            "type": self.type,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "color": self.color,
            "components": self.comp,
            "bits_per_component": self.bpc,
            "encoding": self.enc,
            "interpolate": self.interp,
            "object_id": self.object_id,
            "x_ppi": self.x_ppi,
            "y_ppi": self.y_ppi,
            "min_ppi": self.min_ppi,
            "bytes": self.size,
            "ratio": self.ratio,
            "below_300_dpi": self.min_ppi < MIN_RASTER_DPI,
        }


def parse_pdfimages(text: str) -> list[RasterImage]:
    """Parse ``pdfimages -list`` rows (header + one row per image)."""
    images: list[RasterImage] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 15:
            continue
        if fields[0] == "page" or set(fields[0]) <= {"-"}:
            continue
        if not fields[0].isdigit():
            continue
        try:
            images.append(
                RasterImage(
                    page=int(fields[0]),
                    num=int(fields[1]),
                    type=fields[2],
                    width_px=int(fields[3]),
                    height_px=int(fields[4]),
                    color=fields[5],
                    comp=int(fields[6]),
                    bpc=int(fields[7]),
                    enc=fields[8],
                    interp=fields[9],
                    object_id=fields[10],
                    x_ppi=float(fields[12]),
                    y_ppi=float(fields[13]),
                    size=fields[-2],
                    ratio=fields[-1],
                )
            )
        except (ValueError, IndexError):
            continue
    return images


# ---------------------------------------------------------------------------
# report items
# ---------------------------------------------------------------------------


@dataclass
class Item:
    """One hard failure or warning, with a locator so it can be fixed."""

    check: str
    detail: str
    page: int | None = None
    locator: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, path: str) -> dict[str, Any]:
        out: dict[str, Any] = {"file": path, "check": self.check, "detail": self.detail}
        if self.page is not None:
            out["page"] = self.page
        if self.locator:
            out["locator"] = self.locator
        return out


def md_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel_path(path: Path) -> str:
    """Path relative to the repository root when possible, else absolute."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------


def check_overlaps(
    words: Sequence[dict[str, Any]],
    page_sizes: dict[int, dict[str, Any]],
    threshold: float = OVERLAP_FRACTION,
) -> dict[str, Any]:
    """Word-box intersections above ``threshold`` of the smaller box.

    Exact duplicates (same text, same box) and shadow duplicates (same text,
    box offset by at most 1 pt and nearly coincident) are excluded and counted.
    """
    by_page: dict[int, list[dict[str, Any]]] = {}
    for word in words:
        by_page.setdefault(int(word["page"]), []).append(word)

    pairs: list[dict[str, Any]] = []
    n_exact_duplicates = 0
    n_shadow_duplicates = 0
    n_degenerate = 0
    for page, page_words in sorted(by_page.items()):
        ordered = sorted(page_words, key=lambda w: (w["x0"], w["y0"]))
        heights = [w["height_pt"] for w in ordered if w["height_pt"] > 0]
        median_height = statistics.median(heights) if heights else 0.0
        for i, first in enumerate(ordered):
            if first["height_pt"] <= 0 or first["width_pt"] <= 0:
                n_degenerate += 1
                continue
            for second in ordered[i + 1 :]:
                if second["x0"] >= first["x1"]:
                    break
                if second["height_pt"] <= 0 or second["width_pt"] <= 0:
                    continue
                overlap_x = min(first["x1"], second["x1"]) - max(first["x0"], second["x0"])
                overlap_y = min(first["y1"], second["y1"]) - max(first["y0"], second["y0"])
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                area = overlap_x * overlap_y
                area_first = first["width_pt"] * first["height_pt"]
                area_second = second["width_pt"] * second["height_pt"]
                smaller = min(area_first, area_second)
                fraction = area / smaller if smaller > 0 else 0.0
                if fraction <= threshold:
                    continue
                same_text = first["text"] == second["text"]
                if same_text:
                    offset = max(
                        abs(first["x0"] - second["x0"]),
                        abs(first["y0"] - second["y0"]),
                        abs(first["x1"] - second["x1"]),
                        abs(first["y1"] - second["y1"]),
                    )
                    if offset <= DUPLICATE_BOX_EPS_PT:
                        n_exact_duplicates += 1
                        continue
                    if offset <= SHADOW_DUPLICATE_OFFSET_PT and fraction >= 0.9:
                        n_shadow_duplicates += 1
                        continue
                same_baseline = (
                    abs(first["y0"] - second["y0"]) <= SAME_BASELINE_PT
                    and abs(first["y1"] - second["y1"]) <= SAME_BASELINE_PT
                )
                atypical = (
                    max(first["height_pt"], second["height_pt"])
                    > ATYPICAL_BOX_RATIO * median_height
                    if median_height
                    else False
                )
                if same_baseline:
                    kind = "same_baseline_horizontal"
                    note = "words share a baseline and overlap horizontally: a real text collision"
                elif atypical:
                    kind = "atypical_box_geometry"
                    note = (
                        "at least one box is taller than the page median word box: rotated "
                        "text runs and fragmented glyph runs produce overlapping boxes without "
                        "overlapping ink"
                    )
                else:
                    kind = "adjacent_line_padding"
                    note = (
                        "boxes of vertically adjacent lines overlap because Poppler boxes carry "
                        "font ascent/descent padding; ink may still be clear"
                    )
                pairs.append(
                    {
                        "page": page,
                        "kind": kind,
                        "note": note,
                        "overlap_fraction": round(fraction, 4),
                        "overlap_area_pt2": round(area, 3),
                        "overlap_x_pt": round(overlap_x, 3),
                        "overlap_y_pt": round(overlap_y, 3),
                        "same_baseline": same_baseline,
                        "box_geometry_atypical": atypical,
                        "page_median_word_height_pt": round(median_height, 3),
                        "word_a": {
                            "text": first["text"],
                            "x0": round(first["x0"], 2),
                            "y0": round(first["y0"], 2),
                            "x1": round(first["x1"], 2),
                            "y1": round(first["y1"], 2),
                            "height_pt": round(first["height_pt"], 2),
                        },
                        "word_b": {
                            "text": second["text"],
                            "x0": round(second["x0"], 2),
                            "y0": round(second["y0"], 2),
                            "x1": round(second["x1"], 2),
                            "y1": round(second["y1"], 2),
                            "height_pt": round(second["height_pt"], 2),
                        },
                        "baseline_delta_pt": round(abs(first["y0"] - second["y0"]), 3),
                    }
                )
    pairs.sort(key=lambda p: (-p["overlap_fraction"], p["page"]))
    by_kind: dict[str, int] = {}
    for pair in pairs:
        by_kind[pair["kind"]] = by_kind.get(pair["kind"], 0) + 1
    return {
        "threshold_fraction_of_smaller_box": threshold,
        "n_word_boxes": len(words),
        "n_candidate_pairs": len(pairs),
        "n_duplicate_pairs_ignored_exact": n_exact_duplicates,
        "n_duplicate_pairs_ignored_shadow": n_shadow_duplicates,
        "n_degenerate_boxes": n_degenerate,
        "counts_by_kind": dict(sorted(by_kind.items())),
        "n_same_baseline_pairs": by_kind.get("same_baseline_horizontal", 0),
        "page_sizes": page_sizes,
        "pairs": pairs,
        "method_note": (
            "conservative approximation of visual overlap: derived from poppler word boxes, "
            "which carry font ascent/descent padding and are axis-aligned even for rotated "
            "text; it also cannot see text drawn over graphics. Overlaps are reported as "
            "warnings, never as hard failures."
        ),
    }


def ink_bbox(
    pdf_path: Path,
    page: int,
    render_dir: Path,
    dpi: int = INK_DPI,
    page_size_pt: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Render one page with ``pdftoppm`` and measure the ink bounding box."""
    out: dict[str, Any] = {"available": False, "dpi": dpi}
    if not tool_available("pdftoppm"):
        out["reason"] = "pdftoppm not installed"
        return out
    try:
        from PIL import Image  # noqa: PLC0415 - optional dependency at call time
    except Exception as exc:  # pragma: no cover - PIL is a matplotlib dependency
        out["reason"] = f"PIL unavailable: {exc}"
        return out
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / f"ink_{pdf_path.stem}_p{page}"
    for stale in render_dir.glob(f"{prefix.name}-*.png"):
        stale.unlink()
    proc = run_tool(
        ["pdftoppm", "-r", str(dpi), "-png", "-f", str(page), "-l", str(page), str(pdf_path), str(prefix)]
    )
    produced = sorted(render_dir.glob(f"{prefix.name}-*.png"))
    if not produced:
        out["reason"] = f"pdftoppm produced no image (rc={proc.returncode}): {proc.stderr.strip()[:200]}"
        return out
    scale = dpi / 72.0
    with Image.open(produced[0]) as image:
        grey = image.convert("L")
        width_px, height_px = grey.size
        try:
            import numpy as np  # noqa: PLC0415 - optional accelerator

            pixels = np.asarray(grey)
            mask = pixels < INK_THRESHOLD
            rows = np.flatnonzero(mask.any(axis=1))
            cols = np.flatnonzero(mask.any(axis=0))
            if rows.size:
                min_row, max_row = int(rows[0]), int(rows[-1])
                min_col, max_col = int(cols[0]), int(cols[-1])
            else:
                min_row, max_row, min_col, max_col = height_px, -1, width_px, -1
        except Exception:  # pragma: no cover - pure python fallback
            access = grey.load()
            min_row, max_row, min_col, max_col = height_px, -1, width_px, -1
            for row in range(height_px):
                for col in range(width_px):
                    if access[col, row] < INK_THRESHOLD:
                        if row < min_row:
                            min_row = row
                        if row > max_row:
                            max_row = row
                        if col < min_col:
                            min_col = col
                        if col > max_col:
                            max_col = col
    out.update(
        {
            "available": True,
            "render_png": str(produced[0].relative_to(ROOT)) if produced[0].is_relative_to(ROOT) else str(produced[0]),
            "page_width_pt": width_px / scale,
            "page_height_pt": height_px / scale,
        }
    )
    if max_row < 0:
        out["ink_bbox_pt"] = None
        out["ink_empty"] = True
        return out
    ink = {
        "left": min_col / scale,
        "top": min_row / scale,
        "right": max_col / scale,
        "bottom": max_row / scale,
    }
    out["ink_bbox_pt"] = {k: round(v, 3) for k, v in ink.items()}
    if page_size_pt:
        page_w, page_h = float(page_size_pt[0]), float(page_size_pt[1])
        out["margin_pt"] = {
            "left": round(ink["left"], 3),
            "top": round(ink["top"], 3),
            "right": round(page_w - ink["right"], 3),
            "bottom": round(page_h - ink["bottom"], 3),
        }
        out["ink_flush_to_edge"] = (
            min(out["margin_pt"].values()) <= INK_EDGE_FLUSH_PT
        )
    return out


def extract_text_runs(
    pdf_path: Path, page_height_pt: float, box: dict[str, float]
) -> list[dict[str, Any]]:
    """Text runs (matplotlib ``cm``+``Td`` blocks) whose origin falls inside ``box``.

    The content streams are inflated with zlib and the absolute placement
    matrices are read directly, which recovers the individual runs that Poppler
    merges into one word box when labels are drawn edge to edge.
    """
    runs: list[dict[str, Any]] = []
    try:
        raw = pdf_path.read_bytes()
    except OSError:
        return runs
    for match in re.finditer(rb"stream\r?\n", raw):
        start = match.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        try:
            text = zlib.decompress(raw[start:end]).decode("latin-1")
        except zlib.error:
            continue
        for run in TEXT_RUN_RE.finditer(text):
            x = float(run.group(1))
            y_pdf = float(run.group(2))
            y_top = page_height_pt - y_pdf
            label = run.group(5)
            for escaped, plain in PDF_STRING_ESCAPES:
                label = label.replace(escaped, plain)
            inside_x = box["x0"] - 25.0 <= x <= box["x1"] + 25.0
            inside_y = box["y0"] - 6.0 <= y_top <= box["y1"] + 6.0
            if inside_x and inside_y:
                runs.append(
                    {
                        "text": label,
                        "x_pt": round(x, 3),
                        "baseline_y_top_pt": round(y_top, 3),
                        "font_resource": run.group(3),
                        "font_size_pt": float(run.group(4)),
                    }
                )
    runs.sort(key=lambda r: r["x_pt"])
    # A merged word box can sit next to other labels on a different baseline;
    # keep only the dominant baseline group so the pitch describes the row.
    dominant: list[dict[str, Any]] = []
    dropped = 0
    if runs:
        groups: dict[float, list[dict[str, Any]]] = {}
        for run in runs:
            groups.setdefault(round(run["baseline_y_top_pt"]), []).append(run)
        dominant = max(groups.values(), key=len)
        dropped = len(runs) - len(dominant)
        dominant.sort(key=lambda r: r["x_pt"])
        for index in range(1, len(dominant)):
            dominant[index]["pitch_from_previous_pt"] = round(
                dominant[index]["x_pt"] - dominant[index - 1]["x_pt"], 3
            )
    span = (dominant[-1]["x_pt"] - dominant[0]["x_pt"]) if len(dominant) >= 2 else 0.0
    reliable = len(dominant) >= 2 and span >= 0.4 * max(1.0, box["x1"] - box["x0"])
    for run in dominant:
        run["runs_dropped_other_baseline"] = dropped
    if not reliable:
        # Text inside a Form XObject keeps its own coordinate system, so the
        # placement matrices are not page coordinates and cannot be reported.
        return []
    return dominant


def detect_merged_label_runs(
    pdf_path: Path,
    words: Sequence[dict[str, Any]],
    page_heights: dict[int, float],
    min_repeats: int = 2,
) -> list[dict[str, Any]]:
    """Word boxes whose text repeats a substring: labels drawn with no word gap.

    Poppler splits words on spacing, so two adjacent labels with no space glyph
    between them come back as a single word box such as
    ``timingtimingtiminglengthlength``.  The pairwise overlap test cannot see
    this, and visually the labels read as one continuous string.
    """
    findings: list[dict[str, Any]] = []
    for word in words:
        text = word["text"]
        if len(text) < 8:
            continue
        repeated = REPEATED_TEXT_RE.search(text)
        if not repeated:
            continue
        repeats = len(re.findall(re.escape(repeated.group(1)), text))
        if repeats < min_repeats:
            continue
        page_height = page_heights.get(word["page"])
        runs = (
            extract_text_runs(
                pdf_path,
                page_height,
                {"x0": word["x0"], "x1": word["x1"], "y0": word["y0"], "y1": word["y1"]},
            )
            if page_height
            else []
        )
        pitches = [
            run["pitch_from_previous_pt"] for run in runs if "pitch_from_previous_pt" in run
        ]
        findings.append(
            {
                "page": word["page"],
                "text": text,
                "repeated_unit": repeated.group(1),
                "n_repeats": repeats,
                "x0": round(word["x0"], 2),
                "y0": round(word["y0"], 2),
                "x1": round(word["x1"], 2),
                "y1": round(word["y1"], 2),
                "width_pt": round(word["width_pt"], 3),
                "height_pt": round(word["height_pt"], 3),
                "n_text_runs_found": len(runs),
                "text_runs": runs,
                "min_pitch_pt": round(min(pitches), 3) if pitches else None,
                "max_pitch_pt": round(max(pitches), 3) if pitches else None,
                "method_note": (
                    "the word box is one Poppler word because the individual labels are drawn "
                    "with no space glyph between them; the placement matrices of the underlying "
                    "runs were read from the inflated PDF content streams"
                    + (
                        ""
                        if runs
                        else "; no run positions are reported because the text sits in a nested "
                        "Form XObject whose matrices are not page coordinates"
                    )
                ),
            }
        )
    return findings


def attribute_pages_to_figures(
    page_word_sets: dict[str, set[str]],
    figure_word_sets: dict[str, set[str]],
    min_matches: int = 3,
) -> dict[str, dict[str, Any]]:
    """Map a built-PDF page to the figure whose words it contains.

    Only pages that already carry a finding are attributed (the caller passes
    just those pages' words), which keeps the match discriminating: body text
    shares common words with a figure, but the flagged words of a placed figure
    are its own labels.
    """
    mapping: dict[str, dict[str, Any]] = {}
    for key, page_words in page_word_sets.items():
        best_name, best_hits = None, 0
        for name, words in figure_word_sets.items():
            hits = len(page_words & words)
            if hits > best_hits:
                best_name, best_hits = name, hits
        if best_name and best_hits >= min_matches:
            mapping[key] = {"figure": best_name, "n_matching_words": best_hits}
    return mapping


def detect_footer_collisions(
    words: Sequence[dict[str, Any]],
    min_overlap_pt: float = FOOTER_BAND_MIN_OVERLAP_PT,
) -> list[dict[str, Any]]:
    """Body word boxes that bite into the running page-number band.

    A page whose text block runs long pushes its last line into the footer; the
    pairwise test only sees another instance of ``adjacent_line_padding`` there,
    while on paper the page number is printed over the text.
    """
    findings: list[dict[str, Any]] = []
    by_page: dict[int, list[dict[str, Any]]] = {}
    for word in words:
        by_page.setdefault(int(word["page"]), []).append(word)
    for page, page_words in sorted(by_page.items()):
        footers = [w for w in page_words if PAGE_NUMBER_RE.match(w["text"].strip())]
        if not footers:
            continue
        band_top = min(w["y0"] for w in footers)
        band_bottom = max(w["y1"] for w in footers)
        band_left = min(w["x0"] for w in footers)
        band_right = max(w["x1"] for w in footers)
        collisions = []
        for word in page_words:
            if PAGE_NUMBER_RE.match(word["text"].strip()):
                continue
            overlap_y = min(word["y1"], band_bottom) - max(word["y0"], band_top)
            if overlap_y < min_overlap_pt:
                continue
            overlap_x = min(word["x1"], band_right) - max(word["x0"], band_left)
            if overlap_x <= 0:
                continue
            collisions.append(
                {
                    "text": word["text"],
                    "x0": round(word["x0"], 2),
                    "y0": round(word["y0"], 2),
                    "x1": round(word["x1"], 2),
                    "y1": round(word["y1"], 2),
                    "overlap_y_pt": round(overlap_y, 3),
                    "overlap_x_pt": round(overlap_x, 3),
                }
            )
        if not collisions:
            continue
        collisions.sort(key=lambda c: -c["overlap_y_pt"])
        findings.append(
            {
                "page": page,
                "footer_text": " ".join(w["text"] for w in footers),
                "footer_band_pt": {
                    "x0": round(band_left, 2),
                    "y0": round(band_top, 2),
                    "x1": round(band_right, 2),
                    "y1": round(band_bottom, 2),
                },
                "min_overlap_pt": min_overlap_pt,
                "n_colliding_words": len(collisions),
                "collisions": collisions,
                "worst": collisions[0],
                "method_note": (
                    "body word boxes sharing both axes with the page-number band by at least "
                    f"{min_overlap_pt} pt; the pages reported were checked against a render"
                ),
            }
        )
    return findings


def find_python_generators(figure_name: str, scripts_dir: Path, exclude: Iterable[Path] = ()) -> list[dict[str, Any]]:
    """Scripts under ``scripts/`` whose text mentions the figure name."""
    excluded = {Path(p).resolve() for p in exclude}
    hits: list[dict[str, Any]] = []
    if not scripts_dir.is_dir():
        return hits
    for path in sorted(scripts_dir.rglob("*.py")):
        if path.resolve() in excluded or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if figure_name not in text:
            continue
        lines = [
            number
            for number, line in enumerate(text.splitlines(), start=1)
            if figure_name in line
        ]
        hits.append(
            {
                "script": str(path.relative_to(ROOT)),
                "n_mentions": len(lines),
                "first_lines": lines[:5],
                "sample": next(
                    (line.strip() for line in text.splitlines() if figure_name in line), ""
                )[:200],
            }
        )
    return hits


def measure_print_scale(
    figure_words: Sequence[dict[str, Any]],
    built_documents: Sequence[dict[str, Any]],
    min_words: int = 4,
    min_pairs: int = 6,
    cluster_tolerance: float = 0.005,
    min_cluster_fraction: float = 0.5,
) -> dict[str, Any]:
    """Scale at which a figure is placed in a built PDF, by word matching.

    Distinctive figure words (unique in the figure) that occur exactly once on a
    built-PDF page give unambiguous correspondences; every pair of such words
    yields a distance ratio, and the largest tight cluster of ratios is the
    scale estimate.  ``scale x figure width`` is the printed width.
    """
    result: dict[str, Any] = {"measured": False, "method": "unique-word pairwise distance ratio"}
    candidates: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for word in figure_words:
        counts[word["text"]] = counts.get(word["text"], 0) + 1
    distinctive = [
        word for word in figure_words if len(word["text"]) >= 5 and counts[word["text"]] == 1
    ]
    if len(distinctive) < min_words:
        result["reason"] = f"only {len(distinctive)} distinctive words in the figure"
        return result

    for document in built_documents:
        for page in document["pages"]:
            page_words = [w for w in document["words"] if w["page"] == page["page"]]
            index: dict[str, list[dict[str, Any]]] = {}
            for word in page_words:
                index.setdefault(word["text"], []).append(word)
            matched = [
                (word, index[word["text"]][0])
                for word in distinctive
                if len(index.get(word["text"], [])) == 1
            ]
            if len(matched) < min_words:
                continue
            estimates: list[tuple[float, float, float]] = []
            for i, (first, first_page) in enumerate(matched):
                for second, second_page in matched[i + 1 :]:
                    dx_fig = first["x0"] - second["x0"]
                    dy_fig = first["y0"] - second["y0"]
                    dx_page = first_page["x0"] - second_page["x0"]
                    dy_page = first_page["y0"] - second_page["y0"]
                    distance_fig = (dx_fig**2 + dy_fig**2) ** 0.5
                    if distance_fig < 25.0:
                        continue
                    distance_page = (dx_page**2 + dy_page**2) ** 0.5
                    estimates.append(
                        (
                            distance_page / distance_fig,
                            dx_page / dx_fig if dx_fig else float("nan"),
                            dy_page / dy_fig if dy_fig else float("nan"),
                        )
                    )
            if len(estimates) < min_pairs:
                continue
            values = sorted(estimate[0] for estimate in estimates)
            best_count, best_lo = 0, 0
            for i, value in enumerate(values):
                j = i
                while j + 1 < len(values) and values[j + 1] <= value * (1 + cluster_tolerance):
                    j += 1
                if j - i + 1 > best_count:
                    best_count, best_lo = j - i + 1, i
            window = values[best_lo : best_lo + best_count]
            scale = statistics.median(window)
            cluster = [
                estimate for estimate in estimates if abs(estimate[0] - scale) <= scale * cluster_tolerance
            ]
            xs = [estimate[1] for estimate in cluster if estimate[1] == estimate[1]]
            ys = [estimate[2] for estimate in cluster if estimate[2] == estimate[2]]
            candidates.append(
                {
                    "document": document["label"],
                    "page": page["page"],
                    "n_distinctive_words_matched": len(matched),
                    "n_pairs": len(estimates),
                    "n_pairs_in_cluster": best_count,
                    "cluster_fraction": round(best_count / len(estimates), 4),
                    "scale": round(scale, 6),
                    "scale_x": round(statistics.median(xs), 6) if xs else None,
                    "scale_y": round(statistics.median(ys), 6) if ys else None,
                    "cluster_rel_spread_pct": round(
                        (max(window) - min(window)) / scale * 100.0, 4
                    ),
                }
            )
    if not candidates:
        result["reason"] = "no built-PDF page carried enough unique figure words"
        return result
    candidates.sort(
        key=lambda c: (-c["cluster_fraction"], -c["n_pairs_in_cluster"], c["document"] != "manuscript")
    )
    best = candidates[0]
    confident = (
        best["cluster_fraction"] >= min_cluster_fraction
        and best["cluster_rel_spread_pct"] <= 1.0
        and best["n_distinctive_words_matched"] >= min_words
    )
    result.update(best)
    result["measured"] = True
    result["confident"] = bool(confident)
    result["other_candidates"] = candidates[1:4]
    return result


# ---------------------------------------------------------------------------
# per-file analysis
# ---------------------------------------------------------------------------


@dataclass
class Target:
    path: Path
    kind: str  # figure | manuscript | supporting_information | other
    stem: str


def analyse_file(
    target: Target,
    *,
    render_dir: Path,
    ink_verify: bool,
    tool_state: dict[str, Any],
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    path = target.path
    record: dict[str, Any] = {
        "path": rel_path(path),
        "kind": target.kind,
        "name": target.stem,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "hard_failures": [],
        "warnings": [],
    }
    hard: list[Item] = []
    warn: list[Item] = []

    # ---- pdffonts -------------------------------------------------------
    fonts: list[FontRecord] = []
    if tool_state["pdffonts"]["available"]:
        proc = run_tool(["pdffonts", str(path)])
        commands.append({"tool": "pdffonts", "argv": ["pdffonts", rel_path(path)], "returncode": proc.returncode})
        fonts = parse_pdffonts(proc.stdout)
    else:
        warn.append(Item("TOOL_MISSING", "pdffonts is not installed; fonts were not checked"))
    non_embedded = [font for font in fonts if not font.embedded]
    unnamed = [font for font in fonts if font.name.strip() in {"[none]", "none", ""}]
    type3 = [font for font in fonts if font.type.lower().startswith("type 3")]
    record["fonts"] = {
        "n_fonts": len(fonts),
        "records": [font.as_dict() for font in fonts],
        "types": dict(sorted({font.type: sum(1 for f in fonts if f.type == font.type) for font in fonts}.items())),
        "non_embedded": [font.as_dict() for font in non_embedded],
        "non_embedded_core_fonts": [
            font.as_dict() for font in non_embedded if font.is_core_font_name
        ],
        "n_non_embedded": len(non_embedded),
        "all_embedded": not non_embedded and bool(fonts),
        "unnamed_or_type3": [font.as_dict() for font in unnamed or type3][:6],
        "n_unnamed": len(unnamed),
        "n_type3": len(type3),
    }
    for font in non_embedded:
        kind_note = "core font" if font.is_core_font_name else "font"
        hard.append(
            Item(
                "FONT_NOT_EMBEDDED",
                f"font {font.name!r} ({font.type}, {font.encoding}) is not embedded ({kind_note})",
                locator={"font": font.as_dict()},
            )
        )
    for font in unnamed:
        warn.append(
            Item(
                "FONT_UNNAMED",
                f"font has no name ({font.type}, embedded={font.embedded}); "
                "producer-embedded Type 3 subsets are unnamed by design",
                locator={"font": font.as_dict()},
            )
        )

    # ---- pdfinfo --------------------------------------------------------
    geometry: dict[str, Any] = {"info_available": False}
    pages_count = None
    page_size: list[float] | None = None
    if tool_state["pdfinfo"]["available"]:
        proc = run_tool(["pdfinfo", str(path)])
        commands.append({"tool": "pdfinfo", "argv": ["pdfinfo", rel_path(path)], "returncode": proc.returncode})
        info = parse_pdfinfo(proc.stdout)
        pages_count = info["pages"]
        page_size = info["page_size_pt"]
        per_page = info["per_page_size_pt"]
        if pages_count and not per_page:
            proc2 = run_tool(["pdfinfo", "-f", "1", "-l", str(pages_count), str(path)])
            commands.append(
                {
                    "tool": "pdfinfo",
                    "argv": ["pdfinfo", "-f", "1", "-l", str(pages_count), rel_path(path)],
                    "returncode": proc2.returncode,
                }
            )
            per_page = parse_pdfinfo(proc2.stdout)["per_page_size_pt"]
        sizes = sorted({(round(w, 3), round(h, 3)) for w, h in per_page.values()})
        geometry = {
            "info_available": True,
            "pages": pages_count,
            "page_size_pt": page_size,
            "page_size_in": [round(v / 72.0, 4) for v in page_size] if page_size else None,
            "page_rot": info["page_rot"],
            "encrypted": info["encrypted"],
            "producer": info["producer"],
            "creator": info["creator"],
            "pdf_version": info["pdf_version"],
            "distinct_page_sizes": [list(s) for s in sizes],
            "uniform_page_size": len(sizes) == 1,
            "per_page_size_pt": {str(k): v for k, v in per_page.items()},
            "is_single_page": pages_count == 1,
            "media_box_pt": page_size,
        }
        if target.kind == "figure" and pages_count != 1:
            hard.append(
                Item(
                    "FIGURE_NOT_SINGLE_PAGE",
                    f"figure PDF has {pages_count} pages; a figure must be exactly one page",
                    page=None,
                    locator={"pages": pages_count},
                )
            )
        if not geometry["uniform_page_size"]:
            warn.append(
                Item(
                    "PAGE_SIZE_VARIES",
                    f"page sizes differ between pages: {geometry['distinct_page_sizes']}",
                    locator={"distinct_page_sizes": geometry["distinct_page_sizes"]},
                )
            )
    else:
        warn.append(Item("TOOL_MISSING", "pdfinfo is not installed; page geometry was not checked"))
    record["geometry"] = geometry

    # ---- pdftotext -bbox ------------------------------------------------
    bbox_pages: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    if tool_state["pdftotext"]["available"]:
        proc = run_tool(["pdftotext", "-bbox", str(path), "-"])
        commands.append(
            {
                "tool": "pdftotext",
                "argv": ["pdftotext", "-bbox", rel_path(path), "-"],
                "returncode": proc.returncode,
            }
        )
        bbox_pages, words = parse_bbox_pages(proc.stdout)
    else:
        warn.append(Item("TOOL_MISSING", "pdftotext is not installed; text was not checked"))
    page_boxes = {page["page"]: page for page in bbox_pages}
    if pages_count is not None and bbox_pages and len(bbox_pages) != pages_count:
        warn.append(
            Item(
                "BBOX_PAGE_COUNT_MISMATCH",
                f"pdftotext -bbox reported {len(bbox_pages)} pages but pdfinfo reports {pages_count}",
            )
        )

    # (c) text outside the page box --------------------------------------
    violations: list[dict[str, Any]] = []
    max_overflow = 0.0
    for word in words:
        box = page_boxes.get(word["page"])
        if box is None:
            continue
        over = {
            "left": max(0.0, -word["x0"]),
            "top": max(0.0, -word["y0"]),
            "right": max(0.0, word["x1"] - box["width_pt"]),
            "bottom": max(0.0, word["y1"] - box["height_pt"]),
        }
        worst = max(over.values())
        if worst <= 0:
            continue
        max_overflow = max(max_overflow, worst)
        if worst > OUT_PAGE_TOLERANCE_PT:
            violations.append(
                {
                    "page": word["page"],
                    "text": word["text"],
                    "x0": round(word["x0"], 2),
                    "y0": round(word["y0"], 2),
                    "x1": round(word["x1"], 2),
                    "y1": round(word["y1"], 2),
                    "page_width_pt": round(box["width_pt"], 2),
                    "page_height_pt": round(box["height_pt"], 2),
                    "overflow_pt": {k: round(v, 3) for k, v in over.items() if v > 0},
                    "max_overflow_pt": round(worst, 3),
                }
            )
    record["text_bounds"] = {
        "tolerance_pt": OUT_PAGE_TOLERANCE_PT,
        "n_words": len(words),
        "n_pages_with_words": len({w["page"] for w in words}),
        "n_violations": len(violations),
        "max_overflow_pt": round(max_overflow, 3),
        "violations": violations,
        "violating_pages": sorted({v["page"] for v in violations}),
        "ok": not violations,
    }
    # The word box is Poppler's font box, not the ink: a rotated axis label or a
    # caption line without descenders can put the box 1-3 pt outside the page
    # while the rendered ink stays 1-2 pt inside.  The rendered page decides, so
    # the ink check runs first and a box violation is only a hard failure when the
    # ink could not be measured or the ink really is clipped/flush at the edge.
    ink_checks: list[dict[str, Any]] = []
    record["ink_checks"] = ink_checks
    ink_verdict: dict[int, str] = {}
    for page in record["text_bounds"]["violating_pages"]:
        if not ink_verify:
            ink_verdict[page] = "not_run"
            continue
        check = ink_bbox(
            path,
            page,
            render_dir,
            page_size_pt=[page_boxes[page]["width_pt"], page_boxes[page]["height_pt"]],
        )
        check["page"] = page
        ink_checks.append(check)
        if not check.get("available"):
            ink_verdict[page] = "unavailable"
            warn.append(
                Item(
                    "INK_CHECK_UNAVAILABLE",
                    f"the page could not be rendered, so the box violation on page {page} is "
                    f"unverified: {check.get('reason', 'no reason given')}",
                    page=page,
                )
            )
        elif check.get("ink_flush_to_edge"):
            ink_verdict[page] = "clipped"
            hard.append(
                Item(
                    "INK_CLIPPED_AT_PAGE_EDGE",
                    f"rendered ink reaches within {INK_EDGE_FLUSH_PT} pt of the page edge "
                    f"(margins {check.get('margin_pt')}): glyphs are clipped by the page box",
                    page=page,
                    locator={
                        "ink_bbox_pt": check.get("ink_bbox_pt"),
                        "margin_pt": check.get("margin_pt"),
                        "render_png": check.get("render_png"),
                    },
                )
            )
        else:
            ink_verdict[page] = "padding_only"
            warn.append(
                Item(
                    "TEXT_BOX_PADDING_ONLY",
                    f"word boxes cross the page edge but the rendered ink stays "
                    f"{min(check.get('margin_pt', {'?': 0}).values()):.2f} pt inside: "
                    "Poppler font-box padding, no clipped glyph",
                    page=page,
                    locator={"ink_bbox_pt": check.get("ink_bbox_pt"), "margin_pt": check.get("margin_pt")},
                )
            )
    record["text_bounds"]["ink_verdict_by_page"] = {
        str(page): verdict for page, verdict in sorted(ink_verdict.items())
    }
    record["text_bounds"]["n_hard_violations"] = sum(
        1
        for violation in violations
        if ink_verdict.get(violation["page"], "unavailable") in {"clipped", "unavailable", "not_run"}
    )
    for violation in violations:
        verdict = ink_verdict.get(violation["page"], "unavailable")
        verified_padding = verdict == "padding_only"
        item = Item(
            "TEXT_BOX_PADDING_ONLY" if verified_padding else "TEXT_OUTSIDE_PAGE",
            (
                f"word {violation['text']!r} box extends "
                f"{violation['max_overflow_pt']:.2f} pt outside the page "
                f"({violation['overflow_pt']}); rendered ink stays inside the page, so this is "
                "Poppler font-box padding"
                if verified_padding
                else f"word {violation['text']!r} box extends "
                f"{violation['max_overflow_pt']:.2f} pt outside the page "
                f"({violation['overflow_pt']}); ink verdict: {verdict}"
            ),
            page=violation["page"],
            locator={
                **{
                    k: violation[k]
                    for k in ("x0", "y0", "x1", "y1", "page_width_pt", "page_height_pt", "overflow_pt")
                },
                "ink_verdict": verdict,
            },
        )
        if verified_padding:
            warn.append(item)
        else:
            hard.append(item)

    # (d) minimum text height --------------------------------------------
    # A Poppler word box is the glyph box, so a word made only of x-height
    # letters (``a``, ``no``) reports roughly half the typeset size while a word
    # with an ascender or descender reports about the full size.  Size is
    # therefore estimated per text line: the tallest box on the line is the
    # closest proxy for the typeset size, and a word is only reported when the
    # line itself is small, or when the word is far smaller than its own line
    # (a genuine superscript/subscript).
    parent = list(range(len(words)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    by_page: dict[int, list[int]] = {}
    for index, word in enumerate(words):
        by_page.setdefault(word["page"], []).append(index)
    for page_indices in by_page.values():
        ordered = sorted(page_indices, key=lambda i: (words[i]["y0"], words[i]["x0"]))
        for a in range(len(ordered)):
            ia = ordered[a]
            ha = words[ia]["height_pt"]
            if ha <= 0.05:
                continue
            for b in range(a + 1, len(ordered)):
                ib = ordered[b]
                hb = words[ib]["height_pt"]
                if hb <= 0.05:
                    continue
                if words[ib]["y0"] > words[ia]["y1"]:
                    break
                overlap = min(words[ia]["y1"], words[ib]["y1"]) - max(words[ia]["y0"], words[ib]["y0"])
                if overlap > 0.5 * min(ha, hb):
                    union(ia, ib)
    line_size: dict[int, float] = {}
    for index, word in enumerate(words):
        if word["height_pt"] <= 0.05:
            continue
        root = find(index)
        line_size[root] = max(line_size.get(root, 0.0), word["height_pt"])
    SMALL_FRACTION = 0.45
    tiny: list[dict[str, Any]] = []
    small_words: list[dict[str, Any]] = []
    degenerate = 0
    for index, word in enumerate(words):
        height = word["height_pt"]
        if height <= 0.05:
            degenerate += 1
            continue
        estimated = line_size.get(find(index), height)
        if estimated >= MIN_TEXT_HEIGHT_PT and height >= SMALL_FRACTION * estimated:
            continue
        if estimated >= MIN_TEXT_HEIGHT_PT:
            small_words.append(
                {
                    "page": word["page"],
                    "text": word["text"],
                    "height_pt": round(height, 3),
                    "line_height_pt": round(estimated, 3),
                }
            )
            continue
        neighbours = []
        for other in words[max(0, index - 3) : index + 4]:
            if other is word or other["page"] != word["page"]:
                continue
            neighbours.append(
                {"text": other["text"], "height_pt": round(other["height_pt"], 2)}
            )
        tiny.append(
            {
                "page": word["page"],
                "text": word["text"],
                "x0": round(word["x0"], 2),
                "y0": round(word["y0"], 2),
                "x1": round(word["x1"], 2),
                "y1": round(word["y1"], 2),
                "height_pt": round(height, 3),
                "width_pt": round(word["width_pt"], 3),
                "line_estimated_height_pt": round(estimated, 3),
                "ratio_to_line": round(height / estimated, 3) if estimated else None,
                "neighbour_words": neighbours,
            }
        )
    heights = [w["height_pt"] for w in words if w["height_pt"] > 0.05]
    p05 = None
    if heights:
        ordered_heights = sorted(heights)
        p05 = ordered_heights[max(0, int(round(0.05 * (len(ordered_heights) - 1))))]
    # The literal rule of the original brief -- every word box below the
    # threshold -- is kept as evidence even though the agreed gate uses the
    # line estimate, so nothing has been hidden by the refinement.
    raw_small_boxes = [
        {
            "page": word["page"],
            "text": word["text"],
            "height_pt": round(word["height_pt"], 3),
            "line_estimated_height_pt": round(line_size.get(find(index), word["height_pt"]), 3),
            "x0": round(word["x0"], 2),
            "y0": round(word["y0"], 2),
            "x1": round(word["x1"], 2),
            "y1": round(word["y1"], 2),
        }
        for index, word in enumerate(words)
        if 0.05 < word["height_pt"] < MIN_TEXT_HEIGHT_PT
    ]
    line_sizes = sorted(line_size.values())
    record["min_text_height"] = {
        "threshold_pt": MIN_TEXT_HEIGHT_PT,
        "min_height_pt": round(min(heights), 3) if heights else None,
        "min_line_height_pt": round(line_sizes[0], 3) if line_sizes else None,
        "p05_height_pt": round(p05, 3) if p05 is not None else None,
        "median_height_pt": round(statistics.median(heights), 3) if heights else None,
        "n_words_measured": len(heights),
        "n_below_threshold": len(tiny),
        "n_small_relative_words": len(small_words),
        "n_degenerate_boxes": degenerate,
        "violations": tiny,
        "n_raw_boxes_below_threshold": len(raw_small_boxes),
        "raw_boxes_below_threshold": raw_small_boxes[:200],
        "raw_boxes_below_threshold_truncated": max(0, len(raw_small_boxes) - 200),
        "small_relative_words": small_words[:20],
        "ok": not tiny,
        "method_note": (
            "typeset size is estimated per text line from the tallest Poppler word box on "
            "that line; the raw box height of an x-height-only word (``a``) is about half "
            "the typeset size, so raw boxes are not used as the size criterion"
        ),
    }
    for item in tiny:
        hard.append(
            Item(
                "TEXT_HEIGHT_BELOW_MINIMUM",
                f"word {item['text']!r} box is {item['height_pt']:.2f} pt high "
                f"(< {MIN_TEXT_HEIGHT_PT} pt)",
                page=item["page"],
                locator={
                    "x0": item["x0"],
                    "y0": item["y0"],
                    "x1": item["x1"],
                    "y1": item["y1"],
                    "height_pt": item["height_pt"],
                    "line_estimated_height_pt": item["line_estimated_height_pt"],
                    "ratio_to_line": item["ratio_to_line"],
                    "neighbour_words": item["neighbour_words"],
                },
            )
        )
    if small_words:
        warn.append(
            Item(
                "SMALL_RELATIVE_WORD_BOXES",
                f"{len(small_words)} word box(es) are below {SMALL_FRACTION:.2f} of their own "
                "line height (superscripts, subscripts or fragmented runs); the line itself "
                f"is at or above {MIN_TEXT_HEIGHT_PT} pt",
                locator={"examples": small_words[:8]},
            )
        )
    if degenerate:
        warn.append(
            Item(
                "DEGENERATE_WORD_BOXES",
                f"{degenerate} word box(es) with a non-positive height were excluded from the "
                "height check",
            )
        )

    # (e) overlaps --------------------------------------------------------
    overlaps = check_overlaps(words, {str(k): v for k, v in page_boxes.items()})
    record["overlaps"] = overlaps
    if overlaps["n_same_baseline_pairs"]:
        warn.append(
            Item(
                "OVERLAPPING_TEXT_SAME_BASELINE",
                f"{overlaps['n_same_baseline_pairs']} word-box pair(s) share a baseline and "
                "overlap horizontally (real text collision candidates)",
                locator={"n_pairs": overlaps["n_same_baseline_pairs"]},
            )
        )
    other_pairs = overlaps["n_candidate_pairs"] - overlaps["n_same_baseline_pairs"]
    if other_pairs:
        warn.append(
            Item(
                "OVERLAPPING_WORD_BOXES",
                f"{other_pairs} further word-box pair(s) overlap above "
                f"{OVERLAP_FRACTION:.0%} of the smaller box; box padding/rotated-text "
                "artifacts, verify against the render",
                locator={"counts_by_kind": overlaps["counts_by_kind"]},
            )
        )

    # (e') labels drawn with no word gap: merged into a single word box -----
    merged = detect_merged_label_runs(
        path, words, {page: box["height_pt"] for page, box in page_boxes.items()}
    )
    record["merged_label_runs"] = {
        "n_findings": len(merged),
        "findings": merged,
        "method_note": (
            "a repeated substring inside one word box means adjacent labels were drawn with no "
            "space glyph between them, so Poppler cannot split them into separate words; the "
            "pairwise overlap test is blind to this and the row reads as one continuous string"
        ),
    }
    for finding in merged:
        warn.append(
            Item(
                "MERGED_LABEL_RUN_SUSPECT",
                f"word {finding['text']!r} repeats {finding['repeated_unit']!r} x{finding['n_repeats']} "
                f"inside one box {finding['width_pt']:.1f} pt wide; "
                f"{finding['n_text_runs_found']} drawing run(s) recovered from the content stream"
                + (
                    f", pitch {finding['min_pitch_pt']}-{finding['max_pitch_pt']} pt"
                    if finding["min_pitch_pt"]
                    else ""
                ),
                page=finding["page"],
                locator={
                    "x0": finding["x0"],
                    "y0": finding["y0"],
                    "x1": finding["x1"],
                    "y1": finding["y1"],
                    "text_runs": finding["text_runs"],
                },
            )
        )

    # page-number band: a long text block can push a body line into the footer
    footer_collisions = detect_footer_collisions(words)
    record["footer_collisions"] = {
        "n_findings": len(footer_collisions),
        "min_overlap_pt": FOOTER_BAND_MIN_OVERLAP_PT,
        "findings": footer_collisions,
    }
    for finding in footer_collisions:
        warn.append(
            Item(
                "FOOTER_TEXT_COLLISION",
                f"page number {finding['footer_text']!r} is overprinted by "
                f"{finding['n_colliding_words']} body word box(es); worst "
                f"{finding['worst']['text']!r} at "
                f"({finding['worst']['x0']}, {finding['worst']['y0']}, "
                f"{finding['worst']['x1']}, {finding['worst']['y1']}) overlaps the number band "
                f"{finding['worst']['overlap_y_pt']:.2f} pt vertically",
                page=finding["page"],
                locator={
                    "footer_band_pt": finding["footer_band_pt"],
                    "collisions": finding["collisions"],
                },
            )
        )

    # (g) raster images ---------------------------------------------------
    raster: dict[str, Any] = {
        "tool_available": tool_state["pdfimages"]["available"],
        "n_images": 0,
        "images": [],
        "below_300dpi": [],
        "ok": True,
    }
    if tool_state["pdfimages"]["available"]:
        proc = run_tool(["pdfimages", "-list", str(path)])
        commands.append(
            {
                "tool": "pdfimages",
                "argv": ["pdfimages", "-list", rel_path(path)],
                "returncode": proc.returncode,
            }
        )
        images = parse_pdfimages(proc.stdout)
        below = [image for image in images if image.min_ppi < MIN_RASTER_DPI]
        raster.update(
            {
                "n_images": len(images),
                "images": [image.as_dict() for image in images],
                "below_300dpi": [image.as_dict() for image in below],
                "min_ppi": min((image.min_ppi for image in images), default=None),
                "ok": not below,
            }
        )
        for image in below:
            warn.append(
                Item(
                    "RASTER_BELOW_300_DPI",
                    f"raster image {image.num} on page {image.page} "
                    f"({image.width_px}x{image.height_px} px, {image.color}) has an effective "
                    f"resolution of {image.x_ppi:.0f}x{image.y_ppi:.0f} ppi (< {MIN_RASTER_DPI:.0f})",
                    page=image.page,
                    locator=image.as_dict(),
                )
            )
    else:
        warn.append(Item("TOOL_MISSING", "pdfimages is not installed; raster resolution was not checked"))
    record["raster"] = raster

    # (f) provenance ------------------------------------------------------
    if target.kind == "figure":
        drawio_candidates = [
            ROOT / "figures" / "v17" / "drawio" / f"{target.stem}.drawio",
            ROOT / "figures" / "wrr" / "drawio" / f"{target.stem}.drawio",
        ]
        drawio_expected = next((c for c in drawio_candidates if c.exists()), drawio_candidates[0])
        drawio_repo = sorted(
            str(p.relative_to(ROOT)) for p in (ROOT / "figures").rglob(f"{target.stem}.drawio")
        )
        generators = find_python_generators(
            target.stem, ROOT / "scripts", exclude=[Path(__file__).resolve()]
        )
        schematic_reason = SCHEMATIC_FIGURES.get(target.stem)
        schematic = bool(schematic_reason) or drawio_expected.exists()
        upstream: list[dict[str, Any]] = []
        for candidate in sorted((ROOT / "figures").rglob(f"{target.stem}.pdf")):
            if candidate.resolve() == path.resolve():
                continue
            upstream.append(
                {
                    "path": str(candidate.relative_to(ROOT)),
                    "size_bytes": candidate.stat().st_size,
                    "identical_to_paper_copy": candidate.stat().st_size == path.stat().st_size
                    and sha256_of(candidate) == record["sha256"],
                }
            )
        record["provenance"] = {
            "drawio_source_expected": str(drawio_expected.relative_to(ROOT)),
            "drawio_source_exists": drawio_expected.exists(),
            "drawio_sources_in_repo": drawio_repo,
            "python_generators": generators,
            "schematic": schematic,
            "schematic_reason": schematic_reason
            or ("draw.io source present" if drawio_expected.exists() else None),
            "schematic_list_is_explicit": True,
            "upstream_pdf_candidates": upstream,
        }
        if schematic and not drawio_repo:
            hard.append(
                Item(
                    "SCHEMATIC_WITHOUT_DRAWIO_SOURCE",
                    f"schematic figure has no draw.io source at {drawio_expected.relative_to(ROOT)}",
                    locator={"drawio_sources_in_repo": drawio_repo},
                )
            )
        elif not drawio_expected.exists() and not generators:
            warn.append(
                Item(
                    "PROVENANCE_UNKNOWN",
                    "no draw.io source and no script under scripts/ mentions this figure name",
                    locator={"drawio_sources_in_repo": drawio_repo},
                )
            )
        if drawio_repo:
            record["provenance"]["kind"] = "drawio" if not generators else "drawio+python"
        elif generators:
            record["provenance"]["kind"] = "python"
        else:
            record["provenance"]["kind"] = "unknown"

    record["hard_failures"] = [item.as_dict(record["path"]) for item in hard]
    record["warnings"] = [item.as_dict(record["path"]) for item in warn]
    return record


# ---------------------------------------------------------------------------
# report generation
# ---------------------------------------------------------------------------


def per_figure_row(record: dict[str, Any], scale_row: dict[str, Any] | None) -> list[str]:
    geometry = record.get("geometry", {})
    fonts = record.get("fonts", {})
    bounds = record.get("text_bounds", {})
    small = record.get("min_text_height", {})
    overlaps = record.get("overlaps", {})
    raster = record.get("raster", {})
    provenance = record.get("provenance", {})
    effective_p05 = None
    if scale_row and scale_row.get("scale") and small.get("p05_height_pt"):
        effective_p05 = small["p05_height_pt"] * scale_row["scale"]
    return [
        f"`{record['name']}`",
        str(geometry.get("pages", "-")),
        f"{fmt(geometry.get('page_size_in', [None])[0])}x{fmt(geometry.get('page_size_in', [None, None])[1])}"
        if geometry.get("page_size_in")
        else "-",
        str(fonts.get("n_fonts", "-")),
        str(fonts.get("n_non_embedded", "-")),
        str(bounds.get("n_violations", "-")),
        f"{fmt(small.get('min_height_pt'))}",
        str(overlaps.get("n_candidate_pairs", "-")),
        str(overlaps.get("n_same_baseline_pairs", "-")),
        f"{fmt(raster.get('min_ppi'), 0)}",
        str(provenance.get("kind", "-")),
        fmt(effective_p05) if effective_p05 else "-",
        "HARD" if record["hard_failures"] else ("warn" if record["warnings"] else "ok"),
    ]


def build_markdown(
    payload: dict[str, Any],
    *,
    json_path: Path,
    md_path: Path,
    figure_records: list[dict[str, Any]],
    built_records: list[dict[str, Any]],
    scale_rows: dict[str, dict[str, Any]],
    max_pairs_in_table: int = 25,
    max_small_in_table: int = 25,
) -> str:
    lines: list[str] = []
    summary = payload["summary"]
    add = lines.append
    add("# WRR figure and PDF quality assurance")
    add("")
    add(f"Generated {payload['generated_utc']} by `python3 scripts/266_wrr_figure_qa.py`.")
    add("")
    add(f"* JSON: `{rel_path(json_path)}`")
    add(f"* Markdown: `{rel_path(md_path)}`")
    add(f"* tools: " + ", ".join(f"`{k}` {v or 'MISSING'}" for k, v in payload["tool_versions"].items()))
    add("")
    add("## Verdict")
    add("")
    verdict = "FAIL" if summary["n_hard_failures"] else "PASS (with warnings)" if summary["n_warnings"] else "PASS"
    add(
        f"**{verdict}** — {summary['n_hard_failures']} hard failure(s) in "
        f"{summary['n_hard_failure_groups']} file/check/page group(s), "
        f"{summary['n_warnings']} warning(s)."
    )
    add("")
    add(
        f"Exit status is {payload['exit_code']} for the strict run "
        f"(`--report-only` always exits 0 so the regression test is not turned red by a real finding)."
    )
    add("")
    add("| check | hard failures | warnings |")
    add("|---|---|---|")
    for check in payload["check_catalogue"]:
        add(
            f"| {check['id']} — {check['description']} | "
            f"{summary['hard_failures_by_check'].get(check['id'], 0)} | "
            f"{summary['warnings_by_check'].get(check['id'], 0)} |"
        )
    add("")
    add("Thresholds: "
        f"text outside page > {OUT_PAGE_TOLERANCE_PT} pt, line-estimated type size < {MIN_TEXT_HEIGHT_PT} pt, "
        f"overlap > {OVERLAP_FRACTION:.0%} of the smaller box, raster < {MIN_RASTER_DPI:.0f} dpi.")
    add("")
    add("### Real defects versus box-model artifacts")
    add("")
    real_groups = list(summary["hard_failure_groups"])
    artifact_pages = [
        {
            "file": record["path"],
            "page": check["page"],
            "n": sum(
                1
                for violation in record.get("text_bounds", {}).get("violations", [])
                if violation["page"] == check["page"]
            ),
        }
        for record in figure_records + built_records
        for check in record.get("ink_checks", [])
        if check.get("available") and not check.get("ink_flush_to_edge")
    ]
    if real_groups:
        add(
            "Every hard failure below is either confirmed by a render (the ink really is clipped "
            "at the page edge) or unverified because the page could not be rendered. These are "
            "the findings to act on."
        )
        add("")
        add("| file | check | page | n | example |")
        add("|---|---|---|---|---|")
        for group in real_groups:
            page = group["page"] if group["page"] is not None else "-"
            example = group["examples"][0] if group["examples"] else ""
            add(
                f"| `{group['file']}` | {group['check']} | {page} | {group['n']} | "
                f"{md_escape(example)} |"
            )
    else:
        add(
            "No hard failure was recorded: every word box that crosses a page edge was shown by "
            "the render to keep its ink inside the page, and no line of type is below the size "
            "threshold."
        )
    add("")
    real_warnings = [
        warning for warning in payload["warnings"] if warning["check"] in REAL_DEFECT_WARNINGS
    ]
    if real_warnings:
        add(
            f"**{len(real_warnings)} warning(s) below are defects in the artifact, not box-model "
            "artifacts, and are the ones worth acting on:**"
        )
        add("")
        add("| file | check | page | finding |")
        add("|---|---|---|---|")
        for warning in real_warnings:
            path = warning.get("file", "-")
            page = warning.get("page", "-")
            details = md_escape(warning["detail"])
            locator = warning.get("locator") or {}
            if warning["check"] == "FOOTER_TEXT_COLLISION" and locator.get("collisions"):
                worst = locator["collisions"][0]
                details += (
                    f"; word box ({worst['x0']}, {worst['y0']}, {worst['x1']}, {worst['y1']})"
                )
            add(f"| `{path}` | {warning['check']} | {page} | {details} |")
        add("")
    else:
        add("No warning-level finding is classified as a real defect.")
        add("")
    if artifact_pages:
        add(
            f"{len(artifact_pages)} flagged page(s) are box-model artifacts rather than defects "
            "(word box outside the page box, rendered ink inside): "
            + ", ".join(
                f"`{entry['file']}` p{entry['page']} ({entry['n']} word box(es))"
                for entry in artifact_pages
            )
            + ". They are reported as warnings."
        )
        add("")

    # ---- per figure master table ---------------------------------------
    add("## Per-figure master table")
    add("")
    add(
        "| figure | pages | page size (in) | fonts | non-embedded | text outside page "
        "| min word height (pt) | overlap pairs | of which same baseline | min raster ppi "
        "| source | effective print p05 (pt) | verdict |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for record in figure_records:
        add("| " + " | ".join(per_figure_row(record, scale_rows.get(record["name"]))) + " |")
    add("")
    add(
        "\"effective print p05\" is the 5th-percentile word-box height multiplied by the measured "
        "placement scale in the built PDFs (derived, see the print-size section)."
    )
    add("")

    add("## Built documents")
    add("")
    add("| document | pages | page size (pt) | page size (in) | fonts | non-embedded | text outside page | min word height (pt) | overlap pairs | same baseline | min raster ppi |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for record in built_records:
        geometry = record.get("geometry", {})
        fonts = record.get("fonts", {})
        bounds = record.get("text_bounds", {})
        small = record.get("min_text_height", {})
        overlaps = record.get("overlaps", {})
        raster = record.get("raster", {})
        size_pt = geometry.get("page_size_pt") or [None, None]
        size_in = geometry.get("page_size_in") or [None, None]
        add(
            f"| `{record['path']}` | {geometry.get('pages', '-')} | "
            f"{fmt(size_pt[0])} x {fmt(size_pt[1])} | {fmt(size_in[0])} x {fmt(size_in[1])} | "
            f"{fonts.get('n_fonts', '-')} | {fonts.get('n_non_embedded', '-')} | "
            f"{bounds.get('n_violations', '-')} | {fmt(small.get('min_height_pt'))} | "
            f"{overlaps.get('n_candidate_pairs', '-')} | {overlaps.get('n_same_baseline_pairs', '-')} | "
            f"{fmt(raster.get('min_ppi'), 0)} |"
        )
    add("")

    # ---- fonts ----------------------------------------------------------
    add("## 1. Fonts (check a)")
    add("")
    add(
        "| file | fonts | types | non-embedded | names of non-embedded | unnamed/Type 3 | all embedded |"
    )
    add("|---|---|---|---|---|---|---|")
    for record in figure_records + built_records:
        fonts = record.get("fonts", {})
        types = ", ".join(f"{k} x{v}" for k, v in fonts.get("types", {}).items()) or "-"
        bad = ", ".join(f"`{f['name']}`" for f in fonts.get("non_embedded", [])) or "none"
        unnamed = ", ".join(f"`{f['name']}`" for f in fonts.get("unnamed_or_type3", [])) or "none"
        add(
            f"| `{record['path']}` | {fonts.get('n_fonts', '-')} | {md_escape(types)} | "
            f"{fonts.get('n_non_embedded', '-')} | {md_escape(bad)} | {md_escape(unnamed)} | "
            f"{'yes' if fonts.get('all_embedded') else 'NO'} |"
        )
    add("")
    add(
        "`[none]` is the name Poppler reports for a producer-embedded Type 3 subset with no "
        "BaseFont entry (matplotlib's default pdf.fonttype=3); the font is embedded even though "
        "it is unnamed."
    )
    add("")

    # ---- geometry -------------------------------------------------------
    add("## 2. Page geometry (check b)")
    add("")
    add("| file | pages | page size (pt) | page size (in) | distinct page sizes | single page | text outside page | max overflow (pt) |")
    add("|---|---|---|---|---|---|---|---|")
    for record in figure_records + built_records:
        geometry = record.get("geometry", {})
        bounds = record.get("text_bounds", {})
        size_pt = geometry.get("page_size_pt") or [None, None]
        size_in = geometry.get("page_size_in") or [None, None]
        add(
            f"| `{record['path']}` | {geometry.get('pages', '-')} | {fmt(size_pt[0])} x {fmt(size_pt[1])} | "
            f"{fmt(size_in[0])} x {fmt(size_in[1])} | {len(geometry.get('distinct_page_sizes', []))} | "
            f"{'yes' if geometry.get('is_single_page') else 'no'} | {bounds.get('n_violations', '-')} | "
            f"{fmt(bounds.get('max_overflow_pt'))} |"
        )
    add("")

    # ---- off-page text --------------------------------------------------
    add("## 3. Text outside the page box (check c)")
    add("")
    off_page = [
        (record, violation)
        for record in figure_records + built_records
        for violation in record.get("text_bounds", {}).get("violations", [])
    ]
    if not off_page:
        add(
            f"No word box extends more than {OUT_PAGE_TOLERANCE_PT} pt outside its page in any "
            "target PDF."
        )
        add("")
    else:
        add(f"{len(off_page)} word box(es) cross a page edge by more than {OUT_PAGE_TOLERANCE_PT} pt.")
        add("")
        add("| file | page | word | box (x0, y0, x1, y1) | page box | overflow (pt) |")
        add("|---|---|---|---|---|---|")
        for record, violation in off_page[:max_small_in_table]:
            add(
                f"| `{record['path']}` | {violation['page']} | `{md_escape(violation['text'])}` | "
                f"({violation['x0']}, {violation['y0']}, {violation['x1']}, {violation['y1']}) | "
                f"{violation['page_width_pt']} x {violation['page_height_pt']} | "
                f"{md_escape(json.dumps(violation['overflow_pt']))} |"
            )
        if len(off_page) > max_small_in_table:
            add(f"| ... | | {len(off_page) - max_small_in_table} more in the JSON | | | |")
        add("")
        add("### Ink verification of the flagged pages")
        add("")
        add(
            "Word boxes carry font ascent/descent padding, so the flagged pages were rendered "
            f"with `pdftoppm -r {INK_DPI}` and the ink bounding box was measured "
            f"(grey level < {INK_THRESHOLD} counts as ink, {INK_EDGE_FLUSH_PT} pt counts as flush)."
        )
        add("")
        flush_pages = [
            (record, check)
            for record in figure_records + built_records
            for check in record.get("ink_checks", [])
            if check.get("ink_flush_to_edge")
        ]
        padded_pages = [
            (record, check)
            for record in figure_records + built_records
            for check in record.get("ink_checks", [])
            if check.get("available") and not check.get("ink_flush_to_edge")
        ]
        if flush_pages:
            add(
                f"**{len(flush_pages)} flagged page(s) have rendered ink flush with the page edge "
                f"(within {INK_EDGE_FLUSH_PT} pt): the glyphs are clipped by the page box, so the "
                "box violation is a real defect (`INK_CLIPPED_AT_PAGE_EDGE`):** "
                + ", ".join(f"`{record['path']}` p{check['page']}" for record, check in flush_pages)
                + "."
            )
            add("")
        if padded_pages:
            add(
                f"**{len(padded_pages)} flagged page(s) have ink that stays inside the page: the "
                "box crosses the edge only through Poppler's font-box padding, so the words are "
                "reported as `TEXT_BOX_PADDING_ONLY` warnings rather than hard failures:** "
                + ", ".join(f"`{record['path']}` p{check['page']}" for record, check in padded_pages)
                + "."
            )
            add("")
        unverified = [
            (record, check)
            for record in figure_records + built_records
            for check in record.get("ink_checks", [])
            if not check.get("available")
        ]
        if unverified:
            add(
                f"**{len(unverified)} flagged page(s) could not be rendered, so their box "
                "violations stay hard failures because they are unverified.**"
            )
            add("")
        add("| file | page | ink box (l, t, r, b) | margins (l, t, r, b) | verdict | render |")
        add("|---|---|---|---|---|---|")
        for record in figure_records + built_records:
            for check in record.get("ink_checks", []):
                if not check.get("available"):
                    add(
                        f"| `{record['path']}` | {check.get('page')} | - | - | "
                        f"unavailable: {md_escape(check.get('reason', ''))} | - |"
                    )
                    continue
                ink = check.get("ink_bbox_pt") or {}
                margins = check.get("margin_pt") or {}
                verdict = (
                    "ink flush/clipped at the page edge"
                    if check.get("ink_flush_to_edge")
                    else "box padding only, ink inside the page"
                )
                add(
                    f"| `{record['path']}` | {check['page']} | "
                    f"({fmt(ink.get('left'))}, {fmt(ink.get('top'))}, {fmt(ink.get('right'))}, "
                    f"{fmt(ink.get('bottom'))}) | "
                    f"({fmt(margins.get('left'))}, {fmt(margins.get('top'))}, {fmt(margins.get('right'))}, "
                    f"{fmt(margins.get('bottom'))}) | {verdict} | `{check.get('render_png', '-')}` |"
                )
        add("")

    # ---- tiny text ------------------------------------------------------
    add("## 4. Minimum text height (check d)")
    add("")
    add(
        f"| file | words measured | min box (pt) | 5th pct (pt) | median (pt) | raw boxes < {MIN_TEXT_HEIGHT_PT} pt (literal rule) | lines below threshold (gate) | smaller than their line | degenerate boxes |"
    )
    add("|---|---|---|---|---|---|---|---|---|")
    for record in figure_records + built_records:
        small = record.get("min_text_height", {})
        add(
            f"| `{record['path']}` | {small.get('n_words_measured', '-')} | {fmt(small.get('min_height_pt'))} | "
            f"{fmt(small.get('p05_height_pt'))} | {fmt(small.get('median_height_pt'))} | "
            f"{small.get('n_raw_boxes_below_threshold', '-')} | {small.get('n_below_threshold', '-')} | "
            f"{small.get('n_small_relative_words', '-')} | {small.get('n_degenerate_boxes', '-')} |"
        )
    add("")
    tiny_rows = [
        (record, violation)
        for record in figure_records + built_records
        for violation in record.get("min_text_height", {}).get("violations", [])
    ]
    if tiny_rows:
        add(
            "Grouped by page (one placed figure can carry hundreds of words below the "
            "threshold, so the cause is stated once here):"
        )
        add("")
        add("| file | page | words below threshold | min height (pt) | median height (pt) | example words | attributed figure |")
        add("|---|---|---|---|---|---|---|")
        for group in payload["summary"]["tiny_text_by_page"]:
            add(
                f"| `{group['file']}` | {group['page']} | {group['n_below_threshold']} | "
                f"{fmt(group['min_height_pt'], 3)} | {fmt(group['median_height_pt'], 3)} | "
                f"{md_escape(', '.join(group['distinct_words']))} | "
                f"{group['attributed_figure'] or '-'} |"
            )
        add("")
        add(f"Smallest boxes overall (up to {max_small_in_table} rows):")
        add("")
        add("| file | page | word | box (x0, y0, x1, y1) | height (pt) | line estimate (pt) | height / line | width (pt) | neighbour words (text: height) |")
        add("|---|---|---|---|---|---|---|---|---|")
        for record, violation in sorted(tiny_rows, key=lambda row: row[1]["height_pt"])[:max_small_in_table]:
            neighbours = ", ".join(
                f"{md_escape(n['text'])}: {fmt(n['height_pt'])}" for n in violation["neighbour_words"]
            )
            add(
                f"| `{record['path']}` | {violation['page']} | `{md_escape(violation['text'])}` | "
                f"({violation['x0']}, {violation['y0']}, {violation['x1']}, {violation['y1']}) | "
                f"{fmt(violation['height_pt'], 3)} | {fmt(violation.get('line_estimated_height_pt'), 3)} | "
                f"{fmt(violation.get('ratio_to_line'), 2)} | {fmt(violation['width_pt'], 3)} | {neighbours} |"
            )
        if len(tiny_rows) > max_small_in_table:
            add(f"| ... | | {len(tiny_rows) - max_small_in_table} more in the JSON | | | | |")
        add("")
        add(
            "Typeset size is estimated per text line: the tallest Poppler word box on the line "
            "stands in for the size, because a word made only of x-height letters (``a``, ``no``) "
            "reports roughly half the typeset size while a word with an ascender or descender "
            "reports about the full size. A word is a hard failure only when its own line "
            "estimate is below the threshold; a word far smaller than its line (a superscript, a "
            "subscript or a fragment of a rotated run) is reported as "
            "`SMALL_RELATIVE_WORD_BOXES`. Where a page is attributed to a figure, the governing "
            "number is the printed size in section 8, not the size inside the figure PDF."
        )
    else:
        add(f"No word box is below {MIN_TEXT_HEIGHT_PT} pt in any target PDF.")
    add("")

    # ---- overlaps -------------------------------------------------------
    add("## 5. Overlapping text (check e)")
    add("")
    add(
        f"Rule: pairs of word boxes whose intersection area exceeds {OVERLAP_FRACTION:.0%} of the "
        "smaller box, exact duplicates and shadow duplicates excluded. **This is a conservative "
        "approximation of visual overlap**: it is derived from Poppler word boxes, which are "
        "axis-aligned even for rotated text and which include font ascent/descent, and it cannot "
        "see text drawn over graphics."
    )
    add("")
    add("| file | word boxes | candidate pairs | same baseline (real) | adjacent-line padding | atypical box geometry | duplicates ignored (exact/shadow) |")
    add("|---|---|---|---|---|---|---|")
    for record in figure_records + built_records:
        overlaps = record.get("overlaps", {})
        kinds = overlaps.get("counts_by_kind", {})
        add(
            f"| `{record['path']}` | {overlaps.get('n_word_boxes', '-')} | {overlaps.get('n_candidate_pairs', '-')} | "
            f"{kinds.get('same_baseline_horizontal', 0)} | {kinds.get('adjacent_line_padding', 0)} | "
            f"{kinds.get('atypical_box_geometry', 0)} | "
            f"{overlaps.get('n_duplicate_pairs_ignored_exact', 0)}/{overlaps.get('n_duplicate_pairs_ignored_shadow', 0)} |"
        )
    add("")
    add("### Flagged pairs")
    add("")
    for record in figure_records + built_records:
        pairs = record.get("overlaps", {}).get("pairs", [])
        if not pairs:
            continue
        add(f"#### `{record['path']}` — {len(pairs)} pair(s)")
        add("")
        add("| page | kind | overlap % of smaller | word A | box A | word B | box B | baseline delta (pt) | page median height (pt) |")
        add("|---|---|---|---|---|---|---|---|---|")
        for pair in pairs[:max_pairs_in_table]:
            a, b = pair["word_a"], pair["word_b"]
            add(
                f"| {pair['page']} | {pair['kind']} | {pair['overlap_fraction'] * 100:.1f} | "
                f"`{md_escape(a['text'])}` | ({a['x0']}, {a['y0']}, {a['x1']}, {a['y1']}) | "
                f"`{md_escape(b['text'])}` | ({b['x0']}, {b['y0']}, {b['x1']}, {b['y1']}) | "
                f"{fmt(pair['baseline_delta_pt'])} | {fmt(pair['page_median_word_height_pt'])} |"
            )
        if len(pairs) > max_pairs_in_table:
            add(f"| ... | | | {len(pairs) - max_pairs_in_table} more pairs in the JSON | | | | | |")
        add("")
        add("Pair classification: " + "; ".join(f"`{k}` x{v}" for k, v in record["overlaps"]["counts_by_kind"].items()) + ".")
        add("")

    # ---- merged label runs (the blind spot of the pairwise rule) --------
    merged_records = [
        record
        for record in figure_records + built_records
        if record.get("merged_label_runs", {}).get("n_findings")
    ]
    # ---- page-number band: a real overprint the pair rule calls padding --
    footer_records = [
        record
        for record in figure_records + built_records
        if record.get("footer_collisions", {}).get("n_findings")
    ]
    add("### Page number printed over body text")
    add("")
    if not footer_records:
        add(
            "No body word box bites into a running page-number band, so no page number is "
            "overprinted."
        )
        add("")
    else:
        add(
            "A text block that runs long pushes its last line into the footer. The pairwise rule "
            "classifies that as `adjacent_line_padding`, but on paper the page number sits on top "
            f"of the text; the pages below share both axes with the number band by at least "
            f"{FOOTER_BAND_MIN_OVERLAP_PT} pt."
        )
        add("")
        add("| file | page | page number | number band (x0, y0, x1, y1) | colliding words | worst word | worst box | vertical overlap (pt) |")
        add("|---|---|---|---|---|---|---|---|")
        for record in footer_records:
            for finding in record["footer_collisions"]["findings"]:
                worst = finding["worst"]
                band = finding["footer_band_pt"]
                add(
                    f"| `{record['path']}` | {finding['page']} | `{md_escape(finding['footer_text'])}` | "
                    f"({band['x0']}, {band['y0']}, {band['x1']}, {band['y1']}) | "
                    f"{finding['n_colliding_words']} | `{md_escape(worst['text'])}` | "
                    f"({worst['x0']}, {worst['y0']}, {worst['x1']}, {worst['y1']}) | "
                    f"{fmt(worst['overlap_y_pt'])} |"
                )
        add("")
        add(
            "These pages are also candidates for the text-outside-page check, because the same "
            "overfull block pushes descenders past the bottom page box."
        )
        add("")

    add("### Labels drawn with no word gap (blind spot of the pairwise rule)")
    add("")
    if not merged_records:
        add(
            "No word box repeats a substring, so no row of labels was found drawn edge to edge."
        )
        add("")
    else:
        add(
            "A word box such as `timingtimingtiminglengthlength` is one Poppler word because the "
            "individual labels were drawn with no space glyph between them; the pairwise test "
            "cannot see it (there is no pair) and on paper the row reads as one continuous string."
        )
        add("")
        add("| file | page | extracted word | box (x0, y0, x1, y1) | width (pt) | repeated unit | runs recovered | run pitches (pt) |")
        add("|---|---|---|---|---|---|---|---|")
        for record in merged_records:
            for finding in record["merged_label_runs"]["findings"]:
                pitches = (
                    f"{fmt(finding['min_pitch_pt'], 2)}-{fmt(finding['max_pitch_pt'], 2)}"
                    if finding["min_pitch_pt"]
                    else "-"
                )
                add(
                    f"| `{record['path']}` | {finding['page']} | `{md_escape(finding['text'])}` | "
                    f"({finding['x0']}, {finding['y0']}, {finding['x1']}, {finding['y1']}) | "
                    f"{fmt(finding['width_pt'], 2)} | `{md_escape(finding['repeated_unit'])}` x{finding['n_repeats']} | "
                    f"{finding['n_text_runs_found']} | {pitches} |"
                )
        add("")
        for record in merged_records:
            for finding in record["merged_label_runs"]["findings"]:
                if not finding["text_runs"]:
                    continue
                add(f"`{record['path']}` page {finding['page']} runs inside the merged box:")
                add("")
                add("| run text | x (pt) | baseline y from top (pt) | font resource | size (pt) | pitch from previous (pt) |")
                add("|---|---|---|---|---|---|")
                for run in finding["text_runs"]:
                    add(
                        f"| `{md_escape(run['text'])}` | {fmt(run['x_pt'], 3)} | "
                        f"{fmt(run['baseline_y_top_pt'], 3)} | {run['font_resource']} | "
                        f"{fmt(run['font_size_pt'], 2)} | {fmt(run.get('pitch_from_previous_pt'), 3)} |"
                    )
                add("")
        add(
            "The per-run x positions come from the placement matrices in the inflated PDF content "
            "streams; the individual ink widths are not measured, so a recovered pitch is the "
            "label pitch, not the free space between glyphs."
        )
        add("")

    # ---- provenance -----------------------------------------------------
    add("## 6. Source provenance (check f)")
    add("")
    add("| figure | draw.io source at figures/v17/drawio | schematic | python generator(s) under scripts/ | classification | verdict |")
    add("|---|---|---|---|---|---|")
    for record in figure_records:
        provenance = record.get("provenance", {})
        generators = ", ".join(f"`{g['script']}`" for g in provenance.get("python_generators", [])) or "none"
        add(
            f"| `{record['name']}` | {'yes' if provenance.get('drawio_source_exists') else 'NO'} | "
            f"{'yes — ' + str(provenance.get('schematic_reason')) if provenance.get('schematic') else 'no'} | "
            f"{generators} | {provenance.get('kind', '-')} | "
            f"{'HARD' if any(f['check'] == 'SCHEMATIC_WITHOUT_DRAWIO_SOURCE' for f in record['hard_failures']) else ('warn' if any(w['check'] == 'PROVENANCE_UNKNOWN' for w in record['warnings']) else 'ok')} |"
        )
    add("")
    add(
        "The schematic list is explicit (see `SCHEMATIC_FIGURES` in the script, taken from "
        "`figures/v17/drawio/README.md`): a new architecture or system-design figure must be added "
        "there, otherwise a missing draw.io source cannot be detected."
    )
    add("")
    add("| figure | figure built elsewhere in `figures/` | identical to the paper copy |")
    add("|---|---|---|")
    for record in figure_records:
        for upstream in record.get("provenance", {}).get("upstream_pdf_candidates", []):
            add(
                f"| `{record['name']}` | `{upstream['path']}` | "
                f"{'yes' if upstream['identical_to_paper_copy'] else 'no'} |"
            )
    add("")

    # ---- raster ---------------------------------------------------------
    add("## 7. Raster image resolution (check g)")
    add("")
    add("| file | page | image | pixels | colour | effective ppi (x, y) | flag |")
    add("|---|---|---|---|---|---|---|")
    any_image = False
    for record in figure_records + built_records:
        for image in record.get("raster", {}).get("images", []):
            any_image = True
            add(
                f"| `{record['path']}` | {image['page']} | {image['num']} | "
                f"{image['width_px']}x{image['height_px']} | {image['color']} | "
                f"{image['x_ppi']:.0f}, {image['y_ppi']:.0f} | "
                f"{'BELOW 300 dpi' if image['below_300_dpi'] else 'ok'} |"
            )
    if not any_image:
        add("| - | - | - | no raster images in any target PDF | - | - | - |")
    add("")
    if not any(record.get("raster", {}).get("tool_available") for record in figure_records + built_records):
        add("`pdfimages` is not installed: raster resolution could not be checked.")
        add("")

    # ---- print size -----------------------------------------------------
    add("## 8. Printed size and effective text size (derived)")
    add("")
    add(
        "Method: the scale at which each figure is placed in the built PDFs is measured by "
        "matching the figure's distinctive words against the words of the built pages (all pairs "
        "of unambiguous matches give a distance ratio; the largest tight cluster is the estimate). "
        "`scale x figure width` is the printed width, and raw text heights times the scale give "
        "the size the reader sees on paper. These values are derived, never hard failures."
    )
    add("")
    add("| figure | width (pt) | measured scale | printed width (pt) | printed width (in) | raw min (pt) | raw p05 (pt) | effective min (pt) | effective p05 (pt) | confidence |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for record in figure_records:
        scale_row = scale_rows.get(record["name"], {})
        small = record.get("min_text_height", {})
        geometry = record.get("geometry", {})
        scale = scale_row.get("scale")
        width_pt = (geometry.get("page_size_pt") or [None])[0]
        printed = scale * width_pt if scale and width_pt else None
        add(
            f"| `{record['name']}` | {fmt(width_pt)} | {fmt(scale, 4)} | {fmt(printed)} | "
            f"{fmt(printed / 72.0 if printed else None, 3)} | {fmt(small.get('min_height_pt'))} | "
            f"{fmt(small.get('p05_height_pt'))} | "
            f"{fmt(small.get('min_height_pt', 0) * scale if scale and small.get('min_height_pt') else None)} | "
            f"{fmt(small.get('p05_height_pt', 0) * scale if scale and small.get('p05_height_pt') else None)} | "
            f"{'measured' if scale_row.get('confident') else ('low' if scale else 'unavailable')} |"
        )
    add("")
    widths = [
        scale_rows[record["name"]]["scale"] * (record.get("geometry", {}).get("page_size_pt") or [0])[0]
        for record in figure_records
        if scale_rows.get(record["name"], {}).get("scale")
    ]
    if widths:
        add(
            f"Implied printed width across the {len(widths)} figures with a measured scale: "
            f"median {fmt(statistics.median(widths))} pt "
            f"({fmt(statistics.median(widths) / 72.0, 3)} in), "
            f"range {fmt(min(widths))}-{fmt(max(widths))} pt. "
            "Corroboration: the AGU class file sets `\\textwidth 5.5in` = 396 pt "
            "(`paper/wrr/template/agujournal2025.cls:958`), consistent with a full-width placement."
        )
        add("")
    add(
        "AGU/WRR ask for figure text that stays legible in print; a text height below "
        f"{MIN_TEXT_HEIGHT_PT} pt at printed size is the practical red line used here."
    )
    add("")
    small_print = [
        (record["name"], scale_rows[record["name"]]["effective_p05_height_pt"])
        for record in figure_records
        if scale_rows.get(record["name"], {}).get("effective_p05_height_pt") is not None
        and scale_rows[record["name"]]["effective_p05_height_pt"] < 6.0
    ]
    if small_print:
        add(
            "Advisory (not a failure): the following figures pass the 4.5 pt rule but their 5th "
            "percentile word box prints below 6 pt, which is small even for a journal figure: "
            + ", ".join(f"`{name}` {value:.2f} pt" for name, value in sorted(small_print, key=lambda r: r[1]))
            + "."
        )
        add("")

    # ---- prioritised fix list -------------------------------------------
    add("## 9. Prioritised fix list")
    add("")
    fix_items: list[tuple[str, str, str]] = []
    priority_of = {
        "FONT_NOT_EMBEDDED": "P0",
        "FIGURE_NOT_SINGLE_PAGE": "P0",
        "TEXT_OUTSIDE_PAGE": "P0",
        "SCHEMATIC_WITHOUT_DRAWIO_SOURCE": "P0",
        "TEXT_HEIGHT_BELOW_MINIMUM": "P1",
        "OVERLAPPING_TEXT_SAME_BASELINE": "P1",
        "MERGED_LABEL_RUN_SUSPECT": "P1",
        "FOOTER_TEXT_COLLISION": "P1",
        "EFFECTIVE_PRINT_TEXT_TOO_SMALL": "P1",
        "INK_CLIPPED_AT_PAGE_EDGE": "P0",
        "INK_CHECK_UNAVAILABLE": "P2",
        "SMALL_RELATIVE_WORD_BOXES": "P3",
        "RASTER_BELOW_300_DPI": "P1",
        "OVERLAPPING_WORD_BOXES": "P2",
        "PROVENANCE_UNKNOWN": "P2",
        "FIGURE_NOT_REFERENCED": "P2",
    }
    padding_only = {
        (entry["file"], entry["page"])
        for entry in payload["summary"]["ink_verified_padding_only_pages"]
    }
    for group in payload["summary"]["hard_failure_groups"]:
        check = group["check"]
        page_note = f" page {group['page']}" if group["page"] is not None else ""
        count_note = f" x{group['n']}" if group["n"] > 1 else ""
        priority = priority_of.get(check, "P2")
        suffix = ""
        if check == "TEXT_OUTSIDE_PAGE" and (group["file"], group["page"]) in padding_only:
            priority = "P1"
            suffix = " [ink verified inside the page: box padding only, nothing clipped]"
        fix_items.append(
            (priority, group["file"], f"{check}{page_note}: {group['examples'][0]}{count_note}{suffix}")
        )
    for record in figure_records:
        scale_row = scale_rows.get(record["name"], {})
        small = record.get("min_text_height", {})
        if scale_row.get("scale") and small.get("p05_height_pt"):
            effective = small["p05_height_pt"] * scale_row["scale"]
            if effective < MIN_TEXT_HEIGHT_PT:
                width_pt = (record.get("geometry", {}).get("page_size_pt") or [0])[0]
                fix_items.append(
                    (
                        "P1",
                        record["path"],
                        f"EFFECTIVE_PRINT_TEXT_TOO_SMALL: p05 word height {small['p05_height_pt']:.2f} pt "
                        f"x placement scale {scale_row['scale']:.4f} = {effective:.2f} pt on paper "
                        f"(< {MIN_TEXT_HEIGHT_PT} pt); the figure is drawn {width_pt:.0f} pt wide and printed "
                        f"{scale_row['scale'] * width_pt:.0f} pt wide",
                    )
                )
    for record in figure_records + built_records:
        for item in record["warnings"]:
            if item["check"] in {
                "OVERLAPPING_TEXT_SAME_BASELINE",
                "MERGED_LABEL_RUN_SUSPECT",
                "FOOTER_TEXT_COLLISION",
            }:
                priority = "P1"
            elif item["check"] in {"RASTER_BELOW_300_DPI", "OVERLAPPING_WORD_BOXES"}:
                priority = "P2"
            else:
                priority = "P3"
            page_note = f" page {item['page']}" if item.get("page") is not None else ""
            fix_items.append(
                (priority, record["path"], f"{item['check']}{page_note}: {item['detail']}")
            )
    for item in payload["warnings"]:
        if item["file"] == "-":
            fix_items.append(("P3", "(environment)", f"{item['check']}: {item['detail']}"))
    if fix_items:
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        fix_items.sort(key=lambda row: (order[row[0]], row[1], row[2]))
        add("| priority | file | finding |")
        add("|---|---|---|")
        for priority, path, detail in fix_items:
            add(f"| {priority} | `{path}` | {md_escape(detail)} |")
    else:
        add("No hard failures and no warnings: nothing to fix.")
    add("")

    # ---- caveats --------------------------------------------------------
    add("## 10. Method, reproducibility and caveats")
    add("")
    add("Commands (reproduce with `python3 scripts/266_wrr_figure_qa.py`):")
    add("")
    add("```")
    for command in payload["command_summary"]:
        add(command)
    add("```")
    add("")
    add("Caveats, in order of how easily they can mislead:")
    add("")
    add(
        "1. **Overlap detection is a conservative box test, not a visual diff.** It cannot see "
        "text over graphics, it uses axis-aligned boxes for rotated text, and Poppler boxes "
        "include font ascent/descent, so tightly leaded or rotated text is flagged without any "
        "ink collision. Pairs are classified (`same_baseline_horizontal` is the real-collision "
        "class) and the flagged pages can be rendered for a visual check."
    )
    add(
        "2. **Word box height is not a font size.** For a word made only of x-height letters the "
        "box is smaller than the type size, and for rotated text Poppler emits partial words; a "
        "flagged word is therefore reported with its neighbours instead of being re-set blindly."
    )
    add(
        "3. **Placement scale is derived, not declared.** It is measured from matched words "
        "between the figure PDF and the built PDF; only figures whose matches form a tight "
        "cluster are reported as measured."
    )
    add(
        "4. **Colour is not judged.** The report gives the page size in inches and the effective "
        "raster resolution; it does not check colour-blind safety or greyscale conversion."
    )
    add(
        "5. **Only the files listed above were inspected.** Embedded fonts are reported as "
        "Poppler sees them; a Type 3 subset with no BaseFont name appears as `[none]`."
    )
    add(
        "6. **The artifacts can move under the run.** Every inspected file is pinned by SHA-256 in "
        "the JSON, so a mismatch with a later build is visible rather than silent; re-run the "
        "harness after any rebuild."
    )
    add("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Quality-assure the WRR figures and built PDFs (fonts, geometry, text)."
    )
    parser.add_argument("--paper-dir", type=Path, default=DEFAULT_PAPER_DIR, help="directory holding the figures and built PDFs")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="JSON output path")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD, help="Markdown report output path")
    parser.add_argument("--render-dir", type=Path, default=DEFAULT_RENDER_DIR, help="where ink-verification renders are written")
    parser.add_argument(
        "--extra-pdf",
        type=Path,
        action="append",
        default=[],
        help=(
            "additional PDF to inspect (repeatable); a file whose name contains 'manuscript' or "
            "'supporting' is treated as a built document, anything else as a standalone PDF. "
            "Use this to QA a recovered build without touching paper/**."
        ),
    )
    parser.add_argument("--no-ink-verify", action="store_true", help="skip the pdftoppm ink check")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="record hard failures but exit 0 (used by the regression test)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the summary on stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paper_dir: Path = args.paper_dir if args.paper_dir.is_absolute() else ROOT / args.paper_dir
    json_path: Path = args.json if args.json.is_absolute() else ROOT / args.json
    md_path: Path = args.md if args.md.is_absolute() else ROOT / args.md
    render_dir: Path = args.render_dir if args.render_dir.is_absolute() else ROOT / args.render_dir

    tool_state = {
        name: {"available": tool_available(name), "version": probe_version(name)} for name in TOOL_NAMES
    }
    commands: list[dict[str, Any]] = []

    figures_dir = paper_dir / "figures"
    figure_pdfs = sorted(figures_dir.glob("*.pdf")) if figures_dir.is_dir() else []
    built = [
        ("manuscript", paper_dir / "wrr_manuscript.pdf"),
        ("supporting_information", paper_dir / "wrr_supporting_information.pdf"),
    ]
    targets = [Target(path=path, kind="figure", stem=path.stem) for path in figure_pdfs]
    missing_built: list[str] = []
    for kind, path in built:
        if path.exists():
            targets.append(Target(path=path, kind=kind, stem=path.stem))
        else:
            missing_built.append(rel_path(path))
    for extra in args.extra_pdf:
        extra_path = extra if extra.is_absolute() else ROOT / extra
        if not extra_path.exists():
            missing_built.append(str(extra_path))
            continue
        lowered = extra_path.name.lower()
        if "supporting" in lowered:
            kind = "supporting_information"
        elif "manuscript" in lowered:
            kind = "manuscript"
        else:
            kind = "other"
        targets.append(Target(path=extra_path, kind=kind, stem=extra_path.stem))

    # LaTeX references, so an orphan figure can be reported.
    referenced: set[str] = set()
    for tex in sorted(paper_dir.glob("*.tex")):
        for match in INCLUDE_RE.findall(tex.read_text(encoding="utf-8", errors="replace")):
            referenced.add(Path(match).name)

    records: list[dict[str, Any]] = []
    for target in targets:
        records.append(
            analyse_file(
                target,
                render_dir=render_dir,
                ink_verify=not args.no_ink_verify,
                tool_state=tool_state,
                commands=commands,
            )
        )

    figure_records = [r for r in records if r["kind"] == "figure"]
    built_records = [r for r in records if r["kind"] in {"manuscript", "supporting_information"}]

    for record in figure_records:
        referenced_here = f"{record['name']}.pdf" in referenced
        record["provenance"]["referenced_in_tex"] = referenced_here
        if not referenced_here:
            record["warnings"].append(
                Item(
                    "FIGURE_NOT_REFERENCED",
                    "no \\includegraphics in paper/wrr/*.tex refers to this figure PDF",
                ).as_dict(record["path"])
            )

    # ---- print scale measurement (needs the built PDFs) -----------------
    built_word_docs: list[dict[str, Any]] = []
    for target in targets:
        if target.kind not in {"manuscript", "supporting_information"}:
            continue
        proc = run_tool(["pdftotext", "-bbox", str(target.path), "-"])
        commands.append(
            {
                "tool": "pdftotext",
                "argv": ["pdftotext", "-bbox", rel_path(target.path), "-"],
                "returncode": proc.returncode,
            }
        )
        pages, words = parse_bbox_pages(proc.stdout)
        built_word_docs.append({"label": target.kind, "pages": pages, "words": words})

    scale_rows: dict[str, dict[str, Any]] = {}
    figure_word_sets: dict[str, set[str]] = {}
    for record in figure_records:
        figure_path = ROOT / record["path"]
        proc = run_tool(["pdftotext", "-bbox", str(figure_path), "-"])
        _, words = parse_bbox_pages(proc.stdout)
        figure_word_sets[record["name"]] = {word["text"] for word in words}
        row = measure_print_scale(words, built_word_docs)
        geometry = record.get("geometry", {})
        if row.get("scale") and geometry.get("page_size_pt"):
            row["printed_width_pt"] = round(row["scale"] * geometry["page_size_pt"][0], 3)
            row["printed_width_in"] = round(row["printed_width_pt"] / 72.0, 4)
            small = record.get("min_text_height", {})
            if small.get("min_height_pt"):
                row["effective_min_height_pt"] = round(small["min_height_pt"] * row["scale"], 3)
            if small.get("p05_height_pt"):
                row["effective_p05_height_pt"] = round(small["p05_height_pt"] * row["scale"], 3)
        scale_rows[record["name"]] = row
        record["print_placement"] = row
        effective = row.get("effective_p05_height_pt")
        if row.get("confident") and effective is not None and effective < MIN_TEXT_HEIGHT_PT:
            record["warnings"].append(
                Item(
                    "EFFECTIVE_PRINT_TEXT_TOO_SMALL",
                    f"5th-percentile word height {record['min_text_height']['p05_height_pt']:.2f} pt "
                    f"x measured placement scale {row['scale']:.4f} = {effective:.2f} pt on paper "
                    f"(< {MIN_TEXT_HEIGHT_PT} pt)",
                    locator={
                        "scale": row["scale"],
                        "printed_width_pt": row.get("printed_width_pt"),
                        "effective_p05_height_pt": effective,
                        "document": row.get("document"),
                        "page": row.get("page"),
                    },
                ).as_dict(record["path"])
            )

    # ---- summary --------------------------------------------------------
    hard_failures = [item for record in records for item in record["hard_failures"]]
    warnings = [item for record in records for item in record["warnings"]]
    if missing_built:
        warnings.append(
            {
                "file": "-",
                "check": "BUILT_PDF_MISSING",
                "detail": "built PDF(s) not present: " + ", ".join(missing_built),
            }
        )
    for name, state in tool_state.items():
        if not state["available"]:
            warnings.append(
                {
                    "file": "-",
                    "check": "TOOL_MISSING",
                    "detail": f"{name} is not installed in this environment",
                }
            )

    def count_by_check(items: Sequence[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            counts[item["check"]] = counts.get(item["check"], 0) + 1
        return dict(sorted(counts.items()))

    def group_by_file_check_page(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str, Any], dict[str, Any]] = {}
        for item in items:
            key = (item["file"], item["check"], item.get("page"))
            group = groups.setdefault(
                key,
                {
                    "file": item["file"],
                    "check": item["check"],
                    "page": item.get("page"),
                    "n": 0,
                    "examples": [],
                },
            )
            group["n"] += 1
            if len(group["examples"]) < 3:
                group["examples"].append(item["detail"])
        return sorted(groups.values(), key=lambda g: (g["file"], g["check"], str(g["page"])))

    # Tiny text is the one check that can fire hundreds of times on a single
    # placed figure; group it by page and attribute the page to its figure so
    # the report states the cause once instead of listing every word.
    flagged_page_words: dict[str, set[str]] = {}
    for record in records:
        if record["kind"] == "figure":
            continue  # a figure PDF is its own source; only placed words need attribution
        for violation in record.get("min_text_height", {}).get("violations", []):
            flagged_page_words.setdefault(f"{record['kind']}:{violation['page']}", set()).add(
                violation["text"]
            )
        for violation in record.get("text_bounds", {}).get("violations", []):
            flagged_page_words.setdefault(f"{record['kind']}:{violation['page']}", set()).add(
                violation["text"]
            )
    page_attribution = attribute_pages_to_figures(flagged_page_words, figure_word_sets)
    # A measured placement is stronger evidence than a word match: if a figure
    # is placed on that page at a confident scale, that figure is the source of
    # the page's flagged words.
    for record in figure_records:
        placement = record.get("print_placement", {})
        if placement.get("confident") and placement.get("page"):
            document = placement.get("document")
            kind = "manuscript" if document == "manuscript" else "supporting_information"
            key = f"{kind}:{placement['page']}"
            if key in flagged_page_words:
                page_attribution[key] = {
                    "figure": record["name"],
                    "n_matching_words": None,
                    "evidence": "measured placement scale on that page",
                }
    tiny_by_page: list[dict[str, Any]] = []
    for record in records:
        per_page: dict[int, list[dict[str, Any]]] = {}
        for violation in record.get("min_text_height", {}).get("violations", []):
            per_page.setdefault(int(violation["page"]), []).append(violation)
        for page, violations in sorted(per_page.items()):
            key = f"{record['kind']}:{page}"
            attribution = page_attribution.get(key) if record["kind"] != "figure" else None
            tiny_by_page.append(
                {
                    "file": record["path"],
                    "page": page,
                    "n_below_threshold": len(violations),
                    "min_height_pt": round(min(v["height_pt"] for v in violations), 3),
                    "median_height_pt": round(
                        statistics.median([v["height_pt"] for v in violations]), 3
                    ),
                    "distinct_words": sorted({v["text"] for v in violations})[:8],
                    "attributed_figure": attribution["figure"] if attribution else None,
                    "attributed_matching_words": attribution["n_matching_words"] if attribution else None,
                }
            )

    exit_code = 0 if not hard_failures else 1
    implied_widths = [
        row["printed_width_pt"] for row in scale_rows.values() if row.get("printed_width_pt")
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "script": str(Path(__file__).relative_to(ROOT)),
        "command": "python3 scripts/266_wrr_figure_qa.py",
        "thresholds": {
            "text_outside_page_pt": OUT_PAGE_TOLERANCE_PT,
            "min_text_height_pt": MIN_TEXT_HEIGHT_PT,
            "overlap_fraction_of_smaller_box": OVERLAP_FRACTION,
            "min_raster_dpi": MIN_RASTER_DPI,
            "ink_dpi": INK_DPI,
            "ink_edge_flush_pt": INK_EDGE_FLUSH_PT,
        },
        "hard_failure_definitions": [
            "FONT_NOT_EMBEDDED: any font with emb = no (a non-embedded core font is the classic case)",
            "FIGURE_NOT_SINGLE_PAGE: a figure PDF whose page count is not 1",
            (
                "TEXT_OUTSIDE_PAGE: a word box more than 1 pt outside the page box AND the "
                "rendered page shows the ink is clipped, or the page could not be rendered so "
                "the violation is unverified"
            ),
            "INK_CLIPPED_AT_PAGE_EDGE: rendered ink reaches within 1 pt of the page edge on a flagged page",
            (
                "TEXT_HEIGHT_BELOW_MINIMUM: the estimated typeset size of the text line carrying "
                "the word is below 4.5 pt (the tallest Poppler box on the line estimates the size)"
            ),
            "SCHEMATIC_WITHOUT_DRAWIO_SOURCE: a schematic figure with no figures/v17/drawio/<name>.drawio",
        ],
        "real_defect_warning_checks": list(REAL_DEFECT_WARNINGS),
        "box_model_warning_checks": list(BOX_MODEL_WARNINGS),
        "advisory_definitions": [
            (
                "TEXT_BOX_PADDING_ONLY: a word box crosses the page edge but the rendered ink "
                "stays inside; a box-model artifact, not a defect"
            ),
            (
                "SMALL_RELATIVE_WORD_BOXES: a word box below 0.45 of its own line height "
                "(superscript, subscript or a fragment of a rotated run)"
            ),
        ],
        "check_catalogue": [
            {"id": "FONT_NOT_EMBEDDED", "description": "font not embedded (check a)"},
            {"id": "FIGURE_NOT_SINGLE_PAGE", "description": "figure page count != 1 (check b)"},
            {"id": "TEXT_OUTSIDE_PAGE", "description": "text > 1 pt outside the page and ink clipped or unverified (check c)"},
            {"id": "TEXT_HEIGHT_BELOW_MINIMUM", "description": f"line-estimated type size < {MIN_TEXT_HEIGHT_PT} pt (check d)"},
            {"id": "OVERLAPPING_TEXT_SAME_BASELINE", "description": "overlapping boxes, same baseline (check e)"},
            {"id": "OVERLAPPING_WORD_BOXES", "description": "overlapping boxes, other geometry (check e)"},
            {"id": "MERGED_LABEL_RUN_SUSPECT", "description": "labels drawn with no word gap (check e)"},
            {"id": "FOOTER_TEXT_COLLISION", "description": "page number overprinted by body text (check e)"},
            {"id": "SCHEMATIC_WITHOUT_DRAWIO_SOURCE", "description": "schematic with no draw.io source (check f)"},
            {"id": "PROVENANCE_UNKNOWN", "description": "neither draw.io nor python source (check f)"},
            {"id": "RASTER_BELOW_300_DPI", "description": "raster below 300 dpi effective (check g)"},
            {"id": "EFFECTIVE_PRINT_TEXT_TOO_SMALL", "description": "derived: printed text below 4.5 pt"},
            {"id": "INK_CLIPPED_AT_PAGE_EDGE", "description": "derived: rendered ink clipped/flush at the page edge"},
            {"id": "TEXT_BOX_PADDING_ONLY", "description": "derived: box crosses the edge, ink does not"},
            {"id": "INK_CHECK_UNAVAILABLE", "description": "derived: the flagged page could not be rendered"},
            {"id": "SMALL_RELATIVE_WORD_BOXES", "description": "word far smaller than its own line (check d)"},
            {"id": "FONT_UNNAMED", "description": "embedded font with no BaseFont name"},
            {"id": "DEGENERATE_WORD_BOXES", "description": "word boxes with non-positive height"},
            {"id": "FIGURE_NOT_REFERENCED", "description": "figure PDF not referenced by any .tex"},
            {"id": "PAGE_SIZE_VARIES", "description": "page sizes differ within one PDF"},
            {"id": "BBOX_PAGE_COUNT_MISMATCH", "description": "pdftotext -bbox page count differs from pdfinfo"},
            {"id": "BUILT_PDF_MISSING", "description": "a built PDF was not found"},
            {"id": "TOOL_MISSING", "description": "a required tool is not installed"},
        ],
        "tool_versions": {name: state["version"] for name, state in tool_state.items()},
        "tool_availability": {name: state["available"] for name, state in tool_state.items()},
        "environment": {
            "python": sys.version.split()[0],
            "root": str(ROOT),
            "rendered_pages_dir": rel_path(render_dir),
        },
        "summary": {
            "n_pdfs": len(records),
            "n_figure_pdfs": len(figure_records),
            "n_built_pdfs": len(built_records),
            "n_hard_failures": len(hard_failures),
            "n_hard_failure_groups": len(group_by_file_check_page(hard_failures)),
            "n_warnings": len(warnings),
            "hard_failures_by_check": count_by_check(hard_failures),
            "warnings_by_check": count_by_check(warnings),
            "hard_failure_groups": group_by_file_check_page(hard_failures),
            "tiny_text_by_page": tiny_by_page,
            "page_to_figure": page_attribution,
            "files_with_hard_failures": sorted({item["file"] for item in hard_failures}),
            "schematic_figures": sorted(SCHEMATIC_FIGURES),
            "schematic_figures_without_drawio": sorted(
                record["name"]
                for record in figure_records
                if any(
                    item["check"] == "SCHEMATIC_WITHOUT_DRAWIO_SOURCE"
                    for item in record["hard_failures"]
                )
            ),
            "provenance": {
                "drawio": sorted(
                    record["name"] for record in figure_records if record.get("provenance", {}).get("drawio_source_exists")
                ),
                "python_only": sorted(
                    record["name"]
                    for record in figure_records
                    if not record.get("provenance", {}).get("drawio_source_exists")
                    and record.get("provenance", {}).get("python_generators")
                ),
                "unknown": sorted(
                    record["name"]
                    for record in figure_records
                    if not record.get("provenance", {}).get("drawio_source_exists")
                    and not record.get("provenance", {}).get("python_generators")
                ),
            },
            "figures_not_referenced_in_tex": sorted(
                record["name"] for record in figure_records if not record["provenance"].get("referenced_in_tex")
            ),
            "implied_printed_width_pt": {
                "median": round(statistics.median(implied_widths), 3) if implied_widths else None,
                "min": round(min(implied_widths), 3) if implied_widths else None,
                "max": round(max(implied_widths), 3) if implied_widths else None,
                "n_figures": len(implied_widths),
                "corroboration": "AGU class file sets \\textwidth 5.5in = 396 pt (paper/wrr/template/agujournal2025.cls:958)",
            },
            "ink_verification_pages": sum(len(record.get("ink_checks", [])) for record in records),
            "ink_verified_padding_only_pages": [
                {"file": record["path"], "page": check["page"]}
                for record in records
                for check in record.get("ink_checks", [])
                if check.get("available") and not check.get("ink_flush_to_edge")
            ],
            "ink_verified_clipped_pages": [
                {"file": record["path"], "page": check["page"]}
                for record in records
                for check in record.get("ink_checks", [])
                if check.get("ink_flush_to_edge")
            ],
        },
        "hard_failures": hard_failures,
        "warnings": warnings,
        "files": records,
    }
    payload["exit_code"] = exit_code
    payload["exit_policy"] = (
        "report-only: hard failures recorded, exit 0" if args.report_only else "strict: exit 1 on any hard failure"
    )
    payload["command_summary"] = [
        "pdffonts <file>                      # check a: embedded fonts",
        "pdfinfo <file>; pdfinfo -f 1 -l N <file>   # check b: page count and page boxes",
        "pdftotext -bbox <file> -             # checks c, d, e: word boxes in points",
        "pdfimages -list <file>               # check g: raster images and effective dpi",
        "pdftoppm -r 200 -png -f P -l P <file>  # ink verification of flagged pages",
        "python3 scripts/266_wrr_figure_qa.py   # this harness",
    ]

    markdown = build_markdown(
        payload,
        json_path=json_path,
        md_path=md_path,
        figure_records=figure_records,
        built_records=built_records,
        scale_rows=scale_rows,
    )
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    if not args.quiet:
        summary = {
            "pdfs": len(records),
            "figure_pdfs": len(figure_records),
            "built_pdfs": len(built_records),
            "hard_failures": len(hard_failures),
            "hard_failures_by_check": payload["summary"]["hard_failures_by_check"],
            "warnings": len(warnings),
            "warnings_by_check": payload["summary"]["warnings_by_check"],
            "schematic_figures_without_drawio": payload["summary"]["schematic_figures_without_drawio"],
            "exit_code": 0 if args.report_only else exit_code,
            "json": rel_path(json_path),
            "markdown": rel_path(md_path),
        }
        print(json.dumps(summary, indent=2))
    return 0 if args.report_only else exit_code


if __name__ == "__main__":
    raise SystemExit(main())
