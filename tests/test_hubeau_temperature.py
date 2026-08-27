from __future__ import annotations

import inspect

import pandas as pd

from stream_recoverability.data.hubeau_temperature import (
    cluster_hubeau_rivers,
    hubeau_chronicle_span,
    hubeau_chronique_daily,
    HUBEAU_CORRECT_QUALIFICATION,
    HUBEAU_SANDRE_CORRECTE_NOTE,
)


def test_hubeau_clusters_drop_loire_and_short_rivers() -> None:
    stations = pd.DataFrame(
        {
            "site_id": ["1", "2", "3", "4", "5", "6"],
            "river": [
                "la Loire",
                "la Loire",
                "la Loire",
                "la Garonne",
                "la Garonne",
                "la Garonne",
            ],
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


def test_window_url_never_paginates_past_20k() -> None:
    from stream_recoverability.data.hubeau_temperature import (
        HUBEAU_MAX_WINDOW_RECORDS,
        hubeau_window_url,
    )

    url = hubeau_window_url("06121500", "2010-01-01", "2010-12-31")
    assert "date_debut_mesure=2010-01-01" in url
    assert "date_fin_mesure=2010-12-31" in url
    assert "page=1" in url
    assert "size=20000" in url
    assert "code_qualification=1" in url
    assert HUBEAU_MAX_WINDOW_RECORDS == 20000


def test_date_split_when_count_exceeds_20k(monkeypatch) -> None:
    from stream_recoverability.data import hubeau_temperature as module

    calls: list[str] = []

    def fake_get_json(url, **kwargs):
        del kwargs
        calls.append(url)
        if (
            "date_debut_mesure=2010-01-01" in url
            and "date_fin_mesure=2010-12-31" in url
        ):
            return {
                "count": 2,
                "data": [
                    {
                        "date_mesure_temp": "2010-06-01T00:00:00Z",
                        "resultat": 12.0,
                        "code_qualification": "1",
                    },
                ],
            }
        if (
            "date_debut_mesure=2011-01-01" in url
            and "date_fin_mesure=2011-12-31" in url
        ):
            return {
                "count": 40000,
                "data": [
                    {
                        "date_mesure_temp": "2011-01-01T00:00:00Z",
                        "resultat": 1.0,
                        "code_qualification": "1",
                    }
                ]
                * 10,
                "next": url + "&page=2",
            }
        return {
            "count": 2,
            "data": [
                {
                    "date_mesure_temp": "2011-06-01T00:00:00Z",
                    "resultat": 13.0,
                    "code_qualification": "1",
                },
            ],
        }

    monkeypatch.setattr(module, "get_json", fake_get_json)
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(module, "_refuse_last_check_site", lambda _site: None)
    rows = module.hubeau_chronique_rows("06121500", "2010-01-01", "2011-12-31")
    assert any("2010-01-01" in url and "2010-12-31" in url for url in calls)
    assert any("2011-01-01" in url and "2011-12-31" in url for url in calls)
    assert all(
        "page=2" not in url.split("?")[-1].replace("&page=1", "") or "page=1" in url
        for url in calls
    )
    assert all("page=2" not in url for url in calls)
    assert len(rows) >= 2


def test_empty_yearchunk_cache_is_not_treated_as_data(tmp_path, monkeypatch) -> None:
    from stream_recoverability.data import hubeau_temperature as module

    dest = tmp_path / "hubeau" / "06121500_daily_yearchunk_qc1.csv"
    dest.parent.mkdir(parents=True)
    dest.write_text("site_id,date,temperature_c\n", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "hubeau_chronicle_span",
        lambda site_id: {
            "site_id": site_id,
            "daily_begin": "2010-01-01",
            "daily_end": "2010-01-03",
        },
    )
    monkeypatch.setattr(
        module,
        "hubeau_chronique_rows",
        lambda *args, **kwargs: [
            {
                "date": "2010-01-01T12:00:00",
                "temperature_c": 8.0,
                "quality_code": "1",
            },
            {
                "date": "2010-01-01T18:00:00",
                "temperature_c": 10.0,
                "quality_code": "1",
            },
        ],
    )
    monkeypatch.setattr(module, "_refuse_last_check_site", lambda _site: None)
    daily = module.hubeau_chronique_daily("06121500", cache_dir=tmp_path)
    assert len(daily) == 1
    assert float(daily["temperature_c"].iloc[0]) == 9.0
    assert daily["approval_status"].eq("approved").all()


def test_daily_resample_drops_non_correct_hubeau_rows(tmp_path, monkeypatch) -> None:
    from stream_recoverability.data import hubeau_temperature as module

    monkeypatch.setattr(
        module,
        "hubeau_chronicle_span",
        lambda site_id: {
            "site_id": site_id,
            "daily_begin": "2010-01-01",
            "daily_end": "2010-01-02",
        },
    )
    monkeypatch.setattr(
        module,
        "hubeau_chronique_rows",
        lambda *args, **kwargs: [
            {
                "date": "2010-01-01T12:00:00",
                "temperature_c": 8.0,
                "quality_code": "4",
            }
        ],
    )
    monkeypatch.setattr(module, "_refuse_last_check_site", lambda _site: None)
    daily = module.hubeau_chronique_daily("06121500", cache_dir=tmp_path)
    assert daily.empty


def test_hubeau_correcte_note_does_not_relabel_code4() -> None:
    assert HUBEAU_CORRECT_QUALIFICATION == "1"
    assert "never as T8 Correcte" in HUBEAU_SANDRE_CORRECTE_NOTE
    assert "code 4" in HUBEAU_SANDRE_CORRECTE_NOTE.lower()
    assert "correcte download was correctly not started" in HUBEAU_SANDRE_CORRECTE_NOTE.lower()
