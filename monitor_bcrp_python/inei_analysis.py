"""Análisis de series INEI — variaciones, tendencias, estadísticas"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def analyze_series(df: pd.DataFrame) -> dict:
    """Calcula métricas de análisis para una serie temporal.

    Parámetros
    ----------
    df : DataFrame con columnas ['fecha', 'valor'] ordenado por fecha.

    Retorna
    -------
    dict con métricas: var%, media, tendencia, percentil, etc.
    """
    if df.empty or len(df) < 2:
        return {"error": "Datos insuficientes"}

    df = df.sort_values("fecha").reset_index(drop=True)
    vals = df["valor"].values
    fechas = df["fecha"].values

    result = {}

    # Valor actual y anterior
    result["ultimo_valor"] = float(vals[-1])
    result["fecha_ultimo"] = str(pd.Timestamp(fechas[-1]).date())
    result["valor_anterior"] = float(vals[-2]) if len(vals) > 1 else np.nan
    result["fecha_anterior"] = str(pd.Timestamp(fechas[-2]).date()) if len(vals) > 1 else ""

    # Variación interanual (misma fecha - 1 año atrás)
    result["var_interanual_pct"] = _calc_var_interanual(df)

    # Variación mensual / período anterior
    result["var_periodo_pct"] = _calc_var_periodo(df)

    # Estadísticas descriptivas
    result["media"] = float(np.mean(vals))
    result["mediana"] = float(np.median(vals))
    result["minimo"] = float(np.min(vals))
    result["maximo"] = float(np.max(vals))
    result["desviacion"] = float(np.std(vals, ddof=1))
    result["coef_variacion"] = float(np.std(vals, ddof=1) / np.mean(vals)) if np.mean(vals) != 0 else np.nan

    # Percentil histórico del último valor
    result["percentil_historico"] = float(scipy_stats.percentileofscore(vals, vals[-1]) / 100)

    # Tendencia (pendiente de regresión lineal)
    x = np.arange(len(vals))
    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, vals)
    result["tendencia_pendiente"] = float(slope)
    result["tendencia_r2"] = float(r_value ** 2)
    result["tendencia_pendiente_pct"] = float(slope / np.mean(vals) * 100) if np.mean(vals) != 0 else np.nan

    # Promedio móvil simple (3 y 12 períodos)
    if len(vals) >= 3:
        ma3 = pd.Series(vals).rolling(3).mean()
        result["ma3_ultimo"] = float(ma3.iloc[-1]) if not np.isnan(ma3.iloc[-1]) else np.nan
        result["ma3_penultimo"] = float(ma3.iloc[-2]) if len(ma3) >= 2 and not np.isnan(ma3.iloc[-2]) else np.nan
    if len(vals) >= 12:
        ma12 = pd.Series(vals).rolling(12).mean()
        result["ma12_ultimo"] = float(ma12.iloc[-1]) if not np.isnan(ma12.iloc[-1]) else np.nan

    # Posición vs tendencia (último valor vs regresión lineal)
    trend_line = slope * x + intercept
    result["posicion_vs_tendencia"] = float(vals[-1] - trend_line[-1])
    result["posicion_vs_tendencia_pct"] = float((vals[-1] - trend_line[-1]) / trend_line[-1] * 100) if trend_line[-1] != 0 else np.nan

    # Aceleración (diferencia de pendientes)
    if len(vals) >= 6:
        x1, x2 = np.arange(3), np.arange(3, 6)
        s1, _, _, _, _ = scipy_stats.linregress(x1, vals[:3])
        s2, _, _, _, _ = scipy_stats.linregress(x2, vals[3:6])
        result["aceleracion"] = float(s2 - s1)
    elif len(vals) >= 4:
        half = len(vals) // 2
        x1, x2 = np.arange(half), np.arange(half, len(vals))
        s1, _, _, _, _ = scipy_stats.linregress(x1, vals[:half])
        s2, _, _, _, _ = scipy_stats.linregress(x2, vals[half:])
        result["aceleracion"] = float(s2 - s1)

    return result


def _calc_var_interanual(df: pd.DataFrame) -> float:
    """Variación porcentual vs mismo período del año anterior."""
    if len(df) < 2:
        return np.nan
    df = df.sort_values("fecha").reset_index(drop=True)
    # Para datos mensuales: buscar fecha - 12 meses
    ult_fecha = df["fecha"].iloc[-1]
    anio_ant = ult_fecha - pd.DateOffset(years=1)
    mask = df["fecha"] == anio_ant
    if mask.any():
        idx = mask.idxmax()
        v_act = df["valor"].iloc[-1]
        v_ant = df["valor"].iloc[idx]
        if v_ant != 0 and not np.isnan(v_ant):
            return float((v_act - v_ant) / v_ant * 100)
    # Fallback: buscar fecha exacta
    yr_ant = ult_fecha.year - 1
    mask_yr = df["fecha"].dt.year == yr_ant
    if mask_yr.any():
        idx = df[mask_yr].index[-1]
        v_act = df["valor"].iloc[-1]
        v_ant = df["valor"].iloc[idx]
        if v_ant != 0 and not np.isnan(v_ant):
            return float((v_act - v_ant) / v_ant * 100)
    return np.nan


def _calc_var_periodo(df: pd.DataFrame) -> float:
    """Variación porcentual vs período anterior."""
    if len(df) < 2:
        return np.nan
    v_act = df["valor"].iloc[-1]
    v_ant = df["valor"].iloc[-2]
    if v_ant != 0 and not np.isnan(v_ant):
        return float((v_act - v_ant) / v_ant * 100)
    return np.nan


def annual_average_metrics(df: pd.DataFrame) -> dict:
    """Promedio anual y acumulado año corrido."""
    if df.empty:
        return {}
    df = df.copy()
    df["year"] = df["fecha"].dt.year
    ult_yr = df["year"].max()
    yr_data = df[df["year"] == ult_yr]
    result = {}
    if not yr_data.empty:
        result["promedio_anual"] = float(yr_data["valor"].mean())
        result["acumulado_anual"] = float(yr_data["valor"].sum())
        result["minimo_anual"] = float(yr_data["valor"].min())
        result["maximo_anual"] = float(yr_data["valor"].max())
    # Año anterior
    ant_yr = ult_yr - 1
    ant_data = df[df["year"] == ant_yr]
    if not ant_data.empty:
        result["promedio_anual_anterior"] = float(ant_data["valor"].mean())
        result["acumulado_anual_anterior"] = float(ant_data["valor"].sum())
        prom_act = result.get("promedio_anual", np.nan)
        prom_ant = result["promedio_anual_anterior"]
        if prom_ant != 0 and not np.isnan(prom_ant) and not np.isnan(prom_act):
            result["var_promedio_anual_pct"] = float((prom_act - prom_ant) / prom_ant * 100)
    return result
