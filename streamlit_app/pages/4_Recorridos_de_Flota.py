# streamlit_app/pages/4_Recorridos_de_Flota_(km).py
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


from components.ui import header
from lib.config import load_settings
from lib.sync import sync_from_settings

# ============================
# Configuración de página
# ============================
st.set_page_config(
    page_title="Tecsur · Flota EV — Recorridos de Flota (km)",
    page_icon="🧭",
    layout="wide",
)

header_box = st.container()
messages_box = st.container()

with header_box:
    header("Recorridos de Flota (km)")

# --- Acciones (sidebar) ---
settings = load_settings()   # si ya lo tienes arriba, reutilízalo

with st.sidebar:
    st.subheader("Acciones")
    if st.button("🔄 Actualizar datos", use_container_width=True):
        # si sincronizas con OneDrive/SharePoint:
        sync_from_settings(settings)
        # limpia caché de DataFrames:
        st.cache_data.clear()
        # re-ejecuta la página:
        st.rerun()


# ============================
# Origen de datos
# ============================
XLSX_PATH  = Path(r"C:\Users\Enzo Morote\TECSUR S.A\Gestión Flota EV - Enzo - Documentos\Combustible_EV.xlsx")
SHEET_NAME = "Combustible EV"
SRC_NAME   = XLSX_PATH.name
messages_box.caption(f"Fuente: **{SRC_NAME}** (actualizado automático).")

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

def fmt_commas(v: float, decimals: int = 0) -> str:
    try:
        return f"{float(v):,.{decimals}f}"
    except Exception:
        return "0"

# --- helper para KPIs con coma ---
def miles(n):
    try:
        return f"{int(round(float(n))):,}"
    except Exception:
        return "0"

HAIR = "\u200a"  # (no usado ya, pero lo dejamos por si acaso)

