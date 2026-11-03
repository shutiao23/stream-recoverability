"""Pytest configuration.

Some historical test modules exercise intake scripts that import optional
third-party dependencies (bs4, openpyxl, pyproj, shapely) or read local-only
data files that are not part of the public repository. Those modules run in the
full development environment but cannot be collected on a clean checkout, so
they are ignored at collection time when the dependency or data file is absent.
The EMS-relevant suite (paper arithmetic, packaging, acceptance guards, the
gapbench library and the benchmark layer) is unaffected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

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
