"""Development-only Tier-2 strong-model subsample on the frozen open-qualified slice.

This is not the preregistered Tier-2 sensitivity. The locked 30-network sample
cannot meet the 28--32 open-qualified floor, and the formal reference protocol
requires T/F/L channels that the open temperature panels do not carry. This
runner still executes official PyPOTS SAITS/CSDI fit+predict on every open
network in the frozen sample that passes failure_closure6 today, with all three
required gaps, and records ``passed: false``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    TIER2_GAPS,
    deterministic_placements,
    discover_failure_closure_networks,
    read_panel,
)
from stream_recoverability.experiments.t2_tier2_readiness import (
    SAMPLE_LOCK_RELATIVE_PATH,
    TIER2_MODELS,
    build_tier2_deep_readiness_manifest,
    validate_tier2_sample_lock,
)
from stream_recoverability.models.reference_baselines import require_pypots_15

DEVELOPMENT_MODELS = ("saits", "csdi")
MANIFEST_SCHEMA = "t2_v91_tier2_development_subsample_v1"


def _load_sample(repo: Path) -> dict[str, Any]:
    sample = json.loads((repo / SAMPLE_LOCK_RELATIVE_PATH).read_text(encoding="utf-8"))
    validate_tier2_sample_lock(sample)
    return sample


def _qualified_open_ids(repo: Path) -> set[str]:
    readiness = build_tier2_deep_readiness_manifest(repo, run_constructor_smoke=False)
    return set(readiness["sample_eligibility"]["open_currently_qualified_ids"])


def _target_for_gaps(panel: pd.DataFrame, *, gaps: tuple[int, ...]) -> str | None:
    for column in sorted(panel.columns):
        if all(
            len(
                deterministic_placements(
                    panel, target=str(column), gap_length=int(gap), count=1
                )
            )
            >= 1
            for gap in gaps
        ):
            return str(column)
    return None


def _impute_mae(
    values: np.ndarray,
    *,
    model_name: str,
    gap: int,
    target_col: int,
    epochs: int,
    seed: int,
) -> float:
    bindings = require_pypots_15()
    n_steps, n_features = values.shape
    X = values.reshape(1, n_steps, n_features).astype(np.float32)
    mask = np.zeros_like(X, dtype=bool)
    mask[0, :, target_col] = True
    X_masked = X.copy()
    X_masked[mask] = np.nan
    d_model = int(min(64, max(16, n_features * 8)))
    common = {
        "n_steps": int(gap),
        "n_features": int(n_features),
        "n_layers": 1,
        "d_model": d_model,
        "n_heads": 4,
        "d_k": d_model // 4,
        "d_v": d_model // 4,
        "d_ffn": d_model * 2,
        "dropout": 0.0,
        "batch_size": 1,
        "epochs": int(epochs),
        "patience": max(1, int(epochs)),
        "device": "cpu",
        "saving_path": None,
    }
    if model_name == "saits":
        model = bindings.SAITS(**common)
    elif model_name == "csdi":
        model = bindings.CSDI(
            n_steps=int(gap),
            n_features=int(n_features),
            n_layers=1,
            n_heads=4,
            n_channels=64,
            d_time_embedding=32,
            d_feature_embedding=32,
            d_diffusion_embedding=32,
            n_diffusion_steps=10,
            batch_size=1,
            epochs=int(epochs),
            patience=max(1, int(epochs)),
            device="cpu",
            saving_path=None,
        )
    else:
        raise ValueError(f"unsupported development model: {model_name}")
    train_set = {"X": X_masked}
    model.fit(train_set)
    imputed_raw = model.impute(train_set)
    imputed = np.asarray(
        imputed_raw["imputation"] if isinstance(imputed_raw, dict) else imputed_raw,
        dtype=float,
    )
    if imputed.ndim == 4:
        imputed = imputed[:, 0, :, :]
    truth = X[mask]
    pred = imputed[mask]
    return float(np.nanmean(np.abs(pred - truth)))


def run_tier2_development_subsample(
    repo_root: str | Path,
    *,
    models: tuple[str, ...] = DEVELOPMENT_MODELS,
    gaps: tuple[int, ...] = TIER2_GAPS,
    epochs: int = 3,
    seed: int = 20260827,
    max_networks: int | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    sample = _load_sample(repo)
    qualified = _qualified_open_ids(repo)
    sample_rows = list(sample["sample"])
    open_rows = [row for row in sample_rows if str(row["network_id"]) in qualified]
    if max_networks is not None:
        open_rows = open_rows[: int(max_networks)]
    networks, _ = discover_failure_closure_networks(repo)
    by_id = {network.network_id: network for network in networks}
    rows: list[dict[str, Any]] = []
    for item in open_rows:
        network_id = str(item["network_id"])
        network = by_id.get(network_id)
        if network is None:
            continue
        panel = read_panel(repo, network)
        target = _target_for_gaps(panel, gaps=gaps)
        if target is None:
            rows.append(
                {
                    "network_id": network_id,
                    "role": str(item.get("role", "")),
                    "status": "no_target_with_all_gap_placements",
                }
            )
            continue
        target_col = int(list(panel.columns).index(target))
        for gap in gaps:
            starts = deterministic_placements(
                panel, target=target, gap_length=int(gap), count=1
            )
            if not starts:
                rows.append(
                    {
                        "network_id": network_id,
                        "gap_length_days": int(gap),
                        "status": "no_placement",
                    }
                )
                continue
            start = int(starts[0])
            segment = panel.iloc[start : start + int(gap)].to_numpy(dtype=float)
            for model_name in models:
                if model_name not in DEVELOPMENT_MODELS:
                    continue
                try:
                    mae = _impute_mae(
                        segment,
                        model_name=model_name,
                        gap=int(gap),
                        target_col=target_col,
                        epochs=int(epochs),
                        seed=int(seed),
                    )
                    status = "fit_predict_complete"
                except Exception as error:  # noqa: BLE001
                    mae = float("nan")
                    status = f"failed:{type(error).__name__}"
                rows.append(
                    {
                        "network_id": network_id,
                        "role": str(item.get("role", "")),
                        "target_station": target,
                        "gap_length_days": int(gap),
                        "model": model_name,
                        "placement_start_index": start,
                        "fill_mae_c": mae,
                        "model_fit_called": status == "fit_predict_complete",
                        "model_predict_called": status == "fit_predict_complete",
                        "status": status,
                    }
                )
    frame = pd.DataFrame(rows)
    n_fit = int(frame.get("model_fit_called", pd.Series(dtype=bool)).fillna(False).sum())
    readiness = build_tier2_deep_readiness_manifest(repo, run_constructor_smoke=False)
    eligibility = readiness["sample_eligibility"]
    return {
        "manifest_schema": MANIFEST_SCHEMA,
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "confirmatory_eligible": False,
        "can_claim_compliant_tier2_sensitivity": False,
        "deep_models_run": bool(n_fit > 0),
        "deep_model_training_run": bool(n_fit > 0),
        "deep_model_inference_run": bool(n_fit > 0),
        "models_attempted": list(models),
        "gaps_all_required": [int(value) for value in gaps],
        "roster_obligations_not_run": [
            model for model in TIER2_MODELS if model not in DEVELOPMENT_MODELS
        ],
        "n_sample_open_currently_qualified": int(
            eligibility["n_sample_open_currently_qualified"]
        ),
        "n_networks_attempted": int(len(open_rows)),
        "n_rows": int(len(frame)),
        "n_fit_predict_complete": n_fit,
        "budget_failure": readiness["budget_failure"],
        "status": (
            "development_subsample_executed_budget_failure_remains"
            if n_fit > 0
            else "development_subsample_failed_no_successful_cells"
        ),
        "passed": False,
        "purpose": "tier2_development_subsample_not_confirmatory",
        "rows": frame.to_dict(orient="records"),
    }


def write_tier2_development_subsample(
    repo_root: str | Path,
    output_dir: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = run_tier2_development_subsample(repo_root, **kwargs)
    rows = manifest.pop("rows", [])
    if rows:
        pd.DataFrame(rows).to_csv(output / "tier2_development_subsample_rows.csv", index=False)
    (output / "tier2_development_subsample_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest["rows"] = rows
    return manifest


__all__ = [
    "DEVELOPMENT_MODELS",
    "MANIFEST_SCHEMA",
    "run_tier2_development_subsample",
    "write_tier2_development_subsample",
]