def metric_text(col, label, value_str):
    safe = value_str.replace(",", ",\u200b")  # zero-width space tras cada coma
    col.markdown(f"""
    <div translate="no" style="padding:12px 16px;border:1px solid #e5e7eb;border-radius:10px;">
      <div style="color:#6b7280;font-size:0.9rem">{label}</div>
      <div style="font-weight:700;font-size:2.3rem;line-height:1.1; font-variant-numeric: tabular-nums;">
        <span translate="no">{safe}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

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

# ----------------- Caching de carga y preproceso -----------------
def _file_sig(p: Path):
    """Firma simple del archivo para invalidar caché si cambia."""
    try:
        stt = p.stat()
        return (stt.st_mtime, stt.st_size)
    except Exception:
        return (None, None)

@st.cache_data(show_spinner=False)
def load_xlsx_cached(path_str: str, sheet: str, sig):
    """Lee el Excel cacheado; se invalida si cambia (mtime/size)."""
    p = Path(path_str)
    return _safe_read_excel(p, sheet)

@st.cache_data(show_spinner=False)
def preprocess_base(df_in: pd.DataFrame, km_col: str | None, fecha_col: str | None,
                    usuario_col: str | None, familia_col: str | None) -> pd.DataFrame:
    """Normalización base cacheada: Año, __km__, _Usuario_, _Familia_."""
    df = df_in.copy()
    # Año
    if fecha_col:
        df[fecha_col] = pd.to_datetime(df[fecha_col], errors="coerce")
        # columnas derivadas (para no recalcular en cada interacción)
        df["_Fecha_"] = df[fecha_col]                 # datetime64[ns]
        df["_Dia_"]   = df["_Fecha_"].dt.date         # date puro
        df["_Anio_"]  = df["_Fecha_"].dt.year.astype("Int64")
        df["_Mes_"]   = df["_Fecha_"].dt.month
        # mantiene la columna 'Año' que usas en tablas
        df["Año"]     = df["_Anio_"]
    else:
        df["Año"] = pd.NA


    # Km
    if km_col and km_col in df.columns:
        df["__km__"] = df[km_col].apply(_to_number).fillna(0.0)
    else:
        df["__km__"] = 0.0
    # Usuario
    if usuario_col:
        df["_Usuario_"] = df[usuario_col].map(normaliza_usuario)
    else:
        df["_Usuario_"] = "—"
    # Familia
    if familia_col and familia_col in df.columns:
        df["_Familia_"] = df[familia_col].astype(str).str.strip().replace(r"\s+", " ", regex=True)
    return df


@st.cache_data(show_spinner=False)
def build_daily_cube(df_base: pd.DataFrame, placa_col: str, sig):
    # Índice para agregación diaria por placa
    idx = [placa_col, "_Dia_", "_Anio_", "_Mes_", "_Familia_"]
    daily = (
        df_base.groupby(idx, dropna=False)["__km__"]
               .sum()
               .reset_index()
               .rename(columns={"__km__": "Km", "_Dia_": "Dia", placa_col: "Placa"})
    )
    return daily


####
@st.cache_data(show_spinner=False)
def families_for_year(cube: pd.DataFrame, anio: int):
    vals = cube.loc[cube["_Anio_"] == anio, "_Familia_"].dropna().unique().tolist()
    return sorted(map(str, vals))

@st.cache_data(show_spinner=False)
def slice_cube(cube: pd.DataFrame, anio: int, meses: list[int], familia: str):
    m = (cube["_Anio_"] == anio) & (cube["_Familia_"] == familia)
    if meses:
        m &= cube["_Mes_"].isin(meses)
    return cube.loc[m, ["Dia", "Placa", "Km"]].copy()

@st.cache_data(show_spinner=False)
def plates_for_slice(cube: pd.DataFrame, anio: int, meses: list[int], familia: str):
    df = slice_cube(cube, anio, meses, familia)
    return sorted(df["Placa"].astype(str).unique().tolist())



# ---------------------------------------------------------------

def pick_km_column(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None
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

def normaliza_usuario(x: str) -> str:
    s = str(x or "").strip()
    s_low = canon(s)
    if "los andes" in s_low:            return "Los Andes"
    if s_low in {"lds"}:                return "LDS"
    if s_low in {"sud"}:                return "SUD"
    if "repart" in s_low:               return "Repartición"
    if "sin servicio" in s_low:         return "Sin servicio"
    if "tecsur" in s_low:               return "Tecsur"
    if "apim" in s_low:                 return "APIM"
    return s.title() if s else s

def normaliza_familia(x: str) -> str:
    s = str(x or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s if s else "—"

# ============================
# Carga de datos (cacheada)
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
# Normalización base (cacheada)
# ============================
fecha_col   = find_col(df_full, ["fecha"])
placa_col   = find_col(df_full, ["placa", "vehiculo", "unidad"])
usuario_col = find_col(df_full, ["usuario"])
familia_col = find_col(df_full, ["familia"])

km_col = pick_km_column(df_full)
for c in df_full.columns:
    if canon(c) == "recorrido (km)":
        km_col = c
        break

df_base = preprocess_base(df_full, km_col, fecha_col, usuario_col, familia_col)
daily_cube = build_daily_cube(df_base, placa_col, sig)



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
        f"Usando **{km_col or '—'}** como columna de kilómetros "
        f"y **{fecha_col or '—'}** como fecha."
    )

    # KPIs
    if "__km__" in df.columns and "Año" in df.columns:
        rec_2023 = float(df.loc[df["Año"] == 2023, "__km__"].sum())
        rec_2024 = float(df.loc[df["Año"] == 2024, "__km__"].sum())
        rec_2025 = float(df.loc[df["Año"] == 2025, "__km__"].sum())
    else:
        rec_2023 = rec_2024 = rec_2025 = 0.0
    placas_unicas = df[placa_col].nunique() if placa_col and (placa_col in df.columns) else 0

    c1, c2, c3, c4 = st.columns(4)
    metric_text(c1, "Recorridos 2023", miles(rec_2023))
    metric_text(c2, "Recorridos 2024", miles(rec_2024))
    metric_text(c3, "Recorridos 2025", miles(rec_2025))
    metric_text(c4, "Placas únicas",  miles(placas_unicas))

    st.markdown("---")
    st.subheader("Recorridos por Año y Usuario")

    # --- Pivote Año x Usuario ---
    if "_Usuario_" in df.columns:
        pvt = (
            df.groupby(["Año", "_Usuario_"], dropna=False)["__km__"]
              .sum()
              .unstack(fill_value=0)
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
        fmt_map = {c: "{:,.0f}" for c in num_cols}

        def style_totals(row: pd.Series):
            return [
                "font-weight: bold; background-color: #EAF8EC;" if str(row.get("Año")) == "Total general" else ""
                for _ in row
            ]

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
                   .set_properties(subset=pd.IndexSlice[:, ["Total general"]],**{"font-weight": "bold", "background-color": "#70EA82"})
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)
    else:
        st.info("No se puede construir la tabla dinámica porque falta la columna **Usuario**.")

    # ============================
    # SEGUNDO CUADRO: Recorridos por Mes y Familia (con filtro de Año)
    # ============================
    st.markdown("### Recorridos por Mes y Familia")

    familia_probe = find_col(df, ["familia"])
    if not familia_probe and "_Familia_" not in df.columns:
        st.info("No se encontró la columna **Familia** en la hoja.")
    else:
        if "_Familia_" not in df.columns and familia_probe:
            df["_Familia_"] = df[familia_probe].astype(str).str.strip().replace(r"\s+", " ", regex=True)

        yrs = [int(y) for y in pd.to_numeric(df["Año"], errors="coerce").dropna().unique()]
        yrs = sorted(yrs)
        if len(yrs) == 0:
            st.info("No hay años disponibles en el rango/hoja actual.")
        else:
            idx_default = max(range(len(yrs)), key=lambda i: yrs[i])
            anio_sel = st.selectbox("Año", yrs, index=idx_default, key="anio_familia")

            dfa = df[df["Año"] == anio_sel].copy()
            if fecha_col:
                dfa["Mes"] = pd.to_datetime(dfa[fecha_col], errors="coerce").dt.month
            else:
                dfa["Mes"] = 1

            mes_map = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
                       7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
            orden_meses = list(range(1, 13))

            pvt_f = (dfa.pivot_table(index="_Familia_", columns="Mes", values="__km__",
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

            sty_f = (df_show_f.style
                        .format({c: "{:,.0f}" for c in num_cols_f})
                        .apply(style_total_row, axis=1)
                        .set_table_styles([
                            {"selector":"th.col_heading","props":"background-color:#EAF2FF; font-weight:bold;"},
                            {"selector":"th.row_heading","props":"background-color:#F5F7FA; font-weight:bold;"},
                            {"selector":"tbody td","props":"padding:6px 10px;"},
                            {"selector":"tbody tr:nth-child(even)","props":"background-color:#FBFBFD;"},
                        ])
                        .set_properties(subset=pd.IndexSlice[:, ["Total general"]],**{"font-weight": "bold", "background-color": "#70EA82"}))
            st.dataframe(sty_f, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ============================
    # GRÁFICO — Recorrido diario y promedio (por familia)
    # (MOVIDO DENTRO DE tab_resumen)
    # ============================
    st.markdown("### Gráfico — Recorrido diario y promedio (por familia)")

    # --- Utilidades locales (solo para este bloque)
    def _safe_month_label(m: int) -> str:
        meses = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Ma\u200Byo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
        }
        return meses.get(m, str(m))

    def _metric_card(col, titulo: str, valor: str):
        col.markdown(
            f"""
            <div style="padding:12px 16px;border:1px solid #e5e7eb;border-radius:10px;">
              <div style="color:#6b7280;font-size:0.95rem">{titulo}</div>
              <div style="font-weight:700;font-size:2.0rem;line-height:1.15;">
                <span translate="no">{valor}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    base = df.copy()

    if fecha_col is None or placa_col is None:
        st.info("No se encontró la columna de **Fecha** o **Placa** para construir el gráfico.")
    else:
        base["_Fecha_"] = pd.to_datetime(base[fecha_col], errors="coerce")
        base = base.dropna(subset=["_Fecha_"]).copy()
        base["_Dia_"] = base["_Fecha_"].dt.date
        base["_Anio_"] = base["_Fecha_"].dt.year.astype("Int64")
        base["_Mes_"]  = base["_Fecha_"].dt.month

        anios_disp = sorted([int(x) for x in base["_Anio_"].dropna().unique()])
        if len(anios_disp) == 0:
            st.info("No hay años disponibles para este gráfico con los filtros actuales.")
        else:
            cA, cM = st.columns([1,3])
            anio_sel = cA.selectbox("Año", anios_disp, index=len(anios_disp)-1, key="g_anio")

            meses_disp = sorted([int(x) for x in base.loc[base["_Anio_"] == anio_sel, "_Mes_"].dropna().unique()])
            meses_sel  = cM.multiselect(
                "Meses",
                options=meses_disp,
                default=meses_disp,
                format_func=_safe_month_label,
                key="g_meses",
            )

            df_am = base[(base["_Anio_"] == anio_sel) & (base["_Mes_"].isin(meses_sel))]
            if df_am.empty:
                st.info("No hay datos para el año/mes seleccionado.")
                st.stop()

            if "_Familia_" not in df_am.columns:
                st.info("No se encontró la columna **Familia** en la hoja.")
                st.stop()


            # Familias desde el cubo (cacheado)
            familias = families_for_year(daily_cube, anio_sel)
            fam_sel  = st.selectbox("Familia", familias, index=0, key="g_familia")
     
            # Rebanada cacheada del cubo para (año, meses, familia)
            df_am = slice_cube(daily_cube, anio_sel, meses_sel, fam_sel)
            if df_am.empty:
                st.info("No hay datos para el año/mes seleccionado.")
                st.stop()

            # Ya viene filtrado por familia → no vuelvas a filtrar:
            df_fam = df_am.copy()

            # Placas desde la rebanada cacheada
            placas_all = plates_for_slice(daily_cube, anio_sel, meses_sel, fam_sel)
            total_placas = len(placas_all)


           # 5) UI de placas (¡esto es lo que tienes desde la línea 547 y debe quedarse!)
            placas_sel_default = placas_all
            st.caption(
                f'<div style="margin-top:4px;margin-bottom:8px;"><b>Placas seleccionadas:</b> {len(placas_sel_default)} de {total_placas}</div>',
                unsafe_allow_html=True,
            )
            with st.expander("➕ Mostrar/ocultar lista de placas"):
                placas_sel = st.multiselect(
                    "Placas",
                    options=placas_all,
                    default=placas_sel_default,
                    key="g_placas",
                )
            if "g_placas" in st.session_state and len(st.session_state["g_placas"]) > 0:
                placas_sel = st.session_state["g_placas"]
            else:
                placas_sel = placas_sel_default

            st.caption(
                f'<div style="margin-top:-4px;margin-bottom:6px;color:#6b7280;">{len(placas_sel)} de {total_placas} seleccionadas</div>',
                unsafe_allow_html=True,
            )

            if len(placas_sel) == 0:
                st.warning("Selecciona al menos una placa.")
                st.stop()

            df_fam = df_fam[df_fam[placa_col].astype(str).isin(placas_sel)].copy()
            if df_fam.empty:
                st.info("No hay datos para las placas seleccionadas.")
                st.stop()

 
            # df_fam ya viene de slice_cube con columnas: Dia, Placa, Km
            diario_placa = df_fam if len(placas_sel) == len(placas_all) else df_fam[df_fam["Placa"].isin(placas_sel)]
            if diario_placa.empty:
               st.info("No hay datos para las placas seleccionadas.")
               st.stop()



            # AHORA (promedio por vehículo en cada día)
            serie_diaria = (
                diario_placa
                .groupby("Dia", as_index=False)["Km"]
                .mean()
                .rename(columns={"Dia": "Fecha", "Km": "Km_por_vehiculo"})
            )



            total_km = float(diario_placa["Km"].sum())
            veh_dias = int(len(diario_placa))
            prom_diario = (total_km / veh_dias) if veh_dias > 0 else 0.0

            dias_activos = int(serie_diaria["Fecha"].nunique())

            idxmax = diario_placa["Km"].idxmax()
            if pd.isna(idxmax):
                max_txt = "0 km — —"
            else:
                fila = diario_placa.loc[idxmax]
                max_txt = f"{int(round(fila['Km'])):,} km — {str(fila['Placa'])}".replace(",", ",")

            m1, m2, m3, m4 = st.columns([1,1,1,1.35])
            _metric_card(m1, "Recorrido Total (km)", f"{int(round(total_km)):,}".replace(",", ","))
            _metric_card(m2, "Promedio diario por vehículo (km)", f"{int(round(prom_diario)):,}".replace(",", ","))
            _metric_card(m3, "Días activos", f"{dias_activos:,}".replace(",", ","))
            _metric_card(m4, "Recorrido máximo en 1 día", max_txt)

            #rom_line = float(serie_diaria["Km"].mean()) if not serie_diaria.empty else 0.0
            prom_line = float(prom_diario)


            bars = (
                alt.Chart(serie_diaria)
                  .mark_bar()
                  .encode(
                      x=alt.X("Fecha:T", title="Tiempo (días)"),
                      y=alt.Y("Km_por_vehiculo:Q", title="Promedio por vehículo (km)", axis=alt.Axis(format=",.0f")),
                      tooltip=[
                          alt.Tooltip("Fecha:T", title="Fecha"),
                          alt.Tooltip("Km_por_vehiculo:Q", title="Promedio por vehículo (km)", format=",.0f"),
                      ],
                  )
            )

            PROM_COLOR = "#D32F2F"
            rule = (
                alt.Chart(pd.DataFrame({"y": [prom_line]}))
                  .mark_rule(color=PROM_COLOR, size=4, opacity=1)
                  .encode(y="y:Q")
            )

            label = (
                alt.Chart(pd.DataFrame({"y": [prom_line]}))
                  .mark_text(
                      text=f"Promedio por vehículo: {prom_line:,.0f} km",
                      dy=-10, #vertical
                      dx=48, #empuja a la derecha
                      color=PROM_COLOR, fontWeight="bold", fontSize=13
                   )
                   .encode(y="y:Q", x=alt.value(8))
            )

            chart = (
                (bars + rule + label)
                .properties(height=380, width=1100)#<--tamaño fijo del gráfico.
                .configure_axis(labelFontSize=12, titleFontSize=13)
            )
            st.altair_chart(chart, use_container_width=False)#<--No responsivo

# ----------------------------
# DETALLE
# ----------------------------
with tab_detalle:
    st.subheader("Detalle (datos filtrados)")
    st.dataframe(df, use_container_width=True, hide_index=True)

# ----------------------------
# EXPORTAR
# ----------------------------
with tab_export:
    st.subheader("Descargas")

    csv_filtrado = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar datos filtrados — CSV",
        data=csv_filtrado,
        file_name="recorridos_filtrado.csv",
        mime="text/csv",
        key="dl_reco_filtrado"
    )

    csv_full = df_full.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar hoja completa — CSV",
        data=csv_full,
        file_name="recorridos_hoja_completa.csv",
        mime="text/csv",
        key="dl_reco_full"
    )
