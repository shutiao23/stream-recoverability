from __future__ import annotations

import numpy as np
import pandas as pd

import stream_recoverability.experiments.t2_information_runner_integration as integration
from stream_recoverability.experiments.t2_cached_executor import (
    StrictFitExecutionCache,
)
from stream_recoverability.experiments.t2_information_runner_integration import (
    METEOROLOGY_LAG_ROSTER,
    MaterializedAuxiliary,
    execute_materialized_information_item,
    prepare_information_item,
)
from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
)


def _panel() -> pd.DataFrame:
    index = pd.date_range("2018-01-01", periods=850, freq="D")
    phase = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            "01000001": 10.0 + np.sin(phase / 20.0),
            "01000002": 11.0 + np.cos(phase / 21.0),
            "01000003": 12.0 + np.sin(phase / 22.0),
        },
        index=index,
    )


def _auxiliary(index: pd.DatetimeIndex, *, include_level: bool) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    variables = ["Ta", "P", "W", "RH", "Rs", "F"]
    if include_level:
        variables.append("L")
    for site_offset, site in enumerate(("01000001", "01000002", "01000003")):
        for variable_offset, variable in enumerate(variables):
            meteorology = variable in {"Ta", "P", "W", "RH", "Rs"}
            for ordinal, date in enumerate(index):
                rows.append(
                    {
                        "date": date,
                        "site_id": site,
                        "variable": variable,
                        "value": ordinal / 100.0 + site_offset + variable_offset,
                        "source": (
                            "nasa_power_daily_point"
                            if meteorology
                            else "usgs_ogc_daily"
                        ),
                        "natural_observed": True,
                        "qc_status": "provider_value" if meteorology else "approved",
                        "approval_status": (
                            "NotApplicable" if meteorology else "Approved"
                        ),
                        "quality_approved": True,
                    }
                )
    return pd.DataFrame(rows)


def _item(condition: str) -> WorkItem:
    return WorkItem(
        ordinal=0,
        item_id="source-v3-item",
        network_id="huc8_01000000",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        target_station="01000001",
        model="donor_regression",
        gap_length=7,
        placement=0,
        start_index=800,
        information_condition=condition,
    )


def test_m_consumer_uses_exact_aligned_train_standardized_features() -> None:
    panel = _panel()
    prepared = prepare_information_item(
        panel,
        _auxiliary(panel.index, include_level=False),
        _item("B_union_D_union_M"),
    )
    assert prepared.supported is True
    assert prepared.category == "executable"
    assert prepared.model_frame is not None
    assert prepared.train_mask is not None
    assert prepared.boundary_feature in prepared.model_frame
    assert len(prepared.auxiliary_features) == 15
    assert all("__M__" in name for name in prepared.auxiliary_features)
    assert prepared.model_frame.loc[
        panel.index[800:807], "01000001"
    ].isna().all()
    first_feature = prepared.auxiliary_features[0]
    assert abs(
        prepared.model_frame.loc[prepared.train_mask, first_feature].mean()
    ) < 1e-12
    assert prepared.audit["meteorology_alignment"] == (
        "source_date_equals_target_date_plus_lag_days"
    )
    assert prepared.audit["meteorology_lag_roster"] == list(METEOROLOGY_LAG_ROSTER)
    assert prepared.audit["heldout_skill_used_to_select_meteorology_lag"] is False
    assert prepared.audit["adapter_manifest"]["leakage_boundary"][
        "fit_statistics"
    ] == "train_days_only"


def test_m_plus_h_missing_level_is_fail_closed_not_silently_dropped() -> None:
    panel = _panel()
    prepared = prepare_information_item(
        panel,
        _auxiliary(panel.index, include_level=False),
        _item("B_union_D_union_M_union_H"),
    )
    assert prepared.supported is False
    assert prepared.category == "data_ineligible"
    assert prepared.reason == (
        "requested_auxiliary_feature_coverage_incomplete_fail_closed"
    )
    assert prepared.model_frame is None
    assert prepared.auxiliary_features == ()
    assert prepared.audit["insufficient_train_features"] == [
        "01000001__H__L",
        "01000002__H__L",
        "01000003__H__L",
    ]
    assert prepared.audit["incomplete_gap_features"] == [
        "01000001__H__L",
        "01000002__H__L",
        "01000003__H__L",
    ]
    assert prepared.audit["requested_feature_roster_policy"] == (
        "all_station_by_frozen_group_variables_required_no_channel_substitution"
    )


