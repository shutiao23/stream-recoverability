# RED TEAM: W1-B station ingest QC

Date: 2026-08-26
Role: Implementer B (adversarial competing QC). Production files were not edited.
Target of the attack: a literal station ingest gate that NA-izes values `< -5` or `> 45` °C and rejects only when that NA-ized share exceeds 1%.

## Verdict

The 1% physical-range rule **accepts** USGS `13343000` on Clearwater. That station has exactly two NWIS sentinels in the value field. Those two numbers are enough to collapse donor covariance and to send later-year donor MAE into `10^4` °C. Competing code rejects on **any** NWIS numeric sentinel in the value field, before approval filtering, and does not drop the other three Clearwater stations.

## Attack 1 — 1% misses Clearwater (numeric proof)

File: `results/framework/public_rivers/clearwater_river_huc17_daily_wide.csv`
Station: `13343000`

| quantity | value |
| --- | ---: |
| numeric values in the column | 1848 |
| values equal to `-999999` | 2 |
| values `< -5` or `> 45` °C | 2 (the same two cells) |
| sentinel / range-NA proportion | 2 / 1848 = **0.00108225** (0.108225%) |
| 1% reject threshold | 0.01 |
| sentinels needed to trip 1% | floor(0.01 × 1848) + 1 = **19** |
| shortfall | **17** sentinels |

Literal gate: `0.00108225 < 0.01` → **`accepted`**.

Long NWIS cache (`data/public_rivers/nwis/13343000_2000-01-01_2024-12-31.csv`) is the same 1848 rows. The two bad cells are:

```
2021-01-04  -999999.0  ['P', 'Dis']
2021-01-05  -999999.0  ['P', 'Dis']
```

**Stricter competing rule.** Scan the raw value field first. If any finite number is in `{-999999, -99999, -9999, 9999, 99999, 999999}` or is an integer-valued `|x| ≥ 9999`, the station is `rejected_sentinel`. Zero tolerance. The 1% bucket remains only for true physical-range outliers after sentinels have been removed. `0.0` is never a sentinel.

### Why “NA-ize and accept” still poisons covariance

On the overlapping days of `13343000` vs `13342500`:

| statistic | with the two `-999999` | after sentinel → NA |
| --- | ---: | ---: |
| n overlap | 1835 | 1833 |
| Pearson corr | **0.076** | **0.997** |
| donor mean °C | **−1079.6** | 10.31 |
| donor std °C | **33005** | 2.87 |

`np.linalg.lstsq` on the full overlap shrinks the donor coefficient to `~6e-6` (the intercept eats the series). That is not the production failure mode. Production splits by year (`real_river_checks.year_split`, 70% of calendar years). The two sentinels fall in **2021, a test year**. Train still sees a real coefficient; test then multiplies that coefficient by `-999999`. `leave_one_year_scores.csv`:

| station | observed MAE °C | observed skill vs climatology |
| --- | ---: | ---: |
| 13340000 | 66332 | −10033 |
| 13341050 | 8188 | −2607 |
| 13342500 | 9701 | −2863 |
| 13343000 | 10811 | −0.05 |

The other three stations are physically ordinary. They explode because `13343000` remains a **donor** with a finite sentinel. A QC that NA-izes two cells and then **accepts** the station still leaves any consumer of the original wide CSV poisoned. Production scoring reads that CSV with `wide.to_numpy(dtype=float)`.

Approve-first is a second miss. Of 1848 long rows, 1846 are `['A']` and contain **zero** sentinels. Filtering to Approved and then applying 1% also **accepts**. Competing code rejects because the value field contained sentinels, not because the approved subset failed 1%.

## Attack 2 — other sentinels

NWIS daily JSON stores missing as `-999999` (see `13343000`, `02081022`, `08363510`, Missouri v2 wides). Adjacent codes `-99999`, `-9999`, `99999`, `9999` must be in the same exact-match set. Integer-valued `|x| ≥ 9999` catches formatting variants (`-999999.0`).

Do **not** add `0`. Ice plateaus and true freezing are `0.0`. Hub'Eau feeds that encode missing as 0 are a separate provider contract; treating 0 °C as a sentinel false-rejects winter stations (Clearwater `13341050` already stores a real `0.0`).

Ice is a **qualifier**, not a numeric sentinel. `Ice` / `Ice***` → flag `ice_affected`, keep the value if it is otherwise approved and in range. Equipment (`Eqp`) and discontinued (`Dis`) are non-approved and NA'd; they are not extra sentinel numbers.

## Attack 3 — approval codes, two APIs, and `quality_approved`

| API | field | keep | drop | flagged keep |
| --- | --- | --- | --- | --- |
| NWIS dv (`waterservices/.../dv`) | `qualifiers` list / RDB `*_cd` | `A` | `P`, `Eqp`, `Dis` | `A` + `e` / `E` / `Estimat*` |
| Water Data API / OGC daily | `approval_status` | `Approved` | `Provisional` | `Approved` + estimated qualifier; `Estimated` as status |

Estimated-approved is **not** a provisional drop. Keep the value, set `accepted_with_flags` / `estimated_approved`. Confirmatory production already does this as `qc_status=approved_estimated` (`parse_usgs_daily_values`). A gate that drops every non-`A`-only token loses those days.

`Estimated` as `approval_status` is not in confirmatory's allowed set. Production does:

```python
if approval not in {"Approved", "Provisional"}:
    raise ValueError(...)
```

That is a crash, not a flag. Competing code keeps Estimated-as-status as flagged, not as provisional NA.

**Do not treat `quality.py`'s `quality_approved` as USGS approval.** It is a documented legacy alias of `analysis_eligible` (`paper/terminology.md`). `assign_observation_qc` sets it from `natural_observed`. A column of `True` means “row exists,” not “USGS A.” Competing code records `approval_source=ignored_quality_approved_not_usgs` and never uses that column to keep a `P` row.

