"""Vacuum SQLite cache DB and print size info."""

import os, sqlite3

db = os.path.join(
    os.path.dirname(__file__), "data_cache", "series_raw", "series_cache.db"
)
if os.path.exists(db):
    size_before = os.path.getsize(db) / 1024 / 1024
    conn = sqlite3.connect(db)
    conn.execute("VACUUM")
    conn.close()
    size_after = os.path.getsize(db) / 1024 / 1024
    print(f"DB: {size_before:.1f} MB -> {size_after:.1f} MB")
else:
    print("No cache DB found, skipping vacuum.")
