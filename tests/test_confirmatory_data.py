from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from stream_recoverability.data import confirmatory as external
from stream_recoverability.data.confirmatory import (
    CONFIRMATORY_DATA_VERSION,
    DH_INTERPRETATION,
    FINALIZED_MODEL_ROSTER_SCHEMA_VERSION,
    FROZEN_SITE_IDS,
    FROZEN_VARIABLES,
    FT3_S_TO_M3_S,
    FT_TO_M,
    HTTPResponse,
    OGCCollectionResult,
    assemble_confirmatory_frames,
    build_confirmatory_data,
    build_confirmatory_request_plan,
    fetch_ogc_feature_collection,
    load_confirmatory_protocol,
    load_finalized_model_roster,
    parse_usgs_daily_values,
    strict_json_loads,
    write_immutable_request_plan,
)
from stream_recoverability.experiments.contracts import build_design_contract

DESIGN = Path("configs/design_freeze_v1.yaml")
STUDY_MANIFEST = Path("study_manifest.yaml")
EXPERIMENT_CONFIG = Path("configs/experiments.yaml")
SELECTION_VERSION_MANIFEST = Path("data_versions/published_v1/version_manifest.json")


def _write_finalized_roster(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, suffix in (
        ("ranking", ".csv"),
        ("stage2_selection", ".csv"),
        ("go_no_go", ".json"),
    ):
        path = tmp_path / f"{name}{suffix}"
        path.write_text(f"frozen validation artifact: {name}\n", encoding="utf-8")
        artifacts[name] = {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    contract = build_design_contract(
        design_path=DESIGN,
        manifest_path=STUDY_MANIFEST,
        experiment_config_path=EXPERIMENT_CONFIG,
        data_version="published_v1",
        evaluation_split="validation",
        data_version_manifest_path=SELECTION_VERSION_MANIFEST,
    )
    document = {
        "schema_version": FINALIZED_MODEL_ROSTER_SCHEMA_VERSION,
        "finalized": True,
        "evaluation_split": "validation",
        "evidence_role": "model_selection_only",
        "formal_evidence": False,
        "selected_models": ["linear", "proposed"],
        "best_traditional_model": "linear",
        "proposed_decision": "include_proposed_formally",
        "artifacts": artifacts,
        **contract,
    }
    roster = tmp_path / "finalized_model_roster.json"
    roster.write_text(json.dumps(document), encoding="utf-8")
    return roster, document


def _json_response(
    url: str, payload: dict[str, Any], *, nasa: bool = False
) -> HTTPResponse:
    return HTTPResponse(
        url=url,
        status=200,
        headers={
            "Content-Type": "application/json" if nasa else "application/geo+json"
        },
        body=json.dumps(payload, separators=(",", ":")).encode(),
    )


def _feature_collection(
    features: list[dict[str, Any]], *, next_url: str | None = None
) -> dict[str, Any]:
    links: list[dict[str, str]] = []
    if next_url is not None:
        links.append({"rel": "next", "href": next_url})
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
        "links": links,
    }


def _point_feature(
    feature_id: str, properties: dict[str, Any], longitude: float, latitude: float
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": feature_id,
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
    }


class FrozenMockFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.coordinates = {
            site_id: (-84.10 + index * 0.01, 34.10 - index * 0.01)
            for index, site_id in enumerate(FROZEN_SITE_IDS)
        }

    def __call__(self, url: str, headers: dict[str, str]) -> HTTPResponse:
        self.calls.append((url, dict(headers)))
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc == "power.larc.nasa.gov":
            longitude = float(query["longitude"][0])
            latitude = float(query["latitude"][0])
            payload = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude, 250.0],
                },
                "header": {
                    "title": "NASA/POWER Source Native Resolution Daily Data",
                    "api": {"version": "test", "name": "POWER Daily API"},
                    "sources": ["MERRA2", "POWER"],
                    "fill_value": -999.0,
                    "time_standard": "UTC",
                    "start": "20120101",
                    "end": "20251231",
                },
                "parameters": {
                    spec.provider_code: {
                        "units": spec.source_unit,
                        "longname": f"mock {spec.provider_code}",
                    }
                    for spec in external.METEOROLOGY_SPECS
                },
                "properties": {
                    "parameter": {
                        spec.provider_code: {
                            "20120101": float(index + 1),
                            "20230101": (
                                -999.0
                                if spec.provider_code == "ALLSKY_SFC_SW_DWN"
                                and longitude == self.coordinates[FROZEN_SITE_IDS[0]][0]
                                else float(index + 2)
                            ),
                        }
                        for index, spec in enumerate(external.METEOROLOGY_SPECS)
                    }
                },
                "messages": [],
            }
            return _json_response(url, payload, nasa=True)

        if "monitoring-locations" in parsed.path:
            provider_id = query["id"][0]
            site_id = provider_id.removeprefix("USGS-")
            longitude, latitude = self.coordinates[site_id]
            properties = {
                "id": provider_id,
                "agency_code": "USGS",
                "agency_name": "U.S. Geological Survey",
                "monitoring_location_number": site_id,
                "monitoring_location_name": f"Mock site {site_id}",
                "site_type": "Stream",
                "state_name": "Georgia",
            }
            return _json_response(
                url,
                _feature_collection(
                    [_point_feature(provider_id, properties, longitude, latitude)]
                ),
            )

        site_id = query["monitoring_location_id"][0].removeprefix("USGS-")
        parameter = query["parameter_code"][0]
        spec = next(
            value
            for value in external.HYDROLOGY_SPECS
            if value.provider_code == parameter
        )
        series_id = f"series-{site_id}-{parameter}"
        longitude, latitude = self.coordinates[site_id]
        if "time-series-metadata" in parsed.path:
            properties = {
                "id": series_id,
                "unit_of_measure": spec.source_unit,
                "parameter_name": f"mock {spec.variable}",
                "parameter_code": parameter,
                "statistic_id": "00003",
                "monitoring_location_id": f"USGS-{site_id}",
                "begin": "2012-01-01",
                "end": "2025-12-31",
                "primary": "Primary",
            }
            return _json_response(
                url,
                _feature_collection(
                    [_point_feature(series_id, properties, longitude, latitude)]
                ),
            )

        dates_and_status = [("2012-01-01", "Approved")]
        if site_id == FROZEN_SITE_IDS[0] and parameter == "00060":
            dates_and_status.append(("2023-01-01", "Provisional"))
        features = []
        for row_index, (date, approval) in enumerate(dates_and_status):
            raw = {"00010": "10.5", "00060": "100", "00065": "3.5"}[parameter]
            properties = {
                "time_series_id": series_id,
                "monitoring_location_id": f"USGS-{site_id}",
                "parameter_code": parameter,
                "statistic_id": "00003",
                "time": date,
                "value": raw,
                "unit_of_measure": spec.source_unit,
                "approval_status": approval,
                "qualifier": (
                    ["Estimated"]
                    if site_id == FROZEN_SITE_IDS[0] and parameter == "00010"
                    else None
                ),
                "last_modified": "2026-01-01T00:00:00+00:00",
            }
            features.append(
                _point_feature(
                    f"daily-{site_id}-{parameter}-{row_index}",
                    properties,
                    longitude,
                    latitude,
                )
            )
        return _json_response(url, _feature_collection(features))


