"""Pytest configuration.

Two categories of historical test modules cannot run on a clean public
checkout of this repository:

* modules whose intake scripts import optional third-party dependencies
  (bs4, openpyxl, pyproj, shapely) or the Python 3.11 ``tomllib`` module;
* research-compendium modules that read private, untracked data
  (``data_versions/``, ``data/external/``, ``data/cache/``,
  ``metadata/validation_anchors.csv``, frozen ``results/`` artifacts) or call
  locally installed binaries (``pdftotext``) and heavy optional libraries
  (``lightgbm``, ``numba``) that the CI constraints install does not provide.

Both categories run in the full development environment. On a clean checkout
they are ignored at collection time so that ``python -m pytest`` executes the
self-contained suite: the gapbench library, the EMS manuscript arithmetic,
packaging and acceptance guards, and all tests that depend only on tracked
files. Set ``GAPBENCH_FORCE_SKIP_PRIVATE=1`` to simulate the clean-checkout
suite locally.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil

REPO_ROOT = Path(__file__).resolve().parent

_OPTIONAL_DEPS = {
    "bs4": ["tests/test_njdep_metadata_preflight.py"],
    "openpyxl": [
        "tests/test_nova_scotia_label_completeness.py",
        "tests/test_nova_scotia_portal_comparison.py",
    ],
    "shapely": ["tests/test_wrr_au_catchment_scope_extension.py"],
    "pyproj": [
        "tests/test_wrr_au_dependence_audit.py",
        "tests/test_wrr_new_reference_recruitment.py",
        "tests/test_wrr_usgs_intake_audit.py",
        "tests/test_wrr_usgs_metadata_extension.py",
        "tests/test_wrr_usgs_network_intake.py",
        "tests/test_wrr_usgs_network_resume.py",
        "tests/test_wrr_usgs_prior_cache_audit.py",
        "tests/test_wrr_usgs_reference_preflight.py",
    ],
}

_LOCAL_DATA_MODULES = {
    "tests/test_formal_results_aggregation.py": "data_versions/published_v1/version_manifest.json",
}

# Research-compendium modules that require the private environment. The list is
# derived from the modules that failed on the clean CI checkout (run 41613829752).
_RESEARCH_MODULES = [
    "tests/test_anchor_independence.py",
    "tests/test_anchor_integration.py",
    "tests/test_confirmatory_data.py",
    "tests/test_data_core.py",
    "tests/test_design_contracts.py",
    "tests/test_donor_falsification.py",
    "tests/test_event_catalog.py",
    "tests/test_event_matching_audit.py",
    "tests/test_experiment_runner.py",
    "tests/test_external_confirmation.py",
    "tests/test_formal_authorization.py",
    "tests/test_formal_registry_builder.py",
    "tests/test_frozen_analysis_pipeline.py",
    "tests/test_hubeau_reunion_reference.py",
    "tests/test_p0_protocol.py",
    "tests/test_projected_risk_sensitivity.py",
    "tests/test_protocol_documentation.py",
    "tests/test_public_archive_candidate.py",
    "tests/test_reference_runner.py",
    "tests/test_retrained_information.py",
    "tests/test_science_experiments.py",
    "tests/test_t2_information_corpus_acquisition_v2.py",
    "tests/test_t6_seplains_bfi.py",
    "tests/test_usgs_public_snapshot_manifest.py",
    "tests/test_validation_finalization.py",
    "tests/test_validation_funnel.py",
    "tests/test_wrr_adversarial_revision.py",
    "tests/test_wrr_figure_qa.py",
    "tests/test_wrr_review_completion.py",
    "tests/test_wrr_review_independent.py",
    "tests/test_wrr_review_windows.py",
    "tests/test_wrr_scientific_revision.py",
    "tests/test_wrr_submission.py",
    "tests/test_wrr_target_recovery.py",
]

_RESEARCH_PROBE_FILES = [
    "metadata/validation_anchors.csv",
    "data_versions/published_v1/version_manifest.json",
    "data_versions/global_network_corpus_v1",
    "data/external/wrr_usgs_partial_daily_20261027",
    "data/cache/regulation_panel_v1",
    "results/wrr_review_response_20261027/whole_archive/trends.csv",
]
_RESEARCH_PROBE_MODULES = ["lightgbm", "numba"]
_RESEARCH_PROBE_BINARIES = ["pdftotext"]


def _research_environment_available() -> bool:
    if os.environ.get("GAPBENCH_FORCE_SKIP_PRIVATE") == "1":
        return False
    for relative in _RESEARCH_PROBE_FILES:
        if not (REPO_ROOT / relative).exists():
            return False
    for module in _RESEARCH_PROBE_MODULES:
        if importlib.util.find_spec(module) is None:
            return False
    for binary in _RESEARCH_PROBE_BINARIES:
        if shutil.which(binary) is None:
            return False
    return True


collect_ignore = []
for module in _OPTIONAL_DEPS:
    if importlib.util.find_spec(module) is None:
        collect_ignore.extend(_OPTIONAL_DEPS[module])
for module, relative in _LOCAL_DATA_MODULES.items():
    if not (REPO_ROOT / relative).is_file():
        collect_ignore.append(module)
try:
    import tomllib  # noqa: F401
except ModuleNotFoundError:  # Python 3.10: the test module imports tomllib directly
    collect_ignore.append("tests/test_reference_baselines.py")
if not _research_environment_available():
    collect_ignore.extend(_RESEARCH_MODULES)
