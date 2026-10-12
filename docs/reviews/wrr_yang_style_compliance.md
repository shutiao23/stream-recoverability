# Style compliance check: the twenty-point list

Scope: `paper/wrr/wrr_manuscript.tex` (53 pp), `paper/wrr/wrr_supporting_information.tex`
(15 pp) at commit `fbc1fec1b6` plus the caption and register pass of 2026-10-12.
Every "evidence" entry names the place the claim can be checked.

| # | item | status | evidence |
|---|---|---|---|
| 1 | Title states a finding, not a study object | done | `Gap position, not gap length, governs the error of annual thermal extremes in incomplete river-temperature records`; `tests/test_wrr_submission.py::test_title_and_abstract_state_the_finding` rejects `a study of / analysis of / assessment of / research on / towards` |
| 2 | The abstract's second move gives the precise gap | done | paragraph 1 states the prevailing completeness assumption, paragraph 2 the gap: a gap's length and position cannot be varied independently in a record that failed on its own; 239 words, inside the 250-word AGU limit enforced by the build |
| 3 | The introduction says why the old methods cannot answer the question | done | paragraph 4 names three obstacles: length and position correlate at $-0.86$ in this panel, the target statistic is unknown exactly where the decision matters, and evaluations report discrimination rather than archive composition |
| 4 | Methods answer the introduction's gaps one by one | done | the Methods lead paragraph maps each choice to an obstacle, then the subsections follow that order (reconstruction and what it may read; the rule and the information it is forbidden to read; the test protocol with the declared falsifications) |
| 5 | Figure 1 establishes the phenomenon before any mechanism analysis | deliberate exception | Figure 1 is the identification design and sits in the data/design section, which the style report allows for methods and data papers ("方法型论文常在前两张图加入：因果关系图；工作流；模型模块图"); Figure 2 is the phenomenon on one real record and Figure 3 the heterogeneity, so the results sequence still opens with the phenomenon. Swapping them is a two-line change if the author prefers the discovery-paper order |
| 6 | Figure 2/3 show the heterogeneity the average hides | done | Figure 3 (new) gives the endpoint ordering and the panel forest; the Results step "The response is conditional" adds the continuum, the guidance's own estimands, the collapse under the real calendar, and the agency/assurance spread |
| 7 | Figure 3 or 4 gives process or mechanism evidence | done | Figure 5 (mechanism: bins, nested feature sets, permutation importance, endpoint dependence) and Figure 7 (calibration) carry the mechanism step |
| 8 | A final figure completes attribution or implications | done | Figure 9 applies both rules to the 2422 real incomplete years; Figure 10 gives the representativeness cost of the screen |
| 9 | Every main conclusion has a number and a figure or table | done | `results/wrr_submission_ready/claim_registry.csv` (25 claims with artifact, unit, denominator, evidence type) and `scripts/254_wrr_claim_binding_check.py` (exit 0) |
| 10 | Result headings are scientific judgements | done | 4 step headings plus 12 claim-titled sub-headings; asserted by `test_result_headings_state_conclusions` |
| 11 | The discussion explains disagreement with earlier work | done | `Where this agrees with the standing guidance, and where the disagreement lies`, which attributes the difference to the conditioning axis and the estimand rather than to arithmetic |
| 12 | Strong verbs for phenomena, hedged verbs for mechanisms | done | no `proves / demonstrates / establishes / confirms` anywhere; the mechanism lead reads "organise the pattern", the discussion subsection hedges its second mechanism as "not in the data"; the representativeness caption reads "appears to select on difficulty" |
| 13 | Correlation is not written as causation | done | the catchment-attribute sub-section is titled "Where it is hard" and reports associations, with the geology claim withdrawn in the amendment register |
| 14 | Weak results and poor regions are not hidden | done | the empirical arm ($-0.7$ to $-1.9$ points), the five of 36 reserved networks below 0.85 coverage, the worst reserved network at $+2.8$ points, and the withdrawn maintenance and "peak never observed" claims are all in the text |
| 15 | Management meaning comes from the mechanism | done | the conclusions derive the admission rule from the hidden-support mechanism; the maintenance recommendation was withdrawn because the outage-cause record does not exist |
| 16 | Figure colour has fixed semantics and significance is not colour-only | done | grey = retrospective, blue = sealed confirmation, orange = transport; open markers for diagnostics and secondary strata; panel letters and intervals carry the meaning; palette inherited from `scripts/188_v17_figures.py` and recorded in `figures/wrr/f2_caption_material.md` |
| 17 | Captions are readable without the main text | done | all ten main captions rewritten to 116--210 words: question first, panels a--c in order, units, n, the identity of the sample (retrospective / sealed / exploratory) and the source artifact |
| 18 | Supporting information carries thresholds, alternatives and sensitivity | done | Text S1--S8, Figures S1--S7, Table S1: data provenance, QC rules, protocol history, the amendment register, declared predictions that failed, discarded runs, and the verification ledger |
| 19 | Code, data and processing are reproducible | done | `results/wrr_submission_ready/current_data_manifest.csv` (hashes for the 146 networks), `metadata/data_rights.csv` (licences with live evidence), the companion dataset and dashboard, and `dist/wrr_study_inputs_v1.tar.gz` for confidential review |
| 20 | The whole paper can be stated as one counter-intuitive but testable claim | done | *whether an incomplete year can carry a summer extreme depends on where the gap falls, not on how long it is; and the completeness thresholds in use are the right axis for annual means and the wrong one for extremes* |

## Verification behind the table

* `python3 scripts/223_wrr_build.py` --- desk checks green except the author
  placeholder (human gate).
* `python3 scripts/254_wrr_claim_binding_check.py` --- exit 0.
* `python3 scripts/221_v18_audit_manuscript.py` --- 92 checks passing;
  `scripts/199_v17_audit_manuscript.py` --- 137 table cells match artifacts.
* `python3 scripts/266_wrr_figure_qa.py` --- 0 hard failures: fonts embedded,
  one page per figure, no clipped ink, no line below 4.5 pt, draw.io source for
  every schematic figure.
* `python3 -m pytest tests/ -q` --- exit 0.

## What the author may still want to change

1. Move the design schematic to the SI and promote the phenomenon figure to
   Figure 1 (item 5), if the discovery-paper order is preferred over the
   methods-paper order.
2. Compress the main text from ten figures to the four-to-six the report
   associates with high-impact discovery papers; the natural candidates for the
   SI are the real-gap calendar and the representativeness figure.
