"""Equal-K re-analysis of the Step-5 donor controls (adversarial finding F12).

Two defects motivate this module.

1. *Design.*  ``v17_fitness.mechanism.donor_control_experiment`` advertised a
   donor-count control ("Halving the donor set by training-period correlation
   while holding the count fixed").  It did not hold the count fixed.  It split
   the training-period donor correlations into halves and then intersected each
   half with the decision-time visibility filter, so the strong and the weak arm
   kept *different numbers* of donors (the frozen table records
   ``n_strong - n_weak`` between -7 and +6).  This module implements an exact
   matching design: after the visibility filter, both arms are truncated to the
   same ``K = min(n_visible_strong, n_visible_weak)``, the case is keyed by its
   arm and overlap class, and every compared pair therefore shares donor count,
   outage geometry, station, year and training data.  Three admissible
   within-half selection rules are computed so the result cannot depend on the
   tie-breaking convention: ``top_of_half`` (the rule the later v17 fix used),
   ``gap_minimising`` and ``gap_maximising`` (the two extremes of the
   correlation gap the manipulation can produce).

2. *Provenance.*  ``scripts/183_v17_mechanism.py`` swallowed every worker
   exception (``except Exception: frame = pd.DataFrame()``) and then skipped the
   block that writes the control tables when the concatenated frame was empty,
   while still rewriting ``summary.json``.  A failing run therefore left the
   previous generation's success tables in place beside a summary that denied
   they existed.  ``run_jobs_loudly`` refuses to hide a worker failure and
   ``write_generation``/``verify_generation`` bind every file of a result set to
   one generation id, so a mixed-generation directory is detectable rather than
   plausible.

Nothing here writes to ``results/v17_fitness/**``; the frozen artifacts are
read-only inputs to the comparison.
"""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.experiments.v17_fitness.cases import (
    deseasonalized_correlations,
    station_geometry_pool,
)
from stream_recoverability.experiments.v17_fitness.estimators import (
    StationModels,
    hottest_window_mean,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.mechanism import _phase_shuffled_donors
from stream_recoverability.experiments.v17_fitness.outages import (
    climatological_peak_window,
    design_for_year,
)
from stream_recoverability.experiments.v17_fitness.panel import air_series_for, load_network_panel
from stream_recoverability.experiments.v17_fitness.paths import stable_seed
from stream_recoverability.experiments.wrr_submission_ready.run_identity import sha256_file

# Selection rules applied to the two correlation halves once K is fixed.
# ``top_of_half`` is what the later v17 in-place fix did: take each half's
# highest-correlation visible members.  The other two bracket the manipulation.
MATCH_RULES: tuple[str, ...] = ("top_of_half", "gap_minimising", "gap_maximising")

RULE_DESCRIPTION = {
    "top_of_half": "strong = top-K visible of the strong half, weak = top-K visible of the weak half",
    "gap_minimising": "strong = bottom-K visible of the strong half, weak = top-K visible of the weak half",
    "gap_maximising": "strong = top-K visible of the strong half, weak = bottom-K visible of the weak half",
}

GENERATION_MANIFEST = "MANIFEST.json"


class WorkerFailure(RuntimeError):
    """A parallel worker raised.  Never downgraded to an empty frame."""


class IncompleteGeneration(RuntimeError):
    """The run cannot produce a self-consistent result set, so it must not write one."""


# ---------------------------------------------------------------------------
# The exact-K donor control
# ---------------------------------------------------------------------------


def _subset_for_rule(rule: str, strong_visible: Sequence[str], weak_visible: Sequence[str], k: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the strong and weak donor subsets for one selection rule.

    ``strong_visible``/``weak_visible`` are ordered by descending training-period
    correlation *within their own half*, so index 0 is each half's best donor.
    Both returned tuples have exactly ``k`` members.
    """

    if k < 1:
        raise ValueError("k must be at least 1")
    if rule == "top_of_half":
        return tuple(strong_visible[:k]), tuple(weak_visible[:k])
    if rule == "gap_minimising":
        return tuple(strong_visible[-k:]), tuple(weak_visible[:k])
    if rule == "gap_maximising":
        return tuple(strong_visible[:k]), tuple(weak_visible[-k:])
    raise ValueError(f"unknown match rule: {rule!r}")


def _arm_error(models: StationModels, subset: Sequence[str], observed: np.ndarray, mask: np.ndarray, year_index: pd.DatetimeIndex, truth_metric: float) -> float:
    """Absolute error of the completed-year hot-window mean for one donor subset."""

    if not subset:
        return float("nan")
    fitted = models.donor_ridge(subset)
    if fitted is None:
        return float("nan")
    prediction = models.donor_predict(fitted, year_index)
    completed = observed.copy()
    completed[mask] = prediction[mask]
    if not np.isfinite(completed).all():
        return float("nan")
    return float(abs(hottest_window_mean(completed) - truth_metric))


def donor_control_experiment_paired(job: dict) -> tuple[pd.DataFrame, str]:
    """One pass computing the pre-fix and the exact-K specifications together.

    Running both specifications inside the same loop guarantees they see
    identical outage realizations, identical visibility filters and identical
    seeds, so the old-versus-new difference is a property of the donor-selection
    rule and of nothing else.

    Returns ``(frame, skip_reason)``.  An empty frame always carries a non-empty
    reason, so a silent empty result is impossible to mistake for a processed
    job.
    """

    network_id, station_id = str(job["network_id"]), str(job["station_id"])
    try:
        daily = load_network_panel(network_id, str(job["source_root"]))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        return pd.DataFrame(), f"panel_unavailable:{type(exc).__name__}"
    daily = daily.copy()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame(), "station_absent_from_panel"
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    if donors.shape[1] < 4:
        return pd.DataFrame(), f"too_few_donor_columns:{donors.shape[1]}"
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)
    rows: list[dict[str, Any]] = []
    considered_years = 0

    for year in (int(value) for value in job["complete_years"]):
        year_mask = target.index.year == int(year)
        year_index = daily.index[year_mask]
        truth = target.loc[year_mask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        considered_years += 1
        truth_metric = hottest_window_mean(truth)
        train_mask = pd.Series(~year_mask, index=daily.index)
        correlations = deseasonalized_correlations(target, donors, train_mask).dropna()
        if len(correlations) < 4:
            continue
        ordered = correlations.sort_values(ascending=False)
        k_nominal = len(ordered) // 2
        strong = tuple(ordered.index[:k_nominal])
        weak = tuple(ordered.index[-k_nominal:])

        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), "ctrl"))
        shuffled_donors = _phase_shuffled_donors(donors, rng)

        base_models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        shuffled_models = StationModels(target=target, donors=shuffled_donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(target, exclude_year=int(year))
        realizations = design_for_year(year_index, peak_doys, pool, rng=rng, n_empirical=1)

        for realization in realizations:
            mask = realization.mask(len(year_index))
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            visible = set(usable_donors(donors, year_index, mask))
            # Decision-time visibility filter, then the correlation ordering
            # *within* each half.  Both orderings are deterministic.
            strong_visible = [s for s in strong if s in visible]
            weak_visible = [w for w in weak if w in visible]
            k_matched = min(len(strong_visible), len(weak_visible))

            row: dict[str, Any] = {
                "network_id": network_id,
                "station_id": station_id,
                "year": int(year),
                "realization_id": realization.realization_id,
                "arm": realization.arm,
                "overlap_class": realization.overlap_class,
                "longest_run": int(realization.longest_run),
                "truth_metric": float(truth_metric),
                "n_correlated_donors": int(len(ordered)),
                "k_nominal": int(k_nominal),
                "n_visible": int(len(visible)),
                "n_visible_strong": int(len(strong_visible)),
                "n_visible_weak": int(len(weak_visible)),
                "k_matched": int(k_matched),
                # Pre-fix specification: intersect each half with the visibility
                # filter and keep every survivor, so the two arms differ in count.
                "n_strong_orig": int(len(strong_visible)),
                "n_weak_orig": int(len(weak_visible)),
                "k_orig_diff": int(len(strong_visible) - len(weak_visible)),
                "corr_strong_mean_orig": float(correlations.reindex(strong_visible).mean())
                if strong_visible
                else float("nan"),
                "corr_weak_mean_orig": float(correlations.reindex(weak_visible).mean())
                if weak_visible
                else float("nan"),
            }
            row["abserr_strong_orig"] = _arm_error(
                base_models, tuple(sorted(strong_visible)), observed, mask, year_index, truth_metric
            )
            row["abserr_weak_orig"] = _arm_error(
                base_models, tuple(sorted(weak_visible)), observed, mask, year_index, truth_metric
            )
            row["abserr_all_donors"] = _arm_error(
                base_models, tuple(sorted(visible)), observed, mask, year_index, truth_metric
            )
            row["abserr_anomaly_shuffled"] = _arm_error(
                shuffled_models, tuple(sorted(visible)), observed, mask, year_index, truth_metric
            )
            for rule in MATCH_RULES:
                if k_matched < 1:
                    strong_subset: tuple[str, ...] = ()
                    weak_subset: tuple[str, ...] = ()
                else:
                    strong_subset, weak_subset = _subset_for_rule(rule, strong_visible, weak_visible, k_matched)
                row[f"n_strong_{rule}"] = int(len(strong_subset))
                row[f"n_weak_{rule}"] = int(len(weak_subset))
                row[f"corr_strong_mean_{rule}"] = (
                    float(correlations.reindex(list(strong_subset)).mean()) if strong_subset else float("nan")
                )
                row[f"corr_weak_mean_{rule}"] = (
                    float(correlations.reindex(list(weak_subset)).mean()) if weak_subset else float("nan")
                )
                row[f"abserr_strong_{rule}"] = _arm_error(
                    base_models, strong_subset, observed, mask, year_index, truth_metric
                )
                row[f"abserr_weak_{rule}"] = _arm_error(
                    base_models, weak_subset, observed, mask, year_index, truth_metric
                )
            if row["n_strong_top_of_half"] != row["n_weak_top_of_half"]:
                raise AssertionError(
                    "exact-K matching failed: "
                    f"{row['n_strong_top_of_half']} strong vs {row['n_weak_top_of_half']} weak donors"
                )
            if row["k_matched"] >= 1 and row["n_strong_gap_minimising"] != row["k_matched"]:
                raise AssertionError("gap_minimising arm is not K donors wide")
            rows.append(row)

    if not rows:
        return pd.DataFrame(), f"no_realizations:{considered_years}_years_considered"
    return pd.DataFrame(rows), ""


# ---------------------------------------------------------------------------
# Fail-loud parallel execution
# ---------------------------------------------------------------------------


@dataclass
class JobOutcome:
    """A picklable worker result: rows, or a documented empty result, or an error."""

    key: str
    status: str  # "rows" | "empty" | "error"
    reason: str = ""
    n_rows: int = 0
    frame: pd.DataFrame | None = None
    error: str | None = None


def _job_key(job: Mapping[str, Any]) -> str:
    return f"{job['network_id']}/{job['station_id']}"


def _worker_entry(job: dict) -> JobOutcome:
    key = _job_key(job)
    try:
        frame, reason = donor_control_experiment_paired(job)
    except BaseException as exc:  # noqa: BLE001 — captured, then re-raised in the parent
        return JobOutcome(
            key=key,
            status="error",
            error="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
    if frame.empty:
        if not reason:
            return JobOutcome(key=key, status="error", error="empty frame without a documented reason")
        return JobOutcome(key=key, status="empty", reason=reason)
    return JobOutcome(key=key, status="rows", n_rows=int(len(frame)), frame=frame)


def run_jobs_loudly(
    jobs: Sequence[dict],
    *,
    workers: int = 96,
    executor_factory: Callable[..., Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run ``_worker_entry`` over ``jobs`` and refuse to hide any failure.

    This is the replacement for the ``except Exception: frame = pd.DataFrame()``
    pattern in ``scripts/183_v17_mechanism.py``.  Every submitted job must end
    accounted for as either ``rows`` or a documented ``empty``; anything else
    raises before a single output byte is written.

    Returns ``(concatenated_frame, audit)``.
    """

    from concurrent.futures import ProcessPoolExecutor, as_completed

    if not jobs:
        raise IncompleteGeneration("no jobs submitted")

    factory = executor_factory or ProcessPoolExecutor
    outcomes: dict[str, JobOutcome] = {}
    with factory(max_workers=int(workers)) as pool:
        futures = {pool.submit(_worker_entry, job): _job_key(job) for job in jobs}
        for future in as_completed(futures):
            key = futures[future]
            try:
                outcome = future.result()
            except BaseException as exc:  # noqa: BLE001 — a dead worker is a failed run
                outcomes[key] = JobOutcome(
                    key=key,
                    status="error",
                    error="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                )
                continue
            if not isinstance(outcome, JobOutcome):
                outcomes[key] = JobOutcome(key=key, status="error", error=f"unexpected worker return {type(outcome)!r}")
                continue
            outcomes[key] = outcome

    missing = sorted(_job_key(job) for job in jobs if _job_key(job) not in outcomes)
    errors = sorted((key, outcome.error or "") for key, outcome in outcomes.items() if outcome.status == "error")
    if errors or missing:
        detail = "\n".join(f"--- {key} ---\n{error}" for key, error in errors[:10])
        raise WorkerFailure(
            f"{len(errors)} worker(s) failed and {len(missing)} job(s) were never accounted for; "
            f"refusing to write a partial or stale result set.\n{detail}"
        )

    frames = [outcome.frame for outcome in outcomes.values() if outcome.status == "rows" and outcome.frame is not None]
    if not frames:
        reasons = sorted({outcome.reason for outcome in outcomes.values() if outcome.status == "empty"})
        raise IncompleteGeneration(f"no job produced rows; empty reasons: {reasons[:10]}")
    combined = pd.concat(frames, ignore_index=True)
    audit = {
        "n_jobs_submitted": int(len(jobs)),
        "n_jobs_with_rows": int(sum(1 for o in outcomes.values() if o.status == "rows")),
        "n_jobs_empty_documented": int(sum(1 for o in outcomes.values() if o.status == "empty")),
        "n_jobs_failed": 0,
        "n_rows": int(len(combined)),
        "empty_reasons": sorted({o.reason for o in outcomes.values() if o.status == "empty"}),
    }
    if audit["n_jobs_with_rows"] + audit["n_jobs_empty_documented"] != audit["n_jobs_submitted"]:
        raise IncompleteGeneration("job accounting does not close")
    return combined, audit


def require_controls(frame: pd.DataFrame, *, min_rows: int = 1, min_networks: int = 2) -> dict[str, int]:
    """Guard the invariants a donor-control result set must satisfy to be written."""

    if frame.empty:
        raise IncompleteGeneration("donor control produced no rows; a summary must not be written")
    if len(frame) < int(min_rows):
        raise IncompleteGeneration(f"donor control has {len(frame)} rows, below the required {min_rows}")
    networks = int(frame["network_id"].nunique())
    if networks < int(min_networks):
        raise IncompleteGeneration(
            f"donor control covers {networks} network(s); clustered intervals need at least {min_networks}"
        )
    if bool(frame["network_id"].isna().any()):
        raise IncompleteGeneration("donor control has missing network ids")
    return {"n_cases": int(len(frame)), "n_networks": networks,
            "n_stations": int(frame.groupby(["network_id", "station_id"]).ngroups)}


# ---------------------------------------------------------------------------
# Generation-bound output writing
# ---------------------------------------------------------------------------


def generation_id(artifacts: Mapping[str, bytes], *, inputs: Iterable[Path] = (), code: Iterable[Path] = ()) -> str:
    """Hash the exact bytes of a generation plus its inputs and code."""

    digest = hashlib.sha256()
    for name in sorted(artifacts):
        digest.update(name.encode("utf-8"))
        digest.update(hashlib.sha256(artifacts[name]).digest())
    for path in list(inputs) + list(code):
        resolved = Path(path)
        digest.update(str(resolved).encode("utf-8"))
        digest.update(bytes.fromhex(sha256_file(resolved)) if resolved.is_file() else b"missing")
    return digest.hexdigest()


def write_generation(
    directory: Path,
    artifacts: Mapping[str, str | bytes],
    *,
    summary_name: str = "summary.json",
    inputs: Iterable[Path] = (),
    code: Iterable[Path] = (),
) -> dict[str, Any]:
    """Write one consistent result set, then close it with a hash manifest.

    Files are staged and moved into place, and ``summary.json`` is written
    *after* every table, so a crash mid-write cannot leave a summary that
    describes tables that are not there.  The manifest binds all files to one
    generation id; ``verify_generation`` will refuse a directory whose files do
    not all belong to the recorded generation.
    """

    if summary_name not in artifacts:
        raise IncompleteGeneration(f"generation must contain {summary_name}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        name: (value.encode("utf-8") if isinstance(value, str) else bytes(value))
        for name, value in artifacts.items()
    }
    staged: dict[str, Path] = {}
    for name, blob in payload.items():
        tmp = directory / f".{name}.staged"
        tmp.write_bytes(blob)
        staged[name] = tmp
    order = [name for name in payload if name != summary_name] + [summary_name]
    for name in order:
        os.replace(staged[name], directory / name)
    manifest = {
        "generation_id": generation_id(payload, inputs=inputs, code=code),
        "summary": summary_name,
        "write_order_last": summary_name,
        "files": {name: {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)} for name, blob in payload.items()},
        "inputs": [{"path": str(Path(p)), "sha256": sha256_file(Path(p)) if Path(p).is_file() else None} for p in inputs],
        "code": [{"path": str(Path(p)), "sha256": sha256_file(Path(p)) if Path(p).is_file() else None} for p in code],
    }
    (directory / GENERATION_MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_generation(directory: Path) -> dict[str, Any]:
    """Detect a mixed-generation or partial directory, and raise if found."""

    directory = Path(directory)
    manifest_path = directory / GENERATION_MANIFEST
    if not manifest_path.is_file():
        raise IncompleteGeneration(f"no {GENERATION_MANIFEST} in {directory}; provenance is unverifiable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for name, record in manifest["files"].items():
        path = directory / name
        if not path.is_file():
            problems.append(f"missing file: {name}")
            continue
        actual = sha256_file(path)
        if actual != record["sha256"]:
            problems.append(f"hash mismatch: {name} ({actual[:12]} != {record['sha256'][:12]})")
    present = {p.name for p in directory.iterdir() if p.is_file() and not p.name.startswith(".")}
    unlisted = {
        name
        for name in present
        if name not in manifest["files"] and name != GENERATION_MANIFEST
    }
    if unlisted:
        problems.append(f"unlisted (possible stale) files: {sorted(unlisted)}")
    if problems:
        raise IncompleteGeneration("; ".join(problems))
    return {"generation_id": manifest["generation_id"], "n_files": len(manifest["files"]), "ok": True}


def pre_fix_worker_probe(
    job: dict,
    *,
    ref: str = "fa6547d688",
    scratch_dir: Path,
    relative_path: str = "src/stream_recoverability/experiments/v17_fitness/mechanism.py",
) -> dict[str, Any]:
    """Extract the pre-fix donor control from git and run it on one real job.

    The frozen tables were committed alongside code that used ``stable_seed``
    without importing it.  Rather than assert that, this extracts the committed
    blob and calls it, recording what actually happens.  ``git show`` is
    read-only; the extracted module is written under ``scratch_dir``.
    """

    import importlib.util
    import subprocess

    from stream_recoverability.experiments.wrr_submission_ready.run_identity import REPO_ROOT

    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            ["git", "show", f"{ref}:{relative_path}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    path = scratch_dir / f"pre_fix_mechanism_{ref[:8]}.py"
    path.write_text(completed.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"f12_pre_fix_mechanism_{ref[:8]}", path)
    if spec is None or spec.loader is None:
        return {"available": False, "error": "could not load the extracted module"}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    probe: dict[str, Any] = {
        "available": True,
        "git_ref": ref,
        "extracted_path": str(path),
        "extracted_sha256": sha256_file(path),
        "job": {"network_id": str(job["network_id"]), "station_id": str(job["station_id"])},
        "stable_seed_defined_in_blob": hasattr(module, "stable_seed"),
    }
    try:
        frame = module.donor_control_experiment(job)
        probe.update({"raised": False, "rows": int(len(frame))})
    except BaseException as exc:  # noqa: BLE001 — the failure is the evidence
        probe.update(
            {
                "raised": True,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc().strip().splitlines()[-1],
            }
        )
    return probe


# ---------------------------------------------------------------------------
# Hazard demonstration: what the old writer did with a failing worker
# ---------------------------------------------------------------------------


def legacy_control_block(controls_frames: list[pd.DataFrame], out_dir: Path) -> dict[str, Any]:
    """The control-writing block of ``scripts/183_v17_mechanism.py``, verbatim in shape.

    Kept only as an executable exhibit of the provenance defect: it writes
    ``summary.json`` even when it has no controls, and it never removes the
    previous generation's tables.
    """

    summary_path = out_dir / "summary.json"
    frames = controls_frames
    controls = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    control_summary: dict[str, Any] = {}
    if not controls.empty:
        controls.to_parquet(out_dir / "donor_controls.parquet", index=False)
        (out_dir / "donor_control_summary.csv").write_text("arm,n\nall_donors,%d\n" % len(controls), encoding="utf-8")
        (out_dir / "donor_control_contrasts.csv").write_text("contrast,n_paired\n", encoding="utf-8")
        control_summary = {"n_cases": int(len(controls))}
    else:
        control_table = pd.DataFrame()
        contrast_table = pd.DataFrame()
        _ = (control_table, contrast_table)
    summary = {"importance": {"out_of_fold_r2": 0.3458734271935914}, "controls": control_summary}
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def mixed_generation_hazard_demo(workdir: Path, *, fake_table_bytes: bytes = b"arm,n\nall_donors,12155\n") -> dict[str, Any]:
    """Show that the old writer leaves a stale success table beside an empty summary.

    Deterministic and self-contained: no cluster, no panel data.  A "good"
    generation writes a success table, then a "failing" generation runs the
    legacy block with zero control frames.  The demo records whether the stale
    table survived untouched and whether the new guard would have caught it.
    """

    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    stale = workdir / "donor_control_summary.csv"
    stale.write_bytes(fake_table_bytes)
    before = sha256_file(stale)
    mtime_before = stale.stat().st_mtime_ns

    legacy_summary = legacy_control_block([], workdir)

    after_present = stale.is_file()
    after = sha256_file(stale) if after_present else None
    result: dict[str, Any] = {
        "stale_table_preserved": bool(after_present and after == before),
        "stale_table_sha256": before,
        "stale_table_mtime_unchanged": bool(after_present and stale.stat().st_mtime_ns == mtime_before),
        "summary_controls": legacy_summary["controls"],
        "summary_claims_zero_controls": legacy_summary["controls"] == {},
        "mixed_generation_state": bool(after_present and legacy_summary["controls"] == {}),
    }
    # The new guard must refuse to fabricate that state.
    try:
        require_controls(pd.DataFrame(), min_rows=1, min_networks=2)
        result["new_guard_refused"] = False
        result["new_guard_error"] = None
    except IncompleteGeneration as exc:
        result["new_guard_refused"] = True
        result["new_guard_error"] = str(exc)
    try:
        verify_generation(workdir)
        result["verify_generation_caught_mixed_state"] = False
        result["verify_generation_error"] = None
    except IncompleteGeneration as exc:
        result["verify_generation_caught_mixed_state"] = True
        result["verify_generation_error"] = str(exc)
    return result
