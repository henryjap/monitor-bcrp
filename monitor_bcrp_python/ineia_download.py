"""Headless download script for INEI SIRTOD (GitHub Actions).
Descarga indicadores del portal INEI usando Playwright.

Estrategia:
  - 3 pasadas: Anual â†’ Mensual â†’ Trimestral
  - Cada pasada descarga indicadores con prioridad (los del catÃ¡logo)
  - Omite los ya cacheados (a menos que --force)
  - Rate-limit entre requests para evitar corte de sesiÃ³n
  - Re-intenta indicadores fallidos al final

Uso:
    python ineia_download.py                          # descarga todo desde 1950
    python ineia_download.py --freq Mensual --max 10  # solo 10 mensuales desde 1950
    python ineia_download.py --start-year 1960        # cambia el inicio historico
    python ineia_download.py --force                  # re-descarga todo
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path
from random import uniform

import pandas as pd

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from inei_cache import INEICache


DEFAULT_START_YEAR = "1950"


def ensure_download_log(cache: INEICache) -> None:
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inei_download_log (
                rowkey TEXT,
                frequency TEXT,
                requested_start_year INTEGER,
                requested_end_year INTEGER,
                status TEXT,
                records INTEGER DEFAULT 0,
                min_fecha TEXT,
                max_fecha TEXT,
                error TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (rowkey, frequency, requested_start_year, requested_end_year)
            )
            """
        )


