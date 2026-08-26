from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.data.t2_information_adapters import (
    attach_information_features,
    fit_t2_information_adapter,
)


def _provider_fixture(index: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for site_offset, site in enumerate(("a", "b")):
        for variable_offset, variable in enumerate(("Ta", "P", "W", "RH", "Rs")):
            for ordinal, date in enumerate(index):
                rows.append(
                    {
                        "date": date,
                        "site_id": site,
                        "variable": variable,
                        "value": ordinal + site_offset + variable_offset / 10,
                        "source": "nasa_power_daily_point",
                        "natural_observed": True,
                        "qc_status": "provider_value",
                        # POWER has no observation-level approval status.
                        "approval_status": "NotApplicable",
                        "quality_approved": True,
                    }
                )
        for variable_offset, variable in enumerate(("F", "L")):
            for ordinal, date in enumerate(index):
                rows.append(
                    {
                        "date": date,
                        "site_id": site,
                        "variable": variable,
                        "value": ordinal + site_offset + variable_offset / 10,
                        "source": "usgs_ogc_daily",
                        "natural_observed": True,
                        "qc_status": "approved",
                        "approval_status": "Approved",
                        "quality_approved": True,
                    }
                )
    return pd.DataFrame(rows)


def test_nested_mh_adapter_is_train_fit_and_target_blind() -> None:
    index = pd.date_range("2018-01-01", periods=12, freq="D")
    daily = _provider_fixture(index)
    # An unrelated temperature channel must never affect M/H output.
    temperature = pd.DataFrame(
        {
            "date": index,
            "site_id": "a",
            "variable": "T",
            "value": np.arange(len(index), dtype=float),
            "source": "usgs_ogc_daily",
            "natural_observed": True,
            "qc_status": "approved",
            "approval_status": "Approved",
            "quality_approved": True,
        }
    )
    daily = pd.concat([daily, temperature], ignore_index=True)
    train_mask = pd.Series([True] * 8 + [False] * 4, index=index)
    fitted = fit_t2_information_adapter(
        daily,
        target_index=index,
        train_mask=train_mask,
        site_ids=["a", "b"],
        condition="B_union_D_union_M_union_H",
    )
    original = fitted.transform(daily)
    assert original.features.shape == (12, 14)
    assert fitted.centers["a__M__Ta"] == pytest.approx(3.5)
    assert original.features.loc[index[:8], "a__M__Ta"].mean() == pytest.approx(0.0)
    assert original.audit["temperature_columns_consumed"] == 0
    assert (
        fitted.manifest()["leakage_boundary"]["fit_statistics"]
        == "train_days_only"
    )

    changed = daily.copy()
    changed.loc[changed["variable"].eq("T"), "value"] += 1_000_000
    target_changed = fitted.transform(changed)
    pd.testing.assert_frame_equal(original.features, target_changed.features)


def test_provider_qc_rejects_power_fill_and_provisional_hydraulics() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="D")
    daily = _provider_fixture(index)
    power = (
        daily["site_id"].eq("a")
        & daily["variable"].eq("Ta")
        & daily["date"].eq(index[1])
    )
    daily.loc[power, ["value", "qc_status", "natural_observed"]] = [
        -999.0,
        "provider_fill_value",
        False,
    ]
    provisional = (
        daily["site_id"].eq("a")
        & daily["variable"].eq("F")
        & daily["date"].eq(index[2])
    )
    daily.loc[provisional, ["approval_status", "quality_approved", "qc_status"]] = [
        "Provisional",
        False,
        "excluded_provisional",
    ]
    fitted = fit_t2_information_adapter(
        daily,
        target_index=index,
        train_mask=np.ones(len(index), dtype=bool),
        site_ids=["a"],
        condition="B_union_D_union_M_union_H",
    )
    transformed = fitted.transform(daily)
    assert np.isnan(transformed.features.loc[index[1], "a__M__Ta"])
    assert np.isnan(transformed.features.loc[index[2], "a__H__F"])
    assert transformed.audit["n_provider_rejected_rows"] == 2
    assert (
        transformed.audit["provider_qc_basis_counts"][
            "provider_screened_non_fill_not_provider_approval"
        ]
        > 0
    )


def test_meteorology_lag_convention_and_exact_join_are_explicit() -> None:
    index = pd.date_range("2021-01-01", periods=5, freq="D")
    daily = _provider_fixture(index)
    fitted = fit_t2_information_adapter(
        daily,
        target_index=index,
        train_mask=np.ones(len(index), dtype=bool),
        site_ids=["a"],
        condition="B_union_D_union_M",
        meteorology_lag_days=1,
    )
    transformed = fitted.transform(daily)
    # Source Jan 2 is attached to target Jan 1 when lag_days=+1.
    expected = (1.0 - fitted.centers["a__M__Ta"]) / fitted.scales["a__M__Ta"]
    assert transformed.features.loc[index[0], "a__M__Ta"] == pytest.approx(expected)
    assert np.isnan(transformed.features.loc[index[-1], "a__M__Ta"])
    assert "__H__" not in " ".join(transformed.features.columns)


def test_post_train_auxiliary_does_not_change_fitted_scaling() -> None:
    index = pd.date_range("2022-01-01", periods=8, freq="D")
    daily = _provider_fixture(index)
    train_mask = np.array([True] * 5 + [False] * 3)
    first = fit_t2_information_adapter(
        daily,
        target_index=index,
        train_mask=train_mask,
        site_ids=["a"],
        condition="B_union_D_union_M",
    )
    changed = daily.copy()
    post_train = changed["date"].isin(index[5:]) & changed["variable"].eq("Ta")
    changed.loc[post_train, "value"] += 50_000
    second = fit_t2_information_adapter(
        changed,
        target_index=index,
        train_mask=train_mask,
        site_ids=["a"],
        condition="B_union_D_union_M",
    )
    assert first.centers == second.centers
    assert first.scales == second.scales
    assert first.train_day_sha256 == second.train_day_sha256


def test_attach_requires_identical_daily_axis() -> None:
    index = pd.date_range("2023-01-01", periods=4, freq="D")
    daily = _provider_fixture(index)
    fitted = fit_t2_information_adapter(
        daily,
        target_index=index,
        train_mask=np.ones(len(index), dtype=bool),
        site_ids=["a"],
        condition="B_union_D_union_M",
    )
    bundle = fitted.transform(daily)
    panel = pd.DataFrame({"a": np.arange(4.0)}, index=index)
    joined = attach_information_features(panel, bundle)
    assert joined.shape == (4, 6)
    with pytest.raises(ValueError, match="not date-aligned"):
        attach_information_features(panel.iloc[:-1], bundle)
