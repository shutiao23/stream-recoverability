import numpy as np
import pandas as pd

from stream_recoverability.experiments.tr_revision.outputs import (
    release_states,
    water_air_agreement,
)
from stream_recoverability.experiments.tr_revision.native_temperature import (
    native_series,
)


def test_three_outputs_use_visible_information_and_preserve_only_valid_bounds():
    c = pd.DataFrame(
        {
            "D2": [20.0, 20.0, 20.0, np.nan],
            "risk_score": [0.01, 0.5, 0.01, np.nan],
            "n_complete_years": [5, 5, 5, 0],
            "visible_edge_anomaly": [0, 0, 0, 0],
            "observed_lower_bound__observed_days": [19.0, 19.0, 19.0, np.nan],
            "eval_truth_h30": [20.0, 20.0, 20.0, 20.0],
        }
    )
    quality = [False, False, True, False]
    states = release_states(c, {"visible_edge_anomaly": 2.0}, quality)
    assert states.tolist() == ["estimate", "observed_bound", "unknown", "unknown"]
    c.eval_truth_h30 += 1000
    np.testing.assert_array_equal(
        states, release_states(c, {"visible_edge_anomaly": 2.0}, quality)
    )


def test_air_agreement_requires_seven_contiguous_visible_days():
    air = np.arange(20.0)
    observed = air + 2
    observed[5:12] = air[5:12]
    assert water_air_agreement(observed, air) == 0
    observed[8] = np.nan
    assert water_air_agreement(observed, air) > 0


def test_provider_empty_year_is_missing_and_is_distinct_from_a_server_error():
    empty = native_series(
        b"<Hilltop><Agency>GWRC</Agency></Hilltop>", site="X", series_type="StdSeries"
    )
    assert empty.empty and str(empty.index.tz) == "UTC+12:00"
