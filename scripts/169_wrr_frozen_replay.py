#!/usr/bin/env python3
"""Step 6/8: freeze-aligned station-year replay with inner-year benefit history.

The previous Step-6 run used P0 (published recoverer) predicted benefits to
decide whether to adopt a different recoverer. This script uses the frozen
duration switch, scores historical gaps only inside training years, and never
retunes tau on confirmation networks.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_data import (  # noqa: E402
    joint_complete_feature_rosters,
)
from stream_recoverability.experiments.development_recovery import year_split  # noqa: E402
from stream_recoverability.experiments.wrr_revision.benefit import (  # noqa: E402
    attach_component_predictors,
)
from stream_recoverability.experiments.wrr_revision.decision import adopt_mean_threshold  # noqa: E402
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame  # noqa: E402
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PLACEMENTS,
    GAP_GRID,
    RESULTS_ROOT,
)
from stream_recoverability.experiments.wrr_revision.recoverers import (  # noqa: E402
    fit_station_recoverers,
)
from stream_recoverability.experiments.wrr_revision.replay import (  # noqa: E402
    replay_case,
    seasonal_rule_adopt,
    select_mixed_duration_gaps,
    select_nonoverlapping_gaps,
)
from stream_recoverability.experiments.wrr_revision.score import (  # noqa: E402
    archived_placements,
    generated_placements,
    load_panel,
    score_gap,
)

FREEZE_PATH = RESULTS_ROOT / "DESIGN_FREEZE.json"
OUTPUT = RESULTS_ROOT / "step6_frozen_replay"
CONFIRM_OUTPUT = RESULTS_ROOT / "step8_frozen_replay"
FROZEN_NAMES = ("ridge_neighbor_boundary", "donor_only_ridge", "linear_interp", "doy_climatology")


def _freeze() -> dict:
    return json.loads(FREEZE_PATH.read_text())


def recoverer_for_length(length: int, freeze: dict) -> str:
    mapping = {int(k): str(v) for k, v in freeze["recoverer_by_duration"].items()}
    return mapping.get(int(length), freeze.get("simple_alternative", "donor_only_ridge"))


def inner_masks(index: pd.DatetimeIndex, train_mask: pd.Series, training_years: tuple[int, ...]):
    years = list(training_years)
    if len(years) >= 4:
        hist_years = set(years[-2:])
        fit_years = set(years[:-2])
    elif len(years) >= 2:
        hist_years = {years[-1]}
        fit_years = set(years[:-1])
    else:
        hist_years = set()
        fit_years = set(years)
    fit_mask = train_mask & pd.Series(index.year.isin(fit_years), index=index)
    hist_mask = pd.Series(index.year.isin(hist_years), index=index)
    return fit_mask, hist_mask, hist_years


def both_boundaries(series: pd.Series, start: int, length: int) -> bool:
    if start < 1 or start + length >= len(series):
        return False
    left = float(series.iloc[start - 1])
    right = float(series.iloc[start + length])
    return bool(np.isfinite(left) and np.isfinite(right))


def donors_observed(panel: pd.DataFrame, donors: tuple[str, ...], start: int, length: int) -> bool:
    if not donors:
        return False
    block = panel.loc[:, list(donors)].iloc[start : start + length]
    return bool(block.notna().to_numpy().all())


def _history_rows(
    network_id: str,
    station: str,
    daily: pd.DataFrame,
    donors: tuple[str, ...],
    features: pd.DataFrame,
    recoverers: dict,
    default_fill: np.ndarray,
    hist_mask: pd.Series,
) -> list[dict]:
    if not hist_mask.any():
        return []
    tasks = generated_placements(
        daily,
        target_station=station,
        donors=donors,
        evaluation_mask=hist_mask,
        gap_lengths=GAP_GRID,
        count=3,
    )
    rows = []
    for task in tasks:
        start = int(daily.index.get_indexer([pd.Timestamp(task["gap_start"])])[0])
        gap_length = int(task["gap_length"])
        for name in ("ridge_neighbor_boundary", "donor_only_ridge"):
            rec = recoverers.get(name)
            if rec is None:
                continue
            scored = score_gap(
                rec,
                features=features,
                target=daily[station],
                start=start,
                gap_length=gap_length,
                default_fill=default_fill,
            )
            if scored is None:
                continue
            rows.append(
                {
                    "network_id": network_id,
                    "station_id": station,
                    "gap_length": gap_length,
                    "placement": int(task["placement"]),
                    "gap_start": pd.Timestamp(task["gap_start"]),
                    "season": None,
                    "recoverer": name,
                    "mae_deg_c": scored["mae_deg_c"],
                    "climatology_mae_deg_c": scored["climatology_mae_deg_c"],
                }
            )
    if rows:
        frame = pd.DataFrame(rows)
        from stream_recoverability.experiments.recovery_roster import season_label

        frame["season"] = season_label(frame["gap_start"])
        return frame.to_dict("records")
    return rows


def _eval_gaps(
    network_id: str,
    station: str,
    daily: pd.DataFrame,
    donors: tuple[str, ...],
    eval_years: tuple[int, ...],
    panel_name: str,
) -> pd.DataFrame:
    if panel_name == "first":
        archived = archived_placements(network_id)
        station_archive = archived.loc[archived["station_id"].astype(str).eq(station)]
        if not station_archive.empty:
            return station_archive
    evaluation_mask = pd.Series(daily.index.year.isin(eval_years), index=daily.index)
    tasks = generated_placements(
        daily,
        target_station=station,
        donors=donors,
        evaluation_mask=evaluation_mask,
        gap_lengths=GAP_GRID,
        count=12,
    )
    if not tasks:
        tasks = generated_placements(
            daily,
            target_station=station,
            donors=(),
            evaluation_mask=evaluation_mask,
            gap_lengths=GAP_GRID,
            count=12,
        )
    if not tasks:
        return pd.DataFrame()
    return pd.DataFrame(tasks)


def _predict_for_recoverer(history: pd.DataFrame, gaps: pd.DataFrame, recoverer: str) -> pd.DataFrame:
    ev = gaps.copy()
    if history is None or history.empty or "recoverer" not in history.columns:
        ev["diff_prediction"] = np.nan
        ev["seasonal_empirical_supported"] = False
        return ev
    hist = history.loc[history["recoverer"].eq(recoverer)].copy()
    if "network_id" not in ev.columns:
        ev["network_id"] = hist["network_id"].iloc[0] if len(hist) else "na"
    if hist.empty:
        ev["diff_prediction"] = np.nan
        ev["seasonal_empirical_supported"] = False
        return ev
    attached = attach_component_predictors(hist, ev)
    return attached


def _replay_station(
    network_id: str,
    panel_name: str,
    transfer_history: pd.DataFrame,
    freeze: dict,
) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, training_years, eval_years = year_split(daily.index)
    fit_mask, hist_mask, _ = inner_masks(daily.index, train_mask, training_years)
    tau = 0.0
    rows = []
    for station in daily.columns:
      try:
        donors, _, _ = joint_complete_feature_rosters(
            daily.loc[train_mask],
            target=station,
            donor_candidates=tuple(c for c in daily.columns if c != station),
            meteorology_candidates=(),
            hydraulics_candidates=(),
        )
        donors = tuple(
            d
            for d in donors
            if int((~train_mask & daily[d].notna()).sum()) >= 60
        )
        features = base_feature_frame(daily, donors=donors)
        try:
            hist_recoverers = fit_station_recoverers(
                daily,
                target_station=station,
                donors=donors,
                train_mask=fit_mask if int((fit_mask & daily[station].notna()).sum()) >= 40 else train_mask,
                features=features,
                include_external=False,
                include_names=FROZEN_NAMES,
            )
        except ValueError:
            try:
                hist_recoverers = fit_station_recoverers(
                    daily,
                    target_station=station,
                    donors=donors,
                    train_mask=train_mask,
                    features=features,
                    include_external=False,
                    include_names=FROZEN_NAMES,
                )
            except ValueError:
                continue
        default_fill = np.asarray(hist_recoverers["doy_climatology"].extra["values"], dtype=float)
        local_hist = _history_rows(
            network_id,
            station,
            daily,
            donors,
            features,
            hist_recoverers,
            default_fill,
            hist_mask,
        )
        history = pd.DataFrame(local_hist)
        if (
            panel_name == "confirmation"
            and transfer_history is not None
            and not transfer_history.empty
        ):
            history = (
                pd.concat([history, transfer_history], ignore_index=True)
                if len(history)
                else transfer_history
            )
        try:
            final_recoverers = fit_station_recoverers(
                daily,
                target_station=station,
                donors=donors,
                train_mask=train_mask,
                features=features,
                include_external=False,
                include_names=FROZEN_NAMES,
            )
        except ValueError:
            continue
        default_fill = np.asarray(final_recoverers["doy_climatology"].extra["values"], dtype=float)
        eval_src = _eval_gaps(network_id, station, daily, donors, eval_years, panel_name)
        if eval_src.empty:
            continue
        eval_src = eval_src.copy()
        eval_src["network_id"] = network_id
        eval_src["station_id"] = station
        eval_src["gap_start"] = pd.to_datetime(eval_src["gap_start"])
        for year in eval_years:
            year_gaps = eval_src.loc[eval_src["gap_start"].dt.year == int(year)]
            if year_gaps.empty:
                continue
            year_gaps = year_gaps.copy()
            year_gaps["year"] = int(year)
            patterns: list[tuple[str, int, pd.DataFrame]] = []
            for gap_length, group in year_gaps.groupby("gap_length"):
                selected = select_nonoverlapping_gaps(group, daily.index)
                if not selected.empty:
                    patterns.append(("duration", int(gap_length), selected))
            mixed_src = year_gaps.loc[year_gaps["gap_length"].isin((30, 90, 180))]
            mixed = select_mixed_duration_gaps(
                mixed_src if not mixed_src.empty else year_gaps,
                daily.index,
            )
            if not mixed.empty:
                patterns.append(("mixed", 0, mixed))
            for pattern, stratum, selected in patterns:
                names = [recoverer_for_length(int(length), freeze) for length in selected["gap_length"]]
                # Gates: donors for donor recoverers; both boundaries always for this offline protocol.
                starts = [
                    int(daily.index.get_indexer([pd.Timestamp(s)])[0]) for s in selected["gap_start"]
                ]
                lengths = selected["gap_length"].astype(int).to_numpy()
                gate = []
                for start, length, name in zip(starts, lengths, names):
                    ok_b = both_boundaries(daily[station], start, int(length))
                    needs_donors = name == "donor_only_ridge"
                    ok_d = donors_observed(daily, donors, start, int(length)) if needs_donors else True
                    if needs_donors and not donors:
                        ok_d = False
                    gate.append(bool(ok_b and ok_d))
                gate = pd.Series(gate, index=selected.index)
                pred = np.full(len(selected), np.nan)
                supported = np.zeros(len(selected), dtype=bool)
                for i, name in enumerate(names):
                    attached = _predict_for_recoverer(history, selected.iloc[[i]], name)
                    pred[i] = float(attached["diff_prediction"].iloc[0]) if len(attached) else np.nan
                    supported[i] = bool(attached["seasonal_empirical_supported"].iloc[0]) if len(attached) else False
                pred_s = pd.Series(pred, index=selected.index)
                supp_s = pd.Series(supported, index=selected.index)
                adopt_rank = adopt_mean_threshold(pred_s, tau=tau, supported=supp_s) & gate
                adopt_switch = gate.copy()
                adopt_donor = pd.Series(
                    [
                        both_boundaries(daily[station], start, int(length))
                        and donors_observed(daily, donors, start, int(length))
                        for start, length in zip(starts, lengths)
                    ],
                    index=selected.index,
                )
                seasonal = seasonal_rule_adopt(selected, max_length=30, seasons=("DJF", "MAM", "JJA", "SON")) & gate
                donor_names = ["donor_only_ridge"] * len(selected)
                strategies = {
                    "frozen_rule": (adopt_rank, names),
                    "always_switch_gated": (adopt_switch, names),
                    "always_donor_gated": (adopt_donor, donor_names),
                    "seasonal_le30": (seasonal, names),
                    "all_default": (pd.Series(False, index=selected.index), names),
                }
                record = {
                    "network_id": network_id,
                    "station_id": station,
                    "year": int(year),
                    "pattern": pattern,
                    "stratum_gap_length": int(stratum),
                    "n_gaps": int(len(selected)),
                    "panel": panel_name,
                    "n_donors": int(len(donors)),
                }
                for label, (adopt, rec_names) in strategies.items():
                    out = replay_case(
                        daily[station],
                        default_fill=default_fill,
                        recoverers=final_recoverers,
                        features=features,
                        gaps=selected,
                        predicted_benefit=pred_s,
                        adopt=adopt,
                        chosen_recoverer=rec_names,
                    )
                    record[f"{label}_hottest_30"] = out["hottest_30_benefit"]
                    record[f"{label}_exceed_20"] = out["exceed_days_20_benefit"]
                    record[f"{label}_mae"] = out["mae_benefit"]
                    record[f"{label}_adopt_rate"] = out["adopt_rate"]
                    record[f"{label}_zero_action"] = out["unused_default_is_zero"]
                rows.append(record)
      except Exception as exc:
            print(f"skip {network_id}/{station}: {exc}", flush=True)
            continue
    return pd.DataFrame(rows)


def _worker(payload: tuple[str, str, str]) -> pd.DataFrame:
    network_id, panel_name, transfer_path = payload
    freeze = _freeze()
    transfer = pd.read_csv(transfer_path) if transfer_path else pd.DataFrame()
    return _replay_station(network_id, panel_name, transfer, freeze)


def _write_outputs(out: pd.DataFrame, directory: Path, panel_name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    out.to_csv(directory / "station_year_replay.csv", index=False)
    network = out.groupby("network_id", as_index=False).mean(numeric_only=True)
    network.to_csv(directory / "network_replay.csv", index=False)
    pattern = out.groupby(["pattern", "stratum_gap_length"], as_index=False).agg(
        n_cases=("year", "size"),
        n_networks=("network_id", "nunique"),
        **{
            col: (col, "mean")
            for col in out.columns
            if col.endswith("_hottest_30") or col.endswith("_adopt_rate")
        },
    )
    pattern.to_csv(directory / "pattern_replay.csv", index=False)
    summary = {
        "panel": panel_name,
        "n_cases": int(len(out)),
        "n_networks": int(out["network_id"].nunique()),
        "n_stations": int(out["station_id"].astype(str).nunique()),
    }
    for col in (
        "frozen_rule_hottest_30",
        "always_switch_gated_hottest_30",
        "always_donor_gated_hottest_30",
        "seasonal_le30_hottest_30",
        "all_default_hottest_30",
        "frozen_rule_adopt_rate",
        "always_switch_gated_adopt_rate",
        "always_donor_gated_adopt_rate",
    ):
        if col in out.columns:
            summary[f"mean_{col}"] = float(out[col].mean())
    if "frozen_rule_hottest_30" in out.columns:
        summary["beats_all_default"] = bool(float(out["frozen_rule_hottest_30"].mean()) > 0.0)
        summary["beats_seasonal"] = bool(
            float(out["frozen_rule_hottest_30"].mean()) > float(out["seasonal_le30_hottest_30"].mean())
        )
        summary["beats_always_donor"] = bool(
            float(out["frozen_rule_hottest_30"].mean())
            > float(out["always_donor_gated_hottest_30"].mean())
        )
        summary["beats_always_switch"] = bool(
            float(out["frozen_rule_hottest_30"].mean())
            > float(out["always_switch_gated_hottest_30"].mean())
        )
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


def _transfer_table() -> Path:
    src = RESULTS_ROOT / "step2_fair_recovery" / "placement_scores.csv"
    dest = RESULTS_ROOT / "step6_frozen_replay" / "transfer_history.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        pd.DataFrame().to_csv(dest, index=False)
        return dest
    frame = pd.read_csv(src, usecols=lambda c: c in {
        "network_id",
        "station_id",
        "gap_length",
        "placement",
        "gap_start",
        "season",
        "recoverer",
        "mae_deg_c",
        "climatology_mae_deg_c",
    })
    frame = frame.loc[frame["recoverer"].isin(("ridge_neighbor_boundary", "donor_only_ridge"))]
    frame.to_csv(dest, index=False)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", choices=("first", "confirmation"), default="first")
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    freeze = _freeze()
    transfer = _transfer_table() if args.panel == "confirmation" else ""
    if args.panel == "first":
        ids = sorted(
            pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str).unique()
        )
        panel_name = "first"
        out_dir = OUTPUT
    else:
        inv = pd.read_csv(RESULTS_ROOT / "step8_confirmation" / "network_inventory.csv")
        ids = sorted(
            inv.loc[
                inv["role"].eq("held_out_confirmation_candidate") & inv["eligible_years"].eq(1),
                "network_id",
            ]
            .astype(str)
            .tolist()
        )
        panel_name = "confirmation"
        out_dir = CONFIRM_OUTPUT
    if args.max_networks is not None:
        ids = ids[: args.max_networks]
    payloads = [(n, panel_name, str(transfer) if transfer else "") for n in ids]
    frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_worker, p): p[0] for p in payloads}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frame = fut.result()
                if frame is not None and not frame.empty:
                    frames.append(frame)
                print(f"frozen-replay {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(failures).to_csv(out_dir / "failures.csv", index=False)
    if not frames:
        raise SystemExit("no frozen replay rows")
    out = pd.concat(frames, ignore_index=True)
    _write_outputs(out, out_dir, panel_name)
    _ = freeze


if __name__ == "__main__":
    main()
