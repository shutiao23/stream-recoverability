#!/usr/bin/env python3
"""Build, verify and record the 2026-10-31 final manuscript candidate.

The package starts from the accepted 2026-10-29 candidate's scientific file
scope and replaces every member with the current workspace bytes. Generated
release receipts and a per-file manifest are written at the archive root. A
separate acceptance record binds the archive hash to the two PDFs, the targeted
tests and the extracted-package replay.

This is a local release-consistency tool. It does not rebuild raw data, refit
models, install a clean environment or establish data rights.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "dist/wrr_process_experiments_20261029.zip"
DEST = ROOT / "dist/wrr_final_candidate_20261031_r2.zip"
EXTERNAL_MANIFEST = ROOT / "dist/wrr_final_candidate_20261031_r2.manifest.json"
OUT = ROOT / "results/final_release_20261031_r2"
REVIEW = ROOT / "docs/reviews/wrr_stanford_perspective_20261031"
GENERATED = [
    "REVIEW_PACKAGE_README.txt",
    "dependency_inventory.json",
    "RELEASE_RECEIPT.json",
    "CONTENT_MANIFEST.sha256",
]
BASE_EXCLUDE = {"REVIEW_PACKAGE_README.txt", "dependency_inventory.json"}
ADDITIONS = [
    "docs/reviews/wrr_multiview_review_20261031/MINOR_REVISION_COMPLETION_ZH.md",
    "docs/reviews/wrr_multiview_review_20261031/PACKAGE_README.txt",
    "docs/reviews/wrr_multiview_review_20261031/POSTING_CHECKLIST.md",
    "docs/reviews/wrr_multiview_review_20261031/SIMULATED_WRR_REVIEW_ZH.md",
    "docs/reviews/wrr_stanford_perspective_20261031/REVIEW_ZH.md",
    "docs/reviews/wrr_stanford_perspective_20261031/REVISION_COMPLETION_ZH.md",
    "docs/reviews/wrr_stanford_perspective_20261031/WORK_PLAN_ZH.md",
    "docs/reviews/wrr_stanford_perspective_20261031/diagnostics.py",
    "paper/wrr_tr/stanford_availability_supporting.tex",
    "paper/wrr_tr/stanford_calendar_supporting.tex",
    "paper/wrr_tr/stanford_calendar_table.tex",
    "paper/wrr_tr/stanford_geometry_supporting.tex",
    "paper/wrr_tr/stanford_geometry_table.tex",
    "paper/wrr_tr/stanford_revision_values.tex",
    "results/final_release_20261031_r2/targeted_tests.xml",
    "results/final_release_20261031_r2/targeted_tests_summary.json",
    "results/final_release_20261031_r2/workspace_consistency.json",
    "results/wrr_final_revision_20261031/annual_predictions_compact.csv",
    "results/wrr_final_revision_20261031/case_designs.csv",
    "results/wrr_final_revision_20261031/data_manifest.json",
    "results/wrr_final_revision_20261031/estimator_availability.csv",
    "results/wrr_final_revision_20261031/estimator_paired_comparisons.csv",
    "results/wrr_final_revision_20261031/estimator_unavailable_subset.csv",
    "results/wrr_final_revision_20261031/reference_truths.csv",
    "results/wrr_final_revision_20261031/reference_year_sets.csv",
    "results/wrr_final_revision_20261031/retention_choice_counts.csv",
    "results/wrr_final_revision_20261031/retention_family_summary.csv",
    "results/wrr_final_revision_20261031/retention_geometry_cases.csv",
    "results/wrr_final_revision_20261031/retention_paired_intervals.csv",
    "results/wrr_final_revision_20261031/scope.json",
    "results/wrr_multiview_review_20261031/time_paired_intervals_recheck.csv",
    "results/wrr_multiview_review_20261031/time_primary_recheck.csv",
    "results/wrr_multiview_review_20261031/time_selection_arithmetic.json",
    "results/wrr_multiview_review_20261031/time_station_group_heterogeneity.csv",
    "results/wrr_stanford_perspective_20261031/point_estimator_availability.csv",
    "results/wrr_stanford_perspective_20261031/point_estimator_paired_comparison.csv",
    "results/wrr_stanford_perspective_20261031/point_estimator_unavailable_subset.csv",
    "results/wrr_stanford_perspective_20261031/retention_choice_counts.csv",
    "results/wrr_stanford_perspective_20261031/retention_geometry_cases.csv",
    "results/wrr_stanford_perspective_20261031/retention_geometry_summary.csv",
    "results/wrr_stanford_perspective_20261031/retention_paired_intervals.csv",
    "results/wrr_stanford_perspective_20261031/review_summary.json",
    "results/wrr_stanford_perspective_20261031/scope.json",
    "scripts/980_final_release.py",
    "scripts/981_stanford_revision.py",
    "scripts/982_final_release_tests.py",
    "scripts/983_verify_extension_replay.py",
    "tests/test_final_release_freshness.py",
    "tests/test_stanford_revision.py",
]
TARGETED_TEST_FILES = [
    "tests/test_wrr_source_trajectory_calibration.py",
    "tests/test_independent_calibration_audit.py",
    "tests/test_process_time_gap_sensitivity.py",
    "tests/test_region_water_adversarial.py",
    "tests/test_experiment_data_catalog.py",
    "tests/test_process_experiment_delivery.py",
    "tests/test_wrr_process_revision.py",
    "tests/test_review_manuscript_structure.py",
    "tests/test_wrr_adversarial_revision.py",
    "tests/test_wrr_process_time_gap_revision.py",
    "tests/test_wrr_trajectory_revision.py",
    "tests/test_current_observation_replay.py",
    "tests/test_review_completion_current_evidence.py",
    "tests/test_review_bundle_atomic_write.py",
    "tests/test_process_review_region_water.py",
    "tests/test_stanford_revision.py",
    "tests/test_final_release_freshness.py",
]
MANUSCRIPTS = {
    "article": {
        "tex": "paper/wrr_tr/review_completion_article.tex",
        "pdf": "paper/wrr_tr/review_completion_article.pdf",
    },
    "supporting": {
        "tex": "paper/wrr_tr/review_completion_supporting.tex",
        "pdf": "paper/wrr_tr/review_completion_supporting.pdf",
    },
}


class ReleaseFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseFailure(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_member_path(name: str) -> PurePosixPath:
    require(bool(name) and "\x00" not in name and "\\" not in name, "Invalid ZIP member path: " + repr(name))
    require(not name.startswith("/") and not name.startswith("~"), "Absolute or home-relative ZIP member: " + name)
    parts = name.rstrip("/").split("/")
    require(all(part not in {"", ".", ".."} and ":" not in part for part in parts), "Unsafe ZIP member: " + name)
    path = PurePosixPath(*parts)
    require(not path.is_absolute(), "Absolute ZIP member: " + name)
    return path


def pdf_pages(path: Path) -> int:
    text = subprocess.check_output(["pdfinfo", str(path)], text=True)
    for line in text.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ReleaseFailure("PDF page count missing: " + str(path))


def normalized_pdf_text(path: Path) -> str:
    text = subprocess.check_output(["pdftotext", "-layout", str(path), "-"], text=True)
    # The AGU SI class prints a compile date/time in the running footer. It is
    # build metadata, not manuscript text, and changes on every latexmk run.
    text = re.sub(
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}[ap]m\b",
        "<BUILD_TIME>",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def abstract_words() -> int:
    spec = importlib.util.spec_from_file_location("final_release_930", ROOT / "scripts/930_delivery_consistency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.abstract_words(ROOT))


def key_points() -> list[str]:
    article = (ROOT / "paper/wrr_tr/review_completion_article.tex").read_text()
    block = article.split(r"\keypoints", 1)[1].split(r"\maketitle", 1)[0]
    return [item.strip().strip("{}") for item in block.splitlines() if item.strip().startswith("{")]


def heterogeneity_counts(path: Path) -> dict[str, dict[str, int]]:
    """Recompute the station/group direction counts used in the discussion."""
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(rows, "Heterogeneity table is empty")
    output: dict[str, dict[str, int]] = {}
    for unit in ("station_key", "independence_group"):
        subset = [row for row in rows if row["unit"] == unit]
        require(subset, "Heterogeneity unit is missing: " + unit)
        output[unit] = {
            "n": len(subset),
            "all_improves": sum(float(row["all_minus_warm"]) < 0 for row in subset),
            "cdf_worse": sum(float(row["cdf_minus_warm"]) > 0 for row in subset),
            "sxx_worse": sum(float(row["sxx_minus_warm"]) > 0 for row in subset),
        }
    return output


def base_members() -> list[str]:
    require(OLD.is_file(), "Historical candidate is absent: " + str(OLD))
    with zipfile.ZipFile(OLD) as zipped:
        require(zipped.testzip() is None, "Historical candidate has a CRC failure")
        names = [info.filename for info in zipped.infolist() if not info.is_dir()]
    names = [name for name in names if name not in BASE_EXCLUDE]
    require(len(names) == 3313, f"Historical candidate scope changed: {len(names)} scientific files")
    require(len(set(names)) == len(names), "Historical candidate has duplicate members")
    return sorted(names)


def generated_documents(member_paths: list[str]) -> dict[str, bytes]:
    readme = (REVIEW / "PACKAGE_README.txt").read_bytes()
    dependency = {
        "schema": "final_candidate_dependency_inventory_v1",
        "created_utc": utc_now(),
        "base_scope": {
            "archive": str(OLD.relative_to(ROOT)),
            "sha256": sha256(OLD),
            "scientific_files": len(base_members()),
            "selection": "Every historical scientific member is replaced by its current workspace bytes.",
        },
        "additions": ADDITIONS,
        "generated_at_root": GENERATED,
        "not_included": [
            "author-confirmed names, affiliations, funding, CRediT, conflicts and acknowledgments",
            "LUBW redistribution permission and a legal reviewer-access route",
            "restricted source-case tables, trained model weights and local-only evidence",
            "a permanent repository identifier or DOI",
        ],
        "verification": "See the external acceptance record and the package README; this inventory does not certify data rights.",
    }
    receipt = {
        "schema": "final_candidate_release_receipt_v1",
        "created_utc": utc_now(),
        "revision": "2026-10-31 minor revision: current sources, both PDFs, SI synchronisation and scoped clarifications",
        "manuscripts": {},
        "abstract_words": abstract_words(),
        "key_points": key_points(),
        "member_count": len(member_paths) + len(GENERATED),
        "content_manifest": "CONTENT_MANIFEST.sha256",
        "scope": "Current source-to-PDF identity and embedded release facts. Extracted-package compile and frozen-input replay are checked by the external acceptance record.",
        "pending_author_items": [
            "author names, order, ORCID, affiliations, funding, CRediT, conflicts and acknowledgments",
            "legal reviewer access, including LUBW reuse and redistribution",
            "permanent deposit and citable identifier",
        ],
        "not_claimed": [
            "clean-environment dependency installation",
            "full raw-provider reconstruction",
            "model retraining from zero",
            "cross-climate independent external confirmation",
        ],
    }
    for label, paths in MANUSCRIPTS.items():
        tex = ROOT / paths["tex"]
        pdf = ROOT / paths["pdf"]
        require(tex.is_file() and pdf.is_file(), "Manuscript input missing: " + label)
        receipt["manuscripts"][label] = {
            "tex": paths["tex"],
            "tex_sha256": sha256(tex),
            "pdf": paths["pdf"],
            "pdf_sha256": sha256(pdf),
            "pdf_bytes": pdf.stat().st_size,
            "pdf_pages": pdf_pages(pdf),
        }
    return {
        "REVIEW_PACKAGE_README.txt": readme,
        "dependency_inventory.json": (json.dumps(dependency, ensure_ascii=False, indent=2) + "\n").encode(),
        "RELEASE_RECEIPT.json": (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode(),
    }


def build(_: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = base_members()
    for relative in ADDITIONS:
        path = ROOT / relative
        require(path.is_file(), "Added package file is missing: " + relative)
        require(path.resolve().is_relative_to(ROOT.resolve()), "Added package file escapes the workspace: " + relative)
    overlap = sorted(set(base) & set(ADDITIONS))
    require(not overlap, "Additions duplicate historical members: " + ", ".join(overlap))
    member_paths = sorted(set(base) | set(ADDITIONS))
    generated = generated_documents(member_paths)
    require(set(generated) == {"REVIEW_PACKAGE_README.txt", "dependency_inventory.json", "RELEASE_RECEIPT.json"},
            "Generated root document names changed")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="." + DEST.name + ".", suffix=".tmp", dir=DEST.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    hashes: dict[str, str] = {}
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for relative in member_paths:
                data = (ROOT / relative).read_bytes()
                zipped.writestr(relative, data)
                hashes[relative] = sha256_bytes(data)
            for name in sorted(generated):
                zipped.writestr(name, generated[name])
                hashes[name] = sha256_bytes(generated[name])
            manifest = "".join(f"{hashes[path]}  {path}\n" for path in sorted(hashes)).encode()
            zipped.writestr("CONTENT_MANIFEST.sha256", manifest)
            hashes["CONTENT_MANIFEST.sha256"] = sha256_bytes(manifest)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, DEST)
    finally:
        if temporary.exists():
            temporary.unlink()

    package_sha = sha256(DEST)
    report = {
        "schema": "final_candidate_package_manifest_v1",
        "created_utc": utc_now(),
        "package": str(DEST.relative_to(ROOT)),
        "package_sha256": package_sha,
        "package_bytes": DEST.stat().st_size,
        "members": len(hashes),
        "scientific_members": len(base) + len(ADDITIONS),
        "generated_members": sorted(GENERATED),
        "content_manifest_sha256": hashes["CONTENT_MANIFEST.sha256"],
        "release_receipt_sha256": hashes["RELEASE_RECEIPT.json"],
        "base_archive": str(OLD.relative_to(ROOT)),
        "base_archive_sha256": sha256(OLD),
        "additions": ADDITIONS,
        "manuscripts": {
            label: {
                "tex_sha256": sha256(ROOT / paths["tex"]),
                "pdf_sha256": sha256(ROOT / paths["pdf"]),
                "pdf_pages": pdf_pages(ROOT / paths["pdf"]),
            }
            for label, paths in MANUSCRIPTS.items()
        },
        "scope": "Package/workspace byte identity, current source-to-PDF identity and extracted-package checks are recorded in the acceptance record.",
    }
    EXTERNAL_MANIFEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (OUT / "package_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (DEST.parent / (DEST.name + ".sha256")).write_text(package_sha + "  " + DEST.name + "\n")
    print(json.dumps({"status": "built", "package": report["package"], "sha256": package_sha,
                      "bytes": report["package_bytes"], "members": report["members"]}, ensure_ascii=False))


def verify_members(zipped: zipfile.ZipFile, expected_scientific_members: int | None = None) -> dict:
    require(zipped.testzip() is None, "Final candidate has a CRC failure")
    infos = zipped.infolist()
    names: list[str] = []
    for info in infos:
        path = safe_member_path(info.filename)
        name = path.as_posix()
        require(name not in names, "Duplicate final-candidate member: " + name)
        kind = stat.S_IFMT(info.external_attr >> 16)
        require(kind in {0, stat.S_IFREG, stat.S_IFDIR}, "Symlink or special member: " + name)
        require(not info.flag_bits & 1, "Encrypted member: " + name)
        names.append(name)
    require("CONTENT_MANIFEST.sha256" in names, "Content manifest missing")
    manifest_text = zipped.read("CONTENT_MANIFEST.sha256").decode()
    recorded = {}
    for line in manifest_text.splitlines():
        digest, separator, relative = line.partition("  ")
        require(separator and re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "Malformed manifest line")
        recorded[relative] = digest
    actual = {name for name in names if name != "CONTENT_MANIFEST.sha256"}
    require(set(recorded) == actual, "Manifest membership differs from archive membership")
    for name in sorted(recorded):
        require(sha256_bytes(zipped.read(name)) == recorded[name], "Manifest hash mismatch: " + name)
    compared = 0
    for name in names:
        if name in GENERATED:
            continue
        current = ROOT / name
        require(current.is_file(), "Packaged file is absent from workspace: " + name)
        require(current.read_bytes() == zipped.read(name), "Packaged/workspace bytes differ: " + name)
        compared += 1
    expected = expected_scientific_members if expected_scientific_members is not None else 3313 + len(ADDITIONS)
    require(compared == expected, f"Workspace comparison count differs: {compared} != {expected}")
    return {"status": "passed", "members": len(names), "workspace_byte_comparisons": compared,
            "generated_members": sorted(GENERATED), "manifest_members": len(recorded),
            "manifest_sha256": sha256_bytes(manifest_text.encode())}


def verify(_: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    require(DEST.is_file(), "Final candidate is absent: " + str(DEST))
    require(EXTERNAL_MANIFEST.is_file(), "External package manifest is absent")
    manifest = json.loads(EXTERNAL_MANIFEST.read_text())
    require(sha256(DEST) == manifest["package_sha256"], "Package hash differs from its manifest")
    with zipfile.ZipFile(DEST) as zipped:
        member_report = verify_members(zipped, expected_scientific_members=manifest.get("scientific_members"))
    with tempfile.TemporaryDirectory(prefix="wrr_final_release_") as temporary:
        extracted = Path(temporary)
        with zipfile.ZipFile(DEST) as zipped:
            zipped.extractall(extracted)
        receipt = json.loads((extracted / "RELEASE_RECEIPT.json").read_text())
        spec = importlib.util.spec_from_file_location("final_release_930", extracted / "scripts/930_delivery_consistency.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        transcription = module.check_tree(extracted)
        compile_report = module.compile_pdfs(extracted)
        manuscript_report = {}
        for label, paths in MANUSCRIPTS.items():
            saved_pdf = ROOT / paths["pdf"]
            rebuilt_pdf = extracted / paths["pdf"]
            saved_text = normalized_pdf_text(saved_pdf)
            rebuilt_text = normalized_pdf_text(rebuilt_pdf)
            require(saved_text == rebuilt_text, "Saved and rebuilt PDF text differ: " + paths["pdf"])
            saved_pages = pdf_pages(saved_pdf)
            rebuilt_pages = pdf_pages(rebuilt_pdf)
            require(saved_pages == rebuilt_pages, "Saved and rebuilt PDF page counts differ: " + paths["pdf"])
            require(receipt["manuscripts"][label]["pdf_sha256"] == sha256(saved_pdf),
                    "Receipt PDF hash differs from saved PDF: " + label)
            require(receipt["manuscripts"][label]["tex_sha256"] == sha256(ROOT / paths["tex"]),
                    "Receipt TeX hash differs from saved TeX: " + label)
            manuscript_report[label] = {"pdf_pages": saved_pages, "pdf_sha256": sha256(saved_pdf),
                                        "pdf_text_matches_rebuild": True,
                                        "tex_sha256": sha256(ROOT / paths["tex"])}
        supporting_text = normalized_pdf_text(extracted / MANUSCRIPTS["supporting"]["pdf"])
        article_text = normalized_pdf_text(extracted / MANUSCRIPTS["article"]["pdf"])
        article_source = (extracted / "paper/wrr_tr/review_completion_article.tex").read_text()
        article_prose = re.sub(r"\s+", " ", article_source.replace("--", "–"))
        require("time support of finite-record heat slopes" in supporting_text, "SI title missing from rebuilt PDF")
        require("Observed 1981–2025 220 31 3 32.4 11.36%" in supporting_text, "SI 1981-2025 gap row missing")

        heterogeneity = heterogeneity_counts(
            extracted / "results/wrr_multiview_review_20261031/time_station_group_heterogeneity.csv"
        )
        require(heterogeneity["station_key"] == {"n": 41, "all_improves": 41, "cdf_worse": 14, "sxx_worse": 7},
                "Station heterogeneity counts changed")
        require(heterogeneity["independence_group"] == {"n": 17, "all_improves": 17, "cdf_worse": 3, "sxx_worse": 2},
                "Group heterogeneity counts changed")
        require(f"({heterogeneity['station_key']['all_improves']}/{heterogeneity['station_key']['n']})" in article_prose,
                "Station all-year improvement count missing")
        require(f"({heterogeneity['independence_group']['all_improves']}/{heterogeneity['independence_group']['n']})" in article_prose,
                "Group all-year improvement count missing")
        require(f"{heterogeneity['station_key']['cdf_worse']} of {heterogeneity['station_key']['n']} stations" in article_prose,
                "Station CDF heterogeneity count missing")
        require(f"{heterogeneity['independence_group']['cdf_worse']} of {heterogeneity['independence_group']['n']} groups" in article_prose,
                "Group CDF heterogeneity count missing")
        require(f"{heterogeneity['station_key']['sxx_worse']} of {heterogeneity['station_key']['n']}" in article_prose,
                "Station Sxx heterogeneity count missing")
        require(f"{heterogeneity['independence_group']['sxx_worse']} of {heterogeneity['independence_group']['n']}" in article_prose,
                "Group Sxx heterogeneity count missing")

        controlled_gap = "805 forward controlled-gap archives with 30–90-day gaps" in article_prose
        require(controlled_gap, "Controlled-gap scope missing from the abstract")
        ratio_qualified = ("not per-archive relative errors" in article_prose
                           and "not ecological thresholds" in article_prose)
        require(ratio_qualified, "RMSE/median ratio qualification missing")
        intervals_conditioned = ("conditional on the saved annual predictions" in article_prose
                                 and "retraining source models" in article_prose
                                 and "selecting the rule" in article_prose)
        require(intervals_conditioned, "Conditional group-interval scope missing")
        contribution_stated = ("archive-use recommendation" in article_prose
                               and "calculation ledger" in article_prose)
        require(contribution_stated, "Archive-use contribution statement missing")
        require("time support of finite-record heat slopes" in article_prose, "Article title missing from TeX source")
        absolute_stated = "median absolute 95th-percentile endpoint changes" in article_prose
        require(absolute_stated, "Absolute endpoint-change label missing from the abstract")
        reference_set_stated = ("specified set of complete reference years" in article_prose
                                and "fixed, station-specific reference-year set" in article_prose
                                and "need not be contiguous" in article_prose)
        require(reference_set_stated, "Fixed non-contiguous reference-year set is not defined")
        geometry_stated = ("Algebraic year-set error" in supporting_text
                           and "iid working benchmark" in supporting_text
                           and "not a coverage guarantee" in supporting_text)
        require(geometry_stated, "SI geometry derivation or its boundary is missing")
        calendar_stated = ("Empirical-calendar extension and selection opportunity" in supporting_text
                           and "818" in supporting_text)
        require(calendar_stated, "Calendar-family SI extension is missing")

        cover_text = (extracted / "paper/wrr_tr/review_completion_cover_letter.txt").read_text()
        require("time support of finite-record heat slopes" in cover_text,
                "Cover letter does not use the current manuscript title")
        require("temporal support and uncertainty" not in cover_text,
                "Cover letter retains the superseded manuscript title")
        require("805 forward controlled-gap archives" in cover_text,
                "Cover letter omits the controlled-gap scope")
        cover_letter_report = {
            "path": "paper/wrr_tr/review_completion_cover_letter.txt",
            "sha256": sha256(extracted / "paper/wrr_tr/review_completion_cover_letter.txt"),
            "title_matches": True,
            "controlled_gap_scope": True,
        }
        scientific_text_checks = {
            "article_title_current": True,
            "si_title_and_1981_2025_row": True,
            "controlled_gap_scope_in_abstract": controlled_gap,
            "ratio_interpretation_in_article": ratio_qualified,
            "station_group_heterogeneity_recomputed": True,
            "conditional_group_intervals_in_methods": intervals_conditioned,
            "central_contribution_stated": contribution_stated,
            "absolute_endpoint_change_label": absolute_stated,
            "fixed_reference_year_set_defined": reference_set_stated,
            "si_geometry_derivation": geometry_stated,
            "si_calendar_extension": calendar_stated,
        }
        require(transcription["abstract_words"] == receipt["abstract_words"],
                "Receipt abstract word count differs from extracted package")
        require(all(len(point) <= 140 for point in receipt["key_points"]), "A release key point exceeds 140 characters")

    report = {
        "schema": "final_candidate_verification_v1",
        "status": "passed",
        "created_utc": utc_now(),
        "package": str(DEST.relative_to(ROOT)),
        "package_sha256": sha256(DEST),
        "package_bytes": DEST.stat().st_size,
        "external_manifest": str(EXTERNAL_MANIFEST.relative_to(ROOT)),
        "external_manifest_sha256": sha256(EXTERNAL_MANIFEST),
        "member_check": member_report,
        "manuscripts": manuscript_report,
        "cover_letter": cover_letter_report,
        "scientific_text_checks": scientific_text_checks,
        "heterogeneity_recomputed": heterogeneity,
        "extracted_transcription": transcription,
        "extracted_compile": compile_report,
        "scope": "Safe extraction, manifest and workspace byte identity, saved-vs-rebuilt PDF text/page identity, and extracted transcription/compile. Latest extracted PDF bytes need not equal saved PDF bytes because PDFs embed build time.",
        "not_tested": ["clean-environment installation", "raw-provider reconstruction", "model retraining", "cross-climate external confirmation"],
    }
    (OUT / "package_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "package_sha256": report["package_sha256"],
                      "members": member_report["members"], "abstract_words": transcription["abstract_words"]},
                     ensure_ascii=False))


def git_state() -> dict:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=ROOT, text=True).splitlines()
    counts = {"entries": len(status), "modified": 0, "deleted": 0, "untracked": 0}
    for line in status:
        code = line[:2]
        if code == "??":
            counts["untracked"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        else:
            counts["modified"] += 1
    return {"head": head, "worktree": counts,
            "note": "The worktree is not commit-identified; the package manifest and acceptance hashes identify this candidate."}


def accept(_: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    require(EXTERNAL_MANIFEST.is_file(), "External package manifest is absent")
    manifest = json.loads(EXTERNAL_MANIFEST.read_text())
    require(DEST.is_file(), "Final candidate is absent")
    require(sha256(DEST) == manifest["package_sha256"], "Package hash differs from its manifest")
    verification_path = OUT / "package_verification.json"
    tests_path = OUT / "targeted_tests_summary.json"
    delivery_path = OUT / "package_delivery_check.json"
    replay_path = OUT / "extension_replay.json"
    require(verification_path.is_file(), "Package verification is absent")
    require(tests_path.is_file(), "Targeted test summary is absent")
    require(delivery_path.is_file(), "Extracted-package delivery check is absent")
    require(replay_path.is_file(), "Extension replay record is absent")
    verification = json.loads(verification_path.read_text())
    tests = json.loads(tests_path.read_text())
    delivery = json.loads(delivery_path.read_text())
    replay = json.loads(replay_path.read_text())
    require(verification.get("status") == "passed", "Package verification did not pass")
    require(verification.get("package_sha256") == manifest["package_sha256"], "Verification package hash differs")
    require(verification.get("external_manifest_sha256") == sha256(EXTERNAL_MANIFEST),
            "Verification record does not belong to the current external manifest")
    require(verification.get("member_check", {}).get("status") == "passed",
            "Verification member check did not pass")
    require(verification["member_check"].get("manifest_sha256") == manifest["content_manifest_sha256"],
            "Verification content manifest differs from the external manifest")
    require(verification["member_check"].get("members") == manifest["members"],
            "Verification member count differs from the external manifest")
    require(tests.get("exit_code") == 0, "Targeted tests exited nonzero")
    require(tests.get("files") == TARGETED_TEST_FILES, "Targeted test list differs from the declared release scope")
    require(tests.get("failures") == 0 and tests.get("errors") == 0, "Targeted tests did not pass")
    require(tests.get("passed") == tests.get("tests") - tests.get("skipped"),
            "Targeted test counts are inconsistent")
    require(delivery.get("status") == "passed", "Extracted-package delivery check did not pass")
    require(delivery.get("archive_sha256") == manifest["package_sha256"], "Delivery-check archive hash differs")
    checks = delivery.get("extracted_package_checks", {})
    require(checks.get("transcription_and_pdf_compile"), "Packaged transcription/compile record missing")
    require(checks.get("source_calibration_frozen_replay"), "Packaged source replay record missing")
    require(checks.get("time_support_frozen_replay"), "Packaged time replay record missing")
    require(checks.get("current_observation_replay"), "Packaged observation replay record missing")
    require(replay.get("status") == "passed", "Extracted-package extension replay did not pass")
    require(replay.get("archive_sha256") == manifest["package_sha256"],
            "Extension replay archive hash differs")
    require(replay.get("archives") == 1623 and replay.get("geometry_rows") == 8115,
            "Extension replay denominators differ")
    require(float(replay.get("max_numeric_difference", 1.0)) <= float(replay.get("tolerance", 0.0)),
            "Extension replay exceeds its declared numeric tolerance")

    # Re-establish package/workspace identity at the moment of acceptance. A
    # stale "passed" report is not enough: every packaged scientific file must
    # still equal its current workspace bytes, and the manuscript hashes must be
    # those named by both the receipt and the verification report.
    with zipfile.ZipFile(DEST) as zipped:
        fresh_members = verify_members(zipped, expected_scientific_members=manifest.get("scientific_members"))
        receipt_bytes = zipped.read("RELEASE_RECEIPT.json")
    require(fresh_members["manifest_sha256"] == manifest["content_manifest_sha256"],
            "Current package content manifest differs from the external manifest")
    require(sha256_bytes(receipt_bytes) == manifest["release_receipt_sha256"],
            "Current package receipt differs from the external manifest")
    receipt = json.loads(receipt_bytes)
    require(receipt.get("abstract_words") == verification.get("extracted_transcription", {}).get("abstract_words"),
            "Receipt and extracted verification abstract counts differ")

    manuscript_report = {}
    for label, paths in MANUSCRIPTS.items():
        tex_hash = sha256(ROOT / paths["tex"])
        pdf_hash = sha256(ROOT / paths["pdf"])
        require(verification["manuscripts"][label]["tex_sha256"] == tex_hash,
                "TeX changed after verification: " + label)
        require(verification["manuscripts"][label]["pdf_sha256"] == pdf_hash,
                "PDF changed after verification: " + label)
        require(verification["manuscripts"][label].get("pdf_text_matches_rebuild") is True,
                "Verification did not test saved-versus-rebuilt PDF text: " + label)
        require(receipt["manuscripts"][label]["tex_sha256"] == tex_hash,
                "Package receipt TeX hash differs from current file: " + label)
        require(receipt["manuscripts"][label]["pdf_sha256"] == pdf_hash,
                "Package receipt PDF hash differs from current file: " + label)
        manuscript_report[label] = {
            "tex": paths["tex"], "tex_sha256": tex_hash,
            "pdf": paths["pdf"], "pdf_sha256": pdf_hash,
            "pdf_pages": pdf_pages(ROOT / paths["pdf"]),
        }
    manuscript_report["article"]["abstract_words"] = abstract_words()
    manuscript_report["article"]["key_points"] = key_points()
    completion = REVIEW / "REVISION_COMPLETION_ZH.md"
    acceptance = {
        "schema_version": "final_candidate_acceptance_v1",
        "status": "complete",
        "complete": True,
        "review_date": "2026-10-31 Asia/Shanghai",
        "created_utc": utc_now(),
        "revision": "Minor revision: fixed non-contiguous reference-year target, absolute endpoint-change label, algebraic year-set derivation, empirical-calendar extension, and point-estimate accuracy versus availability; acceptance is bound to the current package and PDFs.",
        "git": git_state(),
        "package": {
            "path": manifest["package"],
            "sha256": manifest["package_sha256"],
            "bytes": manifest["package_bytes"],
            "members": manifest["members"],
            "content_manifest_sha256": manifest["content_manifest_sha256"],
            "release_receipt_sha256": manifest["release_receipt_sha256"],
            "external_manifest": str(EXTERNAL_MANIFEST.relative_to(ROOT)),
            "external_manifest_sha256": sha256(EXTERNAL_MANIFEST),
        },
        "manuscripts": manuscript_report,
        "cover_letter": verification["cover_letter"],
        "review_completion_report": {"path": str(completion.relative_to(ROOT)), "sha256": sha256(completion)},
        "tests": {"path": str(tests_path.relative_to(ROOT)), "sha256": sha256(tests_path),
                  "passed": tests["passed"], "tests": tests["tests"], "failures": tests["failures"],
                  "errors": tests["errors"], "skipped": tests["skipped"], "scope": tests["scope"],
                  "junit": tests.get("junit")},
        "package_verification": {"path": str(verification_path.relative_to(ROOT)), "sha256": sha256(verification_path),
                                 "status": verification["status"], "package_sha256": verification["package_sha256"],
                                 "manuscript_pdf_text_matches_rebuild": all(
                                     row["pdf_text_matches_rebuild"] for row in verification["manuscripts"].values()),
                                 "members": verification["member_check"]["members"],
                                 "abstract_words": verification["extracted_transcription"]["abstract_words"]},
        "package_delivery_check": {"path": str(delivery_path.relative_to(ROOT)), "sha256": sha256(delivery_path),
                                   "status": delivery["status"], "archive_sha256": delivery["archive_sha256"],
                                   "scope": delivery.get("scope"),
                                   "extracted_check_keys": sorted(checks)},
        "extension_replay": {"path": str(replay_path.relative_to(ROOT)), "sha256": sha256(replay_path),
                             "status": replay["status"], "archive_sha256": replay["archive_sha256"],
                             "archives": replay["archives"], "geometry_rows": replay["geometry_rows"],
                             "max_numeric_difference": replay["max_numeric_difference"],
                             "tolerance": replay["tolerance"]},
        "scientific_checks": {
            "main_pages": manuscript_report["article"]["pdf_pages"],
            "supporting_pages": manuscript_report["supporting"]["pdf_pages"],
            "abstract_words": manuscript_report["article"]["abstract_words"],
            "key_points_within_140_chars": all(len(point) <= 140 for point in manuscript_report["article"]["key_points"]),
            "si_title_and_1981_2025_row": verification["scientific_text_checks"]["si_title_and_1981_2025_row"],
            "cover_letter_title_and_scope": verification["cover_letter"]["title_matches"] and verification["cover_letter"]["controlled_gap_scope"],
            "controlled_gap_scope_in_abstract": verification["scientific_text_checks"]["controlled_gap_scope_in_abstract"],
            "ratio_interpretation_in_article": verification["scientific_text_checks"]["ratio_interpretation_in_article"],
            "station_group_heterogeneity_in_discussion": verification["scientific_text_checks"]["station_group_heterogeneity_recomputed"],
            "conditional_group_intervals_in_methods": verification["scientific_text_checks"]["conditional_group_intervals_in_methods"],
            "central_contribution_stated": verification["scientific_text_checks"]["central_contribution_stated"],
            "absolute_endpoint_change_label": verification["scientific_text_checks"]["absolute_endpoint_change_label"],
            "fixed_reference_year_set_defined": verification["scientific_text_checks"]["fixed_reference_year_set_defined"],
            "si_geometry_derivation": verification["scientific_text_checks"]["si_geometry_derivation"],
            "si_calendar_extension": verification["scientific_text_checks"]["si_calendar_extension"],
        },
        "coverage": {
            "proved": [
                "current source to current PDF text and page identity",
                "package/workspace byte identity for every non-generated member",
                "extracted-package transcription and compilation",
                "frozen-input source-calibration, annual-selection and current-observation replay",
                "extracted-package replay of the 1,623-archive calendar extension within 1e-12",
                f"{tests['tests']} targeted tests from the declared release list",
            ],
            "not_proved": verification["not_tested"],
            "replay_scope": delivery.get("scope"),
        },
        "pending_author_items": [
            "author-approved names, order, ORCID, affiliations, funding, CRediT, conflicts and acknowledgments",
            "legal reviewer access, including LUBW reuse and redistribution",
            "permanent repository deposit and citable identifier",
        ],
        "note": "This acceptance record is local release evidence. It does not impersonate a WRR decision, fill author metadata or establish data rights.",
    }
    target = OUT / "acceptance.json"
    target.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "accepted", "acceptance": str(target.relative_to(ROOT)),
                      "package_sha256": acceptance["package"]["sha256"]}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function in [("build", build), ("verify", verify), ("accept", accept)]:
        command = sub.add_parser(name)
        command.set_defaults(function=function)
    args = parser.parse_args()
    try:
        args.function(args)
    except ReleaseFailure as error:
        print(json.dumps({"status": "failed", "failure": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
