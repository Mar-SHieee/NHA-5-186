import sqlite3
from pathlib import Path

import pandas as pd

PY_HASHES = """
    SELECT DISTINCT hash FROM file_change
    WHERE lower(programming_language) = 'python'
"""

QUERIES = {
    "file_change": """
        SELECT *
        FROM file_change
        WHERE lower(programming_language) = 'python'
    """,
    "method_change": """
        SELECT *
        FROM method_change
        WHERE file_change_id IN (
            SELECT file_change_id FROM file_change
            WHERE lower(programming_language) = 'python'
        )
    """,
    "commits": f"""
        SELECT * FROM commits
        WHERE hash IN ({PY_HASHES})
    """,
    "fixes": f"""
        SELECT * FROM fixes
        WHERE hash IN ({PY_HASHES})
    """,
    "cwe_classification": f"""
        SELECT * FROM cwe_classification
        WHERE cve_id IN (
            SELECT cve_id FROM fixes WHERE hash IN ({PY_HASHES})
        )
    """,
}


class CVEfixesExtractor:
    def __init__(self, db_path: Path, output_dir: Path):
        """Initialize the base paths for the class."""
        self.db_path = db_path
        self.output_dir = output_dir

    def _create_connection(self) -> sqlite3.Connection:
        """Single Responsibility: Open and return a connection to the SQLite database."""
        print(f"Connecting to database at: {self.db_path}")
        return sqlite3.connect(self.db_path)

    def _read_table_chunks(self, conn: sqlite3.Connection, table_name: str):
        """Read the table in chunks (to save RAM) and return a generator."""
        print(f"Reading table '{table_name}' in chunks...")
        query = QUERIES.get(table_name, f"SELECT * FROM {table_name}")
        # Read 1000 rows per chunk
        return pd.read_sql_query(query, conn, chunksize=1000)

    def _save_chunks_to_csv(self, chunks_generator, table_name: str) -> None:
        """Single Responsibility: Receive data chunks and incrementally save them to a CSV file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.output_dir / f"{table_name}.csv"
        csv_path.unlink(missing_ok=True)

        print(f"Saving '{table_name}' to: {csv_path}")
        first_chunk = True
        for chunk in chunks_generator:
            # mode='a' appends data; header is written only for the first chunk
            chunk.to_csv(csv_path, mode="a", index=False, header=first_chunk)
            first_chunk = False

        print(f"Successfully extracted and saved {table_name}.csv\n")

    def extract_all_tables(self, table_list: list[str]) -> None:
        """Orchestrator: Manage the sequential extraction process for all specified tables."""
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database file not found at {self.db_path}. "
                f"Run: python -m shield_core.datasets.python_loaders.cvefixes_python_convert_db"
            )

        conn = self._create_connection()

        for table in table_list:
            try:
                # 1. Read in chunks
                chunks = self._read_table_chunks(conn, table)
                # 2. Save incrementally
                self._save_chunks_to_csv(chunks, table)
            except Exception as e:
                print(f"Error processing table '{table}': {e}")

        conn.close()
        print("All requested tables have been successfully extracted to CSV!")


if __name__ == "__main__":
    # ---------------------------------------------------------
    # Dynamically configure paths using pathlib to ensure
    # cross-platform compatibility for the team
    # ---------------------------------------------------------

    # __file__ is shield_core/datasets/python_loaders/cvefixes_python_tables_extraction.py
    current_dir = Path(__file__).resolve().parent

    # python_loaders -> datasets -> shield_core -> project root
    project_root = current_dir.parent.parent.parent

    # Define the path to the SQLite database (located in data/raw)
    DB_FILE_PATH = project_root / "data" / "raw" / "CVEfixes.db"

    # Define the output directory for the extracted CSV files
    CSV_OUTPUT_DIR = project_root / "data" / "raw" / "cvefixes"

    # Tables required by the plan
    tables_to_extract = ["commits", "fixes", "cwe_classification", "file_change", "method_change"]

    # Initialize and run the extractor
    extractor = CVEfixesExtractor(db_path=DB_FILE_PATH, output_dir=CSV_OUTPUT_DIR)
    extractor.extract_all_tables(tables_to_extract)
