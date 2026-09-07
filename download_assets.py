"""
Download original image files from Wikimedia Commons.

Usage:  python download_assets.py

Saves into assets/ using the local names below.
Skips files that already exist. Warns if an image is too small
for a 1080x1920 render with Ken Burns motion.
"""

import os
import requests

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "yt-ops/0.1 (educational shorts project; hadtofindoutfirsttoknow@gmail.com)"
}

OUT_DIR = "assets"
MIN_SHORT_EDGE = 1200   # below this, Ken Burns will look soft

# (local_filename, commons_file_title)
FILES = [
    ("02-viviani-portrait.jpg",
     "File:Vincenzo_Viviani.jpeg"),
    ("03-galileo-portrait.jpg",
     "File:Justus_Sustermans_-_Portrait_of_Galileo_Galilei_-_WGA21972.jpg"),
    ("04-delft-cityscape.jpg",
     "File:Jan_Vermeer_van_Delft_001.jpg"),
    ("05-nieuwe-kerk-delft.jpg",
     "File:00_0725_Tower_of_Nieuwe_Kerk_-_Delft.jpg"),
    ("06-stevin-portrait.jpg",
     "File:Simon-stevin_(cropped).jpeg"),
    ("07-weeghconst-titlepage.png",
     "File:Simon_Stevin_-_Voorblad_van_De_Beghinselen_der_Weeghconst,_1586.png"),
    ("09-inclined-plane.jpg",
     "File:Piano_inclinato,_Museo_Galileo,_Florence,_Inv._104,_224108.jpg"),
    # 01 dropped (ita-mibac restriction)
    # 08 still to find: 1638 Discorsi title page
]


def get_image_info(title):
    """Return (direct_url, width, height, mime) for a Commons file title."""
    resp = requests.get(
        API,
        params={
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        },
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    if "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    return info["url"], info.get("width", 0), info.get("height", 0), info.get("mime", "")


def download(url, dest):
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
    return os.path.getsize(dest)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    problems = []

    for local, title in FILES:
        dest = os.path.join(OUT_DIR, local)

        if os.path.exists(dest):
            print(f"skip  {local}  (already present)")
            continue

        info = get_image_info(title)
        if info is None:
            print(f"FAIL  {local}  -- not found on Commons: {title}")
            problems.append(local)
            continue

        url, w, h, mime = info

        # Warn if the extension disagrees with the real file type.
        ext = os.path.splitext(local)[1].lower()
        real = os.path.splitext(url)[1].lower()
        if ext != real:
            print(f"WARN  {local}  -- Commons file is '{real}', "
                  f"you named it '{ext}'. Renaming to match.")
            local = os.path.splitext(local)[0] + real
            dest = os.path.join(OUT_DIR, local)

        size = download(url, dest)
        short_edge = min(w, h)
        flag = "" if short_edge >= MIN_SHORT_EDGE else "  <-- SMALL, may look soft"
        print(f"ok    {local}  {w}x{h}  {size/1_000_000:.1f}MB{flag}")
        if short_edge < MIN_SHORT_EDGE:
            problems.append(local)

    print()
    if problems:
        print("Needs attention:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("All downloads clean.")


if __name__ == "__main__":
    main()