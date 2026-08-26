from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data import nldi_connectivity, t5_nldi_acquisition
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


def test_execution_resumes_only_missing_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path)
    Path(plan.loc[0, "cache_path"]).write_text(
        json.dumps(_feature_collection()), encoding="utf-8"
    )
    called: list[tuple[str, str]] = []

    def fake_fetch(
        site_id: str,
        direction: str,
        *,
        distance_km: float,
        cache_dir: Path,
        pause_s: float,
    ) -> dict:
        called.append((site_id, direction))
        path = cache_dir / f"{site_id}_{direction}_{int(distance_km)}.json"
        path.write_text(json.dumps(_feature_collection()), encoding="utf-8")
        return _feature_collection()

    monkeypatch.setattr(t5_nldi_acquisition, "fetch_nldi_navigation", fake_fetch)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=2,
        request_interval_seconds=0.25,
    )

    assert called == [("01000001", "DM")]
    assert len(log) == 1
    assert log.loc[0, "status"] == "complete"
    assert audit_plan_cache(plan)["status"].eq("complete").all()


def test_new_invalid_response_is_quarantined_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_predictors(), cache_dir=tmp_path).iloc[[0]]

    def fake_fetch(
        site_id: str,
        direction: str,
        *,
        distance_km: float,
        cache_dir: Path,
        pause_s: float,
    ) -> dict:
        path = cache_dir / f"{site_id}_{direction}_{int(distance_km)}.json"
        path.write_text("{}", encoding="utf-8")
        return {}

    monkeypatch.setattr(t5_nldi_acquisition, "fetch_nldi_navigation", fake_fetch)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=1,
        request_interval_seconds=0.25,
    )

    assert log.loc[0, "status"] == "invalid_response_quarantined"
    assert audit_plan_cache(plan).loc[0, "status"] == "missing"
    assert len(list(tmp_path.glob("*.invalid-*.json"))) == 1


def test_first_request_failure_opens_circuit_breaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_open_target_plan(_two_target_predictors(), cache_dir=tmp_path)
    called: list[tuple[str, str]] = []

    def failed_fetch(
        site_id: str,
        direction: str,
        *,
        distance_km: float,
        cache_dir: Path,
        pause_s: float,
    ) -> None:
        called.append((site_id, direction))

    monkeypatch.setattr(t5_nldi_acquisition, "fetch_nldi_navigation", failed_fetch)
    log = execute_missing_requests(
        plan,
        cache_dir=tmp_path,
        max_new_requests=4,
        request_interval_seconds=0.25,
    )

    assert called == [("01000001", "UM")]
    assert list(log["status"]) == ["request_failed"]
    assert log.attrs["halted_early"] is True
    assert log.attrs["halt_reason"] == "request_failed_after_internal_retries"
    assert log.attrs["n_selected_requests_remaining_after_halt"] == 3
    assert not list(tmp_path.glob("*.json"))


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
