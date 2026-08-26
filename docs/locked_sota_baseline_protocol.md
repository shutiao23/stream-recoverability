# Locked SOTA baseline protocol (P1-01)

Status: sealed comparison contract; Air2stream, PGDL, and graph imputers have not been trained in this revision.

## Shared budget

All added baselines use the same Jinsha or Chattahoochee fitting years, the same artificial masks, the same eligible cells, and a predeclared tuning budget. Early stopping before epoch 50 is recorded as a diagnostic and is not used, after seeing scores, to drop a method.

## Required roster

- Persistence (last observation carried forward within a gap where defined; otherwise climatology).
- Training climatology (already in the formal roster).
- Air2stream or an equivalent air--discharge hybrid [@toffolon2015air2stream].
- One process-guided or Bayesian stream-temperature model.
- One graph or network imputer only when a donor graph is predeclared.

## Outputs

MAE, skill, runtime, and a statement of the information group available to each method. No ranking enters the main text until the budget is locked and evaluation is run once.
