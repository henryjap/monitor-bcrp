import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from ui_logic import *
from constants import *
from html import escape

def polish_chart_layout(fig, top: int = 90):
    fig.update_layout(
        margin=dict(l=24, r=24, t=top, b=32),
        title=dict(
            y=0.98, x=0.02, xanchor="left", yanchor="top", 
            pad=dict(t=8, b=18),
            font=dict(family='Outfit', size=18, color='#0F172A')
        ),
        font=dict(family='Inter', size=12),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hovermode="x unified",
        xaxis=dict(showgrid=False, linecolor='#E2E8F0'),
        yaxis=dict(gridcolor='#F1F5F9', linecolor='#E2E8F0'),
    )
    return fig


def render_kpi_card(label: str, value: str | int, note: str = "", color: str = "#101828") -> None:
    # Map labels to icons for a richer look
    icon_map = {
        "Al alza": "📈", "Normal": "📊", "A la baja": "📉", "Sin datos": "❓",
        "Dato actual": "🎯", "Dato anterior": "⏮️", "Año anterior": "📅", "Estado dato": "⏱️",
        "Máximo histórico": "🏆", "Mínimo histórico": "⬇️", "Máximo año actual": "✨", "Mínimo año actual": "❄️",
        "Desvío vs tendencia": "🔄", "Z tendencia": "📐", "Tendencia 12m": "🌊", "Cambio 12m análisis": "⚡",
        "Posición histórica": "🏛️", "Posición móvil": "📱", "Posición año": "📆", "Cobertura móvil": "🧱"
    }
    icon = icon_map.get(label, "🔹")
    
    st.markdown(
        f"""
        <div class="kpi-card">
          <div style="font-size: 1.2rem; margin-bottom: 0.3rem;">{icon}</div>
          <div class="kpi-label">{escape(label)}</div>

          <div class="kpi-value" style="color:{color};">{escape(str(value))}</div>
          <div class="kpi-note">{escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )





def compact_chart_title(title: str, selected_label: str, max_label_chars: int = 88) -> str:
    label = str(selected_label or "").strip()
    if len(label) > max_label_chars:
        label = f"{label[:max_label_chars].rstrip()}..."
    return f"{escape(title)}<br><span style='font-size:12px;color:#667085'>{escape(label)}</span>"


def semaforo_chart(result_df: pd.DataFrame):
    estado_counts = (
        result_df["semaforo"]
        .value_counts()
        .reindex(SEMAFORO_ORDER, fill_value=0)
        .rename_axis("semaforo")
        .reset_index(name="series")
    )
    fig = px.bar(
        estado_counts,
        x="series",
        y="semaforo",
        orientation="h",
        color="semaforo",
        color_discrete_map=SEMAFORO_COLORS,
        text="series",
        title="Distribución del régimen de tendencia",
    )
    fig.update_layout(
        height=300,
        showlegend=False,
        xaxis_title="Series",
        yaxis_title="",
        yaxis=dict(categoryorder="array", categoryarray=list(reversed(SEMAFORO_ORDER))),
        uirevision="estado",
    )
    polish_chart_layout(fig, top=82)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


def frequency_status_summary(result_df: pd.DataFrame) -> pd.DataFrame:
    freq_col = "frecuencia_bcrp" if "frecuencia_bcrp" in result_df.columns else "frecuencia"
    rows = []
    for label in ["Diaria", "Mensual", "Trimestral", "Anual"]:
        df = result_df[result_df[freq_col].eq(label)].copy() if freq_col in result_df.columns else pd.DataFrame()
        rows.append({
            "frecuencia": label,
            "total": len(df),
            "al_alza": int(df["semaforo"].eq("Al alza").sum()) if "semaforo" in df else 0,
            "normal": int(df["semaforo"].eq("Normal").sum()) if "semaforo" in df else 0,
            "a_la_baja": int(df["semaforo"].eq("A la baja").sum()) if "semaforo" in df else 0,
            "sin_datos": int(df["semaforo"].eq("Sin datos").sum()) if "semaforo" in df else 0,
            "actualizadas": int(df["estado_actualizacion"].eq("Actualizada").sum()) if "estado_actualizacion" in df else 0,
        })
    return pd.DataFrame(rows)


def render_frequency_cards(result_df: pd.DataFrame) -> None:
    summary = frequency_status_summary(result_df)
    cols = st.columns(4)
    for col, row in zip(cols, summary.to_dict("records")):
        with col:
            st.markdown(
                f"""
                <div class="frequency-card">
                  <div class="frequency-card-title">{escape(str(row["frecuencia"]))}</div>
                  <div class="frequency-card-total">{int(row["total"])}</div>
                  <div class="kpi-note">series procesadas</div>
                  <div class="mini-row">
                    <div class="mini-stat" style="background:#D1E9FF;color:#175CD3;">Alza {int(row["al_alza"])}</div>
                    <div class="mini-stat" style="background:#DCFAE6;color:#067647;">Norm {int(row["normal"])}</div>
                    <div class="mini-stat" style="background:#FEE4E2;color:#B42318;">Baja {int(row["a_la_baja"])}</div>
                    <div class="mini-stat" style="background:#EAECF0;color:#344054;">s/d {int(row["sin_datos"])}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def category_status_matrix(result_df: pd.DataFrame) -> pd.DataFrame:
    if "categoria_bcrp" not in result_df.columns or "semaforo" not in result_df.columns:
        return pd.DataFrame()
    tmp = result_df.copy()
    tmp["categoria_bcrp"] = tmp["categoria_bcrp"].fillna("Sin categoría").replace("", "Sin categoría")
    mat = pd.crosstab(tmp["categoria_bcrp"], tmp["semaforo"])
    mat = mat.reindex(columns=SEMAFORO_ORDER, fill_value=0)
    mat["movimiento"] = mat.get("Al alza", 0) + mat.get("A la baja", 0)
    mat = mat.sort_values(["movimiento", "A la baja", "Al alza"], ascending=False).drop(columns="movimiento")
    return mat


def category_heatmap(result_df: pd.DataFrame):
    mat = category_status_matrix(result_df)
    if mat.empty:
        return None
    mat = mat.head(18)
    fig = px.imshow(
        mat,
        text_auto=True,
        aspect="auto",
        color_continuous_scale=["#F9FAFB", "#D1E9FF", "#84CAFF", "#175CD3"],
        title="Mapa de calor: categoría por régimen",
    )
    fig.update_layout(
        height=max(400, 30 * len(mat) + 150), 
        coloraxis_showscale=False,
        yaxis_title="",
        xaxis_title=""
    )
    polish_chart_layout(fig, top=96)
    fig.update_xaxes(side="top")
    return fig


def alert_ranking_chart(result_df: pd.DataFrame, group_col: str = "categoria_bcrp"):
    if group_col not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    tmp = result_df[result_df["semaforo"].isin(["Al alza", "A la baja"])].copy()
    if tmp.empty:
        return None
    tmp[group_col] = tmp[group_col].fillna("Sin categoría").replace("", "Sin categoría")
    counts = tmp.groupby([group_col, "semaforo"]).size().reset_index(name="series")
    totals = counts.groupby(group_col)["series"].sum().sort_values(ascending=False).head(12).index
    counts = counts[counts[group_col].isin(totals)]
    fig = px.bar(
        counts,
        x="series",
        y=group_col,
        color="semaforo",
        orientation="h",
        color_discrete_map=SEMAFORO_COLORS,
        title="Ranking de categorías con movimiento de tendencia",
    )
    fig.update_layout(height=max(380, 34 * len(totals) + 150), yaxis_title="", xaxis_title="Series", legend_title="")
    polish_chart_layout(fig, top=96)
    fig.update_yaxes(categoryorder="total ascending")
    return fig


def distance_position_summary_chart(result_df: pd.DataFrame):
    if "posicion_mov_0_100" not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    tmp = result_df.dropna(subset=["posicion_mov_0_100"]).copy()
    if tmp.empty:
        return None
    fig = px.histogram(
        tmp,
        x="posicion_mov_0_100",
        color="semaforo",
        nbins=10,
        color_discrete_map=SEMAFORO_COLORS,
        title="Distribución de posición móvil 0-100",
    )
    fig.add_vrect(x0=40, x1=60, fillcolor="#EAECF0", opacity=0.25, line_width=0)
    fig.update_layout(height=360, xaxis_title="Posición móvil", yaxis_title="Series", legend_title="")
    polish_chart_layout(fig, top=90)
    return fig


def distance_extreme_ranking_chart(result_df: pd.DataFrame):
    needed = {"codigo", "nombre_bcrp", "posicion_mov_0_100"}
    if not needed.issubset(result_df.columns):
        return None
    tmp = result_df.dropna(subset=["posicion_mov_0_100"]).copy()
    if tmp.empty:
        return None
    low = tmp.nsmallest(8, "posicion_mov_0_100").copy()
    high = tmp.nlargest(8, "posicion_mov_0_100").copy()
    plot_df = pd.concat([low.assign(extremo="Cerca del mínimo"), high.assign(extremo="Cerca del máximo")], ignore_index=True)
    plot_df["serie"] = plot_df["codigo"].astype(str) + " - " + plot_df["nombre_bcrp"].fillna("").astype(str).str.slice(0, 42)
    fig = px.bar(
        plot_df,
        x="posicion_mov_0_100",
        y="serie",
        color="extremo",
        orientation="h",
        text="posicion_mov_0_100",
        color_discrete_map={"Cerca del mínimo": "#B42318", "Cerca del máximo": "#175CD3"},
        title="Series más cercanas a extremos móviles",
    )
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_layout(
        height=max(470, 24 * len(plot_df) + 170),
        xaxis_title="Posición móvil",
        yaxis_title="",
        legend_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0),
        bargap=0.34,
    )
    polish_chart_layout(fig, top=128)
    fig.update_layout(margin=dict(l=24, r=96, t=128, b=36))
    fig.update_yaxes(categoryorder="total ascending")
    return fig


