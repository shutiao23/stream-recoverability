# RED TEAM: Phase 1 theory

Date: 2026-08-26
Status: attack, not a patch. No other files were edited.
Target: `paper/theory.md` (exists; 135 lines). Cross-checked against T1 in `docs/v9_redesign_master_plan.md:27-33`, `configs/design_freeze_v9.yaml` `theory_propositions` / `primary_estimand` / `decision_endpoints.a_placement`, `src/stream_recoverability/analysis/conditional_observability.py`, and `src/stream_recoverability/analysis/heuristic_degeneration.py`.
Sealed temperatures were not opened.

Verdict: T1 is not closed. Prop 1 is the only population identity that is actually proved, and it is proved for a known PSD \(\Sigma\) and a nested pair \(O_1\subseteq O_2\), not for the ridged empirical operator the code returns. Prop 2 cites Krause, Singh, and Guestrin (2008) for a *different* set function than \(\eqref{eq:F}\) in `theory.md`, then states a \((1-1/e)\) guarantee that T3(a) will apply to worst-case MAE. Prop 3 writes \(\varepsilon_\perp+\varepsilon_{d/4}\) as a tautological split of old-minus-new; \(\varepsilon_\perp\) does not vanish under the stated hypotheses because \(B\) is two-sided. Prop 4 is a univariate Gaussian integral restated as an estimator-independent law for `mae_degC` on non-Gaussian recovery models. Section 4 correctly refuses eight-station *labels* as discoveries and refuses calibration claims; it does not name the 6-river LORO or the 8-station table as forbidden *theory* confirmation, and the scoring path already treats \(\sqrt{2/\pi}\,\overline{\sigma}(\hat\Sigma_{G|O})\) as predicted risk on real rivers.

---

## 0. What was attacked

`paper/theory.md` is present. This is not an attack on a missing file. It is an attack on the four proposition statements, their proofs, and the freeze keys that will cite them.

T1 required (`docs/v9_redesign_master_plan.md:28-33`):

1. \(O_1\subseteq O_2\Rightarrow\Sigma_{G|O_2}\preceq\Sigma_{G|O_1}\).
2. Submodularity of log-det information gain \(\Rightarrow\) greedy \((1-1/e)\) (Krause et al. 2008).
3. Additive \(d/4\) as the special case under orthogonality + exponential ACF; write \(\varepsilon_\perp+\varepsilon_{d/4}\) and the region \(R^2_{\mathrm{donor}}\ge 0.5\).
4. Bonus: any estimator MAE \(\ge\sqrt{2/\pi}\cdot\overline{\mathrm{sd}}(\Sigma_{G|O})\) under a second-order Gaussian model.

Freeze machine fields (`configs/design_freeze_v9.yaml:254-262`): `prop2_logdet_submodularity: greedy_one_minus_1_over_e`; `prop3_bias_terms: [epsilon_perp, epsilon_d_over_4]`; `prop4_estimator_independent_mae_bound: sqrt_2_over_pi_times_mean_conditional_sd`; `non_gaussian_fallback: quantile_width_keep_monotonicity_only`.

The code implements a ridged Schur complement and a Gaussian MAE functional. It does not prove T1. `heuristic_degeneration.py` states that its results “are identities of the formula, not empirical findings from a river” and exist “so the current Design cannot be mistaken for a theorem.” That comment is the opposite of treating those identities as Prop 3.

---

## 1. Three skill maps, one word “recoverability”

`theory.md` correctly writes three different maps and then lets later propositions talk as if they were one operator.

Freeze / `theory.md` primary (`theory.md` \(\eqref{eq:R}\); freeze `primary_estimand`):

\[
\mathcal R(O)=1-\sqrt{\frac{\overline{\mathrm{diag}}\,\Sigma_{G|O}}{\overline{\mathrm{diag}}\,\Sigma_{GG}}}.
\]

Code `predicted_skill` (`conditional_observability.py:114-116`, `theory.md` \(\eqref{eq:skill}\)):

\[
s(O)=1-\frac{\overline{\sigma}(\Sigma_{G|O})}{\overline{\sigma}(\Sigma_{GG})},\qquad\overline{\sigma}(\Sigma)=\mathrm{mean}_i\sqrt{\Sigma_{ii}}.
\]

Heuristic conversion (`recoverability_budget.py:99`; forbidden in the freeze as `1_minus_sqrt_1_minus_R2_as_a_theorem`):

