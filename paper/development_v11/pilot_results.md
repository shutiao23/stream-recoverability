# Open-development result and route decision

The completed open run contains 55 river networks, 217 stations, and 1,260
station-by-gap units with matched B+D+M+H XGBoost outcomes. The development
role contributes 38 networks and the validation role 17. A shared
joint-consecutive selector gives the operator and recovery model exactly the
same donor, meteorology, hydraulics, and training-year rosters at all 217
stations.

The literal complete conditional risk is the primary operator. Its LONO
station-gap Spearman is 0.438 and its network-summary Spearman is 0.291.
Equal-network calibration has intercept 0.220 and slope 0.829. The nominal 90%
network-block interval covers 0.909 of whole networks simultaneously, but its
mean width is 11.52 degrees C, so coverage is not operationally sharp.

The literal operator improves LONO Spearman over donor R2 by 0.127, passing the
+0.10 rank component of the advancement gate. It adds only +0.01710 R2 after
the strongest available simple model, missing the +0.05 nested component. Both
components were required, so Route B fails and the recorded decision is Route
A: simple outage geometry and redundancy.

The inner contest also includes nearest-donor correlation and placement
season. Forty-seven folds add nearest correlation to the original four
variables, seven select the original four, and one selects the seasonal
version. The resulting simple model has station-gap Spearman 0.702,
network-summary Spearman 0.789, equal-network calibration intercept 0.034 and
slope 0.976, simultaneous whole-network coverage 0.891, and mean interval
width 6.48 degrees C. The simple model therefore ranks and calibrates better than the operator,
with materially narrower intervals, while its simultaneous coverage miss must
remain visible.

The regime-weighted memory construction is retained only as a diagnostic. On
the 61 stations supporting every gap through 365 days, its mean risk falls
from 0.471 at seven days to 0.453 at 365 days while realized loss rises from
0.544 to 4.719. The literal risk increases from 0.379 to 0.451, the correct
direction but far too little magnitude. No included station is in the
high-memory regime that motivated the weighting rule.

The placement regret curve remains a synthetic implementation benchmark:
selection and evaluation share the same known covariance. It is not empirical
H3 evidence. Machine-readable tables, figures, Route A intervals, and the
217-row exact-roster audit are under `results/development_v11/` and regenerate
with:

```bash
make development-v11
```
