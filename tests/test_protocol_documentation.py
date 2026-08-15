from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from stream_recoverability.experiments.external_confirmation import (
    build_external_confirmation_grid,
)
from stream_recoverability.experiments.grid import (
    ExperimentGrid,
    build_experiment_grid,
)
from stream_recoverability.experiments.retrained_information import (
    build_retrained_information_grid,
)
from stream_recoverability.experiments.science import (
    build_compensation_grid,
    build_dense_science_grid,
    build_resilience_science_grid,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVENT_CATALOG = REPOSITORY_ROOT / "metadata/event_episode_catalog.csv"
COUNT_MARKER = re.compile(r"<!-- protocol-grid-counts: (?P<values>[^>]+) -->")


def _documented_counts(path: Path) -> dict[str, tuple[int, int]]:
    match = COUNT_MARKER.search(path.read_text(encoding="utf-8"))
    assert match is not None, f"missing protocol-grid-counts marker in {path}"
    result: dict[str, tuple[int, int]] = {}
    for field in match.group("values").split():
        name, raw_counts = field.split("=", maxsplit=1)
        conditions, scenarios = raw_counts.split("/", maxsplit=1)
        result[name] = (int(conditions), int(scenarios))
    return result


def _experiment_inventory(
    grid: ExperimentGrid, experiment: str
) -> tuple[int, int]:
    conditions = Counter(condition.experiment for condition in grid.conditions)
    scenarios = Counter(
        scenario.condition.experiment
        for scenario in grid.scenarios
    )
    return conditions[experiment], scenarios[experiment]


def _grid_size(grid: ExperimentGrid) -> tuple[int, int]:
    return len(grid.conditions), len(grid.scenarios)


def test_readme_and_methods_grid_counts_follow_executable_builders() -> None:
    smoke = build_experiment_grid(suite="smoke")
    core = build_experiment_grid(suite="core")
    full_without_catalog = build_experiment_grid(suite="full")
    full = build_experiment_grid(
        suite="full", event_catalog_path=EVENT_CATALOG
    )
    computed = {
        "smoke": _grid_size(smoke),
        "core": _grid_size(core),
        "full_catalog": _grid_size(full),
        "full_without_catalog": _grid_size(full_without_catalog),
        "m6a": _experiment_inventory(full, "M6a"),
        "m6b": _experiment_inventory(full, "M6b"),
        "m7a": _experiment_inventory(full, "M7a"),
        "m7b": _experiment_inventory(full, "M7b"),
        "dense": _grid_size(build_dense_science_grid()),
        "compensation": _grid_size(build_compensation_grid()),
        "resilience": _grid_size(build_resilience_science_grid()),
        "retrained": _grid_size(build_retrained_information_grid()),
        "external": _grid_size(
            build_external_confirmation_grid(
                training_seeds=(11, 22, 33, 44, 55)
            )
        ),
    }

    readme = _documented_counts(REPOSITORY_ROOT / "README.md")
    methods = _documented_counts(REPOSITORY_ROOT / "paper/methods.md")
    assert readme == computed
    assert methods == computed
