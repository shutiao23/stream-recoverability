from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data.open_role_corpus_qc import (
    parse_nwis_daily_json,
    run_open_role_qc,
)
from stream_recoverability.data.sealed_corpus import (
    LOCKED_SPLIT_SHA256,
    HUC8CorpusGate,
    LockedV3Catalog,
    SealedOutcomeAccessError,
)


def _response(site_id: str, values: list[float]) -> bytes:
    dates = pd.date_range("2020-01-01", periods=len(values), freq="D")
    document = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteCode": [{"value": site_id}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "value": str(value),
                                    "qualifiers": ["A"],
                                    "dateTime": date.isoformat(),
                                }
                                for date, value in zip(dates, values)
                            ]
                        }
                    ],
                }
            ]
        }
    }
    return json.dumps(document).encode("utf-8")


def _catalog(role: str) -> LockedV3Catalog:
    sites = ("site_a", "site_b", "site_sentinel", "site_missing")
    end = (
        pd.Timestamp("2020-01-01") + pd.Timedelta(days=8 * 365 - 1)
    ).date().isoformat()
    return LockedV3Catalog(
        roles={"huc8_test": role},
        stations={"huc8_test": sites},
        dates={site: ("2020-01-01", end) for site in sites},
        split_sha256=LOCKED_SPLIT_SHA256,
    )


def _gate(catalog: LockedV3Catalog, tmp_path: Path) -> HUC8CorpusGate:
    return HUC8CorpusGate(
        catalog,
        readable_cache=tmp_path / "readable",
        sealed_vault=tmp_path / "sealed",
        registry_dir=tmp_path / "registry",
    )


def test_open_role_qc_uses_gate_and_only_registered_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog("validation")
    gate = _gate(catalog, tmp_path)
    n_days = 8 * 365
    a_values = [10.0 + (index % 100) / 100.0 for index in range(n_days)]
    b_values = [11.0 + (index % 100) / 100.0 for index in range(n_days)]
    gate.cache_stream("huc8_test", "site_a", [_response("site_a", a_values)])
    gate.cache_stream("huc8_test", "site_b", [_response("site_b", b_values)])
    sentinel_values = [12.0 + (index % 100) / 100.0 for index in range(n_days)]
    sentinel_values[-1] = -9999.0
    gate.cache_stream(
        "huc8_test",
        "site_sentinel",
        [_response("site_sentinel", sentinel_values)],
    )

    opened: list[str] = []
    original_open = gate.open_for_qc

    def observed_open(network_id: str, path: str | Path):
        opened.append(str(path))
        return original_open(network_id, path)

    monkeypatch.setattr(gate, "open_for_qc", observed_open)
    output = tmp_path / "qc"
    manifest = run_open_role_qc(
        role="validation",
        output_dir=output,
        catalog=catalog,
        gate=gate,
    )
    assert len(opened) == 3
    assert all("/validation/huc8_test/" in path for path in opened)
    assert manifest["n_registry_objects_reused"] == 3
    assert manifest["n_objects_not_downloaded"] == 1
    assert manifest["sealed_temperature_records_read"] is False

    network = output / "networks/huc8_test"
    expected = {
        "daily_long_qc.csv",
        "daily_wide_qc.csv",
        "ingest_qc_report.csv",
        "attrition_summary.csv",
        "network_qc_manifest.json",
    }
    assert expected.issubset({path.name for path in network.iterdir()})
    report = pd.read_csv(network / "ingest_qc_report.csv", dtype={"site_id": str})
    assert set(report["site_id"]) == {"site_a", "site_b", "site_sentinel"}
    assert report.set_index("site_id").loc["site_sentinel", "verdict"] == "rejected_sentinel"
    clean = pd.read_csv(network / "daily_long_qc.csv", dtype={"site_id": str})
    assert set(clean["site_id"]) == {"site_a", "site_b"}
    wide = pd.read_csv(network / "daily_wide_qc.csv", index_col=0)
    assert set(wide.columns) == {"site_a", "site_b"}
    attrition = pd.read_csv(network / "attrition_summary.csv").set_index("stage")
    assert int(attrition.loc["locked_network_members", "n"]) == 4
    assert int(attrition.loc["registered_raw_objects", "n"]) == 3
    assert int(attrition.loc["rejected_sentinel", "n"]) == 1


def test_sealed_role_is_rejected_before_any_gate_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog("sealed")
    gate = _gate(catalog, tmp_path)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("sealed gate open was reached")

    monkeypatch.setattr(gate, "open_registered_for_qc", forbidden)
    with pytest.raises(SealedOutcomeAccessError, match="not available"):
        run_open_role_qc(
            role="sealed",
            output_dir=tmp_path / "qc",
            catalog=catalog,
            gate=gate,
        )


def test_parser_rejects_response_for_another_station(tmp_path: Path) -> None:
    path = tmp_path / "response.json"
    path.write_bytes(_response("wrong_site", [10.0]))
    with path.open("rb") as handle, pytest.raises(ValueError, match="differs"):
        parse_nwis_daily_json(
            handle,
            expected_site_id="expected_site",
            expected_start="2020-01-01",
            expected_end="2020-01-01",
        )
