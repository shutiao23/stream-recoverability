"""Field-time rounding must not silently prefer the later label at ties."""
from datetime import datetime
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/'scripts/816_truckee_wqp_field_audit.py'
spec=importlib.util.spec_from_file_location('truckee_wqp_pairing',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_nearest_quarter_tie_and_midnight():
    assert m.nearest_grid(datetime(2011,1,1,10,7,30))==datetime(2011,1,1,10,0)
    assert m.nearest_grid(datetime(2011,1,1,10,7,31))==datetime(2011,1,1,10,15)
    assert m.nearest_grid(datetime(2011,12,31,23,59))==datetime(2012,1,1,0,0)
