#!/usr/bin/env bash
# Resume after Stage 3 aggregate and branch ablation already exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

run_root="results/validation_funnel/published_v2"
stage3="${run_root}/deep_stability"
export PYTHONPATH=src
export PYTHONUNBUFFERED=1
python_bin="${PYTHON:-python}"

"$python_bin" scripts/15_run_validation_funnel.py go-no-go \
  --design configs/design_freeze_v4.yaml \
  --data-version published_v2 \
  --event-metrics \
    "${run_root}/traditional/event_metrics.parquet" \
    "${stage3}/event_metrics.parquet" \
  --branch-ablations "${run_root}/branch_ablation/branch_ablation_metrics.parquet" \
  --best-traditional-model donor_regression

"$python_bin" scripts/15_run_validation_funnel.py summarize-stage3 \
  --design configs/design_freeze_v4.yaml \
  --data-version published_v2 \
  --stage3-dir "$stage3" \
  --event-metrics \
    "${run_root}/traditional/event_metrics.parquet" \
    "${stage3}/event_metrics.parquet"

"$python_bin" scripts/15_run_validation_funnel.py freeze-roster \
  --design configs/design_freeze_v4.yaml \
  --data-version published_v2

printf '%s stage3 through roster complete; starting after-roster science\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

"$python_bin" scripts/ops/after_roster_pipeline.py

printf '%s after-roster pipeline finished\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
