# streamlit_app/pages/3_Energia_EV.py
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata as ud

import pandas as pd
import streamlit as st
import altair as alt
import json

from components.ui import header
from lib.config import load_settings
from lib.sync import sync_from_settings


# ============================
# Configuración de página
# ============================
st.set_page_config(
    page_title="Tecsur · Flota EV — Energía EV",
    page_icon="🔌",
    layout="wide",
)



header_box = st.container()
messages_box = st.container()

with header_box:
    header("Energía EV")
# crear settings para usar en el botón
settings = load_settings()
# === Acciones (sidebar) ===
with st.sidebar:
    st.subheader("Acciones")
    if st.button("🔄 Actualizar datos", use_container_width=True):
        # Si usas sincronización con OneDrive/SharePoint
        sync_from_settings(settings)
        # Limpia el caché de DataFrames
        st.cache_data.clear()
        # Re-ejecuta la página
        st.rerun()
# ============================
# Origen de datos
# ============================
XLSX_PATH  = Path(r"C:\Users\Enzo Morote\TECSUR S.A\Gestión Flota EV - Enzo - Documentos\Combustible_EV.xlsx")
SHEET_NAME = "Combustible EV"
SRC_NAME   = XLSX_PATH.name
#messages_box.caption(f"Fuente: **{SRC_NAME}** (hoja: **{SHEET_NAME}**, actualizado automático).")
messages_box.caption("Fuente: Los Andes-No incluye data de Chosica, San Isidro y Cañete")
# o si quieres mantener la nota:
# messages_box.caption("Fuente: Los Andes · actualizado automático.")