def category_stacked_chart(result_df: pd.DataFrame):
    if "categoria_bcrp" not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    mat = category_status_matrix(result_df)
    if mat.empty:
        return None
    top = mat.assign(total=mat.sum(axis=1)).sort_values("total", ascending=False).head(14).drop(columns="total")
    plot_df = top.reset_index().melt(id_vars="categoria_bcrp", var_name="semaforo", value_name="series")
    fig = px.bar(
        plot_df,
        x="series",
        y="categoria_bcrp",
        color="semaforo",
        orientation="h",
        color_discrete_map=SEMAFORO_COLORS,
        title="Semáforo por categoría",
    )
    fig.update_layout(height=max(390, 30 * len(top) + 150), yaxis_title="", xaxis_title="Series", legend_title="")
    polish_chart_layout(fig, top=92)
    fig.update_yaxes(categoryorder="total ascending")
    return fig


def freshness_chart(result_df: pd.DataFrame):
    if "estado_actualizacion" not in result_df.columns:
        return None
    counts = result_df["estado_actualizacion"].fillna("Sin fecha").replace("", "Sin fecha").value_counts().reset_index()
    counts.columns = ["estado_actualizacion", "series"]
    color_map = {"Actualizada": "#067647", "Rezagada": "#B42318", "Sin fecha": "#667085"}
    fig = px.bar(
        counts,
        x="series",
        y="estado_actualizacion",
        orientation="h",
        color="estado_actualizacion",
        color_discrete_map=color_map,
        text="series",
        title="Frescura de datos",
    )
    fig.update_layout(height=280, showlegend=False, xaxis_title="Series", yaxis_title="")
    polish_chart_layout(fig, top=82)
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


def style_alert_table(df: pd.DataFrame):
    def color_rows(row):
        estado = row.get("semaforo", "")
        bg = SEMAFORO_BG.get(estado, "")
        if not bg:
            return [""] * len(row)
        return [f"background-color: {bg}; color: #101828;" if row.name == row.name else "" for _ in row]

    return df.style.apply(color_rows, axis=1).hide(axis="index")


