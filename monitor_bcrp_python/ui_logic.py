import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
from pathlib import Path
import traceback
from constants import *

def executive_cols(result_df: pd.DataFrame) -> list[str]:
    cols = [
        "semaforo", "regimen_tendencia", "diagnostico", "codigo", "nombre_bcrp",
        "categoria_bcrp", "clase_serie", "grupo_bcrp", "seccion_bcrp", "frecuencia_bcrp", "ultima_fecha", "dato_actual_original",
        "dato_anterior_original", "dato_anio_anterior_original", "var_interanual_pct",
        "posicion_vs_tendencia", "posicion_ytd_0_100", "posicion_mov_0_100",
        "posicion_hist_0_100", "tendencia_12m_cambio", "umbral_regimen_tendencia",
        "estado_actualizacion", "dias_desde_ultimo_dato", "percentil_historico_ultimo",
        "revision_requerida",
    ]
    return [c for c in cols if c in result_df.columns]

def technical_cols(result_df: pd.DataFrame) -> list[str]:
    cols = [
        "semaforo", "regimen_tendencia", "diagnostico", "codigo", "nombre_bcrp",
        "categoria_bcrp", "clase_serie", "grupo_bcrp", "seccion_bcrp", "frecuencia_bcrp", "unidad_medida",
        "tipo_variable", "subtipo_variable", "ventana_variacion", "categoria_operativa", "ultima_fecha",
        "dias_desde_ultimo_dato", "estado_actualizacion", "dato_actual_original",
        "dato_anterior_original", "dato_anio_anterior_original", "dato_actual_analisis",
        "dato_anterior_analisis", "dato_anio_anterior_analisis", "var_interanual_pct",
        "percentil_historico_ultimo", "tendencia_12m_pendiente", "tendencia_12m_direccion",
        "tendencia_12m_cambio", "umbral_regimen_tendencia", "posicion_ytd_0_100",
        "posicion_mov_0_100", "posicion_hist_0_100", "revision_requerida",
        "tratamiento", "confianza_clasificacion", "motivo_clasificacion",
        "alertas_clasificacion", "override_clasificacion", "override_comentario", "lectura"
    ]
    return [c for c in cols if c in result_df.columns]

def anomaly_panel_df(result_df: pd.DataFrame) -> pd.DataFrame:
    out = result_df.copy()
    score = pd.Series(0, index=out.index, dtype=float)
    if "desvio_tendencia_std" in out.columns:
        score += out["desvio_tendencia_std"].abs().fillna(0)
    if "percentil_historico_ultimo" in out.columns:
        score += ((out["percentil_historico_ultimo"].fillna(50) - 50).abs() / 25)
    if "dias_desde_ultimo_dato" in out.columns:
        score += (out["dias_desde_ultimo_dato"].fillna(0) / 90).clip(upper=3)
    out["score_anomalia"] = score
    cols = [c for c in ["semaforo", "codigo", "nombre_bcrp", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "frecuencia_bcrp", "score_anomalia", "desvio_tendencia_std", "percentil_historico_ultimo", "dias_desde_ultimo_dato", "lectura"] if c in out.columns]
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
    cols = [c for c in ["codigo", "nombre_bcrp", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "tipo_variable", "subtipo_variable", "lectura"] if c in df.columns]
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

