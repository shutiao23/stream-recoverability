from __future__ import annotations

import io
import json
import zipfile

from stream_recoverability.data.ehyd_temperature import (
    exact_river_candidates,
    monthly_network,
    parse_monthly_temperature,
    surface_temperature_stations,
)


def _inputs() -> tuple[dict, bytes]:
    features = []
    station_lines = [
        "dbmsnr;hzbnr01;mstnam02;gew03;mpua04;egarea05;daterr06;datauf07;xrkko08;yhkko09;aufge_f;sym_ehyd"
    ]
    for index, station in enumerate(("100", "101", "102", "200")):
        river = "River A" if station != "200" else "River B"
        file_row = {
            "hzbnr": station,
            "file": f"WT-Monatsmittel-{station}.csv",
            "filefrom": 2000 + index % 2,
            "fileto": 2020,
            "filenr": 8,
            "ftyp": "owf_wassertemp_monatsmittel",
        }
        features.append(
            {
                "properties": {
                    "hzbnr01": station,
                    "fjson": json.dumps([file_row]),
                }
            }
        )
        station_lines.append(
            f"{index};{station};Station {station};{river};500;12,5;1980;;1;2;N;1"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("messstellen_owf.csv", "\n".join(station_lines))
        for station in ("100", "101", "102", "200"):
            archive.writestr(
                f"WT-Monatsmittel/WT-Monatsmittel-{station}.csv",
                "Messstelle:;Example\n21.01.2001 00:00:00;  4,5\n"
                "21.02.2001 00:00:00; Lücke\n21.03.2001 00:00:00;  6,5\n",
            )
    return {"features": features}, buffer.getvalue()


def test_official_monthly_catalog_builds_exact_river_candidate() -> None:
    document, package = _inputs()
    stations = surface_temperature_stations(document, package)
    candidates = exact_river_candidates(stations)
    assert len(stations) == 4
    assert candidates["network_id"].tolist() == ["ehyd_river_a"]
    assert candidates.iloc[0]["site_ids"] == "100|101|102"
    assert candidates.iloc[0]["temporal_resolution"] == "monthly_mean"
    assert candidates.iloc[0]["candidate_status"] == (
        "source_qc_failed_monthly_only"
    )


def test_monthly_values_are_parsed_but_never_relabeled_daily() -> None:
    payload = (
        b"Messstelle:;Example\n21.01.2001 00:00:00;  4,5\n"
        b"21.02.2001 00:00:00; L\xfccke\n21.03.2001 00:00:00;  6,5\n"
    )
    parsed = parse_monthly_temperature(payload, "100")
    assert parsed["temperature_c"].tolist() == [4.5, 6.5]
    assert parsed["date"].dt.day.tolist() == [21, 21]

    document, package = _inputs()
    stations = surface_temperature_stations(document, package)
    network = monthly_network(package, stations, ("100", "101", "102"))
    assert network["site_id"].nunique() == 3
    assert len(network) == 6
