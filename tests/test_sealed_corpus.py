from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

from stream_recoverability.data.sealed_corpus import (
    LOCKED_SPLIT_SHA256,
    CorpusCustodyError,
    HUC8CorpusGate,
    LockedV3Catalog,
    SealedOutcomeAccessError,
    registry_manifest,
)
from stream_recoverability.governance import public_export_exclude


def _gate(tmp_path: Path) -> tuple[LockedV3Catalog, HUC8CorpusGate]:
    catalog = LockedV3Catalog.load()
    gate = HUC8CorpusGate(
        catalog,
        readable_cache=tmp_path / "readable",
        sealed_vault=tmp_path / "sealed",
        registry_dir=tmp_path / "registry",
    )
    return catalog, gate


def test_repository_lock_resolves_all_three_executable_roles() -> None:
    catalog = LockedV3Catalog.load()
    assert catalog.split_sha256 == LOCKED_SPLIT_SHA256
    assert catalog.requests("development")
    assert catalog.requests("validation")
    assert catalog.requests("sealed")
    assert {row.role for row in catalog.requests("sealed")} == {"sealed"}


def test_development_and_validation_bytes_can_reach_qc(tmp_path: Path) -> None:
    catalog, gate = _gate(tmp_path)
    for role in ("development", "validation"):
        request = catalog.requests(role)[0]
        payload = f"opaque-{role}-provider-response".encode()
        record = gate.cache_stream(
            request.network_id,
            request.site_id,
            [payload[:7], payload[7:]],
        )
        assert record["role"] == role
        assert record["qc_permitted"] is True
        assert record["content_parsed"] is False
        object_path, _ = gate._locations(request)
        with gate.open_for_qc(request.network_id, object_path) as handle:
            assert handle.read() == payload


def test_sealed_stream_is_hashed_registered_and_not_opened(tmp_path: Path) -> None:
    catalog, gate = _gate(tmp_path)
    request = catalog.requests("sealed")[0]
    payload = b"opaque bytes that the custody layer must not parse"
    record = gate.cache_stream(
        request.network_id,
        request.site_id,
        [payload[:5], payload[5:19], payload[19:]],
    )
    assert record == {
        "registry_schema": "huc8_corpus_byte_registry_v1",
        "network_id": request.network_id,
        "role": "sealed",
        "site_id": request.site_id,
        "request_start": request.start,
        "request_end": request.end,
        "split_sha256": LOCKED_SPLIT_SHA256,
        "storage_class": "sealed_write_only_vault",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_count": len(payload),
        "content_parsed": False,
        "sealed_outcomes_opened": False,
        "qc_permitted": False,
        "reused_registry": False,
    }
    object_path, registry_path = gate._locations(request)
    assert stat.S_IMODE(object_path.stat().st_mode) == 0
    assert json.loads(registry_path.read_text(encoding="utf-8")) == record
    with pytest.raises(SealedOutcomeAccessError, match="cannot be opened"):
        gate.open_for_qc(request.network_id, object_path)


def test_role_cannot_be_spoofed_and_registry_has_no_outcome_fields(
    tmp_path: Path,
) -> None:
    catalog, gate = _gate(tmp_path)
    sealed = catalog.requests("sealed")[0]
    development = catalog.requests("development")[0]
    with pytest.raises(ValueError, match="not a member"):
        gate.cache_stream(sealed.network_id, development.site_id, [b"x"])

    record = gate.cache_stream(sealed.network_id, sealed.site_id, [b"opaque"])
    manifest = registry_manifest([record])
    serialized = json.dumps(manifest, sort_keys=True)
    assert '"temperature_c"' not in serialized
    assert '"values"' not in serialized
    assert '"observations"' not in serialized
    assert manifest["contains_outcome_values"] is False
    assert manifest["sealed_outcomes_opened"] is False


def test_qc_path_must_be_inside_role_scoped_cache(tmp_path: Path) -> None:
    catalog, gate = _gate(tmp_path)
    request = catalog.requests("validation")[0]
    outside = tmp_path / "outside.raw"
    outside.write_bytes(b"not authorized")
    with pytest.raises(PermissionError, match="outside"):
        gate.open_for_qc(request.network_id, outside)


def test_sealed_vault_is_excluded_from_public_export_and_outcomes_are_rejected() -> None:
    assert public_export_exclude(
        "data/sealed_public_rivers_v3/vault/huc8_x/00010.sealed"
    )
    with pytest.raises(ValueError, match="non-custody fields"):
        registry_manifest(
            [
                {
                    "network_id": "huc8_x",
                    "role": "sealed",
                    "temperature_c": 12.3,
                }
            ]
        )


def test_resume_fails_closed_for_missing_or_mismatched_registry(tmp_path: Path) -> None:
    catalog, gate = _gate(tmp_path)
    request = catalog.requests("sealed")[0]
    gate.cache_stream(request.network_id, request.site_id, [b"opaque"])
    object_path, registry_path = gate._locations(request)

    registry_path.unlink()
    with pytest.raises(CorpusCustodyError, match="both exist"):
        gate.resume_record(request.network_id, request.site_id)

    object_path.chmod(0o600)
    object_path.unlink()
    record = gate.cache_stream(request.network_id, request.site_id, [b"opaque"])
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    document["sha256"] = "not-a-sha"
    registry_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CorpusCustodyError, match="invalid SHA-256"):
        gate.resume_record(request.network_id, request.site_id)
    assert record["sealed_outcomes_opened"] is False


def test_runner_resumes_from_registry_without_opening_sealed_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = LockedV3Catalog(
        roles={"huc8_test": "sealed"},
        stations={"huc8_test": ("01234567",)},
        dates={"01234567": ("2000-01-01", "2001-01-01")},
        split_sha256=LOCKED_SPLIT_SHA256,
    )
    gate = HUC8CorpusGate(
        catalog,
        readable_cache=tmp_path / "readable",
        sealed_vault=tmp_path / "sealed",
        registry_dir=tmp_path / "registry",
    )
    request = catalog.requests("sealed")[0]
    fresh = gate.cache_stream(request.network_id, request.site_id, [b"opaque-response"])
    object_path, _ = gate._locations(request)

    original_open = Path.open

    def guarded_open(self: Path, *args: object, **kwargs: object):
        if self == object_path:
            raise AssertionError("sealed object was opened during resume")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)

    script_path = Path(__file__).resolve().parents[1] / "scripts/70_cache_catalog_v3_corpus.py"
    spec = importlib.util.spec_from_file_location("w4_custody_runner", script_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    spec.loader.exec_module(runner)

    def no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("provider was contacted before safe resume")

    manifest = runner.run(
        role="sealed",
        execute=True,
        max_networks=1,
        output_dir=tmp_path / "run",
        acknowledge_sealed=runner.SEALED_ACK,
        catalog=catalog,
        gate=gate,
        opener=no_network,
        pause_s=0,
    )
    assert fresh["reused_registry"] is False
    assert manifest["n_reused"] == 1
    assert manifest["n_newly_registered"] == 0
    assert manifest["n_failures"] == 0
    assert manifest["custody"]["n_reused"] == 1
    assert manifest["custody"]["objects"][0]["reused_registry"] is True
