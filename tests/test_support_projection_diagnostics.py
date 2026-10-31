"""Zero-width distributions must be scored against the actual reference."""
import importlib.util
from pathlib import Path
import pandas as pd

spec=importlib.util.spec_from_file_location('projection_diagnostics',Path(__file__).resolve().parents[1]/'scripts/562_support_projection_diagnostics.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_boundary_contact_does_not_imply_coverage():
    rows=[]
    for i,truth in enumerate([10.,12.]):
        row=dict(family='crossed',mode='forward',station_key=f's{i}',independence_group=f'g{i}',
                 observed_lower_bound__observed_days=10.,reference_h30=truth,D2=10.,year=2010)
        for prefix in ['D2','stochastic_cal']:
            for q in m.QS:row[f'{prefix}_q{q:02d}']=10.
        rows.append(row)
    f=m.summarize(pd.DataFrame(rows))
    assert (f.zero_width90==2).all()
    assert (f.truth_equal_bound==1).all()
    assert (f.median_at_bound_truth_equal==1).all()
    assert (f.median_at_bound_truth_above==1).all()
    assert (f.zero_width90_covered==1).all()
    assert (f.zero_width90_missed==1).all()
    assert (f.zero_width90_missed_stations==1).all()
    assert (f.zero_width90_missed_station_years==1).all()
    assert (f.zero_width90_truth_above_bound==1).all()
