from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stream_recoverability.experiments.sealed_evaluator_scaffold import (
    FIXTURE_RESULT_SCHEMA,
    MemorySealedObjectReader,
    SealedEvaluatorError,
    SealedObjectRef,
    build_evaluator_preflight,
    evaluate_synthetic_fixture,
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
                    "variable": {
                        "variableCode": [{"value": "00010"}],
                        "unit": {"unitCode": "deg C"},
                        "options": {
                            "option": [
                                {"name": "Statistic", "optionCode": "00003"}
                            ]
                        },
                    },
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
        request_start=(f"{year:04d}-01-01T00:00:00Z" if year else "2020-01-01"),
        request_end=(
            f"{year + 1:04d}-01-01T00:00:00Z" if year else "2020-12-31"
        ),
        request_end_inclusive=year is None,
    )


def test_provider_parsers_are_strict_and_preserve_qc_codes() -> None:
    nwis = parse_huc8_nwis_response(_nwis_payload(), site_id="01234567")
    assert nwis["temperature_c"].tolist() == [12.5, -999999.0]
    assert nwis["approval_code"].tolist() == ["A", "A"]
    foen = parse_foen_response(_foen_payload(), site_id="2018")
    assert foen["approval_code"].tolist() == ["A", "P"]
    with pytest.raises(SealedEvaluatorError, match="station mismatch"):
        parse_foen_response(_foen_payload(), site_id="wrong")


def test_nwis_requires_daily_mean_celsius_and_locked_date_range() -> None:
    base = json.loads(_nwis_payload().decode())
    variable = base["value"]["timeSeries"][0]["variable"]
    variable["options"]["option"][0]["optionCode"] = "00001"
    with pytest.raises(SealedEvaluatorError, match="daily mean statistic 00003"):
        parse_huc8_nwis_response(json.dumps(base).encode(), site_id="01234567")

    variable["options"]["option"][0]["optionCode"] = "00003"
    variable["unit"]["unitCode"] = "deg F"
    with pytest.raises(SealedEvaluatorError, match="not Celsius"):
        parse_huc8_nwis_response(json.dumps(base).encode(), site_id="01234567")

    with pytest.raises(SealedEvaluatorError, match="precedes request range"):
        parse_huc8_nwis_response(
            _nwis_payload(),
            site_id="01234567",
            request_start="2021-01-01",
            request_end="2021-12-31",
        )


def test_foen_enforces_request_year_and_calendar_day_duplicate_rule() -> None:
    with pytest.raises(SealedEvaluatorError, match="precedes request range"):
        parse_foen_response(_foen_payload(), site_id="2018", request_year=2021)

    document = json.loads(_foen_payload().decode())
    rows = document["data"]["water"]["observations"]["data_1day_mean"]
    rows.append(dict(rows[0]))
    frame = parse_foen_response(
        json.dumps(document).encode(), site_id="2018", request_year=2020
    )
    assert len(frame) == 2
    rows[-1]["value"] = 99.0
    with pytest.raises(SealedEvaluatorError, match="conflicting duplicate"):
        parse_foen_response(
            json.dumps(document).encode(), site_id="2018", request_year=2020
        )


def test_repository_preflight_is_metadata_only_and_blocked_now() -> None:
    manifest = build_evaluator_preflight()
    assert manifest["authorized_for_object_reads"] is False
    assert manifest["evaluate_once_lock_claimed_by_preflight"] is False
    assert manifest["vault_path_resolved_or_statted"] is False
    assert manifest["sealed_objects_read"] == 0
    assert "evaluate_once_lock_missing_or_invalid" in manifest["blockers"]
    assert "production_reader_not_implemented" in manifest["blockers"]
    assert manifest["production_reader_available"] is False


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
    assert all(ref.request_start and ref.request_end for ref in references)


def test_registry_reference_replay_rejects_incomplete_readiness_inventory() -> None:
    readiness_path = (
        Path(__file__).resolve().parents[1]
        / "results/framework/t2_sealed_confirmatory_v1/preunseal_readiness_manifest.json"
    )
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness["sealed_registry_inventory"]["north_america_huc8"]["n_objects"] -= 1
    with pytest.raises(SealedEvaluatorError, match="differs from readiness"):
        registered_object_references(readiness)


def test_synthetic_fixture_records_sentinel_attrition_and_has_no_once_semantics(
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
    manifest = evaluate_synthetic_fixture(
        references=refs,
        reader=reader,
        output_dir=tmp_path,
    )
    assert manifest["manifest_schema"] == FIXTURE_RESULT_SCHEMA
    assert manifest["formal_evidence"] is False
    assert manifest["production_authorization_consumed"] is False
    assert manifest["production_evaluate_once_semantics"] is False
    assert manifest["n_synthetic_objects_read"] == 2
    qc = (tmp_path / "synthetic_station_qc.csv").read_text(encoding="utf-8")
    assert "rejected_sentinel" in qc
    attrition = (tmp_path / "synthetic_network_attrition.csv").read_text(
        encoding="utf-8"
    )
    assert "fewer_than_3_qc_accepted_stations" in attrition
    with pytest.raises(SealedEvaluatorError, match="fixture ledger already exists"):
        evaluate_synthetic_fixture(
            references=refs,
            reader=MemorySealedObjectReader({}),
            output_dir=tmp_path,
        )


def test_failure_is_written_nonretryable_before_first_read(tmp_path: Path) -> None:
    body = _nwis_payload()
    ref = _reference("usgs_nwis", body, network="huc8_x", site="01234567")
    bad = SealedObjectRef(**{**ref.__dict__, "expected_sha256": "0" * 64})
    with pytest.raises(SealedEvaluatorError, match="SHA-256 mismatch"):
        evaluate_synthetic_fixture(
            references=[bad],
            reader=MemorySealedObjectReader({bad.key: body}),
            output_dir=tmp_path,
        )
    ledger = json.loads((tmp_path / "synthetic_fixture_ledger.json").read_text())
    assert ledger["status"] == "synthetic_fixture_failed"
    assert ledger["production_authorization_consumed"] is False


def test_memory_reader_subclass_is_refused(tmp_path: Path) -> None:
    class MemoryReaderSubclass(MemorySealedObjectReader):
        pass

    with pytest.raises(SealedEvaluatorError, match="exact memory reader"):
        evaluate_synthetic_fixture(
            references=[],
            reader=MemoryReaderSubclass({}),
            output_dir=tmp_path,
        )
    assert not (tmp_path / "synthetic_fixture_ledger.json").exists()
