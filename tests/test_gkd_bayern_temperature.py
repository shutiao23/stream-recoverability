from __future__ import annotations

import io
import zipfile

import pandas as pd

from stream_recoverability.data.gkd_bayern_temperature import (
    Station,
    candidate_networks,
    merge_provider_rows,
    parse_archive,
    parse_catalog,
    parse_coordinates,
)


def test_catalog_parser_reads_station_and_river() -> None:
    document = """
    <table><tr><td><a href="https://www.gkd.bayern.de/de/fluesse/wassertemperatur/isar/eins-10000001/messwerte?method=tabellen">Eins</a></td><td>Main</td></tr></table>
    """
    stations = parse_catalog(document)
    assert stations == (
        Station(
            "10000001",
            "Eins",
            "Main",
            "https://www.gkd.bayern.de/de/fluesse/wassertemperatur/isar/eins-10000001",
            "https://www.gkd.bayern.de/de/fluesse/wassertemperatur/isar/eins-10000001/download",
        ),
    )


def test_candidate_builder_retains_three_station_river() -> None:
    stations = tuple(
        Station(str(index), f"S{index}", "Fränkische Saale", f"m{index}", f"d{index}")
        for index in range(3)
    ) + (
        Station("9", "Other", "Else", "m9", "d9"),
    )
    candidates = candidate_networks(stations)
    assert candidates["network_id"].tolist() == ["gkd_bayern_fraenkische_saale"]
    assert candidates["n_catalog_stations"].tolist() == [3]


def test_archive_parser_keeps_checked_daily_means() -> None:
    csv_body = """Quelle;GKD
Datum;Mittelwert;Maximum;Minimum;Prüfstatus
2020-01-01;4,2;4,5;4,0;Geprueft
2020-01-02;4,3;4,6;4,1;Ungeprueft
""".encode()
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as archive:
        archive.writestr("fluesse-wassertemperatur/100.csv", csv_body)
    frame = parse_archive(memory.getvalue(), "100")
    assert frame["temperature_c"].tolist() == [4.2, 4.3]
    assert frame["qualifier"].tolist() == ["A", "P"]
    assert frame["provider_quality_status"].tolist() == ["Geprueft", "Ungeprueft"]


def test_coordinate_parser_and_shared_table_replacement(tmp_path) -> None:
    latitude, longitude = parse_coordinates(
        '"pinMarker":{"center_lon":"11.5","center_lat":"48.2"}'
    )
    assert (latitude, longitude) == (48.2, 11.5)
    path = tmp_path / "summary.csv"
    pd.DataFrame(
        [
            {"network_id": "old", "provider": "gkd_bayern", "domain": "germany"},
            {"network_id": "keep", "provider": "usgs", "domain": "united_states"},
        ]
    ).to_csv(path, index=False)
    additions = pd.DataFrame(
        [{"network_id": "new", "provider": "gkd_bayern", "domain": "germany"}]
    )
    merged = merge_provider_rows(path, additions)
    assert set(merged["network_id"]) == {"keep", "new"}
