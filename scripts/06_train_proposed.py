#!/usr/bin/env python3
"""Run a lightweight deterministic smoke training of the proposed model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.models.proposed import (  # noqa: E402
    MissingAwareMultisourceImputer,
    ProposedModelConfig,
)
from stream_recoverability.models.proposed_training import (  # noqa: E402
    ProposedTrainingConfig,
    set_deterministic_seed,
    train_proposed_model,
)


def _synthetic_batches(seed: int, batch_size: int) -> tuple[list[dict[str, torch.Tensor]], list[dict[str, torch.Tensor]]]:
    generator = torch.Generator().manual_seed(seed)
    samples, steps, stations, variables = 12, 24, 3, 8
    time = torch.arange(steps, dtype=torch.float32).view(1, steps, 1)
    station = torch.arange(stations, dtype=torch.float32).view(1, 1, stations)
    air = 10.0 + 7.0 * torch.sin(2.0 * torch.pi * time / steps) + 0.4 * station
    flow = 5.0 + 0.4 * torch.cos(2.0 * torch.pi * time / steps) + station
    level = 2.0 + 0.12 * flow
    target = 0.65 * air + 0.15 * flow + 0.2 * station

    truth = torch.zeros((samples, steps, stations, variables), dtype=torch.float32)
    noise = 0.02 * torch.randn((samples, steps, stations), generator=generator)
    truth[..., 0] = target.expand(samples, -1, -1) + noise
    truth[..., 1] = flow.expand(samples, -1, -1)
    truth[..., 2] = level.expand(samples, -1, -1)
    truth[..., 3] = air.expand(samples, -1, -1)
    truth[..., 4] = torch.relu(torch.sin(time / 3.0)).expand(samples, -1, stations)
    truth[..., 5] = 2.0
    truth[..., 6] = 55.0
    truth[..., 7] = 8.0 + torch.cos(time / 4.0).expand(samples, -1, stations)

    natural_mask = torch.rand(truth.shape, generator=generator) > 0.03
    artificial_mask = torch.zeros_like(natural_mask)
    artificial_mask[:, 9:14, :, 0] = True
    phase = 2.0 * torch.pi * torch.arange(steps, dtype=torch.float32) / steps
    seasonal = torch.stack((torch.sin(phase), torch.cos(phase), torch.sin(phase / 2), torch.cos(phase / 2)), dim=-1)
    seasonal = seasonal.unsqueeze(0).expand(samples, -1, -1).clone()

    dataset = {
        "values": truth.clone(),
        "natural_mask": natural_mask,
        "artificial_mask": artificial_mask,
        "target": truth[..., 0].clone(),
        "quality_mask": natural_mask[..., 0].clone(),
        "seasonal_features": seasonal,
    }

    def batches(indices: np.ndarray) -> list[dict[str, torch.Tensor]]:
        return [
            {key: value[part] for key, value in dataset.items()}
            for start in range(0, len(indices), batch_size)
            for part in [torch.as_tensor(indices[start : start + batch_size], dtype=torch.long)]
        ]

    return batches(np.arange(0, 9)), batches(np.arange(9, samples))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Explicitly select the synthetic smoke run")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--checkpoint", type=Path, default=Path("checkpoints/proposed_smoke.pt"))
    parser.add_argument("--device", default="cpu")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.smoke:
        parser.error("this entry point is synthetic smoke-only; pass --smoke")
    set_deterministic_seed(args.seed)
    train_batches, validation_batches = _synthetic_batches(args.seed, args.batch_size)
    model = MissingAwareMultisourceImputer(
        ProposedModelConfig(hidden_size=16, dropout=0.0)
    )
    result = train_proposed_model(
        model,
        train_batches,
        validation_batches,
        ProposedTrainingConfig(
            epochs=args.epochs,
            patience=max(1, min(3, args.epochs)),
            seed=args.seed,
            device=args.device,
            source_dropout_probability=0.25,
        ),
        checkpoint_path=args.checkpoint,
    )
    with torch.no_grad():
        example = validation_batches[0]
        output = model(
            example["values"].to(args.device),
            example["natural_mask"].to(args.device),
            example["artificial_mask"].to(args.device),
            seasonal_features=example["seasonal_features"].to(args.device),
        )
    summary = {
        "mode": "smoke",
        "best_epoch": result.best_epoch,
        "best_validation_loss": result.best_validation_loss,
        "epochs_run": result.epochs_run,
        "quantile_shape": list(output["quantiles"].shape),
        "checkpoint": str(args.checkpoint),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
