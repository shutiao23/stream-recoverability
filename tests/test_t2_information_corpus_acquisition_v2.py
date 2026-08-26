from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data import confirmatory as provider
from stream_recoverability.data.t2_information_adapters import _provider_eligible
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    LEGACY_NETWORK_SCHEMA_VERSION,
    LEGACY_PROVIDER,
    NETWORK_SCHEMA_VERSION,
    AuditedRateLimitedFetcher,
    LegacyNetworkRequest,
    ProviderCircuitOpen,
    acquire_network,
    archive_nonterminal_attempt,
    load_v2_corpus_plan,
    parse_legacy_hydraulics_rdb,
    plan_as_dict,
    run_v2_corpus_acquisition,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _ok(url: str, body: bytes = b"ok") -> provider.HTTPResponse:
    return provider.HTTPResponse(
        url=url,
        status=200,
        headers={"Content-Type": "text/plain"},
        body=body,
    )


def test_v2_plan_uses_exactly_one_legacy_request_per_network() -> None:
    first = load_v2_corpus_plan(ROOT)
    second = load_v2_corpus_plan(ROOT)
    assert first == second
    assert len(first.networks) == 67
    assert sum(len(network.sites) for network in first.networks) == 340
    assert sum(len(network.legacy_requests) for network in first.networks) == 67
    assert max(
        request.estimated_site_days
        for network in first.networks
        for request in network.legacy_requests
    ) <= 200_000
    serialized = plan_as_dict(first)
    assert serialized["plan_sha256"] == first.plan_sha256
    assert serialized["n_legacy_usgs_requests"] == 67
    assert serialized["n_power_requests"] == 340
    assert serialized["v1_ogc_root_read_or_mutated"] is False


