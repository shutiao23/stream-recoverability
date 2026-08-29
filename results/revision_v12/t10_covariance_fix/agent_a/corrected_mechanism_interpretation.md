# Corrected mechanism interpretation (estimand-correct)

## What the conditional covariance is

The analytic operator returns the conditional covariance of the hidden gap
block, \(\Sigma_{G\mid O}=\Sigma_{GG}-\Sigma_{GO}\Sigma_{OO}^{+}\Sigma_{OG}\),
estimated by fitting a Gaussian VAR(1) to the fitting-period anomaly record
of each network and propagating the covariance across the gap. Under the
assumed Gaussian model the conditional distribution of the gap block is
Gaussian with this covariance, and the optimal (minimum expected squared
error) predictor of each hidden day has conditional standard deviation
\(\sigma_i=\sqrt{[\Sigma_{G\mid O}]_{ii}}\).

Two scale conventions must be kept separate. The Gaussian expected mean
absolute error of one hidden day is \(E[|e_i|]=\sqrt{2/\pi}\,\sigma_i\),
and the expected root-mean-squared error is \(\sigma_i\). In the shipped
operator, `complete_operator_risk` is the **expected Gaussian MAE**,
\(\sqrt{2/\pi}\) times the mean per-day conditional SD — not a
conditional standard deviation and not a variance. The mechanism table's
column label "conditional-variance lower bound" and the manuscript's phrase
"mean conditional standard deviation" therefore mislabel an already-MAE-scaled
quantity; the numbers in the published decomposition (0.379 to 0.451 degC at
7 to 365 days) are on the expected-MAE scale, and the published remainder
(0.165 to 4.268 degC) is a MAE-scale difference that already uses the
\(\sqrt{2/\pi}\) convention. Had the published column instead been read
literally as an SD, the corrected comparison would be
\(E|e|=\sqrt{2/\pi}\cdot 0.379=0.303\) degC at 7 days and
\(\sqrt{2/\pi}\cdot 0.451=0.360\) degC at 365 days, with remainders of
0.242 and 4.359 degC. Either way the substantive pattern is unchanged: the
Gaussian bound stays essentially flat across horizons while realized loss
grows by nearly an order of magnitude.

## What the comparison can claim

Recomputed on the same 61 stations with all seven horizons, the conditional
SD rises only from 0.475 to 0.565 degC, the expected Gaussian MAE from 0.379
to 0.451 degC, while realized MAE rises from 0.544 to 4.719 degC and realized
RMSE from 0.694 to 5.271 degC. The difference between realized and expected
loss grows from roughly 0.165 to 4.268 degC in MAE scale and from 0.219 to
4.706 degC in RMSE scale. What the conditional covariance can claim is only
this: it is an **optimal-prediction bound within the fitted Gaussian model**.
For any zero-mean Gaussian gap error with covariance
\(\Sigma_{G\mid O}\), no predictor can achieve smaller expected squared
error than the conditional mean, and the implied MAE bound is
\(\sqrt{2/\pi}\,\bar\sigma\). In that sense the flatness of the bound
is informative: extra boundary, donor, meteorological, and hydraulic
information is largely exhausted at short horizons, and the Gaussian bound
saturates.

## What the comparison cannot claim

The residual gap between realized loss and the Gaussian bound is **not
identifiable as model error plus drift**, and the bound is **not a MAE lower
bound in general**. The realized-vs-expected gap aggregates at least six
distinct and inseparable components: (i) covariance misspecification — the
VAR(1) Gaussian assumption and the ridge-regularized estimation of
\(\Sigma_{GG}, \Sigma_{GO}, \Sigma_{OO}\); (ii) parameter estimation
error — the operator's transition matrix, noise covariance, and memory
weight are estimated on a finite fitting record (the controlled simulation
shows plug-in conditional SD understates the true value in small samples,
because the squared sample correlation is upward-biased); (iii)
non-Gaussianity of the actual gap errors — fat tails make realized MAE and
RMSE exceed the Gaussian prediction at any given variance; (iv) aggregation —
the table compares a per-gap covariance bound with the mean over stations of
the mean over placements of realized loss, mixing station, placement, and
year effects; (v) finite-sample evaluation noise at 61 stations; and (vi)
genuine drift and model error of the recovery procedure itself. A remainder
over a Gaussian optimal bound is therefore an **upper envelope** of these
terms, not a measurement of any single one. The correct statement is: the
realized loss at long horizons is many times larger than the best achievable
Gaussian bound, so the shortfall must be attributed jointly to the
distributional and estimation assumptions, and any decomposition that assigns
it to model error and drift alone requires identification assumptions the
data do not provide.
