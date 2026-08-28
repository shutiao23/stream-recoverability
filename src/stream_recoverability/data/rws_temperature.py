"""Rijkswaterstaat WaterWebservices temperature catalog and observations."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd


CATALOG_URL = (
    "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
    "METADATASERVICES/OphalenCatalogus"
)
OBSERVATIONS_URL = (
    "https://ddapi20-waterwebservices.rijkswaterstaat.nl/"
    "ONLINEWAARNEMINGENSERVICES/OphalenWaarnemingen"
)
GOOD_QUALITY_CODES = frozenset(("00", "10", "20", "25", "30", "40"))

NETWORKS = {
    "rws_rijn_lek_nederrijn": (
        "Rijn–Lek–Nederrijn",
        ("amerongen.boven", "driel.boven", "hagestein.boven"),
    ),
    "rws_maas": (
        "Maas",
        ("eijsden", "belfeld.boven", "hank.bergschemaas"),
    ),
    "rws_twentekanalen": (
        "Twentekanalen",
        ("delden.sluis.beneden", "eefde.sluis.beneden", "hengelo.oelerbrug"),
    ),
    "rws_amsterdam_rijnkanaal": (
        "Amsterdam-Rijnkanaal",
        (
            "amsterdam.schellingwouderbrug",
            "maarssen.kanaal",
            "nieuwegein.lekkanaal",
        ),
    ),
    "rws_haringvliet": (
        "Haringvliet",
        ("haringvliet.10", "haringvliet.2", "middelharnis.meetboei"),
    ),
    "rws_grevelingen": (
        "Grevelingen",
        (
            "bommenede",
            "brouwersdam.brouwershavensegat.2",
            "brouwersdam.brouwershavensegat.8",
        ),
    ),
    "rws_volkerak_krammer": (
        "Volkerak–Krammer",
        (
            "bruinisse.krammersluis.laagbekken",
            "dinteloord.volkerak.voorheenboeinv3",
            "krammerput",
        ),
    ),
    "rws_westerschelde": (
        "Westerschelde",
        ("ossenisse", "kloosterzande.baalhoek", "terneuzen.sluiskilbrug"),
    ),
    "rws_oosterschelde": (
        "Oosterschelde",
        ("oosterschelde.4", "kamperland.schotsman.ruiterplaat", "arnemuiden.oranjeplaat"),
    ),
    "rws_waddenzee": (
        "Waddenzee",
        (
            "denhelder.veersteiger",
            "eierlandsegat",
            "kornwerderzand.waddenzee.buitenhaven",
        ),
    ),
    "rws_noordzee": (
        "Noordzee",
        ("europlatform", "goeree.lichteiland", "hoekvanholland"),
    ),
    "rws_rijn_maas_delta": (
        "Rijn–Maasdelta",
        (
            "rotterdam.lekhaven",
            "rotterdam.brienenoordbrug",
            "kinderdijk.linkeroever.km988.8",
        ),
    ),
    "rws_ijsselmeer_markermeer": (
        "IJsselmeer–Markermeer",
        ("markermeer.midden", "markermeer.trintelzand", "andijk"),
    ),
}
RIVER_NETWORKS = frozenset(("rws_rijn_lek_nederrijn", "rws_maas"))


def post_json(url: str, document: Mapping[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(document).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "stream-recoverability/0.1 open-rws-qc",
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    return {} if not payload else json.loads(payload.decode("utf-8"))


def catalog_document() -> dict[str, Any]:
    return post_json(
        CATALOG_URL,
        {
            "CatalogusFilter": {
                "Compartimenten": True,
                "Grootheden": True,
                "WaardeBewerkingsMethoden": True,
                "Eenheden": True,
                "ProcesTypes": True,
            }
        },
    )


def temperature_locations(document: Mapping[str, Any]) -> pd.DataFrame:
    """Locations linked to raw measured T in surface water."""

    raw_ids = {
        item["AquoMetadata_MessageID"]
        for item in document["AquoMetadataLijst"]
        if (item.get("Compartiment") or {}).get("Code") == "OW"
        and (item.get("Grootheid") or {}).get("Code") == "T"
        and (item.get("WaardeBewerkingsMethode") or {}).get("Code") == "NVT"
        and item.get("ProcesType") == "meting"
    }
    location_ids = {
        item["Locatie_MessageID"]
        for item in document["AquoMetadataLocatieLijst"]
        if item["AquoMetaData_MessageID"] in raw_ids
    }
    return pd.DataFrame(
        [
            item
            for item in document["LocatieLijst"]
            if item["Locatie_MessageID"] in location_ids
        ]
    )


def candidate_table(locations: pd.DataFrame) -> pd.DataFrame:
    lookup = locations.set_index("Code")
    rows = []
    for network_id, (water_body, stations) in NETWORKS.items():
        selected = lookup.loc[list(stations)]
        rows.append(
            {
                "network_id": network_id,
                "provider": "rws_waterwebservices",
                "domain": "netherlands",
                "river_group": water_body,
                "n_catalog_stations": len(stations),
                "site_ids": "|".join(stations),
                "latitude": float(selected["Lat"].mean()),
                "longitude": float(selected["Lon"].mean()),
                "prior_temperature_values_seen": False,
                "candidate_status": (
                    "metadata_candidate_pending_daily_qc"
                    if network_id in RIVER_NETWORKS
                    else "source_audit_non_river_domain"
                ),
            }
        )
    return pd.DataFrame(rows)


def observation_request(station: str, year: int) -> dict[str, Any]:
    return {
        "Locatie": {"Code": str(station)},
        "AquoPlusWaarnemingMetadata": {
            "AquoMetadata": {
                "Compartiment": {"Code": "OW"},
                "Grootheid": {"Code": "T"},
                "WaardeBewerkingsMethode": {"Code": "NVT"},
                "ProcesType": "meting",
            }
        },
        "Periode": {
            "Begindatumtijd": f"{year}-01-01T00:00:00.000+01:00",
            "Einddatumtijd": f"{year + 1}-01-01T00:00:00.000+01:00",
        },
    }


def parse_observations(document: Mapping[str, Any], station: str) -> pd.DataFrame:
    rows = []
    for series in document.get("WaarnemingenLijst") or []:
        for item in series.get("MetingenLijst") or []:
            metadata = item.get("WaarnemingMetadata") or {}
            quality = str(metadata.get("Kwaliteitswaardecode") or "")
            if quality in GOOD_QUALITY_CODES:
                rows.append(
                    {
                        "site_id": str(station),
                        "date": item["Tijdstip"],
                        "temperature_c": item["Meetwaarde"]["Waarde_Numeriek"],
                        "qualifier": "A",
                    }
                )
    frame = pd.DataFrame(
        rows, columns=["site_id", "date", "temperature_c", "qualifier"]
    )
    if len(frame):
        frame["date"] = pd.to_datetime(frame["date"].astype(str).str[:10])
        frame["temperature_c"] = pd.to_numeric(frame["temperature_c"])
        frame = (
            frame.groupby(["site_id", "date"], as_index=False)
            .agg(
                temperature_c=("temperature_c", "mean"),
                qualifier=("qualifier", "first"),
            )
            .sort_values("date")
        )
    return frame


def download_station(station: str, years: Sequence[int]) -> pd.DataFrame:
    frames = [
        parse_observations(
            post_json(OBSERVATIONS_URL, observation_request(station, int(year))),
            station,
        )
        for year in years
    ]
    return pd.concat([frame for frame in frames if len(frame)], ignore_index=True)


__all__ = [
    "NETWORKS",
    "RIVER_NETWORKS",
    "candidate_table",
    "catalog_document",
    "download_station",
    "observation_request",
    "parse_observations",
    "temperature_locations",
]
