# Reference audit, 2026-10-20

Every entry in `paper/wrr/references.bib` was compared, field by field, against
the publisher's own metadata. The method was:

1. resolve each DOI through `https://doi.org/<doi>` with
   `Accept: application/x-bibtex` (the publisher-deposited BibTeX);
2. fetch `https://api.crossref.org/works/<doi>` for the structured record
   (author list, container title, volume, issue, pages, print and online dates);
3. for the four entries without a DOI, fetch the publisher or agency page and
   read the metadata from its `<meta name="citation_*">` block;
4. normalise both sides (LaTeX accents, braces, capitalisation, dash style,
   `--` versus `-`) and compare authors, title, venue, volume, issue, pages, year
   and DOI. A field counts as wrong only when the normalised strings differ.

## Corrections applied

| key | field | was | now | evidence |
|---|---|---|---|---|
| `corona2025` | first author's given names | Corona, Claire R. | Corona, Claudia Rebecca | Crossref deposit 10.5194/hess-29-2521-2025 |
| `corona2025` | last author's given names | Hogue, Terri S. | Hogue, Terri Sue | same |
| `isaak2017` | author 12 | Horan, Dona | Horan, Dona L. | Crossref deposit 10.1002/2017WR020969 |
| `isaak2017` | author 13 | Payne, Sharon L. | Parkes-Payne, Sharon | same; the byline is hyphenated |
| `li2017` | issue | 2 | 1 | Crossref: volume 28, issue 1, print 2017-02 |
| `mauger2015` | last author | Bogan, Daniel | Bogan, Dan | Crossref deposit 10.1016/j.ejrh.2015.07.008 |
| `zaoui2020` | author order | Zaoui, Denis, Hebiri | Denis, Hebiri, Zaoui | arXiv 2006.16597 and HAL hal-02883996 both list that order |
| `wac2024` | section cited | WAC 173-201A-020 and -200 | WAC 173-201A-200 | the legislature's table: 173-201A-020 is "Definitions", 173-201A-200 is "Fresh water designated uses and criteria" |
| `wac2024` | title | added the two section numbers to the title | chapter title only, sections in the note | chapter heading is "Water Quality Standards for Surface Waters of the State of Washington" |
| `nasapower2026` | title and venue | "POWER daily data, T2M (MERRA-2)", "Prediction Of Worldwide Energy Resources project" | product description plus the project's full name, access year in the note | `power.larc.nasa.gov` product naming |

A second defect is not a field error but a citation-management one: eight entries
(`hare2023`, `jackson2025`, `sanikhani2026`, `wang2025`, `you2026`, `zhang2011`,
`angelopoulos2022`, `bai2026`) existed in **both** `references.bib` and
`references_additions.bib`. With `\bibliography{references,references_additions}`
BibTeX keeps the first copy and logs a repeated-entry warning. The additions file
is now a comment-only provenance note, so each entry has one source of truth;
`wrr_manuscript.blg` reports zero warnings after the change.

## Accepted, documented differences

| key | difference | why it is kept |
|---|---|---|
| `caissie2006` | Crossref deposits "Caissie, D."; the entry has "Caissie, Daniel" | the full given name is the author's published name; the initial is an abbreviation, not a different person |
| `zhang2011` | Crossref parses the author as "Tank, Albert Klein"; the entry has "Klein Tank, Albert" | "Klein Tank" is the surname; the Crossref parse splits it wrongly |
| `li2017` | Crossref's BibTeX says 2016; the entry says 2017 | 2016 is the online-first date; the article is in volume 28, issue 1, February 2017. The issue year is the citation year; the online date is recorded here |
| `falcone2011` | Crossref returns a record with no title and no author | the DOI landing page confirms the title and "Falcone, J.A., 2011"; the entry uses that |
| `geifman2017`, `zaoui2020` | no DOI | NeurIPS proceedings have no DOI; verified through the proceedings page (Geifman) and arXiv/HAL (author order, Zaoui) |
| `wang2025` | DOI is not in Crossref | the publisher page `ckyyb.crsri.cn/CN/10.11988/ckyyb.20240856` gives author 王盛辉 (Wang, Sheng-hui), volume 42(10), pages 54–63, 2025, and the English journal name |

## Verdict per reference

| key | paper | verdict |
|---|---|---|
| `beaufort2022` | Spatial extrapolation of stream thermal peaks using heterogeneous time series at a national scale | match |
| `caissie2006` | The thermal regime of rivers: a review | match (name form) |
| `corona2025` | Machine learning in stream and river water temperature modeling: a review and metrics for evaluation | corrected |
| `falcone2011` | GAGES-II: Geospatial Attributes of Gages for Evaluating Streamflow | match (Crossref incomplete) |
| `geifman2017` | Selective classification for deep neural networks | match (proceedings page) |
| `isaak2017` | The NorWeST summer stream temperature model and scenarios for the western U.S. | corrected |
| `johnson2021` | Heed the data gap: guidelines for using incomplete datasets in annual stream temperature analyses | match |
| `kratzert2023` | Caravan — a global community dataset for large-sample hydrology | match |
| `lei2018` | Distribution-free predictive inference for regression | match |
| `li2017` | Missing data imputation for paired stream and air temperature sensor data | corrected (issue) |
| `mauger2015` | Stream temperature data collection standards for Alaska | corrected (author spelling) |
| `mauger2017` | Summer temperature regimes in southcentral Alaska streams | match |
| `mohseni1998` | A nonlinear regression model for weekly stream temperatures | match |
| `nasapower2026` | POWER project data sets: daily 2 m air temperature (MERRA-2) | corrected (description) |
| `rubin1976` | Inference and missing data | match |
| `wac2024` | Water quality standards for surface waters of the State of Washington | corrected (sections) |
| `grey2024` | Analysis of irregularly sampled stream temperature time series | match |
| `huang2023` | Long-term river water temperature reconstruction and investigation | match |
| `zaoui2020` | Regression with reject option and application to kNN | corrected (author order) |
| `hare2023` | Paired air and stream temperature analysis (PASTA) | match |
| `jackson2025` | The influence of equipment bias on reported temperature trends | match |
| `sanikhani2026` | Large-scale climate teleconnections and multiscale controls on river water temperature | match |
| `wang2025` | Long-term reconstruction and variation characteristics of water temperature in mainstream Yangtze River | match |
| `you2026` | Unveiling river thermal regimes in the Yangtze river basin | match |
| `zhang2011` | Indices for monitoring changes in extremes based on daily temperature and precipitation data | match (name form) |
| `angelopoulos2022` | Conformal risk control | match |
| `bai2026` | Risk-controlling predictive sets for time-series events under selective observation | match |

## Reproducing this audit

`python3 scripts/338_wrr_reference_audit.py` (or `make wrr-reference-audit`)
re-fetches the deposits (cached under `scratch/reference_audit/authoritative/`)
and re-runs the field comparison. It prints one line per entry and exits non-zero
if an unexplained difference appears; the five documented deviations above are
whitelisted with their reasons in the script.

## Re-verification

After the edits, the same comparison was re-run. Every entry with a machine-readable
deposit matches on authors, title, venue, volume, issue, pages, year and DOI,
except the five documented deviations above. The build logs zero BibTeX warnings,
renders 27 entries, and the manuscript's citation keys are unchanged, so no prose
needs updating.
