from __future__ import annotations

import json

import numpy as np

from stream_recoverability.masks import (
    generate_point_mask,
    load_mask_library,
    load_mask_manifest,
    save_mask_library,
)


def test_fixed_mask_library_round_trip(tmp_path) -> None:
    eligible = np.ones((20, 2, 2), dtype=bool)
    scenario = generate_point_mask(
        eligible,
        0.30,
        station_indices=[0],
        variable_indices=[0],
        seed=12,
        station_ids=["S1", "S2"],
        variable_names=["T", "F"],
        split="validation",
    )
    dates = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-01-21"))
    save_mask_library(
        [scenario],
        tmp_path,
        dates=dates,
        station_ids=["S1", "S2"],
        variable_names=["T", "F"],
    )

    loaded = load_mask_library(tmp_path)
    scenario_id = scenario[1]["scenario_id"]
    loaded_mask, loaded_metadata = loaded[scenario_id]
    assert np.array_equal(loaded_mask, scenario[0])
    assert loaded_metadata == scenario[1]

    manifest = load_mask_manifest(tmp_path)
    assert manifest["axes"]["order"] == ["date", "station", "variable"]
    assert manifest["axes"]["station"] == ["S1", "S2"]
    assert manifest["axes"]["variable"] == ["T", "F"]
    assert (tmp_path / "masks.npz").is_file()
    assert (tmp_path / "manifest.csv").is_file()
    json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

