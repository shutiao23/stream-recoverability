from __future__ import annotations

import urllib.parse

from stream_recoverability.data.arso_temperature import (
    NETWORKS,
    archive_url,
    candidate_table,
    parse_daily_temperature,
)


def test_arso_candidates_are_exact_rivers_with_disjoint_station_ids() -> None:
    candidates = candidate_table()
    assert len(candidates) == 12
    assert candidates["network_id"].is_unique
    assert candidates["n_catalog_stations"].ge(3).all()
    rosters = [set(value.split("|")) for value in candidates["site_ids"]]
    assert sum(map(len, rosters)) == len(set().union(*rosters))
    assert set(candidates["river_group"]) == {
        river for river, _ in NETWORKS.values()
    }


def test_arso_daily_temperature_parser_uses_reviewed_daily_column() -> None:
    source = """
    <table id="lepa_tabela">
      <thead><tr><th>Datum</th><th>vodostaj (cm)</th><th>temp. vode (°C)</th></tr></thead>
      <tbody>
        <tr><td>01.01.2020</td><td>123</td><td>4,5</td></tr>
        <tr><td>02.01.2020</td><td>120</td><td></td></tr>
        <tr><td>03.01.2020</td><td>118</td><td>5.7</td></tr>
      </tbody>
    </table>
    """
    frame = parse_daily_temperature(source, "8031")
    assert frame["temperature_c"].tolist() == [4.5, 5.7]
    assert frame["qualifier"].eq("A").all()
    assert frame["date"].dt.day.tolist() == [1, 3]

    parsed = urllib.parse.urlparse(archive_url("Soča", "8031", 2020))
    query = urllib.parse.parse_qs(parsed.query)
    assert query["p_vodotok"] == ["Soča"]
    assert query["p_postaja"] == ["8031"]
    assert query["p_leto"] == ["2020"]
