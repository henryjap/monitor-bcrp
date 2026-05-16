import os
import shutil

app_path = "app.py"
charts_path = "ui_charts.py"

with open(app_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Encontrar índices de inicio y fin de las gráficas
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("def polish_chart_layout"):
        start_idx = i
    if line.startswith("def top_movements_chart"):
        # Buscar el final de esta función
        end_idx = i
        for j in range(i+1, len(lines)):
            if lines[j].startswith("def ") or lines[j].startswith("def "):
                pass
            if lines[j].startswith("def show_dashboard"):
                end_idx = j - 1
                break

if start_idx != -1 and end_idx != -1:
    chart_lines = lines[start_idx:end_idx+1]
    
    # Escribir ui_charts.py
    with open(charts_path, "w", encoding="utf-8") as f:
        f.write("import pandas as pd\nimport numpy as np\nimport plotly.express as px\nimport plotly.graph_objects as go\nimport streamlit as st\n\n")
        f.writelines(chart_lines)
    
    # Quitar las líneas de app.py
    new_app_lines = lines[:start_idx] + ["from ui_charts import *\n"] + lines[end_idx+1:]
    with open(app_path, "w", encoding="utf-8") as f:
        f.writelines(new_app_lines)
        
    print(f"Éxito: Se extrajeron {len(chart_lines)} líneas a {charts_path}")
else:
    print("No se encontraron las funciones de gráficas.")