def test_complete_m_plus_h_roster_is_executable_and_consumes_both_groups() -> None:
    panel = _panel()
    prepared = prepare_information_item(
        panel,
        _auxiliary(panel.index, include_level=True),
        _item("B_union_D_union_M_union_H"),
    )
    assert prepared.supported is True
    assert len(prepared.auxiliary_features) == 21
    assert any("__M__" in name for name in prepared.auxiliary_features)
    assert any("__H__" in name for name in prepared.auxiliary_features)
    assert prepared.audit["requested_information_groups"] == ["B", "D", "M", "H"]


def test_all_three_meteorology_lags_are_separate_required_cells() -> None:
    panel = _panel()
    daily = _auxiliary(panel.index, include_level=True)
    prepared = [
        prepare_information_item(
            panel,
            daily,
            _item("B_union_D_union_M_union_H"),
            meteorology_lag_days=lag,
        )
        for lag in METEOROLOGY_LAG_ROSTER
    ]
    assert all(cell.supported for cell in prepared)
    assert [cell.audit["meteorology_lag_days"] for cell in prepared] == [-1, 0, 1]
    assert len({cell.audit["adapter_cache_key"] for cell in prepared}) == 3


def test_adapter_cache_reuses_identical_network_train_condition_lag() -> None:
    panel = _panel()
    daily = _auxiliary(panel.index, include_level=False)
    cache = {}
    first = prepare_information_item(
        panel,
        daily,
        _item("B_union_D_union_M"),
        adapter_cache=cache,
        auxiliary_cache_identity="fixture-auxiliary-sha",
    )
    second_item = WorkItem(
        **{
            **_item("B_union_D_union_M").__dict__,
            "placement": 1,
            "start_index": 801,
        }
    )
    second = prepare_information_item(
        panel,
        daily,
        second_item,
        adapter_cache=cache,
        auxiliary_cache_identity="fixture-auxiliary-sha",
    )
    assert first.audit["adapter_cache_hit"] is False
    assert second.audit["adapter_cache_hit"] is True
    assert first.audit["adapter_cache_key"] == second.audit["adapter_cache_key"]
    assert len(cache) == 1


def test_candidate_executor_passes_all_m_features_to_model(
    monkeypatch,
) -> None:
    panel = _panel()
    daily = _auxiliary(panel.index, include_level=False)
    captured: dict[str, object] = {}

    class RecordingDonor:
        def __init__(self, donor_cols, target_col, *, covariate_cols):
            captured["donors"] = tuple(donor_cols)
            captured["target"] = target_col
            captured["covariates"] = tuple(covariate_cols)

        def fit(self, data, *, dates, train_mask):
            captured["fit_train_rows"] = int(train_mask.sum())
            return self

        def predict(self, data, *, dates):
            return pd.Series(10.0, index=data.index)

    monkeypatch.setattr(integration, "DonorRegressionBaseline", RecordingDonor)
    network = OpenNetwork(
        network_id="huc8_01000000",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="unused_with_preloaded_panel.csv",
        wide_sha256="0" * 64,
        manifest_path="unused_with_preloaded_panel.json",
        n_days=len(panel),
        n_stations=3,
    )
    auxiliary = MaterializedAuxiliary(
        daily_long=daily,
        coverage=pd.DataFrame(),
        audit={
            "daily_long_sha256": "1" * 64,
            "sealed_temperature_records_read": False,
        },
    )
    result = execute_materialized_information_item(
        ".",
        network,
        _item("B_union_D_union_M"),
        panel=panel,
        auxiliary=auxiliary,
    )
    assert result["status"] == "candidate_complete_not_formal"
    assert result["formal_evidence"] is False
    assert result["consumed_information"] == ["B", "D", "M"]
    covariates = captured["covariates"]
    assert isinstance(covariates, tuple)
    assert covariates[0] == "__boundary_B_prediction"
    assert len(covariates) == 16
    assert all("__M__" in name for name in covariates[1:])


