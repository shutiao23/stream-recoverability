#!/usr/bin/env python3
"""Steps 5–6: complete-year hottest-30 B_q policies and ablations.

Development uses design_development river complete years only. Tau is chosen
on hist years. Eval years are the internal test. candidate_unseen is Step 10.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    STEP5_THERMAL_DECISION,
    STEP6_ABLATIONS,
)
from stream_recoverability.experiments.wrr_revision.thermal_decision import (  # noqa: E402
    attach_calibrated_policies,
    compare_eval_policies,
    load_trusted_roster,
    score_network_complete_years,
)

POWER = ROOT / "results/wrr_revision/forcing/nasa_power_t2m.parquet"


def _air_map(network_id: str) -> dict[str, pd.Series]:
    if not POWER.exists():
        return {}
    frame = pd.read_parquet(POWER)
    frame["date"] = pd.to_datetime(frame["date"])
    sub = frame.loc[frame["network_id"].astype(str).eq(network_id)]
    out: dict[str, pd.Series] = {}
    for station, group in sub.groupby("station_id"):
        out[str(station)] = group.set_index("date")["air_temperature_c"]
    return out


def _one(payload: tuple[str, str, str, bool]) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    network_id, evidence_use, failure_mode, co_missing = payload
    roster = load_trusted_roster(evidence_use)
    roster = roster.loc[roster["network_id"].eq(network_id)]
    gaps, years = score_network_complete_years(
        network_id,
        roster,
        air_by_station=_air_map(network_id),
        failure_mode=failure_mode,
        include_co_missing=co_missing,
    )
    return network_id, gaps, years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-use", default="design_development")
    parser.add_argument("--failure-mode", default="archived_or_generated")
    parser.add_argument("--co-missing", action="store_true")
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--networks", default=None)
    parser.add_argument("--output", default=str(STEP5_THERMAL_DECISION))
    parser.add_argument("--skip-calibration", action="store_true")
    args = parser.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    roster = load_trusted_roster(args.evidence_use)
    ids = sorted(roster["network_id"].unique())
    if args.networks:
        requested = {item.strip() for item in args.networks.split(",") if item.strip()}
        ids = [item for item in ids if item in requested]
    if args.max_networks is not None:
        ids = ids[: args.max_networks]
    payloads = [(nid, args.evidence_use, args.failure_mode, bool(args.co_missing)) for nid in ids]
    gap_frames = []
    year_frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_one, payload): payload[0] for payload in payloads}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                _, gaps, years = fut.result()
                if gaps is not None and not gaps.empty:
                    gap_frames.append(gaps)
                if years is not None and not years.empty:
                    year_frames.append(years)
                print(
                    f"thermal {network_id} gaps={0 if gaps is None else len(gaps)} years={0 if years is None else len(years)}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    pd.DataFrame(failures).to_csv(out_dir / "failures.csv", index=False)
    if not year_frames:
        raise SystemExit("no complete-year thermal rows")
    gaps = pd.concat(gap_frames, ignore_index=True) if gap_frames else pd.DataFrame()
    years = pd.concat(year_frames, ignore_index=True)
    gaps.to_csv(out_dir / "gap_scores.csv", index=False)
    years.to_csv(out_dir / "year_policies_raw.csv", index=False)
    if args.skip_calibration:
        years.to_csv(out_dir / "year_policies.csv", index=False)
        summary = {
            "evidence_use": args.evidence_use,
            "failure_mode": args.failure_mode,
            "skip_calibration": True,
            "n_gap_rows": int(len(gaps)),
            "n_year_rows": int(len(years)),
            "n_networks": int(years["network_id"].nunique()) if not years.empty else 0,
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        print(json.dumps(summary, indent=2))
        return
    calibrated, freeze = attach_calibrated_policies(years)
    calibrated.to_csv(out_dir / "year_policies.csv", index=False)
    comparison = compare_eval_policies(calibrated)
    comparison.to_csv(out_dir / "eval_policy_comparison.csv", index=False)
    (out_dir / "tau_freeze.json").write_text(json.dumps(freeze, indent=2))
    if Path(args.output).resolve() == STEP5_THERMAL_DECISION.resolve():
        ablation_dir = STEP6_ABLATIONS
        ablation_dir.mkdir(parents=True, exist_ok=True)
        comparison.to_csv(ablation_dir / "eval_policy_comparison.csv", index=False)
    summary = {
        "evidence_use": args.evidence_use,
        "failure_mode": args.failure_mode,
        "n_gap_rows": int(len(gaps)),
        "n_year_rows": int(len(calibrated)),
        "n_networks": int(calibrated["network_id"].nunique()) if not calibrated.empty else 0,
        "tau": freeze,
        "eval_policies": comparison.to_dict(orient="records"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "eval_policies"}, indent=2))
    if not comparison.empty:
        print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
