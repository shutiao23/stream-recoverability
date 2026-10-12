# Simple-descriptor development result

The complete development run selects the simple-descriptor model. This is a
development decision, not a confirmation result.

The matched B+D+M+H analysis contains 55 independent river networks, 217
stations, and 1,260 station-by-gap units. Every realized loss comes from the
fixed B+D+M+H XGBoost recovery condition on placements for which every declared
donor, meteorological, and hydraulic input is present throughout the gap.

The literal complete operator passed the rank criterion but failed the
incremental-variance criterion. Its leave-one-network-out Spearman was 0.438
versus 0.311 for donor \(R^2\), an increment of +0.127. Adding the operator
after the training-fold-selected simple model increased station-gap \(R^2\)
by only 0.0171 rather than the required +0.05. The simple model alone had LONO
Spearman 0.702 and \(R^2=0.680\); adding the operator changed these to 0.765
and 0.697, respectively. The increment is too small to carry the proposed
information-operator novelty.

A network-random-intercept mixed model reached marginal \(R^2=0.688\) and
conditional \(R^2=0.758\) with the simple predictors. Adding the operator
raised these by only 0.0090 and 0.0012, respectively. The likelihood-ratio test
was precise because of the repeated station-gap rows, but the effect remained
far below the prespecified selection magnitude.

The simple model calibrated substantially better than the operator.
Equal-network simple-model slope was 0.976 and network-level Spearman was
0.789. Its network-block interval covered 99.4% of station-gap rows and 89.1%
of whole networks simultaneously, but still averaged 6.48 °C in width. The
literal operator's corresponding slope was 0.829 and its interval averaged
11.52 °C.

Nearest-donor correlation and placement season were included in the inner
model contest. Forty-seven outer folds selected the original four variables
plus nearest-donor correlation, seven selected the original four, and one
selected the original four plus the two seasonal coordinates.

The selected development model is therefore:

> Simple outage geometry, target memory, and donor redundancy predict much of
> the recoverable-loss variation across development stream-temperature networks; the
> completed covariance operator adds too little incremental information to
> justify its complexity.

The confirmation tested this narrower statement with rank, calibration,
coverage, and gap triage. Operator superiority, full-operator placement, and
information-gain novelty are removed from the headline.

The subsequently required fitting-period empirical-transfer baseline changed
the positive claim again. On 780 supported confirmation units at 7, 30, 90,
and 180 days, its station-gap Spearman was 0.934, network Spearman was 0.922,
and \(R^2\) was 0.812. The same-unit simple model reached 0.785, 0.687, and
0.563, respectively. The simple model therefore remains an important diagnosis, but
simple-descriptor sufficiency is no longer the manuscript claim.

Across all 1,440 confirmation units, 660 unsupported-horizon cells use the
fitting-period network mean and none remain missing. The empirical predictor
retains higher network-level Spearman than the simple model (0.767 versus
0.563), but has lower pooled Spearman (0.633 versus 0.803) and lower \(R^2\)
(0.145 versus 0.603). This fallback cost prevents an unqualified claim that the
empirical predictor wins at every scale.

## Confirmation result

Daily-value QC retained 45 wholly new stream networks. Three had no scoreable
B+D evaluation gap, leaving 42 networks and 1,440 station-gap units. The fixed
simple model transported rank (station-gap Spearman 0.803; network Spearman
0.563) but not operational magnitude. Network-bootstrap 95% intervals were
0.747--0.855 for station-gap rank, 0.728--0.876 for calibration slope, and
0.762--0.952 for simultaneous whole-network coverage. Intervals averaged
6.49 °C.

The US subset had slope 0.954 and simultaneous coverage 1.00; 25 cross-domain
networks had slope 0.753 and simultaneous coverage 0.76. Thermal-state-shift
cells had slope 0.270. The fixed gap-triage threshold also failed: it released
1.39% of cells with a 10% false-release rate, above the 5% cap. The simple model is
therefore supported as a descriptive risk ranking, not as calibrated
operational guidance.

Post-confirmation method development also found that horizon-Mondrian
intervals traded the original 6.49 °C mean width for 1.99 °C while reducing
simultaneous whole-network coverage to 0.405. An exact learn-then-test rule
certified no nonempty 5% false-release set through 200 requested labelled rows.
Real-data placement replay favored simple-risk minimax over MI and QR pivoting
across 14 networks with complete five-or-more-station replay matrices.

## Second-confirmation result

The internally hash-bound v2 roster attempted 60 networks and scored 57 after
three networks had no eligible evaluation gap. At directly supported horizons,
the empirical predictor covered 874 units and reached station-gap Spearman
0.945, network-level Spearman 0.805, and calibration slope 0.938. Across all
1,446 units, 572 network-mean fallbacks reduced these to 0.740, 0.715, and
0.950. The simple model reached 0.819, 0.614, and 1.017, respectively.

Ranking and calibration therefore reproduced at the network level, but the
decision endpoints did not. The empirical network-block interval covered every
network while its median width was 8.40 times median loss. Exact 5% triage
certified and released zero units for both predictors. The v2 amendment and
outcomes share a commit, so this result is not represented as externally
verifiable preregistration.

## Post-confirmation boundary analyses

An actual bidirectional LSTM sensitivity covered 14 networks, eight providers,
seven countries, and 165 station-gap units. Empirical risk versus LSTM loss had
station-gap/network Spearman 0.338/0.631, while XGBoost loss versus LSTM loss
had 0.314/0.411. Because 92.9% of runs reached the five-epoch cap, this does not
establish convergence, SOTA performance, or full-roster transfer.

The published air2stream-8 equation was implemented with its Crank--Nicolson
update and train-only bounded multistart calibration. On a fixed independent
US subset of eight networks, 14 stations, and 89 cells, empirical risk versus
process loss had station-gap/network Spearman 0.173/0.238. The alternate
optimizer, US-only inputs, and POWER-versus-USGS daily boundary mismatch remain
limitations.

On 1,327 matched planted outage geometries from 49 development networks,
empirical network Spearman was 0.566 versus 0.734 for matched artificial gaps.
The paired difference was -0.168 (95% interval -0.328 to -0.012), calibration
slope was 0.401, and 85.8% of natural-geometry items used a network-mean
fallback. Actual missing days still have no truth.

US random-intercept-and-slope models found a simple-model maritime slope of
0.649 versus 1.160 for arid/semiarid networks (interaction \(p = 0.0024\)).
Empirical climate and regulation interactions were not significant; regulated
and unregulated empirical slopes were 0.887 and 0.741 (interaction
\(p = 0.119\)). These are descriptive HUC2 and GAGES-II strata, not causal
effects.
