"""Headless download script for GitHub Actions.
Downloads ALL BCRP series from metadata CSV and saves to cache."""

from datetime import date, datetime
from pathlib import Path
import csv
import json
import os
import sqlite3
import sys
import time

import pandas as pd
import requests

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from bcrp_monitor_core import (
    fetch_bcrp_series,
    fetch_bcrp_batch_series,
    clean_code,
)
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


def read_all_codes_from_metadata() -> list[str]:
    """Read ALL codes from the BCRP metadata CSV (~16,945 series)."""
    candidates = [
        HERE / "BCRPData-metadata-20260509-181936.csv",
        HERE / "BCRP_metadata_fusionada_nombre_serie_con_medicion.xlsx",
    ]
    for path in candidates:
        if path.exists():
            print(f"  📄 Reading codes from: {path.name}")
            if path.suffix == ".csv":
                df = pd.read_csv(path, encoding="latin1", sep=";", low_memory=False)
                col = df.columns[0]
            else:
                df = pd.read_excel(path)
                col = "codigo" if "codigo" in df.columns else df.columns[0]
            codes = (
                df[col].dropna().astype(str).str.strip().str.upper().unique().tolist()
            )
            codes = sorted([c for c in codes if c and c != "NAN" and c != "NONE"])
            print(f"     → {len(codes)} unique codes found")
            return codes
    return []


def read_catalog_codes() -> list[str]:
    """Fallback: read from the 264-catalog CSV."""
    path = HERE / "catalogo_bcrp_monitor_264.csv"
    if path.exists():
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            codes = sorted(
                set(
                    clean_code(r.get("codigo", ""))
                    for r in reader
                    if clean_code(r.get("codigo", ""))
                )
            )
            print(f"  📄 Using catalog: {len(codes)} codes")
            return codes
    from constants import DEFAULT_CODES

    codes = [c.strip() for c in DEFAULT_CODES.strip().split("\n") if c.strip()]
    print(f"  📄 Using DEFAULT_CODES fallback: {len(codes)} codes")
    return codes


def already_cached_count() -> int:
    """How many distinct codes already in DB."""
    try:
        init_db()
        with sqlite3.connect(local_series_db_path()) as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT codigo) FROM series_data"
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def main():
    print("=" * 60)
    print(f"BCRP Data Downloader — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    codes = read_all_codes_from_metadata()
    if not codes:
        codes = read_catalog_codes()

    if not codes:
        print("❌ No codes found to download.")
        sys.exit(1)

    already = already_cached_count()
    print(f"  🗄️  Already in cache DB: {already} series")

    end = date.today()
    start = date(2015, 1, 1)
    print(f"  📅 Range: {start} → {end}")
    print()

    # Batch size: keep URLs under ~2000 chars
    # Each code is ~9 chars, separator ~1 → ~10 per code → max ~150 per batch
    BATCH_SIZE = 50
    code_groups = [codes[i : i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    total = len(codes)
    ok = 0
    fail = 0
    skipped = 0
    errors = []
    last_save = time.time()

    print(
        f"⚙️  Fetching {total} series in {len(code_groups)} batches of {BATCH_SIZE}...\n"
    )

    for idx, group in enumerate(code_groups, 1):
        print(
            f"  [{idx}/{len(code_groups)}] batch of {len(group)}...",
            end=" ",
            flush=True,
        )
        try:
            series_map, meta_map = fetch_bcrp_batch_series(group, start, end)
            batch_ok = 0
            for code in group:
                df = series_map.get(code, pd.DataFrame())
                if df is not None and not df.empty:
                    save_to_cache(code, df)
                    batch_ok += 1
            ok += batch_ok
            fail += len(group) - batch_ok
            print(f"{batch_ok}/{len(group)} ok")

            # Save progress every 10 batches
            if time.time() - last_save > 30:
                print(f"     ⏺️  Checkpoint: {ok} ok, {fail} fail, {skipped} skip")
                last_save = time.time()

        except Exception as e:
            print(f"BATCH FAILED: {e}")
            # Fallback: retry each code individually
            batch_ok = 0
            for code in group:
                try:
                    df, meta = fetch_bcrp_series(code, start, end)
                    if df is not None and not df.empty:
                        save_to_cache(code, df)
                        batch_ok += 1
                        ok += 1
                    else:
                        fail += 1
                except Exception as e2:
                    fail += 1
                    errors.append(f"{code}: {e2}")
                time.sleep(0.2)
            print(f"     {batch_ok}/{len(group)} ok (individual fallback)")

        time.sleep(0.3)

    # Final stats
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
    print(f"✅ Result: {ok} downloaded, {fail} failed / {total} total")
    print(f"📊 Cache DB: {count} unique series, {total_rows} observations")

    if errors:
        print(f"\n⚠️  Errors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  • {e}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")

    # Save summaries
    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    summary = {
        "date": datetime.now().isoformat(),
        "total_codes": total,
        "downloaded": ok,
        "failed": fail,
        "cache_series": count,
        "cache_obs": total_rows,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "errors": errors[:50],
    }
    with open(DATA_CACHE_DIR / "ci_download_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  📝 Summary → data_cache/ci_download_summary.json")

    # Cache stats CSV
    try:
        with sqlite3.connect(local_series_db_path()) as conn:
            stats = pd.read_sql(
                "SELECT codigo, COUNT(*) as obs, MIN(fecha) as desde, MAX(fecha) as hasta FROM series_data GROUP BY codigo ORDER BY codigo",
                conn,
            )
            stats.to_csv(DATA_CACHE_DIR / "ci_cache_stats.csv", index=False)
            print(f"  📊 Stats   → data_cache/ci_cache_stats.csv")
    except Exception:
        pass

    print(f"\n🏁 Done at {datetime.now():%H:%M:%S}")
    sys.exit(0 if fail < total * 0.5 else 1)


if __name__ == "__main__":
    main()
