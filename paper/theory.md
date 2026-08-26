# Conditional observability of stream-temperature gaps

Status: Phase 1 theory note for `configs/design_freeze_v9.yaml`. Not a result, not a title license, and not a real-river confirmation. Sealed temperatures are not used. The operator is the Schur complement already implemented in `src/stream_recoverability/analysis/conditional_observability.py`. The additive \(d/4\) formula in manuscript §2.4 is a special case and a preregistered baseline, not this operator.

Audience: WRR methods. Propositions 1 and the algebraic part of 3 are standard linear algebra. Gaussian identification, the exponential ACF, and the choice of summaries are modeling. Submodularity of information gain is cited, not re-proved.

## 1. Setup

Let \(Z\) be a zero-mean second-order random vector on a finite index set \(G\cup U\), with positive semidefinite covariance \(\Sigma\). Coordinates in \(G\) are the hidden gap (target station-days after a fitting-period climatology has been subtracted). Coordinates in \(U\) are candidate observations: local left and right boundaries \(B\), synchronous donor temperatures \(D\), and any additional channels (meteorology, hydraulics, operations) that enter the same joint covariance. An observation set is \(O\subseteq U\). Climatology is a fitted deterministic baseline, not an element of \(U\); write \(\Sigma_{G|\mathrm{clim}}:=\Sigma_{GG}\).

The population residual covariance is the Schur complement
\begin{equation}
\Sigma_{G|O}=\Sigma_{GG}-\Sigma_{GO}\Sigma_{OO}^{+}\Sigma_{OG},
\label{eq:schur}
\end{equation}
with the Moore--Penrose inverse if \(\Sigma_{OO}\) is singular. This is the residual-regression identity: \(\Sigma_{G|O}=\mathrm{Cov}(Z_G-P_O Z_G)\), where \(P_O\) is \(L^2\) linear projection onto \(\mathrm{span}\{Z_o:o\in O\}\). Code applies a ridge PSD projection before solving; that is numerics, not part of the population identities below.

## 2. Primary estimand and the code skill ratio

The freeze primary estimand is
\begin{equation}
\mathcal R(O)=1-\sqrt{\frac{\overline{\mathrm{diag}}\,\Sigma_{G|O}}{\overline{\mathrm{diag}}\,\Sigma_{G|\mathrm{clim}}}}.
\label{eq:R}
\end{equation}
It is a continuous spectrum, not a hard type label. Achieved skill on held-out gaps remains a loss ratio versus climatology and is not assumed equal to \(\mathcal R\).

The function `predicted_skill` in the operator code is the Gaussian MAE ratio
\begin{equation}
s(O)=1-\frac{\overline{\sigma}(\Sigma_{G|O})}{\overline{\sigma}(\Sigma_{G|\mathrm{clim}})},
\qquad
\overline{\sigma}(\Sigma):=\mathrm{mean}_i\sqrt{\Sigma_{ii}}.
\label{eq:skill}
\end{equation}
The factor \(\sqrt{2/\pi}\) in `expected_gaussian_mae` cancels in the ratio, so \(s\) is a ratio of mean conditional standard deviations, not the square-root mean-variance map \eqref{eq:R}. The two agree when every hidden coordinate has the same residual variance; otherwise Jensen's inequality for \(x\mapsto x^2\) separates them. Manuscript §2.4's conversion \(1-\sqrt{1-R^2_{\mathrm{avail}}}\) is a third, equal-variance location--scale map. It is not a theorem and is not the primary estimand.

## 3. Four propositions

**Proposition 1 (monotonicity).** Let \(\Sigma\) be a PSD covariance on coordinates \(G\cup U\). For observation sets \(O_1\subseteq O_2\subseteq U\),
\begin{equation}
\Sigma_{G|O_2}\preceq\Sigma_{G|O_1}
\label{eq:loewner}
\end{equation}
in the Loewner order (the difference is PSD). Therefore mean diagonal, trace, and expected Gaussian MAE of the residual are nonincreasing in \(O\), and \(\mathcal R(O)\) in \eqref{eq:R} is nondecreasing.

*Standard linear algebra. No Gaussianity.*

