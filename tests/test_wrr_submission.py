"""Checks a Water Resources Research desk editor makes before peer review.

A submission that fails any of these is returned without review, so they belong
in the test suite rather than in a checklist someone remembers to run.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper" / "wrr"
MANUSCRIPT = PAPER / "wrr_manuscript.tex"
TEMPLATE = PAPER / "template"

sys.path.insert(0, str(ROOT / "scripts"))


def build_report() -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "223_wrr_build.py"), "--skip-build"],
        capture_output=True,
        text=True,
    )
    report = json.loads((PAPER / "build_report.json").read_text())
    report["_returncode"] = result.returncode
    return report


def test_agu_limits_pass():
    report = build_report()
    assert not report["checks_failed"], report["checks_failed"]
    assert report["_returncode"] == 0


def test_three_key_points_within_the_character_limit():
    report = build_report()
    lengths = [c["chars"] for c in report["checks_passed"] if c["check"].startswith("key point")]
    assert len(lengths) == 3
    assert all(length <= 140 for length in lengths), lengths


def test_abstract_and_plain_language_summary_within_limits():
    report = build_report()
    by_check = {c["check"]: c for c in report["checks_passed"]}
    assert by_check["abstract length"]["words"] <= 250
    assert by_check["plain language summary length"]["words"] <= 200


def test_author_block_is_not_invented():
    """The repository must not put a name on a title page it cannot verify."""

    text = MANUSCRIPT.read_text(encoding="utf-8")
    assert "AFFILIATION PENDING AUTHOR CONFIRMATION" in text
    report = build_report()
    assert report["blocked_on_author_information"] is True
    assert report["submission_ready"] is False


def test_template_is_vendored_with_provenance():
    provenance = TEMPLATE / "PROVENANCE.md"
    assert provenance.exists()
    text = provenance.read_text(encoding="utf-8")
    assert "agujournal2025-latex-template" in text
    assert re.search(r"`[0-9a-f]{40}`", text), "the template commit is not recorded"
    for name in (
        "agujournal2025.cls",
        "wiley-macros.tex",
        "tweaklist-git-moderncv-fixed.sty",
        "agu-logo-large.pdf",
        "agu-logo-small.pdf",
    ):
        assert (TEMPLATE / name).exists(), name


def test_every_figure_referenced_is_included_and_present():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    referenced = set(re.findall(r"\\ref\{fig:([a-z]+)\}", text))
    defined = set(re.findall(r"\\label\{fig:([a-z]+)\}", text))
    assert referenced <= defined, sorted(referenced - defined)
    for path in re.findall(r"\\includegraphics\[[^\]]*\]\{(figures/[^}]+)\}", text):
        assert (PAPER / path).exists(), path


def test_built_pdfs_are_current():
    pdf = PAPER / "wrr_manuscript.pdf"
    si = PAPER / "wrr_supporting_information.pdf"
    if not pdf.exists():
        pytest.skip("submission not built; run make wrr")
    assert pdf.stat().st_mtime >= MANUSCRIPT.stat().st_mtime - 1, "run make wrr"
    assert si.exists() and si.stat().st_size > 20_000


def test_result_headings_state_conclusions():
    """A heading that names an analysis stage tells the reader nothing.

    Yang-style result headings answer what was established, not what was run.
    """

    text = MANUSCRIPT.read_text(encoding="utf-8")
    results = text.split("\\section{Results}")[1].split("\\section{Discussion}")[0]
    headings = [
        " ".join(h.split())
        for h in re.findall(r"\\sub(?:sub)?section\{((?:[^{}]|\n)*?)\}", results)
    ]
    # Four step headings plus their claim-titled sub-headings.
    assert len(headings) >= 8, headings
    banned = ("RQ", "Model validation", "Sensitivity analysis", "Ablation study")
    for heading in headings:
        assert not any(heading.startswith(b) for b in banned), heading
        # a conclusion needs a verb; a stage name usually has none
        assert len(heading.split()) >= 6, heading


def test_introduction_ends_in_linked_questions_not_a_contribution_list():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    intro = text.split("\\section{Introduction}")[1].split("\\section{Study system")[0]
    assert "\\begin{enumerate}" not in intro, "the introduction still carries a contribution list"
    assert "Three questions organise the paper" in intro
    assert intro.count("?") >= 3, intro.count("?")


def test_latex_compiles_without_errors():
    """A log with errors means the PDF is not what the source says."""

    for stem in ("wrr_manuscript", "wrr_manuscript_published", "wrr_supporting_information"):
        log = PAPER / f"{stem}.log"
        if not log.exists():
            pytest.skip("submission not built; run make wrr")
        errors = [line for line in log.read_text(errors="replace").splitlines() if line.startswith("!")]
        assert not errors, f"{stem}: {errors[:3]}"


def test_figures_are_rendered_at_page_aspect():
    """A 3.9:1 figure in a 5.5 inch column is an inch and a half tall."""

    if shutil.which("pdfinfo") is None:
        pytest.skip("pdfinfo not available")
    for path in sorted((PAPER / "figures").glob("*.pdf")):
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
        size = next(line for line in info.splitlines() if line.startswith("Page size:"))
        width, _, height, *_ = size.split(":", 1)[1].split()
        ratio = float(width) / float(height)
        assert ratio < 2.2, f"{path.name} is {ratio:.2f}:1; re-render with WRR_JOURNAL_FIGURES=1"


def test_figures_are_placed_in_the_text():
    """Figures belong beside the paragraph that cites them, not in a block."""

    text = MANUSCRIPT.read_text(encoding="utf-8")
    assert "%% ---- Figures ----" not in text, "figures are collected at the end"
    body, _, tail = text.partition("\\section*{Open Research Statement}")
    # Ten figures carry the argument; the remaining four are supporting
    # information, which is where a figure goes when it supports a claim the
    # main text does not have to make.
    assert body.count("\\begin{figure}") == 10, body.count("\\begin{figure}")
    assert "\\begin{figure}" not in tail
    assert "\\begin{figure}[htbp]" in body
    si = (PAPER / "wrr_supporting_information.tex").read_text(encoding="utf-8")
    # Six since 2026-10-12: the dense "problem frame" schematic moved from the
    # article (where a data-driven example figure now opens the paper) into the
    # supporting information as Figure S1.
    # Seven since 2026-10-12: the catchment-attribute figure moved to the SI.
    assert si.count("\\begin{figure}") == 7, si.count("\\begin{figure}")


def test_tables_fit_the_column():
    """Every table is a tabularx sized to the text width, with weights summing
    to its number of X columns; otherwise it under- or over-fills."""

    import re  # noqa: PLC0415

    text = MANUSCRIPT.read_text(encoding="utf-8")
    specs = re.findall(r"\\begin\{tabularx\}\{\\textwidth\}\{([^}]*(?:\}[^}]*)*?)\}\n", text)
    assert len(specs) >= 10, len(specs)
    for spec in specs:
        weights = [float(w) for w in re.findall(r"[YZ]\{([0-9.]+)\}", spec)]
        assert weights, spec
        assert abs(sum(weights) - len(weights)) < 0.02, (spec, sum(weights), len(weights))

def test_title_and_abstract_state_the_finding():
    """The title names a finding, not a study object, and the abstract carries
    the prevailing assumption, the gap and a number."""

    import re  # noqa: PLC0415

    text = MANUSCRIPT.read_text(encoding="utf-8")
    title = re.search(r"\\title\{(.*?)\}", text, re.S).group(1)
    lowered = " ".join(title.lower().split())
    for vague in ("a study of", "analysis of", "assessment of", "research on",
                  "investigation of", "towards ", "toward "):
        assert vague not in lowered, (vague, title)
    assert "not" in lowered or "," in lowered, title

    abstract = text.split("\\begin{abstract}")[1].split("\\end{abstract}")[0]
    assert re.search(r"\d", abstract), "the abstract carries no number"
    for word in ("position", "length", "support"):
        assert word in abstract.lower(), word
    for hype in ("groundbreaking", "unprecedented", "paradigm-shifting", "novel framework"):
        assert hype not in text.lower(), hype
    assert not re.search(r"\bremarkable\b", text, re.I), "remarkable"  # 'unremarkable' is fine
