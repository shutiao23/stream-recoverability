"""Custody-preserving caches for bounded T2 baseline execution.

Only immutable source panels and deterministic climatology outputs are cached.
Model fits whose training inputs differ by placement or information condition
remain item-scoped.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from stream_recoverability.experiments.t2_recovery_benchmark import (
    OpenNetwork,
    WorkItem,
    _cell_contract,
    execute_item,
    read_panel,
)

CACHE_CONTRACT_VERSION = "t2_network_panel_climatology_cache_v1"


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

    def stats(self) -> Mapping[str, int | str]:
        return {
            "cache_contract_version": CACHE_CONTRACT_VERSION,
            "panels_cached": len(self._panels),
            "panel_cache_hits": self.panel_cache_hits,
            "panel_cache_misses_custody_reads": self.panel_cache_misses,
            "climatology_entries": len(self._climatology),
            "climatology_cache_hits": self.climatology_cache_hits,
            "climatology_cache_misses_fits": self.climatology_cache_misses,
        }


__all__ = ["CACHE_CONTRACT_VERSION", "NetworkExecutionCache"]
