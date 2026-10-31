"""Resume the same metadata plan only after an observed NLDI quota wait."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import importlib
import json
import os
import subprocess
import sys
import time
import wrr_r3_common as C
N = importlib.import_module('411_wrr_usgs_network_intake')

def retry_deadline(record, timeout_seconds=45, margin_seconds=5):
    """Honor Retry-After from a timestamp after the actual response was seen."""
    if record.get('http_status') != 429:
        raise ValueError('A quota wait requires an observed HTTP 429')
    value = str(record.get('retry_after') or '').strip()
    if value.isdigit():
        observed = record.get('response_observed_at_utc')
        if observed is None:
            raise ValueError('Relative Retry-After requires an actual post-response timestamp')
        acquired = datetime.fromisoformat(observed)
        if acquired.tzinfo is None:
            raise ValueError('An observed response time must include its timezone')
        return acquired.astimezone(timezone.utc) + timedelta(seconds=int(value) + margin_seconds)
    try:
        deadline = parsedate_to_datetime(value)
    except (TypeError, ValueError) as error:
        raise ValueError('No valid server retry time; do not issue another request') from error
    if deadline is None or deadline.tzinfo is None:
        raise ValueError('No valid timezone-aware server retry time')
    return deadline.astimezone(timezone.utc) + timedelta(seconds=margin_seconds)

def observed_quota_deadline(acquisition, settings):
    deadlines = []
    for result in acquisition['results']:
        if result['status'] != 'pending_http_429':
            continue
        for source in result['sources']:
            path = C.ROOT / source['path']
            if '.failure_' not in path.name:
                continue
            record = json.loads(path.read_text())
            if record.get('http_status') == 429:
                deadlines.append(retry_deadline({**record, 'response_observed_at_utc': result['recorded_at_utc']}))
    return max(deadlines) if deadlines else None

def state(status, **extra):
    C.write_json(N.OUT / 'resume_state.json', {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'controller_pid': os.getpid(), 'status': status, 'new_temperature_values_opened': False, 'new_prediction_errors_opened': False, **extra})

def main():
    settings = json.loads(N.CONFIG.read_text())
    N.OUT.mkdir(parents=True, exist_ok=True)
    while True:
        acquisition = json.loads((N.OUT / 'acquisition.json').read_text())
        deadline = observed_quota_deadline(acquisition, settings)
        previous_path = N.OUT / 'resume_state.json'
        if deadline is not None and previous_path.exists():
            previous = json.loads(previous_path.read_text()).get('next_allowed_utc')
            if previous:
                retained = datetime.fromisoformat(previous)
                if retained.tzinfo is None:
                    raise ValueError('Retained quota wait has no timezone')
                deadline = max(deadline, retained.astimezone(timezone.utc))
        if deadline is not None:
            state('waiting_for_observed_quota_reset', next_allowed_utc=deadline.isoformat(), attempted_jobs=acquisition['attempted_jobs'], planned_jobs=acquisition['planned_jobs'])
            last_report = 0.0
            while (remaining := (deadline - datetime.now(timezone.utc)).total_seconds()) > 0:
                if time.monotonic() - last_report >= 60:
                    print(f'[413] quota wait: {int(remaining)} seconds; next request no earlier than {deadline.isoformat()}', flush=True)
                    last_report = time.monotonic()
                time.sleep(min(30.0, remaining))
        state('running_same_frozen_metadata_plan', next_allowed_utc=deadline.isoformat() if deadline else None)
        command = [sys.executable, str(C.ROOT / 'scripts/411_wrr_usgs_network_intake.py'), 'fetch', '--workers', '2', '--retry-pending']
        print('[413] resuming the retained plan and response caches; no alternate endpoint or credentials', flush=True)
        result = subprocess.run(command, cwd=C.ROOT)
        acquisition = json.loads((N.OUT / 'acquisition.json').read_text())
        if result.returncode == 0:
            checked = subprocess.run([sys.executable, str(C.ROOT / 'scripts/411_wrr_usgs_network_intake.py'), 'summarize'], cwd=C.ROOT)
            state('base_metadata_plan_finished_not_independent_confirmation', returncode=checked.returncode, attempted_jobs=acquisition['attempted_jobs'], planned_jobs=acquisition['planned_jobs'])
            return checked.returncode
        later = observed_quota_deadline(acquisition, settings)
        if later is None or later <= datetime.now(timezone.utc) or (deadline is not None and later <= deadline):
            state('stopped_requires_service_or_metadata_review', returncode=result.returncode, attempted_jobs=acquisition['attempted_jobs'], planned_jobs=acquisition['planned_jobs'])
            return result.returncode
if __name__ == '__main__':
    raise SystemExit(main())
