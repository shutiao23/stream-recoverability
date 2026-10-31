from pathlib import Path
import importlib
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
M = importlib.import_module("419_wrr_neon_large_river_metadata")


def test_temperature_correction_flags_do_not_become_an_independent_temperature():
    schema = pd.DataFrame({"table": ["waq_instantaneous"] * 3,
                           "fieldName": ["fDOMTempQF", "waterTemp", "sensorDepth"],
                           "units": [None, "celsius", "meter"]})
    assert M.measured_temperature_fields(schema, "waq_instantaneous") == ["waterTemp"]
    assert M.measured_temperature_fields(schema.iloc[[0, 2]], "waq_instantaneous") == []


def test_metadata_or_another_product_table_does_not_supply_water_quality_measurements():
    schema = pd.DataFrame({"table": ["sensor_positions", "TSD_30_min", "waq_instantaneous"],
                           "fieldName": ["temperatureOffset", "tsdWaterTempMean", "pH"],
                           "units": ["celsius", "celsius", None]})
    assert M.measured_temperature_fields(schema, "waq_instantaneous") == []
