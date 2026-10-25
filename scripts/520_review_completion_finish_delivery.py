#!/usr/bin/env python3
"""Refresh review deliverables after the identified European recovery job.

Uses completed source experiments only. A public registration archive is
preserved, and no command acquires independent water observations or marks the
user's goal complete. Every subprocess must finish before its dependent stage.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import wrr_tr_common as T
from wrr_review_forcing_reporting import europe_evidence

OUT = T.ROOT / "results/wrr_review_completion_20261024"
EVIDENCE = OUT / "evidence"


def record(**data):
    T.write_json(EVIDENCE / "final_delivery_progress.json", {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "new_NZ_water_values_requested": False, "all_user_requirements_complete": False, **data})


def wait_for_recovery(pid):
    while Path(f"/proc/{pid}").exists():
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except FileNotFoundError:
            break
        if not command:
            break
        if "515_review_completion_forcing_recovery.py" not in command or "--region europe" not in command:
            raise RuntimeError("The watched PID no longer identifies the European recovery job")
        record(stage="waiting_for_existing_European_recovery", pid=pid)
        time.sleep(30)


def run(stage, arguments, cwd=None, environment=None):
    log = T.ROOT / "scratch" / ("review_completion_final_" + stage + ".log")
    record(stage=stage, status="running", log=str(log.relative_to(T.ROOT)))
    with log.open("w") as stream:
        result = subprocess.run(arguments, cwd=cwd or T.ROOT, stdout=stream, stderr=subprocess.STDOUT,
            env=os.environ | {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"} | (environment or {}))
    if result.returncode:
        record(stage=stage, status="failed", returncode=result.returncode, log=str(log.relative_to(T.ROOT)))
        raise RuntimeError(f"Final {stage} failed; inspect {log}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch-pid", type=int)
    args = parser.parse_args()
    if args.watch_pid:
        wait_for_recovery(args.watch_pid)
    european = europe_evidence(OUT)
    recovery = json.loads((OUT / "inputs/forcing_recovery/europe/status.json").read_text())
    numerical = json.loads((OUT / "inputs/forcing_recovery/europe/numerical_audit.json").read_text())
    if not european["full_source"] or recovery.get("partial", True) or not numerical.get("passed"):
        raise RuntimeError("Full European input controls and recovery evidence must complete before final reporting")
    run("evidence", [sys.executable, "scripts/473_review_completion_evidence.py"])
    forcing_doc = (T.ROOT / "docs/reviews/wrr_review_completion_20261024/FORCING_EXECUTION_ZH.md").read_text()
    if "## 欧洲完整结果" not in forcing_doc or "## 恢复概率重算" not in forcing_doc:
        raise RuntimeError("The European and recovery reporting sections were not both preserved")
    paper = T.ROOT / "paper/wrr_tr"
    for name in ["article", "supporting"]:
        run(name, ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", f"review_completion_{name}.tex"],
            cwd=paper, environment={"TEXINPUTS": ".:../wrr/template:"})
        log = (paper / f"review_completion_{name}.log").read_text()
        if re.search(r"undefined references|multiply defined|LaTeX Warning: (?:Reference|Citation).*undefined", log):
            raise RuntimeError(f"Unresolved manuscript references in {name}")
    if (paper / "review_completion_tables_si.tex").read_text().count("\\begin{table}") > 30:
        raise RuntimeError("The supporting evidence exceeds the thirty-table limit")
    study = OUT / "independent_study"
    status = json.loads((study / "public_registration_status.json").read_text())
    if not str(status.get("status", "")).startswith("public_"):
        backup = T.ROOT / "scratch" / ("review_completion_registration_previous_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_before_final_Europe")
        backup.mkdir()
        for name in ["registration_code_and_protocol.tar.gz", "file_sha256.json", "bundle_inventory.json"]:
            shutil.copy2(study / name, backup / name)
        run("bundle", [sys.executable, "scripts/472_review_completion_prereg.py"])
    run("archive_execution", [sys.executable, "scripts/516_review_completion_archive_smoke.py"])
    run("validation", [sys.executable, "scripts/474_review_completion_validate.py"])
    validation = json.loads((EVIDENCE / "validation.json").read_text())
    if (not validation["full_Europe_available_coordinate_forcing_complete"]
            or not validation["driver_recovery_models_complete"]["europe"]
            or not all(check["passed"] for check in validation["checks"])):
        raise RuntimeError("The refreshed European evidence did not pass full validation")
    run("receipt", [sys.executable, "scripts/512_review_completion_delivery.py"])
    run("receipt_verify", [sys.executable, "scripts/512_review_completion_delivery.py", "--verify"])
    record(stage="delivery_refreshed", European_full_source=True,
        remaining="Public registration/new independent outcomes and unresolved historical national eligibility; author/platform fields user-owned")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        record(stage="stopped_for_review", error=str(error))
        raise
