#!/usr/bin/env python3
"""Read only the public CAMELSH ZIP central directory, without observations."""
import argparse
from datetime import datetime,timezone
import io
import json
from pathlib import Path
import re
import zipfile
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_camelsh_hourly'
RECORD='https://zenodo.org/api/records/21324088';NAME='StreamTemperature.zip'

class RemoteIndex(io.RawIOBase):
    """Read a bounded amount of metadata from a server supporting exact ranges."""
    def __init__(self,url,size,etag=None,max_bytes=12*1024*1024):
        self.url=url;self.size=size;self.pos=0;self.etag=etag;self.max_bytes=max_bytes;self.total=0;self.calls=0
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=io.SEEK_SET):
        pos=offset if whence==io.SEEK_SET else (self.pos+offset if whence==io.SEEK_CUR else self.size+offset)
        if pos<0:raise ValueError('Negative remote offset')
        self.pos=pos;return pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        n=min(n,self.size-self.pos)
        if n<=0:return b''
        if self.total+n>self.max_bytes:raise ValueError('Remote metadata read exceeds fixed budget')
        start=self.pos;end=start+n-1
        r=requests.get(self.url,headers={'Range':f'bytes={start}-{end}','User-Agent':'stream-temperature reference qualification/1.0'},timeout=35)
        if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {start}-{end}/{self.size}' or len(r.content)!=n:
            raise RuntimeError('Server did not honor exact byte-range request')
        if self.etag and r.headers.get('ETag') and r.headers['ETag']!=self.etag:raise RuntimeError('Archive changed between requests')
        self.pos+=n;self.total+=n;self.calls+=1;return r.content

def freeze():
    OUT.mkdir(parents=True,exist_ok=True);dest=OUT/'plan.json'
    if dest.exists():raise FileExistsError('Preserve existing CAMELSH plan')
    response=requests.get(RECORD,timeout=20,headers={'User-Agent':'stream-temperature reference qualification/1.0'});response.raise_for_status()
    data=response.json();files=[x for x in data['files'] if x['key']==NAME]
    if len(files)!=1 or data['metadata'].get('license',{}).get('id')!='cc-by-4.0':raise ValueError('Dataset or license metadata differs')
    f=files[0];source=OUT/'record_metadata.json';source.write_bytes(response.content)
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'exploratory metadata-only plan, after prior reference searches; before inspecting archive member names or target water values',
          'purpose':'Identify whether the published 1,297 hourly-gauge archive contains potentially uncontacted USGS stations; archive membership is a candidate list, not validation.',
          'record':'https://doi.org/10.5281/zenodo.21324088','license':'CC BY 4.0 as declared in version-specific record',
          'archive_url':f['links']['self'],'archive_size':int(f['size']),'archive_index_only':'Retrieve ZIP central-directory byte ranges, recording names and metadata; no member contents, temperature values or model errors are accessed.',
          'selection':'First classify member IDs against named prior source, evaluation, donor and metadata-contact inventories. Any later time-coverage, quality, river-network and model-error examinations require separate recorded plans.',
          'limits':'Version metadata and listed files may be revised. A partial read does not open every listed file. USGS gauge identifiers, complete years, quality flags, timezone consistency, independence and rights for any derived values must be established separately.'}
    dest.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded CAMELSH metadata-only search plan')

def index():
    p=json.loads((OUT/'plan.json').read_text());source=OUT/'record_metadata.json'
    remote=RemoteIndex(p['archive_url'],p['archive_size']);rows=[]
    with zipfile.ZipFile(remote) as z:
        for x in z.infolist():
            if x.is_dir():continue
            basename=Path(x.filename).name
            match=re.fullmatch(r'(\d{8,15})\.(?:nc|nc4|csv)',basename,re.IGNORECASE)
            rows.append({'member':x.filename,'compressed_bytes':x.compress_size,'uncompressed_bytes':x.file_size,
                         'crc32':f'{x.CRC:08x}','station_id':match.group(1) if match else ''})
    frame=pd.DataFrame(rows);path=OUT/'archive_members.csv';frame.to_csv(path,index=False)
    status={'status':'index_read','files':len(frame),'recognizable_station_files':int(frame.station_id.ne('').sum()),
            'distinct_recognizable_station_ids':int(frame.loc[frame.station_id.ne(''),'station_id'].nunique()),
            'remote_requests':remote.calls,'remote_bytes':remote.total,'member_contents_opened':False,'temperature_values_opened':False,'model_errors_opened':False,
            'limits':p['limits']}
    (OUT/'index_status.json').write_text(json.dumps(status,indent=2)+'\n');print(json.dumps(status,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','index']);a=parser.parse_args();freeze() if a.action=='freeze' else index()
