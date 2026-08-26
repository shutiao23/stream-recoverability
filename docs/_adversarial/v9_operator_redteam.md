# RED TEAM: Phase 1 operator wiring (second pass)

Date: 2026-08-26  
Role: attack leftovers in the **merged** code only. Not a protocol. Not a license to implement.  
Parent already accepted: primary \(\mathcal R\) is the sqrt mean-diag map; `predicted_skill` stays secondary; Shapley **default** is `recoverability_r`; \(\varepsilon_\perp\) is a remainder that also absorbs two-sided vs nearest-boundary mismatch.

Sealed temperatures were not opened.

---

## Verdict

The missing files landed. `recoverability_r` exists and is the freeze map. `operator_shapley.py` defaults to that key. `heuristic_bias.py` writes a named split. Those are not leftovers.

What is left is that **every live caller still ignores the default**. Spectrum \(\tau\), the baseline suite, the 6-river scorer, `scripts/53`, `shapley_toy.csv`, and the river Shapley tests all still attribute MAE skill. \(\varepsilon_\perp\) is still `old − new − ε_{d/4}` with no on/off isolation of the orthogonality piece from the accepted two-sided remainder. Empirical \(d=365\) still `nan_to_num(..., 0)` then ridge. Tests that matter still sit on identities or on MAE.

T1 is not closed.

---

## 1. \(\varepsilon_\perp\) is still an unidentified dump

Parent allows \(\varepsilon_\perp\) to include two-sided vs nearest-boundary mismatch. That does **not** license treating every leftover as \(\varepsilon_\perp\) without isolation.

Code (`heuristic_bias.py` `bias_terms`):

```text
epsilon_d_over_4 = (1 - R2_donor) * (-heuristic_gap)
epsilon_perp     = (old - new) - epsilon_d_over_4
```

That is an accounting identity, not an identification. `test_bias_terms_split_old_minus_new_into_epsilons` only checks the identity. `test_epsilon_perp_grows_when_orthogonality_is_violated` only checks \(|\varepsilon_\perp|\) at \(d=30\).

`heuristic_bias_terms.csv` already shows the isolation failed:

| system | \(d\) | \(\varepsilon_\perp\) | \(|\varepsilon_\perp|\) |
| --- | ---: | ---: | ---: |
| `orthogonal_ar1_donor` | 14 | −0.0445 | **0.0445** |
| `nonorthogonal_ar1_donor` | 14 | +0.0319 | 0.0319 |
| `orthogonal_ar1_donor` | 30 | −0.0090 | 0.0090 |
| `nonorthogonal_ar1_donor` | 30 | +0.0232 | 0.0232 |

At \(d=14\), turning orthogonality **off** *shrinks* \(|\varepsilon_\perp|\). The “grows” test is a \(d=30\) window. There is no reported \(\Delta\varepsilon_\perp\), no predeclared two-sided remainder, and no third column for ACF / topology misspecification.

`epsilon_d_over_4` always uses scalar \(\varphi=|A_{00}|\) and `jensen_acf_gap`. On `advection_chain` and `endpoint_*` that AR(1) story is false, so the misspecification is dumped into \(\varepsilon_\perp\) (advection \(d=14\): \(\varepsilon_\perp=-0.155\)). `paper/theory.md` limitations say \(\varepsilon_\perp\) absorbs the two-sided remainder. They do not say it absorbs a wrong ACF.

`test_high_donor_high_memory_forces_the_hard_label` only asserts the heuristic identity. It does not assert operator \(V_B(\mathcal R)>0\) in the degeneration region. CSV at mixed \(d=30\): \(\mathcal R(B\cup D)=0.661\), heuristic forced. Remaining boundary value is untested.

---

## 2. Shapley default is \(\mathcal R\); every shipped call overrides to MAE

`shapley_from_conditionals` / `shapley_from_var1` default `value_key="recoverability_r"`. That default is unused in the live Phase 1 path.

| Caller | `value_key` |
| --- | --- |
| `scripts/53_quantify_heuristic_bias.py` | **`expected_mae_conditional`** (hard-coded twice) |
| `results/framework/synthetic_identifiability/shapley_toy.csv` | **`expected_mae_conditional`** |
| `test_memory_dominant_boundary_shapley_exceeds_donor` | **`expected_mae_conditional`** |
| `test_donor_dominant_donor_shapley_exceeds_boundary` | **`expected_mae_conditional`** |
| `test_four_set_shapley_is_efficient` | **`expected_mae_conditional`** |

No test calls `shapley_from_var1` without `value_key`. The freeze default is untested on a river. The written toy table is MAE reduction, not \(\mathcal R\).

`LOWER_BETTER_KEYS` includes MAE and ncv, not `recoverability_r` (higher-is-better). That part is correct. The leftover is that Phase 1 artifacts and tests refuse the default.

---

## 3. Live pipeline still treats `predicted_skill` / MAE as primary \(\mathcal R\)

`recoverability_r` is in `conditional_summaries`. Callers that build the scientific objects do not use it.

**Spectrum \(\tau\)** (`recoverability_spectrum.py`):

```text
spectrum_from_conditionals(..., risk_key="expected_mae_conditional")
```

then `recoverability(L_S, L_0) = 1 - mae_S/mae_0`, which **is** `predicted_skill`. Freeze incremental is \(V_D=\mathcal R(B\cup D)-\mathcal R(B)\). E0 signs and `real_river_checks` `tau` are therefore still MAE-skill \(\tau\).