Wide files have **no** qualifier column (`public_temperature.river_wide_panel` copies only `date` and `temperature_c`). Approval cannot be reconstructed from `*_daily_wide.csv`. Layout must be accepted, but approval is `absent`.

## Attack 4 — constant run > 14 days

Flag `suspect_constant_run`. Do not auto-reject.

Clearwater `13340000` has a **41-day** constant run and `13341050` a **19-day** run. Both are otherwise in-range. Auto-reject would drop usable stations. A 20-day winter `0.0` plateau (ice) and a 20-day sensor flatline at `12.0` get the same flag. Reject only if a hard reject is already true (sentinel, range > 1%, no evaluable year).

## Attack 5 — jump > 10 °C

Flag `suspect_jump` on **consecutive calendar-day** `|x_t − x_{t−1}| > 10`. Do not reject. Weather fronts at some sites are real.

Do **not** use `|x − median| > 10`. A station that moves from 2 °C to 22 °C over three weeks has seasonal distance from the median above 10 °C and **no** day-to-day jump. That rule would flag ordinary summers.

## Attack 6 — wide vs long, both APIs

Clearwater production artifact is **wide**. The download cache is **long** (`site_id,date,temperature_c,qualifier`). OGC daily (`public_temperature._usgs_ogc_daily`) is long with a qualifier string and **no** `approval_status`. NWIS JSON (`nwis_daily_temperature`) is long with a Python-repr qualifier list (`"['P', 'Dis']"`). Water Data / confirmatory is long with `approval_status ∈ {Approved, Provisional}`.

Competing QC accepts both layouts and both qualifier dialects. Verdicts for a sentinel station must agree across wide and long. Production currently applies **no** station gate on either path before `score_rivers`.

## Attack 7 — whole-river drop vs station drop

This QC emits **one row per station**. No network verdict.

Production dropped the river after seeing the MAE. `public_river_operator_ablation.py` says “Clearwater is dropped when donor MAE is physically impossible.” `leave_one_river_out_without_clearwater.csv` exists with no writer. `overlap.csv` already had an input rule (`complete_enough`) that Clearwater fails by one concurrent day; Suwannee fails too and was kept because its MAE looked ordinary.

Correct action on this gate: `13343000` → `rejected_sentinel`. `13340000` / `13341050` / `13342500` stay `accepted` or `accepted_with_flags`. Dropping the river throws away three usable donors.

## Attack 8 — units

Do not assume Kelvin vs Celsius from the parameter code. Convert only when the **series median** is near 273 K (here: median in [260, 320] and ≥80% of finite non-sentinel values in that band). A Celsius series with a single 273 spike is a range NA, not a unit conversion. `0` is 0 °C, not “missing Kelvin.”

Public download assumes `00010` is already °C (`unit_of_measure: degC` in the legacy RDB parser). If a Kelvin series leaked, every value would be `> 45`, the 1% rule would reject the whole station as `rejected_sentinel`, and the report would lie about the reason. Competing code labels `converted_kelvin_median_near_273`.

## Predicted production bugs

1. **No ingest QC on the public-river path.** `nwis_daily_temperature` / `_usgs_ogc_daily` run `pd.to_numeric` and keep `-999999`. `river_wide_panel` pivots those floats. `scripts/47` writes the wide CSV. `river_station_scores` does `wide.to_numpy(dtype=float)` with no sentinel mask. This is the 6.6×10^4 °C MAE.

2. **Literal 1% gate accepts `13343000`.** 2/1848 = 0.108% < 1%. Need 19 sentinels to trip the spec as written. If Implementer A NA-izes then accepts, the QC report looks clean while every reader of the original wide still sees `-999999`.

3. **Approve-first hides the sentinel.** The two bad rows are `P`/`Dis`. Approved-only analysis of the long file sees 1846 clean °C and accepts. The wide file, which lost the qualifier, still carries `-999999`.

4. **Qualifiers are dropped at the wide pivot.** `river_wide_panel` keeps `temperature_c` only. Station ingest that only understands long+qualifier will disagree with the file the ablation actually scores.

5. **`quality_approved` is not USGS `A`.** Using it as an approval filter keeps every observed row, including sentinels and provisionals, on any path that went through `assign_observation_qc`.

6. **Estimated-as-status crashes confirmatory.** `approval not in {Approved, Provisional}` raises. Estimated-approved via qualifier is kept. The two APIs are not the same contract.

7. **OGC download does not store `approval_status`.** `_usgs_ogc_daily` writes `qualifier` only. A Water Data gate that requires `approval_status` will treat the public OGC cache as unqualified.

8. **Whole-river peek-and-drop.** Ablation threshold `INSANE_DONOR_MAE_C = 50` fires after scores. The ingest failure is station `13343000`, not river `clearwater_river_huc17`. The other three stations have constant-run flags (41 d / 19 d / 14 d) and no sentinels.

9. **`13343000` has zero years with ≥300 days.** Even without sentinels it is not evaluable under the year rule (seasonal fragments, max year 197 days). Sentinel reject must still win so the reason is not filed as coverage.

10. **Jump-from-median and 0-as-missing** will false-reject real winter/summer series if someone “tightens” the spec without the attacks above.

## Competing outputs

- `scratch/adversarial/w1b/ingest_qc.py`
- `scratch/adversarial/w1b/test_ingest_qc.py`
- `scratch/adversarial/w1b/ingest_qc_report.csv` / `clearwater_qc.csv` (station rows only)

Required verdict: `13343000` → `rejected_sentinel`. Naive 1% column on that row → `accepted`.
