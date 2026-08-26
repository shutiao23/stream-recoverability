from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import stat
import sys
from pathlib import Path

import pytest
import yaml

from stream_recoverability.data.foen_sealed_corpus import (
    LOCKED_CATALOG_SHA256,
    LOCKED_QUERY_TEMPLATE_SHA256,
    LOCKED_SPLIT_SHA256,
    FoenCustodyError,
    FoenSealedAccessError,
    FoenSealedCorpusGate,
    LockedFoenCatalog,
    registry_manifest,
)
from stream_recoverability.governance import public_export_exclude

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/73_cache_foen_sealed_corpus.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("foen_custody_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _small_catalog() -> LockedFoenCatalog:
    return LockedFoenCatalog(
        roles={"foen_test": "sealed"},
        stations={"foen_test": ("2001", "2002", "2003")},
        split_sha256=LOCKED_SPLIT_SHA256,
        catalog_sha256=LOCKED_CATALOG_SHA256,
        query_template_sha256=LOCKED_QUERY_TEMPLATE_SHA256,
        endpoint="https://data.bafu.admin.ch/api",
        query_template="query X { water { observations { data_1day_mean { value } } } }",
        start_year=2024,
        end_year_exclusive=2026,
    )


def _small_gate(tmp_path: Path) -> tuple[LockedFoenCatalog, FoenSealedCorpusGate]:
    catalog = _small_catalog()
    gate = FoenSealedCorpusGate(
        catalog,
        sealed_vault=tmp_path / "vault",
        registry_dir=tmp_path / "registry",
    )
    return catalog, gate


def test_repository_lock_verifies_three_hashes_and_exact_request_grid() -> None:
    catalog = LockedFoenCatalog.load()
    assert catalog.split_sha256 == LOCKED_SPLIT_SHA256
    assert catalog.catalog_sha256 == LOCKED_CATALOG_SHA256
    assert catalog.query_template_sha256 == LOCKED_QUERY_TEMPLATE_SHA256
    requests = catalog.requests()
    assert len({row.network_id for row in requests}) == 10
    assert len({(row.network_id, row.site_id) for row in requests}) == 51
    assert len(requests) == 51 * 52
    assert {row.year for row in requests} == set(range(1974, 2026))
    assert all(row.role == "sealed" for row in requests)
    assert all(row.site_id != "2016" for row in requests)


@pytest.mark.parametrize("target", ["split", "catalog", "template"])
def test_loader_fails_closed_on_hashed_file_drift(tmp_path: Path, target: str) -> None:
    paths = {
        "split": ROOT
        / "results/framework/public_catalog/foen_prospective_split_v1.csv",
        "catalog": ROOT / "configs/foen_prospective_catalog_v1.yaml",
        "template": ROOT / "configs/foen_daily_value_query_v1.graphql",
    }
    copies = {}
    for label, source in paths.items():
        destination = tmp_path / source.name
        destination.write_bytes(
            source.read_bytes() + (b"\nDRIFT" if label == target else b"")
        )
        copies[label] = destination
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        LockedFoenCatalog.load(
            canonical_path=copies["split"],
            catalog_path=copies["catalog"],
            query_template_path=copies["template"],
        )


def test_loader_rejects_request_contract_drift(tmp_path: Path) -> None:
    split = yaml.safe_load(
        (ROOT / "configs/foen_prospective_split_v1.yaml").read_text()
    )
    split["future_request_contract"]["template_executed"] = True
    path = tmp_path / "split.yaml"
    path.write_text(yaml.safe_dump(split), encoding="utf-8")
    with pytest.raises(ValueError, match="request contract drift"):
        LockedFoenCatalog.load(split_path=path)


def test_opaque_stream_is_mode_zero_hashed_and_never_exposed_for_qc(
    tmp_path: Path,
) -> None:
    catalog, gate = _small_gate(tmp_path)
    payload = b'{"data":{"water":{"observations":{"value":12.3}}}}'
    record = gate.cache_stream("foen_test", "2001", 2024, [payload[:9], payload[9:]])
    assert record["provider"] == "foen"
    assert record["response_sha256"] == hashlib.sha256(payload).hexdigest()
    assert record["byte_count"] == len(payload)
    assert record["content_parsed"] is False
    assert record["json_decoded"] is False
    assert record["value_fields_inspected"] is False
    assert record["sealed_outcomes_opened"] is False
    assert record["qc_permitted"] is False
    assert "temperature_c" not in record
    assert "value" not in record
    request = catalog.exact_request("foen_test", "2001", 2024)
    object_path, registry_path = gate._locations(request)
    assert stat.S_IMODE(object_path.stat().st_mode) == 0
    assert json.loads(registry_path.read_text(encoding="utf-8")) == record
    with pytest.raises(FoenSealedAccessError):
        gate.assert_qc_allowed("foen_test")
    assert not hasattr(gate, "open_for_qc")


def test_safe_resume_does_not_open_sealed_object(tmp_path: Path, monkeypatch) -> None:
    catalog, gate = _small_gate(tmp_path)
    payload = b"opaque-provider-response"
    original = gate.cache_stream("foen_test", "2001", 2024, [payload])
    request = catalog.exact_request("foen_test", "2001", 2024)
    object_path, _ = gate._locations(request)
    original_open = Path.open

    def guarded_open(self: Path, *args: object, **kwargs: object):
        if self == object_path:
            raise AssertionError("resume opened sealed FOEN bytes")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    resumed = gate.resume_record("foen_test", "2001", 2024)
    assert resumed == {**original, "reused_registry": True}


def test_resume_fails_closed_for_missing_half_and_mode_drift(tmp_path: Path) -> None:
    catalog, gate = _small_gate(tmp_path)
    gate.cache_stream("foen_test", "2001", 2024, [b"opaque"])
    request = catalog.exact_request("foen_test", "2001", 2024)
    object_path, registry_path = gate._locations(request)
    registry_path.unlink()
    with pytest.raises(FoenCustodyError, match="both exist"):
        gate.resume_record("foen_test", "2001", 2024)

    object_path.chmod(0o600)
    object_path.unlink()
    gate.cache_stream("foen_test", "2001", 2024, [b"opaque"])
    object_path, _ = gate._locations(request)
    object_path.chmod(0o600)
    with pytest.raises(FoenCustodyError, match="mode 000"):
        gate.resume_record("foen_test", "2001", 2024)


def test_registry_manifest_has_strict_non_outcome_schema(tmp_path: Path) -> None:
    _, gate = _small_gate(tmp_path)
    record = gate.cache_stream("foen_test", "2001", 2024, [b"opaque"])
    manifest = registry_manifest([record])
    assert manifest["n_objects"] == 1
    assert manifest["contains_outcome_values"] is False
    with pytest.raises(ValueError, match="strict custody schema"):
        registry_manifest([{**record, "temperature_c": 12.0}])


def test_dry_run_plans_all_requests_without_contacting_provider(tmp_path: Path) -> None:
    runner = _load_runner()

    def no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("dry-run contacted FOEN")

    manifest = runner.run(
        execute=False,
        max_networks=None,
        all_networks=False,
        output_dir=tmp_path,
        opener=no_network,
    )
    assert manifest["n_networks_planned"] == 10
    assert manifest["n_stations_planned"] == 51
    assert manifest["n_calendar_years_per_station"] == 52
    assert manifest["n_station_year_requests_planned"] == 2652
    assert manifest["provider_requests_opened"] is False
    assert manifest["query_template_executed"] is False
    assert manifest["json_decoded"] is False


def test_execute_requires_selection_ack_and_committed_implementation(
    tmp_path: Path,
) -> None:
    runner = _load_runner()
    catalog, gate = _small_gate(tmp_path)
    base = {
        "execute": True,
        "max_networks": None,
        "all_networks": False,
        "output_dir": tmp_path / "run",
        "catalog": catalog,
        "gate": gate,
    }
    with pytest.raises(ValueError, match="max-networks"):
        runner.run(**base)
    base["max_networks"] = 1
    with pytest.raises(PermissionError, match="acknowledge-sealed"):
        runner.run(**base)
    base["acknowledge_sealed"] = runner.SEALED_ACK
    with pytest.raises(PermissionError, match="committed implementation"):
        runner.run(**base)


def test_simulated_execute_and_resume_never_decode_response(tmp_path: Path) -> None:
    runner = _load_runner()
    catalog, gate = _small_gate(tmp_path)
    payload = b'{"data":{"value":9.75}}'
    opened = 0

    def fake_open(*args: object, **kwargs: object):
        nonlocal opened
        opened += 1
        return io.BytesIO(payload)

    commit = "a" * 40
    kwargs = {
        "execute": True,
        "max_networks": 1,
        "all_networks": False,
        "output_dir": tmp_path / "run",
        "acknowledge_sealed": runner.SEALED_ACK,
        "implementation_commit": commit,
        "catalog": catalog,
        "gate": gate,
        "opener": fake_open,
        "commit_verifier": lambda value: value,
        "pause_s": 0,
    }
    first = runner.run(**kwargs)
    assert first["implementation_commit"] == commit
    assert first["n_station_year_requests"] == 6
    assert first["n_newly_registered"] == 6
    assert first["n_reused"] == 0
    assert first["n_failures"] == 0
    assert first["json_decoded"] is False
    assert opened == 6

    def no_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("safe resume contacted provider")

    kwargs["opener"] = no_network
    second = runner.run(**kwargs)
    assert second["n_reused"] == 6
    assert second["n_newly_registered"] == 0
    assert second["n_failures"] == 0


def test_runner_contains_no_response_json_decoder() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "json.loads" not in source
    assert "response.json" not in source


def test_foen_provider_vault_is_ignored_and_excluded_from_public_export() -> None:
    relative = "data/sealed_public_rivers_foen_v1/vault/foen_test/2001_2024.sealed"
    assert public_export_exclude(relative)
    assert (
        "data/sealed_public_rivers_foen_v1/"
        in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
