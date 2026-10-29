"""Current freezes must detect changes without fabricating historical hashes."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("current_observation_replay", ROOT / "scripts/967_current_observation_replay.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def make_snapshot(tmp_path):
    base = tmp_path / "snapshot"
    base.mkdir()
    (base / "daily.bin").write_bytes(b"current daily observations")
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"scope": "previously selected subset", "files": [{"path": "daily.bin"}]}))
    spec = {"legacy": "legacy.json", "base": "snapshot", "script": "fake_verifier.py", "report": "new_report.json"}
    (tmp_path / "fake_verifier.py").write_text("# test verifier\n")
    return spec, legacy


def test_new_freeze_records_current_bytes_without_retrofitting_legacy(tmp_path):
    spec, legacy = make_snapshot(tmp_path)
    original = legacy.read_bytes()
    destination = tmp_path / "new_manifest.json"
    result = M.prepare_manifest(spec, destination, tmp_path)
    current = M.verify_current_manifest(destination, spec, tmp_path)
    assert legacy.read_bytes() == original
    assert "sha256" not in json.loads(original)["files"][0]
    assert current["legacy_manifest"]["sha256"] == M.sha256(legacy)
    assert current["legacy_manifest"]["files_without_sha256"] == 1
    assert current["files"][0]["sha256"] == M.sha256(tmp_path / "snapshot/daily.bin")
    assert current["historical_provenance_authenticated"] is False
    assert current["freeze_semantics"] == "current content freeze, not evidence of past provenance"
    frozen = destination.read_bytes()
    assert M.prepare_manifest(spec, destination, tmp_path)["reused_existing_current_freeze"] is True
    assert destination.read_bytes() == frozen
    assert result["reused_existing_current_freeze"] is False


def test_current_freeze_rejects_changed_data_or_missing_hash(tmp_path):
    spec, legacy = make_snapshot(tmp_path)
    destination = tmp_path / "new_manifest.json"
    M.prepare_manifest(spec, destination, tmp_path)
    doc = json.loads(destination.read_text())
    doc["files"][0].pop("sha256")
    destination.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="changed"):
        M.verify_current_manifest(destination, spec, tmp_path)
    destination.unlink()
    M.prepare_manifest(spec, destination, tmp_path)
    (tmp_path / "snapshot/daily.bin").write_bytes(b"changed observations")
    with pytest.raises(ValueError, match="changed"):
        M.verify_current_manifest(destination, spec, tmp_path)
    with pytest.raises(ValueError, match="changed"):
        M.prepare_manifest(spec, destination, tmp_path)


def test_preparation_refuses_symlinks_and_parent_path_escapes(tmp_path):
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    base = tmp_path / "snapshot"
    base.mkdir()
    (base / "alias.bin").symlink_to(outside)
    with pytest.raises(ValueError, match="Symlink"):
        M.safe_file(base, "alias.bin")
    with pytest.raises(ValueError, match="Unsafe"):
        M.safe_file(base, "../outside.bin")


def test_zero_exit_cannot_reuse_an_old_passing_report(tmp_path, monkeypatch):
    spec, legacy = make_snapshot(tmp_path)
    destination = tmp_path / "new_manifest.json"
    M.prepare_manifest(spec, destination, tmp_path)
    report = tmp_path / spec["report"]
    report.write_text(json.dumps({"status": "passed"}))
    monkeypatch.setattr(M.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    result = M.replay_one("open_observed", spec, destination, tmp_path, tmp_path)
    assert result["status"] == "failed"
    assert result["returncode"] == 0
    assert not report.exists()
    assert Path(result["stdout_log"]).is_file()
    assert Path(result["stderr_log"]).is_file()
