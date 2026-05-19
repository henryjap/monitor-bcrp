import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
from pathlib import Path
import traceback
from constants import *


def executive_cols(result_df: pd.DataFrame) -> list[str]:
    cols = [
        "semaforo",
        "regimen_tendencia",
        "diagnostico",
        "codigo",
        "nombre_bcrp",
        "categoria_bcrp",
        "clase_serie",
        "grupo_bcrp",
        "seccion_bcrp",
        "frecuencia_bcrp",
        "ultima_fecha",
        "dato_actual_original",
        "dato_anterior_original",
        "dato_anio_anterior_original",
        "var_interanual_pct",
        "posicion_vs_tendencia",
        "posicion_ytd_0_100",
        "posicion_mov_0_100",
        "posicion_hist_0_100",
        "tendencia_12m_cambio",
        "umbral_regimen_tendencia",
        "estado_actualizacion",
        "dias_desde_ultimo_dato",
        "percentil_historico_ultimo",
        "revision_requerida",
    ]
    return [c for c in cols if c in result_df.columns]


def technical_cols(result_df: pd.DataFrame) -> list[str]:
    cols = [
        "semaforo",
        "regimen_tendencia",
        "diagnostico",
        "codigo",
        "nombre_bcrp",
        "categoria_bcrp",
        "clase_serie",
        "grupo_bcrp",
        "seccion_bcrp",
        "frecuencia_bcrp",
        "unidad_medida",
        "tipo_variable",
        "subtipo_variable",
        "ventana_variacion",
        "categoria_operativa",
        "ultima_fecha",
        "dias_desde_ultimo_dato",
        "estado_actualizacion",
        "dato_actual_original",
        "dato_anterior_original",
        "dato_anio_anterior_original",
        "dato_actual_analisis",
        "dato_anterior_analisis",
        "dato_anio_anterior_analisis",
        "var_interanual_pct",
        "percentil_historico_ultimo",
        "tendencia_12m_pendiente",
        "tendencia_12m_direccion",
        "tendencia_12m_cambio",
        "umbral_regimen_tendencia",
        "posicion_ytd_0_100",
        "posicion_mov_0_100",
        "posicion_hist_0_100",
        "revision_requerida",
        "tratamiento",
        "confianza_clasificacion",
        "motivo_clasificacion",
        "alertas_clasificacion",
        "override_clasificacion",
        "override_comentario",
        "lectura",
    ]
    return [c for c in cols if c in result_df.columns]


def anomaly_panel_df(result_df: pd.DataFrame) -> pd.DataFrame:
    out = result_df.copy()
    score = pd.Series(0, index=out.index, dtype=float)
    if "desvio_tendencia_std" in out.columns:
        score += out["desvio_tendencia_std"].abs().fillna(0)
    if "percentil_historico_ultimo" in out.columns:
        score += (out["percentil_historico_ultimo"].fillna(50) - 50).abs() / 25
    if "dias_desde_ultimo_dato" in out.columns:
        score += (out["dias_desde_ultimo_dato"].fillna(0) / 90).clip(upper=3)
    out["score_anomalia"] = score
    cols = [
        c
        for c in [
            "semaforo",
            "codigo",
            "nombre_bcrp",
            "categoria_bcrp",
            "grupo_bcrp",
            "seccion_bcrp",
            "frecuencia_bcrp",
            "score_anomalia",
            "desvio_tendencia_std",
            "percentil_historico_ultimo",
            "dias_desde_ultimo_dato",
            "lectura",
        ]
        if c in out.columns
    ]
    return out.sort_values("score_anomalia", ascending=False).head(25)[cols]


def smart_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip():
        return df.head(25)
    synonyms = {
        "inflacion": ["inflacion", "ipc", "precios"],
        "tipo de cambio": ["tipo de cambio", "tc", "dolar", "soles por dolar"],
        "empleo": ["empleo", "desempleo", "pea", "ocupada"],
        "mineria": ["mineria", "minero", "cobre", "oro", "zinc"],
        "tasas": ["tasa", "interes", "rendimiento", "encaje"],
        "pbi": ["pbi", "producto bruto", "actividad economica"],
    }
    q = query.strip().lower()
    terms = synonyms.get(q, [q])
    cols = [
        c
        for c in [
            "codigo",
            "nombre_bcrp",
            "categoria_bcrp",
            "grupo_bcrp",
            "seccion_bcrp",
            "tipo_variable",
            "subtipo_variable",
            "lectura",
        ]
        if c in df.columns
    ]
    mask = pd.Series(False, index=df.index)
    for col in cols:
        text = df[col].fillna("").astype(str).str.lower()
        for term in terms:
            mask = mask | text.str.contains(term, regex=False)
    return df[mask].copy()


