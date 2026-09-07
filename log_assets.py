"""
Fetch licences from Wikimedia Commons and log assets to the database.

Replaces the old fetch_licenses.py + log_assets.py pair, so there is no
copy-paste step between them to get wrong.

Usage:
    python log_assets.py          # dry run: show what would be logged
    python log_assets.py --write  # verify, then insert into db.sqlite

Nothing is inserted unless every asset has a usable commercial licence.
"""

import os
import re
import sqlite3
import sys

import requests

VIDEO_ID = 1
DB = "db.sqlite"

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "yt-ops/0.1 (educational shorts project; hadtofindoutfirsttoknow@gmail.com)"
}

# (local_path, commons_file_title)
# Local path extension MUST match the real file on Commons.
FILES = [
   # ("assets/01-pisa-tower.jpg",
#"File:The_Leaning_Tower_of_Pisa_2026.jpg"),
    ("assets/02-viviani-portrait.jpg",
     "File:Vincenzo_Viviani.jpeg"),
    ("assets/03-galileo-portrait.jpg",
     "File:Justus_Sustermans_-_Portrait_of_Galileo_Galilei_-_WGA21972.jpg"),
    ("assets/04-delft-cityscape.jpg",
     "File:Jan_Vermeer_van_Delft_001.jpg"),
    ("assets/05-nieuwe-kerk-delft.jpg",
     "File:Gezicht_op_Delft,_RP-P-AO-11-10.jpg"),
    ("assets/06-stevin-portrait.jpg",
     "File:Simon-stevin_(cropped).jpeg"),
    ("assets/07-weeghconst-titlepage.png",
     "File:Simon_Stevin_-_Voorblad_van_De_Beghinselen_der_Weeghconst,_1586.png"),
    # 08: still the WRONG document -- that URL is a 1902 physiology book,
    # not Galileo's Discorsi (1638). Find the real title page or drop it.
    ("assets/09-inclined-plane.jpg",
     "File:Piano_inclinato_inv_1041_IF_21341.jpg"),
]


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def dedupe(s):
    """Commons repeats the author string in its HTML: 'UnknownUnknown'."""
    s = strip_html(s)
    half = len(s) // 2
    if len(s) % 2 == 0 and s[:half] == s[half:]:
        return s[:half]
    return s


def classify(short_name, usage_terms):
    """-> (license, commercial_ok, attribution_required). None = unusable."""
    t = f"{short_name} {usage_terms}".lower()
    if any(x in t for x in ("non-commercial", "-nc", "noncommercial",
                            "noderiv", "-nd", "fair use")):
        return None, 0, 0
    if "public domain" in t or t.strip().startswith("pd"):
        return "public_domain", 1, 0
    if "cc0" in t:
        return "cc0", 1, 0
    if "cc" in t and "sa" in t:
        return "cc_by_sa", 1, 1
    if "cc" in t and "by" in t:
        return "cc_by", 1, 1
    return None, 0, 0


def lookup(title):
    resp = requests.get(API, params={
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "extmetadata|url|size", "format": "json",
    }, headers=HEADERS, timeout=30)

    if resp.status_code != 200 or "json" not in resp.headers.get("content-type", ""):
        return {"error": f"HTTP {resp.status_code}: {resp.text[:120]}"}

    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if "imageinfo" not in page:
        return {"error": "not found on Commons"}

    info = page["imageinfo"][0]
    md = info.get("extmetadata", {})
    short = md.get("LicenseShortName", {}).get("value", "")
    terms = md.get("UsageTerms", {}).get("value", "")
    lic, ok, attr = classify(short, terms)

    return {
        "short": short,
        "artist": dedupe(md.get("Artist", {}).get("value", "")),
        "restrictions": md.get("Restrictions", {}).get("value", ""),
        "license": lic,
        "commercial_ok": ok,
        "attribution_required": attr,
        "real_ext": os.path.splitext(info.get("url", ""))[1].lower(),
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "page_url": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
    }


def main():
    write = "--write" in sys.argv
    rows, blockers = [], []

    for local, title in FILES:
        r = lookup(title)
        if "error" in r:
            print(f"FAIL  {local}\n      {r['error']}")
            blockers.append(f"{local}: {r['error']}")
            continue

        note = ""
        if r["restrictions"]:
            note = f"  RESTRICTIONS: {r['restrictions']}"
            blockers.append(f"{local}: has restrictions ({r['restrictions']})")

        # Extension mismatch is cosmetic -- ffmpeg reads file headers --
        # so note it rather than blocking the whole insert.
        ext = os.path.splitext(local)[1].lower()
        norm = lambda e: ".jpg" if e in (".jpg", ".jpeg") else e
        if r["real_ext"] and norm(ext) != norm(r["real_ext"]):
            print(f"  note: {local} is really '{r['real_ext']}' on Commons")

        if r["license"] is None:
            print(f"BLOCK {local}   {r['short']!r} -- unusable{note}")
            blockers.append(f"{local}: licence {r['short']!r} not usable")
            continue

        if min(r["width"], r["height"]) < 1200:
            print(f"  note: {local} is {r['width']}x{r['height']} "
                  f"-- small, may look soft when zoomed")

        attribution = (f"{r['artist']}, {r['short']}, via Wikimedia Commons"
                       if r["attribution_required"] else "")

        print(f"OK    {local}   {r['license']:14s} {r['short']}{note}")
        rows.append((local, r["page_url"], r["artist"], r["license"],
                     r["commercial_ok"], r["attribution_required"],
                     attribution))

    print()
    if blockers:
        print("NOT LOGGED -- fix these first:")
        for b in blockers:
            print(f"  - {b}")
        raise SystemExit(1)

    if not write:
        print(f"{len(rows)} assets ready. Re-run with --write to insert.")
        return

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    n = con.execute("SELECT COUNT(*) FROM videos WHERE id = ?",
                    (VIDEO_ID,)).fetchone()[0]
    if not n:
        con.close()
        raise SystemExit(
            f"no videos row with id={VIDEO_ID} -- create the "
            f"topic/angle/script/video chain first")

    con.execute("DELETE FROM assets WHERE video_id = ?", (VIDEO_ID,))
    con.executemany(
        "INSERT INTO assets (video_id, local_path, source_url, creator, "
        "license, commercial_ok, attribution_required, attribution_text) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(VIDEO_ID,) + r for r in rows])
    con.commit()
    con.close()
    print(f"logged {len(rows)} assets for video_id={VIDEO_ID}")


if __name__ == "__main__":
    main()