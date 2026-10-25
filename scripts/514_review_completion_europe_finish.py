#!/usr/bin/env python3
"""Complete the exact European source cohort after its existing weather job.

The running controller loaded the older coordinate table. After it exits, the
verified French supplement is applied, existing responses are reused, and only
the still-missing nine source-weather inputs are requested under the same quota.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import wrr_tr_common as T
from wrr_review_forcing_reporting import europe_evidence

OUT=T.ROOT/"results/wrr_review_completion_20261024/europe_full_source_exact"


def record(**data):T.write_json(OUT/"finish_progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),**data})


def adjust_old_body_backoff():
    """Correct only our old generic fallback, preserving every provider reply.

    No request is sent here. Integer Retry-After records are never changed.
    The running old client reads this state while waiting for the same request.
    """
    path=OUT/"quota_status.json";snapshot=OUT/"provider_rate_limit_source_20261024.swift"
    if not path.exists() or not snapshot.exists():return
    original=path.read_bytes()
    try:d=json.loads(original)
    except json.JSONDecodeError:return
    kind=d.get("delay_source","").removeprefix("provider ").removesuffix("-limit response")
    if d.get("delay_source") not in ["provider hourly-limit response","provider daily-limit response"]:return
    now=datetime.now(timezone.utc);observed=datetime.fromisoformat(d["observed_utc"])
    if (now-observed).total_seconds()<130:return
    text=snapshot.read_text()
    if "if (now % 3600) < 60" not in text or "if (now % (24 * 3600)) < 60" not in text:return
    period=3600 if kind=="hourly" else 86400;epoch=observed.timestamp();start=math.floor(epoch/period)*period
    reset=start+60 if epoch-start<60 else start+period+60
    delay=max(1,math.ceil(reset-epoch))
    if delay>=d["retry_after_seconds"]:return
    history=OUT/"quota_history";history.mkdir(exist_ok=True)
    backup=history/(observed.strftime("%Y%m%dT%H%M%S")+"_original.json")
    if not backup.exists():backup.write_bytes(original)
    d.update(retry_after_seconds=delay,delay_source=f"inferred documented UTC {kind} reset plus60s; original generic fallback retained",
        documented_reset_utc=datetime.fromtimestamp(reset,timezone.utc).isoformat(),
        documentation_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        documentation_url="https://github.com/open-meteo/open-meteo/blob/main/Sources/App/Helper/Vapor/RateLimiter.swift")
    if path.read_bytes()!=original:return
    temp=path.with_suffix(".adjustment.tmp");temp.write_text(json.dumps(d,indent=2)+"\n");temp.replace(path)
    print(f"Recorded documented UTC {kind} reset; acquisition request unchanged",flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--watch-pid",type=int);a=p.parse_args()
    if a.watch_pid:
        proc=Path(f"/proc/{a.watch_pid}")
        while proc.exists():
            try:command=(proc/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
            except FileNotFoundError:break
            if "510_review_completion_europe_full.py" not in command:
                if not command:break
                raise RuntimeError("The watched PID is no longer the original European weather job")
            adjust_old_body_backoff()
            record(stage="waiting_for_existing_weather_job",pid=a.watch_pid);time.sleep(15)
    prior=json.loads((OUT/"acquisition.json").read_text())
    if prior.get("service_stop"):
        record(stage="provider_error_requires_review",prior_acquisition=prior)
        raise RuntimeError("The previous weather job stopped for an API error")
    audit=json.loads((OUT.parent/"inputs/source_coordinate_supplement_audit.json").read_text())
    if not audit.get("passed") or audit["n_source_stations"]!=9:raise RuntimeError("French source-coordinate evidence is not verified")
    backup=OUT/"before_coordinate_supplement"
    backup.mkdir(exist_ok=True)
    for name in ["roster.csv","design.json","acquisition.json","analysis_summary.json","paired_summary.csv","original_core_control_audit.json"]:
        path=OUT/name
        if path.exists() and not (backup/name).exists():shutil.copy2(path,backup/name)
    record(stage="complete_weather_and_refit",previous_retrieved=prior["retrieved"],supplementary_source_sites=9)
    log=T.ROOT/"scratch/review_completion_europe_full_after_coordinates.log"
    with log.open("w") as stream:
        result=subprocess.run([sys.executable,"scripts/510_review_completion_europe_full.py","--workers","2","--analysis-workers","16"],
            cwd=T.ROOT,stdout=stream,stderr=subprocess.STDOUT,env=os.environ|{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1"})
    if result.returncode:
        record(stage="failed",returncode=result.returncode,log=str(log.relative_to(T.ROOT)))
        raise RuntimeError("European completion stage failed")
    evidence=europe_evidence(OUT.parent)
    if not evidence["full_source"]:raise RuntimeError("The completed job does not cover the full European source cohort")
    artifacts={}
    for name in ["roster.csv","design.json","acquisition.json","analysis_summary.json","paired_summary.csv","paired_group_bootstrap.csv","original_core_control_audit.json"]:
        path=OUT/name;artifacts[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    T.write_json(OUT/"completion.json",{"complete":True,"n_source_sites":evidence["selected"],"n_weather_retrieved":evidence["retrieved"],
        "original_control":evidence["control"],"artifacts_sha256":artifacts,"new_NZ_water_values_requested":False,
        "scope":"all original European source stations, exact original daily-model controls; fixed-case sensitivity, not annual risk-model refits"})
    record(stage="complete",n_source_sites=evidence["selected"],n_weather_retrieved=evidence["retrieved"])
    return 0


if __name__=="__main__":raise SystemExit(main())
