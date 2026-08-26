from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.t2_online_causal import (
    NONNEGATIVE_DONOR_LAGS,
    bind_online_item,
    build_online_workload_manifest,
    causal_exposure,
    execute_online_item,
    iter_online_workload,
    online_cell_contract,
    placement_signature,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
    load_v91_budget,
)

ROOT = Path(__file__).resolve().parents[1]


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, OpenNetwork, pd.DataFrame]:
    directory = (
        tmp_path
        / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6/development"
        / "networks/huc8_online"
    )
    directory.mkdir(parents=True)
    index = pd.date_range("2016-01-01", periods=365 * 5, freq="D")
    day = np.arange(len(index), dtype=float)
    frame = pd.DataFrame(
        {
            "target": 11.0 + 2.0 * np.sin(day / 37.0),
            "donor": 10.0 + 1.5 * np.sin((day - 2.0) / 37.0),
        },
        index=index,
    )
    frame.index.name = "date"
    path = directory / "daily_wide_qc.csv"
    frame.to_csv(path)
    network = OpenNetwork(
        network_id="huc8_online",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path=str(path.relative_to(tmp_path)),
        wide_sha256=_file_sha(path),
        manifest_path="unused.json",
        n_days=len(frame),
        n_stations=2,
    )
    return tmp_path, network, frame


def _offline_item(*, model: str = "donor_regression", information: str = "B_union_D") -> WorkItem:
    return WorkItem(
        ordinal=7,
        item_id="offline-item",
        network_id="huc8_online",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        target_station="target",
        model=model,
        gap_length=30,
        placement=3,
        start_index=1200,
        information_condition=information,
        geometry="artificial_stress",
        boundary_mode="both",
    )


def _rewrite(
    repo: Path, network: OpenNetwork, frame: pd.DataFrame
) -> OpenNetwork:
    path = repo / network.wide_path
    frame.to_csv(path)
    return replace(network, wide_sha256=_file_sha(path))


def test_online_binding_preserves_frozen_placement_and_identity() -> None:
    offline = _offline_item()
    online = bind_online_item(offline)
    assert online.task == "online_causal"
    assert online.item_id != offline.item_id
    assert placement_signature(online) == placement_signature(offline)
    for field in (
        "start_index",
        "gap_length",
        "placement",
        "geometry",
        "geometry_id",
        "truth_start_date",
        "donor_mask_rule",
    ):
        assert getattr(online, field) == getattr(offline, field)


def test_online_exposure_hides_gap_and_all_later_target(tmp_path: Path) -> None:
    _, _, frame = _fixture(tmp_path)
    item = bind_online_item(_offline_item())
    exposed, train = causal_exposure(frame, item)
    stop = item.start_index + item.gap_length
    assert len(exposed) == stop
    assert exposed["target"].iloc[item.start_index :].isna().all()
    assert train.iloc[: item.start_index].all()
    assert not train.iloc[item.start_index :].any()
    assert NONNEGATIVE_DONOR_LAGS == tuple(range(31))


def test_future_target_and_right_boundary_cannot_change_prediction(tmp_path: Path) -> None:
    repo, network, frame = _fixture(tmp_path)
    item = bind_online_item(_offline_item())
    original = execute_online_item(repo, network, item)
    assert original["status"] == "complete"
    assert original["right_boundary_exposed_to_model"] is False
    assert original["post_gap_target_exposed_to_model"] is False

    changed = frame.copy()
    # Includes hidden truth, the right boundary, and every post-gap target.
    changed.iloc[item.start_index :, changed.columns.get_loc("target")] += 1000.0
    # Donor observations strictly after the scored interval are also unavailable.
    stop = item.start_index + item.gap_length
    changed.iloc[stop:, changed.columns.get_loc("donor")] -= 500.0
    changed_network = _rewrite(repo, network, changed)
    rerun = execute_online_item(repo, changed_network, item)
    assert rerun["status"] == "complete"
    assert rerun["prediction_sha256"] == original["prediction_sha256"]


def test_left_history_is_consumed_but_offline_model_identities_are_not_renamed(
    tmp_path: Path,
) -> None:
    repo, network, frame = _fixture(tmp_path)
    donor = bind_online_item(_offline_item())
    original = execute_online_item(repo, network, donor)
    changed = frame.copy()
    changed.iloc[donor.start_index - 1, changed.columns.get_loc("target")] += 100.0
    changed_network = _rewrite(repo, network, changed)
    rerun = execute_online_item(repo, changed_network, donor)
    assert rerun["prediction_sha256"] != original["prediction_sha256"]

    for model, reason in (
        ("pchip_or_linear", "registered_pchip_or_linear_identity_requires_future_boundary"),
        ("kalman", "registered_kalman_smoother_identity_uses_future_observations"),
    ):
        item = bind_online_item(_offline_item(model=model, information="B"))
        contract = online_cell_contract(item)
        assert contract["category"] == "structural_not_applicable"
        assert contract["reason"] == reason


def test_manifest_counts_partition_the_shared_artificial_grid(tmp_path: Path) -> None:
    repo, network, _ = _fixture(tmp_path)
    budget = load_v91_budget(ROOT)
    inventory = {"sealed_input_roots_allowed": [], "qualification_mode": "fixture"}
    manifest = build_online_workload_manifest(
        repo,
        [network],
        inventory,
        budget,
        include_frozen_geometry=False,
    )
    expected = 2 * 7 * 5 * 20 * 5
    assert manifest["n_work_items"] == expected
    assert sum(
        manifest["counts"][name]
        for name in (
            "executable",
            "reference",
            "structural_not_applicable",
            "data_ineligible",
            "external_dependency",
        )
    ) == expected
    assert manifest["placement_binding"]["reselected_for_online"] is False
    assert manifest["formal_evidence"] is False
    items = iter_online_workload(
        repo,
        [network],
        budget,
        include_frozen_geometry=False,
        models=["donor_regression"],
        gaps=[30],
        information_conditions=["D", "B_union_D"],
    )
    by_slot: dict[tuple[str, int], set[int]] = {}
    for item in items:
        by_slot.setdefault((item.target_station, item.placement), set()).add(
            item.start_index
        )
    assert all(len(starts) == 1 for starts in by_slot.values())
