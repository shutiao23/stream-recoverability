#!/usr/bin/env python3
"""Run formal, science, sensitivity, confirmatory, and analysis after roster freeze.

This is an operations driver.  It does not invent MAE, skill, or a frontier.
Incomplete manifests stay pending.  scripts/13 is not modified: its aggregate
manifest is moved out of results/run_manifest.json after each successful build.
"""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
FORMAL_ROOT = ROOT / "results"
EVENT_CATALOG = ROOT / "metadata/event_episode_catalog_v2.csv"
CONFIRMATORY_VERSION = "external_upper_middle_chattahoochee_v1"
PLACEHOLDER_RE = re.compile(
    r"<!-- RESULTS_PENDING: ([A-Z0-9_]+) — .*?-->",
    re.DOTALL,
)

signal.signal(signal.SIGHUP, signal.SIG_IGN)
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from stream_recoverability.experiments.contracts import load_frozen_data_versions

DESIGN_PATH = ROOT / "configs/design_freeze_v4.yaml"
FROZEN_DATA_VERSIONS = load_frozen_data_versions(DESIGN_PATH)
PRIMARY_DATA_VERSION = FROZEN_DATA_VERSIONS.primary
SENSITIVITY_VERSIONS = FROZEN_DATA_VERSIONS.sensitivities


def _validation_run_root() -> Path:
    from stream_recoverability.experiments.contracts import build_design_contract

    contract = build_design_contract(
        design_path=DESIGN_PATH,
        manifest_path=ROOT / "study_manifest.yaml",
        experiment_config_path=ROOT / "configs/experiments.yaml",
        data_version=PRIMARY_DATA_VERSION,
        evaluation_split="validation",
        data_version_manifest_path=(
            FROZEN_DATA_VERSIONS.manifest_path(ROOT / "data_versions")
        ),
    )
    return ROOT / "results/validation_funnel" / PRIMARY_DATA_VERSION


RUN = _validation_run_root()
ROSTER = RUN / "finalized_model_roster.json"
STATUS = RUN / "after_roster_status.json"
LOG = RUN / "after_roster.log"


def log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + message
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def load_status() -> dict[str, Any]:
    if STATUS.is_file():
        return json.loads(STATUS.read_text(encoding="utf-8"))
    return {"schema_version": "after_roster_status_v1", "steps": {}}


