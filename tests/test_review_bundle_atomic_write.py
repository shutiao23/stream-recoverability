"""A failed archive build must preserve the existing review candidate."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_bundle", ROOT / "scripts/536_prepare_review_bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def test_missing_file_does_not_truncate_candidate(tmp_path):
    dest = tmp_path / "candidate.zip"
    dest.write_bytes(b"previous candidate")
    with pytest.raises(RuntimeError, match="missing"):
        bundle.write_review_archive(dest, [tmp_path / "missing"], "readme", [], root=tmp_path)
    assert dest.read_bytes() == b"previous candidate"
    assert list(tmp_path.glob(".candidate.zip.*.tmp")) == []


def test_failure_during_copy_preserves_candidate(tmp_path, monkeypatch):
    dest = tmp_path / "candidate.zip"
    dest.write_bytes(b"previous candidate")
    source = tmp_path / "source.txt"
    source.write_text("new result")

    def fail(*args, **kwargs):
        raise OSError("source became unavailable")

    monkeypatch.setattr(zipfile.ZipFile, "write", fail)
    with pytest.raises(OSError, match="unavailable"):
        bundle.write_review_archive(dest, [source], "readme", [], root=tmp_path)
    assert dest.read_bytes() == b"previous candidate"
    assert list(tmp_path.glob(".candidate.zip.*.tmp")) == []


def test_success_replaces_candidate_with_relative_members(tmp_path):
    dest = tmp_path / "candidate.zip"
    dest.write_bytes(b"previous candidate")
    source = tmp_path / "results" / "summary.csv"
    source.parent.mkdir()
    source.write_text("value\n1\n")
    bundle.write_review_archive(dest, [source], "local candidate", [{"path": "restricted", "included_in_package": False}], root=tmp_path)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert z.read("results/summary.csv") == source.read_bytes()
        assert z.read("REVIEW_PACKAGE_README.txt") == b"local candidate"
        assert json.loads(z.read("dependency_inventory.json"))["inputs"][0]["included_in_package"] is False
    assert list(tmp_path.glob(".candidate.zip.*.tmp")) == []
