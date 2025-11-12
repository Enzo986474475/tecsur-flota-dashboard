# streamlit_app/lib/data.py
from __future__ import annotations
from datetime import date
from pathlib import Path
import re
import unicodedata as ud
import pandas as pd
import streamlit as st

def _canon(s: str) -> str:
    s = str(s).strip().lower()
    s = ''.join(ch for ch in ud.normalize('NFD', s) if ud.category(ch) != 'Mn')  # sin acentos
    s = s.replace('(', ' ').replace(')', ' ').replace('/', ' ').replace('-', ' ')
    s = re.sub(r'[^a-z0-9\s]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def _find_col(df: pd.DataFrame, keys: list[str]) -> str | None:
    cols = [(c, _canon(c)) for c in df.columns]
    for c, cc in cols:
        for k in keys:
            if k in cc:
                return c
    return None

@st.cache_data(show_spinner=False)
def load_excel(path: str | Path, sheet: str | int | None = 0) -> pd.DataFrame:
    # base = .../streamlit_app
    base = Path(__file__).resolve().parents[1]
    p = Path(path)
    # Si la ruta no es absoluta, hazla relativa a streamlit_app
    if not p.is_absolute():
        p = base / p

    # (opcional) muestra la ruta que está usando para depurar
    # st.caption(f"Buscando archivo en: {p}")

    if not p.exists():
        return pd.DataFrame()

    try:
        df = pd.read_excel(p, sheet_name=sheet, engine="openpyxl")
        if isinstance(df, dict):
            df = next(iter(df.values()))
        df.columns = [str(col).strip() for col in df.columns]
        return df
    except Exception as e:
        st.warning(f"No se pudo leer {p.name}: {e}")
        return pd.DataFrame()



def kpis_home(recorridos_df: pd.DataFrame, soat_df: pd.DataFrame,
              fecha_ini: date, fecha_fin: date, soat_warn_days: int = 30) -> dict:
    # --- KM del rango ---
    km_mes = 0.0
    if not recorridos_df.empty:
        r = recorridos_df.copy()
        r.columns = [str(c).strip() for c in r.columns]
        f_col  = _find_col(r, ["fecha", "date"])
        km_col = _find_col(r, ["km", "kilometraje", "distancia km", "distancia"])
        if f_col and km_col:
            r[f_col] = pd.to_datetime(r[f_col], errors="coerce").dt.date
            mask = (r[f_col] >= fecha_ini) & (r[f_col] <= fecha_fin)
            km_mes = float(r.loc[mask, km_col].fillna(0).sum())

    # --- SOAT por vencer ≤ X días ---
    soat_alertas = 0
    if not soat_df.empty:
        s = soat_df.copy()
        s.columns = [str(c).strip() for c in s.columns]
        fin_col = _find_col(s, ["fecha fin", "vence", "vencimiento"])
        if fin_col:
            s[fin_col] = pd.to_datetime(s[fin_col], errors="coerce").dt.date
            hoy = date.today()
            s["dias_restantes"] = (s[fin_col] - hoy).apply(lambda d: d.days if pd.notna(d) else 9999)
            soat_alertas = int((s["dias_restantes"] <= soat_warn_days).sum())

    return dict(
        disp_pct=None,
        km_mes=km_mes,
        soat_alertas=soat_alertas,
        km_por_kwh=None
    )
