"""Master download script for INEI — llena la cache completa desde 1950.

Modos:
    python ineia_download_all.py --freq Anual --all
    python ineia_download_all.py --freq Mensual --chunk 2 5
    python ineia_download_all.py --resume
    python ineia_download_all.py --status
"""
from __future__ import annotations

import argparse
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


FREQUENCIES = ["Trimestral", "Mensual", "Anual"]
# Año histórico por frecuencia
HISTORICAL_START = {"Anual": 1950, "Mensual": 2000, "Trimestral": 2000}
MAX_RETRIES = 3


def init_progress(cache: INEICache, freq: str):
    """Llena inei_download_progress con indicadores pendientes."""
    indicators = cache.get_indicators(frequency=freq)
    if indicators.empty:
        from_cache = cache.get_catalog()
        if not from_cache.empty:
            indicators = from_cache.copy()
            indicators["frequency"] = freq
    if indicators.empty:
        print("No hay indicadores en el catálogo para", freq)
        return
    with sqlite3.connect(cache.db_path) as conn:
        for _, row in indicators.iterrows():
            conn.execute(
                """INSERT OR IGNORE INTO inei_download_progress
                   (rowkey, frequency, label, estado)
                   VALUES (?, ?, ?, 'pendiente')""",
                (row["rowkey"], freq, row.get("label", "")),
            )


def get_pending(cache: INEICache, freq: str) -> list[dict]:
    """Obtiene indicadores pendientes de descargar."""
    with sqlite3.connect(cache.db_path) as conn:
        rows = conn.execute(
            """SELECT rowkey, frequency, label, intentos, error
               FROM inei_download_progress
               WHERE frequency = ? AND estado IN ('pendiente', 'fallido')
               AND intentos < ?
               ORDER BY rowkey""",
            (freq, MAX_RETRIES),
        ).fetchall()
    return [
        {"rowkey": r[0], "frequency": r[1], "label": r[2],
         "intentos": r[3], "error": r[4]}
        for r in rows
    ]


def mark(cache: INEICache, rowkey: str, freq: str, estado: str, error: str = ""):
    with sqlite3.connect(cache.db_path) as conn:
        conn.execute(
            """UPDATE inei_download_progress
               SET estado = ?, intentos = intentos + 1, error = ?,
                   downloaded_at = CASE WHEN ? = 'completado' THEN datetime('now') ELSE downloaded_at END
               WHERE rowkey = ? AND frequency = ?""",
            (estado, error, estado, rowkey, freq),
        )


def progress_summary(cache: INEICache, freq: str) -> dict:
    with sqlite3.connect(cache.db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM inei_download_progress WHERE frequency = ?", (freq,)
        ).fetchone()[0]
        done = conn.execute(
            "SELECT COUNT(*) FROM inei_download_progress WHERE frequency = ? AND estado = 'completado'", (freq,)
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM inei_download_progress WHERE frequency = ? AND estado = 'fallido'", (freq,)
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM inei_download_progress WHERE frequency = ? AND estado = 'pendiente'", (freq,)
        ).fetchone()[0]
    return {"total": total, "completado": done, "fallido": failed, "pendiente": pending}


LOOKBACK_YEARS = 3  # años hacia atrás para descarga incremental


def _incremental_start(cache: INEICache, rk: str, freq: str) -> str:
    """Calcula año de inicio para descarga incremental.
    - Si hay datos cacheados: pide desde (último año - LOOKBACK)
      para cubrir revisiones retroactivas del INEI.
    - Si no hay datos: año histórico completo."""
    with sqlite3.connect(cache.db_path) as conn:
        row = conn.execute(
            "SELECT MAX(fecha) FROM inei_series WHERE rowkey = ? AND frequency = ?",
            (rk, freq),
        ).fetchone()
    if row and row[0]:
        latest_year = int(str(row[0])[:4])
        start = max(latest_year - LOOKBACK_YEARS, 2000)
        return str(start)
    return str(HISTORICAL_START.get(freq, 2000))


