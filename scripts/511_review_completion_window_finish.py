#!/usr/bin/env python3
"""Continue the existing20-seed native-H7 generator without duplicating it."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wrr_tr_common as T

OUT=T.ROOT/"results/wrr_review_completion_20261024/target_windows/h7/full"


def record(**values):T.write_json(OUT/"finish_progress.json",{"updated_utc":datetime.now(timezone.utc).isoformat(),**values})


def restore_legacy_stage_metadata():
    """The first driver wrote seed0 requests over generation metadata only.

    Preserve those files and restore the independently recorded full command.
    Native cases, caches and predictions are never edited by this correction.
    """
    expected=list(range(20));generation=json.loads((OUT/"generation_summary.json").read_text())
    if not generation.get("complete") or sorted(r["seed"] for r in generation["results"])!=expected:
        raise RuntimeError("The existing H7 generator did not finish all20 seeds")
    settings=T.settings()|{"version":"review_completion_h7_v1/seeds_"+'_'.join(map(str,expected)),"primary_window_days":7,
        "replication_seeds":expected,"trajectory_targets":["h7"],"classical_baselines":True,"training_split":"leave_one_year_out"}
    path=OUT/"generation_settings.json";current=json.loads(path.read_text())
    if current!=settings:
        prior=OUT/"generation_settings_before_stage_metadata_fix.json"
        if not prior.exists():prior.write_bytes(path.read_bytes())
        T.write_json(path,settings)
        design_path=OUT/"design.json";design=json.loads(design_path.read_text())
        backup=OUT/"design_before_stage_metadata_fix.json"
        if not backup.exists():backup.write_bytes(design_path.read_bytes())
        design.update(seeds=expected,partial=False);design.pop("with_trends",None);T.write_json(design_path,design)
        T.write_json(OUT/"stage_metadata_correction.json",{"cause":"initial driver recorded seed0 analysis requests over generation metadata",
            "restored_from":"executed20-seed generation command and complete generation summary; original entry script snapshot retained",
            "scientific_case_files_modified":False,"registered_H30_outputs_modified":False})
    files=["scripts/431_tr_cases.py","scripts/wrr_tr_common.py","scripts/wrr_tr_law.py",
        "src/stream_recoverability/experiments/tr_revision/simulation.py","src/stream_recoverability/experiments/tr_revision/windows.py",
        "scripts/466_review_completion_refit.py","scripts/467_review_completion_analysis.py"]
    T.write_json(OUT/"processing_code_sha256.json",{name:hashlib.sha256((T.ROOT/name).read_bytes()).hexdigest() for name in files})


def main():
    p=argparse.ArgumentParser();p.add_argument("--watch-pid",type=int);a=p.parse_args()
    if a.watch_pid:
        proc=Path(f"/proc/{a.watch_pid}")
        while proc.exists():
            try:command=(proc/"cmdline").read_bytes().replace(b"\0",b" ").decode(errors="replace")
            except FileNotFoundError:break
            if "506_review_completion_window_refits.py --stage generate" not in command:
                if not command:break
                raise RuntimeError("The watched PID is no longer the H7 source generator")
            record(stage="waiting_for_existing_generator",pid=a.watch_pid)
            time.sleep(15)
    restore_legacy_stage_metadata()
    stages=[("refits",["scripts/506_review_completion_window_refits.py","--stage","refit","--workers","48"]),
        ("analyses",["scripts/506_review_completion_window_refits.py","--stage","analyse","--workers","16","--with-trends"]),
        ("evidence",["scripts/509_review_completion_window_evidence.py"])]
    for name,args in stages:
        log=T.ROOT/"scratch"/f"review_completion_h7_full_{name}.log"
        record(stage=name,status="running",log=str(log.relative_to(T.ROOT)))
        with log.open("w") as stream:
            result=subprocess.run([sys.executable,*args],cwd=T.ROOT,stdout=stream,stderr=subprocess.STDOUT,
                env=os.environ|{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1"})
        if result.returncode:
            record(stage=name,status="failed",returncode=result.returncode,log=str(log.relative_to(T.ROOT)))
            raise RuntimeError(f"H7 {name} failed; inspect {log}")
    record(stage="complete",target="H7",source_seeds=20,outer_fits=540)
    return 0


if __name__=="__main__":raise SystemExit(main())