def test_mh_model_fit_cache_is_semantically_equivalent_across_heldout_gaps() -> None:
    panel = _panel()
    daily = _auxiliary(panel.index, include_level=False)
    network = OpenNetwork(
        network_id="huc8_01000000",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="unused_with_preloaded_panel.csv",
        wide_sha256="0" * 64,
        manifest_path="unused_with_preloaded_panel.json",
        n_days=len(panel),
        n_stations=3,
    )
    auxiliary = MaterializedAuxiliary(
        daily_long=daily,
        coverage=pd.DataFrame(),
        audit={
            "daily_long_sha256": "1" * 64,
            "sealed_temperature_records_read": False,
        },
    )
    items = [
        _item("B_union_D_union_M"),
        WorkItem(
            **{
                **_item("B_union_D_union_M").__dict__,
                "ordinal": 1,
                "item_id": "source-v3-item-second-gap",
                "placement": 1,
                "start_index": 820,
            }
        ),
    ]
    legacy = [
        execute_materialized_information_item(
            ".", network, item, panel=panel, auxiliary=auxiliary
        )
        for item in items
    ]
    cache = StrictFitExecutionCache(".")
    adapter_cache = {}
    optimized = [
        execute_materialized_information_item(
            ".",
            network,
            item,
            panel=panel,
            auxiliary=auxiliary,
            adapter_cache=adapter_cache,
            fit_resolver=cache.resolve_fit,
        )
        for item in items
    ]
    fields = (
        "ordinal",
        "item_id",
        "status",
        "reason",
        "implementation",
        "n_scored",
        "mae_deg_c",
        "climatology_mae_deg_c",
        "achieved_skill",
        "prediction_sha256",
        "source_v3_runner_contract_version",
        "formal_evidence",
        "sealed_temperature_records_read",
    )
    assert [
        {field: row.get(field) for field in fields} for row in optimized
    ] == [{field: row.get(field) for field in fields} for row in legacy]
    assert [row["prediction_sha256"] for row in optimized] == [
        row["prediction_sha256"] for row in legacy
    ]
    assert cache.stats()["fit_cache_misses_by_model"] == {
        "climatology": 1,
        "donor_regression": 1,
    }
    assert cache.stats()["fit_cache_hits_by_model"] == {
        "climatology": 1,
        "donor_regression": 1,
    }


def test_extended_consumer_attrits_missing_climatology_training_target() -> None:
    panel = _panel()
    target = "01000001"
    truth = panel[target].iloc[800:807].copy()
    panel[target] = np.nan
    panel.loc[panel.index[800:807], target] = truth.to_numpy()
    network = OpenNetwork(
        network_id="huc8_01000000",
        role="development",
        source_key="open_role_qc/failure_closure6/development",
        wide_path="unused_with_preloaded_panel.csv",
        wide_sha256="0" * 64,
        manifest_path="unused_with_preloaded_panel.json",
        n_days=len(panel),
        n_stations=3,
    )
    auxiliary = MaterializedAuxiliary(
        daily_long=_auxiliary(panel.index, include_level=False),
        coverage=pd.DataFrame(),
        audit={
            "daily_long_sha256": "1" * 64,
            "sealed_temperature_records_read": False,
        },
    )

    result = execute_materialized_information_item(
        ".",
        network,
        _item("B_union_D_union_M"),
        panel=panel,
        auxiliary=auxiliary,
    )

    assert result["status"] == "data_ineligible"
    assert result["reason"] == (
        "undefined_skill_no_finite_climatology_training_targets"
    )
    assert "achieved_skill" not in result


def test_extended_consumer_blocks_masked_donors_before_reading_auxiliary() -> None:
    panel = _panel()
    item = WorkItem(
        **{
            **_item("B_union_D_union_M").__dict__,
            "donor_mask_rule": "mask_all_network_stations_during_gap",
        }
    )
    prepared = prepare_information_item(panel, pd.DataFrame(), item)
    assert prepared.supported is False
    assert prepared.category == "structural_not_applicable"
    assert prepared.reason == "D_information_masked_by_frozen_geometry"
