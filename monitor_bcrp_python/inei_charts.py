"""Gráficos Plotly para dashboard INEI"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def polish_chart_layout(fig, top: int = 80):
    """Estilo consistente para todos los gráficos."""
    fig.update_layout(
        margin=dict(l=24, r=24, t=top, b=32),
        title=dict(
            y=0.97,
            x=0.02,
            xanchor="left",
            yanchor="top",
            pad=dict(t=8, b=12),
            font=dict(family="DM Sans", size=16, color="#1A1A2E"),
        ),
        font=dict(family="DM Sans", size=11),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
        xaxis=dict(showgrid=False, linecolor="#D8D2CA"),
        yaxis=dict(gridcolor="#EAE5DF", linecolor="#D8D2CA"),
    )
    return fig


def line_chart(df: pd.DataFrame, label: str, freq: str = "Anual") -> go.Figure:
    """Gráfico de línea principal."""
    fig = px.line(df, x="fecha", y="valor", markers=True)
    fig.update_traces(
        line=dict(color="#2565AE", width=2),
        marker=dict(size=5, color="#2565AE"),
        hovertemplate="%{x|%Y-%m}<br>%{y:,.2f}<extra></extra>",
    )
    freq_suffix = {"Anual": "", "Mensual": " (mensual)", "Trimestral": " (trimestral)"}
    fig.update_layout(
        title=f"{label}{freq_suffix.get(freq, '')}",
        yaxis_title="Valor",
        xaxis_title="",
    )
    return polish_chart_layout(fig)


def comparison_chart(df: pd.DataFrame, analysis: dict,
                     label: str) -> go.Figure:
    """Gráfico con banda de tendencia y promedios móviles."""
    fig = go.Figure()
    x = df["fecha"]
    y = df["valor"]

    # Serie original
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers",
        name="Original",
        line=dict(color="#2565AE", width=2),
        marker=dict(size=4, color="#2565AE"),
    ))

    # Promedio móvil 12m
    if len(y) >= 12:
        ma12 = y.rolling(12).mean()
        fig.add_trace(go.Scatter(
            x=x, y=ma12, mode="lines",
            name="MA 12",
            line=dict(color="#C62828", width=1.5, dash="dash"),
        ))

    # Promedio móvil 3m
    if len(y) >= 3:
        ma3 = y.rolling(3).mean()
        fig.add_trace(go.Scatter(
            x=x, y=ma3, mode="lines",
            name="MA 3",
            line=dict(color="#C9A84C", width=1.5, dash="dot"),
        ))

    fig.update_layout(
        title=f"{label} — Comparación",
        yaxis_title="Valor",
        xaxis_title="",
    )
    return polish_chart_layout(fig)


def var_chart(df: pd.DataFrame, analysis: dict,
              label: str) -> go.Figure | None:
    """Gráfico de barras de variación interanual."""
    if "var_interanual_pct" not in analysis or np.isnan(analysis.get("var_interanual_pct", np.nan)):
        return None

    # Calcular var% interanual para toda la serie
    df_v = df.copy().sort_values("fecha")
    df_v["var_ia"] = df_v["valor"].pct_change(periods=12 if len(df_v) > 12 else 1) * 100

    fig = px.bar(
        df_v.dropna(subset=["var_ia"]),
        x="fecha", y="var_ia",
        color=df_v.dropna(subset=["var_ia"])["var_ia"] >= 0,
        color_discrete_map={True: "#11734C", False: "#C62828"},
    )
    fig.update_traces(hovertemplate="%{x|%Y-%m}<br>%{y:,.2f}%<extra></extra>")
    fig.update_layout(
        title=f"{label} — Variación interanual %",
        yaxis_title="Var %",
        xaxis_title="",
        showlegend=False,
    )
    return polish_chart_layout(fig)


def distribution_chart(df: pd.DataFrame, analysis: dict,
                       label: str) -> go.Figure:
    """Histograma de la distribución de valores."""
    fig = px.histogram(
        df, x="valor", nbins=30,
        color_discrete_sequence=["#2565AE"],
    )
    fig.update_traces(hovertemplate="Rango: %[x:,.2f]<br>Frecuencia: %[y]<extra></extra>")
    fig.update_layout(
        title=f"{label} — Distribución",
        yaxis_title="Frecuencia",
        xaxis_title="Valor",
        showlegend=False,
    )
    return polish_chart_layout(fig)
