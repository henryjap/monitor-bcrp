"""Headless download script for GitHub Actions.
Downloads BCRP series using filtered catalog + incremental updates."""

from datetime import date, datetime
from pathlib import Path
import csv
import json
import sqlite3
import sys
import time

import pandas as pd

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from bcrp_monitor_core import fetch_bcrp_series, fetch_bcrp_batch_series, clean_code
from constants import RAW_CACHE_DIR, DATA_CACHE_DIR


def local_series_db_path() -> Path:
    p = RAW_CACHE_DIR / "series_cache.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db():
    db_path = local_series_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS series_data (
                codigo TEXT,
                fecha TEXT,
                valor REAL,
                PRIMARY KEY (codigo, fecha)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_codigo ON series_data(codigo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fecha ON series_data(fecha)")
        conn.execute("PRAGMA journal_mode=WAL")


def save_to_cache(code: str, df: pd.DataFrame):
    if df is None or df.empty:
        return
    clean = df[["fecha", "valor"]].copy()
    clean["fecha"] = pd.to_datetime(clean["fecha"], errors="coerce").dt.date.astype(str)
    clean["valor"] = pd.to_numeric(clean["valor"], errors="coerce")
    clean = clean.dropna(subset=["fecha", "valor"]).drop_duplicates(
        "fecha", keep="last"
    )
    if clean.empty:
        return
    clean.insert(0, "codigo", code)
    init_db()
    temp_table = f"temp_{code.replace('.', '_').replace('-', '_')}"
    try:
        with sqlite3.connect(local_series_db_path()) as conn:
            clean.to_sql(temp_table, conn, if_exists="replace", index=False)
            conn.execute(f"""
                INSERT OR REPLACE INTO series_data (codigo, fecha, valor)
                SELECT codigo, fecha, valor FROM {temp_table}
            """)
            conn.execute(f"DROP TABLE {temp_table}")
    except Exception as e:
        print(f"  [WARN] DB save error for {code}: {e}")


def load_local_bulk_cache() -> dict:
    """Load all cached series into memory (codes only)."""
    try:
        init_db()
        with sqlite3.connect(local_series_db_path()) as conn:
            rows = conn.execute("SELECT DISTINCT codigo FROM series_data").fetchall()
            return {r[0]: True for r in rows}
    except Exception:
        return {}


def save_local_series_cache_bulk(updates: dict):
    """Persist multiple series at once."""
    for code, df in updates.items():
        save_to_cache(code, df)


def load_enriched_catalog() -> list[dict]:
    """Load metadata CSV as enriched records."""
    path = HERE / "BCRPData-metadata-20260509-181936.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, encoding="latin1", sep=";", low_memory=False)
    cols = df.columns.tolist()
    records = []
    for _, row in df.iterrows():
        records.append(
            {
                "codigo": str(row.iloc[0]).strip().upper(),
                "nombre_bcrp": str(row.iloc[3]) if len(cols) > 3 else "",
                "grupo_bcrp": str(row.iloc[2]) if len(cols) > 2 else "",
                "categoria": str(row.iloc[1]) if len(cols) > 1 else "",
                "frecuencia": str(row.iloc[10]) if len(cols) > 10 else "",
            }
        )
    return records


def main():
    print("=" * 60)
    print(f"BCRP Data Downloader — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    # 1. Load enriched catalog
    records = load_enriched_catalog()
    if not records:
        print("❌ Metadata CSV not found")
        sys.exit(1)
    print(f"  📄 Catalog: {len(records)} total records")

    # 2. Filter out unwanted series
    filtered = []
    skipped = {"CD": 0, "discontinued": 0, "old_hist": 0}
    for r in records:
        code = r["codigo"]
        name = r["nombre_bcrp"].lower()
        group = r["grupo_bcrp"]

        if code.startswith("CD"):
            skipped["CD"] += 1
            continue
        if "(descontinuada)" in name:
            skipped["discontinued"] += 1
            continue
        if group == "Entre 1930 a 1980":
            skipped["old_hist"] += 1
            continue
        filtered.append(r)

    print(
        f"  🚫 Skipped: {skipped['CD']} CD, {skipped['discontinued']} discontinued, {skipped['old_hist']} historical"
    )
    print(f"  ✅ Active series: {len(filtered)}")

    # 3. Identify which active codes are missing from cache
    bulk_cache = load_local_bulk_cache()
    all_active_codes = [r["codigo"] for r in filtered]
    missing_codes = [c for c in all_active_codes if c not in bulk_cache]

    already_cached = len(all_active_codes) - len(missing_codes)
    print(f"  🗄️  Already cached: {already_cached}")
    print(f"  📥 Missing to download: {len(missing_codes)}")

    if not missing_codes:
        print("\n✅ All active series already cached. Running incremental update only.")

    # 4. Date range
    end = date.today()
    last_run_file = DATA_CACHE_DIR / "last_run_date.txt"
    if bulk_cache and last_run_file.exists():
        start = date.fromisoformat(last_run_file.read_text().strip())
        print(f"  🔄 Incremental mode (since {start})")
    else:
        start = date(1900, 1, 1)
        print(f"  🆕 Full download from {start}")
    print(f"  📅 Range: {start} → {end}")
    print()

    # 5. Download in batches — only missing codes OR incremental for all active
    codes_to_fetch = missing_codes if missing_codes else all_active_codes
    batch_size = 20
    batches = [
        codes_to_fetch[i : i + batch_size]
        for i in range(0, len(codes_to_fetch), batch_size)
    ]
    total = len(codes_to_fetch)
    ok = 0
    fail = 0
    failed_codes = []
    errors = []

    print(f"⚙️  Fetching {total} series in {len(batches)} batches of {batch_size}...\n")

    for idx, batch in enumerate(batches, 1):
        print(f"  [{idx}/{len(batches)}] batch of {len(batch)}...", end=" ", flush=True)
        try:
            series_map, meta_map = fetch_bcrp_batch_series(batch, start, end)
            batch_ok = 0
            for code in batch:
                df = series_map.get(code, pd.DataFrame())
                if df is not None and not df.empty:
                    save_to_cache(code, df)
                    batch_ok += 1
                else:
                    failed_codes.append(code)
            ok += batch_ok
            fail += len(batch) - batch_ok
            print(f"{batch_ok}/{len(batch)} ok")
        except Exception as e:
            print(f"BATCH FAILED: {e}")
            for code in batch:
                try:
                    df, meta = fetch_bcrp_series(code, start, end)
                    if df is not None and not df.empty:
                        save_to_cache(code, df)
                        ok += 1
                    else:
                        fail += 1
                        failed_codes.append(code)
                except Exception as e2:
                    fail += 1
                    failed_codes.append(code)
                    errors.append(f"{code}: {e2}")
                time.sleep(0.2)
            print(f"     → retried individually")
        time.sleep(0.3)

    # 6. Retry pass for individual failed codes (uses /esp endpoint)
    if failed_codes:
        unique_failed = sorted(set(failed_codes))
        print(f"\n🔁 Retry pass: {len(unique_failed)} codes individually...")
        retry_ok = 0
        for idx, code in enumerate(unique_failed, 1):
            print(f"  [{idx}/{len(unique_failed)}] {code}...", end=" ", flush=True)
            try:
                df, meta = fetch_bcrp_series(code, start, end)
                if df is not None and not df.empty:
                    save_to_cache(code, df)
                    retry_ok += 1
                    ok += 1
                    fail -= 1
                    print("✅")
                else:
                    print("❌ no data")
            except Exception as e:
                print(f"❌ {str(e)[:80]}")
            time.sleep(0.3)
        print(f"  Retry recovered: {retry_ok}/{len(unique_failed)}")

    # 7. Final stats
    init_db()
    try:
        with sqlite3.connect(local_series_db_path()) as conn:
            count = conn.execute(
                "SELECT COUNT(DISTINCT codigo) FROM series_data"
            ).fetchone()[0]
            total_rows = conn.execute("SELECT COUNT(*) FROM series_data").fetchone()[0]
    except Exception:
        count, total_rows = 0, 0

    print(f"\n{'=' * 60}")
    print(f"✅ Downloaded: {ok} | Failed: {fail} | Total: {total}")
    print(f"📊 Cache DB: {count} unique series, {total_rows} observations")

    if errors:
        print(f"\n⚠️  Errors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  • {e}")

    # Save markers
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_CACHE_DIR / "last_run_date.txt", "w") as f:
        f.write(end.isoformat())

    summary = {
        "date": datetime.now().isoformat(),
        "total_active": len(filtered),
        "downloaded": ok,
        "failed": fail,
        "cache_series": count,
        "cache_obs": total_rows,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    with open(DATA_CACHE_DIR / "ci_download_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  📝 Summary saved")

    try:
        with sqlite3.connect(local_series_db_path()) as conn:
            stats = pd.read_sql(
                "SELECT codigo, COUNT(*) as obs, MIN(fecha) as desde, MAX(fecha) as hasta FROM series_data GROUP BY codigo ORDER BY codigo",
                conn,
            )
            stats.to_csv(DATA_CACHE_DIR / "ci_cache_stats.csv", index=False)
    except Exception:
        pass

    print(f"\n🏁 Done at {datetime.now():%H:%M:%S}")
    sys.exit(0 if fail < total * 0.8 else 1)


if __name__ == "__main__":
    main()
