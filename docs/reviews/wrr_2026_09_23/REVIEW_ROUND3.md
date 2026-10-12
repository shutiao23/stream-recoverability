# Referee report, third round — the revised v17 manuscript

**Manuscript:** *Outage timing, not outage length, decides whether a
stream-temperature year can be used* (`paper_archived/v17/`), as revised in response to
`REVIEW_ROUND2.md`.

**Review round:** third adversarial read, 2026-09-23. Round 1 rejected the v16
submission and specified the redesign. Round 2 attacked the first v17 draft and
forced a reproducibility rebuild, a missing sensitivity, and a reframing. This
round reads the revision. Nobody has read it yet, which is the only reason it is
worth reading again.

**Recommendation: Major revision, and the title must change.** (The revision
recorded in `RESULTS.md` makes these changes; this report is the version that
found the problems.) The paper's
central claim is true for the endpoint it was built on and false for the
endpoint the most closely related published guidance actually studied. That is
a narrowing, not a refutation, and the narrowed version is a better paper — but
it cannot go out as written.

---

## 1. Major comment — the general claim does not survive a change of metric,
and the metric it fails on is the one the cited guidance used

The title, the abstract and §3.2 make a claim about stream-temperature records:
timing of the outage governs the error, length does not. All of the evidence is
built on one endpoint, the hottest consecutive 30-day mean. Johnson et al.
(2021), the guidance this paper positions itself against, worked on the annual
mean, the phase and the amplitude. So I computed three further endpoints on the
same completed years — the annual mean, the coldest consecutive 30-day mean,
and the peak-to-trough amplitude — and scored each against a tolerance equal to
the same fraction of its own interannual standard deviation that 0.5 °C is of
the peak's.

Single-axis discrimination of a consequential error, development cases:

| endpoint | peak-window overlap | warm-season coverage | outage length | winning axis |
|---|---:|---:|---:|---|
| hottest 30-day mean | 0.819 | 0.820 | 0.750 | **timing** |
| **annual mean** | 0.672 | 0.818 | **0.845** | **length** |
| **coldest 30-day mean** | **0.447** | 0.619 | **0.803** | **length** |
| amplitude | 0.758 | 0.792 | 0.768 | **timing** |

The ordering is stable at tolerances of 0.25, 0.47 and 1.0 interannual standard
deviations — I checked, because the obvious objection is that the null is a
tolerance artefact. It is not. And the three-variable timing rule, which buys 3.6 points on
the peak (95% interval 2.9–4.4) and 1.5 on the amplitude, buys nothing at all
on the annual mean (+0.1 points, interval −0.1 to +0.3).

Two things follow, and the second is more interesting than the first.

The narrow point is that the paper overclaims. A completeness rule on outage
length is the *right* axis for an average, because an average is a sum over
days and what matters is how many days are missing; it is the wrong axis for a
warm-season extreme, because an extreme lives in a specific window and what
matters is whether that window survived. The coldest-30 result makes this
mechanical rather than rhetorical: peak-window overlap has an AUC of 0.447 for
the cold extreme, which is to say hiding the summer peak tells you nothing
useful about the winter minimum, exactly as it should not.

The broad point is that this *resolves* the observation the paper currently
quotes as an open puzzle. Johnson et al. reported that timing of missing data
affected thermal signal estimates "inconsistently in space and time". They were
working across metrics that include the annual mean. On the metrics where
timing should matter it does, strongly and consistently; on the metrics where
it should not, it does not. The inconsistency was a mixture of two regimes. A
paper that says so is a contribution to the guidance literature rather than a
correction of it, and it should be written that way.

I would require: the title narrowed to the endpoint class; §3.2 restructured
around the dichotomy rather than around a single endpoint; an explicit
recommendation that length-based screening be retained for averages; and the
certificate scoped in the abstract to warm-season extremes.

## 2. Major comment — a third reproducibility defect, from the same family as
the first two

Round 2 found that the case table was seeded from a salted hash, and that a
shared summary filename let one run overwrite another's counts. Both were
fixed. I found a third instance.

The case table's *content* was deterministic after the repair, but its *row
order* was not: worker results are concatenated in completion order. The
verification round 2 performed — set an index, sort, compare — is exactly the
check that cannot see this. Row order matters here because a discrete screening
rule has massive ties (thousands of cases share an outage length of exactly 90
days) and the tie-break jitter is assigned positionally. Re-running the
pipeline with identical content in a different order moved the headline
confirmation contrast from −7.06 to −7.16 points.

