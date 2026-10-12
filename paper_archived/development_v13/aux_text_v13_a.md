# Auxiliary text v13 (agent A): Key Points and Plain Language Summary

Companion to `paper/development_v13/manuscript_v13_a.md`.

## Key Points

Exactly three key points; each is a complete sentence; each is <= 140
characters (character counts stated after each point).

1. Model-conditional fitting-period stress curves rank the same model's future loss on 57 outcome-disjoint networks (network Spearman 0.80). (137 characters)

2. Rank increment over the station-by-horizon mean is small (paired DeltaRho +0.042, CI straddling zero); 365-day extrapolation fails. (131 characters)

3. Decision value is conditional: triage fails, support-aware selection reaches regret 0.0067 at 8.5% coverage, benefit is baseline-dependent. (139 characters)

Character counts were computed including spaces and punctuation, excluding
the trailing period-count marker. The same sentences appear at the top of
the manuscript; the counts were verified with a byte-accurate character
count (ASCII) of each sentence string.

## Plain Language Summary

A failed logger can leave weeks of missing stream temperature while nearby
stations and weather data remain available. Managers need to know, before
the missing truth arrives, how much recovery error the model will make on a
given gap. We tested the recovery model itself: we cut held-out artificial gaps in later years of each record, after the fitting years used to train
the model, measured how well the model recovered them, and asked whether
that historical stress curve predicts the model's error on future gaps. On
57 networks that were not used to develop the original frozen predictor,
the stress curve ranked future recovery error well at the gap lengths and
seasons where a same-record trial curve existed (network Spearman 0.80).
Most of that strength comes from exact station-season curves; a network
average is a weak substitute, and 365-day predictions are extrapolation
that fails. The ordering is shared among regression-style recovery models
but not with neural or process-based models, and a stress curve built for
one kind of missingness badly misranks other kinds. These results support
using historical stress tests as model-conditional screening tools. They do
not support automatic filling or removal of monitoring stations, and
decision use requires explicit support checks, calibrated abstention,
coverage floors, and independent preregistered validation.

Wording constraints honored: the summary uses the phrases "held-out
artificial gaps in later years" and "57 networks that were not used to
develop the original frozen predictor". The two forbidden formulations do
not appear anywhere in the summary text above.