def test_protocol_and_plan_are_exact_and_network_free(tmp_path: Path) -> None:
    protocol = load_confirmatory_protocol(DESIGN)
    assert protocol.site_ids == FROZEN_SITE_IDS
    assert [
        (period.label, period.start, period.end) for period in protocol.periods
    ] == [
        ("train", "2012-01-01", "2020-12-31"),
        ("validation", "2021-01-01", "2022-12-31"),
        ("confirmatory", "2023-01-01", "2025-12-31"),
    ]
    plan = build_confirmatory_request_plan(protocol)
    assert plan["initial_request_count"] == 40
    requests = plan["initial_requests"]
    assert (
        sum(row["request_kind"] == "monitoring_location_metadata" for row in requests)
        == 5
    )
    assert sum(row["request_kind"] == "time_series_metadata" for row in requests) == 15
    assert sum(row["request_kind"] == "daily_values" for row in requests) == 15
    assert (
        sum(row["request_kind"] == "daily_point_meteorology" for row in requests) == 5
    )
    daily = next(row for row in requests if row["request_kind"] == "daily_values")
    assert "statistic_id=00003" in daily["url"]
    assert "datetime=2012-01-01/2025-12-31" in daily["url"]
    power = next(
        row for row in requests if row["request_kind"] == "daily_point_meteorology"
    )
    assert "community=AG" in power["url"]
    assert "time-standard=UTC" in power["url"]
    assert "ALLSKY_SFC_SW_DWN" in power["url"]
    assert len(plan["plan_sha256"]) == 64

    output = tmp_path / "request_plan.json"
    write_immutable_request_plan(plan, output)
    assert json.loads(output.read_text())["plan_sha256"] == plan["plan_sha256"]
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_immutable_request_plan(plan, output)


