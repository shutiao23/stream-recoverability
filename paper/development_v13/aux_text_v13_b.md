# Auxiliary text v13 (agent b)

Companion to `paper/development_v13/manuscript_v13_b.md`. Both items below are
worded to comply with the v13 review constraints: the plain-language text
avoids prohibited phrasing about actual out-of-sample gaps and about networks
being unused to build anything, uses the required phrases "held-out artificial
gaps in later years" and "57 networks that were not used to develop the
original frozen predictor", and avoids claiming to be the strongest tested
screen.

## Key Points

Exactly three complete sentences. Each sentence is at most 140 characters
(spaces included); the character count of each sentence is stated after it.

1. Fitting-period stress curves rank a recovery model's error on later gaps across 57 outcome-disjoint networks (network Spearman 0.805). *(134 characters)*

2. The station-by-horizon historical mean nearly matches them (pooled 0.942 vs 0.945; paired +0.042, CI spanning zero). *(116 characters)*

3. Decision value is conditional: triage fails, support-gated selection reaches regret 0.0067 at 8.5% coverage, and validation is required. *(136 characters)*

## Plain Language Summary

A failed logger can leave weeks or months of missing stream temperature while
neighboring stations and weather data remain available. Managers need to know
how much recovery error a gap will cause before the truth for that gap
exists. We tested the recovery model itself: we cut held-out artificial gaps in later years of each record, measured how well the model recovered them, and
asked whether that historical stress curve predicts the model's error on gaps
that occur after the fitting period. The evaluation used 57 networks that were not used to develop the original frozen predictor. On the gap lengths and
seasons where a same-record trial curve existed, the stress curve ranked later
recovery error well (network Spearman 0.805). However, most of that strength
comes from exact station-season curves, and a simple benchmark—the average of
each station's own historical trial errors at the same gap length—ranks almost
as well, so the added value of the seasonal empirical curve is modest.
Predictions beyond the supported durations are extrapolation that fails and
must be withheld: the 365-day horizon ranked poorly and its uncertainty
intervals covered the truth less than half the time. The difficulty ordering
is shared among regression-style recovery models but not with neural or
process-based models, and two independent studies of different gap patterns
(for example, outages that also take down neighboring stations) disagreed, so
those results are not yet ready to use. A predictor that ranks future error
well is not automatically a good basis for action: when managers used it to
choose which gaps to fix under a fixed budget, it captured less of the total
recovery loss than simple gap descriptors, and choosing gaps by predicted
error could even worsen some downstream temperature metrics compared with a
simple climatology fill. These results support using historical stress tests
as model-conditional screening tools with explicit support checks and
calibrated abstention. They do not support automatic filling or removal of
monitoring stations, and decision use requires independent preregistered
validation.
