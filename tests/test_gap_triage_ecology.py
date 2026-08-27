from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.experiments.gap_triage_ecology import ecological_bridge_for_scores


def test_ecological_bridge_uses_w2_plant_start_and_year_split() -> None:
    dates = pd.date_range("2010-01-01", periods=1200, freq="D")
    target = np.sin(np.arange(1200) / 30.0) + 10.0
    donor = target + 0.05 * np.sin(np.arange(1200) / 17.0)
    wide = pd.DataFrame({"s1": target, "s2": donor}, index=dates)
    plant_start = str(dates[800].date())
    scores = pd.DataFrame(
        {
            "network_id": ["net_a"],
            "station_id": ["s1"],
            "gap_length": [30],
            "plant_start": [plant_start],
            "predicted_conditional_risk": [0.01],
            "fill_mae": [0.2],
        }
    )
    payload = ecological_bridge_for_scores(
        scores,
        {"net_a": wide},
        freeze={"decision_endpoints": {"b_gap_triage": {"false_release_rate": 1.0}}},
    )
    assert payload["n_safe_rows"] >= 1
    assert payload["policy_summary"]["operator"]["n_safe_fills"] >= 1