*Proof.* Write \(O_2=O_1\cup A\). The joint residual covariance of \((Z_G,Z_A)\) given \(O_1\) is the Schur complement of a PSD block and is therefore PSD: if \(M=[A,B;B^\top,C]\succeq 0\), then for any \(x\) the quadratic form of \(M\) at \((x,-C^{+}B^\top x)\) equals \(x^\top(A-BC^{+}B^\top)x\ge 0\), using \(\mathrm{range}(B^\top)\subseteq\mathrm{range}(C)\) for PSD \(M\). The \(G\)-block of that residual and a further Schur step give the residual-regression identity
\begin{equation}
\Sigma_{G|O_2}=\Sigma_{G|O_1}-\Sigma_{GA|O_1}\Sigma_{AA|O_1}^{+}\Sigma_{AG|O_1}.
\label{eq:further}
\end{equation}
The subtracted term is a Gram form \(B C^{+} B^\top\succeq 0\), which is \eqref{eq:loewner}. Equivalently, \(P_{O_2}\) projects onto a larger linear space than \(P_{O_1}\), so \(\mathrm{Var}(a^\top(Z_G-P_{O_2}Z_G))\le\mathrm{Var}(a^\top(Z_G-P_{O_1}Z_G))\) for every \(a\).

Taking \(a=e_i\) shows that each diagonal of \(\Sigma_{G|O}\) is nonincreasing in \(O\), hence so are the mean diagonal and the trace. The map \(v\mapsto\sqrt{v}\) is increasing on \([0,\infty)\), so \(\overline{\sigma}(\Sigma_{G|O})\) in \eqref{eq:skill} is nonincreasing, and the expected-Gaussian-MAE functional \(\sqrt{2/\pi}\,\overline{\sigma}(\Sigma_{G|O})\) is nonincreasing. Combined with \eqref{eq:R}, \(\mathcal R\) is nondecreasing. The MAE *interpretation* of that functional uses Proposition 4; the inequality on the functional does not. \(\square\)

**Proposition 2 (log-det submodularity).** For fixed hidden set \(G\), the set function
\begin{equation}
F(O)=\log\det\Sigma_{GG}-\log\det\Sigma_{G|O}
\label{eq:F}
\end{equation}
on finite observation coordinates is monotone and submodular (ridge-stabilize the determinants as in `safe_logdet` when a block is only PSD). Therefore greedy selection of \(k\) sensors has the standard \((1-1/e)\) guarantee for maximizing \(F\) (Krause, Singh, and Guestrin, *JMLR* 2008). This note does not prove the general combinatorial theorem.

*Monotonicity of \(\log\det\) on PD matrices is linear algebra. Identifying \(F\) with mutual information, and submodularity, are Gaussian-process / information-gain modeling plus the cited theorem. Using \(F\) as a placement objective is a modeling choice.*

*Proof of monotonicity only.* If the residual blocks are made PD, Loewner \eqref{eq:loewner} and operator monotonicity of \(\log\det\) on the positive-definite cone give \(F(O_2)\ge F(O_1)\) whenever \(O_1\subseteq O_2\). Under joint Gaussianity, \eqref{eq:F} equals \(2\,I(Z_G;Z_O)\). Krause, Singh, and Guestrin (2008) prove that this information-gain set function is submodular on a finite ground set of sensor coordinates and that the standard greedy algorithm for monotone submodular maximization therefore returns a \(k\)-set whose \(F\)-value is at least \(1-1/e\) times that of an \(F\)-optimal \(k\)-set.

*Limitation.* The guarantee is for \(F\) in \eqref{eq:F}. It is not automatically a guarantee for worst-case MAE, for \(\mathcal R\) in \eqref{eq:R}, or for \(s\) in \eqref{eq:skill}. Those set functions need not be submodular, and skill versus climatology can rank placements differently from log-det reduction.

**Proposition 3 (heuristic as special case).** Let \(R^2_D\) be the population explained variance of a target anomaly from simultaneous donors, and let \(\rho(\ell)=\varphi^{|\ell|}\) with \(|\varphi|<1\). Under (i) donor anomalies orthogonal to local boundary residuals after a joint second-order model and (ii) that scalar exponential ACF on the target anomaly, the additive heuristic
\begin{equation}
R^2_{\mathrm{avail}}=R^2_D+(1-R^2_D)\,\rho(d/4)^2
\label{eq:heur}
\end{equation}
equals the operator's explained-variance summary evaluated at a *single* representative lag \(d/4\), not the block-average of residual variances. Write
\begin{equation}
(\mathrm{old})-(\mathrm{new})=\varepsilon_\perp+\varepsilon_{d/4}.
\label{eq:bias}
\end{equation}
If \(R^2_D\ge 1/2\), the hard label is forced donor-dominated for any \(\rho^2\le 1\).

