"""MAXIMIXE DataBank INEI.

Modulo Streamlit para explorar indicadores INEI con la misma arquitectura UX
del monitor BCRP: tablero ejecutivo, buscador, ficha tecnica y analisis de serie.
"""
from __future__ import annotations

from datetime import date
from html import escape
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from inei_analysis import analyze_series, annual_average_metrics
from inei_cache import INEICache
from inei_charts import comparison_chart, distribution_chart, line_chart, var_chart
from inei_logic import analysis_html, metric_card
from ui_charts import render_kpi_card
from ui_logic import inject_css


FREQUENCIES = ["Anual", "Mensual", "Trimestral"]
DEFAULT_START_YEAR = 1950


st.set_page_config(
    page_title="MAXIMIXE DataBank INEI",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='12' fill='%2307112E'/><text x='50' y='67' font-size='52' font-family='Arial' fill='%23F4B321' text-anchor='middle' font-weight='900'>X</text></svg>",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_resource
def get_cache() -> INEICache:
    return INEICache()


@st.cache_data(show_spinner=False)
def tree_paths(app_dir: str) -> dict[str, dict[str, str]]:
    path = Path(app_dir) / "inei_tree_full.json"
    if not path.exists():
        return {}
    nodes = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}

    def walk(node: dict, parents: list[str]) -> None:
        rowkey = str(node.get("rowkey", "")).strip()
        label = str(node.get("label", "")).strip()
        current = parents + ([label] if label else [])
        if rowkey and rowkey not in out:
            out[rowkey] = {
                "categoria": current[0] if len(current) >= 1 else "",
                "seccion": current[1] if len(current) >= 2 else "",
                "subseccion": current[2] if len(current) >= 3 else "",
                "ruta": " / ".join(current),
            }
        for child in node.get("children", []) or []:
            walk(child, current)

    for root in nodes:
        walk(root, [])
    return out


@st.cache_data(show_spinner=False)
def cached_catalog(app_dir: str, frequency: str | None = None) -> pd.DataFrame:
    cache = INEICache()
    # Try frequency-aware catalog first
    if frequency:
        freq_cat = cache.get_catalog(frequency=frequency)
        if not freq_cat.empty:
            paths = tree_paths(app_dir)
            meta = pd.DataFrame.from_dict(paths, orient="index").reset_index(names="rowkey")
            out = freq_cat.merge(meta, on="rowkey", how="left")
            out["categoria"] = out["categoria"].fillna("No clasificado")
            out["seccion"] = out["seccion"].fillna("No clasificado")
            out["subseccion"] = out["subseccion"].fillna("")
            out["ruta"] = out["ruta"].fillna(out["label"])
            return out
    # Fallback to old catalog
    catalog = cache.get_catalog()
    if catalog.empty:
        return pd.DataFrame(columns=["rowkey", "label", "categoria", "seccion", "subseccion", "ruta"])
    paths = tree_paths(app_dir)
    meta = pd.DataFrame.from_dict(paths, orient="index").reset_index(names="rowkey")
    out = catalog.merge(meta, on="rowkey", how="left")
    out["categoria"] = out["categoria"].fillna("No clasificado")
    out["seccion"] = out["seccion"].fillna("No clasificado")
    out["subseccion"] = out["subseccion"].fillna("")
    out["ruta"] = out["ruta"].fillna(out["label"])
    return out


@st.cache_data(show_spinner=False)
def cached_series_status(db_path: str) -> pd.DataFrame:
    path = Path(db_path)
    if not path.exists():
        return pd.DataFrame(columns=["rowkey", "frequency", "registros", "fecha_inicio", "fecha_fin"])
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            """
            SELECT rowkey, frequency, COUNT(*) AS registros,
                   MIN(fecha) AS fecha_inicio, MAX(fecha) AS fecha_fin
            FROM inei_series
            GROUP BY rowkey, frequency
            """,
            conn,
        )


def section_head(label: str, meta: str = "") -> None:
    meta_html = f"<span class='section-head-meta'>{escape(meta)}</span>" if meta else ""
    st.markdown(
        f"<div class='section-head'><span class='section-head-label'>{escape(label)}</span>{meta_html}</div>",
        unsafe_allow_html=True,
    )