def compare_snapshots(current: pd.DataFrame, previous: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if current.empty or previous.empty or "codigo" not in current.columns or "codigo" not in previous.columns:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    cur = current[["codigo", "semaforo", "ultima_fecha", "dato_actual_original"]].copy()
    prev = previous[[c for c in ["codigo", "semaforo", "ultima_fecha", "dato_actual_original"] if c in previous.columns]].copy()
    merged = cur.merge(prev, on="codigo", how="left", suffixes=("_actual", "_previo"))
    changed = merged[merged["semaforo_actual"].ne(merged["semaforo_previo"]) & merged["semaforo_previo"].notna()].copy()
    new_red = changed[changed["semaforo_actual"].eq("A la baja")].copy()
    out_red = changed[changed["semaforo_previo"].eq("A la baja") & ~changed["semaforo_actual"].eq("A la baja")].copy()
    new_data = merged[merged["ultima_fecha_actual"].ne(merged["ultima_fecha_previo"]) & merged["ultima_fecha_previo"].notna()].copy()
    return new_red, out_red, new_data

def normalize_regime_value(value: object) -> str:
    text = str(value or "").strip()
    legacy = {
        "Verde": "Normal", "Amarillo": "Normal", "Rojo": "A la baja", "Gris": "Sin datos",
        "": "Sin datos", "nan": "Sin datos", "None": "Sin datos",
    }
    return legacy.get(text, text if text in SEMAFORO_ORDER else "Sin datos")

def normalize_result_regime(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty: return result_df
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
    if result_df.empty: return result_df
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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700&display=swap');
        
        /* General Layout */
        body, .main, div[data-testid='stAppViewContainer'] {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: #F8FAFC;
            color: #1E293B;
        }
        
        h1, h2, h3, .hero-title {
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
        }
        
        .block-container {
            padding-top: 2rem;
            padding-bottom: 5rem;
            max-width: 1300px;
        }

        /* Hero Section */
        .hero {
            background: linear-gradient(105deg, #0F172A 0%, #1E293B 100%);
            color: #FFFFFF;
            border-radius: 20px;
            padding: 3rem;
            margin-bottom: 2.5rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            position: relative;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .hero::after {
            content: "";
            position: absolute;
            top: -50%;
            right: -10%;
            width: 400px;
            height: 400px;
            background: radial-gradient(circle, rgba(56, 189, 248, 0.15) 0%, transparent 70%);
            border-radius: 50%;
            pointer-events: none;
        }

        .hero-title {
            font-size: 2.8rem;
            letter-spacing: -0.02em;
            margin-bottom: 0.75rem;
            background: linear-gradient(to right, #FFFFFF, #94A3B8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hero-subtitle {
            font-size: 1.2rem;
            color: #94A3B8;
            max-width: 850px;
            line-height: 1.6;
        }

        /* KPI Cards */
        .kpi-card {
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 1rem 0.75rem;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
            transition: all 0.2s ease;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-height: 120px;
        }

        .kpi-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.08);
            border-color: #CBD5E1;
        }

        .kpi-label {
            font-size: 0.7rem;
            color: #64748B;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.02em;
            margin-bottom: 0.25rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .kpi-value {
            font-size: 1.6rem;
            font-weight: 700;
            font-family: 'Outfit', sans-serif;
            color: #0F172A;
            line-height: 1.2;
            margin-bottom: 0.15rem;
        }

        .kpi-note {
            font-size: 0.7rem;
            color: #94A3B8;
            font-weight: 500;
        }


        /* Frequency Cards */
        .frequency-card {
            background: #FFFFFF;
            border-radius: 16px;
            padding: 1.25rem;
            border: 1px solid #E2E8F0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        
        .frequency-card:hover {
            transform: scale(1.02);
        }

        .frequency-card-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.1rem;
            font-weight: 600;
            color: #334155;
            margin-bottom: 0.25rem;
        }

        .frequency-card-total {
            font-size: 1.75rem;
            font-weight: 700;
            color: #0F172A;
        }

        .mini-row {
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
            margin-top: 10px;
        }

        .mini-stat {
            font-size: 0.65rem;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
        }

        /* Status Pills */
        .status-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 8px;
            padding: 0.4rem 0.9rem;
            font-weight: 600;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.025em;
            border: 1px solid transparent;
        }

        .status-Al-alza { background: rgba(16, 185, 129, 0.1); color: #059669; border-color: rgba(16, 185, 129, 0.2); }
        .status-Normal { background: rgba(59, 130, 246, 0.1); color: #2563EB; border-color: rgba(59, 130, 246, 0.2); }
        .status-A-la-baja { background: rgba(239, 68, 68, 0.1); color: #DC2626; border-color: rgba(239, 68, 68, 0.2); }
        .status-Sin-datos { background: rgba(100, 116, 139, 0.1); color: #475467; border-color: rgba(100, 116, 139, 0.2); }

        /* Tabs and Inputs Customization */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
            background-color: transparent;
        }

        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            gap: 1px;
            padding-top: 10px;
            padding-bottom: 10px;
        }

        .stTabs [aria-selected="true"] {
            background-color: transparent;
            font-weight: bold;
            color: #2563EB !important;
        }

        /* Streamlit Element Overrides */
        div[data-testid="stExpander"] {
            border: 1px solid #E2E8F0 !important;
            border-radius: 12px !important;
            background-color: white !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        }

        .stButton>button {
            border-radius: 10px !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.5rem !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }

        .stButton>button:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
        }

        /* Selectbox and Radio styling */
        div[data-testid="stSelectbox"] > div {
            border-radius: 10px !important;
        }
        </style>
        """, unsafe_allow_html=True,
    )


def render_hero(result_df: pd.DataFrame, end_date, meta_file) -> None:
    _ = meta_file # Removed from display but kept in signature for compatibility
    date_str = pd.to_datetime(end_date).strftime('%d %b %Y')
    st.markdown(
        f"""
        <div class='hero'>
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class='hero-title'>MAXIMIXE DataBank</div>
                    <div class='hero-subtitle'>
                        Portal de datos de MAXIMIXE Economía & Mercados. 
                        Monitoreando y analizando <b>{len(result_df):,}</b> series macroeconómicas.
                    </div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 0.8rem; color: #94A3B8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 4px;">ESTADO DEL SISTEMA</div>
                    <div class='status-pill status-Normal' style="background: rgba(16, 185, 129, 0.15); color: #10B981;">● En línea y estable</div>
                </div>
            </div>
            <div style='margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(255, 255, 255, 0.1); display: flex; gap: 2rem; align-items: center;'>
                <div style='display: flex; flex-direction: column;'>
                    <span style='color: #94A3B8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;'>ÚLTIMA ACTUALIZACIÓN</span>
                    <span style='color: #F8FAFC; font-weight: 600;'>{date_str}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True,
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
    moving = result_df[result_df["semaforo"].isin(["Al alza", "A la baja"])][executive_cols(result_df)].head(30)
    html_table = friendly_columns(moving).to_html(index=False, escape=True)
    return f"""
    <html><head><meta charset="utf-8"><title>Monitor MAXIMIXE Data</title>
    <style>body{{font-family:Arial,sans-serif;color:#101828;margin:32px}} h1{{margin-bottom:4px}} .kpi{{display:inline-block;border:1px solid #ddd;border-radius:8px;padding:10px 14px;margin:6px}} table{{border-collapse:collapse;width:100%;font-size:12px}} th,td{{border:1px solid #ddd;padding:6px;text-align:left}} th{{background:#f3f4f6}}</style>
    </head><body>
    <h1>Monitor MAXIMIXE Data</h1>
    <p>Reporte ejecutivo generado el {datetime.now():%d/%m/%Y %H:%M}.</p>
    <div class="kpi">Al alza: <b>{int(counts.get("Al alza",0))}</b></div>
    <div class="kpi">Normal: <b>{int(counts.get("Normal",0))}</b></div>
    <div class="kpi">A la baja: <b>{int(counts.get("A la baja",0))}</b></div>
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
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        return f"{float(value):,.2f}"
    return str(value)


def format_dataframe_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]) and not pd.api.types.is_bool_dtype(out[col]):
            out[col] = out[col].round(2)
    return out


def format_dataframe_for_export(df: pd.DataFrame) -> pd.DataFrame:
    out = format_dataframe_values(df)
    return out.where(pd.notna(out), "")


def friendly_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = format_dataframe_values(df)
    return out.rename(columns={c: DISPLAY_NAMES.get(str(c), str(c)) for c in out.columns})


def status_css_class(value: object) -> str:
    text = str(value or "Sin datos").strip() or "Sin datos"
    return "status-" + text.replace(" ", "-")