\[
s_{\mathrm{heur}}=1-\sqrt{1-R^2_{\mathrm{avail}}}.
\]

Jensen on \(x\mapsto x^2\) gives \(\sqrt{\overline{\mathrm{diag}}}\ge\overline{\sigma}\), with equality iff every hidden coordinate has the same residual variance. A two-sided gap is *designed* to violate that: residual variance is smaller near \(B\) than at mid-gap. So \(\mathcal R\neq s\) on the intended \(G\). The 6-river scorer (`real_river_checks.py:101-106`) writes `predicted_conditional_risk = expected_mae_conditional` (that is \(c\,\overline{\sigma}(\hat\Sigma_{G|O})\), Prop 4’s functional) and `predicted_skill = s`, not \(\mathcal R\). Any sentence that says “the operator” was confirmed is referring to a different functional than T1’s primary estimand.

Must-fix: T1 must pick one functional and prove statements about that functional. \(\eqref{eq:R}\) cannot inherit \(\eqref{eq:mae}\) or \(s_{\mathrm{heur}}\).

---

## 2. Prop 1 — population Loewner, not the implemented operator

### What is true

For a *known* PSD joint covariance on a *fixed* index set \(G\cup U\), and for \(O_1\subseteq O_2\subseteq U\), the residual-regression identity

\[
\Sigma_{G|O_2}=\Sigma_{G|O_1}-\Sigma_{GA|O_1}\Sigma_{AA|O_1}^{+}\Sigma_{AG|O_1}
\qquad(A=O_2\setminus O_1)
\]

(`theory.md` \(\eqref{eq:further}\)) implies Loewner \(\eqref{eq:loewner}\). Diagonals, trace, \(\overline{\sigma}\), and \(\mathcal R\) then move in the claimed directions. Gaussianity is not required for that matrix fact. The proof sketch is standard.

### Missing assumptions (not written as hypotheses)

1. **Known \(\Sigma\), fixed \(G\).** Fitting-period \(\hat\Sigma\) is not \(\Sigma\). Adding a nearly collinear donor can *increase* \(\mathrm{diag}\,\hat\Sigma_{G|O}\) (overfit). Sensor placement that moves a station from \(G\) into \(O\) changes \(G\); \(\eqref{eq:loewner}\) does not apply. T3(a) is that placement problem.
2. **Nested information only.** \(B\not\subseteq D\) and \(D\not\subseteq B\). Prop 1 does not order \(R(B)\) versus \(R(D)\). The freeze spectrum \(\tau=\log((V_B+\varepsilon)/(V_D+\varepsilon))\) is not a Prop 1 corollary.
3. **One second-order law.** \(\Sigma_{G|\mathrm{clim}}:=\Sigma_{GG}\) (`theory.md` §1) requires that climatology is a known deterministic function already subtracted and that the leftover field is weakly stationary. The empirical operator (`empirical_information_set_conditionals`) only subtracts column means. The heuristic subtracts a calendar-day *median* (`recoverability_budget.py:19-20`). Those are three different residuals. Seasonal heteroskedasticity (summer variance \(\neq\) winter variance) makes a single \(\Sigma\) the wrong object for a year-round gap.
4. **Range condition.** \(\eqref{eq:schur}\) uses \(\Sigma_{OO}^{+}\). The proof invokes \(\mathrm{range}(B^\top)\subseteq\mathrm{range}(C)\) for a PSD block. After `np.nan_to_num(joint, nan=0.0)` (`conditional_observability.py:403`) that inclusion need not hold; the filled zeros are not a covariance.
5. **Online vs offline.** The locked benchmark has `online_causal: future_boundary_forbidden`. Dropping the right endpoint is a smaller \(O\), so population residuals grow. Prop 3’s two-sided \(d/4\) story is then a different proposition. Not stated.

### Mathematical gap to code (this is the operator T1 is supposed to license)

`schur_complement` (`conditional_observability.py:54-76`) does **not** return \(\eqref{eq:schur}\). It returns

\[
\texttt{ridge\_psd}\!\left(\Sigma_{GG}-\Sigma_{GO}\,(\texttt{ridge\_psd}(\Sigma_{OO}))^{-1}\Sigma_{OG},\,r\right),\qquad r=10^{-8}.
\]

`theory.md` line 15 calls this “numerics, not part of the population identities.” That sentence is how T1 avoids proving anything about the object that will be computed. Eigenvalue flooring of \(\Sigma_{OO}\) and of the residual is **not** Loewner-monotone in \(O\): a larger, more collinear \(O\) can attract more ridge and a *larger* reported residual. `safe_logdet` floors the same way (`conditional_observability.py:42-49`), so Prop 2’s \(F\) as implemented is a different set function.

