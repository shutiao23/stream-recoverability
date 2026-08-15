import numpy as np
import pandas as pd
import pytest

from stream_recoverability.models.baselines import (
    AirHydroBaseline,
    AirOnlyBaseline,
    ClimatologyBaseline,
    DonorRegressionBaseline,
    IndependentFlowBaseline,
    KalmanSmootherBaseline,
    OfflineLinearInterpolation,
    PCHIPInterpolation,
    RandomForestBaseline,
    RatingCurveBaseline,
)


def test_climatology_uses_only_training_and_doy_window():
    dates = pd.to_datetime(
        ["2019-01-01", "2019-01-14", "2020-01-07", "2020-01-14"]
    )
    frame = pd.DataFrame(
        {"date": dates, "T": [0.0, 100.0, 999.0, 999.0], "train": [1, 1, 0, 0]}
    )
    model = ClimatologyBaseline("T", window=7).fit(frame, train_mask="train")
    prediction = model.predict(frame)
    assert prediction.iloc[2] == pytest.approx(50.0)
    assert prediction.iloc[3] == pytest.approx(100.0)


def test_offline_interpolators_fill_only_bounded_gaps():
    series = pd.Series([np.nan, 0.0, np.nan, np.nan, 3.0, np.nan])
    linear = OfflineLinearInterpolation().predict(series)
    pchip = PCHIPInterpolation().predict(series)
    assert np.isnan(linear.iloc[0]) and np.isnan(linear.iloc[-1])
    assert np.isnan(pchip.iloc[0]) and np.isnan(pchip.iloc[-1])
    np.testing.assert_allclose(linear.iloc[2:4], [1.0, 2.0])
    np.testing.assert_allclose(pchip.iloc[2:4], [1.0, 2.0])
    with pytest.raises(ValueError, match="offline-only"):
        OfflineLinearInterpolation(online=True)


def test_kalman_smoother_produces_finite_gap_predictions():
    values = pd.Series(np.sin(np.linspace(0, 4, 50)) + np.linspace(0, 1, 50), name="T")
    model = KalmanSmootherBaseline("T").fit(values)
    masked = values.copy()
    masked.iloc[20:25] = np.nan
    prediction = model.predict(masked)
    assert np.isfinite(prediction.iloc[20:25]).all()


def test_air_models_and_random_forest_have_runnable_fit_predict():
    dates = pd.date_range("2018-01-01", periods=120, freq="D")
    air = np.linspace(-3.0, 15.0, len(dates))
    flow = 2.0 + np.sin(np.arange(len(dates)) / 9.0)
    level = 4.0 + flow / 10.0
    target = 1.5 * air + 0.4 * flow + np.sin(np.arange(len(dates)) / 20.0)
    frame = pd.DataFrame(
        {"date": dates, "Ta": air, "F": flow, "L": level, "T": target}
    )
    for model in (
        AirOnlyBaseline("Ta", "T"),
        AirHydroBaseline("Ta", ["F", "L"], "T"),
        RandomForestBaseline(["Ta", "F", "L"], "T", n_estimators=20),
    ):
        prediction = model.fit(frame).predict(frame)
        assert len(prediction) == len(frame)
        assert np.isfinite(prediction).all()


def test_donor_lag_is_selected_on_training_rows():
    rng = np.random.default_rng(4)
    donor = pd.Series(rng.normal(size=120))
    target = donor.shift(2)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2018-01-01", periods=120),
            "donor": donor,
            "target": target,
        }
    )
    model = DonorRegressionBaseline(
        ["donor"], "target", candidate_lags=range(-3, 4), harmonics=1, alpha=0.01
    ).fit(frame)
    assert model.selected_lags_["donor"] == 2
    prediction = model.predict(frame)
    valid = target.notna()
    assert np.corrcoef(target[valid], prediction[valid])[0, 1] > 0.99


def test_rating_curve_and_independent_flow_guard():
    level = np.linspace(1.0, 4.0, 40)
    flow = 2.0 * level**2 + 3.0 * level + 1.0
    frame = pd.DataFrame({"L": level, "F": flow})
    prediction = RatingCurveBaseline("L", "F", degree=2).fit(frame).predict(frame)
    np.testing.assert_allclose(prediction, flow, rtol=1e-8, atol=1e-8)
    with pytest.raises(ValueError, match="forbidden"):
        IndependentFlowBaseline(["donor_F", "L"], "L", "F")

