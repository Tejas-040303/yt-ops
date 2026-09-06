import sqlite3

VIDEO_ID = 1

# local_path, source_url, creator, license, commercial_ok, attribution_required, attribution_text
ROWS = [
 ("assets/01-pisa-tower.jpg",                "https://commons.wikimedia.org/wiki/File:The_Leaning_Tower_of_Pisa_SB.jpeg", "", "", 0, 0, ""),
 ("assets/02-viviani-portrait.jpg",          "https://commons.wikimedia.org/wiki/File:Vincenzo_Viviani.jpeg", "", "", 0, 0, ""),
 ("assets/03-galileo-portrait.jpg",          "https://commons.wikimedia.org/wiki/File:Justus_Sustermans_-_Portrait_of_Galileo_Galilei_-_WGA21972.jpg", "", "", 0, 0, ""),
 ("assets/04-delft-map.jpg",                 "https://commons.wikimedia.org/wiki/File:Jan_Vermeer_van_Delft_001.jpg", "", "", 0, 0, ""),
 ("assets/05-nieuwe-kerk-delft.jpg",         "https://commons.wikimedia.org/wiki/File:00_0725_Tower_of_Nieuwe_Kerk_-_Delft.jpg", "", "", 0, 0, ""),
 ("assets/06-stevin-portrait.jpg",           "https://commons.wikimedia.org/wiki/File:Simon-stevin_(cropped).jpeg", "", "", 0, 0, ""),
 ("assets/07-weeghconst-titlepage.jpg",      "https://commons.wikimedia.org/wiki/File:Simon_Stevin_-_Voorblad_van_De_Beghinselen_der_Weeghconst,_1586.png", "", "", 0, 0, ""),
 ("assets/08-two-new-sciences-titlepage.jpg","https://commons.wikimedia.org/wiki/File:Some_apostles_of_physiology_-_being_an_account_of_their_lives_and_labours,_labours_that_have_contributed_to_the_advancement_of_the_healing_art_as_well_as_to_the_prevention_of_disease_(1902)_(14761482756).jpg", "", "", 0, 0, ""),
 ("assets/09-inclined-plane.jpg",            "https://commons.wikimedia.org/wiki/File:Piano_inclinato,_Museo_Galileo,_Florence,_Inv._104,_224108.jpg", "", "", 0, 0, ""),
]

bad = [r[0] for r in ROWS if not r[1] or not r[3] or r[4] != 1]
if bad:
    raise SystemExit("REJECTED - missing url/license or commercial_ok=0:\n  " +
                     "\n  ".join(bad))

con = sqlite3.connect("db.sqlite")
con.executemany("""INSERT INTO assets
  (video_id, local_path, source_url, creator, license,
   commercial_ok, attribution_required, attribution_text)
  VALUES (?,?,?,?,?,?,?,?)""",
  [(VIDEO_ID,) + r for r in ROWS])
con.commit()
print(f"logged {len(ROWS)} assets")