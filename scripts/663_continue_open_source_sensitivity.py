#!/usr/bin/env python3
"""Continue the frozen open-source sensitivity as model receipts become ready.

Runs only the mode-region tasks not already launched manually, with separate
local logs. Stops on a child failure. No results are externally shared.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private/wrr_open_source_sensitivity_20261026'
PLAN = ROOT / 'results/wrr_review_response_20261027/open_source_sensitivity/plan.json'
ALREADY_LAUNCHED = {('offline', x) for x in ['foen', 'gkd_bayern', 'syke', 'usgs_huc03', 'usgs_huc04']}


def model_process_alive(pid):
    try:
        return b'scripts/657_open_source_sensitivity_refit.py' in Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return False


def write_state(state):
    path = PRIVATE / 'continuation_status.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refit-pid', type=int, required=True)
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text())
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (PRIVATE / 'continuation.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('A continuation scheduler is already active')
    pending = [(x['mode'], x['region']) for x in plan['target_mode_region_stations'] if (x['mode'], x['region']) not in ALREADY_LAUNCHED]
    running = {}
    finished = []
    failed = []
    logdir = PRIVATE / 'continuation_logs'
    logdir.mkdir(exist_ok=True, mode=0o700)
    while pending or running:
        for key, proc in list(running.items()):
            code = proc.poll()
            if code is not None:
                (finished if code == 0 else failed).append({'mode': key[0], 'region': key[1], 'exit_code': code})
                running.pop(key)
        if failed and not running:
            break
        receipt_path = PRIVATE / 'refit_receipts.json'
        try:
            receipts = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        except json.JSONDecodeError:
            receipts = {}
        if not failed:
            for mode, region in list(pending):
                if len(running) >= 2:
                    break
                if mode + '|' + region not in receipts:
                    continue
                logpath = logdir / (mode + '_' + region + '.log')
                log = logpath.open('ab', buffering=0)
                os.chmod(logpath, 0o600)
                command = [sys.executable, 'scripts/658_open_source_archive_sensitivity.py', '--mode', mode,
                           '--region', region, '--replicates', '20', '--workers', '4']
                proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                log.close()
                running[(mode, region)] = proc
                pending.remove((mode, region))
        state = {'status': 'failed' if failed else 'running', 'refit_pid': args.refit_pid,
                 'refit_process_alive': model_process_alive(args.refit_pid),
                 'pending': [list(x) for x in pending],
                 'running': [{'mode': k[0], 'region': k[1], 'pid': p.pid} for k, p in running.items()],
                 'finished': finished, 'failed': failed,
                 'limitation': 'Local post-hoc sensitivity only; case outputs and models are not authorized for publication.'}
        write_state(state)
        if pending and not model_process_alive(args.refit_pid) and not running:
            state['status'] = 'refit_process_ended_before_models_ready'
            write_state(state)
            raise RuntimeError('Refit process ended before all required model receipts were available')
        if pending or running:
            time.sleep(5)
    if failed:
        raise RuntimeError('Archive reanalysis failed; see local continuation logs')
    # All scheduled child tasks finished. Manually launched tasks are verified
    # by the full summary's complete 3,320-receipt check, never assumed done.
    proc = subprocess.run([sys.executable, 'scripts/662_open_source_input_integrity.py'], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode:
        state['status'] = 'source_input_audit_failed'
        write_state(state)
        raise RuntimeError('Source input integrity audit failed: ' + (proc.stdout + proc.stderr)[-2000:])
    report = subprocess.run([sys.executable, 'scripts/661_open_source_archive_summary.py'], cwd=ROOT, capture_output=True, text=True)
    (logdir / 'full_summary.log').write_text(report.stdout + report.stderr)
    if report.returncode:
        state['status'] = 'full_summary_failed'
        write_state(state)
        raise RuntimeError('Full summary rejected incomplete or inconsistent receipts; see local log')
    state['status'] = 'full_summary_passed'
    write_state(state)
    print('All scheduled settings and full paired summary passed.', flush=True)


if __name__ == '__main__':
    main()