*Sequential \(R^2\) is linear algebra. Orthogonality, the exponential ACF, the lag \(d/4\), and hard labels are modeling (and, for labels, a design defect).*

*Proof.* The operator's explained-variance summary on a coordinate set is
\begin{equation}
\mathcal R^2(O):=1-\frac{\overline{\mathrm{diag}}\,\Sigma_{G|O}}{\overline{\mathrm{diag}}\,\Sigma_{GG}},
\label{eq:R2}
\end{equation}
which is not \(\mathcal R\) in \eqref{eq:R}. Frisch--Waugh residual regression gives the exact split \(\mathcal R^2(D\cup B)=R^2_D+(1-R^2_D)\,r^2_{B|D}\), where \(r^2_{B|D}\) is the mean explained variance of donor-residualized hidden coordinates by donor-residualized boundaries.

Assumption (i) sets the donor--boundary inner product to zero after the joint second-order fit, so the residual process \(\tilde Z=Z-P_D Z\) is uncorrelated with \(D\) and still carries the local boundary. Assumption (ii) gives \(\mathrm{Corr}(\tilde Z_g,\tilde Z_{g\pm\ell})=\rho(\ell)=\varphi^{|\ell|}\). Evaluating \eqref{eq:R2} at a single representative lag \(d/4\) (not necessarily attained by a discrete day) gives the one-coordinate nearest-boundary Schur step \(R^2_D+(1-R^2_D)\rho(d/4)^2\), which is \eqref{eq:heur}. That is not a block average of residual variances.

On the full block \(G=\{0,\ldots,d-1\}\), \eqref{eq:R2} uses \(\overline{\mathrm{diag}}\,\Sigma_{G|O}\), the mean of residual *variances*. Under (i)--(ii) and the nearest-boundary reduction used by `jensen_acf_gap`, that block summary is \(R^2_{\mathrm{seq}}:=R^2_D+(1-R^2_D)\,d^{-1}\sum_{g\in G}\rho(\ell_g)^2\) with \(\ell_g=\min(g+1,d-g)\) as in `nearest_boundary_distances`. Set old \(=R^2_{\mathrm{avail}}\) and new \(=\mathcal R^2(D\cup B)\). Then \eqref{eq:bias} holds with the omitted cross term
\begin{equation}
\varepsilon_\perp=R^2_{\mathrm{seq}}-\mathcal R^2(D\cup B)=(1-R^2_D)\Bigl(d^{-1}\sum_g\rho(\ell_g)^2-r^2_{B|D}\Bigr)
\label{eq:eperp}
\end{equation}
and the single-lag substitution
\begin{equation}
\varepsilon_{d/4}=(1-R^2_D)\Bigl(\rho(d/4)^2-d^{-1}\sum_g\rho(\ell_g)^2\Bigr).
\label{eq:ed4}
\end{equation}
The inner product in \eqref{eq:eperp} vanishes under (i) when \(\rho\) is the residual ACF; otherwise donors already absorb part of the boundary-correlated variance and \(C_{GB|D}\ne C_{GB}\). The lag error \eqref{eq:ed4} splits as \(\rho(d/4)^2-\rho(\overline L)^2\) plus \(\rho(\overline L)^2-\overline{\rho(L)^2}\). For a continuous two-sided block, a uniform interior point has mean nearest-boundary distance \(d/4\); the discrete mean `mean_nearest_boundary_distance` is larger (\(\overline L=d/4+1/2\) when \(d\) is even). The map \(\ell\mapsto\rho(\ell)^2=|\varphi|^{2\ell}\) is convex, so \(\overline{\rho(L)^2}\ge\rho(\overline L)^2\) (Jensen), which is the `jensen_gap` field of `jensen_acf_gap`; `heuristic_gap` compares the same block average to \(\rho(d/4)^2\).

*Degeneration region.* The hard rule in manuscript §2.4 labels a station donor-dominated when the donor component is at least the memory component \(M=(1-R^2_D)\rho^2\). If \(R^2_D\ge 1/2\) and \(\rho^2\le 1\), then \(M\le 1-R^2_D\le R^2_D\). The label is therefore forced donor-dominated for every admissible \(\rho\). This is the identity `forced_donor_dominated` in `heuristic_degeneration.py`, not an empirical discovery from the eight case-study stations. \(\square\)

