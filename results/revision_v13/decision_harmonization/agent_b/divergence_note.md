# Divergence note — agent_a vs agent_b, t08 downstream thermal metrics

Both agents ran the same overall experiment (downstream thermal-regime distortion of the
XGBoost B_union_D gap reconstruction) but with different implementations. Numbers from the
two agents are **not directly comparable** and should never be pooled. Key differences:

## 1. Network/station/placement panels

| aspect | agent_a | agent_b |
|---|---|---|
| networks | 15 first-confirmation QC networks with the most scored station-gaps | 15 networks — the reviewer-completion empirical roster (all 15 in `confirmation_daily_qc`) |
| stations | 131 | 117 |
| station-gaps | 393 (117 per horizon × 3 horizons) | 351 (117 per horizon) |
| placements | **1,965** (5 per station-gap) | **1,755** (5 per station-gap) |
| shared networks | 11 of 15, with **identical per-network rosters** (1530 placements in both agents): arso_sava, arso_savinja, foen_aare_aaregebiet, gkd_bayern_donau, gkd_bayern_isar, gkd_bayern_main, huc8_02040101, huc8_05030103, huc8_17090004, lubw_neckar, usgs_missouri_river_huc10 | same |

Agent_a selected networks by "most scored station-gaps" and added 4 US huc8 networks
(huc8_02040104 90, huc8_03110206 75, huc8_10020007 120, huc8_17090001 150 = 435 placements)
that agent_b did not score; agent_b added arso_bistrica (60), lubw_rhein (60),
rws_rijn_lek_nederrijn (45) and usgs_snake_river_huc4_1706 (60) = 225 placements that
agent_a did not. Hence 1965 = 1530 + 435 vs 1755 = 1530 + 225; on the 11 shared networks
the two panels are identical (verified placement by placement).

## 2. Metric window definition

- **agent_a**: metrics computed on the **whole evaluation record** with one gap filled at a
  time (all non-gap days keep observed truth).
- **agent_b**: metrics computed on a **365-day window centred on the gap centre** (gap fully
  inside the window; windows clipped to the panel range).

This is the main reason per-metric absolute errors differ between agents (e.g. agent_a
annual-mean distortion ≈ 0.011 °C vs agent_b ≈ 0.093 °C: agent_b's 90-day gaps occupy 25%
of its 365-day window, whereas the same gap is ~1.2% of agent_a's multi-year record).

## 3. Untreated baseline ("no recovery")

- **agent_a**: untreated gaps are filled with **climatology** (day-of-year medians from
  training). "No treatment" = climatology fill.
- **agent_b**: untreated gaps are **dropped (no-fill)**, the status quo for downstream users.

Both agents additionally evaluate a no-fill variant (agent_b: `*_missing` columns; agent_a:
not the budget baseline). The two budget experiments therefore answer different questions:
"recovery vs climatology fill" (agent_a) vs "recovery vs dropping the gap days" (agent_b).

## 4. Risk score

- **agent_a**: `empirical_transfer_prediction` matched by exact gap start, else
  station-gap-season, with the t01 fallback chain; 0.96 of placements supported beyond the
  network-mean fallback. All 1965 placements carry a risk score.
- **agent_b**: same source, averaged to the station-gap level; only **270 of 351**
  station-gaps carry a score (reviewer roster subset). Budget experiments restricted to the
  common 270-unit pool (261 for amplitude).

## 5. Budget experiment

| aspect | agent_a | agent_b |
|---|---|---|
| unit | placement (393 of 1965 = 20%) | station-gap (54 of 270 = 20%) |
| default | climatology fill | no-fill (drop gap days) |
| selection score | per-placement empirical transfer risk | per-station-gap mean empirical transfer risk / gap length |
| random | 200 draws (mean ± sd) | 20 draws (mean ± sd) |
| overlapping placements | filled deterministically (recon wins over climatology) | not applicable (station-gap budget, disjoint) |
| per-metric n | 1965 (1950 for summer metrics/amplitude) | 270 (261 amplitude) |

## 6. Consequences observed in the numbers

- **Sign of budget reductions flips for threshold/extreme metrics.** Under the agent_a
  climatology default, the risk policy has negative reductions for degree days (−17.9 %),
  days>20 (−22.2 %), days>25 (−42.5 %), amplitude (−33.8 %), summer mean (−23.0 %)
  (reconstruction is worse than climatology on the long summer gaps the risk policy
  targets). Under the agent_b no-fill default, the same metric families show large positive
  reductions (degree days +39.5 %, days>20 +30.8 %, p90 +30.7 %, trend +34.8 %). Both are
  internally consistent: climatology already captures the seasonal cycle (so XGBoost adds
  little on long gaps, and its cold peak bias flips threshold crossings), while no-fill
  destroys the gap days entirely (so any fill helps).
- **Level of per-placement distortion differs** (metric window, above): agent_a amplitude
  mean |err| 0.0246 °C vs agent_b 0.0386 °C; agent_a trend 0.0061 vs agent_b 0.0831 °C/yr.
- **Risk→distortion correlation direction differs for phase and trend** (agent_a
  network-level ρ phase −0.20, trend −0.09; agent_b phase +0.73, trend +0.33): agent_b's
  windowed metric errors are dominated by gap-length mechanics, agent_a's by the
  reconstruction's annual-cycle properties. Neither is "wrong"; they measure different
  objects.

## 7. Recommendation for the manuscript

Report the two baselines as a deliberate robustness contrast: (i) recovery-vs-no-fill
(agent_b, per-station-gap budget) for the "is filling better than dropping?" question, and
(ii) recovery-vs-climatology (agent_a, per-placement budget) for the "does the learned fill
beat the naive seasonal fill on the hardest gaps?" question. Never average the two panels.
See `budget_joint_table.csv` for the aligned policy×metric×default table.
