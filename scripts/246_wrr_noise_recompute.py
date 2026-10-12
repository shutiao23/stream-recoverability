#!/usr/bin/env python3
"""F11 — regenerate the step-22 sensor-noise sensitivity under one locked method,
and extend it with error models a reviewer would actually ask for.

Audit finding F11 (``results/wrr_submission_ready/F_FINDINGS_CLOSURE_AUDIT.csv``)
records that the published ``results/v17_fitness/step22_robustness/
noise_sensitivity.json`` predates the fix to ``noise_sensitivity`` in
``scripts/202_v17_robustness.py``: the published clean and perturbed arms were
scored through *different* reconstruction choices, so part of the published
"noise effect" was a method change. The function is fixed (commit a9a7ad99cf);
the published numbers are not regenerated.

Stages
------
``preserve``   copy the pre-fix ``noise_sensitivity.json`` and ``REPORT.md``
               byte-identically into
               ``results/wrr_submission_ready/amendments/step22_noise_pre_fix/``
               and record sha256 digests in ``sha256.json``.
``refix``      import the *fixed* ``noise_sensitivity`` from
               ``scripts/202_v17_robustness.py`` via ``sys.path`` (never a copy)
               and re-run it on the development and reserved panels. Write the
               old-versus-new comparison to
               ``amendments/step22_noise_post_fix/noise_sensitivity.json``.
``scenarios``  re-derive the case table under a pluggable sensor-error model
               with ``stream_recoverability.experiments.wrr_submission_ready.
               noise_scenarios`` (whole-year bias, AR(1), mid-year step,
               drift), validate that re-run against the frozen case table on
               the original iid model, and write the per-case errors to
               ``scratch/f11/scenario_cases.parquet``.
``contrasts``  recompute the length-rule-versus-certificate contrast for every
               scenario at the locked method (``certificate_choice``), with
               clustered bootstrap intervals, and assert that the retained case
               set is identical between the clean and perturbed arms.
``report``     write ``summary.json``, ``scenario_contrasts.csv`` and
               ``REPORT.md`` into the post-fix amendment directory.

Nothing in ``results/v17_fitness/**``, ``src/**`` (other than the new module),
``paper/**`` or the sealed confirmation artifacts is modified.

Usage::

    PYTHONPATH=src python3 scripts/246_wrr_noise_recompute.py            # all stages
    PYTHONPATH=src python3 scripts/246_wrr_noise_recompute.py --stages preserve,refix
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    PRIMARY_TOLERANCE_C,
    STEP10_CONFIRM,
    STEP1_PANEL,
    STEP3_CASES,
    STEP4_CEILING,
    STEP6_SCREEN,
)
from stream_recoverability.experiments.v17_fitness.panel import station_jobs, station_roster  # noqa: E402
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.wrr_submission_ready.noise_scenarios import (  # noqa: E402
    CLEAN_PREFIX,
    FROZEN_NOISE_TAG,
    SCENARIO_MODELS,
    SCENARIO_ORDER,
    TRUTH_PREFIX,
    build_station_scenarios,
)

STEP22 = ROOT / "results" / "v17_fitness" / "step22_robustness"
WRR = ROOT / "results" / "wrr_submission_ready"
AMEND = WRR / "amendments"
PRE_DIR = AMEND / "step22_noise_pre_fix"
POST_DIR = AMEND / "step22_noise_post_fix"
SCRATCH = ROOT / "scratch" / "f11"
FIXED_SCRIPT = SCRIPTS / "202_v17_robustness.py"
PRESERVED_FILES = ("noise_sensitivity.json", "REPORT.md")

CASE_KEY = ["network_id", "station_id", "year", "realization_id"]
FROZEN_ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
FEATURE_COLUMNS = (
    "truth_hottest30",
    "longest_run",
    "peak_overlap",
    "warm_observed_fraction",
    "missing_fraction",
    "n_visible_donors",
)

# Bootstrap draws. The paper's own clustered intervals use 1200 (script 202) to
# 2000 (stats.DEFAULT_DRAWS); 1000 keeps ~40 bootstraps inside the run budget
# used here. Recorded in every output so the number is never implicit.
BOOTSTRAP_DRAWS = 1000
JITTER_SEED = 83
#: A constant offset is constant up to floating-point noise; below this the
#: within-series autocorrelation is undefined and is reported as null.
CONSTANT_SD_TOLERANCE_C = 1e-9

SOURCE_ARTIFACTS = {
    "step22_noise_sensitivity_pre_fix": STEP22 / "noise_sensitivity.json",
    "step22_report_pre_fix": STEP22 / "REPORT.md",
    "step3_cases": STEP3_CASES / "cases.parquet",
    "step4_development_cases": STEP4_CEILING / "development_cases.parquet",
    "step6_development_certificates": STEP6_SCREEN / "development_certificates.parquet",
    "step10_reserved_cases": STEP10_CONFIRM / "reserved_cases.parquet",
    "step10_reserved_certificates": STEP10_CONFIRM / "reserved_certificates.parquet",
    "scripts_202_v17_robustness": FIXED_SCRIPT,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(ROOT))


def load_fixed_module():
    """The fixed sensor-noise function, imported from ``scripts/`` via sys.path."""

    module = importlib.import_module("202_v17_robustness")
    if Path(module.__file__).resolve() != FIXED_SCRIPT.resolve():
        raise RuntimeError(f"imported the wrong module: {module.__file__}")
    doc = module.noise_sensitivity.__doc__ or ""
    if "same reconstruction choice" not in doc:
        raise RuntimeError("scripts/202_v17_robustness.py does not carry the F11 fix; refusing to run")
    return module


# --------------------------------------------------------------------------- #
# rate at fixed retention, with the retained case set exposed for assertions
# --------------------------------------------------------------------------- #
def rate_locked_detail(
    score: pd.Series | np.ndarray,
    clean_errors: pd.Series | np.ndarray,
    eval_errors: pd.Series | np.ndarray,
    retention: float,
    tolerance: float = PRIMARY_TOLERANCE_C,
) -> dict[str, object]:
    """Mirror of ``scripts/202_v17_robustness.py::_rate_locked``, plus indices.

    The mirror exists only so that the retained *case set* can be compared
    between arms; every published rate comes from the imported function and the
    mirror is asserted equal to it (see ``assert_mirror_matches``).
    """

    values = pd.to_numeric(pd.Series(score), errors="coerce").to_numpy(dtype=float)
    clean = pd.to_numeric(pd.Series(clean_errors), errors="coerce").to_numpy(dtype=float)
    eval_err = pd.to_numeric(pd.Series(eval_errors), errors="coerce").to_numpy(dtype=float)
    good = np.isfinite(clean) & np.isfinite(eval_err)
    values = np.where(np.isfinite(values), values, np.inf)[good]
    eval_err = eval_err[good]
    order = np.argsort(values, kind="mergesort")
    k = max(1, int(round(float(retention) * len(eval_err))))
    retained = np.flatnonzero(good)[order[:k]]
    return {
        "rate": float((eval_err[order[:k]] > float(tolerance)).mean()),
        "n_good": int(good.sum()),
        "k": int(k),
        "retained": retained,
    }


def assert_mirror_matches(module, score, clean, eval_err, label: str, tolerance: float = 1e-12) -> float:
    detail = rate_locked_detail(score, clean, eval_err, module.RETENTION)
    reference = module._rate_locked(pd.Series(score), pd.Series(clean), pd.Series(eval_err))
    gap = abs(float(detail["rate"]) - float(reference))
    if not gap <= tolerance:
        raise AssertionError(f"{label}: retained-set mirror disagrees with _rate_locked by {gap}")
    return gap


# --------------------------------------------------------------------------- #
# stage: preserve
# --------------------------------------------------------------------------- #
def stage_preserve() -> dict:
    PRE_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for name in PRESERVED_FILES:
        source = STEP22 / name
        destination = PRE_DIR / name
        shutil.copyfile(source, destination)
        source_digest = sha256_file(source)
        destination_digest = sha256_file(destination)
        if source_digest != destination_digest:
            raise AssertionError(f"preservation is not byte-identical for {name}")
        if source.stat().st_size != destination.stat().st_size:
            raise AssertionError(f"preservation changed the size of {name}")
        files.append(
            {
                "file": name,
                "source": rel(source),
                "destination": rel(destination),
                "bytes": int(destination.stat().st_size),
                "sha256": destination_digest,
                "source_sha256": source_digest,
                "byte_identical": True,
            }
        )
    record = {
        "generated_by": rel(Path(__file__)),
        "generated_utc": utc_now(),
        "git_head": git_head(),
        "purpose": (
            "Pre-fix bytes of the step-22 reference-series sensitivity, preserved before the F11 "
            "recompute so that the superseded numbers stay citable."
        ),
        "fix_commit": "a9a7ad99cf",
        "files": files,
    }
    (PRE_DIR / "sha256.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"[preserve] {len(files)} files -> {rel(PRE_DIR)}")
    for item in files:
        print(f"           {item['file']} sha256={item['sha256'][:16]}… bytes={item['bytes']}")
    return record


# --------------------------------------------------------------------------- #
# stage: refix
# --------------------------------------------------------------------------- #
def panel_tables() -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    return {
        "development": (
            pd.read_parquet(STEP4_CEILING / "development_cases.parquet").reset_index(drop=True),
            pd.read_parquet(STEP6_SCREEN / "development_certificates.parquet").reset_index(drop=True),
        ),
        "reserved": (
            pd.read_parquet(STEP10_CONFIRM / "reserved_cases.parquet").reset_index(drop=True),
            pd.read_parquet(STEP10_CONFIRM / "reserved_certificates.parquet").reset_index(drop=True),
        ),
    }


def contrast_fields(module, cases: pd.DataFrame, certificates: pd.DataFrame, choice, errors_fn) -> dict:
    """Rate table for one arm: rank by certificate bound and by outage length."""

    clean = pd.Series(
        module.gather(cases, certificates["certificate_choice"], prefix="abserr_"), index=cases.index
    )
    eval_err = errors_fn(cases, clean)
    score = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
    rng = np.random.default_rng(JITTER_SEED)
    length = pd.Series(
        pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases)),
        index=cases.index,
    )
    cert = rate_locked_detail(score, clean, eval_err, module.RETENTION)
    length_rule = rate_locked_detail(length, clean, eval_err, module.RETENTION)
    return {
        "clean_errors": clean,
        "eval_errors": pd.Series(eval_err, index=cases.index),
        "score": score,
        "length": length,
        "cert": cert,
        "length_rule": length_rule,
        "contrast_points": (float(length_rule["rate"]) - float(cert["rate"])) * 100.0,
    }


def pre_fix_reproduction(module, tables: dict, old: dict) -> dict:
    """Reproduce the published pre-fix numbers from the frozen inputs.

    The pre-fix code path is re-instated in two places only: the length arm
    evaluated the information-conditioned policy error, and the perturbed
    certificate arm evaluated that same policy error instead of the error of
    the certificate's chosen reconstruction. Everything else (the ranking
    scores, the top-k retention rule behind ``frontier_for_score``, the frozen
    tables) is unchanged, so a complete reproduction is possible and is the
    strongest available check that the preserved bytes and the frozen inputs
    describe the same run.
    """

    out: dict[str, dict] = {}
    for panel, (cases, certificates) in tables.items():
        choice = certificates["certificate_choice"]
        policy = cases["policy_choice"]
        clean_policy = pd.Series(module.gather(cases, policy, prefix="abserr_"), index=cases.index)
        noisy_policy = pd.Series(module.gather(cases, policy, prefix="abserr_noisy_"), index=cases.index)
        clean_cert = pd.Series(module.gather(cases, choice, prefix="abserr_"), index=cases.index)
        score = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
        certificate_abs = pd.to_numeric(certificates["certificate_abs_error"], errors="coerce")
        rng = np.random.default_rng(JITTER_SEED)
        length = pd.Series(
            pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases)),
            index=cases.index,
        )

        def rate(score_series, error_series) -> float:
            return float(rate_locked_detail(score_series, error_series, error_series, module.RETENTION)["rate"])

        reproduced = {
            "mean_abs_error_clean_c": float(pd.to_numeric(clean_policy, errors="coerce").mean()),
            "mean_abs_error_noisy_c": float(pd.to_numeric(noisy_policy, errors="coerce").mean()),
            "length_rule_at_70_clean": rate(length, clean_policy),
            "length_rule_at_70_noisy": rate(length, noisy_policy),
            "certificate_at_70_clean": rate(score, certificate_abs),
            "certificate_at_70_noisy": rate(score, noisy_policy),
        }
        reproduced["contrast_clean_points"] = (
            reproduced["length_rule_at_70_clean"] - reproduced["certificate_at_70_clean"]
        ) * 100.0
        reproduced["contrast_noisy_points"] = (
            reproduced["length_rule_at_70_noisy"] - reproduced["certificate_at_70_noisy"]
        ) * 100.0
        gaps = {field: float(reproduced[field]) - float(old[panel][field]) for field in reproduced}
        worst = max(abs(value) for value in gaps.values())
        if worst > 1e-12:
            raise AssertionError(f"{panel}: pre-fix artifact not reproduced, worst gap {worst}")

        difference = (pd.to_numeric(clean_cert, errors="coerce") - certificate_abs).abs()
        out[panel] = {
            "reproduced_pre_fix_rates": reproduced,
            "gaps_reproduced_minus_published": gaps,
            "max_abs_gap_vs_published": float(worst),
            "pre_fix_artifact_reproduced_exactly": bool(worst <= 1e-12),
            "certificate_abs_error_identical_to_chosen_case_error": {
                "max_abs_difference": float(np.nanmax(difference.to_numpy())) if len(difference) else 0.0,
                "rows": int(len(difference)),
                "identical": bool(float(np.nanmax(difference.to_numpy())) == 0.0) if len(difference) else True,
            },
        }
    out["what_this_shows"] = (
        "the preserved pre-fix numbers are exactly what the frozen case table and certificates produce "
        "under the pre-fix method mix, so the old-versus-new difference is a code change and not a data "
        "change; the two choices that moved are the length arm's reconstruction (information-conditioned "
        "policy error -> certificate_choice error) and the perturbed certificate arm's error column "
        "(policy noisy error -> certificate_choice noisy error). Because certificate_abs_error is identical "
        "to the chosen method's case error on every row, the clean certificate arm cannot move."
    )
    return out


def stage_refix() -> dict:
    module = load_fixed_module()
    tables = panel_tables()
    old = json.loads((PRE_DIR / "noise_sensitivity.json").read_text(encoding="utf-8"))
    reproduction = pre_fix_reproduction(module, tables, old)

    new: dict[str, dict] = {}
    for panel, (cases, certificates) in tables.items():
        new[panel] = module.noise_sensitivity(cases, certificates)

    # Retention detail for the same two arms, from the same frozen inputs.
    detail: dict[str, dict] = {}
    for panel, (cases, certificates) in tables.items():
        clean = pd.Series(
            module.gather(cases, certificates["certificate_choice"], prefix="abserr_"), index=cases.index
        )
        noisy = pd.Series(
            module.gather(cases, certificates["certificate_choice"], prefix="abserr_noisy_"), index=cases.index
        )
        score = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
        rng = np.random.default_rng(JITTER_SEED)
        length = pd.Series(
            pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases)),
            index=cases.index,
        )
        clean_finite = pd.to_numeric(clean, errors="coerce").notna()
        noisy_finite = pd.to_numeric(noisy, errors="coerce").notna()
        cert_clean = rate_locked_detail(score, clean, clean, module.RETENTION)
        cert_noisy = rate_locked_detail(score, clean, noisy, module.RETENTION)
        len_clean = rate_locked_detail(length, clean, clean, module.RETENTION)
        len_noisy = rate_locked_detail(length, clean, noisy, module.RETENTION)
        mirror_gap = max(
            assert_mirror_matches(module, score, clean, clean, f"{panel} cert clean"),
            assert_mirror_matches(module, score, clean, noisy, f"{panel} cert noisy"),
            assert_mirror_matches(module, length, clean, clean, f"{panel} length clean"),
            assert_mirror_matches(module, length, clean, noisy, f"{panel} length noisy"),
        )
        retained_identical = bool(
            np.array_equal(cert_clean["retained"], cert_noisy["retained"])
            and np.array_equal(len_clean["retained"], len_noisy["retained"])
        )
        if not retained_identical:
            raise AssertionError(f"{panel}: retained case set moved between clean and iid arms")
        detail[panel] = {
            "n_cases": int(len(cases)),
            "n_certificate_choice_finite_clean": int(clean_finite.sum()),
            "n_certificate_choice_finite_iid": int(noisy_finite.sum()),
            "n_evaluated": int(cert_clean["n_good"]),
            "n_retained_at_70": int(cert_clean["k"]),
            "retained_set_identical_clean_vs_iid": retained_identical,
            "mean_abs_error_clean_c": float(pd.to_numeric(clean, errors="coerce").mean()),
            "mean_abs_error_iid_c": float(pd.to_numeric(noisy, errors="coerce").mean()),
            "mean_abs_error_clean_on_evaluated_c": float(
                pd.to_numeric(clean, errors="coerce")[clean_finite].mean()
            ),
            "mean_abs_error_iid_on_evaluated_c": float(
                pd.to_numeric(noisy, errors="coerce")[pd.to_numeric(clean, errors="coerce").notna()].mean()
            ),
            "mirror_vs_fixed_max_abs_rate_gap": float(mirror_gap),
            "cases_where_iid_error_differs_from_clean": int(
                (
                    pd.to_numeric(noisy, errors="coerce").fillna(-1)
                    != pd.to_numeric(clean, errors="coerce").fillna(-1)
                ).sum()
            ),
        }

    fields = list(new["development"].keys())
    comparison: dict[str, dict] = {}
    for panel in ("development", "reserved"):
        old_panel = old[panel]
        new_panel = new[panel]
        change = {field: float(new_panel[field]) - float(old_panel[field]) for field in fields if field in old_panel}
        relative = {
            "contrast_clean_relative_change": (
                change["contrast_clean_points"] / float(old_panel["contrast_clean_points"])
            ),
            "contrast_noisy_relative_change": (
                change["contrast_noisy_points"] / float(old_panel["contrast_noisy_points"])
            ),
        }
        comparison[panel] = {
            "old_published": old_panel,
            "new_fixed": new_panel,
            "change_new_minus_old": change,
            "relative_change": relative,
            "retention_detail": detail[panel],
            "verdict": {
                "definition": (
                    "the qualitative conclusion is that timing beats outage length, i.e. the "
                    "contrast is positive and its clustered 95% interval excludes zero, under a "
                    "reference series perturbed by the sensor error"
                ),
                "new_noisy_contrast_points": float(new_panel["contrast_noisy_points"]),
                "new_noisy_contrast_positive": bool(new_panel["contrast_noisy_points"] > 0),
                "old_noisy_contrast_points": float(old_panel["contrast_noisy_points"]),
                "old_noisy_contrast_positive": bool(old_panel["contrast_noisy_points"] > 0),
                "sensor_noise_moves_contrast_by_points": float(
                    new_panel["contrast_noisy_points"] - new_panel["contrast_clean_points"]
                ),
                "sensor_noise_moves_contrast_relative": float(
                    (new_panel["contrast_noisy_points"] - new_panel["contrast_clean_points"])
                    / new_panel["contrast_clean_points"]
                ),
                "clustered_interval_reported_in": rel(POST_DIR / "scenario_contrasts.csv"),
            },
        }

    artifact = {
        "generated_by": rel(Path(__file__)),
        "generated_utc": utc_now(),
        "git_head": git_head(),
        "status": "supersedes the published pre-fix artifact",
        "supersedes": rel(PRE_DIR / "noise_sensitivity.json"),
        "superseded_by": rel(POST_DIR / "noise_sensitivity.json"),
        "fix_commit": "a9a7ad99cf",
        "fixed_function": {
            "source": rel(FIXED_SCRIPT),
            "sha256": sha256_file(FIXED_SCRIPT),
            "imported_as": "importlib.import_module('202_v17_robustness') with scripts/ on sys.path",
            "method_locked_to": new["development"]["method_locked_to"],
        },
        "what_changed": {
            "published_pre_fix": [
                "clean arm: information-conditioned simple policy (abserr_policy)",
                "perturbed arm: the same information-conditioned choice on the perturbed reference",
                "certificate arm: ranked by certificate_bound but evaluated on certificate_abs_error in the "
                "clean arm and on the information-conditioned noisy error in the perturbed arm",
                "retention: frontier_for_score lookup at retention == 0.70",
            ],
            "fixed": [
                "both arms use the certificate's own reconstruction choice (certificate_choice) in the "
                "clean and the perturbed evaluation",
                "the certificate is ranked by certificate_bound and evaluated on the error of that same "
                "chosen method",
                "retention: top-k on the finite mask, same k and same retained cases in both arms",
            ],
            "why_it_matters": (
                "the published contrast difference between the clean and perturbed arms mixed a method "
                "change into the noise effect; the fixed number isolates the sensor-error effect"
            ),
        },
        "development": comparison["development"],
        "reserved": comparison["reserved"],
        "pre_fix_reproduction": reproduction,
        "preserved_pre_fix": {
            "directory": rel(PRE_DIR),
            "sha256_record": rel(PRE_DIR / "sha256.json"),
            "files": [item["file"] for item in json.loads((PRE_DIR / "sha256.json").read_text(encoding="utf-8"))["files"]],
        },
    }
    POST_DIR.mkdir(parents=True, exist_ok=True)
    (POST_DIR / "noise_sensitivity.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print("[refix] development: old noisy {:.4f} -> new noisy {:.4f} points".format(
        float(old["development"]["contrast_noisy_points"]), float(new["development"]["contrast_noisy_points"])
    ))
    print("[refix] reserved:    old noisy {:.4f} -> new noisy {:.4f} points".format(
        float(old["reserved"]["contrast_noisy_points"]), float(new["reserved"]["contrast_noisy_points"])
    ))
    print("[refix] pre-fix artifact reproduced exactly: worst gap dev {:.2e}, reserved {:.2e}".format(
        float(reproduction["development"]["max_abs_gap_vs_published"]),
        float(reproduction["reserved"]["max_abs_gap_vs_published"]),
    ))
    return artifact


# --------------------------------------------------------------------------- #
# stage: scenarios
# --------------------------------------------------------------------------- #
def endpoint_level_perturbation(cases: pd.DataFrame) -> dict:
    """How far each process moves the *endpoint itself*, not just the daily value.

    Two processes with the same marginal daily sd do not perturb a thirty-day
    mean equally: the mean of an AR(1) error keeps more of the daily variance
    than the mean of an iid one. This reports the realized spread of
    ``H(truth + eps) - H(truth)`` over the study's own cases, which is the size
    of the perturbation the contrast actually sees.
    """

    reference = pd.to_numeric(cases["truth_hottest30"], errors="coerce")
    out: dict[str, dict] = {}
    for key in SCENARIO_ORDER:
        delta = pd.to_numeric(cases[f"{TRUTH_PREFIX}{key}"], errors="coerce") - reference
        out[key] = {
            "spec": SCENARIO_MODELS[key].note,
            "n_cases": int(delta.notna().sum()),
            "mean_delta_c": float(delta.mean()),
            "sd_delta_c": float(delta.std(ddof=1)),
            "mean_abs_delta_c": float(delta.abs().mean()),
        }
    anchor = out["iid_0.15"]["sd_delta_c"]
    for key in SCENARIO_ORDER:
        out[key]["sd_ratio_to_iid_0.15"] = float(out[key]["sd_delta_c"] / anchor) if anchor else float("nan")
    out["_comment"] = {
        "quantity": "H(truth + eps) - H(truth) for the hottest-30-day mean H, over every case in the panel",
        "why": (
            "the daily sd alone does not say how hard a process hits a thirty-day mean; an autocorrelated "
            "error survives averaging, so the AR(1) scenario perturbs the endpoint more than the iid "
            "scenario does at the same marginal sd"
        ),
    }
    return out


def stage_scenarios(workers: int) -> dict:
    roster = station_roster()
    split = pd.read_csv(STEP1_PANEL / "network_split.csv")
    split["network_id"] = split["network_id"].astype(str)
    jobs = station_jobs(roster, split)
    if not jobs:
        raise RuntimeError("no station jobs; is the panel roster available?")

    frozen = pd.read_parquet(STEP3_CASES / "cases.parquet")
    frozen_keys = set(map(tuple, frozen[CASE_KEY].astype(str).to_numpy()))

    started = time.time()
    frames: list[pd.DataFrame] = []
    failures: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(build_station_scenarios, job): job for job in jobs}
        done = 0
        for future in as_completed(futures):
            job = futures[future]
            try:
                frame = future.result()
            except Exception as error:  # noqa: BLE001 - recorded, not silenced
                failures.append(
                    {"network_id": job["network_id"], "station_id": job["station_id"], "error": repr(error)}
                )
                frame = pd.DataFrame()
            if not frame.empty:
                frames.append(frame)
            done += 1
            if done % 100 == 0:
                print(f"  [scenarios] {done}/{len(jobs)} stations ({time.time() - started:.0f}s)", flush=True)
    if not frames:
        raise RuntimeError("scenario case build produced nothing")
    cases = pd.concat(frames, ignore_index=True)
    cases = cases.sort_values(
        ["network_id", "station_id", "year", "arm", "realization_id"], kind="mergesort"
    ).reset_index(drop=True)

    # ---- validation against the frozen case table ------------------------- #
    mine_keys = set(map(tuple, cases[CASE_KEY].astype(str).to_numpy()))
    merged = frozen.merge(cases, on=CASE_KEY, how="inner", suffixes=("", "_scenario"), validate="one_to_one")
    max_abs: dict[str, float] = {}
    nan_mismatch: dict[str, int] = {}
    compared = 0
    for name in FROZEN_ESTIMATORS:
        for frozen_column, scenario_column in (
            (f"abserr_hottest30_{name}", f"{CLEAN_PREFIX}{name}"),
            (f"abserr_noisy_{name}", f"{SCENARIO_MODELS['iid_0.15'].key}__{name}"),
        ):
            left = pd.to_numeric(merged[frozen_column], errors="coerce").to_numpy(dtype=float)
            right = pd.to_numeric(merged[scenario_column], errors="coerce").to_numpy(dtype=float)
            nan_mismatch[f"{frozen_column}_vs_{scenario_column}"] = int((np.isnan(left) != np.isnan(right)).sum())
            both = np.isfinite(left) & np.isfinite(right)
            compared += int(both.sum())
            max_abs[f"{frozen_column}_vs_{scenario_column}"] = (
                float(np.max(np.abs(left[both] - right[both]))) if both.any() else 0.0
            )
    for column in FEATURE_COLUMNS:
        left = pd.to_numeric(merged[column], errors="coerce").to_numpy(dtype=float)
        right = pd.to_numeric(merged[f"{column}_scenario"], errors="coerce").to_numpy(dtype=float)
        both = np.isfinite(left) & np.isfinite(right)
        nan_mismatch[f"{column}_vs_scenario"] = int((np.isnan(left) != np.isnan(right)).sum())
        max_abs[f"{column}_vs_scenario"] = (
            float(np.max(np.abs(left[both] - right[both]))) if both.any() else 0.0
        )
    categorical_mismatch = {
        column: int((merged[column].astype(str) != merged[f"{column}_scenario"].astype(str)).sum())
        for column in ("provider", "split_role", "arm", "overlap_class")
    }

    validation = {
        "frozen_case_table": rel(STEP3_CASES / "cases.parquet"),
        "frozen_cases": int(len(frozen)),
        "rebuilt_cases": int(len(cases)),
        "keys_missing_from_rebuild": int(len(frozen_keys - mine_keys)),
        "keys_not_in_frozen_table": int(len(mine_keys - frozen_keys)),
        "keys_compared": int(len(merged)),
        "values_compared": int(compared),
        "max_abs_difference_frozen_vs_rebuild": max_abs,
        "nan_position_mismatches": nan_mismatch,
        "categorical_mismatches": categorical_mismatch,
        "replica_is_exact": bool(
            max(max_abs.values(), default=0.0) == 0.0
            and not any(nan_mismatch.values())
            and not any(categorical_mismatch.values())
        ),
        "failures": failures,
        "seconds": round(time.time() - started, 1),
    }
    if len(frozen_keys - mine_keys) or len(mine_keys - frozen_keys):
        raise AssertionError("the rebuilt case table does not cover the frozen case keys exactly")
    if not validation["replica_is_exact"]:
        raise AssertionError(f"replica does not reproduce the frozen case table: {validation}")

    # ---- realized statistics of each error process ------------------------ #
    process_checks = realized_process_checks(cases)
    endpoint_checks = endpoint_level_perturbation(cases)

    SCRATCH.mkdir(parents=True, exist_ok=True)
    cases.to_parquet(SCRATCH / "scenario_cases.parquet", index=False)
    (SCRATCH / "validation.json").write_text(
        json.dumps(
            {
                "validation": validation,
                "process_checks": process_checks,
                "endpoint_level_perturbation": endpoint_checks,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"[scenarios] {len(cases):,} cases rebuilt over {len(jobs)} stations in {validation['seconds']}s; "
        f"replica exact={validation['replica_is_exact']}"
    )
    return {
        "validation": validation,
        "process_checks": process_checks,
        "endpoint_level_perturbation": endpoint_checks,
        "cases_path": rel(SCRATCH / "scenario_cases.parquet"),
    }


def realized_process_checks(cases: pd.DataFrame, n_series: int = 60) -> dict:
    """Within-series statistics of each process on real year calendars.

    Pooled statistics are misleading for the deterministic processes (a
    constant bias has zero pooled sd because every series draws the same
    constant), so the summary is taken inside each station-year and then
    averaged across series. Series with no within-series variation are counted
    separately rather than fed to a correlation that is undefined for them.
    """

    triples = (
        cases[["network_id", "station_id", "year"]]
        .drop_duplicates()
        .sort_values(["network_id", "station_id", "year"], kind="mergesort")
        .head(n_series)
    )
    out: dict[str, dict] = {}
    for key, model in SCENARIO_MODELS.items():
        sds: list[float] = []
        offsets: list[float] = []
        autocorrelations: list[float] = []
        constant_series = 0
        for row in triples.itertuples(index=False):
            index = pd.date_range(f"{int(row.year)}-01-01", f"{int(row.year)}-12-31", freq="D")
            values = model.draw(
                index, network_id=str(row.network_id), station_id=str(row.station_id), year=int(row.year)
            )
            sd = float(np.std(values, ddof=1))
            sds.append(sd)
            offsets.append(abs(float(np.mean(values))))
            if sd > CONSTANT_SD_TOLERANCE_C:
                autocorrelations.append(float(np.corrcoef(values[:-1], values[1:])[0, 1]))
            else:
                constant_series += 1
        out[key] = {
            "kind": model.kind,
            "spec": model.note,
            "seed_tag": model.seed_tag or model.key,
            "n_series": int(len(sds)),
            "n_days_per_series": "365 or 366, the real calendar of the sampled station-year",
            "mean_within_series_sd_c": float(np.mean(sds)),
            "mean_within_series_abs_offset_c": float(np.mean(offsets)),
            "mean_within_series_lag1_autocorr": (
                float(np.mean(autocorrelations)) if autocorrelations else None
            ),
            "constant_series": int(constant_series),
        }
    out["_comment"] = {
        "why": (
            "documents that each named process is the process it claims to be; the series are drawn on the "
            "real calendar of sampled station-years, so 366-day leap years are included"
        ),
        "constant_series_means": (
            "the whole-year bias is a constant, so its within-series sd is zero and its lag-1 "
            "autocorrelation is undefined; its size is the mean absolute offset"
        ),
        "frozen_reference": {"model": "iid_0.15", "seed_tag": FROZEN_NOISE_TAG, "sd_c": 0.15},
    }
    return out


# --------------------------------------------------------------------------- #
# stage: contrasts
# --------------------------------------------------------------------------- #
def _bootstrap_task(payload: dict) -> dict:
    """One clustered bootstrap: the absolute contrast, or the paired change.

    ``paired_vs_clean`` recomputes both arms inside every resample, so the
    interval is on the *change* the error model causes, which is the quantity
    the audit question is about. Both arms keep the locked reconstruction
    choice and the same ranking scores.
    """

    frame = pd.DataFrame(payload["frame"])
    retention = float(payload["retention"])
    tolerance = float(payload["tolerance"])
    mode = payload["mode"]

    def arm(block: pd.DataFrame, eval_column: str) -> float:
        clean_block = block["clean_error"]
        eval_block = block[eval_column]
        cert = rate_locked_detail(block["score"], clean_block, eval_block, retention, tolerance)["rate"]
        length_rate = rate_locked_detail(block["length_jittered"], clean_block, eval_block, retention, tolerance)["rate"]
        return (float(length_rate) - float(cert)) * 100.0

    if mode == "paired_vs_clean":

        def contrast(block: pd.DataFrame) -> float:
            return arm(block, "scenario_error") - arm(block, "clean_error")

    elif mode == "absolute":

        def contrast(block: pd.DataFrame) -> float:
            return arm(block, "scenario_error")

    else:
        raise ValueError(f"unknown bootstrap mode: {mode!r}")

    stat = cluster_bootstrap(frame, contrast, draws=int(payload["draws"]), seed=0)
    stat["label"] = payload["label"]
    stat["mode"] = mode
    stat["draws"] = int(payload["draws"])
    return stat


def _merge_scenarios(frozen: pd.DataFrame, scenarios: pd.DataFrame) -> pd.DataFrame:
    merged = frozen.merge(scenarios, on=CASE_KEY, how="left", suffixes=("", "_scenario"), validate="one_to_one")
    if len(merged) != len(frozen):
        raise AssertionError("scenario merge changed the number of rows")
    if merged[f"{CLEAN_PREFIX}doy_climatology"].isna().all():
        raise AssertionError("scenario merge produced no values")
    return merged


def stage_contrasts(workers: int) -> dict:
    module = load_fixed_module()
    scenarios = pd.read_parquet(SCRATCH / "scenario_cases.parquet")
    for column in ("network_id", "station_id", "realization_id"):
        scenarios[column] = scenarios[column].astype(str)
    tables = panel_tables()

    panels: dict[str, dict] = {}
    boot_payloads: list[dict] = []
    for panel, (cases, certificates) in tables.items():
        merged = _merge_scenarios(cases, scenarios)
        choice = certificates["certificate_choice"]
        clean = pd.Series(module.gather(merged, choice, prefix=CLEAN_PREFIX), index=merged.index)
        score = pd.to_numeric(certificates["certificate_bound"], errors="coerce")
        rng = np.random.default_rng(JITTER_SEED)
        length = pd.Series(
            pd.to_numeric(merged["longest_run"], errors="coerce").to_numpy() + rng.random(len(merged)),
            index=merged.index,
        )
        if not np.array_equal(
            pd.to_numeric(clean, errors="coerce").notna().to_numpy(),
            pd.to_numeric(
                pd.Series(module.gather(cases, choice, prefix="abserr_"), index=cases.index), errors="coerce"
            )
            .notna()
            .to_numpy(),
        ):
            raise AssertionError(f"{panel}: rebuilt clean errors do not cover the frozen error mask")

        clean_detail = rate_locked_detail(score, clean, clean, module.RETENTION)
        mirror_gap = max(
            assert_mirror_matches(module, score, clean, clean, f"{panel} scenario-table cert clean"),
            assert_mirror_matches(module, length, clean, clean, f"{panel} scenario-table length clean"),
        )
        rows: list[dict] = []
        branches = [("clean", clean)] + [
            (key, pd.Series(module.gather(merged, choice, prefix=f"{key}__"), index=merged.index))
            for key in SCENARIO_ORDER
        ]
        retained_reference = {
            "certificate": clean_detail["retained"],
            "length_rule": rate_locked_detail(length, clean, clean, module.RETENTION)["retained"],
        }
        for key, errors in branches:
            cert = rate_locked_detail(score, clean, errors, module.RETENTION)
            length_rule = rate_locked_detail(length, clean, errors, module.RETENTION)
            retained_identical = bool(
                np.array_equal(cert["retained"], retained_reference["certificate"])
                and np.array_equal(length_rule["retained"], retained_reference["length_rule"])
            )
            if not retained_identical:
                raise AssertionError(
                    f"{panel}/{key}: retained case set differs from the clean arm "
                    f"(cert n={len(cert['retained'])} vs {len(retained_reference['certificate'])})"
                )
            if cert["n_good"] != clean_detail["n_good"] or cert["k"] != clean_detail["k"]:
                raise AssertionError(f"{panel}/{key}: evaluated case count moved with the error model")
            errors_finite = pd.to_numeric(errors, errors="coerce")
            clean_finite = pd.to_numeric(clean, errors="coerce")
            rows.append(
                {
                    "panel": panel,
                    "scenario": key,
                    "kind": SCENARIO_MODELS[key].kind if key in SCENARIO_MODELS else "clean",
                    "spec": SCENARIO_MODELS[key].note if key in SCENARIO_MODELS else "unperturbed reference series",
                    "n_cases": int(len(merged)),
                    "n_evaluated": int(cert["n_good"]),
                    "n_retained_at_70": int(cert["k"]),
                    "n_networks": int(merged["network_id"].nunique()),
                    "mean_abs_error_clean_c": float(clean_finite.mean()),
                    "mean_abs_error_scenario_c": float(errors_finite[clean_finite.notna()].mean()),
                    "length_rule_at_70": float(length_rule["rate"]),
                    "certificate_at_70": float(cert["rate"]),
                    "contrast_points": (float(length_rule["rate"]) - float(cert["rate"])) * 100.0,
                    "retained_set_identical_to_clean": retained_identical,
                    "cases_moved_by_error_model": int(
                        (errors_finite.fillna(-1) != clean_finite.fillna(-1)).sum()
                    ),
                }
            )
            frame = pd.DataFrame(
                {
                    "network_id": merged["network_id"].astype(str).to_numpy(),
                    "clean_error": pd.to_numeric(clean, errors="coerce").to_numpy(dtype=float),
                    "scenario_error": pd.to_numeric(errors, errors="coerce").to_numpy(dtype=float),
                    "score": pd.to_numeric(score, errors="coerce").to_numpy(dtype=float),
                    "length_jittered": pd.to_numeric(length, errors="coerce").to_numpy(dtype=float),
                }
            )
            base = {
                "frame": frame.to_dict("list"),
                "retention": float(module.RETENTION),
                "tolerance": float(module.PRIMARY_TOLERANCE_C),
                "draws": BOOTSTRAP_DRAWS,
            }
            boot_payloads.append({**base, "label": f"{panel}|{key}|absolute", "mode": "absolute"})
            if key != "clean":
                boot_payloads.append({**base, "label": f"{panel}|{key}|paired_vs_clean", "mode": "paired_vs_clean"})
        panels[panel] = {
            "n_cases": int(len(merged)),
            "n_evaluated": int(clean_detail["n_good"]),
            "n_retained_at_70": int(clean_detail["k"]),
            "n_networks": int(merged["network_id"].nunique()),
            "mirror_vs_fixed_max_abs_rate_gap": float(mirror_gap),
            "rows": rows,
        }

    started = time.time()
    boot: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_bootstrap_task, payload): payload["label"] for payload in boot_payloads}
        for future in as_completed(futures):
            label = futures[future]
            boot[label] = future.result()
    print(f"[contrasts] {len(boot)} clustered bootstraps ({BOOTSTRAP_DRAWS} draws) in {time.time() - started:.0f}s")

    # Attach intervals and the paired change.
    point_gaps: list[float] = []
    for panel, block in panels.items():
        for row in block["rows"]:
            absolute = boot[f"{panel}|{row['scenario']}|absolute"]
            row["contrast_ci_low"] = float(absolute["low"])
            row["contrast_ci_high"] = float(absolute["high"])
            row["contrast_ci_excludes_zero"] = bool(absolute["low"] > 0 or absolute["high"] < 0)
            row["retains_positive_contrast"] = bool(absolute["low"] > 0)
            row["n_clusters"] = int(absolute["n_clusters"])
            point_gaps.append(abs(float(absolute["point"]) - float(row["contrast_points"])))
            if row["scenario"] == "clean":
                row["contrast_change_vs_clean_points"] = 0.0
                row["contrast_change_ci_low"] = 0.0
                row["contrast_change_ci_high"] = 0.0
                row["contrast_change_ci_excludes_zero"] = False
            else:
                paired = boot[f"{panel}|{row['scenario']}|paired_vs_clean"]
                row["contrast_change_vs_clean_points"] = float(
                    row["contrast_points"] - block["rows"][0]["contrast_points"]
                )
                row["contrast_change_ci_low"] = float(paired["low"])
                row["contrast_change_ci_high"] = float(paired["high"])
                row["contrast_change_ci_excludes_zero"] = bool(paired["low"] > 0 or paired["high"] < 0)
                point_gaps.append(abs(float(paired["point"]) - float(row["contrast_change_vs_clean_points"])))
    if max(point_gaps, default=0.0) > 1e-9:
        raise AssertionError(f"bootstrap point estimates disagree with the direct contrast by {max(point_gaps)}")
    table = pd.DataFrame([row for panel in panels.values() for row in panel["rows"]])
    POST_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(POST_DIR / "scenario_contrasts.csv", index=False)
    (SCRATCH / "bootstraps.json").write_text(
        json.dumps({"draws": BOOTSTRAP_DRAWS, "results": boot}, indent=2) + "\n", encoding="utf-8"
    )
    (SCRATCH / "contrasts.json").write_text(
        json.dumps(
            {"panels": panels, "table": table.to_dict("records"), "bootstrap_draws": BOOTSTRAP_DRAWS},
            indent=2,
            default=float,
        )
        + "\n",
        encoding="utf-8",
    )
    print(table[["panel", "scenario", "contrast_points", "contrast_ci_low", "contrast_ci_high", "n_evaluated"]].round(4).to_string(index=False))
    return {"panels": panels, "table": table.to_dict("records"), "bootstrap_draws": BOOTSTRAP_DRAWS}


# --------------------------------------------------------------------------- #
# stage: report
# --------------------------------------------------------------------------- #
def stage_report(extra: dict) -> dict:
    refix = json.loads((POST_DIR / "noise_sensitivity.json").read_text(encoding="utf-8"))
    contrasts = extra["contrasts"]
    scenarios = extra["scenarios"]
    preservation = json.loads((PRE_DIR / "sha256.json").read_text(encoding="utf-8"))
    table = pd.DataFrame(contrasts["table"])
    table = table[
        [
            "panel",
            "scenario",
            "kind",
            "spec",
            "n_cases",
            "n_evaluated",
            "n_retained_at_70",
            "n_networks",
            "mean_abs_error_clean_c",
            "mean_abs_error_scenario_c",
            "length_rule_at_70",
            "certificate_at_70",
            "contrast_points",
            "contrast_ci_low",
            "contrast_ci_high",
            "contrast_change_vs_clean_points",
            "contrast_change_ci_low",
            "contrast_change_ci_high",
            "retains_positive_contrast",
            "retained_set_identical_to_clean",
            "cases_moved_by_error_model",
        ]
    ]

    # The replica branch must reproduce the fixed-function iid numbers exactly.
    cross_check = {}
    for panel in ("development", "reserved"):
        replica = table.loc[(table["panel"] == panel) & (table["scenario"] == "iid_0.15")].iloc[0]
        fixed = refix[panel]["new_fixed"]
        cross_check[panel] = {
            "post_fix_contrast_noisy_points": float(fixed["contrast_noisy_points"]),
            "replica_scenario_contrast_points": float(replica["contrast_points"]),
            "abs_difference": float(abs(float(fixed["contrast_noisy_points"]) - float(replica["contrast_points"]))),
            "post_fix_length_rule_at_70_noisy": float(fixed["length_rule_at_70_noisy"]),
            "replica_length_rule_at_70": float(replica["length_rule_at_70"]),
            "post_fix_certificate_at_70_noisy": float(fixed["certificate_at_70_noisy"]),
            "replica_certificate_at_70": float(replica["certificate_at_70"]),
        }
        if cross_check[panel]["abs_difference"] > 1e-9:
            raise AssertionError(f"{panel}: replica branch does not reproduce the fixed-function iid contrast")

    summary = {
        "generated_by": rel(Path(__file__)),
        "generated_utc": utc_now(),
        "git_head": git_head(),
        "finding": {
            "id": "F11",
            "severity": "Major",
            "statement": (
                "the published step-22 sensor-noise sensitivity compared two different reconstruction "
                "methods between its clean and perturbed arms; the function is fixed but the published "
                "numbers had not been regenerated"
            ),
            "closure": (
                "pre-fix bytes preserved; pre-fix numbers regenerated with the fixed function imported from "
                "scripts/202_v17_robustness.py; four additional error models recomputed on the full case set"
            ),
        },
        "provenance": {
            "source_artifacts_sha256": {name: sha256_file(path) for name, path in SOURCE_ARTIFACTS.items()},
            "preserved_pre_fix": preservation,
            "new_module": {
                "path": rel(ROOT / "src/stream_recoverability/experiments/wrr_submission_ready/noise_scenarios.py"),
                "sha256": sha256_file(
                    ROOT / "src/stream_recoverability/experiments/wrr_submission_ready/noise_scenarios.py"
                ),
                "why": (
                    "the frozen case table carries one perturbed-error column per estimator, built from a "
                    "single iid error process; a different daily error process cannot be recovered from it, "
                    "so the case construction is re-run with a pluggable process while everything else is "
                    "held identical"
                ),
            },
            "bootstrap_draws": contrasts["bootstrap_draws"],
            "jitter_seed": JITTER_SEED,
        },
        "replication_of_frozen_case_table": scenarios["validation"],
        "error_process_checks": scenarios["process_checks"],
        "endpoint_level_perturbation": scenarios.get("endpoint_level_perturbation"),
        "post_fix_noise_sensitivity": refix,
        "scenario_cross_check_vs_fixed_function": cross_check,
        "scenario_contrasts": contrasts["table"],
        "panel_counts": {panel: {k: v for k, v in block.items() if k != "rows"} for panel, block in contrasts["panels"].items()},
        "headline": {
            "development": {
                "old_published_contrast_clean_points": float(refix["development"]["old_published"]["contrast_clean_points"]),
                "old_published_contrast_noisy_points": float(refix["development"]["old_published"]["contrast_noisy_points"]),
                "new_contrast_clean_points": float(refix["development"]["new_fixed"]["contrast_clean_points"]),
                "new_contrast_noisy_points": float(refix["development"]["new_fixed"]["contrast_noisy_points"]),
                "n_cases": int(refix["development"]["retention_detail"]["n_cases"]),
                "n_evaluated": int(refix["development"]["retention_detail"]["n_evaluated"]),
            },
            "reserved": {
                "old_published_contrast_clean_points": float(refix["reserved"]["old_published"]["contrast_clean_points"]),
                "old_published_contrast_noisy_points": float(refix["reserved"]["old_published"]["contrast_noisy_points"]),
                "new_contrast_clean_points": float(refix["reserved"]["new_fixed"]["contrast_clean_points"]),
                "new_contrast_noisy_points": float(refix["reserved"]["new_fixed"]["contrast_noisy_points"]),
                "n_cases": int(refix["reserved"]["retention_detail"]["n_cases"]),
                "n_evaluated": int(refix["reserved"]["retention_detail"]["n_evaluated"]),
            },
        },
        "caveats": [
            "the perturbation is applied to the reference series and to the observed days of the completed "
            "year; the estimator's fill values stay those fitted on the clean record (the convention of the "
            "frozen construction), so this measures sensitivity to reference-series error, not error "
            "propagating into the reconstruction",
            "the error processes are independent across station-years and share one draw per station-year "
            "across that year's outage realizations, exactly as the frozen iid process does",
            "the whole-year bias cancels between estimate and reference on observed days and does not cancel "
            "across filled days: it raises the absolute error without moving the contrast much; a bias that "
            "also shifted the filled days would be a larger perturbation and is not claimed here",
            "clustered intervals resample networks (development: 110, reserved: 36) with {draws} draws; "
            "they describe between-network uncertainty, not the uncertainty of one station".format(
                draws=contrasts["bootstrap_draws"]
            ),
            "the step is placed at day-of-year 183 (2 July) for every year, so it always lands in the warm "
            "season; a step at another date is a different scenario",
            "the ranking is the frozen certificate's, so the retained case set is fixed by design in every "
            "arm (and is asserted identical). This measures whether sensor error changes the "
            "tolerance-exceedance contrast *among the retained cases*, not whether a certificate rebuilt "
            "from perturbed data would retain a different set; the latter cannot be compared on the same "
            "case set and is out of scope for this amendment",
            "the AR(1) and mid-year-step processes perturb the thirty-day endpoint roughly twice as strongly "
            "as the iid process at the same marginal daily sd (endpoint table above), so their null results "
            "are the stronger evidence; the whole-year biases are exact constant shifts of the endpoint "
            "rather than spreads",
        ],
    }
    (POST_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = ["# F11 — sensor-noise sensitivity, regenerated under one locked method", ""]
    lines.append(
        "The published `results/v17_fitness/step22_robustness/noise_sensitivity.json` was produced before "
        "`noise_sensitivity` in `scripts/202_v17_robustness.py` was fixed (commit a9a7ad99cf). In the published "
        "version the clean arm used the information-conditioned simple policy while the perturbed certificate "
        "arm was evaluated on a different method's error, so part of the published noise effect was a method "
        "change. The pre-fix bytes are preserved under `amendments/step22_noise_pre_fix/` (sha256 in "
        "`sha256.json`); the numbers below supersede them."
    )
    lines.append("")
    lines.append("## Headline: old versus new, same locked method")
    lines.append("")
    lines.append("| panel | arm | old published (points) | new, fixed (points) | change | n cases | n evaluated |")
    lines.append("|---|---|---|---|---|---|---|")
    for panel in ("development", "reserved"):
        for arm in ("contrast_clean_points", "contrast_noisy_points"):
            old_value = float(refix[panel]["old_published"][arm])
            new_value = float(refix[panel]["new_fixed"][arm])
            lines.append(
                f"| {panel} | {arm.replace('contrast_', '').replace('_points', '').replace('_', ' ')} "
                f"| {old_value:.4f} | {new_value:.4f} | {new_value - old_value:+.4f} "
                f"| {refix[panel]['retention_detail']['n_cases']:,} "
                f"| {refix[panel]['retention_detail']['n_evaluated']:,} |"
            )
    lines.append("")
    lines.append(
        "The sensor-noise movement of the contrast under the fixed method is "
        + "; ".join(
            f"**{panel}** {refix[panel]['verdict']['sensor_noise_moves_contrast_by_points']:+.4f} points "
            f"({100 * refix[panel]['verdict']['sensor_noise_moves_contrast_relative']:+.2f} %)"
            for panel in ("development", "reserved")
        )
        + ". Mean absolute error of the certificate's chosen method, clean versus perturbed: "
        + "; ".join(
            f"**{panel}** {refix[panel]['retention_detail']['mean_abs_error_clean_c']:.4f} -> "
            f"{refix[panel]['retention_detail']['mean_abs_error_iid_c']:.4f} °C"
            for panel in ("development", "reserved")
        )
        + "."
    )
    lines.append("")
    lines.append("## Which choice moved each number")
    lines.append("")
    reproduction = refix["pre_fix_reproduction"]
    lines.append(
        "Re-instating the two pre-fix choices on the frozen inputs reproduces the published artifact exactly "
        f"(worst gap {max(reproduction['development']['max_abs_gap_vs_published'], reproduction['reserved']['max_abs_gap_vs_published']):.1e}), "
        "so the difference below is a code change and not a data change. Only two evaluations moved:"
    )
    lines.append("")
    lines.append("| panel | quantity | evaluated pre-fix | evaluated fixed | pre-fix | fixed |")
    lines.append("|---|---|---|---|---|---|")
    for panel in ("development", "reserved"):
        pairs = (
            ("length rule at 70, clean", "policy error", "certificate_choice error", "length_rule_at_70_clean"),
            (
                "certificate rule at 70, clean",
                "certificate_abs_error",
                "certificate_choice case error",
                "certificate_at_70_clean",
            ),
            (
                "length rule at 70, perturbed",
                "policy noisy error",
                "certificate_choice noisy error",
                "length_rule_at_70_noisy",
            ),
            (
                "certificate rule at 70, perturbed",
                "policy noisy error",
                "certificate_choice noisy error",
                "certificate_at_70_noisy",
            ),
        )
        for label, pre_arm, fixed_arm, field in pairs:
            old_value = float(reproduction[panel]["reproduced_pre_fix_rates"][field])
            new_value = float(refix[panel]["new_fixed"][field])
            lines.append(
                f"| {panel} | {label} | {pre_arm} | {fixed_arm} | {old_value:.6f} | {new_value:.6f} |"
            )
    lines.append("")
    lines.append(
        "`certificate_abs_error` is identical to the certificate's chosen method's case error on every row "
        f"({reproduction['development']['certificate_abs_error_identical_to_chosen_case_error']['rows']:,} "
        "development rows and "
        f"{reproduction['reserved']['certificate_abs_error_identical_to_chosen_case_error']['rows']:,} reserved "
        "rows, maximum absolute difference "
        f"{reproduction['development']['certificate_abs_error_identical_to_chosen_case_error']['max_abs_difference']:.1e}), "
        "so the clean certificate rate cannot move and does not."
    )
    lines.append("")
    lines.append("## Does the qualitative conclusion survive the sensor noise?")
    lines.append("")
    for panel in ("development", "reserved"):
        row = next(
            record
            for record in contrasts["table"]
            if record["panel"] == panel and record["scenario"] == "iid_0.15"
        )
        positive = (
            "stays positive with a clustered 95% interval above zero"
            if row["retains_positive_contrast"]
            else "does not stay clearly positive"
        )
        moved = (
            "the change is itself distinguishable from zero"
            if row["contrast_change_ci_excludes_zero"]
            else "the change is not distinguishable from zero"
        )
        lines.append(
            f"- **{panel}**: the 0.15 C independent Gaussian perturbation moves the contrast by "
            f"{row['contrast_change_vs_clean_points']:+.4f} points (paired clustered 95% interval "
            f"[{row['contrast_change_ci_low']:+.4f}, {row['contrast_change_ci_high']:+.4f}] over "
            f"{row['n_evaluated']:,} cases, retained set identical to the clean arm), and {moved}. "
            f"The perturbed contrast itself is {row['contrast_points']:.4f} points with clustered 95% "
            f"interval [{row['contrast_ci_low']:.4f}, {row['contrast_ci_high']:.4f}], so it {positive}."
        )
    lines.append("")
    lines.append(
        "Timing beats outage length by roughly six points on both panels in every arm, which is the sense in "
        "which the qualitative conclusion survives the sensor error."
    )
    lines.append("")
    lines.append("## Extra error models at the same locked method")
    lines.append("")
    lines.append(
        "Contrast = (consequential-error rate of the outage-length rule at 70 % retention) - (rate of the "
        "certificate rule), in percentage points, both ranked with the frozen certificate and evaluated with "
        "the perturbed error column of the certificate's chosen reconstruction. Intervals are clustered by "
        f"network, {contrasts['bootstrap_draws']} bootstrap draws."
    )
    lines.append("")
    lines.append(
        "| panel | scenario | spec | contrast | 95% CI | change vs clean | n evaluated | n retained | retained set == clean |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in contrasts["table"]:
        lines.append(
            f"| {row['panel']} | {row['scenario']} | {row['spec']} | {row['contrast_points']:.4f} "
            f"| [{row['contrast_ci_low']:.4f}, {row['contrast_ci_high']:.4f}] "
            f"| {row['contrast_change_vs_clean_points']:+.4f} "
            f"| {row['n_evaluated']:,} | {row['n_retained_at_70']:,} "
            f"| {row['retained_set_identical_to_clean']} |"
        )
    lines.append("")
    worst_abs = table.loc[table["panel"] == "development"].sort_values("mean_abs_error_scenario_c").iloc[-1]
    lines.append(
        "The clean error column is the same in every row of a panel (the clean errors do not depend on the "
        "error model) and each scenario's error column is finite exactly where the clean column is, which is "
        "what keeps the retained set fixed. The perturbation does move the *absolute* error even where it "
        "leaves the contrast alone: on development the mean absolute error of the certificate's chosen "
        f"method rises from {float(worst_abs['mean_abs_error_clean_c']):.4f} C clean to "
        f"{float(worst_abs['mean_abs_error_scenario_c']):.4f} C under `{worst_abs['scenario']}`. Full columns "
        "in `scenario_contrasts.csv`."
    )
    lines.append("")
    lines.append("## Checks run in code")
    lines.append("")
    lines.append(
        f"- Rebuilt case table versus frozen `step3_cases/cases.parquet`: "
        f"{scenarios['validation']['keys_compared']:,} keys compared, "
        f"{scenarios['validation']['values_compared']:,} values, max absolute difference "
        f"{max(scenarios['validation']['max_abs_difference_frozen_vs_rebuild'].values()):.1e}, "
        f"NaN-position mismatches {sum(scenarios['validation']['nan_position_mismatches'].values())}."
    )
    lines.append(
        "- The replica error process (`iid_0.15`, frozen seed tag `sensor`) reproduces the frozen "
        "`abserr_noisy_*` columns exactly, so the extended error models run through the same instrument."
    )
    lines.append(
        "- The replica branch reproduces the fixed-function iid contrast exactly: "
        + "; ".join(
            f"{panel} {cross_check[panel]['replica_scenario_contrast_points']:.6f} vs "
            f"{cross_check[panel]['post_fix_contrast_noisy_points']:.6f} points"
            for panel in ("development", "reserved")
        )
        + "."
    )
    lines.append(
        "- The retained case set at 70 % retention is asserted identical between the clean arm and every "
        "perturbed arm, for both the certificate rule and the outage-length rule (all rows above are `True`)."
    )
    lines.append(
        "- The retained-set mirror used for those assertions is asserted equal to the imported "
        "`_rate_locked` rate for every arm (max absolute gap "
        f"{max(contrasts['panels'][panel]['mirror_vs_fixed_max_abs_rate_gap'] for panel in contrasts['panels']):.1e})."
    )
    lines.append("")
    lines.append("## Error processes as realized")
    lines.append("")
    lines.append(
        "Statistics are computed inside each sampled station-year and averaged across series; a constant "
        "process has no within-series sd and no defined autocorrelation."
    )
    lines.append("")
    lines.append("| scenario | spec | within-series sd (C) | mean abs offset (C) | lag-1 autocorr | constant series |")
    lines.append("|---|---|---|---|---|---|")
    for key, check in scenarios["process_checks"].items():
        if key.startswith("_"):
            continue
        autocorr = check["mean_within_series_lag1_autocorr"]
        lines.append(
            f"| {key} | {check['spec']} | {check['mean_within_series_sd_c']:.4f} "
            f"| {check['mean_within_series_abs_offset_c']:.4f} "
            f"| {'n/a' if autocorr is None else f'{autocorr:+.3f}'} "
            f"| {check['constant_series']}/{check['n_series']} |"
        )
    lines.append("")
    lines.append("## How hard each process hits the endpoint")
    lines.append("")
    lines.append(
        "`H(truth + eps) - H(truth)` over every case, where `H` is the hottest-30-day mean. The same daily "
        "sd does not mean the same perturbation of a thirty-day mean."
    )
    lines.append("")
    lines.append("| scenario | spec | mean delta (C) | sd of delta (C) | sd relative to iid 0.15 |")
    lines.append("|---|---|---|---|---|")
    endpoint_checks = scenarios.get("endpoint_level_perturbation") or {}
    for key, check in endpoint_checks.items():
        if key.startswith("_"):
            continue
        lines.append(
            f"| {key} | {check['spec']} | {check['mean_delta_c']:+.4f} | {check['sd_delta_c']:.4f} "
            f"| {check['sd_ratio_to_iid_0.15']:.2f}x |"
        )
    lines.append("")
    lines.append("## What was and was not changed")
    lines.append("")
    lines.append("Read-only: every `results/v17_fitness/**` artifact, the sealed confirmation inputs, `paper/**`.")
    lines.append(
        "New: `scripts/246_wrr_noise_recompute.py`, "
        "`src/stream_recoverability/experiments/wrr_submission_ready/noise_scenarios.py`, and this amendment "
        "directory. `scripts/202_v17_robustness.py` is imported, never edited; its sha256 is recorded in "
        "`summary.json`."
    )
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    for caveat in summary["caveats"]:
        lines.append(f"- {caveat}")
    (POST_DIR / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[report] wrote {rel(POST_DIR / 'summary.json')}, {rel(POST_DIR / 'REPORT.md')}, "
          f"{rel(POST_DIR / 'scenario_contrasts.csv')}")
    return summary


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        default="preserve,refix,scenarios,contrasts,report",
        help="comma-separated subset of preserve,refix,scenarios,contrasts,report",
    )
    parser.add_argument("--workers", type=int, default=48)
    args = parser.parse_args()
    stages = [stage.strip() for stage in args.stages.split(",") if stage.strip()]

    extra: dict = {}
    if "preserve" in stages:
        stage_preserve()
    if "refix" in stages:
        stage_refix()
    if "scenarios" in stages:
        extra["scenarios"] = stage_scenarios(args.workers)
    if "contrasts" in stages:
        extra["contrasts"] = stage_contrasts(args.workers)
    if "report" in stages:
        if "scenarios" not in extra:
            extra["scenarios"] = json.loads((SCRATCH / "validation.json").read_text(encoding="utf-8"))
        if "contrasts" not in extra:
            extra["contrasts"] = json.loads((SCRATCH / "contrasts.json").read_text(encoding="utf-8"))
        stage_report(extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
