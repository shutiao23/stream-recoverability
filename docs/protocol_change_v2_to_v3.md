# Protocol change: `design_freeze_v2` to `design_freeze_v3`

`configs/design_freeze_v1.yaml` and `configs/design_freeze_v2.yaml` remain
historical. They are not silently rewritten. The executable default is
`configs/design_freeze_v3.yaml`.

This amendment was written before current-protocol development-test or
confirmatory performance was observed. It does not report MAE, skill, frontier
days, or confirmatory results.

## Why v3 exists

Two scientific-identity problems remained after v2:

1. Proposed-model training already reached the 200-epoch cap
   (`hit_epoch_limit=true`). Ranking under that budget can depend on an
   arbitrary ceiling rather than on a completed optimisation.
2. The validation scenario-ID repair (commit `056cc769` and later) changed the
   evidence identity of selection artifacts. v2 Stage 1 units cannot be reused
   as v3 selection evidence.

v3 is a one-time, pre-result protocol amendment. The epoch cap is not raised
again after this freeze.

## Frozen amendments

| Item | v2 | v3 |
| --- | --- | --- |
| Executable freeze | `design_freeze_v2` | `design_freeze_v3` |
| Common `max_epochs` | 200 | 400 |
| Further epoch-cap increase | not forbidden | forbidden |
| `hit_epoch_limit=true` | recorded only | `budget_unstable`; cannot enter the roster |
| Primary data version | `published_v1` | `published_v2` |
| QA fields | `quality_approved` only | `analysis_eligible`, `provider_qc_status`, `known_issue_flag` |
| Dual frontier | best-simple declared for later | both frontiers required |
| Donor C falsification | not executable | predeclared lag/permutation grid |
| Application frontier | `not_declared` | still `not_declared` |

## Training-budget rule

All formal deep candidates use `max_epochs=400` and `patience=20`. Any
required seed that records `hit_epoch_limit=true` is labelled
`budget_unstable` and is ineligible for Stage 2 retention, Stage 3, and the
final roster. The cap is not raised a third time.

## Data-version rule

`published_v2` keeps published values and adds explicit QC fields. Unknown
provider quality is `provider_qc_status=unknown` and must not be written as
`approved`. B1 level from 2019-01-01 and S2 hydrology for 2013–2019 receive
`known_issue_flag=true` on the main version; the three sensitivity versions
remain the exclusion/shift tests.

v1 versions remain historical. Their hashes are not reused as v3 selection
evidence.

## Dual frontier and falsification

Formal recoverability claims require both:

- climatology-relative skill and frontier;
- validation-selected best-simple-baseline-relative skill and frontier.

Donor-station Group C claims require the predeclared lag and permutation
grid. If a gain survives implausible lags and station permutation, the paper
may say “correlated predictive source” and must not say “network heat
propagation.”

## What is not claimed

- No development-test or confirmatory performance.
- `published_v2` artifact hashes are named in `design_freeze_v3.yaml` only after
  `scripts/14_build_data_versions.py` wrote the immutable directories.
- No operational recoverability boundary (application thresholds remain undeclared).
- v2 Stage 1/2/3 artifacts are not v3 selection evidence.

## Migration checklist

1. Point `DEFAULT_DESIGN_PATH` at `configs/design_freeze_v3.yaml`.
2. Rebuild `published_v2` and the three v2 sensitivities.
3. Re-run Stage 1 and Stage 2 under the v3 design hash.
4. Complete Stage 3, the proposed gate, and `finalized_model_roster_v1` before opening development-test or confirmatory performance.
5. Do not raise `max_epochs` again.
