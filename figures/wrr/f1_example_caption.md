# Figure 1 - a real annual record, two equal-length gaps, two statistics

**Drop-in caption.** The same station-year, one complete annual water-temperature
record, carries two statistics with different supports: an annual mean, supported
on every day, and a hottest 30-day mean, supported on the single 30-day window
that achieves the maximum. **(a)** The complete daily series of chmi_berounka
station 0-203-1-198600, calendar year 2013 (n = 365 days, no missing
day), with two designed gaps of identical length, 30 days, marked in different
positions: gap A over the peak window that achieves the complete-record hottest
30-day mean (2013-07-15 to 2013-08-13), gap B in late autumn
(2013-11-01 to 2013-11-30). The daily curve is drawn faint
inside the two bands, where the record exists but the analyst does not see it, and
dark where the gap leaves it observed. The orange line is the 30-day running mean
recomputed with both bands withheld, so it breaks wherever no fully observed
window remains; dotted lines are the two complete-record statistics, and panels
(b) and (c) score each gap separately.
**(b)** Each gap's effect on each statistic, in degrees Celsius. Dots are
estimates from the days the gap leaves; the open dot and dotted line are the
complete-record truth. The two panels use different vertical scales and neither
starts at zero, so the values, not bar lengths, carry the comparison (10.05 °C annual mean,
21.58 °C hottest 30-day mean). A 30-day gap over the
peak window moves the hottest 30-day mean by -3.99 °C
while the same length in late autumn leaves it exact (+0.00 °C);
the annual mean moves by -1.03 °C under gap A and
+0.24 °C under gap B. **(c)** The length-matched sweep: every one
of the 336 possible 30-day gap starts of the same year, plotting the error each
position induces in the hottest 30-day mean (orange) and in the annual mean (blue);
the shaded band holds the starts whose window reaches the peak window. Position,
not length, decides whether the peak survives.

This figure is an illustration of the mechanism on one real record, not a result:
it reports no model, no estimate of a population quantity and no test. The
station-year belongs to the reserved (retrospective holdout) split of the study
panel, whose recorded prior use is descriptive only, and it enters no fit
reported here.

## Identity and provenance

| item | value |
| --- | --- |
| panel | `results/development_v11/confirmation_daily_qc/networks/chmi_berounka/daily_wide_temperature.csv` |
| panel root | `results/development_v11/confirmation_daily_qc/networks` |
| provider / network | chmi / chmi_berounka (river group Berounka) |
| split role | reserved (retrospective holdout; prior use `prior_descriptive`) |
| station id | 0-203-1-198600 |
| calendar year | 2013 (365 days, complete; station QC verdict `accepted`) |
| network data window | 2010-01-01 to 2018-01-01 |
| statistic definitions | `src/stream_recoverability/experiments/wrr_revision/thermal.py` (hottest 30-day mean = maximum of the 30-day rolling mean over fully observed windows; annual mean over the calendar year) |
| units | degrees Celsius |
| gap length | 30 days each, designed, not observed |
| selection rule | C1-C7 in `scripts/265_wrr_figure1_example.py`; screened over the 165 network panels of the root (551 complete station-years on accepted, reserved-role stations), of which 195 survive and the ranking picks this one |

## Numbers (degC)

| quantity | complete record (truth) | gap A: over the peak window | gap B: late autumn |
| --- | --- | --- | --- |
| annual mean | 10.051 | 9.018 (-1.033) | 10.296 (+0.245) |
| hottest 30-day mean | 21.581 | 17.588 (-3.992) | 21.581 (+0.000) |

Peak window of the complete record: 2013-07-15 to 2013-08-13.
Gap A removes exactly that window; gap B removes 2013-11-01 to 2013-11-30.
The contrast the figure is built on: the same 30-day length costs
3.99 °C in the hottest 30-day mean when it covers the peak
and 0.24 °C in the annual mean when it sits in late autumn,
a factor of 16.3.
