from pathlib import Path

append_content = r'''
result_df = normalize_result_regime(st.session_state.result_df)
if not result_df.empty and not st.session_state.metadata_df.empty:
    result_df = recode_taxonomy_from_metadata(result_df, st.session_state.metadata_df)
st.session_state.result_df = result_df
series_data = st.session_state.series_data
errors_df = st.session_state.errors_df

if result_df.empty:
    if not errors_df.empty: st.warning('No se pudo procesar ninguna serie.')
    else: st.info('Configuracion lista.')
    if not errors_df.empty: st.dataframe(friendly_columns(errors_df), use_container_width=True, hide_index=True)
    st.stop()

if 'codigo' in result_df.columns:
    cd_mask = result_df['codigo'].str.startswith('CD', na=False)
    name_col = 'nombre_bcrp' if 'nombre_bcrp' in result_df.columns else 'nombre'
    disc_mask = result_df[name_col].str.contains(r'\(descontinuada\)', case=False, na=False) if name_col in result_df.columns else pd.Series(False, index=result_df.index)
    combined_hist_mask = cd_mask | disc_mask

manual_names = {
    'PN01689PM': 'Precio Techo - Maiz', 'PN01690PM': 'Precio Techo - Arroz',
    'PN01691PM': 'Precio Techo - Azucar', 'PN01692PM': 'Precio Techo - Leche Entera en Polvo',
    'PN01693PM': 'Precio Piso - Maiz', 'PN01694PM': 'Precio Piso - Arroz',
    'PN01695PM': 'Precio Piso - Azucar', 'PN01696PM': 'Precio Piso - Leche Entera en Polvo'
}
if 'codigo' in result_df.columns:
    for code, name in manual_names.items():
        mask = result_df['codigo'] == code
        if mask.any():
            result_df.loc[mask, 'nombre_bcrp'] = name
            result_df.loc[mask, 'categoria_bcrp'] = 'Cotizaciones internacionales'

working_df = result_df.copy()
if not show_legacy:
    if 'codigo' in working_df.columns: working_df = working_df[~combined_hist_mask]
    if 'grupo_bcrp' in working_df.columns: working_df = working_df[working_df['grupo_bcrp'] != 'Entre 1930 a 1980']

render_hero(working_df, st.session_state.last_run_asof or end_date, meta_file)

main_options = ['Tablero ejecutivo', 'Analisis de series']
if config_mode: main_options.extend(['Auditoria', 'Exportar'])

main_mode = st.radio('Modo principal', main_options, horizontal=True, label_visibility='collapsed')

if main_mode == 'Tablero ejecutivo':
    st.subheader('Resumen ejecutivo')
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    semaforo_series = working_df['semaforo'] if 'semaforo' in working_df.columns else pd.Series(dtype=str)
    con_dato = int(pd.to_datetime(working_df.get('ultima_fecha', pd.Series(dtype=object)), errors='coerce').notna().sum())
    with c1: render_kpi_card('Series procesadas', len(working_df), 'universo evaluado')
    with c2: render_kpi_card('Con dato', con_dato, 'series con ultimo dato', '#175CD3')
    with c3: render_kpi_card('Al alza', int(semaforo_series.eq('Al alza').sum()), 'tendencia', SEMAFORO_COLORS['Al alza'])
    with c4: render_kpi_card('A la baja', int(semaforo_series.eq('A la baja').sum()), 'tendencia', SEMAFORO_COLORS['A la baja'])
    with c5: render_kpi_card('Normal', int(semaforo_series.eq('Normal').sum()), 'tendencia', SEMAFORO_COLORS['Normal'])
    with c6:
        no_data_count = int(semaforo_series.eq('Sin datos').sum())
        days_series = pd.to_numeric(result_df.get('dias_desde_ultimo_dato', pd.Series(dtype=float)), errors='coerce')
        median_days = int(days_series.dropna().median()) if days_series.notna().any() else 0
        render_kpi_card('Sin datos', no_data_count, f'mediana {median_days} dias', SEMAFORO_COLORS['Sin datos'])

    st.divider()
    render_frequency_cards(result_df)
    st.divider()
    st.plotly_chart(semaforo_chart(result_df), use_container_width=True)
    
    st.divider()
    graph_left, graph_right = st.columns(2)
    heatmap = category_heatmap(working_df)
    ranking = alert_ranking_chart(working_df)
    with graph_left:
        if heatmap is not None: st.plotly_chart(heatmap, use_container_width=True)
    with graph_right:
        if ranking is not None: st.plotly_chart(ranking, use_container_width=True)

if main_mode == 'Analisis de series':
    st.subheader('Explorar serie')
    explore_df = filter_explore_series(working_df)
    if not explore_df.empty:
        series_options = explore_df['codigo'].tolist()
        series_labels = {row['codigo']: f"{row['codigo']} - {row.get('nombre_bcrp') or row['codigo']}" for _, row in explore_df.iterrows()}
        selected = st.selectbox('Seleccione una serie', series_options, format_func=lambda c: series_labels.get(c, c), key='selected_series')
        sel_row = working_df.loc[working_df['codigo'] == selected].iloc[0]
        df_sel = series_data.get(selected)
        if df_sel is not None and not df_sel.empty:
            render_series_snapshot(sel_row)
            st.plotly_chart(series_band_chart(df_sel, series_labels[selected]), use_container_width=True)
            st.plotly_chart(trend_deviation_chart(df_sel, series_labels[selected]), use_container_width=True)
            st.plotly_chart(historical_distribution_chart(df_sel, series_labels[selected]), use_container_width=True)

if main_mode == 'Auditoria':
    st.subheader('Auditoria metodologica')
    audit_df = st.session_state.classification_audit
    if not audit_df.empty: st.dataframe(friendly_columns(audit_df), use_container_width=True, hide_index=True)

if main_mode == 'Exportar':
    st.subheader('Exportar resultados')
    sheets = build_export_sheets(result_df, series_data, errors_df)
    xlsx_bytes = dataframe_to_excel_bytes(sheets)
    st.download_button('Exportar base completa (Excel)', data=xlsx_bytes, file_name='monitor_bcrp.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
'''
path = Path('app.py')
with open(path, 'a', encoding='utf-8') as f:
    f.write(append_content)
