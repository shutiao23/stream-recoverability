from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stream_recoverability.experiments.twin_e as twin_e_module
from stream_recoverability.experiments.synthetic_river import (
    TWIN_DAM_MEMORY,
    TWIN_FACTOR_NOISE,
    TWIN_LOCAL_NOISE,
    TWIN_ORDINARY_MEMORY,
)
from stream_recoverability.experiments.twin_e import (
    HOLDOUT_FAMILIES,
    OBSERVATION_NOISE,
    TWIN_E_FAMILIES,
    UNIVARIATE_PREDICTORS,
    TemporalTwinEFamily,
    generate_twin_e_scores,
    load_locked_holdout_families,
    run_locked_twin_e_holdout,
    run_twin_e,
    simulate_temporal_twin_e,
    validate_temporal_twin_e_pair,
    write_locked_twin_e_holdout_artifacts,
    write_twin_e_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_FREEZE = ROOT / "configs/twin_e_holdout_freeze_v1.yaml"


def test_inspected_families_are_debug_only_and_reuse_existing_constants() -> None:
    assert HOLDOUT_FAMILIES == ()
    assert {family.split for family in TWIN_E_FAMILIES} == {"design_debug"}
    assert {family.marginal_phi for family in TWIN_E_FAMILIES} == {
        TWIN_DAM_MEMORY,
        TWIN_ORDINARY_MEMORY,
    }
    assert OBSERVATION_NOISE == TWIN_LOCAL_NOISE + TWIN_FACTOR_NOISE


def test_twin_e_pairs_match_margins_but_change_conditional_covariance() -> None:
    scores = generate_twin_e_scores()
    assert set(scores["cell"]) == {"E"}
    for _, pair in scores.groupby(["family", "gap_length"], sort=False):
        assert len(pair) == 2
        assert pair["marginal_acf30"].nunique() == 1
        assert pair["donor_r2"].nunique() == 1
        assert pair["marginal_phi"].nunique() == 1
        assert pair["n_donors"].nunique() == 1
        conditional = pair[
            ["sigma_cond_00", "sigma_cond_01", "sigma_cond_10", "sigma_cond_11"]
        ].to_numpy(dtype=float)
        assert not np.allclose(conditional[0], conditional[1])
        assert pair["true_recoverability"].nunique() == 2


def test_truth_and_operator_use_independent_computational_paths(monkeypatch) -> None:
    family = TWIN_E_FAMILIES[0]
    loading = twin_e_module._observation_loading(
        family, 30, donor_relation="complementary"
    )
    _, truth_before = twin_e_module._true_recoverability_from_generator(loading)
    sigma_gg, sigma_go, sigma_oo = twin_e_module._joint_covariance(
        family, 30, donor_relation="complementary"
    )
    monkeypatch.setattr(
        twin_e_module,
        "schur_complement",
        lambda *_args, **_kwargs: 0.5 * np.eye(2),
    )
    _, operator_after = twin_e_module._operator_recoverability_from_known_sigma(
        sigma_gg, sigma_go, sigma_oo
    )
    _, truth_after = twin_e_module._true_recoverability_from_generator(loading)
    assert truth_after == truth_before
    assert not np.isclose(operator_after, truth_after)


def test_inspected_twin_e_rows_cannot_pass_the_formal_gate() -> None:
    result = run_twin_e()
    gate = result["gate"]
    assert gate["cell"] == "E"
    assert gate["evaluated_split"] == "design_debug"
    assert gate["holdout_families"] == []
    assert gate["holdout_family_locked_before_scoring"] is False
    assert gate["passed"] is False
    assert gate["status"] == "not_tested_holdout_not_prelocked"
    assert gate["forbidden_metric"] == "classification_auc"
    assert set(result["univariates"]["predictor"]) == set(UNIVARIATE_PREDICTORS)


def test_twin_e_negative_result_writer_reads_failed_holdout_manifest(tmp_path) -> None:
    holdout = tmp_path / "twin_e_holdout_manifest.json"
    holdout.write_text(
        """
{
  "experiment": "E5_twin_e_locked_holdout",
  "protocol_amendment": "v9.1",
  "cell": "E",
  "estimand": "analytic_truth_vs_finite_training_hat_sigma_operator",
  "lock_path": "configs/twin_e_holdout_freeze_v1.yaml",
  "lock_commit": "abc123",
  "gate": {
    "passed": false,
    "status": "twin_e_operator_calibration_miss",
    "generator_retuned_to_save_gate": false,
    "operator_spearman": 0.936,
    "operator_calibration_slope": 0.76
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    record = twin_e_module.write_twin_e_holdout_negative_result(
        holdout_manifest_path=holdout,
    )
    assert record["publishable_negative_result"] is True
    assert record["passed"] is False
    assert record["generator_retuning_allowed"] is False
    assert (tmp_path / "twin_e_holdout_negative_result.json").is_file()


    truth = np.linspace(0.1, 0.9, 24)
    rng = np.random.default_rng(1701)
    frame = pd.DataFrame(
        {
            "family": [f"f{index:02d}" for index in range(len(truth))],
            "true_recoverability": truth,
            "operator_recoverability": truth / 0.75,
            "gap_length_only": rng.permutation(len(truth)),
            "acf_only": rng.permutation(len(truth)),
            "donor_r2_only": rng.permutation(len(truth)),
            "additive_d4": rng.permutation(len(truth)),
        }
    )

    _, gate = twin_e_module._score_correlations(frame, formal_holdout=True)

    assert gate["operator_meets_floor"] is True
    assert gate["univariate_meets_ceiling"] is True
    assert gate["operator_calibration_meets_band"] is False
    assert gate["passed"] is False
    assert gate["status"] == "twin_e_operator_calibration_miss"


def test_holdout_freeze_expands_full_factorial_without_scoring() -> None:
    families, commit = load_locked_holdout_families(
        HOLDOUT_FREEZE, require_committed=False
    )
    assert commit is None
    assert len(families) == 9
    assert len({family.family for family in families}) == 9
    assert {family.propagation_lag for family in families} == {2, 5, 10}
    assert {family.seed for family in families} == {104729, 130363, 155921}
    assert {family.n_train for family in families} == {2920}
    assert {family.phi for family in families} == {TWIN_ORDINARY_MEMORY}


def test_temporal_generator_has_explicit_edges_lags_transition_and_noise() -> None:
    family = TemporalTwinEFamily(
        family="temporal_debug",
        propagation_lag=5,
        seed=17,
        n_train=500,
        burn_in=200,
        n_nodes=5,
        phi=TWIN_ORDINARY_MEMORY,
        factor_process_noise=TWIN_FACTOR_NOISE,
        local_process_noise=TWIN_LOCAL_NOISE,
        advect=0.22,
        dispersion=0.18,
    )
    redundant, graph_r = simulate_temporal_twin_e(family, "redundant")
    complementary, graph_c = simulate_temporal_twin_e(family, "complementary")
    assert redundant.shape == complementary.shape == (500, 5)
    assert graph_r["edges"] == ((3, 1), (1, 0), (0, 2), (2, 4))
    assert graph_c["edges"] == ((0, 1), (1, 2), (2, 3), (3, 4))
    assert graph_r["offsets"][1:3] == (-5, -5)
    assert graph_c["offsets"][1:3] == (-5, -10)
    assert graph_r["transition"][0, 0] == TWIN_ORDINARY_MEMORY
    assert graph_r["process_noise"][0, 0] == TWIN_FACTOR_NOISE
    assert not np.array_equal(redundant[:, 1], complementary[:, 1])


def test_all_unscored_temporal_families_match_margins_before_scoring() -> None:
    families, _ = load_locked_holdout_families(
        HOLDOUT_FREEZE, require_committed=False
    )
    for family in families:
        match = validate_temporal_twin_e_pair(family)
        assert match["target_series_exact"] is True
        assert match["acf30_redundant"] == match["acf30_complementary"]
        assert match["population_donor_r2_delta"] <= 1e-12
        assert match["sample_donor_r2_delta"] <= 0.02
        assert match["minimum_true_recoverability_delta"] > 1e-12


def test_temporal_operator_uses_finite_series_empirical_hat_sigma(monkeypatch) -> None:
    family = TemporalTwinEFamily(
        family="temporal_debug",
        propagation_lag=2,
        seed=23,
        n_train=400,
        burn_in=50,
        n_nodes=5,
        phi=TWIN_ORDINARY_MEMORY,
        factor_process_noise=TWIN_FACTOR_NOISE,
        local_process_noise=TWIN_LOCAL_NOISE,
        advect=0.22,
        dispersion=0.18,
    )
    calls = []

    def fake_empirical(series, **kwargs):
        calls.append((series.shape, kwargs["gap_length"]))
        return {"B_union_D": {"predicted_skill": 0.314}}

    monkeypatch.setattr(
        twin_e_module, "empirical_information_set_conditionals", fake_empirical
    )
    monkeypatch.setattr(
        twin_e_module,
        "_analytic_temporal_truth",
        lambda _family, _graph, gap: (float(gap), 0.2),
    )
    monkeypatch.setattr(
        twin_e_module,
        "validate_temporal_twin_e_pair",
        lambda _family: {
            "sample_donor_r2_delta": 0.0,
            "population_donor_r2_delta": 0.0,
            "target_series_exact": True,
        },
    )
    scores = twin_e_module.generate_temporal_twin_e_scores((family,))
    assert len(calls) == 6
    assert {shape for shape, _ in calls} == {(400, 5)}
    assert set(scores["operator_recoverability"]) == {0.314}
    assert set(scores["true_recoverability"]) == {0.2}


def test_holdout_runner_refuses_a_lock_outside_the_repository(tmp_path) -> None:
    outside = tmp_path / "uncommitted_holdout.yaml"
    outside.write_text(HOLDOUT_FREEZE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="inside the repository"):
        run_locked_twin_e_holdout(outside)


def test_formal_writer_refuses_unverified_design_diagnostic(tmp_path) -> None:
    with pytest.raises(ValueError, match="verified lock commit"):
        write_locked_twin_e_holdout_artifacts(
            run_twin_e(), tmp_path, lock_path=HOLDOUT_FREEZE
        )


def test_twin_e_artifacts_are_separate_from_historical_a_to_d(tmp_path) -> None:
    historical = tmp_path / "twin_design_manifest.json"
    historical.write_text("historical A-D audit\n", encoding="utf-8")
    output = tmp_path / "twin_e"
    paths = write_twin_e_artifacts(run_twin_e(), output)
    assert historical.read_text(encoding="utf-8") == "historical A-D audit\n"
    assert set(paths) == {"scores", "univariates", "manifest"}
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["cell"] == "E"
    assert manifest["purpose"] == "exploratory_design_debug_not_gate_evidence"
    assert manifest["gate"]["passed"] is False
    assert manifest["holdout_status"] == "locked_unscored_not_run_by_this_script"
    assert manifest["superseded_auc_gate_used"] is False
    assert manifest["historical_a_to_d_artifacts_overwritten"] is False
