from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import glob
import math
import re
import time
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

API_BASE = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
DEFAULT_METADATA_FILENAME = "BCRP_metadata_fusionada_nombre_serie_con_medicion.xlsx"
DEFAULT_OVERRIDES_FILENAME = "overrides_clasificacion_bcrp.csv"
DEFAULT_VARIABLE_CLASSIFICATION_FILENAME = "BCRP_metadata_clasificacion_variables.xlsx"

FREQ_ALIASES = {
    "diaria": "D", "diario": "D", "daily": "D", "d": "D",
    "semanal": "W", "weekly": "W", "w": "W",
    "mensual": "M", "monthly": "M", "m": "M",
    "trimestral": "Q", "quarterly": "Q", "q": "Q",
    "semestral": "S", "s": "S",
    "anual": "A", "annual": "A", "a": "A", "y": "A",
}

MONTHS_ES = {
    "ene": 1, "enero": 1, "jan": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4, "apr": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8, "aug": 8,
    "sep": 9, "set": 9, "sept": 9, "septiembre": 9, "setiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12, "dec": 12,
}

@dataclass(frozen=True)
class SeriesMeta:
    codigo: str
    nombre: str = ""
    frecuencia: str = ""
    nombre_bcrp: str = ""
    frecuencia_bcrp: str = ""
    bloque: str = ""
    uso_analitico: str = ""
    tratamiento: str = "auto"
    clase_serie: str = "auto"
    categoria_bcrp: str = ""
    grupo_bcrp: str = ""
    seccion_bcrp: str = ""
    grupo_publicacion_bcrp: str = ""
    unidad_medida: str = ""
    escala: str = ""
    fecha_actualizacion_meta: str = ""
    fecha_inicio_meta: str = ""
    fecha_creacion_meta: str = ""
    fecha_fin_meta: str = ""
    sentido_economico: str = ""
    prioridad: str = ""
    tipo_variable: str = ""
    subtipo_variable: str = ""
    ventana_variacion: str = ""
    categoria_operativa: str = ""
    unidad_inferida: str = ""
    regla_aplicada: str = ""
    confianza_tipo_variable: str = ""
    requiere_revision_manual: str = ""


def clean_code(code: str) -> str:
    if code is None:
        return ""
    try:
        if pd.isna(code):
            return ""
    except (TypeError, ValueError):
        pass
    return re.sub(r"\s+", "", str(code).strip().upper())


def norm_text(x: object) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip())


def fix_encoding(s: object) -> str:
    """Fix double-encoded UTF-8 strings (e.g. Ã­ → í, Ã± → ñ, Ã© → é).
    Aplica encode latin-1 + decode utf-8 para revertir el patrón de corrupción
    que ocurre cuando bytes UTF-8 se interpretaron como Latin-1."""
    if s is None:
        return ""
    txt = str(s)
    if not txt:
        return txt
    try:
        fixed = txt.encode("latin-1").decode("utf-8")
        return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        return txt


def low_ascii(x: object) -> str:
    s = norm_text(x).lower()
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def safe_pct_change(current: float, previous: float) -> float:
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return np.nan
    return (current / previous - 1.0) * 100.0


def infer_frequency(code: str = "", explicit: str = "") -> str:
    txt = low_ascii(explicit)
    if txt in FREQ_ALIASES:
        return FREQ_ALIASES[txt]
    for k, v in FREQ_ALIASES.items():
        if len(k) > 1 and re.search(rf"\b{re.escape(k)}\b", txt):
            return v
    c = clean_code(code)
    if len(c) >= 2:
        suf = c[-1]
        if suf in {"D", "M", "Q", "S", "A"}:
            return suf
    return "?"


def frequency_name(freq: str) -> str:
    return {"D": "Diaria", "W": "Semanal", "M": "Mensual", "Q": "Trimestral", "S": "Semestral", "A": "Anual"}.get(str(freq).upper(), str(freq or ""))


def read_csv_flexible(path: str | Path, nrows: Optional[int] = None) -> pd.DataFrame:
    path = Path(path)
    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
    seps = [None, ";", ",", "\t"]
    last_error = None
    for enc in encodings:
        for sep in seps:
            try:
                if sep is None:
                    return pd.read_csv(path, sep=None, engine="python", encoding=enc, nrows=nrows)
                return pd.read_csv(path, sep=sep, encoding=enc, nrows=nrows)
            except Exception as exc:
                last_error = exc
    raise RuntimeError(f"No se pudo leer {path}: {last_error}")


def find_metadata_file(metadata_path: str = "", base_dir: str | Path = ".") -> Optional[Path]:
    candidates: List[Path] = []
    if metadata_path:
        candidates.append(Path(metadata_path))
    base = Path(base_dir)
    candidates.append(base / DEFAULT_METADATA_FILENAME)
    candidates.extend(sorted(base.glob("bcrp_metadata_16945_con_gran_categoria*.xlsx"), reverse=True))
    candidates.extend(sorted(Path.cwd().glob("bcrp_metadata_16945_con_gran_categoria*.xlsx"), reverse=True))
    candidates.extend(sorted(base.glob("bcrp_metadata*.xlsx"), reverse=True))
    candidates.extend(sorted(Path.cwd().glob("bcrp_metadata*.xlsx"), reverse=True))
    candidates.append(base / "BCRPData-metadata-20260509-181936.csv")
    candidates.extend(sorted(base.glob("BCRPData-metadata*.csv"), reverse=True))
    candidates.extend(sorted(Path.cwd().glob("BCRPData-metadata*.csv"), reverse=True))
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def load_bcrp_metadata(metadata_path: str = "", base_dir: str | Path = ".") -> pd.DataFrame:
    file_path = find_metadata_file(metadata_path, base_dir)
    if file_path is None:
        return pd.DataFrame()
    if file_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        try:
            # Nueva pestaña preferida para el archivo fusionado
            df = pd.read_excel(file_path, sheet_name="Fusion_BCRP")
        except Exception:
            try:
                # Intentar con el nombre anterior Fusion_BCRO (por si acaso)
                df = pd.read_excel(file_path, sheet_name="Fusion_BCRO")
            except Exception:
                try:
                    df = pd.read_excel(file_path, sheet_name="Catalogo_clasificado")
                except Exception:
                    df = pd.read_excel(file_path)
    else:
        df = read_csv_flexible(file_path)

    # Mapeo unificado basado en las nuevas especificaciones del usuario
    rename_map = {
        "Gran categoría inferida": "categoria_bcrp",
        "Código de serie": "codigo",
        "Categoría de serie": "grupo_bcrp",
        "Grupo de serie": "seccion_bcrp",
        "Nombre de serie": "nombre_bcrp",
        "Nombre de serie ajustado": "nombre_serie_ajustado",
        "Nombre de serie original": "nombre_original_bcrp",
        "Medición agregada desde grupo": "medicion_agregada_desde_grupo",
        "Regla de ajuste del nombre": "regla_ajuste_nombre",
        "Frecuencia": "frecuencia_bcrp",
        "unidad_inferida": "unidad_inferida",
        "tipo_variable": "tipo_variable",
        "subtipo_variable": "subtipo_variable",
        "ventana_variacion": "ventana_variacion",
        "categoria_operativa": "categoria_operativa",
        "regla_aplicada": "regla_aplicada",
        "confianza": "confianza_tipo_variable",
        "requiere_revision_manual": "requiere_revision_manual",
        "estado_fusion_clasificacion": "estado_fusion_clasificacion",
        "Fecha de inicio": "fecha_inicio_meta",
        "Fecha de actualización": "fecha_actualizacion_meta",
        "Fecha de creación": "fecha_creacion_meta",
        "Grupo de publicación": "grupo_publicacion_bcrp",
    }
    
    # Soporte para nombres alternativos (fallback)
    for col in df.columns:
        if col in rename_map:
            continue
        key = low_ascii(col).replace(" ", "_")
        if key in {"gran_categoria_inferida", "gran_categoria"}:
            rename_map[col] = "categoria_bcrp"
        elif key == "codigo_de_serie":
            rename_map[col] = "codigo"
        elif key in {"nombre_de_serie", "nombre_de_serie_actualizado"}:
            rename_map[col] = "nombre_bcrp"
        elif key == "nombre_de_serie_ajustado":
            rename_map[col] = "nombre_serie_ajustado"
        elif key == "nombre_de_serie_original":
            rename_map[col] = "nombre_original_bcrp"
        elif key == "categoria_de_serie":
            rename_map[col] = "grupo_bcrp"
        elif key == "grupo_de_serie":
            rename_map[col] = "seccion_bcrp"
        elif key == "grupo_de_publicacion":
            rename_map[col] = "grupo_publicacion_bcrp"
        elif key == "clase":
            rename_map[col] = "clase_serie"
        elif key == "unidad_inferida":
            rename_map[col] = "unidad_inferida"
        elif key == "confianza":
            rename_map[col] = "confianza_tipo_variable"
        elif key == "fecha_de_actualizacion":
            rename_map[col] = "fecha_actualizacion_meta"
        elif key == "fecha_de_inicio":
            rename_map[col] = "fecha_inicio_meta"
        elif key == "fecha_de_fin":
            rename_map[col] = "fecha_fin_meta"
        elif key == "fecha_de_creacion":
            rename_map[col] = "fecha_creacion_meta"
    
    df = df.rename(columns=rename_map)
    if df.columns.duplicated().any():
        deduped = {}
        for col in dict.fromkeys(df.columns):
            same = df.loc[:, df.columns == col]
            if same.shape[1] == 1:
                deduped[col] = same.iloc[:, 0]
            else:
                deduped[col] = same.replace("", np.nan).bfill(axis=1).iloc[:, 0].fillna("")
        df = pd.DataFrame(deduped)

    # Limpieza básica
    if "codigo" not in df.columns:
        return pd.DataFrame()
    df["codigo"] = df["codigo"].map(clean_code)
    df = df[df["codigo"].ne("")].copy()
    for col in [
        "categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "grupo_publicacion_bcrp",
        "nombre_bcrp", "nombre_original_bcrp", "nombre_serie_ajustado",
        "medicion_agregada_desde_grupo",
        "regla_ajuste_nombre", "descripcion_bcrp", "unidad_medida", "unidad_inferida",
        "escala", "fuente", "frecuencia_bcrp", "fecha_creacion_meta",
        "fecha_actualizacion_meta", "fecha_inicio_meta", "fecha_fin_meta",
        "tipo_variable", "subtipo_variable", "ventana_variacion", "categoria_operativa",
        "regla_aplicada", "confianza_tipo_variable", "requiere_revision_manual",
        "estado_fusion_clasificacion",
    ]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").map(fix_encoding).map(norm_text)
    if {"nombre_bcrp", "nombre_serie_ajustado", "medicion_agregada_desde_grupo"}.issubset(df.columns):
        adjusted = df["nombre_serie_ajustado"].map(low_ascii).isin({"si", "s", "yes", "true"})
        has_measure = df["medicion_agregada_desde_grupo"].fillna("").ne("")
        needs_measure = ~df.apply(
            lambda row: low_ascii(row.get("medicion_agregada_desde_grupo", "")) in low_ascii(row.get("nombre_bcrp", "")),
            axis=1,
        )
        mask = adjusted & has_measure & needs_measure
        df.loc[mask, "nombre_bcrp"] = (
            df.loc[mask, "nombre_bcrp"].str.rstrip()
            + " "
            + df.loc[mask, "medicion_agregada_desde_grupo"].str.strip()
        ).map(norm_text)
    return df.drop_duplicates("codigo", keep="first")


def normalize_catalog_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        key = low_ascii(col).replace(" ", "_")
        if key in {"codigo", "cod", "codigo_de_serie", "code"}:
            mapping[col] = "codigo"
        elif key in {"nombre", "variable", "nombre_de_serie", "serie"}:
            mapping[col] = "nombre"
        elif key in {"frecuencia", "freq"}:
            mapping[col] = "frecuencia"
        elif key in {"bloque", "categoria", "pilar"}:
            mapping[col] = "bloque"
        elif key in {"uso_analitico", "uso", "lectura", "uso_analítico"}:
            mapping[col] = "uso_analitico"
        elif key in {"tratamiento", "tratamiento_base", "transformacion", "transformación"}:
            mapping[col] = "tratamiento"
        elif key in {"clase_serie", "clase", "tipo_serie", "tipo"}:
            mapping[col] = "clase_serie"
        elif key in {"sentido_economico", "sentido", "interpretacion_sentido"}:
            mapping[col] = "sentido_economico"
        elif key in {"prioridad", "priority"}:
            mapping[col] = "prioridad"
    out = df.rename(columns=mapping).copy()
    if "codigo" not in out.columns:
        raise ValueError("El catálogo debe incluir una columna de código BCRP.")
    out["codigo"] = out["codigo"].map(clean_code)
    out = out[out["codigo"].ne("")].copy()
    for col in ["nombre", "frecuencia", "bloque", "uso_analitico", "tratamiento", "clase_serie", "sentido_economico", "prioridad"]:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").map(fix_encoding).map(norm_text)
    out["tratamiento"] = out["tratamiento"].replace("", "auto")
    out["clase_serie"] = out["clase_serie"].replace("", "auto")
    return out.drop_duplicates("codigo", keep="first")


