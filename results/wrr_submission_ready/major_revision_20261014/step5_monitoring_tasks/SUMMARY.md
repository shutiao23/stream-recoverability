# Step 5 — monitoring-matched tasks (status)

## 5a Arm and anomalous-year splits (done)

Artifact: `arm_and_thermal_contrasts.csv`

| Panel / stratum | Δ vs length @70%/0.5°C (pp) | CI |
|---|---|---|
| wave-2 pooled | −6.01 | [−7.08, −5.04] |
| wave-2 **empirical** | **−0.80** | [−1.59, −0.35] |
| wave-2 stratified | −8.96 | [−10.37, −7.52] |
| reserved empirical | −0.71 | [−2.36, +0.03] (includes 0) |
| wave-2 anomalous-warm | −8.58 | [−10.52, −6.73] |

**Interpretation:** Pooled designed-panel gains are driven by stratified pressure outages. Empirical-arm gains are an order of magnitude smaller; reserved empirical still includes zero. Do not quote −5.9 pp as expected real-fault benefit.

## 5b Full-year calendar replay + co-failure (exploratory probe done)

Artifact: `calendar_replay_cofailure/`

Intact annual missingness calendars from real incomplete years transplanted by DOY onto complete years at the same station; donors optionally receive the same calendar.

| Donor co-fail fraction | n (14 nets) | mean \|err\| donor | mean \|err\| clim | peak−length @70% (pp) |
|---|---|---|---|---|
| 0.0 (target only) | 177 | 0.09 | 0.11 | −0.81 [−3.08, 0.00] |
| 0.5 | 177 | 0.16 | 0.11 | 0.00 |
| 1.0 | 177 | **0.39** | 0.11 | 0.00 |

**Interpretation:** Real annual calendars in this probe are often mild (base consequential rates ~4–7%). When all donors share the outage, donor reconstruction collapses toward (and past) climatology — neighbour resilience is conditional. Peak-overlap vs length contrast is small/unstable on these mild calendars (consistent with empirical-arm attenuation). **Not sealed; may not enter abstract.**

## Still open for full Step 5 closure

- Expand calendar replay beyond the 16-network cap; report provider-separate effects
- Train-on-ordinary / test-on-anomalous (labels currently evaluation-only)
- Explicit abstention behaviour under co-failure (does the screen refuse when donors die?)