def save_snapshot(result_df: pd.DataFrame, snapshot_dir: Path) -> Path:
    snapshot_dir.mkdir(exist_ok=True)
    path = snapshot_dir / f"maximixe_data_snapshot_{datetime.now():%Y%m%d_%H%M%S}.csv"
    result_df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")
    return path


def compare_snapshots(
    current: pd.DataFrame, previous: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if (
        current.empty
        or previous.empty
        or "codigo" not in current.columns
        or "codigo" not in previous.columns
    ):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    cur = current[["codigo", "semaforo", "ultima_fecha", "dato_actual_original"]].copy()
    prev = previous[
        [
            c
            for c in ["codigo", "semaforo", "ultima_fecha", "dato_actual_original"]
            if c in previous.columns
        ]
    ].copy()
    merged = cur.merge(prev, on="codigo", how="left", suffixes=("_actual", "_previo"))
    changed = merged[
        merged["semaforo_actual"].ne(merged["semaforo_previo"])
        & merged["semaforo_previo"].notna()
    ].copy()
    new_red = changed[changed["semaforo_actual"].eq("A la baja")].copy()
    out_red = changed[
        changed["semaforo_previo"].eq("A la baja")
        & ~changed["semaforo_actual"].eq("A la baja")
    ].copy()
    new_data = merged[
        merged["ultima_fecha_actual"].ne(merged["ultima_fecha_previo"])
        & merged["ultima_fecha_previo"].notna()
    ].copy()
    return new_red, out_red, new_data


def normalize_regime_value(value: object) -> str:
    text = str(value or "").strip()
    legacy = {
        "Verde": "Normal",
        "Amarillo": "Normal",
        "Rojo": "A la baja",
        "Gris": "Sin datos",
        "": "Sin datos",
        "nan": "Sin datos",
        "None": "Sin datos",
    }
    return legacy.get(text, text if text in SEMAFORO_ORDER else "Sin datos")


def normalize_result_regime(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty:
        return result_df
    out = result_df.copy()
    if "semaforo" in out.columns:
        out["semaforo"] = out["semaforo"].map(normalize_regime_value)
    elif "regimen_tendencia" in out.columns:
        out["semaforo"] = out["regimen_tendencia"].map(normalize_regime_value)
    else:
        out["semaforo"] = "Sin datos"
    out["estado"] = out["semaforo"]
    out["regimen_tendencia"] = out["semaforo"]
    return out


def sort_result_df(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty:
        return result_df
    out = result_df.copy()
    out = normalize_result_regime(out)
    if "codigo" in out.columns:
        out = out.drop_duplicates(subset=["codigo"], keep="last").copy()

    # Prioridad absoluta: Categoría > Clase > Grupo (según instrucción del usuario)
    sort_cols = []
    ascending = []

    for col in ["categoria_bcrp", "clase_serie", "grupo_bcrp"]:
        if col in out.columns:
            sort_cols.append(col)
            ascending.append(True)

    if "semaforo" in out.columns:
        order_estado = {"A la baja": 0, "Al alza": 1, "Normal": 2, "Sin datos": 3}
        out["orden_estado"] = out["semaforo"].map(order_estado).fillna(9)
        sort_cols.append("orden_estado")
        ascending.append(True)

    if "dias_desde_ultimo_dato" in out.columns:
        sort_cols.append("dias_desde_ultimo_dato")
        ascending.append(False)

    if "codigo" in out.columns:
        sort_cols.append("codigo")
        ascending.append(True)

    out = out.sort_values(sort_cols, ascending=ascending, na_position="last")
    if "orden_estado" in out.columns:
        out = out.drop(columns="orden_estado")
    return out


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&display=swap');

        :root {
            --color-bg: #F4F1EC;
            --color-bg-card: #FFFFFF;
            --color-bg-alt: #F8F6F2;
            --color-mxm-navy: #07122E;
            --color-mxm-navy-light: #0F1E42;
            --color-mxm-gold: #F4B321;
            --color-mxm-gold-hover: #D99A0D;
            --color-mxm-gold-light: rgba(244, 179, 33, 0.1);
            --color-accent: #C62828;
            --color-accent-hover: #A82020;
            --color-accent-light: rgba(198, 40, 40, 0.06);
            --color-text: #1A1A1A;
            --color-text-secondary: #6B7280;
            --color-text-muted: #9CA3AF;
            --color-border: #D8D2CA;
            --color-border-light: #EAE5DF;
            --color-rule: #CEC7BF;
            --color-table-stripe: #F9F8F6;
            --color-tag-bg: #FEF8E8;
            --color-tag-border: #FCE8A0;
            --font-display: 'Playfair Display', Georgia, 'Times New Roman', serif;
            --font-body: 'DM Sans', -apple-system, sans-serif;
            --sem-alza: #11734C;
            --sem-normal: #2565AE;
            --sem-baja: #C62828;
            --sem-sindatos: #9CA3AF;
        }

        body, .main, div[data-testid='stAppViewContainer'] {
            font-family: var(--font-body);
            background-color: var(--color-bg);
            color: var(--color-text);
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: var(--font-display);
            font-weight: 600;
            color: var(--color-primary);
            letter-spacing: -0.01em;
        }

        p, li, span, div, label {
            font-family: var(--font-body);
        }

        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 5rem;
            max-width: 1320px;
        }

        /* ── EDITORIAL TOP BAR ── */
        .hero-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 0 0.6rem 0;
            margin-bottom: 0.8rem;
            border-bottom: 1px solid var(--color-rule);
        }
        .hero-topbar-left {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        .hero-topbar-dateline {
            font-size: 0.7rem;
            font-weight: 500;
            color: var(--color-text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* ── HERO ── */
        .hero {
            background: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: 4px;
            padding: 1.8rem 2rem 1.4rem;
            margin-bottom: 1.5rem;
            position: relative;
            box-shadow: 0 1px 4px rgba(0,0,0,0.03);
        }
        .hero::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: var(--color-accent);
        }
        .hero::after {
            content: "";
            position: absolute;
            top: 3px;
            left: 0;
            width: 100%;
            height: 1px;
            background: var(--color-rule);
        }
        .hero-content {
            position: relative;
            z-index: 1;
        }
        .hero-row {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 2rem;
        }
        .hero-brand {
            display: flex;
            align-items: baseline;
            gap: 0.65rem;
            margin-bottom: 0.6rem;
        }
        .mxm-wordmark {
            display: inline-flex;
            align-items: baseline;
            font-family: 'Playfair Display', Georgia, serif;
            font-weight: 900;
            font-size: 1.6rem;
            color: var(--color-mxm-navy);
            letter-spacing: 0.01em;
            line-height: 1;
        }
        .mxm-wordmark .mxm-x {
            color: var(--color-mxm-gold);
            font-weight: 900;
            font-size: 1.05em;
            font-style: italic;
            display: inline-block;
            transform: skew(-8deg);
            margin: 0 0.01em;
        }
        .mxm-wordmark--sidebar {
            font-size: 1.1rem;
        }
        .mxm-wordmark-sub {
            font-size: 0.5rem;
            font-weight: 700;
            color: var(--color-text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            display: block;
            margin-top: 0.06rem;
            font-family: var(--font-body);
        }
        .mxm-tag {
            font-size: 0.65rem;
            font-weight: 700;
            color: var(--color-mxm-navy);
            text-transform: uppercase;
            letter-spacing: 0.06em;
            border: 1px solid var(--color-mxm-gold);
            background: var(--color-mxm-gold-light);
            padding: 0.15rem 0.5rem;
            border-radius: 2px;
            line-height: 1.4;
        }
        .hero-title {
            font-family: var(--font-display);
            font-size: 1.95rem;
            font-weight: 700;
            color: var(--color-primary);
            margin-bottom: 0.25rem;
            line-height: 1.25;
        }
        .hero-subtitle {
            font-family: var(--font-body);
            font-size: 0.92rem;
            color: var(--color-text-secondary);
            line-height: 1.6;
            font-weight: 400;
            max-width: 720px;
        }
        .hero-subtitle b {
            color: var(--color-text);
            font-weight: 600;
        }
        .hero-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            align-items: center;
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid var(--color-border-light);
        }
        .hero-meta-item {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .hero-meta-label {
            font-size: 0.6rem;
            font-weight: 600;
            color: var(--color-text-muted);
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .hero-meta-value {
            font-size: 0.88rem;
            font-weight: 600;
            color: var(--color-text);
        }
        .hero-status {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.7rem;
            font-weight: 600;
            color: #11734C;
            background: rgba(17, 115, 76, 0.06);
            padding: 0.25rem 0.65rem;
            border-radius: 2px;
            border: 1px solid rgba(17, 115, 76, 0.15);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        /* ── KPI CARDS ── */
        .kpi-card {
            background: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: 4px;
            padding: 1rem 0.75rem;
            text-align: center;
            box-shadow: none;
            transition: all 0.2s ease;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            min-height: 120px;
            position: relative;
        }
        .kpi-card::after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 2px;
            border-radius: 0;
            background: var(--color-rule);
            opacity: 0;
            transition: opacity 0.2s ease;
        }
        .kpi-card:hover::after {
            opacity: 1;
            background: var(--color-accent);
        }
        .kpi-card:hover {
            border-color: var(--color-text-muted);
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        }
        .kpi-icon {
            font-size: 1rem;
            margin-bottom: 0.35rem;
            color: var(--color-text-muted);
        }
        .kpi-label {
            font-family: var(--font-body);
            font-size: 0.6rem;
            color: var(--color-text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.15rem;
        }
        .kpi-value {
            font-family: var(--font-display);
            font-size: 1.7rem;
            font-weight: 700;
            color: var(--color-primary);
            line-height: 1.15;
            margin-bottom: 0.05rem;
        }
        .kpi-note {
            font-size: 0.62rem;
            color: var(--color-text-muted);
            font-weight: 500;
        }

        /* ── FREQUENCY CARDS ── */
        .frequency-card {
            background: var(--color-bg-card);
            border-radius: 4px;
            padding: 1.15rem;
            border: 1px solid var(--color-border);
            box-shadow: none;
            transition: all 0.2s ease;
        }
        .frequency-card:hover {
            border-color: var(--color-text-muted);
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        }
        .frequency-card-title {
            font-family: var(--font-display);
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--color-primary);
            margin-bottom: 0.15rem;
        }
        .frequency-card-total {
            font-family: var(--font-display);
            font-size: 1.7rem;
            font-weight: 700;
            color: var(--color-primary);
        }
        .mini-row {
            display: flex;
            flex-wrap: wrap;
            gap: 3px;
            margin-top: 8px;
        }
        .mini-stat {
            font-size: 0.58rem;
            padding: 2px 6px;
            border-radius: 2px;
            font-weight: 600;
        }

        /* ── STATUS PILLS ── */
        .status-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 2px;
            padding: 0.2rem 0.55rem;
            font-weight: 600;
            font-size: 0.65rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            border: 1px solid transparent;
            font-family: var(--font-body);
        }
        .status-Al-alza { background: rgba(17, 115, 76, 0.06); color: var(--sem-alza); border-color: rgba(17, 115, 76, 0.2); }
        .status-Normal { background: rgba(37, 101, 174, 0.06); color: var(--sem-normal); border-color: rgba(37, 101, 174, 0.2); }
        .status-A-la-baja { background: rgba(198, 40, 40, 0.06); color: var(--sem-baja); border-color: rgba(198, 40, 40, 0.2); }
        .status-Sin-datos { background: rgba(156, 163, 175, 0.06); color: var(--sem-sindatos); border-color: rgba(156, 163, 175, 0.2); }

        /* ── EDITORIAL SECTION HEADERS ── */
        .section-head {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin: 1.5rem 0 0.85rem 0;
        }
        .section-head::after {
            content: "";
            flex: 1;
            height: 1px;
            background: var(--color-rule);
        }
        .section-head-label {
            font-family: var(--font-display);
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--color-primary);
            letter-spacing: -0.01em;
            white-space: nowrap;
        }
        .section-head-meta {
            font-size: 0.65rem;
            color: var(--color-text-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            white-space: nowrap;
        }

        /* ── TABS ── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0;
            background-color: transparent;
            border-radius: 0;
            padding: 0;
            border: none;
            border-bottom: 1px solid var(--color-rule);
        }
        .stTabs [data-baseweb="tab"] {
            height: auto;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 0;
            padding: 0.55rem 1.25rem;
            font-family: var(--font-body);
            font-size: 0.78rem;
            font-weight: 600;
            color: var(--color-text-secondary);
            transition: all 0.15s ease;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            border-bottom: 2px solid transparent;
            margin-bottom: -1px;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: var(--color-text);
            border-bottom-color: var(--color-text-muted);
        }
        .stTabs [aria-selected="true"] {
            color: var(--color-primary) !important;
            border-bottom-color: var(--color-accent) !important;
            font-weight: 700;
            background: transparent !important;
        }

        /* ── SIDEBAR ── */
        section[data-testid="stSidebar"] {
            background-color: var(--color-bg-card);
            border-right: 1px solid var(--color-border);
        }
        section[data-testid="stSidebar"] .stTitle {
            font-family: var(--font-display);
            color: var(--color-primary);
        }

        /* ── EXPANDERS ── */
        div[data-testid="stExpander"] {
            border: 1px solid var(--color-border) !important;
            border-radius: 4px !important;
            background-color: var(--color-bg-card) !important;
            box-shadow: none !important;
            margin-bottom: 0.4rem;
        }
        div[data-testid="stExpander"] summary {
            font-family: var(--font-body);
            font-weight: 600;
            font-size: 0.82rem;
            color: var(--color-text);
        }

        /* ── BUTTONS ── */
        .stButton>button {
            border-radius: 2px !important;
            font-weight: 600 !important;
            padding: 0.45rem 1.25rem !important;
            transition: all 0.15s ease !important;
            border: 1px solid var(--color-border) !important;
            font-family: var(--font-body);
            font-size: 0.8rem;
        }
        .stButton>button:hover {
            border-color: var(--color-text-muted) !important;
        }
        .stButton>button[kind="primary"] {
            background: var(--color-accent) !important;
            color: #FFF !important;
            border: 1px solid var(--color-accent) !important;
        }
        .stButton>button[kind="primary"]:hover {
            background: var(--color-accent-hover) !important;
            box-shadow: 0 2px 8px rgba(198, 40, 40, 0.25) !important;
        }

        /* ── SELECTBOX / RADIO ── */
        div[data-testid="stSelectbox"] > div {
            border-radius: 2px !important;
            border-color: var(--color-border) !important;
        }
        div[data-testid="stSelectbox"] > div:focus-within {
            border-color: var(--color-accent) !important;
        }
        div[data-testid="stRadio"] > div[role="radiogroup"] {
            background: transparent;
            border: none;
            border-radius: 0;
            padding: 0;
            display: flex;
            gap: 0;
            border-bottom: 1px solid var(--color-border-light);
        }
        div[data-testid="stRadio"] label {
            border-radius: 0;
            padding: 0.45rem 1rem;
            font-family: var(--font-body);
            font-weight: 600;
            font-size: 0.75rem;
            transition: all 0.15s ease;
            background: transparent !important;
            color: var(--color-text-secondary) !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            border-bottom: 2px solid transparent;
            margin-bottom: -1px;
        }
        div[data-testid="stRadio"] label:hover {
            color: var(--color-text) !important;
            border-bottom-color: var(--color-text-muted);
        }
        div[data-testid="stRadio"] label[data-selected="true"] {
            color: var(--color-primary) !important;
            border-bottom-color: var(--color-accent) !important;
            font-weight: 700;
        }

        /* ── DATAFRAME ── */
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--color-border) !important;
            border-radius: 4px !important;
            overflow: hidden;
        }
        div[data-testid="stDataFrame"] thead tr th {
            background-color: var(--color-bg-card) !important;
            color: var(--color-text-secondary) !important;
            font-family: var(--font-body);
            font-weight: 600;
            font-size: 0.7rem;
            padding: 8px 12px !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            border-bottom: 2px solid var(--color-rule);
        }
        div[data-testid="stDataFrame"] tbody tr td {
            font-family: var(--font-body);
            font-size: 0.78rem;
            padding: 6px 12px !important;
        }
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) {
            background-color: var(--color-table-stripe);
        }
        div[data-testid="stDataFrame"] tbody tr:hover {
            background-color: var(--color-accent-light) !important;
        }

        /* ── STREAMLIT NATIVE ELEMENTS ── */
        .st-emotion-cache-1r4qj8v, .st-emotion-cache-1p1m4al {
            font-family: var(--font-body);
        }

        /* ── DIVIDERS ── */
        hr {
            border: none !important;
            height: 1px !important;
            background: var(--color-rule) !important;
            opacity: 0.4;
            margin: 1.25rem 0 !important;
        }

        /* ── METRIC / INFO BOXES ── */
        div[data-testid="stMetric"] {
            background: var(--color-bg-card);
            border: 1px solid var(--color-border);
            border-radius: 4px;
            padding: 0.7rem 0.9rem;
        }
        div[data-testid="stInfo"] {
            border-radius: 2px;
            border-left: 3px solid var(--color-accent);
        }
        div[data-testid="stSuccess"] {
            border-radius: 2px;
        }
        div[data-testid="stWarning"] {
            border-radius: 2px;
        }
        div[data-testid="stError"] {
            border-radius: 2px;
        }

        /* ── PROGRESS BAR ── */
        div[role="progressbar"] > div {
            background: var(--color-accent) !important;
        }

        /* ── STATUS WIDGET ── */
        div[data-testid="stStatusWidget"] {
            border-radius: 2px;
            border: 1px solid var(--color-border);
        }

        /* ── LOADING ANIMATION ── */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .hero, .kpi-card, .frequency-card {
            animation: fadeIn 0.35s ease forwards;
        }
        .kpi-card:nth-child(2) { animation-delay: 0.05s; }
        .kpi-card:nth-child(3) { animation-delay: 0.1s; }
        .kpi-card:nth-child(4) { animation-delay: 0.15s; }
        .kpi-card:nth-child(5) { animation-delay: 0.2s; }
        .kpi-card:nth-child(6) { animation-delay: 0.25s; }

        /* ── PRINT-LIKE SUBHEADER ── */
        .st-emotion-cache-1wbqy5l h2, .st-emotion-cache-1wbqy5l h3 {
            font-family: var(--font-display);
        }

        /* ── TOOLTIP / SMALL TEXT ── */
        .stCaption, caption {
            font-family: var(--font-body) !important;
            font-size: 0.7rem !important;
            color: var(--color-text-muted) !important;
        }

        /* ── CHECKBOX ── */
        .stCheckbox label {
            font-size: 0.8rem;
        }

        /* ── SCROLLBAR ── */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: var(--color-bg);
        }
        ::-webkit-scrollbar-thumb {
            background: var(--color-border);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--color-text-muted);
        }

        /* ── MULTISELECT ── */
        div[data-baseweb="select"] {
            border-radius: 2px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(result_df: pd.DataFrame, end_date, meta_file) -> None:
    _ = meta_file
    # Usar la fecha real de los datos (ultima_fecha máxima), no la del análisis
    if not result_df.empty and "ultima_fecha" in result_df.columns:
        max_date = pd.to_datetime(result_df["ultima_fecha"], errors="coerce").max()
        if pd.notna(max_date):
            effective = max_date
        else:
            effective = pd.to_datetime(end_date)
    else:
        effective = pd.to_datetime(end_date)
    date_str = effective.strftime("%d %b %Y")
    total = len(result_df)
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    has_data = not result_df.empty
    if has_data:
        con_dato = int(
            pd.to_datetime(
                result_df.get("ultima_fecha", pd.Series(dtype=object)), errors="coerce"
            )
            .notna()
            .sum()
        )
        freshness = f"{con_dato} series con datos"
    else:
        freshness = ""
    st.markdown(
        f"""
        <div class='hero'>
            <div class="hero-content">
                <div class="hero-topbar">
                    <div class="hero-topbar-left">
                        <div>
                            <span class="mxm-wordmark">MA<span class="mxm-x">X</span>IMIXE</span>
                            <span class="mxm-wordmark-sub">Consultoría estratégica</span>
                        </div>
                        <span class="mxm-tag">Data Monitor</span>
                    </div>
                    <div class="hero-topbar-dateline">{now_str}</div>
                </div>
                <div class="hero-row">
                    <div style="flex: 1;">
                        <div class="hero-title">MAXIDataBank</div>
                        <div class="hero-subtitle">
                            <b>MAXIMIXE Economía & Mercados</b>.
                            Monitoreando <b>{total:,}</b> series macroeconómicas en tiempo real.
                        </div>
                    </div>
                    <div style="flex-shrink: 0; text-align: right;">
                        <div class="hero-status">● En línea</div>
                    </div>
                </div>
                <div class="hero-meta">
                    <div class="hero-meta-item">
                        <span class="hero-meta-label">Última actualización</span>
                        <span class="hero-meta-value">{date_str}</span>
                    </div>
                    {f'<div class="hero-meta-item"><span class="hero-meta-label">Universo</span><span class="hero-meta-value">{total:,} series</span></div>' if has_data else ''}
                    {f'<div class="hero-meta-item"><span class="hero-meta-label">Cobertura</span><span class="hero-meta-value">{freshness}</span></div>' if freshness else ''}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def frequency_bucket_for_update(freq: str | None) -> str:
    text = str(freq or "").strip().lower()
    if not text:
        return ""
    if text in {"d", "diaria", "daily"} or "diar" in text:
        return "D"
    if text in {"m", "mensual", "monthly"} or "mens" in text:
        return "M"
    if text in {"q", "t", "trimestral", "quarterly"} or "trim" in text:
        return "Q"
    if text in {"s", "semestral"} or "semes" in text:
        return "S"
    if text in {"a", "y", "anual", "annual"} or "anual" in text:
        return "A"
    return ""


def generate_html_report(result_df: pd.DataFrame) -> str:
    from ui_charts import friendly_columns

    counts = result_df["semaforo"].value_counts().reindex(SEMAFORO_ORDER, fill_value=0)
    moving = result_df[result_df["semaforo"].isin(["Al alza", "A la baja"])][
        executive_cols(result_df)
    ].head(30)
    html_table = friendly_columns(moving).to_html(index=False, escape=True)
    return f"""
    <html><head><meta charset="utf-8"><title>MAXIMIXE — Data Monitor</title>
    <style>body{{font-family:Arial,sans-serif;color:#1A1A1A;margin:32px}} h1{{margin-bottom:2px;font-family:Georgia,serif;color:#07122E}} h1 span{{color:#F4B321;font-style:italic}} p{{color:#6B7280;font-size:13px}} .kpi{{display:inline-block;border:1px solid #D8D2CA;border-radius:2px;padding:8px 12px;margin:6px}} table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{border:1px solid #D8D2CA;padding:6px;text-align:left}} th{{background:#F4F1EC;text-transform:uppercase;font-size:11px;letter-spacing:0.04em}}</style>
    </head><body>
    <h1>MA<span>X</span>IMIXE <span style="color:#07122E;font-style:normal;font-weight:400;">· Data Monitor</span></h1>
    <p>Reporte ejecutivo &mdash; {datetime.now():%d/%m/%Y %H:%M} &mdash; MAXIMIXE Consultoría estratégica</p>
    <div class="kpi">Al alza: <b>{int(counts.get("Al alza", 0))}</b></div>
    <div class="kpi">Normal: <b>{int(counts.get("Normal", 0))}</b></div>
    <div class="kpi">A la baja: <b>{int(counts.get("A la baja", 0))}</b></div>
    <div class="kpi">Sin datos: <b>{int(counts.get("Sin datos", 0))}</b></div>
    <div class="kpi">Total: <b>{len(result_df)}</b></div>
    <h2>Series con tendencia definida</h2>{html_table}
    </body></html>
    """


def display_value(value) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    ):
        return f"{float(value):,.2f}"
    return str(value)


def format_dataframe_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]) and not pd.api.types.is_bool_dtype(
            out[col]
        ):
            out[col] = out[col].round(2)
    return out


def format_dataframe_for_export(df: pd.DataFrame) -> pd.DataFrame:
    out = format_dataframe_values(df)
    return out.where(pd.notna(out), "")


def friendly_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = format_dataframe_values(df)
    return out.rename(
        columns={c: DISPLAY_NAMES.get(str(c), str(c)) for c in out.columns}
    )


def status_css_class(value: object) -> str:
    text = str(value or "Sin datos").strip() or "Sin datos"
    return "status-" + text.replace(" ", "-")
