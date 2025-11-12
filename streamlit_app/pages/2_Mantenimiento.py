# streamlit_app/pages/2_Mantenimiento.py
from __future__ import annotations
from lib.io import load

from datetime import date
from pathlib import Path
import calendar
import re

import pandas as pd
import numpy as np
import streamlit as st


# ============================
# Configuración de página (consistente con el resto)
# ============================
st.set_page_config(
    page_title="Tecsur · Flota EV — Mantenimiento",
    page_icon="🛠️",
    layout="wide",
)

# (Opcional) Integración con utilidades existentes
try:
    from lib.config import load_settings
    from lib.sync import sync_from_settings
    settings = load_settings()
    sync_from_settings(settings)
except Exception:
    pass

APP_DIR = Path(__file__).resolve().parents[1]
ASSETS  = APP_DIR / "assets"
LOGO    = ASSETS / "logo_tecsur.png"

# ============================
# Header unificado
# ============================
c1, c2, c3 = st.columns([1,5,2])
with c1:
    if LOGO.exists():
        st.image(str(LOGO), use_container_width=True)
    else:
        st.markdown("**TECSUR**")
with c2:
    st.markdown("### Tecsur · Flota EV")
    st.markdown("## **Mantenimiento**")
with c3:
    hoy = date.today().strftime("%d/%m/%Y")
    st.caption(f"Última actualización: **{hoy}**")

st.divider()

# ============================
# Rutas de origen
# ============================
BASE_DIR = Path(r"C:\Users\Enzo Morote\TECSUR S.A\Gestión Flota EV - Enzo - Documentos")
PATH_MANT  = BASE_DIR / "Mantenimientos.xlsx"
PATH_DISP  = BASE_DIR / "Disponibilidad Mecánica.xlsx"   # reservado para futuros cuadros
PATH_FLOTA = BASE_DIR / "Control-de-Flota-Vehicular-Tecsur 12.xlsx"

import os

# Fuentes desde secretos (si no hay secreto, cae a la ruta local)
FLOTA_SRC = load(os.getenv("URL_FLOTA", str(PATH_FLOTA)))
MANT_SRC  = load(os.getenv("URL_MANT",  str(PATH_MANT)))
DISP_SRC  = load(os.getenv("URL_DISP",  str(PATH_DISP)))  # reservado para futuros cuadros

# ============================
# Helpers
# ============================
@st.cache_data(show_spinner=False)
def _read_flota(path: Path) -> pd.DataFrame:
    """Lee Flota con encabezado en fila 8 y datos desde col C. Devuelve columnas clave."""
   
    df = _df_or_path_to_df(path, sheet_name="Flota", header=7)
    cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
    df = df.rename(columns=cols)

    placa_col        = next((c for c in df.columns if c.lower().startswith("placa") and "vehiculo" in c.lower()), "Placa Vehiculo")
    familia_col      = next((c for c in df.columns if c.lower().startswith("familia")), "Familia")
    combustible_col  = next((c for c in df.columns if c.lower().startswith("combustible")), "Combustible")
    motorizacion_col = next((c for c in df.columns if c.lower().startswith("motoriz")), "Motorización")

    df = df[[placa_col, familia_col, combustible_col, motorizacion_col]].copy()
    df.columns = ["Placa Vehiculo", "Familia", "Combustible", "Motorización"]

    df["Placa Vehiculo"] = df["Placa Vehiculo"].astype(str).str.upper().str.replace(" ", "", regex=False)
    df["Familia"]        = df["Familia"].astype(str).str.strip()
    df["Combustible"]    = df["Combustible"].astype(str).str.strip()
    df["Motorización"]   = df["Motorización"].astype(str).str.strip()

    df = df.dropna(subset=["Placa Vehiculo"]).drop_duplicates(subset=["Placa Vehiculo"])
    return df

@st.cache_data(show_spinner=False)
def _read_mantenimientos(path: Path) -> pd.DataFrame:

    df = _df_or_path_to_df(path, sheet_name=0)
    cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
    df = df.rename(columns=cols)

    placa_col    = next((c for c in df.columns if c.lower().startswith("placa")), "Placa Vehiculo")
    tipo_col     = next((c for c in df.columns if "tipo" in c.lower() and "ot" in c.lower()), "Tipo de OT")
    horas_col    = next((c for c in df.columns if c.lower().startswith("horas") and "taller" in c.lower()), "Horas Taller")
    anio_col     = next((c for c in df.columns if c.lower() in ("año","anio","year")), "Año")
    mes_col      = next((c for c in df.columns if c.lower() == "mes"), "Mes")
    # NUEVO: detectar "Ingresos al Taller"
    ingresos_col = next(
        (c for c in df.columns if ("ingres" in c.lower()) and ("taller" in c.lower())),
        "Ingresos al Taller"
    )

    # Selección de columnas (incluye Ingresos)
    want_cols = [placa_col, tipo_col, horas_col, anio_col, mes_col]
    if ingresos_col in df.columns:
        want_cols.append(ingresos_col)
    df = df[want_cols].copy()

    # Renombrado estándar
    new_cols = ["Placa Vehiculo", "Tipo de OT", "Horas Taller", "Año", "Mes"]
    if ingresos_col in df.columns:
        new_cols.append("Ingresos al Taller")
    df.columns = new_cols

    # Normalizaciones
    df["Placa Vehiculo"] = df["Placa Vehiculo"].astype(str).str.upper().str.replace(" ", "", regex=False)

    def _norm_tipo(x: str) -> str:
        s = str(x).strip().lower()
        if not s:
            return ""
        if any(k in s for k in ["correctiv","mc"]): return "MC"
        if any(k in s for k in ["prevent","mp"]):   return "MP"
        if "garant" in s:                            return "Garantia"
        if any(k in s for k in ["siniest","accident","choque","colision","colisión"]): return "Siniestro"
        if any(k in s for k in ["implem","implementación","implementacion"]):          return "Implementacion"
        return s.title()

    df["Tipo de OT"]   = df["Tipo de OT"].map(_norm_tipo)
    df["Horas Taller"] = pd.to_numeric(df["Horas Taller"], errors="coerce").fillna(0.0)
    df["Año"]          = pd.to_numeric(df["Año"], errors="coerce").astype("Int64")

    def _to_mes_num(v) -> int | None:
        try:
            n = int(v)
            return n if 1 <= n <= 12 else None
        except Exception:
            s = str(v).strip().lower()
            mapa = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
                    "noviembre":11,"diciembre":12,
                    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
            return mapa.get(s)

    df["Mes"] = df["Mes"].map(_to_mes_num).astype("Int64")

    # NUEVO: normalizar "Ingresos al Taller" a 0/1 (0 = abierto, 1 = cerrado)
    if "Ingresos al Taller" in df.columns:
        def _norm_ing(v):
            s = str(v).strip().lower()
            if s in {"1", "true", "sí", "si", "cerrado", "closed", "1.0"}: return 1
            if s in {"0", "false", "no", "abierto", "open", "en proceso", "en proceso.", ""}: return 0
            try:
                n = float(s)
                return 1 if n >= 1 else 0
            except Exception:
                return 0
        df["Ingresos al Taller"] = df["Ingresos al Taller"].map(_norm_ing).astype("Int64")
    else:
        # Si no existe, asumimos todo cerrado (compatibilidad hacia atrás)
        df["Ingresos al Taller"] = pd.Series(1, index=df.index, dtype="Int64")

    df = df.dropna(subset=["Placa Vehiculo", "Año", "Mes"]).copy()
    return df

@st.cache_data(show_spinner=False)
def _teoricas_horas(anio: int, mes: int) -> float:
    dias = calendar.monthrange(int(anio), int(mes))[1]
    return 24.0 * dias

