import requests, re, json
from urllib.parse import unquote

FILES = [
 ("assets/01-pisa-tower.jpg",                 "File:The_Leaning_Tower_of_Pisa_SB.jpeg"),
 ("assets/02-viviani-portrait.jpg",           "File:Vincenzo_Viviani.jpeg"),
 ("assets/03-galileo-portrait.jpg",           "File:Justus_Sustermans_-_Portrait_of_Galileo_Galilei_-_WGA21972.jpg"),
 ("assets/04-delft-cityscape.jpg",            "File:Jan_Vermeer_van_Delft_001.jpg"),
 ("assets/05-nieuwe-kerk-delft.jpg",          "File:00_0725_Tower_of_Nieuwe_Kerk_-_Delft.jpg"),
 ("assets/06-stevin-portrait.jpg",            "File:Simon-stevin_(cropped).jpeg"),
 ("assets/07-weeghconst-titlepage.png",       "File:Simon_Stevin_-_Voorblad_van_De_Beghinselen_der_Weeghconst,_1586.png"),
 # ("assets/08-two-new-sciences-titlepage.jpg", "File:REPLACE_ME"),
 ("assets/09-inclined-plane.jpg",             "File:Piano_inclinato,_Museo_Galileo,_Florence,_Inv._104,_224108.jpg"),
]


def classify(short, terms):
    t = f"{short} {terms}".lower()
    if "non-commercial" in t or "-nc" in t or "noderiv" in t or "-nd" in t:
        return None, 0, 0          # unusable
    if "public domain" in t or t.strip().startswith("pd"):
        return "public_domain", 1, 0
    if "cc0" in t:
        return "cc0", 1, 0
    if "sa" in t and "cc" in t:
        return "cc_by_sa", 1, 1
    if "cc" in t and "by" in t:
        return "cc_by", 1, 1
    return None, 0, 0              # unknown -> reject

for local, title in FILES:
    resp = requests.get(API, params={
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json"},
        headers=HEADERS, timeout=30)

    if resp.status_code != 200 or not resp.headers.get("content-type","").startswith("application/json"):
        print(f"!! HTTP {resp.status_code} for {title}")
        print(f"   content-type: {resp.headers.get('content-type')}")
        print(f"   body: {resp.text[:300]}\n")
        continue

    r = resp.json()
    r = requests.get(API, params={
        "action": "query", "titles": title, "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json"}, timeout=30).json()

    page = next(iter(r["query"]["pages"].values()))
    if "imageinfo" not in page:
        print(f"!! NOT FOUND: {title}\n")
        continue

    md    = page["imageinfo"][0].get("extmetadata", {})
    short = md.get("LicenseShortName", {}).get("value", "")
    terms = md.get("UsageTerms", {}).get("value", "")
    artist= strip(md.get("Artist", {}).get("value", ""))
    credit= strip(md.get("Credit", {}).get("value", ""))
    restr = md.get("Restrictions", {}).get("value", "")

    lic, comm, attr = classify(short, terms)
    url = "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_")

    print(f"# {local}")
    print(f"#   commons says : {short!r}")
    if restr: print(f"#   RESTRICTIONS: {restr}")
    if lic is None:
        print(f"#   >>> UNUSABLE or UNRECOGNISED - check by hand, find another file\n")
        continue
    att = f"{artist}, {short}, via Wikimedia Commons" if attr else ""
    print(f' ("{local}",\n  "{url}",\n  "{artist}",\n  "{lic}", {comm}, {attr}, "{att}"),\n')