Must-fix: either prove a monotonicity statement for the ridged map that `schur_complement` actually returns, or write in the proposition that \(\eqref{eq:loewner}\) is **not** a theorem about `conditional_observability.py`. “Numerics” is not a hypothesis.

---

## 3. Prop 2 — \((1-1/e)\) is attached to the wrong objective and the wrong paper

### The stated claim

`theory.md` \(\eqref{eq:F}\):

\[
F(O)=\log\det\Sigma_{GG}-\log\det\Sigma_{G|O}
\]

for *fixed* \(G\). The proposition statement then says this \(F\) “is monotone and submodular (ridge-stabilize the determinants as in `safe_logdet` …). Therefore greedy selection of \(k\) sensors has the standard \((1-1/e)\) guarantee for maximizing \(F\) (Krause, Singh, and Guestrin, *JMLR* 2008).”

The proof is labeled “Proof of monotonicity only.” Submodularity and the greedy bound are cited, not proved. T1 required proofs.

### Error 1: Krause et al. 2008 is not a theorem about \(\eqref{eq:F}\)

Krause, Singh, and Guestrin (*JMLR* 9:235–284, 2008) maximize

\[
I(X_A;X_{V\setminus A}),
\]

mutual information between the *selected* coordinates and their complement in a ground set \(V\). That set function is submodular and **not monotone**. Their greedy analysis uses an extra restriction (they work in the regime \(|A|\le|V|/2\)) precisely because monotonicity fails when adding a sensor shrinks the unobserved set.

\(\eqref{eq:F}\) is a different function: \(G\) is held fixed and disjoint from \(O\), and \(F(O)=2I(Z_G;Z_O)\) only under joint Gaussianity. The combinatorial theorem that actually applies to a monotone submodular \(F\) under a cardinality constraint is Nemhauser, Wolsey, and Fisher (1978). Citing Krause 2008 for \(\eqref{eq:F}\) plus \((1-1/e)\) is a wrong-objective citation *inside T1*, before T3 even starts.

### Error 2: ridge-stabilized \(F\) is not submodular

The proposition statement parenthetically folds `safe_logdet` into the claim that \(F\) “is monotone and submodular.” Eigenvalue flooring is not a homomorphism of the Loewner lattice and does not preserve diminishing returns. After ridge, \(\eqref{eq:F}\) as coded is not the \(F\) in the citation.

### Error 3: T3(a) scores worst-case MAE, not \(F\)

Freeze `decision_endpoints.a_placement` (`design_freeze_v9.yaml:293-304`): method name `greedy_logdet_placement`; success is **worst-case MAE reduction** \(\ge 0.15\) versus random / degree / distance / correlation / Oh & Bartos QR. Sensor-policy held-out metrics are `expected_mae`, `worst_case_mae`, `heatwave_preservation`, `failure_regret`.

`theory.md` has a limitation paragraph that \(\eqref{eq:F}\) is not a guarantee for worst-case MAE, \(\mathcal R\), or \(s\). That paragraph is a disclaimer, not a repair. The **proposition statement** still sells “greedy \((1-1/e)\).” The freeze key is still `greedy_one_minus_1_over_e`. T3(a) will cite the statement. MAE, \(\mathcal R\), and \(s\) need not be submodular; they can rank placements differently from \(\log\det\). A \((1-1/e)\)-\(F\)-optimal design can be arbitrarily bad for worst-case MAE (one mid-gap coordinate with huge residual variance is almost invisible to \(\log\det\) of a long block).

### Error 4: T3(a) does not hold \(G\) fixed

Placement moves a station from the hidden set into the sensor set. Then the domain of \(\eqref{eq:F}\) changes: each added sensor *removes* coordinates from \(G\) and *adds* them to \(O\). That is Krause’s \(I(X_A;X_{V\setminus A})\) setting, where \((1-1/e)\) is not free, or it is a changing-domain problem that `theory.md` never states. Prop 2 as written (fixed \(G\)) does not license `greedy_logdet_placement`.

### Error 5: \(|G|\) is gap length

\(\log\det\Sigma_{G|O}\) scales with \(d=|G|\). The locked gap catalog is \(\{7,14,30,60,90,180,365\}\). \(F\) is not comparable across those cells. Greedy on pooled \(F\) prefers short, highly correlated blocks. Not mentioned.

