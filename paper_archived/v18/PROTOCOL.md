# v18 experiment protocol

The v17 protocol (`paper/v17/PROTOCOL.md`) is unchanged and its freeze stands.
This file records what was added after the reserved panel was opened, which is
why none of it is confirmatory.

## Standing rule added in this round

19. **A panel that cannot be scored is still a population.** Records that carry
    no truth cannot produce an error rate, but they can produce a decision, a
    composition and a transported risk. A study whose rule never touches them
    has not been deployed, only simulated. Where a number on that panel is
    model-based it is labelled as an extrapolation and the exchangeability it
    assumes is tested separately.
20. **A screening rule is specified with its strata.** Selecting on difficulty
    selects on whatever difficulty correlates with. Retention by covariate is
    reported alongside the error rate, and the threshold is applied within
    stratum unless there is a reason not to.
21. **A failed prediction is a finding.** Three of the predictions declared for
    this round were not met. Each is reported with the diagnosis it forced, and
    two of the three produced a better statement of the law than the prediction
    would have.

## Steps

| Step | What it settles | Script | Artifact | Status |
|---|---|---|---|---|
| E0 | Correct the imputed limit of the incumbent from 91 to 140 days and re-run every artifact that used it | `frontier.py`, then 184/187/192/194/195/198/193 | `step7_frontier/`, `step10_confirmation/` | done — the incumbent's retention at that point rises from 74.0% to 85.1% and the screen's advantage there falls from 6.2 to 4.4 points |
| E1 | When real outages happen, and what the maintenance calendar is worth | `scripts/210_v18_outage_seasonality.py` | `e1_outage_seasonality/` | done — outages of 90 d and longer start Sep–Jan (72.3%, p = 9.5e-14); shorter ones are uniform; a spring calendar costs +4.43 points |
| E2 | The rules applied to 2,422 real incomplete station-years | `scripts/211_v18_archive_deployment.py` | `e2_archive_deployment/` | done — 15.1% disagreement; the published imputed limit admits 17 years with the peak wholly unobserved |
| E3+E6 | Extended endpoint table: sine-fit parameters and the hottest-*k* family, on the same realizations | `scripts/212_v18_endpoint_cases.py` | `endpoint_cases.parquet` | done — 51,524 cases, identical to the v17 case table |
| E4 | Representativeness of the retained archive, and the price of fixing it | `scripts/213_v18_representativeness.py` | `e4_representativeness/` | done — the screen tilts against high elevation (ρ = −0.27 reserved); balancing costs 0.31 points |
| E3 | The axis comparison on Johnson et al.'s own estimands | `scripts/214_v18_sine_endpoints.py` | `e3_sine_endpoints/` | done — length wins on the fitted mean, influence weighting on the amplitude and phase; one declared prediction failed |
| E6 | Support width as a continuous knob, and the conditioning-window matrix | `scripts/215_v18_support_width.py` | `e6_support_width/` | done — crossover 91.0 days; two declared predictions failed and produced the dilation result |
| E7 | Is missingness informative? | `scripts/216_v18_informative_missingness.py` | `e7_informative_missingness/` | done — weakly, and bounded well below the tolerance |
| E5a | Coordinates for all 457 stations | `scripts/217_v18_station_coordinates.py` | `e5_air_forcing/coordinate_coverage.csv` | done — 457/457 |
| E5b | NASA POWER daily air temperature, 1981–2026 | `scripts/218_v18_air_forcing.py` | `data/interim/v18_air_forcing.parquet` | done — 7.6 M values, 16,679 days per station |
| E5c | Does the result survive the field's own reconstruction? | `scripts/219_v18_air_sensitivity.py` | `e5_air_forcing/` | done — air support 2.3% → 98.6%; the axis contrast is unchanged; the incumbent is not rescued by an always-air pairing |
| F | Figures | `scripts/220_v18_figures.py`, `scripts/205_v17_drawio_export.py` | `figures/v18/`, `figures/v17/f*.pdf` | done |
| A | Audit every v18 number in the manuscript against its artifact | `scripts/221_v18_audit_manuscript.py` | `results/v18_closure/manuscript_audit.json` | done — run by the test suite |

## Reproduction

```
# v17 artifacts with the corrected incumbent limit
python3 scripts/184_v17_screen_frontier.py
python3 scripts/187_v17_confirm.py
python3 scripts/192_v17_paper_tables.py
python3 scripts/194_v17_baseline_strength.py
python3 scripts/195_v17_simple_rule.py
python3 scripts/198_v17_weighting.py
python3 scripts/193_v17_paper_numbers.py

# v18 closure programme
python3 scripts/210_v18_outage_seasonality.py
python3 scripts/211_v18_archive_deployment.py
python3 scripts/212_v18_endpoint_cases.py --workers 96
python3 scripts/213_v18_representativeness.py
python3 scripts/214_v18_sine_endpoints.py
python3 scripts/215_v18_support_width.py
python3 scripts/216_v18_informative_missingness.py

# air forcing: coordinates, download, sensitivity
python3 scripts/217_v18_station_coordinates.py
python3 scripts/218_v18_air_forcing.py
STREAM_AIR_FORCING=data/interim/v18_air_forcing.parquet \
    python3 scripts/181_v17_cases.py --workers 40 --out cases_air.parquet
python3 scripts/219_v18_air_sensitivity.py

# figures and audit
python3 scripts/220_v18_figures.py
make figures-drawio
python3 scripts/221_v18_audit_manuscript.py
python3 -m pytest tests/test_v18_closure.py
```

The two steps that reach the network are `217` (USGS NWIS and ARSO station
feeds) and `218` (NASA POWER); both write to `data/interim/` and everything
downstream reads from there.
