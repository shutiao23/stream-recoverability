"""Small missing-aware multisource model for stream-temperature recovery.

The model has a permanent baseline branch, ``S0``, and four switchable
information groups. ``S0`` contains calendar/seasonal features, an optional
training-only climatology, and station identity. ``A`` contains local target
history, ``B`` same-station FLOW/WLEVEL, ``C`` other-station T/F/L through a
small masked-attention summary, and ``D`` same-station meteorology only. The
cross-station branch is deliberately not a graph neural network; it is suitable
for the current three-station case study.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from itertools import product

import torch
import torch.nn.functional as F
from torch import Tensor, nn

MAIN_ARCHITECTURE_VERSION = "s0_abcd_rs_v1"
RETIRED_SUNSHINE_DH_ARCHITECTURE_VERSION = "s0_abcd_v2"
MAIN_METEOROLOGY_VARIABLES = ("Ta", "P", "W", "RH", "Rs")
MAIN_VARIABLE_NAMES = ("T", "F", "L", "Ta", "P", "W", "RH", "Rs")
INFORMATION_GROUPS = ("A", "B", "C", "D")
GROUP_ALIASES = {
    "A": "A",
    "LOCAL": "A",
    "LOCAL_TEMPORAL": "A",
    "B": "B",
    "HYDRO": "B",
    "SAME_STATION_HYDRO": "B",
    "C": "C",
    "CROSS_STATION": "C",
    "D": "D",
    "MET": "D",
    "METEOROLOGY": "D",
    "METEOROLOGY_SEASON": "D",
}


@dataclass(frozen=True)
class ProposedModelConfig:
    station_ids: tuple[str, ...] = ("B1", "S2", "P3")
    variable_names: tuple[str, ...] = MAIN_VARIABLE_NAMES
    target_variable: str = "T"
    hydro_variables: tuple[str, ...] = ("F", "L")
    cross_station_variables: tuple[str, ...] = ("T", "F", "L")
    meteorology_variables: tuple[str, ...] = MAIN_METEOROLOGY_VARIABLES
    hidden_size: int = 32
    station_embedding_size: int = 8
    variable_embedding_size: int = 4
    seasonal_feature_size: int = 4
    dropout: float = 0.1
    max_time_gap: float = 736.0
    architecture_version: str = MAIN_ARCHITECTURE_VERSION


def require_main_rs_architecture(
    *,
    architecture_version: str,
    meteorology_variables: Sequence[str],
    variable_names: Sequence[str] | None = None,
) -> None:
    """Fail closed if Group D is Rs while the architecture token stays on DH."""

    version = str(architecture_version)
    meteorology = tuple(str(name) for name in meteorology_variables)
    names = tuple(str(name) for name in (variable_names or ()))
    uses_rs = "Rs" in meteorology or "Rs" in names
    if version == RETIRED_SUNSHINE_DH_ARCHITECTURE_VERSION:
        raise ValueError(
            "architecture_version 's0_abcd_v2' is retired for the main model; "
            "Group D now uses Rs (s0_abcd_rs_v1). Jinsha DH sunshine hours are "
            "sensitivity-only. s0_abcd_v2 cannot be used while Rs is the main "
            "meteorology channel."
        )
    if version != MAIN_ARCHITECTURE_VERSION:
        raise ValueError(
            f"architecture_version must be {MAIN_ARCHITECTURE_VERSION!r}"
        )
    if meteorology != MAIN_METEOROLOGY_VARIABLES:
        raise ValueError(
            "main Group D meteorology must be Ta, P, W, RH, Rs; "
            f"got {meteorology}"
        )
    if "DH" in meteorology:
        raise ValueError(
            "DH sunshine hours are sensitivity-only and cannot be a main "
            "Group D channel"
        )
    if uses_rs is False:
        raise ValueError("main architecture_version s0_abcd_rs_v1 requires Rs")


def information_group_mask(
    groups: Collection[str], *, device: torch.device | None = None
) -> Tensor:
    """Convert group names or aliases to a four-element A/B/C/D mask."""

    selected: set[str] = set()
    for group in groups:
        key = str(group).strip().upper().replace("-", "_").replace(" ", "_")
        if key not in GROUP_ALIASES:
            raise ValueError(f"Unknown information group {group!r}; use A, B, C, or D")
        selected.add(GROUP_ALIASES[key])
    return torch.tensor(
        [group in selected for group in INFORMATION_GROUPS],
        dtype=torch.bool,
        device=device,
    )


def all_information_group_combinations() -> tuple[tuple[str, ...], ...]:
    """Return the 16 A/B/C/D combinations used for ablation analysis."""

    return tuple(
        tuple(group for group, enabled in zip(INFORMATION_GROUPS, flags) if enabled)
        for flags in product((False, True), repeat=4)
    )


def compute_bidirectional_time_gaps(
    available_target: Tensor, max_gap: float = 736.0
) -> Tensor:
    """Compute days since previous and until next available target value."""

    if available_target.ndim != 3:
        raise ValueError("available_target must have shape [batch, time, station]")
    available = available_target.bool()
    batch, steps, stations = available.shape
    previous = torch.empty(
        (batch, steps, stations), dtype=torch.float32, device=available.device
    )
    following = torch.empty_like(previous)

    counter = torch.full((batch, stations), float(max_gap), device=available.device)
    for index in range(steps):
        counter = torch.where(
            available[:, index],
            torch.zeros_like(counter),
            torch.clamp(counter + 1.0, max=float(max_gap)),
        )
        previous[:, index] = counter

    counter.fill_(float(max_gap))
    for index in range(steps - 1, -1, -1):
        counter = torch.where(
            available[:, index],
            torch.zeros_like(counter),
            torch.clamp(counter + 1.0, max=float(max_gap)),
        )
        following[:, index] = counter
    return torch.stack((previous, following), dim=-1)


def _safe_masked_softmax(logits: Tensor, valid: Tensor, dim: int = -1) -> Tensor:
    valid = valid.bool()
    finite_floor = torch.finfo(logits.dtype).min
    masked = logits.masked_fill(~valid, finite_floor)
    maximum = masked.max(dim=dim, keepdim=True).values
    maximum = torch.where(
        valid.any(dim=dim, keepdim=True), maximum, torch.zeros_like(maximum)
    )
    weights = torch.exp(masked - maximum) * valid.to(logits.dtype)
    return weights / weights.sum(dim=dim, keepdim=True).clamp_min(1e-12)


class MissingAwareMultisourceImputer(nn.Module):
    """Permanent-S0 quantile imputer with gated A/B/C/D information sources."""

    quantile_levels = (0.05, 0.25, 0.50, 0.75, 0.95)

    def __init__(self, config: ProposedModelConfig | None = None) -> None:
        super().__init__()
        self.config = config or ProposedModelConfig()
        if self.config.hidden_size < 4:
            raise ValueError("hidden_size must be at least 4")
        require_main_rs_architecture(
            architecture_version=self.config.architecture_version,
            meteorology_variables=self.config.meteorology_variables,
            variable_names=self.config.variable_names,
        )
        if not self.config.station_ids:
            raise ValueError("At least one station is required")
        if not 0.0 <= self.config.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")

        self.variable_index = {
            name: index for index, name in enumerate(self.config.variable_names)
        }
        required = {
            self.config.target_variable,
            *self.config.hydro_variables,
            *self.config.cross_station_variables,
        }
        absent = sorted(required.difference(self.variable_index))
        if absent:
            raise ValueError(f"variable_names is missing required channels: {absent}")
        self.target_index = self.variable_index[self.config.target_variable]
        self.hydro_indices = tuple(
            self.variable_index[name] for name in self.config.hydro_variables
        )
        self.cross_indices = tuple(
            self.variable_index[name] for name in self.config.cross_station_variables
        )
        self.met_indices = tuple(
            self.variable_index[name]
            for name in self.config.meteorology_variables
            if name in self.variable_index
        )

        hidden = self.config.hidden_size
        station_size = self.config.station_embedding_size
        variable_size = self.config.variable_embedding_size
        self.station_embedding = nn.Embedding(
            len(self.config.station_ids), station_size
        )
        self.variable_embedding = nn.Embedding(
            len(self.config.variable_names), variable_size
        )

        temporal_input_size = 4 + station_size + variable_size
        direction_size = max(2, math.ceil(hidden / 2))
        self.temporal_encoder = nn.GRU(
            temporal_input_size,
            direction_size,
            batch_first=True,
            bidirectional=True,
        )
        self.temporal_projection = nn.Sequential(
            nn.Linear(direction_size * 2, hidden),
            nn.GELU(),
            nn.Dropout(self.config.dropout),
        )

        variable_input_size = 2 + variable_size
        self.hydro_value_encoder = self._value_encoder(variable_input_size, hidden)
        self.cross_value_encoder = self._value_encoder(variable_input_size, hidden)
        self.met_value_encoder = self._value_encoder(variable_input_size, hidden)

        self.cross_station_projection = nn.Sequential(
            nn.Linear(hidden + station_size, hidden), nn.GELU()
        )
        self.cross_key = nn.Linear(hidden, hidden, bias=False)
        self.cross_query = nn.Linear(station_size, hidden, bias=False)

        self.s0_projection = nn.Sequential(
            nn.Linear(
                self.config.seasonal_feature_size + 2 + station_size,
                hidden,
            ),
            nn.GELU(),
            nn.Dropout(self.config.dropout),
        )
        self.met_projection = nn.Sequential(
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Dropout(self.config.dropout),
        )
        gate_input_size = hidden * 5 + 4 + station_size
        self.gate = nn.Sequential(
            nn.Linear(gate_input_size, hidden),
            nn.GELU(),
            nn.Linear(hidden, 4),
        )
        self.quantile_head = nn.Sequential(
            nn.Linear(hidden + station_size, hidden),
            nn.GELU(),
            nn.Linear(hidden, len(self.quantile_levels)),
        )

    def _value_encoder(self, input_size: int, hidden: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Linear(input_size, hidden),
            nn.GELU(),
            nn.Dropout(self.config.dropout),
            nn.Linear(hidden, hidden),
        )

    def _validate_inputs(
        self, values: Tensor, natural_mask: Tensor, artificial_mask: Tensor | None
    ) -> None:
        if values.ndim != 4:
            raise ValueError("values must have shape [batch, time, station, variable]")
        if natural_mask.shape != values.shape:
            raise ValueError("natural_mask must have the same shape as values")
        if artificial_mask is not None and artificial_mask.shape != values.shape:
            raise ValueError("artificial_mask must have the same shape as values")
        if values.shape[2] != len(self.config.station_ids):
            raise ValueError("values station axis does not match config.station_ids")
        if values.shape[3] != len(self.config.variable_names):
            raise ValueError(
                "values variable axis does not match config.variable_names"
            )

    def _encode_variables(
        self,
        filled_values: Tensor,
        available: Tensor,
        indices: Sequence[int],
        encoder: nn.Module,
    ) -> tuple[Tensor, Tensor]:
        selected_values = filled_values[..., list(indices)]
        selected_mask = available[..., list(indices)]
        ids = torch.tensor(indices, dtype=torch.long, device=filled_values.device)
        embeddings = self.variable_embedding(ids)
        view_shape = (1,) * (selected_values.ndim - 1) + embeddings.shape
        embeddings = embeddings.view(view_shape).expand(
            *selected_values.shape, embeddings.shape[-1]
        )
        features = torch.cat(
            (
                selected_values.unsqueeze(-1),
                selected_mask.to(filled_values.dtype).unsqueeze(-1),
                embeddings,
            ),
            dim=-1,
        )
        encoded = encoder(features) * selected_mask.unsqueeze(-1).to(
            filled_values.dtype
        )
        denominator = (
            selected_mask.sum(dim=-1, keepdim=True).clamp_min(1).to(filled_values.dtype)
        )
        summary = encoded.sum(dim=-2) / denominator
        availability = selected_mask.to(filled_values.dtype).mean(dim=-1)
        return summary, availability

    def _time_gaps(
        self, time_gap: Tensor | None, target_available: Tensor, values: Tensor
    ) -> Tensor:
        computed = compute_bidirectional_time_gaps(
            target_available, self.config.max_time_gap
        )
        if time_gap is None:
            result = computed
        elif time_gap.shape == (*target_available.shape, 2):
            result = time_gap
        elif time_gap.shape == target_available.shape:
            result = torch.stack((time_gap, computed[..., 1]), dim=-1)
        elif time_gap.shape == values.shape:
            result = torch.stack(
                (time_gap[..., self.target_index], computed[..., 1]), dim=-1
            )
        elif time_gap.shape == (*values.shape, 2):
            result = time_gap[..., self.target_index, :]
        else:
            raise ValueError(
                "time_gap must be [B,T,N], [B,T,N,2], [B,T,N,V], or [B,T,N,V,2]"
            )
        return (
            torch.nan_to_num(
                result.to(values.dtype), nan=self.config.max_time_gap
            ).clamp(min=0.0, max=self.config.max_time_gap)
            / self.config.max_time_gap
        )

    def _s0_features(
        self,
        seasonal_features: Tensor | None,
        training_climatology: Tensor | None,
        *,
        shape: tuple[int, int, int],
        reference: Tensor,
    ) -> tuple[Tensor, Tensor]:
        """Return finite seasonal and optional training-climatology features.

        ``training_climatology`` is expected to be derived from training rows
        only and expressed on the same scale as the target channel. Its finite
        indicator lets the model distinguish a missing climatology from a
        legitimate standardized value of zero. Missing optional inputs fall
        back to zeros; S0 therefore remains finite and available.
        """

        batch, steps, stations = shape
        seasonal_shape = (batch, steps, stations, self.config.seasonal_feature_size)
        if seasonal_features is None:
            seasonal = reference.new_zeros(seasonal_shape)
        elif seasonal_features.shape == (
            batch,
            steps,
            self.config.seasonal_feature_size,
        ):
            seasonal = seasonal_features[:, :, None, :].expand(-1, -1, stations, -1)
        elif seasonal_features.shape == seasonal_shape:
            seasonal = seasonal_features
        else:
            raise ValueError(
                "seasonal_features must have shape [B,T,S] or [B,T,N,S] "
                "matching seasonal_feature_size"
            )
        seasonal = torch.nan_to_num(
            seasonal.to(device=reference.device, dtype=reference.dtype),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        climatology_shape = (batch, steps, stations)
        if training_climatology is None:
            climatology = reference.new_zeros(climatology_shape)
            climatology_available = torch.zeros(
                climatology_shape,
                dtype=torch.bool,
                device=reference.device,
            )
        else:
            climatology = training_climatology.to(
                device=reference.device,
                dtype=reference.dtype,
            )
            if climatology.shape == (batch, steps):
                climatology = climatology[:, :, None].expand(-1, -1, stations)
            elif climatology.shape == (*climatology_shape, 1):
                climatology = climatology.squeeze(-1)
            elif climatology.shape != climatology_shape:
                raise ValueError(
                    "training_climatology must have shape [B,T], [B,T,N], or [B,T,N,1]"
                )
            climatology_available = torch.isfinite(climatology)
            climatology = torch.nan_to_num(
                climatology,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            )
        climatology_features = torch.stack(
            (
                climatology,
                climatology_available.to(reference.dtype),
            ),
            dim=-1,
        )
        return seasonal, climatology_features

    def _group_enabled(
        self,
        enabled_groups: Collection[str] | Tensor | None,
        group_mask: Tensor | None,
        shape: tuple[int, int, int],
        device: torch.device,
    ) -> Tensor:
        batch, steps, stations = shape
        if enabled_groups is not None and group_mask is not None:
            raise ValueError("Pass enabled_groups or group_mask, not both")
        if group_mask is not None:
            mask = group_mask.to(device=device, dtype=torch.bool)
        elif isinstance(enabled_groups, Tensor):
            mask = enabled_groups.to(device=device, dtype=torch.bool)
        elif enabled_groups is None:
            mask = torch.ones(4, dtype=torch.bool, device=device)
        else:
            mask = information_group_mask(enabled_groups, device=device)
        if mask.shape == (4,):
            return mask.view(1, 1, 1, 4).expand(batch, steps, stations, 4)
        if mask.shape == (batch, 4):
            return mask[:, None, None, :].expand(batch, steps, stations, 4)
        if mask.shape == (batch, steps, stations, 4):
            return mask
        raise ValueError(
            "group mask must have shape [4], [batch,4], or [batch,time,station,4]"
        )

    def forward(
        self,
        values: Tensor,
        natural_mask: Tensor,
        artificial_mask: Tensor | None = None,
        time_gap: Tensor | None = None,
        seasonal_features: Tensor | None = None,
        *,
        training_climatology: Tensor | None = None,
        enabled_groups: Collection[str] | Tensor | None = None,
        group_mask: Tensor | None = None,
    ) -> dict[str, Tensor]:
        self._validate_inputs(values, natural_mask, artificial_mask)
        artificial = (
            torch.zeros_like(natural_mask, dtype=torch.bool)
            if artificial_mask is None
            else artificial_mask.bool()
        )
        available = natural_mask.bool() & ~artificial & torch.isfinite(values)
        filled = torch.where(
            available, torch.nan_to_num(values), torch.zeros_like(values)
        )
        batch, steps, stations, _ = values.shape
        station_ids = torch.arange(stations, device=values.device)
        station_embedding = self.station_embedding(station_ids)
        station_context = station_embedding.view(1, 1, stations, -1).expand(
            batch, steps, -1, -1
        )

        # S0: permanent calendar/climatology/static-station baseline. It is not
        # represented in enabled_groups and therefore cannot be switched off.
        seasonal, climatology_features = self._s0_features(
            seasonal_features,
            training_climatology,
            shape=(batch, steps, stations),
            reference=values,
        )
        branch_s0 = self.s0_projection(
            torch.cat((seasonal, climatology_features, station_context), dim=-1)
        )

        # A: same-station target values with explicit two-sided temporal context.
        target_available = available[..., self.target_index]
        target_values = filled[..., self.target_index]
        gaps = self._time_gaps(time_gap, target_available, values)
        target_variable_embedding = self.variable_embedding.weight[self.target_index]
        target_variable_context = target_variable_embedding.view(1, 1, 1, -1).expand(
            batch, steps, stations, -1
        )
        temporal_input = torch.cat(
            (
                target_values.unsqueeze(-1),
                target_available.to(values.dtype).unsqueeze(-1),
                gaps,
                station_context,
                target_variable_context,
            ),
            dim=-1,
        )
        temporal_flat = temporal_input.permute(0, 2, 1, 3).reshape(
            batch * stations, steps, -1
        )
        temporal_encoded, _ = self.temporal_encoder(temporal_flat)
        branch_a = (
            self.temporal_projection(temporal_encoded)
            .reshape(batch, stations, steps, self.config.hidden_size)
            .permute(0, 2, 1, 3)
        )
        availability_a = (
            target_available.to(values.dtype)
            .mean(dim=1, keepdim=True)
            .expand(-1, steps, -1)
        )

        # B: same-station hydrological variables F/L.
        branch_b, availability_b = self._encode_variables(
            filled, available, self.hydro_indices, self.hydro_value_encoder
        )

        # C: masked attention over other stations' T/F/L summaries (not a GNN).
        cross_source, cross_source_availability = self._encode_variables(
            filled, available, self.cross_indices, self.cross_value_encoder
        )
        cross_source = self.cross_station_projection(
            torch.cat((cross_source, station_context), dim=-1)
        )
        keys = self.cross_key(cross_source)
        queries = self.cross_query(station_embedding)
        logits = torch.einsum("btsh,nh->btns", keys, queries) / math.sqrt(
            self.config.hidden_size
        )
        donor_available = cross_source_availability > 0
        donor_valid = (
            donor_available[:, :, None, :]
            .expand(batch, steps, stations, stations)
            .clone()
        )
        donor_valid &= ~torch.eye(
            stations, dtype=torch.bool, device=values.device
        ).view(1, 1, stations, stations)
        cross_attention = _safe_masked_softmax(logits, donor_valid)
        branch_c = torch.einsum("btns,btsh->btnh", cross_attention, cross_source)
        availability_c = donor_valid.any(dim=-1).to(values.dtype)

        # D: same-station meteorology only. Calendar and climatology belong to
        # permanent S0 and cannot make this source available.
        if self.met_indices:
            met_summary, met_availability = self._encode_variables(
                filled, available, self.met_indices, self.met_value_encoder
            )
        else:
            met_summary = torch.zeros_like(branch_a)
            met_availability = torch.zeros(
                (batch, steps, stations), device=values.device, dtype=values.dtype
            )
        branch_d = self.met_projection(met_summary)
        availability_d = met_availability

        branches = torch.stack((branch_a, branch_b, branch_c, branch_d), dim=-2)
        branch_availability = torch.stack(
            (availability_a, availability_b, availability_c, availability_d), dim=-1
        )
        enabled = self._group_enabled(
            enabled_groups, group_mask, (batch, steps, stations), values.device
        )
        valid_branches = enabled & (branch_availability > 0)
        masked_branches = branches * enabled.unsqueeze(-1).to(values.dtype)
        masked_availability = branch_availability * enabled.to(values.dtype)
        gate_input = torch.cat(
            (
                masked_branches.flatten(start_dim=-2),
                masked_availability,
                branch_s0,
                station_context,
            ),
            dim=-1,
        )
        gate_logits = self.gate(gate_input)
        gate_weights = _safe_masked_softmax(gate_logits, valid_branches)
        optional_fusion = (masked_branches * gate_weights.unsqueeze(-1)).sum(dim=-2)
        fused = branch_s0 + optional_fusion

        raw_quantiles = self.quantile_head(torch.cat((fused, station_context), dim=-1))
        median = raw_quantiles[..., 0]
        median_spacing = (
            4.0 * torch.finfo(raw_quantiles.dtype).eps * (median.detach().abs() + 1.0)
        )
        lower_inner = F.softplus(raw_quantiles[..., 1]) + median_spacing
        upper_inner = F.softplus(raw_quantiles[..., 3]) + median_spacing
        q25 = median - lower_inner
        q75 = median + upper_inner
        lower_outer = F.softplus(raw_quantiles[..., 2]) + (
            4.0 * torch.finfo(raw_quantiles.dtype).eps * (q25.detach().abs() + 1.0)
        )
        upper_outer = F.softplus(raw_quantiles[..., 4]) + (
            4.0 * torch.finfo(raw_quantiles.dtype).eps * (q75.detach().abs() + 1.0)
        )
        q05 = q25 - lower_outer
        q95 = q75 + upper_outer
        quantiles = torch.stack((q05, q25, median, q75, q95), dim=-1)
        return {
            "quantiles": quantiles,
            "q05": quantiles[..., 0],
            "q25": quantiles[..., 1],
            "q50": quantiles[..., 2],
            "q75": quantiles[..., 3],
            "q95": quantiles[..., 4],
            "gate_weights": gate_weights,
            "branch_availability": branch_availability,
            "source_available_S0": torch.ones(
                (batch, steps, stations),
                dtype=torch.bool,
                device=values.device,
            ),
            "source_available_A": branch_availability[..., 0] > 0,
            "source_available_B": branch_availability[..., 1] > 0,
            "source_available_C": branch_availability[..., 2] > 0,
            "source_available_D": branch_availability[..., 3] > 0,
            "gate_A": gate_weights[..., 0],
            "gate_B": gate_weights[..., 1],
            "gate_C": gate_weights[..., 2],
            "gate_D": gate_weights[..., 3],
            "effective_available_mask": available,
            "cross_station_attention": cross_attention,
        }


def masked_imputation_loss(
    output: Mapping[str, Tensor] | Tensor,
    target: Tensor,
    artificial_target_mask: Tensor,
    *,
    quality_mask: Tensor | None = None,
    observed_target: Tensor | None = None,
    observed_mask: Tensor | None = None,
    huber_weight: float = 1.0,
    pinball_weight: float = 1.0,
    consistency_weight: float = 0.0,
    huber_delta: float = 1.0,
) -> dict[str, Tensor]:
    """Masked-only Huber + pinball loss with optional observed consistency."""

    quantiles = output["quantiles"] if isinstance(output, Mapping) else output
    if quantiles.shape[:-1] != target.shape or quantiles.shape[-1] != 5:
        raise ValueError("quantiles must have shape target.shape + (5,)")
    eligible = artificial_target_mask.bool() & torch.isfinite(target)
    if quality_mask is not None:
        eligible &= quality_mask.bool()
    truth = torch.nan_to_num(target)

    huber_values = F.huber_loss(
        quantiles[..., 2], truth, delta=huber_delta, reduction="none"
    )
    count = eligible.sum()
    denominator = count.clamp_min(1).to(quantiles.dtype)
    huber = (huber_values * eligible.to(huber_values.dtype)).sum() / denominator

    levels = quantiles.new_tensor(MissingAwareMultisourceImputer.quantile_levels)
    error = truth.unsqueeze(-1) - quantiles
    pinball_values = torch.maximum(levels * error, (levels - 1.0) * error)
    pinball = (
        pinball_values * eligible.unsqueeze(-1).to(pinball_values.dtype)
    ).sum() / (denominator * float(len(MissingAwareMultisourceImputer.quantile_levels)))

    consistency = quantiles.sum() * 0.0
    if consistency_weight > 0:
        if observed_target is None or observed_mask is None:
            raise ValueError(
                "observed_target and observed_mask are required for consistency loss"
            )
        consistent = observed_mask.bool() & torch.isfinite(observed_target)
        consistent_count = consistent.sum().clamp_min(1).to(quantiles.dtype)
        consistency_values = F.smooth_l1_loss(
            quantiles[..., 2], torch.nan_to_num(observed_target), reduction="none"
        )
        consistency = (
            consistency_values * consistent.to(quantiles.dtype)
        ).sum() / consistent_count

    total = (
        huber_weight * huber
        + pinball_weight * pinball
        + consistency_weight * consistency
    )
    return {
        "loss": total,
        "huber": huber,
        "pinball": pinball,
        "consistency": consistency,
        "masked_count": count,
    }


# Short aliases keep experiment scripts readable without introducing wrappers.
ProposedImputer = MissingAwareMultisourceImputer
ProposedModel = MissingAwareMultisourceImputer


__all__ = [
    "INFORMATION_GROUPS",
    "MAIN_ARCHITECTURE_VERSION",
    "MAIN_METEOROLOGY_VARIABLES",
    "MAIN_VARIABLE_NAMES",
    "MissingAwareMultisourceImputer",
    "ProposedImputer",
    "ProposedModel",
    "ProposedModelConfig",
    "RETIRED_SUNSHINE_DH_ARCHITECTURE_VERSION",
    "all_information_group_combinations",
    "compute_bidirectional_time_gaps",
    "information_group_mask",
    "masked_imputation_loss",
    "require_main_rs_architecture",
]
