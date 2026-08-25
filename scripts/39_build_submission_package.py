#!/usr/bin/env python3
"""Build self-contained AGU manuscript and Supporting Information drafts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
OUTPUT = PAPER / "submission"


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity(path: Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _markdown_table(
    path: Path,
    *,
    columns: Iterable[str] | None = None,
    rename: dict[str, str] | None = None,
    digits: int = 3,
) -> str:
    frame = pd.read_csv(path, dtype={"station_id": str})
    if columns is not None:
        active = [column for column in columns if column in frame]
        frame = frame.loc[:, active]
    numeric = frame.select_dtypes(include="number").columns
    frame.loc[:, numeric] = frame.loc[:, numeric].round(digits)
    for column in frame.select_dtypes(include="object").columns:
        frame[column] = (
            frame[column]
            .astype(str)
            .str.replace("\\", "\\\\", regex=False)
            .str.replace("$", "\\$", regex=False)
        )
    if rename:
        frame = frame.rename(columns=rename)
    return frame.to_markdown(index=False)


def _figure_captions() -> tuple[dict[int, str], dict[int, str]]:
    text = (PAPER / "figure_captions.md").read_text(encoding="utf-8")
    figures: dict[int, str] = {}
    tables: dict[int, str] = {}
    for kind, number, title, body in re.findall(
        r"\*\*(Figure|Table) (\d+)\. (.*?)\*\* (.*?)(?=\n\n|$)",
        text,
        flags=re.DOTALL,
    ):
        value = f"{title}. {body.strip()}"
        target = figures if kind == "Figure" else tables
        target[int(number)] = value
    return figures, tables


def _main_source() -> str:
    manuscript = (PAPER / "manuscript.md").read_text(encoding="utf-8")
    title = manuscript.splitlines()[0].removeprefix("# ").strip()
    manuscript = manuscript.split("\n", 1)[1].lstrip()
    key_points = (PAPER / "key_points.md").read_text(encoding="utf-8")
    key_points = key_points.split("\n", 1)[1].lstrip()
    plain = (PAPER / "plain_language_summary.md").read_text(encoding="utf-8")
    plain = plain.split("\n", 1)[1].lstrip()
    if _words(plain) > 200:
        raise ValueError("Plain Language Summary exceeds 200 words")
    for line in key_points.splitlines():
        if line.startswith("- ") and len(line[2:]) > 140:
            raise ValueError(f"Key Point exceeds 140 characters: {line}")

    acknowledgments = """
## Acknowledgments

**AUTHOR INPUT REQUIRED:** Insert all funding bodies, grant identifiers, in-kind support, and acknowledged contributors before submission.

## Conflict of Interest

**AUTHOR APPROVAL REQUIRED:** Replace this line with the final declaration approved by every author.

## Author Contributions

**AUTHOR INPUT REQUIRED:** Insert the approved CRediT contribution statement.

"""
    manuscript = manuscript.replace(
        "## 6. Data and Code Availability", acknowledgments + "## 6. Open Research"
    )

    figure_captions, table_captions = _figure_captions()
    tables = ["\n# Tables\n"]
    for number in range(1, 6):
        table_path = PAPER / "tables" / f"table_{number:02d}.csv"
        tables.extend(
            [
                f"\n## Table {number}\n",
                _markdown_table(table_path),
                f"\n*Table {number}. {table_captions[number]}*\n",
            ]
        )
    figures = ["\n# Figures\n"]
    for number in range(1, 8):
        figure_path = ROOT / "figures" / "main" / f"figure_{number:02d}.png"
        figures.extend(
            [
                f"\n## Figure {number}\n",
                f"![Figure {number}]({figure_path.as_posix()}){{ width=95% }}\n",
                f"*Figure {number}. {figure_captions[number]}*\n",
            ]
        )

    return f"""---
title: "{title}"
author:
  - "[Full author names and affiliations required]"
date: "Draft built from repository evidence"
keywords:
  - stream temperature
  - reservoir regulation
  - missing data
  - monitoring networks
  - thermal memory
---

# Title Page

