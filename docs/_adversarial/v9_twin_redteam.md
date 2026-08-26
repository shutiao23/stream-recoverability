# RED TEAM: Phase 2 twins, second pass (leftovers only)

Date: 2026-08-26  
Role: leftovers only. Parent-accepted decisions are not re-opened.  
Target: current `twin_design.py`, `synthetic_river.py` `twin_*`, `results/framework/synthetic_v2/`, `docs/experiments/e5_twin_design.md`, `tests/test_twin_design.py`.  
Sealed temperatures were not opened. No other files were edited.

Parent already accepted: honest joint-gate fail (univariate AUC 1.0 because dam-like := high AR + isolation); 2×2 cells A–D were added. **Do not retune the generator to pass 0.65.**

---

## What is no longer a finding

- **Twin A is not an index endpoint.** Chain dam at `n//2` has directed ancestors and descendants (n=6: up `{0,1,2}`, down `{4,5}`). Confluence dam is the join with three undirected neighbors and both directions in `directed_partition`. VAR is bidirectional (`advect` + `dispers`). `one_sided_donors` is false on every Twin A dam in `twin_node_scores.csv`. `_stabilize` did not fire (radii 0.88–0.94; written diagonals 0.52 / 0.93 survive).
- **Twin B leaf AR equals Twin A ordinary nodes.** Both are `TWIN_ORDINARY_MEMORY = 0.52` on the diagonal. Twin B is not the old `endpoint_*` (`phi=0.88`) implant.
- **Joint gate is recorded as fail.** Manifest `gate_pass: false`, `univariate_max_auc: 1.0`. Docs say do not retune. Do not demand a 0.65 rescue.
- **No real-river sentence** in the listed files. `formal_evidence: false`, `headline_claim_licensed: false`, `sealed_outcomes_opened: false`. E5: 不当确认.

---

## Leftover 1 — Twin D is Twin B with another name

**Answer: C is a real extra cell. D is not.**

`twin_d_ordinary_interior_chain` and `twin_b_ordinary_endpoint_chain` share the same `A` and `Q` (`np.allclose` true). D still sets `ordinary_endpoint=0` (the leaf) and never stores the interior index it computes. `_twin_river` then writes D’s notes/regime as Twin B:

> `Twin B chain: ordinary-memory endpoint 0 with one-sided donors.` / `regime=twin_b`

C’s notes are also false: dam at 0 is labeled `Twin A … interior dam-like node 0`.

Suite inventory: A/B on chain (n=5,6,7) and confluence (n=5,6). C/D on **chain only** (n=5,6). No C/D confluence. `test_two_by_two_cells_exist` only checks constructors and name token `{a,b,c,d}`.

Hard-negative AUC ignores C/D by design. All-node AUC’s 73 negatives include D rows that are copies of B. The 2×2 is four **labels**, not four **designs**.

**Must-fix:** give D a designated ordinary-interior node (or score B’s interior as D and drop the clone). Fix C/D notes/regime. If the 2×2 is claimed on the suite, put C/D on the confluence family too. Do not retune AR/isolation to do this.

---

## Leftover 2 — AUC is the design suite

**Answer: yes, leaked. Same 14 graphs that define the generator are the ROC population.**

`run_twin_design` → `multi_graph_suite()` → `score_twin_nodes(..., source="exact_sigma")` → `summarize_aucs`. Script 54 does not pass `include_finite_sample`. No hold-out size, seed, or family. `TWIN_*` constants and the 14 names are the design and the score.

Operator AUC 1.0 / univariate 1.0 is therefore an in-sample identity of “high AR + isolation,” which parent already accepted as the honest fail. It is not a hold-out identifiability number.

**Must-fix:** do not move `operator_auc: 1.0` into `paper/next/`, tables, or a later “twins passed.” Any future pass claim needs a family locked before scoring. Do not bump constants until 0.65.

---

## Leftover 3 — `identifiability_status: separable` is the operator half, not the gate

`gate_from_aucs` sets `separable` whenever operator AUC ≥ 0.85, ignoring the univariate ceiling. Manifest top-level `identifiability_status` is that half-status. Joint `gate_pass` is false.

E5 text: 算子也分不开就写 inseparable. The operator *does* separate, because the label is the generator knob. Quoting `separable` reads as a pass.

**Must-fix:** treat the joint gate as the only status that may be cited. Do not write “twins are separable” from this manifest. No retune.

---

## The five questions, short

| Question | Leftover? |
| --- | --- |
| Twin A still an endpoint in disguise? | **No** (geometry). Isolation = accepted tautology; do not retune. |
| Twin B leaf AR = Twin A ordinary nodes? | **Yes, 0.52.** Closed. |
| AUC leaked on the design graphs? | **Yes.** Leftover 2. |
| C/D actually in the suite? | **C yes; D is a B clone; no C/D confluence.** Leftover 1. |
| Any real-river claim? | **No** in these files. Do not let Leftover 3 (`separable`) become one. |

---

## Must-fix leftovers only

1. **Stop calling D a cell.** Designate the ordinary interior node, or delete the B-duplicate. Correct C/D notes (`interior` on node 0 is false). Add C/D on confluence if the suite still claims a 2×2.
2. **Do not promote the in-sample AUCs.** Design suite = scored suite. Lock a hold-out before any later pass language. Do not retune to 0.65.
3. **Do not cite `identifiability_status: separable`.** The joint gate failed. That string is not T5 and not a river result.
