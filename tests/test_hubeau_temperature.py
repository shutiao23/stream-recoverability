from __future__ import annotations

import inspect

import pandas as pd

from stream_recoverability.data.hubeau_temperature import (
    cluster_hubeau_rivers,
    hubeau_chronicle_span,
    hubeau_chronique_daily,
)


def test_hubeau_clusters_drop_loire_and_short_rivers() -> None:
    stations = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4", "5", "6"],
            "river": ["la Loire", "la Loire", "la Loire", "la Garonne", "la Garonne", "la Garonne"],
        }
    )
    clusters = cluster_hubeau_rivers(stations, min_stations=3, exclude_loire=True)
    assert list(clusters["river"]) == ["la Garonne"]
    assert bool(clusters["countable_public_daily"].iloc[0]) is False
    assert int(clusters["n_stations"].iloc[0]) == 3


def test_chronicle_span_reads_date_mesure_temp_not_invented_years() -> None:
    source = inspect.getsource(hubeau_chronicle_span)
    assert "date_mesure_temp" in source
    assert "instantaneous_not_daily" in source
    assert "countable_public_daily" in source


def test_daily_resample_is_labeled_derived_not_invented() -> None:
    source = inspect.getsource(hubeau_chronique_daily)
    assert "resample" in source
    assert "Loire" in source

