from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data import nldi_connectivity, t5_nldi_acquisition
from stream_recoverability.data.http_json import JsonHttpError
from stream_recoverability.data.t5_nldi_acquisition import (
    audit_plan_cache,
    build_open_target_plan,
    execute_missing_requests,
)


def _predictors(role: str = "development") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_id": ["huc8_a", "huc8_a"],
            "station_id": ["01000001", "01000001"],
            "role": [role, role],
            "n_donors": [2, 2],
            "donor_station_ids": ["01000002|01000003", "01000002|01000003"],
            "gap_length": [30, 90],
        }
    )


def _two_target_predictors() -> pd.DataFrame:
    first = _predictors()
    second = first.copy()
    second["network_id"] = "huc8_b"
    second["station_id"] = "02000001"
    second["donor_station_ids"] = "02000002|02000003"
    return pd.concat([first, second], ignore_index=True)


def _feature_collection() -> dict:
    return {"type": "FeatureCollection", "features": []}


def test_plan_is_two_directions_per_unique_open_target(tmp_path: Path) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)

    assert len(plan) == 2
    assert list(plan["request_ordinal"]) == [0, 1]
    assert list(plan["direction"]) == ["UM", "DM"]
    assert plan["endpoint"].str.endswith("?distance=200").all()


def test_plan_rejects_sealed_role(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-open roles"):
        build_open_target_plan(_predictors("sealed"), cache_dir=tmp_path)


def test_cache_audit_distinguishes_invalid_existing(tmp_path: Path) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)
    Path(plan.loc[0, "cache_path"]).write_text("{}", encoding="utf-8")
    Path(plan.loc[1, "cache_path"]).write_text(
        json.dumps(_feature_collection()), encoding="utf-8"
    )

    audit = audit_plan_cache(plan)

    assert list(audit["status"]) == ["invalid_existing_cache", "complete"]


def test_copied_unavailable_sidecar_is_identity_mismatch_and_blocks_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)
    source = plan.iloc[0]
    payload = {
        "schema_version": "t5_nldi_provider_unavailable_v1",
        "classification": "provider_confirmed_unavailable",
        "target_station_id": source["target_station_id"],
        "direction": source["direction"],
        "distance_km": int(source["distance_km"]),
        "http_status": 404,
        "endpoint": source["endpoint"],
    }
    for unavailable_path in plan["unavailable_path"]:
        path = Path(unavailable_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    audit = audit_plan_cache(plan)

    assert list(audit["status"]) == [
        "provider_confirmed_unavailable",
        "invalid_existing_unavailable_sidecar",
    ]
    called = False

    def forbidden_get(url: str, *, timeout: int) -> dict:
        nonlocal called
        called = True
        return _feature_collection()

    monkeypatch.setattr(t5_nldi_acquisition, "get_json", forbidden_get)
    with pytest.raises(RuntimeError, match="fail-closed invalid NLDI artifacts"):
        execute_missing_requests(
            plan,
            cache_dir=tmp_path,
            max_new_requests=1,
            request_interval_seconds=0,
        )
    assert called is False


def test_execution_resumes_only_missing_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)
    Path(plan.loc[0, "cache_path"]).write_text(
        json.dumps(_feature_collection()), encoding="utf-8"
    )
    called: list[str] = []

    def fake_get(url: str, *, timeout: int) -> dict:
        called.append(url)
        return _feature_collection()

    monkeypatch.setattr(t5_nldi_acquisition, "get_json", fake_get)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=2,
        request_interval_seconds=0,
    )

    assert len(called) == 1
    assert "/DM/" in called[0]
    assert len(log) == 1
    assert log.loc[0, "status"] == "complete"
    assert audit_plan_cache(plan)["status"].eq("complete").all()


def test_new_invalid_response_halts_without_caching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path).iloc[[0]]

    def fake_get(url: str, *, timeout: int) -> dict:
        return {}

    monkeypatch.setattr(t5_nldi_acquisition, "get_json", fake_get)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=1,
        request_interval_seconds=0,
    )

    assert log.loc[0, "status"] == "invalid_response"
    assert log.attrs["halted_early"] is True
    assert audit_plan_cache(plan).loc[0, "status"] == "missing"
    assert not list(tmp_path.glob("*.json"))


def test_first_request_failure_opens_circuit_breaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_two_target_predictors(), cache_dir=tmp_path)
    called: list[str] = []

    def failed_get(url: str, *, timeout: int) -> dict:
        called.append(url)
        raise JsonHttpError(429, url)

    monkeypatch.setattr(t5_nldi_acquisition, "get_json", failed_get)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=4,
        request_interval_seconds=0,
    )

    assert len(called) == 1
    assert list(log["status"]) == ["transient_failure"]
    assert list(log["http_status"]) == [429]
    assert log.attrs["halted_early"] is True
    assert log.attrs["halt_reason"] == "transient_failure"
    assert log.attrs["n_selected_requests_remaining_after_halt"] == 3
    assert not list(tmp_path.glob("*.json"))


def test_confirmed_404_writes_sidecar_and_does_not_halt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)

    def status_aware_get(url: str, *, timeout: int) -> dict:
        if "/UM/" in url:
            raise JsonHttpError(404, url)
        return _feature_collection()

    monkeypatch.setattr(t5_nldi_acquisition, "get_json", status_aware_get)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=2,
        request_interval_seconds=0,
    )

    assert list(log["status"]) == ["provider_confirmed_unavailable", "complete"]
    assert list(log["http_status"]) == [404, 200]
    assert log.attrs["halted_early"] is False
    assert list(audit_plan_cache(plan)["status"]) == [
        "provider_confirmed_unavailable",
        "complete",
    ]
    assert not Path(plan.loc[0, "cache_path"]).exists()
    assert Path(plan.loc[0, "unavailable_path"]).is_file()


def test_nldi_response_cache_is_atomic_and_failures_are_not_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        nldi_connectivity, "get_json", lambda url, timeout: _feature_collection()
    )
    result = nldi_connectivity.fetch_nldi_navigation(
        "01000001", "UM", cache_dir=tmp_path, pause_s=0
    )

    assert result == _feature_collection()
    assert (tmp_path / "01000001_UM_200.json").is_file()
    assert not list(tmp_path.glob("*.partial"))

    def fail(url: str, timeout: int) -> dict:
        raise RuntimeError("retry budget exhausted")

    monkeypatch.setattr(nldi_connectivity, "get_json", fail)
    result = nldi_connectivity.fetch_nldi_navigation(
        "02000001", "DM", cache_dir=tmp_path, pause_s=0
    )

    assert result is None
    assert not (tmp_path / "02000001_DM_200.json").exists()
