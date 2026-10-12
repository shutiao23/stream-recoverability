"""Regression tests for the WRR figure/PDF quality-assurance harness.

``scripts/266_wrr_figure_qa.py`` is run as a subprocess, exactly the way the
coordinator runs it, and the test asserts two things:

1. the harness itself works -- it exits 0 in ``--report-only`` mode (real
   findings must not turn the suite red), writes a parseable JSON report and a
   Markdown report, and every check is internally consistent with the
   measurements it claims to have made;
2. the exit-code contract holds -- a strict run exits 0 when the JSON records
   no hard failure and non-zero when it does.

The agreed contract (coordinator decision, 13:5x) is that a word box crossing a
page edge is a hard failure only when the rendered page shows the ink really is
clipped or the page cannot be rendered; a box-only overflow is the
``TEXT_BOX_PADDING_ONLY`` warning.  Check (d) estimates the typeset size per
text line and fails a word only when its own line estimate is below 4.5 pt,
reporting words far smaller than their line as ``SMALL_RELATIVE_WORD_BOXES``.
Fonts that are not embedded, a figure with more than one page, ink clipped at a
page edge and a schematic without a draw.io source stay hard failures.

The test also pins the read-only rule: the manuscript, a figure and the TeX
sources must be byte-identical before and after a harness run.

The tests skip cleanly when the built PDFs are absent (for example while the
manuscript is being rebuilt), because the harness is then not expected to find
anything to check.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "266_wrr_figure_qa.py"
PAPER_DIR = ROOT / "paper" / "wrr"
FIGURES_DIR = PAPER_DIR / "figures"
BUILT_PDFS = (
    PAPER_DIR / "wrr_manuscript.pdf",
    PAPER_DIR / "wrr_supporting_information.pdf",
)

REQUIRED_FILE_KEYS = {
    "path",
    "kind",
    "sha256",
    "fonts",
    "geometry",
    "text_bounds",
    "min_text_height",
    "overlaps",
    "raster",
    "hard_failures",
    "warnings",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _skip_reason() -> str | None:
    if not SCRIPT.is_file():
        return f"{SCRIPT} is missing"
    if not FIGURES_DIR.is_dir() or not list(FIGURES_DIR.glob("*.pdf")):
        return f"no figure PDFs under {FIGURES_DIR}"
    if not any(path.is_file() for path in BUILT_PDFS):
        return "the built PDFs are absent (nothing to quality-assure yet)"
    return None


def _run_harness(tmp_path: Path, *, extra: tuple[str, ...] = ()) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    json_path = tmp_path / "figure_qa.json"
    md_path = tmp_path / "figure_qa_report.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            str(json_path),
            "--md",
            str(md_path),
            "--render-dir",
            str(tmp_path / "render"),
            "--quiet",
            *extra,
        ],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=str(ROOT),
    )
    return proc, json_path, md_path


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    tmp_path = tmp_path_factory.mktemp("figure_qa")
    proc, json_path, md_path = _run_harness(tmp_path, extra=("--report-only",))
    assert proc.returncode == 0, (
        f"--report-only must exit 0 even with hard failures, got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert json_path.is_file(), "the harness wrote no JSON report"
    assert md_path.is_file(), "the harness wrote no Markdown report"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["_md_text"] = md_path.read_text(encoding="utf-8")
    payload["_tmp_path"] = str(tmp_path)
    payload["_proc"] = proc
    return payload


def test_report_shape(report: dict) -> None:
    """The JSON carries the documented top-level sections."""
    for key in (
        "schema_version",
        "generated_utc",
        "thresholds",
        "tool_versions",
        "tool_availability",
        "check_catalogue",
        "summary",
        "hard_failures",
        "warnings",
        "files",
    ):
        assert key in report, f"missing top-level key {key!r}"
    assert report["schema_version"]
    assert report["files"], "no file was analysed"
    for record in report["files"]:
        assert REQUIRED_FILE_KEYS <= set(record), f"{record.get('path')} lacks required keys"
        assert record["kind"] in {"figure", "manuscript", "supporting_information", "other"}
        assert len(record["sha256"]) == 64


def test_every_figure_pdf_is_analysed(report: dict) -> None:
    """One record per figure PDF, and none of them is silently dropped."""
    expected = sorted(path.name for path in FIGURES_DIR.glob("*.pdf"))
    analysed = sorted(
        Path(record["path"]).name for record in report["files"] if record["kind"] == "figure"
    )
    assert analysed == expected


def test_font_check_matches_raw_measurement(report: dict) -> None:
    """A FONT_NOT_EMBEDDED failure exists exactly when pdffonts reported emb=no."""
    for record in report["files"]:
        fonts = record["fonts"]
        assert fonts["n_non_embedded"] == len(fonts["non_embedded"])
        flagged = [
            failure for failure in record["hard_failures"] if failure["check"] == "FONT_NOT_EMBEDDED"
        ]
        assert len(flagged) == fonts["n_non_embedded"], record["path"]
        for entry in fonts["non_embedded"]:
            assert entry["embedded"] is False
        for entry in fonts["records"]:
            assert isinstance(entry["name"], str) and entry["type"]


def test_no_hard_failure_is_a_warning(report: dict) -> None:
    """The summary lists exactly the per-file hard failures and warnings."""
    hard = [item for record in report["files"] for item in record["hard_failures"]]
    warnings = [item for record in report["files"] for item in record["warnings"]]
    environment = [item for item in report["warnings"] if item["file"] == "-"]
    assert report["summary"]["n_hard_failures"] == len(hard) == len(report["hard_failures"])
    assert report["summary"]["n_warnings"] == len(warnings) + len(environment)
    for item in hard:
        assert item["check"] and item["detail"] and item["file"]


def test_hard_failure_checks_are_the_documented_ones(report: dict) -> None:
    """Only the checks named as hard failures may appear in that list."""
    allowed = {
        "FONT_NOT_EMBEDDED",
        "FIGURE_NOT_SINGLE_PAGE",
        "TEXT_OUTSIDE_PAGE",
        "TEXT_HEIGHT_BELOW_MINIMUM",
        "INK_CLIPPED_AT_PAGE_EDGE",
        "SCHEMATIC_WITHOUT_DRAWIO_SOURCE",
    }
    for item in report["hard_failures"]:
        assert item["check"] in allowed, f"unexpected hard-failure check {item['check']}"


def test_figure_page_count_rule(report: dict) -> None:
    """A figure is a hard failure for page count only when it is not one page."""
    for record in report["files"]:
        pages = record["geometry"]["pages"]
        flagged = any(
            failure["check"] == "FIGURE_NOT_SINGLE_PAGE" for failure in record["hard_failures"]
        )
        if record["kind"] == "figure":
            assert flagged == (pages != 1), record["path"]
        else:
            assert not flagged, "a built document must not be judged as a figure"


def test_violations_carry_coordinates(report: dict) -> None:
    """Every flagged word is reported with a box so the coordinator can find it."""
    for record in report["files"]:
        for violation in record["text_bounds"]["violations"]:
            assert violation["max_overflow_pt"] > report["thresholds"]["text_outside_page_pt"]
            for key in ("x0", "y0", "x1", "y1", "page", "text", "overflow_pt"):
                assert key in violation, f"{record['path']}: {key} missing"
        for violation in record["min_text_height"]["violations"]:
            # the criterion is the estimated typeset size of the word's own line
            assert violation["line_estimated_height_pt"] < report["thresholds"]["min_text_height_pt"]
            assert violation["height_pt"] <= violation["line_estimated_height_pt"] + 1e-6
            for key in ("x0", "y0", "x1", "y1", "page", "text"):
                assert key in violation, f"{record['path']}: {key} missing"
        for pair in record["overlaps"]["pairs"]:
            assert pair["overlap_fraction"] > report["thresholds"]["overlap_fraction_of_smaller_box"]
            for side in ("word_a", "word_b"):
                box = pair[side]
                assert {"text", "x0", "y0", "x1", "y1"} <= set(box)


def test_ink_gate_decides_page_overflow(report: dict) -> None:
    """A box-only overflow is a warning; a hard failure needs clipped or unmeasured ink."""
    for record in report["files"]:
        verdicts = record["text_bounds"].get("ink_verdict_by_page", {})
        hard_pages = {
            failure["page"]
            for failure in record["hard_failures"]
            if failure["check"] in {"TEXT_OUTSIDE_PAGE", "INK_CLIPPED_AT_PAGE_EDGE"}
        }
        warning_pages = {
            warning["page"]
            for warning in record["warnings"]
            if warning["check"] == "TEXT_BOX_PADDING_ONLY"
        }
        for page_key, verdict in verdicts.items():
            page = int(page_key)
            if verdict == "padding_only":
                assert page in warning_pages, f"{record['path']} p{page} should warn, not fail"
                assert page not in hard_pages
            elif verdict in {"clipped", "unavailable", "not_run"}:
                assert page in hard_pages, f"{record['path']} p{page} should fail"
            else:  # pragma: no cover - defensive
                raise AssertionError(f"unknown ink verdict {verdict!r}")
        if verdicts:
            assert record["ink_checks"], "ink verdicts without ink measurements"


def test_flagged_pages_have_ink_measurements(report: dict) -> None:
    """Regression: the ink checks must reach the JSON (they were reset once)."""
    flagged = [
        record
        for record in report["files"]
        if record["text_bounds"]["violations"]
    ]
    for record in flagged:
        assert record["ink_checks"], f"{record['path']} has box violations but no ink evidence"
        for check in record["ink_checks"]:
            assert check.get("available"), f"{record['path']} p{check.get('page')} not rendered"
            assert "margin_pt" in check and "ink_bbox_pt" in check
    reported = sum(len(record["ink_checks"]) for record in report["files"])
    assert report["summary"]["ink_verification_pages"] == reported


def test_small_relative_words_are_advisory(report: dict) -> None:
    """A word far smaller than its line is never a hard failure."""
    for record in report["files"]:
        small = record["min_text_height"]["small_relative_words"]
        assert record["min_text_height"]["n_small_relative_words"] >= len(small)
        if record["min_text_height"]["n_small_relative_words"]:
            assert any(
                warning["check"] == "SMALL_RELATIVE_WORD_BOXES" for warning in record["warnings"]
            ), record["path"]
        hard_checks = {failure["check"] for failure in record["hard_failures"]}
        assert "SMALL_RELATIVE_WORD_BOXES" not in hard_checks


def test_overlap_counts_are_consistent(report: dict) -> None:
    """Pair counts add up and duplicates are excluded from the pair list."""
    for record in report["files"]:
        overlaps = record["overlaps"]
        kinds = overlaps["counts_by_kind"]
        assert sum(kinds.values()) == overlaps["n_candidate_pairs"] == len(overlaps["pairs"])
        assert overlaps["n_same_baseline_pairs"] == kinds.get("same_baseline_horizontal", 0)
        for pair in overlaps["pairs"]:
            a, b = pair["word_a"], pair["word_b"]
            assert pair["overlap_fraction"] > 0.25
            if pair["same_baseline"]:
                assert pair["kind"] == "same_baseline_horizontal"
            assert not (
                a["text"] == b["text"]
                and abs(a["x0"] - b["x0"]) < 1e-9
                and abs(a["y0"] - b["y0"]) < 1e-9
            ), "an exact duplicate was not excluded"


def test_overlap_caveat_is_in_the_report(report: dict) -> None:
    """The report must state that the box test is a conservative approximation."""
    text = report["_md_text"].lower()
    assert "conservative approximation" in text
    assert "cannot see text drawn over graphics" in text
    assert "ascent/descent" in text


def test_report_has_the_required_sections(report: dict) -> None:
    text = report["_md_text"]
    for heading in (
        "# WRR figure and PDF quality assurance",
        "## Verdict",
        "## Per-figure master table",
        "## 1. Fonts",
        "## 2. Page geometry",
        "## 3. Text outside the page box",
        "## 4. Minimum text height",
        "## 5. Overlapping text",
        "## 6. Source provenance",
        "## 7. Raster image resolution",
        "## 8. Printed size and effective text size",
        "## 9. Prioritised fix list",
        "## 10. Method, reproducibility and caveats",
    ):
        assert heading in text, f"missing report section {heading!r}"


def test_provenance_is_recorded_for_every_figure(report: dict) -> None:
    """Each figure states its draw.io source and/or its generating script."""
    for record in report["files"]:
        if record["kind"] != "figure":
            continue
        provenance = record["provenance"]
        assert "drawio_source_exists" in provenance
        assert "python_generators" in provenance
        assert provenance["kind"] in {"drawio", "drawio+python", "python", "unknown"}
        if provenance["schematic"] and not provenance["drawio_source_exists"]:
            assert any(
                failure["check"] == "SCHEMATIC_WITHOUT_DRAWIO_SOURCE"
                for failure in record["hard_failures"]
            ), record["path"]
        if provenance["kind"] == "unknown":
            assert any(warning["check"] == "PROVENANCE_UNKNOWN" for warning in record["warnings"])


def test_derived_print_scale_is_self_consistent(report: dict) -> None:
    """The printed size and effective text size follow from the measured scale."""
    for record in report["files"]:
        if record["kind"] != "figure":
            continue
        placement = record.get("print_placement", {})
        if not placement.get("measured") or not placement.get("scale"):
            continue
        width_pt = record["geometry"]["page_size_pt"][0]
        expected = placement["scale"] * width_pt
        assert placement["printed_width_pt"] == pytest.approx(expected, abs=1e-3)
        minimum = record["min_text_height"]["min_height_pt"]
        if minimum:
            assert placement["effective_min_height_pt"] == pytest.approx(
                minimum * placement["scale"], abs=1e-3
            )


def test_raster_and_font_provenance_tooling_is_declared(report: dict) -> None:
    """The report says which tools were present, and absent tools become warnings."""
    for tool, available in report["tool_availability"].items():
        assert isinstance(available, bool)
        if not available:
            assert any(
                warning["check"] == "TOOL_MISSING" and tool in warning["detail"]
                for warning in report["warnings"]
            ), tool
        if available:
            assert report["tool_versions"][tool], tool
    assert report["tool_availability"]["pdffonts"] is True
    assert report["tool_availability"]["pdftotext"] is True


def test_strict_exit_code_contract(tmp_path: Path) -> None:
    """Strict mode exits non-zero exactly when the JSON records a hard failure."""
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    proc, json_path, _ = _run_harness(tmp_path, extra=("--no-ink-verify",))
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    has_hard = bool(payload["hard_failures"])
    assert proc.returncode == (1 if has_hard else 0), (
        f"strict exit code {proc.returncode} disagrees with {len(payload['hard_failures'])} "
        "recorded hard failure(s)"
    )
    assert payload["exit_code"] == (1 if has_hard else 0)


def test_sources_are_not_modified(tmp_path: Path) -> None:
    """The harness is read-only on paper/**."""
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    watched = [
        path
        for path in list(FIGURES_DIR.glob("*.pdf"))[:1] + list(BUILT_PDFS) + list(PAPER_DIR.glob("*.tex"))
        if path.is_file()
    ]
    assert watched
    before = {path: _sha256(path) for path in watched}
    _run_harness(tmp_path, extra=("--report-only", "--no-ink-verify"))
    after = {path: _sha256(path) for path in watched}
    assert before == after, "the harness modified a paper/ or figures/ artifact"