def render_sticky_table(df: pd.DataFrame, height: int = 520, max_rows: int = 350) -> None:
    if df.empty:
        st.info("No hay filas para mostrar.")
        return
    show = df.head(max_rows).copy() if max_rows and len(df) > max_rows else df.copy()
    if max_rows and len(df) > max_rows:
        st.caption(f"Vista rápida: se muestran {max_rows} de {len(df)} filas. Use filtros o exporte la base completa para ver todo.")
    sticky_cols = ["semaforo", "diagnostico", "codigo", "nombre_bcrp"]
    sticky_widths = {
        "semaforo": 92,
        "diagnostico": 112,
        "codigo": 116,
        "nombre_bcrp": 360,
    }
    left_positions = {}
    left = 0
    for col in sticky_cols:
        if col in show.columns:
            left_positions[col] = left
            left += sticky_widths[col]

    headers = []
    for col in show.columns:
        classes = "sticky-col" if col in left_positions else ""
        style = ""
        if col in left_positions:
            style = f"left:{left_positions[col]}px; min-width:{sticky_widths[col]}px; max-width:{sticky_widths[col]}px;"
        elif col == "lectura":
            style = "min-width:420px;"
        else:
            style = "min-width:130px;"
        headers.append(f'<th class="{classes}" style="{style}">{escape(DISPLAY_NAMES.get(str(col), str(col)))}</th>')

    rows = []
    for _, row in show.iterrows():
        estado = str(row.get("semaforo", ""))
        bg = SEMAFORO_BG.get(estado, "#FFFFFF")
        cells = []
        for col in show.columns:
            val = row.get(col, "")
            val = display_value(val)
            classes = "sticky-col" if col in left_positions else ""
            style = f"background:{bg};"
            if col in left_positions:
                style += f"left:{left_positions[col]}px; min-width:{sticky_widths[col]}px; max-width:{sticky_widths[col]}px;"
            elif col == "lectura":
                style += "min-width:420px;"
            else:
                style += "min-width:130px;"
            cells.append(f'<td class="{classes}" style="{style}">{escape(val)}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    st.markdown(
        f"""
        <div class="sticky-table-wrap" style="border:1px solid #EAECF0; border-radius:8px;">
          <table class="sticky-table">
            <thead><tr>{''.join(headers)}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        <style>
          .sticky-table {{
            border-collapse: separate;
            border-spacing: 0;
            width: max-content;
            min-width: 100%;
            font-size: 0.82rem;
          }}
          .sticky-table-wrap {{
            max-width: 100%;
            overflow-x: auto;
            overflow-y: visible;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior-x: contain;
            overscroll-behavior-y: auto;
          }}
          .sticky-table th {{
            position: sticky;
            top: 0;
            z-index: 4;
            background: #F9FAFB;
            color: #475467;
            border-bottom: 1px solid #EAECF0;
            border-right: 1px solid #EAECF0;
            text-align: left;
            padding: 0.45rem 0.55rem;
            white-space: nowrap;
          }}
          .sticky-table td {{
            border-bottom: 1px solid rgba(152, 162, 179, 0.24);
            border-right: 1px solid rgba(152, 162, 179, 0.24);
            padding: 0.42rem 0.55rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .sticky-table .sticky-col {{
            position: sticky;
            z-index: 3;
            box-shadow: 1px 0 0 #D0D5DD;
          }}
          .sticky-table th.sticky-col {{
            z-index: 5;
            background: #F2F4F7;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_card_value(value) -> str:
    if pd.isna(value):
        return "s/d"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def render_series_snapshot(row: pd.Series) -> None:
    # Summary Info Box
    semaforo = row.get("semaforo", "Sin datos")
    pill_class = f"status-{semaforo.replace(' ', '-')}"
    
    st.markdown(
        f"""
        <div style="background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <div style="font-family: 'Outfit', sans-serif; font-size: 1.25rem; font-weight: 700; color: #0F172A;">
                    {escape(str(row.get('codigo', '')))} <span style="color: #94A3B8; font-weight: 400; margin: 0 8px;">|</span> {escape(str(row.get('nombre_bcrp', '')))}
                </div>
                <span class="status-pill {pill_class}">{semaforo}</span>
            </div>
            <p style="color: #475467; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                {escape(str(row.get('lectura', '')))}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


    is_annual = frequency_bucket_for_update(row.get("frecuencia_bcrp") or row.get("frecuencia")) == "A"
    
    # Primary Data Cards
    cards = [
        ("Dato actual", row.get("dato_actual_original"), row.get("fecha_dato_actual", "")),
        ("Dato anterior", row.get("dato_anterior_original"), row.get("fecha_dato_anterior", "")),
        ("Estado dato", row.get("estado_actualizacion", ""), f"{row.get('dias_desde_ultimo_dato', '')} días"),
    ]
    if not is_annual:
        cards.insert(2, ("Año anterior", row.get("dato_anio_anterior_original"), row.get("fecha_dato_anio_anterior", "")))
    
    cols = st.columns(len(cards))
    for col, (label, value, note) in zip(cols, cards):
        color = "#0F172A"
        if label == "Estado dato":
            color = "#059669" if value == "Actualizada" else "#DC2626" if value == "Rezagada" else "#64748B"
        with col:
            render_kpi_card(label, fmt_card_value(value), str(note), color)

    # Secondary Variations
    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
    delta_prev = None
    delta_year = None
    if pd.notna(row.get("dato_actual_original")) and pd.notna(row.get("dato_anterior_original")):
        delta_prev = row.get("dato_actual_original") - row.get("dato_anterior_original")
    if not is_annual and pd.notna(row.get("dato_actual_original")) and pd.notna(row.get("dato_anio_anterior_original")):
        delta_year = row.get("dato_actual_original") - row.get("dato_anio_anterior_original")
    
    dcols = st.columns(1 if is_annual else 2)
    with dcols[0]:
        render_kpi_card("Diferencia vs anterior", fmt_card_value(delta_prev), "unidades originales")
    if not is_annual:
        with dcols[1]:
            render_kpi_card("Diferencia vs año anterior", fmt_card_value(delta_year), "unidades originales")


def render_series_extreme_cards(row: pd.Series) -> None:
    st.subheader("Extremos y tendencia")
    is_annual = frequency_bucket_for_update(row.get("frecuencia_bcrp") or row.get("frecuencia")) == "A"
    cards = [
        ("Máximo histórico", row.get("maximo_historico_valor"), row.get("fecha_maximo_historico", "")),
        ("Mínimo histórico", row.get("minimo_historico_valor"), row.get("fecha_minimo_historico", "")),
    ]
    if not is_annual:
        cards.extend([
            ("Máximo año actual", row.get("maximo_anio_actual_valor"), row.get("fecha_maximo_anio_actual", "")),
            ("Mínimo año actual", row.get("minimo_anio_actual_valor"), row.get("fecha_minimo_anio_actual", "")),
        ])
    cols = st.columns(len(cards))
    for col, (label, value, note) in zip(cols, cards):
        with col:
            render_kpi_card(label, fmt_card_value(value), str(note))

    trend_cols = st.columns(4)
    with trend_cols[0]:
        render_kpi_card("Desvío vs tendencia", fmt_card_value(row.get("desvio_frente_tendencia")), "unidades análisis")
    with trend_cols[1]:
        render_kpi_card("Z tendencia", fmt_card_value(row.get("desvio_tendencia_std")), row.get("posicion_vs_tendencia", ""))
    with trend_cols[2]:
        render_kpi_card("Tendencia anual" if is_annual else "Tendencia 12m", row.get("tendencia_12m_direccion", "s/d"), f"pendiente {fmt_card_value(row.get('tendencia_12m_pendiente'))}")
    with trend_cols[3]:
        render_kpi_card("Cambio anual análisis" if is_annual else "Cambio 12m análisis", fmt_card_value(row.get("tendencia_12m_cambio")), "serie tratada")


def render_distance_position_cards(row: pd.Series) -> None:
    st.subheader("Distancias metodológicas")
    is_annual = frequency_bucket_for_update(row.get("frecuencia_bcrp") or row.get("frecuencia")) == "A"
    cards = [("Posición histórica", row.get("posicion_hist_0_100"), row.get("semaforo_posicion_hist", ""))]
    if not is_annual:
        cards = [
            ("Posición año", row.get("posicion_ytd_0_100"), row.get("semaforo_posicion_ytd", "")),
            ("Posición móvil", row.get("posicion_mov_0_100"), row.get("semaforo_posicion_mov", "")),
            ("Posición histórica", row.get("posicion_hist_0_100"), row.get("semaforo_posicion_hist", "")),
            ("Cobertura móvil", row.get("cobertura_mov"), "observaciones"),
        ]
    cols = st.columns(len(cards))
    for col, (label, value, note) in zip(cols, cards):
        with col:
            render_kpi_card(label, fmt_card_value(value), str(note))

    dcols = st.columns(2)
    with dcols[0]:
        render_kpi_card("Distancia al mínimo móvil", fmt_card_value(row.get("dist_min_mov")), row.get("fecha_min_mov", ""))
    with dcols[1]:
        render_kpi_card("Distancia al máximo móvil", fmt_card_value(row.get("dist_max_mov")), row.get("fecha_max_mov", ""))
    comentario = str(row.get("comentario_distancias") or "")
    if comentario:
        st.caption(comentario)


def distance_position_bar_chart(row: pd.Series):
    values = pd.DataFrame([
        {"ventana": "Año", "posición": row.get("posicion_ytd_0_100"), "zona": row.get("semaforo_posicion_ytd", "")},
        {"ventana": "Móvil", "posición": row.get("posicion_mov_0_100"), "zona": row.get("semaforo_posicion_mov", "")},
        {"ventana": "Histórica", "posición": row.get("posicion_hist_0_100"), "zona": row.get("semaforo_posicion_hist", "")},
    ]).dropna(subset=["posición"])
    if values.empty:
        return None
    fig = px.bar(
        values,
        x="ventana",
        y="posición",
        color="zona",
        text="posición",
        title="Posición 0-100 frente a mínimos y máximos",
        color_discrete_map={
            "Muy cerca del mínimo": "#B42318",
            "Zona baja": "#F97066",
            "Zona media": "#98A2B3",
            "Zona alta": "#84CAFF",
            "Muy cerca del máximo": "#175CD3",
        },
    )
    fig.add_hrect(y0=40, y1=60, fillcolor="#EAECF0", opacity=0.28, line_width=0)
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    fig.update_layout(height=360, yaxis_range=[0, 105], xaxis_title="", yaxis_title="Posición en rango")
    polish_chart_layout(fig, top=88)
    return fig


def series_band_chart(df_sel: pd.DataFrame, selected_label: str):
    d = df_sel.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    if d.empty:
        return None
    p10 = d["valor"].expanding(min_periods=min(12, max(3, len(d) // 5))).quantile(0.1)
    p90 = d["valor"].expanding(min_periods=min(12, max(3, len(d) // 5))).quantile(0.9)
    ma = d["valor"].rolling(20, min_periods=5).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["fecha"], y=p90, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=d["fecha"],
        y=p10,
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(102,112,133,0.16)",
        name="Banda p10-p90",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(x=d["fecha"], y=d["valor"], mode="lines", name="Valor", line=dict(color="#175CD3", width=2)))
    fig.add_trace(go.Scatter(x=d["fecha"], y=ma, mode="lines", name="Media 20", line=dict(color="#B7791F", width=2, dash="dot")))
    fig.update_layout(
        title=f"Evolución con banda histórica: {selected_label}",
        height=420,
        margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="",
        yaxis_title="Valor original",
        uirevision=f"band-{selected_label}",
    )
    return fig


def ytd_extreme_chart(df_sel: pd.DataFrame, selected_label: str, freq: str = ""):
    if frequency_bucket_for_update(freq) == "A":
        return None
    d = df_sel.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    if d.empty:
        return None
    year = int(d["fecha"].max().year)
    ytd = d[d["fecha"].dt.year.eq(year)].copy()
    if ytd.empty:
        return None
    fig = px.line(ytd, x="fecha", y="valor", markers=True, title=compact_chart_title(f"Año actual: máximos y mínimos ({year})", selected_label), labels={"valor": "Valor"})
    max_row = ytd.loc[ytd["valor"].idxmax()]
    min_row = ytd.loc[ytd["valor"].idxmin()]
    fig.add_trace(go.Scatter(x=[max_row["fecha"]], y=[max_row["valor"]], mode="markers+text", name="Máximo YTD", marker=dict(color="#B42318", size=11), text=["Máx"], textposition="top center"))
    fig.add_trace(go.Scatter(x=[min_row["fecha"]], y=[min_row["valor"]], mode="markers+text", name="Mínimo YTD", marker=dict(color="#175CD3", size=11), text=["Mín"], textposition="bottom center"))
    fig.update_layout(height=400, margin=dict(l=18, r=18, t=82, b=76), xaxis_title="", yaxis_title="Valor original", legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, itemwidth=110))
    return fig


def previous_periods_extreme_chart(df_sel: pd.DataFrame, selected_label: str, freq: str = ""):
    bucket = frequency_bucket_for_update(freq)
    window_map = {"D": 365, "M": 12, "Q": 4}
    label_map = {
        "D": "365 datos diarios",
        "M": "12 meses",
        "Q": "4 trimestres",
    }
    window = window_map.get(bucket)
    if window is None:
        return None
    d = df_sel.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    if len(d) < 2:
        return None
    plot_df = d.tail(window).copy()
    current = plot_df.iloc[[-1]].copy()
    if plot_df.empty:
        return None
    window_label = label_map[bucket]
    fig = px.line(plot_df, x="fecha", y="valor", markers=True, title=compact_chart_title(f"Máximos y mínimos de los últimos {window_label}", selected_label), labels={"valor": "Valor"})
    max_row = plot_df.loc[plot_df["valor"].idxmax()]
    min_row = plot_df.loc[plot_df["valor"].idxmin()]
    fig.add_trace(go.Scatter(x=[max_row["fecha"]], y=[max_row["valor"]], mode="markers+text", name=f"Máximo últimos {window_label}", marker=dict(color="#B42318", size=11), text=["Máx"], textposition="top center"))
    fig.add_trace(go.Scatter(x=[min_row["fecha"]], y=[min_row["valor"]], mode="markers+text", name=f"Mínimo últimos {window_label}", marker=dict(color="#175CD3", size=11), text=["Mín"], textposition="bottom center"))
    fig.update_layout(height=420, margin=dict(l=18, r=18, t=82, b=82), xaxis_title="", yaxis_title="Valor original", legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, itemwidth=130))

    return fig


def historical_extreme_range_chart(df_sel: pd.DataFrame, selected_label: str):
    d = df_sel.dropna(subset=["fecha", "valor"]).copy().sort_values("fecha")
    if d.empty:
        return None
    fig = px.line(d, x="fecha", y="valor", title=compact_chart_title("Máximo y mínimo histórico del rango cargado", selected_label), labels={"valor": "Valor"})
    max_row = d.loc[d["valor"].idxmax()]
    min_row = d.loc[d["valor"].idxmin()]
    fig.add_trace(go.Scatter(x=[max_row["fecha"]], y=[max_row["valor"]], mode="markers+text", name="Máximo histórico", marker=dict(color="#B42318", size=11), text=["Máx"], textposition="top center"))
    fig.add_trace(go.Scatter(x=[min_row["fecha"]], y=[min_row["valor"]], mode="markers+text", name="Mínimo histórico", marker=dict(color="#175CD3", size=11), text=["Mín"], textposition="bottom center"))
    fig.update_layout(height=420, margin=dict(l=18, r=18, t=82, b=82), xaxis_title="", yaxis_title="Valor original", legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, itemwidth=130))

    return fig


def historical_distribution_chart(df_sel: pd.DataFrame, selected_label: str):
    d = df_sel.dropna(subset=["valor"]).copy()
    if d.empty:
        return None
    last_value = d["valor"].iloc[-1]
    fig = px.histogram(d, x="valor", nbins=35, title=f"Distribución histórica: {selected_label}", labels={"valor": "Valor"})
    fig.add_vline(x=last_value, line_color="#B42318", line_width=3, annotation_text="Último", annotation_position="top right")
    fig.update_layout(height=330, margin=dict(l=10, r=10, t=55, b=10), xaxis_title="Valor original", yaxis_title="Frecuencia")
    return fig


def trend_deviation_chart(df_sel: pd.DataFrame, selected_label: str):
    d = df_sel.dropna(subset=["fecha", "valor_analisis"]).copy().sort_values("fecha").tail(36)
    if len(d) < 5:
        return None
    x = list(range(len(d)))
    y = d["valor_analisis"].astype(float).to_numpy()
    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return None
    d["tendencia"] = intercept + slope * pd.Series(x, index=d.index)
    d["desvio"] = d["valor_analisis"] - d["tendencia"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["fecha"], y=d["valor_analisis"], mode="lines", name="Serie análisis", line=dict(color="#175CD3", width=2)))
    fig.add_trace(go.Scatter(x=d["fecha"], y=d["tendencia"], mode="lines", name="Tendencia", line=dict(color="#B7791F", width=2, dash="dash")))
    fig.add_trace(go.Bar(x=d["fecha"], y=d["desvio"], name="Desvío", marker_color="#98A2B3", opacity=0.35, yaxis="y2"))
    fig.update_layout(
        title=f"Tendencia reciente y desvío: {selected_label}",
        height=390,
        margin=dict(l=10, r=10, t=55, b=10),
        xaxis_title="",
        yaxis=dict(title="Valor análisis"),
        yaxis2=dict(title="Desvío", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def filter_results(result_df: pd.DataFrame, key_prefix: str = "filters") -> pd.DataFrame:
    if result_df.empty:
        return result_df
    with st.container():
        f1, f2, f3, f4 = st.columns([1.2, 1.3, 1.4, 1.2])
        available_states = [s for s in SEMAFORO_ORDER if s in set(result_df.get("semaforo", []))]
        selected_states = f1.multiselect("Régimen", available_states, default=available_states, key=f"{key_prefix}_estado")
        freq_col = "frecuencia_bcrp" if "frecuencia_bcrp" in result_df.columns else "frecuencia"
        freq_values = sorted([x for x in result_df.get(freq_col, pd.Series(dtype=str)).dropna().unique().tolist() if str(x)])
        selected_freqs = f2.multiselect("Frecuencia", freq_values, default=freq_values, key=f"{key_prefix}_freq")
        class_values = sorted([x for x in result_df.get("clase_serie", pd.Series(dtype=str)).dropna().unique().tolist() if str(x)])
        selected_classes = f3.multiselect("Clase de serie", class_values, default=class_values, key=f"{key_prefix}_class")
        review_only = f4.checkbox("Solo revisión requerida", value=False, key=f"{key_prefix}_review")
        query = st.text_input("Buscar por código, nombre o diagnóstico", value="", key=f"{key_prefix}_query")

    filtered = result_df.copy()
    if selected_states and "semaforo" in filtered.columns:
        filtered = filtered[filtered["semaforo"].isin(selected_states)]
    if selected_freqs and freq_col in filtered.columns:
        filtered = filtered[filtered[freq_col].isin(selected_freqs)]
    if selected_classes and "clase_serie" in filtered.columns:
        filtered = filtered[filtered["clase_serie"].isin(selected_classes)]
    if review_only and "revision_requerida" in filtered.columns:
        filtered = filtered[filtered["revision_requerida"].fillna(False).astype(bool)]
    if query.strip():
        q = query.strip().lower()
        search_cols = [c for c in ["codigo", "nombre_bcrp", "nombre", "diagnostico", "lectura"] if c in filtered.columns]
        mask = pd.Series(False, index=filtered.index)
        for col in search_cols:
            mask = mask | filtered[col].fillna("").astype(str).str.lower().str.contains(q, regex=False)
        filtered = filtered[mask]
    return filtered


def _filter_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].fillna("").astype(str).str.strip()
    unique_vals = [x for x in values.unique().tolist() if x]
    
    # Priority sorting for categories
    if column == "categoria_bcrp":
        priority = [x for x in PRIORITY_CATEGORIES if x in unique_vals]
        others = sorted([x for x in unique_vals if x not in PRIORITY_CATEGORIES])
        return priority + others
        
    return sorted(unique_vals)


def filter_explore_series(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty:
        return result_df

    freq_col = "frecuencia_bcrp" if "frecuencia_bcrp" in result_df.columns else "frecuencia"
    c1, c2, c3, c4 = st.columns(4)
    selected_freqs = c1.multiselect(
        "Frecuencia",
        _filter_values(result_df, freq_col),
        default=[],
        key="explore_filter_frequency",
        placeholder="Todas",
    )
    selected_categories = c2.multiselect(
        "Categoría",
        _filter_values(result_df, "categoria_bcrp"),
        default=[],
        key="explore_filter_category",
        placeholder="Todas",
    )
    selected_groups = c3.multiselect(
        "Grupo",
        _filter_values(result_df, "grupo_bcrp"),
        default=[],
        key="explore_filter_group",
        placeholder="Todos",
    )
    selected_sections = c4.multiselect(
        "Sección",
        _filter_values(result_df, "seccion_bcrp"),
        default=[],
        key="explore_filter_section",
        placeholder="Todas",
    )

    c5, c6, c7 = st.columns(3)
    selected_states = c5.multiselect(
        "Régimen",
        [s for s in SEMAFORO_ORDER if s in set(result_df.get("semaforo", []))],
        default=[],
        key="explore_filter_state",
        placeholder="Todos",
    )
    selected_classes = c6.multiselect(
        "Clase / tipo",
        _filter_values(result_df, "clase_serie") or _filter_values(result_df, "tipo_variable"),
        default=[],
        key="explore_filter_class",
        placeholder="Todas",
    )
    query = c7.text_input(
        "Buscar",
        value="",
        key="explore_filter_query",
        placeholder="Código, nombre, grupo, sección...",
    )

    filtered = result_df.copy()
    if selected_freqs and freq_col in filtered.columns:
        filtered = filtered[filtered[freq_col].fillna("").astype(str).isin(selected_freqs)]
    if selected_categories and "categoria_bcrp" in filtered.columns:
        filtered = filtered[filtered["categoria_bcrp"].fillna("").astype(str).isin(selected_categories)]
    if selected_groups and "grupo_bcrp" in filtered.columns:
        filtered = filtered[filtered["grupo_bcrp"].fillna("").astype(str).isin(selected_groups)]
    if selected_sections and "seccion_bcrp" in filtered.columns:
        filtered = filtered[filtered["seccion_bcrp"].fillna("").astype(str).isin(selected_sections)]
    if selected_states and "semaforo" in filtered.columns:
        filtered = filtered[filtered["semaforo"].fillna("").astype(str).isin(selected_states)]
    if selected_classes:
        class_col = "clase_serie" if "clase_serie" in filtered.columns else "tipo_variable"
        if class_col in filtered.columns:
            filtered = filtered[filtered[class_col].fillna("").astype(str).isin(selected_classes)]
    if query.strip():
        q = query.strip().lower()
        search_cols = [
            c
            for c in ["codigo", "nombre_bcrp", "nombre", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "tipo_variable", "clase_serie"]
            if c in filtered.columns
        ]
        mask = pd.Series(False, index=filtered.index)
        for col in search_cols:
            mask = mask | filtered[col].fillna("").astype(str).str.lower().str.contains(q, regex=False)
        filtered = filtered[mask]

    st.caption(f"Universo filtrado: {len(filtered)} de {len(result_df)} series.")
    return filtered


def render_frequency_category_view(result_df: pd.DataFrame) -> None:
    st.markdown("<div style='margin-bottom: 2rem;'></div>", unsafe_allow_html=True)
    
    freq_col = "frecuencia_bcrp" if "frecuencia_bcrp" in result_df.columns else "frecuencia"
    category_col = "categoria_bcrp" if "categoria_bcrp" in result_df.columns else ""
    
    frequency_tabs = [
        ("Diarias", "Diaria"),
        ("Mensuales", "Mensual"),
        ("Trimestrales", "Trimestral"),
        ("Anuales", "Anual"),
    ]
    
    # Header
    st.markdown("### 📊 Desglose por Frecuencia")
    
    labels = [f"{label} ({int(result_df[freq_col].eq(value).sum()) if freq_col in result_df.columns else 0})" for label, value in frequency_tabs]
    selected_label = st.radio("Frecuencia", labels, horizontal=True, key="frequency_view", label_visibility="collapsed")
    
    label_idx = labels.index(selected_label)
    label, freq_value = frequency_tabs[label_idx]
    
    freq_df = result_df[result_df[freq_col].eq(freq_value)].copy() if freq_col in result_df.columns else pd.DataFrame()
    
    if freq_df.empty:
        st.info(f"No hay series de frecuencia {label.lower()}.")
        return

    # Category Selector inside the view
    if category_col:
        unique_cats = [str(x) for x in freq_df[category_col].fillna("").unique().tolist() if str(x).strip()]
        priority = [x for x in PRIORITY_CATEGORIES if x in unique_cats]
        others = sorted([x for x in unique_cats if x not in PRIORITY_CATEGORIES])
        categories = priority + others
        
        category = st.selectbox(
            f"Filtrar {label.lower()} por categoría",
            ["Todas"] + categories,
            key=f"cat_select_{freq_value}",
        )
        if category != "Todas":
            freq_df = freq_df[freq_df[category_col].eq(category)].copy()

    # Visual Summary
    cat_counts = freq_df.groupby(category_col).size().reset_index(name="series") if category_col else pd.DataFrame()
    cat_counts = cat_counts.sort_values("series", ascending=False) if not cat_counts.empty else cat_counts
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f"#### 🏷️ Resumen Categorías")
        st.dataframe(friendly_columns(cat_counts), use_container_width=True, hide_index=True)
        st.caption(f"{len(freq_df)} series visibles.")
        
    with c2:
        st.markdown(f"#### 🔍 Vista de Auditoría")
        render_sticky_table(freq_df[executive_cols(freq_df)].head(200))


def apply_focus_filter(result_df: pd.DataFrame, category: str = "Todas", frequency: str = "Todas") -> pd.DataFrame:
    out = result_df.copy()
    if category != "Todas" and "categoria_bcrp" in out.columns:
        out = out[out["categoria_bcrp"].fillna("").eq(category)].copy()
    if frequency != "Todas":
        freq_col = "frecuencia_bcrp" if "frecuencia_bcrp" in out.columns else "frecuencia"
        if freq_col in out.columns:
            out = out[out[freq_col].fillna("").eq(frequency)].copy()
    return out


def sort_by_reading_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    if mode == "Rezago de datos" and "dias_desde_ultimo_dato" in out.columns:
        return out.sort_values("dias_desde_ultimo_dato", ascending=False, na_position="last")
    if mode == "Movimientos recientes" and {"dato_actual_original", "dato_anterior_original"}.issubset(out.columns):
        out["_mov_abs"] = (out["dato_actual_original"] - out["dato_anterior_original"]).abs()
        return out.sort_values("_mov_abs", ascending=False, na_position="last").drop(columns="_mov_abs")
    if mode == "Comparación anual" and {"dato_actual_original", "dato_anio_anterior_original"}.issubset(out.columns):
        out["_yoy_abs"] = (out["dato_actual_original"] - out["dato_anio_anterior_original"]).abs()
        return out.sort_values("_yoy_abs", ascending=False, na_position="last").drop(columns="_yoy_abs")
    order = {"A la baja": 0, "Al alza": 1, "Normal": 2, "Sin datos": 3}
    if "semaforo" in out.columns:
        out["_risk_order"] = out["semaforo"].map(order).fillna(9)
        return out.sort_values(["_risk_order", "dias_desde_ultimo_dato", "codigo"], ascending=[True, False, True], na_position="last").drop(columns="_risk_order")
    return out


def risk_radar_df(result_df: pd.DataFrame) -> pd.DataFrame:
    if result_df.empty:
        return pd.DataFrame()
    tmp = result_df.copy()
    tmp["alerta"] = tmp["semaforo"].isin(["Al alza", "A la baja"]).map({True: "Con tendencia", False: "Normal/sin datos"})
    tmp["frescura"] = tmp["estado_actualizacion"].eq("Actualizada").map({True: "Dato actualizado", False: "Dato rezagado"})
    return tmp.groupby(["alerta", "frescura"]).size().reset_index(name="series")


def risk_radar_chart(result_df: pd.DataFrame):
    df = risk_radar_df(result_df)
    if df.empty:
        return None
    fig = px.bar(
        df,
        x="frescura",
        y="series",
        color="alerta",
        barmode="group",
        color_discrete_map={"Con tendencia": "#175CD3", "Normal/sin datos": "#067647"},
        title="Radar de tendencia: régimen vs frescura",
        text="series",
    )
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=55, b=10), xaxis_title="", yaxis_title="Series", legend_title="")
    return fig


def timeline_alerts_chart(result_df: pd.DataFrame):
    if "ultima_fecha" not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    tmp = result_df.dropna(subset=["ultima_fecha"]).copy()
    tmp["ultima_fecha"] = pd.to_datetime(tmp["ultima_fecha"], errors="coerce")
    tmp = tmp.dropna(subset=["ultima_fecha"])
    if tmp.empty:
        return None
    tmp["periodo"] = tmp["ultima_fecha"].dt.to_period("M").astype(str)
    counts = tmp.groupby(["periodo", "semaforo"]).size().reset_index(name="series")
    fig = px.bar(
        counts,
        x="periodo",
        y="series",
        color="semaforo",
        color_discrete_map=SEMAFORO_COLORS,
        title="Timeline de últimos datos por régimen",
    )
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=55, b=10), xaxis_title="", yaxis_title="Series", legend_title="")
    return fig


