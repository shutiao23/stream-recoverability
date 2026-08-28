from __future__ import annotations

import pandas as pd

from stream_recoverability.data.rws_temperature import (
    NETWORKS,
    RIVER_NETWORKS,
    candidate_table,
    observation_request,
    parse_observations,
    temperature_locations,
)


def test_rws_candidates_are_thirteen_disjoint_three_station_networks() -> None:
    stations = [station for _, roster in NETWORKS.values() for station in roster]
    assert len(stations) == len(set(stations))
    locations = pd.DataFrame(
        {
            "Code": stations,
            "Lat": range(len(stations)),
            "Lon": range(len(stations)),
        }
    )
    candidates = candidate_table(locations)
    assert len(candidates) == 13
    assert RIVER_NETWORKS == {"rws_rijn_lek_nederrijn", "rws_maas"}
    assert candidates.loc[
        ~candidates["network_id"].isin(RIVER_NETWORKS), "candidate_status"
    ].eq("source_audit_non_river_domain").all()
    assert candidates["network_id"].is_unique
    assert candidates["n_catalog_stations"].eq(3).all()
    rosters = [set(value.split("|")) for value in candidates["site_ids"]]
    assert sum(map(len, rosters)) == len(set().union(*rosters))


def test_catalog_selects_raw_measured_surface_temperature_locations() -> None:
    document = {
        "AquoMetadataLijst": [
            {
                "AquoMetadata_MessageID": 1,
                "Compartiment": {"Code": "OW"},
                "Grootheid": {"Code": "T"},
                "WaardeBewerkingsMethode": {"Code": "NVT"},
                "ProcesType": "meting",
            },
            {
                "AquoMetadata_MessageID": 2,
                "Compartiment": {"Code": "OW"},
                "Grootheid": {"Code": "T"},
                "WaardeBewerkingsMethode": {"Code": "GEM24H"},
                "ProcesType": "meting",
            },
        ],
        "AquoMetadataLocatieLijst": [
            {"AquoMetaData_MessageID": 1, "Locatie_MessageID": 10},
            {"AquoMetaData_MessageID": 2, "Locatie_MessageID": 11},
        ],
        "LocatieLijst": [
            {"Locatie_MessageID": 10, "Code": "raw"},
            {"Locatie_MessageID": 11, "Code": "daily"},
        ],
    }
    assert temperature_locations(document)["Code"].tolist() == ["raw"]


def test_raw_observations_are_aggregated_to_approved_daily_means() -> None:
    document = {
        "WaarnemingenLijst": [
            {
                "MetingenLijst": [
                    {
                        "Meetwaarde": {"Waarde_Numeriek": value},
                        "Tijdstip": timestamp,
                        "WaarnemingMetadata": {"Kwaliteitswaardecode": quality},
                    }
                    for value, timestamp, quality in (
                        (4.0, "2020-01-01T00:00:00.000+01:00", "00"),
                        (6.0, "2020-01-01T12:00:00.000+01:00", "10"),
                        (7.0, "2020-01-02T00:00:00.000+01:00", "99"),
                    )
                ]
            }
        ]
    }
    daily = parse_observations(document, "station")
    assert daily["temperature_c"].tolist() == [5.0]
    assert daily["qualifier"].tolist() == ["A"]
    request = observation_request("station", 2020)
    metadata = request["AquoPlusWaarnemingMetadata"]["AquoMetadata"]
    assert metadata["Grootheid"]["Code"] == "T"
    assert metadata["Compartiment"]["Code"] == "OW"
    assert metadata["WaardeBewerkingsMethode"]["Code"] == "NVT"
