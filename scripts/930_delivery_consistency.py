#!/usr/bin/env python3
"""Recompute the transcription checks that a passing test suite can miss.

The script reads saved result tables, regenerates nothing, and compares the
country label, external case families, paired denominators, overlap boundary
and seed-level coverage changes with the manuscript text.  With --archive it
repeats that check in an extracted copy, compiles the article and supporting
PDF, and records whether the package matches the workspace.  It does not
refit a model.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def load_inputs(root: Path):
    sys.path.insert(0, str(root / "scripts"))
    sys.path.insert(0, str(root / "src"))
    spec = importlib.util.spec_from_file_location(
        "delivery_manuscript_inputs", root / "scripts/929_manuscript_inputs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    strata = importlib.util.spec_from_file_location(
        "delivery_failure_strata", root / "scripts/927_failure_strata.py"
    )
    strata_module = importlib.util.module_from_spec(strata)
    strata.loader.exec_module(strata_module)
    return module, strata_module

def abstract_words(root: Path) -> int:
    paper = root / "paper/wrr_tr"
    article = (paper / "review_completion_article.tex").read_text()
    abstract = article.split(r"\begin{abstract}", 1)[1].split(
        r"\begin{plainlanguagesummary}", 1
    )[0]
    commands = {}
    for path in paper.glob("*.tex"):
        for name, value in re.findall(
            r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", path.read_text()
        ):
            commands[name] = value
    expanded = abstract
    for _ in range(4):
        expanded = re.sub(
            r"\\([A-Za-z]+)\{\}",
            lambda match: commands.get(match.group(1), match.group(0)),
            expanded,
        )
    expanded = re.sub(r"\$[^$]*\$", " math ", expanded)
    expanded = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})*", " ", expanded)
    return len(re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", expanded.replace("--", " ")))

def check_tree(root: Path) -> dict:
    module, strata = load_inputs(root)
    facts = module.external_facts()
    paired = module.two_method_intersection(
        pd.read_csv(root / "results/wrr_review_response_20261027/whole_archive/uncertainty_common_cases.csv")
    )
    forward = paired.loc[paired.family.eq("crossed") & paired["mode"].eq("forward")].iloc[0]
    cases = pd.read_parquet(
        root / "results/wrr_adversarial_review_20261027/failure_strata/failure_strata_cases.parquet"
    )
    exact = cases.loc[np.isclose(cases.peak_overlap, 0.5)]
    labels = strata.overlap_labels(pd.Series([0.0, 0.5, 1.0]))
    rank = pd.read_csv(
        root / "results/wrr_adversarial_review_20261027/rank_convergence/rank_convergence_cases.csv.gz",
        usecols=["method", "construction", "seed", "draws", "covered"],
    )
    per_seed = rank.groupby(
        ["method", "construction", "seed", "draws"], observed=True
    ).covered.mean().unstack("draws")
    seed_max = float((per_seed[4096] - per_seed[1024]).abs().max() * 100)
    paper = root / "paper/wrr_tr"
    values = (paper / "core_claims_values.tex").read_text()
    table = (paper / "external_qualification_table.tex").read_text()
    article = (paper / "review_completion_article.tex").read_text()
    results = (paper / "simple_research_results.tex").read_text()
    points = article.split(r"\keypoints", 1)[1].split(r"\maketitle", 1)[0]
    errors = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(facts["bc_total"] == 372 and facts["bc_controlled"] == 288 and facts["bc_calendar"] == 84, "BC mask families")
    require(facts["truckee_cases"] == 72 and facts["truckee_years"] == 4, "Truckee scored cases")
    require(facts["reservoir_scored_cases"] == 306 and facts["reservoir_scored_stations"] == 4 and facts["reservoir_scored_years"] == 17, "reservoir score")
    require(facts["usgs_complete_years"] == 8 and facts["usgs_four_year_sites"] == 0, "USGS complete years versus four-year stations")
    require(facts["rio_complete_years"] == [2017] and facts["rio_bounded_years"] == [2012, 2019], "Rio Mora quarter-hour years")
    require(int(forward.n_paired) == 736 and int(forward.incomplete_years) == 3328, "paired forward denominator")
    require(int(forward.n_own_d2) == 818 and int(forward.n_own_classic) == 736, "method availability")
    require(np.isclose(forward.annual_weighted_d2, 0.9072, atol=5e-4), "paired D2 annual coverage")
    require(np.isclose(seed_max, 0.815, atol=5e-4), "single-seed coverage change")
    require(len(exact) == 47 and set(exact.overlap_bin.astype(str)) == {"at least half"}, "overlap of exactly 0.5")
    require(list(labels.astype(str)) == ["no overlap", "at least half", "at least half"], "boundary labels")
    require("CCRegionSwitzerlandCov" in values and "CCRegionFinlandCov" not in values, "Switzerland macro")
    require("in Finland" not in results and "Swiss FOEN" in results, "Switzerland sentence")
    require("0.4 percentage" not in results and "0.4 percentage" not in article, "precision claim removed")
    require("No H30 model was scored" not in table and "108 masks" not in table, "external table contradictions")
    require("288 controlled gaps" in table and "72 controlled-gap masks" in table and "306 exploratory" in table, "external table counts")
    require("[-5,50]" in article, "Rio Mora bound in the article")
    require(all("D2" not in line for line in points.splitlines()), "key-point abbreviation")
    require(abstract_words(root) < 250, f"abstract length {abstract_words(root)}")
    if errors:
        raise RuntimeError("Delivery consistency failed: " + "; ".join(errors))
    return {
        "bc_masks": [facts["bc_controlled"], facts["bc_calendar"], facts["bc_total"]],
        "truckee_cases": facts["truckee_cases"],
        "reservoir_cases": facts["reservoir_scored_cases"],
        "usgs_complete_years": facts["usgs_complete_years"],
        "usgs_four_year_stations": facts["usgs_four_year_sites"],
        "paired_forward_archives": int(forward.n_paired),
        "paired_forward_years": int(forward.incomplete_years),
        "seed_change_max_pp": seed_max,
        "overlap_exact_half": int(len(exact)),
        "abstract_words": abstract_words(root),
    }

def compile_pdfs(root: Path) -> dict:
    logs = {}
    for name in ["review_completion_article.tex", "review_completion_supporting.tex"]:
        proc = subprocess.run(
            ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", name],
            cwd=root / "paper/wrr_tr",
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "TEXINPUTS": ".:../wrr/template:"},
            capture_output=True,
            text=True,
        )
        log_name = name.replace(".tex", ".log")
        log_text = (root / "paper/wrr_tr" / log_name).read_text(errors="replace") if (root / "paper/wrr_tr" / log_name).exists() else proc.stdout + proc.stderr
        if proc.returncode:
            raise RuntimeError(f"{name} failed to compile:\n" + (proc.stdout + proc.stderr)[-4000:])
        if "Float too large" in log_text:
            raise RuntimeError(f"{name} still has a float larger than the page")
        text = subprocess.check_output(
            ["pdftotext", "-layout", str(root / "paper/wrr_tr" / name.replace(".tex", ".pdf")), "-"],
            text=True,
        )
        logs[name] = {"pages_text_characters": len(text)}
        if name.endswith("supporting.tex"):
            for phrase in ["Switzerland (FOEN)", "USGS HUC17", "at least half"]:
                if phrase not in text:
                    raise RuntimeError(f"Supporting PDF text is missing {phrase}")
            if text.count("USGS HUC17") < 2:
                raise RuntimeError("Supporting PDF does not show both USGS HUC17 rows")
        else:
            if "in Finland" in text:
                raise RuntimeError("Article PDF still says in Finland")
            if "Switzerland" not in text and "Swiss" not in text:
                raise RuntimeError("Article PDF does not name Switzerland")
    return logs

def package_matches_workspace(archive: Path, workspace: Path, extract: Path) -> dict:
    mismatches = []
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            if info.is_dir() or info.filename in {"REVIEW_PACKAGE_README.txt", "dependency_inventory.json"}:
                continue
            current = workspace / info.filename
            extracted = extract / info.filename
            if not current.is_file():
                mismatches.append(info.filename + " missing from workspace")
                continue
            if current.read_bytes() != extracted.read_bytes():
                mismatches.append(info.filename)
    if mismatches:
        raise RuntimeError("Package differs from workspace: " + ", ".join(mismatches[:30]))
    return {"members_compared": "all packaged files except the package readme and dependency inventory"}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/wrr_adversarial_review_20261028/delivery_check.json",
    )
    args = parser.parse_args()
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "saved-result transcription, manuscript text, and optional isolated compile",
        "not_tested": [
            "full raw-data reconstruction",
            "model retraining",
            "strict independent external confirmation",
        ],
        "historical_package_note": "An older candidate package is not evidence for the current workspace.",
    }
    if args.archive is None:
        report["workspace"] = check_tree(ROOT)
    else:
        archive = args.archive if args.archive.is_absolute() else ROOT / args.archive
        with tempfile.TemporaryDirectory(prefix="wrr_delivery_") as temp:
            dest = Path(temp)
            with zipfile.ZipFile(archive) as zipped:
                if zipped.testzip():
                    raise RuntimeError("ZIP CRC failure")
                zipped.extractall(dest)
            report["extracted"] = check_tree(dest)
            report["package_match"] = package_matches_workspace(archive, ROOT, dest)
            report["compile"] = compile_pdfs(dest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
