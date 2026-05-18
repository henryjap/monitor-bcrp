"""
INEI Data Cache — SQLite local cache para datos del INEI SIRTOD
Mismo patrón que el cache BCRP pero para fuente INEI.

Uso:
    cache = INEICache()
    cache.update_catalog()                   # descarga árbol de indicadores
    df = cache.get_series("0_1_0_0")         # carga desde SQLite
    df = cache.fetch_and_cache("0_1_0_0")    # descarga y guarda
"""
from __future__ import annotations
import json
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from inei_scraper import INEIScraper


class INEICache:
    def __init__(self, db_path: str | Path | None = None):
        self.app_dir = Path(__file__).parent
        self.cache_dir = self.app_dir / "data_cache" / "inei_raw"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else (
            self.cache_dir / "inei_cache.db"
        )
        self._init_db()
        self._scraper = None

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inei_catalog (
                    rowkey TEXT PRIMARY KEY,
                    label TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            # Migración: agregar frequency a PK si es necesario
            has_freq_pk = conn.execute("""
                SELECT sql FROM sqlite_master
                WHERE type='table' AND name='inei_series'
            """).fetchone()
            if has_freq_pk and "frequency" not in (has_freq_pk[0] or ""):
                conn.execute("ALTER TABLE inei_series RENAME TO inei_series_old")
                conn.execute("""
                    CREATE TABLE inei_series (
                        rowkey TEXT,
                        fecha TEXT,
                        valor REAL,
                        label TEXT,
                        frequency TEXT DEFAULT 'Anual',
                        downloaded_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (rowkey, frequency, fecha)
                    )
                """)
                conn.execute("""
                    INSERT INTO inei_series (rowkey, fecha, valor, label, frequency, downloaded_at)
                    SELECT rowkey, fecha, valor, label, 'Anual', downloaded_at
                    FROM inei_series_old
                """)
                conn.execute("DROP TABLE inei_series_old")
            else:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS inei_series (
                        rowkey TEXT,
                        fecha TEXT,
                        valor REAL,
                        label TEXT,
                        frequency TEXT DEFAULT 'Anual',
                        downloaded_at TEXT DEFAULT (datetime('now')),
                        PRIMARY KEY (rowkey, frequency, fecha)
                    )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inei_metadata (
                    rowkey TEXT PRIMARY KEY,
                    label TEXT,
                    json_data TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inei_freq_index (
                    rowkey TEXT,
                    frequency TEXT,
                    label TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (rowkey, frequency)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inei_download_progress (
                    rowkey TEXT,
                    frequency TEXT,
                    label TEXT DEFAULT '',
                    estado TEXT DEFAULT 'pendiente',
                    intentos INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    downloaded_at TEXT,
                    PRIMARY KEY (rowkey, frequency)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inei_series_rowkey ON inei_series(rowkey)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inei_series_fecha ON inei_series(fecha)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inei_freq_freq ON inei_freq_index(frequency)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_inei_dl_estado ON inei_download_progress(estado)")

    def _scraper_instance(self) -> INEIScraper:
        if self._scraper is None:
            self._scraper = INEIScraper(headless=True)
        return self._scraper

    # ----------------------------------------------------------------
    #  Catálogo
    # ----------------------------------------------------------------
    def update_freq_catalog(self, freq: str) -> int:
        """Explora el árbol para una frecuencia y guarda los indicadores
        seleccionables en inei_freq_index."""
        scraper = self._scraper_instance()
        nodes = scraper.explore_indicators_by_frequency(freq)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM inei_freq_index WHERE frequency = ?", (freq,)
            )
            conn.executemany(
                "INSERT OR REPLACE INTO inei_freq_index (rowkey, frequency, label) VALUES (?, ?, ?)",
                [(n["rowkey"], freq, n["label"]) for n in nodes]
            )
        # Guardar JSON también
        path = self.cache_dir / f"inei_freq_{freq.lower()}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(nodes, f, indent=2, ensure_ascii=False)
        return len(nodes)

    def get_indicators(self, frequency: str | None = None) -> pd.DataFrame:
        """Devuelve catálogo de indicadores, opcionalmente filtrado por frecuencia."""
        with sqlite3.connect(self.db_path) as conn:
            if frequency:
                return pd.read_sql_query(
                    "SELECT rowkey, label, frequency FROM inei_freq_index WHERE frequency = ? ORDER BY label",
                    conn, params=(frequency,)
                )
            return pd.read_sql_query(
                "SELECT DISTINCT rowkey, label FROM inei_freq_index ORDER BY label", conn
            )

    def freq_catalog_status(self) -> dict:
        """Estado del catálogo por frecuencia."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT frequency, COUNT(*) as cnt FROM inei_freq_index GROUP BY frequency"
            ).fetchall()
        result = {"total_indicadores": 0}
        for freq, cnt in rows:
            result[freq] = cnt
            result["total_indicadores"] += cnt
        return result

    def update_catalog(self, max_depth: int = 99) -> int:
        """Descarga y guarda el árbol completo de indicadores."""
        scraper = self._scraper_instance()
        nodes = scraper.fetch_indicators_tree(max_depth=max_depth)
        leaves = scraper.get_leaves(nodes)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM inei_catalog")
            conn.executemany(
                "INSERT OR REPLACE INTO inei_catalog (rowkey, label) VALUES (?, ?)",
                [(l["rowkey"], l["label"]) for l in leaves]
            )
        # Guardar JSON también
        with open(self.cache_dir / "inei_catalog.json", "w", encoding="utf-8") as f:
            json.dump(leaves, f, indent=2, ensure_ascii=False)
        return len(leaves)

    def get_catalog(self, frequency: str | None = None) -> pd.DataFrame:
        """Devuelve el catálogo de indicadores como DataFrame.
        Si se especifica frequency, filtra solo los disponibles en esa frecuencia.
        Si inei_freq_index está vacío, cae al viejo inei_catalog."""
        with sqlite3.connect(self.db_path) as conn:
            if frequency:
                df = pd.read_sql_query(
                    "SELECT rowkey, label, frequency FROM inei_freq_index WHERE frequency = ? ORDER BY label",
                    conn, params=(frequency,)
                )
                if not df.empty:
                    return df
                return pd.DataFrame(columns=["rowkey", "label", "frequency"])
            # Sin frecuencia: probar freq_index primero
            df = pd.read_sql_query(
                "SELECT DISTINCT rowkey, label FROM inei_freq_index ORDER BY label", conn
            )
            if not df.empty:
                return df
            # Fallback al viejo catálogo
            return pd.read_sql_query(
                "SELECT rowkey, label FROM inei_catalog ORDER BY rowkey", conn
            )

    def search_indicators(self, query: str, frequency: str | None = None) -> pd.DataFrame:
        """Busca indicadores por nombre."""
        df = self.get_catalog(frequency=frequency)
        if df.empty:
            return df
        return df[df["label"].str.lower().str.contains(query.lower(), na=False)]

    # ----------------------------------------------------------------
    #  Series
    # ----------------------------------------------------------------
    def get_series(
        self, rowkey: str, start_year: int | None = None,
        end_year: int | None = None, frequency: str = "Anual"
    ) -> pd.DataFrame:
        """Carga datos de un indicador desde la caché local por frecuencia."""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                "SELECT fecha, valor, label, frequency FROM inei_series WHERE rowkey = ? AND frequency = ? ORDER BY fecha",
                conn, params=(rowkey, frequency)
            )
        if df.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        if start_year:
            df = df[df["fecha"].dt.year >= start_year]
        if end_year:
            df = df[df["fecha"].dt.year <= end_year]
        return df.reset_index(drop=True)

    def fetch_and_cache(
        self, rowkey: str, frequency: str = "Anual",
        start_year: str = "2010", end_year: str | None = None,
    ) -> pd.DataFrame:
        """Descarga datos del portal y los guarda en caché."""
        scraper = self._scraper_instance()
        df = scraper.fetch_series(rowkey, frequency, start_year, end_year)

        # Buscar label en catálogo
        label = rowkey
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT label FROM inei_catalog WHERE rowkey = ?", (rowkey,)
            )
            row = cur.fetchone()
            if row:
                label = row[0]

        if not df.empty:
            df["rowkey"] = rowkey
            df["label"] = label
            df["frequency"] = frequency
            self._save_bulk(df)

        return df

    def _save_bulk(self, df: pd.DataFrame):
        """Guarda datos en SQLite (upsert)."""
        if df.empty or "rowkey" not in df.columns or "fecha" not in df.columns:
            return
        temp = df[["rowkey", "fecha", "valor", "label", "frequency"]].copy()
        temp["fecha"] = pd.to_datetime(temp["fecha"]).dt.strftime("%Y-%m-%d")
        temp["valor"] = pd.to_numeric(temp["valor"], errors="coerce")
        temp = temp.dropna(subset=["fecha", "valor"]).drop_duplicates(
            subset=["rowkey", "frequency", "fecha"], keep="last"
        )
        if temp.empty:
            return
        with sqlite3.connect(self.db_path) as conn:
            temp.to_sql("_inei_temp", conn, if_exists="replace", index=False)
            conn.execute("""
                INSERT OR REPLACE INTO inei_series (rowkey, fecha, valor, label, frequency)
                SELECT rowkey, fecha, valor, label, frequency FROM _inei_temp
            """)
            conn.execute("DROP TABLE _inei_temp")

    def cache_status(self) -> dict:
        """Estado de la caché."""
        with sqlite3.connect(self.db_path) as conn:
            total_catalog = conn.execute(
                "SELECT COUNT(*) FROM inei_catalog"
            ).fetchone()[0]
            total_indicators_with_data = conn.execute(
                "SELECT COUNT(DISTINCT rowkey) FROM inei_series"
            ).fetchone()[0]
            total_series = conn.execute(
                "SELECT COUNT(*) FROM (SELECT rowkey, frequency FROM inei_series GROUP BY rowkey, frequency)"
            ).fetchone()[0]
            total_records = conn.execute(
                "SELECT COUNT(*) FROM inei_series"
            ).fetchone()[0]
            last_date = conn.execute(
                "SELECT MAX(downloaded_at) FROM inei_series"
            ).fetchone()[0]
            freq_breakdown = conn.execute(
                "SELECT frequency, COUNT(*) as cnt, COUNT(DISTINCT rowkey) as indicators FROM inei_series GROUP BY frequency"
            ).fetchall()
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        result = {
            "total_indicadores_catalog": total_catalog,
            "total_indicadores_con_datos": total_indicators_with_data,
            "total_series_descargadas": total_series,
            "total_registros": total_records,
            "ultima_descarga": last_date or "Nunca",
            "tamano_db_mb": round(db_size / (1024 * 1024), 2),
        }
        for freq, cnt, inds in freq_breakdown:
            result[f"registros_{freq.lower()}"] = cnt
            result[f"indicadores_{freq.lower()}"] = inds
        return result

    # ----------------------------------------------------------------
    #  Batch
    # ----------------------------------------------------------------
    def download_all(
        self, frequency: str = "Anual",
        start_year: str = "1950", end_year: str | None = None,
        max_items: int | None = None,
    ) -> pd.DataFrame:
        """Descarga todos los indicadores del catálogo."""
        catalog = self.get_catalog()
        if catalog.empty:
            print("Catálogo vacío. Ejecuta update_catalog() primero.")
            return pd.DataFrame()
        leaves = catalog.to_dict("records")
        if max_items:
            leaves = leaves[:max_items]
        all_dfs = []
        total = len(leaves)
        for idx, leaf in enumerate(leaves):
            rk = leaf["rowkey"]
            label = leaf["label"]
            print(f"[{idx+1}/{total}] {label} ({rk})")
            try:
                df = self.fetch_and_cache(rk, frequency, start_year, end_year)
                if not df.empty:
                    all_dfs.append(df)
                    print(f"  -> {len(df)} registros")
                else:
                    print(f"  -> vacío")
            except Exception as e:
                print(f"  -> Error: {e}")
            time.sleep(0.5)
        if all_dfs:
            return pd.concat(all_dfs, ignore_index=True)
        return pd.DataFrame()


if __name__ == "__main__":
    cache = INEICache()

    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "update_catalog":
        n = cache.update_catalog(max_depth=50)
        print(f"Catálogo actualizado: {n} indicadores")

    elif cmd == "catalog":
        df = cache.get_catalog()
        print(df.to_string())

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else "población"
        df = cache.search_indicators(q)
        print(f"Resultados para '{q}': {len(df)}")
        print(df.to_string())

    elif cmd == "fetch":
        rk = sys.argv[2] if len(sys.argv) > 2 else "0_1_0_0"
        freq = sys.argv[3] if len(sys.argv) > 3 else "Anual"
        df = cache.fetch_and_cache(rk, freq, "1950", str(date.today().year))
        print(f"Descargados {len(df)} registros ({freq})")
        print(df.head(10))

    elif cmd == "get":
        rk = sys.argv[2] if len(sys.argv) > 2 else "0_1_0_0"
        freq = sys.argv[3] if len(sys.argv) > 3 else "Anual"
        df = cache.get_series(rk, 2010, 2024, frequency=freq)
        print(f"Cargados {len(df)} registros desde caché ({freq})")
        print(df.head(10))

    elif cmd == "status":
        st = cache.cache_status()
        for k, v in st.items():
            print(f"{k}: {v}")

    elif cmd == "download_all":
        freq = sys.argv[2] if len(sys.argv) > 2 else "Anual"
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        df = cache.download_all(frequency=freq, max_items=n)
        print(f"\nTotal descargado: {len(df)} registros de {df['label'].nunique() if not df.empty else 0} indicadores")

    elif cmd == "explore_freq":
        freq = sys.argv[2] if len(sys.argv) > 2 else "Anual"
        n = cache.update_freq_catalog(freq)
        print(f"Indexados {n} indicadores para {freq}")

    elif cmd == "freq_status":
        st = cache.freq_catalog_status()
        for k, v in st.items():
            print(f"{k}: {v}")
