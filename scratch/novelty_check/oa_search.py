#!/usr/bin/env python3
"""Search OpenAlex by title+abstract and print screenable rows.

Usage: python3 oa_search.py "query terms" [--n 10] [--from 2018] [--abstract]
"""
import argparse
import json
import textwrap
import urllib.parse
import urllib.request

UA = "stream-recoverability-novelty-check/1.0 (mailto:research@example.org)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as fh:
        return json.load(fh)


def abstract_of(work):
    inv = work.get("abstract_inverted_index")
    if not inv:
        return None
    pos = {}
    for word, ps in inv.items():
        for p in ps:
            pos[p] = word
    return " ".join(pos[i] for i in sorted(pos))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--from", dest="from_year", type=int, default=None)
    ap.add_argument("--abstract", action="store_true")
    ap.add_argument("--field", default="title_and_abstract.search")
    a = ap.parse_args()
    filters = [f"{a.field}:{a.query}"]
    if a.from_year:
        filters.append(f"from_publication_date:{a.from_year}-01-01")
    url = (
        "https://api.openalex.org/works?filter="
        + urllib.parse.quote(",".join(filters), safe=":,")
        + f"&per-page={a.n}&mailto=research@example.org"
        + "&select=id,doi,title,publication_year,primary_location,biblio,abstract_inverted_index,cited_by_count,type"
    )
    res = get(url)
    print("count:", res["meta"]["count"])
    for w in res["results"]:
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        print("-" * 78)
        print(f"{w.get('publication_year')} | {w.get('title')}")
        print(f"   venue: {src} | doi: {w.get('doi')} | cites: {w.get('cited_by_count')}")
        if a.abstract:
            ab = abstract_of(w)
            if ab:
                print(textwrap.fill(ab[:900], 110, initial_indent="   ", subsequent_indent="   "))


if __name__ == "__main__":
    main()