**Authors and affiliations:** [AUTHOR INPUT REQUIRED]\
**Corresponding author:** [NAME, EMAIL, AND ORCID REQUIRED]

# Key Points

{key_points}

# Plain Language Summary

{plain}

{manuscript}

{"".join(tables)}

{"".join(figures)}
"""


def _si_source() -> str:
    overview = (PAPER / "si.md").read_text(encoding="utf-8")
    overview = overview.split("## Contents", 1)[0].strip()
    methods = (PAPER / "methods.md").read_text(encoding="utf-8")
    methods = methods.split("\n", 1)[1].lstrip()
    audits = (PAPER / "si_independence_audits.md").read_text(encoding="utf-8")
    audits = audits.split("\n", 1)[1].lstrip()
    table_specs = [
        (
            "Table S1. Recoverability-type sensitivity across classification horizons",
            ROOT / "results/revision/recoverability_type_horizon_sensitivity.csv",
            [
                "network",
                "station_id",
                "gap_length",
                "donor_component",
                "memory_component",
                "recoverability_type",
            ],
        ),
        (
            "Table S2. P3 change-date sensitivity",
            ROOT / "results/revision/p3_change_point_summary.csv",
            None,
        ),
        (
            "Table S3. State sensitivity of the covariance heuristic",
            ROOT / "results/revision/budget_evaluation_summary.csv",
            None,
        ),
        (
            "Table S4. Cross-fitted singleton-failure effects",
            ROOT / "results/revision/node_importance_cross_fitted.csv",
            [
                "station_id",
                "failed_station_id",
                "full_network_value",
                "failed_value",
                "impact",
                "impact_ci_lower",
                "impact_ci_upper",
                "n_events",
            ],
        ),
        (
            "Table S5. Held-out Chattahoochee fixed-model evaluation",
            ROOT / "results/revision/external_confirmation_summary.csv",
            [
                "station_id",
                "predicted_type",
                "validation_selected_model",
                "observed_selected_skill_30d",
                "observed_selected_skill_90d",
                "observed_selected_skill_180d",
                "qualitative_prediction_consistent",
            ],
        ),
        (
            "Table S6. Regulated-site distance profile",
            ROOT / "results/regulation_panel_v1_legacy_transport/distance_profile.csv",
            None,
        ),
        (
            "Table S7. National-panel regression estimates",
            ROOT
            / "results/regulation_panel_v1_legacy_transport/logistic_regression.csv",
            None,
        ),
        (
            "Table S8. Post-hoc within-fold leave-one-ecoregion-out AUC",
            ROOT / "results/revision/loeo_within_fold_auc.csv",
            [
                "held_out_ecoregion",
                "n",
                "n_regulated",
                "n_unregulated",
                "base_rate",
                "oof_probability_median",
                "within_fold_auc",
            ],
        ),
    ]
    tables = []
    for title, path, columns in table_specs:
        tables.extend([f"\n## {title}\n", _markdown_table(path, columns=columns)])
    figure_s1 = ROOT / "results/revision/p3_change_point_diagnostic.png"
    return f"""---
title: "Supporting Information"
author:
  - "[Authors must match the main manuscript]"
date: "Draft built from repository evidence"
---

{overview}

# Text S1. Extended Methods

{methods}

# Text S2. Independence and Matching Audits

{audits}

# Figure S1. P3 Change-Date Sensitivity

![P3 change-date sensitivity]({figure_s1.as_posix()}){{ width=95% }}

*Figure S1. Daily fitting-period anomalies, Pettitt and least-squares single-break diagnostics, dependence-aware bootstrap intervals, first-unit operation, and annual endpoints. Only the least-squares sensitivity interval covers 20 December 2014.*

{"".join(tables)}

# Evidence Boundaries

