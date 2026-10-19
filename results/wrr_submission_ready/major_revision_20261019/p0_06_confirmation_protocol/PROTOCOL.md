# Confirmation protocol and the one verdict this panel can support

The locked object is `final_method_config.json` in the parent directory:
hottest-30 absolute error, tolerance 0.5 °C, fitted risk score trained on
`abserr_policy`, threshold equal to the largest retention in {0.10, …, 0.95}
whose independence-group clustered bootstrap bound at `1 - 0.05/86` is at most
5%. The pre-specified benefit is retention of that score minus retention of the
peak-window rule under the same rule. The margin that would have counted as a
clear operational gain is 5 points. Missing the margin is a result. The margin
is not revised after seeing the table.

## What was scored

`scripts/311_wrr_p0_02_frozen_risk_thresholds.py` wrote
`../p0_02_isolated_risk_thresholds/`. Outer-fold calibration scores are stored
per fold. Fold assignment uses the 41 shared-station components on the external
panel and the 110 development networks, which do not share stations. A unit test
in `tests/test_outer_fold_isolation.py` checks that changing one outer fold's
labels leaves that fold's calibration scores and model unchanged.

No held-out provider panel is left unused. This cross-fit is therefore not a
new sealed confirmation. The historical sealed number is the frozen certificate
screen at 70% retention.

## Verdict

On the external panel, three fold seeds:

| contrast | point estimates |
|---|---|
| fitted risk minus peak-window rule | 3.27, 2.64, 2.76 points; every interval excludes zero; none clears 5 points |
| fitted risk minus calibrated bound | −1.80, −2.40, −2.48 points; the bound keeps more records |
| fitted risk minus length rule | 28.9, 27.6, 29.0 points; weak baseline, not the confirmatory contrast |

The 5-point margin against the peak-window rule is not met. The fitted score is
not recommended over the calibrated certificate bound on retention at this cap.
The length-rule gap stays large and does not carry the recommendation.

The frozen certificate versus the length rule at 70% retention, with bootstrap
clusters equal to the 41 groups, is −5.89 points, interval [−6.96, −4.76]. That
sentence belongs to the certificate screen.

## Real calendar and hot-year split

`scripts/324_wrr_same_method_replay_and_hotyear.py` applies the development
outer-fold fitted-risk models to the 418 already placed real-calendar groups.
The scored network is not in the model's training fold. On target-only,
partial-donor and all-donor failure, the admitted-share difference versus the
peak-window rule is between −0.7 and +1.9 points. Eight of the nine intervals
include zero. The length rule admits 16–18 points less. Error among records the
fitted score keeps is 0.5–1.3%, against 2.6–4.1% if every available
reconstruction is kept.

On the external designed panel at 20 °C, seed 101, the fitted score's predicted
hot-year share differs from the full candidate pool by +0.9 points. That total
is a −0.3 point prediction error plus a +1.2 point selection shift. Reconstructing
every candidate differs by −0.6 points. Lower error among admitted years does not
imply a more accurate regional share.

## What is not claimed

`scripts/322_wrr_selection_null_calibration.py` ran 2000 repetitions of the
selector. The pointwise bound exceeded 5% on fresh groups in 19.2% of
repetitions (Monte Carlo SE 0.009). The simultaneous bound exceeded it in 8.5%
(SE 0.006). No network-count recommendation is issued from that simulation or
from the old design-effect formula.
