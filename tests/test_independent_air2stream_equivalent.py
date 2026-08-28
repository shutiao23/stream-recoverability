from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/development_v11/independent_air2stream_equivalent"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_independent_air2stream_manifest_is_fail_closed_and_bound() -> None:
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    assert manifest["model"]["published_equation"] is True
    assert manifest["model"]["original_executable_used"] is False
    assert manifest["coverage"]["candidate_networks"] == 12
    assert manifest["coverage"]["input_eligible_networks"] >= 1
    assert manifest["coverage"]["fit_failures"] == 0
    assert len(manifest["selected_networks_before_input_qc"]) == 12
    for name, expected in manifest["output_sha256"].items():
        assert _sha256(OUTPUT / name) == expected


def test_scored_stations_have_complete_strict_inputs_and_disjoint_years() -> None:
    coverage = pd.read_csv(OUTPUT / "input_coverage.csv", dtype={"station_id": str})
    losses = pd.read_csv(
        OUTPUT / "station_gap_losses.csv", dtype={"network_id": str, "station_id": str}
    )
    parameters = pd.read_csv(
        OUTPUT / "model_parameters.csv", dtype={"network_id": str, "station_id": str}
    )
    eligible = coverage.loc[coverage["input_eligible"]]
    assert eligible["strict_positive_complete_flow"].all()
    assert eligible["complete_air_temperature"].all()
    scored = losses[["network_id", "station_id"]].drop_duplicates()
    merged = scored.merge(
        eligible[["network_id", "station_id"]],
        on=["network_id", "station_id"],
        how="left",
        indicator=True,
    )
    assert merged["_merge"].eq("both").all()
    assert np.isfinite(losses["air2stream_mae_deg_c"]).all()
    for row in parameters.itertuples(index=False):
        training = set(map(int, str(row.training_years).split("|")))
        evaluation = set(map(int, str(row.evaluation_years).split("|")))
        assert training
        assert evaluation
        assert training.isdisjoint(evaluation)


def test_subset_does_not_overlap_earlier_scored_panels() -> None:
    scored = set(
        pd.read_csv(OUTPUT / "station_gap_losses.csv", usecols=["network_id"])[
            "network_id"
        ].astype(str)
    )
    development = set(
        pd.read_csv(
            ROOT / "results/development_v11/station_gap_outcomes.csv",
            usecols=["network_id"],
        )["network_id"].astype(str)
    )
    first = set(
        pd.read_csv(
            ROOT / "results/development_v11/route_a_confirmation/predictions.csv",
            usecols=["network_id"],
        )["network_id"].astype(str)
    )
    assert scored.isdisjoint(development)
    assert scored.isdisjoint(first)
