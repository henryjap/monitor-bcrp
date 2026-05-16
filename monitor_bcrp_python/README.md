# Monitor MAXIMIXE Data

Aplicación local en Streamlit para monitorear series económicas con identidad MAXIMIXE Data, metadatos de fuente, clasificación económica, régimen ejecutivo de tendencia, auditoría de reglas y exportación a CSV/Excel.

La interfaz está organizada en cuatro modos:

- `Ejecutivo`: sala de control y régimen de tendencia con nombres de columnas amigables.
- `Analítico`: frecuencia, dinámica y exploración profunda de series.
- `Auditoría`: clasificación, casos que requieren revisión, catálogo enriquecido y errores.
- `Exportar`: resumen ejecutivo en CSV y base completa en Excel.

Las tablas ejecutivas muestran solo las columnas clave para decisión: semáforo, diagnóstico, código, serie, categoría, frecuencia, último corte, dato actual, dato anterior, dato del año previo, variación interanual, posición frente a tendencia, actualización, días sin actualizar, percentil histórico y revisión. El detalle técnico conserva la base completa.

El tablero incorpora visuales ejecutivos: tarjetas por frecuencia, mapa de calor categoría por semáforo, ranking de categorías con alertas, barras apiladas por categoría, frescura de datos, ficha comparativa por serie y gráfico de evolución con banda histórica p10-p90.

La pestaña `Dinámica` agrega análisis interactivo: drill-down por categoría/frecuencia, modo de lectura, radar de riesgo, treemap, timeline, animación temporal, comparador de series, sensibilidad de alertas, buscador inteligente, panel de anomalías y bookmarks.

La pestaña `Explorar serie` funciona como ficha analítica de una variable: muestra dato actual, dato anterior, dato comparable del año previo, máximos y mínimos históricos, máximos y mínimos del año actual, desvío frente a tendencia, dirección de los últimos 12 meses, distribución histórica, comparación de cortes, tendencia con desvío y evolución anual.

Las tablas principales muestran como identidad de serie los campos del metadato BCRP: `codigo`, `nombre_bcrp`, `grupo_bcrp`, `categoria_bcrp`, `frecuencia_bcrp` y `fecha_inicio_meta`. La fecha final no se toma del metadato; se reporta como `ultima_fecha`, calculada desde la respuesta vigente de la API.

En las vistas ejecutivas, las columnas `semaforo`, `diagnostico`, `codigo` y `nombre_bcrp` quedan fijas al desplazar la tabla hacia la derecha. Además se muestran tres cortes comparables: `dato_actual_original`, `dato_anterior_original` y `dato_anio_anterior_original`, con sus fechas respectivas. Para series diarias el dato anterior es la observación previa disponible; para series mensuales, trimestrales y anuales corresponde al periodo anterior. El dato de año anterior corresponde al mismo periodo comparable del año previo.

Cuando está disponible `BCRP_metadata_clasificacion_variables.xlsx`, el monitor usa la hoja `Clasificacion_series` para decidir el tratamiento por `tipo_variable`, `subtipo_variable` y `ventana_variacion`. Esa capa evita transformar dos veces series que ya vienen como variación porcentual y mantiene como nivel las tasas, ratios, participaciones e índices de difusión cuando corresponde. Los overrides manuales siguen teniendo prioridad final.

## Instalación rápida en Windows

1. Descomprima el ZIP en una carpeta local, por ejemplo en `Documentos`.
2. Haga doble clic en `Monitor MAXIMIXE Data.vbs`.
3. La primera vez se crea el entorno local `.venv` y se instalan dependencias.
4. Espere a que se abra el navegador con la app.

El archivo `ejecutar_monitor.bat` crea el entorno `.venv` solo la primera vez, instala dependencias una sola vez y luego abre el navegador automáticamente. Si el puerto `8501` está ocupado, usa el siguiente puerto disponible. La ventana de consola debe quedar abierta mientras se use la app.

Para un arranque más limpio, use `Monitor MAXIMIXE Data.vbs`. Ese lanzador abre la misma app con la consola minimizada.

La PC debe tener Python 3.10 o superior instalado. Si no lo tiene, instálelo desde `https://www.python.org/downloads/` y marque `Add python.exe to PATH` durante la instalación.

Si cambia `requirements.txt` o necesita reinstalar librerías, ejecute `reinstalar_dependencias.bat`.

También puede abrir una terminal en la carpeta y correr:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

## Flujo recomendado

1. Pegue códigos BCRP o suba el catálogo CSV/Excel.
2. También puede elegir `Todas las series del metadato` para construir el universo desde el CSV de metadatos; si no existe, se usa el Excel de clasificación como respaldo.
3. Defina fecha inicial, fecha final y el máximo de series, o active `Procesar todas las series disponibles` para no aplicar límite.
4. Mantenga activada la clasificación con metadatos para usar nombre, grupo, unidad y frecuencia BCRP.
5. Mantenga activada la base de tipo de variable si tiene el Excel `BCRP_metadata_clasificacion_variables.xlsx`.
6. Ejecute el monitor.
7. Revise primero `Resumen`, `Régimen` y `Por frecuencia`.
8. Use `Explorar serie` para justificar casos puntuales.
9. Use `Auditoría` para revisar series dudosas o corregidas por override.
10. Exporte el resumen ejecutivo o la base completa.

