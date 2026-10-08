# shield_core/datasets/cvefixes_python_convert_db.py
import gzip
import sqlite3
import sys
import urllib.request
from pathlib import Path

# <this file> -> datasets -> shield_core -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DST = RAW_DIR / "CVEfixes.db"

# Direct link to Zenodo for CVEfixes v1.0.8
DOWNLOAD_URL = "https://zenodo.org/records/10439153/files/CVEfixes_v1.0.8.sql.gz"
EXPECTED_FILE = RAW_DIR / "CVEfixes_v1.0.8.sql.gz"

# Finds the dump whatever the version is (CVEfixes_v1.0.7.sql.gz, v1.0.8, ...).
dumps = sorted(RAW_DIR.glob("CVEfixes_v*.sql.gz"))

if not dumps:
    print(f"Dataset not found in {RAW_DIR}. Starting automated download...")
    print(f"Downloading from: {DOWNLOAD_URL}")
    print("Please wait, this is a large file and might take a while...")

    # Ensure the raw directory exists before downloading
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Download the file directly to the expected path
        urllib.request.urlretrieve(DOWNLOAD_URL, EXPECTED_FILE)
        print("Download completed successfully!")
        SRC = EXPECTED_FILE
    except Exception as e:
        print(f"Download failed: {e}")
        print("Please download it manually from Zenodo and place it in the raw directory.")
        sys.exit(1)
else:
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
