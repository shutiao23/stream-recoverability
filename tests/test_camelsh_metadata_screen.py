"""Metadata screening must not promote partial years or lose HUC leading zeroes."""
import importlib.util
from pathlib import Path
import sys

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('camelsh_metadata_screen',SCRIPTS/'787_camelsh_metadata_screen.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_full_calendar_year_envelope_and_unknown():
    assert m.full_years('2011-01-01','2014-12-31')==4
    assert m.full_years('2011-01-02','2014-12-30')==2
    assert m.full_years('2026-01-01','2020-12-31') is None
    assert m.full_years(None,'2024-12-31') is None


def test_huc8_preserves_standard_prefix_and_rejects_unknown():
    assert m.huc8('1090004')=='01090004'
    assert m.huc8('170501130101')=='17050113'
    assert m.huc8('unknown') is None
