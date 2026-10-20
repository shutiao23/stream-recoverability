# Novelty comparison for the WRR manuscript (adversarial finding F20)

Scope: verify the works that compete directly with `paper/wrr/wrr_manuscript.tex`,
find any others at least as relevant, and state honestly what the manuscript's
claims already have prior art behind them.

Revision examined: `paper/wrr/wrr_manuscript.tex`,
sha256 `5f91dcbc2619b0776b216f84b5fd1ef3007f593ab60d8b14bdd64eb38aaa01e0`,
1450 lines, mtime 2026-10-12T10:09:22Z. **The file was edited while this review was
running** (it grew from 1388 to 1450 lines between my first and second read), so
every line number below refers to this revision only; re-check before applying.

Nothing was edited. Writes were limited to
`docs/reviews/wrr_novelty_comparison.md`, `paper/wrr/references.bib` (the entries formerly in `references_additions.bib` were merged there on 2026-10-20),
and `scratch/novelty_check/`.

Verification method: every work below was resolved through the Crossref REST API
(`api.crossref.org/works/<doi>`), the OpenAlex API, or DataCite, and — where the
content mattered — through a fetched copy of the work itself (publisher HTML,
repository metadata, or the author's institutional page). No citation, DOI,
quote, year, or journal in this report comes from memory. The verification
commands and raw responses are in `scratch/novelty_check/` (`verify_doi.py`,
`search_crossref.py`, `oa_search.py`, `beaufort_text.txt`, `guidance.txt`,
`ckyyb_en.html`).

---

## 1. Verified works

Directly competing or immediately adjacent (Group A):

| ID | Full citation | DOI / URL |
|----|---------------|-----------|
| A1 | Grey, V., Hatt, B. E., Fletcher, T. D., Smith-Miles, K., & Coleman, R. A. (2024). Analysis of irregularly sampled stream temperature time series: challenges and solutions. *Journal of Hydrology*, 636, 131244. | [10.1016/j.jhydrol.2024.131244](https://doi.org/10.1016/j.jhydrol.2024.131244) — already in `references.bib`, re-verified |
| A2 | Johnson, Z. C., Johnson, B. G., Briggs, M. A., Snyder, C. D., Hitt, N. P., & Devine, W. D. (2021). Heed the data gap: guidelines for using incomplete datasets in annual stream temperature analyses. *Ecological Indicators*, 122, 107229. (USGS Publications Warehouse 70216999.) | [10.1016/j.ecolind.2020.107229](https://doi.org/10.1016/j.ecolind.2020.107229) — already in `references.bib`, re-verified |
| A3 | Beaufort, A., Diamond, J. S., Sauquet, E., & Moatar, F. (2022). Spatial extrapolation of stream thermal peaks using heterogeneous time series at a national scale. *Hydrology and Earth System Sciences*, 26(13), 3477–3495. | [10.5194/hess-26-3477-2022](https://doi.org/10.5194/hess-26-3477-2022) — already in `references.bib`, re-verified; full text read |
| A4 | Huang, F., Qian, B., & Ochoa, C. G. (2023). Long-term river water temperature reconstruction and investigation: a case study of the Dongting Lake Basin, China. *Journal of Hydrology*, 616, 128857. | [10.1016/j.jhydrol.2022.128857](https://doi.org/10.1016/j.jhydrol.2022.128857) — already in `references.bib`, re-verified |
| A5 | Hare, D. K., Benz, S. A., Kurylyk, B. L., Johnson, Z. C., Terry, N. C., & Helton, A. M. (2023). Paired air and stream temperature analysis (PASTA) to evaluate groundwater influence on streams. *Water Resources Research*, 59(4), e2022WR033912. | [10.1029/2022WR033912](https://doi.org/10.1029/2022WR033912) — **new** |
| A6 | Jackson, F. L., Fryer, R. J., Stirling, D., & Malcolm, I. A. (2025). The influence of equipment bias on reported temperature trends: implications for river temperature monitoring networks. *River Research and Applications*, 41(8), 1604–1615. | [10.1002/rra.70012](https://doi.org/10.1002/rra.70012) — **new** |
| A7 | Sanikhani, H., Khorsandi, M., Déry, S. J., & St-Hilaire, A. (2026). Large-scale climate teleconnections and multiscale controls on river water temperature. *Journal of Hydrology*, 679, 136301. | [10.1016/j.jhydrol.2026.136301](https://doi.org/10.1016/j.jhydrol.2026.136301) — **new** |
| A8 | Wang, S.-h. (2025). Long-term reconstruction and variation characteristics of water temperature in mainstream Yangtze River. *Journal of Changjiang River Scientific Research Institute*, 42(10), 54–63. | doi [10.11988/ckyyb.20240856](https://doi.org/10.11988/ckyyb.20240856) (resolves to the journal's own page; not registered with Crossref — see §8) — **new** |
| A9 | You, Y., Wang, Y., Tao, J., Zhao, L., Wang, S., Zhang, Y., Meng, C., & Wang, D. (2026). Unveiling river thermal regimes in the Yangtze river basin, China, with a hybrid deep learning model. *Journal of Environmental Management*, 398, 128460. | [10.1016/j.jenvman.2025.128460](https://doi.org/10.1016/j.jenvman.2025.128460) — **new, bibliographic record only** |
| A10 | Bai, S., Fang, Z., & Chen, J. (2026). Risk-controlling predictive sets for time-series events under selective observation with finite-sample guarantees. *Axioms*, 15(9), 706. | [10.3390/axioms15090706](https://doi.org/10.3390/axioms15090706) — **new** |
| A11 | Angelopoulos, A. N., Bates, S., Fisch, A., Lei, L., & Schuster, T. (2022). Conformal risk control. arXiv:2208.02814. | [10.48550/arXiv.2208.02814](https://doi.org/10.48550/arXiv.2208.02814) — **new; methods basis, not a competitor** |

Screening-practice precedent (Group B): Zhang, X., Alexander, L., Hegerl, G. C.,
Jones, P., Klein Tank, A., Peterson, T. C., Trewin, B., & Zwiers, F. W. (2011).
Indices for monitoring changes in extremes based on daily temperature and
precipitation data. *WIREs Climate Change*, 2(6), 851–870.
[10.1002/wcc.147](https://doi.org/10.1002/wcc.147) — **new**.

---

## 2. Table A — endpoint, data/region, method

| ID | Endpoint studied | Data / region | Method |
|----|------------------|---------------|--------|
| A1 | Long-term **trends** and **means/summary statistics** (site means); no annual extreme reported | Monte-Carlo simulation built to mimic tropical, temperate and cold stream-temperature monitoring records; time-of-day and seasonal sampling artefacts | Monte-Carlo simulation; several candidate analysis models compared under each artefact |
| A2 | Sine-fit **annual mean, phase, amplitude** (and imputation as a treatment) | Headwater stream-temperature sites, Pacific Northwest and Mid-Atlantic USA | Constructed consecutive missing blocks (7–357 days) on complete 365-day records; sine-wave regressions; probability of falling inside the 95–99% CI of the complete-record value |
| A3 | **Thermal peak** `Tp` = interannual average of the mean temperature of the 30 hottest consecutive days of each year | ~1700 stream-temperature stations, France and Corsica, 2009–2017 (45 million hourly measurements); 105 800 RHT reaches modelled | Data harmonisation + outlier filtering; station-specific stream–air regression ("climate correction") to fill gaps; permutation test with 1–9 **artificially removed whole years** at 30 reference stations; regression / ANN / random forest / multi-model spatial extrapolation |
| A4 | **Monthly** water temperature (aggregated to annual means), trends, periodicity, complexity; no daily or extreme statistic | Dongting Lake Basin, China (Xiangjiang, Zishui, Yuanjiang, Lishui); 1960–2020 reconstruction | LSTM driven by air temperature, evaporation and streamflow, trained on historical observations; TFPW Mann-Kendall, Sen's slope, wavelet transform, moving sample entropy |
| A5 | Sine-fit **phase and amplitude** of paired daily air and stream temperature, by calendar or water year; stream–air regression slope | Global/generic: linked public stream-temperature datasets plus user uploads; Daymet air temperature where not measured | Web tool (`cuahsi.shinyapps.io/pasta`) fitting sinusoidal curves per year and linear stream–air regressions |
| A6 | Long-term **trend** in river temperature, and how much of it is an equipment artefact | Girnock Burn, Scotland; one 35-year daily series; historical vs contemporary loggers | Calibration experiment against a calibrated internal reference logger; raw vs bias-corrected trend comparison |
| A7 | Reconstructed **daily** water temperature used to compute summer (JAS) anomalies and **exceedance frequencies above 20 °C**; ENSO/PDO coherence | Cold-region Pacific watershed (regulated and natural stations); 1950–2024 reconstruction, 1950–2021 analysis | Hybrid Air2Stream reconstruction of gap-containing observed records, then continuous/bivariate/partial/multiple wavelet coherence |
| A8 | Reconstructed **daily** water temperature -> decadal warming rates and monthly-scale attribution | Seven hydrological stations, mainstream Yangtze River; 1980–2022 | XGBoost on Hydrological Yearbook measurements plus ERA5-Land reanalysis; RMSE/R² validation; trend and correlation analysis |
| A9 | River thermal regimes (per title); content not retrievable | Yangtze River basin, China | Hybrid deep learning (per title) |
| A10 | Risk control for **predictive sets on time-series events under selective observation** (labels exist only when an event triggers observation) | Synthetic maintenance/financial studies; a real dependent sensor series; 4000 selection-level validation runs | Selective-observation weighted risk control: Horvitz–Thompson losses, randomized audits, martingale-mixture boundary; finite-sample control under temporal dependence |
| A11 | Distribution-free control of any **monotone risk** (not coverage alone) | Methods paper; image segmentation and other benchmarks | Conformal risk control: choose the set size by a calibration bound on the risk |
| B1 | ETCCDI extreme indices (percentile- and threshold-based daily temperature/precipitation extremes) | Global station networks | Review of index definitions and of the obstacles to robust calculation, including data-completeness handling |

## 3. Table B — what it already answers, what this manuscript adds, what stays unverified

| ID | What it already answers (relative to the manuscript's claims) | What this manuscript adds beyond it | What remains unverified here |
|----|---------------------------------------------------------------|--------------------------------------|------------------------------|
| A1 | **That irregular sampling and sampling artefacts bias derived statistics** — but for trends and site means. Also answers "which analysis model is robust to these artefacts": models with an explicit seasonal component recovered trends and means with high confidence under almost all artefacts tested. Structural time-of-day sampling bias is the exception that remains damaging. | The extreme half of the estimand family (hottest-*k*-day mean), the estimand-dependence of the governing axis, within-year gap placement as a designed contrast, and an archive-admission decision rather than an estimation correction. | Whether the full text also examines an annual extreme or a maximum-type statistic. The published abstract names only trends and means/summary statistics ("site means"); the publisher version is behind a captcha and the repository (Minerva/Unimelb handle 11343/348874) exposes metadata but no bitstream. I could not rule out a supplementary extreme-statistic analysis. |
| A2 | **That gap length bounds which annual thermal parameters are estimable, and that the timing of missing data matters.** Verified verbatim from the abstract: "datasets with less than seven weeks of consecutively missing data enabled estimation of all annual signal parameters with reasonable accuracy"; "imputation of missing data expanded this range to approximately 20 weeks"; and "The timing of consecutive missing data points within a year had inconsistent effects on annual thermal parameter estimates among regions, years, and individual parameters." | The *decomposition* of that inconsistent timing effect: the manuscript attributes it to the three estimands having different influence functions and predicts in advance which parameter should show a timing effect. Also the annual extreme, which A2 does not score. | 1. The manuscript's quotation at line 1228 ("inconsistently in space and time") could not be matched to the abstract, which says "among regions, years, and individual parameters" — see §5, item 8. 2. The full text (and therefore any timing analysis beyond the abstract) is paywalled and was not read. |
| A3 | **That the error of a target thermal metric under designed gaps can be measured, with and without filling.** At 30 stations with 1–9 artificially removed whole years, the difference in \|bias\| between unfilled and climate-corrected `Tp` grew "from a median of 0.03 °C with 1 year of gaps to 0.25 °C with 8 years of gaps", and corrected biases "remained below 0.25 °C for 75 % of the stations with up to 6 years of introduced gaps". Also **that a climatological peak window can be used to admit partial-season records**: "only 3 % of site years had their hottest 30 d outside of this period", which is why July–August-only agency records were used. | Within-year gap placement (A3's gaps are whole years), the per-station-year admission decision (A3 "declines no station-year" — verified: stations with as little as one year of data are retained), a per-year rather than interannual-mean endpoint, network-level holdout, and a calibrated bound. | Nothing material about A3 is unverified: the full HESS article was fetched and read, and the preprint (`hess-2021-218`) is the same work. |
| A4 | **That long-term thermal records can be reconstructed for data-sparse Chinese basins and that reconstruction is enough for trend analysis** (four Dongting tributaries, monthly 1960–2020, +0.15 °C per decade). | Everything the manuscript does about extremes and admission: A4 reconstructs *monthly* means, so a hottest-30-day statistic is not computable from its product at all, and it contains no admission rule, no designed outage, and no calibrated uncertainty. | Whether the paper reports any completeness criterion for the stations it trained on. The abstract does not; the article is paywalled. The abstract used here was fetched from the co-author's institutional page ([Oregon State Ecohydrology](https://ecohydrology.oregonstate.edu/pubs/long-term-river-water-temperature-reconstruction-and-investigation-case-study-dongting-lake)) and matches an independent aggregator record; I treat it as reliable but second-hand to the publisher. |
| A5 | **That the annual sine-fit parameters the manuscript adopts as its comparison estimands are computed in operational practice**, on calendar or water years, by a public tool that accepts heterogeneous uploaded records ("allowing the repurposing of existing stream temperature data"). | PASTA is a consumer of these estimands, not a screening rule; the manuscript supplies the admission decision PASTA does not make. | Whether PASTA enforces any minimum-completeness rule before fitting a year. The abstract describes none; the tool itself and the full text were not inspected. **Do not claim PASTA fits incomplete years without a criterion unless that is checked.** |
| A6 | **That a long-term river-temperature archive can be wrong for reasons unrelated to gaps**: uncorrected instrument bias produced moderated trends (positive biases pre-1998, negative 1998–2007) in a 35-year Scottish series, and calibration/quality-control procedures are required. | The manuscript's subject is missing-record geometry, not instrument calibration. Their contribution is a competing threat to archive trustworthiness that the manuscript should name and bound, not a competing screening method. | Nothing material about A6 was unverified; the abstract was fetched in full from Crossref/OpenAlex. Note that the manuscript's instrument-error check perturbs the reference series with 0.15 °C of *random* noise (lines 417–420), which does not represent a *systematic, time-varying* instrument bias of the A6 kind. |
| A7 | **That recent published practice reconstructs daily water temperature from gap-containing observations and then computes derived thermal statistics** (summer anomalies, counts of days above 20 °C) with no admission decision at any point. | The manuscript supplies the decision A7 assumes away, and asks whether the derived statistic's error, not the daily series' error, should govern it. | Whether A7 reports a completeness criterion for the records it reconstructed; the abstract describes reconstruction but no screen. |
| A8 | **That Chinese river-temperature reconstruction in the last five years is reconstruction-accuracy-led**: daily XGBoost reconstruction at seven mainstream Yangtze stations (1980–2022), validated by RMSE (0.831–1.021 °C) and R² (0.951–0.987), then used for warming rates. No admission or admissibility analysis. | Same as A7: the screening question, and the extreme statistic (A8 reports warming rates, not a hottest-30-day mean). | The article is in a Chinese-language journal; the abstract and metadata were read from the journal's own English article page. The DOI resolves through doi.org but is absent from Crossref, so the record could not be cross-checked against a DOI registry (see §8). |
| A9 | Nothing could be established about the content. Its title places it in the same recent Chinese Yangtze thermal-regime space as A8. | Unknown. Listed only so that the authors do not re-derive it later. | **Everything except the bibliographic record.** No abstract is available in OpenAlex or via the aggregator page I fetched; ScienceDirect is captcha-blocked. Treat as "exists, unread" — not as a competitor on evidence. |
| A10 | **That distribution-free risk control under *selective observation* is already a solved problem statement in the methods literature** — finite-sample control of population risk when outcomes are observed only under a predictable selection mechanism, with audits restoring identifiability, and with explicit treatment of temporal dependence. Its applications are maintenance/financial/sensor, not environmental archives. | The environmental instantiation: a named annual thermal statistic, gap geometry as the selection mechanism, and admission/abstention as the actions. The manuscript's contribution cannot be "calibrating risk under incomplete observation" as such. | Nothing material about A10 was unverified (Crossref record + full abstract). Its relevance to F20 is positioning, not priority. |
| A11 | **That the calibration object the manuscript uses (a bound on a monotone risk, not just an interval) is a standard, published tool.** | The application and the selection-conditional, network-grouped calibration design — not the machinery. (The repository's own novelty review already notes that the calibration contribution is small relative to the change of conditioning axis; that is an internal assessment, not something I re-derived here.) | The ICLR 2024 venue for this work could not be verified from DataCite (which records the arXiv preprint only: arXiv, 2022, five listed authors). Cite the arXiv version unless the authors verify the proceedings record. |
| B1 | **That data-completeness handling for extreme indices is a recognised problem with statistic-specific conventions** in climate monitoring, and that different indices require different completeness treatment. The specific per-index numeric thresholds are in ETCCDI guidance documents I could not fetch in primary form. | The manuscript's conditioning variable — how much of the *target statistic's own support* is hidden — which B1 does not use; B1's conventions are counts of missing values. | The exact numeric rules (e.g. the "no more than three missing days in a month" convention often attributed to this literature) were **not** verified against a primary source in this session. A verifiable count-based example that *was* fetched: the WMO CCl ET-NCMP *Specification for National Climate Monitoring Products*, v0.6, 21 September 2015, states that a monthly mean temperature and a monthly rainfall total are computed only "if there are fewer than 10% of missing values" ([hadobs.metoffice.gov.uk](https://www.metoffice.gov.uk/hadobs/opace2_tt_ncmp/Draft_Guidance_v0.6.docx)). |

---

## 4. (b) Suggested revised novelty paragraph

Written to the verified record above: 204 words with the citation macros counted
as single words (about 215 words once they expand in print). It claims no priority and no
result that the table does not support. Suggested placement: replacing the
current lines 142–154, with lines 155–157 (the Mauger transfer example) kept as
the illustration that follows.

> Prior work already constrains much of this ground. Incomplete and irregularly
> sampled thermal records bias long-term trends and site means, and model
> structure decides whether an estimate survives the sampling artefacts common in
> monitoring programmes \cite{grey2024}. The length of consecutive missing data
> bounds which annual signal parameters remain estimable, and the guidance
> reporting those bounds also tested timing, finding its effects inconsistent
> across regions, years and parameters \cite{johnson2021}. \citeA{beaufort2022}
> went further on a second axis: they removed whole years artificially at
> reference stations, measured the bias of a target thermal metric with and
> without air-regression filling, and used the climatological position of the
> hottest-30-day window to admit July--August-only records. Equipment bias, a
> non-gap threat to the same archives, can change the direction of reported
> trends \cite{jackson2025}. What remains open is the per-station-year admission
> decision for a named annual statistic: \citeA{beaufort2022} vary gaps only
> between years; \citeA{johnson2021} threshold gap length; \citeA{grey2024}
> address means and trends rather than an annual extreme. We therefore ask
> whether conditioning on the share of the target statistic's own support that a
> gap hides predicts that statistic's error better than gap length does, whether
> the answer depends on the statistic, and whether acting on it changes which
> station-years an archive admits --- answered here with within-year designed
> outages, a network-level holdout and a calibrated admission bound, and reported
> with the regimes in which the gain does not survive.

---

## 5. (c) Sentences to soften

Quoted verbatim from revision `5f91dcbc…`. Line numbers are from that revision.

1. **Lines 152–154.** "Across the completeness thresholds in common use the
   conditioning variable is a property of the record. None is a property of the
   statistic being computed from it, and the transfer does happen in practice:"
   *Problem:* too absolute. Three counterexamples are already in the manuscript's
   own text: the deployment window at lines 136–137 is recommended "to capture
   the thermal maxima" (a rule chosen for the statistic); \citeA{beaufort2022}
   admitted July–August-only records because the hottest 30 days were known to
   fall in a climatological window; and in climate monitoring, completeness
   conventions are statistic-specific (Table B1).
   *Suggested:* "Across the completeness thresholds in common use the
   conditioning variable is a property of the record --- its length, season or
   duration. Where a rule is statistic-aware, it targets the season the statistic
   lives in or the count of missing values; what none of them quantifies is how
   much of the statistic's own support a record contains."

2. **Lines 128–130.** "Between the two sits a decision nobody writes down ---
   whether this station-year may be used at all --- which is made for every
   record in every thermal archive, is made by a rule..."
   *Problem:* "a decision nobody writes down" is contradicted by published
   guidance that does write admission rules down (A2's seven-week/20-week limits;
   A3's implicit summer-window admission). What is rarely written down is an
   *estimand-specific* rule.
   *Suggested:* "...sits a decision that is rarely written down as an
   estimand-specific rule --- whether this station-year may be used at all..."

3. **Lines 142–146.** "The gap-filling literature optimises the accuracy of the
   filled series rather than the admissibility of the completed year
   \cite{mohseni1998,li2017}, and the closest prior work fills incomplete summer
   records so that a thermal peak can be computed, but applies the filling
   uniformly and declines no station-year \cite{beaufort2022}."
   *Problem:* the last clause is accurate but materially incomplete about
   \citeA{beaufort2022}, which is the nearest competitor: they did measure the
   *derived statistic's* error under designed outages (median bias difference
   0.03 °C at one removed year to 0.25 °C at eight; corrected bias <0.25 °C for
   75% of stations up to six removed years) and they did admit partial-season
   records on the climatological position of the hottest-30-day window. A
   reviewer who knows A3 will read the current sentence as selective.
   *Suggested:* "...the closest prior work fills incomplete summer records so
   that a thermal peak can be computed, applies that filling uniformly, declines
   no station-year, and admits July--August-only records on the climatological
   position of the hottest window \cite{beaufort2022}; it also quantifies the
   resulting bias of the thermal peak itself when whole years are removed, which
   is the closest precedent for the designed-outage measurement here."

4. **Lines 180–182.** "Three things make the question answerable now that were not
   available to the studies that raised it."
   *Problem:* designed outages on complete years *were* available and were used
   by \citeA{beaufort2022} (whole years, 30 reference stations). What was not
   available is the combination: within-year gap placement, per-station-year
   admission, network-level holdout, multi-agency panel.
   *Suggested:* "Three things make the question answerable now that the studies
   that raised it did not combine."

5. **Lines 146–152.** "Irregular sampling and sampling artifacts already bias
   mean and trend estimates in stream-temperature series \cite{grey2024}, and
   long-term reconstruction frameworks have been developed for regulated and
   data-sparse basins including Chinese catchments \cite{huang2023}. Those
   studies answer prediction and reconstruction questions; they do not yet close
   the archive-admission question for a named annual estimand."
   *Problem:* defensible, but "answer prediction and reconstruction questions"
   understates \citeA{grey2024}, which answers an estimation-reliability question
   for means and trends and identifies which models are trustworthy. It should be
   clear that the gap is the *extreme* statistic and the *admission* decision,
   not the reliability question in general.
   *Suggested:* add after "estimates in stream-temperature series
   \cite{grey2024}": "--- and identify which model structures remain trustworthy
   for means and trends under those artefacts ---" and, at the end, "they do not
   close the archive-admission question for a named annual extreme."

6. **Line 216 (Table `tab:map`, conditioning axis for completeness guidance).**
   "completeness guidance \cite{johnson2021} & tolerable amount of missing data &
   station-year & outage size"
   *Problem:* \citeA{johnson2021} tested timing as well as length, and reported
   inconsistent timing effects (verified abstract). Labelling the paper's
   conditioning axis as "outage size" alone is what a reviewer will object to.
   *Suggested axis cell:* "outage size (timing tested; effects reported
   inconsistent)".

7. **Line 219 (Table `tab:map`, peak reconstruction row).**
   "peak reconstruction \cite{beaufort2022} & spatial coverage of the thermal
   peak & reach & air regression, applied uniformly"
   *Problem:* omits that the same work used the climatological peak window as an
   admission device and measured target-metric bias under designed gaps.
   *Suggested axis cell:* "air regression applied uniformly; climatological
   summer window used to admit partial-season records".

8. **Lines 1226–1228 (Discussion).** "Its authors observed that the timing of
   missing data affected thermal-signal estimates ``inconsistently in space and
   time''."
   *Problem (quote integrity):* the verified abstract of \citeA{johnson2021}
   reads "The timing of consecutive missing data points within a year had
   inconsistent effects on annual thermal parameter estimates **among regions,
   years, and individual parameters**". "inconsistently in space and time" did
   not appear in either abstract version I retrieved (Crossref has none; OpenAlex
   and the USGS Publications Warehouse abstract agree with each other). It may be
   verbatim in the paywalled full text, but it is currently an unverified
   quotation.
   *Suggested:* either verify the phrase against the full text, or quote what is
   verifiable: ``inconsistent effects ... among regions, years, and individual
   parameters''.

9. **Lines 155–157.** "\citeA{mauger2017}, for example, retain a site-year for a
   mean July temperature only ``when at least 90\% of the days were captured'',
   and then report the maximum weekly maximum temperature from the same
   records."
   *Problem (quote integrity):* the quoted clause was **not** verified in this
   session (Canadian Journal of Fisheries and Aquatic Sciences, paywalled; not
   open in Unpaywall). The internal inconsistency it describes is exactly on
   point, so keep it — but confirm the wording against the PDF before
   resubmission.

10. **Lines 1245–1253 (Discussion).** "The disagreement with the gap-filling
    literature is of a different kind and is not resolved by our result.
    \citeA{beaufort2022} fill every record alike, and on our panel pairing the
    incumbent rule with that treatment makes it worse rather than better
    (Table~\ref{tab:fair})."
    *Problem:* "fill every record alike" is a fair description of the treatment,
    but the paragraph should acknowledge that \citeA{beaufort2022} validated that
    treatment against the *target metric* (A3), otherwise the contrast reads as
    an attack on a straw man.
    *Suggested:* append "Their filling was validated against the target metric
    under whole-year gaps \cite{beaufort2022}; what differs here is that the
    reconstruction is chosen per station-year and the comparison is scored on
    within-year gap geometry."

11. **Lines 75–76 (Abstract).** "Thermal archives are usually screened by
    completeness thresholds that measure outage size, not the support of the
    target statistic."
    *Problem:* "usually" is doing necessary hedging, but two named cases are
    statistic-aware (A3's summer window; the June–August deployment standard at
    lines 136–137). Keep the sentence, but consider "...measure outage size
    rather than the support of the target statistic; the statistic-aware rules
    that do exist target seasons or counts, not support."

---

## 6. (d) Manuscript claims that already have prior art behind them

Stated plainly, because a reviewer will find them:

1. **Incomplete or irregular thermal records bias derived statistics.** A1 (means
   and trends), A3 (a target thermal metric under designed whole-year gaps).
2. **The error of a derived statistic, not of the daily series, is the quantity
   that should be measured.** A3 measured `|Tp,fill − Tp,ref|` and
   `|Tp,gap − Tp,ref|` directly; the manuscript's line 109 framing ("the error of
   a derived thermal statistic, not the error of a daily temperature series") is
   therefore not new as a *stance*, only as a per-year, per-station-year
   application.
3. **Filling helps relative to using observed days alone for the target
   statistic.** A3, quantitatively (0.03 → 0.25 °C median bias difference over
   1–8 removed years).
4. **The timing of missing data matters for annual thermal parameters.** A2
   reported it explicitly and called the effects inconsistent; the manuscript's
   contribution there is the influence-function explanation, not the observation.
5. **Gap length is the right axis for annual means and sine-fit parameters.**
   A2 derived its limits for exactly those parameters; the manuscript's own
   §"Why this agrees with the standing guidance rather than against it" concedes
   this.
6. **The hottest-30-day window is climatologically locatable, and partial-season
   records can still yield a thermal-peak estimate.** A3: the hottest day fell
   within ~28 July–30 August (mean 12 August ± 16 d) and only 3% of site-years
   had their hottest 30 days outside it.
7. **Instrument bias is an independent threat to long-term river-temperature
   archives and must be quality-controlled.** A6.
8. **Completeness conventions are already statistic-specific in monitoring
   practice** (count-based): B1 and the ET-NCMP `v0.6` rule that a monthly mean
   is computed only with <10% missing.
9. **Distribution-free risk control under selective observation** is an existing,
   solved problem statement in the methods literature: A10, A11.

## 7. What appears genuinely new, bounded by the evidence above

These are the only claims the table supports as additions:

1. Making the **share of the target statistic's own support that a gap hides**
   the screening variable for a per-station-year archive-admission decision, with
   the influence function as the stated mechanism.
2. **Within-year gap placement** varied independently of gap length on the same
   complete years, with a support-width sweep and a located crossover — A3 varies
   whole years only, A2 varies length only (timing observed, not designed as the
   conditioning axis).
3. A **per-year extreme** (hottest-*k*-day mean) as the endpoint, where A1/A2/A3
   use means, trends, or an interannual average of the annual peak.
4. **Network-level holdout and a never-used panel** with a calibrated
   (split-conformal) admission/abstention bound tied to a named annual statistic.
5. The **negative result that the gain collapses under the agencies' own gap
   geometry**, which is a finding about archives, not about the method.

---

## 8. Reference verification log, omissions, and search limits

Written to `paper/wrr/references_additions.bib` (8 entries, parsed cleanly by
BibTeX 0.99d with `plain.bst`: 8 `\bibitem`s, no errors). Group A entries are
competing/adjacent prior work; the Group B entry is a screening-practice
precedent; Group C entries are calibration machinery the manuscript uses but does
not cite. Deliberately **not** written to the file:

| Omitted | Why |
|---------|-----|
| "Event-Grouped Calibration for Conformal Streamflow Reconstruction", SSRN, 2026, doi 10.2139/ssrn.7589481 | SSRN preprint; no journal record verified. In scope (conformal + streamflow + reconstruction) but not citable as peer-reviewed work. |
| "Conformal Prediction for Deep Learning Streamflow Forecasting", Zenodo deposit doi 10.5281/zenodo.21925950 | Code/data deposit accompanying an unnamed manuscript; no article record verified. |
| Met Office / WMO CCl ET-NCMP, *Specification for National Climate Monitoring Products*, v0.6, 21 September 2015 (Kennedy, Vincent, Chang'a, Blunden, Braganza, Takeuchi, Ramos, Hechler, Driouech), [docx](https://www.metoffice.gov.uk/hadobs/opace2_tt_ncmp/Draft_Guidance_v0.6.docx) | Fetched and quoted, but it is an undated-as-published draft specification, not a journal article; including it in a WRR bibliography would be a judgement call for the authors. It is cited in this report as practice evidence (the <10% missing rule for monthly means). |
| ETCCDI per-index numeric completeness rules (e.g. the "no more than three missing days in a month" convention) | No primary source could be fetched: the JGR paper that states the criteria is publisher-blocked, the RMIT repository PDF returned an empty body, and the HadEX3 user guide's completeness discussion concerns grid-box selection, not per-station index admissibility. Do not assert these numbers without checking. |
| Oregon DEQ water-quality assessment methodology (data-sufficiency rules for the 7-day-average daily maximum criterion) | `oregon.gov` was unreachable from this environment (HTTP 000); no verification possible. This is a promising lead for regulator-side, statistic-specific sufficiency rules. |
| Shanxi provincial hydrologic-statistics document quoting an annual-statistics rule (compute annual statistics only if incomplete months ≤ 4 and missing months ≤ 2) | The `.docx` fetch returned HTTP 502; the rule is highly relevant (a count-based, statistic-specific quota) but I could not verify the document or the national standard behind it. Worth chasing by the authors; do not cite on this evidence. |
| `10.11988/ckyyb.20240856` (A8) | Valid: `https://doi.org/10.11988/ckyyb.20240856` resolves to `http://ckyyb.crsri.cn/CN/10.11988/ckyyb.20240856`, and that article page was fetched successfully (HTTP 200) with title, author, volume 42(10), pages 54–63, 2025 and the full English abstract; a later re-check of the same URL returned a transient HTTP 502 from the journal server, from which no conclusion should be drawn. The DOI is absent from Crossref and DataCite, so no independent registry record exists to cross-check; the entry in `references_additions.bib` therefore rests on the publisher's own page plus DOI resolution. |
| `you2026` (A9) | Bibliographic fields verified through Crossref (title, journal, volume 398, article 128460, issue date 2026-01, eight authors). Its content is unverified — no abstract retrievable — so cite it only for existence, never for a finding. Note the DOI string says 2025 while the issue year is 2026. |

Also flagged, not omitted: the existing `references.bib` entries for A1–A4 were
re-verified against Crossref and need no correction.

Searches that returned no work conditioning record admission on the support of a
target statistic (documented so the boundary of the claim is known): OpenAlex
relevance and title/abstract searches on missing data × annual maximum × stream
temperature; data-completeness criteria for extreme statistics; "hottest 30-day"
metrics; conformal prediction × streamflow/water temperature/hydrology;
conformal/selective risk control for sensor and environmental data quality;
missing data × extreme-value/return-level estimation; flood-frequency
incomplete-record guidance; and Chinese-language water-temperature reconstruction
and missing-data screening. Nothing surfaced that screens incomplete records by
gap–support overlap. That is a search result, not a proof of absence, and the
report's wording should stay inside it.

Not verified in this session (no access): full texts of A1, A2, A4, A6, A7, A8,
A9; the Mauger et al. (2017) quotation at manuscript line 156; the Johnson et al.
phrase at line 1228.
