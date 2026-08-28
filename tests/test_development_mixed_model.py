import numpy as np
import pandas as pd

from stream_recoverability.analysis.development_mixed_model import (
    compare_mixed_models,
)


def test_mixed_model_reports_network_variance_and_operator_increment() -> None:
    rng = np.random.default_rng(10)
    rows = []
    for network in range(8):
        offset = rng.normal(0, 0.3)
        for station_gap in range(20):
            simple = rng.normal()
            operator = rng.normal()
            rows.append(
                {
                    "network_id": f"n{network}",
                    "simple": simple,
                    "operator": operator,
                    "observed_recovery_loss": 2 + offset + simple + 0.4 * operator + rng.normal(0, 0.1),
                }
            )
    summaries, increment = compare_mixed_models(
        pd.DataFrame(rows),
        simple_predictors=("simple",),
        operator="operator",
    )
    assert len(summaries) == 2
    assert summaries.iloc[1]["network_random_intercept_variance"] > 0
    assert increment["marginal_r2_increment"] > 0
    assert increment["likelihood_ratio_p"] < 0.05
