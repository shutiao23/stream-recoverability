#!/usr/bin/env bash
# Wait for the live Stage 3 inference shards, then run the frozen post-105
# scientific path: aggregate -> branch ablation -> go-no-go -> summarize ->
# freeze roster -> after-roster science.
#
# This script does not retrain. It does not restart a dead shard. If workers
# exit before 105 status.json files exist, it exits 2 so a human can inspect
# shard logs. Do not launch a second copy while this waiter or the eight
# inference shards are already running.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

run_root="results/validation_funnel/published_v2"
stage3="${run_root}/deep_stability"
log_dir="${stage3}/shard_logs"
mkdir -p "$log_dir"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-8}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-8}"
export PYTHONPATH=src
export PYTHONUNBUFFERED=1

python_bin="${PYTHON:-python}"

wait_for_shards() {
  while pgrep -f '15_run_validation_funnel.py run --stage deep_stability .*--shard-count 8' >/dev/null; do
    n="$(find "${stage3}/scenarios" -name status.json -type f 2>/dev/null | wc -l)"
    printf '%s waiting status_json=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$n"
    sleep 60
  done
}

wait_for_shards
n="$(find "${stage3}/scenarios" -name status.json -type f 2>/dev/null | wc -l)"
if [ "$n" -lt 105 ]; then
  printf '%s incomplete status_json=%s after workers exited\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$n"
  exit 2
fi

"$python_bin" scripts/15_run_validation_funnel.py run \
  --stage deep_stability \
  --models brits_ref proposed csdi \
  --design configs/design_freeze_v4.yaml \
  --data-version published_v2 \
  --resume \
  --shard-index 0 \
  --shard-count 1

"$python_bin" scripts/15_run_validation_funnel.py run-branch-ablation \
  --design configs/design_freeze_v4.yaml \
  --data-version published_v2 \
  --device cpu

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
