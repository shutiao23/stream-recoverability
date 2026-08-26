from __future__ import annotations

import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data import confirmatory as provider
from stream_recoverability.data import (
    t2_information_corpus_acquisition_v2 as acquisition_v2,
)
from stream_recoverability.data.t2_information_adapters import _provider_eligible
from stream_recoverability.data.t2_information_corpus_acquisition_v2 import (
    LEGACY_EMPTY_NO_SITES_RDB,
    LEGACY_NETWORK_SCHEMA_VERSION,
    LEGACY_PROVIDER,
    LOCKED_PROVIDER_NONNUMERIC_CODES,
    NETWORK_SCHEMA_VERSION,
    V2_4_NETWORK_SCHEMA_VERSION,
    AuditedRateLimitedFetcher,
    LegacyNetworkRequest,
    ProviderCircuitOpen,
    RootExecutionLock,
    _migrate_archived_terminal_without_provider,
    _network_plan_sha_for_schema,
    acquire_network,
    archive_nonterminal_attempt,
    load_v2_corpus_plan,
    parse_legacy_hydraulics_rdb,
    plan_as_dict,
    run_v2_corpus_acquisition,
    scan_legacy_rdb_nonnumeric_codes,
)

ROOT = Path(__file__).resolve().parents[1]


def test_root_execution_lock_refuses_a_second_writer(tmp_path: Path) -> None:
    first = RootExecutionLock(tmp_path)
    with pytest.raises(RuntimeError, match="another v2 acquisition writer"):
        RootExecutionLock(tmp_path)
    first.release()
    second = RootExecutionLock(tmp_path)
    second.release()


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
        assert "provider_calls_started" not in state
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
        end="2020-01-07",
        parameter_codes=("00060", "00065"),
        statistic_code="00003",
        url="https://waterservices.usgs.gov/nwis/dv/?test",
        estimated_site_days=7,
    )


def test_legacy_rdb_A_only_qc_and_units_are_explicit() -> None:
    payload = b"""# official response
agency_cd\tsite_no\tdatetime\t11_00060_00003\t11_00060_00003_cd\t12_00065_00003\t12_00065_00003_cd
5s\t15s\t20d\t14n\t10s\t14n\t10s
USGS\t01095220\t2020-01-01\t10\tA:[4]\t5\tA:R
USGS\t01095220\t2020-01-02\t20\tP\t6\tP
USGS\t01095220\t2020-01-03\tIce\tA\t7\tA:e
USGS\t01095220\t2020-01-04\tEqp\tP\t\t
USGS\t01095220\t2020-01-05\t***\tP\t\t
USGS\t01095220\t2020-01-06\tBkw\tP\t\t
USGS\t01095220\t2020-01-07\tRat\tP\t\t
"""
    frame = parse_legacy_hydraulics_rdb(
        payload,
        _legacy_request(),
        response_sha256="a" * 64,
        response_artifact="raw/response.rdb",
    )
    assert LOCKED_PROVIDER_NONNUMERIC_CODES == (
        "Ice",
        "Eqp",
        "***",
        "Bkw",
        "Rat",
    )
    assert len(frame) == 10
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
    for code in LOCKED_PROVIDER_NONNUMERIC_CODES:
        excluded = frame.loc[frame["raw_text"].eq(code)].iloc[0]
        assert pd.isna(excluded["value"])
        assert pd.isna(excluded["raw_value"])
        assert excluded["quality_approved"] is False or not bool(
            excluded["quality_approved"]
        )
        assert excluded["approval_status"] == "Provisional"
        assert excluded["qc_status"] == "excluded_non_numeric_provider_code"
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


def test_only_exact_official_no_sites_rdb_is_accepted_as_empty() -> None:
    assert len(LEGACY_EMPTY_NO_SITES_RDB) == 81
    real_root = (
        ROOT
        / "data_versions/global_network_corpus_v1/open_role_auxiliary_legacy_v2"
        / "failure_closure6/development/networks/huc8_15030108"
    )
    real_matches = [
        path
        for path in real_root.rglob("response.rdb")
        if path.read_bytes() == LEGACY_EMPTY_NO_SITES_RDB
    ]
    assert real_matches
    parsed = parse_legacy_hydraulics_rdb(
        LEGACY_EMPTY_NO_SITES_RDB,
        _legacy_request(),
        response_sha256="c" * 64,
        response_artifact="raw/empty.response.rdb",
    )
    assert parsed.empty

    near_misses = (
        LEGACY_EMPTY_NO_SITES_RDB.replace(b"#  No sites", b"# No sites"),
        LEGACY_EMPTY_NO_SITES_RDB.removesuffix(b"\t\t\n"),
        LEGACY_EMPTY_NO_SITES_RDB.replace(b"5s\t15s\t20d", b"5s\t15s\t19d"),
        LEGACY_EMPTY_NO_SITES_RDB + b"# trailing content\n",
        (
            b"#  No values found matching all criteria\n"
            b"agency_cd\tsite_no\tdatetime\n5s\t15s\t20d\n\t\t\n"
        ),
    )
    for payload in near_misses:
        with pytest.raises(
            ValueError, match="no requested daily-mean F/L column"
        ):
            parse_legacy_hydraulics_rdb(
                payload,
                _legacy_request(),
                response_sha256="d" * 64,
                response_artifact="raw/rejected-empty.response.rdb",
            )