### Error 6: estimated \(F\) and warm starts

Greedy on \(\hat F\) has no \((1-1/e)\) guarantee for population \(F\). The sensor-policy strategy `current_network` is not greedy-from-empty; Nemhauser is for construction from \(\emptyset\).

Must-fix: rewrite Prop 2 so that (i) \(F\) in \(\eqref{eq:F}\) is proved submodular *or* the \((1-1/e)\) sentence is deleted; (ii) Krause 2008 is not cited as a theorem about \(\eqref{eq:F}\); (iii) ridge is not inside the theorem; (iv) the proposition statement itself forbids applying \((1-1/e)\) to MAE / \(\mathcal R\) / \(s\) / safe-fill; (v) fixed-\(G\) donor selection is separated from changing-\(G\) placement. T3(a) may not cite Prop 2 as a near-optimality license.

---

## 4. Prop 3 — \(\varepsilon_\perp\) and \(\varepsilon_{d/4}\) are named remainders, not derived Schur remainders

### The special-case sentence is false of the operator

`theory.md` line 3 and Prop 3 claim that

\[
R^2_{\mathrm{avail}}=R^2_D+(1-R^2_D)\,\rho(d/4)^2
\qquad\eqref{eq:heur}
\]

“equals the operator’s explained-variance summary evaluated at a *single* representative lag \(d/4\).” That is a \(1\times 1\) nearest-boundary Schur step, not \(\eqref{eq:schur}\) on \(G=\{0,\ldots,d-1\}\). The note itself says it is “not a block average of residual variances.” An operator on a \(d\)-block is not a special case of a one-lag scalar. The honest statement is: \(\eqref{eq:heur}\) is a further diagonal-constant, single-lag *approximation* to one summary of the operator, after two extra reductions (nearest-boundary only; lag \(d/4\)).

### Frisch–Waugh is stated for the wrong object

`theory.md` \(\eqref{eq:R2}\):

\[
\mathcal R^2(O)=1-\frac{\overline{\mathrm{diag}}\,\Sigma_{G|O}}{\overline{\mathrm{diag}}\,\Sigma_{GG}}.
\]

The text then writes \(\mathcal R^2(D\cup B)=R^2_D+(1-R^2_D)\,r^2_{B|D}\) with \(r^2_{B|D}\) “the mean explained variance of donor-residualized hidden coordinates.” Mean of per-coordinate \(R^2_i=1-\Sigma_{ii|O}/\Sigma_{ii}\) equals the mean-diag ratio **only if** \(\Sigma_{GG,ii}\) is constant in \(i\). Under an exponential ACF the *conditional* variances are not constant in \(g\in G\). The identity holds if and only if one *defines*

\[
R^2_D:=1-\frac{\overline{\mathrm{diag}}\,\Sigma_{G|D}}{\overline{\mathrm{diag}}\,\Sigma_{GG}},\qquad
r^2_{B|D}:=1-\frac{\overline{\mathrm{diag}}\,\Sigma_{G|D\cup B}}{\overline{\mathrm{diag}}\,\Sigma_{G|D}}.
\]

That is not the \(R^2_D\) in baseline #4. `budget_decomposition` (`recoverability_budget.py:24-32,73`) is an **in-sample** contemporaneous regression of the whole anomaly series on simultaneous donors — one scalar for all days, no year-block CV, not \(1-\overline{\mathrm{diag}}\,\Sigma_{G|D}/\overline{\mathrm{diag}}\,\Sigma_{GG}\). The freeze forbids `in_sample_donor_r2_without_cv` as primary (`design_freeze_v9.yaml:87-89`) and requires `year_block_cross_validated_r2`. Prop 3 equates two different \(R^2_D\) symbols.

### \(\eqref{eq:bias}\) is a tautology; \(\varepsilon_\perp\) does not vanish under (i)–(ii)

They set old \(=R^2_{\mathrm{avail}}\), new \(=\mathcal R^2(D\cup B)\), and

\begin{align}
\varepsilon_\perp&=(1-R^2_D)\Bigl(d^{-1}\textstyle\sum_g\rho(\ell_g)^2-r^2_{B|D}\Bigr),
\tag{eq:eperp}\\
\varepsilon_{d/4}&=(1-R^2_D)\Bigl(\rho(d/4)^2-d^{-1}\textstyle\sum_g\rho(\ell_g)^2\Bigr),
\tag{eq:ed4}
\end{align}

