#!/usr/bin/env python3
"""Recheck USGS response IDs and locally recorded non-USGS donor metadata."""
import csv
import json
from pathlib import Path
import pandas as pd
import wrr_tr_common as T

ROOT=T.ROOT;OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance/usgs_metadata'

def main():
    plan=json.loads((OUT/'donor_usgs_metadata_plan.json').read_text());status=json.loads((OUT/'donor_usgs_metadata_status.json').read_text())
    if status['status']!='completed':raise ValueError('Incomplete frozen metadata lookup')
    roster=pd.read_csv(PRIVATE/'unresolved_columns.csv',dtype=str);expected=set(roster.station_id)
    returned=[]
    for item in status['batches']:
        path=PRIVATE/f"batch_{item['batch']:02d}.rdb"
        if item['status']!='completed':raise ValueError('USGS response changed')
        with path.open(encoding='utf-8',newline='') as f:
            lines=(line for line in f if not line.startswith('#') and line.strip())
            reader=csv.DictReader(lines,delimiter='\t');next(reader)
            for row in reader:
                if row['agency_cd']!='USGS':raise ValueError('Unexpected agency')
                returned.append(row['site_no'])
    if len(returned)!=len(set(returned)) or set(returned)!=expected or len(roster)!=73 or len(expected)!=69:
        raise ValueError('USGS metadata responses do not cover the frozen identifiers')
    if set(json.loads((PRIVATE/'returned_ids.json').read_text()))!=set(returned):raise ValueError('USGS parsers disagree')
    station=pd.read_parquet(T.E1/'station_years.parquet',columns=['network_id','provider','station_id'])
    coverage=pd.read_csv(T.COVERAGE,dtype=str,usecols=['network_id','provider','station_id'])
    def keys(df):return set(zip(df.network_id.astype(str),df.provider.astype(str),df.station_id.astype(str)))
    known=keys(station)|keys(coverage);usgs=set(pd.read_csv(T.E1/'usgs_site_metadata.csv',dtype={'site_no':str}).site_no.astype(str))
    jobs=pd.DataFrame(T.load_script('extra_donor_source_jobs',ROOT/'scripts/431_tr_cases.py').jobs_for('source'))
    jobs=jobs[jobs.provider.eq('gkd_bayern')];matched=0;extra=0;qc_hashes={}
    for path,g in jobs.groupby('input_path',sort=True):
        if g.network_id.nunique()!=1:raise ValueError('Ambiguous panel network')
        network=str(g.network_id.iloc[0])
        with open(path,encoding='utf-8-sig',newline='') as f:header=next(csv.reader(f))
        unknown=[x for x in header[1:] if (network,'gkd_bayern',x) not in known]
        if not unknown:continue
        extra+=len(unknown);qc=Path(path).parent/'network_qc.csv'
        if not qc.is_file():continue
        table=pd.read_csv(qc,dtype=str);
        for name in unknown:
            row=table[table.site_id.eq(name)&table.network_id.eq(network)&table.provider.eq('gkd_bayern')]
            if len(row)==1:matched+=1
    if extra!=1 or matched!=1:raise ValueError('Additional local GKD metadata needs reassessment')
    panel_counts=pd.read_csv(OUT/'donor_provenance_panels.csv').set_index('provider')
    if int(panel_counts.loc['gkd_bayern','outside_all_local_catalogs'])!=extra:raise ValueError('GKD scope differs')
    report={'status':'passed_metadata_identity_checks','usgs_unmatched_local_panel_columns':len(roster),
            'usgs_unique_ids_matched_to_official_response':len(expected),'gkd_extra_panel_columns':extra,
            'gkd_ids_matched_to_project_network_qc':matched,'usgs_source':'https://waterservices.usgs.gov/nwis/site/',
            'interpretation':'All 74 panel-column occurrences absent from the first three local catalogs have a matching identifier in an additional source: 73 in USGS site metadata and one in a project-generated GKD network-QC table. USGS metadata is authoritative for the existence of the site identifier; the GKD QC row is a local project record, not an independent provider confirmation. Neither proves that the cached temperatures came from those records, that every preprocessing input is identified, or that data or model derivatives can be redistributed.',
            'audit':'Separate Python CSV parser verifies the two saved USGS responses, compares the complete frozen ID roster, and checks the provider/network/site fields in the local QC table; no model or temperature values are retrieved.'}
    (OUT/'donor_metadata_independent_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