# ============================
# Utilidades
# ============================
def canon(s: str) -> str:
    s = str(s or "").strip().lower()
    s = "".join(ch for ch in ud.normalize("NFD", s) if ud.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9\s_/.\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def find_col(df: pd.DataFrame, keys: list[str]) -> str | None:
    if df is None or df.empty:
        return None
    keys_c = [canon(k) for k in keys]
    for c in df.columns:
        cc = canon(c)
        if any(k in cc for k in keys_c):
            return c
    return None

def _to_number(x) -> float:
    """Convierte texto con miles/decimales mixtos a float. Último separador es decimal."""
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s:
        return 0.0
    if "." in s and "," in s:
        last_dot = s.rfind("."); last_com = s.rfind(",")
        if last_dot > last_com:   # 1,234,567.89
            s = s.replace(",", "")
        else:                     # 1.234.567,89
            s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:   # 1,234,567
        s = s.replace(",", "")
    elif "." in s and "," not in s:   # 1.234.567
        s = s.replace(".", "")
    try:
        return float(s)
    except Exception:
        v = pd.to_numeric(s, errors="coerce")
        return float(v) if pd.notna(v) else 0.0

def fmt_int(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", ",\u200b")
    except Exception:
        return "0"

def fmt_money(v) -> str:
    try:
        return f"S/ {float(v):,.2f}".replace(",", ",\u200b")
    except Exception:
        return "S/ 0.00"

def metric_card(col, label: str, value_html: str):
    col.markdown(
        f"""
        <div translate="no" style="padding:12px 16px;border:1px solid #e5e7eb;border-radius:10px;">
          <div style="color:#6b7280;font-size:0.9rem">{label}</div>
          <div style="font-weight:700;font-size:2.1rem;line-height:1.1; font-variant-numeric: tabular-nums;">
            {value_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _safe_read_excel(path: Path, sheet_name: str) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except PermissionError:
        tmp = Path(tempfile.gettempdir()) / f"__tmp_{path.name}"
        try:
            shutil.copy2(path, tmp)
            return pd.read_excel(tmp, sheet_name=sheet_name, engine="openpyxl")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
    except OSError:
        with open(path, "rb") as f:
            return pd.read_excel(f, sheet_name=sheet_name, engine="openpyxl")

def _file_sig(p: Path):
    try:
        stt = p.stat()
        return (stt.st_mtime, stt.st_size)
    except Exception:
        return (None, None)

@st.cache_data(show_spinner=False)
def load_xlsx_cached(path_str: str, sheet: str, sig):
    p = Path(path_str)
    return _safe_read_excel(p, sheet)

# ============================
# Autodetección de columnas
# ============================
def pick_kwh_column(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    BEST = {"kwh", "energia (kwh)", "energia kwh", "consumo (kwh)", "comsumo (kw/h)", "consumo (kw/h)"}

    for c in df.columns:
        if canon(c) in BEST:
            return c
    best_c, best_score = None, -10**9
    for c in df.columns:
        cc = canon(c); 
        if "/100" in cc or "100 km" in cc or "kwh/100" in cc:
            continue

        score = 0
        if "kwh" in cc: score += 120
        if "energia" in cc: score += 80
        if "consumo" in cc: score += 60
        if "(kwh)" in cc or " kwh" in f" {cc} ": score += 30
        if score > best_score: best_score, best_c = score, c
    return best_c if best_score > 0 else None

def pick_cost_column(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
    candidates = ["costo", "monto", "importe", "tarifa", "costo total", "monto total"]
    return find_col(df, candidates)

def pick_km_column(df: pd.DataFrame) -> str | None:
    # Reutilizamos la lógica de Recorridos
    BEST_EXACTS = {"recorrido (km)", "recorrido km", "suma de recorrido (km)"}
    PENALIZE = {"inicial", "final", "odometro", "odometer", "odo"}
    for c in df.columns:
        if canon(c) in BEST_EXACTS:
            return c
    best_c, best_score = None, -10**9
    for c in df.columns:
        cc = canon(c); score = 0
        if "recorrido" in cc and "km" in cc: score += 100
        if "recorrido" in cc and "km" not in cc: score += 60
        if "kilometraje" in cc: score += 50
        if cc.endswith("(km)") or cc.endswith(" km") or " km " in f" {cc} ": score += 20
        if "km" in cc: score += 10
        if any(p in cc for p in PENALIZE): score -= 120
        if score > best_score: best_score, best_c = score, c
    return best_c if best_score > 0 else None

# ============================
# Preprocesos (cacheados)
# ============================
@st.cache_data(show_spinner=False)
def preprocess_energy(df_in: pd.DataFrame,
                      fecha_col: str | None,
                      placa_col: str | None,
                      usuario_col: str | None,
                      familia_col: str | None,
                      kwh_col: str | None,
                      cost_col: str | None,
                      km_col: str | None) -> pd.DataFrame:
    df = df_in.copy()

    # Fechas y campos derivados
    if fecha_col:
        df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")
        df["_Fecha_"] = df[fecha_col]
        df["_Dia_"]   = df["_Fecha_"].dt.date
        df["_Anio_"]  = df["_Fecha_"].dt.year.astype("Int64")
        df["_Mes_"]   = df["_Fecha_"].dt.month
        df["Año"]     = df["_Anio_"]
    else:
        df["Año"] = pd.NA

    # Normalizaciones
    if placa_col:
        df["_Placa_"] = df[placa_col].astype(str).str.strip()
    else:
        df["_Placa_"] = "—"

    if usuario_col:
        df["_Usuario_"] = df[usuario_col].astype(str).str.strip().str.title()
    else:
        df["_Usuario_"] = "—"

    if familia_col:
        df["_Familia_"] = df[familia_col].astype(str).str.strip().replace(r"\s+", " ", regex=True)
    else:
        df["_Familia_"] = "—"

    # Métricas numéricas
    df["__kwh__"]  = df[kwh_col].apply(_to_number) if kwh_col and kwh_col in df.columns else 0.0
    df["__costo__"] = df[cost_col].apply(_to_number) if cost_col and cost_col in df.columns else 0.0
    df["__km__"]    = df[km_col].apply(_to_number) if km_col and km_col in df.columns else 0.0

    return df

@st.cache_data(show_spinner=False)
def build_daily_cube_energy(df: pd.DataFrame):
    # Agregado diario por placa y familia (kWh)
    idx = ["_Placa_", "_Dia_", "_Anio_", "_Mes_", "_Familia_"]
    daily = (
        df.groupby(idx, dropna=False)["__kwh__"]
          .sum()
          .reset_index()
          .rename(columns={"_Placa_": "Placa", "_Dia_": "Dia", "__kwh__": "kWh"})
    )
    return daily

# ============================
# Carga
# ============================
error_text = ""
df_full: pd.DataFrame | None = None

try:
    sig = _file_sig(XLSX_PATH)  # invalida el caché si cambia el archivo
    df_full = load_xlsx_cached(str(XLSX_PATH), SHEET_NAME, sig)
except FileNotFoundError:
    error_text = f"No pude abrir el archivo: **{XLSX_PATH}**"
except ValueError as e:
    error_text = f"No pude leer la hoja **{SHEET_NAME}**: {e}"
except Exception as e:
    error_text = f"Falla al leer el Excel: {e}"

if error_text:
    messages_box.error(error_text)
    st.stop()

if df_full is None or df_full.empty:
    messages_box.info("La hoja está vacía o no se pudo detectar contenido.")
    st.stop()

# ============================
# Detectar columnas
# ============================
fecha_col   = find_col(df_full, ["fecha", "inicio", "fecha carga", "timestamp"])
placa_col   = find_col(df_full, ["placa", "vehiculo", "unidad"])
usuario_col = find_col(df_full, ["usuario", "cliente"])
familia_col = find_col(df_full, ["familia"])
#kwh_col     = pick_kwh_column(df_full)
# Priorizar explícitamente la columna deseada
kwh_col = find_col(df_full, ["Comsumo (Kw/h)", "Consumo (Kw/h)"])
if not kwh_col:
    kwh_col = pick_kwh_column(df_full)  # fallback
cost_col    = pick_cost_column(df_full)
km_col      = pick_km_column(df_full)  # opcional, para km/kWh

df_base = preprocess_energy(df_full, fecha_col, placa_col, usuario_col, familia_col, kwh_col, cost_col, km_col)
daily_cube = build_daily_cube_energy(df_base)

# ============================
# Filtros (sidebar)
# ============================
with st.sidebar:
    st.subheader("Filtros")
    placa_q = st.text_input("Buscar placa (opcional)")
    if fecha_col:
        min_d = pd.to_datetime(df_base[fecha_col], errors="coerce").min()
        max_d = pd.to_datetime(df_base[fecha_col], errors="coerce").max()
        if pd.isna(min_d) or pd.isna(max_d):
            min_d = date(2023, 1, 1)
            max_d = date.today()
        dr = st.date_input(
            "Rango de fechas",
            value=(min_d.date(), max_d.date()),
            min_value=min_d.date(),
            max_value=max_d.date(),
        )
    else:
        dr = None

df = df_base.copy()
if placa_q and placa_col:
    df = df[df[placa_col].astype(str).str.contains(placa_q.strip(), case=False, na=False)]
if fecha_col and dr:
    d_from, d_to = dr[0], dr[1]
    m_from, m_to = pd.to_datetime(d_from), pd.to_datetime(d_to)
    df = df[(df[fecha_col] >= m_from) & (df[fecha_col] <= m_to)]

# ============================
# Tabs
# ============================
tab_resumen, tab_detalle, tab_export = st.tabs(["Resumen", "Detalle", "Exportar"])

# ----------------------------
# RESUMEN
# ----------------------------
with tab_resumen:
    st.caption(
        f"Usando **{kwh_col or '—'}** como columna de kWh, "
        f"**{fecha_col or '—'}** como fecha"
        + (f" y **{km_col}** como km." if km_col else ".")
    )

    # KPIs
    kwh_2023 = float(df.loc[df["Año"] == 2023, "__kwh__"].sum())
    kwh_2024 = float(df.loc[df["Año"] == 2024, "__kwh__"].sum())
    kwh_2025 = float(df.loc[df["Año"] == 2025, "__kwh__"].sum())
    #sesiones = int(len(df))  # si hay 1 fila por sesión; si no, igual indica registros
    
    # >>> por estas líneas:
    placa_col = "Placa" if "Placa" in df.columns else ("PLACA" if "PLACA" in df.columns else None)
    placas_unicas = (
        df[placa_col].astype(str).str.strip().replace({"": None}).dropna().nunique()
    ) if placa_col else 0

    costo_tot = float(df["__costo__"].sum()) if "__costo__" in df.columns else 0.0

    km_tot = float(df["__km__"].sum()) if "__km__" in df.columns else 0.0
    kmkwh = (km_tot / df["__kwh__"].sum()) if df["__kwh__"].sum() > 0 else None

    c1, c2, c3, c4 = st.columns(4)
    metric_card(c1, "kWh 2023", f"<span>{fmt_int(kwh_2023)}</span>")
    metric_card(c2, "kWh 2024", f"<span>{fmt_int(kwh_2024)}</span>")
    metric_card(c3, "kWh 2025", f"<span>{fmt_int(kwh_2025)}</span>")
    #metric_card(c4, "Sesiones (registros)", f"<span>{fmt_int(sesiones)}</span>")
    metric_card(c4, "Placas únicas", f"<span>{fmt_int(placas_unicas)}</span>")

    c5, c6 = st.columns(2)
    metric_card(c5, "Costo total", f"<span>{fmt_money(costo_tot)}</span>")
    if kmkwh is not None and kmkwh > 0:
        metric_card(c6, "Rendimiento Global (km/kWh) ", f"<span>{kmkwh:,.2f}</span>".replace(",", ",\u200b"))
    else:
        metric_card(c6, "Rendimiento Global (km/kWh)", "<span>—</span>")

    st.markdown("---")


 
    # ============================
    # NUEVA SECCIÓN: Rendimiento (km/kWh) por Placa y Mes
    # ============================
    st.markdown("### Rendimiento (km/kWh) por Placa y Mes — Agrupado por Familia")

    # (Aquí irá el bloque de cálculo y visualización de rendimientos)
    # ---------- Rendimiento (km/kWh) por Placa y Mes — Agrupado por Familia ----------
    # Config editable de umbrales por familia (puedes modificarla cuando quieras)
    DEFAULT_RULES_KMKWH = {
        "bus ev yutong":       [1.0, 2.0],  # [amarillo/rojo, verde]
        "camion ev jac":       [1.0, 2.0],
        "pick up ev 4x2 jac":  [3.0, 4.0],
        "pick up hibrida byd": None,
        "suv byd (gerencia)": (3.0, 4.0),
        "suv ev byd": (4.0, 6.0),  
        "suv ev jac":          [3.0, 4.0],
        "van cargo ev byd":    [4.0, 6.0],
        # "pick up hibrida byd": None  # si alguna familia no desea reglas, usar None
    }

    RULES_KMKWH = DEFAULT_RULES_KMKWH


    # Filtro de año
    anios_disp = sorted([int(x) for x in df["Año"].dropna().unique()])
    if len(anios_disp) == 0:
        st.info("No hay años disponibles para construir el cuadro de rendimiento.")
    else:
        anio_rend = st.selectbox("Año", anios_disp, index=len(anios_disp)-1, key="anio_rend")

        @st.cache_data(show_spinner=False)
        def _rendimiento_pivot(df_base: pd.DataFrame, year: int):
            # Requeridos
            req = ["_Fecha_", "_Placa_", "_Familia_", "__km__", "__kwh__"]
            for r in req:
                if r not in df_base.columns:
                    return pd.DataFrame()

            dfy = df_base.loc[df_base["Año"] == year, req].copy()
            if dfy.empty:
                return pd.DataFrame()

            dfy = dfy.dropna(subset=["_Fecha_", "_Placa_", "_Familia_"])
            dfy = dfy[dfy["__kwh__"] > 0]  # evita divisiones por cero
            dfy["_Mes_"] = pd.to_datetime(dfy["_Fecha_"], errors="coerce").dt.month
            dfy["Rendimiento"] = dfy["__km__"] / dfy["__kwh__"]

            # Promedio por placa para cada mes
            g = (
                dfy.groupby(["_Familia_", "_Placa_", "_Mes_"], dropna=False)["Rendimiento"]
                   .mean()
                   .reset_index()
            )

            # Pivot con meses como columnas (1..12). Redondeo a 2 decimales para la UI.
            meses = list(range(1, 13))
            pvt = (
                g.pivot_table(index=["_Familia_", "_Placa_"], columns="_Mes_", values="Rendimiento", aggfunc="mean")
                 .reindex(columns=meses)
                 .sort_index()
                 .reset_index()
            )
            for m in meses:
                if m in pvt.columns:
                    pvt[m] = pvt[m].astype(float).round(2)
            return pvt

        pvt = _rendimiento_pivot(df, anio_rend)

        if pvt.empty:
            st.info("No hay datos de rendimiento para el año seleccionado.")
        else:
            mes_map = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
                       7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
            # Renombra columnas de mes
            rename_cols = {m: mes_map[m] for m in range(1,13) if m in pvt.columns}
            pvt = pvt.rename(columns=rename_cols)
            month_cols = [mes_map[m] for m in range(1,13) if mes_map[m] in pvt.columns]

            # ---- Render expandible por Familia (+) ----
            familias = pvt["_Familia_"].astype(str).unique().tolist()
            familias = sorted(familias, key=lambda s: s.lower())

            def _style_family(df_fam: pd.DataFrame, fam: str):
                fam_norm = canon(fam)
                limits = RULES_KMKWH.get(fam_norm)
                # Construye mapa de formato
                fmt = {c: "{:.2f}" for c in month_cols}
                # Función de estilos por fila
                def _row_style(row: pd.Series):
                    out = []
                    for c in df_fam.columns:
                        v = row[c]
                        if c not in month_cols or pd.isna(v) or limits in (None, [], {}):
                             out.append("")
                        else:
                            low, high = limits
                            try:
                                fv = float(v)
                            except Exception:
                                out.append("")
                                continue
                            if fv < low:
                                out.append("background-color:#FFC7CE; color:#9C0006;")   # rojo
                            elif fv < high:
                                out.append("background-color:#FFEB9C; color:#9C6500;")  # amarillo
                            else:
                                out.append("background-color:#C6EFCE; color:#006100;")  # verde
                    return out

                return (df_fam.style
                            .format(fmt)
                            .apply(_row_style, axis=1))

            # Muestra por familia con “+”
            for fam in familias:
                df_fam = pvt.loc[pvt["_Familia_"] == fam].drop(columns=["_Familia_"]).copy()
            
                # 🔧 Renombrar la columna interna a etiqueta visible
                if "_Placa_" in df_fam.columns:
                     df_fam = df_fam.rename(columns={"_Placa_": "Placa"})

                # Fila de TOTAL FAMILIA (promedio de placas por mes)
                if not df_fam.empty:
                    tot_vals = df_fam[month_cols].mean(numeric_only=True)
                    total_row = pd.DataFrame([["TOTAL FAMILIA"] + [round(t, 2) for t in tot_vals.tolist()]], 
                                             columns=["Placa"] + month_cols)
                    df_fam = pd.concat([total_row, df_fam], ignore_index=True)

                with st.expander(f"➕ {fam}", expanded=False):
                    sty = _style_family(df_fam, fam)
                    st.dataframe(sty, use_container_width=True, hide_index=True)
    # ---------- Fin Rendimiento (km/kWh) por Placa y Mes ----------

    # ===============================================================
   
    st.subheader("Energía por Año y Usuario")

    # Selector de métrica (kWh o Costo) para las tablas
    metrica = st.radio(
        "Métrica a mostrar en tablas",
        options=["kWh", "Costo (S/)"],
        index=0,
        horizontal=True,
        key="energia_metric",
    )
    value_col = "__kwh__" if metrica == "kWh" else "__costo__"

    # Pivote Año × Usuario
    if "_Usuario_" in df.columns:
        pvt = (
            df.groupby(["Año", "_Usuario_"], dropna=False)[value_col]
              .sum()
              .unstack(fill_value=0.0)
              .sort_index()
        )
        pvt.index.name = "Año"
        pvt["Total general"] = pvt.sum(axis=1)
        tot_row = pd.DataFrame([pvt.sum(axis=0)], index=["Total general"])
        tot_row.index.name = "Año"
        pvt_tot = pd.concat([pvt, tot_row])
        df_show = pvt_tot.reset_index()

        num_cols = [c for c in df_show.columns if c != "Año"]
        df_show[num_cols] = df_show[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0)

        def style_totals(row: pd.Series):
            return [
                "font-weight: bold; background-color: #EAF8EC;" if str(row.get("Año")) == "Total general" else ""
                for _ in row
            ]

        fmt_map = {c: ("{:,.0f}" if value_col == "__kwh__" else "S/ {:,.2f}") for c in num_cols}
        styler = (
            df_show.style
                  .format(fmt_map)
                  .apply(style_totals, axis=1)
                  .set_table_styles([
                      {"selector": "th.col_heading", "props": "background-color:#EAF2FF; font-weight:bold;"},
                      {"selector": "th.row_heading", "props": "background-color:#F5F7FA; font-weight:bold;"},
                      {"selector": "tbody td", "props": "padding:6px 10px;"},
                      {"selector":"tbody tr:nth-child(even)","props":"background-color:#FBFBFD;"},
                  ])
                  .set_properties(
                      subset=pd.IndexSlice[:, ["Total general"]],
                      **{"font-weight": "bold", "background-color": "#70EA82"}
                  )
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)
    else:
        st.info("No se puede construir la tabla dinámica porque falta la columna **Usuario**.")
     


    # ============================
    # Tabla: Energía por Mes y Familia (filtro de Año)
    # ============================
    st.markdown("### Energía por Mes y Familia")

    if "_Familia_" not in df.columns:
        st.info("No se encontró la columna **Familia** en la hoja.")
    else:
        yrs = [int(y) for y in pd.to_numeric(df["Año"], errors="coerce").dropna().unique()]
        yrs = sorted(yrs)
        if len(yrs) == 0:
            st.info("No hay años disponibles en el rango/hoja actual.")
        else:
            idx_default = max(range(len(yrs)), key=lambda i: yrs[i])
            anio_sel = st.selectbox("Año", yrs, index=idx_default, key="anio_familia_energia")

            dfa = df[df["Año"] == anio_sel].copy()
            if fecha_col:
                dfa["Mes"] = pd.to_datetime(dfa[fecha_col], errors="coerce").dt.month
            else:
                dfa["Mes"] = 1

            mes_map = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
                       7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
            orden_meses = list(range(1, 12+1))

            pvt_f = (dfa.pivot_table(index="_Familia_", columns="Mes", values=value_col,
                                     aggfunc="sum", fill_value=0.0)
                       .reindex(columns=orden_meses, fill_value=0.0))
            pvt_f.columns = [mes_map[m] for m in pvt_f.columns]
            pvt_f.index.name = "Familia"

            pvt_f["Total general"] = pvt_f.sum(axis=1)
            total_row_f = pd.DataFrame([pvt_f.sum(axis=0)], index=["Total general"])
            pvt_f = pd.concat([pvt_f, total_row_f])

            df_show_f = pvt_f.reset_index()
            if "index" in df_show_f.columns:
                df_show_f = df_show_f.rename(columns={"index": "Familia"})
            num_cols_f = [c for c in df_show_f.columns if c != "Familia"]
            df_show_f[num_cols_f] = df_show_f[num_cols_f].apply(pd.to_numeric, errors="coerce").fillna(0)

            def style_total_row(row: pd.Series):
                return [
                    "font-weight:bold; background-color:#EAF8EC;"
                    if str(row.get("Familia")) == "Total general" else "" for _ in row
                ]

            fmt_map_f = {c: ("{:,.0f}" if value_col == "__kwh__" else "S/ {:,.2f}") for c in num_cols_f}
            sty_f = (df_show_f.style
                        .format(fmt_map_f)
                        .apply(style_total_row, axis=1)
                        .set_table_styles([
                            {"selector":"th.col_heading","props":"background-color:#EAF2FF; font-weight:bold;"},
                            {"selector":"th.row_heading","props":"background-color:#F5F7FA; font-weight:bold;"},
                            {"selector":"tbody td","props":"padding:6px 10px;"},
                            {"selector":"tbody tr:nth-child(even)","props":"background-color:#FBFBFD;"},
                        ])
                        .set_properties(
                            subset=pd.IndexSlice[:, ["Total general"]],
                            **{"font-weight": "bold", "background-color": "#70EA82"}
                        ))
            st.dataframe(sty_f, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ============================
    # GRÁFICO — kWh diario y promedio (por familia)
    # ============================
    st.markdown("### Gráfico — kWh diario promedio por vehículo (por familia)")

    if fecha_col is None or placa_col is None:
        st.info("No se encontró la columna de **Fecha** o **Placa** para construir el gráfico.")
    else:
        base = df.copy()
        base["_Fecha_"] = pd.to_datetime(base[fecha_col], errors="coerce")
        base = base.dropna(subset=["_Fecha_"]).copy()
        base["_Dia_"]  = base["_Fecha_"].dt.date
        base["_Anio_"] = base["_Fecha_"].dt.year.astype("Int64")
        base["_Mes_"]  = base["_Fecha_"].dt.month

        anios_disp = sorted([int(x) for x in base["_Anio_"].dropna().unique()])
        if len(anios_disp) == 0:
            st.info("No hay años disponibles para este gráfico con los filtros actuales.")
        else:
            cA, cM = st.columns([1,3])
            anio_sel = cA.selectbox("Año", anios_disp, index=len(anios_disp)-1, key="g_anio_en")

            meses_disp = sorted([int(x) for x in base.loc[base["_Anio_"] == anio_sel, "_Mes_"].dropna().unique()])
            meses_sel  = cM.multiselect(
                "Meses",
                options=meses_disp,
                default=meses_disp,
                key="g_meses_en",
            )

            # Familias (desde cubo cacheado)
            familias = sorted(daily_cube.loc[daily_cube["_Anio_"] == anio_sel, "_Familia_"].dropna().unique().tolist())
            if not familias:
                st.info("No hay familias para el año seleccionado.")
                st.stop()
            fam_sel  = st.selectbox("Familia", familias, index=0, key="g_familia_en")

            # Rebanada cacheada del cubo para (año, meses, familia)
            df_am = daily_cube[(daily_cube["_Anio_"] == anio_sel)]
            if meses_sel:
                df_am = df_am[df_am["_Mes_"].isin(meses_sel)]
            df_am = df_am[df_am["_Familia_"] == fam_sel]

            if df_am.empty:
                st.info("No hay datos para el año/mes/familia seleccionado.")
                st.stop()

            placas_all = sorted(df_am["Placa"].astype(str).unique().tolist())
            total_placas = len(placas_all)

            st.caption(
                f'<div style="margin-top:4px;margin-bottom:8px;"><b>Placas seleccionadas:</b> {total_placas} de {total_placas}</div>',
                unsafe_allow_html=True,
            )
            with st.expander("➕ Mostrar/ocultar lista de placas"):
                placas_sel = st.multiselect(
                    "Placas",
                    options=placas_all,
                    default=placas_all,
                    key="g_placas_en",
                )
            placas_sel = st.session_state.get("g_placas_en", placas_all)

            st.caption(
                f'<div style="margin-top:-4px;margin-bottom:6px;color:#6b7280;">{len(placas_sel)} de {total_placas} seleccionadas</div>',
                unsafe_allow_html=True,
            )

            if len(placas_sel) == 0:
                st.warning("Selecciona al menos una placa.")
                st.stop()

            diario_placa = df_am[df_am["Placa"].isin(placas_sel)].copy()
            if diario_placa.empty:
                st.info("No hay datos para las placas seleccionadas.")
                st.stop()

            # Serie diaria: promedio por vehículo
            serie_diaria = (
                diario_placa
                .groupby("Dia", as_index=False)["kWh"]
                .mean()
                .rename(columns={"Dia": "Fecha", "kWh": "kWh_por_vehiculo"})
            )

            total_kwh  = float(diario_placa["kWh"].sum())
            veh_dias   = int(len(diario_placa))
            prom_diario = (total_kwh / veh_dias) if veh_dias > 0 else 0.0
            dias_activos = int(serie_diaria["Fecha"].nunique())

            idxmax = diario_placa["kWh"].idxmax()
            if pd.isna(idxmax):
                max_txt = "0 kWh — —"
            else:
                fila = diario_placa.loc[idxmax]
                max_txt = f"{int(round(fila['kWh'])):,} kWh — {str(fila['Placa'])}".replace(",", ",")

            m1, m2, m3, m4 = st.columns([1,1,1,1.35])
            metric_card(m1, "Energía Total (kWh)", f"<span>{fmt_int(total_kwh)}</span>")
            metric_card(m2, "Promedio diario por vehículo (kWh)", f"<span>{fmt_int(prom_diario)}</span>")
            metric_card(m3, "Días activos", f"<span>{fmt_int(dias_activos)}</span>")
            metric_card(m4, "kWh máximo en 1 día", max_txt)

            PROM_COLOR = "#D32F2F"
            bars = (
                alt.Chart(serie_diaria)
                  .mark_bar()
                  .encode(
                      x=alt.X("Fecha:T", title="Tiempo (días)"),
                      y=alt.Y("kWh_por_vehiculo:Q", title="Promedio por vehículo (kWh)", axis=alt.Axis(format=",.0f")),
                      tooltip=[
                          alt.Tooltip("Fecha:T", title="Fecha"),
                          alt.Tooltip("kWh_por_vehiculo:Q", title="Promedio por vehículo (kWh)", format=",.0f"),
                      ],
                  )
            )
            rule = (
                alt.Chart(pd.DataFrame({"y": [prom_diario]}))
                  .mark_rule(color=PROM_COLOR, size=4, opacity=1)
                  .encode(y="y:Q")
            )
            label = (
                alt.Chart(pd.DataFrame({"y": [prom_diario]}))
                  .mark_text(
                      text=f"Promedio por vehículo: {prom_diario:,.0f} kWh",
                      dy=-10, dx=48, color=PROM_COLOR, fontWeight="bold", fontSize=13
                  )
                  .encode(y="y:Q", x=alt.value(8))
            )
            chart = (
                (bars + rule + label)
                .properties(height=380, width=1100)
                .configure_axis(labelFontSize=12, titleFontSize=13)
            )
            st.altair_chart(chart, use_container_width=False)

    # ------------------------------
    # Tamaño de bateria (debajo del gráfico)
    # ------------------------------
    st.subheader("Tamaño de Baterias")

    # Helper para encontrar la primera columna que exista
    def pick_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    fam_col   = pick_col(df, ["Familia", "FAMILIA"])
    bat_col   = pick_col(df, ["Tamaño de Bateria (kWh)", "Tamaño de Batería (kWh)", "Tamaño de Batería", "Tamano de Bateria (kWh)"])
    placa_col = pick_col(df, ["Placa", "PLACA"])

    faltan = [n for n, c in {
        "Familia": fam_col, 
        "Tamaño de Batería (kWh)": bat_col, 
        "Placa": placa_col
    }.items() if c is None]

    if faltan:
        st.warning("Faltan columnas en el DataFrame para esta tabla: " + ", ".join(faltan))
    else:
        datos_adic = (
            df[[fam_col, bat_col, placa_col]]
            .dropna(subset=[placa_col])
            .assign(
                **{
                    fam_col:   lambda x: x[fam_col].astype(str).str.strip(),
                    bat_col:   lambda x: x[bat_col].astype(str).str.strip(),
                    placa_col: lambda x: x[placa_col].astype(str).str.strip(),
                }
            )
            .groupby([fam_col, bat_col], as_index=False)[placa_col]
            .nunique()
            .rename(columns={
                fam_col: "Familias",
                bat_col: "Tamaño de Batería",
                placa_col: "Cantidad de Unidades"
            })
            .sort_values(["Familias", "Tamaño de Batería"])
        )

        st.dataframe(
            datos_adic,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Familias": st.column_config.TextColumn("Familias"),
                "Tamaño de Batería": st.column_config.TextColumn("Tamaño de Batería"),
                "Cantidad de Unidades": st.column_config.NumberColumn("Cantidad de Unidades", format="%d"),
            },
        )


    # ============================
    # Bandas de control por Familia (kWh/100 km) — 2 columnas
    # ============================
    st.markdown("---")
    st.markdown("### Consumos Anómalos — Bandas de control por Familia (kWh/100 km)")

    # Usamos las columnas normalizadas generadas en preprocess_energy
    placa_c = "_Placa_"    if "_Placa_"    in df.columns else placa_col
    fam_c   = "_Familia_"  if "_Familia_"  in df.columns else familia_col
    kwh_c   = "__kwh__"    if "__kwh__"    in df.columns else kwh_col
    km_c    = "__km__"     if "__km__"     in df.columns else km_col

    needed = [placa_c, fam_c, kwh_c, km_c]
    if any(c is None or c not in df.columns for c in needed):
        st.info("No se puede construir la banda: faltan columnas requeridas.")
    else:
        _base = (
            df[[placa_c, fam_c, kwh_c, km_c]]
            .dropna(subset=[placa_c])
            .assign(
                **{
                    placa_c: lambda x: x[placa_c].astype(str).str.strip(),
                    fam_c:   lambda x: x[fam_c].astype(str).str.strip(),
                }
            )
            .groupby([fam_c, placa_c], as_index=False, sort=False)
            .agg(kwh_tot=(kwh_c, "sum"), km_tot=(km_c, "sum"))
        )
        _base = _base.loc[_base["km_tot"] > 0].copy()

        if _base.empty:
            st.info("No hay recorridos > 0 km con los filtros actuales.")
        else:
            _base["kWh/100 km"] = (_base["kwh_tot"] / _base["km_tot"]) * 100.0
            _familias = sorted(_base[fam_c].dropna().unique().tolist(), key=lambda s: s.lower())

            c1, c2 = st.columns(2)

            def _chart_familia(df_fam: pd.DataFrame, titulo: str):
                mean = float(df_fam["kWh/100 km"].mean())
                std  = float(df_fam["kWh/100 km"].std(ddof=1)) if df_fam["kWh/100 km"].size > 1 else 0.0
                li, ls = mean - 2.0 * std, mean + 2.0 * std

                orden = df_fam.sort_values("kWh/100 km", kind="mergesort")[placa_c].tolist()

                band_src = pd.DataFrame({placa_c: orden, "y1": [li]*len(orden), "y2": [ls]*len(orden)})
                band = (
                    alt.Chart(band_src)
                    .mark_area(opacity=0.25, color="#ffc0cb")
                    .encode(
                        x=alt.X(f"{placa_c}:N", title="Placa", sort=orden,
                                axis=alt.Axis(labelLimit=80, labelAngle=-90)),
                        y=alt.Y("y1:Q", title="kWh/100 km"),
                        y2="y2:Q",
                    )
                )

                pts = (
                    alt.Chart(df_fam.assign(fuera=(df_fam["kWh/100 km"].gt(ls) | df_fam["kWh/100 km"].lt(li))))
                    .mark_point(size=70)
                    .encode(
                        x=alt.X(f"{placa_c}:N", sort=orden,
                                axis=alt.Axis(labelLimit=80, labelAngle=-90)),
                        y=alt.Y("kWh/100 km:Q"),
                        color=alt.condition(alt.datum.fuera, alt.value("red"), alt.value("#1f77b4")),
                        tooltip=[
                            alt.Tooltip(f"{placa_c}:N", title="Placa"),
                            alt.Tooltip("kWh/100 km:Q", title="kWh/100 km", format=",.2f"),
                        ],
                    )
                )

                outs = df_fam[df_fam["kWh/100 km"].gt(ls) | df_fam["kWh/100 km"].lt(li)]
                labels = (
                    alt.Chart(outs)
                    .mark_text(dy=-10, fontWeight="bold")
                    .encode(
                        x=alt.X(f"{placa_c}:N", sort=orden,
                                axis=alt.Axis(labelLimit=80, labelAngle=-90)),
                        y=alt.Y("kWh/100 km:Q"),
                        text=f"{placa_c}:N",
                    )
                ) if not outs.empty else alt.Chart(pd.DataFrame({"x": [], "y": []})).mark_text()

                rules = (
                    alt.Chart(pd.DataFrame({
                        "y": [li, mean, ls],
                        "tipo": ["Límite inferior (-2σ)", "Promedio", "Límite superior (+2σ)"],
                    }))
                    .mark_rule(strokeDash=[6, 3])
                    .encode(y="y:Q", color=alt.Color("tipo:N", legend=alt.Legend(title="Referencias")))
                )

                return (band + pts + labels + rules).properties(height=360, title=titulo)

            for i, fam in enumerate(_familias):
                sub = _base.loc[_base[fam_c] == fam, [placa_c, "kWh/100 km"]].copy()
                if sub.empty:
                    continue
                with (c1 if i % 2 == 0 else c2):
                    st.altair_chart(_chart_familia(sub, fam), use_container_width=True)


# ----------------------------
# DETALLE
# ----------------------------
with tab_detalle:
    st.subheader("Detalle (datos filtrados)")

    cols_show = []
    # Preferimos columnas originales si existen
    for c in [fecha_col, placa_col, usuario_col, familia_col, kwh_col, cost_col, km_col]:
        if c and c in df.columns and c not in cols_show:
            cols_show.append(c)
    # Derivadas útiles
    for c in ["Año", "_Mes_", "__kwh__", "__costo__", "__km__"]:
        if c in df.columns and c not in cols_show:
            cols_show.append(c)

    st.dataframe(
        df[cols_show] if cols_show else df,
        use_container_width=True,
        hide_index=True
    )

# ----------------------------
# EXPORTAR
# ----------------------------
with tab_export:
    st.subheader("Descargas")

    # CSV con los datos filtrados (lo que ves en pantalla)
    csv_filtrado = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar datos filtrados — CSV",
        data=csv_filtrado,
        file_name="energia_filtrado.csv",
        mime="text/csv",
        key="dl_energia_filtrado"
    )

    # CSV con toda la hoja original
    csv_full = df_full.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar hoja completa — CSV",
        data=csv_full,
        file_name="energia_hoja_completa.csv",
        mime="text/csv",
        key="dl_energia_full"
    )
