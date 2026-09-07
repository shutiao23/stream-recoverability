# Step 6: station-year replay on the first panel

**Superseded as a test of the frozen rule.** This run used
`xgb_longblock_boundary` with P0 (published-trainer) predicted benefits.
Long-gap refusals therefore follow the withdrawn neighbour-boundary ranking,
not the freeze. Use `step6_frozen_replay/` (and `step8_frozen_replay/`)
instead.

First-panel development networks, all 42. Recoverer:
`xgb_longblock_boundary` from `fit_station_recoverers` (long-block
training with gap-wide linear-interp boundary). The case is one
station-year plus a non-overlapping outage pattern. After adopt/reject
is applied, the completed year is scored once. Primary endpoint is
hottest-30 benefit versus climatology on that completed year, averaged
over **all cases**, including rejected gaps (those contribute 0 against
all-default). Spearman is not the endpoint.

- Script: `scripts/163_wrr_end_to_end_replay.py --recoverer xgb_longblock_boundary`
- Cases: 10,709 station-year patterns (219 stations; 6 cases have
  undefined hottest-30 on truncated 2026 years and are omitted from
  means)
- Network failures: 0
- Decision rule: adopt if predicted MAE benefit > 0 and the cell is
  supported; otherwise keep climatology (τ = 0, unsupported → reject)
- Seasonal comparator: adopt gaps of length ≤ 30 days in any
  meteorological season (a duration cap, not a JJA-only rule)

Archived factorial placements of every length cannot sit on the same
days. Each duration is replayed as its own non-overlapping pattern, and
a mixed 30/90/180-day pattern is replayed separately. Stacking every
experimental gap into one year would overwrite the record with 365-day
blocks and force hottest-30 benefit to 0.

## Headlines (mean over all cases)

| Strategy | hottest-30 benefit (°C) | adopt rate |
|---|---:|---:|
| all-default | **0** | 0 |
| seasonal rule (≤ 30 d) | **+0.030** | — |
| adopt/reject rule | **+0.144** | **0.789** |
| all-reconstruct | **+0.255** | 1 |

The adopt/reject rule **beats all-default** (0.144 > 0) **and beats the
seasonal rule** (0.144 > 0.030) on the mean over all 10,709 cases, not
only adopted gaps. Gap-weighted adopt rate is 0.845. Network-equal
means are the same sign: rule +0.148, seasonal +0.041, all-reconstruct
+0.274, all-default 0; 40/42 networks have rule > 0 and 36/42 have
rule > seasonal.

The rule does **not** beat always-reconstruct. Long-block XGBoost
remains helpful on hottest-30 even at 180 and 365 days, so refusing
those gaps leaves benefit on the table. That is a property of this
recoverer, not of the decision layer.

## 1. What a case is

A case is one station-year and one outage pattern:

- `duration`: non-overlapping archived gaps of a single length (7, 14,
  30, 60, 90, 180, or 365 days)
- `mixed`: non-overlapping 30/90/180-day gaps, one length per start
  date, cycling those three lengths

Benefit is

\[
B_{30} = L_{30}(\text{climatology year},\ \text{truth})
- L_{30}(\text{chosen year},\ \text{truth})
\]

with \(L_{30}\) the absolute error of the hottest consecutive 30-day
mean. All-default is identically 0. Rejected gaps are filled with
climatology, so they do not inflate the mean.

## 2. All-cases mean (required test)

Pooled over duration strata and mixed patterns (recoverer
`xgb_longblock_boundary`):

- all-default hottest-30: **0 °C**
- seasonal rule: **+0.0298 °C** (10.8% of cases harmful, 15.9% helpful)
- adopt/reject: **+0.1441 °C** (10.8% harmful, 31.9% helpful; 57.2%
  exactly 0, mostly years whose peak is untouched)
- all-reconstruct: **+0.2547 °C** (14.2% harmful, 44.3% helpful)

Adopt rate: **0.789** mean of case-level rates (0.845 if gaps are
pooled). Daily MAE benefit of the rule is +0.191 °C on the same cases
(diagnostic only).

Verdict: the frozen mean-threshold rule with support refusal beats
all-default and the seasonal duration cap on the first panel. It is
not the best of the four strategies; always using long-block
reconstruction is.

## 3. Mixed-duration years

These are the closer analogue of an operational year with several
outages of different lengths (1,616 cases, 42 networks):

| Strategy | hottest-30 (°C) | adopt rate |
|---|---:|---:|
| all-default | 0 | 0 |
| seasonal | +0.024 | (only ≤ 30 d) |
| adopt/reject | **+0.193** | 0.706 |
| all-reconstruct | +0.386 | 1 |

Rule minus seasonal = +0.169 °C. Network-equal mixed: rule +0.198,
seasonal +0.023, all-reconstruct +0.426; 37/42 networks have rule > 0
and 34/42 have rule > seasonal.

## 4. Duration diagnostics

| Length (d) | n | networks | rule | seasonal | all-reconstruct | adopt rate |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 1,603 | 42 | +0.032 | +0.032 | +0.032 | 0.996 |
| 14 | 1,581 | 42 | +0.047 | +0.047 | +0.047 | 0.993 |
| 30 | 1,557 | 42 | +0.099 | +0.100 | +0.100 | 0.983 |
| 60 | 1,501 | 42 | +0.266 | 0 | +0.270 | 0.906 |
| 90 | 1,390 | 42 | +0.285 | 0 | +0.327 | 0.738 |
| 180 | 968 | 39 | +0.132 | 0 | +0.531 | 0.212 |
| 365 | 493 | 32 | +0.055 | 0 | +0.912 | 0.047 |

At 7–30 days the three active strategies coincide: the rule adopts
almost everything, matching seasonal and always-on. The seasonal cap
then contributes 0 at 60–365 days by design. The MAE-based rule still
adopts most 60-day years and many 90-day years, which is where it
pulls ahead of seasonal. At 180 and 365 days it mostly refuses, while
always-on long-block reconstruction is strongly positive on hottest-30.
That refusal is why the rule loses to all-reconstruct and why an
MAE-trained threshold is conservative for this thermal endpoint.

## 5. What this step can and cannot claim

On the 42 first-panel networks, a τ = 0 supported-only adopt rule in
front of `xgb_longblock_boundary` improves station-year hottest-30
error relative to climatology and relative to “reconstruct only short
gaps,” with about four-fifths of gaps adopted. Always reconstructing
with the same recoverer is better still. Two networks have
network-mean rule benefit ≤ 0 (`huc8_02040104`, `huc8_10020007`).
This is development-panel evidence, not confirmation.

## Artifacts

- `station_year_replay.csv` — one row per case
- `network_replay.csv` — network means
- `pattern_replay.csv` — duration / mixed means
- `failures.csv` — empty
- `summary.json` — headline JSON
