"""Backfill missing time-series-metadata responses, paced for the API rate limit."""
import glob, json, os, sys, time, urllib.parse, urllib.request

CACHE = "results/wrr_submission_ready/amendments/outage_causes/raw_cache"
UA = "stream-recoverability outage-cause audit (WRR submission)"
URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/time-series-metadata/items"

have = {os.path.basename(p)[4:-5] for p in glob.glob(os.path.join(CACHE, "tsm_*.json"))}
stations = sorted({os.path.basename(p).split("_")[1] for p in glob.glob(os.path.join(CACHE, "dv_*.rdb"))})
todo = [s for s in stations if s not in have]
print("todo:", len(todo), flush=True)

for index, site in enumerate(todo, 1):
    dest = os.path.join(CACHE, f"tsm_{site}.json")
    query = urllib.parse.urlencode({
        "monitoring_location_id": f"USGS-{site}", "parameter_code": "00010",
        "statistic_id": "00003", "limit": 200, "f": "json"})
    for attempt in range(6):
        try:
            request = urllib.request.Request(URL + "?" + query, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=120) as response:
                text = response.read().decode("utf-8", errors="replace")
            break
        except Exception as error:
            wait = 15 * (attempt + 1)
            print(f"  {site}: {error} -> sleep {wait}s", flush=True)
            time.sleep(wait)
    else:
        print(f"FAILED {site}", flush=True)
        continue
    if text.lstrip().startswith("{"):
        json.loads(text)  # validate
        open(dest, "w", encoding="utf-8").write(text)
    else:
        print(f"non-json for {site}", flush=True)
    if index % 10 == 0 or index == len(todo):
        print(f"backfilled {index}/{len(todo)}", flush=True)
    time.sleep(2.0)
print("done", flush=True)
