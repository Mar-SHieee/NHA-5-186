# shield_core/datasets/python_loaders/cvefixes_python_convert_db.py
import gzip
import sqlite3
import sys
import urllib.request
import zipfile
from pathlib import Path

# <this file> -> datasets -> shield_core -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DST = RAW_DIR / "CVEfixes.db"


# Zenodo record for CVEfixes v1.0.8 (ships as a single zip)
DOWNLOAD_URL = "https://zenodo.org/records/13118970/files/CVEfixes_v1.0.8.zip?download=1"
ZIP_FILE = RAW_DIR / "CVEfixes_v1.0.8.zip"


def _find_dumps() -> list[Path]:
    return sorted(RAW_DIR.glob("CVEfixes_v*.sql.gz"))


def _extract_dump_from_zip() -> None:
    """Pull the .sql.gz out of the zip into RAW_DIR."""
    with zipfile.ZipFile(ZIP_FILE) as z:
        members = [m for m in z.namelist() if m.endswith(".sql.gz")]
        if not members:
            print(f"No .sql.gz found in {ZIP_FILE.name}. Contents: {z.namelist()}")
            sys.exit(1)
        for m in members:
            target = RAW_DIR / Path(m).name
            print(f"Extracting {m} -> {target.name}")
            with z.open(m) as src, open(target, "wb") as out:
                while chunk := src.read(1024 * 1024):
                    out.write(chunk)


RAW_DIR.mkdir(parents=True, exist_ok=True)
dumps = _find_dumps()

if not dumps:
    if not ZIP_FILE.exists():
        print(f"Downloading {DOWNLOAD_URL} (12.7 GB, this will take a while)...")
        try:
            urllib.request.urlretrieve(DOWNLOAD_URL, ZIP_FILE)
        except Exception as e:
            ZIP_FILE.unlink(missing_ok=True)  # don't leave a partial zip behind
            print(f"Download failed: {e}")
            print(f"Download it manually and place it at {ZIP_FILE}")
            sys.exit(1)
    _extract_dump_from_zip()
    dumps = _find_dumps()
    if not dumps:
        print("Extracted files don't match CVEfixes_v*.sql.gz. Rename the dump and re-run.")
        sys.exit(1)

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
