"""Quality checks for the exploratory French reference intake."""
import importlib.util
from pathlib import Path
import numpy as np


def load_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("reunion_reference_test", root / "scripts/540_hubeau_reunion_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_reference_day_requires_all_correct_nonconflicting_hours():
    module = load_module()
    records = [dict(date_mesure_temp="2020-01-01", heure_mesure_temp=f"{hour:02d}:00:00",
                    resultat=float(hour), symbole_unite="°C", code_qualification="1")
               for hour in range(24)]
    daily, count, conflicts = module.quality_daily(records)
    assert count == 24 and conflicts == 0
    assert daily.n_hours.iloc[0] == 24 and daily.temperature_c.iloc[0] == 11.5
    bad_quality = [dict(row) for row in records]
    bad_quality[3]["code_qualification"] = "4"
    daily, _, _ = module.quality_daily(bad_quality)
    assert np.isnan(daily.temperature_c.iloc[0]) and daily.n_hours.iloc[0] == 23
    conflict = records + [dict(records[3], resultat=33.0)]
    daily, _, n_conflicts = module.quality_daily(conflict)
    assert n_conflicts == 1 and np.isnan(daily.temperature_c.iloc[0])
