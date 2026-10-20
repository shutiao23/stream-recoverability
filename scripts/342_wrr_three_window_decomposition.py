#!/usr/bin/env python3
"""R2-03 (review op. 3, 2026-10-20b) -- three peak windows, one exact identity.

The mechanism section grouped cases by whether the *reconstructed* peak window
landed away from the *true* one and read the larger error as the effect of
misplacement.  Three different windows are in play:

* ``W*``  the true hottest 30-day window of the complete reference year;
* ``W_c`` the climatological window, estimated from the station's other years --
  the only window a deployable rule can see;
* ``W_r`` the hottest window of the reconstructed (completed) year.

Exact identity.  Let ``e_t = completed_t - truth_t`` (zero on observed days),
``e_W`` the mean of ``e`` over a 30-day window ``W`` and ``D_W = H30(truth) -
mean_W(truth) >= 0``.  Then

    H30(completed) - H30(truth) = max_W ( e_W - D_W )  =  e_{W*}  +  F,   F >= 0,

because ``D_{W*} = 0``.  ``e_{W*}`` is the **hiding channel**: error the true
window inherits from imputed days inside it (it is exactly zero when none of
``W*`` is hidden).  ``F`` is the **false-peak channel**: how far a competing or
shifted window overshoots the true window once its own residuals are added.

The script (1) verifies the identity on every case, (2) reports the two channels
by true hidden-share class, (3) re-estimates the "misaligned minus aligned"
contrast *within* hidden-share classes, so a common cause cannot masquerade as a
mechanism, (4) separates climatological-window error from reconstructed-window
error, and (5) runs three interventions on the reconstruction residuals inside
the gap (permute them, remove their mean, keep only their mean) while holding gap
geometry, truth and reconstructor fixed.  The interventions are controlled
numerical experiments on recorded residuals, not natural-process causal
identification.

Outputs: ``results/wrr_submission_ready/major_revision_20261020b/r2_03_three_windows/``.
"""

from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The air-forcing table must be fixed before the pipeline modules are imported
# (paths.py reads it at import time); this is the table scripts/317 used.
os.environ["STREAM_AIR_FORCING"] = os.path.join(ROOT_PATH, "data", "interim", "v18_air_forcing.parquet")

import argparse  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from joblib import Parallel, delayed  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrr_r2_common as C  # noqa: E402

from stream_recoverability.experiments.v17_fitness.cases import station_geometry_pool  # noqa: E402
from stream_recoverability.experiments.v17_fitness.estimators import (  # noqa: E402
    StationModels,
    hottest_window_mean,
    linear_interp_fill,
    usable_donors,
)
from stream_recoverability.experiments.v17_fitness.outages import (  # noqa: E402
    climatological_peak_window,
    design_for_year,
    peak_overlap_fraction,
)
from stream_recoverability.experiments.v17_fitness.panel import (  # noqa: E402
    air_series_for,
    load_network_panel,
)
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    REALIZATIONS_PER_STATION_YEAR,
    stable_seed,
)

OUT = C.RUN / "r2_03_three_windows"
M317 = C.load_script("wrr317", C.ROOT / "scripts" / "317_wrr_p1_mechanism_boundary.py")

WINDOW = 30
RECONSTRUCTORS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")
LENGTHS = (30, 60, 90)
N_PERM = 25
DRAWS = 2000
HARMLESS_C = 0.10
FALSE_PEAK_C = 0.10


def roll_mean(values: np.ndarray) -> np.ndarray:
    """Right-aligned 30-day means; NaN where undefined (index = window end)."""

    x = np.asarray(values, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) < WINDOW or not np.isfinite(x).all():
        return out
    csum = np.cumsum(np.concatenate([[0.0], x]))
    out[WINDOW - 1 :] = (csum[WINDOW:] - csum[:-WINDOW]) / WINDOW
    return out


def h30(values: np.ndarray) -> float:
    r = roll_mean(values)
    return float(np.nanmax(r)) if np.isfinite(r).any() else float("nan")