Para ampliar una corrida existente, cambie `Modo de corrida` a `Agregar nuevas series`, pegue o cargue solo los códigos nuevos y ejecute el monitor. La app conserva las series ya procesadas en memoria y solo procesa los códigos que todavía no existen en la corrida actual.

Para refrescar una corrida existente, use `Actualizar datos nuevos`. Ese botón toma las variables ya cargadas, revisa si cada serie realmente puede tener un periodo nuevo según su frecuencia, consulta la API desde la última fecha conocida hasta la fecha final elegida y recalcula solo cuando encuentra observaciones nuevas o revisiones de datos. Si una serie ya fue revisada hoy sin cambios, la app la omite para no repetir llamadas innecesarias.

## Caché local para acelerar corridas

El monitor guarda en caché local los metadatos, la base de clasificación, las descargas de la API y el análisis por serie. Si vuelve a ejecutar el mismo universo con el mismo rango de fechas y tratamiento, la corrida reutiliza esos resultados y termina mucho más rápido.

En `Avanzado` puede usar `Limpiar caché local` para forzar una actualización completa desde cero. Use esa opción si cambió archivos base, reglas o quiere descartar resultados almacenados.

## Cambios frente a v2

- Lee el CSV completo de metadatos BCRP.
- Clasifica cada serie usando categoría, grupo, nombre, unidad, frecuencia y código.
- Aplica tratamientos distintos por clase económica.
- Separa `estado_actualizacion` de `estado` del régimen.
- Evita falsos positivos en tasas administradas, como la tasa de referencia BCRP.
- Guarda resultados en `st.session_state`, por lo que la exploración de una serie ya no borra la corrida completa.
- Usa `uirevision` y claves estables en Plotly para evitar reseteos innecesarios de gráficos.
- Presenta los resultados como tablero ejecutivo con tabs, filtros, KPIs y semáforo visual.

## Ajustes incorporados desde el master skill de 19 puntos

- Agrega campos ejecutivos `semaforo`, `regimen_tendencia`, `diagnostico`, `tratamiento_base`, `criterio_tratamiento` y `sentido_economico`.
- Calcula último dato original y último dato tratado por separado.
- Calcula comparación interanual, ventana anual móvil y acumulado del año cuando corresponde.
- Calcula tendencia reciente, desvío frente a tendencia y posición del último dato.
- Reporta fecha de inicio descargada, máximo histórico, mínimo histórico, fechas de extremos y percentiles.
- Trata variaciones porcentuales ya calculadas como niveles porcentuales para evitar dobles transformaciones.
- Trata tasas, spreads, precios financieros, commodities, valores, volúmenes, stocks, ratios y política monetaria con reglas diferenciadas.
- Exporta Excel con hojas `Regimen`, `Detalle_metricas`, `Series_originales`, `Series_analisis`, `Reglas`, `Catalogo_enriquecido`, `Metadatos_usados` y `Errores` cuando aplique.
- Limpia columnas y aplica color por semáforo en el Excel exportado.
- Corrige la lectura de periodos BCRP en API para formatos diarios (`13.Abr.26`), mensuales (`Abr.2026`) y trimestrales (`T1.25`).
- Ajusta la inferencia de frecuencia para que `Trimestral` no sea confundido con mensual por la letra `m`.
- Incluye la opción `Usar inicio histórico del metadato BCRP`, que descarga cada serie desde `Fecha de inicio` del metadato hasta la fecha final elegida en la app.
- Divide automáticamente hojas Excel grandes en partes para no superar el límite de filas de Excel cuando se exportan series históricas completas.
- Agrega una capa auditable de clasificación: la app genera `Auditoria_clasificacion` con confianza, motivo y alertas por serie.
- Agrega `overrides_clasificacion_bcrp.csv` para corregir manualmente solo los casos necesarios sin tocar código.

## Overrides de clasificación

El archivo `overrides_clasificacion_bcrp.csv` permite corregir casos puntuales. Tiene prioridad sobre la regla automática.

Formato:

```text
codigo;clase_serie;tratamiento_base;sentido_economico;comentario
PN01271PM;variacion_pct;nivel;sube_desfavorable;IPC var mensual ya calculada
```

La app mostrará cuántas series requieren revisión y exportará una hoja `Auditoria_clasificacion` para revisar solo los casos dudosos.

## Clases de serie usadas

- `valor_monetario`
- `volumen_fisico`
- `indice_nivel`
- `variacion_pct`
- `tasa_pct`
- `ratio_pct`
- `spread_pbs`
- `precio_financiero_diario`
- `commodity`
- `politica_monetaria_step`
- `balance_flujo`
- `stock_financiero`
- `precio_financiero`
- clases heredadas de compatibilidad usadas por catálogos anteriores.

## Recomendación de uso

Use el CSV de 264 variables como catálogo y el archivo completo de metadatos BCRP como soporte de clasificación. El catálogo puede tener solo la columna `codigo`; el monitor completará nombre, frecuencia y clasificación desde el metadato cuando lo encuentre.