**Proposition 4 (estimator-independent Gaussian MAE bound).** If hidden residuals are zero-mean jointly Gaussian, then for any estimator the expected coordinatewise MAE is at least \(\sqrt{2/\pi}\) times the mean conditional standard deviation. Equality holds for the conditional mean. Therefore recoverability in this second-order model is an information bound, not a model-class score. The constant is `GAUSSIAN_MAE_FACTOR` already in code,
\begin{equation}
c=\sqrt{2/\pi}=\texttt{GAUSSIAN\_MAE\_FACTOR}\approx 0.7978845608028654.
\label{eq:c}
\end{equation}

*The bound for a univariate centered Gaussian is a standard Gaussian integral. Applying it to every estimator is decision theory under the Gaussian model. Treating \(\Sigma\) as known is modeling; estimation error in \(\Sigma\) is outside the proposition.*

*Proof.* For \(X\sim\mathcal N(0,\sigma^2)\), \(\mathbb E[|X|]=\sigma\sqrt{2/\pi}=c\sigma\) with \(c\) from \eqref{eq:c}. The conditional law of coordinate \(i\) given \(Z_O\) is \(\mathcal N(\mu_i(O),\sigma_i(O)^2)\) with \(\sigma_i(O)=\sqrt{(\Sigma_{G|O})_{ii}}\) from \eqref{eq:schur}. For any measurable \(f_i(Z_O)\),
\begin{equation}
\mathbb E[|Z_{G,i}-f_i|]=\mathbb E\bigl[\mathbb E[|Z_{G,i}-f_i|\mid Z_O]\bigr]\ge\mathbb E[c\,\sigma_i(O)],
\label{eq:condmae}
\end{equation}
because the inner MAE risk is minimized by the conditional median, which equals the conditional mean, with risk \(c\,\sigma_i(O)\). Averaging \eqref{eq:condmae} over \(i\in G\) yields
\begin{equation}
\mathbb E\bigl[\overline{|Z_G-f|}\bigr]\ge c\,\overline{\sigma}(\Sigma_{G|O}).
\label{eq:mae}
\end{equation}
Equality holds when \(f\) is the conditional mean. Off-diagonal dependence does not enter \eqref{eq:mae}: coordinatewise MAE uses only the marginal conditional variances. Under joint Gaussianity that mean is the linear projection whose residual covariance is \eqref{eq:schur}, so the bound is attained inside the second-order model and cannot be improved by changing model class. \(\square\)

*When the Gaussian assumption fails.* Keep Proposition 1 (Loewner uses only second-order structure). Drop Proposition 4 and do not treat \eqref{eq:mae} or \(s(O)\) in \eqref{eq:skill} as a proved MAE law. The freeze fallback is quantile-width of the residual predictive distribution. A nonlinear estimator may then beat the second-order number; that is a PIT/QQ failure of the model, not a license to keep the Gaussian MAE claim.

## 4. Non-claims

*Limitations of these proofs (parent merge of the Phase 1 red team).* Equation \eqref{eq:schur} is the population map. Code applies `ridge_psd` before the solve; monotonicity of that ridged map is a numerical property checked in tests, not a theorem here. Submodularity is cited for Gaussian information gain \(I(Z_G;Z_O)\); \(F\) equals that mutual information (up to the conventional factor of 2 in nats) only under joint Gaussianity and without ridge. The \((1-1/e)\) guarantee is only for maximizing \(F\), never for T3(a) worst-case MAE. In \eqref{eq:eperp}, \(\varepsilon_\perp\) also absorbs the two-sided-block versus nearest-boundary remainder when that reduction is inexact; it is not a pure inner-product term. Proposition 4 is a Gaussian integral. It is not a bound on XGBoost, SAITS, or CSDI `mae_degC`, and it is not a calibration of \(\mathcal R\) to achieved skill. The eight-station table and the six-river pilot are not theory confirmation.

These propositions do not attribute recoverability to reservoirs or operations, and they do not use operations data. They do not claim that the eight-station donor/memory labels in the historical case study were empirical findings: the region \(R^2_D\ge 1/2\) is an identity of \eqref{eq:heur}. They do not open sealed temperatures and do not report sealed or confirmatory skill. They do not claim that \(\mathcal R\) or \(s\) has been calibrated to achieved skill on any real river, that greedy \(F\)-placement reduces worst-case MAE, or that the additive \(d/4\) formula implements \eqref{eq:schur}. Formal evidence and a headline license remain false until the v9 confirmatory protocol says otherwise.

## Reference

Krause, A., A. Singh, and C. Guestrin (2008), Near-optimal sensor placements in Gaussian processes: Theory, efficient algorithms and empirical studies, *Journal of Machine Learning Research*, 9, 235--284.
