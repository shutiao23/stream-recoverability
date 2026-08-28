import importlib.util
from pathlib import Path

import yaml


def test_v11_script_imports_without_running() -> None:
    path = Path(__file__).parents[1] / "scripts/106_run_development_v11.py"
    spec = importlib.util.spec_from_file_location("development_v11_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_v11_primary_is_literal_complete_operator_risk() -> None:
    root = Path(__file__).parents[1]
    config = yaml.safe_load(
        (root / "configs/development_v11.yaml").read_text(encoding="utf-8")
    )
    assert config["operator"]["primary_risk"] == "complete_operator_risk"
    assert config["operator"]["regime_weighted_memory"] == "diagnostic_only"