def already_attempted_range(
    cache: INEICache, rowkey: str, frequency: str, start_year: str, end_year: str
) -> bool:
    ensure_download_log(cache)
    with sqlite3.connect(cache.db_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM inei_download_log
            WHERE rowkey = ?
              AND frequency = ?
              AND requested_start_year <= ?
              AND requested_end_year >= ?
              AND status IN ('ok', 'empty')
            LIMIT 1
            """,
            (rowkey, frequency, int(start_year), int(end_year)),
        ).fetchone()
    return row is not None


def write_download_log(
    cache: INEICache,
    rowkey: str,
    frequency: str,
    start_year: str,
    end_year: str,
    status: str,
    df: pd.DataFrame | None = None,
    error: str = "",
) -> None:
    records = int(len(df)) if df is not None else 0
    min_fecha = ""
    max_fecha = ""
    if df is not None and not df.empty and "fecha" in df.columns:
        fechas = pd.to_datetime(df["fecha"], errors="coerce").dropna()
        if not fechas.empty:
            min_fecha = fechas.min().date().isoformat()
            max_fecha = fechas.max().date().isoformat()
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO inei_download_log
            (rowkey, frequency, requested_start_year, requested_end_year, status, records, min_fecha, max_fecha, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                rowkey,
                frequency,
                int(start_year),
                int(end_year),
                status,
                records,
                min_fecha,
                max_fecha,
                error[:500],
            ),
        )


def main():
    parser = argparse.ArgumentParser(description="Descarga indicadores INEI")
    parser.add_argument("--freq", choices=["Anual", "Mensual", "Trimestral"],
                        default=None, help="Solo esta frecuencia")
    parser.add_argument("--max", type=int, default=None,
                        help="MÃ¡ximo de indicadores a descargar")
    parser.add_argument("--force", action="store_true",
                        help="Re-descargar aunque ya estÃ©n cacheados")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay base entre requests (segundos)")
    parser.add_argument("--start-year", default=DEFAULT_START_YEAR,
                        help="AÃ±o inicial para descargar historia completa")
    parser.add_argument("--end-year", default=str(date.today().year),
                        help="AÃ±o final para descargar")
    args = parser.parse_args()

    print("=" * 60)
    print(f"INEI Data Downloader â€” {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)

    cache = INEICache()
    ensure_download_log(cache)
    catalog = cache.get_catalog()
    if catalog.empty:
        print("âŒ CatÃ¡logo vacÃ­o. Ejecuta update_catalog primero.")
        sys.exit(1)

    print(f"  ðŸ“„ CatÃ¡logo: {len(catalog)} indicadores")
    print(f"  Rango: {args.start_year}-{args.end_year}")

    status = cache.cache_status()
    previously_cached = status.get("total_series_descargadas", 0)
    print(f"  Solo se omiten series ya auditadas para {args.start_year}-{args.end_year}.")
    print(f"  Series con algun dato en cache: {previously_cached}")

    # Frecuencias a procesar
    freqs = [args.freq] if args.freq else ["Anual", "Mensual", "Trimestral"]

    total_ok = 0
    total_fail = 0
    total_skip = 0
    failed_codes = []

    for freq in freqs:
        print(f"\n{'=' * 40}")
        print(f"ðŸ“¥ Pasada: {freq}")
        print(f"{'=' * 40}")

        leaves = catalog.to_dict("records")
        if args.max:
            leaves = leaves[:args.max]

        freq_ok = 0
        freq_fail = 0
        freq_skip = 0

        for idx, leaf in enumerate(leaves, 1):
            rk = leaf["rowkey"]
            label = leaf["label"]

            # Saltar solo si el mismo rango ya fue auditado, no por tener datos parciales.
            if not args.force and already_attempted_range(cache, rk, freq, args.start_year, args.end_year):
                freq_skip += 1
                if idx % 100 == 0:
                    print(f"  [{idx}/{len(leaves)}] {freq}: {freq_skip} ya auditados para {args.start_year}-{args.end_year}...")
                continue

            # Descargar
            print(f"  [{idx}/{len(leaves)}] {label} ({rk})...", end=" ", flush=True)
            try:
                df = cache.fetch_and_cache(rk, freq, args.start_year, args.end_year)
                if not df.empty:
                    n = len(df)
                    print(f"âœ… {n} registros")
                    freq_ok += 1
                    write_download_log(cache, rk, freq, args.start_year, args.end_year, "ok", df)
                else:
                    print(f"âš ï¸  vacÃ­o")
                    freq_fail += 1
                    failed_codes.append(rk)
                    write_download_log(cache, rk, freq, args.start_year, args.end_year, "empty", df)
            except Exception as e:
                print(f"âŒ {str(e)[:100]}")
                freq_fail += 1
                failed_codes.append(rk)
                write_download_log(cache, rk, freq, args.start_year, args.end_year, "error", None, str(e))

            # Rate-limit aleatorio para evitar corte de sesiÃ³n
            if idx < len(leaves):
                delay = uniform(args.delay * 0.7, args.delay * 1.5)
                time.sleep(delay)

        total_ok += freq_ok
        total_fail += freq_fail
        total_skip += freq_skip
        print(f"\n  {freq}: {freq_ok} ok, {freq_fail} fail, {freq_skip} skip")

    # Retry para fallidos
    if failed_codes:
        print(f"\nðŸ” Retry: {len(failed_codes)} indicadores fallidos...")
        retry_ok = 0
        for idx, rk in enumerate(failed_codes, 1):
            label = catalog[catalog["rowkey"] == rk]["label"].values
            lbl = label[0] if len(label) else rk
            print(f"  [{idx}/{len(failed_codes)}] {lbl}...", end=" ", flush=True)
            try:
                for freq in freqs:
                    df = cache.fetch_and_cache(rk, freq, args.start_year, args.end_year)
                    if not df.empty:
                        retry_ok += 1
                        total_ok += 1
                        total_fail -= 1
                        write_download_log(cache, rk, freq, args.start_year, args.end_year, "ok", df)
                        print(f"âœ… (como {freq})")
                        break
                else:
                    print(f"âŒ")
            except Exception as e:
                print(f"âŒ {str(e)[:80]}")
            time.sleep(uniform(1.0, 2.0))
        print(f"  Retry recuperados: {retry_ok}")

    # Guardar resumen
    final_status = cache.cache_status()
    summary_path = HERE / "data_cache" / "inei_raw" / "ci_download_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "date": datetime.now().isoformat(),
        "freqs": freqs,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "downloaded": total_ok,
        "failed": total_fail,
        "skipped": total_skip,
        "total_cached_indicators": final_status.get("total_series_descargadas", 0),
        "total_cached_records": final_status.get("total_registros", 0),
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"âœ… Descargados: {total_ok} | Fallidos: {total_fail} | Omitidos: {total_skip}")
    print(f"ðŸ“Š Cache: {final_status.get('total_series_descargadas', 0)} indicadores, "
          f"{final_status.get('total_registros', 0)} registros")
    print(f"ðŸ Fin: {datetime.now():%H:%M:%S}")

    attempted = total_ok + total_fail
    if total_fail == 0:
        sys.exit(0)
    sys.exit(0 if attempted and total_fail < attempted * 0.8 else 1)


if __name__ == "__main__":
    main()
