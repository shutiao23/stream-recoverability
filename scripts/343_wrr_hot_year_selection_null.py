#!/usr/bin/env python3
"""R2-04 (review op. 7, 2026-10-20b) -- is refusing hot years a hot-year harm?

The aligned round reported that the fitted score refuses 25 % of the true hot
years and read it as damage to the archive's purpose.  A rule that ignores
whether a year is hot and keeps 74 % of everything also refuses about 26 % of the
hot years.  The refusal share is therefore an *information-loss* number until it
is compared with the refusal of the other records.  This script reports

1. ``excess_hot_refusal = retention(all) - retention(hot years)``: positive when
   hot years are refused more often than records in general, with a
   shared-station-group clustered interval;
2. the action-cost view: an admitted record is judged hot/cool from its
   reconstruction, a refused record is an abstention.  The total loss of an arm
   is ``rho*FN + FP + c_A*A`` per case.  The *break-even abstention cost*
   ``c_A*`` is the cost of one abstention at which the arm and the
   reconstruct-everything arm have the same loss; a screen pays only when an
   abstention costs less than ``c_A*`` wrong judgements.

Inputs are the case-level admissions of scripts 330 and 341 and, for the real
calendars, those of script 331.  Nothing is refitted.

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/r2_04_hot_year_null/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

OUT = C.RUN / "r2_04_hot_year_null"
SEEDS = (101, 202, 303)
HOT = (18.0, 20.0)
RHO = (1.0, 2.0, 5.0, 10.0)
DRAWS = 4000
ARMS_330 = ("fitted_risk", "calibrated_bound", "peak_overlap_rule", "length_rule", "reconstruct_all")
ESTIMATORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
PANELS = {
    "wave2_confirmation": C.EXTERNAL_PARQUET,
    "development": None,  # filled below (path helper imports the package)
}


def policy_prediction(cases: pd.DataFrame) -> np.ndarray:
    choice = cases["policy_choice"].astype(str).to_numpy()
    pred = np.full(len(cases), np.nan)
    for name in ESTIMATORS:
        mask = choice == name
        col = f"hottest30_{name}"
        if mask.any() and col in cases.columns:
            pred[mask] = pd.to_numeric(cases.loc[mask, col], errors="coerce").to_numpy(dtype=float)
    return pred


def boot_sums(codes: np.ndarray, columns: dict[str, np.ndarray], n_groups: int, seed: int):
    """Per-group sums for a dict of columns, plus one shared set of resamples."""

    sums = {k: np.bincount(codes, weights=v.astype(float), minlength=n_groups) for k, v in columns.items()}
    resamples = np.random.default_rng(seed).integers(0, n_groups, size=(DRAWS, n_groups))
    return sums, resamples


def interval(draws: np.ndarray) -> tuple[float, float]:
    finite = draws[np.isfinite(draws)]
    if not finite.size:
        return float("nan"), float("nan")
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))


def ratio_draws(sums, resamples, num: str | list[str], den: str | list[str], sign=None) -> np.ndarray:
    def total(keys):
        keys = [keys] if isinstance(keys, str) else keys
        return sum(sums[k][resamples].sum(axis=1) for k in keys)

    n, d = total(num), total(den)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(d > 0, n / np.maximum(d, 1e-12), np.nan)


def analyse(frame: pd.DataFrame, truth: np.ndarray, pred: np.ndarray, hot_c: float, arms, group_codes, label, seed0):
    n_groups = int(group_codes.max()) + 1
    truth_hot = truth > hot_c
    pred_hot = pred > hot_c
    valid = np.isfinite(truth) & np.isfinite(pred)
    rows = []
    all_adm = valid.copy()
    # reference arm quantities (reconstruct everything)
    ref = {
        "fp": (all_adm & pred_hot & ~truth_hot),
        "fn": (all_adm & ~pred_hot & truth_hot),
    }
    for arm in arms:
        adm = frame[f"admit_{arm}"].to_numpy(dtype=bool) & valid
        refused = ~adm
        cols = {
            "n": np.ones(len(frame)),
            "adm": adm.astype(float),
            "hot": truth_hot.astype(float),
            "adm_hot": (adm & truth_hot).astype(float),
            "cool": (~truth_hot).astype(float),
            "adm_cool": (adm & ~truth_hot).astype(float),
            "fp": (adm & pred_hot & ~truth_hot).astype(float),
            "fn": (adm & ~pred_hot & truth_hot).astype(float),
            "refused": refused.astype(float),
            "fp_all": ref["fp"].astype(float),
            "fn_all": ref["fn"].astype(float),
        }
        sums, rs = boot_sums(group_codes, cols, n_groups, seed0)
        t = {k: v.sum() for k, v in cols.items()}
        r = t["adm"] / t["n"]
        r_hot = t["adm_hot"] / t["hot"]
        r_cool = t["adm_cool"] / t["cool"]
        d_r = ratio_draws(sums, rs, "adm", "n")
        d_hot = ratio_draws(sums, rs, "adm_hot", "hot")
        d_cool = ratio_draws(sums, rs, "adm_cool", "cool")
        excess = d_r - d_hot  # >0: hot years refused more than records in general
        lo, hi = interval(excess)
        gap = d_hot - d_cool
        glo, ghi = interval(gap)
        row = {
            "panel": label, "hot_c": hot_c, "arm": arm, "n_cases": int(t["n"]),
            "retention": r, "retention_hot": r_hot, "retention_cool": r_cool,
            "refused_hot_share": 1 - r_hot,
            "same_retention_random_refusal": 1 - r,
            "excess_hot_refusal": r - r_hot, "excess_ci_low": lo, "excess_ci_high": hi,
            "hot_minus_cool_retention": r_hot - r_cool, "hot_minus_cool_ci_low": glo, "hot_minus_cool_ci_high": ghi,
            "false_hot": int(t["fp"]), "missed_hot": int(t["fn"]),
            "wrong_judgement_rate": (t["fp"] + t["fn"]) / t["n"],
            "abstention_rate": t["refused"] / t["n"],
        }
        for rho in RHO:
            err_all = rho * t["fn_all"] + t["fp_all"]
            err_arm = rho * t["fn"] + t["fp"]
            a = t["refused"]
            row[f"breakeven_abstention_cost_rho{int(rho)}"] = (err_all - err_arm) / a if a > 0 else np.nan
            if a > 0:
                num = rho * sums["fn_all"][rs].sum(axis=1) + sums["fp_all"][rs].sum(axis=1) - (
                    rho * sums["fn"][rs].sum(axis=1) + sums["fp"][rs].sum(axis=1)
                )
                den = sums["refused"][rs].sum(axis=1)
                with np.errstate(invalid="ignore", divide="ignore"):
                    d = np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)
                l, h = interval(d)
                row[f"breakeven_rho{int(rho)}_ci_low"] = l
                row[f"breakeven_rho{int(rho)}_ci_high"] = h
        rows.append(row)
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dev_path = C.development_parquet()
    paths = {"wave2_confirmation": C.EXTERNAL_PARQUET, "development": dev_path}
    abl = C.RUN / "r2_02_same_capacity_ablation"
    out_rows = []
    for panel, path in paths.items():
        cases = pd.read_parquet(path).reset_index(drop=True)
        pred = policy_prediction(cases)
        truth = pd.to_numeric(cases["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
        a330 = pd.read_parquet(C.ALIGNED / f"case_level_admissions_{panel}.parquet")
        a341 = pd.read_parquet(abl / f"case_admissions_{panel}.parquet")
        for seed in SEEDS:
            b = a330[a330.fold_seed == seed].reset_index(drop=True)
            x = a341[a341.fold_seed == seed].reset_index(drop=True)
            assert len(b) == len(cases) == len(x)
            assert (b.network_id.to_numpy() == x.network_id.to_numpy()).all()
            assert (b.station_id.to_numpy() == x.station_id.to_numpy()).all()
            frame = pd.DataFrame(
                {f"admit_{arm}": b[f"admit_riskcap_{arm}"].to_numpy(dtype=bool) for arm in ARMS_330}
            )
            frame["admit_generic"] = x["admit_generic"].to_numpy(dtype=bool)
            frame["admit_generic+support"] = x["admit_generic+support"].to_numpy(dtype=bool)
            codes = pd.factorize(b["independence_group"].astype(str), sort=True)[0]
            arms = list(ARMS_330) + ["generic"]
            for hot_c in HOT:
                for row in analyse(frame, truth, pred, hot_c, arms, codes, panel, 17 + seed):
                    row["fold_seed"] = seed
                    row["population"] = "designed"
                    out_rows.append(row)

    # ---- real calendars ------------------------------------------------------
    replay = pd.read_parquet(C.REPLAY_CASES)
    for level in sorted(replay.level.unique()):
        for seed in SEEDS:
            block = replay[(replay.level == level) & (replay.seed == seed)].reset_index(drop=True)
            frame = pd.DataFrame({f"admit_{arm}": block[f"admit_{arm}"].to_numpy(dtype=bool) for arm in ARMS_330})
            truth = pd.to_numeric(block["truth_hottest30"], errors="coerce").to_numpy(dtype=float)
            pred = pd.to_numeric(block["policy_metric"], errors="coerce").to_numpy(dtype=float)
            codes = pd.factorize(block["network_id"].astype(str), sort=True)[0]
            for hot_c in HOT:
                for row in analyse(frame, truth, pred, hot_c, ARMS_330, codes, f"real_calendar:{level}", 31 + seed):
                    row["fold_seed"] = seed
                    row["population"] = "real_calendar"
                    out_rows.append(row)

    table = pd.DataFrame(out_rows)
    table.to_csv(OUT / "hot_year_selection_null.csv", index=False)
    write_summary(table)
    C.write_fingerprint(
        OUT,
        "scripts/343_wrr_hot_year_selection_null.py",
        {
            "admissions_330_external": C.ALIGNED / "case_level_admissions_wave2_confirmation.parquet",
            "admissions_330_development": C.ALIGNED / "case_level_admissions_development.parquet",
            "admissions_341_external": abl / "case_admissions_wave2_confirmation.parquet",
            "admissions_341_development": abl / "case_admissions_development.parquet",
            "replay_decisions": C.REPLAY_CASES,
        },
    )
    print((OUT / "SUMMARY.md").read_text())
    return 0


def write_summary(table: pd.DataFrame) -> None:
    lines = ["# R2-04 hot-year selection null and abstention cost", ""]
    lines.append(
        "`excess_hot_refusal` = retention(all records) - retention(true hot years); "
        "positive means hot years are refused more often than records in general."
    )
    lines.append("")
    for pop, hot in (("designed", 20.0), ("real_calendar", 20.0)):
        block = table[(table.population == pop) & (table.hot_c == hot) & (table.fold_seed == 101)]
        lines.append(f"## {pop}, hot threshold {hot:g} C, fold seed 101")
        lines.append("")
        show = block[
            [
                "panel", "arm", "retention", "retention_hot", "retention_cool", "refused_hot_share",
                "excess_hot_refusal", "excess_ci_low", "excess_ci_high", "wrong_judgement_rate",
                "abstention_rate", "breakeven_abstention_cost_rho1", "breakeven_abstention_cost_rho5",
            ]
        ]
        lines.append(show.round(4).to_string(index=False))
        lines.append("")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
