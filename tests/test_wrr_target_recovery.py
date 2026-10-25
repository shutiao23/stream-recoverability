"""Unit checks for the target-recovery (TR) helpers; no archive data are read."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import wrr_tr_common as T  # noqa: E402
import wrr_tr_law as L  # noqa: E402
import wrr_tr_rules as R  # noqa: E402


def _script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_") + "_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _year(seed: int = 0) -> tuple[np.ndarray, pd.DatetimeIndex]:
    index = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    rng = np.random.default_rng(seed)
    season = 10 - 8 * np.cos(2 * np.pi * (index.dayofyear.to_numpy() - 20) / 365)
    return season + rng.normal(0, 0.5, len(index)), index


def test_target_statistics_match_direct_computation() -> None:
    values, index = _year()
    stats = T.target_statistics(values, index, 20.0)
    rolled = pd.Series(values).rolling(30).mean()
    assert stats["h30"] == pytest.approx(rolled.max())
    assert stats["c30"] == pytest.approx(rolled.min())
    assert stats["annual_mean"] == pytest.approx(values.mean())
    jjas = index.month.isin([6, 7, 8, 9])
    assert stats[T.DEGREE_DAYS] == pytest.approx(np.clip(values[jjas], 0, None).sum())
    shifted = T.target_statistics(values, index, 20.0, (5, 6, 7, 8))
    assert shifted[T.DEGREE_DAYS] == pytest.approx(np.clip(values[index.month.isin([5, 6, 7, 8])], 0, None).sum())
    matrix = T.target_statistics(np.vstack([values, values + 1]), index, 20.0)
    assert matrix["h30"][1] - matrix["h30"][0] == pytest.approx(1.0)


def test_hot_year_definitions() -> None:
    assert T.hemisphere_shift_days(-35.0) == (184 if T.SEASON_MODE == "hot_year" else 0)
    assert T.hemisphere_shift_days(45.0) == 0 and T.hemisphere_shift_days(None) == 0
    doy = np.arange(1, 366)
    # A climatology peaking at the start of August: the five hottest consecutive months are May-September.
    climate = 12 - 8 * np.cos(2 * np.pi * (doy - 30) / 365)
    assert T.hottest_months(climate, doy, 5) == (5, 6, 7, 8, 9)
    # A Southern Hemisphere station on its shifted (July-June) year peaks in the middle of that year too.
    shifted = 12 - 8 * np.cos(2 * np.pi * (doy - 15) / 365)
    assert T.hottest_months(shifted, doy, 4) == (6, 7, 8, 9)


def test_conformal_offsets_are_finite_sample_quantiles() -> None:
    cqr = _script("451_tr2_cqr.py")
    residuals = np.repeat(np.arange(1, 20, dtype=float)[:, None], len(cqr.LEVELS), axis=1)
    out = cqr.offsets(residuals)
    levels = list(cqr.LEVELS)
    # n = 19: the 95% level takes the ceil(20 * 0.95) = 19th order statistic, the 5% level the floor(20 * 0.05) = 1st.
    assert out[levels.index(0.95)] == pytest.approx(19.0)
    assert out[levels.index(0.05)] == pytest.approx(1.0)
    assert out[levels.index(0.5)] == pytest.approx(10.0)


def test_label_free_admission_with_factor() -> None:
    rule = _script("453_tr2_expected_risk.py")
    score = np.array([0.01, 0.02, 0.03, 0.2, 0.5])
    weight = np.ones(5)
    assert list(rule.admit(score, weight, 0.05, 1.0)) == [True, True, True, False, False]
    # k = 3 requires a mean predicted risk of at most 1/60: only the first two cases.
    assert list(rule.admit(score, weight, 0.05, 3.0)) == [True, True, False, False, False]
    assert not rule.admit(np.array([0.2, 0.3]), np.ones(2), 0.05, 1.0).any()


def test_mask_from_runs_round_trip() -> None:
    mask = T.mask_from_runs("3:4;100:30", 365)
    assert mask.sum() == 34 and mask[3:7].all() and mask[100:130].all() and not mask[7]


def test_low_flow_classical_extension_preserves_historical_cases_and_random_stream() -> None:
    flow = _script("461_tr2_flow_demo.py")
    index = pd.date_range("2000-04-01", "2004-03-31")
    rng = np.random.default_rng(42)
    anomaly = rng.normal(0, .3, len(index))
    seasonal = .5 * np.sin(np.arange(len(index)) * 2 * np.pi / 365)
    panel = pd.DataFrame({"target": seasonal + anomaly,
                          "donor": seasonal + anomaly + rng.normal(0, .01, len(index))}, index=index)
    arguments = ("target", panel, ["donor"], [[(60, 30)], [(180, 60)]], "region1", 3)
    historical = pd.DataFrame(flow.station_cases(*arguments))
    extended = pd.DataFrame(flow.station_cases(*arguments, classical=True))
    assert len(historical) > 0
    pd.testing.assert_frame_equal(historical, extended[historical.columns], check_exact=True)
    assert extended.move1_log7q.notna().all()
    assert extended.stochastic_log7q_draws.map(len).eq(20).all()
    assert extended.mask_sha256.str.len().eq(64).all()


def test_zero_flow_proxy_rejects_unapproved_negative_and_conflicting_dates() -> None:
    module = _script("519_review_completion_zero_flow_missingness.py")
    raw = pd.DataFrame({"site": ["a", "a", "a", "b", "b", "c"],
        "date": pd.to_datetime(["2000-01-01", "2000-01-01", "2000-01-02", "2000-01-01", "2000-01-02", "2000-01-01"]),
        "flow_cms": ["0", "1", "2", "-9999", "0", "0"], "flow_code": ["A", "A", "A", "A", "P", "A"]})
    result = module.zero_flow_proxy(raw).set_index("site")
    assert result.loc["a", "approved_days"] == 1 and result.loc["a", "zero_days"] == 0
    assert "b" not in result.index
    assert result.loc["c", "zero_days"] == 1


def test_missingness_bootstrap_helper_imports_in_spawned_workers() -> None:
    module = _script("519_review_completion_zero_flow_missingness.py")
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({"station_key": np.repeat(np.arange(6), 12),
        "independence_group": np.repeat(np.arange(6), 12), "z_air": rng.normal(size=72),
        "trend": np.tile(np.arange(12), 6), "outcome": rng.integers(0, 2, 72)})
    result = module.missingness_model().bootstrap_conditional(frame, "outcome", ["z_air", "trend"], "station_key", draws=2, seed=0, workers=2)
    assert len(result) == 2 and np.isfinite(result["beta__z_air"]).all()


def delivery_controller_fixture(tmp_path, monkeypatch):
    module = _script("520_review_completion_finish_delivery.py")
    monkeypatch.setattr(module, "OUT", tmp_path / "results")
    monkeypatch.setattr(module, "EVIDENCE", module.OUT / "evidence")
    monkeypatch.setattr(module.T, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["520_review_completion_finish_delivery.py"])
    files = {
        "inputs/forcing_recovery/europe/status.json": {"partial": False},
        "inputs/forcing_recovery/europe/numerical_audit.json": {"passed": True},
        "independent_study/public_registration_status.json": {"status": "public_registration_and_attachments_verified"},
        "evidence/validation.json": {"full_Europe_available_coordinate_forcing_complete": True,
            "driver_recovery_models_complete": {"europe": True}, "checks": [{"passed": True}]},
    }
    for name, value in files.items():
        path = module.OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
    bundle = module.OUT / "independent_study/registration_code_and_protocol.tar.gz"
    bundle.write_bytes(b"publicly registered immutable bytes")
    paper = tmp_path / "paper/wrr_tr"; paper.mkdir(parents=True)
    for name in ["article", "supporting"]:
        (paper / f"review_completion_{name}.log").write_text("Clean compilation")
    (paper / "review_completion_tables_si.tex").write_text("\\begin{table}\\end{table}")
    doc = tmp_path / "docs/reviews/wrr_review_completion_20261024/FORCING_EXECUTION_ZH.md"
    doc.parent.mkdir(parents=True); doc.write_text("## 欧洲完整结果\n\n## 恢复概率重算\n")
    return module, bundle


def test_final_delivery_stops_before_mutations_without_full_european_evidence(tmp_path, monkeypatch):
    module, bundle = delivery_controller_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "europe_evidence", lambda out: {"full_source": False})
    calls = []
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="must complete"):
        module.main()
    assert calls == [] and bundle.read_bytes() == b"publicly registered immutable bytes"


def test_final_delivery_preserves_public_registration_archive(tmp_path, monkeypatch):
    module, bundle = delivery_controller_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "europe_evidence", lambda out: {"full_source": True})
    calls = []
    monkeypatch.setattr(module, "run", lambda stage, *args, **kwargs: calls.append(stage))
    assert module.main() == 0
    assert "bundle" not in calls and "receipt_verify" in calls
    assert bundle.read_bytes() == b"publicly registered immutable bytes"
    assert not json.loads((module.EVIDENCE / "final_delivery_progress.json").read_text())["all_user_requirements_complete"]


def test_variance_factor_limits() -> None:
    assert L.variance_factor(np.array([1.0]), 0.8)[0] == pytest.approx(1.0)
    assert L.variance_factor(np.array([10.0]), 0.0)[0] == pytest.approx(0.1)
    assert L.variance_factor(np.array([30.0]), 0.99)[0] > L.variance_factor(np.array([30.0]), 0.5)[0]
    # A fully hidden window with no residual persistence couples as 1/30 per hidden day.
    assert L.cross_factor(np.array([30.0]), 0.0)[0] == pytest.approx(1 / 30)


def _law_row(shares: str, anomalies: str, **extra) -> pd.Series:
    base = dict(law_hidden_shares=shares, law_peak_anomalies=anomalies, law_sigma_a=1.5, law_sigma_r_warm=1.0, law_mu_r_warm=0.0,
                law_phi_r=0.8, law_phi_a=0.9, h30__policy=20.0, observed_lower_bound__observed_days=np.nan)
    base.update(extra)
    return pd.Series(base)


def test_recovery_law_is_cold_and_grows_with_hidden_share() -> None:
    none = L.case_law(_law_row("0;0;0", "1;1;1"))
    half = L.case_law(_law_row("0.5;0.5;0.5", "1;1;1"))
    full = L.case_law(_law_row("1;1;1", "1;1;1"))
    assert none["law_pfail"] == pytest.approx(0.0, abs=1e-6)
    assert full["law_bias"] < half["law_bias"] < 0
    assert full["law_pfail"] > half["law_pfail"] > none["law_pfail"]
    # The observed lower bound truncates positive errors only.
    truncated = L.case_law(_law_row("1;1;1", "-1;-1;-1", observed_lower_bound__observed_days=20.0))
    untruncated = L.case_law(_law_row("1;1;1", "-1;-1;-1"))
    assert truncated["law_bias"] <= untruncated["law_bias"]


def test_replay_law_reflects_training_errors() -> None:
    row = pd.Series({"law_replay_errors": "-0.9;-0.8;-1.0;-0.7"})
    law = L.replay_law(row)
    assert law["law_bias"] == pytest.approx(-0.85)
    assert law["law_pfail"] > 0.9


def test_published_rules_on_handmade_masks() -> None:
    cases = pd.DataFrame({
        "mask_runs": ["200:10", "10:16", "180:62", ""],
        "year": [2021, 2021, 2021, 2021],
        "warm_observed_fraction": [0.93, 1.0, 0.59, 1.0],
        "observed_lower_bound__observed_days": [20.0, 20.0, 19.0, 20.0],
        "train_h30_mean": [19.0] * 4, "train_h30_sd": [1.0] * 4,
    })
    rules = R.fixed_rules(R.mask_features(cases), cases)
    assert list(rules["R1_wmo_11_5"]) == [False, False, False, True]
    # ETCCDI also caps each month at three missing days, so a 10-day July gap fails.
    assert list(rules["R1_etccdi_15_3"]) == [False, False, False, True]
    assert list(rules["R1_gsim_350d"]) == [True, False, False, True]
    assert list(rules["R2_beaufort_julaug_complete"]) == [False, True, False, True]
    assert list(rules["R1_johnson_gap_le_49d"]) == [True, True, False, True]
    assert list(rules["R2_oregon_jas_80pct"]) == [True, True, False, True]


def test_risk_retention_curve_and_ties() -> None:
    e5 = _script("436_tr_e5_rules.py")
    score = np.array([0.0, 0.0, 0.1, 0.2, 0.9])
    fail = np.array([0.0, 0.0, 0.0, 1.0, 1.0])
    curve = e5.curve(score, fail, np.ones(5))
    assert list(curve.coverage) == [0.4, 0.6, 0.8, 1.0]
    assert e5.retention_at(curve, 0.0) == pytest.approx(0.6)
    assert e5.retention_at(curve, 0.25) == pytest.approx(0.8)
    pfail = e5.predictive_pfail(np.array([[9.0, 9.5, 10.0, 10.5, 11.0]]), (0.05, 0.25, 0.5, 0.75, 0.95), np.array([10.0]), 0.5)
    assert pfail[0] == pytest.approx(0.5)


def test_expected_risk_threshold_needs_no_labels() -> None:
    e7d = _script("447_tr_e7_expected_risk.py")
    score = np.array([0.01, 0.02, 0.03, 0.2, 0.5])
    # Admitting 0.2 would raise the mean predicted risk to 0.065.
    assert e7d.expected_risk_threshold(score, np.ones(5), 0.05) == pytest.approx(0.03)
    score = np.array([0.01, 0.02, 0.03, 0.12, 0.5])
    assert e7d.expected_risk_threshold(score, np.ones(5), 0.05) == pytest.approx(0.12)


def test_inverse_cdf_stays_inside_extrapolated_support() -> None:
    e8 = _script("440_tr_e8_downstream.py")
    levels = np.array([0.05, 0.25, 0.5, 0.75, 0.95])
    quantiles = np.array([[9.0, 9.5, 10.0, 10.5, 11.0]])
    draws = e8.inverse_cdf(np.repeat(quantiles, 200, axis=0), levels, np.linspace(0, 1, 200)[:, None])
    assert np.all(np.diff(draws[:, 0]) >= 0)
    assert draws[100, 0] == pytest.approx(10.0, abs=0.05)
    slope, se = e8.ols(np.arange(2000, 2020, dtype=float), np.arange(20, dtype=float) * 0.05)
    assert slope == pytest.approx(0.5) and se == pytest.approx(0.0, abs=1e-9)
