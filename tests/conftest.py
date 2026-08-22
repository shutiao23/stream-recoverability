"""Repository-wide deterministic fixtures for evidence-contract tests."""

from __future__ import annotations

import pytest

from stream_recoverability.experiments.runner import ExperimentRunner


@pytest.fixture(autouse=True)
def _committed_test_code_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep unit tests independent of the developer's current git worktree.

    Dedicated provenance tests exercise real temporary Git repositories and
    call the unpatched gate for the formal dirty-tree failure path.
    """

    monkeypatch.setattr(
        ExperimentRunner,
        "_assert_formal_code_provenance",
        staticmethod(lambda training_profile_name, code_provenance, **_kwargs: None),
    )
