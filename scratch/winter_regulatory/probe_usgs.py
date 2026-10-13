import urllib.request, json
UA = "stream-recoverability-research/1.0 (research; contact: repo maintainer)"
def get(url, timeout=90):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")

legacy = ("https://waterservices.usgs.gov/nwis/dv/?format=rdb&sites=06025500"
          "&parameterCd=00010&statCd=00001&siteStatus=all&startDT=2015-01-01&endDT=2016-01-01")
try:
    st, body = get(legacy)
    print("LEGACY status", st, "len", len(body))
    print("\n".join(body.splitlines()[:40]))
except Exception as e:
    print("LEGACY FAIL", type(e).__name__, e)

new = ("https://api.waterdata.usgs.gov/ogcapi/v0/collections/daily/items?"
       "monitoring_location_id=USGS-06025500&parameter_code=00010&statistic_id=00001&limit=3")
try:
    st, body = get(new)
    print("NEW status", st, "len", len(body))
    print(body[:800])
except Exception as e:
    print("NEW FAIL", type(e).__name__, e)
