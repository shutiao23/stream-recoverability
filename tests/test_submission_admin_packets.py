from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_zenodo_json_matches_title_and_has_no_doi() -> None:
    payload = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert "doi" not in payload
    assert payload["upload_type"] == "software"
    assert payload["title"] == (
        "Stream-Temperature Gap Recoverability and Monitoring-Network Evaluation"
    )
    assert payload["version"] == "1.1.0"


def test_citation_cff_doi_remains_unset() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation.get("doi") in {None, ""}
    assert "doi" not in citation.get("preferred-citation", {})


def test_four_administrative_blockers_remain_open() -> None:
    approval = json.loads(
        (ROOT / "metadata/editor_data_exception_approval.json").read_text(
            encoding="utf-8"
        )
    )
    authors = json.loads(
        (ROOT / "metadata/submission_author_metadata.json").read_text(encoding="utf-8")
    )
    upload = json.loads(
        (ROOT / "metadata/gems_reviewer_data_upload.json").read_text(encoding="utf-8")
    )
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    request = (ROOT / "paper/editor_data_exception_request.md").read_text(
        encoding="utf-8"
    )
    assert approval.get("accepted") is not True
    assert authors.get("complete") is not True
    assert authors.get("authors") == []
    assert upload.get("uploaded") is not True
    assert not citation.get("doi")
    assert "Date sent: **OPEN**" in request


def test_gems_bundle_directory_is_gitignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "private/gems_reviewer_bundle/" in ignore


def test_reviewer_inventory_is_values_free() -> None:
    inventory = json.loads(
        (ROOT / "metadata/gems_reviewer_bundle_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    assert inventory["gems_upload_complete"] is False
    assert inventory["not_a_public_archive"] is True
    dumped = json.dumps(inventory)
    for token in ("WTEMP", "WLEVEL", "RHMEAN", "WDSP", "PRCP"):
        assert token not in dumped
    for item in inventory["expected_files"]:
        assert set(item) == {"path", "found", "category", "rights_class"}
