# Problem definition (next round, frozen 2026-09-07)

One page. This replaces the v16 mean-benefit superiority target for new
experiments. It does not rewrite the v16 paper's already-failed claim.

## User and decision time

The user repairs a daily stream-temperature archive. Visible information may
include historical target observations, synchronous donor temperatures,
meteorology, and one or both flanking observations. The right boundary is
available in the primary offline-repair setting. Missing right boundary is an
information condition, not an automatic reject for every method.

## Population and truth

The study population is **rivers**. Seas, lakes, canals, and estuaries are a
separate transfer list. Annual hottest-30 truth is defined only on fully
observed calendar years. Reference series are never imputed. The v16 36-object
confirmation set, including the 846-case river+complete-year subset, has been
read and is not unseen confirmation.

## Default and actions

Default is day-of-year median climatology. Actions are {adopt a supported
candidate reconstruction, reject and keep the default}. Zero action is always
legal. Support is method-specific (donors for donor regression, both flanks
for interpolation, air for air-driven models).

## Primary endpoint

\[
B_q = L_q(\text{default},\ \text{truth})
- L_q(\text{policy},\ \text{truth})
\]

\(L_q\) is absolute error of the hottest consecutive 30-day mean on a complete
calendar year. Report absolute default and policy error, and over/under
direction. Days above 20 °C remain a sensitivity metric.

## What counts as success

Primary claim: **risk control**. On river networks or years that did not
participate in rule selection, a historically calibrated policy must be
non-inferior to the strongest historically supported simple method by more
than 0.05 °C in network-equal mean \(B_q\), and must reduce the rate of
negative-\(B_q\) cases. Harm reduction must beat same-adoption-rate random
reject and a simple length/season rule.

Alternative claim: mean \(B_q\) strictly above that simple method. If neither
claim holds, the paper reports the training-mismatch diagnosis and simple
applicability, not a new superior decision layer.