with \(\ell_g=\min(g+1,d-g)\). Then old \(-\) new \(=\varepsilon_\perp+\varepsilon_{d/4}\) is algebra, not a derivation from \(\eqref{eq:further}\). No magnitude, sign, or bound is proved. No table computes either term on any river.

They then claim the inner product in \(\eqref{eq:eperp}\) “vanishes under (i) when \(\rho\) is the residual ACF.” That requires \(r^2_{B|D}=d^{-1}\sum_g\rho(\ell_g)^2\). \(\rho(\ell_g)^2\) is the \(R^2\) of the **nearest single** boundary. The operator’s \(B\) is **two-sided** (`gap_nodes`: left at time \(-1\), right at time \(d\)). For a stationary AR(1),

\[
\frac{\mathrm{Var}(Z_g\mid Z_{-1},Z_d)}{\sigma^2}
=\frac{(1-\varphi^{2(g+1)})(1-\varphi^{2(d-g)})}{1-\varphi^{2(d+1)}}
\;<\;
1-\varphi^{2\ell_g}
=\frac{\mathrm{Var}(Z_g\mid\text{nearest})}{\sigma^2}.
\]

So even under (i) donor \(\perp\) boundary and (ii) \(\rho(\ell)=\varphi^{|\ell|}\),

\[
r^2_{B|D} \;>\; d^{-1}\sum_g\rho(\ell_g)^2
\qquad\Rightarrow\qquad
\varepsilon_\perp<0.
\]

The missing term is a two-sided / nearest-boundary remainder \(\varepsilon_{2\mathrm{s}}\). It has been dumped into \(\varepsilon_\perp\). Assumption (i) does not make \(\varepsilon_\perp=0\). The bias expansion advertised in T1 and in `prop3_bias_terms` is not a derived Schur expansion.

`jensen_acf_gap` (`heuristic_degeneration.py:84-114`) only compares \(d^{-1}\sum\rho(\ell_g)^2\), \(\rho(\overline L)^2\), and \(\rho(d/4)^2\) for a scalar AR(1). That can support \(\eqref{eq:ed4}\) as a *definition*. It does not derive \(\eqref{eq:eperp}\), and it does not identify \(\eqref{eq:heur}\) with \(\eqref{eq:schur}\).

### \(d/4\) is the continuous mean, not the discrete one, and not what the code evaluates

For \(x\sim\mathrm{Unif}[0,d]\), \(\mathbb E[\min(x,d-x)]=d/4\). For the discrete grid in `nearest_boundary_distances`, \(\overline L=d/4+1/2\) when \(d\) is even (`heuristic_degeneration.py` field `mean_nearest_minus_d_over_4`). The note says this. Baseline #4 does not use \(\varphi^{d/4}\): `_rho_at_distance` (`recoverability_budget.py:42-53,81-83`) linearly interpolates the **empirical** anomaly ACF at lag \(d/4\). Assumption (ii) is not the implemented heuristic. Stream-temperature anomalies are not AR(1) (seasonal leftover, synoptic 3–7 day band, snowmelt). \(\varepsilon_{d/4}\) as written is a lag-substitution error *inside an AR(1) that the baseline does not use*.

### Degeneration is a label identity, not a recoverability theorem

\(M=(1-R^2_D)\rho^2\le 1-R^2_D\le R^2_D\) whenever \(R^2_D\ge 1/2\) (`heuristic_degeneration.py:36-47`, `forced_donor_dominated`). Correct, and correctly called a design defect. It is not a property of \(\eqref{eq:schur}\) and it is not confirmed by eight stations: it is true in the empty product. See §6.

### Orthogonality is empty on the intended domain

Donors and the target share synoptic weather, the same residual seasonality, and routing. Assumption (i) is not a river. Calling \(\eqref{eq:heur}\) “the special case” of the operator on that domain is a special case with no elements.

Must-fix: (i) drop “special case of the operator”; write two explicit approximation steps; (ii) define \(R^2_D\) and \(r^2_{B|D}\) as the same mean-diag functional, and do not identify them with `budget_decomposition`’s in-sample \(R^2\); (iii) split \(\varepsilon_{2\mathrm{s}}\) out of \(\varepsilon_\perp\) and delete the sentence that \(\varepsilon_\perp\) vanishes under (i)–(ii); (iv) derive or delete `prop3_bias_terms`; (v) state that \(\eqref{eq:heur}\) is offline two-sided only; (vi) keep degeneration as a label identity, not a numbered recoverability proposition.

---

