"""Tests for the v18 closure programme.

These are not unit tests of the analysis; they are the checks that keep the
article honest. The prose must equal the artifacts, the extended endpoint table
must line up with the case table it claims to extend, the schematics must be
generated from their draw.io sources, and every claim in the matrix must name an
artifact that exists.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.v17_fitness.paths import STEP3_CASES  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    JOHNSON_FILLED_DAYS,
    JOHNSON_UNFILLED_DAYS,
    RESULTS_ROOT,
    SUPPORT_WIDTHS,
)

MANUSCRIPT = ROOT / "paper_archived" / "v18" / "manuscript.md"
CLAIMS = ROOT / "paper_archived" / "v18" / "claims_v18.md"
DRAWIO = ROOT / "figures" / "v17" / "drawio"
KEY = ["network_id", "station_id", "year", "realization_id"]

requires_artifacts = pytest.mark.skipif(
    not (RESULTS_ROOT / "endpoint_cases.parquet").exists(),
    reason="v18 artifacts not built; run paper_archived/v18/PROTOCOL.md",
)


def test_johnson_filled_limit_is_twenty_weeks():
    """The source says twenty weeks. v17 used thirteen and every artifact moved."""

    assert JOHNSON_FILLED_DAYS == 140
    assert JOHNSON_UNFILLED_DAYS == 49
    frontier = (ROOT / "src" / "stream_recoverability" / "experiments" / "v17_fitness" / "frontier.py").read_text()
    assert "JOHNSON_FILLED_DAYS = 140" in frontier
    assert "JOHNSON_FILLED_DAYS = 91" not in frontier


@requires_artifacts
def test_manuscript_numbers_equal_the_artifacts():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "221_v18_audit_manuscript.py")],
        capture_output=True,
        text=True,
    )
    report = json.loads((RESULTS_ROOT / "manuscript_audit.json").read_text())
    assert report["passed"], report["failures"]
    assert report["checks"] >= 60
    assert result.returncode == 0


@requires_artifacts
def test_endpoint_table_lines_up_with_the_case_table():
    """The sweep regenerates the v17 realizations rather than sampling new ones."""

    endpoints = pd.read_parquet(RESULTS_ROOT / "endpoint_cases.parquet", columns=KEY + ["arm"])
    cases = pd.read_parquet(STEP3_CASES / "cases.parquet", columns=KEY + ["arm"])
    assert len(endpoints) == len(cases)
    left = endpoints.sort_values(KEY).reset_index(drop=True)
    right = cases.sort_values(KEY).reset_index(drop=True)
    pd.testing.assert_frame_equal(left[KEY], right[KEY])
    assert left["arm"].equals(right["arm"])


@requires_artifacts
def test_support_sweep_is_complete_and_ends_where_it_must():
    sweep = pd.read_csv(RESULTS_ROOT / "e6_support_width" / "support_width_sweep.csv")
    development = sweep.loc[sweep["split"] == "development"]
    assert set(development["support_width_days"]) == set(SUPPORT_WIDTHS)
    # At a full-year support the restricted axis IS the whole-year missing
    # fraction, so the two must coincide. If they do not, the support window is
    # being computed wrongly somewhere.
    widest = development.loc[development["support_width_days"] == 365].iloc[0]
    assert abs(widest["support_minus_missing_fraction"]) < 0.005


@requires_artifacts
def test_crossover_is_bracketed_by_the_measured_contrasts():
    summary = json.loads((RESULTS_ROOT / "e6_support_width" / "summary.json").read_text())
    crossover = summary["P2_crossover"]["crossover_width_days"]
    advantage = summary["P2_crossover"]["advantage_by_width"]
    assert 60 < crossover < 182
    assert advantage["30"] > 0 > advantage["182"]


@requires_artifacts
def test_deployment_panel_is_disjoint_from_the_scored_panel():
    """A station-year is either truth or a deployment case, never both."""

    years = pd.read_parquet(
        RESULTS_ROOT / "e2_archive_deployment" / "real_station_years.parquet",
        columns=["network_id", "station_id", "year", "complete"],
    )
    incomplete = years.loc[~years["complete"]]
    cases = pd.read_parquet(STEP3_CASES / "cases.parquet", columns=["network_id", "station_id", "year"])
    scored = set(map(tuple, cases.drop_duplicates().to_numpy()))
    deployed = set(map(tuple, incomplete[["network_id", "station_id", "year"]].to_numpy()))
    assert not (scored & deployed)


@requires_artifacts
def test_failed_predictions_are_recorded_as_failures():
    """A claim matrix that only contains successes is not a claim matrix."""

    text = CLAIMS.read_text(encoding="utf-8")
    assert text.count("does not stand") >= 8
    for identifier in ("L4", "L5", "J2", "A3", "D4", "R4"):
        row = next(line for line in text.splitlines() if line.startswith(f"| {identifier} "))
        assert "does not stand" in row or "withdrawn" in row, row

    e6 = json.loads((RESULTS_ROOT / "e6_support_width" / "summary.json").read_text())
    assert e6["P1_monotone_decay"]["outcome"] is False
    assert e6["P3_support_axis_dominates"]["outcome"] is False
    e3 = json.loads((RESULTS_ROOT / "e3_sine_endpoints" / "summary.json").read_text())
    assert e3["verdicts"]["P2_phase_is_transition_governed"]["outcome"] is False
    assert e3["verdicts"]["P1_mean_is_length_governed"]["outcome"] is True


def test_schematics_are_generated_from_their_drawio_sources():
    sources = sorted(DRAWIO.glob("*.drawio"))
    assert len(sources) >= 5
    for source in sources:
        pdf = ROOT / "figures" / "v17" / f"{source.stem}.pdf"
        assert pdf.exists(), f"{source.name} has no exported PDF; run make figures-drawio"
        assert pdf.stat().st_mtime >= source.stat().st_mtime - 1, (
            f"{pdf.name} is older than its source; run make figures-drawio"
        )
        # Uncompressed XML, so the source diffs line by line in review.
        assert "<mxGraphModel" in source.read_text(encoding="utf-8")


def test_every_figure_the_manuscript_cites_is_listed_with_a_file():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    cited = {int(n) for n in re.findall(r"Figure (\d+)[a-d]?\b", text)}
    listed = {int(n) for n, _ in re.findall(r"^\| (\d+) \| `([^`]+)` \|", text, re.M)}
    assert cited <= listed, f"cited but not listed: {sorted(cited - listed)}"
    for path in re.findall(r"^\| (?:\d+|SI-\d+) \| `([^`]+)` \|", text, re.M):
        assert (ROOT / path).exists(), f"{path} is listed in the manuscript but does not exist"


@requires_artifacts
def test_claim_matrix_artifacts_exist():
    text = CLAIMS.read_text(encoding="utf-8")
    referenced = set(re.findall(r"`(e\d_[a-z_]+/[A-Za-z0-9_./-]+)`", text))
    assert referenced, "no artifacts referenced"
    for relative in referenced:
        assert (RESULTS_ROOT / relative).exists(), f"{relative} is claimed but missing"


def test_manuscript_pdf_is_built_from_the_markdown():
    """The Markdown is the source; the PDF is a build product and must not lag."""

    pdf = ROOT / "paper_archived" / "v18" / "manuscript.pdf"
    if not pdf.exists():
        pytest.skip("reading copy not built; run make v18-pdf")
    assert pdf.stat().st_mtime >= MANUSCRIPT.stat().st_mtime - 1, (
        "manuscript.pdf is older than manuscript.md; run make v18-pdf"
    )
    assert pdf.stat().st_size > 100_000
