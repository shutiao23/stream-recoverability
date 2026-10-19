# P1 — what the finished side analyses are, and are not

The repeated learning curves and the phase/air-temperature checks stay in the paper. They are not rerun. They do not become confirmation of the locked admission rule.

- Development cases: 40704; network labels 110; unique stations 354; independence groups 110; within-panel station-overlap pairs 0.
- Reserved cases: 10820; network labels 36; unique stations 103; independence groups 36; within-panel station-overlap pairs 0.
- Stations present in both development and reserved cases: 0.

scripts/316 repeats training-network draws on development network labels. Those draws are not independence groups, and the interval across draws is training-sample variation on a fixed test panel, not a new-basin interval.

scripts/317 scores the phase and air-temperature boundary on development networks. It remains a mechanism check for the hottest-30 endpoint. It is not evidence that the fitted risk score is necessary, and it is not recomputed here.

Three uncertainties stay separate: variation across training subsets, uncertainty on the fixed test panel, and uncertainty for a basin that shares no station with the fit.

# P2 — extensions that are not results of this revision

An agency case with a fault log, a second temperature sensor, or an independent reference observation would measure changed admission decisions, abstentions, and manual checks. This archive does not contain that log. No maintenance saving and no ecological recovery is claimed.

A later basin test is informative only when it changes the mechanism boundary already named: a warm season that does not match the historical peak window, a regulated or groundwater-dominated thermal regime, a short history, a weak donor, or a gap that persists across years. Adding another country without one of those contrasts does not strengthen the admission claim.

The primary endpoint remains the hottest 30-day mean. Annual means, cold extremes, and phase are boundary checks. They are not additional primary claims.

A dataset or dashboard, if released, has to carry this method config, the measurement contract, and the evidence label of each number. Policy text does not add a universal risk guarantee.
