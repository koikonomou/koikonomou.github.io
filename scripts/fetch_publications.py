#!/usr/bin/env python3
"""Fetch publications from OpenAlex and write publications.json.

Run by .github/workflows/update-publications.yml. Set the optional
OPENALEX_API_KEY repository secret if the anonymous rate limit is hit.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

AUTHOR_ID = "a5041627686"
OUT = os.path.join(os.path.dirname(__file__), "..", "publications.json")

params = {
    "filter": f"authorships.author.id:{AUTHOR_ID}",
    "per_page": "100",
    "sort": "publication_date:desc",
    "select": "id,title,publication_year,publication_date,type,type_crossref,doi,"
              "primary_location,biblio,authorships,cited_by_count",
}
key = os.environ.get("OPENALEX_API_KEY")
if key:
    params["api_key"] = key
url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)

req = urllib.request.Request(url, headers={"User-Agent": "koikonomou.github.io publication sync"})
with urllib.request.urlopen(req, timeout=60) as r:
    results = json.load(r)["results"]


def kind(w):
    src = ((w.get("primary_location") or {}).get("source") or {})
    t, tc, st = w.get("type"), w.get("type_crossref"), src.get("type")
    if t == "dissertation" or tc == "dissertation":
        return "thesis"
    if tc == "proceedings-article" or st == "conference":
        return "conference"
    if t == "preprint" or st == "repository":
        return "preprint"
    if tc == "journal-article" or st == "journal" or t == "article":
        return "journal"
    if t in ("book-chapter", "book"):
        return "chapter"
    return "other"


RANK = {"journal": 0, "conference": 1, "chapter": 2, "thesis": 3, "preprint": 4, "other": 5}
SKIP_TYPES = {"peer-review", "paratext", "erratum", "dataset", "retraction", "editorial"}

pubs = {}
for w in results:
    if not w.get("title") or w.get("type") in SKIP_TYPES:
        continue
    src = ((w.get("primary_location") or {}).get("source") or {})
    doi = w.get("doi")
    landing = (w.get("primary_location") or {}).get("landing_page_url")
    p = {
        "title": re.sub(r"<[^>]+>", "", w["title"]).strip(),
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "kind": kind(w),
        "venue": src.get("display_name") or "",
        "volume": (w.get("biblio") or {}).get("volume") or "",
        "authors": [(a.get("author") or {}).get("display_name", "") for a in w.get("authorships", [])],
        "url": doi or landing or w.get("id"),
        "doi": doi.replace("https://doi.org/", "") if doi else "",
        "citations": w.get("cited_by_count", 0),
    }
    # De-duplicate the same paper indexed twice (e.g. preprint + journal version).
    k = re.sub(r"[^a-z0-9]", "", p["title"].lower())
    old = pubs.get(k)
    if old is None or (RANK[p["kind"]], not p["venue"]) < (RANK[old["kind"]], not old["venue"]):
        if old:
            p["citations"] = max(p["citations"], old["citations"])
        pubs[k] = p
    else:
        old["citations"] = max(p["citations"], old["citations"])

out = sorted(pubs.values(), key=lambda p: (p["date"] or ""), reverse=True)
if not out:
    sys.exit("OpenAlex returned no publications; keeping the existing file.")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"source": f"https://openalex.org/authors/{AUTHOR_ID}", "works": out}, f, ensure_ascii=False, indent=1)
    f.write("\n")
print(f"Wrote {len(out)} publications")
