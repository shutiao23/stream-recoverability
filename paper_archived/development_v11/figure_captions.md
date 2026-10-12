# Figure captions

**Figure 1. Fitting-period evidence is evaluated before it enters a monitoring
decision.** Artificial gaps and structural descriptors are measured in fitting
years, mapped to loss across development networks, evaluated on new networks,
and only then considered for placement or triage. Conditional covariance is a
Gaussian lower bound within this chain.

**Figure 2. Simple-descriptor ordering transfers, while magnitude calibration
changes by domain.** Small points are all 1,440 first-panel station-gap units
colored by US versus cross-domain source; outlined symbols are network medians.
Both axes are logarithmic, and the diagonal is the 1:1 line. The lower panel
shows realized minus predicted MAE.

**Figure 3. Conditional risk saturates while realized long-gap loss grows.**
Means use the same 61 stations that support every horizon from 7 to 365 days.
The conditional-variance lower bound rises little, whereas the simple model
tracks the growing realized loss.

**Figure 4. Cross-domain calibration often requires labelled adaptation and
remains unreliable at tested budgets.** The left panel shows reliability by
domain on common axes. The right panel shows the fraction of network-grouped
method-development resamples with evaluation slope in [0.9, 1.1] versus the
requested labelled station-gap budget.

**Figure 5. US calibration heterogeneity is detectable for simple descriptors
but not stable for empirical transfer.** Points and intervals are adjusted
prediction slopes from network-random-intercept-and-slope models spanning
development and both outcome panels. Simple-model maritime calibration is
shallower than the arid/semiarid reference, whereas empirical climate and
regulation interactions are not significant. HUC2 climate and GAGES-II
major-dam strata are descriptive, not causal.

**Figure S1. Gap-specific minimax placement has the lowest mean non-oracle
regret in the available development replay.** Curves show worst-target 90-day
MAE above the realized-outcome oracle across retained fractions. Fourteen
development networks retained a complete directed replay matrix with at least
five stations. This figure remains development-only; the 13-network second
replay is reported separately and showed a small directional reduction without
a prespecified utility margin.
