from pathlib import Path

import pandas as pd

from stream_recoverability.experiments.development_data import (
    complete_operator_network_predictions,
    load_auxiliary_networks,
    station_gap_outcomes,
)


def test_station_gap_outcomes_keeps_placement_variability() -> None:
    rows = pd.DataFrame(
        {
            "network_id": ["n1", "n1", "n1"],
            "station_id": ["s1", "s1", "s1"],
            "gap_length": [90, 90, 90],
            "model": ["xgboost", "xgboost", "kalman"],
            "information_condition": ["B_union_D", "B_union_D", "B"],
            "status": ["complete", "complete", "complete"],
            "observed_recovery_loss": [1.0, 3.0, 8.0],
            "predicted_conditional_risk": [1.5, 1.5, 2.0],
            "donor_r2_only": [0.4, 0.4, 0.4],
        }
    )

    result = station_gap_outcomes(rows)

    assert result.loc[0, "realized_loss"] == 2.0
    assert result.loc[0, "placement_sd"] == 2**0.5
    assert result.loc[0, "n_placements"] == 2


def test_load_auxiliary_networks_adds_network_id(tmp_path: Path) -> None:
    path = tmp_path / "development/networks/n1"
    path.mkdir(parents=True)
    pd.DataFrame(
        {"date": ["2020-01-01"], "site_id": ["s1"], "variable": ["Ta"], "value": [3.0]}
    ).to_parquet(path / "daily_long_auxiliary.parquet", index=False)

    result = load_auxiliary_networks(tmp_path)

    assert result.loc[0, "network_id"] == "n1"


def test_complete_operator_network_predictions_binds_meteorology_and_flow(
    tmp_path: Path,
) -> None:
    dates = pd.date_range("2010-01-01", periods=800, freq="D")
    phase = pd.Series(range(len(dates)), dtype=float)
    temperature = pd.DataFrame(
        {
            "date": dates,
            "s1": 10 + (phase / 20).map(__import__("math").sin),
            "s2": 11 + (phase / 23).map(__import__("math").sin),
        }
    )
    temperature_path = tmp_path / "temperature.csv"
    temperature.to_csv(temperature_path, index=False)
    auxiliary_rows = []
    for site in ("s1", "s2"):
        for variable, offset in (("Ta", 0.0), ("F", 1.0)):
            for index, date in enumerate(dates):
                auxiliary_rows.append(
                    {
                        "date": date,
                        "site_id": site,
                        "variable": variable,
                        "value": offset + index / 100.0,
                    }
                )
    auxiliary_path = tmp_path / "auxiliary.parquet"
    pd.DataFrame(auxiliary_rows).to_parquet(auxiliary_path, index=False)

    result = complete_operator_network_predictions(
        temperature_path,
        auxiliary_path,
        network_id="n1",
        gaps=(7,),
    )

    assert len(result) == 2
    assert result["meteorology_incremental_information"].notna().all()
    assert result["hydraulics_incremental_information"].notna().all()
    assert result["operator_training_years"].eq("2010|2011").all()

    temperature.loc[temperature["date"].dt.year.eq(2012), ["s1", "s2"]] += 500.0
    temperature.to_csv(temperature_path, index=False)
    auxiliary = pd.DataFrame(auxiliary_rows)
    auxiliary.loc[pd.to_datetime(auxiliary["date"]).dt.year.eq(2012), "value"] += 500.0
    auxiliary.to_parquet(auxiliary_path, index=False)
    rerun = complete_operator_network_predictions(
        temperature_path,
        auxiliary_path,
        network_id="n1",
        gaps=(7,),
    )
    columns = [
        column
        for column in result.columns
        if pd.api.types.is_numeric_dtype(result[column])
    ]
    pd.testing.assert_frame_equal(result[columns], rerun[columns])

    missing_date = pd.Timestamp("2011-03-01")
    sparse_temperature = temperature.loc[~temperature["date"].eq(missing_date)]
    explicit_temperature = temperature.copy()
    explicit_temperature.loc[
        explicit_temperature["date"].eq(missing_date), ["s1", "s2"]
    ] = float("nan")
    sparse_auxiliary = auxiliary.loc[
        ~pd.to_datetime(auxiliary["date"]).eq(missing_date)
    ]
    sparse_temperature.to_csv(tmp_path / "sparse.csv", index=False)
    explicit_temperature.to_csv(tmp_path / "explicit.csv", index=False)
    sparse_auxiliary.to_parquet(tmp_path / "sparse_aux.parquet", index=False)
    sparse = complete_operator_network_predictions(
        tmp_path / "sparse.csv",
        tmp_path / "sparse_aux.parquet",
        network_id="n1",
        gaps=(7,),
    )
    explicit = complete_operator_network_predictions(
        tmp_path / "explicit.csv",
        tmp_path / "sparse_aux.parquet",
        network_id="n1",
        gaps=(7,),
    )
    pd.testing.assert_frame_equal(sparse[columns], explicit[columns])
