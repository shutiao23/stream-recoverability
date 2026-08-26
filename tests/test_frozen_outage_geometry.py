from __future__ import annotations

import json

import pandas as pd

from stream_recoverability.experiments.frozen_outage_geometry import (
    build_adversarial_catalog,
    build_binding_manifest,
    build_natural_outage_catalog,
    canonical_csv_sha256,
    load_frozen_geometry_bindings,
    load_open_role_availability,
    write_frozen_geometry_artifacts,
)


def _availability() -> pd.DataFrame:
    first = pd.date_range("2020-01-01", "2020-01-20", freq="D")
    second = pd.date_range("2020-01-28", "2021-12-31", freq="D")
    dates = first.append(second)
    rows = []
    for station in ("A", "B"):
        for date in dates:
            rows.append(
                {
                    "role": "development",
                    "network_id": "huc8_test",
                    "station_id": station,
                    "date": date,
                }
            )
    return pd.DataFrame(rows)


def test_natural_catalog_never_claims_truth_for_actual_missing_days() -> None:
    catalog = build_natural_outage_catalog(_availability())
    assert len(catalog) == 2
    assert catalog["length_days"].eq(7).all()
    assert ~catalog["actual_missing_truth_available"].any()
    assert catalog["benchmark_eligible"].all()
    assert catalog["benchmark_start_date"].notna().all()
    assert catalog["benchmark_end_date"].notna().all()
    assert catalog["benchmark_truth_source"].eq("held_out_observed_counterpart").all()
    missing_start = pd.to_datetime(catalog["start_date"])
    missing_end = pd.to_datetime(catalog["end_date"])
    counterpart_start = pd.to_datetime(catalog["benchmark_start_date"])
    counterpart_end = pd.to_datetime(catalog["benchmark_end_date"])
    assert ((counterpart_end < missing_start) | (counterpart_start > missing_end)).all()


def test_natural_catalog_blocks_geometry_without_counterpart() -> None:
    dates = pd.date_range("2020-01-01", "2020-01-21", freq="D").difference(
        pd.date_range("2020-01-08", "2020-01-14", freq="D")
    )
    availability = pd.DataFrame(
        {
            "role": "development",
            "network_id": "huc8_short",
            "station_id": "A",
            "date": dates,
        }
    )
    catalog = build_natural_outage_catalog(availability)
    assert len(catalog) == 1
    assert not bool(catalog.iloc[0]["benchmark_eligible"])
    assert catalog.iloc[0]["benchmark_truth_source"] == "unavailable"


def test_adversarial_catalog_has_resolved_truth_bearing_windows() -> None:
    catalog = build_adversarial_catalog(_availability(), lengths=(30,))
    assert not catalog.empty
    assert catalog["benchmark_eligible"].all()
    assert catalog["truth_source"].eq("held_out_observed_days").all()
    assert catalog["selection_uses_outcome_values"].eq(False).all()
    assert {"record_left_edge", "record_right_edge", "donor_thin", "synchronous_network_outage"}.issubset(
        set(catalog["stress_id"])
    )


def test_manifest_is_a_non_result_and_hash_is_order_stable() -> None:
    availability = _availability()
    natural = build_natural_outage_catalog(availability)
    adversarial = build_adversarial_catalog(availability, lengths=(30,))
    shuffled = natural.sample(frac=1.0, random_state=3)
    assert canonical_csv_sha256(natural) == canonical_csv_sha256(shuffled)
    manifest = build_binding_manifest(availability, natural, adversarial, {"sources": []})
    assert manifest["passed"] is False
    assert manifest["formal_evidence"] is False
    assert manifest["sealed_temperature_records_read"] is False
    assert manifest["outcome_columns_loaded"] == []
    assert "full_model_scoring_not_run" in manifest["blocked_cells"]


def test_sealed_role_is_rejected() -> None:
    availability = _availability()
    availability["role"] = "sealed"
    try:
        build_natural_outage_catalog(availability)
    except ValueError as error:
        assert "non-open role" in str(error)
    else:
        raise AssertionError("sealed role must be rejected")


def test_runner_loader_verifies_bytes_and_truth_contract(tmp_path) -> None:
    availability = _availability()
    natural = build_natural_outage_catalog(availability)
    adversarial = build_adversarial_catalog(availability, lengths=(30,))
    manifest = build_binding_manifest(availability, natural, adversarial, {"sources": []})
    write_frozen_geometry_artifacts(tmp_path, natural, adversarial, manifest)
    loaded_natural, loaded_adversarial, loaded_manifest = load_frozen_geometry_bindings(
        tmp_path
    )
    assert len(loaded_natural) == len(natural)
    assert len(loaded_adversarial) == len(adversarial)
    assert loaded_manifest["purpose"] == "geometry_binding_not_model_result"

    with (tmp_path / "natural_outage_catalog.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    try:
        load_frozen_geometry_bindings(tmp_path)
    except ValueError as error:
        assert "byte drift" in str(error)
    else:
        raise AssertionError("catalog byte drift must be rejected")


def test_open_role_loader_requires_closure6_and_complete_enough(tmp_path) -> None:
    common = {
        "qualification_mode": "failure_closure6",
        "qualified_years_min": 6,
        "relaxation_applied": True,
        "relaxation_trigger": "open_survival_projection_lt_100",
        "sealed_temperature_records_read": False,
        "split_sha256": "split-lock",
    }
    for role in ("development", "validation"):
        role_root = tmp_path / role
        (role_root / "networks").mkdir(parents=True)
        (role_root / "qc_manifest.json").write_text(
            json.dumps({**common, "role": role}), encoding="utf-8"
        )
    for network_id, complete in (("huc8_keep", True), ("huc8_skip", False)):
        network_root = tmp_path / "development" / "networks" / network_id
        network_root.mkdir()
        (network_root / "network_qc_manifest.json").write_text(
            json.dumps(
                {
                    **common,
                    "role": "development",
                    "network_id": network_id,
                    "overlap": {"complete_enough": complete},
                }
            ),
            encoding="utf-8",
        )
        pd.DataFrame(
            {"site_id": ["A"], "eligible_for_network": [True]}
        ).to_csv(network_root / "ingest_qc_report.csv", index=False)
        pd.DataFrame(
            {
                "site_id": ["A", "A", "A"],
                "date": pd.date_range("2020-01-01", periods=3),
                "temperature_c": [999.0, -999.0, 42.0],
            }
        ).to_csv(network_root / "daily_long_qc.csv", index=False)

    availability, audit = load_open_role_availability(tmp_path)
    assert set(availability["network_id"]) == {"huc8_keep"}
    assert list(availability.columns) == ["role", "network_id", "station_id", "date"]
    assert audit["n_sources"] == 1
    assert audit["split_sha256"] == "split-lock"

    manifest_path = tmp_path / "development" / "qc_manifest.json"
    wrong = json.loads(manifest_path.read_text(encoding="utf-8"))
    wrong["qualification_mode"] = "primary8"
    manifest_path.write_text(json.dumps(wrong), encoding="utf-8")
    try:
        load_open_role_availability(tmp_path)
    except ValueError as error:
        assert "failure-closure-6" in str(error)
    else:
        raise AssertionError("primary8 source must not enter a closure6 freeze")