Validation-only model rankings are not manuscript performance evidence. State-matched, annual-demeaned, cross-fitted node-importance, external fixed-model, and within-fold leave-one-ecoregion-out AUC analyses are post-hoc sensitivities. The frozen primary national metric remains the pooled leave-one-ecoregion-out AUC. The Chattahoochee panel is one temporal/network evaluation, not five independent basins. No ecological, application, or regulatory safe-fill threshold was declared. Data and software are archived separately and are not Supporting Information.
"""


def _run_pandoc(source: Path, output: Path, *, pdf: bool) -> None:
    command = [
        "pandoc",
        str(source),
        "--from=markdown+tex_math_dollars+tex_math_single_backslash+citations+raw_tex",
        "--citeproc",
        f"--bibliography={PAPER / 'references.bib'}",
        f"--resource-path={ROOT}:{PAPER}:{ROOT / 'figures'}:{ROOT / 'results'}",
        "--standalone",
        "-o",
        str(output),
    ]
    if pdf:
        command.extend(
            [
                "--pdf-engine=xelatex",
                f"--include-in-header={OUTPUT / 'latex_header.tex'}",
                "-V",
                "geometry:margin=0.85in",
                "-V",
                "fontsize=10pt",
                "-V",
                "linestretch=1.35",
                "-V",
                "mainfont=DejaVu Serif",
                "-V",
                "sansfont=DejaVu Sans",
                "-V",
                "monofont=DejaVu Sans Mono",
            ]
        )
    subprocess.run(command, cwd=ROOT, check=True)


def _enable_docx_line_numbers(path: Path) -> None:
    """Enable continuous line numbering in every Word section."""

    temporary = path.with_name(f".{path.name}.line-numbers.tmp")
    with zipfile.ZipFile(path, "r") as source:
        members = {name: source.read(name) for name in source.namelist()}
    document_name = "word/document.xml"
    document = members[document_name]
    marker = b"<w:sectPr"
    insertion = b'<w:lnNumType w:countBy="1" w:restart="continuous"/>'
    cursor = 0
    rebuilt = bytearray()
    while True:
        start = document.find(marker, cursor)
        if start < 0:
            rebuilt.extend(document[cursor:])
            break
        opening_end = document.find(b">", start)
        if opening_end < 0:
            raise ValueError("DOCX section properties are malformed")
        rebuilt.extend(document[cursor : opening_end + 1])
        rebuilt.extend(insertion)
        cursor = opening_end + 1
    members[document_name] = bytes(rebuilt)
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, content in members.items():
            target.writestr(name, content)
    temporary.replace(path)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    header = OUTPUT / "latex_header.tex"
    header.write_text(
        "\\usepackage{lineno}\n"
        "\\linenumbers\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{longtable}\n"
        "\\usepackage{float}\n"
        "\\usepackage{xcolor}\n"
        "\\setlength{\\emergencystretch}{3em}\n",
        encoding="utf-8",
    )
    main_source = OUTPUT / "agu_main_manuscript.md"
    si_source = OUTPUT / "agu_supporting_information.md"
    main_source.write_text(_main_source(), encoding="utf-8")
    si_source.write_text(_si_source(), encoding="utf-8")

    outputs = [
        main_source,
        si_source,
        header,
        OUTPUT / "agu_main_manuscript.pdf",
        OUTPUT / "agu_main_manuscript.docx",
        OUTPUT / "agu_supporting_information.pdf",
    ]
    _run_pandoc(main_source, outputs[3], pdf=True)
    _run_pandoc(main_source, outputs[4], pdf=False)
    _enable_docx_line_numbers(outputs[4])
    _run_pandoc(si_source, outputs[5], pdf=True)
    manifest = {
        "schema_version": "agu_submission_package_v1",
        "status": "draft_blocked_external_and_author_inputs",
        "artifacts": [_identity(path) for path in outputs],
        "blockers": [
            "author names, affiliations, ORCID, funding, contributions, and declarations",
            "written editor acceptance of the restricted-data exception",
            "real archival software DOI",
            "GEMS confidential reviewer-data upload",
        ],
        "plain_language_summary_words": _words(
            (PAPER / "plain_language_summary.md").read_text(encoding="utf-8")
        ),
        "main_figures": 7,
        "main_tables": 5,
    }
    manifest_path = OUTPUT / "submission_package_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": manifest["status"], "artifacts": len(outputs)}))


if __name__ == "__main__":
    main()
