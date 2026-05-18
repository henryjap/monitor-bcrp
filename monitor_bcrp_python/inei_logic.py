"""Lógica de UI para dashboard INEI"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st


def metric_card(label: str, value, fmt: str = "{:,.2f}",
                delta=None, help_text: str = ""):
    """Tarjeta métrica con formato."""
    if value is None or (isinstance(value, float) and (pd.isna(value) or np.isinf(value))):
        display = "—"
        delta = None
    else:
        try:
            display = fmt.format(value)
        except (ValueError, TypeError):
            display = str(value)
    st.metric(label=label, value=display, delta=delta, help=help_text)


def analysis_html(analysis: dict) -> str:
    """Genera HTML con métricas de análisis."""
    if not analysis or "error" in analysis:
        return f'<p style="color:#C62828;">{analysis.get("error", "Sin datos")}</p>'

    def v(key, fmt="{:,.2f}", default="—"):
        val = analysis.get(key)
        if val is None or (isinstance(val, float) and (pd.isna(val) or np.isinf(val))):
            return default
        try:
            return fmt.format(val)
        except (ValueError, TypeError):
            return str(val)

    h = f"""
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
      <div><b>Último:</b> {v('ultimo_valor')}</div>
      <div><b>Fecha:</b> {v('fecha_ultimo', '{}')}</div>
      <div><b>Anterior:</b> {v('valor_anterior')}</div>
      <div><b>Fecha ant:</b> {v('fecha_anterior', '{}')}</div>
      <div><b>Var % período:</b> {v('var_periodo_pct', '{:+.2f}%')}</div>
      <div><b>Var % interanual:</b> {v('var_interanual_pct', '{:+.2f}%')}</div>
      <div><b>Media:</b> {v('media')}</div>
      <div><b>Mediana:</b> {v('mediana')}</div>
      <div><b>Mínimo:</b> {v('minimo')}</div>
      <div><b>Máximo:</b> {v('maximo')}</div>
      <div><b>Desviación:</b> {v('desviacion')}</div>
      <div><b>Coef. variación:</b> {v('coef_variacion', '{:.4f}')}</div>
      <div><b>Percentil histórico:</b> {v('percentil_historico', '{:.1%}')}</div>
      <div><b>Tendencia pendiente:</b> {v('tendencia_pendiente')}</div>
      <div><b>Tendencia R²:</b> {v('tendencia_r2', '{:.3f}')}</div>
    </div>
    """
    return h
