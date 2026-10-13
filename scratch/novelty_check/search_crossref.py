#!/usr/bin/env python3
"""Search Crossref by title/author and print candidate matches.

Usage: python3 search_crossref.py "title words" [--author Grey] [--rows 5]
"""
import argparse
import json
import urllib.parse
import urllib.request

UA = "stream-recoverability-novelty-check/1.0 (mailto:research@example.org)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--author", default=None)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--container", default=None)
    a = ap.parse_args()
    params = {
        "query.bibliographic": a.query,
        "rows": str(a.rows),
        "select": "DOI,title,container-title,volume,issue,page,article-number,issued,author,type",
    }
    if a.author:
        params["query.author"] = a.author
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    items = get(url)["message"]["items"]
    for it in items:
        au = ", ".join(
            f"{x.get('family','?')} {x.get('given','')[:1]}." for x in (it.get("author") or [])[:6]
        )
        yr = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        print("-" * 70)
        print(" title    :", (it.get("title") or [None])[0])
        print(" journal  :", (it.get("container-title") or [None])[0])
        print(f" year     : {yr}  vol {it.get('volume')} issue {it.get('issue')} "
              f"page {it.get('page')} art {it.get('article-number')}")
        print(" authors  :", au)
        print(" doi      :", it.get("DOI"), " type:", it.get("type"))


if __name__ == "__main__":
    main()