## 5. Prop 4 — \(\sqrt{2/\pi}\) is not a bound on the paper’s MAE

### What is true

If \(X\sim\mathcal N(0,\sigma^2)\), then \(\mathbb E[|X|]=\sigma\sqrt{2/\pi}\). If \(Z_G\mid Z_O\) is jointly Gaussian, the coordinatewise MAE risk of any estimator is at least \(c\,\sigma_i(O)\) with \(c=\sqrt{2/\pi}\), and the conditional mean attains it (`theory.md` \(\eqref{eq:condmae}\)–\(\eqref{eq:mae}\)). Off-diagonals do not enter coordinatewise MAE. That is a standard Gaussian calculation. It is **not** “second-order” without Gaussianity: a covariance \(\Sigma\) does not determine \(\mathbb E[|Z_i-\mathrm{median}_i|]\).

### Error 1: “second-order model” in the proposition lead-in

T1 and the freeze say “second-order Gaussian.” The proof body says “zero-mean jointly Gaussian.” The closing sentence of the proof says the bound “cannot be improved by changing model class.” The non-Gaussian paragraph then says a nonlinear estimator may beat “the second-order number.” Those four sentences do not name the same hypothesis. Second-order structure is Prop 1. MAE equality at \(c\,\overline{\sigma}(\Sigma)\) is Gaussian. A field with the same \(\Sigma\) and a different law can have coordinatewise MAE arbitrarily close to 0 (mass at 0 plus rare spikes with variance \(\sigma^2\)) or equal to \(\sigma\) (two-point \(\pm\sigma\)). Laplace already gives \(\mathbb E[|X|]=\sigma/\sqrt{2}<c\sigma\). Stream-temperature residuals are bounded, seasonal, and right-skewed in heatwaves. \(\eqref{eq:mae}\) is not a bound on `loss: mae_degC`.

### Error 2: the paper’s estimators are not the Gaussian conditional mean

Locked recovery models include XGBoost, air2stream, PGDL / Graph WaveNet, SAITS, CSDI / GRIN (`design_freeze_v9.yaml:381-389`). Their training loss is not the Gaussian MAE risk of a known \(\Sigma\). Prop 4 does not lower-bound those MAEs. The freeze fallback `quantile_width_keep_monotonicity_only` already admits this. Titling the proposition `prop4_estimator_independent_mae_bound` is the overclaim.

### Error 3: \(\Sigma\) is estimated; the bound is written for known \(\Sigma\)

The note says estimation error “is outside the proposition.” Then \(\eqref{eq:mae}\) is not a bound on the MAE of any procedure that uses \(\hat\Sigma\) from a fitting window. The implemented predictor is that procedure. `expected_gaussian_mae` (`conditional_observability.py:77-83`) multiplies \(\overline{\sigma}(\hat\Sigma)\) by `GAUSSIAN_MAE_FACTOR` for *every* covariance it is given, including the empirical path. That is Prop 4 applied to non-Gaussian, estimated, mean-centered (not seasonally residualized) series.

### Error 4: the bound is not a statement about \(\mathcal R\) or \(s\)

\(\sqrt{2/\pi}\) cancels in \(s(O)\) (`theory.md` lines 27–34). Prop 4 does no work for the skill ratio the code reports. It only affects absolute `expected_mae_*` / `predicted_conditional_risk`. The primary estimand \(\eqref{eq:R}\) uses \(\sqrt{\overline{\mathrm{diag}}}\), not \(\overline{\sigma}\). Prop 4 does not bound \(\mathcal R\).

### Error 5: “Bonus” is a T1 shrink hatch

Master plan T1.4 is marked **Bonus**. The freeze still lists Prop 4 as a theory proposition. The failure branch is: if PIT/QQ fails, drop Prop 4 and keep Prop 1. That is how T1 becomes three propositions after the Gaussian model fails on the data it was written for. If Prop 4 is optional, delete it from the required list. If it is required, it cannot be the MAE law of XGBoost on rivers.

Must-fix: restate Prop 4 as “if \(Z_G\mid Z_O\) is exactly \(\mathcal N(\mu(O),\Sigma_{G|O})\) with known \(\Sigma\), coordinatewise Bayes MAE equals \(c\,\overline{\sigma}(\Sigma_{G|O})\).” Forbid applying \(\eqref{eq:mae}\) to achieved `mae_degC`, to \(\mathcal R\), or to \(\hat\Sigma\). Do not call it estimator-independent on the locked model roster. Do not mark it Bonus while leaving it in `theory_propositions`.