def catalog_from_codes(codes: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame({"codigo": [clean_code(c) for c in codes if clean_code(c)]}).drop_duplicates()


def merge_catalog_with_metadata(catalog: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    cat = normalize_catalog_columns(catalog)
    if metadata is None or metadata.empty:
        cat["metadata_encontrado"] = False
        return cat
    cols = [
        "codigo", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp",
        "grupo_publicacion_bcrp", "nombre_bcrp", "nombre_original_bcrp",
        "nombre_serie_ajustado",
        "medicion_agregada_desde_grupo", "regla_ajuste_nombre", "descripcion_bcrp",
        "unidad_medida", "unidad_inferida", "escala", "fuente",
        "frecuencia_bcrp", "fecha_creacion_meta", "fecha_actualizacion_meta", "fecha_inicio_meta",
        "fecha_fin_meta", "tipo_variable", "subtipo_variable", "ventana_variacion", 
        "categoria_operativa", "regla_aplicada", "confianza_tipo_variable",
        "requiere_revision_manual", "estado_fusion_clasificacion"
    ]
    meta = metadata[[c for c in cols if c in metadata.columns]].copy()
    out = cat.merge(meta, on="codigo", how="left")
    out["metadata_encontrado"] = out["nombre_bcrp"].fillna("").ne("")
    out["nombre"] = np.where(out["nombre"].fillna("").eq(""), out["nombre_bcrp"].fillna(out["codigo"]), out["nombre"])
    out["frecuencia"] = np.where(out["frecuencia"].fillna("").eq(""), out["frecuencia_bcrp"].fillna(""), out["frecuencia"])
    for col in cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("")
    return out


def variable_classification_to_treatment(row: pd.Series | Dict) -> Tuple[str, str]:
    get = row.get if hasattr(row, "get") else lambda k, default="": default
    tipo = low_ascii(get("tipo_variable", ""))
    subtipo = low_ascii(get("subtipo_variable", ""))
    freq = infer_frequency(str(get("codigo", "")), str(get("frecuencia", "") or get("frecuencia_bcrp", "") or get("Frecuencia", "")))

    if "puntos basicos" in tipo or "spread" in subtipo or "diferencial" in subtipo:
        return "spread_pbs", "diferencia"
    if "tasa" in tipo or "tasa" in subtipo or "rentabilidad" in subtipo:
        return "tasa_pct", "diferencia_pbs"
    if "variacion" in tipo or "porcentaje de cambio" in subtipo:
        return "variacion_pct", "nivel"
    if "participacion" in tipo or "ratio" in subtipo or "estructura porcentual" in subtipo or "proporcion" in subtipo or "coeficiente" in subtipo:
        return "ratio_pct", "nivel"
    if "promedio movil" in tipo:
        if "volumen" in subtipo or "cantidad" in subtipo:
            return "volumen_fisico", "var_interanual"
        if "indice" in subtipo or "suavizado" in subtipo:
            return "indice_nivel", "var_interanual"
        return "valor_monetario", "var_interanual"
    if "indice de difusion" in subtipo:
        return "indice_difusion", "nivel"
    if "indice" in subtipo:
        return "indice_nivel", "var_interanual"
    if "volumen" in subtipo or "cantidad" in subtipo:
        return "volumen_fisico", "var_interanual"
    if "valor / precio" in subtipo or "precio" in subtipo:
        return ("precio_financiero_diario" if freq == "D" else "precio_financiero"), "retorno_log"
    if "valor monetario" in subtipo:
        return "valor_monetario", "var_interanual"
    return "valor_monetario", "var_interanual"


def load_variable_classification(path: str | Path = "", base_dir: str | Path = ".") -> pd.DataFrame:
    candidates: List[Path] = []
    if path:
        candidates.append(Path(path))
    base = Path(base_dir)
    candidates.append(base / DEFAULT_VARIABLE_CLASSIFICATION_FILENAME)
    candidates.append(Path.home() / "Downloads" / DEFAULT_VARIABLE_CLASSIFICATION_FILENAME)
    candidates.extend(sorted(base.glob("BCRP_metadata_clasificacion_variables*.xlsx"), reverse=True))
    for c in candidates:
        if not c.exists() or not c.is_file():
            continue
        try:
            df = pd.read_excel(c, sheet_name="Clasificacion_series")
        except Exception:
            # Si no tiene la hoja buscada, intentamos con la primera hoja disponible
            try:
                df = pd.read_excel(c)
            except Exception:
                continue
        rename_map = {}
        for col in df.columns:
            key = low_ascii(col).replace(" ", "_")
            if key in {"codigo_de_serie", "codigo", "codigo_serie"}:
                rename_map[col] = "codigo"
            elif key == "gran_categoria_inferida":
                rename_map[col] = "categoria_bcrp"
            elif key == "categoria_de_serie":
                rename_map[col] = "grupo_bcrp"
            elif key == "grupo_de_serie":
                rename_map[col] = "seccion_bcrp"
            elif key == "nombre_de_serie":
                rename_map[col] = "nombre_bcrp"
            elif key == "frecuencia":
                rename_map[col] = "frecuencia_bcrp"
            elif key == "fecha_de_inicio":
                rename_map[col] = "fecha_inicio_meta"
        out = df.rename(columns=rename_map).copy()
        if "codigo" not in out.columns:
            continue
        out["codigo"] = out["codigo"].map(clean_code)
        out = out[out["codigo"].ne("")].copy()
        for col in [
            "tipo_variable",
            "subtipo_variable",
            "ventana_variacion",
            "categoria_operativa",
            "unidad_inferida",
            "regla_aplicada",
            "confianza",
            "requiere_revision_manual",
            "categoria_bcrp",
            "grupo_bcrp",
            "seccion_bcrp",
            "nombre_bcrp",
            "frecuencia_bcrp",
            "fecha_inicio_meta",
        ]:
            if col not in out.columns:
                out[col] = ""
            out[col] = out[col].fillna("").map(fix_encoding).map(norm_text)
        mapped = out.apply(variable_classification_to_treatment, axis=1, result_type="expand")
        out["clase_serie_clasificacion"] = mapped[0]
        out["tratamiento_clasificacion"] = mapped[1]
        keep = [
            "codigo",
            "tipo_variable",
            "subtipo_variable",
            "ventana_variacion",
            "categoria_operativa",
            "unidad_inferida",
            "regla_aplicada",
            "confianza",
            "requiere_revision_manual",
            "clase_serie_clasificacion",
            "tratamiento_clasificacion",
        ]
        return out[keep].drop_duplicates("codigo", keep="first")
    return pd.DataFrame()


def apply_variable_classification(catalog: pd.DataFrame, variable_classification: pd.DataFrame) -> pd.DataFrame:
    out = catalog.copy()
    out["clasificacion_variable_encontrada"] = False
    if variable_classification is None or variable_classification.empty:
        return out
    vc = variable_classification.copy()
    # Evitar colisión de nombres (tipo_variable_x, tipo_variable_y)
    overlap = [c for c in vc.columns if c != "codigo" and c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    
    out = out.merge(vc, on="codigo", how="left")
    
    if "tipo_variable" not in out.columns:
        out["tipo_variable"] = ""
        
    matched = out["tipo_variable"].fillna("").ne("")
    out["clasificacion_variable_encontrada"] = matched
    out["clase_serie"] = np.where(matched, out["clase_serie_clasificacion"], out.get("clase_serie", "auto"))
    out["tratamiento"] = np.where(matched, out["tratamiento_clasificacion"], out.get("tratamiento", "auto"))
    out["confianza_tipo_variable"] = out.get("confianza", "").fillna("")
    drop_cols = [c for c in ["clase_serie_clasificacion", "tratamiento_clasificacion", "confianza"] if c in out.columns]
    return out.drop(columns=drop_cols)


def load_classification_overrides(path: str | Path = "") -> pd.DataFrame:
    if not path:
        path = Path.cwd() / DEFAULT_OVERRIDES_FILENAME
    path = Path(path)
    if not path.exists() or not path.is_file():
        return pd.DataFrame(columns=["codigo", "clase_serie", "tratamiento", "sentido_economico", "comentario"])
    df = read_csv_flexible(path)
    df = normalize_catalog_columns(df)
    for col in ["sentido_economico", "comentario"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").map(fix_encoding).map(norm_text)
    keep = [c for c in ["codigo", "clase_serie", "tratamiento", "sentido_economico", "comentario"] if c in df.columns]
    return df[keep].drop_duplicates("codigo", keep="last")


def apply_classification_overrides(catalog: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    out = catalog.copy()
    out["override_clasificacion"] = False
    out["override_comentario"] = ""
    if overrides is None or overrides.empty:
        return out
    ovr = overrides.rename(columns={
        "clase_serie": "override_clase_serie",
        "tratamiento": "override_tratamiento",
        "sentido_economico": "override_sentido_economico",
        "comentario": "override_comentario",
    }).copy()
    out = out.merge(ovr, on="codigo", how="left")
    matched = out["override_clase_serie"].fillna("").ne("") | out["override_tratamiento"].fillna("").ne("") | out["override_sentido_economico"].fillna("").ne("")
    out["override_clasificacion"] = matched
    for dest, src in [
        ("clase_serie", "override_clase_serie"),
        ("tratamiento", "override_tratamiento"),
        ("sentido_economico", "override_sentido_economico"),
    ]:
        if dest not in out.columns:
            out[dest] = ""
        if src in out.columns:
            out[dest] = np.where(out[src].fillna("").ne(""), out[src], out[dest])
    out["override_comentario"] = out.get("override_comentario", "").fillna("")
    drop_cols = [c for c in ["override_clase_serie", "override_tratamiento", "override_sentido_economico"] if c in out.columns]
    return out.drop(columns=drop_cols)


def classify_series(row: pd.Series | Dict) -> str:
    get = row.get if hasattr(row, "get") else lambda k, default="": default
    text = " ".join([
        str(get("codigo", "")), str(get("nombre", "")), str(get("nombre_bcrp", "")),
        str(get("categoria_bcrp", "")), str(get("grupo_bcrp", "")), str(get("seccion_bcrp", "")), str(get("unidad_medida", "")), str(get("bloque", "")),
    ])
    t = low_ascii(text)
    freq = infer_frequency(str(get("codigo", "")), str(get("frecuencia", "") or get("frecuencia_bcrp", "")))
    explicit = low_ascii(get("clase_serie", ""))
    if explicit and explicit != "auto":
        return explicit

    if "tasa de referencia" in t or "politica monetaria" in t or "encaje" in t:
        return "politica_monetaria_step"
    if "interbancaria" in t or "tasa de interes" in t or "rendimiento" in t:
        return "tasa_pct"
    if "embig" in t or "riesgo pais" in t or "spread" in t:
        return "spread_pbs"
    if "bonos del tesoro" in t or "tesoro ee" in t or "rendimiento del bono" in t or "yield" in t or "bono soberano" in t:
        return "tasa_pct"
    if "tipo de cambio" in t or "tc " in t or "euro" in t:
        return "precio_financiero_diario" if freq == "D" else "precio_financiero"
    if "cotizacion internacional" in t or "precio internacional" in t or any(k in t for k in ["cobre", "oro", "zinc", "petroleo", "wti", "trigo", "maiz", "soya", "plata", "cafe", "azucar"]):
        return "commodity"
    if "bursatil" in t or "dow jones" in t or "s&p" in t or "indice general bvl" in t or "bolsa" in t:
        return "precio_financiero_diario" if freq == "D" else "precio_financiero"
    if "var% 12 meses" in t or "var. % 12 meses" in t or "variacion 12 meses" in t or "doce meses" in t:
        return "variacion_pct"
    if "var% mensual" in t or "var. % mensual" in t or "variacion mensual" in t:
        return "variacion_pct"
    if "variacion porcentual interanual" in t or "var.% interanual" in t or "var. % interanual" in t:
        return "variacion_pct"
    if "pea ocupada" in t or "empleo" in t or "puestos de trabajo" in t:
        if "tasa" in t or "desempleo" in t:
            return "tasa_pct"
        return "volumen_fisico"
    if "tasa de desempleo" in t or "desempleo" in t:
        return "tasa_pct"
    if "exportaciones" in t or "importaciones" in t or "ingresos" in t or "gasto" in t:
        return "valor_monetario"
    if "balanza comercial" in t or "cuenta corriente" in t or "balanza de pagos" in t:
        return "balance_flujo"
    if "credito" in t or "liquidez" in t or "depositos" in t or "colocaciones" in t or "circulante" in t:
        if "coeficiente" in t or "dolarizacion" in t or "%" in t:
            return "ratio_pct"
        return "stock_financiero"
    if "deuda" in t or "resultado economico" in t or "resultado primario" in t or "ingresos" in t or "gasto" in t:
        if "%" in t or "porcentaje" in t or "pbi" in t:
            return "ratio_pct"
        return "balance_flujo"
    if "coeficiente" in t or "porcentaje" in t or str(get("unidad_medida", "")).strip() == "%":
        return "ratio_pct"
    if "indice" in t:
        return "indice_nivel"
    if freq == "D":
        return "precio_financiero_diario"
    if any(k in t for k in ["millones", "soles", "us$", "usd"]):
        return "valor_monetario"
    if any(k in t for k in ["toneladas", "barriles", "produccion fisica", "personas"]):
        return "volumen_fisico"
    return "valor_monetario"


def default_transform_for_class(clase: str, freq: str = "") -> str:
    clase = low_ascii(clase)
    if clase in {"politica_monetaria_step", "tasa_interbancaria", "tasa_mercado", "tasa_pct"}:
        return "diferencia_pbs"
    if clase in {"spread_riesgo", "spread_pbs"}:
        return "diferencia"
    if clase in {"indice_difusion"}:
        return "nivel"
    if clase in {"tipo_cambio", "commodity", "precio_financiero", "precio_financiero_diario", "serie_diaria_generica"}:
        return "retorno_log"
    if clase in {"inflacion_mensual", "inflacion_12m", "actividad_var_interanual", "variacion_ya_calculada", "variacion_pct", "mercado_laboral_tasa", "ratio", "ratio_financiero", "ratio_fiscal", "ratio_pct", "balance_externo", "balance_flujo"}:
        return "nivel"
    if clase in {"mercado_laboral_nivel", "sector_externo_flujo", "saldo_nominal", "flujo_fiscal", "indice_nivel", "valor_monetario", "volumen_fisico", "stock_financiero"}:
        return "var_interanual"
    return "nivel" if freq == "D" else "var_interanual"


def final_transform(row: pd.Series | Dict) -> str:
    tr = norm_text(row.get("tratamiento", "auto") if hasattr(row, "get") else "auto").lower()
    if tr and tr != "auto":
        return tr
    freq = infer_frequency(row.get("codigo", ""), row.get("frecuencia", "") or row.get("frecuencia_bcrp", ""))
    return default_transform_for_class(row.get("clase_serie", "nivel_generico"), freq)


def period_to_date(period: str, freq_hint: str = "") -> pd.Timestamp:
    p = str(period or "").strip()
    if not p:
        return pd.NaT
    # ISO daily
    if re.match(r"^\d{4}-\d{2}-\d{2}$", p):
        return pd.to_datetime(p, errors="coerce")
    # yyyy-mm or yyyy-m
    if re.match(r"^\d{4}-\d{1,2}$", p):
        y, m = p.split("-")
        return pd.Timestamp(int(y), int(m), 1) + pd.offsets.MonthEnd(0)
    # yyyy-Qn
    if re.match(r"^\d{4}-Q[1-4]$", p, flags=re.I):
        y, q = p.upper().split("-Q")
        month = int(q) * 3
        return pd.Timestamp(int(y), month, 1) + pd.offsets.MonthEnd(0)
    # BCRP quarterly labels can arrive as T1.25, T124, 1T2024 or 2024-T1.
    quarter_patterns = [
        re.match(r"^T([1-4])\.?-?(\d{2}|\d{4})$", p, flags=re.I),
        re.match(r"^([1-4])T\.?-?(\d{2}|\d{4})$", p, flags=re.I),
        re.match(r"^(\d{4})-T([1-4])$", p, flags=re.I),
    ]
    for m in quarter_patterns[:2]:
        if m:
            q, yy = m.groups()
            year = int(yy)
            if year < 100:
                year += 2000 if year < 50 else 1900
            month = int(q) * 3
            return pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    if quarter_patterns[2]:
        yy, q = quarter_patterns[2].groups()
        month = int(q) * 3
        return pd.Timestamp(int(yy), month, 1) + pd.offsets.MonthEnd(0)
    # yyyy-Sn
    if re.match(r"^\d{4}-S[1-2]$", p, flags=re.I):
        y, s = p.upper().split("-S")
        month = 6 if int(s) == 1 else 12
        return pd.Timestamp(int(y), month, 1) + pd.offsets.MonthEnd(0)
    # BCRP monthly labels commonly arrive as Abr.2026, Ene.26 or Abr26.
    month_label = re.match(r"^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,})\.?[-/ ]?(\d{2}|\d{4})$", p)
    if month_label:
        mon, yy = month_label.groups()
        mon_key = low_ascii(mon)[:3]
        if mon_key in MONTHS_ES:
            year = int(yy)
            if year < 100:
                year += 2000 if year < 50 else 1900
            return pd.Timestamp(year, MONTHS_ES[mon_key], 1) + pd.offsets.MonthEnd(0)
    # Daily labels from BCRP can arrive as 13.Abr.26 or 13Abr26.
    day_month_label = re.match(r"^(\d{1,2})\.?([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,})\.?[-/ ]?(\d{2}|\d{4})$", p)
    if day_month_label:
        dd, mon, yy = day_month_label.groups()
        mon_key = low_ascii(mon)[:3]
        if mon_key in MONTHS_ES:
            year = int(yy)
            if year < 100:
                year += 2000 if year < 50 else 1900
            return pd.Timestamp(year, MONTHS_ES[mon_key], int(dd))
    # dd-Mmm-yyyy / Mmm-yyyy
    parts = re.split(r"[-/. ]+", p)
    if len(parts) == 3:
        a, b, c = parts
        if low_ascii(b)[:3] in MONTHS_ES:
            year = int(c)
            if year < 100:
                year += 2000 if year < 50 else 1900
            return pd.Timestamp(year, MONTHS_ES[low_ascii(b)[:3]], int(a))
    if len(parts) == 2 and low_ascii(parts[0])[:3] in MONTHS_ES:
        return pd.Timestamp(int(parts[1]), MONTHS_ES[low_ascii(parts[0])[:3]], 1) + pd.offsets.MonthEnd(0)
    if re.match(r"^\d{4}$", p):
        return pd.Timestamp(int(p), 12, 31)
    return pd.to_datetime(p, errors="coerce")


def date_to_bcrp_period(dt: date | datetime | pd.Timestamp, freq: str) -> str:
    d = pd.Timestamp(dt)
    f = str(freq or "").upper()
    if f == "D":
        return d.strftime("%Y-%m-%d")
    if f == "Q":
        q = math.ceil(d.month / 3)
        return f"{d.year}-Q{q}"
    if f == "S":
        s = 1 if d.month <= 6 else 2
        return f"{d.year}-S{s}"
    if f == "A":
        return f"{d.year}"
    return f"{d.year}-{d.month}"


def _safe_float(x) -> float:
    """Convierte valores BCRP a float sin romper por comas, vacíos o n.d."""
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    s = str(x).strip()
    if s == "" or s.lower() in {"n.d.", "nd", "nan", "none", "na", "null"}:
        return np.nan
    # BCRP suele devolver punto decimal. Si viniera separador de miles, lo quitamos.
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_bcrp_json(data: dict, code: str, freq_hint: str = "") -> Tuple[pd.DataFrame, Dict[str, str]]:
    meta: Dict[str, str] = {"codigo": code}
    rows = []

    # Formato vigente BCRPData: config.series + periods.
    # En este formato, periods[i]["values"] suele venir como LISTA, no como diccionario.
    # Ejemplo: {"name": "2026-4", "values": ["4.01"]}
    if isinstance(data, dict) and "periods" in data:
        config = data.get("config", {}) or {}
        config_series = config.get("series", []) or []
        series_code = code
        if config_series:
            s0 = config_series[0] or {}
            meta["nombre_api"] = fix_encoding(s0.get("name") or s0.get("nombre") or config.get("title") or code)
            meta["frecuencia_api"] = s0.get("frequency") or s0.get("freq") or s0.get("frecuencia") or ""
            series_code = s0.get("dec") or s0.get("code") or s0.get("codigo") or code
        else:
            meta["nombre_api"] = config.get("title") or code
            meta["frecuencia_api"] = config.get("frequency") or ""

        for p in data.get("periods", []) or []:
            if not isinstance(p, dict):
                continue
            period_name = p.get("name") or p.get("fecha") or p.get("period")
            values = p.get("values")
            val = None
            if isinstance(values, list):
                val = values[0] if values else None
            elif isinstance(values, dict):
                val = values.get(series_code)
                if val is None:
                    val = values.get(code)
                if val is None and values:
                    val = next(iter(values.values()))
            else:
                val = p.get("value") or p.get("valor")

            num = _safe_float(val)
            dt = period_to_date(period_name, freq_hint)
            if pd.notna(dt) and not np.isnan(num):
                rows.append({"fecha": dt, "periodo": period_name, "valor": num})

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(), meta
        return df.dropna(subset=["fecha", "valor"]).sort_values("fecha").drop_duplicates("fecha", keep="last"), meta

def parse_bcrp_batch_json(data: dict, codes: List[str], freq_hint: str = "") -> Tuple[Dict[str, pd.DataFrame], Dict[str, dict]]:
    results_df = {code: [] for code in codes}
    results_meta = {code: {"codigo": code} for code in codes}
    
    if not isinstance(data, dict) or "periods" not in data:
        return {c: pd.DataFrame() for c in codes}, results_meta

    config = data.get("config", {}) or {}
    config_series = config.get("series", []) or []
    # El BCRP devuelve los metadatos en el mismo orden que la lista de códigos pedida
    for i, s_meta in enumerate(config_series):
        if i < len(codes):
            code = codes[i]
            results_meta[code]["nombre_api"] = fix_encoding(s_meta.get("name") or s_meta.get("nombre") or "")

            results_meta[code]["frecuencia_api"] = s_meta.get("frequency") or ""

    for p in data.get("periods", []) or []:
        if not isinstance(p, dict): continue
        period_name = p.get("name") or p.get("fecha") or p.get("period")
        values = p.get("values")
        dt = period_to_date(period_name, freq_hint)
        if pd.isna(dt) or not values or not isinstance(values, list):
            continue
        
        for i, val in enumerate(values):
            if i < len(codes):
                code = codes[i]
                num = _safe_float(val)
                if not np.isnan(num):
                    results_df[code].append({"fecha": dt, "periodo": period_name, "valor": num})
    
    final_dfs = {}
    for code, rows in results_df.items():
        if not rows:
            final_dfs[code] = pd.DataFrame()
        else:
            df = pd.DataFrame(rows)
            final_dfs[code] = df.dropna(subset=["fecha", "valor"]).sort_values("fecha").drop_duplicates("fecha", keep="last")
            
    return final_dfs, results_meta

def fetch_bcrp_batch_series(codes: List[str], start: date, end: date, freq_hint: str = "") -> Tuple[Dict[str, pd.DataFrame], Dict[str, dict]]:
    if not codes: return {}, {}
    codes_str = "-".join(codes)
    start_str = date_to_bcrp_period(start, freq_hint)
    end_str = date_to_bcrp_period(end, freq_hint)
    url = f"{API_BASE}/{codes_str}/json/{start_str}/{end_str}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return parse_bcrp_batch_json(resp.json(), codes, freq_hint)
    except Exception:
        # Retry una vez
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return parse_bcrp_batch_json(resp.json(), codes, freq_hint)
        except Exception:
            return {c: pd.DataFrame() for c in codes}, {c: {"codigo": c} for c in codes}


    # Fallback para respuestas alternativas: series[0].values = [[fecha, valor], ...]
    if isinstance(data, dict) and "series" in data:
        serie = (data.get("series") or [{}])[0] or {}
        meta["nombre_api"] = serie.get("nombre") or serie.get("name") or code
        meta["frecuencia_api"] = serie.get("frecuencia") or serie.get("frequency") or serie.get("freq") or ""
        for v in serie.get("values", []) or []:
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                num = _safe_float(v[1])
                dt = period_to_date(v[0], freq_hint)
                if pd.notna(dt) and not np.isnan(num):
                    rows.append({"fecha": dt, "periodo": v[0], "valor": num})
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(), meta
        return df.dropna(subset=["fecha", "valor"]).sort_values("fecha").drop_duplicates("fecha", keep="last"), meta

    return pd.DataFrame(), meta


def fetch_bcrp_series(code: str, start: date, end: date, freq_hint: str = "") -> Tuple[pd.DataFrame, Dict[str, str]]:
    code = clean_code(code)
    freq = infer_frequency(code, freq_hint)
    start_p = date_to_bcrp_period(start, freq)
    end_p = date_to_bcrp_period(end, freq)
    if freq == "Q":
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        start_q = math.ceil(start_ts.month / 3)
        end_q = math.ceil(end_ts.month / 3)
        start_p = f"{start_ts.year}-{start_q}"
        end_p = f"{end_ts.year}-Q{end_q}"
    url = f"{API_BASE}/{code}/json/{start_p}/{end_p}/esp"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MonitorBCRP/4.0)",
        "Accept": "application/json,text/plain,*/*",
    }
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            resp.raise_for_status()
            break
        except requests.HTTPError as exc:
            last_exc = exc
            status = exc.response.status_code if exc.response is not None else None
            if status not in {403, 429, 500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    else:
        raise last_exc or RuntimeError(f"No se pudo consultar la API para {code}.")
    try:
        data = resp.json()
    except ValueError as exc:
        sample = resp.text[:200].replace("\n", " ")
        raise ValueError(f"La API no devolvió JSON válido para {code}. Respuesta inicial: {sample}") from exc
    df, meta = parse_bcrp_json(data, code, freq)
    meta["url_api"] = url
    if df.empty:
        keys = ", ".join(data.keys()) if isinstance(data, dict) else type(data).__name__
        raise ValueError(f"La API respondió, pero no trajo valores numéricos para {code}. Claves: {keys}. URL: {url}")
    return df, meta


def periods_per_year(freq: str) -> int:
    return {"D": 252, "W": 52, "M": 12, "Q": 4, "S": 2, "A": 1}.get(str(freq).upper(), 12)


def trend_window_for_frequency(freq: str, available: int) -> int:
    """Observations used for the main trend signal by frequency."""
    f = str(freq).upper()
    target = {"D": 252, "W": 52, "M": 12, "Q": 4, "S": 4, "A": 5}.get(f, 12)
    if available < 2:
        return available
    return max(2, min(target, available))


def trend_fit_window_for_frequency(freq: str) -> Tuple[int, int]:
    """Total window and minimum observations for trend fitting."""
    return {
        "D": (252, 60),
        "W": (104, 26),
        "M": (36, 12),
        "Q": (16, 6),
        "S": (10, 4),
        "A": (10, 3),
    }.get(str(freq).upper(), (36, 12))


def transform_series(df: pd.DataFrame, transform: str, freq: str) -> pd.DataFrame:
    out = df[["fecha", "valor"]].copy().dropna().sort_values("fecha")
    tr = low_ascii(transform)
    ppy = periods_per_year(freq)
    if tr in {"nivel", "level"}:
        out["valor_analisis"] = out["valor"]
    elif tr in {"diferencia", "diff"}:
        out["valor_analisis"] = out["valor"].diff()
    elif tr in {"diferencia_pbs", "pbs", "bp"}:
        out["valor_analisis"] = out["valor"].diff() * 100.0
    elif tr in {"var_periodo", "pct_change"}:
        out["valor_analisis"] = out["valor"].pct_change() * 100.0
    elif tr in {"var_interanual", "yoy"}:
        out["valor_analisis"] = out["valor"].pct_change(ppy) * 100.0
    elif tr in {"log_var_interanual", "log_yoy"}:
        out["valor_analisis"] = (np.log(out["valor"]).diff(ppy)) * 100.0
    elif tr in {"retorno_log", "log_return"}:
        if (out["valor"] <= 0).any():
            out["valor_analisis"] = out["valor"].pct_change() * 100.0
        else:
            out["valor_analisis"] = (np.log(out["valor"]).diff()) * 100.0
    else:
        out["valor_analisis"] = out["valor"]
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def treatment_criterion(clase: str, transform: str, freq: str) -> str:
    cls = low_ascii(clase)
    tr = low_ascii(transform)
    if cls == "politica_monetaria_step":
        return "Evento discreto de politica monetaria: cambio frente al dato previo en puntos basicos."
    if cls in {"tasa_pct", "tasa_interbancaria", "tasa_mercado"}:
        return "Tasa porcentual: diferencia frente al dato previo expresada en puntos basicos."
    if cls in {"spread_pbs", "spread_riesgo"}:
        return "Spread en puntos basicos: diferencia simple, sin multiplicar por 100."
    if cls == "indice_difusion":
        return "Indice de difusion: se mantiene el ultimo nivel observado y se compara contra su historia."
    if cls in {"variacion_pct", "variacion_ya_calculada", "inflacion_mensual", "inflacion_12m"}:
        return "Serie ya expresada como variacion o porcentaje: se mantiene el nivel y se comparan puntos porcentuales."
    if cls in {"precio_financiero_diario", "tipo_cambio", "commodity", "precio_financiero", "serie_diaria_generica"}:
        return "Precio financiero o commodity: retorno logaritmico y comparacion contra ventanas moviles."
    if tr == "var_interanual":
        if str(freq).upper() == "A":
            return "Serie anual en nivel: variacion porcentual frente al ano anterior."
        return "Serie en nivel: variacion interanual contra el mismo periodo del ano previo."
    return "Serie evaluada en nivel con comparaciones historicas y de tendencia."


def infer_sentido_economico(row: pd.Series | Dict, clase: str) -> str:
    explicit = low_ascii(row.get("sentido_economico", "") if hasattr(row, "get") else "")
    allowed = {"sube_favorable", "sube_desfavorable", "baja_favorable", "baja_desfavorable", "neutro", "contextual"}
    if explicit in allowed:
        return explicit
    text = low_ascii(" ".join([
        str(row.get("codigo", "")), str(row.get("nombre", "")), str(row.get("nombre_bcrp", "")),
        str(row.get("categoria_bcrp", "")), str(row.get("grupo_bcrp", "")), str(row.get("seccion_bcrp", "")),
    ]) if hasattr(row, "get") else "")
    cls = low_ascii(clase)
    if cls == "politica_monetaria_step":
        return "neutro"
    if cls in {"spread_pbs", "spread_riesgo"} or "embi" in text or "riesgo pais" in text:
        return "sube_desfavorable"
    if "inflacion" in text or "ipc" in text or "desempleo" in text or "deuda" in text or "deficit" in text:
        return "sube_desfavorable"
    if "tipo de cambio" in text or cls in {"precio_financiero_diario", "precio_financiero"}:
        return "contextual"
    if "petroleo" in text or "wti" in text:
        return "sube_desfavorable"
    if any(k in text for k in ["pbi", "produccion", "empleo", "exportaciones", "cobre", "oro", "credito"]):
        return "sube_favorable"
    if cls in {"valor_monetario", "volumen_fisico", "stock_financiero", "indice_nivel"}:
        return "sube_favorable"
    return "contextual"


def audit_classification_row(row: pd.Series | Dict) -> Dict[str, object]:
    get = row.get if hasattr(row, "get") else lambda k, default="": default
    text = " ".join([
        str(get("codigo", "")), str(get("nombre", "")), str(get("nombre_bcrp", "")),
        str(get("categoria_bcrp", "")), str(get("grupo_bcrp", "")), str(get("seccion_bcrp", "")), str(get("unidad_medida", "")),
    ])
    t = low_ascii(text)
    clase = norm_text(get("clase_serie", "")) or classify_series(row)
    tratamiento = norm_text(get("tratamiento", "")) or final_transform({**dict(row), "clase_serie": clase} if hasattr(row, "items") else row)
    sentido = norm_text(get("sentido_economico", "")) or infer_sentido_economico(row, clase)
    reasons: List[str] = []
    warnings: List[str] = []
    confidence = 0.7

    if bool(get("override_clasificacion", False)):
        confidence = 1.0
        reasons.append("Override manual aplicado")
    elif bool(get("clasificacion_variable_encontrada", False)):
        reasons.append("Clasificacion por base de tipo de variable")
        confidence = 0.95 if low_ascii(get("confianza_tipo_variable", "")) == "alta" else 0.75
    if "var%" in t or "variacion porcentual" in t or "var. %" in t:
        reasons.append("Nombre indica variacion porcentual ya calculada")
        if clase != "variacion_pct":
            warnings.append("Dice variacion porcentual pero no quedo como variacion_pct")
    if any(k in t for k in ["millones", "us$", "soles"]) and clase not in {"valor_monetario", "balance_flujo", "stock_financiero", "variacion_pct"}:
        warnings.append("Unidad monetaria no coincide claramente con clase")
    if "%" in str(get("unidad_medida", "")) and clase in {"valor_monetario", "volumen_fisico", "stock_financiero"}:
        warnings.append("Unidad porcentual clasificada como nivel monetario/fisico")
    if any(k in t for k in ["tasa", "rendimiento", "interes"]) and clase not in {"tasa_pct", "politica_monetaria_step", "variacion_pct"}:
        warnings.append("Nombre sugiere tasa pero clase no es tasa_pct")
    if any(k in t for k in ["embi", "spread", "riesgo pais"]) and clase != "spread_pbs":
        warnings.append("Nombre sugiere spread en pbs pero clase no es spread_pbs")
    if any(k in t for k in ["indice", "ipc"]) and clase not in {"indice_nivel", "variacion_pct", "precio_financiero_diario"}:
        warnings.append("Nombre sugiere indice pero clase no es indice_nivel/variacion_pct")
    if low_ascii(get("requiere_revision_manual", "")) in {"si", "s", "yes"}:
        warnings.append("Base de tipo de variable marca revision manual")
    if clase == "valor_monetario" and tratamiento != "var_interanual":
        warnings.append("Valor monetario deberia usar var_interanual salvo excepcion")
    if clase == "variacion_pct" and tratamiento != "nivel":
        warnings.append("Variacion ya calculada no debe transformarse de nuevo")
    if clase == "spread_pbs" and tratamiento not in {"diferencia", "nivel"}:
        warnings.append("Spread en pbs no debe multiplicarse por 100")
    if clase == "tasa_pct" and tratamiento not in {"diferencia_pbs", "nivel"}:
        warnings.append("Tasa porcentual requiere diferencia_pbs o nivel")

    if not reasons:
        reasons.append("Clasificacion por reglas automaticas de texto/metadato")
    if warnings:
        confidence = min(confidence, 0.45)
    elif bool(get("metadata_encontrado", False)):
        confidence = max(confidence, 0.8)

    return {
        "codigo": clean_code(get("codigo", "")),
        "nombre_bcrp": norm_text(get("nombre_bcrp", "") or get("nombre", "")),
        "categoria_bcrp": norm_text(get("categoria_bcrp", "")),
        "grupo_bcrp": norm_text(get("grupo_bcrp", "")),
        "seccion_bcrp": norm_text(get("seccion_bcrp", "")),
        "unidad_medida": norm_text(get("unidad_medida", "")),
        "frecuencia_bcrp": norm_text(get("frecuencia_bcrp", "") or get("frecuencia", "")),
        "tipo_variable": norm_text(get("tipo_variable", "")),
        "subtipo_variable": norm_text(get("subtipo_variable", "")),
        "ventana_variacion": norm_text(get("ventana_variacion", "")),
        "categoria_operativa": norm_text(get("categoria_operativa", "")),
        "confianza_tipo_variable": norm_text(get("confianza_tipo_variable", "")),
        "requiere_revision_manual": norm_text(get("requiere_revision_manual", "")),
        "clase_serie": clase,
        "tratamiento_base": tratamiento,
        "sentido_economico": sentido,
        "confianza_clasificacion": confidence,
        "revision_requerida": bool(warnings),
        "motivo_clasificacion": "; ".join(reasons),
        "alertas_clasificacion": "; ".join(warnings),
        "override_clasificacion": bool(get("override_clasificacion", False)),
        "override_comentario": norm_text(get("override_comentario", "")),
    }


def audit_classification_catalog(catalog: pd.DataFrame) -> pd.DataFrame:
    if catalog is None or catalog.empty:
        return pd.DataFrame()
    rows = []
    for _, row in catalog.iterrows():
        rowd = row.to_dict()
        if not rowd.get("clase_serie") or rowd.get("clase_serie") == "auto":
            rowd["clase_serie"] = classify_series(rowd)
        if not rowd.get("tratamiento") or rowd.get("tratamiento") == "auto":
            rowd["tratamiento"] = final_transform(rowd)
        if not rowd.get("sentido_economico"):
            rowd["sentido_economico"] = infer_sentido_economico(rowd, rowd["clase_serie"])
        rows.append(audit_classification_row(rowd))
    return pd.DataFrame(rows)


def is_flow_like(clase: str) -> bool:
    return low_ascii(clase) in {"valor_monetario", "volumen_fisico", "balance_flujo", "sector_externo_flujo", "flujo_fiscal"}


def is_level_growth_like(clase: str) -> bool:
    return low_ascii(clase) in {"valor_monetario", "volumen_fisico", "stock_financiero", "indice_nivel", "mercado_laboral_nivel", "saldo_nominal", "sector_externo_flujo", "flujo_fiscal"}


def comparison_metrics(df_t: pd.DataFrame, clase: str, freq: str) -> Dict[str, float]:
    out = {
        "var_interanual_pct": np.nan,
        "diferencia_interanual_pp": np.nan,
        "diferencia_interanual_pbs": np.nan,
        "ventana_anual_actual": np.nan,
        "ventana_anual_previa": np.nan,
        "var_ventana_anual_vs_previa_pct": np.nan,
        "diferencia_ventana_anual_pp": np.nan,
        "diferencia_ventana_anual_pbs": np.nan,
        "acumulado_anio_actual": np.nan,
        "acumulado_anio_previo_comparable": np.nan,
        "var_acumulada_anio_pct": np.nan,
        "diferencia_acumulada_anio_pp": np.nan,
        "diferencia_acumulada_anio_pbs": np.nan,
    }
    d = df_t.dropna(subset=["fecha", "valor"]).copy()
    if d.empty:
        return out
    ppy = periods_per_year(freq)
    cls = low_ascii(clase)
    x = d["valor"].astype(float)
    if len(x) > ppy:
        last = x.iloc[-1]
        comp = x.iloc[-ppy-1]
        if is_level_growth_like(cls):
            out["var_interanual_pct"] = safe_pct_change(last, comp)
        else:
            diff = last - comp
            if cls in {"tasa_pct", "politica_monetaria_step"}:
                out["diferencia_interanual_pbs"] = diff * 100.0
            elif cls in {"spread_pbs", "spread_riesgo"}:
                out["diferencia_interanual_pbs"] = diff
            else:
                out["diferencia_interanual_pp"] = diff

    if len(d) >= ppy * 2:
        cur = x.iloc[-ppy:]
        prev = x.iloc[-ppy * 2:-ppy]
        if is_flow_like(cls):
            cur_v, prev_v = cur.sum(), prev.sum()
            out["ventana_anual_actual"] = cur_v
            out["ventana_anual_previa"] = prev_v
            out["var_ventana_anual_vs_previa_pct"] = safe_pct_change(cur_v, prev_v)
        else:
            cur_v, prev_v = cur.mean(), prev.mean()
            out["ventana_anual_actual"] = cur_v
            out["ventana_anual_previa"] = prev_v
            diff = cur_v - prev_v
            if cls in {"tasa_pct", "politica_monetaria_step"}:
                out["diferencia_ventana_anual_pbs"] = diff * 100.0
            elif cls in {"spread_pbs", "spread_riesgo"}:
                out["diferencia_ventana_anual_pbs"] = diff
            else:
                out["diferencia_ventana_anual_pp"] = diff

    last_date = d["fecha"].max()
    year = int(last_date.year)
    upto_month = int(last_date.month)
    cur_y = d[(d["fecha"].dt.year == year) & (d["fecha"].dt.month <= upto_month)]["valor"].astype(float)
    prev_y = d[(d["fecha"].dt.year == year - 1) & (d["fecha"].dt.month <= upto_month)]["valor"].astype(float)
    if len(cur_y) and len(prev_y):
        if is_flow_like(cls):
            cur_v, prev_v = cur_y.sum(), prev_y.sum()
            out["acumulado_anio_actual"] = cur_v
            out["acumulado_anio_previo_comparable"] = prev_v
            out["var_acumulada_anio_pct"] = safe_pct_change(cur_v, prev_v)
        else:
            cur_v, prev_v = cur_y.mean(), prev_y.mean()
            out["acumulado_anio_actual"] = cur_v
            out["acumulado_anio_previo_comparable"] = prev_v
            diff = cur_v - prev_v
            if cls in {"tasa_pct", "politica_monetaria_step"}:
                out["diferencia_acumulada_anio_pbs"] = diff * 100.0
            elif cls in {"spread_pbs", "spread_riesgo"}:
                out["diferencia_acumulada_anio_pbs"] = diff
            else:
                out["diferencia_acumulada_anio_pp"] = diff
    return out


def safe_last(s: pd.Series, default=np.nan):
    s2 = s.dropna()
    return s2.iloc[-1] if len(s2) else default


def current_previous_metrics(df_t: pd.DataFrame, freq: str) -> Dict[str, object]:
    d = df_t.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    out: Dict[str, object] = {
        "fecha_dato_actual": "",
        "dato_actual_original": np.nan,
        "dato_actual_analisis": np.nan,
        "fecha_dato_anterior": "",
        "dato_anterior_original": np.nan,
        "dato_anterior_analisis": np.nan,
        "fecha_dato_anio_anterior": "",
        "dato_anio_anterior_original": np.nan,
        "dato_anio_anterior_analisis": np.nan,
    }
    if d.empty:
        return out

    last = d.iloc[-1]
    out["fecha_dato_actual"] = last["fecha"].date().isoformat()
    out["dato_actual_original"] = float(last["valor"]) if pd.notna(last["valor"]) else np.nan
    out["dato_actual_analisis"] = float(last["valor_analisis"]) if "valor_analisis" in d.columns and pd.notna(last.get("valor_analisis")) else np.nan

    if len(d) >= 2:
        prev = d.iloc[-2]
        out["fecha_dato_anterior"] = prev["fecha"].date().isoformat()
        out["dato_anterior_original"] = float(prev["valor"]) if pd.notna(prev["valor"]) else np.nan
        out["dato_anterior_analisis"] = float(prev["valor_analisis"]) if "valor_analisis" in d.columns and pd.notna(prev.get("valor_analisis")) else np.nan

    f = str(freq).upper()
    if f == "D":
        target = pd.Timestamp(last["fecha"]) - pd.DateOffset(years=1)
        prior_year = d[d["fecha"].le(target)].tail(1)
    else:
        ppy = periods_per_year(freq)
        prior_year = d.iloc[[-ppy - 1]] if len(d) > ppy else pd.DataFrame()
    if not prior_year.empty:
        py = prior_year.iloc[0]
        out["fecha_dato_anio_anterior"] = py["fecha"].date().isoformat()
        out["dato_anio_anterior_original"] = float(py["valor"]) if pd.notna(py["valor"]) else np.nan
        out["dato_anio_anterior_analisis"] = float(py["valor_analisis"]) if "valor_analisis" in d.columns and pd.notna(py.get("valor_analisis")) else np.nan
    return out


def get_lag_value(series: pd.Series, n: int) -> float:
    s = series.dropna()
    if len(s) <= n:
        return np.nan
    return s.iloc[-n-1]


def rolling_stats(s: pd.Series, window: int) -> Dict[str, float]:
    x = s.dropna()
    if len(x) < max(8, window // 2):
        return {"mean": np.nan, "std": np.nan, "z": np.nan, "robust_z": np.nan}
    recent = x.iloc[-window:] if len(x) >= window else x
    mean = recent.mean()
    std = recent.std(ddof=0)
    last = x.iloc[-1]
    z = (last - mean) / std if std and not np.isnan(std) else 0.0
    med = recent.median()
    mad = (recent - med).abs().median()
    rz = 0.6745 * (last - med) / mad if mad and not np.isnan(mad) else 0.0
    return {"mean": mean, "std": std, "z": z, "robust_z": rz}


def pct_rank_last(s: pd.Series) -> float:
    x = s.dropna()
    if len(x) < 3:
        return np.nan
    return float((x <= x.iloc[-1]).mean() * 100.0)


def annual_average_metrics(df_t: pd.DataFrame) -> Dict[str, float]:
    d = df_t.dropna(subset=["valor"]).copy()
    if d.empty:
        return {"prom_anual_actual": np.nan, "prom_anual_previo": np.nan, "dif_prom_anual": np.nan}
    d["anio"] = d["fecha"].dt.year
    y = int(d["anio"].max())
    avg_cur = d.loc[d["anio"].eq(y), "valor"].mean()
    avg_prev = d.loc[d["anio"].eq(y-1), "valor"].mean()
    return {"prom_anual_actual": avg_cur, "prom_anual_previo": avg_prev, "dif_prom_anual": avg_cur - avg_prev if pd.notna(avg_cur) and pd.notna(avg_prev) else np.nan}


def recent_window_delta(series: pd.Series, n: int, mult: float = 1.0) -> float:
    s = series.dropna()
    if len(s) <= n:
        return np.nan
    return (s.iloc[-1] - s.iloc[-n-1]) * mult


def volatility_ratio(s: pd.Series, short: int, long: int) -> float:
    x = s.dropna()
    if len(x) < max(short + 5, 20):
        return np.nan
    short_std = x.iloc[-short:].std(ddof=0)
    long_std = x.iloc[-long:].std(ddof=0) if len(x) >= long else x.std(ddof=0)
    return short_std / long_std if long_std and not np.isnan(long_std) else np.nan


def trend_slope(s: pd.Series, n: int) -> float:
    x = s.dropna().iloc[-n:]
    if len(x) < max(5, n//3):
        return np.nan
    xi = np.arange(len(x), dtype=float)
    try:
        return float(np.polyfit(xi, x.values.astype(float), 1)[0])
    except Exception:
        return np.nan


def drawdown_pct(series: pd.Series) -> float:
    x = series.dropna()
    if len(x) < 2:
        return np.nan
    peak = x.cummax()
    dd = (x.iloc[-1] / peak.iloc[-1] - 1) * 100 if peak.iloc[-1] else np.nan
    return float(dd)


def page_hinkley_score(s: pd.Series, delta: float = 0.01) -> float:
    x = s.dropna().astype(float)
    if len(x) < 20:
        return np.nan
    mean = x.expanding().mean()
    ph = ((x - mean - delta).cumsum())
    return float((ph - ph.cummin()).iloc[-1])


def historical_extreme(series: pd.Series) -> Tuple[bool, bool]:
    x = series.dropna()
    if len(x) < 24:
        return False, False
    last = x.iloc[-1]
    prev = x.iloc[:-1]
    return bool(last >= prev.max()), bool(last <= prev.min())


def date_value_at_extreme(df_t: pd.DataFrame, column: str, which: str) -> Tuple[float, str]:
    d = df_t.dropna(subset=["fecha", column]).copy()
    if d.empty:
        return np.nan, ""
    idx = d[column].idxmax() if which == "max" else d[column].idxmin()
    row = d.loc[idx]
    return float(row[column]), row["fecha"].date().isoformat()


def _position_label(pos: object) -> str:
    try:
        if pd.isna(pos):
            return "Sin datos"
        p = float(pos)
    except Exception:
        return "Sin datos"
    if p <= 20:
        return "Muy cerca del mínimo"
    if p <= 40:
        return "Zona baja"
    if p <= 60:
        return "Zona media"
    if p <= 80:
        return "Zona alta"
    return "Muy cerca del máximo"


def _window_position_metrics(d: pd.DataFrame, prefix: str) -> Dict[str, object]:
    out: Dict[str, object] = {
        f"min_{prefix}": np.nan,
        f"fecha_min_{prefix}": "",
        f"max_{prefix}": np.nan,
        f"fecha_max_{prefix}": "",
        f"dist_min_{prefix}": np.nan,
        f"dist_max_{prefix}": np.nan,
        f"posicion_{prefix}_0_100": np.nan,
        f"lectura_posicion_{prefix}": "Sin datos",
        f"rango_plano_{prefix}": False,
        f"cobertura_{prefix}": np.nan,
    }
    w = d.dropna(subset=["fecha", "valor"]).copy()
    if w.empty:
        return out
    min_val, min_date = date_value_at_extreme(w, "valor", "min")
    max_val, max_date = date_value_at_extreme(w, "valor", "max")
    last = float(w["valor"].iloc[-1])
    out.update({
        f"min_{prefix}": min_val,
        f"fecha_min_{prefix}": min_date,
        f"max_{prefix}": max_val,
        f"fecha_max_{prefix}": max_date,
        f"dist_min_{prefix}": last - min_val if pd.notna(min_val) else np.nan,
        f"dist_max_{prefix}": max_val - last if pd.notna(max_val) else np.nan,
        f"cobertura_{prefix}": float(len(w)),
    })
    if pd.notna(min_val) and pd.notna(max_val):
        rng = max_val - min_val
        if rng == 0:
            out[f"rango_plano_{prefix}"] = True
            out[f"dist_min_{prefix}"] = 0.0
            out[f"dist_max_{prefix}"] = 0.0
            out[f"lectura_posicion_{prefix}"] = "Sin variación en la ventana"
        else:
            pos = max(0.0, min(100.0, ((last - min_val) / rng) * 100))
            out[f"posicion_{prefix}_0_100"] = float(pos)
            out[f"lectura_posicion_{prefix}"] = _position_label(pos)
    return out


def distance_position_metrics(df_t: pd.DataFrame, freq: str) -> Dict[str, object]:
    d = df_t.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    out: Dict[str, object] = {
        "comentario_distancias": "Sin datos suficientes para medir posición en rangos.",
        "ventana_movil_observaciones_esperadas": np.nan,
        "ventana_movil_incompleta": False,
    }
    if d.empty:
        return out

    last_date = d["fecha"].max()
    ytd = d[d["fecha"].dt.year.eq(int(last_date.year))].copy()
    f = str(freq).upper()
    expected_map = {"D": 365, "W": 52, "M": 12, "Q": 4, "S": 2, "A": 10}
    expected = expected_map.get(f, periods_per_year(freq))
    if f == "D":
        start_mov = last_date - pd.Timedelta(days=365)
        movable = d[d["fecha"].ge(start_mov)].copy()
    else:
        movable = d.tail(min(expected, len(d))).copy()
    historical = d.copy()

    out.update(_window_position_metrics(ytd, "ytd"))
    out.update(_window_position_metrics(movable, "mov"))
    out.update(_window_position_metrics(historical, "hist"))
    out["ventana_movil_observaciones_esperadas"] = float(expected)
    out["ventana_movil_incompleta"] = bool(len(movable) < max(2, math.ceil(expected * 0.7)))
    out["semaforo_posicion_mov"] = _position_label(out.get("posicion_mov_0_100"))
    out["semaforo_posicion_ytd"] = _position_label(out.get("posicion_ytd_0_100"))
    out["semaforo_posicion_hist"] = _position_label(out.get("posicion_hist_0_100"))
    out["comentario_distancias"] = (
        f"El dato se ubica en {fmt_num(out.get('posicion_ytd_0_100'))} sobre 100 dentro del año, "
        f"en {fmt_num(out.get('posicion_mov_0_100'))} sobre 100 en la ventana móvil y "
        f"en {fmt_num(out.get('posicion_hist_0_100'))} sobre 100 frente a toda la historia."
    )
    return out


def history_metrics(df_t: pd.DataFrame, freq: str) -> Dict[str, object]:
    d = df_t.dropna(subset=["fecha", "valor"]).copy()
    out: Dict[str, object] = {
        "fecha_inicio_serie": "",
        "primer_valor_serie": np.nan,
        "maximo_historico_valor": np.nan,
        "fecha_maximo_historico": "",
        "minimo_historico_valor": np.nan,
        "fecha_minimo_historico": "",
        "promedio_historico_valor": np.nan,
        "percentil_historico_ultimo": np.nan,
        "maximo_52s_o_12m": np.nan,
        "fecha_maximo_reciente": "",
        "minimo_52s_o_12m": np.nan,
        "fecha_minimo_reciente": "",
        "maximo_anio_actual_valor": np.nan,
        "fecha_maximo_anio_actual": "",
        "minimo_anio_actual_valor": np.nan,
        "fecha_minimo_anio_actual": "",
        "maximo_analisis": np.nan,
        "fecha_maximo_analisis": "",
        "minimo_analisis": np.nan,
        "fecha_minimo_analisis": "",
        "percentil_analisis_ultimo": np.nan,
    }
    if d.empty:
        return out
    out["fecha_inicio_serie"] = d["fecha"].iloc[0].date().isoformat()
    out["primer_valor_serie"] = float(d["valor"].iloc[0])
    out["maximo_historico_valor"], out["fecha_maximo_historico"] = date_value_at_extreme(d, "valor", "max")
    out["minimo_historico_valor"], out["fecha_minimo_historico"] = date_value_at_extreme(d, "valor", "min")
    out["promedio_historico_valor"] = float(d["valor"].mean())
    out["percentil_historico_ultimo"] = pct_rank_last(d["valor"])
    recent_n = periods_per_year(freq)
    recent = d.tail(recent_n) if len(d) > recent_n else d
    out["maximo_52s_o_12m"], out["fecha_maximo_reciente"] = date_value_at_extreme(recent, "valor", "max")
    out["minimo_52s_o_12m"], out["fecha_minimo_reciente"] = date_value_at_extreme(recent, "valor", "min")
    last_year = int(d["fecha"].max().year)
    ytd = d[d["fecha"].dt.year.eq(last_year)].copy()
    out["maximo_anio_actual_valor"], out["fecha_maximo_anio_actual"] = date_value_at_extreme(ytd, "valor", "max")
    out["minimo_anio_actual_valor"], out["fecha_minimo_anio_actual"] = date_value_at_extreme(ytd, "valor", "min")
    da = df_t.dropna(subset=["fecha", "valor_analisis"]).copy()
    if not da.empty:
        out["maximo_analisis"], out["fecha_maximo_analisis"] = date_value_at_extreme(da, "valor_analisis", "max")
        out["minimo_analisis"], out["fecha_minimo_analisis"] = date_value_at_extreme(da, "valor_analisis", "min")
        out["percentil_analisis_ultimo"] = pct_rank_last(da["valor_analisis"])
    return out


def trend_metrics(df_t: pd.DataFrame, freq: str) -> Dict[str, object]:
    n, min_n = trend_fit_window_for_frequency(freq)
    d = df_t.dropna(subset=["fecha", "valor_analisis"]).tail(n).copy()
    out: Dict[str, object] = {
        "tendencia_valor_estimado_ultimo": np.nan,
        "desvio_frente_tendencia": np.nan,
        "desvio_tendencia_std": np.nan,
        "posicion_vs_tendencia": "Sin datos",
        "tendencia_12m_pendiente": np.nan,
        "tendencia_12m_cambio": np.nan,
        "tendencia_12m_direccion": "Sin datos",
    }
    if len(d) < min_n:
        return out
    y = d["valor_analisis"].astype(float).to_numpy()
    x = np.arange(len(y), dtype=float)
    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return out
    fitted = intercept + slope * x
    resid = y - fitted
    std = resid.std(ddof=0)
    dev = y[-1] - fitted[-1]
    z = dev / std if std and not np.isnan(std) else 0.0
    if z > 2:
        pos = "Por encima de tendencia, desvio fuerte"
    elif z > 1:
        pos = "Por encima de tendencia"
    elif z < -2:
        pos = "Por debajo de tendencia, desvio fuerte"
    elif z < -1:
        pos = "Por debajo de tendencia"
    else:
        pos = "En linea con tendencia"
    out.update({
        "tendencia_valor_estimado_ultimo": float(fitted[-1]),
        "desvio_frente_tendencia": float(dev),
        "desvio_tendencia_std": float(z),
        "posicion_vs_tendencia": pos,
    })
    last12_n = trend_window_for_frequency(freq, len(d))
    if last12_n >= 2:
        d12 = d.tail(last12_n)
        y12 = d12["valor_analisis"].astype(float).to_numpy()
        x12 = np.arange(len(y12), dtype=float)
        try:
            slope12, _ = np.polyfit(x12, y12, 1)
            change12 = y12[-1] - y12[0]
            if slope12 > 0:
                direction12 = "Al alza"
            elif slope12 < 0:
                direction12 = "A la baja"
            else:
                direction12 = "Estable"
            out.update({
                "tendencia_12m_pendiente": float(slope12),
                "tendencia_12m_cambio": float(change12),
                "tendencia_12m_direccion": direction12,
            })
        except Exception:
            pass
    return out


def freshness_state(freq: str, days: Optional[int]) -> str:
    if days is None or np.isnan(days):
        return "Sin fecha"
    f = str(freq).upper()
    thresholds = {"D": 5, "W": 15, "M": 45, "Q": 120, "S": 220, "A": 450}
    lim = thresholds.get(f, 90)
    return "Actualizada" if days <= lim else "Rezagada"


def class_windows(freq: str) -> Dict[str, int]:
    f = str(freq).upper()
    if f == "D":
        return {"short": 20, "medium": 60, "long": 252, "z": 60}
    if f == "W":
        return {"short": 8, "medium": 26, "long": 104, "z": 26}
    if f == "Q":
        return {"short": 4, "medium": 8, "long": 20, "z": 12}
    if f == "A":
        return {"short": 2, "medium": 3, "long": 8, "z": 8}
    return {"short": 3, "medium": 6, "long": 24, "z": 24}


def moving_average_metrics(df_t: pd.DataFrame, freq: str) -> Dict[str, float]:
    d = df_t.dropna(subset=["valor"]).copy()
    if d.empty:
        return {}
    windows = [5, 20, 60, 252] if str(freq).upper() == "D" else [3, 6, 12]
    out = {}
    for n in windows:
        label = f"media_movil_{n}{'d' if str(freq).upper() == 'D' else 'p'}"
        out[label] = float(d["valor"].tail(n).mean()) if len(d) >= min(n, 3) else np.nan
    return out


def diagnostic_from_state(estado: str) -> str:
    return {
        "Al alza": "Tendencia al alza",
        "Normal": "Tendencia estable",
        "A la baja": "Tendencia a la baja",
        "Sin datos": "Sin datos",
        "Verde": "Normal",
        "Amarillo": "Vigilancia",
        "Rojo": "Critica",
        "Gris": "Sin datos",
    }.get(str(estado), "Sin datos")


def trend_regime_from_12m(freq: str, analysis: pd.Series, metrics: Dict[str, object]) -> Tuple[str, str, Dict[str, float]]:
    a = analysis.dropna().astype(float)
    change12 = metrics.get("tendencia_12m_cambio", np.nan)
    slope12 = metrics.get("tendencia_12m_pendiente", np.nan)
    aux: Dict[str, float] = {
        "umbral_regimen_tendencia": np.nan,
        "cambio_regimen_tendencia": change12,
    }
    if len(a) < 2 or pd.isna(change12) or pd.isna(slope12):
        return "Sin datos", "Sin datos suficientes para clasificar la tendencia de 12 meses.", aux

    periods = trend_window_for_frequency(freq, len(a))
    if periods < 2:
        return "Sin datos", "Sin datos suficientes para clasificar la tendencia por frecuencia.", aux
    recent = a.tail(max(periods * 2, periods + 1))
    diff_std = recent.diff().dropna().std(ddof=0)
    level_anchor = max(abs(float(recent.iloc[-1])) if len(recent) else 0.0, 1.0)
    threshold_candidates = []
    if pd.notna(diff_std) and diff_std > 0:
        threshold_candidates.append(float(diff_std) * math.sqrt(periods) * 0.35)
    threshold_candidates.append(level_anchor * 0.01)
    threshold = max(threshold_candidates)
    aux["umbral_regimen_tendencia"] = float(threshold)

    change = float(change12)
    pos_mov = metrics.get("posicion_mov_0_100", np.nan)
    pos_ytd = metrics.get("posicion_ytd_0_100", np.nan)
    high_zone = pd.notna(pos_mov) and float(pos_mov) >= 60
    low_zone = pd.notna(pos_mov) and float(pos_mov) <= 40
    ytd_high = pd.notna(pos_ytd) and float(pos_ytd) >= 60
    ytd_low = pd.notna(pos_ytd) and float(pos_ytd) <= 40

    if abs(change) <= threshold and not high_zone and not low_zone:
        return (
            "Normal",
            f"Tendencia estable: cambio de {fmt_num(change)} dentro del umbral prudente de {fmt_num(threshold)} y posición móvil en zona media.",
            aux,
        )
    if change > threshold or (high_zone and ytd_high):
        return (
            "Al alza",
            f"Régimen al alza: cambio 12m de {fmt_num(change)}, posición móvil {fmt_num(pos_mov)} sobre 100 y posición anual {fmt_num(pos_ytd)} sobre 100.",
            aux,
        )
    if change < -threshold or (low_zone and ytd_low):
        return (
            "A la baja",
            f"Régimen a la baja: cambio 12m de {fmt_num(change)}, posición móvil {fmt_num(pos_mov)} sobre 100 y posición anual {fmt_num(pos_ytd)} sobre 100.",
            aux,
        )
    return (
        "Normal",
        f"Régimen normal: la tendencia 12m y la posición 0-100 no confirman una zona alta o baja persistente.",
        aux,
    )


def fmt_num(x: object, ndigits: int = 2) -> str:
    try:
        if pd.isna(x):
            return "no disponible"
        return f"{float(x):,.{ndigits}f}"
    except Exception:
        return str(x or "no disponible")


def fmt_pct(x: object) -> str:
    return "no disponible" if pd.isna(x) else f"{float(x):.2f}%"


def days_without_change(df_t: pd.DataFrame) -> Optional[int]:
    d = df_t.dropna(subset=["fecha", "valor"]).copy()
    if len(d) < 2:
        return None
    last = d["valor"].iloc[-1]
    changed = d[d["valor"].ne(last)]
    if changed.empty:
        return int((d["fecha"].iloc[-1] - d["fecha"].iloc[0]).days)
    return int((d["fecha"].iloc[-1] - changed["fecha"].iloc[-1]).days)


def build_economic_reading(code: str, name: str, clase: str, transform: str, criterio: str, estado: str, diagnostico: str, df_t: pd.DataFrame, metrics: Dict[str, object], freq: str = "") -> str:
    d = df_t.dropna(subset=["fecha", "valor"]).copy()
    if d.empty:
        return "La serie no cuenta con datos suficientes para una lectura economica automatica."
    last_date = d["fecha"].max().date().isoformat()
    last_value = safe_last(d["valor"])
    cls = low_ascii(clase)
    if cls == "politica_monetaria_step":
        dsc = days_without_change(df_t)
        last_change = metrics.get("cambio_ultimo_pbs", np.nan)
        return (
            f"La serie {code} registra un ultimo dato de {fmt_num(last_value)} al {last_date}. "
            f"La tasa de politica se evalua como evento discreto; el ultimo cambio fue de {fmt_num(last_change, 0)} puntos basicos. "
            f"Permanece {dsc if dsc is not None else 'no disponible'} dias sin variacion. Diagnostico: {diagnostico}."
        )
    if cls in {"precio_financiero_diario", "commodity", "precio_financiero", "tipo_cambio", "serie_diaria_generica"}:
        return (
            f"La serie {code} registra un ultimo valor de {fmt_num(last_value)} al {last_date}. "
            f"El tratamiento aplicado fue {criterio} "
            f"El desvio frente a la tendencia reciente fue de {fmt_num(metrics.get('desvio_tendencia_std'))} desviaciones estandar. "
            f"El maximo reciente fue {fmt_num(metrics.get('maximo_52s_o_12m'))} el {metrics.get('fecha_maximo_reciente', '')}; "
            f"el minimo reciente fue {fmt_num(metrics.get('minimo_52s_o_12m'))} el {metrics.get('fecha_minimo_reciente', '')}. Diagnostico: {diagnostico}."
        )
    if str(freq).upper() == "A":
        return (
            f"La serie {code} registra un ultimo dato anual de {fmt_num(last_value)} al {last_date}. "
            f"El tratamiento aplicado fue {criterio} "
            f"El ultimo dato se ubica {metrics.get('posicion_vs_tendencia', 'sin datos').lower()}, con un desvio de {fmt_num(metrics.get('desvio_tendencia_std'))} desviaciones estandar. "
            f"La variacion frente al ano anterior fue {fmt_pct(metrics.get('var_interanual_pct'))}. "
            f"El maximo historico fue {fmt_num(metrics.get('maximo_historico_valor'))} el {metrics.get('fecha_maximo_historico', '')}; "
            f"el minimo historico fue {fmt_num(metrics.get('minimo_historico_valor'))} el {metrics.get('fecha_minimo_historico', '')}. Diagnostico: {diagnostico}."
        )
    return (
        f"La serie {code} registra un ultimo dato de {fmt_num(last_value)} al {last_date}. "
        f"El tratamiento aplicado fue {criterio} "
        f"El ultimo dato se ubica {metrics.get('posicion_vs_tendencia', 'sin datos').lower()}, con un desvio de {fmt_num(metrics.get('desvio_tendencia_std'))} desviaciones estandar. "
        f"La variacion anual movil fue {fmt_pct(metrics.get('var_ventana_anual_vs_previa_pct'))}, mientras que el acumulado del ano registro {fmt_pct(metrics.get('var_acumulada_anio_pct'))}. "
        f"El maximo historico fue {fmt_num(metrics.get('maximo_historico_valor'))} el {metrics.get('fecha_maximo_historico', '')}; "
        f"el minimo historico fue {fmt_num(metrics.get('minimo_historico_valor'))} el {metrics.get('fecha_minimo_historico', '')}. Diagnostico: {diagnostico}."
    )


def evaluate_regime(clase: str, freq: str, original: pd.Series, analysis: pd.Series, metrics: Dict[str, float]) -> Tuple[str, str, Dict[str, float]]:
    cls = low_ascii(clase)
    f = str(freq).upper()
    x = original.dropna().astype(float)
    a = analysis.dropna().astype(float)
    aux = {}
    if x.empty:
        return "Gris", "Sin datos suficientes para evaluar la serie.", aux
    last = float(x.iloc[-1])
    last_a = float(a.iloc[-1]) if len(a) else np.nan
    z = abs(metrics.get("z_rolling", np.nan))
    rz = abs(metrics.get("robust_z", np.nan))
    pct = metrics.get("percentil_historico", np.nan)
    vol = metrics.get("volatilidad_ratio", np.nan)
    is_max = bool(metrics.get("maximo_historico", False))
    is_min = bool(metrics.get("minimo_historico", False))
    w = class_windows(freq)

    def state(score: int, reading: str) -> Tuple[str, str, Dict[str, float]]:
        if score >= 2:
            return "Rojo", reading, aux
        if score == 1:
            return "Amarillo", reading, aux
        return "Verde", reading, aux

    # Política monetaria: se evalúa como evento discreto, no como tendencia de mercado.
    if cls == "politica_monetaria_step":
        d1 = recent_window_delta(x, 1, 100)
        d20 = recent_window_delta(x, w["short"], 100)
        d60 = recent_window_delta(x, w["medium"], 100)
        aux.update({"cambio_ultimo_pbs": d1, "cambio_corto_pbs": d20, "cambio_medio_pbs": d60})
        if pd.notna(d1) and abs(d1) >= 25:
            return state(2, f"Cambio reciente de política: {d1:.0f} pbs frente al dato previo.")
        if pd.notna(d20) and abs(d20) >= 50:
            return state(2, f"Ajuste acumulado relevante en ventana corta: {d20:.0f} pbs.")
        if (pd.notna(d20) and abs(d20) >= 25) or (pd.notna(d60) and abs(d60) >= 50):
            return state(1, f"Señal moderada de ajuste acumulado: {d20:.0f} pbs en ventana corta.")
        return state(0, f"Tasa estable en {last:.2f}%; no hay cambio reciente de postura.")

    if cls in {"tasa_interbancaria", "tasa_mercado", "tasa_pct"}:
        d1 = recent_window_delta(x, 1, 100)
        d20 = recent_window_delta(x, w["short"], 100)
        d60 = recent_window_delta(x, w["medium"], 100)
        aux.update({"cambio_ultimo_pbs": d1, "cambio_corto_pbs": d20, "cambio_medio_pbs": d60})
        score = 0
        reasons = []
        if pd.notna(d20) and abs(d20) >= 75:
            score = max(score, 2); reasons.append(f"reprecificación de {d20:.0f} pbs en ventana corta")
        elif pd.notna(d20) and abs(d20) >= 35:
            score = max(score, 1); reasons.append(f"movimiento de {d20:.0f} pbs en ventana corta")
        if pd.notna(z) and z >= 3:
            score = max(score, 2); reasons.append(f"cambio atípico por z-score ({z:.1f})")
        elif pd.notna(z) and z >= 2:
            score = max(score, 1); reasons.append(f"cambio moderadamente atípico por z-score ({z:.1f})")
        if pd.notna(vol) and vol >= 2.0:
            score = max(score, 1); reasons.append("aumento de volatilidad")
        return state(score, "; ".join(reasons) if reasons else f"Sin reprecificación relevante; último nivel {last:.2f}%.")

    if cls in {"spread_riesgo", "spread_pbs"}:
        d20 = recent_window_delta(x, w["short"], 1)
        d60 = recent_window_delta(x, w["medium"], 1)
        aux.update({"cambio_corto_pbs": d20, "cambio_medio_pbs": d60})
        score = 0; reasons=[]
        if pd.notna(pct) and pct >= 90:
            score = max(score, 2); reasons.append(f"nivel en percentil {pct:.0f}")
        elif pd.notna(pct) and pct >= 75:
            score = max(score, 1); reasons.append(f"nivel relativamente alto, percentil {pct:.0f}")
        if pd.notna(d20) and d20 >= 50:
            score = max(score, 2); reasons.append(f"aumento de {d20:.0f} pbs en ventana corta")
        elif pd.notna(d20) and d20 >= 25:
            score = max(score, 1); reasons.append(f"aumento de {d20:.0f} pbs en ventana corta")
        if pd.notna(d60) and d60 <= -50 and score == 0:
            reasons.append(f"mejora acumulada de {abs(d60):.0f} pbs")
        return state(score, "; ".join(reasons) if reasons else f"Riesgo país sin deterioro relevante; nivel actual {last:.0f} pbs.")

    if cls in {"tipo_cambio", "commodity", "precio_financiero", "precio_financiero_diario", "serie_diaria_generica"}:
        score = 0; reasons=[]
        if pd.notna(z) and z >= 3:
            score = max(score, 2); reasons.append(f"retorno extremo, z={z:.1f}")
        elif pd.notna(z) and z >= 2:
            score = max(score, 1); reasons.append(f"retorno elevado, z={z:.1f}")
        if pd.notna(vol) and vol >= 2.5:
            score = max(score, 2); reasons.append("salto fuerte de volatilidad")
        elif pd.notna(vol) and vol >= 1.7:
            score = max(score, 1); reasons.append("mayor volatilidad reciente")
        if is_max or is_min:
            score = max(score, 1); reasons.append("nuevo extremo histórico")
        return state(score, "; ".join(reasons) if reasons else "Sin shock financiero relevante en la ventana reciente.")

    if cls == "inflacion_12m" or (cls == "variacion_pct" and "inflacion" in low_ascii(str(metrics.get("nombre", "")))):
        d3 = recent_window_delta(x, 3 if f == "M" else 1, 1)
        d6 = recent_window_delta(x, 6 if f == "M" else 2, 1)
        aux.update({"cambio_3m_pp": d3, "cambio_6m_pp": d6})
        score = 0; reasons=[]
        if last > 4.0 or last < 0:
            score = max(score, 2); reasons.append(f"inflación anual fuera de zona confortable: {last:.2f}%")
        elif last > 3.0 or last < 1.0:
            score = max(score, 1); reasons.append(f"inflación anual fuera del rango 1%-3%: {last:.2f}%")
        if pd.notna(d6) and abs(d6) >= 1.5:
            score = max(score, 2); reasons.append(f"cambio de {d6:.2f} pp en seis meses")
        elif pd.notna(d3) and abs(d3) >= 0.7:
            score = max(score, 1); reasons.append(f"cambio de {d3:.2f} pp en tres meses")
        return state(score, "; ".join(reasons) if reasons else f"Inflación anual estable en {last:.2f}%.")

    if cls == "inflacion_mensual":
        score = 0; reasons=[]
        if pd.notna(z) and z >= 2.5:
            score = max(score, 2); reasons.append(f"inflación mensual atípica, z={z:.1f}")
        elif pd.notna(z) and z >= 1.8:
            score = max(score, 1); reasons.append(f"inflación mensual por encima del patrón reciente, z={z:.1f}")
        ma3 = x.iloc[-3:].mean() if len(x) >= 3 else np.nan
        aux["prom_3m"] = ma3
        if pd.notna(ma3) and ma3 >= 0.45:
            score = max(score, 1); reasons.append(f"promedio 3m elevado: {ma3:.2f}% mensual")
        return state(score, "; ".join(reasons) if reasons else f"Inflación mensual sin desvío relevante: {last:.2f}%.")

    if cls in {"actividad_var_interanual", "mercado_laboral_nivel", "sector_externo_flujo", "saldo_nominal", "flujo_fiscal", "indice_nivel", "valor_monetario", "volumen_fisico", "stock_financiero"}:
        # Se evalúa la serie transformada, usualmente crecimiento interanual.
        score = 0; reasons=[]
        ma_short = a.iloc[-w["short"]:].mean() if len(a) >= w["short"] else a.tail(min(3, len(a))).mean()
        ma_prev = a.iloc[-2*w["short"]:-w["short"]].mean() if len(a) >= 2*w["short"] else np.nan
        aux.update({"promedio_reciente_analisis": ma_short, "promedio_previo_analisis": ma_prev})
        if pd.notna(z) and z >= 2.8:
            score = max(score, 2); reasons.append(f"desvío fuerte frente a ventana reciente, z={z:.1f}")
        elif pd.notna(z) and z >= 2.0:
            score = max(score, 1); reasons.append(f"desvío moderado frente a ventana reciente, z={z:.1f}")
        if pd.notna(ma_short) and pd.notna(ma_prev):
            dif = ma_short - ma_prev
            aux["dif_promedios_analisis"] = dif
            if cls == "actividad_var_interanual" and ma_short < 0:
                score = max(score, 2); reasons.append("promedio reciente en contracción")
            elif abs(dif) >= 5:
                score = max(score, 1); reasons.append(f"cambio de tendencia de {dif:.1f} pp entre ventanas")
        if is_max or is_min:
            score = max(score, 1); reasons.append("último dato en extremo histórico")
        return state(score, "; ".join(reasons) if reasons else "Sin cambio de régimen relevante en crecimiento o tendencia reciente.")

    if cls in {"mercado_laboral_tasa", "ratio", "ratio_financiero", "ratio_fiscal", "ratio_pct", "balance_externo", "balance_flujo", "variacion_ya_calculada", "variacion_pct", "nivel_generico"}:
        score = 0; reasons=[]
        d_short = recent_window_delta(x, w["short"], 1)
        aux["cambio_corto"] = d_short
        if pd.notna(z) and z >= 2.8:
            score = max(score, 2); reasons.append(f"nivel atípico, z={z:.1f}")
        elif pd.notna(z) and z >= 2.0:
            score = max(score, 1); reasons.append(f"nivel moderadamente atípico, z={z:.1f}")
        if is_max or is_min:
            score = max(score, 1); reasons.append("último dato en extremo histórico")
        return state(score, "; ".join(reasons) if reasons else "Nivel sin desvío relevante frente a su historia reciente.")

    return state(0, "Serie evaluada con regla general; sin alerta relevante.")


def analyze_series(df_raw: pd.DataFrame, meta: SeriesMeta, api_meta: Optional[Dict[str, str]] = None, asof: Optional[date] = None) -> Tuple[Dict[str, object], pd.DataFrame]:
    api_meta = api_meta or {}
    asof_ts = pd.Timestamp(asof or date.today())
    freq = infer_frequency(meta.codigo, meta.frecuencia or api_meta.get("frecuencia_api", ""))
    row_like = {
        "codigo": meta.codigo, "nombre": meta.nombre, "frecuencia": meta.frecuencia, "clase_serie": meta.clase_serie,
        "tratamiento": meta.tratamiento, "nombre_bcrp": api_meta.get("nombre_api", ""),
        "categoria_bcrp": meta.categoria_bcrp, "grupo_bcrp": meta.grupo_bcrp, "seccion_bcrp": meta.seccion_bcrp, "unidad_medida": meta.unidad_medida,
        "sentido_economico": meta.sentido_economico,
    }
    clase = meta.clase_serie if meta.clase_serie and meta.clase_serie != "auto" else classify_series(row_like)
    row_like["clase_serie"] = clase
    transform = final_transform(row_like)
    df_t = transform_series(df_raw, transform, freq)
    if df_t.empty:
        raise ValueError(f"Serie vacía para {meta.codigo}")

    last_date = df_t["fecha"].max()
    # No permitir fechas futuras
    if pd.notna(last_date) and last_date > asof_ts:
        last_date = asof_ts
    days = int((asof_ts - last_date).days) if pd.notna(last_date) else None
    windows = class_windows(freq)
    stats = rolling_stats(df_t["valor_analisis"], windows["z"])
    vol = volatility_ratio(df_t["valor_analisis"], windows["short"], windows["long"])
    is_max, is_min = historical_extreme(df_t["valor"])
    ann = annual_average_metrics(df_t)
    metrics = {
        "z_rolling": stats["z"],
        "robust_z": stats["robust_z"],
        "media_ventana": stats["mean"],
        "desv_ventana": stats["std"],
        "volatilidad_ratio": vol,
        "page_hinkley": page_hinkley_score(df_t["valor_analisis"]),
        "percentil_historico": pct_rank_last(df_t["valor"]),
        "drawdown_pct": drawdown_pct(df_t["valor"]),
        "maximo_historico": is_max,
        "minimo_historico": is_min,
        "pendiente_corta": trend_slope(df_t["valor_analisis"], windows["short"]),
        **ann,
    }
    metrics.update(comparison_metrics(df_t, clase, freq))
    metrics.update(history_metrics(df_t, freq))
    metrics.update(distance_position_metrics(df_t, freq))
    metrics.update(trend_metrics(df_t, freq))
    metrics.update(moving_average_metrics(df_t, freq))
    metrics.update(current_previous_metrics(df_t, freq))
    alerta_metodologica, lectura_regla, aux = evaluate_regime(clase, freq, df_t["valor"], df_t["valor_analisis"], metrics)
    metrics.update(aux)
    estado, lectura, trend_aux = trend_regime_from_12m(freq, df_t["valor_analisis"], metrics)
    metrics.update(trend_aux)
    freshness = freshness_state(freq, days)
    sentido = infer_sentido_economico(row_like, clase)
    diagnostico = diagnostic_from_state(estado)
    criterio = treatment_criterion(clase, transform, freq)
    lectura_ejecutiva = build_economic_reading(
        meta.codigo, meta.nombre or api_meta.get("nombre_api", meta.codigo), clase, transform, criterio, estado, diagnostico, df_t, metrics, freq
    )
    result = {
        "codigo": meta.codigo,
        "nombre": meta.nombre or api_meta.get("nombre_api", meta.codigo),
        "nombre_bcrp": meta.nombre or api_meta.get("nombre_api", meta.codigo),
        "nombre_api": api_meta.get("nombre_api", ""),
        "frecuencia": frequency_name(freq),
        "frecuencia_bcrp": frequency_name(freq),
        "frecuencia_codigo": freq,
        "bloque": meta.bloque,
        "uso_analitico": meta.uso_analitico,
        "clase_serie": clase,
        "tratamiento": transform,
        "tratamiento_base": transform,
        "criterio_tratamiento": criterio,
        "sentido_economico": sentido,
        "ultima_fecha": last_date.date().isoformat() if pd.notna(last_date) else "",
        "dias_desde_ultimo_dato": days,
        "estado_actualizacion": freshness,
        "ultimo_valor": safe_last(df_t["valor"]),
        "ultimo_dato_original": safe_last(df_t["valor"]),
        "ultimo_valor_analisis": safe_last(df_t["valor_analisis"]),
        "ultimo_dato_analisis": safe_last(df_t["valor_analisis"]),
        "dato_actual_original": metrics.get("dato_actual_original", np.nan),
        "dato_anterior_original": metrics.get("dato_anterior_original", np.nan),
        "dato_anio_anterior_original": metrics.get("dato_anio_anterior_original", np.nan),
        "fecha_dato_actual": metrics.get("fecha_dato_actual", ""),
        "fecha_dato_anterior": metrics.get("fecha_dato_anterior", ""),
        "fecha_dato_anio_anterior": metrics.get("fecha_dato_anio_anterior", ""),
        "dato_actual_analisis": metrics.get("dato_actual_analisis", np.nan),
        "dato_anterior_analisis": metrics.get("dato_anterior_analisis", np.nan),
        "dato_anio_anterior_analisis": metrics.get("dato_anio_anterior_analisis", np.nan),
        "estado": estado,
        "semaforo": estado,
        "regimen_tendencia": estado,
        "diagnostico": diagnostico,
        "lectura": lectura_ejecutiva,
        "lectura_regla": lectura,
        "comentario_distancias": metrics.get("comentario_distancias", ""),
        "alerta_metodologica": alerta_metodologica,
        "lectura_alerta_metodologica": lectura_regla,
        "url_api": api_meta.get("url_api", ""),
        "metadata_encontrado": bool(meta.categoria_bcrp or meta.grupo_bcrp or meta.seccion_bcrp or meta.fecha_actualizacion_meta),
        "categoria_bcrp": meta.categoria_bcrp,
        "grupo_bcrp": meta.grupo_bcrp,
        "seccion_bcrp": meta.seccion_bcrp,
        "unidad_medida": meta.unidad_medida,
        "escala": meta.escala,
        "fecha_actualizacion_meta": meta.fecha_actualizacion_meta,
        "fecha_actualizacion_metadata": meta.fecha_actualizacion_meta,
        "fecha_inicio_meta": meta.fecha_inicio_meta,
        "fecha_inicio_metadata": meta.fecha_inicio_meta,
        "fecha_fin_meta": meta.fecha_fin_meta,
        "fecha_fin_metadata": meta.fecha_fin_meta,
        "prioridad": meta.prioridad,
        "tipo_variable": meta.tipo_variable,
        "subtipo_variable": meta.subtipo_variable,
        "ventana_variacion": meta.ventana_variacion,
        "categoria_operativa": meta.categoria_operativa,
        "unidad_inferida": meta.unidad_inferida,
        "regla_aplicada": meta.regla_aplicada,
        "confianza_tipo_variable": meta.confianza_tipo_variable,
        "requiere_revision_manual": meta.requiere_revision_manual,
    }
    result.update(metrics)
    return result, df_t


def series_meta_from_row(row: pd.Series) -> SeriesMeta:
    rowd = row.to_dict()
    clase = rowd.get("clase_serie", "auto") or "auto"
    if clase == "auto":
        clase = classify_series(rowd)
    tmp = dict(rowd)
    tmp["clase_serie"] = clase
    tratamiento = rowd.get("tratamiento", "auto") or "auto"
    if tratamiento == "auto":
        tratamiento = final_transform(tmp)
    return SeriesMeta(
        codigo=clean_code(rowd.get("codigo", "")),
        nombre=norm_text(rowd.get("nombre", "") or rowd.get("nombre_bcrp", "")),
        frecuencia=norm_text(rowd.get("frecuencia", "") or rowd.get("frecuencia_bcrp", "")),
        bloque=norm_text(rowd.get("bloque", "")),
        uso_analitico=norm_text(rowd.get("uso_analitico", "")),
        tratamiento=tratamiento,
        clase_serie=clase,
        categoria_bcrp=norm_text(rowd.get("categoria_bcrp", "")),
        grupo_bcrp=norm_text(rowd.get("grupo_bcrp", "")),
        seccion_bcrp=norm_text(rowd.get("seccion_bcrp", "")),
        unidad_medida=norm_text(rowd.get("unidad_medida", "")),
        escala=norm_text(rowd.get("escala", "")),
        fecha_actualizacion_meta=norm_text(rowd.get("fecha_actualizacion_meta", "")),
        fecha_inicio_meta=norm_text(rowd.get("fecha_inicio_meta", "")),
        fecha_fin_meta=norm_text(rowd.get("fecha_fin_meta", "")),
        sentido_economico=norm_text(rowd.get("sentido_economico", "")),
        prioridad=norm_text(rowd.get("prioridad", "")),
        tipo_variable=norm_text(rowd.get("tipo_variable", "")),
        subtipo_variable=norm_text(rowd.get("subtipo_variable", "")),
        ventana_variacion=norm_text(rowd.get("ventana_variacion", "")),
        categoria_operativa=norm_text(rowd.get("categoria_operativa", "")),
        unidad_inferida=norm_text(rowd.get("unidad_inferida", "")),
        regla_aplicada=norm_text(rowd.get("regla_aplicada", "")),
        confianza_tipo_variable=norm_text(rowd.get("confianza_tipo_variable", "")),
        requiere_revision_manual=norm_text(rowd.get("requiere_revision_manual", "")),
    )


def dataframe_to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    max_excel_rows = 1_000_000

    def clean_df(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out = out.loc[:, ~out.columns.duplicated()].copy()
        out.columns = [re.sub(r"\s+", "_", str(c)).strip("_")[:120] for c in out.columns]
        numeric_cols = out.select_dtypes(include=[np.number]).columns
        if len(numeric_cols):
            out[numeric_cols] = out[numeric_cols].round(2)
        for col in out.columns:
            out[col] = out[col].map(lambda v: str(v) if isinstance(v, (list, dict, tuple, set)) else v)
        return out.where(pd.notna(out), "")

    def split_df(df: pd.DataFrame) -> List[pd.DataFrame]:
        if len(df) <= max_excel_rows:
            return [df]
        return [df.iloc[i:i + max_excel_rows].copy() for i in range(0, len(df), max_excel_rows)]

    def safe_sheet_name(base_name: str, part: Optional[int] = None) -> str:
        suffix = f"_{part}" if part is not None else ""
        base_len = 31 - len(suffix)
        safe = re.sub(r"[^A-Za-z0-9_ ]", "", base_name)[:base_len].strip() or "Hoja"
        return f"{safe}{suffix}"

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for name, df in sheets.items():
            df = clean_df(df)
            parts = split_df(df)
            for part_idx, part_df in enumerate(parts, start=1):
                safe = safe_sheet_name(name, part_idx if len(parts) > 1 else None)
                part_df.to_excel(writer, sheet_name=safe, index=False)
                ws = writer.sheets[safe]
                wb = writer.book
                header_fmt = wb.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1})
                for idx, col in enumerate(part_df.columns):
                    ws.write(0, idx, col, header_fmt)
                width_sample = part_df.head(5000)
                for idx, col in enumerate(part_df.columns):
                    if len(width_sample):
                        content_width = int(width_sample[col].astype(str).map(len).quantile(0.8)) + 2
                    else:
                        content_width = 12
                    width = min(max(len(str(col)) + 2, content_width), 45)
                    ws.set_column(idx, idx, width)
                sem_col = next((i for i, c in enumerate(part_df.columns) if c.lower() in {"semaforo", "estado"}), None)
                if sem_col is not None and len(part_df):
                    colors = {
                        "Al alza": "#B7D7F7",
                        "Normal": "#D9EAD3",
                        "A la baja": "#F4CCCC",
                        "Sin datos": "#D9E1F2",
                        "Verde": "#C6EFCE",
                        "Amarillo": "#FFEB9C",
                        "Rojo": "#FFC7CE",
                        "Gris": "#D9E1F2",
                    }
                    for value, color in colors.items():
                        fmt = wb.add_format({"bg_color": color})
                        ws.conditional_format(1, sem_col, len(part_df), sem_col, {"type": "text", "criteria": "containing", "value": value, "format": fmt})
    return output.getvalue()
