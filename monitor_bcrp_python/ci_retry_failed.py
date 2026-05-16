"""Retry failed BCRP series individually with proper retry logic."""

from datetime import date, datetime
from pathlib import Path
import json
import sqlite3
import sys
import time

import pandas as pd

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from bcrp_monitor_core import fetch_bcrp_series, clean_code
from constants import RAW_CACHE_DIR, DATA_CACHE_DIR


def local_series_db_path() -> Path:
    p = RAW_CACHE_DIR / "series_cache.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db():
    db_path = local_series_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS series_data (
                codigo TEXT,
                fecha TEXT,
                valor REAL,
                PRIMARY KEY (codigo, fecha)
            )
        """)
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


def get_cached_codes() -> set:
    try:
        init_db()
        with sqlite3.connect(local_series_db_path()) as conn:
            rows = conn.execute("SELECT DISTINCT codigo FROM series_data").fetchall()
            return {r[0] for r in rows}
    except Exception:
        return set()


def main():
    print("=" * 60)
    print(f"BCRP Retry Failed Series — {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    # Read all codes from metadata
    csv_path = HERE / "BCRPData-metadata-20260509-181936.csv"
    if not csv_path.exists():
        print("❌ Metadata CSV not found")
        sys.exit(1)
    meta = pd.read_csv(csv_path, encoding="latin1", sep=";", low_memory=False)
    all_codes = set(
        meta.iloc[:, 0].dropna().astype(str).str.strip().str.upper().unique()
    )
    cached = get_cached_codes()
    failed_codes = sorted(all_codes - cached)
    print(f"  Total metadata: {len(all_codes)}")
    print(f"  Cached: {len(cached)}")
    print(f"  Failed to retry: {len(failed_codes)}")

    # Categories the user wants to prioritize
    priority_cats = [
        "Exportaciones e importaciones",
        "Banco Central de Reserva",
        "Producción",
        "Expectativas Empresariales",
        "Empresas bancarias",
        "Otros no categorizados",
    ]
    # Filter to priority + any other non-historical categories
    cat_col = meta.columns[1]
    meta_subset = meta[
        meta.iloc[:, 0].astype(str).str.strip().str.upper().isin(failed_codes)
    ]
    priority = meta_subset[meta_subset[cat_col].isin(priority_cats)]
    other = meta_subset[
        ~meta_subset[cat_col].isin(
            [
                *priority_cats,
                "Periodo colonial temprano",
                "Periodo colonial tardío",
                "Primera centuria independiente",
            ]
        )
    ]

    codes_to_retry = sorted(
        set(
            list(priority.iloc[:, 0].astype(str).str.strip().str.upper().unique())
            + list(other.iloc[:, 0].astype(str).str.strip().str.upper().unique())
        )
    )
    print(f"  Codes to retry: {len(codes_to_retry)} (excluding pure historical)")

    if not codes_to_retry:
        print("✅ Nothing to retry.")
        sys.exit(0)

    end = date.today()
    start = date(1990, 1, 1)
    print(f"  📅 Range: {start} → {end}")
    print()

    ok = 0
    fail = 0
    errors = []

    for idx, code in enumerate(codes_to_retry, 1):
        print(f"  [{idx}/{len(codes_to_retry)}] {code}...", end=" ", flush=True)
        try:
            df, meta_info = fetch_bcrp_series(code, start, end)
            if df is not None and not df.empty:
                save_to_cache(code, df)
                ok += 1
                print("✅")
            else:
                fail += 1
                print("❌ empty")
                errors.append(f"{code}: empty response")
        except Exception as e:
            fail += 1
            msg = str(e).split("\n")[0][:100]
            print(f"❌ {msg}")
            errors.append(f"{code}: {msg}")
        time.sleep(0.3)

    # Stats
    new_cached = get_cached_codes()
    print(f"\n{'=' * 60}")
    print(f"✅ Retry complete: {ok} downloaded, {fail} failed")
    print(f"📊 Total cached now: {len(new_cached)} / {len(all_codes)} series")

    if errors:
        print(f"\n⚠️  Remaining errors ({len(errors)}):")
        for e in errors[:20]:
            print(f"  • {e}")

    DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_CACHE_DIR / "retry_summary.json", "w") as f:
        json.dump(
            {
                "date": datetime.now().isoformat(),
                "retried": len(codes_to_retry),
                "downloaded": ok,
                "failed": fail,
                "total_cached": len(new_cached),
            },
            f,
            indent=2,
        )

    sys.exit(0 if fail < len(codes_to_retry) * 0.8 else 1)


if __name__ == "__main__":
    main()
