import io, os, time, urllib.parse, urllib.request, json, random
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

PANEL = "results/v18_closure/e2_archive_deployment/incomplete_years_scored.parquet"
CACHE = "scratch/outage_probe/cache"
os.makedirs(CACHE, exist_ok=True)
UA = "stream-recoverability-outage-cause-audit/1.0 (research)"

def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return open(dest, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        t = r.read().decode("utf-8", errors="replace")
    open(dest, "w", encoding="utf-8").write(t)
    return t

def codes_for(args):
    site, y0, y1 = args
    url = "https://waterservices.usgs.gov/nwis/dv/?" + urllib.parse.urlencode({
        "format": "rdb", "sites": site, "parameterCd": "00010", "statCd": "00003",
        "startDT": f"{y0}-01-01", "endDT": f"{y1}-12-31"})
    dest = os.path.join(CACHE, f"{site}_{y0}_{y1}.rdb")
    try:
        t = fetch(url, dest)
    except Exception as e:
        return site, y0, y1, None, 0, str(e), []
    lines = [l for l in t.splitlines() if l and not l.startswith("#")]
    defs = [l for l in t.splitlines() if l.startswith("#") and l.strip().startswith(("A ", "P ", "e ", "Ice", "Eqp", "Mnt", "Dis", "Ssn", "***", "Rat", "Fld", "Dry", "Bkw"))]
    if len(lines) < 3:
        return site, y0, y1, {}, 0, "no rows", defs
    body = "\n".join([lines[0], *lines[2:]])
    try:
        df = pd.read_csv(io.StringIO(body), sep="\t", dtype=str)
    except Exception as e:
        return site, y0, y1, None, 0, f"parse:{e}", defs
    cdcol = [c for c in df.columns if c.endswith("_cd")]
    if not cdcol:
        return site, y0, y1, {}, 0, "no cd col", defs
    counts = df[cdcol[0]].fillna("<NA>").value_counts().to_dict()
    return site, y0, y1, counts, len(df), None, defs

df = pd.read_parquet(PANEL)
u = df[df.provider == "usgs"]
span = u.groupby("station_id")["year"].agg(["min", "max"])
stations = list(span.index)
random.seed(7)
sample = random.sample(stations, 24)
jobs = [(s, int(span.loc[s, "min"]), int(span.loc[s, "max"])) for s in sample]
t0 = time.time()
with ThreadPoolExecutor(max_workers=4) as ex:
    for site, y0, y1, counts, n, err, defs in ex.map(codes_for, jobs):
        print(site, y0, y1, n, counts, err, flush=True)
print("elapsed", round(time.time()-t0, 1))