def test_changed_design_freeze_is_rejected(tmp_path: Path) -> None:
    document = yaml.safe_load(DESIGN.read_text())
    document["confirmatory_dataset"]["frozen_external_protocol"]["site_ids"][0] = (
        "00000000"
    )
    changed = tmp_path / "changed.yaml"
    changed.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError, match="site_ids"):
        load_confirmatory_protocol(changed)


def test_usgs_paging_follows_exact_next_and_hashes_raw_exchange(
    tmp_path: Path,
) -> None:
    initial = (
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items?"
        "f=json&limit=1&monitoring_location_id=USGS-02334430&"
        "parameter_code=00010&statistic_id=00003&"
        "datetime=2012-01-01/2025-12-31"
    )
    next_url = initial + "&offset=1"
    first = _point_feature("one", {"example": 1}, -84.0, 34.0)
    second = _point_feature("two", {"example": 2}, -84.0, 34.0)
    calls: list[tuple[str, dict[str, str]]] = []

    def fetcher(url: str, headers: dict[str, str]) -> HTTPResponse:
        calls.append((url, dict(headers)))
        payload = (
            _feature_collection([first], next_url=next_url)
            if url == initial
            else _feature_collection([second])
        )
        return _json_response(url, payload)

    raw_root = tmp_path / "staging" / "raw"
    result = fetch_ogc_feature_collection(
        initial,
        request_kind="daily_values",
        site_id="02334430",
        variable="T",
        raw_root=raw_root,
        artifact_prefix="usgs/daily/02334430/T",
        fetcher=fetcher,
        api_key="super-secret",
    )
    assert [url for url, _ in calls] == [initial, next_url]
    assert all(headers["X-Api-Key"] == "super-secret" for _, headers in calls)
    assert [feature["id"] for feature in result.features] == ["one", "two"]
    assert len(result.request_records) == 2
    for record in result.request_records:
        request_path = tmp_path / "staging" / record["request_artifact"]
        response_path = tmp_path / "staging" / record["response_artifact"]
        assert (
            hashlib.sha256(request_path.read_bytes()).hexdigest()
            == record["request_sha256"]
        )
        assert (
            hashlib.sha256(response_path.read_bytes()).hexdigest()
            == record["response_sha256"]
        )
        assert b"super-secret" not in request_path.read_bytes()