def save_status(status: dict[str, Any]) -> None:
    status["updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    STATUS.write_text(
        json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def step_done(status: dict[str, Any], name: str) -> bool:
    return status.get("steps", {}).get(name) == "complete"


def mark(status: dict[str, Any], name: str, value: str) -> None:
    status.setdefault("steps", {})[name] = value
    save_status(status)


def run_cmd(args: list[str], logfile: Path) -> int:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"
    log("RUN " + " ".join(args))
    with logfile.open("a", encoding="utf-8") as handle:
        handle.write("\n--- " + " ".join(args) + " ---\n")
        handle.flush()
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    log(f"exit={completed.returncode} log={logfile.name}")
    return completed.returncode


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def roster_doc() -> dict[str, Any]:
    doc = read_json(ROSTER)
    if doc is None:
        raise FileNotFoundError(ROSTER)
    return doc


def proposed_included() -> bool:
    return roster_doc().get("proposed_decision") == "include_proposed_formally"


def suite_dir(data_version: str, suite: str) -> Path:
    return (
        ROOT
        / "results/experiments_v2"
        / data_version
        / "development_test"
        / suite
    )


def science_dir(data_version: str, command: str) -> Path:
    folder = {
        "dense": "dense",
        "resilience": "resilience",
        "compensation": "compensation",
        "donor-falsification": "donor_falsification",
        "retrained-information": "retrained_information_upper_bounds",
    }[command]
    return (
        ROOT
        / "results/science_experiments"
        / data_version
        / "development_test"
        / folder
    )


def frozen_dir(data_version: str) -> Path:
    return ROOT / "results/frozen" / data_version


def formal_complete(path: Path) -> bool:
    doc = read_json(path / "run_manifest.json")
    if doc is None:
        return False
    return doc.get("formal_design_complete") is True and doc.get("complete") is True


def trainable_checkpoint_count() -> int:
    trainable = {"brits_ref", "saits_ref", "csdi", "proposed"}
    selected = [
        str(model)
        for model in roster_doc().get("selected_models", ())
        if str(model) in trainable
    ]
    return len(selected) * 5


def run_sharded(
    args: list[str], output: Path, logfile: Path, *, bootstrap: bool
) -> int:
    minimum = trainable_checkpoint_count()
    command = [
        PYTHON,
        str(ROOT / "scripts/ops/run_sharded.py"),
        "--output-dir",
        str(output),
        "--log-dir",
        str(logfile.with_name(logfile.stem + "_shards")),
        "--shard-count",
        "4",
        "--min-checkpoints",
        str(minimum),
    ]
    if bootstrap:
        command.append("--bootstrap-checkpoints")
    command.extend(["--", *args])
    return run_cmd(command, logfile)


def run_08(status: dict[str, Any], data_version: str, suite: str) -> bool:
    name = f"08_{suite}_{data_version}"
    if step_done(status, name):
        return True
    output = suite_dir(data_version, suite)
    if formal_complete(output):
        mark(status, name, "complete")
        return True
    mark(status, name, "running")
    args = [
        PYTHON,
        str(ROOT / "scripts/08_run_experiments.py"),
        "--suite",
        suite,
        "--evaluation-split",
        "development_test",
        "--data-version",
        data_version,
        "--finalized-model-roster",
        str(ROSTER),
    ]
    if suite == "full":
        args.extend(["--event-catalog", str(EVENT_CATALOG)])
    code = run_sharded(args, output, RUN / f"{name}.log", bootstrap=True)
    if code == 0 and formal_complete(output):
        mark(status, name, "complete")
        return True
    mark(status, name, "failed" if code != 0 else "incomplete")
    return False


def run_12(
    status: dict[str, Any],
    command: str,
    data_version: str,
    extra: list[str] | None = None,
) -> bool:
    name = f"12_{command.replace('-', '_')}_{data_version}"
    if step_done(status, name):
        return True
    output = science_dir(data_version, command)
    if formal_complete(output):
        mark(status, name, "complete")
        return True
    mark(status, name, "running")
    args = [
        PYTHON,
        str(ROOT / "scripts/12_run_science_experiments.py"),
        command,
        "--data-version",
        data_version,
        "--evaluation-split",
        "development_test",
        "--finalized-model-roster",
        str(ROSTER),
    ]
    if extra:
        args.extend(extra)
    if command in {"dense", "resilience"}:
        code = run_sharded(args, output, RUN / f"{name}.log", bootstrap=True)
    else:
        code = run_cmd(args, RUN / f"{name}.log")
    if code == 0 and formal_complete(output):
        mark(status, name, "complete")
        return True
    mark(status, name, "failed" if code != 0 else "incomplete")
    return False


def run_information(status: dict[str, Any]) -> None:
    if step_done(status, "training_information"):
        return
    output = (
        ROOT
        / "results/analysis"
        / PRIMARY_DATA_VERSION
        / "training_information_metrics.csv"
    )
    if output.is_file():
        mark(status, "training_information", "complete")
        return
    mark(status, "training_information", "running")
    code = run_cmd(
        [
            PYTHON,
            str(ROOT / "scripts/12_run_science_experiments.py"),
            "information",
            "--data-version",
            PRIMARY_DATA_VERSION,
        ],
        RUN / "training_information.log",
    )
    mark(status, "training_information", "complete" if code == 0 else "failed")


def run_optional_proposed(status: dict[str, Any], data_version: str) -> bool:
    if not proposed_included():
        mark(status, f"12_compensation_{data_version}", "skipped_framework_only")
        if data_version == PRIMARY_DATA_VERSION:
            mark(
                status,
                f"12_retrained_information_{PRIMARY_DATA_VERSION}",
                "skipped_framework_only",
            )
        return True
    checkpoint_suite = "full" if data_version == PRIMARY_DATA_VERSION else "core"
    extra = [
        "--checkpoint-dir",
        str(suite_dir(data_version, checkpoint_suite) / "checkpoints"),
    ]
    if not run_12(status, "compensation", data_version, extra):
        return False
    if data_version == PRIMARY_DATA_VERSION:
        if not run_12(status, "retrained-information", data_version):
            return False
    return True


def registry_path(data_version: str) -> Path:
    return frozen_dir(data_version) / "suite_registry.json"


def primary_manifests() -> list[Path]:
    return [
        suite_dir(PRIMARY_DATA_VERSION, "full") / "run_manifest.json",
        science_dir(PRIMARY_DATA_VERSION, "dense") / "run_manifest.json",
        science_dir(PRIMARY_DATA_VERSION, "donor-falsification") / "run_manifest.json",
        science_dir(PRIMARY_DATA_VERSION, "resilience") / "run_manifest.json",
    ]


def sensitivity_manifests(data_version: str) -> list[Path]:
    paths = [
        suite_dir(data_version, "core") / "run_manifest.json",
        science_dir(data_version, "dense") / "run_manifest.json",
    ]
    if proposed_included():
        paths.append(science_dir(data_version, "compensation") / "run_manifest.json")
    return paths


def run_registry(status: dict[str, Any], data_version: str) -> bool:
    name = f"21_registry_{data_version}"
    output = registry_path(data_version)
    if output.is_file() or step_done(status, name):
        mark(status, name, "complete")
        return True
    manifests = (
        primary_manifests()
        if data_version == PRIMARY_DATA_VERSION
        else sensitivity_manifests(data_version)
    )
    missing = [str(path) for path in manifests if not path.is_file()]
    if missing:
        log(f"registry wait missing={missing[:3]}")
        mark(status, name, "blocked_missing_manifests")
        return False
    mark(status, name, "running")
    args = [
        PYTHON,
        str(ROOT / "scripts/21_build_formal_suite_registry.py"),
        "--finalized-model-roster",
        str(ROSTER),
        "--formal-root",
        str(FORMAL_ROOT),
        "--output",
        str(output),
        "--data-version",
        data_version,
        "--evaluation-split",
        "development_test",
        "--data-version-manifest",
        str(ROOT / "data_versions" / data_version / "version_manifest.json"),
    ]
    for path in manifests:
        args.extend(["--manifest", str(path)])
    output.parent.mkdir(parents=True, exist_ok=True)
    code = run_cmd(args, RUN / f"{name}.log")
    if code == 0 and output.is_file():
        mark(status, name, "complete")
        return True
    mark(status, name, "failed")
    return False


def run_aggregate(status: dict[str, Any], data_version: str) -> bool:
    name = f"13_aggregate_{data_version}"
    dest = frozen_dir(data_version) / "top_manifest.json"
    if dest.is_file() or step_done(status, name):
        mark(status, name, "complete")
        return True
    if not run_registry(status, data_version):
        return False
    mark(status, name, "running")
    results_root = frozen_dir(data_version)
    results_root.mkdir(parents=True, exist_ok=True)
    spilled = ROOT / "results/run_manifest.json"
    if spilled.is_file():
        spilled.unlink()
    code = run_cmd(
        [
            PYTHON,
            str(ROOT / "scripts/13_aggregate_formal_results.py"),
            "--formal-root",
            str(FORMAL_ROOT),
            "--results-root",
            str(results_root),
            "--suite-registry",
            str(registry_path(data_version)),
            "--data-version",
            data_version,
            "--evaluation-split",
            "development_test",
            "--data-version-manifest",
            str(ROOT / "data_versions" / data_version / "version_manifest.json"),
        ],
        RUN / f"{name}.log",
    )
    spilled = ROOT / "results/run_manifest.json"
    if spilled.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        spilled.replace(dest)
    if code == 0 and dest.is_file():
        mark(status, name, "complete")
        return True
    mark(status, name, "failed")
    return False


def run_analyze(status: dict[str, Any]) -> bool:
    name = "09_analyze"
    analysis = ROOT / "results/analysis/analysis_manifest.json"
    if analysis.is_file():
        doc = read_json(analysis) or {}
        if doc.get("status") == "complete":
            mark(status, name, "complete")
            return True
    for version in (PRIMARY_DATA_VERSION, *SENSITIVITY_VERSIONS):
        if not run_aggregate(status, version):
            return False
    mark(status, name, "running")
    args = [
        PYTHON,
        str(ROOT / "scripts/09_analyze_results.py"),
        "--predictions",
        str(frozen_dir(PRIMARY_DATA_VERSION) / "predictions.parquet"),
        "--event-metrics",
        str(frozen_dir(PRIMARY_DATA_VERSION) / "event_metrics.parquet"),
        "--top-manifest",
        str(frozen_dir(PRIMARY_DATA_VERSION) / "top_manifest.json"),
        "--output-dir",
        str(ROOT / "results/analysis"),
    ]
    for version in SENSITIVITY_VERSIONS:
        args.extend(
            ["--sensitivity-manifest", str(frozen_dir(version) / "top_manifest.json")]
        )
    code = run_cmd(args, RUN / f"{name}.log")
    doc = read_json(analysis) or {}
    if code == 0 and doc.get("status") == "complete":
        mark(status, name, "complete")
        return True
    mark(status, name, "failed")
    return False


def run_figures(status: dict[str, Any]) -> bool:
    name = "11_figures"
    if step_done(status, name):
        return True
    mark(status, name, "running")
    code = run_cmd(
        [
            PYTHON,
            str(ROOT / "scripts/11_make_figures.py"),
            "--daily-predictions",
            str(frozen_dir(PRIMARY_DATA_VERSION) / "predictions.parquet"),
            "--event-metrics",
            str(frozen_dir(PRIMARY_DATA_VERSION) / "event_metrics.parquet"),
            "--analysis-dir",
            str(ROOT / "results/analysis"),
        ],
        RUN / f"{name}.log",
    )
    mark(status, name, "complete" if code == 0 else "failed")
    return code == 0


def confirmatory_data_ready() -> bool:
    manifest = ROOT / "data_versions" / CONFIRMATORY_VERSION / "version_manifest.json"
    doc = read_json(manifest)
    return bool(doc and doc.get("immutable") is True)


def confirmatory_feasibility_report() -> Path:
    return (
        ROOT
        / "results/confirmatory"
        / CONFIRMATORY_VERSION
        / "feasibility"
        / "confirmatory_feasibility_report.json"
    )


def confirmatory_lock() -> Path:
    return (
        ROOT
        / "data_versions"
        / f".{CONFIRMATORY_VERSION}.confirmatory-evaluation-once.lock.json"
    )


def run_confirmatory(status: dict[str, Any]) -> bool:
    if step_done(status, "confirmatory_evaluate_once"):
        return True
    if not confirmatory_data_ready():
        mark(status, "confirmatory_build", "running")
        code = run_cmd(
            [
                PYTHON,
                str(ROOT / "scripts/19_build_confirmatory_data.py"),
                "build",
                "--finalized-model-roster",
                str(ROSTER),
            ],
            RUN / "confirmatory_build.log",
        )
        if code != 0 or not confirmatory_data_ready():
            mark(status, "confirmatory_build", "failed")
            return False
        mark(status, "confirmatory_build", "complete")
    else:
        mark(status, "confirmatory_build", "complete")
    report_path = confirmatory_feasibility_report()
    report = read_json(report_path)
    if report is None or report.get("status") != "passed":
        if report_path.parent.is_dir() and report is None:
            mark(status, "confirmatory_feasibility", "blocked_existing_output")
            return False
        if report_path.parent.is_dir() and report.get("status") != "passed":
            mark(status, "confirmatory_feasibility", "failed_existing")
            return False
        mark(status, "confirmatory_feasibility", "running")
        code = run_cmd(
            [
                PYTHON,
                str(ROOT / "scripts/20_run_confirmatory_evaluation.py"),
                "--feasibility-only",
                "--finalized-model-roster",
                str(ROSTER),
            ],
            RUN / "confirmatory_feasibility.log",
        )
        report = read_json(report_path)
        if code != 0 or not report or report.get("status") != "passed":
            mark(status, "confirmatory_feasibility", "failed")
            return False
        mark(status, "confirmatory_feasibility", "complete")
    else:
        mark(status, "confirmatory_feasibility", "complete")
    lock = confirmatory_lock()
    eval_manifest = (
        ROOT
        / "results/confirmatory"
        / CONFIRMATORY_VERSION
        / "external_confirmation"
        / "run_manifest.json"
    )
    eval_doc = read_json(eval_manifest)
    if eval_doc and eval_doc.get("complete") is True:
        mark(status, "confirmatory_evaluate_once", "complete")
        return True
    if lock.is_file() and not (eval_doc and eval_doc.get("complete") is True):
        mark(status, "confirmatory_evaluate_once", "blocked_once_lock")
        return False
    mark(status, "confirmatory_evaluate_once", "running")
    code = run_cmd(
        [
            PYTHON,
            str(ROOT / "scripts/20_run_confirmatory_evaluation.py"),
            "--finalized-model-roster",
            str(ROSTER),
        ],
        RUN / "confirmatory_evaluate_once.log",
    )
    eval_doc = read_json(eval_manifest)
    if code == 0 and eval_doc and eval_doc.get("complete") is True:
        mark(status, "confirmatory_evaluate_once", "complete")
        return True
    mark(status, "confirmatory_evaluate_once", "failed")
    return False


def _num(value: object) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite")
    absolute = abs(number)
    if absolute >= 100:
        return f"{number:.1f}"
    if absolute >= 10:
        return f"{number:.2f}"
    return f"{number:.3f}"


def _table_sentences(path: Path, *, limit: int = 12) -> str | None:
    if not path.is_file():
        return None
    import pandas as pd

    frame = pd.read_csv(path)
    if frame.empty:
        return None
    rows = []
    for _, row in frame.head(limit).iterrows():
        parts = []
        for column in (
            "model",
            "station_id",
            "target",
            "metric",
            "gap_length",
            "component",
            "section",
        ):
            if column in row and pd.notna(row[column]):
                parts.append(f"{column}={row[column]}")
        for column in ("mean", "value", "ci_lower", "ci_upper", "n_events"):
            if column in row and pd.notna(row[column]):
                try:
                    parts.append(f"{column}={_num(row[column])}")
                except (TypeError, ValueError):
                    parts.append(f"{column}={row[column]}")
        if parts:
            rows.append("; ".join(parts))
    if not rows:
        return None
    more = "" if len(frame) <= limit else f" Showing {limit} of {len(frame)} rows."
    return " ".join(f"({item})" for item in rows) + more


def _csv_sentences(
    path: Path, columns: tuple[str, ...], *, limit: int = 8
) -> str | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    import pandas as pd

    frame = pd.read_csv(path)
    if frame.empty or ("status" in frame and frame["status"].eq("unavailable").all()):
        return None
    usable = [column for column in columns if column in frame.columns]
    if not usable:
        return None
    bits = []
    for _, row in frame.head(limit).iterrows():
        parts = []
        for column in usable:
            value = row[column]
            if value != value:
                continue
            try:
                parts.append(f"{column}={_num(value)}")
            except (TypeError, ValueError):
                parts.append(f"{column}={value}")
        if parts:
            bits.append("; ".join(parts))
    if not bits:
        return None
    return "Values from " + path.name + ": " + " ".join(f"({item})" for item in bits)


def update_readme_evidence(fields: dict[str, str]) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"(<!-- evidence-status:start -->\n```json\n)(.*?)(\n```\n<!-- evidence-status:end -->)",
        text,
        re.DOTALL,
    )
    if match is None:
        log("readme evidence block missing; skip")
        return
    payload = json.loads(match.group(2))
    payload.update(fields)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(
        text[: match.start()]
        + match.group(1)
        + rendered
        + match.group(3)
        + text[match.end() :],
        encoding="utf-8",
    )