def build_station(job: dict) -> pd.DataFrame:
    network_id, station_id = str(job["network_id"]), str(job["station_id"])
    protocol = str(job.get("fit_protocol", "leave_one_year_out"))
    try:
        daily = load_network_panel(network_id, str(job["source_root"])).copy()
    except (FileNotFoundError, ValueError, KeyError):
        return pd.DataFrame()
    daily.columns = [str(c) for c in daily.columns]
    if station_id not in daily.columns:
        return pd.DataFrame()
    target = pd.to_numeric(daily[station_id], errors="coerce")
    donors = daily.drop(columns=[station_id])
    air = air_series_for(network_id, station_id, daily.index)
    pool = station_geometry_pool(daily)
    years = tuple(int(y) for y in job["complete_years"])
    if len(years) < 2:
        return pd.DataFrame()
    rows: list[dict] = []
    for year in years:
        ymask = target.index.year == int(year)
        yindex = daily.index[ymask]
        truth = target.loc[ymask].to_numpy(dtype=float)
        if not np.isfinite(truth).all() or len(truth) < 360:
            continue
        truth_metric = hottest_window_mean(truth)
        if not np.isfinite(truth_metric):
            continue
        train_mask = pd.Series(~ymask, index=daily.index)
        peak_source = target.loc[target.index.year != int(year)]
        models = StationModels(target=target, donors=donors, air=air, train_mask=train_mask)
        peak_doys = climatological_peak_window(peak_source, exclude_year=None)
        if len(target.loc[train_mask].dropna()) < 365:
            continue
        rng = np.random.default_rng(stable_seed(network_id, station_id, int(year), protocol))
        realizations = design_for_year(
            yindex,
            peak_doys,
            pool,
            rng=rng,
            n_empirical=max(1, REALIZATIONS_PER_STATION_YEAR // 3),
            cross_overlap=True,
        )
        n_days = len(truth)
        rolled_truth = roll_mean(truth)
        t_end = int(np.nanargmax(rolled_truth))
        t_slice = slice(t_end - WINDOW + 1, t_end + 1)
        delta = truth_metric - rolled_truth  # D_W >= 0, NaN before the first full window
        # climatological window start/end index in this year (observable at decision time)
        c_start = int(min(max(int(peak_doys[0]) - 1, 0), n_days - WINDOW))
        c_end = c_start + WINDOW - 1
        # strongest competing disjoint truth window
        ends = np.flatnonzero(np.isfinite(rolled_truth))
        disjoint = ends[(ends <= t_end - WINDOW) | (ends >= t_end + WINDOW)]
        comp_gap = float(truth_metric - rolled_truth[disjoint].max()) if len(disjoint) else float("nan")

        for real in realizations:
            if real.arm != "stratified" or int(real.longest_run) not in LENGTHS:
                continue
            mask = real.mask(n_days)
            if not mask.any() or mask.all():
                continue
            observed = truth.copy()
            observed[mask] = np.nan
            visible = usable_donors(donors, yindex, mask)
            fits = {
                "doy_climatology": models.doy_climatology(yindex),
                "smooth_climatology": models.smooth_climatology(yindex),
                "linear_interp": linear_interp_fill(observed),
            }
            donor_fit = models.donor_ridge(visible) if visible else None
            fits["donor_ridge"] = (
                models.donor_predict(donor_fit, yindex) if donor_fit is not None else np.full(n_days, np.nan)
            )
            fits["air_ridge"] = models.air_predict(yindex) if air is not None else np.full(n_days, np.nan)

            h_true = float(mask[t_slice].mean())
            base = {
                "network_id": network_id,
                "station_id": station_id,
                "year": int(year),
                "realization_id": real.realization_id,
                "longest_run": int(real.longest_run),
                "design_class": real.overlap_class,
                "peak_overlap": float(peak_overlap_fraction(yindex, mask, peak_doys)),
                "true_hidden_fraction": h_true,
                "true_window_end": t_end,
                "clim_window_end": c_end,
                "clim_minus_true_days": float(c_end - t_end),
                "abs_clim_minus_true_days": float(abs(c_end - t_end)),
                "competing_peak_gap_C": comp_gap,
                "truth_hottest30": float(truth_metric),
            }
            for name in RECONSTRUCTORS:
                fill = np.asarray(fits[name], dtype=float)
                completed = observed.copy()
                completed[mask] = fill[mask]
                case = dict(base, reconstructor=name)
                if not np.isfinite(completed).all():
                    case["status"] = "not_finite"
                    rows.append(case)
                    continue
                resid = completed - truth  # zero on observed days by construction
                rolled_c = roll_mean(completed)
                r_end = int(np.nanargmax(rolled_c))
                error = float(rolled_c[r_end] - truth_metric)
                e_w = roll_mean(resid)
                ident = float(np.nanmax(e_w - delta))
                hide = float(e_w[t_end])
                false_peak = error - hide
                gap_resid = resid[mask]
                inside_mean = float(gap_resid.mean())
                case.update(
                    {
                        "status": "ok",
                        "error": error,
                        "abs_error": abs(error),
                        "identity_residual": float(error - ident),
                        "hide_channel": hide,
                        "false_peak_channel": false_peak,
                        "recon_window_end": r_end,
                        "recon_minus_true_days": float(r_end - t_end),
                        "abs_recon_minus_true_days": float(abs(r_end - t_end)),
                        "recon_minus_clim_days": float(r_end - c_end),
                        "abs_recon_minus_clim_days": float(abs(r_end - c_end)),
                        "window_aligned": bool(r_end == t_end),
                        "window_disjoint_from_truth": bool(abs(r_end - t_end) >= WINDOW),
                        "gap_resid_mean": inside_mean,
                        "gap_resid_sd": float(gap_resid.std()),
                    }
                )
                # ---- interventions on the gap residuals --------------------
                prng = np.random.default_rng(
                    stable_seed("r2-intervene", network_id, station_id, int(year), real.realization_id, name)
                )
                gap_idx = np.flatnonzero(mask)
                perm_err = np.empty(N_PERM)
                for k in range(N_PERM):
                    alt = truth.copy()
                    alt[gap_idx] = truth[gap_idx] + prng.permutation(gap_resid)
                    perm_err[k] = h30(alt) - truth_metric
                alt = truth.copy()
                alt[gap_idx] = truth[gap_idx] + (gap_resid - inside_mean)
                debias_err = h30(alt) - truth_metric
                alt = truth.copy()
                alt[gap_idx] = truth[gap_idx] + inside_mean
                bias_err = h30(alt) - truth_metric
                case.update(
                    {
                        "abs_error_permuted": float(np.mean(np.abs(perm_err))),
                        "error_permuted": float(np.mean(perm_err)),
                        "abs_error_debiased": abs(float(debias_err)),
                        "error_debiased": float(debias_err),
                        "abs_error_bias_only": abs(float(bias_err)),
                        "error_bias_only": float(bias_err),
                    }
                )
                rows.append(case)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# network-clustered summaries
# ---------------------------------------------------------------------------
def cmean(block: pd.DataFrame, col: str, seed: int) -> dict:
    block = block[["network_id", col]].dropna()
    if block.empty:
        return {"point": np.nan, "lo": np.nan, "hi": np.nan, "n": 0, "n_networks": 0}
    parts = [(g[col].sum(), len(g)) for _, g in block.groupby("network_id")]

    def stat(chosen):
        s = sum(p[0] for p in chosen)
        n = sum(p[1] for p in chosen)
        return s / n if n else np.nan

    point, lo, hi = C.cluster_bootstrap(parts, stat, draws=DRAWS, seed=seed)
    return {"point": point, "lo": lo, "hi": hi, "n": int(len(block)), "n_networks": len(parts)}


def cdiff(block: pd.DataFrame, col: str, flag: str, seed: int) -> dict:
    """flag==True minus flag==False; network-clustered, networks lacking either arm drop out."""

    block = block[["network_id", col, flag]].dropna()
    parts = []
    for _, g in block.groupby("network_id"):
        a, b = g.loc[g[flag].astype(bool), col], g.loc[~g[flag].astype(bool), col]
        if len(a) and len(b):
            parts.append((a.sum(), len(a), b.sum(), len(b)))
    if len(parts) < 2:
        return {"point": np.nan, "lo": np.nan, "hi": np.nan, "n_true": 0, "n_false": 0, "n_networks": len(parts)}

    def stat(chosen):
        sa, na = sum(p[0] for p in chosen), sum(p[1] for p in chosen)
        sb, nb = sum(p[2] for p in chosen), sum(p[3] for p in chosen)
        return sa / na - sb / nb if na and nb else np.nan

    point, lo, hi = C.cluster_bootstrap(parts, stat, draws=DRAWS, seed=seed)
    return {
        "point": point, "lo": lo, "hi": hi,
        "n_true": int(block[flag].astype(bool).sum()),
        "n_false": int((~block[flag].astype(bool)).sum()),
        "n_networks": len(parts),
    }


def strata_weighted_diff(block: pd.DataFrame, seed: int, min_cell: int = 5) -> dict:
    """Misaligned minus aligned |error|, averaged over climatological-class x
    true-class strata with the strata's own case counts as weights.

    A stratum enters only when both arms of the contrast have at least
    ``min_cell`` cases in the whole sample; networks are resampled as units and
    the strata weights are recomputed inside every draw.
    """

    keys = list(block.groupby(["clim_class", "true_class"]).groups)
    parts = []
    for _, g in block.groupby("network_id"):
        cells = {}
        for key in keys:
            sel = g[(g.clim_class == key[0]) & (g.true_class == key[1])]
            m, a = sel[sel.misaligned], sel[~sel.misaligned]
            cells[key] = (m.abs_error.sum(), len(m), a.abs_error.sum(), len(a))
        parts.append(cells)
    total = {k: [sum(p[k][i] for p in parts) for i in range(4)] for k in keys}
    usable = [k for k in keys if total[k][1] >= min_cell and total[k][3] >= min_cell]

    def stat(chosen):
        num, den = 0.0, 0.0
        for k in usable:
            sm, nm, sa, na = (sum(p[k][i] for p in chosen) for i in range(4))
            if nm and na:
                w = nm + na
                num += w * (sm / nm - sa / na)
                den += w
        return num / den if den else np.nan

    point, lo, hi = C.cluster_bootstrap(parts, stat, draws=DRAWS, seed=seed)
    return {"point": point, "lo": lo, "hi": hi, "n_networks": len(parts)}


def true_class(h: pd.Series) -> pd.Series:
    return pd.Series(np.select([h <= 0.0, h >= 0.999], ["none", "all"], default="partial"), index=h.index)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    jobs = M317.crossed_panel_jobs()
    print(f"[342] {len(jobs)} stations", flush=True)
    frames = Parallel(n_jobs=min(int(args.workers), len(jobs)), verbose=2)(
        delayed(build_station)(job) for job in jobs
    )
    cases = pd.concat([f for f in frames if len(f)], ignore_index=True)
    ok = cases[cases.status.eq("ok")].copy()
    ok["true_class"] = true_class(ok["true_hidden_fraction"])
    ok["clim_class"] = ok["design_class"]
    ok["window_aligned"] = ok["window_aligned"].astype(bool)
    ok["window_disjoint_from_truth"] = ok["window_disjoint_from_truth"].astype(bool)
    ok["misaligned"] = ~ok["window_aligned"]
    ok["false_peak_case"] = ok["false_peak_channel"] > FALSE_PEAK_C
    ok["harmless_switch"] = ok["misaligned"] & (ok["false_peak_channel"].abs() <= FALSE_PEAK_C)
    cases.to_parquet(OUT / "cases_three_windows.parquet", index=False)
    print(f"[342] {len(cases)} cases ({len(ok)} finite) in {time.time() - started:.0f}s", flush=True)

    # ---- (1) identity -----------------------------------------------------
    ident = {
        "n_cases_checked": int(len(ok)),
        "max_abs_identity_residual_C": float(ok["identity_residual"].abs().max()),
        "min_false_peak_channel_C": float(ok["false_peak_channel"].min()),
        "share_false_peak_channel_negative_beyond_1e-9": float((ok["false_peak_channel"] < -1e-9).mean()),
        "share_hide_channel_zero_when_true_window_visible": float(
            (ok.loc[ok.true_hidden_fraction <= 0, "hide_channel"].abs() < 1e-9).mean()
        ),
    }
    pd.Series(ident).to_csv(OUT / "identity_check.csv", header=["value"])

    # ---- (2) channels by true hidden class ---------------------------------
    rows = []
    seed = 700
    for recon, rblock in ok.groupby("reconstructor"):
        for klass in ("none", "partial", "all", "pooled"):
            block = rblock if klass == "pooled" else rblock[rblock.true_class == klass]
            seed += 1
            ae = cmean(block, "abs_error", seed)
            seed += 1
            hc = cmean(block, "hide_channel", seed)
            seed += 1
            fp = cmean(block, "false_peak_channel", seed)
            seed += 1
            fpc = cmean(block.assign(v=block.false_peak_case.astype(float)), "v", seed)
            rows.append(
                {
                    "reconstructor": recon,
                    "true_hidden_class": klass,
                    "n_cases": ae["n"],
                    "mean_abs_error_C": ae["point"], "mean_abs_error_lo": ae["lo"], "mean_abs_error_hi": ae["hi"],
                    "mean_hide_channel_C": hc["point"], "hide_lo": hc["lo"], "hide_hi": hc["hi"],
                    "mean_false_peak_channel_C": fp["point"], "false_lo": fp["lo"], "false_hi": fp["hi"],
                    "share_false_peak_cases": fpc["point"], "share_lo": fpc["lo"], "share_hi": fpc["hi"],
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "channels_by_hidden_class.csv", index=False)

    # ---- (3) misaligned minus aligned, raw and within hidden-share class ----
    rows = []
    for recon, rblock in ok.groupby("reconstructor"):
        for klass in ("pooled", "none", "partial", "all"):
            block = rblock if klass == "pooled" else rblock[rblock.true_class == klass]
            seed += 1
            d = cdiff(block, "abs_error", "misaligned", seed)
            rows.append(
                {
                    "reconstructor": recon,
                    "stratum": klass,
                    "contrast": "misaligned_minus_aligned_abs_error",
                    "point_C": d["point"], "lo_C": d["lo"], "hi_C": d["hi"],
                    "n_misaligned": d["n_true"], "n_aligned": d["n_false"], "n_networks": d["n_networks"],
                    "share_misaligned": float(block.misaligned.mean()) if len(block) else np.nan,
                }
            )
        # design-matched: same climatological class AND same true class
        seed += 1
        sw = strata_weighted_diff(rblock, seed)
        rows.append(
            {
                "reconstructor": recon,
                "stratum": "clim_class_x_true_class_weighted",
                "contrast": "misaligned_minus_aligned_abs_error",
                "point_C": sw["point"], "lo_C": sw["lo"], "hi_C": sw["hi"],
                "n_misaligned": int(rblock.misaligned.sum()),
                "n_aligned": int((~rblock.misaligned).sum()),
                "n_networks": sw["n_networks"],
                "share_misaligned": float(rblock.misaligned.mean()),
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "misalignment_within_strata.csv", index=False)

    # ---- (4) three window distances ----------------------------------------
    rows = []
    for recon, rblock in ok.groupby("reconstructor"):
        for label, col in (
            ("climatological_vs_true", "abs_clim_minus_true_days"),
            ("reconstructed_vs_true", "abs_recon_minus_true_days"),
            ("reconstructed_vs_climatological", "abs_recon_minus_clim_days"),
        ):
            v = rblock[col].dropna()
            rows.append(
                {
                    "reconstructor": recon,
                    "pair": label,
                    "median_days": float(v.median()),
                    "p90_days": float(v.quantile(0.9)),
                    "share_equal": float((v == 0).mean()),
                    "share_ge_7_days": float((v >= 7).mean()),
                    "share_ge_30_days": float((v >= 30).mean()),
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "window_distances.csv", index=False)

    # climatological window error: observable class vs true class
    rows = []
    for (cc, tc), g in ok[ok.reconstructor.eq("doy_climatology")].groupby(["clim_class", "true_class"]):
        rows.append(
            {
                "climatological_class": cc, "true_class": tc, "n_cases": len(g),
                "mean_abs_error_C": float(g.abs_error.mean()),
                "median_abs_clim_minus_true_days": float(g.abs_clim_minus_true_days.median()),
            }
        )
    tab = pd.DataFrame(rows)
    tab["share_of_climatological_class"] = tab.n_cases / tab.groupby("climatological_class").n_cases.transform("sum")
    tab.to_csv(OUT / "climatological_vs_true_class.csv", index=False)

    # error by climatological-window misplacement, within design class "none"
    rows = []
    bins = [-0.1, 0.5, 7.5, 14.5, 29.5, 1000]
    labels = ["0", "1-7", "8-14", "15-29", ">=30"]
    for recon, rblock in ok.groupby("reconstructor"):
        rblock = rblock.assign(d_bin=pd.cut(rblock.abs_clim_minus_true_days, bins, labels=labels))
        for klass in ("none", "partial", "full"):
            for lab in labels:
                g = rblock[(rblock.clim_class == klass) & (rblock.d_bin == lab)]
                if len(g) < 10:
                    continue
                rows.append(
                    {
                        "reconstructor": recon, "clim_class": klass, "clim_true_distance_bin": lab, "n_cases": len(g),
                        "mean_abs_error_C": float(g.abs_error.mean()),
                        "mean_true_hidden_fraction": float(g.true_hidden_fraction.mean()),
                    }
                )
    pd.DataFrame(rows).to_csv(OUT / "error_by_climatological_misplacement.csv", index=False)

    # ---- (5) interventions on the residuals --------------------------------
    rows = []
    for recon, rblock in ok.groupby("reconstructor"):
        for klass in ("pooled", "none", "partial", "all"):
            block = rblock if klass == "pooled" else rblock[rblock.true_class == klass]
            seed += 1
            rec = {"reconstructor": recon, "true_hidden_class": klass, "n_cases": len(block)}
            for col, label in (
                ("abs_error", "recorded"),
                ("abs_error_permuted", "permuted_within_gap"),
                ("abs_error_debiased", "mean_removed"),
                ("abs_error_bias_only", "mean_only"),
            ):
                r = cmean(block, col, seed)
                rec[f"{label}_C"] = r["point"]
                rec[f"{label}_lo"] = r["lo"]
                rec[f"{label}_hi"] = r["hi"]
            for col, label in (
                ("abs_error_permuted", "permuted_minus_recorded"),
                ("abs_error_debiased", "mean_removed_minus_recorded"),
                ("abs_error_bias_only", "mean_only_minus_recorded"),
            ):
                diff = block.assign(d=block[col] - block["abs_error"])
                seed += 1
                r = cmean(diff, "d", seed)
                rec[f"{label}_C"] = r["point"]
                rec[f"{label}_lo"] = r["lo"]
                rec[f"{label}_hi"] = r["hi"]
            rows.append(rec)
    pd.DataFrame(rows).to_csv(OUT / "residual_interventions.csv", index=False)

    # ---- (6) harmless switches ---------------------------------------------
    rows = []
    for recon, rblock in ok.groupby("reconstructor"):
        mis = rblock[rblock.misaligned]
        for label, sel in (
            ("overlapping shift (<30 d)", mis[mis.abs_recon_minus_true_days < WINDOW]),
            ("disjoint window (>=30 d)", mis[mis.abs_recon_minus_true_days >= WINDOW]),
            ("all misaligned", mis),
        ):
            rows.append(
                {
                    "reconstructor": recon, "kind": label, "n_cases": len(sel),
                    "share_of_all_cases": len(sel) / len(rblock),
                    "median_abs_error_C": float(sel.abs_error.median()) if len(sel) else np.nan,
                    "share_abs_error_le_0.1C": float((sel.abs_error <= 0.1).mean()) if len(sel) else np.nan,
                    "share_abs_error_le_0.5C": float((sel.abs_error <= 0.5).mean()) if len(sel) else np.nan,
                    "mean_false_peak_channel_C": float(sel.false_peak_channel.mean()) if len(sel) else np.nan,
                }
            )
    pd.DataFrame(rows).to_csv(OUT / "window_switches.csv", index=False)

    write_summary(ident)
    C.write_fingerprint(
        OUT,
        "scripts/342_wrr_three_window_decomposition.py",
        {"crossed_panel_cases": C.CROSSED_PARQUET},
        extra={
            "n_permutations": N_PERM,
            "elapsed_seconds": round(time.time() - started, 1),
            "note": "daily series regenerated from the same seeds as scripts/317 (stratified arm, lengths 30/60/90)",
        },
    )
    print(f"[342] done in {time.time() - started:.0f}s -> {OUT}", flush=True)
    return 0


def write_summary(ident: dict) -> None:
    lines = ["# R2-03 three windows and the exact identity", ""]
    lines += ["## Identity check", "", pd.Series(ident).to_string(), ""]
    for name, title in (
        ("channels_by_hidden_class.csv", "Hiding channel and false-peak channel by true hidden-share class"),
        ("misalignment_within_strata.csv", "Misaligned minus aligned, pooled and within hidden-share classes"),
        ("window_distances.csv", "Distances between the three windows (days)"),
        ("climatological_vs_true_class.csv", "Climatological design class vs true hidden-share class (day-of-year climatology)"),
        ("residual_interventions.csv", "Interventions on the gap residuals"),
        ("window_switches.csv", "What a window switch costs"),
    ):
        table = pd.read_csv(OUT / name)
        lines += [f"## {title}", "", table.round(3).to_string(index=False), ""]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