def test_retry_429_then_success_uses_deterministic_global_cooldown() -> None:
    fake_time = FakeTime()
    calls = 0

    def fetch(url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        nonlocal calls
        del headers
        calls += 1
        if calls == 1:
            raise RuntimeError(f"HTTP 429 while fetching {url}")
        return _ok(url)

    limited = AuditedRateLimitedFetcher(
        fetch,
        interval_seconds=0,
        max_transient_retries=2,
        backoff_initial_seconds=1,
        backoff_max_seconds=8,
        http_429_cooldown_seconds=4,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )
    assert limited("https://waterservices.usgs.gov/test", {}).status == 200
    assert calls == 2
    assert fake_time.sleeps == [4.0]
    assert limited.audit()["events"] == [
        {
            "event": "transient_provider_failure",
            "url": "https://waterservices.usgs.gov/test",
            "status": 429,
            "reason": "HTTP 429 while fetching https://waterservices.usgs.gov/test",
            "retry_index": 0,
            "attempt_number": 1,
            "retry_budget": 2,
            "cooldown_seconds": 4.0,
            "jitter_seconds": 0.0,
            "exhausted": False,
        }
    ]


def test_retry_exhaustion_opens_global_circuit_and_refuses_more_calls() -> None:
    fake_time = FakeTime()
    calls = 0

    def fetch(url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        nonlocal calls
        del headers
        calls += 1
        return provider.HTTPResponse(
            url=url,
            status=503,
            headers={"Content-Type": "text/plain", "Retry-After": "3"},
            body=b"busy",
        )

    limited = AuditedRateLimitedFetcher(
        fetch,
        interval_seconds=0,
        max_transient_retries=1,
        backoff_initial_seconds=1,
        backoff_max_seconds=8,
        http_429_cooldown_seconds=4,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )
    with pytest.raises(ProviderCircuitOpen, match="global circuit opened"):
        limited("https://waterservices.usgs.gov/test", {})
    assert calls == 2
    assert fake_time.sleeps == [3.0]
    assert limited.circuit_open is True
    with pytest.raises(ProviderCircuitOpen, match="already open"):
        limited("https://power.larc.nasa.gov/test", {})
    assert calls == 2


def test_corpus_run_stops_at_first_exhausted_request(tmp_path: Path) -> None:
    fake_time = FakeTime()
    calls = 0
    saw_atomic_in_progress = False

    def fetch(url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        nonlocal calls, saw_atomic_in_progress
        del headers
        state = json.loads((tmp_path / "root_execution_manifest.json").read_text())
        saw_atomic_in_progress = state["status"] == "in_progress"
        calls += 1
        raise RuntimeError(f"HTTP 429 while fetching {url}")

    network_id = load_v2_corpus_plan(ROOT).networks[0].network_id
    manifest = run_v2_corpus_acquisition(
        ROOT,
        tmp_path,
        execute=True,
        network_ids=[network_id],
        acknowledged_network_count=1,
        request_interval_seconds=0,
        max_transient_retries=0,
        retry_backoff_initial_seconds=0,
        retry_backoff_max_seconds=0,
        http_429_cooldown_seconds=0,
        fetcher=fetch,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
    )
    assert calls == 1
    assert saw_atomic_in_progress is True
    assert manifest["status"] == "execution_stopped_fail_closed"
    assert manifest["stop"]["reason"] == "provider_circuit_open"
    assert manifest["stop"]["network_id"] == network_id
    assert manifest["provider_transport_audit"]["circuit_open"] is True
    terminal_state = json.loads((tmp_path / "root_execution_manifest.json").read_text())
    assert terminal_state["status"] == "execution_stopped_fail_closed"
    assert manifest["global_attrition"]["materialization_status_counts"] == {
        "interrupted_nonterminal": 1,
        "not_materialized": 66,
    }


def test_nonretryable_http_404_stops_conservatively_without_retry(tmp_path: Path) -> None:
    calls = 0

    def fetch(url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        nonlocal calls
        del headers
        calls += 1
        return provider.HTTPResponse(
            url=url,
            status=404,
            headers={"Content-Type": "text/plain"},
            body=b"not found",
        )

    network_id = load_v2_corpus_plan(ROOT).networks[0].network_id
    manifest = run_v2_corpus_acquisition(
        ROOT,
        tmp_path,
        execute=True,
        network_ids=[network_id],
        acknowledged_network_count=1,
        request_interval_seconds=0,
        max_transient_retries=4,
        retry_backoff_initial_seconds=0,
        retry_backoff_max_seconds=0,
        http_429_cooldown_seconds=0,
        fetcher=fetch,
    )
    assert calls == 1
    assert manifest["status"] == "execution_stopped_fail_closed"
    assert manifest["stop"]["reason"] == "network_acquisition_error"
    assert manifest["stop"]["error_type"] == "RuntimeError"
    assert "non-success HTTP 404" in manifest["stop"]["error"]
    assert manifest["provider_transport_audit"]["n_retry_events"] == 0
    assert manifest["provider_transport_audit"]["circuit_open"] is False


def _legacy_request() -> LegacyNetworkRequest:
    return LegacyNetworkRequest(
        request_id="legacy_test",
        network_id="huc8_01070004",
        role="development",
        site_ids=("01095220",),
        start="2020-01-01",
        end="2020-01-03",
        parameter_codes=("00060", "00065"),
        statistic_code="00003",
        url="https://waterservices.usgs.gov/nwis/dv/?test",
        estimated_site_days=3,
    )


def test_legacy_rdb_A_only_qc_and_units_are_explicit() -> None:
    payload = b"""# official response
agency_cd\tsite_no\tdatetime\t11_00060_00003\t11_00060_00003_cd\t12_00065_00003\t12_00065_00003_cd
5s\t15s\t20d\t14n\t10s\t14n\t10s
USGS\t01095220\t2020-01-01\t10\tA:[4]\t5\tA:R
USGS\t01095220\t2020-01-02\t20\tP\t6\tP
USGS\t01095220\t2020-01-03\tIce\tA\t7\tA:e
"""
    frame = parse_legacy_hydraulics_rdb(
        payload,
        _legacy_request(),
        response_sha256="a" * 64,
        response_artifact="raw/response.rdb",
    )
    assert len(frame) == 6
    approved = frame.loc[frame["approval_status"].eq("Approved")]
    provisional = frame.loc[frame["approval_status"].eq("Provisional")]
    assert set(approved["variable"]) == {"F", "L"}
    assert approved.set_index("variable").loc["F", "value"] == pytest.approx(
        10 * 0.028316846592
    )
    assert approved.loc[approved["date"].eq(pd.Timestamp("2020-01-01"))].set_index(
        "variable"
    ).loc["L", "value"] == pytest.approx(5 * 0.3048)
    assert provisional["value"].isna().all()
    assert frame["source"].eq(LEGACY_PROVIDER).all()
    ice = frame.loc[frame["raw_text"].eq("Ice")].iloc[0]
    assert pd.isna(ice["value"])
    assert pd.isna(ice["raw_value"])
    assert ice["quality_approved"] is False or not bool(ice["quality_approved"])
    assert ice["approval_status"] == "Provisional"
    assert ice["qc_status"] == "excluded_non_numeric_provider_code"
    estimated = frame.loc[frame["raw_text"].eq("7")].iloc[0]
    assert estimated["approval_status"] == "Approved"
    assert bool(estimated["estimated_qualifier"]) is True
    assert estimated["qc_status"] == "approved_estimated"

    with pytest.raises(ValueError, match="unknown non-numeric provider text"):
        parse_legacy_hydraulics_rdb(
            payload.replace(b"Ice", b"UnknownCode"),
            _legacy_request(),
            response_sha256="b" * 64,
            response_artifact="raw/unknown.response.rdb",
        )


def test_adapter_accepts_approved_legacy_source_without_calling_it_ogc() -> None:
    rows = pd.DataFrame(
        [
            {
                "variable": "F",
                "value": 1.0,
                "source": LEGACY_PROVIDER,
                "natural_observed": True,
                "qc_status": "approved",
                "approval_status": "Approved",
                "quality_approved": True,
            }
        ]
    )
    eligible, basis = _provider_eligible(rows)
    assert eligible.tolist() == [True]
    assert basis.tolist() == ["usgs_approval_status_approved"]
    assert rows.loc[0, "source"] != "usgs_ogc_daily"


def test_retry_manifest_and_interrupted_directory_are_fully_archived(tmp_path: Path) -> None:
    network = load_v2_corpus_plan(ROOT).networks[0]
    retry = tmp_path / "retry"
    retry.mkdir()
    (retry / "raw").mkdir()
    (retry / "raw/old.response").write_bytes(b"old raw")
    (retry / "network_manifest.json").write_text(
        json.dumps(
            {
                "manifest_schema": NETWORK_SCHEMA_VERSION,
                "status": "acquisition_retry_required",
                "network_id": network.network_id,
                "role": network.role,
                "network_plan_sha256": network.network_plan_sha256,
            }
        )
    )
    archived = archive_nonterminal_attempt(retry, network)
    assert archived == retry / "attempts/attempt_0001"
    audit = json.loads((archived / "attempt_archive_manifest.json").read_text())
    assert audit["archive_reason"] == "nonterminal_manifest_acquisition_retry_required"
    assert audit["n_files"] == 2
    assert (archived / "raw/old.response").read_bytes() == b"old raw"
    assert not (retry / "raw").exists()

    interrupted = tmp_path / "interrupted"
    interrupted.mkdir()
    (interrupted / "request_plan.json").write_text("{}")
    archived = archive_nonterminal_attempt(interrupted, network)
    audit = json.loads((archived / "attempt_archive_manifest.json").read_text())
    assert audit["archive_reason"] == "interrupted_missing_manifest"
    assert (archived / "request_plan.json").is_file()

    recovering = tmp_path / "recovering"
    staging = recovering / "attempts/.attempt_0001.in_progress"
    staging.mkdir(parents=True)
    (staging / "raw").mkdir()
    (staging / "raw/already_moved.rdb").write_bytes(b"first half")
    (staging / ".archive_intent.json").write_text(
        json.dumps(
            {
                "manifest_schema": "t2_v91_open_role_mh_attempt_archive_intent_v2_1",
                "attempt_number": 1,
                "network_id": network.network_id,
                "role": network.role,
                "network_plan_sha256": network.network_plan_sha256,
                "archive_reason": "interrupted_missing_manifest",
                "archive_started_at_utc": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    (recovering / "request_plan.json").write_text("{}")
    completed = archive_nonterminal_attempt(recovering, network)
    assert completed == recovering / "attempts/attempt_0001"
    audit = json.loads((completed / "attempt_archive_manifest.json").read_text())
    assert audit["recovered_from_in_progress_staging"] is True
    assert (completed / "raw/already_moved.rdb").is_file()
    assert (completed / "request_plan.json").is_file()
    assert not staging.exists()

    stale = tmp_path / "stale_terminal"
    stale.mkdir()
    (stale / "daily_long_auxiliary.parquet").write_bytes(b"old terminal")
    (stale / "network_manifest.json").write_text(
        json.dumps(
            {
                "manifest_schema": LEGACY_NETWORK_SCHEMA_VERSION,
                "status": "materialized_partial",
                "network_id": network.network_id,
                "role": network.role,
            }
        )
    )
    archived = archive_nonterminal_attempt(stale, network)
    audit = json.loads((archived / "attempt_archive_manifest.json").read_text())
    assert audit["archive_reason"] == "terminal_rebuild_parser_contract_v2_1"


class V2Fetcher:
    def __init__(self, network: object) -> None:
        self.network = network
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        del headers
        self.calls.append(url)
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc in {"waterservices.usgs.gov", "nwis.waterservices.usgs.gov"}:
            lines = [
                "# mock legacy response",
                "agency_cd\tsite_no\tdatetime\t11_00060_00003\t11_00060_00003_cd\t12_00065_00003\t12_00065_00003_cd",
                "5s\t15s\t20d\t14n\t10s\t14n\t10s",
            ]
            for site in self.network.sites:
                lines.extend(
                    [
                        f"USGS\t{site.site_id}\t{site.target_start}\t10\tA\t5\tA:R",
                        f"USGS\t{site.site_id}\t{site.target_end}\t20\tP\t6\tP",
                    ]
                )
            return provider.HTTPResponse(
                url=url,
                status=200,
                headers={"Content-Type": "text/plain"},
                body=("\n".join(lines) + "\n").encode(),
            )
        start = query["start"][0]
        end = query["end"][0]
        parameters = {}
        values = {}
        for offset, spec in enumerate(provider.METEOROLOGY_SPECS):
            parameters[spec.provider_code] = {"units": spec.source_unit}
            values[spec.provider_code] = {start: float(offset + 1), end: float(offset + 2)}
        return provider.HTTPResponse(
            url=url,
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            float(query["longitude"][0]),
                            float(query["latitude"][0]),
                            100,
                        ],
                    },
                    "header": {
                        "api": {"name": "POWER", "version": "test"},
                        "sources": ["mock"],
                        "fill_value": -999,
                        "time_standard": "UTC",
                        "start": start,
                        "end": end,
                    },
                    "parameters": parameters,
                    "properties": {"parameter": values},
                    "messages": [],
                }
            ).encode(),
        )


def test_v2_network_materialization_and_resume_are_independent_of_v1(tmp_path: Path) -> None:
    network = load_v2_corpus_plan(ROOT).networks[0]
    raw_fetcher = V2Fetcher(network)
    limited = AuditedRateLimitedFetcher(
        raw_fetcher,
        interval_seconds=0,
        max_transient_retries=0,
        backoff_initial_seconds=0,
        backoff_max_seconds=0,
        http_429_cooldown_seconds=0,
    )
    manifest, resumed = acquire_network(ROOT, tmp_path, network, fetcher=limited)
    assert resumed is False
    assert manifest["provider_request_counts"] == {
        LEGACY_PROVIDER: 1,
        "nasa_power_daily_point": len(network.sites),
    }
    assert manifest["v1_ogc_root_read_or_mutated"] is False
    assert manifest["sealed_temperature_records_read"] is False
    output = tmp_path / network.role / "networks" / network.network_id
    daily = pd.read_parquet(output / "daily_long_auxiliary.parquet")
    assert set(daily["source"]) == {LEGACY_PROVIDER, "nasa_power_daily_point"}
    assert "temperature_c" not in daily.columns
    assert daily.loc[daily["approval_status"].eq("Provisional"), "value"].isna().all()
    calls = len(raw_fetcher.calls)
    second, resumed = acquire_network(ROOT, tmp_path, network, fetcher=limited)
    assert resumed is True
    assert second["network_plan_sha256"] == manifest["network_plan_sha256"]
    assert len(raw_fetcher.calls) == calls
    records = json.loads((output / "raw_request_log.json").read_text())
    request_artifact = output / records[0]["request_artifact"]
    request_artifact.write_bytes(b"tampered request")
    with pytest.raises(ValueError, match="raw request integrity failure"):
        acquire_network(ROOT, tmp_path, network, fetcher=limited)
