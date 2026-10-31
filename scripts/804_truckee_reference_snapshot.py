#!/usr/bin/env python3
"""Stage attributable public Truckee reference and POWER input, not models."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027'
SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027'

def copy(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():raise FileExistsError('Preserve existing open snapshot: '+str(dest))
    if not dest.exists():shutil.copyfile(src,dest)

def main():
    finite=json.loads((OUT/'finite_reference_status.json').read_text());audit=json.loads((OUT/'finite_reference_independent_audit.json').read_text())
    forcing=json.loads((OUT/'exploratory_forcing_status.json').read_text());acq=json.loads((PRIVATE/'acquisition.json').read_text())
    if finite['status']!='finite_published_reference_screened' or audit['status']!='passed' or forcing['status']!='forcing_complete' or len(acq)!=12:
        raise ValueError('Reference or forcing checks incomplete')
    SNAP.mkdir(parents=True,exist_ok=True);manifest=[]
    for item in acq:
        src=PRIVATE/'raw'/f"{item['station_code']}.csv.gz";dest=SNAP/'raw'/src.name;copy(src,dest)
        manifest.append({'file':str(dest.relative_to(SNAP)),'uncompressed_source_bytes':item['source_bytes'],'station_code':item['station_code']})
    ancillary=[(OUT/'metadata.xml','metadata.xml',),
        (OUT/'station_metadata_01.csv','station_metadata_01.csv',),
        (OUT/'station_metadata_02.csv','station_metadata_02.csv',),
        (OUT/'station_metadata_03.csv','station_metadata_03.csv',),
        (PRIVATE/'timestamp_station_years.csv','timestamp_station_years.csv',),
        (PRIVATE/'finite_reference_years.csv','finite_reference_years.csv',),
        (PRIVATE/'finite_reported_daily.parquet','finite_reported_daily.parquet',),
        (PRIVATE/'exploratory_power_response.json','exploratory_power_response.json',),
        (PRIVATE/'exploratory_air_forcing.parquet','exploratory_air_forcing.parquet',)]
    for source,name in ancillary:
        target=SNAP/name;copy(source,target);manifest.append({'file':name,})
    data={'created_utc':datetime.now(timezone.utc).isoformat(),'files':manifest,'provider_doi':'https://doi.org/10.6073/pasta/aefcf302d088aeacc40459091d7e990c',
          'description':'Public provider 12-station water files, metadata, project-derived daily reference and USGS-independent NASA POWER weather. No model weights, source calibration, target masks, or per-case predictions are included.',
          'license_scope':'EDI metadata states CC0; California discovery catalog states Creative Commons Attribution without specifying a version. Source attribution is provided and the discrepancy should be reconciled before permanent publication.',
          'power_notice':'NASA POWER requests notification when data are transmitted to other researchers. This is a local candidate; no external notification or release was made.'}
    (SNAP/'manifest.json').write_text(json.dumps(data,indent=2)+'\n')
    (SNAP/'ATTRIBUTION.txt').write_text('Frantzich, J. and Davis, L. (2026). Truckee River Continuous (15 minute) Water Quality Monitoring, 1998–2025. California Department of Water Resources / Environmental Data Initiative. https://doi.org/10.6073/pasta/aefcf302d088aeacc40459091d7e990c\nEDI EML describes CC0 1.0; California catalog lists Creative Commons Attribution. Attribution is retained, with version differences to be resolved before permanent publication.\nProcessed daily means and finite-day screens were calculated by this project from the unmodified source files.\nNASA POWER T2M: NASA Langley Research Center POWER Project, Daily API v2.10.1, accessed 2026-10-27, https://power.larc.nasa.gov/. NASA requests notification upon transmission to other researchers; no notification was sent.\n')
    print('Staged public Truckee reference and weather inputs; model weights and case predictions remain local.')

if __name__=='__main__':main()
