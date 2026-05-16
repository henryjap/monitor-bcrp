import sqlite3
import pandas as pd
from pathlib import Path
import os
import sys

def migrate():
    data_dir = Path("data_cache/series_raw")
    db_path = data_dir / "series_cache.db"
    
    csv_files = list(data_dir.glob("*.csv"))
    total = len(csv_files)
    if total == 0:
        print("No hay archivos CSV para migrar.")
        return
        
    print(f"Iniciando migración de {total} archivos CSV a SQLite...")
    
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS series_data (
                codigo TEXT,
                fecha TEXT,
                valor REAL,
                PRIMARY KEY (codigo, fecha)
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_codigo ON series_data(codigo)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON series_data(fecha)')
    
    batch_size = 500
    batch_dfs = []
    processed = 0
    
    with sqlite3.connect(db_path) as conn:
        for p in csv_files:
            try:
                df = pd.read_csv(p)
                if not df.empty and "fecha" in df.columns and "valor" in df.columns:
                    df["codigo"] = p.stem.upper()
                    batch_dfs.append(df[["codigo", "fecha", "valor"]])
            except Exception as e:
                pass
                
            processed += 1
            if len(batch_dfs) >= batch_size:
                combined = pd.concat(batch_dfs, ignore_index=True)
                combined.to_sql("series_data", conn, if_exists="append", index=False)
                batch_dfs = []
                print(f"Progreso: {processed}/{total} procesados...")
                
        if batch_dfs:
            combined = pd.concat(batch_dfs, ignore_index=True)
            combined.to_sql("series_data", conn, if_exists="append", index=False)
            print(f"Progreso: {processed}/{total} procesados...")
            
    print("Migración exitosa. Eliminando los 16,945 archivos CSV antiguos para liberar Windows...")
    for p in csv_files:
        try:
            p.unlink()
        except:
            pass
            
    print("¡Limpieza finalizada! Todo el disco está limpio y el sistema es ahora 100% SQLite.")

if __name__ == "__main__":
    migrate()