def fill_results(status: dict[str, Any]) -> bool:
    name = "fill_results"
    if step_done(status, name):
        return True
    analysis = read_json(ROOT / "results/analysis/analysis_manifest.json")
    if not analysis or analysis.get("status") != "complete":
        mark(status, name, "blocked_analysis_incomplete")
        return False
    roster = roster_doc()
    top = read_json(frozen_dir(PRIMARY_DATA_VERSION) / "top_manifest.json") or {}
    analysis_dir = ROOT / "results/analysis"
    tables = ROOT / "paper/tables"
    r1 = (
        f"The primary aggregate manifest reports schema {top.get('schema_version')}, "
        f"formal_design_complete={top.get('formal_design_complete')}, "
        f"suite_count={top.get('suite_count')}, "
        f"expected_run_unit_count={top.get('expected_run_unit_count')}, "
        f"completed_evidence_run_unit_count={top.get('completed_evidence_run_unit_count')}, "
        f"and structural_skip_run_unit_count={top.get('structural_skip_run_unit_count')}. "
        f"Selected models were {roster.get('selected_models')}; "
        f"proposed_decision={roster.get('proposed_decision')}. "
        "These counts are the reporting denominator; incomplete historical dumps were not used."
    )
    r2 = _table_sentences(tables / "table_02.csv")
    r2 = (
        "Random-point temperature recovery (Table 2) used paired mask events. " + r2
        if r2
        else None
    )
    r3 = _csv_sentences(
        analysis_dir / "statistical_frontiers.csv",
        ("model", "target", "station_id", "statistical_frontier_days", "status"),
    )
    r4 = _csv_sentences(
        analysis_dir / "calibration_overall.csv",
        ("model", "coverage", "mean_interval_width", "status"),
    )
    r5 = _csv_sentences(
        analysis_dir / "event_episode_metrics.csv",
        ("model", "station_id", "target", "MAE", "status"),
    )
    r6 = _csv_sentences(
        analysis_dir / "shapley_contributions.csv",
        ("source", "shapley", "status"),
    )
    info_csv = (
        ROOT
        / "results/analysis"
        / PRIMARY_DATA_VERSION
        / "training_information_metrics.csv"
    )
    r7 = _csv_sentences(info_csv, ("pair", "metric", "estimate", "p_value"))
    r8 = _csv_sentences(
        analysis_dir / "resilience_auc.csv",
        ("model", "station_id", "auc", "status"),
    )
    r9_table = _table_sentences(tables / "table_04.csv")
    r9 = (
        "Internal leave-one-station-out and station-outage rows are reported separately from the online supplement. "
        + (
            r9_table
            or "Online metrics under results/online were not present; R9 therefore reports only offline LOSO/outage evidence."
        )
    )
    d1 = (
        "Interpretation is restricted to the complete frozen analysis. "
        f"proposed_decision={roster.get('proposed_decision')}. "
        "No model is ranked as operationally superior unless a paired effect estimate in the frozen tables supports that comparison."
    )
    d2 = (
        "Shapley values, mutual information, and transfer entropy remain descriptive. "
        "They are not treated as causal attribution of recoverability."
    )
    eval_doc: dict[str, Any] = {}
    confirmatory_manifest = (
        ROOT / "data_versions" / CONFIRMATORY_VERSION / "version_manifest.json"
    )
    if confirmatory_manifest.is_file():
        eval_manifest = (
            ROOT
            / "results/confirmatory"
            / CONFIRMATORY_VERSION
            / "external_confirmation"
            / "run_manifest.json"
        )
        eval_doc = read_json(eval_manifest) or {}
    d3 = (
        "Within this three-station Upper Jinsha case study, the completed frozen bundle "
        f"supports the reporting structure above. Confirmatory evaluation complete="
        f"{eval_doc.get('complete')}. Transport beyond this network is not claimed."
    )
    git_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    a1 = (
        "Public software is MIT-licensed in this repository. "
        f"Current commit {git_commit}. No Zenodo DOI is registered (CITATION.cff doi unset)."
    )
    a2 = (
        "Archived scientific artifacts are the finalized roster, the four frozen "
        "aggregates under results/frozen/, results/analysis/analysis_manifest.json, "
        "and generated paper/tables files whose status is generated. Restricted hydrology "
        "and CMA/GSOD-matched columns are not redistributed."
    )
    mapping = {
        "R1_FORMAL_COMPLETENESS": r1,
        "R2_OVERALL_ACCURACY": r2
        or "Table 2 was not generated from the frozen event metrics, so random-point MAE/skill values are not inserted.",
        "R3_RECOVERABILITY_FRONTIERS": r3
        or "Statistical frontier rows were empty or unavailable in the frozen analysis; no frontier day is reported.",
        "R4_PROBABILISTIC_DIAGNOSTICS": r4
        or "Calibration tables were empty or not applicable (no probabilistic model in the roster, or no finite intervals).",
        "R5_SCIENTIFIC_PRESERVATION": r5
        or "Event-episode scientific-preservation rows were not available in the frozen analysis.",
        "R6_COMPENSATION": r6
        or "Shapley/compensation tables are not applicable or empty under the frozen proposed_decision.",
        "R7_INFORMATION_METRICS": r7
        or "Training-only mutual-information and transfer-entropy estimates were not available at fill time.",
        "R8_NETWORK_RESILIENCE": r8
        or "Resilience AUC rows were empty or unavailable in the frozen analysis.",
        "R9_ONLINE_AND_LOSO": r9,
        "D1_PRIMARY_INTERPRETATION": d1,
        "D2_INFORMATION_TRADEOFFS": d2,
        "D3_CONCLUSION": d3,
        "A1_CODE_ARCHIVE": a1,
        "A2_RESULT_ARTIFACTS": a2,
    }
    manuscript = ROOT / "paper/manuscript.md"
    original = manuscript.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        text = mapping.get(key)
        if not text:
            return match.group(0)
        return text

    updated = PLACEHOLDER_RE.sub(replace, original)
    remaining = PLACEHOLDER_RE.findall(updated)
    manuscript.write_text(updated, encoding="utf-8")
    claims = (
        "populated_from_frozen_analysis"
        if not remaining
        else "partial_pending_placeholders"
    )
    update_readme_evidence(
        {
            "validation_funnel": "complete_selection_only",
            "finalized_model_roster": "finalized",
            "development_test_formal_evidence": "complete_current_protocol",
            "confirmatory_data": (
                "built" if confirmatory_data_ready() else "not_opened"
            ),
            "confirmatory_evaluation": (
                "complete" if eval_doc.get("complete") is True else "not_run"
            ),
            "current_protocol_result_claims": claims,
        }
    )
    mark(status, name, "complete" if not remaining else "partial")
    log(f"fill_results remaining_placeholders={remaining}")
    return not remaining