def test_paging_rejects_filter_changes_cycles_and_duplicate_feature_ids(
    tmp_path: Path,
) -> None:
    initial = (
        "https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items?"
        "monitoring_location_id=USGS-02334430&parameter_code=00010"
    )
    changed = initial.replace("00010", "00060") + "&offset=1"

    def changed_fetcher(url: str, headers: dict[str, str]) -> HTTPResponse:
        del headers
        return _json_response(
            url,
            _feature_collection(
                [_point_feature("one", {}, -84.0, 34.0)], next_url=changed
            ),
        )

    with pytest.raises(ValueError, match="changed frozen query"):
        fetch_ogc_feature_collection(
            initial,
            request_kind="daily_values",
            site_id="02334430",
            variable="T",
            raw_root=tmp_path / "one" / "raw",
            artifact_prefix="x",
            fetcher=changed_fetcher,
        )

    next_url = initial + "&offset=1"
    call = 0

    def duplicate_fetcher(url: str, headers: dict[str, str]) -> HTTPResponse:
        nonlocal call
        del headers
        call += 1
        return _json_response(
            url,
            _feature_collection(
                [_point_feature("same", {}, -84.0, 34.0)],
                next_url=next_url if call == 1 else None,
            ),
        )

    with pytest.raises(ValueError, match="duplicate USGS feature id"):
        fetch_ogc_feature_collection(
            initial,
            request_kind="daily_values",
            site_id="02334430",
            variable="T",
            raw_root=tmp_path / "two" / "raw",
            artifact_prefix="x",
            fetcher=duplicate_fetcher,
        )


def _daily_result(
    spec: external.ExternalVariableSpec, rows: list[dict[str, Any]]
) -> OGCCollectionResult:
    features = []
    for index, row in enumerate(rows):
        properties = {
            "time_series_id": "series",
            "monitoring_location_id": "USGS-02334430",
            "parameter_code": spec.provider_code,
            "statistic_id": "00003",
            "time": row["date"],
            "value": row["value"],
            "unit_of_measure": spec.source_unit,
            "approval_status": row["approval"],
            "qualifier": row.get("qualifier"),
            "last_modified": "2026-01-01T00:00:00Z",
        }
        features.append(_point_feature(f"feature-{index}", properties, -84.0, 34.0))
    provenance = tuple(
        {
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "response_artifact": "raw/response.json",
            "page_number": 1,
        }
        for _ in features
    )
    return OGCCollectionResult(tuple(features), provenance, ())


def test_approved_estimated_and_provisional_rules_and_exact_conversions() -> None:
    flow = next(spec for spec in external.HYDROLOGY_SPECS if spec.variable == "F")
    parsed = parse_usgs_daily_values(
        "02334430",
        flow,
        _daily_result(
            flow,
            [
                {
                    "date": "2012-01-01",
                    "value": "100",
                    "approval": "Approved",
                    "qualifier": ["Estimated"],
                },
                {
                    "date": "2023-01-01",
                    "value": "200",
                    "approval": "Provisional",
                },
            ],
        ),
        allowed_time_series_ids={"series"},
        start="2012-01-01",
        end="2025-12-31",
    )
    approved, provisional = parsed.iloc[0], parsed.iloc[1]
    assert approved["raw_value"] == 100
    assert approved["value"] == pytest.approx(100 * FT3_S_TO_M3_S, abs=0)
    assert bool(approved["estimated_qualifier"])
    assert approved["qc_status"] == "approved_estimated"
    assert provisional["raw_value"] == 200
    assert np.isnan(provisional["value"])
    assert not bool(provisional["quality_approved"])
    assert provisional["qc_status"] == "excluded_provisional"

    level = next(spec for spec in external.HYDROLOGY_SPECS if spec.variable == "L")
    level_row = parse_usgs_daily_values(
        "02334430",
        level,
        _daily_result(
            level,
            [{"date": "2012-01-01", "value": "3.5", "approval": "Approved"}],
        ),
        allowed_time_series_ids={"series"},
        start="2012-01-01",
        end="2025-12-31",
    ).iloc[0]
    assert level_row["raw_value"] == 3.5
    assert level_row["value"] == pytest.approx(3.5 * FT_TO_M, abs=0)


