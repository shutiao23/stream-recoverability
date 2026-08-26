from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stream_recoverability.experiments.sealed_evaluator_scaffold import (
    PREFLIGHT_SCHEMA,
    MemorySealedObjectReader,
    SealedEvaluatorError,
    SealedObjectRef,
    build_evaluator_preflight,
    evaluate_with_injected_reader,
    parse_foen_response,
    parse_huc8_nwis_response,
    registered_object_references,
)


def _nwis_payload(site: str = "01234567") -> bytes:
    document = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteCode": [{"value": site}]},
                    "variable": {"variableCode": [{"value": "00010"}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "12.5",
                                    "dateTime": "2020-01-01T00:00:00Z",
                                    "qualifiers": ["A"],
                                },
                                {
                                    "value": "-999999",
                                    "dateTime": "2020-01-02T00:00:00Z",
                                    "qualifiers": ["A"],
                                },
                            ]
                        }
                    ],
                }
            ]
        }
    }
    return json.dumps(document).encode()


def _foen_payload(site: str = "2018") -> bytes:
    document = {
        "data": {
            "water": {
                "observations": {
                    "data_1day_mean": [
                        {
                            "timestamp": "2020-01-01T00:00:00Z",
                            "value": 8.5,
                            "parameterName": "WT",
                            "unitSymbol": "°C",
                            "releaseState": 2,
                            "station": {"no": site},
                        },
                        {
                            "timestamp": "2020-01-02T00:00:00Z",
                            "value": 8.8,
                            "parameterName": "WT",
                            "unitSymbol": "°C",
                            "releaseState": 1,
                            "station": {"no": site},
                        },
                    ]
                }
            }
        }
    }
    return json.dumps(document).encode()


def _authorized_preflight() -> dict[str, object]:
    return {
        "manifest_schema": PREFLIGHT_SCHEMA,
        "authorized_for_object_reads": True,
        "blockers": [],
        "bindings": {
            "v4_workload": {"path": "workload.json", "sha256": "a" * 64},
            "v4_result_binding": {"path": "result.json", "sha256": "b" * 64},
            "model_freeze": {"path": "model.json", "sha256": "c" * 64},
            "head_commit": "d" * 40,
        },
    }


def _reference(
    provider: str, body: bytes, *, network: str, site: str, year: int | None = None
) -> SealedObjectRef:
    return SealedObjectRef(
        provider=provider,
        network_id=network,
        site_id=site,
        request_year=year,
        expected_sha256=hashlib.sha256(body).hexdigest(),
        expected_byte_count=len(body),
    )


def test_provider_parsers_are_strict_and_preserve_qc_codes() -> None:
    nwis = parse_huc8_nwis_response(_nwis_payload(), site_id="01234567")
    assert nwis["temperature_c"].tolist() == [12.5, -999999.0]
    assert nwis["approval_code"].tolist() == ["A", "A"]
    foen = parse_foen_response(_foen_payload(), site_id="2018")
    assert foen["approval_code"].tolist() == ["A", "P"]
    with pytest.raises(SealedEvaluatorError, match="station mismatch"):
        parse_foen_response(_foen_payload(), site_id="wrong")


def test_repository_preflight_is_metadata_only_and_blocked_now() -> None:
    manifest = build_evaluator_preflight()
    assert manifest["authorized_for_object_reads"] is False
    assert manifest["evaluate_once_lock_claimed_by_preflight"] is False
    assert manifest["vault_path_resolved_or_statted"] is False
    assert manifest["sealed_objects_read"] == 0
    assert "evaluate_once_lock_missing_or_invalid" in manifest["blockers"]


def test_default_registry_builds_opaque_references_without_vault_paths() -> None:
    readiness_path = (
        Path(__file__).resolve().parents[1]
        / "results/framework/t2_sealed_confirmatory_v1/preunseal_readiness_manifest.json"
    )
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    references = registered_object_references(readiness)
    assert len(references) == 228 + 2652
    assert sum(ref.provider == "usgs_nwis" for ref in references) == 228
    assert sum(ref.provider == "foen" for ref in references) == 2652
    assert all("vault" not in ref.key.lower() for ref in references)


def test_blocked_preflight_never_calls_reader(tmp_path: Path) -> None:
    body = _nwis_payload()
    ref = _reference("usgs_nwis", body, network="huc8_x", site="01234567")
    reader = MemorySealedObjectReader({ref.key: body})
    blocked = _authorized_preflight()
    blocked["authorized_for_object_reads"] = False
    blocked["blockers"] = ["not_ready"]
    with pytest.raises(SealedEvaluatorError, match="forbidden"):
        evaluate_with_injected_reader(
            blocked,
            references=[ref],
            reader=reader,
            output_dir=tmp_path,
            fixture_execution=True,
        )
    assert reader.read_keys == []
    assert not (tmp_path / "run_ledger.json").exists()


def test_mock_once_run_records_sentinel_attrition_and_cannot_rerun(
    tmp_path: Path,
) -> None:
    nwis_body = _nwis_payload()
    foen_body = _foen_payload()
    refs = [
        _reference("usgs_nwis", nwis_body, network="huc8_x", site="01234567"),
        _reference("foen", foen_body, network="foen_x", site="2018", year=2020),
    ]
    reader = MemorySealedObjectReader(
        {ref.key: body for ref, body in zip(refs, [nwis_body, foen_body])}
    )
    manifest = evaluate_with_injected_reader(
        _authorized_preflight(),
        references=refs,
        reader=reader,
        output_dir=tmp_path,
        fixture_execution=True,
    )
    assert manifest["formal_evidence"] is False
    assert manifest["n_objects_read_once"] == 2
    qc = (tmp_path / "sealed_station_qc.csv").read_text(encoding="utf-8")
    assert "rejected_sentinel" in qc
    attrition = (tmp_path / "sealed_network_attrition.csv").read_text(encoding="utf-8")
    assert "fewer_than_3_qc_accepted_stations" in attrition
    assert manifest["v4_bindings"]["v4_workload"]["sha256"] == "a" * 64
    with pytest.raises(SealedEvaluatorError, match="rerun forbidden"):
        evaluate_with_injected_reader(
            _authorized_preflight(),
            references=refs,
            reader=MemorySealedObjectReader({}),
            output_dir=tmp_path,
            fixture_execution=True,
        )


def test_failure_is_written_nonretryable_before_first_read(tmp_path: Path) -> None:
    body = _nwis_payload()
    ref = _reference("usgs_nwis", body, network="huc8_x", site="01234567")
    bad = SealedObjectRef(**{**ref.__dict__, "expected_sha256": "0" * 64})
    with pytest.raises(SealedEvaluatorError, match="SHA-256 mismatch"):
        evaluate_with_injected_reader(
            _authorized_preflight(),
            references=[bad],
            reader=MemorySealedObjectReader({bad.key: body}),
            output_dir=tmp_path,
            fixture_execution=True,
        )
    ledger = json.loads((tmp_path / "run_ledger.json").read_text())
    assert ledger["status"] == "failed_nonretryable"
    assert ledger["rerun_permitted"] is False


def test_non_mock_reader_is_refused_even_after_authorized_preflight(
    tmp_path: Path,
) -> None:
    class PathlessReader:
        def read_object(self, reference: SealedObjectRef) -> bytes:
            raise AssertionError(reference)

    with pytest.raises(SealedEvaluatorError, match="production sealed reader"):
        evaluate_with_injected_reader(
            _authorized_preflight(),
            references=[],
            reader=PathlessReader(),
            output_dir=tmp_path,
            fixture_execution=True,
        )
    assert not (tmp_path / "run_ledger.json").exists()
