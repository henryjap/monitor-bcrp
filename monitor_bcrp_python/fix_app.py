import os
from pathlib import Path

# Usamos comillas simples triples para el exterior y evitamos triples comillas dentro
content_part1 = r\"\"\"from __future__ import annotations
from datetime import date, datetime
import hashlib
from html import escape
from io import StringIO
import json
import pickle
from pathlib import Path
import sqlite3
import traceback
import concurrent.futures
import os
import time

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from constants import *
from ui_logic import *
from ui_charts import *

from bcrp_monitor_core import (
    analyze_series,
    apply_classification_overrides,
    apply_variable_classification,
    audit_classification_catalog,
    catalog_from_codes,
    dataframe_to_excel_bytes,
    fetch_bcrp_series,
    fetch_bcrp_batch_series,
    find_metadata_file,
    load_classification_overrides,
    load_bcrp_metadata,
    load_variable_classification,
    merge_catalog_with_metadata,
    normalize_catalog_columns,
    period_to_date,
    SeriesMeta,
    series_meta_from_row,
)

st.set_page_config(
    page_title='MAXIMIXE DataBank',
    page_icon='📈',
    layout='wide',
    initial_sidebar_state='expanded'
)


def init_state() -> None:
    defaults = {
        'result_df': pd.DataFrame(),
        'series_data': {},
        'analysis_data': {},
        'errors_df': pd.DataFrame(),
        'catalog_enriched': pd.DataFrame(),
        'metadata_df': pd.DataFrame(),
        'classification_audit': pd.DataFrame(),
        'variable_classification_df': pd.DataFrame(),
        'bookmarks': {},
        'update_check_log': {},
        'pending_update_phase': '',
        'last_update_phase_summary': '',
        'last_run_asof': None,
        'last_metadata_file': '',
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def prune_loaded_series_data(max_items: int = 3) -> None:
    series_data = st.session_state.get('series_data', {})
    if not isinstance(series_data, dict) or len(series_data) <= max_items:
        return
    keep_codes = []
    selected = st.session_state.get('selected_series')
    if selected in series_data:
        keep_codes.append(selected)
    recent_codes = list(series_data.keys())[-max_items:]
    keep_codes.extend([c for c in recent_codes if c not in keep_codes])
    keep_codes = keep_codes[:max_items]
    st.session_state.series_data = {c: series_data[c] for c in keep_codes if c in series_data}
    analysis_data = st.session_state.get('analysis_data', {})
    if isinstance(analysis_data, dict):
        st.session_state.analysis_data = {c: analysis_data[c] for c in keep_codes if c in analysis_data}


@st.cache_data(show_spinner=False, persist='disk')
def cached_metadata(path: str, app_dir: str) -> pd.DataFrame:
    return load_bcrp_metadata(path, app_dir)


@st.cache_data(show_spinner=False, persist='disk')
def cached_variable_classification(path: str, app_dir: str) -> pd.DataFrame:
    return load_variable_classification(path, app_dir)


@st.cache_data(show_spinner=False, persist='disk')
def cached_fetch(code: str, start, end, freq_hint: str, fetch_version: str):
    _ = fetch_version
    return fetch_bcrp_series(code, start, end, freq_hint)


@st.cache_data(show_spinner=False, persist='disk', max_entries=20000)
def cached_analyze_series(df_raw: pd.DataFrame, meta_values: dict, api_meta: dict, asof_iso: str, analysis_version: str):
    meta = SeriesMeta(**meta_values)
    asof_date = pd.to_datetime(asof_iso).date()
    return analyze_series(df_raw, meta, api_meta, asof=asof_date)


def local_series_db_path() -> Path:
    if (RAW_CACHE_DIR / 'series_cache.db').exists():
        return (RAW_CACHE_DIR / 'series_cache.db').absolute()
    cwd_db = Path('data_cache/series_raw/series_cache.db')
    if cwd_db.exists():
        return cwd_db.absolute()
    return (RAW_CACHE_DIR / 'series_cache.db').absolute()


def init_db():
    db_path = local_series_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS series_data (codigo TEXT, fecha TEXT, valor REAL, PRIMARY KEY (codigo, fecha))')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_codigo ON series_data(codigo)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON series_data(fecha)')
        conn.execute('PRAGMA journal_mode=WAL')


