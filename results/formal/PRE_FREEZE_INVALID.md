# Pre-freeze artifacts — not scientific evidence

Everything already present under this `results/formal/` tree was generated before
`configs/design_freeze_v1.yaml` and the v2 evidence contract. These artifacts use
independently sampled block locations, non-nested point masks, duplicated M7 event
seeds, the pre-S0/D model architecture, and/or stale training settings.

They are retained only to avoid destructive deletion and to support engineering
audit. They must not be aggregated with v2 outputs, cited in the manuscript, or
used to select models. A valid replacement must carry all of the following fields
with the current values in its mask metadata, checkpoint/run contract, prediction
rows, metric rows, and top-level manifest:

- `design_version`
- `design_hash`
- `data_version`
- `evaluation_split`
- `mask_schema_version`
- `model_schema_version`
- `statistics_schema_version`

New work belongs under versioned `results/experiments_v2/` or a later frozen
formal root after the validation funnel has selected the finalists.
