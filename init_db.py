import sqlite3, os, sys

DB = "db.sqlite"

if os.path.exists(DB):
    if input(f"{DB} exists. Delete and rebuild? [y/N] ").lower() != "y":
        sys.exit("aborted")
    os.remove(DB)

con = sqlite3.connect(DB)
con.executescript(open("schema.sql", encoding="utf-8").read())

tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' order by name")]
myths = con.execute("select count(*) from myth_blacklist").fetchone()[0]
con.close()

print(f"created {DB}")
print(f"{len(tables)} tables: {', '.join(tables)}")
print(f"myth_blacklist seeded with {myths} rows")