The effect is small and does not threaten the conclusion. The pattern does. Three
defects of the same family in one codebase says the project does not yet have a
working definition of "reproducible", and the definition it needs is: *byte-identical
artifacts from a clean run, including order, verified by a test that compares
the files rather than a normalised view of them.* The case table is now sorted
on a declared key before it is written, two independent runs are byte-identical
including order, and a test pins it. Every number in the revision comes from
the run behind that fix.

## 3. Major comment — the open problem from round 2 is closable, and the paper
should close it rather than name it

Round 2 established that the conformal intervals are valid for a population of
networks but not at an individual new site: per-network coverage had a tenth
percentile of 0.839 and a minimum of 0.709, with six of 36 reserved networks
below 0.85. The revision states this honestly and calls a cluster-aware
calibration the obvious next step. It is one afternoon of work and I think the
author should do it rather than leave it as a promissory note, having already
been caught once this round with a promissory note in the methods.

I implemented it: calibrate on the per-network conformal quantiles and take a
high quantile of those, which targets "coverage holds inside most networks"
instead of "coverage holds on average over cases". It works, and it is not
even particularly expensive:

| calibration | marginal coverage | per-network minimum | networks below 0.85 | median width | rate at 70% |
|---|---:|---:|---:|---:|---:|
| pooled | 0.909 | 0.778 | 13.9% | 0.54 °C | 2.53% |
| cluster, 0.7 | 0.932 | 0.842 | 5.6% | 0.60 °C | 2.53% |
| cluster, 0.9 | 0.964 | 0.851 | **0%** | 0.80 °C | 2.53% |

Two things about this deserve to be in the paper. First, the price should be
quoted rather than hidden: site-level validity costs about a 1.5× widening and
overshoots nominal marginal coverage, so it is a choice the analyst should make
rather than one the method should make for them. Second — and this is the part
that protects the paper's main claim — **the screening result is completely
unaffected by the choice of calibration**, identical to four decimal places,
because the rank order the screen uses is a monotone transform of the bound and
a change of scale cannot reorder it. The author should say so explicitly,
because a reader who distrusts the intervals will otherwise assume the distrust
propagates to the frontier, and it does not.

Report it as a dial with its price, not as a single conservative setting.

## 4. Major comment — the panel is unbalanced and the point estimate is
case-weighted

One provider contributes 56 of the 110 development networks and network sizes
differ by an order of magnitude. The bootstrap clusters by network, which makes
the interval honest about that, but the point estimate still weights cases
equally, so a few large networks can carry it. I recomputed the contrast with
each network, each station and each provider weighted equally, and looked at
the distribution over individual networks rather than the pooled number. On the
reserved panel: case-equal −7.01 points, provider-equal −6.30, network-equal
−5.82, station-equal −5.54. Every weighting clears the declared five points and
every interval excludes zero, and across individual reserved networks the
median contrast is −5.0 points with **83% of networks favouring the
certificate** and a worst case of +2.8.

The result is therefore not carried by a few large places, and the author
should say so with the least favourable weighting in the text rather than only
the pooled number. This is the one attack in this round that the paper answers
completely.

## 5. Minor but substantive

**5.1 Cross-year outages are excluded by construction and this is not stated.**
Outages are placed within a calendar year. Real logger failures straddle New
Year, and a gap that runs from November to February damages two annual metrics
at once while hiding no part of either warm season. The design cannot represent
that case, and the paper should say so in the limitations rather than leave a
reader to infer that the outage catalogue is complete.

**5.2 The oracle curve in Figure 2** is an oracle over retention with the
reconstruction held fixed, while the certificate curve also selects the method.
Round 2 asked for the caption to say so; the revision changed the caption but
the asymmetry should also be one sentence in the text, since the gap at the
left edge is where a reader will look.

**5.3 The amplitude endpoint is worth keeping.** It behaves like the peak, and
it is the endpoint most used in thermal-regime classification. Adding it costs
nothing and doubles the scope of the positive claim.

## 6. What survived this round

Everything I attacked in the screening result held. The frontier is unchanged
under every conformal calibration. The metric dichotomy narrows the claim but
strengthens the mechanism, because it predicts in advance which endpoints
should and should not respond to timing and then confirms it on a metric where
the effect reverses. The reproducibility defect moved the headline by a tenth
of a point. The paper's problem was never that its result was fragile; it was
that the result was stated more broadly than it had been tested.
