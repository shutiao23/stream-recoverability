"""The NVE probe holds out whole previously observed basin prefixes."""
import importlib.util
from pathlib import Path
import pandas as pd

spec=importlib.util.spec_from_file_location('nve_probe',Path(__file__).resolve().parents[1]/'scripts/550_nve_chart_reference_probe.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_previously_opened_basin_excluded_and_selection_deterministic():
    f=pd.DataFrame({'stasjonnr':['2.200.0','3.10.0','3.11.0','10.1.0'],
                    'antallkompletteaar':[20,5,9,6]})
    selected=m.select_unseen_basins(f,{'2.1.0'})
    assert selected.stasjonnr.tolist()==['3.11.0','10.1.0']
