from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data import confirmatory as provider
from stream_recoverability.data.t2_information_corpus_acquisition import (
    EXPECTED_NETWORKS,
    build_network_request_plan,
    load_corpus_plan,
    plan_as_dict,
    run_corpus_acquisition,
    select_networks,
)

ROOT = Path(__file__).resolve().parents[1]


def _response(url: str, payload: object) -> provider.HTTPResponse:
    return provider.HTTPResponse(
        url=url,
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload, sort_keys=True).encode(),
    )


def _point(feature_id: str, properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": feature_id,
        "properties": properties,
        "geometry": {"type": "Point", "coordinates": [-71.8, 42.4]},
    }


def _collection(features: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "numberReturned": len(features),
        "features": features,
        "links": [],
    }


class CorpusFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        del headers
        self.calls.append(url)
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc == "power.larc.nasa.gov":
            start = query["start"][0]
            end = query["end"][0]
            parameters: dict[str, object] = {}
            values: dict[str, object] = {}
            for offset, spec in enumerate(provider.METEOROLOGY_SPECS):
                parameters[spec.provider_code] = {"units": spec.source_unit}
                values[spec.provider_code] = {
                    start: -999.0 if spec.variable == "Ta" else float(offset + 1),
                    end: float(offset + 2),
                }
            return _response(
                url,
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            float(query["longitude"][0]),
                            float(query["latitude"][0]),
                            100.0,
                        ],
                    },
                    "header": {
                        "api": {"name": "POWER", "version": "test"},
                        "sources": ["mock"],
                        "fill_value": -999.0,
                        "time_standard": "UTC",
                        "start": start,
                        "end": end,
                    },
                    "parameters": parameters,
                    "properties": {"parameter": values},
                    "messages": [],
                },
            )

        site_id = query["monitoring_location_id"][0].removeprefix("USGS-")
        code = query["parameter_code"][0]
        spec = next(item for item in provider.HYDROLOGY_SPECS if item.provider_code == code)
        series_id = f"series-{site_id}-{code}"
        if "time-series-metadata" in parsed.path:
            return _response(
                url,
                _collection(
                    [
                        _point(
                            series_id,
                            {
                                "id": series_id,
                                "monitoring_location_id": f"USGS-{site_id}",
                                "parameter_code": code,
                                "statistic_id": "00003",
                                "unit_of_measure": spec.source_unit,
                            },
                        )
                    ]
                ),
            )
        start, end = query["datetime"][0].split("/")
        features = [
            _point(
                f"daily-{site_id}-{code}-{ordinal}",
                {
                    "time_series_id": series_id,
                    "monitoring_location_id": f"USGS-{site_id}",
                    "parameter_code": code,
                    "statistic_id": "00003",
                    "time": date,
                    "value": "10.0",
                    "unit_of_measure": spec.source_unit,
                    "approval_status": approval,
                    "qualifier": ["Estimated"] if ordinal == 0 else None,
                },
            )
            for ordinal, (date, approval) in enumerate(
                [(start, "Approved"), (end, "Provisional")]
            )
        ]
        return _response(url, _collection(features))


def test_corpus_plan_is_exact_deterministic_open_failure_closure() -> None:
    first = load_corpus_plan(ROOT)
    second = load_corpus_plan(ROOT)
    assert first == second
    assert len(first.networks) == EXPECTED_NETWORKS == 67
    assert sum(len(network.sites) for network in first.networks) == 340
    assert {network.role for network in first.networks} == {"development", "validation"}
    assert all("sealed" not in network.source_key for network in first.networks)
    serialized = plan_as_dict(first)
    assert serialized["plan_sha256"] == first.plan_sha256
    assert serialized["temperature_columns_read"] == []
    assert serialized["sealed_paths_traversed"] is False
    assert serialized["performance_metrics_computed"] is False
    assert any(
        site.power_start == "1981-01-01"
        for network in first.networks
        for site in network.sites
    )


