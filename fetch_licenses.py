"""
Fetch licence metadata for Wikimedia Commons files.

Usage:  python fetch_licenses.py

Prints ROWS entries you can paste into log_assets.py.
Anything flagged UNUSABLE must be checked by hand or replaced.
"""

import re
import requests

API = "https://commons.wikimedia.org/w/api.php"

# Wikimedia rejects generic clients. A descriptive User-Agent is required.
HEADERS = {
    "User-Agent": "yt-ops/0.1 (educational shorts project; hadtofindoutfirsttoknow@gmail.com)"
}


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


# (local_path, commons_file_title)
FILES = [
    ("assets/01-pisa-tower.jpg",
     "File:The_Leaning_Tower_of_Pisa_SB.jpeg"),
    ("assets/02-viviani-portrait.jpg",
     "File:Vincenzo_Viviani.jpeg"),
    ("assets/03-galileo-portrait.jpg",
     "File:Justus_Sustermans_-_Portrait_of_Galileo_Galilei_-_WGA21972.jpg"),
    ("assets/04-delft-cityscape.jpg",
     "File:Jan_Vermeer_van_Delft_001.jpg"),
    ("assets/05-nieuwe-kerk-delft.jpg",
     "File:00_0725_Tower_of_Nieuwe_Kerk_-_Delft.jpg"),
    ("assets/06-stevin-portrait.jpg",
     "File:Simon-stevin_(cropped).jpeg"),
    ("assets/07-weeghconst-titlepage.png",
     "File:Simon_Stevin_-_Voorblad_van_De_Beghinselen_der_Weeghconst,_1586.png"),
    # TODO: find the 1638 Discorsi title page on Commons, then uncomment:
    # ("assets/08-two-new-sciences-titlepage.jpg", "File:REPLACE_ME"),
    ("assets/09-inclined-plane.jpg",
     "File:Piano_inclinato,_Museo_Galileo,_Florence,_Inv._104,_224108.jpg"),
]


def classify(short_name, usage_terms):
    """Map a Commons licence string to (license, commercial_ok, attribution_required).

    Returns (None, 0, 0) for anything unusable or unrecognised -- check by hand.
    """
    t = f"{short_name} {usage_terms}".lower()

    # Reject non-commercial and no-derivatives outright.
    if any(x in t for x in ("non-commercial", "-nc", "noncommercial",
                            "noderiv", "-nd")):
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


def main():
    for local, title in FILES:
        try:
            resp = requests.get(
                API,
                params={
                    "action": "query",
                    "titles": title,
                    "prop": "imageinfo",
                    "iiprop": "extmetadata|url",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=30,
            )
        except requests.RequestException as e:
            print(f"!! REQUEST FAILED: {title}\n   {e}\n")
            continue

        ctype = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "json" not in ctype:
            print(f"!! HTTP {resp.status_code} for {title}")
            print(f"   content-type: {ctype}")
            print(f"   body: {resp.text[:200]}\n")
            continue

        pages = resp.json().get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        if "imageinfo" not in page:
            print(f"!! NOT FOUND ON COMMONS: {title}\n")
            continue

        md = page["imageinfo"][0].get("extmetadata", {})
        short = md.get("LicenseShortName", {}).get("value", "")
        terms = md.get("UsageTerms", {}).get("value", "")
        artist = strip_html(md.get("Artist", {}).get("value", ""))
        restrictions = md.get("Restrictions", {}).get("value", "")

        lic, commercial_ok, attr_required = classify(short, terms)
        url = "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_")

        print(f"# {local}")
        print(f"#   commons licence: {short!r}")
        if restrictions:
            print(f"#   RESTRICTIONS: {restrictions}")

        if lic is None:
            print("#   >>> UNUSABLE or UNRECOGNISED -- open the page and check "
                  "by hand, or find another file\n")
            continue

        attribution = (f"{artist}, {short}, via Wikimedia Commons"
                       if attr_required else "")
        print(f' ("{local}",')
        print(f'  "{url}",')
        print(f'  "{artist}",')
        print(f'  "{lic}", {commercial_ok}, {attr_required}, "{attribution}"),')
        print()


if __name__ == "__main__":
    main()