def update_readme_after_roster() -> None:
    roster = roster_doc()
    update_readme_evidence(
        {
            "validation_funnel": "complete_selection_only",
            "finalized_model_roster": "finalized",
            "development_test_formal_evidence": "pending_current_protocol",
            "current_protocol_result_claims": "none",
        }
    )
    cover = ROOT / "paper/cover_letter.md"
    text = cover.read_text(encoding="utf-8")
    old = (
        "README evidence status remains `validation_funnel=pending_execution` "
        "until a `finalized_model_roster_v1` exists."
    )
    new = (
        "A `finalized_model_roster_v1` now exists "
        f"(proposed_decision={roster.get('proposed_decision')}; "
        f"selected_models={roster.get('selected_models')}). "
        "README still reports `current_protocol_result_claims=none` until the "
        "frozen analysis is complete."
    )
    if old in text:
        cover.write_text(text.replace(old, new), encoding="utf-8")


def stop_after_p12() -> bool:
    explicit = os.environ.get("AFTER_ROSTER_STOP_AFTER", "p12").strip().lower()
    allow_p13 = (RUN / "ALLOW_P13_P14").is_file()
    return explicit != "p14" or not allow_p13


def main() -> int:
    if not ROSTER.is_file():
        log("no roster yet; exit")
        return 0
    log(f"after_roster_start pid={os.getpid()}")
    status = load_status()
    update_readme_after_roster()
    if not run_08(status, PRIMARY_DATA_VERSION, "full"):
        log(f"primary full {PRIMARY_DATA_VERSION} incomplete")
        return 1
    if not run_12(
        status, "dense", PRIMARY_DATA_VERSION, extra=["--variables", "T"]
    ):
        log(f"T dense {PRIMARY_DATA_VERSION} incomplete; retry later")
        return 1
    if not run_12(
        status,
        "donor-falsification",
        PRIMARY_DATA_VERSION,
        extra=["--estimator", "donor_regression"],
    ):
        return 1
    if not run_12(status, "resilience", PRIMARY_DATA_VERSION):
        return 1
    if not run_optional_proposed(status, PRIMARY_DATA_VERSION):
        return 1
    for version in SENSITIVITY_VERSIONS:
        if not run_08(status, version, "core"):
            log(f"sensitivity core {version} incomplete")
            return 1
        if not run_12(status, "dense", version, extra=["--variables", "T"]):
            return 1
        if not run_optional_proposed(status, version):
            return 1
    for version in (PRIMARY_DATA_VERSION, *SENSITIVITY_VERSIONS):
        if not run_aggregate(status, version):
            return 1
    if not run_analyze(status):
        return 1
    run_figures(status)
    if stop_after_p12():
        log(
            "stopping after P12 (registry/aggregate/analyze/figures). "
            "P13 confirmatory once-lock and P14 manuscript fill require "
            "AFTER_ROSTER_STOP_AFTER=p14 and ALLOW_P13_P14."
        )
        mark(status, "pipeline", "stopped_after_p12")
        return 0
    if not run_confirmatory(status):
        log("confirmatory incomplete; retry later")
        return 1
    fill_results(status)
    if not step_done(status, "fill_results"):
        log("fill_results incomplete; retry later")
        return 1
    log("after_roster_pass_finished")
    mark(status, "pipeline", "complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
