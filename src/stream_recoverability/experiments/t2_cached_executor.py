"""Custody-preserving caches for bounded T2 baseline execution.

The published v3 panel/climatology cache remains unchanged.  V4 adds an exact
training-identity fit cache; every v4 gap prediction and score stays item-scoped.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    FitCacheKey,
    OpenNetwork,
    WorkItem,
    _cell_contract,
    execute_item,
    read_panel,
)

CACHE_CONTRACT_VERSION = "t2_network_panel_climatology_cache_v1"
FIT_CACHE_CONTRACT_VERSION = "t2_strict_training_fit_cache_v2"


class NetworkExecutionCache:
    """Chunk-scoped cache with one custody-checked read per used network."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._panels: dict[tuple[str, str, str], pd.DataFrame] = {}
        self._climatology: dict[
            tuple[str, str, int, int], tuple[pd.Series, float]
        ] = {}
        self.panel_cache_hits = 0
        self.panel_cache_misses = 0
        self.climatology_cache_hits = 0
        self.climatology_cache_misses = 0

    def panel(self, network: OpenNetwork) -> pd.DataFrame:
        identity = (
            network.network_id,
            network.wide_sha256,
            network.wide_path,
        )
        cached = self._panels.get(identity)
        if cached is not None:
            self.panel_cache_hits += 1
            return cached
        # read_panel is intentionally the only cache fill path: it enforces
        # the open-role allowlist and verifies network.wide_sha256 from bytes.
        loaded = read_panel(self.repo_root, network)
        self._panels[identity] = loaded
        self.panel_cache_misses += 1
        return loaded

    def execute(self, network: OpenNetwork, item: WorkItem) -> dict[str, Any]:
        contract = _cell_contract(item)
        if not contract["supported"]:
            return execute_item(self.repo_root, network, item)
        key = (
            network.wide_sha256,
            item.target_station,
            int(item.start_index),
            int(item.start_index) + int(item.gap_length),
        )
        had_climatology = key in self._climatology
        result = execute_item(
            self.repo_root,
            network,
            item,
            panel=self.panel(network),
            climatology_cache=self._climatology,
        )
        if had_climatology:
            self.climatology_cache_hits += 1
        elif key in self._climatology:
            self.climatology_cache_misses += 1
        return result

    def stats(self) -> Mapping[str, Any]:
        return {
            "cache_contract_version": CACHE_CONTRACT_VERSION,
            "panels_cached": len(self._panels),
            "panel_cache_hits": self.panel_cache_hits,
            "panel_cache_misses_custody_reads": self.panel_cache_misses,
            "climatology_entries": len(self._climatology),
            "climatology_cache_hits": self.climatology_cache_hits,
            "climatology_cache_misses_fits": self.climatology_cache_misses,
        }


class StrictFitExecutionCache:
    """V4-only cache for exact training identities; predictions stay item-scoped."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._panels: dict[tuple[str, str, str], pd.DataFrame] = {}
        self._fits: dict[FitCacheKey, Any] = {}
        self.panel_cache_hits = 0
        self.panel_cache_misses = 0
        self.fit_cache_hits: Counter[str] = Counter()
        self.fit_cache_misses: Counter[str] = Counter()

    def panel(self, network: OpenNetwork) -> pd.DataFrame:
        identity = (network.network_id, network.wide_sha256, network.wide_path)
        cached = self._panels.get(identity)
        if cached is not None:
            self.panel_cache_hits += 1
            return cached
        loaded = read_panel(self.repo_root, network)
        self._panels[identity] = loaded
        self.panel_cache_misses += 1
        return loaded

    def resolve_fit(self, key: FitCacheKey, factory: Callable[[], Any]) -> Any:
        cached = self._fits.get(key)
        if cached is not None:
            self.fit_cache_hits[key.model] += 1
            return cached
        fitted = factory()
        self._fits[key] = fitted
        self.fit_cache_misses[key.model] += 1
        return fitted

    def execute(
        self,
        network: OpenNetwork,
        item: WorkItem,
        *,
        meteorology_lag_days: int | None = None,
    ) -> dict[str, Any]:
        contract = _cell_contract(item)
        if not contract["supported"]:
            return execute_item(self.repo_root, network, item)
        return execute_item(
            self.repo_root,
            network,
            item,
            panel=self.panel(network),
            fit_resolver=self.resolve_fit,
            meteorology_lag_days=meteorology_lag_days,
        )

    def stats(self) -> Mapping[str, Any]:
        return {
            "cache_contract_version": FIT_CACHE_CONTRACT_VERSION,
            "panels_cached": len(self._panels),
            "panel_cache_hits": self.panel_cache_hits,
            "panel_cache_misses_custody_reads": self.panel_cache_misses,
            "fit_entries": len(self._fits),
            "fit_cache_hits_by_model": dict(sorted(self.fit_cache_hits.items())),
            "fit_cache_misses_by_model": dict(sorted(self.fit_cache_misses.items())),
        }


__all__ = [
    "CACHE_CONTRACT_VERSION",
    "FIT_CACHE_CONTRACT_VERSION",
    "NetworkExecutionCache",
    "StrictFitExecutionCache",
]
