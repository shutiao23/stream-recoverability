from __future__ import annotations

from stream_recoverability.analysis.public_confirmatory_lock import (
    is_forbidden_sealed,
    propose_sealed_networks,
    write_lock_or_refuse,
)


def test_burned_and_last_check_cannot_be_sealed() -> None:
    assert is_forbidden_sealed("willamette_river_huc17")
    assert is_forbidden_sealed("willamette_mainstem")
    assert is_forbidden_sealed("jinsha_upper")
    assert is_forbidden_sealed("hubeau_la_loire")
    assert is_forbidden_sealed("colorado_mainstem")


def test_lock_is_refused_below_floors(tmp_path) -> None:
    candidates = [
        {"network_id": f"river_{i:03d}", "continent": "north_america", "complete_enough": True}
        for i in range(48)
    ]
    proposal = propose_sealed_networks(candidates)
    assert proposal["enough_to_lock"] is False
    assert proposal["non_north_america_n"] == 0
    assert proposal["sealed_outcomes_opened"] is False
    assert proposal["sealed_network_ids"] == []
    written = write_lock_or_refuse(proposal, path=tmp_path / "lock.json")
    assert written["lock_created"] is False
    assert not (tmp_path / "lock.json").is_file()


def test_unknown_continent_and_nan_complete_are_not_eligible() -> None:
    candidates = [
        {"network_id": f"na_river_{i:03d}", "continent": "north_america", "complete_enough": True}
        for i in range(40)
    ] + [
        {"network_id": "mystery_river", "continent": "unknown", "complete_enough": True},
        {"network_id": "nan_river", "continent": "europe", "complete_enough": float("nan")},
        {"network_id": "false_river", "continent": "europe", "complete_enough": "False"},
    ]
    proposal = propose_sealed_networks(candidates)
    assert proposal["enough_to_lock"] is False
    assert proposal["non_north_america_n"] == 0


def test_lock_records_ids_without_opening_temps(tmp_path) -> None:
    candidates = [
        {
            "network_id": f"na_river_{i:03d}",
            "continent": "north_america",
            "complete_enough": True,
        }
        for i in range(35)
    ] + [
        {
            "network_id": f"eu_river_{i:03d}",
            "continent": "europe",
            "complete_enough": True,
        }
        for i in range(12)
    ]
    proposal = propose_sealed_networks(candidates)
    assert proposal["enough_to_lock"] is True
    sealed = proposal["sealed_network_ids"]
    assert len(sealed) >= 40
    assert sum(item.startswith("eu_river_") for item in sealed) >= 10
    written = write_lock_or_refuse(proposal, path=tmp_path / "lock.json")
    assert written["lock_created"] is True
    assert written["temperatures_opened"] is False
    assert "willamette_river_huc17" not in written["sealed_network_ids"]
    assert "willamette_mainstem" not in written["sealed_network_ids"]