def animated_status_chart(result_df: pd.DataFrame):
    if "ultima_fecha" not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    tmp = result_df.dropna(subset=["ultima_fecha"]).copy()
    tmp["ultima_fecha"] = pd.to_datetime(tmp["ultima_fecha"], errors="coerce")
    tmp = tmp.dropna(subset=["ultima_fecha"])
    if tmp.empty:
        return None
    tmp["periodo"] = tmp["ultima_fecha"].dt.to_period("M").astype(str)
    counts = tmp.groupby(["periodo", "semaforo"]).size().reset_index(name="series")
    frames = []
    for periodo in sorted(counts["periodo"].unique()):
        cur = counts[counts["periodo"].le(periodo)].groupby("semaforo")["series"].sum().reindex(SEMAFORO_ORDER, fill_value=0).reset_index()
        cur["periodo"] = periodo
        frames.append(cur)
    plot_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if plot_df.empty:
        return None
    fig = px.bar(
        plot_df,
        x="semaforo",
        y="series",
        color="semaforo",
        animation_frame="periodo",
        color_discrete_map=SEMAFORO_COLORS,
        title="Animación temporal de régimen acumulado",
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=55, b=10), showlegend=False, xaxis_title="", yaxis_title="Series")
    return fig


def treemap_category_chart(result_df: pd.DataFrame):
    if "categoria_bcrp" not in result_df.columns or "semaforo" not in result_df.columns:
        return None
    tmp = result_df.copy()
    tmp["categoria_bcrp"] = tmp["categoria_bcrp"].fillna("Sin categoría").replace("", "Sin categoría")
    tmp["riesgo_score"] = tmp["semaforo"].map({"A la baja": 3, "Al alza": 2, "Normal": 1, "Sin datos": 0}).fillna(0)
    agg = tmp.groupby("categoria_bcrp").agg(series=("codigo", "count"), riesgo=("riesgo_score", "mean")).reset_index()
    if agg.empty:
        return None
    fig = px.treemap(agg, path=["categoria_bcrp"], values="series", color="riesgo", color_continuous_scale=["#EAECF0", "#DCFAE6", "#D1E9FF", "#FEE4E2"], title="Treemap por categoría")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=55, b=10))
    return fig


