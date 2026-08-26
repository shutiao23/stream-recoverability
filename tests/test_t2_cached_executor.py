from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

import stream_recoverability.experiments.t2_cached_executor as cache_module
import stream_recoverability.experiments.t2_recovery_benchmark as benchmark
from stream_recoverability.experiments.t2_cached_executor import (
    NetworkExecutionCache,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    RUNNER_CONTRACT_VERSION,
    OpenNetwork,
    WorkItem,
    _fit_cache_key,
    _year_split,
)


def _without_runtime(result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in result.items() if key != "runtime_seconds"}


def test_cache_is_custody_checked_and_numerically_equivalent(monkeypatch) -> None:
    index = pd.date_range("2018-01-01", periods=2_000, freq="D")
    phase = np.arange(len(index), dtype=float)
    panel = pd.DataFrame(
        {
            "target": 12.0 + np.sin(phase / 37.0),
            "donor": 11.0 + np.cos(phase / 41.0),
        },
        index=index,
    )
    network = OpenNetwork(
        network_id="huc8_cache_test",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="open/daily_wide_qc.csv",
        wide_sha256="a" * 64,
        manifest_path="open/network_manifest.json",
        n_days=len(panel),
        n_stations=2,
    )
    template = WorkItem(
        ordinal=0,
        item_id="item-0",
        network_id=network.network_id,
        role=network.role,
        source_key=network.source_key,
        target_station="target",
        model="climatology",
        gap_length=7,
        placement=0,
        start_index=1_600,
        information_condition="B",
    )
    items = [
        replace(
            template,
            ordinal=ordinal,
            item_id=f"item-{ordinal}",
            placement=ordinal // 3,
            start_index=1_600 + (ordinal // 3) * 20,
            model=("climatology", "pchip_or_linear", "kalman")[ordinal % 3],
        )
        for ordinal in range(6)
    ]

    reads = {"legacy": 0, "cached": 0}

    def legacy_read(*_args, **_kwargs):
        reads["legacy"] += 1
        return panel.copy()

    def cached_read(*_args, **_kwargs):
        reads["cached"] += 1
        return panel.copy()

    monkeypatch.setattr(benchmark, "read_panel", legacy_read)
    legacy = [benchmark.execute_item(".", network, item) for item in items]
    monkeypatch.setattr(cache_module, "read_panel", cached_read)
    cache = NetworkExecutionCache(".")
    optimized = [cache.execute(network, item) for item in items]

    assert [_without_runtime(row) for row in optimized] == [
        _without_runtime(row) for row in legacy
    ]
    assert reads == {"legacy": 6, "cached": 1}
    assert cache.stats() == {
        "cache_contract_version": "t2_network_panel_climatology_cache_v1",
        "panels_cached": 1,
        "panel_cache_hits": 5,
        "panel_cache_misses_custody_reads": 1,
        "climatology_entries": 2,
        "climatology_cache_hits": 4,
        "climatology_cache_misses_fits": 2,
    }
    assert all(row["status"] in {"complete", "reference_complete"} for row in optimized)
    assert all(row["sealed_temperature_records_read"] is False for row in optimized)
    assert all(row["runner_contract_version"] == RUNNER_CONTRACT_VERSION for row in optimized)


def test_same_network_id_with_changed_custody_identity_is_read_again(monkeypatch) -> None:
    index = pd.date_range("2020-01-01", periods=10, freq="D")
    panel = pd.DataFrame({"target": np.arange(10, dtype=float)}, index=index)
    network = OpenNetwork(
        network_id="huc8_identity_test",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="open/daily_wide_qc.csv",
        wide_sha256="a" * 64,
        manifest_path="open/network_manifest.json",
        n_days=len(panel),
        n_stations=1,
    )
    changed = replace(network, wide_sha256="b" * 64)
    reads: list[tuple[str, str, str]] = []

    def custody_read(_repo, selected: OpenNetwork):
        reads.append(
            (
                selected.network_id,
                selected.wide_sha256,
                selected.wide_path,
            )
        )
        return panel.copy()

    monkeypatch.setattr(cache_module, "read_panel", custody_read)
    cache = NetworkExecutionCache(".")
    cache.panel(network)
    cache.panel(network)
    cache.panel(changed)

    assert reads == [
        (network.network_id, network.wide_sha256, network.wide_path),
        (changed.network_id, changed.wide_sha256, changed.wide_path),
    ]
    assert cache.stats()["panels_cached"] == 2
    assert cache.stats()["panel_cache_misses_custody_reads"] == 2
    assert cache.stats()["panel_cache_hits"] == 1


def test_strict_fit_key_binds_only_declared_training_identity() -> None:
    index = pd.date_range("2018-01-01", periods=1_100, freq="D")
    panel = pd.DataFrame(
        {
            "target": np.arange(len(index), dtype=float),
            "donor": np.arange(len(index), dtype=float) / 2.0,
        },
        index=index,
    )
    train, _ = _year_split(index)
    mask = pd.Series(train, index=index)

    def key(**overrides):
        arguments = {
            "input_sha256": "a" * 64,
            "target_station": "target",
            "model": "donor_regression",
            "information_condition": "D",
            "meteorology_lag_days": None,
            "frame": panel,
            "train_mask": mask,
            "feature_columns": ["target", "donor"],
        }
        arguments.update(overrides)
        return _fit_cache_key(**arguments)

    baseline = key()
    heldout_truth_changed = panel.copy()
    heldout_truth_changed.loc[~mask, "target"] += 1_000_000.0
    assert key(frame=heldout_truth_changed) == baseline

    training_feature_changed = panel.copy()
    training_feature_changed.loc[mask, "donor"] += 1.0
    assert key(frame=training_feature_changed) != baseline
    changed_mask = mask.copy()
    changed_mask.iloc[0] = False
    assert key(train_mask=changed_mask) != baseline
    assert key(input_sha256="b" * 64) != baseline
    assert key(target_station="another_target") != baseline
    assert key(model="xgboost") != baseline
    assert key(information_condition="B_union_D") != baseline
    assert key(meteorology_lag_days=1) != baseline