def test_all_current_raw_rdb_nonnumeric_codes_equal_locked_set() -> None:
    raw_root = (
        ROOT
        / "data_versions/global_network_corpus_v1/open_role_auxiliary_legacy_v2"
        / "failure_closure6"
    )
    paths = sorted(raw_root.rglob("response.rdb"))
    assert paths
    counts = scan_legacy_rdb_nonnumeric_codes(paths)
    assert set(counts) == set(LOCKED_PROVIDER_NONNUMERIC_CODES)
    assert all(counts[code] > 0 for code in LOCKED_PROVIDER_NONNUMERIC_CODES)


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
                "manifest_schema": "t2_v91_open_role_mh_attempt_archive_intent_v2_6",
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
    assert audit["archive_reason"] == "terminal_rebuild_parser_contract_v2_6"


class V2Fetcher:
    def __init__(
        self,
        network: object,
        *,
        nonnumeric_code: str | None = None,
        empty_legacy: bool = False,
    ) -> None:
        self.network = network
        self.nonnumeric_code = nonnumeric_code
        self.empty_legacy = empty_legacy
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        del headers
        self.calls.append(url)
        parsed = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc in {"waterservices.usgs.gov", "nwis.waterservices.usgs.gov"}:
            if self.empty_legacy:
                return provider.HTTPResponse(
                    url=url,
                    status=200,
                    headers={"Content-Type": "text/plain"},
                    body=LEGACY_EMPTY_NO_SITES_RDB,
                )
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
            if self.nonnumeric_code is not None:
                site = self.network.sites[0]
                extra_date = (pd.Timestamp(site.target_start) + pd.Timedelta(days=1)).date()
                lines.append(
                    f"USGS\t{site.site_id}\t{extra_date}\t{self.nonnumeric_code}\tP\t\t"
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _downgrade_terminal_to_v2_4(output: Path, network: object) -> pd.DataFrame:
    daily_path = output / "daily_long_auxiliary.parquet"
    daily = pd.read_parquet(daily_path)
    old = daily.loc[~daily["raw_text"].eq("Rat").fillna(False)].reset_index(drop=True)
    old.to_parquet(daily_path, index=False)
    manifest_path = output / "network_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    historical_plan_sha = _network_plan_sha_for_schema(
        network, V2_4_NETWORK_SCHEMA_VERSION
    )
    manifest["manifest_schema"] = V2_4_NETWORK_SCHEMA_VERSION
    manifest["parser_contract_version"] = "legacy_nwis_rdb_hydraulics_parser_v2_4"
    manifest["locked_provider_nonnumeric_codes"] = ["Ice", "Eqp", "***", "Bkw"]
    manifest["network_plan_sha256"] = historical_plan_sha
    manifest["n_auxiliary_rows"] = len(old)
    manifest["artifacts"]["daily_long_auxiliary"].update(
        {"sha256": _sha256(daily_path), "bytes": daily_path.stat().st_size}
    )
    request_plan_path = output / "request_plan.json"
    request_plan = json.loads(request_plan_path.read_text())
    request_plan["network_plan_sha256"] = historical_plan_sha
    unhashed = dict(request_plan)
    unhashed.pop("request_plan_sha256")
    request_plan["request_plan_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    request_plan_path.write_text(
        json.dumps(request_plan, indent=2, sort_keys=True) + "\n"
    )
    manifest["artifacts"]["request_plan"].update(
        {
            "sha256": _sha256(request_plan_path),
            "bytes": request_plan_path.stat().st_size,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return old


def _rebuild_archive_inventory(archive: Path) -> None:
    path = archive / "attempt_archive_manifest.json"
    manifest = json.loads(path.read_text())
    inventory = acquisition_v2._archive_inventory(archive)
    manifest["inventory"] = inventory
    manifest["n_files"] = len(inventory)
    manifest["total_bytes"] = sum(row["bytes"] for row in inventory)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _copy_real_v2_archive(tmp_path: Path) -> tuple[object, Path, Path]:
    network = next(
        value
        for value in load_v2_corpus_plan(ROOT).networks
        if value.network_id == "huc8_02040103"
    )
    source = (
        ROOT
        / "data_versions/global_network_corpus_v1/open_role_auxiliary_legacy_v2"
        / "failure_closure6/development/networks/huc8_02040103"
        / "attempts/attempt_0001"
    )
    output = tmp_path / network.role / "networks" / network.network_id
    archive = output / "attempts/attempt_0001"
    shutil.copytree(source, archive)
    return network, output, archive


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


def test_exact_empty_legacy_response_becomes_terminal_H_attrition(tmp_path: Path) -> None:
    network = next(
        item
        for item in load_v2_corpus_plan(ROOT).networks
        if item.network_id == "huc8_15030108"
    )
    raw_fetcher = V2Fetcher(network, empty_legacy=True)
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
    assert manifest["status"] == "materialized_partial"
    assert manifest["acquisition_terminal"] is True
    output = tmp_path / network.role / "networks" / network.network_id
    failures = json.loads((output / "source_failures.json").read_text())
    assert len(failures) == 2 * len(network.sites)
    assert {row["variable"] for row in failures} == {"F", "L"}
    assert {row["provider"] for row in failures} == {LEGACY_PROVIDER}
    assert {row["status"] for row in failures} == {
        "source_unavailable_no_rows_in_successful_response"
    }
    coverage = pd.read_csv(output / "coverage.csv")
    hydraulics = coverage.loc[coverage["information_group"].eq("H")]
    assert hydraulics["source_status"].eq("failed_or_unavailable").all()
    assert hydraulics["n_provider_rows"].eq(0).all()


def test_stale_terminal_migrates_after_full_archive_with_zero_provider_calls(
    tmp_path: Path,
) -> None:
    network = load_v2_corpus_plan(ROOT).networks[0]
    source = V2Fetcher(network, nonnumeric_code="Rat")
    initial_fetcher = AuditedRateLimitedFetcher(source, interval_seconds=0)
    acquire_network(ROOT, tmp_path, network, fetcher=initial_fetcher)
    output = tmp_path / network.role / "networks" / network.network_id
    old_daily = _downgrade_terminal_to_v2_4(output, network)
    old_eligible = old_daily.loc[
        old_daily["natural_observed"].astype(bool)
        & old_daily["quality_approved"].astype(bool)
        & pd.to_numeric(old_daily["value"], errors="coerce").notna(),
        ["date", "site_id", "variable", "value"],
    ].sort_values(["date", "site_id", "variable"])

    def forbidden_fetch(url: str, headers: dict[str, str]) -> provider.HTTPResponse:
        del url, headers
        raise AssertionError("provider must not be called during terminal migration")

    no_provider = AuditedRateLimitedFetcher(forbidden_fetch, interval_seconds=0)
    manifest, resumed = acquire_network(
        ROOT, tmp_path, network, fetcher=no_provider
    )
    assert resumed is False
    assert no_provider.n_base_calls == 0
    migration = manifest["provider_free_terminal_migration"]
    assert migration["accepted"] is True
    assert migration["provider_calls"] == 0
    assert migration["raw_request_and_response_sha256_verified"] is True
    assert migration["eligible_numeric_keys_and_values_exact"] is True
    assert migration["new_excluded_nonnumeric_code_counts"] == {"Rat": 1}

    archive = output / "attempts/attempt_0001"
    assert (archive / "network_manifest.json").is_file()
    assert (archive / "daily_long_auxiliary.parquet").is_file()
    assert not (archive / "terminal_migration_attempt.json").exists()
    attempt = json.loads(
        (
            output
            / "attempts/terminal_migration_audit/migration_0001.json"
        ).read_text()
    )
    assert attempt["accepted"] is True
    assert attempt["n_verified_request_response_pairs"] == 1 + len(network.sites)
    current = pd.read_parquet(output / "daily_long_auxiliary.parquet")
    current_eligible = current.loc[
        current["natural_observed"].astype(bool)
        & current["quality_approved"].astype(bool)
        & pd.to_numeric(current["value"], errors="coerce").notna(),
        ["date", "site_id", "variable", "value"],
    ].sort_values(["date", "site_id", "variable"])
    pd.testing.assert_frame_equal(
        old_eligible.reset_index(drop=True),
        current_eligible.reset_index(drop=True),
        check_dtype=False,
        check_exact=True,
    )
    rat = current.loc[current["raw_text"].eq("Rat")]
    assert len(rat) == 1
    assert rat["value"].isna().all()
    assert rat["raw_value"].isna().all()
    assert rat["qc_status"].eq("excluded_non_numeric_provider_code").all()


def test_terminal_migration_rejects_plan_drift_and_preserves_online_fallback(
    tmp_path: Path,
) -> None:
    network = load_v2_corpus_plan(ROOT).networks[0]
    source = V2Fetcher(network, nonnumeric_code="Rat")
    acquire_network(
        ROOT,
        tmp_path,
        network,
        fetcher=AuditedRateLimitedFetcher(source, interval_seconds=0),
    )
    output = tmp_path / network.role / "networks" / network.network_id
    _downgrade_terminal_to_v2_4(output, network)
    archive = archive_nonterminal_attempt(output, network)
    assert archive is not None
    plan_path = archive / "request_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["power_requests"][0]["end"] = "1999-12-31"
    unhashed = dict(plan)
    unhashed.pop("request_plan_sha256")
    plan["request_plan_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    old_manifest_path = archive / "network_manifest.json"
    old_manifest = json.loads(old_manifest_path.read_text())
    old_manifest["artifacts"]["request_plan"].update(
        {"sha256": _sha256(plan_path), "bytes": plan_path.stat().st_size}
    )
    old_manifest_path.write_text(
        json.dumps(old_manifest, indent=2, sort_keys=True) + "\n"
    )
    # Rebuild the archive custody manifest so the rejection is specifically
    # plan drift, not an incidental SHA mismatch.
    inventory = []
    for path in sorted(value for value in archive.rglob("*") if value.is_file()):
        if path.name in {"attempt_archive_manifest.json", ".archive_intent.json"}:
            continue
        inventory.append(
            {
                "path": str(path.relative_to(archive)),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    archive_manifest_path = archive / "attempt_archive_manifest.json"
    archive_manifest = json.loads(archive_manifest_path.read_text())
    archive_manifest["inventory"] = inventory
    archive_manifest["n_files"] = len(inventory)
    archive_manifest["total_bytes"] = sum(row["bytes"] for row in inventory)
    archive_manifest_path.write_text(
        json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n"
    )

    with RootExecutionLock(tmp_path) as root_lock:
        migrated, audit = _migrate_archived_terminal_without_provider(
            ROOT, tmp_path, output, network, archive, root_lock=root_lock
        )
    assert migrated is None
    assert audit["accepted"] is False
    assert "request plan drifted" in audit["rejection_reason"]
    assert audit["provider_calls"] == 0
    assert audit["fallback"] == (
        "explicit_compatibility_rejection_may_rebuild_from_providers"
    )
    assert not (output / "network_manifest.json").exists()
    assert (archive / "network_manifest.json").is_file()


def test_copied_real_legacy_terminal_migrates_offline_in_tmp(tmp_path: Path) -> None:
    network, output, archive = _copy_real_v2_archive(tmp_path)
    before = {
        str(path.relative_to(archive)): _sha256(path)
        for path in archive.rglob("*")
        if path.is_file()
    }
    with RootExecutionLock(tmp_path) as root_lock:
        migrated, audit = _migrate_archived_terminal_without_provider(
            ROOT, tmp_path, output, network, archive, root_lock=root_lock
        )
    assert migrated is not None, audit
    assert audit["accepted"] is True
    assert audit["provider_calls"] == 0
    assert audit["eligible_numeric_keys_and_values_exact"] is True
    assert audit["n_verified_request_response_pairs"] == 4
    assert migrated["provider_free_terminal_migration"]["power_reparsed_from_raw"] is True
    after = {
        str(path.relative_to(archive)): _sha256(path)
        for path in archive.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_terminal_migration_requires_owned_lock_and_empty_current(tmp_path: Path) -> None:
    network, output, archive = _copy_real_v2_archive(tmp_path)
    sentinel = output / "concurrent-writer-artifact.bin"
    sentinel.write_bytes(b"keep")
    wrong_root = tmp_path / "wrong-root"
    wrong_root.mkdir()
    with (
        RootExecutionLock(wrong_root) as wrong_lock,
        pytest.raises(RuntimeError, match="does not own"),
    ):
        _migrate_archived_terminal_without_provider(
            ROOT,
            tmp_path,
            output,
            network,
            archive,
            root_lock=wrong_lock,
        )
    with (
        RootExecutionLock(tmp_path) as root_lock,
        pytest.raises(RuntimeError, match="empty current output"),
    ):
        _migrate_archived_terminal_without_provider(
            ROOT,
            tmp_path,
            output,
            network,
            archive,
            root_lock=root_lock,
        )
    assert sentinel.read_bytes() == b"keep"
    assert (archive / "network_manifest.json").is_file()
    assert not (output / "attempts/terminal_migration_audit").exists()


def test_terminal_migration_rejects_archive_core_and_resigned_plan_hashes(
    tmp_path: Path,
) -> None:
    core_root = tmp_path / "core"
    core_root.mkdir()
    network, output, archive = _copy_real_v2_archive(core_root)
    archive_manifest_path = archive / "attempt_archive_manifest.json"
    archive_manifest = json.loads(archive_manifest_path.read_text())
    archive_manifest.update(
        {"network_id": "huc8_FAKE", "role": "sealed", "network_plan_sha256": "0" * 64}
    )
    archive_manifest_path.write_text(
        json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n"
    )
    with RootExecutionLock(core_root) as root_lock:
        migrated, audit = _migrate_archived_terminal_without_provider(
            ROOT,
            core_root,
            output,
            network,
            archive,
            root_lock=root_lock,
        )
    assert migrated is None
    assert "archive core" in audit["rejection_reason"]

    plan_root = tmp_path / "plan"
    plan_root.mkdir()
    network, output, archive = _copy_real_v2_archive(plan_root)
    fake = "f" * 64
    request_plan_path = archive / "request_plan.json"
    request_plan = json.loads(request_plan_path.read_text())
    request_plan["network_plan_sha256"] = fake
    unhashed = dict(request_plan)
    unhashed.pop("request_plan_sha256")
    request_plan["request_plan_sha256"] = hashlib.sha256(
        json.dumps(
            unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    request_plan_path.write_text(
        json.dumps(request_plan, indent=2, sort_keys=True) + "\n"
    )
    old_manifest_path = archive / "network_manifest.json"
    old_manifest = json.loads(old_manifest_path.read_text())
    old_manifest["network_plan_sha256"] = fake
    old_manifest["artifacts"]["request_plan"].update(
        {
            "sha256": _sha256(request_plan_path),
            "bytes": request_plan_path.stat().st_size,
        }
    )
    old_manifest_path.write_text(
        json.dumps(old_manifest, indent=2, sort_keys=True) + "\n"
    )
    _rebuild_archive_inventory(archive)
    with RootExecutionLock(plan_root) as root_lock:
        migrated, audit = _migrate_archived_terminal_without_provider(
            ROOT,
            plan_root,
            output,
            network,
            archive,
            root_lock=root_lock,
        )
    assert migrated is None
    assert "reproducible historical plan" in audit["rejection_reason"]


def test_terminal_migration_rejects_unlogged_raw_symlink(tmp_path: Path) -> None:
    network, output, archive = _copy_real_v2_archive(tmp_path)
    logged = next((archive / "raw").rglob("*.request.json"))
    extra = archive / "raw/unlogged.request.json"
    extra.symlink_to(logged)
    _rebuild_archive_inventory(archive)
    with RootExecutionLock(tmp_path) as root_lock:
        migrated, audit = _migrate_archived_terminal_without_provider(
            ROOT,
            tmp_path,
            output,
            network,
            archive,
            root_lock=root_lock,
        )
    assert migrated is None
    assert "contains a symlink" in audit["rejection_reason"]
    assert extra.is_symlink()


def test_terminal_migration_io_failure_is_fail_closed_and_audit_chained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    network, output, archive = _copy_real_v2_archive(tmp_path)

    def fail_copy(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("injected staging write failure")

    monkeypatch.setattr(acquisition_v2, "_copy_verified_raw_files", fail_copy)
    with (
        RootExecutionLock(tmp_path) as root_lock,
        pytest.raises(OSError, match="injected staging write failure"),
    ):
        _migrate_archived_terminal_without_provider(
            ROOT,
            tmp_path,
            output,
            network,
            archive,
            root_lock=root_lock,
        )
    assert not any(path.name.startswith(".terminal_migration_") for path in output.iterdir())
    assert not (output / "network_manifest.json").exists()
    audits = sorted((output / "attempts/terminal_migration_audit").glob("*.json"))
    assert len(audits) == 2
    accepted, failed = (json.loads(path.read_text()) for path in audits)
    assert accepted["accepted"] is True
    assert failed["accepted"] is False
    assert failed["fallback"] == "none_internal_or_io_failure_fail_closed"
    assert failed["previous_audit_path"] == str(audits[0].relative_to(output))
    assert failed["previous_audit_sha256"] == _sha256(audits[0])
