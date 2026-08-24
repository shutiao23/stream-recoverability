from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stream_recoverability.analysis.regulation_panel import (
    _parse_legacy_rdb,
    cluster_bootstrap_auc,
    enforce_isolation,
    exact_lag_acf,
    leave_ecoregion_out_predictions,
    load_freeze,
    logistic_models,
    select_station_series,
)

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "configs/regulation_panel_freeze_v1.yaml"


def test_freeze_is_sealed_and_rejects_confirmatory_paths() -> None:
    config = load_freeze(FREEZE)
    enforce_isolation([ROOT / "data/cache/regulation_panel_v1"], config)
    with pytest.raises(ValueError, match="isolation violation"):
        enforce_isolation([ROOT / "results/confirmatory/something"], config)
    digest = __import__("hashlib").sha256(FREEZE.read_bytes()).hexdigest()
    seal = (ROOT / "metadata/regulation_panel_freeze_v1.sha256").read_text()
    assert digest in seal


def test_exact_lag_acf_uses_calendar_pairs_not_adjacent_rows() -> None:
    dates = pd.to_datetime(
        ["2000-01-01", "2000-01-31", "2000-02-01", "2000-03-01", "2000-03-31"]
    )
    values = pd.Series([1.0, 2.0, 100.0, 3.0, 4.0], index=dates)
    correlation, pairs = exact_lag_acf(values, 30)
    assert pairs == 3
    assert correlation == pytest.approx(1.0)


def test_series_selection_never_splices_and_counts_complete_years() -> None:
    config = load_freeze(FREEZE)
    config["eligibility"]["minimum_qualifying_calendar_years"] = 2
    config["eligibility"]["minimum_approved_distinct_days_per_qualifying_year"] = 3
    rows = []
    for series, dates in (
        (
            "long",
            pd.to_datetime(
                [
                    "2000-01-01",
                    "2000-01-02",
                    "2000-01-03",
                    "2001-01-01",
                    "2001-01-02",
                    "2001-01-03",
                ]
            ),
        ),
        ("short", pd.to_datetime(["2002-01-01", "2002-01-02", "2002-01-03"])),
    ):
        for index, date in enumerate(dates):
            rows.append(
                {
                    "time": date,
                    "value": 10 + index,
                    "approval_status": "Approved",
                    "monitoring_location_id": "USGS-01234567",
                    "time_series_id": series,
                }
            )
    metadata = pd.DataFrame(
        {"id": ["long", "short"], "begin": pd.to_datetime(["2000-01-01", "2002-01-01"])}
    )
    retained, choices = select_station_series(pd.DataFrame(rows), metadata, config)
    assert set(retained["time_series_id"]) == {"long"}
    assert choices.loc[0, "n_qualifying_years"] == 2
    assert retained["qualifying_year"].all()


def test_legacy_rdb_parser_retains_approved_values_with_suffix_qualifiers() -> None:
    payload = b"""# official response\nagency_cd\tsite_no\tdatetime\t7_00010_00003\t7_00010_00003_cd
5s\t15s\t20d\t14n\t10s
USGS\t01234567\t2019-01-01\t4.2\tA:[4]
USGS\t01234567\t2019-01-02\t4.3\tA:R
USGS\t01234567\t2019-01-03\t4.4\tP
"""
    parsed = _parse_legacy_rdb(payload, {"01234567": "series"})
    assert parsed["approval_status"].tolist() == [
        "Approved",
        "Approved",
        "Provisional",
    ]
    assert parsed["time_series_id"].eq("series").all()


def _synthetic_model_panel() -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(11)
    for region_index in range(6):
        for index in range(20):
            feature = rng.normal()
            probability = 1 / (1 + np.exp(-feature))
            label = int(rng.uniform() < probability)
            rows.append(
                {
                    "station_id": f"S{region_index:02d}{index:02d}",
                    "AGGECOREGION": f"R{region_index}",
                    "memory_range_index_per_degC": feature,
                    "upstream_major_dam_2009": label,
                    "DRAIN_SQKM": 10 + index,
                }
            )
    return pd.DataFrame(rows)


def test_frozen_logistic_and_leave_ecoregion_out_analysis_are_finite() -> None:
    panel = _synthetic_model_panel()
    coefficients = logistic_models(panel)
    primary = coefficients.loc[
        coefficients["model"].eq("primary_unadjusted")
        & coefficients["term"].eq("z_memory_range_index")
    ].iloc[0]
    assert primary["coefficient_log_odds"] > 0
    predictions = leave_ecoregion_out_predictions(panel)
    assert len(predictions) == len(panel)
    assert predictions["oof_probability"].between(0, 1).all()
    low, high, draws = cluster_bootstrap_auc(predictions, replicates=100, seed=5)
    assert 0 <= low <= high <= 1
    assert draws == 100
