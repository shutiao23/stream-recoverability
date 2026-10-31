#!/usr/bin/env python3
"""Identity search and approximate nearest opened USGS observations to BC sites.

No river-network independence or zero prior contact is proved by this screen.
BC coordinates are rounded to 0.01 degree; distances are approximate.
"""
import json
import subprocess
import tempfile
from pathlib import Path
import pandas as pd
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/wrr_review_response_20261027/external_bc_air2stream'


def main():
    roster = pd.read_csv(OUT/'roster.csv', dtype={'station_number':str})
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf8') as f:
        f.write('\n'.join(roster.station_number)+'\n'); f.flush()
        cmd = ['rg','-l','-F','-f',f.name,'scripts','docs','paper','results','data',
               '--glob','*.py','--glob','*.csv','--glob','*.json','--glob','*.md','--glob','*.tex',
               '--glob','!results/wrr_review_response_20261027/external_bc_air2stream/**']
        search = subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    if search.returncode not in (0,1):
        raise RuntimeError(search.stderr)
    source = pd.read_csv(ROOT/'results/wrr_target_recovery_20261021/e1_archive/usgs_site_metadata.csv',dtype={'site_no':str})
    source = source.rename(columns={'site_no':'station_id','station_nm':'name','dec_lat_va':'latitude','dec_long_va':'longitude'})
    folder=ROOT/'results/wrr_review_completion_20261024/national_meaning/site_results'
    processed=set()
    for path in folder.glob('*.json'):
        try:
            if json.loads(path.read_text()).get('status') == 'processed': processed.add(path.stem)
        except (OSError,json.JSONDecodeError):
            continue
    national=pd.read_csv(ROOT/'results/wrr_review_completion_20261024/national_meaning/national_roster.csv',dtype={'station_id':str})
    national=national.loc[national.station_id.isin(processed)].rename(columns={'monitoring_location_name':'name'})
    geod=Geod(ellps='WGS84'); rows=[]
    for r in roster.itertuples(index=False):
        for origin,frame in [('source_USGS',source),('processed_national_USGS',national)]:
            frame=frame.dropna(subset=['latitude','longitude'])
            distances=[geod.inv(r.longitude,r.latitude,float(x.longitude),float(x.latitude))[2]/1000 for x in frame.itertuples()]
            i=min(range(len(distances)),key=distances.__getitem__); match=frame.iloc[i]
            rows.append(dict(station_number=r.station_number, inventory=origin, nearest_usgs_station=match.station_id,
                             nearest_usgs_name=match['name'], distance_km_approx=round(distances[i],1)))
    pd.DataFrame(rows).to_csv(OUT/'nearest_prior_usgs.csv',index=False)
    audit={'identifier_matches':search.stdout.splitlines(),'search_roots':['scripts','docs','paper','results','data'],
           'suffixes':['.py','.csv','.json','.md','.tex'],
           'search_excludes':'new BC intake itself and unsearched binary/compressed/other formats',
           'distance_scope':'nearest USGS source metadata and successfully processed national-panel site metadata; approximate, not river-network membership',
           'caveat':'Different station IDs and distance do not establish independent river networks, climate, or a repository-wide absence of earlier contact.'}
    (OUT/'prior_contact_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))

if __name__ == '__main__': main()