---

## 6. Eight-station and six-river numbers are not theory confirmation

`theory.md` §4 says the region \(R^2_D\ge 1/2\) is an identity of \(\eqref{eq:heur}\), not an empirical finding from the eight case-study stations; it says \(\mathcal R\) and \(s\) have not been calibrated to achieved skill on any real river; it says greedy \(F\)-placement is not claimed to reduce worst-case MAE. Those sentences are necessary and not sufficient.

What the note must also refuse, by name:

| Number | Where it lives | What it is | What it is not |
| --- | --- | --- | --- |
| Eight-station 30-day \(D\), \(M\), labels | `results/revision/recoverability_type_classification_uncertainty.csv`; BL-015 table | Audit of the *label* identity, and two unforced empirical comparisons (B1/S2, P3/02334430) | Not a measurement of \(\varepsilon_\perp\) or \(\varepsilon_{d/4}\); not a special-case check of \(\eqref{eq:schur}\); not Prop 3. Four of eight labels are forced by \(R^2_D\ge 0.5\) in empty arithmetic. |
| 6-river LORO Spearman \(\approx 0.77\), CI \(\approx(-0.01,1)\) | `paper/next/results.md`; charter T2 | Failed pilot of a *prediction* task; interval includes 0; failed the 0.40 floor | Not Prop 1, not Prop 4, not confirmation that \(\hat{\mathcal R}\) equals achieved skill. The scorer used \(s\) and \(c\,\overline{\sigma}(\hat\Sigma)\), not \(\eqref{eq:R}\). `public_river_check.json` 0.821 / 0.094 includes Clearwater and is a different failed number. |
| 10-river sensor-policy 2/10 at 15% | `paper/next/results.md` | Failed T3(a) peek | Not a \((1-1/e)\) demonstration. |
| `jensen_acf_gap`, `degeneration_bound`, `donor_count_inflation` | `heuristic_degeneration.py` | Formula identities and one Monte Carlo | Not proofs on a river; `donor_count_inflation` is not a theorem. |
| `results/framework/baseline_nested_r2.csv` | framework | Synthetic nested sequence | Not a real-data \(\Delta R^2\) after donor \(R^2\) (BL-015 already says this). |

T1 is proofs. A Spearman on six rivers cannot confirm a Loewner identity, a combinatorial guarantee, or a Gaussian integral. Using those numbers as “the theory works” is the confirmatory smuggle T1 exists to prevent.

The scoring path already does the smuggle in code: `real_river_checks.py` treats Prop 4’s functional as `predicted_conditional_risk` on USGS series. `theory.md` §4 must name that path and forbid reading it as a Prop 4 confirmation.

---

## 7. Other missing hypotheses the note treats as scenery

- **VAR(1).** `information_set_conditionals` / `stationary_covariance` require a strictly stable VAR(1) (`spectral_radius < 1-10^{-8}`). Stream temperature, even as anomalies, is not that process. `theory.md` never mentions VAR(1). The “exact” joints in code are exact for a model the note does not assume.
- **\(M,H,O\) (meteorology, hydraulics, operations).** Freeze information sources include them. Code `INFORMATION_SETS` are `none, B, D, B_union_D` only. Props 1–2 on \(U\) that the operator cannot see are unused symbols.
- **Shapley and synthetic bias tables.** Phase 1 (`v9_redesign_master_plan.md:82`) also required these. They are absent. Not a substitute for the equation errors above; they are an incomplete Phase 1 gate.
- **PIT/QQ.** Named only as a failure branch. No proposition states what is being tested (which residual, which information set, which gap length).

---

## Must-fix (equation-level)

1. **Close the three-map gap.** State T1 about one functional. If the freeze primary is \(\eqref{eq:R}\), delete any implication that Props 2–4 are theorems about \(s\) (`theory.md` \(\eqref{eq:skill}\)), about \(c\,\overline{\sigma}\) (`conditional_observability.py:77-83,117-118`), or about \(1-\sqrt{1-R^2_{\mathrm{avail}}}\) (`recoverability_budget.py:99`). If the scorer keeps using \(s\) and `expected_mae_conditional`, the freeze primary is not what T1 proved.