def test_request_plan_contains_only_M_and_H_provider_requests() -> None:
    network = load_corpus_plan(ROOT).networks[0]
    request_plan = build_network_request_plan(network)
    assert request_plan["n_initial_requests"] == len(network.sites) * 5
    assert {row["variable"] for row in request_plan["requests"]} == {
        None,
        "F",
        "L",
    }
    assert request_plan["temperature_columns_read"] == []


def test_execute_requires_exact_bounded_or_all_acknowledgement(tmp_path: Path) -> None:
    plan = load_corpus_plan(ROOT)
    assert len(select_networks(plan, max_networks=1)) == 1
    with pytest.raises(ValueError, match="explicit bounded selection"):
        run_corpus_acquisition(ROOT, tmp_path, execute=True)
    with pytest.raises(ValueError, match="acknowledge-network-count 1"):
        run_corpus_acquisition(
            ROOT,
            tmp_path,
            execute=True,
            max_networks=1,
            acknowledged_network_count=2,
        )
    with pytest.raises(ValueError, match="acknowledge-all-network-count 67"):
        run_corpus_acquisition(
            ROOT,
            tmp_path,
            execute=True,
            all_networks=True,
            acknowledge_all_network_count=66,
        )


def test_dry_run_opens_no_provider_and_writes_global_attrition(tmp_path: Path) -> None:
    fetcher = CorpusFetcher()
    manifest = run_corpus_acquisition(ROOT, tmp_path, fetcher=fetcher)
    assert manifest["status"] == "dry_run"
    assert manifest["n_networks_in_frozen_roster"] == 67
    assert manifest["n_sites_in_frozen_roster"] == 340
    assert manifest["provider_responses_opened"] is False
    assert manifest["passed"] is False
    assert fetcher.calls == []
    attrition = pd.read_csv(tmp_path / "global_attrition.csv")
    assert len(attrition) == 67
    assert set(attrition["materialization_status"]) == {"not_materialized"}


def test_one_network_execution_is_qc_audited_and_resumable(tmp_path: Path) -> None:
    network = load_corpus_plan(ROOT).networks[0]
    fetcher = CorpusFetcher()
    first = run_corpus_acquisition(
        ROOT,
        tmp_path,
        execute=True,
        network_ids=[network.network_id],
        acknowledged_network_count=1,
        request_interval_seconds=0,
        fetcher=fetcher,
    )
    assert first["n_networks_executed_now"] == 1
    assert first["n_networks_resumed"] == 0
    network_root = tmp_path / network.role / "networks" / network.network_id
    network_manifest = json.loads((network_root / "network_manifest.json").read_text())
    assert network_manifest["raw_response_hashes_complete_for_logged_responses"] is True
    assert network_manifest["performance_metrics_computed"] is False
    assert network_manifest["sealed_temperature_records_read"] is False
    assert network_manifest["passed"] is False
    daily = pd.read_parquet(network_root / "daily_long_auxiliary.parquet")
    assert set(daily["variable"]) == {"Ta", "P", "W", "RH", "Rs", "F", "L"}
    assert "T" not in set(daily["variable"])
    assert "temperature_c" not in daily.columns
    assert daily.loc[daily["qc_status"].eq("provider_fill_value"), "value"].isna().all()
    assert daily.loc[daily["approval_status"].eq("Provisional"), "value"].isna().all()

    calls_after_first = len(fetcher.calls)
    second = run_corpus_acquisition(
        ROOT,
        tmp_path,
        execute=True,
        network_ids=[network.network_id],
        acknowledged_network_count=1,
        request_interval_seconds=0,
        fetcher=fetcher,
    )
    assert second["n_networks_executed_now"] == 0
    assert second["n_networks_resumed"] == 1
    assert len(fetcher.calls) == calls_after_first

    records = json.loads((network_root / "raw_request_log.json").read_text())
    raw_response = network_root / records[0]["response_artifact"]
    raw_response.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="raw response integrity failure"):
        run_corpus_acquisition(
            ROOT,
            tmp_path,
            execute=True,
            network_ids=[network.network_id],
            acknowledged_network_count=1,
            request_interval_seconds=0,
            fetcher=fetcher,
        )
