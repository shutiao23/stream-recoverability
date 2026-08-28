from __future__ import annotations

import numpy as np
import pandas as pd

from stream_recoverability.analysis.us_heterogeneity import (
    climate_band,
    collapse_climate_band,
    fit_mixed_calibration,
    infer_huc2,
    regulation_stratum,
    split_site_ids,
)


def test_network_metadata_parsers_cover_all_frozen_id_shapes() -> None:
    assert infer_huc2("huc8_02040101") == "02"
    assert infer_huc2("usgs_arkansas_river_huc11") == "11"
    assert infer_huc2("usgs2_huc2_08") == "08"
    assert infer_huc2("usgs2_huc4_0306") == "03"
    assert infer_huc2("usgs2_huc6_010802") == "01"
    assert infer_huc2("not_a_huc") is None
    assert climate_band("17") == "marine_west_coast"
    assert collapse_climate_band("humid_continental") == "humid"
    assert collapse_climate_band("hot_arid") == "arid_semiarid"
    assert split_site_ids("01234567|07654321,01111111") == [
        "01234567",
        "07654321",
        "01111111",
    ]


def test_regulation_stratum_uses_any_major_dam_and_preserves_unmatched() -> None:
    gages = pd.DataFrame(
        {
            "STAID": ["01234567", "07654321"],
            "MAJ_NDAMS_2009": [0, 2],
        }
    )
    assert regulation_stratum("01234567", gages) == "unregulated"
    assert regulation_stratum("01234567|07654321", gages) == "regulated"
    assert regulation_stratum("09999999", gages) == "unmatched_gages"


def test_random_slope_mixed_calibration_returns_level_slopes() -> None:
    rng = np.random.default_rng(12)
    rows = []
    for network in range(30):
        moderator = "humid" if network % 2 else "arid_semiarid"
        phase = ("development", "first", "second")[network % 3]
        network_shift = rng.normal(scale=0.12)
        slope = (0.8 if moderator == "humid" else 1.1) + rng.normal(scale=0.08)
        for index, predicted in enumerate(np.linspace(0.2, 2.0, 12)):
            rows.append(
                {
                    "risk_model": "simple_descriptors",
                    "network_uid": f"{phase}::{network}",
                    "phase": phase,
                    "climate_group": moderator,
                    "predicted_loss": predicted,
                    "observed_recovery_loss": (
                        0.1 + network_shift + slope * predicted + rng.normal(scale=0.03)
                    ),
                    "station_id": str(index),
                }
            )
    coefficients, diagnostic = fit_mixed_calibration(
        pd.DataFrame(rows),
        risk_model="simple_descriptors",
        moderator="climate_group",
    )
    assert diagnostic["converged"] is True
    assert diagnostic["n_networks"] == 30
    assert {item["level"] for item in diagnostic["level_slopes"]} == {
        "arid_semiarid",
        "humid",
    }
    assert coefficients["estimate"].notna().all()