def download_loop(cache: INEICache, freq: str, chunk: int | None = None,
                  total_chunks: int | None = None, delay: float = 1.5,
                  deep: bool = False):
    """Bucle de descarga con progreso.
    Si deep=False, descarga incremental (solo últimos LOOKBACK años).
    Si deep=True, descarga desde año histórico completo."""
    init_progress(cache, freq)
    pending = get_pending(cache, freq)

    if total_chunks and chunk:
        chunk_size = max(1, len(pending) // total_chunks)
        start = (chunk - 1) * chunk_size
        end = start + chunk_size if chunk < total_chunks else len(pending)
        pending = pending[start:end]
        print(f"  Chunk {chunk}/{total_chunks}: {len(pending)} indicadores")

    total = len(pending)
    if total == 0:
        print(f"  ✅ No hay pendientes para {freq}")
        return

    start_time = time.time()
    ok = fail = 0

    for idx, item in enumerate(pending, 1):
        rk = item["rowkey"]
        lbl = item["label"] or rk
        end_yr = str(date.today().year)
        if deep:
            start_yr = str(HISTORICAL_START.get(freq, 2000))
        else:
            start_yr = _incremental_start(cache, rk, freq)

        elapsed = time.time() - start_time
        rate = idx / elapsed if elapsed > 0 else 0
        eta = (total - idx) / rate if rate > 0 else 0

        print(f"  [{idx}/{total}] {lbl} ({rk})  "
              f"[{elapsed/60:.0f}m ETA {eta/60:.0f}m] {start_yr}-{end_yr}...",
              end=" ", flush=True)

        try:
            df = cache.fetch_and_cache(rk, freq, start_yr, end_yr)
            n = len(df) if not df.empty else 0
            mark(cache, rk, freq, "completado")
            print(f"✅ {n} registros")
            ok += 1
        except Exception as e:
            err_msg = str(e)[:200]
            mark(cache, rk, freq, "fallido", err_msg)
            print(f"❌ {err_msg[:80]}")
            fail += 1

        # Rate limit con jitter
        if idx < total:
            time.sleep(uniform(delay * 0.6, delay * 1.4))

    elapsed = time.time() - start_time
    print(f"\n  {freq}: {ok} ok, {fail} fail de {total} en {elapsed/60:.1f}m")


def show_status(cache: INEICache):
    print("\n=== Estado de descarga masiva ===\n")
    for freq in FREQUENCIES:
        ps = progress_summary(cache, freq)
        if ps["total"] > 0:
            pct = ps["completado"] / ps["total"] * 100
            bar = "#" * int(pct / 2) + "." * (50 - int(pct / 2))
            print(f"  {freq:12s} [{bar}] {ps['completado']}/{ps['total']} "
                  f"({pct:.0f}%)  F:{ps['fallido']} P:{ps['pendiente']}")
        else:
            print(f"  {freq:12s}  Sin datos de progreso")


def main():
    parser = argparse.ArgumentParser(description="Descarga masiva INEI")
    parser.add_argument("--freq", choices=FREQUENCIES,
                        help="Frecuencia a descargar")
    parser.add_argument("--all", action="store_true",
                        help="Descargar todos los indicadores de la frecuencia")
    parser.add_argument("--chunk", type=int, nargs=2, metavar=("N", "TOTAL"),
                        help="Descargar chunk N de TOTAL (ej. --chunk 1 5)")
    parser.add_argument("--resume", action="store_true",
                        help="Reanudar descargas fallidas/pendientes")
    parser.add_argument("--status", action="store_true",
                        help="Mostrar estado del progreso")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay entre requests (segundos)")
    parser.add_argument("--deep", action="store_true",
                        help="Re-descargar desde año histórico completo (no incremental)")
    args = parser.parse_args()

    cache = INEICache()

    if args.status:
        show_status(cache)
        return

    if args.resume:
        # Reanudar frecuencias que tengan pendientes
        for freq in FREQUENCIES:
            mode = "íntegra" if args.deep else "incremental"
            ps = progress_summary(cache, freq)
            pending_count = ps["pendiente"] + ps["fallido"]
            if pending_count > 0:
                print(f"\n📥 Reanudando {freq} ({pending_count} pendientes, modo {mode})")
                download_loop(cache, freq, delay=args.delay, deep=args.deep)
        return

    if not args.freq:
        print("Especifica --freq (o --resume / --status)")
        parser.print_help()
        sys.exit(1)

    mode = "íntegra" if args.deep else "incremental"
    if args.all:
        print(f"\n📥 Descarga {mode} de {args.freq}")
        download_loop(cache, args.freq, delay=args.delay, deep=args.deep)
    elif args.chunk:
        n, total = args.chunk
        print(f"\n📥 Chunk {n}/{total} de {args.freq} ({mode})")
        download_loop(cache, args.freq, chunk=n, total_chunks=total,
                      delay=args.delay, deep=args.deep)

    # Resumen final
    print("\n=== Resumen final ===")
    show_status(cache)

    # Guardar summary JSON
    summary_path = HERE / "data_cache" / "inei_raw" / "download_all_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {"date": datetime.now().isoformat(), "freqs": {}}
    for freq in FREQUENCIES:
        ps = progress_summary(cache, freq)
        summary["freqs"][freq] = ps
    import json
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
