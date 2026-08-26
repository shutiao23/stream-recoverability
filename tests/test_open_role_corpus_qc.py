from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stream_recoverability.data.open_role_corpus_qc import (
    FAILURE_CLOSURE_MODE,
    FAILURE_CLOSURE_QUALIFIED_YEARS,
    FAILURE_CLOSURE_TRIGGER,
    PRIMARY_MODE,
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


def test_failure_closure_is_fixed_at_six_reparses_raw_and_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog("validation")
    gate = _gate(catalog, tmp_path)
    n_days = (
        pd.Timestamp("2026-01-02") - pd.Timestamp("2020-01-01")
    ).days + 1
    for offset, site_id in enumerate(("site_a", "site_b", "site_sentinel")):
        values = [10.0 + offset + (index % 100) / 100.0 for index in range(n_days)]
        gate.cache_stream("huc8_test", site_id, [_response(site_id, values)])

    output_root = tmp_path / "open_role_qc"
    primary_dir = output_root / "validation"
    primary = run_open_role_qc(
        role="validation",
        output_dir=primary_dir,
        catalog=catalog,
        gate=gate,
        qualification_mode=PRIMARY_MODE,
    )
    assert primary["n_networks_complete_enough"] == 0
    assert pd.read_csv(primary_dir / "networks/huc8_test/daily_long_qc.csv").empty
    primary_manifest_path = primary_dir / "qc_manifest.json"
    primary_manifest_before = primary_manifest_path.read_bytes()

    development_dir = output_root / "development"
    development_dir.mkdir(parents=True)
    (development_dir / "qc_manifest.json").write_text(
        json.dumps(
            {
                "role": "development",
                "split_sha256": LOCKED_SPLIT_SHA256,
                "sealed_temperature_records_read": False,
                "qualification_mode": PRIMARY_MODE,
                "relaxation_applied": False,
                "n_networks_selected": 102,
                "n_networks_complete_enough": 59,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must write"):
        run_open_role_qc(
            role="validation",
            output_dir=primary_dir,
            catalog=catalog,
            gate=gate,
            qualification_mode=FAILURE_CLOSURE_MODE,
        )
    with pytest.raises(ValueError, match="qualification_mode"):
        run_open_role_qc(
            role="validation",
            output_dir=output_root / "failure_closure5/validation",
            catalog=catalog,
            gate=gate,
            qualification_mode="failure_closure5",
        )
    assert primary_manifest_path.read_bytes() == primary_manifest_before

    opened = 0
    original_open = gate.open_for_qc

    def observed_open(network_id: str, path: str | Path):
        nonlocal opened
        opened += 1
        return original_open(network_id, path)

    monkeypatch.setattr(gate, "open_for_qc", observed_open)
    relaxed_dir = output_root / FAILURE_CLOSURE_MODE / "validation"
    relaxed = run_open_role_qc(
        role="validation",
        output_dir=relaxed_dir,
        catalog=catalog,
        gate=gate,
        qualification_mode=FAILURE_CLOSURE_MODE,
    )
    assert opened == 3
    assert relaxed["qualified_years_min"] == FAILURE_CLOSURE_QUALIFIED_YEARS == 6
    assert relaxed["relaxation_applied"] is True
    assert relaxed["relaxation_trigger"] == FAILURE_CLOSURE_TRIGGER
    assert relaxed["raw_registry_objects_reparsed"] is True
    assert relaxed["primary_8yr_clean_products_reused"] is False
    assert relaxed["primary_8yr_counts"]["open_complete_enough_total"] == 59
    assert relaxed["primary_8yr_counts"]["open_selected_total"] == 103
    assert relaxed["n_networks_complete_enough"] == 1
    clean = pd.read_csv(relaxed_dir / "networks/huc8_test/daily_long_qc.csv")
    assert set(clean["site_id"]) == {"site_a", "site_b", "site_sentinel"}
    assert primary_manifest_path.read_bytes() == primary_manifest_before
