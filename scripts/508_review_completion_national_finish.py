#!/usr/bin/env python3
"""Finish national source analyses after the existing acquisition controller.

Wait on the identified live job, retain each stage's log, and stop on an error.
This never starts a second water acquisition or an independent NZ test.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/national_meaning"


def record(**data):
    T.write_json(OUT/"finish_progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),
        "NZ_independent_values_requested":False,**data})


def main():
    p=argparse.ArgumentParser();p.add_argument("--watch-pid",type=int);p.add_argument("--workers",type=int,default=24);a=p.parse_args()
    if a.watch_pid:
        proc=Path(f"/proc/{a.watch_pid}")
        while proc.exists():
            command=(proc/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
            if "500_review_completion_national_inputs.py" not in command:
                raise RuntimeError("The requested PID is no longer the source acquisition controller")
            record(stage="waiting_for_existing_acquisition",acquisition_pid=a.watch_pid,command=command)
            time.sleep(30)
    acquisition=json.loads((OUT/"acquisition.json").read_text())
    if not acquisition.get("all_planned_attempted") or acquisition.get("service_stop"):
        record(stage="acquisition_incomplete",acquisition=acquisition)
        raise RuntimeError("Full source acquisition is incomplete; follow-up analyses were not run")
    stages=[("forcing",["scripts/501_review_completion_national_forcing.py","--workers","2"]),
            ("application",["scripts/502_review_completion_national_application.py","--workers",str(a.workers),"--resume"]),
            ("meaning",["scripts/503_review_completion_national_meaning.py","--bootstrap","2000"])]
    for name,args in stages:
        log=T.ROOT/"scratch"/f"review_completion_national_full_{name}.log"
        record(stage=name,status="running",log=str(log.relative_to(T.ROOT)))
        with log.open("w") as stream:
            result=subprocess.run([sys.executable,*args],cwd=T.ROOT,stdout=stream,stderr=subprocess.STDOUT,
                env=os.environ|{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1"})
        if result.returncode:
            record(stage=name,status="failed",returncode=result.returncode,log=str(log.relative_to(T.ROOT)))
            raise RuntimeError(f"National {name} failed; inspect {log}")
    status=json.loads((OUT/"status.json").read_text())
    record(stage="analyses_finished",scientific_completion=status.get("complete",False),status=status)
    return 0


if __name__=="__main__":raise SystemExit(main())