def test_duplicate_and_conflicting_observations_are_rejected() -> None:
    temperature = next(
        spec for spec in external.HYDROLOGY_SPECS if spec.variable == "T"
    )
    duplicated = _daily_result(
        temperature,
        [
            {"date": "2012-01-01", "value": "10", "approval": "Approved"},
            {"date": "2012-01-01", "value": "11", "approval": "Approved"},
        ],
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        parse_usgs_daily_values(
            "02334430",
            temperature,
            duplicated,
            allowed_time_series_ids={"series"},
            start="2012-01-01",
            end="2025-12-31",
        )
    with pytest.raises(ValueError, match="duplicate key"):
        strict_json_loads(b'{"value":1,"value":2}')


def test_alignment_has_complete_frozen_axes_splits_and_dh_proxy() -> None:
    protocol = load_confirmatory_protocol(DESIGN)
    empty = pd.DataFrame()
    long_data, wide = assemble_confirmatory_frames(empty, empty, protocol)
    expected_days = len(pd.date_range("2012-01-01", "2025-12-31", freq="D"))
    assert len(long_data) == expected_days * len(FROZEN_SITE_IDS) * len(
        FROZEN_VARIABLES
    )
    assert len(wide) == expected_days
    assert long_data["split"].value_counts().to_dict() == {
        "train": 3288 * 5 * 8,
        "validation": 730 * 5 * 8,
        "confirmatory": 1096 * 5 * 8,
    }
    dh = long_data["variable"].eq("DH")
    assert long_data.loc[dh, "interpretation"].eq(DH_INTERPRETATION).all()
    assert long_data.loc[dh, "raw_name"].eq("ALLSKY_SFC_SW_DWN").all()
    assert not long_data["quality_approved"].any()
    assert "02334430_T" in wide
    assert "02337170_DH" in wide


@pytest.mark.parametrize(
    ("problem", "message"),
    [
        ("schema", "schema_version"),
        ("not_finalized", "finalized=true"),
        ("split", "evaluation_split=validation"),
        ("formal", "formal_evidence=false"),
        ("data_version", "contract mismatch"),
        ("design_hash", "contract mismatch"),
        ("empty_models", "non-empty selected_models"),
        ("decision", "inconsistent"),
        ("artifact_hash", "SHA-256 does not match"),
        ("unexpected_performance", "fields differ from the frozen schema"),
    ],
)
def test_finalized_roster_gate_fails_closed_before_network_or_directory_creation(
    tmp_path: Path,
    problem: str,
    message: str,
) -> None:
    roster, document = _write_finalized_roster(tmp_path)
    if problem == "schema":
        document["schema_version"] = "legacy_selection_manifest"
    elif problem == "not_finalized":
        document["finalized"] = False
    elif problem == "split":
        document["evaluation_split"] = "development_test"
    elif problem == "formal":
        document["formal_evidence"] = True
    elif problem == "data_version":
        document["data_version"] = CONFIRMATORY_DATA_VERSION
    elif problem == "design_hash":
        document["design_hash"] = "0" * 64
    elif problem == "empty_models":
        document["selected_models"] = []
    elif problem == "decision":
        document["proposed_decision"] = "framework_only"
    elif problem == "artifact_hash":
        document["artifacts"]["ranking"]["sha256"] = "0" * 64
    else:
        document["confirmatory_performance"] = {"MAE": 0.0}
    roster.write_text(json.dumps(document), encoding="utf-8")
    fetch_calls = 0

    def forbidden_fetcher(url: str, headers: dict[str, str]) -> HTTPResponse:
        nonlocal fetch_calls
        del url, headers
        fetch_calls += 1
        raise AssertionError("network must remain closed")

    output = tmp_path / "uncreated-parent" / "external"
    with pytest.raises((TypeError, ValueError), match=message):
        build_confirmatory_data(
            DESIGN,
            output,
            finalized_model_roster_path=roster,
            fetcher=forbidden_fetcher,
        )
    assert fetch_calls == 0
    assert not output.parent.exists()


def test_stage2_selection_manifest_cannot_unlock_confirmatory_values(
    tmp_path: Path,
) -> None:
    roster, document = _write_finalized_roster(tmp_path)
    document["schema_version"] = "stage2_finalist_selection_v1"
    document["command"] = "select-finalists"
    document.pop("finalized")
    roster.write_text(json.dumps(document), encoding="utf-8")
    output = tmp_path / "uncreated" / "external"

    with pytest.raises(ValueError, match="finalized_model_roster_v1"):
        build_confirmatory_data(
            DESIGN,
            output,
            finalized_model_roster_path=roster,
        )
    assert not output.parent.exists()


def test_docs_only_provenance_change_does_not_invalidate_canonical_roster(
    tmp_path: Path,
) -> None:
    roster, document = _write_finalized_roster(tmp_path)
    document["code_provenance"]["git_commit"] = "f" * 40
    document["code_provenance"]["status"] = "historical_frozen_audit"
    roster.write_text(json.dumps(document), encoding="utf-8")

    validated = load_finalized_model_roster(roster)

    assert "code_provenance" not in validated.selection_contract
    assert validated.selection_contract["code_identity"] == document["code_identity"]
    assert validated.selection_code_provenance["git_commit"] == "f" * 40


def test_selection_data_version_identity_is_required_before_access(
    tmp_path: Path,
) -> None:
    roster, _ = _write_finalized_roster(tmp_path)
    output = tmp_path / "uncreated" / "external"

    with pytest.raises(FileNotFoundError, match="data-version manifest"):
        build_confirmatory_data(
            DESIGN,
            output,
            finalized_model_roster_path=roster,
            selection_data_version_manifest_path=tmp_path / "missing-version.json",
        )
    assert not output.parent.exists()

    with pytest.raises(ValueError, match="published_v1"):
        build_confirmatory_data(
            DESIGN,
            output,
            finalized_model_roster_path=roster,
            selection_data_version="b1_no_level_v1",
        )
    assert not output.parent.exists()


def test_full_mocked_build_is_atomic_immutable_and_provenance_complete(
    tmp_path: Path,
) -> None:
    fetcher = FrozenMockFetcher()
    roster, roster_document = _write_finalized_roster(tmp_path)
    validated_roster = load_finalized_model_roster(roster)
    assert validated_roster.selected_models == ("linear", "proposed")
    output = tmp_path / "external_v1"
    manifest = build_confirmatory_data(
        DESIGN,
        output,
        finalized_model_roster_path=roster,
        fetcher=fetcher,
        usgs_api_key="not-persisted-secret",
    )
    assert len(fetcher.calls) == 40
    assert manifest["request_count"] == 40
    assert manifest["raw_response_count"] == 40
    assert manifest["performance_metrics_computed"] is False
    assert manifest["confirmatory_evaluation_executed"] is False
    assert manifest["dh_interpretation"] == DH_INTERPRETATION
    gate = manifest["confirmatory_access_gate"]
    assert gate["manifest_path"] == str(roster.resolve())
    assert gate["manifest_sha256"] == hashlib.sha256(roster.read_bytes()).hexdigest()
    assert gate["selected_models"] == roster_document["selected_models"]
    assert gate["best_traditional_model"] == "linear"
    assert gate["proposed_decision"] == "include_proposed_formally"
    assert gate["selection_contract"]["data_version"] == "published_v1"
    assert gate["selection_contract"]["evaluation_split"] == "validation"
    assert (
        gate["selection_data_version_manifest"]["sha256"]
        == hashlib.sha256(SELECTION_VERSION_MANIFEST.read_bytes()).hexdigest()
    )
    assert set(gate["artifacts"]) == {"ranking", "stage2_selection", "go_no_go"}
    expected_files = {
        "daily_long.parquet",
        "daily_wide.parquet",
        "splits/train.parquet",
        "splits/validation.parquet",
        "splits/confirmatory.parquet",
        "metadata/site_metadata.parquet",
        "metadata/time_series_metadata.parquet",
        "metadata/power_point_metadata.parquet",
        "metadata/availability_report.parquet",
        "metadata/availability_report.json",
        "metadata/quality_detail.parquet",
        "metadata/quality_report.json",
        "metadata/request_log.json",
        "metadata/request_plan.json",
        "provenance_manifest.json",
        "provenance_manifest.json.sha256",
    }
    assert all((output / relative).is_file() for relative in expected_files)
    long_data = pd.read_parquet(output / "daily_long.parquet")
    wide = pd.read_parquet(output / "daily_wide.parquet")
    assert len(long_data) == 204_560
    assert len(wide) == 5_114
    assert set(long_data["data_version"]) == {CONFIRMATORY_DATA_VERSION}
    estimated = long_data.query(
        "site_id == '02334430' and variable == 'T' and date == '2012-01-01'"
    ).iloc[0]
    assert bool(estimated["quality_approved"])
    assert bool(estimated["estimated_qualifier"])
    provisional = long_data.query(
        "site_id == '02334430' and variable == 'F' and date == '2023-01-01'"
    ).iloc[0]
    assert provisional["raw_value"] == 100
    assert np.isnan(provisional["value"])
    assert provisional["qc_status"] == "excluded_provisional"
    flow = long_data.query(
        "site_id == '02334430' and variable == 'F' and date == '2012-01-01'"
    ).iloc[0]
    assert flow["raw_value"] == 100
    assert flow["value"] == pytest.approx(100 * FT3_S_TO_M3_S, abs=0)
    assert len(pd.read_parquet(output / "metadata/site_metadata.parquet")) == 5
    assert len(pd.read_parquet(output / "metadata/time_series_metadata.parquet")) == 15
    assert len(pd.read_parquet(output / "metadata/power_point_metadata.parquet")) == 5
    availability = pd.read_parquet(output / "metadata/availability_report.parquet")
    assert len(availability) == 120
    quality = json.loads((output / "metadata/quality_report.json").read_text())
    assert quality["provisional_excluded_rows"] == 1
    assert quality["estimated_approved_rows"] == 1
    request_log = json.loads((output / "metadata/request_log.json").read_text())
    assert request_log["api_key_values_persisted"] is False
    assert (
        "not-persisted-secret" not in (output / "metadata/request_log.json").read_text()
    )
    for relative, identity in manifest["artifacts"].items():
        assert (
            hashlib.sha256((output / relative).read_bytes()).hexdigest()
            == identity["sha256"]
        )
    stored_manifest = output / "provenance_manifest.json"
    assert (
        hashlib.sha256(stored_manifest.read_bytes()).hexdigest()
        == (output / "provenance_manifest.json.sha256").read_text().strip()
    )

    calls_before = len(fetcher.calls)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build_confirmatory_data(
            DESIGN,
            output,
            finalized_model_roster_path=roster,
            fetcher=fetcher,
        )
    assert len(fetcher.calls) == calls_before


def test_access_gate_and_failed_fetch_leave_no_output(tmp_path: Path) -> None:
    calls = 0

    def forbidden_fetcher(url: str, headers: dict[str, str]) -> HTTPResponse:
        nonlocal calls
        del url, headers
        calls += 1
        raise RuntimeError("synthetic failure")

    locked = tmp_path / "locked-parent" / "locked"
    with pytest.raises(FileNotFoundError, match="finalized model roster"):
        build_confirmatory_data(
            DESIGN,
            locked,
            finalized_model_roster_path=tmp_path / "missing-roster.json",
            fetcher=forbidden_fetcher,
        )
    assert calls == 0 and not locked.parent.exists()

    roster, _ = _write_finalized_roster(tmp_path)
    failed = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="synthetic failure"):
        build_confirmatory_data(
            DESIGN,
            failed,
            finalized_model_roster_path=roster,
            fetcher=forbidden_fetcher,
        )
    assert calls == 1 and not failed.exists()
    assert not list(tmp_path.glob(".failed.staging.*"))
    assert not (tmp_path / ".failed.build.lock").exists()


def test_cli_build_requires_finalized_roster_before_network_or_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "must-not-exist"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/19_build_confirmatory_data.py",
            "build",
            "--design",
            str(DESIGN),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--finalized-model-roster" in result.stderr
    assert not output.exists()