2. **Prop 1: name the implemented map.** Add hypotheses: known PSD \(\Sigma\), fixed \(G\), \(O_1\subseteq O_2\), climatology already subtracted and not re-estimated. Write that `schur_complement` returns \(\texttt{ridge\_psd}(\Sigma_{GG}-\Sigma_{GO}(\texttt{ridge\_psd}\,\Sigma_{OO})^{-1}\Sigma_{OG})\) (`conditional_observability.py:54-76`), not \(\eqref{eq:schur}\), and that \(\eqref{eq:loewner}\) is not proved for that map, nor for \(\hat\Sigma\) after `nan_to_num(..., nan=0.0)` (line 403). Do not apply Prop 1 to T3(a) placement that changes \(G\).

3. **Prop 2: take \((1-1/e)\) off the wrong objective.** Delete “therefore greedy \((1-1/e)\)” from the proposition statement unless \(F\) in \(\eqref{eq:F}\) is *proved* submodular and the guarantee is restricted to maximizing that \(F\) under a cardinality constraint from \(\emptyset\). Replace the Krause et al. 2008 citation as a theorem about \(\eqref{eq:F}\); that paper is about \(I(X_A;X_{V\setminus A})\), which is not monotone. Do not put `safe_logdet` ridge inside the submodularity claim. Write in the statement, not a footnote, that the guarantee does **not** apply to worst-case MAE, \(\mathcal R\), \(s\), or safe-fill, and does **not** apply to `greedy_logdet_placement` (changing \(G\)). Change `prop2_logdet_submodularity: greedy_one_minus_1_over_e` so T3(a) cannot cite it as MAE near-optimality.

4. **Prop 3: derive or delete the bias terms.** Stop calling \(\eqref{eq:heur}\) a special case of \(\eqref{eq:schur}\). Define \(R^2_D\) and \(r^2_{B|D}\) as the same mean-diag functional; do not identify them with in-sample `_donor_r2`. Split the two-sided / nearest-boundary remainder \(\varepsilon_{2\mathrm{s}}\) out of \(\eqref{eq:eperp}\). Delete the claim that \(\varepsilon_\perp\) vanishes under (i)–(ii). \(\eqref{eq:bias}\) as a tautology of named remainders does not satisfy T1’s “write bias \(\varepsilon_\perp+\varepsilon_{d/4}\).” Either expand \(\mathcal R^2(D\cup B)-R^2_{\mathrm{avail}}\) from \(\eqref{eq:further}\) with explicit remainders, or drop `prop3_bias_terms`. State that baseline #4 evaluates an interpolated *empirical* ACF at \(d/4\), not \(\varphi^{d/4}\), and is offline-only.

5. **Prop 4: do not apply \(\eqref{eq:mae}\) to non-Gaussian MAE.** Restate: known Gaussian conditional law, coordinatewise Bayes MAE \(=c\,\overline{\sigma}(\Sigma_{G|O})\). Forbid reading \(\eqref{eq:mae}\) as a lower bound on locked-roster `mae_degC`, on \(\mathcal R\), or on any functional of \(\hat\Sigma\). Drop “estimator-independent” and “cannot be improved by changing model class” for the paper’s models. Resolve Bonus vs required: if PIT/QQ can kill Prop 4, it is not a T1 must.

6. **Name the numbers that are not confirmation.** In §4, forbid by name: the eight-station 30-day table as confirmation of \(\eqref{eq:eperp}\)–\(\eqref{eq:ed4}\) or of \(\eqref{eq:schur}\); the 6-river Spearman \(\approx 0.77\) / CI lower \(\approx-0.01\) as confirmation of Props 1–4; `public_river_check.json` 0.821; the 2/10 sensor-policy peek as a \((1-1/e)\) result; E0 / `jensen_acf_gap` / `degeneration_bound` as river theorems. BL-015 remains a label-identity audit. T1 is proofs.

Until 1–6 are in `paper/theory.md` (and the freeze keys that quote it), Phase 1 theory is not a gate pass.

---

## Residuals (not must-fix)

- Notation collision in the Prop 1 proof: \(A\) is both \(O_2\setminus O_1\) and the top-left block of \(M\).
- \(\mathbb E[c\,\sigma_i(O)]\) in \(\eqref{eq:condmae}\) is just \(c\,\sigma_i\) for a fixed index set and a Gaussian (conditional variance does not depend on the realized \(Z_O\)).
- Phase 1 Shapley values and synthetic bias tables are still missing; they do not repair the equations above.
- `INFORMATION_SETS` omit \(M,H\); unused freeze symbols.
- VAR(1) joints in code are an unstated model.
- Parenthetical “Audience: WRR methods. … Submodularity … is cited, not re-proved” is an admission that T1.2 has no proof.
