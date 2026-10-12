#!/usr/bin/env python3
"""Typeset the v18 manuscript as a PDF.

The article is written in Markdown so it can be diffed, tested against the
artifacts and kept under version control; this builds the reading copy. Two
things need handling rather than passing through:

* the machine-readable headline-numbers block, which exists for the audit
  script and is not article content;
* the figure table, whose rows name files. Those become real figure
  environments so the PDF carries the plots rather than a list of paths.

XeLaTeX with DejaVu Serif, because the prose uses degree signs, Greek letters
and superscript exponents that a Latin-1 font silently drops.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "paper_archived" / "v18" / "manuscript.md"
OUTPUT = ROOT / "paper_archived" / "v18" / "manuscript.pdf"

PREAMBLE = r"""
\usepackage{graphicx}
\usepackage{float}
\usepackage[font=small,labelfont=bf,justification=justified,singlelinecheck=false]{caption}
\usepackage{microtype}
\setlength{\emergencystretch}{3em}
\renewcommand{\arraystretch}{1.15}
\setlength{\tabcolsep}{4pt}
\usepackage{etoolbox}
% Journal tables run wide; let them shrink rather than run into the margin.
\AtBeginEnvironment{longtable}{\footnotesize}
\AtBeginEnvironment{tabular}{\footnotesize}
\usepackage{sectsty}
\allsectionsfont{\sffamily}
"""


def strip_numbers_block(text: str) -> str:
    return re.sub(
        r"<!-- numbers:start -->.*?<!-- numbers:end -->\s*", "", text, flags=re.S
    )


def clean_caption(text: str) -> str:
    """Table-cell markdown into caption prose."""

    text = text.replace("|", " ")
    text = re.sub(r"`([^`]*)`", r"\\texttt{\1}", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*([^*]*)\*", r"\\emph{\1}", text)
    for char, replacement in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")):
        text = text.replace(char, replacement)
    return " ".join(text.split())


def figure_blocks(text: str) -> tuple[str, int]:
    """Replace the figure table with figure environments carrying the plots."""

    rows = re.findall(r"^\| (\d+|SI-\d+) \| `([^`]+)` \| (.*?) \|\s*$", text, re.M)
    if not rows:
        return text, 0

    blocks = []
    for number, path, caption in rows:
        target = ROOT / path
        if not target.exists():
            continue
        label = f"Figure {number}." if not number.startswith("SI") else f"Figure {number}."
        blocks.append(
            "```{=latex}\n"
            "\\begin{figure}[H]\n"
            "\\centering\n"
            f"\\includegraphics[width=\\linewidth,height=0.42\\textheight,keepaspectratio]{{{target}}}\n"
            f"\\caption*{{\\textbf{{{label}}} {clean_caption(caption)}}}\n"
            "\\end{figure}\n"
            "```\n"
        )

    table = re.search(
        r"^\| # \| file \| what it shows \|\n\|[-| ]+\|\n(?:^\|.*\|\n)+", text, re.M
    )
    if table is None:
        return text, 0
    return text[: table.start()] + "\n".join(blocks) + text[table.end() :], len(blocks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.output = args.output.resolve()

    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc is required")
    if shutil.which("xelatex") is None:
        raise SystemExit("xelatex is required")

    text = args.source.read_text(encoding="utf-8")
    text = strip_numbers_block(text)
    text, n_figures = figure_blocks(text)

    title = text.splitlines()[0].lstrip("# ").strip()
    body = "\n".join(text.splitlines()[1:]).lstrip("\n")

    scratch = args.output.parent / ".build"
    scratch.mkdir(parents=True, exist_ok=True)
    preamble = scratch / "preamble.tex"
    preamble.write_text(PREAMBLE, encoding="utf-8")
    prepared = scratch / "manuscript.md"
    prepared.write_text(body, encoding="utf-8")

    command = [
        "pandoc",
        str(prepared),
        "-f", "markdown+tex_math_single_backslash+pipe_tables+raw_attribute",
        "-t", "pdf",
        "--pdf-engine=xelatex",
        "-V", "documentclass=article",
        "-V", "classoption=11pt",
        "-V", "geometry:a4paper,margin=2.4cm",
        "-V", "mainfont=DejaVu Serif",
        "-V", "sansfont=DejaVu Sans",
        "-V", "monofont=DejaVu Sans Mono",
        "-V", "fontsize=10pt",
        "-V", "linestretch=1.08",
        "-V", "colorlinks=true",
        "-V", "linkcolor=black",
        "-V", "urlcolor=[HTML]{1C5CAB}",
        "-V", f"title={title}",
        "-V", "date=Draft of 2026-09-24",
        "--toc", "--toc-depth=2",
        "-H", str(preamble),
        "--resource-path", f"{ROOT}:{args.source.parent}",
        "-o", str(args.output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("pandoc failed")
    size = args.output.stat().st_size
    pages = subprocess.run(
        ["pdfinfo", str(args.output)], capture_output=True, text=True
    ).stdout
    page_count = next(
        (line.split()[-1] for line in pages.splitlines() if line.startswith("Pages:")), "?"
    )
    try:
        shown = args.output.relative_to(ROOT)
    except ValueError:
        shown = args.output
    print(f"{shown} — {page_count} pages, {n_figures} figures, {size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
