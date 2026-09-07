# Problem definition (frozen)

One page. This is the object of the WRR revision experiments, not an introduction.

## User and decision time

The user is an analyst repairing a completed daily stream-temperature archive
after an outage has ended. Both flanking observations are available. The
decision is made with historical observations plus information that is visible
at that repair moment. A separate real-time protocol that forbids the right
boundary is not the primary task; it is a later stress test.

## Default and actions

Default handling is the training-period day-of-year median climatology. The
action set is {adopt the candidate reconstruction on this outage, reject it and
keep the default}. There is no demonstrated resource constraint that forces a
20% reconstruction quota. Budget-capped ranking is a supplementary analysis.
Zero action (all default) is always a legal competitor. Unsupported predictions
map to reject.

## Available information

Allowed inputs are the target station's historical temperature, synchronous
donor temperatures that remain observed during the outage, calendar season, and
any meteorology or discharge that is actually present. Evaluation never uses
the hidden target values except as truth.

## Primary and secondary endpoints

A case is one station-year (calendar year) together with an outage pattern,
which may contain several gaps. After actions are applied, the completed
series is scored against the unhidden truth.

Primary loss \(L_q\) is the absolute error of the hottest consecutive 30-day
mean. Secondary loss is the absolute error of days above 20 °C, labelled as a
sensitivity setting rather than a species-specific standard. Daily MAE is an
intermediate diagnostic only.

Benefit on a completed case is

\[
B_q = L_q(\text{default output},\ \text{truth})
- L_q(\text{chosen output},\ \text{truth}).
\]

Positive \(B_q\) means the decision improved the thermal-regime judgment.

## What would count as success

On networks or years that did not participate in design choice, a rule fixed
from historical data must beat all-default and beat the strongest historically
supported simple alternative on mean \(B_q\), while allowing rejection. A
ranking correlation without a net gain over all-default does not solve the
problem.

## Explicitly not claimed here

No recoverability law, no model-family-independent station threshold, and no
Johnson (2021) numerical confirmation are assumed. Those claims are either
dropped or subjected to a predeclared falsification experiment.