def sidebar_brand() -> None:
    st.markdown(
        """
        <div style="margin-bottom:0.7rem;">
          <div class="mxm-wordmark mxm-wordmark--sidebar">MA<span class="mxm-x">X</span>IMIXE</div>
          <span class="mxm-wordmark-sub">DataBank INEI</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_inei_hero(catalog: pd.DataFrame, status: dict, end_year: int) -> None:
    total_catalog = len(catalog)
    total_series = int(status.get("total_series_descargadas", 0) or 0)
    total_records = int(status.get("total_registros", 0) or 0)
    updated = str(status.get("ultima_descarga", "Nunca") or "Nunca")
    st.markdown(
        f"""
        <div class='hero'>
          <div class='hero-content'>
            <div class='hero-row'>
              <div>
                <div class='hero-brand'>
                  <div class='mxm-wordmark'>MA<span class='mxm-x'>X</span>IMIXE</div>
                  <span class='mxm-tag'>INEI</span>
                </div>
                <div class='hero-title'>DataBank INEI</div>
                <div class='hero-subtitle'>
                  Portal operativo para consultar, cachear y analizar indicadores estadísticos del INEI.
                  Universo catalogado: <b>{total_catalog:,}</b> indicadores.
                </div>
              </div>
              <div class='hero-status'>En línea</div>
            </div>
            <div class='hero-meta'>
              <div class='hero-meta-item'><span class='hero-meta-label'>Series cacheadas</span><span class='hero-meta-value'>{total_series:,}</span></div>
              <div class='hero-meta-item'><span class='hero-meta-label'>Registros</span><span class='hero-meta-value'>{total_records:,}</span></div>
              <div class='hero-meta-item'><span class='hero-meta-label'>Rango objetivo</span><span class='hero-meta-value'>{DEFAULT_START_YEAR}-{end_year}</span></div>
              <div class='hero-meta-item'><span class='hero-meta-label'>Última descarga</span><span class='hero-meta-value'>{escape(updated)}</span></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def enrich_catalog_with_cache(catalog: pd.DataFrame, status_df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    out = catalog.copy()
    freq_status = status_df[status_df["frequency"].eq(frequency)].copy() if not status_df.empty else status_df
    if not freq_status.empty:
        out = out.merge(freq_status, on="rowkey", how="left")
    else:
        out["registros"] = np.nan
        out["fecha_inicio"] = ""
        out["fecha_fin"] = ""
    out["estado_cache"] = np.where(out["registros"].fillna(0).astype(float).gt(0), "Cacheado", "Sin cache")
    return out


def render_metadata_card(row: pd.Series, frequency: str, start_year: int, end_year: int) -> None:
    items = [
        ("Código INEI", str(row.get("rowkey", ""))),
        ("Frecuencia", frequency),
        ("Categoría", str(row.get("categoria", ""))),
        ("Sección", str(row.get("seccion", ""))),
        ("Subsección", str(row.get("subseccion", "") or "s/d")),
        ("Estado cache", str(row.get("estado_cache", "Sin cache"))),
        ("Registros cacheados", f"{int(row.get('registros')):,}" if pd.notna(row.get("registros")) else "0"),
        ("Rango solicitado", f"{start_year}-{end_year}"),
    ]
    cells = "".join(
        "<div>"
        f"<div style='font-size:0.72rem;color:#667085;margin-bottom:0.15rem;'>{escape(label)}</div>"
        f"<div style='font-size:0.9rem;color:#111827;font-weight:650;line-height:1.25;'>{escape(value)}</div>"
        "</div>"
        for label, value in items
    )
    st.markdown(
        "<div style='background:#fff;border:1px solid #D8D2CA;border-radius:4px;padding:1rem 1.15rem;margin:0.25rem 0 1rem;'>"
        "<div style='font-size:0.78rem;color:#667085;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;margin-bottom:0.85rem;'>Ficha técnica del indicador</div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:0.8rem 1.25rem;'>{cells}</div>"
        f"<div style='margin-top:0.85rem;padding-top:0.75rem;border-top:1px solid #EAE5DF;color:#475467;font-size:0.86rem;'>{escape(str(row.get('ruta', row.get('label', ''))))}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_dashboard(catalog: pd.DataFrame, status_df: pd.DataFrame, status: dict) -> None:
    section_head("Tablero ejecutivo", "Resumen de cache y catálogo")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card("Indicadores", len(catalog), "catálogo INEI")
    with c2:
        render_kpi_card("Series cacheadas", int(status.get("total_series_descargadas", 0) or 0), "indicador-frecuencia")
    with c3:
        render_kpi_card("Registros", int(status.get("total_registros", 0) or 0), "observaciones")
    with c4:
        render_kpi_card("Anuales", int(status.get("indicadores_anual", 0) or 0), "indicadores")
    with c5:
        render_kpi_card("Mensuales/trim.", int(status.get("indicadores_mensual", 0) or 0) + int(status.get("indicadores_trimestral", 0) or 0), "indicadores")

    section_head("Cobertura", "Por frecuencia y categoría")
    left, right = st.columns(2)
    with left:
        if not status_df.empty:
            freq = status_df.groupby("frequency").agg(series=("rowkey", "nunique"), registros=("registros", "sum")).reset_index()
            fig = px.bar(freq, x="frequency", y="series", text="series", color="frequency", title="Indicadores cacheados por frecuencia")
            fig.update_layout(height=340, showlegend=False, xaxis_title="", yaxis_title="Indicadores")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("La cache aún no tiene series descargadas.")
    with right:
        top = catalog["categoria"].value_counts().head(12).reset_index()
        top.columns = ["categoria", "indicadores"]
        fig = px.bar(top, x="indicadores", y="categoria", orientation="h", text="indicadores", title="Principales categorías del catálogo")
        fig.update_layout(height=340, yaxis_title="", xaxis_title="Indicadores")
        fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig, use_container_width=True)


def render_explorer(catalog: pd.DataFrame, status_df: pd.DataFrame, cache: INEICache) -> None:
    section_head("Explorar indicador", "Búsqueda y análisis de serie")
    f1, f2, f3 = st.columns([1, 1, 1.4])
    with f1:
        frequency = st.selectbox("Frecuencia", FREQUENCIES, index=0)
        # Load frequency-filtered catalog
        freq_catalog = cached_catalog(str(HERE), frequency=frequency)
        if freq_catalog.empty:
            freq_catalog = catalog  # fallback
        active_catalog = freq_catalog
    with f2:
        cache_state = st.selectbox("Estado cache", ["Todos", "Cacheado", "Sin cache"], index=0)
    with f3:
        query = st.text_input("Buscar", placeholder="Código, nombre, categoría...")

    f4, f5, f6 = st.columns(3)
    with f4:
        categories = sorted([x for x in active_catalog["categoria"].dropna().unique().tolist() if str(x).strip()])
        category = st.selectbox("Categoría", ["Todas"] + categories)
    with f5:
        start_year = st.number_input("Año inicio", min_value=1950, max_value=2030, value=DEFAULT_START_YEAR)
    with f6:
        end_year = st.number_input("Año fin", min_value=1950, max_value=2030, value=date.today().year)

    explore = enrich_catalog_with_cache(active_catalog, status_df, frequency)
    if category != "Todas":
        explore = explore[explore["categoria"].eq(category)].copy()
    if cache_state != "Todos":
        explore = explore[explore["estado_cache"].eq(cache_state)].copy()
    if query.strip():
        q = query.strip().lower()
        mask = pd.Series(False, index=explore.index)
        for col in ["rowkey", "label", "categoria", "seccion", "subseccion", "ruta"]:
            mask = mask | explore[col].fillna("").astype(str).str.lower().str.contains(q, regex=False)
        explore = explore[mask].copy()

    st.caption(f"Universo filtrado: {len(explore):,} de {len(catalog):,} indicadores.")
    if explore.empty:
        st.info("No hay indicadores con esos filtros.")
        return

    options = explore["rowkey"].tolist()
    labels = {r["rowkey"]: f"{r['rowkey']} - {r['label']}" for _, r in explore.iterrows()}
    selected = st.selectbox("Seleccione un indicador", options, format_func=lambda x: labels.get(x, x))
    row = explore[explore["rowkey"].eq(selected)].iloc[0]

    section_head("Indicador", labels[selected])
    render_metadata_card(row, frequency, int(start_year), int(end_year))

    df = cache.get_series(selected, int(start_year), int(end_year), frequency=frequency)
    if df.empty:
        st.warning("Este indicador no tiene datos cacheados para la frecuencia y rango seleccionados.")
        if st.button("Descargar indicador seleccionado", type="primary", use_container_width=True):
            with st.spinner("Descargando desde INEI..."):
                df = cache.fetch_and_cache(selected, frequency, str(int(start_year)), str(int(end_year)))
            cached_series_status.clear()
            st.success(f"Descargados {len(df):,} registros.")
            st.rerun()
        return

    analysis = analyze_series(df)
    analysis.update(annual_average_metrics(df))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Último valor", analysis.get("ultimo_valor"))
    with c2:
        metric_card("Var % periodo", analysis.get("var_periodo_pct"), "{:+.2f}%")
    with c3:
        metric_card("Var % interanual", analysis.get("var_interanual_pct"), "{:+.2f}%")
    with c4:
        metric_card("Percentil histórico", analysis.get("percentil_historico"), "{:.1%}")

    st.plotly_chart(line_chart(df, row["label"], frequency), use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(comparison_chart(df, analysis, row["label"]), use_container_width=True)
    with right:
        st.plotly_chart(distribution_chart(df, analysis, row["label"]), use_container_width=True)
    var_fig = var_chart(df, analysis, row["label"])
    if var_fig:
        st.plotly_chart(var_fig, use_container_width=True)

    section_head("Datos y estadística", "Detalle de la serie")
    d1, d2 = st.columns([1.25, 1])
    with d1:
        show_df = df[["fecha", "valor"]].copy()
        show_df["fecha"] = pd.to_datetime(show_df["fecha"]).dt.date
        st.dataframe(show_df, use_container_width=True, hide_index=True, height=380)
    with d2:
        st.markdown(analysis_html(analysis), unsafe_allow_html=True)


def render_cache_view(status_df: pd.DataFrame, status: dict) -> None:
    section_head("Estado de cache", "Descarga masiva INEI")
    st.info("Para llenar la cache completa use sync_inei_cache.bat. Descarga Anual, Mensual y Trimestral desde 1950.")
    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card("Series", int(status.get("total_series_descargadas", 0) or 0), "indicador-frecuencia")
    with c2:
        render_kpi_card("Registros", int(status.get("total_registros", 0) or 0), "observaciones")
    with c3:
        render_kpi_card("Tamaño DB", status.get("tamano_db_mb", 0), "MB")
    if not status_df.empty:
        st.dataframe(status_df.sort_values(["frequency", "rowkey"]), use_container_width=True, hide_index=True, height=520)


inject_css()

cache = get_cache()
catalog = cached_catalog(str(HERE))
status_df = cached_series_status(str(cache.db_path))
status = cache.cache_status()

with st.sidebar:
    sidebar_brand()
    with st.expander("Datos", expanded=True):
        st.caption("Fuente: INEI SIRTOD")
        # Per-frequency catalog counts
        freq_status = cache.freq_catalog_status()
        has_freq_catalog = freq_status.get("total_indicadores", 0) > 0
        if has_freq_catalog:
            for freq in FREQUENCIES:
                n = int(freq_status.get(freq, 0) or 0)
                st.write(f"  {freq}: {n:,} indicadores")
        else:
            st.write(f"Catálogo: {len(catalog):,} indicadores")
        st.write(f"Cache: {int(status.get('total_series_descargadas', 0) or 0):,} series")
    with st.expander("Sincronización", expanded=False):
        st.caption("Carga masiva desde 1950.")
        st.code(".\\sync_inei_cache.bat", language="powershell")
    with st.expander("Opciones secundarias", expanded=False):
        if st.button("Actualizar catálogo completo", use_container_width=True):
            with st.spinner("Actualizando catálogo INEI..."):
                n = cache.update_catalog()
            cached_catalog.clear()
            st.success(f"Catálogo actualizado: {n:,} indicadores.")
            st.rerun()
        for freq in FREQUENCIES:
            if st.button(f"Explorar {freq}", use_container_width=True,
                         help=f"Escanea el árbol INEI en modo {freq} para indexar indicadores disponibles"):
                with st.spinner(f"Explorando indicadores {freq}..."):
                    n = cache.update_freq_catalog(freq)
                cached_catalog.clear()
                st.success(f"Indexados {n:,} indicadores en modo {freq}.")
                st.rerun()
        if st.button("Limpiar cache de Streamlit", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

render_inei_hero(catalog, status, date.today().year)

main_mode = st.radio(
    "Modo principal",
    ["Tablero ejecutivo", "Analisis de series", "Cache"],
    horizontal=True,
    label_visibility="collapsed",
)

if main_mode == "Tablero ejecutivo":
    render_dashboard(catalog, status_df, status)
elif main_mode == "Analisis de series":
    render_explorer(catalog, status_df, cache)
else:
    render_cache_view(status_df, status)