`spectrum_frame` still writes `predicted_skill_{name}` and `predicted_risk_{name}`. No `recoverability_r_{name}`.

Trap: switching `risk_key` to `"recoverability_r"` without changing the wrapper is worse. `recoverability_r` at `none` is 0, so `recoverability(R_S, R_0)` divides by zero. Incremental must consume \(\mathcal R\) **levels**, not wrap them in a loss ratio.

**Baseline suite** (`recoverability_baselines.predictor_frame`):

```text
observed_structural_skill = recoverability(mae_S, mae_0)
conditional_covariance    = predicted_skill
```

Still \(X=Y\). `results/framework/baseline_nested_r2.csv` last row remains `r2=1.0`. `test_operator_explains_residual_after_simple_baselines` still asserts `residual_r2 > 0`.

**6-river scorer** (`real_river_checks.py`): stores `predicted_skill` and MAE `tau`. No `recoverability_r` column. T2 Spearman on this table is still \(\mathrm{corr}(s, \text{achieved skill})\).

Historical `recoverability_budget.py` `1-sqrt(1-R2_avail)` is baseline #4. Not a new Phase 1 write. Do not cite it as the Schur \(\mathcal R\).

---

## 4. Empirical \(d=365\) still `nan_to_num` → 0 → ridge

Unchanged (`conditional_observability.py`):

```text
empirical_pair_covariance: missing lag → 0.0
joint = ridge_psd(np.nan_to_num(joint, nan=0.0), ridge)
```

No `inference_status`. No \(n_{\mathrm{eff}}\) floor. First-pass number still stands: memory river, 4 years, \(d=365\), empirical `predicted_skill` \(\approx 0.50\) vs exact \(\approx 0.030\). Freeze stress list includes 365. Zero tests import `empirical_information_set_conditionals`. Zero tests at `gap_length=365`.

---

## 5. Tests still do not leave the identity / MAE set

| Test | What it actually checks | What it does not |
| --- | --- | --- |
| `test_recoverability_r_matches_v9_...` | 2×2 diagonal: \(\mathcal R\neq s\) | Any VAR gap, any \(d=365\) |
| `test_adding_observations_never_...` | Loewner / MAE / \(\mathcal R\) monotone at **\(d=14\)** | Degeneration \(V_B(\mathcal R)>0\) |
| `test_spectrum_recovers_known_...` | MAE-skill \(\tau\) sign at \(d=30\) | \(\tau\) on `recoverability_r` |
| Shapley river tests | MAE order / efficiency | Default `recoverability_r` |
| `test_bias_terms_split_...` | \(\varepsilon_\perp+\varepsilon_{d/4}=\mathrm{old}-\mathrm{new}\) | Isolation |
| `test_epsilon_perp_grows_...` | \(\lvert\varepsilon_\perp\rvert\) at \(d=30\) only | \(d=14\) (fails the “grows” story); \(\Delta\varepsilon_\perp\) |
| `test_high_donor_high_memory_...` | Heuristic forced | Operator remaining memory |
| `test_operator_relative_error_...` | Schur vs precision at \(d=14\) | Empirical long gap |
| E0 / residual-gain | Signs + tautology \(R^2>0\) | Primary \(\mathcal R\) incremental |

`test_four_set_interface_...` only checks keys and `n_observed==4`. It does not Shapley \(\mathcal R\) on {B, D, M, H}.

---

## Must-fix leftovers

1. **Isolate the orthogonality piece.** Keep the accepted two-sided remainder inside \(\varepsilon_\perp\) if named. Add an on/off contrast (orthogonal vs correlated, same \(\varphi\), same \(d\)) that reports \(\Delta\varepsilon_\perp\) as the orthogonality increment, and a declared remainder for ACF/topology misspecification. Stop applying scalar `jensen_acf_gap` to non-AR(1) rivers without a misspecification flag. Assert operator \(V_B(\mathcal R)>0\) on `high_donor_and_high_memory`. Drop or rewrite the “grows at \(d=30\)” test; \(d=14\) already contradicts it.

2. **Ship Shapley on `recoverability_r`.** Change `scripts/53` and regenerate `shapley_toy.csv`. Add one river test that calls `shapley_from_var1` **without** `value_key`. Four-set efficiency on \(\mathcal R\), not MAE.

3. **Point the live spectrum and scorer at \(\mathcal R\).** `spectrum_from_conditionals` must use `recoverability_r` **levels** for \(V_D,V_B,\tau\) (do not wrap in `recoverability()`). `spectrum_frame` must write `recoverability_r_{name}`. `real_river_checks` must store `recoverability_r`. Kill the baseline tautology: `conditional_covariance` cannot equal `observed_structural_skill`. Recompute or delete `baseline_nested_r2.csv` \(R^2=1.0\).

4. **Close empirical \(d=365\).** Missing lag or \(n_{\mathrm{eff}}\) below a floor → NaN + `withheld`, not `0.0` then `ridge_psd`. Test that the 4-year memory case does not report skill \(\approx 0.5\).

5. **Tests must use the merged defaults.** At least one spectrum test with `risk_key` omitted after the default is \(\mathcal R\); one Shapley test with `value_key` omitted; one degeneration-region operator assertion; one empirical long-gap withheld. MAE-only suites do not close T1.
