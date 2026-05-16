import os

charts_path = "ui_charts.py"
with open(charts_path, "r", encoding="utf-8") as f:
    content = f.read()

constants = """
SEMAFORO_COLORS = {
    "Al alza": "#175CD3",
    "Normal": "#067647",
    "A la baja": "#B42318",
    "Sin datos": "#667085",
    "Rojo": "#B42318",
    "Amarillo": "#B7791F",
    "Verde": "#067647",
    "Gris": "#667085",
}
SEMAFORO_BG = {
    "Al alza": "#D1E9FF",
    "Normal": "#DCFAE6",
    "A la baja": "#FEE4E2",
    "Sin datos": "#EAECF0",
    "Rojo": "#FEE4E2",
    "Amarillo": "#FEF0C7",
    "Verde": "#DCFAE6",
    "Gris": "#EAECF0",
}
SEMAFORO_ORDER = ["Al alza", "Normal", "A la baja", "Sin datos"]
"""

with open(charts_path, "w", encoding="utf-8") as f:
    f.write(content.replace("import streamlit as st\n\n", f"import streamlit as st\n{constants}\n"))