def load_local_series_cache_bulk(codes: list[str]) -> dict[str, pd.DataFrame]:
    db_path = local_series_db_path()
    results = {c: pd.DataFrame(columns=['fecha', 'valor']) for c in codes}
    try:
        init_db()
        if not db_path.exists() or db_path.stat().st_size == 0:
            return results
        placeholders = ','.join(['?'] * len(codes))
        with sqlite3.connect(db_path) as conn:
            try:
                df_all = pd.read_sql_query(f'SELECT codigo, fecha, valor FROM series_data WHERE codigo IN ({placeholders})', conn, params=codes)
            except Exception:
                df_all = pd.DataFrame(columns=['codigo', 'fecha', 'valor'])
        if not df_all.empty:
            for code, group in df_all.groupby('codigo'):
                group['fecha'] = pd.to_datetime(group['fecha'], errors='coerce')
                group['valor'] = pd.to_numeric(group['valor'], errors='coerce')
                results[code] = group.dropna(subset=['fecha', 'valor']).sort_values('fecha').drop(columns=['codigo'])
    except Exception as e:
        print(f'Error bulk loading: {e}')
    return results


def load_local_series_cache(code: str) -> pd.DataFrame:
    db_path = local_series_db_path()
    try:
        init_db()
        with sqlite3.connect(db_path) as conn:
            try:
                df = pd.read_sql_query('SELECT fecha, valor FROM series_data WHERE codigo = ? ORDER BY fecha', conn, params=(code,))
            except Exception:
                df = pd.DataFrame(columns=['fecha', 'valor'])
            if df.empty: return pd.DataFrame(columns=['fecha', 'valor'])
            df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
            return df.dropna(subset=['fecha', 'valor']).drop_duplicates('fecha', keep='last')
    except Exception:
        return pd.DataFrame(columns=['fecha', 'valor'])


def save_local_series_cache_bulk(updates_dict: dict[str, pd.DataFrame]) -> None:
    if not updates_dict:
        return
    all_rows = []
    for code, df in updates_dict.items():
        if df is None or df.empty: continue
        clean = df[['fecha', 'valor']].copy()
        clean['fecha'] = pd.to_datetime(clean['fecha'], errors='coerce').dt.date.astype(str)
        clean['valor'] = pd.to_numeric(clean['valor'], errors='coerce')
        clean = clean.dropna(subset=['fecha', 'valor']).drop_duplicates('fecha', keep='last')
        if not clean.empty:
            clean.insert(0, 'codigo', code)
            all_rows.append(clean)
    if not all_rows: return
    bulk_df = pd.concat(all_rows, ignore_index=True)
    db_path = local_series_db_path()
    if not db_path.exists(): init_db()
    try:
        with sqlite3.connect(db_path) as conn:
            bulk_df.to_sql('temp_bulk', conn, if_exists='replace', index=False)
            conn.execute('INSERT OR REPLACE INTO series_data (codigo, fecha, valor) SELECT codigo, fecha, valor FROM temp_bulk')
            conn.execute('DROP TABLE temp_bulk')
    except Exception as e:
        print(f'Error bulk saving to db: {e}')

def save_local_series_cache(code: str, df: pd.DataFrame) -> None:
    if df is None or df.empty: return
    clean = df[['fecha', 'valor']].copy()
    clean['fecha'] = pd.to_datetime(clean['fecha'], errors='coerce').dt.date.astype(str)
    clean['valor'] = pd.to_numeric(clean['valor'], errors='coerce')
    clean = clean.dropna(subset=['fecha', 'valor']).drop_duplicates('fecha', keep='last')
    if clean.empty: return
    clean.insert(0, 'codigo', code)
    db_path = local_series_db_path()
    if not db_path.exists(): init_db()
    try:
        temp_table = f'temp_{code.replace(\".\", \"_\").replace(\"-\", \"_\")}'
        with sqlite3.connect(db_path) as conn:
            clean.to_sql(temp_table, conn, if_exists='replace', index=False)
            conn.execute(f'INSERT OR REPLACE INTO series_data (codigo, fecha, valor) SELECT codigo, fecha, valor FROM {temp_table}')
            conn.execute(f'DROP TABLE {temp_table}')
    except Exception as e:
        print(f'Error saving to db ({code}): {e}')
\"\"\"

path = Path('app.py')
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = 0
for i, line in enumerate(lines):
    if 'def clear_local_series_cache()' in line:
        start_idx = i
        break

if start_idx > 0:
    new_content = content_part1 + '\\n\\n' + ''.join(lines[start_idx:])
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('SUCCESS')
else:
    new_content = content_part1 + \"\\n\\ndef clear_local_series_cache() -> int: return 0\\n\"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('FORCED RECONSTRUCTION')
