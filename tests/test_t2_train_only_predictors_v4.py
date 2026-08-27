from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stream_recoverability.experiments.t2_train_only_predictors_v4 as v4_predictors
from stream_recoverability.experiments.t2_recovery_benchmark import OpenNetwork
from stream_recoverability.experiments.t2_train_only_predictors import (
    PREDICTOR_COLUMNS,
    PredictorContractError,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _panel() -> pd.DataFrame:
    index = pd.date_range("2001-01-01", "2008-12-31", freq="D")
    rng = np.random.default_rng(44)
    innovations = rng.normal(0.0, 0.2, size=(len(index), 3))
    values = np.empty_like(innovations)
    values[0] = innovations[0]
    for row in range(1, len(index)):
        values[row] = 0.68 * values[row - 1] + innovations[row]
    return pd.DataFrame(values, index=index, columns=["a", "b", "c"])


def test_predictor_v2_reuses_train_fit_for_arbitrary_gap_roster(monkeypatch) -> None:
    calls = 0
    original = v4_predictors._fit_var1

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(v4_predictors, "_fit_var1", counted)
    frame = v4_predictors.predict_network_panel_v2(
        "huc8_test", _panel(), role="development", gaps=(7, 8, 31, 365)
    )
    assert calls == 3
    assert len(frame) == 12
    assert sorted(frame["gap_length"].unique().tolist()) == [7, 8, 31, 365]
    assert frame[list(PREDICTOR_COLUMNS)].notna().all().all()


def _write_contract(tmp_path: Path, *, forbidden: bool = False) -> tuple[Path, Path]:
    repo = tmp_path
    design = repo / "configs/design_freeze_v9.yaml"
    design.parent.mkdir(parents=True)
    design.write_text("design_id: design_freeze_v9\n", encoding="utf-8")
    source = repo / "source_v3.json"
    inventory = {"sealed_input_roots_allowed": [], "catalog_split_sha256": "c" * 64}
    input_map = {"huc8_test": "a" * 64}
    source.write_text(
        json.dumps({"design_sha256": _sha(design), "input_inventory": inventory}),
        encoding="utf-8",
    )
    item = {
        "geometry": "artificial_stress",
        "gap_length": 7,
        **({"achieved_skill": 0.9} if forbidden else {}),
    }
    rows = []
    for ordinal, (geometry, gap) in enumerate(
        [("artificial_stress", 7), ("natural_outage", 31), ("adversarial_stress", 90)]
    ):
        value = dict(item, geometry=geometry, gap_length=gap)
        rows.append(
            {
                "ordinal": ordinal,
                "item_id": f"item-{ordinal}",
                "source_v3_ordinal": ordinal,
                "source_v3_item_id": f"source-{ordinal}",
                "network_id": "huc8_test",
                "meteorology_lag_days": "none",
                "source_item_json": json.dumps(value),
            }
        )
    index = repo / "item_index.parquet"
    pd.DataFrame(rows, columns=list(v4_predictors.EXPECTED_INDEX_COLUMNS)).to_parquet(
        index, index=False
    )
    item_record = {
        "manifest_schema": v4_predictors.V4_ITEM_INDEX_SCHEMA,
        "columns": list(v4_predictors.EXPECTED_INDEX_COLUMNS),
        "n_rows": len(rows),
        "path": index.name,
        "file_sha256": _sha(index),
        "work_item_identity_sha256": "b" * 64,
    }
    draft = repo / "index_draft_manifest.json"
    draft.write_text(
        json.dumps(
            {
                "manifest_schema": v4_predictors.V4_INDEX_DRAFT_SCHEMA,
                "sealed_paths_traversed": False,
                "sealed_temperature_records_read": False,
                "input_inventory": inventory,
                "source_v3_workload_path": source.name,
                "source_v3_workload_sha256": _sha(source),
                "network_ids": ["huc8_test"],
                "input_sha256_by_network": input_map,
                "input_sha256_by_network_sha256": _canonical_sha(input_map),
                "item_index": item_record,
            }
        ),
        encoding="utf-8",
    )
    return draft, design


def test_builder_binds_complete_index_roster_and_is_create_once(
    tmp_path: Path, monkeypatch
) -> None:
    draft, design = _write_contract(tmp_path)
    network = OpenNetwork(
        network_id="huc8_test",
        role="development",
        source_key="open",
        wide_path="open/panel.csv",
        wide_sha256="a" * 64,
        manifest_path="open/manifest.json",
        n_days=len(_panel()),
        n_stations=3,
    )
    monkeypatch.setattr(
        v4_predictors,
        "discover_failure_closure_networks",
        lambda _: ([network], {"roles": {"development": 1}}),
    )
    monkeypatch.setattr(v4_predictors, "read_panel", lambda *_: _panel())
    panel_path = tmp_path / network.wide_path
    panel_path.parent.mkdir()
    panel_path.write_text("open fixture", encoding="utf-8")
    output = tmp_path / "predictors"
    first = v4_predictors.build_v4_train_only_predictor_sidecar(
        repo_root=tmp_path,
        index_draft_manifest_path=draft,
        design_path=design,
        output_dir=output,
    )
    second = v4_predictors.build_v4_train_only_predictor_sidecar(
        repo_root=tmp_path,
        index_draft_manifest_path=draft,
        design_path=design,
        output_dir=output,
    )
    assert first == second
    assert first["manifest_schema"] == v4_predictors.SIDECAR_SCHEMA
    assert first["gaps"] == [7, 31, 90]
    assert first["gaps_by_geometry"] == {
        "adversarial_stress": [90],
        "artificial_stress": [7],
        "natural_outage": [31],
    }
    assert first["n_rows"] == 9
    assert first["achieved_skill_read"] is False
    assert first["item_index_sha256"] == _sha(tmp_path / "item_index.parquet")
    assert first["input_inventory_sha256"] == _canonical_sha({"huc8_test": "a" * 64})


def test_builder_rejects_outcome_field_in_item_index(tmp_path: Path) -> None:
    draft, design = _write_contract(tmp_path, forbidden=True)
    with pytest.raises(PredictorContractError, match="forbidden outcome"):
        v4_predictors.build_v4_train_only_predictor_sidecar(
            repo_root=tmp_path,
            index_draft_manifest_path=draft,
            design_path=design,
            output_dir=tmp_path / "predictors",
        )


def test_builder_refuses_sealed_output_before_read(tmp_path: Path) -> None:
    draft = tmp_path / "draft.json"
    design = tmp_path / "design.yaml"
    draft.write_text("not read", encoding="utf-8")
    design.write_text("not read", encoding="utf-8")
    with pytest.raises(PredictorContractError, match="sealed-path"):
        v4_predictors.build_v4_train_only_predictor_sidecar(
            repo_root=tmp_path,
            index_draft_manifest_path=draft,
            design_path=design,
            output_dir=tmp_path / "sealed_predictors",
        )
