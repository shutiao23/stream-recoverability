#!/usr/bin/env python3
"""Write the local independent-study plan; optionally record an OSF link."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
import wrr_tr_common as T
from stream_recoverability.seeds import plain_seed
from stream_recoverability.experiments.tr_revision.independent import (
    accepted_public_registration,
    registration_identifier,
)

CONFIG = json.loads(
    (T.ROOT / "configs/wrr_review_completion_20261024.json").read_text()
)
OUT = T.ROOT / CONFIG["out"] / "independent_study"


def power():
    rows = []
    for seed in CONFIG["seeds"]:
        files = sorted(
            (OUT.parent / f"refits/leave_one_year_out/seed_{seed:02d}").glob(
                "*.parquet"
            )
        )
        if not files:
            return None
        c = pd.concat(
            [
                pd.read_parquet(
                    p,
                    columns=[
                        "independence_group",
                        "design_family",
                        "D2",
                        "eval_truth_h30",
                        "risk_score",
                    ],
                )
                for p in files
            ]
        )
        c = c.loc[c.design_family.eq("crossed")].copy()
        c["admitted"] = c.risk_score.le(0.1)
        c["bad"] = c.admitted & (c.D2 - c.eval_truth_h30).abs().gt(0.5)
        g = c.groupby("independence_group").agg(a=("admitted", "sum"), b=("bad", "sum"))
        a, b = (g.a.to_numpy(float), g.b.to_numpy(float))
        for n in [20, 30, 40, 60, 80, 100, 150, 200]:
            rng = np.random.default_rng(plain_seed(72, seed, n))
            index = rng.integers(0, len(g), (2000, n))
            admitted = a[index]
            bad = b[index]
            total = admitted.sum(axis=1)
            risk = np.divide(
                bad.sum(axis=1), total, out=np.full(2000, np.nan), where=total > 0
            )
            evaluable = admitted >= 20
            ratios = np.divide(
                bad, admitted, out=np.full_like(bad, np.nan), where=admitted > 0
            )
            excess = np.divide(
                ((ratios > 0.1) & evaluable).sum(axis=1),
                evaluable.sum(axis=1),
                out=np.full(2000, np.nan),
                where=evaluable.sum(axis=1) > 0,
            )
            influence = (bad - risk[:, None] * admitted) / np.maximum(
                admitted.mean(axis=1)[:, None], 1e-12
            )
            upper = risk + 1.645 * influence.std(axis=1, ddof=1) / np.sqrt(n)
            success = (
                np.isfinite(risk + excess)
                & (risk <= 0.06)
                & (upper <= 0.08)
                & (excess <= 0.1)
            )
            rows.append(
                dict(
                    seed=seed,
                    independent_groups=n,
                    simulation_repetitions=2000,
                    joint_E1_E2_probability=float(success.mean()),
                )
            )
    per_seed = pd.DataFrame(rows)
    per_seed.to_csv(OUT / "sample_size_planning_by_seed.csv", index=False)
    combined = []
    for n, b in per_seed.groupby("independent_groups"):
        p = b.joint_E1_E2_probability
        combined.append(
            dict(
                independent_groups=n,
                n_source_seeds=b.seed.nunique(),
                simulation_repetitions_per_seed=2000,
                total_simulations=2000 * len(b),
                joint_E1_E2_probability=float(p.mean()),
                source_seed_lower=float(p.quantile(0.025)),
                source_seed_upper=float(p.quantile(0.975)),
            )
        )
    result = pd.DataFrame(combined)
    result.to_csv(OUT / "sample_size_planning.csv", index=False)
    T.write_json(
        OUT / "planning_design.json",
        {
            "source_seeds": CONFIG["seeds"],
            "mixing": "equal mixture of seed-specific independent-group empirical resampling; 2000 simulations per seed and group budget",
            "interpretation": "algorithm and source-group composition sensitivity on the same opened archive, not independent climates or confirmed new-region power",
            "E1_interval": "delta-method planning approximation; registered evaluation uses group bootstrap",
            "joint": "E1 and E2 must both pass; zero admission or no evaluable group fails",
        },
    )
    return result


def verify_osf(identifier):
    identifier = registration_identifier(identifier)
    response = requests.get(
        f"https://api.osf.io/v2/registrations/{identifier}/?version=2.20", timeout=30
    )
    response.raise_for_status()
    timestamp = accepted_public_registration(response.json(), identifier)
    T.write_json(
        OUT / "public_registration_status.json",
        {
            "status": "public_registration_record_found",
            "registration_id": identifier,
            "registered_utc": timestamp,
            "url": f"https://osf.io/{identifier}/",
        },
    )


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "status": "local research plan; public registration is optional",
        "population": "nine metadata-selected Greater Wellington river sites in three conservative management zones",
        "measurement_plan": "acquisition_plan.json",
        "method": "unchanged source annual model and calibration; local daily models fit other observed years",
        "source_model": "results/wrr_review_completion_20261024/deployment/global_source_candidate.joblib",
        "endpoints": [
            "observed-window record witnesses",
            "annual MAE and 90% coverage",
            "selected error risk and availability",
        ],
        "qualification": "at least four complete July-June years of quality-accepted native daily means",
        "inference": "report all nine eligibility outcomes; three zones do not establish broad climate transfer",
        "registration": "report actual registration/access dates; an unregistered test remains unregistered",
        "authorship": "user supplies author, institution, funding and deposit details",
    }
    T.write_json(OUT / "protocol_draft.json", protocol)
    T.write_json(
        OUT / "source_case_settings.json",
        T.settings()
        | {
            "classical_baselines": True,
            "trajectory_targets": ["h30"],
            "replication_seeds": [0],
            "training_split": "leave_one_year_out",
        },
    )
    T.write_json(
        OUT / "source_missingness_generator.json",
        json.loads((T.E1_MISSINGNESS / "mnar_generator.json").read_text()),
    )
    return protocol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--osf-registration")
    parser.add_argument("--planning-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.osf_registration:
        verify_osf(args.osf_registration)
    elif args.planning_only:
        power()
    else:
        prepare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
