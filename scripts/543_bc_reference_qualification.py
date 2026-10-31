#!/usr/bin/env python3
"""Qualify published BC daily-mean references without assuming 24 hours/day.

Roster and the exploratory qualification plan were recorded before downloading
this time-series file. The original authors accepted days with >=20 hourly
values and used water-air checks; the individual hour counts are unavailable.
"""
import json
from datetime import datetime, timezone
import requests
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/wrr_review_response_20261027/external_bc_air2stream'

def qualify(roster, frame):
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame.date, errors='coerce')
    if frame.date.isna().any():
        raise ValueError('Unparseable published observation dates')
    frame['tw_obs'] = pd.to_numeric(frame.tw_obs, errors='coerce')
    frame.loc[~np.isfinite(frame.tw_obs), 'tw_obs'] = np.nan
    # Contradictory or duplicate records are rejected for the date, including
    # identical duplicates: this avoids silently treating an unknown overlap as data.
    frame['duplicate'] = frame.duplicated(['station_number', 'date'], keep=False)
    frame.loc[frame.duplicate, 'tw_obs'] = np.nan
    unknown = set(frame.station_number) - set(roster.station_number)
    if unknown:
        raise ValueError(f'Data include stations outside fixed roster: {unknown}')
    years, stations = [], []
    for site in roster.itertuples(index=False):
        block = frame.loc[frame.station_number.eq(site.station_number)]
        valid = block.set_index('date').tw_obs
        # Duplicate index values are excluded, then at most one row/date remains.
        valid = valid.loc[~valid.index.duplicated(keep=False)]
        for year in sorted(block.date.dt.year.unique()):
            idx = pd.date_range(f'{year}-01-01', f'{year}-12-31', freq='D')
            v = valid.reindex(idx)
            years.append(dict(station_number=site.station_number, year=int(year), expected_days=len(idx),
                              usable_daily_values=int(v.notna().sum()), complete_published_daily=bool(v.notna().all())))
        site_years = [y for y in years if y['station_number'] == site.station_number and y['complete_published_daily']]
        stations.append(dict(station_number=site.station_number, station_name=site.station_name,
                             latitude=site.latitude, longitude=site.longitude, regulation=site.status,
                             complete_published_daily_years=len(site_years),
                             qualified_exploratory_20h_reference=len(site_years)>=4,
                             strict_24h_reference_qualified=False,
                             strict_qualification_reason='hourly counts and per-day flags not supplied in this published derivative',
                             n_rows=len(block), duplicate_rows=int(block.duplicate.sum())))
    return pd.DataFrame(stations), pd.DataFrame(years), frame

def main():
    if not (OUT/'plan.json').exists():
        raise RuntimeError('The fixed local plan must precede time-series acquisition')
    source_file = OUT/'ts_all_58.csv'
    if not source_file.exists():
        url = 'https://zenodo.org/api/records/14502248/files/ts_all_58.csv/content'
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        source_file.write_bytes(response.content)
        (OUT/'request.json').write_text(json.dumps(dict(url=url, retrieved_utc=datetime.now(timezone.utc).isoformat(),
            bytes=len(response.content), status=response.status_code), indent=2)+'\n')
    roster = pd.read_csv(OUT/'roster.csv', dtype={'station_number':str})
    frame = pd.read_csv(OUT/'ts_all_58.csv', dtype={'station_number':str})
    station, years, frame = qualify(roster, frame)
    station.to_csv(OUT/'qualification.csv', index=False)
    years.to_csv(OUT/'qualification_years.csv', index=False)
    (OUT/'daily').mkdir(exist_ok=True)
    for code, block in frame.groupby('station_number'):
        block = block.loc[~block.duplicate].sort_values('date')
        block[['date','tw_obs']].rename(columns={'tw_obs':'temperature_c'}).to_parquet(OUT/'daily'/f'{code}.parquet',index=False)
    status = dict(n_roster=len(roster), n_exploratory_eligible=int(station.qualified_exploratory_20h_reference.sum()),
                  n_strict_24h_eligible=0, n_duplicate_rows=int(station.duplicate_rows.sum()),
                  reconstruction_accuracy_evaluated=False,
                  strict_limitation='This derivative does not identify 24 valid hourly measurements or day-specific raw QC flags; cannot satisfy strict full-day reference',
                  previous_contact='no WSC identifiers found in initial searched local metadata and scripts; geographic network dependence remains to be checked',
                  time_zone='not established for the published derivative',
                  selection='unregistered, all published stations; original authors selected >=5 total years, not a random population',
                  citation='https://doi.org/10.5281/zenodo.14502248')
    (OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(station.to_string(index=False))
    print(json.dumps(status,indent=2))

if __name__ == '__main__':
    main()