def network_sunburst_chart(result_df: pd.DataFrame):
    needed = {"categoria_bcrp", "grupo_bcrp", "codigo", "semaforo"}
    if not needed.issubset(result_df.columns):
        return None
    tmp = result_df.copy()
    tmp["categoria_bcrp"] = tmp["categoria_bcrp"].fillna("Sin categoría").replace("", "Sin categoría")
    tmp["grupo_bcrp"] = tmp["grupo_bcrp"].fillna("Sin grupo").replace("", "Sin grupo")
    if "seccion_bcrp" in tmp.columns:
        tmp["seccion_bcrp"] = tmp["seccion_bcrp"].fillna("Sin sección").replace("", "Sin sección")
    tmp["riesgo_score"] = tmp["semaforo"].map({"A la baja": 3, "Al alza": 2, "Normal": 1, "Sin datos": 0}).fillna(0)
    plot_tmp = tmp.head(800).copy()
    plot_tmp["series_count"] = 1
    fig = px.sunburst(
        plot_tmp,
        path=[c for c in ["categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "codigo"] if c in plot_tmp.columns],
        values="series_count",
        color="riesgo_score",
        color_continuous_scale=["#EAECF0", "#DCFAE6", "#D1E9FF", "#FEE4E2"],
        title="Red exploratoria: categoría > grupo > sección > serie",
    )
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=55, b=10))
    return fig


