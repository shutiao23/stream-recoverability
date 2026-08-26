from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pandas as pd

from stream_recoverability.data import confirmatory as provider
from stream_recoverability.data.t2_information_acquisition import (
    PILOT_NETWORK_ID,
    build_request_plan,
    load_bounded_pilot_plan,
    run_bounded_pilot,
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


class PilotFetcher:
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
            parameters = {}
            values = {}
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
        spec = next(s for s in provider.HYDROLOGY_SPECS if s.provider_code == code)
        series_id = f"series-{site_id}-{code}"
        if "time-series-metadata" in parsed.path:
            # Exercise honest source absence without widening the pilot.
            if site_id == "01095434" and spec.variable == "L":
                return _response(url, _collection([]))
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
        features = []
        for ordinal, (date, approval) in enumerate(
            [(start, "Approved"), (end, "Provisional")]
        ):
            features.append(
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
            )
        return _response(url, _collection(features))


def test_plan_is_bounded_to_first_complete_development_network() -> None:
    plan = load_bounded_pilot_plan(ROOT)
    assert plan.network_id == PILOT_NETWORK_ID
    assert [site.site_id for site in plan.sites] == [
        "01095220",
        "01095375",
        "01095434",
    ]
    request_plan = build_request_plan(plan)
    assert request_plan["n_networks"] == 1
    assert request_plan["n_initial_requests"] == 15
    assert request_plan["temperature_columns_read"] == []
    assert request_plan["sealed_paths_traversed"] is False


def test_dry_run_opens_no_provider_response(tmp_path: Path) -> None:
    fetcher = PilotFetcher()
    manifest = run_bounded_pilot(ROOT, tmp_path, fetcher=fetcher)
    assert manifest["status"] == "dry_run"
    assert manifest["passed"] is False
    assert manifest["provider_responses_opened"] is False
    assert fetcher.calls == []


def test_execute_preserves_provider_rejections_and_missing_source(tmp_path: Path) -> None:
    fetcher = PilotFetcher()
    manifest = run_bounded_pilot(ROOT, tmp_path, execute=True, fetcher=fetcher)
    assert manifest["network_id"] == PILOT_NETWORK_ID
    assert manifest["status"] == "materialized_partial"
    assert manifest["passed"] is False
    assert manifest["performance_metrics_computed"] is False
    assert manifest["sealed_temperature_records_read"] is False
    assert manifest["n_raw_responses"] == 14
    assert manifest["raw_response_hashes_complete_for_logged_responses"] is True

    daily = pd.read_parquet(tmp_path / "daily_long_auxiliary.parquet")
    assert set(daily["variable"]) == {"Ta", "P", "W", "RH", "Rs", "F", "L"}
    assert "T" not in set(daily["variable"])
    power_fill = daily.loc[
        daily["variable"].eq("Ta") & daily["qc_status"].eq("provider_fill_value")
    ]
    assert len(power_fill) == 3
    assert power_fill["value"].isna().all()
    provisional = daily.loc[daily["qc_status"].eq("excluded_provisional")]
    assert len(provisional) == 5
    assert provisional["value"].isna().all()
    assert not provisional["quality_approved"].astype(bool).any()

    failures = json.loads((tmp_path / "source_failures.json").read_text())
    assert failures == [
        {
            "error": None,
            "error_type": None,
            "provider": "usgs_ogc_daily",
            "site_id": "01095434",
            "status": "source_unavailable_no_daily_mean_series",
            "variable": "L",
        }
    ]
    coverage = pd.read_csv(tmp_path / "coverage.csv")
    missing = coverage.loc[
        coverage["site_id"].astype(str).str.zfill(8).eq("01095434")
        & coverage["variable"].eq("L")
    ].iloc[0]
    assert missing["source_status"] == "failed_or_unavailable"
    assert missing["n_provider_rows"] == 0
