"""W2 Phase-4 y-specification tests. Production code is imported read-only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

W2 = Path(__file__).resolve().parent
REPO = W2.parents[2]
SRC = REPO / "src"
if str(W2) not in sys.path:
    sys.path.insert(0, str(W2))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gap_specific_scorer import (  # noqa: E402
    REQUIRED_SIX,
    SUWANNEE_ID,
    W2_INFERENCE_STATUS,
    W2_PURPOSE,
    concurrent_enough_roster,
    gap_length_delta_r2,
    later_year_station_rows,
    planted_station_rows,
    shock_toy_wide,
    skill_copied_across_gap_lengths,
    usable_donor_indices,
    w2_manifest,
)
from stream_recoverability.experiments.public_river_operator_ablation import (  # noqa: E402
    nested_ablation_table,
    run_public_river_operator_ablation,
    station_operator_rows,
)
from stream_recoverability.experiments.real_river_checks import year_split  # noqa: E402

OVERLAP = REPO / "results/framework/public_rivers/overlap.csv"
PRODUCTION_MANIFEST = REPO / "results/framework/public_rivers/operator_ablation_manifest.json"
CONTRACT = W2 / "manifest_contract.json"


def _assert_no_tested_status(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if item == "tested" or (
                key in {"inference_status", "network_ci_status"} and str(item) == "tested"
            ):
                raise AssertionError(f"tested network CI leaked at {key}={item!r}")
            _assert_no_tested_status(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_tested_status(item)


def test_production_later_year_y_identical_across_l() -> None:
    wide = shock_toy_wide(seed=2)
    rows = station_operator_rows("toy", wide, gap_lengths=(30, 90))
    frame = pd.DataFrame(rows)
    scored = frame.loc[np.isfinite(pd.to_numeric(frame["achieved_skill"], errors="coerce"))]
    assert not scored.empty
    assert scored["gap_length"].nunique() == 2
    for _, group in scored.groupby("station_id"):
        skills = pd.to_numeric(group["achieved_skill"], errors="coerce")
        assert skills.nunique(dropna=True) == 1
        assert float(skills.iloc[0]) == float(skills.iloc[-1])
    assert skill_copied_across_gap_lengths(scored) is True


def test_planted_y_differs_across_l_on_toy() -> None:
    wide = shock_toy_wide(seed=3)
    frame = pd.DataFrame(planted_station_rows("toy", wide, gap_lengths=(30, 90)))
    scored = frame.loc[np.isfinite(pd.to_numeric(frame["achieved_skill"], errors="coerce"))]
    target = scored.loc[scored["station_id"].eq("s0")]
    assert set(target["gap_length"].astype(int)) == {30, 90}
    skill_30 = float(target.loc[target["gap_length"].eq(30), "achieved_skill"].iloc[0])
    skill_90 = float(target.loc[target["gap_length"].eq(90), "achieved_skill"].iloc[0])
    assert skill_30 != skill_90
    assert skill_copied_across_gap_lengths(scored) is False


def test_pooling_gaps_required_for_gap_length_delta_r2() -> None:
    rows = []
    for station in range(8):
        for gap, skill in ((30, 0.85 - 0.01 * station), (90, 0.25 - 0.01 * station)):
            rows.append(
                {
                    "network_id": f"net{station // 2}",
                    "station_id": f"s{station}",
                    "gap_length": gap,
                    "acf30": 0.4 + 0.01 * station,
                    "donor_r2": 0.5 + 0.01 * station,
                    "heuristic_explained_variance": 0.55 + 0.01 * station,
                    "recoverability_r": 0.6 + 0.01 * station,
                    "achieved_skill": skill,
                }
            )
    frame = pd.DataFrame(rows)
    pooled = gap_length_delta_r2(frame, pooled=True)
    per_gap = gap_length_delta_r2(frame, pooled=False)
    assert np.isfinite(pooled) and pooled > 0.05
    assert np.isfinite(per_gap) and per_gap == 0.0
    for gap in (30, 90):
        nested = nested_ablation_table(
            frame.loc[frame["gap_length"].eq(gap)],
            level="station",
            scope=f"gap_{gap}",
        )
        delta = float(nested.loc[nested["added"].eq("gap_length"), "delta_r2"].iloc[0])
        assert delta == 0.0
    production = run_public_river_operator_ablation(
        {"toy_a": shock_toy_wide(seed=4), "toy_b": shock_toy_wide(seed=5, shock=0.0)},
        gap_lengths=(30, 90),
    )
    nested = production["nested"]
    gap_steps = nested.loc[nested["added"].eq("gap_length"), "delta_r2"]
    assert (pd.to_numeric(gap_steps, errors="coerce").fillna(0.0) == 0.0).all()
    assert "separate per gap" in str(production["manifest"].get("nested_grids", ""))


def test_six_concurrent_enough_ids_suwannee_is_not_delaware() -> None:
    overlap = pd.read_csv(OVERLAP)
    roster = concurrent_enough_roster(overlap)
    assert roster == REQUIRED_SIX
    assert "delaware_river_huc20" in roster
    assert SUWANNEE_ID not in roster
    suwannee = overlap.loc[overlap["network_id"].astype(str).eq(SUWANNEE_ID)].iloc[0]
    delaware = overlap.loc[overlap["network_id"].astype(str).eq("delaware_river_huc20")].iloc[0]
    assert bool(delaware["complete_enough"]) is True
    assert int(delaware["days_with_min_stations"]) == 8857
    assert bool(suwannee["complete_enough"]) is False
    production = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    assert production["delaware_scored"] is False
    assert "delaware_river_huc20" in production["requested_primary_missing"]
    assert SUWANNEE_ID in production["scored_networks"]
    assert "delaware_river_huc20" not in production["scored_networks"]
    assert production["n_networks"] == 5


def test_manifest_contract_w2_keys() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["n_networks"] == 6
    assert contract["passed"] is False
    assert contract["purpose"] == W2_PURPOSE
    assert contract["achieved_skill_is_later_year_not_gap_specific"] is False
    assert contract["formal_evidence"] is False
    assert contract["headline_claim_licensed"] is False
    assert set(contract["primary_networks"]) == set(REQUIRED_SIX)
    assert SUWANNEE_ID not in contract["primary_networks"]
    assert "delaware_river_huc20" in contract["primary_networks"]
    _assert_no_tested_status(contract)
    assert contract["network_interval"]["inference_status"] == W2_INFERENCE_STATUS
    assert contract["network_interval"]["ci_lower"] is None
    assert contract["evaluate_success"]["passed"] is False
    built = w2_manifest(pd.DataFrame(), roster=REQUIRED_SIX)
    assert built["n_networks"] == 6
    assert built["passed"] is False
    assert built["purpose"] == W2_PURPOSE
    assert built["achieved_skill_is_later_year_not_gap_specific"] is False
    _assert_no_tested_status(built)


def test_delaware_all_donor_constraint_is_the_later_year_failure() -> None:
    path = REPO / "results/framework/public_rivers/delaware_river_huc20_daily_wide.csv"
    wide = pd.read_csv(path, index_col=0, parse_dates=True).apply(
        pd.to_numeric, errors="coerce"
    )
    assert int((wide.notna().sum(axis=1) == wide.shape[1]).sum()) == 0
    values = wide.to_numpy(dtype=float)
    train, _test = year_split(wide.index)
    target = values[:, 2]
    donors = np.delete(values, 2, axis=1)
    assert usable_donor_indices(target, donors, train)
    production = pd.DataFrame(
        later_year_station_rows("delaware_river_huc20", wide, gap_lengths=(30, 90))
    )
    assert production["reason"].iloc[0] == "could_not_score_any_station"


def test_demo_first_rows_match_only_under_later_year() -> None:
    payload = json.loads((W2 / "demo" / "later_year_vs_gap_specific.json").read_text(encoding="utf-8"))
    assert payload["later_year_first_rows_match"] is True
    assert payload["planted_first_rows_differ"] is True
    later = payload["later_year_first_rows"]
    planted = payload["planted_gap_first_rows"]
    assert later[0]["gap_length"] != later[1]["gap_length"]
    assert later[0]["achieved_skill"] == later[1]["achieved_skill"]
    assert planted[0]["achieved_skill"] != planted[1]["achieved_skill"]


def test_scratch_six_river_outputs_keep_delaware() -> None:
    path = W2 / "outputs" / "w2_pipeline_manifest.json"
    if not path.is_file():
        pytest.skip("six-river scratch outputs not generated")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["n_networks"] == 6
    assert manifest["passed"] is False
    assert manifest["purpose"] == W2_PURPOSE
    assert manifest["achieved_skill_is_later_year_not_gap_specific"] is False
    assert manifest["delaware_scored"] is True
    assert set(manifest["scored_networks"]) == set(REQUIRED_SIX)
    assert SUWANNEE_ID not in manifest["scored_networks"]
    assert manifest["network_interval"]["inference_status"] != "tested"
    _assert_no_tested_status(manifest)
    nested = pd.read_csv(W2 / "outputs" / "w2_pooled_nested_ablation.csv")
    gap_delta = float(nested.loc[nested["added"].eq("gap_length"), "delta_r2"].iloc[0])
    assert gap_delta != 0.0


def test_flag_only_does_not_fix_copied_y() -> None:
    wide = shock_toy_wide(seed=6)
    later = pd.DataFrame(later_year_station_rows("toy", wide, gap_lengths=(30, 90)))
    later = later.loc[np.isfinite(pd.to_numeric(later["achieved_skill"], errors="coerce"))]
    lying = {
        "achieved_skill_is_later_year_not_gap_specific": False,
        "n_networks": 6,
        "passed": False,
        "purpose": W2_PURPOSE,
    }
    assert lying["achieved_skill_is_later_year_not_gap_specific"] is False
    assert skill_copied_across_gap_lengths(later) is True
    assert gap_length_delta_r2(later, pooled=True) == pytest.approx(0.0, abs=1e-12)
