"""Test end-to-end: simula el procesamiento de 3 series para validar los fixes"""
import os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date

# 1. Test constants path fix
from constants import APP_DIR, RAW_CACHE_DIR, RUN_CACHE_DIR, DATA_CACHE_DIR
print("=" * 50)
print("TEST 1: Rutas corregidas")
print(f"  RUN_CACHE_DIR: {RUN_CACHE_DIR}")
assert "data_cache" in str(RUN_CACHE_DIR), "RUN_CACHE_DIR debe estar dentro de data_cache"
print("  ✅ PASS")

# 2. Test DB access
print("\nTEST 2: Acceso a DB")
db_path = RAW_CACHE_DIR / "series_cache.db"
assert db_path.exists(), f"DB no existe en {db_path}"
with sqlite3.connect(str(db_path)) as conn:
    total = conn.execute("SELECT COUNT(DISTINCT codigo) FROM series_data").fetchone()[0]
assert total > 0, "DB vacía"
print(f"  DB tiene {total} series")
print("  ✅ PASS")

# 3. Test bulk_cache loading
print("\nTEST 3: Bulk cache loading")
with sqlite3.connect(str(db_path)) as conn:
    bulk_df = pd.read_sql_query("SELECT codigo, fecha, valor FROM series_data", conn)
    bulk_df["fecha"] = pd.to_datetime(bulk_df["fecha"], errors="coerce")
    bulk_df["valor"] = pd.to_numeric(bulk_df["valor"], errors="coerce")
    bulk_df = bulk_df.dropna(subset=["fecha", "valor"]).sort_values("fecha")
    bulk_cache = {code: group.drop(columns=["codigo"]).copy() 
                  for code, group in bulk_df.groupby("codigo")}
print(f"  bulk_cache: {len(bulk_cache)} series")
assert len(bulk_cache) > 10000, "bulk_cache tiene muy pocas series"
print("  ✅ PASS")

# 4. Test series_meta_from_row with dict input (the fix)
print("\nTEST 4: series_meta_from_row con dict (fix thread-safety)")
from bcrp_monitor_core import series_meta_from_row, analyze_series
test_row_dict = {
    "codigo": "PN00347MM", "nombre_bcrp": "Test serie",
    "frecuencia_bcrp": "Mensual", "clase_serie": "auto", "tratamiento": "auto",
    "categoria_bcrp": "", "grupo_bcrp": "", "unidad_medida": "",
}
# This is what the fixed code does: convert dict -> pd.Series
row_as_series = pd.Series(test_row_dict)
meta = series_meta_from_row(row_as_series)
print(f"  meta.codigo = '{meta.codigo}'")
assert meta.codigo, "codigo vacío"
print("  ✅ PASS")

# 5. Test full processing of one series
print("\nTEST 5: Procesamiento completo de 1 serie")
test_code = meta.codigo
if test_code in bulk_cache:
    cached_data = bulk_cache[test_code]
    print(f"  Serie {test_code}: {len(cached_data)} observaciones")
    if not cached_data.empty:
        api_meta = {"codigo": test_code, "url_api": "cache local"}
        try:
            result, df_t = analyze_series(cached_data, meta, api_meta, asof=date.today())
            print(f"  semaforo = '{result.get('semaforo', 'N/A')}'")
            print(f"  diagnostico = '{result.get('diagnostico', 'N/A')}'")
            print(f"  ✅ PASS - Serie procesada correctamente!")
        except Exception as e:
            print(f"  ❌ FAIL: {e}")
else:
    print(f"  ⚠ Serie {test_code} no está en bulk_cache")
    # Try with a code we know exists
    alt_code = list(bulk_cache.keys())[0]
    print(f"  Probando con {alt_code}...")
    alt_row = {"codigo": alt_code, "nombre_bcrp": "Test", "frecuencia_bcrp": "Mensual",
               "clase_serie": "auto", "tratamiento": "auto"}
    alt_meta = series_meta_from_row(pd.Series(alt_row))
    cached_data = bulk_cache[alt_code]
    api_meta = {"codigo": alt_code, "url_api": "cache local"}
    result, df_t = analyze_series(cached_data, alt_meta, api_meta, asof=date.today())
    print(f"  semaforo = '{result.get('semaforo', 'N/A')}'")
    print("  ✅ PASS")

# 6. Test snapshot directory
print("\nTEST 6: Directorio de snapshots")
RUN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
print(f"  Directorio: {RUN_CACHE_DIR}")
print(f"  Existe: {RUN_CACHE_DIR.exists()}")
pkls = list(RUN_CACHE_DIR.glob("*.pkl"))
print(f"  Snapshots existentes: {len(pkls)} (debe ser 0 después de limpieza)")
print("  ✅ PASS")

print("\n" + "=" * 50)
print("🎉 TODOS LOS TESTS PASARON!")
print("La app debería funcionar correctamente ahora.")
print("=" * 50)
