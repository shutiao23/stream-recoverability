#!/usr/bin/env python3
"""Fixed-budget residual-bridge sensitivity with frozen daily-model inputs.

The original six stations / 27 station-years are reused. Each daily model,
whole-archive mask and residual history is fixed before any seed comparison.
For each of three declared seeds, 20/100/500 are prefixes of the same 500-path
sample. This is a finite-subset Monte Carlo diagnostic, not a convergence or
source-role calibration check. No source-role offsets are re-estimated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.tr_revision.archive import LEVELS, mask_archive
from stream_recoverability.experiments.tr_revision.baselines import ar1_bridge
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.seeds import plain_seed

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/wrr_review_response_20261027/whole_archive"
E1_GEN = ROOT / "results/wrr_target_recovery_20261021/e1_missingness/mnar_generator.json"
ORIGINAL = ROOT / "results/wrr_process_review_20261028/trajectory_nested_cases.csv"
OUT = ROOT / "results/wrr_process_revision_20261029"
PAPER = ROOT / "paper/wrr_tr"
COUNTS = (20, 100, 500)
SEEDS = (0, 1, 2)
THRESHOLD_C = 0.05
PREDECLARED = [
    "foen|2016", "foen|2019", "foen|2029",
    "gkd_bayern|10026293", "gkd_bayern|10039802", "gkd_bayern|10046105",
]
CASE_KEYS = ["station_key", "year"]
STRATA = ["region", "reconstructor"]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_hash(*values: np.ndarray) -> str:
    digest = hashlib.sha256()
    for value in values:
        array = np.ascontiguousarray(np.asarray(value, dtype="<f8"))
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def parse_draws(value) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return np.asarray(value, float)
    if isinstance(value, (list, tuple)):
        return np.asarray(value, float)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            return np.asarray(json.loads(text), float)
        return np.asarray([float(x) for x in text.split(";") if x], float)
    return np.asarray(list(value), float)


def quantile_row(draws: np.ndarray) -> dict:
    draws = np.asarray(draws, float)
    draws = draws[np.isfinite(draws)]
    out = {f"q{int(100 * level):02d}": float(np.quantile(draws, level)) for level in LEVELS}
    out["n_draws"] = int(len(draws))
    out["width90"] = out["q95"] - out["q05"]
    return out


def scores(draws: np.ndarray, truth: float, bound: float) -> dict:
    draws = np.asarray(draws, float)
    draws = draws[np.isfinite(draws)]
    if np.isfinite(bound):
        draws = np.maximum(draws, bound)
    if draws.size == 0 or not np.isfinite(truth):
        return {}
    q = quantile_row(draws)
    q.update(
        mae=abs(q["q50"] - truth),
        bias=q["q50"] - truth,
        coverage90=float(q["q05"] - 1e-8 <= truth <= q["q95"] + 1e-8),
        crps=sample_crps(draws, truth),
        truth=float(truth),
    )
    return q


def prepare_station(job: dict, output: Path) -> list[dict]:
    """Freeze the original replay inputs once, before varying bridge seeds."""
    folder = BASE / "crossed/forward/replicate_00" / job["station_key"].replace("|", "_")
    design_path = folder / "design.json"
    design = json.loads(design_path.read_text())
    truth = pd.read_parquet(
        ROOT / "results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet",
        columns=["station_key", "year", "design_family", "eval_truth_h30"],
    )
    truth = truth.loc[truth.station_key.eq(job["station_key"]) & truth.design_family.eq("crossed")]
    truth = truth.drop_duplicates("year").set_index("year").eval_truth_h30
    core = T.load_script("trajectory_budget_frozen_cases", ROOT / "scripts/431_tr_cases.py")
    # Keep regeneration caches inside the new revision directory.
    core.CACHE = output / "daily_fit_replay"
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    real_index = panel.index
    analysis = panel.copy()
    analysis.index += pd.Timedelta(days=T.hemisphere_shift_days(job.get("latitude")))
    masks = {int(year): runs for year, runs in design["masks"].items()}
    visible = mask_archive(analysis, job["station_id"], masks)
    settings = T.settings() | {
        "version": "trajectory_budget/frozen500",
        "replication_seeds": [0],
        "training_split": "before_2010",
        "classical_baselines": True,
        "trajectory_targets": ["h30"],
        "trajectory_draws": 8,
        "multiple_imputations": 500,
    }
    by_seed = {plain_seed(9, 0, job["station_index"], year, 0): year for year in masks}
    captured = {}

    def capture(observed, mean, residual, seed, draws=20):
        year = by_seed[int(seed)]
        captured[year] = tuple(np.asarray(x, float).copy() for x in (observed, mean, residual))
        return ar1_bridge(observed, mean, residual, seed, draws)

    core.ar1_bridge = capture
    with TemporaryDirectory(dir=output) as temporary:
        path = Path(temporary) / "visible.csv"
        water = visible.copy()
        water.index = real_index
        water.index.name = "date"
        water.to_csv(path)
        local = job | {"input_path": str(path), "roster": "real", "real_years": sorted(masks)}
        result = core.station_cases(local, settings, json.loads(E1_GEN.read_text()), [], False)
    if not result.get("cache"):
        raise RuntimeError(f"No replay inputs for {job['station_key']}: {result}")
    generated = pd.read_parquet(result["cache"])
    generated = generated.loc[generated.design_family.eq("real")].set_index("year")
    rows = []
    original_cases = pd.read_csv(ORIGINAL)
    original_years = set(original_cases.loc[original_cases.station_key.eq(job["station_key"]), "year"])
    frozen = output / "trajectory_frozen_inputs"
    frozen.mkdir(exist_ok=True)
    for year, (observed, mean, residual) in sorted(captured.items()):
        # Keep exactly the originally scored cases. One original archive year
        # has no usable bridge residual history and was already unsupported.
        if year not in original_years:
            continue
        row = generated.loc[year]
        filename = f"{job['station_key'].replace('|', '_')}_{year}.npz"
        np.savez_compressed(frozen / filename, observed=observed, mean=mean, residual=residual)
        finite = residual[np.isfinite(residual)]
        pairs = np.isfinite(residual[:-1]) & np.isfinite(residual[1:])
        phi = np.corrcoef(residual[:-1][pairs], residual[1:][pairs])[0, 1] if pairs.sum() > 10 else 0.0
        rows.append({
            "station_key": job["station_key"], "station_index": int(job["station_index"]),
            "region": job["region"], "independence_group": job["independence_group"],
            "year": int(year), "reconstructor": str(row.policy_choice),
            "truth": float(truth.loc[year]), "bound": float(row.observed_lower_bound__observed_days),
            "mask_runs": str(row.mask_runs), "training_split": "before_2010",
            "residual_mu": float(finite.mean()), "residual_sigma": max(float(finite.std(ddof=1)), 1e-3),
            "residual_phi": float(np.clip(np.nan_to_num(phi), -0.95, 0.995)),
            "input_file": str((frozen / filename).relative_to(output)),
            "input_sha256": array_hash(observed, mean, residual),
            "design_sha256": file_hash(design_path),
        })
    return rows


def validate_case_set(manifest: pd.DataFrame, original: pd.DataFrame) -> None:
    expected = original[CASE_KEYS].drop_duplicates().sort_values(CASE_KEYS).reset_index(drop=True)
    actual = manifest[CASE_KEYS].sort_values(CASE_KEYS).reset_index(drop=True)
    if manifest.duplicated(CASE_KEYS).any() or not actual.equals(expected):
        raise ValueError("Frozen case set differs from the original 27 station-years")
    if len(actual) != 27 or set(manifest.station_key) != set(PREDECLARED):
        raise ValueError("Expected exactly the original six stations / 27 station-years")
    if manifest.independence_group.nunique() != 2:
        raise ValueError("Expected the original two connected groups")


def sample_frozen(manifest: pd.DataFrame, output: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, draw_rows = [], []
    for case in manifest.itertuples(index=False):
        with np.load(output / case.input_file) as data:
            observed, mean, residual = (data[key] for key in ("observed", "mean", "residual"))
            if array_hash(observed, mean, residual) != case.input_sha256:
                raise ValueError(f"Frozen input changed: {case.station_key} / {case.year}")
            for repeat_seed in SEEDS:
                bridge_seed = plain_seed(9, repeat_seed, case.station_index, case.year, 0)
                paths = ar1_bridge(observed, mean, residual, bridge_seed, max(COUNTS))
                draws = T.window_means(paths, 30).max(axis=1)
                if len(draws) != max(COUNTS) or not np.isfinite(draws).all():
                    raise ValueError(f"Incomplete bridge draws: {case.station_key} / {case.year}")
                shared = {key: getattr(case, key) for key in CASE_KEYS + STRATA + ["independence_group"]}
                shared.update(seed=repeat_seed, bridge_seed=int(bridge_seed), input_sha256=case.input_sha256)
                draw_rows.append(shared | {"h30_draws": draws.tolist()})
                for count in COUNTS:
                    rows.append(shared | {"count": count} | scores(draws[:count], case.truth, case.bound))
    return pd.DataFrame(rows), pd.DataFrame(draw_rows)


def case_deltas(replay: pd.DataFrame) -> pd.DataFrame:
    """Paired absolute endpoint changes; never gate them by an overall median."""
    keys = ["seed"] + CASE_KEYS + STRATA + ["independence_group"]
    base = replay.loc[replay["count"].eq(20)].set_index(keys)
    rows = []
    for count in (100, 500):
        other = replay.loc[replay["count"].eq(count)].set_index(keys)
        pair = base[["q05", "q50", "q95", "width90", "coverage90"]].join(
            other[["q05", "q50", "q95", "width90", "coverage90"]], lsuffix="_20", rsuffix="_other", validate="one_to_one"
        ).reset_index()
        pair["comparison"] = f"20_to_{count}"
        for tail in ("q05", "q50", "q95"):
            pair[f"delta_{tail}"] = pair[f"{tail}_other"] - pair[f"{tail}_20"]
            pair[f"abs_delta_{tail}"] = pair[f"delta_{tail}"].abs()
            pair[f"{tail}_exceeds_005"] = pair[f"abs_delta_{tail}"] > THRESHOLD_C
        pair["either_tail_exceeds_005"] = pair.q05_exceeds_005 | pair.q95_exceeds_005
        pair["width_change"] = pair.width90_other - pair.width90_20
        pair["coverage_changed"] = pair.coverage90_other.ne(pair.coverage90_20)
        rows.append(pair)
    return pd.concat(rows, ignore_index=True)


def tail_summary(deltas: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, block in deltas.groupby(["seed", "comparison"] + STRATA):
        row = dict(zip(["seed", "comparison"] + STRATA, keys))
        row.update(n_cases=len(block), n_stations=block.station_key.nunique(), n_groups=block.independence_group.nunique())
        for tail in ("q05", "q50", "q95"):
            row[f"median_abs_delta_{tail}"] = float(block[f"abs_delta_{tail}"].median())
            row[f"max_abs_delta_{tail}"] = float(block[f"abs_delta_{tail}"].max())
            row[f"n_{tail}_exceeds_005"] = int(block[f"{tail}_exceeds_005"].sum())
        row["n_either_tail_exceeds_005"] = int(block.either_tail_exceeds_005.sum())
        row["n_coverage_changed"] = int(block.coverage_changed.sum())
        rows.append(row)
    return pd.DataFrame(rows)


def score_summary(replay: pd.DataFrame, strata: bool = True) -> pd.DataFrame:
    keys = ["seed", "count"] + (STRATA if strata else [])
    return replay.groupby(keys).agg(
        n_cases=("truth", "size"), n_stations=("station_key", "nunique"),
        n_groups=("independence_group", "nunique"),
        n_covered=("coverage90", "sum"), coverage90=("coverage90", "mean"),
        mean_width90=("width90", "mean"), mean_mae=("mae", "mean"), mean_crps=("crps", "mean"),
    ).reset_index()


def source_calibration_status() -> dict:
    """An explicit scope statement, with no target-subset calibration surrogate."""
    return {
        "source_role_offsets_reestimated": False,
        "source_role_calibration_sensitivity_executed": False,
        "target_subset_even_odd_calibration_executed": False,
        "trajectory_count_convergence_established": False,
        "fine_method_ranking_robustness_established": False,
        "interpretation": "This 962 package is an uncalibrated nested-prefix diagnostic on two groups. "
        "It does not re-estimate source-role offsets. Source-role recalibration is a separate experiment "
        "(scripts/968). Fully sampled tails and fine method rankings remain unresolved in this package.",
    }
def seed_ranges(summary: pd.DataFrame) -> pd.DataFrame:
    values = [name for name in summary if name.startswith(("median_", "max_", "n_"))]
    rows = []
    for keys, block in summary.groupby(["comparison"] + STRATA):
        row = dict(zip(["comparison"] + STRATA, keys))
        row["n_seeds"] = block.seed.nunique()
        for value in values:
            row[f"{value}_min"] = float(block[value].min())
            row[f"{value}_max"] = float(block[value].max())
        rows.append(row)
    return pd.DataFrame(rows)


def write_paper_outputs(deltas: pd.DataFrame, tails: pd.DataFrame, overall: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    final = deltas.loc[deltas.comparison.eq("20_to_500")]
    original = final.loc[final.seed.eq(0)]
    swiss = tails.loc[tails.seed.eq(0) & tails.comparison.eq("20_to_500") & tails.region.eq("foen")].iloc[0]
    bavaria = tails.loc[tails.seed.eq(0) & tails.comparison.eq("20_to_500") & tails.region.eq("gkd_bayern")].iloc[0]
    original_scores = overall.loc[overall.seed.eq(0)].set_index("count")
    values = {
        "PRTrajRevisionSeeds": ", ".join(map(str, SEEDS)), "PRTrajRevisionN": "27", "PRTrajRevisionGroups": "2",
        "PRTrajRevisionSwissUpperMedian": f"{swiss.median_abs_delta_q95:.4f}",
        "PRTrajRevisionBavariaUpperMedian": f"{bavaria.median_abs_delta_q95:.4f}",
        "PRTrajRevisionBavariaUpperExceed": str(int(bavaria.n_q95_exceeds_005)),
        "PRTrajRevisionUpperMax": f"{original.abs_delta_q95.max():.4f}",
        "PRTrajRevisionUpperExceed": str(int(original.q95_exceeds_005.sum())),
        "PRTrajRevisionEitherExceed": str(int(original.either_tail_exceeds_005.sum())),
        "PRTrajRevisionWidthTwenty": f"{original_scores.loc[20].mean_width90:.4f}",
        "PRTrajRevisionWidthFiveHundred": f"{original_scores.loc[500].mean_width90:.4f}",
        "PRTrajRevisionWidthIncrease": f"{100 * (original_scores.loc[500].mean_width90 / original_scores.loc[20].mean_width90 - 1):.1f}",
        "PRTrajRevisionCoveredTwenty": str(int(original_scores.loc[20].n_covered)),
        "PRTrajRevisionCoveredFiveHundred": str(int(original_scores.loc[500].n_covered)),
    }
    for region, label in (("foen", "Swiss"), ("gkd_bayern", "Bavaria")):
        block = tails.loc[tails.comparison.eq("20_to_500") & tails.region.eq(region)]
        values[f"PRTrajRevision{label}UpperMedianRange"] = f"{block.median_abs_delta_q95.min():.4f}--{block.median_abs_delta_q95.max():.4f}"
        values[f"PRTrajRevision{label}UpperExceedRange"] = f"{int(block.n_q95_exceeds_005.min())}--{int(block.n_q95_exceeds_005.max())}"
    (PAPER / "process_trajectory_revision_values.tex").write_text(
        "% Generated by scripts/962_process_trajectory_budget.py; no source-role recalibration.\n" +
        "\n".join("\\newcommand{\\" + key + "}{" + value + "}" for key, value in values.items()) + "\n"
    )
    lines = [
        r"\begin{table}[p]\centering\small",
        r"\caption{Fixed-input trajectory sensitivity, 20 to 500 nested draws, by seed and region--reconstructor stratum. Med./max. are absolute 95th-percentile changes in $^{\circ}$C. Tail count is the number with either endpoint moving by more than 0.05$^{\circ}$C. Intervals are uncalibrated; each stratum is one connected group.}",
        r"\label{tab:trajectory-revision}",
        r"\begin{tabular}{llrrrrr}", r"\toprule",
        r"Seed & Stratum & $n$ & Med./max. & Tail count & Width 20/500 & Covered 20/500 \\",
        r"\midrule",
    ]
    strat_scores = score_summary(pd.read_csv(OUT / "trajectory_revision_nested_cases.csv")).set_index(["seed", "count"] + STRATA)
    for row in tails.loc[tails.comparison.eq("20_to_500")].itertuples(index=False):
        a = strat_scores.loc[(row.seed, 20, row.region, row.reconstructor)]
        b = strat_scores.loc[(row.seed, 500, row.region, row.reconstructor)]
        name = "Switzerland / donor" if row.region == "foen" else "Bavaria / air"
        lines.append(f"{row.seed} & {name} & {row.n_cases} & {row.median_abs_delta_q95:.4f}/{row.max_abs_delta_q95:.4f} & {row.n_either_tail_exceeds_005} & {a.mean_width90:.3f}/{b.mean_width90:.3f} & {int(a.n_covered)}/{int(b.n_covered)}" + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER / "process_trajectory_revision_table.tex").write_text("\n".join(lines) + "\n")
    (PAPER / "process_trajectory_revision_supporting.tex").write_text(
        r"\paragraph{Fixed-budget trajectory sensitivity.} "
        r"The six-station diagnostic was selected after the original results were known and is exploratory. "
        r"The original 27 station-years, whole-archive masks, before-2010 daily fits, residual histories and bridge parameters remain fixed. "
        r"Seeds 0, 1 and 2 change only the residual-bridge random stream; 20/100/500 are prefixes of the same 500-path sample for each seed. "
        r"Seed 0 reproduces the original saved case quantiles. Each of the two region--reconstructor strata belongs to one connected group: "
        r"18 Swiss donor-ridge cases and nine Bavarian air-ridge cases. Region, reconstructor and group therefore cannot be separated by this diagnostic. "
        r"Casewise endpoint changes, counts exceeding 0.05$^{\circ}$C, width and coverage are reported for every seed. "
        r"A small overall median does not establish tail stability in either stratum. "
        r"The 20-path comparator is a fixed computational-budget implementation. This 962 diagnostic does not re-estimate source-role offsets, "
        r"and no target-subset even/odd calibration was performed. The current paper's source-role experiment is scripts/968, which re-estimates original-role offsets at each budget before scoring the same 27 targets. "
        r"These uncalibrated results do not establish convergence or a robust fine ranking between methods. "
        r"\input{process_trajectory_revision_table.tex}" + "\n"
    )
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "ps.fonttype": 42})
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.7), gridspec_kw={"width_ratios": [1.5, 1]})
    order = original.sort_values(STRATA + CASE_KEYS)[CASE_KEYS]
    position = {tuple(row): k for k, row in enumerate(order.itertuples(index=False, name=None))}
    colors = ["#176b87", "#d17925", "#75608c"]
    for seed, color in zip(SEEDS, colors):
        block = final.loc[final.seed.eq(seed)]
        x = np.array([position[(row.station_key, row.year)] for row in block.itertuples(index=False)])
        y = block[["abs_delta_q05", "abs_delta_q95"]].max(axis=1)
        axes[0].scatter(x + (seed - 1) * .15, y, color=color, s=18, label=f"Seed {seed}", alpha=.85)
    axes[0].axvline(17.5, color=".7", linewidth=.8)
    axes[0].set_xticks([8.5, 22], ["Switzerland / donor ridge\n18 cases, 1 group", "Bavaria / air ridge\n9 cases, 1 group"])
    axes[0].set_ylabel("Larger absolute endpoint change ($^{\\circ}$C)")
    axes[0].set_xlabel("Fixed station-year cases; 20 to 500 paths")
    axes[0].legend(frameon=False, ncol=3, loc="upper left", fontsize=8)
    for k, region in enumerate(("foen", "gkd_bayern")):
        for seed, color in zip(SEEDS, colors):
            block = final.loc[final.region.eq(region) & final.seed.eq(seed)]
            x = k + (seed - 1) * .18
            axes[1].plot([x, x], [block.abs_delta_q95.median(), block.abs_delta_q95.max()], color=color, linewidth=1.3)
            axes[1].scatter(x, block.abs_delta_q95.median(), color=color, s=28)
            axes[1].scatter(x, block.abs_delta_q95.max(), color=color, marker="x", s=28)
    axes[1].set_xticks([0, 1], ["Switzerland\ndonor ridge", "Bavaria\nair ridge"])
    axes[1].set_ylabel("Absolute 95th-percentile change ($^{\\circ}$C)")
    axes[1].set_title("Dots: median; crosses: maximum", fontsize=9)
    axes[1].set_xlim(-.5, 1.5)
    for ax in axes:
        ax.axhline(.05, color=".35", linestyle="--", linewidth=.9)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(bottom=-.01)
    fig.tight_layout()
    figdir = PAPER / "figures/process_revision"
    figdir.mkdir(parents=True, exist_ok=True)
    # Do not overwrite Figure 11. The manuscript figure is written by 970 from the
    # source-role experiment; this uncalibrated diagnostic is a named reference only.
    fig.savefig(figdir / "04_trajectory_budget_uncalibrated.pdf", bbox_inches="tight")
    fig.savefig(figdir / "04_trajectory_budget_uncalibrated.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    (figdir / "04_trajectory_budget_uncalibrated.source.json").write_text(json.dumps({
        "script": "scripts/962_process_trajectory_budget.py", "cases": "results/wrr_process_revision_20261029/trajectory_revision_case_deltas.csv",
        "seeds": list(SEEDS), "comparison": "20_to_500", "source_role_offsets_reestimated": False,
        "manuscript_figure": "04_trajectory_budget is written by scripts/970_process_experiment_report.py",
    }, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true", help="Prepare missing frozen daily-model inputs from the original masked archives")
    parser.add_argument("--refresh-frozen", action="store_true", help="Rebuild frozen daily inputs and check exact seed-0 reproduction")
    args = parser.parse_args()
    started = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "trajectory_revision_frozen_manifest.csv"
    if args.refresh_frozen or not manifest_path.exists():
        if not (args.replay or args.refresh_frozen):
            parser.error("Run with --replay once to prepare the frozen daily-model inputs")
        core = T.load_script("trajectory_budget_jobs", ROOT / "scripts/431_tr_cases.py")
        jobs = {job["station_key"]: job for job in core.jobs_for("source") if job["station_key"] in PREDECLARED}
        manifests = []
        for key in PREDECLARED:
            print("FREEZE DAILY INPUTS", key, flush=True)
            manifests.extend(prepare_station(jobs[key], OUT))
        manifest = pd.DataFrame(manifests)
        manifest.to_csv(manifest_path, index=False)
    else:
        manifest = pd.read_csv(manifest_path)
    original = pd.read_csv(ORIGINAL)
    validate_case_set(manifest, original)
    replay, draws = sample_frozen(manifest, OUT)
    zero = replay.loc[replay.seed.eq(0)].set_index(CASE_KEYS + ["count"]).sort_index()
    old = original.set_index(CASE_KEYS + ["count"]).sort_index()
    if not np.allclose(zero[["q05", "q50", "q95"]], old[["q05", "q50", "q95"]], atol=1e-8, rtol=0):
        raise ValueError("Seed 0 no longer reproduces the original fixed-case quantiles")
    replay.to_csv(OUT / "trajectory_revision_nested_cases.csv", index=False)
    draws.to_parquet(OUT / "trajectory_revision_h30_draws.parquet", index=False)
    deltas = case_deltas(replay)
    tails = tail_summary(deltas)
    overall = score_summary(replay, strata=False)
    deltas.to_csv(OUT / "trajectory_revision_case_deltas.csv", index=False)
    tails.to_csv(OUT / "trajectory_revision_stratum_tails.csv", index=False)
    seed_ranges(tails).to_csv(OUT / "trajectory_revision_seed_ranges.csv", index=False)
    score_summary(replay).to_csv(OUT / "trajectory_revision_stratum_scores.csv", index=False)
    overall.to_csv(OUT / "trajectory_revision_overall_scores.csv", index=False)
    groups = manifest.groupby(["independence_group"] + STRATA).agg(
        n_cases=("year", "size"), n_stations=("station_key", "nunique"),
        first_year=("year", "min"), last_year=("year", "max"),
        station_keys=("station_key", lambda x: ";".join(sorted(set(x)))),
    ).reset_index()
    groups.to_csv(OUT / "trajectory_revision_group_scope.csv", index=False)
    write_paper_outputs(deltas, tails, overall)
    report = {
        "predeclared_stations": PREDECLARED,
        "selection_note": "Original six-station subset fixed before this replay; the diagnostic itself is post hoc, not preregistered.",
        "counts": list(COUNTS), "seeds": list(SEEDS), "n_cases_per_seed": len(manifest),
        "bridge_seed_formula": "plain_seed(9, repeat_seed, station_index, year, 0)",
        "nested_sampling": "One 500-path sample per frozen case and seed; budgets are its first 20, 100, or 500 H30 draws.",
        "threshold_c": THRESHOLD_C, "d2_not_refit": True, "daily_inputs_fixed_across_seeds": True,
        "original_seed_zero_reproduced": True, "source_calibration": source_calibration_status(),
        "scope": groups.to_dict("records"),
        "stratified_20_to_500": tails.loc[tails.comparison.eq("20_to_500")].to_dict("records"),
        "runtime_seconds": time.monotonic() - started,
        "daily_inputs_refreshed_this_run": bool(args.refresh_frozen),
        "command": "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src python scripts/962_process_trajectory_budget.py --replay" + (" --refresh-frozen" if args.refresh_frozen else ""),
    }
    (OUT / "trajectory_revision_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(tails.loc[tails.comparison.eq("20_to_500")].to_string(index=False), flush=True)
    print(overall.to_string(index=False), flush=True)
    print(f"Runtime: {report['runtime_seconds']:.2f} seconds", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
