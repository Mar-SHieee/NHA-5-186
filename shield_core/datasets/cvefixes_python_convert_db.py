# shield_core/datasets/cvefixes_python_convert_db.py
import gzip
import sqlite3
from pathlib import Path

# <this file> -> datasets -> shield_core -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DST = RAW_DIR / "CVEfixes.db"

# Finds the dump whatever the version is (CVEfixes_v1.0.7.sql.gz, v1.0.8, ...).
dumps = sorted(RAW_DIR.glob("CVEfixes_v*.sql.gz"))
if not dumps:
    raise FileNotFoundError(
        f"No CVEfixes_v*.sql.gz found in {RAW_DIR}. Download it from Zenodo and put it there."
    )
SRC = dumps[-1]
if len(dumps) > 1:
    print(f"Found several dumps, using the last one: {SRC.name}")

if DST.exists():
    raise FileExistsError(f"{DST} already exists. Delete or rename it first.")

TOTAL = SRC.stat().st_size

con = sqlite3.connect(DST)
con.execute("PRAGMA journal_mode=OFF")
con.execute("PRAGMA synchronous=OFF")

parts: list[str] = []
n = 0

print(f"Importing {SRC.name} -> {DST.name}. This can take an hour or more.", flush=True)
with gzip.open(SRC, "rt", encoding="utf-8", errors="replace") as f:
    for line in f:
        parts.append(line)
        # cheap check first: only a line ending with ';' can end a statement
        if not line.rstrip().endswith(";"):
            continue
        stmt = "".join(parts)
        if not sqlite3.complete_statement(stmt):
            continue
        try:
            con.execute(stmt)
        except sqlite3.Error as e:
            print(f"\nFailed on statement #{n + 1}: {e}")
            print(stmt[:300])
            con.commit()
            con.close()
            raise
        parts.clear()
        n += 1
        if n % 5000 == 0:
            con.commit()
            pct = f.buffer.fileobj.tell() / TOTAL * 100
            print(f"{n} statements | ~{pct:.1f}% of the file", flush=True)

con.commit()
con.close()
print(f"Done: {n} statements -> {DST}")