def top_movements_df(result_df: pd.DataFrame, mode: str, n: int = 15) -> pd.DataFrame:
    out = result_df.copy()
    if mode == "vs anterior":
        if {"dato_actual_original", "dato_anterior_original"}.issubset(out.columns):
            out["movimiento"] = out["dato_actual_original"] - out["dato_anterior_original"]
        else:
            out["movimiento"] = pd.NA
    else:
        if {"dato_actual_original", "dato_anio_anterior_original"}.issubset(out.columns):
            out["movimiento"] = out["dato_actual_original"] - out["dato_anio_anterior_original"]
        else:
            out["movimiento"] = pd.NA
    out["movimiento_abs"] = out["movimiento"].abs()
    cols = [c for c in ["semaforo", "codigo", "nombre_bcrp", "frecuencia_bcrp", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp", "dato_actual_original", "movimiento"] if c in out.columns]
    return out.dropna(subset=["movimiento_abs"]).sort_values("movimiento_abs", ascending=False).head(n)[cols]


def top_movements_chart(result_df: pd.DataFrame, mode: str):
    df = top_movements_df(result_df, mode, 12)
    if df.empty:
        return None
    fig = px.bar(
        df,
        x="movimiento",
        y="codigo",
        color="semaforo",
        color_discrete_map=SEMAFORO_COLORS,
        orientation="h",
        title=f"Top movimientos {mode}",
        hover_data=[c for c in ["nombre_bcrp", "categoria_bcrp", "grupo_bcrp", "seccion_bcrp"] if c in df.columns],
    )
    fig.update_layout(height=390, margin=dict(l=10, r=10, t=55, b=10), yaxis_title="", xaxis_title="Diferencia")
    fig.update_yaxes(categoryorder="total ascending")
    return fig

    return fig
