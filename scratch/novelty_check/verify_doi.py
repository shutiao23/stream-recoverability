#!/usr/bin/env python3
"""Verify a DOI against Crossref and OpenAlex and print the fields a
references.bib entry needs, plus the abstract when one is available.

Usage: python3 verify_doi.py 10.xxxx/yyy [10.xxxx/zzz ...]
"""
import json
import sys
import urllib.parse
import urllib.request

UA = "stream-recoverability-novelty-check/1.0 (mailto:research@example.org)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as fh:
        return json.load(fh)


def crossref(doi):
    d = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))["message"]
    return {
        "title": (d.get("title") or [None])[0],
        "container": (d.get("container-title") or [None])[0],
        "short_container": (d.get("short-container-title") or [None])[0],
        "volume": d.get("volume"),
        "issue": d.get("issue"),
        "page": d.get("page"),
        "article_number": d.get("article-number"),
        "published_print": d.get("published-print", {}).get("date-parts"),
        "published_online": d.get("published-online", {}).get("date-parts"),
        "issued": d.get("issued", {}).get("date-parts"),
        "authors": [
            (a.get("family"), a.get("given")) for a in (d.get("author") or [])
        ],
        "type": d.get("type"),
        "publisher": d.get("publisher"),
        "url": d.get("URL"),
    }


def openalex(doi):
    d = get(
        "https://api.openalex.org/works/doi:"
        + urllib.parse.quote(doi)
        + "?mailto=research@example.org"
    )
    out = {
        "title": d.get("title"),
        "year": d.get("publication_year"),
        "date": d.get("publication_date"),
        "venue": ((d.get("primary_location") or {}).get("source") or {}).get(
            "display_name"
        ),
        "bibtex_volume": (d.get("biblio") or {}).get("volume"),
        "bibtex_issue": (d.get("biblio") or {}).get("issue"),
        "first_page": (d.get("biblio") or {}).get("first_page"),
        "last_page": (d.get("biblio") or {}).get("last_page"),
        "cited_by": d.get("cited_by_count"),
        "landing": (d.get("primary_location") or {}).get("landing_page_url"),
        "open_access_pdf": ((d.get("best_oa_location") or {}) or {}).get("pdf_url"),
    }
    inv = d.get("abstract_inverted_index")
    if inv:
        pos = {}
        for word, ps in inv.items():
            for p in ps:
                pos[p] = word
        out["abstract"] = " ".join(pos[i] for i in sorted(pos))
    return out


def main(dois):
    for doi in dois:
        print("=" * 78)
        print("DOI:", doi)
        try:
            c = crossref(doi)
            print("-- crossref --")
            for k, v in c.items():
                print(f"  {k}: {v}")
        except Exception as exc:  # noqa: BLE001
            print("  crossref FAILED:", exc)
        try:
            o = openalex(doi)
            print("-- openalex --")
            for k, v in o.items():
                if k == "abstract":
                    continue
                print(f"  {k}: {v}")
            ab = o.get("abstract")
            print("  abstract:", (ab[:3000] if ab else "NONE"))
        except Exception as exc:  # noqa: BLE001
            print("  openalex FAILED:", exc)


if __name__ == "__main__":
    main(sys.argv[1:])
