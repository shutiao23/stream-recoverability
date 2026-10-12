# Auxiliary text v13 (merged): Key Points and Plain Language Summary

Companion to `paper/development_v13/manuscript_v13.md`. Merged from the
independent adversarial versions `aux_text_v13_a.md` and `aux_text_v13_b.md`;
numbers re-verified against `results/revision_v13/` and the v12 artifacts.

## Key Points

Exactly three key points; each is a complete sentence and at most 140
characters (spaces included; character counts stated after each point).

1. Model-conditional fitting-period stress curves rank the same model's future loss on 57 outcome-disjoint networks (network Spearman 0.805). (132 characters)

2. A station-by-horizon historical mean nearly matches them (pooled 0.942 vs 0.945; paired +0.042, CI spanning zero). (116 characters)

3. Decision value is conditional: triage fails, support-gated selection reaches regret 0.0067 at 8.5% coverage, and independent validation is required. (137 characters)

Character counts verified with a byte-accurate ASCII count of each sentence.

## Plain Language Summary

A failed logger can leave weeks or months of missing stream temperature while
neighboring stations and weather data remain available. Managers need to know
how much recovery error a gap will cause before the truth for that gap
exists. We tested the recovery model itself: we cut held-out artificial gaps
in later years of each record, measured how well the model recovered them,
and asked whether that historical stress curve predicts the model's error on
gaps that occur after the fitting period. The evaluation used 57 networks
that were not used to develop the original frozen predictor. On the gap
lengths and seasons where a same-record trial curve existed, the stress
curve ranked later recovery error well (network Spearman 0.805). However,
most of that strength comes from exact station-season curves, and a simple
benchmark--the average of each station's own historical trial errors at the
same gap length--ranks almost as well, so the added value of the seasonal
empirical curve is modest. Predictions beyond the supported durations are
extrapolation that fails and must be withheld: the 365-day horizon ranked
poorly and its uncertainty intervals covered the truth less than half the
time. The difficulty ordering is shared among regression-style recovery
models but not with neural or process-based models, and two independent
studies of different gap patterns (for example, outages that also take down
neighboring stations) disagreed, so those results are not yet ready to use.
A predictor that ranks future error well is not automatically a good basis
for action: when managers used it to choose which gaps to fix under a fixed
budget, it captured less of the total recovery loss than simple gap
descriptors, and choosing gaps by predicted error could even worsen some
downstream temperature metrics compared with a simple climatology fill.
These results support using historical stress tests as model-conditional
screening tools with explicit support checks and calibrated abstention. They
do not support automatic filling or removal of monitoring stations, and
decision use requires independent preregistered validation.

Wording constraints honored: the summary uses the phrases "held-out
artificial gaps in later years" and "57 networks that were not used to
develop the original frozen predictor". The forbidden formulations ("real
future gaps", "not used to build anything") do not appear.