def _df_or_path_to_df(x, **kwargs):
    return x if isinstance(x, pd.DataFrame) else pd.read_excel(x, **kwargs)

# ============================
# Tabs principales
# ============================
TAB_RESUMEN, TAB_DETALLE, TAB_EXPORTAR = st.tabs(["Resumen", "Detalle", "Exportar"])

# ============================
# RESUMEN
# ============================
with TAB_RESUMEN:
    st.markdown("### Flota Tecsur")
    st.caption("Disponibilidad mecánica por **Familia** con desglose por placas. Filtros: **Año, Mes, Combustible, Motorización**. Solo se contabilizan OTs **cerradas** (Ingresos al Taller = 1).")

    # ---- Filtros superiores (Año, Mes, Combustible, Motorización, Toggle Siniestros) ----
    # === Acciones (sidebar) ===
    with st.sidebar:
        st.subheader("Acciones")
        if st.button("🔄 Actualizar datos", use_container_width=True):
            sync_from_settings(settings)   # si usas OneDrive/SharePoint
            st.cache_data.clear()          # limpia cache de DataFrames
            st.rerun()                     # vuelve a ejecutar la página

    #df_mant_all  = _read_mantenimientos(PATH_MANT)
    #df_flota_all = _read_flota(PATH_FLOTA)

    # ahora:
    df_mant_all  = _read_mantenimientos(MANT_SRC)
    df_flota_all = _read_flota(FLOTA_SRC)

    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([1,1,2,2,2])
    with col_f1:
        anios = sorted([int(x) for x in df_mant_all["Año"].dropna().unique().tolist()])
        anio_sel = st.selectbox("Año", options=anios, index=len(anios)-1 if anios else 0)
    with col_f2:
        meses_disp = sorted([int(x) for x in df_mant_all.loc[df_mant_all["Año"]==anio_sel, "Mes"].dropna().unique().tolist()])
        mes_sel = st.selectbox("Mes", options=meses_disp or list(range(1,13)), index=(len(meses_disp)-1) if meses_disp else (date.today().month-1))
    with col_f3:
        combustibles = ["Todos"] + sorted([c for c in df_flota_all["Combustible"].dropna().unique().tolist() if c])
        combustible_sel = st.selectbox("Combustible", options=combustibles, index=0)
    with col_f4:
        motorizaciones = ["Todos"] + sorted([m for m in df_flota_all["Motorización"].dropna().unique().tolist() if m])
        motorizacion_sel = st.selectbox("Motorización", options=motorizaciones, index=0)
    with col_f5:
        incluir_siniestros = st.toggle("Incluir Siniestros", value=False, help="Por defecto no se consideran por ser causas operativas.")

    # ---- Cálculo de Disponibilidad por placa ----
    df_mant = df_mant_all[(df_mant_all["Año"] == anio_sel) & (df_mant_all["Mes"] == mes_sel)].copy()
    # NUEVO: considerar solo OTs cerradas
    df_mant = df_mant[df_mant["Ingresos al Taller"] == 1]

    pvt = df_mant.pivot_table(index=["Placa Vehiculo"], columns="Tipo de OT",
                              values="Horas Taller", aggfunc="sum", fill_value=0.0)
    pvt = pvt.rename_axis(None, axis=1).reset_index()
    for col in ["MC","MP","Garantia","Siniestro"]:
        if col not in pvt.columns:
            pvt[col] = 0.0

    pvt["Horas Taller Total"] = pvt["MC"] + pvt["MP"] + pvt["Garantia"] + (pvt["Siniestro"] if incluir_siniestros else 0.0)

    df_flota = df_flota_all.copy()
    if combustible_sel != "Todos":
        df_flota = df_flota[df_flota["Combustible"].astype(str) == combustible_sel]
    if motorizacion_sel != "Todos":
        df_flota = df_flota[df_flota["Motorización"].astype(str) == motorizacion_sel]

    universo = df_flota[["Placa Vehiculo","Familia","Combustible","Motorización"]].dropna(subset=["Placa Vehiculo"]).drop_duplicates("Placa Vehiculo")

    placas = universo.merge(pvt, on="Placa Vehiculo", how="left")
    placas[["MC","MP","Garantia","Siniestro","Horas Taller Total"]] = placas[["MC","MP","Garantia","Siniestro","Horas Taller Total"]].fillna(0.0)

    H_teo = _teoricas_horas(anio_sel, mes_sel)
    placas["Horas Disponibles (reales)"] = (H_teo - placas["Horas Taller Total"]).clip(lower=0.0)
    placas["Disponibilidad (%)"] = (placas["Horas Disponibles (reales)"] / H_teo * 100.0).round(2)

    # ---- Agregación por familia + Totales ----
    fam_agg = (
        placas.groupby("Familia", dropna=False)
              .agg(**{
                  "Cantidad de placas": ("Placa Vehiculo", "nunique"),
                  "Disponibilidad (%)": ("Disponibilidad (%)", "mean"),
              })
              .reset_index()
              .sort_values("Familia", na_position="last")
    )
    fam_agg["Disponibilidad (%)"] = fam_agg["Disponibilidad (%)"].round(2)

    total_placas = int(placas["Placa Vehiculo"].nunique())
    disp_global = (placas["Horas Disponibles (reales)"].sum() / (H_teo * total_placas) * 100.0) if total_placas else 0.0

    total_row = pd.DataFrame({
        "Familia": ["Total"],
        "Cantidad de placas": [total_placas],
        "Disponibilidad (%)": [round(disp_global, 2)],
    })
    fam_agg_total = pd.concat([fam_agg, total_row], ignore_index=True)

    # --- Colores por rangos para Disponibilidad (%) (tabla principal) ---
    def _disp_bg(v):
        try:
            x = float(v)
        except Exception:
            return ""
        if x > 98:
            return "background-color:#2ecc71; color:white"  # verde fuerte
        elif x >= 95:
            return "background-color:#a3e4b8"               # verde suave
        elif x >= 90:
            return "background-color:#f9e79f"               # ámbar
        else:
            return "background-color:#f5b7b1"               # rojo tenue

    sty_fam = fam_agg_total.style.map(_disp_bg, subset=["Disponibilidad (%)"]).format({"Disponibilidad (%)": "{:.2f}"})
    st.dataframe(sty_fam, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Desglose por familia (click en + para ver placas)")

    # Estilos: rojo para horas en taller + colores para Disponibilidad (%)
    def _styler_desglose(df: pd.DataFrame) -> pd.io.formats.style.Styler:
        def _red(v):
            try:
                return "color: red" if float(v) > 0 else ""
            except Exception:
                return ""
        def _bg(v):
            try:
                x = float(v)
            except Exception:
                return ""
            if x > 98:
                return "background-color:#2ecc71; color:white"
            elif x >= 95:
                return "background-color:#a3e4b8"
            elif x >= 90:
                return "background-color:#f9e79f"
            else:
                return "background-color:#f5b7b1"

        cols_red = [c for c in ["MC","MP","Garantia","Siniestro","Horas Taller Total"] if c in df.columns]
        sty = df.style.map(_bg, subset=["Disponibilidad (%)"])
        for c in cols_red:
            sty = sty.map(_red, subset=[c])
        return sty.format(precision=2)

    for _, row in fam_agg.iterrows():
        fam = row["Familia"]
        with st.expander(f"{fam} — {int(row['Cantidad de placas'])} placas | Disp. prom.: {row['Disponibilidad (%)']:.2f}%"):
            sub = placas.loc[placas["Familia"] == fam,
                             ["Placa Vehiculo", "Disponibilidad (%)", "MC", "MP", "Garantia", "Siniestro", "Horas Taller Total"]]\
                        .sort_values("Placa Vehiculo")
            st.dataframe(_styler_desglose(sub), use_container_width=True, hide_index=True)

    ##############
    # ============================
    # Gráficos de Mantenimiento (2x2)
    # ============================
    st.markdown("---")
    st.markdown("### Gráficos de Mantenimiento")

    # --- Filtro de Familia (usa el universo ya calculado arriba) ---
    familias_opts = ["Todas"] + sorted(universo["Familia"].dropna().astype(str).unique().tolist())
    familia_sel = st.selectbox(
        "Familia",
        options=familias_opts,
        index=0,
        help="Filtra los gráficos por familia (aplica a los 4 gráficos)"
    )

    MESES_ABBR = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    TIPOS = ["MC", "MP", "Garantia", "Siniestro"]  # orden consistente

    @st.cache_data(show_spinner=False)
    def _aggs_para_graficos(df_mant_all: pd.DataFrame,
                            df_flota_all: pd.DataFrame,
                            anio: int,
                            mes_hasta: int,
                            familia: str | None,
                            incluir_sin: bool):
        # Universo de placas (acota por familia si corresponde)
        universo_local = df_flota_all[["Placa Vehiculo","Familia"]].dropna(subset=["Placa Vehiculo"]).drop_duplicates()
        if familia and familia != "Todas":
            universo_local = universo_local[universo_local["Familia"].astype(str) == str(familia)]

        placas_set = set(universo_local["Placa Vehiculo"].tolist())
        idx = pd.Index(range(1, mes_hasta + 1), name="Mes")

        if not placas_set:
            horas_mes_tipo = pd.DataFrame(0.0, index=idx, columns=TIPOS)
            cnt_mes_tipo   = pd.DataFrame(0,   index=idx, columns=TIPOS)
            disp_mensual   = pd.DataFrame({"Mes": idx, "DispPct": np.nan})
            pareto_total   = pd.Series(0.0, index=TIPOS, name="Horas")
            return horas_mes_tipo, cnt_mes_tipo, disp_mensual, pareto_total, universo_local

        # Filtra mantenimientos por año, mes y universo de placas
        df_y = df_mant_all[
            (df_mant_all["Año"] == anio) &
            (df_mant_all["Mes"].between(1, mes_hasta)) &
            (df_mant_all["Placa Vehiculo"].isin(placas_set)) &
            (df_mant_all["Ingresos al Taller"] == 1)  # NUEVO: solo OTs cerradas
        ].copy()

        # Horas por mes y tipo
        horas_mes_tipo = (df_y
            .pivot_table(index="Mes", columns="Tipo de OT", values="Horas Taller", aggfunc="sum", fill_value=0.0)
            .reindex(index=idx, fill_value=0.0)
            .reindex(columns=TIPOS, fill_value=0.0)
            .astype(float)
        )

        # Conteo de intervenciones por mes y tipo
        cnt_mes_tipo = (df_y
            .groupby(["Mes","Tipo de OT"]).size().unstack(fill_value=0)
            .reindex(index=idx, fill_value=0)
            .reindex(columns=TIPOS, fill_value=0)
            .astype(int)
        )

        # Disponibilidad mensual (%)
        if incluir_sin:
            horas_tot = horas_mes_tipo[["MC","MP","Garantia","Siniestro"]].sum(axis=1)
        else:
            horas_tot = horas_mes_tipo[["MC","MP","Garantia"]].sum(axis=1)

        n_placas = max(1, universo_local["Placa Vehiculo"].nunique())
        disp_vals = []
        for m in idx:
            h_teo = _teoricas_horas(anio, int(m)) * n_placas
            pct   = 100.0 * (1.0 - (horas_tot.loc[m] / h_teo if h_teo > 0 else 0.0))
            disp_vals.append(max(0.0, min(100.0, pct)))
        disp_mensual = pd.DataFrame({"Mes": idx, "DispPct": disp_vals})

        # Pareto total de horas por tipo (ordenado desc)
        if incluir_sin:
            orden = ["MC","Siniestro","MP","Garantia"]
        else:
            orden = ["MC","MP","Garantia"]
        pareto_total = horas_mes_tipo.sum(axis=0).reindex(orden, fill_value=0.0).astype(float)

        return horas_mes_tipo, cnt_mes_tipo, disp_mensual, pareto_total, universo_local

    horas_mes_tipo, cnt_mes_tipo, disp_mensual, pareto_total, _uni_local = _aggs_para_graficos(
        df_mant_all, df_flota_all, anio_sel, int(mes_sel), familia_sel, incluir_siniestros
    )

    import matplotlib.pyplot as plt

    # Paleta de colores EXACTA
    COLORS = {
        "MC": "#1f77b4",        # azul
        "MP": "#ff7f0e",        # naranja
        "Garantia": "#2ca02c",  # verde
        "Siniestro": "#d62728", # rojo
    }

    # ---------- FIG 1: Disponibilidad mensual ----------
    fig1, ax1 = plt.subplots(figsize=(6.0, 3.6))
    ax1.plot(disp_mensual["Mes"], disp_mensual["DispPct"], marker="o", linewidth=2.5, color=COLORS["MC"])
    ax1.set_ylim(90, 100)
    ax1.set_xlim(1, int(mes_sel))
    ax1.set_xticks(range(1, int(mes_sel)+1))
    ax1.set_xticklabels([MESES_ABBR[i-1] for i in range(1, int(mes_sel)+1)])
    ax1.set_ylabel("% Disp.")
    ax1.set_title("Disponibilidad mensual (%)")

    # Bandas de fondo
    ax1.axhspan(90, 95, facecolor="#f5b7b1", alpha=0.6, zorder=0)
    ax1.axhspan(95, 98, facecolor="#f9e79f", alpha=0.5, zorder=0)
    ax1.axhspan(98, 100, facecolor="#a3e4b8", alpha=0.4, zorder=0)

    # ---------- FIG 2: Horas en taller por tipo ----------
    fig2, ax2 = plt.subplots(figsize=(6.0, 3.6))
    x = np.arange(1, int(mes_sel)+1)
    bottom = np.zeros_like(x, dtype=float)
    tipos_horas = ["MC","MP","Garantia"] + (["Siniestro"] if incluir_siniestros else [])
    for t in tipos_horas:
        vals = horas_mes_tipo.loc[range(1, int(mes_sel)+1), t].to_numpy()
        ax2.bar(x, vals, bottom=bottom, label=f"{'GAR' if t=='Garantia' else t[:2].upper()}(hrs)", color=COLORS[t])
        bottom += vals
    ax2.set_xticks(x)
    ax2.set_xticklabels([MESES_ABBR[i-1] for i in x])
    ax2.set_ylabel("Horas")
    ax2.set_title("Horas en taller por tipo")
    ax2.legend()

    # ---------- FIG 3: Cantidad de intervenciones ----------
    fig3, ax3 = plt.subplots(figsize=(6.0, 3.6))
    x = np.arange(1, int(mes_sel)+1)
    bottom = np.zeros_like(x, dtype=float)
    for t in tipos_horas:
        vals = cnt_mes_tipo.loc[range(1, int(mes_sel)+1), t].to_numpy()
        ax3.bar(x, vals, bottom=bottom, label=("GAR" if t=="Garantia" else t[:2]), color=COLORS[t])
        bottom += vals
    ax3.set_xticks(x)
    ax3.set_xticklabels([MESES_ABBR[i-1] for i in x])
    ax3.set_ylabel("Intervenciones")
    ax3.set_title("Cantidad de intervenciones por tipo")
    ax3.legend()

    # ---------- FIG 4: Pareto de horas en taller ----------
    fig4, ax4 = plt.subplots(figsize=(6.0, 3.6))
    serie = pareto_total.sort_values(ascending=False)
    tipos_ord = serie.index.tolist()
    ax4.bar(range(len(serie)), serie.values, color=[COLORS[t] for t in tipos_ord])
    ax4.set_xticks(range(len(serie)))
    ax4.set_xticklabels([f"{'GAR' if t=='Garantia' else t[:3].upper()}(hrs)" for t in tipos_ord])
    ax4.set_title("Pareto de horas en taller")

    # Línea acumulada %
    ax4_2 = ax4.twinx()
    cum = serie.cumsum() / max(1e-9, serie.sum()) * 100.0
    ax4_2.plot(range(len(serie)), cum.values, marker="o", linewidth=2.0, color="#ff7f0e")
    ax4_2.set_ylim(0, 110)
    for i, pct in enumerate(cum.values):
        ax4_2.text(i, pct + 3, f"{pct:.0f}%", ha="center", va="bottom", color="#ff7f0e", fontweight="bold")
    ax4_2.grid(False)

    # ---------- DISTRIBUCIÓN 2×2 ----------
    c1, c2 = st.columns(2)
    with c1:
        st.pyplot(fig1, use_container_width=True)
    with c2:
        st.pyplot(fig2, use_container_width=True)

    c3, c4 = st.columns(2)
    with c3:
        st.pyplot(fig3, use_container_width=True)
    with c4:
        st.pyplot(fig4, use_container_width=True)

    ###########
    # ============================
    # MTBF / MTTR — Tabla + Gráficos (con Motorización, Disponibilidad(%) y TOTAL)
    # ============================
    st.markdown("---")
    st.markdown("### MTBF / MTTR")
    st.caption("En todos los cálculos se consideran únicamente OTs **cerradas** (Ingresos al Taller = 1).")

    # Reutilizamos data ya cargada arriba
    #df_mant_all  = _read_mantenimientos(PATH_MANT)
    #df_flota_all = _read_flota(PATH_FLOTA)

    df_mant_all  = _read_mantenimientos(MANT_SRC)
    df_flota_all = _read_flota(FLOTA_SRC)

    # --- Filtros (rápidos) ---
    col_a, col_b, col_c, col_c2, col_d, col_e = st.columns([1,1,2,2,2,2])
    with col_a:
        anios_m = sorted([int(x) for x in df_mant_all["Año"].dropna().unique().tolist()])
        anio_m  = st.selectbox("Año", options=anios_m, index=len(anios_m)-1 if anios_m else 0, key="mtbf_anio2")
    with col_b:
        meses_m = sorted([int(x) for x in df_mant_all.loc[df_mant_all["Año"]==anio_m, "Mes"].dropna().unique().tolist()])
        mes_hasta = st.selectbox(
            "Hasta mes",
            options=meses_m or list(range(1,13)),
            index=(len(meses_m)-1) if meses_m else (date.today().month-1),
            key="mtbf_mes2"
        )
    with col_c:
        familias_m = ["Todas"] + sorted(df_flota_all["Familia"].dropna().astype(str).unique().tolist())
        fam_m = st.selectbox("Familia", familias_m, index=0, key="mtbf_fam2",
                            help="Aplica a la tabla y a ambos gráficos")
    with col_c2:
        mot_opts = ["Todos"] + sorted(df_flota_all["Motorización"].dropna().astype(str).unique().tolist())
        mot_f = st.selectbox("Motorización", mot_opts, index=0, key="mtbf_mot2")
    with col_d:
        nivel = st.radio("Nivel de tabla", ["Familia", "Placa"], horizontal=True, key="mtbf_nivel2")
    with col_e:
        incluir_mp = st.toggle(
            "Incluir MP como 'falla' en MTBF/MTTR",
            value=True,
            help="Las horas de MP SIEMPRE restan a las horas operativas; este switch solo decide si MP cuenta como 'falla' en los denominadores.",
            key="mtbf_incluir_mp2"
        )

    # Metas (ajustables)
    META_MTBF_H = 600.0   # objetivo: ≥ 600 h operativas entre fallas
    META_MTTR_H = 8.0     # objetivo: ≤ 8 h por evento

    @st.cache_data(show_spinner=False)
    def _mtbf_mttr_preagg_op(df_mant_all: pd.DataFrame,
                            df_flota_all: pd.DataFrame,
                            anio: int,
                            mes_hasta: int,
                            familia_filtro: str | None,
                            motoriz_filtro: str | None,
                            incluir_mp: bool):
        """
        Reglas:
        - Horas operativas = Horas teóricas – (hrs_MC + hrs_GAR + hrs_MP)   [MP siempre resta]
        - Disponibilidad(%) = Horas operativas / Horas teóricas * 100       [siempre con MP]
        - MTBF = Horas operativas / (#MC + #GAR + (#MP si incluir_mp=True))
        - MTTR = (hrs_MC + hrs_GAR + (hrs_MP si incluir_mp)) / (#MC + #GAR + (#MP si incluir_mp))
        Solo se consideran OTs cerradas (Ingresos al Taller = 1).
        """
        universo = df_flota_all[["Placa Vehiculo","Familia","Motorización"]].dropna(subset=["Placa Vehiculo"]).drop_duplicates()

        if familia_filtro and familia_filtro != "Todas":
            universo = universo[universo["Familia"].astype(str) == str(familia_filtro)]
        if motoriz_filtro and motoriz_filtro != "Todos":
            universo = universo[universo["Motorización"].astype(str) == str(motoriz_filtro)]

        placas_set = set(universo["Placa Vehiculo"].tolist())
        idx = pd.Index(range(1, int(mes_hasta)+1), name="Mes")

        # Subset del año/placas — NUEVO: solo OTs cerradas
        df_y = df_mant_all[
            (df_mant_all["Año"] == anio) &
            (df_mant_all["Mes"].between(1, mes_hasta)) &
            (df_mant_all["Placa Vehiculo"].isin(placas_set)) &
            (df_mant_all["Ingresos al Taller"] == 1)
        ].copy()

        # Flags y horas por tipo
        df_y["is_MC"]  = (df_y["Tipo de OT"] == "MC").astype(int)
        df_y["is_GAR"] = (df_y["Tipo de OT"] == "Garantia").astype(int)
        df_y["is_MP"]  = (df_y["Tipo de OT"] == "MP").astype(int)

        df_y["hrs_MC"]  = np.where(df_y["is_MC"]==1,  df_y["Horas Taller"], 0.0)
        df_y["hrs_GAR"] = np.where(df_y["is_GAR"]==1, df_y["Horas Taller"], 0.0)
        df_y["hrs_MP"]  = np.where(df_y["is_MP"]==1,  df_y["Horas Taller"], 0.0)

        # Agregado mensual
        agr = (df_y.groupby("Mes")[["is_MC","is_GAR","is_MP","hrs_MC","hrs_GAR","hrs_MP"]]
                .sum().reindex(idx, fill_value=0))
        horas_taller_tot = agr["hrs_MC"] + agr["hrs_GAR"] + agr["hrs_MP"]  # MP siempre resta

        # Teóricas del mes * #placas activas
        n_placas = max(1, universo["Placa Vehiculo"].nunique())
        horas_teo_mes = pd.Series([_teoricas_horas(anio, int(m)) * n_placas for m in idx], index=idx, name="HorasTeoricas")

        # Horas operativas por mes (no negativas) y Disponibilidad(%)
        horas_op_mes = (horas_teo_mes - horas_taller_tot).clip(lower=0.0)
        disp_pct_mes = np.where(horas_teo_mes.values > 0, horas_op_mes.values / horas_teo_mes.values * 100.0, np.nan)

        # Conteo de fallas para MTBF/MTTR
        if incluir_mp:
            fallas_mes = agr["is_MC"] + agr["is_GAR"] + agr["is_MP"]
            horas_rep  = agr["hrs_MC"] + agr["hrs_GAR"] + agr["hrs_MP"]
            cnt_rep    = fallas_mes.copy()
        else:
            fallas_mes = agr["is_MC"] + agr["is_GAR"]
            horas_rep  = agr["hrs_MC"] + agr["hrs_GAR"]
            cnt_rep    = fallas_mes.copy()

        # Series (se usan para los gráficos)
        serie_mtbf = pd.DataFrame({
            "Mes": idx,
            "MTBF_h": np.where(fallas_mes>0, (horas_op_mes.values / fallas_mes.to_numpy()), np.nan)
        })
        serie_mttr = pd.DataFrame({
            "Mes": idx,
            "MTTR_h": np.where(cnt_rep.replace(0, np.nan)>0, (horas_rep.values / cnt_rep.replace(0, np.nan).values), np.nan)
        })

        # ---- Tabla del mes de corte ----
        df_m = df_y[df_y["Mes"] == mes_hasta].copy()
        if df_m.empty:
            return serie_mtbf, serie_mttr, pd.DataFrame(), universo

        base_placa = (df_m.groupby("Placa Vehiculo")
                        .agg(MC=("is_MC","sum"),
                            GAR=("is_GAR","sum"),
                            MP =("is_MP","sum"),
                            Horas_MC=("hrs_MC","sum"),
                            Horas_GAR=("hrs_GAR","sum"),
                            Horas_MP=("hrs_MP","sum"))
                        .reset_index())
        base_placa = universo.merge(base_placa, on="Placa Vehiculo", how="left")\
                            .fillna({"MC":0,"GAR":0,"MP":0,"Horas_MC":0.0,"Horas_GAR":0.0,"Horas_MP":0.0})

        base_placa["HorasTeoricas"]     = _teoricas_horas(anio, int(mes_hasta))
        base_placa["Horas_Taller_Tot"]  = (base_placa["Horas_MC"] + base_placa["Horas_GAR"] + base_placa["Horas_MP"])
        base_placa["Horas_Operativas"]  = (base_placa["HorasTeoricas"] - base_placa["Horas_Taller_Tot"]).clip(lower=0.0)
        # Disponibilidad(%) SIEMPRE con MP
        base_placa["Disp_%"]            = np.where(base_placa["HorasTeoricas"]>0,
                                                base_placa["Horas_Operativas"]/base_placa["HorasTeoricas"]*100.0, np.nan)

        if incluir_mp:
            base_placa["Fallas"]    = base_placa["MC"] + base_placa["GAR"] + base_placa["MP"]
            base_placa["Horas_Rep"] = base_placa["Horas_Taller_Tot"]
            base_placa["Cnt_Rep"]   = base_placa["Fallas"]
        else:
            base_placa["Fallas"]    = base_placa["MC"] + base_placa["GAR"]
            base_placa["Horas_Rep"] = base_placa["Horas_MC"] + base_placa["Horas_GAR"]
            base_placa["Cnt_Rep"]   = base_placa["Fallas"]

        base_placa["MTBF_h"] = np.where(base_placa["Fallas"]>0,
                                        base_placa["Horas_Operativas"] / base_placa["Fallas"],
                                        np.nan)
        base_placa["MTTR_h"] = np.where(base_placa["Cnt_Rep"]>0,
                                        base_placa["Horas_Rep"] / base_placa["Cnt_Rep"],
                                        np.nan)

        # Conteos como enteros (sin .000)
        for c in ["Fallas","MC","GAR","MP"]:
            base_placa[c] = base_placa[c].astype("Int64")

        # Agregación por familia
        tabla_familia = (base_placa.groupby(["Familia"], dropna=False)
                            .agg(Placas=("Placa Vehiculo","nunique"),
                                Fallas=("Fallas","sum"),
                                MC=("MC","sum"),
                                GAR=("GAR","sum"),
                                MP=("MP","sum"),
                                Horas_Taller_Tot=("Horas_Taller_Tot","sum"),
                                Horas_Operativas=("Horas_Operativas","sum"),
                                HorasTeoricas=("HorasTeoricas","sum"),
                                Horas_Rep=("Horas_Rep","sum"))
                            .reset_index())

        # Disponibilidad(%) y MTBF/MTTR por familia
        tabla_familia["Disp_%"]  = np.where(tabla_familia["HorasTeoricas"]>0,
                                            tabla_familia["Horas_Operativas"]/tabla_familia["HorasTeoricas"]*100.0, np.nan)
        tabla_familia["MTBF_h"]  = np.where(tabla_familia["Fallas"]>0,
                                            tabla_familia["Horas_Operativas"]/tabla_familia["Fallas"], np.nan)
        tabla_familia["MTTR_h"]  = np.where(tabla_familia["Fallas"]>0,
                                            tabla_familia["Horas_Rep"]/tabla_familia["Fallas"], np.nan)

        # Cast enteros en familia
        for c in ["Placas","Fallas","MC","GAR","MP"]:
            tabla_familia[c] = tabla_familia[c].astype("Int64")

        return serie_mtbf, serie_mttr, (base_placa, tabla_familia), universo

    serie_mtbf, serie_mttr, tablas, _universo_local = _mtbf_mttr_preagg_op(
        df_mant_all, df_flota_all, anio_m, int(mes_hasta), fam_m, mot_f, incluir_mp
    )

    # ---- Tabla (según nivel) + TOTAL ----
    if isinstance(tablas, tuple):
        base_placa, tabla_familia = tablas

        if nivel == "Familia":
            # Totales para familia
            tot_fallas = int(tabla_familia["Fallas"].sum())
            tot_mc     = int(tabla_familia["MC"].sum())
            tot_gar    = int(tabla_familia["GAR"].sum())
            tot_mp     = int(tabla_familia["MP"].sum())
            tot_placas = int(tabla_familia["Placas"].sum())
            tot_ht     = float(tabla_familia["HorasTeoricas"].sum())
            tot_htal   = float(tabla_familia["Horas_Taller_Tot"].sum())
            tot_hop    = float(tabla_familia["Horas_Operativas"].sum())
            tot_hrep   = float(tabla_familia["Horas_Rep"].sum())
            mtbf_tot   = (tot_hop / tot_fallas) if tot_fallas > 0 else np.nan
            mttr_tot   = (tot_hrep / tot_fallas) if tot_fallas > 0 else np.nan
            disp_tot   = (tot_hop / tot_ht * 100.0) if tot_ht > 0 else np.nan  # SIEMPRE con MP

            tot_row = pd.DataFrame([{
                "Familia": "Total",
                "Placas": tot_placas,
                "Fallas": tot_fallas,
                "MC": tot_mc,
                "GAR": tot_gar,
                "MP": tot_mp,
                "HorasTeoricas": tot_ht,
                "Horas_Taller_Tot": tot_htal,
                "Horas_Operativas": tot_hop,
                "Disp_%": disp_tot,
                "MTBF_h": mtbf_tot,
                "MTTR_h": mttr_tot,
            }])

            show_tbl = (tabla_familia
                        .loc[:, ["Familia","Placas","Fallas","MC","GAR","MP",
                                "HorasTeoricas","Horas_Taller_Tot","Horas_Operativas","Disp_%",
                                "MTBF_h","MTTR_h"]]
                        .sort_values(["Familia"]))
            show_tbl = pd.concat([show_tbl, tot_row], ignore_index=True)

        else:
            # Totales para nivel placa (familia = 'Total', placa vacío)
            tot_fallas = int(base_placa["Fallas"].sum())
            tot_mc     = int(base_placa["MC"].sum())
            tot_gar    = int(base_placa["GAR"].sum())
            tot_mp     = int(base_placa["MP"].sum())
            tot_ht     = float(base_placa["HorasTeoricas"].sum())
            tot_htal   = float(base_placa["Horas_Taller_Tot"].sum())
            tot_hop    = float(base_placa["Horas_Operativas"].sum())
            tot_hrep   = float(base_placa["Horas_Rep"].sum())
            mtbf_tot   = (tot_hop / tot_fallas) if tot_fallas > 0 else np.nan
            mttr_tot   = (tot_hrep / tot_fallas) if tot_fallas > 0 else np.nan
            disp_tot   = (tot_hop / tot_ht * 100.0) if tot_ht > 0 else np.nan  # SIEMPRE con MP

            tot_row = pd.DataFrame([{
                "Familia": "Total",
                "Placa Vehiculo": "",
                "Fallas": tot_fallas,
                "MC": tot_mc,
                "GAR": tot_gar,
                "MP": tot_mp,
                "HorasTeoricas": tot_ht,
                "Horas_Taller_Tot": tot_htal,
                "Horas_Operativas": tot_hop,
                "Disp_%": disp_tot,
                "MTBF_h": mtbf_tot,
                "MTTR_h": mttr_tot,
            }])

            show_tbl = (base_placa
                        .loc[:, ["Familia","Placa Vehiculo","Fallas","MC","GAR","MP",
                                "HorasTeoricas","Horas_Taller_Tot","Horas_Operativas","Disp_%",
                                "MTBF_h","MTTR_h"]]
                        .sort_values(["Familia","Placa Vehiculo"]))
            show_tbl = pd.concat([show_tbl, tot_row], ignore_index=True)

        # Estilo semáforo vs metas y formateo
        def _bg_mtbf(v):
            try: x = float(v)
            except Exception: return ""
            if np.isnan(x):           return "background-color:#f0f0f0"
            if x >= META_MTBF_H:      return "background-color:#a3e4b8"
            if x >= META_MTBF_H*0.7:  return "background-color:#f9e79f"
            return "background-color:#f5b7b1"

        def _bg_mttr(v):
            try: x = float(v)
            except Exception: return ""
            if np.isnan(x):           return "background-color:#f0f0f0"
            if x <= META_MTTR_H:      return "background-color:#a3e4b8"
            if x <= META_MTTR_H*1.5:  return "background-color:#f9e79f"
            return "background-color:#f5b7b1"

        def _bg_disp(v):
            try: x = float(v)
            except Exception: return ""
            if np.isnan(x):  return "background-color:#f0f0f0"
            if x > 98:       return "background-color:#2ecc71; color:white"
            if x >= 95:      return "background-color:#a3e4b8"
            if x >= 90:      return "background-color:#f9e79f"
            return "background-color:#f5b7b1"

        sty = (show_tbl.style
            .map(_bg_disp, subset=["Disp_%"])
            .map(_bg_mtbf, subset=["MTBF_h"])
            .map(_bg_mttr, subset=["MTTR_h"])
            .format({
                "Placas":"{:,.0f}",
                "Fallas":"{:,.0f}",
                "MC":"{:,.0f}",
                "GAR":"{:,.0f}",
                "MP":"{:,.0f}",
                "HorasTeoricas":"{:.0f} h",
                "Horas_Taller_Tot":"{:.1f} h",
                "Horas_Operativas":"{:.1f} h",
                "Disp_%":"{:.2f} %",
                "MTBF_h":"{:.1f} h",
                "MTTR_h":"{:.1f} h",
            }))
        st.dataframe(sty, use_container_width=True, hide_index=True)
    else:
        st.info("Sin datos para el año/mes/familia/motorización seleccionados.")

    # ---- Gráficos de serie temporal (MTBF y MTTR) ----
    import matplotlib.pyplot as plt
    MESES_ABBR = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

    col_g1, col_g2 = st.columns(2)

    with col_g1:
        fig_mtbf, ax = plt.subplots(figsize=(6.0, 3.6))
        # Bandas
        ax.axhspan(0, META_MTBF_H*0.7,            facecolor="#f5b7b1", alpha=0.6, zorder=0)  # rojo
        ax.axhspan(META_MTBF_H*0.7, META_MTBF_H,  facecolor="#f9e79f", alpha=0.5, zorder=0)  # ámbar
        ax.axhspan(META_MTBF_H, META_MTBF_H*5,    facecolor="#a3e4b8", alpha=0.4, zorder=0)  # verde
        ax.plot(serie_mtbf["Mes"], serie_mtbf["MTBF_h"], marker="o", linewidth=2.5)
        ax.axhline(META_MTBF_H, linestyle="--")
        ax.set_xticks(range(1, int(mes_hasta)+1))
        ax.set_xticklabels([MESES_ABBR[i-1] for i in range(1, int(mes_hasta)+1)])
        ax.set_ylabel("Horas")
        ax.set_title(f"MTBF (h) por mes{' + MP' if incluir_mp else ''}")
        # Etiqueta de meta
        xmin, xmax = 1, int(mes_hasta)
        ax.text(xmin, META_MTBF_H*1.02,
                f"Meta: {META_MTBF_H:.0f} hras ≈ 1 falla al mes",
                va="bottom", ha="left", fontsize=9)
        st.pyplot(fig_mtbf, use_container_width=True)

    with col_g2:
        fig_mttr, ax2 = plt.subplots(figsize=(6.0, 3.6))
        # Bandas inversas para MTTR
        ax2.axhspan(0, META_MTTR_H,                 facecolor="#a3e4b8", alpha=0.4, zorder=0)  # verde
        ax2.axhspan(META_MTTR_H, META_MTTR_H*1.5,   facecolor="#f9e79f", alpha=0.5, zorder=0)  # ámbar
        ax2.axhspan(META_MTTR_H*1.5, META_MTTR_H*5, facecolor="#f5b7b1", alpha=0.6, zorder=0)  # rojo
        ax2.plot(serie_mttr["Mes"], serie_mttr["MTTR_h"], marker="o", linewidth=2.5)
        ax2.axhline(META_MTTR_H, linestyle="--")
        ax2.set_xticks(range(1, int(mes_hasta)+1))
        ax2.set_xticklabels([MESES_ABBR[i-1] for i in range(1, int(mes_hasta)+1)])
        ax2.set_ylabel("Horas")
        ax2.set_title(f"MTTR (h) por mes{' + MP' if incluir_mp else ''}")
        # Etiqueta de meta
        xmin2, xmax2 = 1, int(mes_hasta)
        ax2.text(xmin2, META_MTTR_H*1.03,
                f"Meta: {META_MTTR_H:.0f} hras",
                va="bottom", ha="left", fontsize=9)
        st.pyplot(fig_mttr, use_container_width=True)

    st.caption("Metas: MTBF ≥ {:.0f} h · MTTR ≤ {:.0f} h · La Disponibilidad(%) SIEMPRE descuenta MC + GAR + MP".format(META_MTBF_H, META_MTTR_H))

    ###########################

# ======================================================================
    # Próximos mantenimientos – construcción de tabla_mp
    # (Pegar antes del bloque de UI que usa `tabla_mp`)
    # ======================================================================

    # Rutas de archivos adicionales
    PATH_MP_INTERVALOS = BASE_DIR / "mp_intervalos.xlsx"
    PATH_RECORRIDOS    = BASE_DIR / "recorridos_maestro.xlsx"

    # (debajo de donde defines PATH_MP_INTERVALOS y PATH_RECORRIDOS)
    MP_SRC  = load(os.getenv("URL_MP",       str(PATH_MP_INTERVALOS)))
    REC_SRC = load(os.getenv("URL_RECORR",   str(PATH_RECORRIDOS)))


    @st.cache_data(show_spinner=False)
    def _read_flota_kms(path: Path) -> pd.DataFrame:
        """Flota (pestaña 'Flota', header fila 8). Devuelve placa, familia, motorización,
        Km Actual y Fecha último Km."""
     
        df = _df_or_path_to_df(path, sheet_name="Flota", header=7)
        cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
        df = df.rename(columns=cols)

        def pick(name_like, fallback):
            return next((c for c in df.columns if name_like(c)), fallback)

        placa_col = pick(lambda c: c.lower().startswith("placa") and "vehiculo" in c.lower(), "Placa Vehiculo")
        fam_col   = pick(lambda c: c.lower().startswith("familia"), "Familia")
        mot_col   = pick(lambda c: c.lower().startswith("motoriz"), "Motorización")
        km_col    = pick(lambda c: c.lower().startswith("km actual"), "Km Actual")
        fkm_col   = pick(lambda c: "fecha" in c.lower() and "km" in c.lower(), "Fecha último Km")

        df = df[[placa_col, fam_col, mot_col, km_col, fkm_col]].copy()
        df.columns = ["Placa Vehiculo", "Familia", "Motorización", "Km Actual", "Fecha último Km"]

        df["Placa Vehiculo"] = df["Placa Vehiculo"].astype(str).str.upper().str.replace(" ", "", regex=False)
        df["Familia"]        = df["Familia"].astype(str).str.strip()
        df["Motorización"]   = df["Motorización"].astype(str).str.strip()
        df["Km Actual"]      = pd.to_numeric(df["Km Actual"], errors="coerce").fillna(0.0)
        df["Fecha último Km"] = pd.to_datetime(df["Fecha último Km"], errors="coerce")

        return df.dropna(subset=["Placa Vehiculo"]).drop_duplicates(subset=["Placa Vehiculo"])

    @st.cache_data(show_spinner=False)
    def _read_mp_intervalos(path: Path) -> pd.DataFrame:
        """mp_intervalos (pestaña 'Data Flota'). Usa 'Placa Vehiculo' y 'Próximo Mantto' (kilómetros)."""
       
        df = _df_or_path_to_df(path, sheet_name="Data Flota")

        cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
        df = df.rename(columns=cols)

        placa_col = next((c for c in df.columns if c.lower().startswith("placa")), "Placa Vehiculo")
        prox_col  = next((c for c in df.columns if "próximo" in c.lower() and "mantto" in c.lower()), "Próximo Mantto")

        df = df[[placa_col, prox_col]].copy()
        df.columns = ["Placa Vehiculo", "Próximo Mantto (km)"]

        df["Placa Vehiculo"]      = df["Placa Vehiculo"].astype(str).str.upper().str.replace(" ", "", regex=False)
        df["Próximo Mantto (km)"] = pd.to_numeric(df["Próximo Mantto (km)"], errors="coerce")
        return df.dropna(subset=["Placa Vehiculo"]).drop_duplicates(subset=["Placa Vehiculo"])

    @st.cache_data(show_spinner=False)
    def _read_recorridos(path: Path) -> pd.DataFrame:
        """recorridos_maestro (única pestaña). Usa 'Vehículo', 'Fecha', 'Distancia (km)'."""
       
        df = _df_or_path_to_df(path, sheet_name=0)

        cols = {c: re.sub(r"\s+", " ", str(c)).strip() for c in df.columns}
        df = df.rename(columns=cols)

        veh_col   = next((c for c in df.columns if "vehículo" in c.lower() or "vehiculo" in c.lower()), "Vehículo")
        fecha_col = next((c for c in df.columns if c.lower().startswith("fecha")), "Fecha")
        dist_col  = next((c for c in df.columns if "distancia" in c.lower()), "Distancia (km)")

        df = df[[veh_col, fecha_col, dist_col]].copy()
        df.columns = ["Placa Vehiculo", "Fecha", "Distancia (km)"]

        df["Placa Vehiculo"] = df["Placa Vehiculo"].astype(str).str.upper().str.replace(" ", "", regex=False)
        df["Fecha"]          = pd.to_datetime(df["Fecha"], errors="coerce")
        df["Distancia (km)"] = pd.to_numeric(df["Distancia (km)"], errors="coerce").fillna(0.0)

        # Consolidar por día y placa (por si hay múltiples viajes en el mismo día)
        df = (df.dropna(subset=["Placa Vehiculo", "Fecha"])
                .groupby(["Placa Vehiculo", "Fecha"], as_index=False)["Distancia (km)"].sum())
        return df

    @st.cache_data(show_spinner=True)
    def _build_tabla_mp(
        path_flota: Path,
        path_mp: Path,
        path_recorridos: Path
    ) -> pd.DataFrame:
        flota = _read_flota_kms(path_flota)
        mp    = _read_mp_intervalos(path_mp)
        rec   = _read_recorridos(path_recorridos)

        # Sumar recorridos DESDE la "Fecha último Km" (inclusive) por placa
        m = rec.merge(flota[["Placa Vehiculo", "Fecha último Km"]], on="Placa Vehiculo", how="right")
        mask_valid = (~m["Fecha"].isna()) & (~m["Fecha último Km"].isna()) & (m["Fecha"] >= m["Fecha último Km"])
        suma_desde_f_ult = (m.loc[mask_valid]
                            .groupby("Placa Vehiculo")["Distancia (km)"]
                            .sum()
                            .reindex(flota["Placa Vehiculo"])
                            .fillna(0.0))

        flota = flota.set_index("Placa Vehiculo")
        flota["Recorrido actual (km)"] = flota["Km Actual"].fillna(0.0) + suma_desde_f_ult

        # Próximo Mantto
        flota = flota.reset_index().merge(mp, on="Placa Vehiculo", how="left")

        # Estado (OK / Alerta / Alerta Urgente / Falta dato) — delta_km solo para colorear
        flota["delta_km"] = flota["Próximo Mantto (km)"] - flota["Recorrido actual (km)"]
        flota["Estado"] = np.select(
            [
                flota["Próximo Mantto (km)"].isna(),
                flota["delta_km"] <= 1000,
                flota["delta_km"] <= 3000
            ],
            ["Falta dato", "Alerta Urgente", "Alerta"],
            default="OK"
        )

        out = (flota[["Familia", "Placa Vehiculo", "Motorización",
                    "Próximo Mantto (km)", "Recorrido actual (km)", "Estado", "delta_km"]]
            .copy())

        # Renombrar la diferencia para mostrarla en la UI
        out = out.rename(columns={"delta_km": "Km restantes para mantto"})

        out["Próximo Mantto (km)"]   = pd.to_numeric(out["Próximo Mantto (km)"], errors="coerce")
        out["Recorrido actual (km)"] = pd.to_numeric(out["Recorrido actual (km)"], errors="coerce").fillna(0.0)

        return out.sort_values(["Familia", "Placa Vehiculo"]).reset_index(drop=True)

    # Construir dataframe para la UI
    #tabla_mp = _build_tabla_mp(PATH_FLOTA, PATH_MP_INTERVALOS, PATH_RECORRIDOS)
    tabla_mp = _build_tabla_mp(FLOTA_SRC, MP_SRC, REC_SRC)
    # ============================
    # UI · Próximos mantenimientos (por placa)
    # ============================
    st.markdown("### Próximos mantenimientos preventivos (por placa)")
    st.caption("Cruza *Flota* (Km actual / Fecha último Km) + *recorridos_maestro* (distancia diaria) + *mp_intervalos* (Próximo Mantto).")

    # Leemos recorridos una sola vez (cacheado)
    #recorridos_all = _read_recorridos(PATH_RECORRIDOS)
    recorridos_all = _read_recorridos(REC_SRC)

    # Filtros (Año + Mes numérico)
    col_fam, col_buscar, col_mot, col_anio, col_mes = st.columns([2, 3, 2, 1.2, 1.2])

    with col_fam:
        fam_opts = ["Todas"] + sorted(tabla_mp["Familia"].dropna().astype(str).unique().tolist())
        fam_sel  = st.selectbox("Familia", fam_opts, index=0, key="mp_fam")

    with col_buscar:
        q = st.text_input("Buscar placa", value="", key="mp_buscar")

    with col_mot:
        mot_opts = ["Todos"] + sorted(tabla_mp["Motorización"].dropna().astype(str).unique().tolist())
        mot_sel  = st.selectbox("Motorización", mot_opts, index=0, key="mp_mot")

    with col_anio:
        years = sorted(
            (recorridos_all["Fecha"].dt.year.dropna().unique().tolist() if not recorridos_all.empty else [date.today().year])
        )
        anio_sel_mp = st.selectbox("Año", options=years, index=len(years)-1, key="mp_anio")

    with col_mes:
        mes_sel_mp = st.selectbox("Mes", options=list(range(1, 13)),
                                index=date.today().month-1, key="mp_mes")

    # Filtro para la primera tabla (estado + colores)
    df_view = tabla_mp.copy()
    if fam_sel != "Todas":
        df_view = df_view[df_view["Familia"].astype(str) == fam_sel]
    if mot_sel != "Todos":
        df_view = df_view[df_view["Motorización"].astype(str) == mot_sel]
    if q.strip():
        qn = q.strip().upper().replace(" ", "")
        df_view = df_view[df_view["Placa Vehiculo"].str.contains(qn, case=False, na=False)]

    # Colores: estado + “Recorrido actual (km)” según los Km restantes
    def _estado_bg(v):
        s = str(v).strip().lower()
        if s == "ok":
            return "background-color:#e8f6ec; color:#196f3d; font-weight:600"
        if "urgente" in s:
            return "background-color:#f8d7da; color:#7b241c; font-weight:700"   # rojo
        if "alerta" in s:
            return "background-color:#fdebd0; color:#7d6608; font-weight:700"   # ámbar
        return "background-color:#fbe5e5; color:#922b21; font-weight:700"        # falta dato

    def _recorrido_color(row):
        try:
            delta = float(row["Km restantes para mantto"])
        except Exception:
            return "background-color:#fbe5e5; color:#922b21; font-weight:700"
        if np.isnan(delta):
            return "background-color:#fbe5e5; color:#922b21; font-weight:700"
        if delta <= 1000:
            return "background-color:#f8d7da; color:#7b241c; font-weight:700"   # rojo
        if delta <= 3000:
            return "background-color:#fdebd0; color:#7d6608; font-weight:700"   # ámbar
        return ""

    sty = (df_view.style
        .apply(lambda _s: df_view.apply(_recorrido_color, axis=1), subset=["Recorrido actual (km)"])
        .map(_estado_bg, subset=["Estado"])
        .format({
            "Próximo Mantto (km)": "{:,.0f}",
            "Recorrido actual (km)": "{:,.0f}",
            "Km restantes para mantto": "{:,.0f}",
        }))

    st.dataframe(
        sty,
        use_container_width=True,
        hide_index=True
    )

    # ============================
    # CUADRO 2: Recorridos diarios por placa (mes seleccionado)
    # ============================
    st.markdown("#### Recorridos diarios por placa (mes seleccionado)")

    # Subset por mes/año seleccionados
    rec_m = recorridos_all[
        (recorridos_all["Fecha"].dt.year == anio_sel_mp) &
        (recorridos_all["Fecha"].dt.month == mes_sel_mp)
    ].copy()

    # Universo de placas (de Flota)
    flota_base = _read_flota_kms(PATH_FLOTA)[["Placa Vehiculo", "Familia", "Motorización"]]

    # Pivot día a día
    rec_m["dia"] = rec_m["Fecha"].dt.day
    pvt = rec_m.pivot_table(index="Placa Vehiculo",
                            columns="dia",
                            values="Distancia (km)",
                            aggfunc="sum").sort_index(axis=1)

    # Garantizar columnas 1..N del mes (usar año/mes seleccionados)
    ndays = calendar.monthrange(int(anio_sel_mp), int(mes_sel_mp))[1]
    all_days = list(range(1, ndays+1))
    pvt = pvt.reindex(columns=all_days)

    # Recorrido TOTAL histórico por placa (suma de todas las fechas)
    total_hist = (recorridos_all.groupby("Placa Vehiculo")["Distancia (km)"]
                .sum()
                .rename("Recorrido total (km)")
                .reset_index())

    # Merge con universo + Próximo Mantto (de la primera tabla) + total histórico
    resumen_cols = df_view[["Placa Vehiculo", "Próximo Mantto (km)"]].copy()
    tabla_dias = (flota_base.merge(pvt, left_on="Placa Vehiculo", right_index=True, how="left")
                            .merge(total_hist, on="Placa Vehiculo", how="left")
                            .merge(resumen_cols, on="Placa Vehiculo", how="left"))

    # Filtros (mismos de arriba)
    if fam_sel != "Todas":
        tabla_dias = tabla_dias[tabla_dias["Familia"].astype(str) == fam_sel]
    if mot_sel != "Todos":
        tabla_dias = tabla_dias[tabla_dias["Motorización"].astype(str) == mot_sel]
    if q.strip():
        qn = q.strip().upper().replace(" ", "")
        tabla_dias = tabla_dias[tabla_dias["Placa Vehiculo"].str.contains(qn, case=False, na=False)]

    # Totales y promedio mensual
    tabla_dias["Recorrido mensual (km)"] = tabla_dias[all_days].sum(axis=1, skipna=True)
    tabla_dias["Promedio mensual (km/día)"] = (tabla_dias["Recorrido mensual (km)"] / ndays).round(2)

    # Orden de columnas: Familia, Placa, (días...), Promedio, Mensual, Total, Próximo Mantto
    cols_final = (["Familia", "Placa Vehiculo", "Motorización"] +
                all_days +
                ["Promedio mensual (km/día)", "Recorrido mensual (km)", "Recorrido total (km)", "Próximo Mantto (km)"])
    tabla_dias = tabla_dias.reindex(columns=cols_final)

    # Estilos: celdas sin dato (NaN) en rosa, >100 km en ámbar
    def _style_dias(v):
        try:
            x = float(v)
        except Exception:
            return "background-color:#fde2e2"  # rosa si NaN/vacío
        if np.isnan(x):
            return "background-color:#fde2e2"
        if x > 100:
            return "background-color:#fdebd0; font-weight:600"  # ámbar
        return ""

    sty_dias = (tabla_dias.style
                .applymap(_style_dias, subset=all_days)
                .format({**{d: "{:,.0f}" for d in all_days},
                        "Recorrido mensual (km)": "{:,.0f}",
                        "Recorrido total (km)": "{:,.0f}",
                        "Promedio mensual (km/día)": "{:,.2f}",
                        "Próximo Mantto (km)": "{:,.0f}"}))

    st.dataframe(sty_dias, use_container_width=True, hide_index=True)





    st.caption("Fuente: Los Andes — No incluye datos de Chosica, San Isidro y Cañete")





# ============================
# DETALLE
# ============================
with TAB_DETALLE:
    st.markdown("### Detalle de Mantenimientos")
    st.info("(Próximo) Tabla detallada con filtros avanzados y exportación.")

# ============================
# EXPORTAR
# ============================
with TAB_EXPORTAR:
    st.markdown("### Exportar")
    st.info("(Próximo) Botones de exportación a CSV/XLSX del resultado filtrado.")






   