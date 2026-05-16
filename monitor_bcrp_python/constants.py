import os
from pathlib import Path

# Get the absolute path of the directory where this file is located
CURRENT_FILE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = CURRENT_FILE_DIR
METADATA_DIR = APP_DIR

SNAPSHOT_DIR = APP_DIR / "snapshots"
DATA_CACHE_DIR = APP_DIR / "data_cache"
RUN_CACHE_DIR = DATA_CACHE_DIR / "run_snapshots"
RAW_CACHE_DIR = DATA_CACHE_DIR / "series_raw"
ANALYSIS_CACHE_DIR = DATA_CACHE_DIR / "analysis"

FETCH_CACHE_VERSION = "annual-refresh-2026-05-13"
ANALYSIS_CACHE_VERSION = "taxonomy-categoria-grupo-seccion-2026-05-16"

DEFAULT_CODES = "PN01728AM\nPN01271PM\nPN01273PM\nPD04719XD\nPD12301MD\nPD04718XD\nPD04720XD\nPD04692MD\nPD04709XD\nPN38051GM"

UPDATE_PHASES = [
    ("D", "diarias", "Diarias"),
    ("M", "mensuales", "Mensuales"),
    ("Q", "trimestrales", "Trimestrales"),
    ("A", "anuales", "Anuales"),
]
UPDATE_PHASE_LABELS = {code: label for code, _name, label in UPDATE_PHASES}
UPDATE_PHASE_NAMES = {code: name for code, name, _label in UPDATE_PHASES}

DEFAULT_METADATA_PATH = "BCRP_metadata_fusionada_nombre_serie_con_medicion.xlsx"
DEFAULT_VARIABLE_CLASSIFICATION_PATH = str(Path.home() / "Downloads" / "BCRP_metadata_clasificacion_variables.xlsx")
DEFAULT_OVERRIDES_PATH = "overrides_clasificacion_bcrp.csv"

SEMAFORO_COLORS = {
    "Al alza": "#175CD3", "Normal": "#067647", "A la baja": "#B42318", "Sin datos": "#667085",
    "Rojo": "#B42318", "Amarillo": "#B7791F", "Verde": "#067647", "Gris": "#667085",
}

SEMAFORO_BG = {
    "Al alza": "#D1E9FF", "Normal": "#DCFAE6", "A la baja": "#FEE4E2", "Sin datos": "#EAECF0",
    "Rojo": "#FEE4E2", "Amarillo": "#FEF0C7", "Verde": "#DCFAE6", "Gris": "#EAECF0",
}

SEMAFORO_ORDER = ["Al alza", "Normal", "A la baja", "Sin datos"]

DISPLAY_NAMES = {
    "semaforo": "Régimen", "regimen_tendencia": "Régimen tendencia", "diagnostico": "Diagnóstico",
    "codigo": "Código", "nombre_bcrp": "Nombre", "categoria_bcrp": "Categoría", "clase_serie": "Clase",
    "grupo_bcrp": "Grupo", "seccion_bcrp": "Sección",
    "frecuencia_bcrp": "Frecuencia", "fecha_inicio_meta": "Inicio fuente", "tipo_variable": "Tipo",
    "subtipo_variable": "Subtipo", "ventana_variacion": "Ventana", "categoria_operativa": "Cat. Operativa",
    "ultima_fecha": "Última fecha", "dias_desde_ultimo_dato": "Días sin actualizar", "estado_actualizacion": "Actualización",
    "fecha_dato_actual": "Fecha actual", "dato_actual_original": "Actual", "fecha_dato_anterior": "Fecha anterior",
    "dato_anterior_original": "Anterior", "fecha_dato_anio_anterior": "Fecha año previo",
    "dato_anio_anterior_original": "Año previo", "dato_actual_analisis": "Actual tratado",
    "dato_anterior_analisis": "Anterior tratado", "dato_anio_anterior_analisis": "Año previo tratado",
    "var_interanual_pct": "Var. interanual %", "posicion_vs_tendencia": "Posición vs tendencia",
    "percentil_historico_ultimo": "Percentil histórico", "tendencia_12m_cambio": "Cambio 12m",
    "tendencia_12m_pendiente": "Pendiente 12m", "tendencia_12m_direccion": "Dirección 12m",
    "umbral_regimen_tendencia": "Umbral régimen", "cambio_regimen_tendencia": "Cambio régimen",
    "alerta_metodologica": "Alerta metodológica", "posicion_ytd_0_100": "Posición año",
    "posicion_mov_0_100": "Posición móvil", "posicion_hist_0_100": "Posición histórica",
    "dist_min_mov": "Dist. mínimo móvil", "dist_max_mov": "Dist. máximo móvil",
    "semaforo_posicion_mov": "Zona móvil", "comentario_distancias": "Lectura de distancias",
    "revision_requerida": "Revisión", "lectura": "Lectura",
}

# Priorities for UI sorting
PRIORITY_CATEGORIES = [
    "Sector Real",
    "Sector Externo",
]
