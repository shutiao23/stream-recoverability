# P0-1 test-audit root cause

## What failed

GitHub Actions run [31915311576](https://github.com/shutiao23/stream-recoverability/actions/runs/31915311576) on `origin/main` `6a6cffa` reported **17 failed, 361 passed** on `ubuntu-latest` Python 3.11. The job installed **numpy 2.4.6** and **pandas 3.0.5** because `pyproject.toml` declared `numpy>=1.24` and `pandas>=2.0` with no upper bound.

A local `PYTHONPATH=src python -m pytest --maxfail=3` on numpy 1.26.4 / pandas 2.1.4 stopped after **3 failed, 360 passed**. Those three are version-independent. The remaining 14 CI failures only appear on the unpinned CI majors.

### CI failures (17)

| Test | Error |
| --- | --- |
| `tests/test_metrics.py::test_quantile_coverage_width_pinball_and_crps` | `AttributeError: module 'numpy' has no attribute 'trapz'` |
| `tests/test_experiment_runner.py::test_proposed_prediction_uses_requested_windows_and_only_covers_hidden_t` | `np.trapz` |
| `tests/test_experiment_runner.py::test_old_proposed_checkpoint_without_scaler_requires_structured_retraining` | `np.trapz` |
| `tests/test_frozen_analysis_pipeline.py::test_resilience_requires_and_summarizes_complete_three_site_powersets` | `np.trapz` |
| `tests/test_reference_runner.py::test_csdi_runner_stitches_samples_and_emits_interval_metrics` | `np.trapz` |
| `tests/test_retrained_information.py::test_partial_retrained_run_writes_exact_retryable_and_hash_gates` | `np.trapz` |
| `tests/test_science_experiments.py::test_compensation_output_uses_checkpoint_for_s0_and_strict_score_mask` | `np.trapz` |
| `tests/test_science_experiments.py::test_compensation_resume_preserves_other_seed_and_excludes_bad_checkpoint` | `np.trapz` |
| `tests/test_science_experiments.py::test_compensation_rejects_training_input_changes_against_version_manifest` | `np.trapz` |
| `tests/test_scientific_analysis.py::test_network_resilience_requires_complete_three_station_powersets` | `np.trapz` |
| `tests/test_scientific_analysis.py::test_frontier_uses_dense_fixed_window_first_loss_and_paired_bootstrap` | pandas 3 `stack(dropna=...)` `ValueError` |
| `tests/test_scientific_analysis.py::test_shapley_validates_each_scenario_training_seed_before_aggregation` | `assert nan is None` |
| `tests/test_scientific_analysis.py::test_scientific_trends_are_seed_specific_and_require_complete_reconstruction` | `assert nan is None` |
| `tests/test_confirmatory_data.py::test_full_mocked_build_is_atomic_immutable_and_provenance_complete` | empty `query` then `iloc[0]` `IndexError` |
| `tests/test_reference_runner.py::test_reference_and_proposed_target_roster_is_t_only_without_training` | `assert False is True` on `run_manifest["complete"]` |
| `tests/test_reference_runner.py::test_reference_protocol_supports_both_development_splits[validation]` | `ValueError: formal execution requires a data-version manifest` |
| `tests/test_scientific_analysis.py::test_analysis_script_rejects_unmanifested_result_tables` | argparse required `--sensitivity-manifest` before the missing top-manifest check |

### Local maxfail=3 failures (3)

The same last three rows. Local numpy still has `np.trapz` and local pandas 2.1 still accepts `stack(dropna=False)` and string-date `query`, so the suite never reached a green full run here.

## Root cause

1. **NumPy 2 removed `np.trapz`.** Call sites in `evaluation/metrics.py` (approximate CRPS) and `analysis/resilience.py` (resilience AUC) used the removed name. Most CI failures are that one missing attribute during scoring.

2. **pandas 3 changed `DataFrame.stack`.** `analysis/frontiers.py` called `.stack(dropna=False)`. The new stack implementation forbids `dropna`.

3. **pandas 3 coerces `None` to NA/NaN** in mixed optional-text columns. Shapley `reason` and scientific `sequence_metric_reason` are defined as `None` when a unit is complete; tests correctly assert identity `is None`.

4. **pandas 3 `DataFrame.query` no longer matches datetime columns to date strings.** The confirmatory builder still wrote the 2012-01-01 / 2023-01-01 rows (row counts passed). The test lookup was empty.

5. **`run_manifest["complete"]` is now `formal_design_complete`.** Smoke runs without formal authorization are fail-closed `False`. The roster test still treated `complete` as "this smoke shard finished," which is now `run_complete`.

6. **Validation-split runners require a hashed data-version manifest and quality table.** That gate is intentional. The reference-runner helper built only a synthetic wide table.

7. **`scripts/09_analyze_results.py` now requires `--sensitivity-manifest` three times.** The unmanifested-table test never reached the missing top-manifest path.

8. **No major-version pins.** CI could (and did) jump to numpy 2 / pandas 3 on the next `pip install`.

## Fix

- Use `np.trapezoid` with `np.trapz` fallback in metrics and resilience so numpy 1.26 and 2.x both work.
- Stack frontier panels with `future_stack=True`, falling back to `stack(dropna=False)` on older pandas.
- Re-materialize optional text columns as object dtype with explicit `None` after DataFrame construction.
- Look up confirmatory rows with normalized timestamps, not string `query`.
- Assert `run_complete` / structural-skip keys on the smoke roster test; keep `complete` / `formal_design_complete` False.
- For the validation development-split test, write a tmp quality table and `version_manifest.json`. Do not disable `require_manifest`.
- Pass three `--sensitivity-manifest` paths, then still require the missing top-manifest name in stderr.
- Pin `numpy>=1.24,<3` and `pandas>=2.0,<4` so CI cannot silently take the next major.

## Verification

- `python -m compileall -q src scripts tests` passed.
- `ruff check --select E4,E7,E9,F src` passed (ruff 0.16.2).
- Anaconda env (numpy 1.26.4 / pandas 2.1.4): full `PYTHONPATH=src python -m pytest` reported **378 passed** in 211s.
- Dedicated venv `/tmp/sr-ci-np2` (does not use Anaconda site-packages): `pip install -e ".[dev,reference]" numpy==2.4.6 pandas==3.0.5`. Confirmed `numpy==2.4.6`, `pandas==3.0.5`, `np.trapz` absent, `np.trapezoid` present.
- On that stack: `PYTHONPATH=src /tmp/sr-ci-np2/bin/python -m pytest` reported **391 passed, 0 failed, 0 skipped** in 286.83s. JUnit: `results/test_audit/pytest.xml` (copy of `pytest_np24_pd30.xml`). Log: `results/test_audit/pytest_np24_pd30_stdout.txt`. Collected count rose from 378 because other in-progress work added tests; none failed on this stack.

## Remaining risk

- Pins are `numpy>=1.24,<3` and `pandas>=2.0,<4`. They allow the CI majors (2.4.6 / 3.0.5) and now those exact versions are proven green locally. They do not lock patch/minor versions.
- There is still no lockfile. Patch/minor drift inside numpy 2.x or pandas 3.x remains possible.
- `requires-python = ">=3.10"` is not exercised by CI (3.11 only).
- Optional `pypots==1.5` is CI-installed via `.[reference]`; a pypots/torch resolver change can still break reference tests.
- The workflow timeout is 90 minutes; a slower runner could still fail without a product bug.
- Untracked local `masks/`, `paper/manuscript.md`, `results/experiments_v2/`, and `results/formal/` were left in place and were not the CI failures.
