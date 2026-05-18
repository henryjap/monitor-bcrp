"""Vacuum INEI SQLite cache."""
from pathlib import Path
import sqlite3

db = Path(__file__).parent / "data_cache" / "inei_raw" / "inei_cache.db"
if db.exists():
    size_before = db.stat().st_size / 1024 / 1024
    conn = sqlite3.connect(str(db))
    conn.execute("VACUUM")
    conn.close()
    size_after = db.stat().st_size / 1024 / 1024
    print(f"INEI DB: {size_before:.1f} MB -> {size_after:.1f} MB")
else:
    print("No INEI cache DB found, skipping vacuum.")
