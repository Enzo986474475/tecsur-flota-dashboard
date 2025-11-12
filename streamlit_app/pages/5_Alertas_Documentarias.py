# streamlit_app/pages/5_Alertas_Documentarias.py
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import unicodedata as ud

import pandas as pd
import streamlit as st
import altair as alt
import openpyxl

from components.ui import header
from lib.config import load_settings
from lib.sync import sync_from_settings

# ---------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Tecsur · Flota EV — Alertas Documentales",
    page_icon="📄",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parents[1]
SHOW_DEBUG = False

header_box   = st.container()
messages_box = st.container()


# ------- Estilos para tablas (usar con Styler) -------
POS_BG = "#9DF571"   # color suave; prueba también "#E8F5E9" o "#E8F4FF"

def _fmt_currency(v):
    try:
        return f"S/. {float(v):,.2f}"
    except Exception:
        return v

def _bg_if_pos(v):
    try:
        return f"background-color: {POS_BG}" if float(v) > 0 else ""
    except Exception:
        return ""


# === Helpers de color para SOAT ===
def _bg_if_pos_red(v):
    """Rojo tenue si el valor > 0 (para 'Cantidad Soat Vencidos')."""
    try:
        return "background-color: #FDE2E2" if float(v) > 0 else ""
    except Exception:
        return ""

def _bg_if_pos_blue(v):
    """Celeste tenue si el valor > 0 (para 'Cantidad Soat Vigentes')."""
    try:
        return "background-color: #E8F4FF" if float(v) > 0 else ""
    except Exception:
        return ""



# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
SPANISH_MONTHS = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
]
MES_MAP = {
    "ene":"Enero","enero":"Enero","1":"Enero","01":"Enero",
    "feb":"Febrero","febrero":"Febrero","2":"Febrero","02":"Febrero",
    "mar":"Marzo","marzo":"Marzo","3":"Marzo","03":"Marzo",
    "abr":"Abril","abril":"Abril","4":"Abril","04":"Abril",
    "may":"Mayo","mayo":"Mayo","5":"Mayo","05":"Mayo",
    "jun":"Junio","junio":"Junio","6":"Junio","06":"Junio",
    "jul":"Julio","julio":"Julio","7":"Julio","07":"Julio",
    "ago":"Agosto","agosto":"Agosto","8":"Agosto","08":"Agosto",
    "sep":"Septiembre","sept":"Septiembre","septiembre":"Septiembre","9":"Septiembre","09":"Septiembre",
    "oct":"Octubre","octubre":"Octubre","10":"Octubre",
    "nov":"Noviembre","noviembre":"Noviembre","11":"Noviembre",
    "dic":"Diciembre","diciembre":"Diciembre","12":"Diciembre",
    # por si viniera en inglés:
    "january":"Enero","february":"Febrero","march":"Marzo","april":"Abril","june":"Junio",
    "july":"Julio","august":"Agosto","september":"Septiembre","october":"Octubre",
    "november":"Noviembre","december":"Diciembre"
}

# Normaliza distintos formatos de MES -> 'Enero'..'Diciembre'

def _norm_mes(val) -> str | None:
    if pd.isna(val):
        return None

    # 1) Si es número 1..12, mapear directo
    if isinstance(val, (int, float)) and 1 <= int(val) <= 12:
        return SPANISH_MONTHS[int(val) - 1]

    s = str(val).strip()
    if not s:
        return None

    # 2) Fecha -> mes
    ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.notna(ts):
        return SPANISH_MONTHS[int(ts.month) - 1]

    # 3) Número de mes dentro del string (p.ej. '03-2025')
    mnum = re.search(r"\b(1[0-2]|0?[1-9])\b", s)
    if mnum:
        return SPANISH_MONTHS[int(mnum.group(1)) - 1]

    # 4) Nombre/abreviatura del mes
    s_c = canon(s)
    return MES_MAP.get(s_c, None)


# Limpia 'Impuesto (S/)' a float, tolerando 'S/ 2,079.00', '1.234,56', etc.



def _to_amount(x) -> float:
    if pd.isna(x):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)

    s = str(x)

    # limpiar moneda y NBSP
    s = s.replace("\u00a0", "")
    s = s.replace("S/.", "").replace("S/", "").replace("s/.", "").replace("s/", "").strip()
    # dejar solo dígitos y separadores
    s = re.sub(r"[^\d.,\-]", "", s)

    # decidir separador decimal por el último separador presente
    if "." in s and "," in s:
        if s.rfind(".") > s.rfind(","):      # último '.' => estilo US  1,234.56
            s = s.replace(",", "")
        else:                                 # último ',' => estilo EU  1.234,56
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")               # 1234,56

    try:
        return float(s)
    except Exception:
        v = pd.to_numeric(s, errors="coerce")
        return float(v) if pd.notna(v) else 0.0



def canon(s: str) -> str:
    s = str(s or "").strip().lower()
    s = ''.join(ch for ch in ud.normalize('NFD', s) if ud.category(ch) != 'Mn')
    s = re.sub(r'[^a-z0-9\s_/.\-]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
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

def _try_read_excel(path: str | Path, sheet_candidates: list[str], skiprows: int) -> tuple[pd.DataFrame, str]:
    """Lee una hoja de Excel probando varios nombres. Devuelve (df, nombre_hoja_usado)."""
    last_exc = None
    for sh in sheet_candidates:
        try:
            df = pd.read_excel(path, sheet_name=sh, skiprows=skiprows)
            return df, sh
        except Exception as e:
            last_exc = e
    # fallback: intenta activa/Sheet1
    for sh in [0, "Sheet1"]:
        try:
            df = pd.read_excel(path, sheet_name=sh, skiprows=skiprows)
            return df, str(sh)
        except Exception as e:
            last_exc = e
    raise last_exc if last_exc else FileNotFoundError("No pude leer la hoja solicitada.")

def _cut_first_two_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[1] >= 2:
        return df.iloc[:, 2:].copy()
    return df.copy()

def _cut_until_col_name(df: pd.DataFrame, name_hints: list[str]) -> pd.DataFrame:
    """Conserva columnas desde el inicio hasta la PRIMERA que matchee (inclusive)."""
    if df.empty:
        return df
    target = find_col(df, name_hints)
    if target:
        idx = df.columns.get_loc(target)
        return df.iloc[:, : idx + 1].copy()
    return df

def _ensure_dates_and_status(df: pd.DataFrame, placa_keys: list[str], due_keys: list[str]) -> tuple[pd.DataFrame, dict]:
    """
    SOAT / ITV: estandariza a Placa, Fecha fin, Días restantes, Estado.
    """
    info = {}

    placa_col = find_col(df, placa_keys)
    due_col   = find_col(df, due_keys)

    if not placa_col or not due_col:
        return pd.DataFrame(), {"placa_col": placa_col, "due_col": due_col}

    base = df[[placa_col, due_col]].copy()
    base.rename(columns={placa_col: "Placa", due_col: "Fecha fin"}, inplace=True)

    base["Fecha fin"] = pd.to_datetime(base["Fecha fin"], errors="coerce").dt.date
    base["Días restantes"] = (pd.to_datetime(base["Fecha fin"]) - pd.to_datetime(date.today())).dt.days
    base["Días restantes"] = pd.to_numeric(base["Días restantes"], errors="coerce").astype("Int64")

    base["Estado"] = base["Fecha fin"].apply(
        lambda d: "Vencido" if (pd.notna(d) and d < date.today()) else "Vigente"
    )

    info.update({"placa_col": placa_col, "due_col": due_col})
    return base, info


# ---------------------------------------------------------------------
# Cargas específicas por documento
# ---------------------------------------------------------------------


def load_soat_df(xlsx_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dbg = {"path": str(xlsx_path)}
    SHEET_CANDS = ["Soat", "SOAT", "soat", 0]
    SKIP = 6

    df_raw, sheet_used = _try_read_excel(xlsx_path, SHEET_CANDS, SKIP)
    dbg["sheet_used"] = sheet_used
    if df_raw is None or df_raw.empty:
        dbg["error"] = "Hoja vacía o no encontrada"
        return pd.DataFrame(), pd.DataFrame(), dbg

    df_full = _cut_first_two_cols(df_raw)

    link_col = find_col(df_full, ["link"])
    if link_col:
        idx = df_full.columns.get_loc(link_col)
        df_full = df_full.iloc[:, : idx + 1].copy()
        df_full = df_full.drop(columns=[link_col], errors="ignore")

    col_placa = find_col(df_full, ["placa", "vehiculo", "unidad"])
    col_ini   = find_col(df_full, ["fecha ini", "fecha inicio"])
    col_fin   = find_col(df_full, ["fecha fin"])
    col_dias  = find_col(df_full, ["dias falt", "dias rest", "dias restantes"])

    if not col_placa or (not col_fin and not col_dias):
        return pd.DataFrame(), df_full, dbg

    work = df_full.copy()
    if col_ini: work[col_ini] = pd.to_datetime(work[col_ini], errors="coerce").dt.date
    if col_fin: work[col_fin] = pd.to_datetime(work[col_fin], errors="coerce").dt.date
    if not col_dias and col_fin:
        work["__dias_restantes__"] = (pd.to_datetime(work[col_fin]) - pd.to_datetime(date.today())).dt.days
        col_dias = "__dias_restantes__"

    out_cols = [c for c in [col_placa, col_ini, col_fin, col_dias] if c]
    df_alertas = work[out_cols].rename(columns={
        col_placa: "Placa",
        col_ini: "Fecha inicio" if col_ini else "Fecha inicio",
        col_fin: "Fecha fin" if col_fin else "Fecha fin",
        col_dias: "Días restantes" if col_dias else "Días restantes",
    })

    if "Fecha fin" in df_alertas.columns:
        df_alertas["Estado"] = df_alertas["Fecha fin"].apply(
            lambda d: "Vencido" if (pd.notna(d) and d < date.today()) else "Vigente"
        )
    else:
        df_alertas["Estado"] = df_alertas["Días restantes"].apply(
            lambda x: "Vencido" if pd.to_numeric(x, errors="coerce") < 0 else "Vigente"
        )

    if "Días restantes" in df_alertas.columns:
        df_alertas["Días restantes"] = pd.to_numeric(df_alertas["Días restantes"], errors="coerce").astype("Int64")

    return df_alertas, df_full, dbg


# ---------- SAT (Impuestos) – basado en Estatus Pendiente, no fechas ----------



def load_sat_df(xlsx_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Impuestos (SAT)
    - Hoja: "Impuestos-Sat" (con fallbacks).
    - skiprows=3, corta hasta 'Comprobante' inclusive.
    - Normaliza:
        * __imp_norm__  -> float desde la columna de importes (evitando 'Tipo Impuesto')
        * __mes_norm__  -> 'Enero'..'Diciembre' desde 'Mes' (número, fecha o texto)
    - Alertas: solo Estatus == 'Pendiente' con columnas ['Placa','Trimestre','Estatus','Año'] (si existen).
    """
    dbg = {"path": str(xlsx_path)}
    SHEET_CANDS = ["Impuestos-Sat", "Impuestos", "SAT", "Sat", "Impuesto", "Impuesto Vehicular"]
    SKIP = 3

    # Leer hoja
    df_raw, sheet_used = _try_read_excel(xlsx_path, SHEET_CANDS, SKIP)
    dbg["sheet_used"] = sheet_used
    if df_raw is None or df_raw.empty:
        dbg["error"] = "Hoja vacía o no encontrada"
        return pd.DataFrame(), pd.DataFrame(), dbg

    # Quitar columnas A y B; cortar hasta 'Comprobante' inclusive
    df_full = _cut_first_two_cols(df_raw)
    df_full = _cut_until_col_name(df_full, ["comprobante"])

    # --- detectar columnas principales ---
    mes_col = find_col(df_full, ["mes"])
    fam_col = find_col(df_full, ["familia"])

    # ===== DETECCIÓN ROBUSTA DE IMPORTE (evitando 'Tipo Impuesto') =====
    # 1) Patrones más específicos primero
    imp_col = None
    for pat in ["impuesto (s/)", "impuesto s/", "impuesto s/.", "impuesto (s/.)"]:
        c = find_col(df_full, [pat])
        if c:
            imp_col = c
            break

    # 2) Si no encontró, probar por candidatos y elegir el que tenga mayor suma numérica
    if not imp_col:
        candidates = []
        for c in df_full.columns:
            cc = canon(c)
            # incluir si menciona 'impuesto' pero NO 'tipo'
            if "impuesto" in cc and "tipo" not in cc:
                candidates.append(c)
            # incluir opciones como 'importe impuesto'
            elif "importe" in cc and ("imp" in cc or "impuesto" in cc):
                candidates.append(c)

        best, best_sum = None, -1.0
        for c in candidates:
            s = pd.Series(df_full[c]).apply(_to_amount)
            sm = float(s.sum(skipna=True))
            if sm > best_sum:
                best, best_sum = c, sm
        imp_col = best

    estatus_col = find_col(df_full, ["estatus", "estado"])
    anio_col    = find_col(df_full, ["año", "ano", "anio"])

    # --- normalizaciones ---
    if imp_col:
        df_full["__imp_norm__"] = df_full[imp_col].apply(_to_amount)
    else:
        dbg["warn"] = "No se encontró columna de importes (Impuesto (S/)). Revisa encabezado."
        df_full["__imp_norm__"] = 0.0

    if mes_col:
        df_full["__mes_norm__"] = df_full[mes_col].apply(_norm_mes)
    else:
        df_full["__mes_norm__"] = None

    if anio_col:
        df_full[anio_col] = pd.to_numeric(df_full[anio_col], errors="coerce").astype("Int64")

    # Guardar mapeo para usar en Resumen
    dbg["sat_cols"] = {
        "mes": mes_col,
        "mes_norm": "__mes_norm__",
        "familia": fam_col,
        "impuesto": imp_col,
        "imp_norm": "__imp_norm__",
        "estatus": estatus_col,
        "anio": anio_col,
    }

    # --- construir df_alertas (solo 'Pendiente') ---
    placa_col = find_col(df_full, ["placa", "placa vehiculo", "vehiculo", "unidad"])
    trim_col  = find_col(df_full, ["trimestre"])

    # Si falta placa o estatus, no se puede armar alertas (pero sí devolvemos df_full normalizado)
    if not placa_col or not estatus_col:
        return pd.DataFrame(), df_full, dbg

    cols_min = [c for c in [placa_col, trim_col, estatus_col, anio_col] if c]
    df_min = df_full[cols_min].copy()
    df_min.rename(
        columns={
            placa_col: "Placa",
            trim_col: "Trimestre" if trim_col else "Trimestre",
            estatus_col: "Estatus",
            anio_col: "Año" if anio_col else "Año",
        },
        inplace=True,
    )

    mask_pend = df_min["Estatus"].astype(str).str.strip().str.lower() == "pendiente"
    df_alertas = df_min[mask_pend].copy()

    keep_cols = [c for c in ["Placa", "Trimestre", "Estatus", "Año"] if c in df_alertas.columns]
    df_alertas = df_alertas[keep_cols] if keep_cols else pd.DataFrame()

    return df_alertas, df_full, dbg



def load_itv_df(xlsx_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dbg = {"path": str(xlsx_path)}
    SHEET_CANDS = ["ITV", "CITV", "Revisiones", "Revisión Técnica", "Revisiones Técnicas"]
    SKIP = 3

    df_raw, sheet_used = _try_read_excel(xlsx_path, SHEET_CANDS, SKIP)
    dbg["sheet_used"] = sheet_used
    if df_raw is None or df_raw.empty:
        dbg["error"] = "Hoja vacía o no encontrada"
        return pd.DataFrame(), pd.DataFrame(), dbg

    df_full = _cut_first_two_cols(df_raw)
    df_full = _cut_until_col_name(df_full, ["prox insp", "próx insp", "proxima insp", "próxima insp"])

    df_alertas, extra = _ensure_dates_and_status(
        df_full,
        placa_keys=["placa", "vehiculo", "unidad"],
        due_keys=["prox insp", "próx insp", "proxima insp", "próxima insp", "venc", "vencimiento"],
    )
    dbg.update(extra)

    return df_alertas, df_full, dbg

# ---------------------------------------------------------------------
# Header + settings + sync
# ---------------------------------------------------------------------
settings = load_settings()
sync_from_settings(settings)

with header_box:
    header("Alertas Documentales")



# --- Acciones (sidebar) ---
with st.sidebar:
    st.subheader("Acciones")
    if st.button("🔄 Actualizar datos", use_container_width=True):
        # Re-sincroniza (SharePoint/OneDrive) y limpia caché
        sync_from_settings(settings)
        st.cache_data.clear()
        st.rerun()


# Rutas / settings base
data_cfg   = settings.get("data", {}) or {}
soat_rel   = data_cfg.get("soats_src") or data_cfg.get("soats") or ""
soat_path  = (APP_DIR / soat_rel).resolve() if soat_rel and not Path(soat_rel).is_absolute() else Path(soat_rel)

# SharePoint URLs (botones por documento)
sp_cfg = settings.get("sharepoint", {}) or {}
SOAT_FOLDER_URL = sp_cfg.get(
    "soat_folder_url",
    "https://tecsurpe.sharepoint.com/sites/GestinFlotaEV-Enzo/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2FGestinFlotaEV%2DEnzo%2FDocumentos%20compartidos%2F2%2E%2DDocumentos%2FControl%20Documentario%2FSOAT&p=true&ga=1",
)
SAT_FOLDER_URL = sp_cfg.get(
    "sat_folder_url",
    "https://tecsurpe.sharepoint.com/sites/GestinFlotaEV-Enzo/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2FGestinFlotaEV%2DEnzo%2FDocumentos%20compartidos%2F2%2E%2DDocumentos%2FControl%20Documentario%2FSAT%2FPagos%20Impuesto%5FFlota&p=true&ga=1",
)
ITV_FOLDER_URL = sp_cfg.get(
    "itv_folder_url",
    "https://tecsurpe.sharepoint.com/sites/GestinFlotaEV-Enzo/Documentos%20compartidos/Forms/AllItems.aspx?id=%2Fsites%2FGestinFlotaEV%2DEnzo%2FDocumentos%20compartidos%2F2%2E%2DDocumentos%2FControl%20Documentario%2FITV%2F01%20ITV&p=true&ga=1",
)

# Umbrales por documento
thr_cfg = settings.get("thresholds", {}) or {}
SOAT_WARN_DEFAULT = int(thr_cfg.get("soat_warning_days", 30))
SAT_WARN_DEFAULT  = int(thr_cfg.get("sat_warning_days", 15))
ITV_WARN_DEFAULT  = int(thr_cfg.get("itv_warning_days", 30))

# ---------------------------------------------------------------------
# Selector de documento + filtros
# ---------------------------------------------------------------------
doc_choice = st.radio("Documento", ["SOAT", "SAT (Impuestos)", "ITV"], horizontal=True)

with st.sidebar:
    st.subheader("Filtros")
    placa_q = st.text_input("Buscar placa (opcional)")
    if doc_choice == "SOAT":
        warn_default = SOAT_WARN_DEFAULT
    elif doc_choice == "SAT (Impuestos)":
        warn_default = SAT_WARN_DEFAULT
    else:
        warn_default = ITV_WARN_DEFAULT
    warn_days = st.slider("Umbral de días", 1, 90, value=warn_default)
    only_alerts = st.checkbox("Mostrar solo alertas (vencidos o ≤ umbral)", value=True if doc_choice!="SAT (Impuestos)" else False)

src_name = soat_path.name if soat_rel else "_"
messages_box.caption(f"Fuente: **{src_name}** (actualizado automático). Umbral: **{warn_days}** días.")

# ---------------------------------------------------------------------
# Carga según documento
# ---------------------------------------------------------------------
error_text = ""
dbg_info = {}

# <<< Agrega estas dos líneas ANTES del try >>>
df_alertas: pd.DataFrame | None = None
df_full: pd.DataFrame | None = None



try:
    if doc_choice == "SOAT":
        df_alertas, df_full, dbg_info = load_soat_df(str(soat_path))
        folder_url = SOAT_FOLDER_URL
    elif doc_choice == "SAT (Impuestos)":
        df_alertas, df_full, dbg_info = load_sat_df(str(soat_path))
        folder_url = SAT_FOLDER_URL
    else:  # ITV
        df_alertas, df_full, dbg_info = load_itv_df(str(soat_path))
        folder_url = ITV_FOLDER_URL
except FileNotFoundError:
    error_text = f"No pude abrir el archivo: **{soat_path}**"
except Exception as e:
    error_text = f"Falla al leer el Excel: {e}"

if (df_alertas is None) and not error_text:
    error_text = "No pude construir las alertas. Revisa la hoja/encabezados/fechas."
if error_text:
    messages_box.error(error_text)
    st.stop()

# ---------------------------------------------------------------------
# Filtros y orden (según documento)
# ---------------------------------------------------------------------
current_year = date.today().year

if doc_choice == "SAT (Impuestos)":
    tmp = df_alertas.copy()
    # filtro de placa
    if placa_q and "Placa" in tmp.columns:
        tmp = tmp[tmp["Placa"].astype(str).str.contains(placa_q.strip(), case=False, na=False)]
    # quedarnos con pendientes
    if "Estatus" in tmp.columns:
        tmp = tmp[tmp["Estatus"].astype(str).str.strip().str.lower() == "pendiente"]
    # ordenar por Trimestre y Placa si existen
    sort_cols = [c for c in ["Año", "Trimestre", "Placa"] if c in tmp.columns]
    if sort_cols:
        tmp = tmp.sort_values(sort_cols, na_position="last")
else:
    tmp = df_alertas.copy()
    if placa_q:
        tmp = tmp[tmp["Placa"].astype(str).str.contains(placa_q.strip(), case=False, na=False)]
    if "Días restantes" in tmp.columns:
        vencidos = (tmp["Días restantes"] < 0).sum()
        le_7     = ((tmp["Días restantes"] >= 0) & (tmp["Días restantes"] <= 7)).sum()
        le_warn  = ((tmp["Días restantes"] >= 0) & (tmp["Días restantes"] <= warn_days)).sum()
        if only_alerts:
            tmp = tmp[(tmp["Días restantes"] <= warn_days) | (tmp["Días restantes"] < 0) | (tmp["Estado"] == "Vencido")]
    else:
        vencidos = (tmp["Estado"] == "Vencido").sum() if "Estado" in tmp.columns else 0
        le_7 = 0
        le_warn = 0
        if only_alerts and "Estado" in tmp.columns:
            tmp = tmp[tmp["Estado"] == "Vencido"]
    if "Días restantes" in tmp.columns:
        tmp = tmp.sort_values(["Días restantes", "Fecha fin"], ascending=[True, True], na_position="last")
    elif "Fecha fin" in tmp.columns:
        tmp = tmp.sort_values(["Fecha fin"], ascending=True, na_position="last")

# ---------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------
tab_resumen, tab_detalle, tab_export = st.tabs(["Resumen", "Detalle", "Exportar"])





with tab_resumen:
    # Botón a la carpeta del documento seleccionado
    st.link_button(
        f"📂 Abrir carpeta { 'SOAT' if doc_choice=='SOAT' else ('SAT' if doc_choice.startswith('SAT') else 'ITV') } (SharePoint)",
        folder_url
    )

    if doc_choice == "SAT (Impuestos)":
        # --- KPI único: Placas pendientes SAT (cuenta Estatus == 'Pendiente') ---
        if isinstance(tmp, pd.DataFrame) and "Estatus" in tmp.columns:
            pending = (tmp["Estatus"].astype(str).str.strip().str.lower() == "pendiente").sum()
        else:
            pending = len(tmp) if tmp is not None else 0

        st.metric(f"Placas pendientes SAT {date.today().year}", f"{pending:,}")

        # --- Tabla Familia x Mes sumando Impuesto (S/), excluyendo 'Pendiente' ---
        sat_cols = dbg_info.get("sat_cols", {}) if isinstance(dbg_info, dict) else {}
        fam_c    = sat_cols.get("familia")
        est_c    = sat_cols.get("estatus")
        mes_norm = sat_cols.get("mes_norm")   # '__mes_norm__' creado en load_sat_df
        imp_norm = sat_cols.get("imp_norm")   # '__imp_norm__' creado en load_sat_df

        if fam_c and mes_norm and imp_norm and (mes_norm in df_full.columns) and (imp_norm in df_full.columns):
            dfp = df_full.copy()

            # Excluir pendientes si existe columna estatus
            if est_c and est_c in dfp.columns:
                dfp = dfp[dfp[est_c].astype(str).str.strip().str.lower() != "pendiente"]

            # Filas válidas y asegurar numérico
            dfp = dfp[dfp[mes_norm].notna()]
            dfp[imp_norm] = pd.to_numeric(dfp[imp_norm], errors="coerce").fillna(0.0)

            # Pivote: Familia x Mes
            pivot = dfp.pivot_table(
                index=fam_c, columns=mes_norm, values=imp_norm, aggfunc="sum", fill_value=0.0
            )

            # Asegurar todas las columnas de meses y en orden
            pivot = pivot.reindex(columns=SPANISH_MONTHS, fill_value=0.0)
            # Total por fila (familia)
            pivot["Total"] = pivot.sum(axis=1)
            # Fila Total general
            total_row = pd.DataFrame([pivot.sum(numeric_only=True)], index=["Total"])
            pivot = pd.concat([pivot, total_row], axis=0)

            # Columnas numéricas a formatear/colorear (meses + Total que existan en el pivot)
            num_cols = [c for c in (SPANISH_MONTHS + ["Total"]) if c in pivot.columns]

            # Construimos un Styler con formato moneda y fondo suave si > 0
            styled = (
                pivot.style
                    .format(_fmt_currency, subset=num_cols)
                    .applymap(_bg_if_pos, subset=num_cols)
            )

            st.markdown("**Pagos por Familia y Mes (S/)**")
            st.dataframe(
                styled,
                use_container_width=True,
                hide_index=False,
                key="sat_pivot"
            )
        else:
            st.info("No encuentro columnas **Familia**, **Mes** e **Impuesto (S/)** en la hoja SAT.")

    else:
        # --- SOAT / ITV métricas ---
        if "Días restantes" in df_alertas.columns:
            #c1, c2, c3 = st.columns(3)
            #c1.metric("Vencidos", f"{(df_alertas['Días restantes'] < 0).sum():,}")
            #c2.metric("≤ 7 días", f"{((df_alertas['Días restantes'] >= 0) & (df_alertas['Días restantes'] <= 7)).sum():,}")
            #c3.metric(f"≤ {warn_days} días", f"{((df_alertas['Días restantes'] >= 0) & (df_alertas['Días restantes'] <= warn_days)).sum():,}")
            vencidos = int((df_alertas["Días restantes"] < 0).sum())
            label = "ITV vencidos" if doc_choice == "ITV" else "SOAT vencidos"
            st.metric("ITV Vencidos", f"{vencidos:,}")

        # --- SOAT — Resumen por Familia ---
        if doc_choice == "SOAT":
            fam_col = find_col(df_full, ["familia"])
            est_pol_col = find_col(
                df_full,
                ["estado poliza", "estado póliza", "estado soat", "estado poliza soat", "estado"]
            )

            if fam_col and est_pol_col:
                dfp = df_full[[fam_col, est_pol_col]].copy()

                # Normalizar valores de estado (vigente/vencido)
                est_norm = dfp[est_pol_col].astype(str).str.strip().str.lower()
                dfp["__estado__"] = est_norm.map(
                    lambda s: "Vencido" if "vencid" in s else ("Vigente" if "vigent" in s else None)
                )
                dfp = dfp.dropna(subset=["__estado__"])

                tabla = (
                    dfp.groupby([fam_col, "__estado__"])
                       .size()
                       .unstack(fill_value=0)
                       .rename(columns={
                           "Vencido": "Cantidad Soat Vencidos",
                           "Vigente": "Cantidad Soat Vigentes"
                       })
                )

                # Asegurar columnas y orden
                for col in ["Cantidad Soat Vencidos", "Cantidad Soat Vigentes"]:
                    if col not in tabla.columns:
                        tabla[col] = 0
                tabla = tabla[["Cantidad Soat Vencidos", "Cantidad Soat Vigentes"]].sort_index()

                # ➕ Agregar fila Total al final
                total_row = pd.DataFrame(
                    [[int(tabla["Cantidad Soat Vencidos"].sum()), int(tabla["Cantidad Soat Vigentes"].sum())]],
                    columns=tabla.columns,
                    index=["Total"]
                )
                tabla = pd.concat([tabla, total_row])

                # === Formato + colores: rojo tenue para Vencidos > 0; celeste tenue para Vigentes > 0 ===
                styled_soat = (
                    tabla.style
                         .format({
                             "Cantidad Soat Vencidos": "{:.0f}",
                             "Cantidad Soat Vigentes": "{:.0f}",
                         })
                         .applymap(_bg_if_pos_red,  subset=["Cantidad Soat Vencidos"])
                         .applymap(_bg_if_pos_blue, subset=["Cantidad Soat Vigentes"])
                )

                st.markdown("**SOAT — Resumen por Familia**")
                st.dataframe(
                    styled_soat,
                    use_container_width=True,
                    hide_index=False,
                    key="soat_resumen_familia"
                )
            else:
                st.info("No encuentro columnas **Familia** y **Estado Poliza** en la hoja SOAT.")

     

with tab_detalle:
    st.subheader("Detalle (vista para alertas)")
    if doc_choice == "SAT (Impuestos)":
        cols_show = [c for c in ["Placa", "Trimestre", "Estatus", "Año"] if c in tmp.columns]
        st.dataframe(tmp[cols_show] if cols_show else tmp, use_container_width=True, hide_index=True, key="sat_alertas_table")
    else:
        cols_show_detalle = [c for c in ["Placa", "Fecha inicio", "Fecha fin", "Días restantes", "Estado"] if c in tmp.columns]
        st.dataframe(
            tmp[cols_show_detalle] if cols_show_detalle else tmp,
            use_container_width=True, hide_index=True, key="alertas_table",
        )

    st.markdown("---")
    st.subheader("Detalle total")
    df_full_show = df_full.copy()
    link_col = find_col(df_full_show, ["link"])
    if link_col and link_col in df_full_show.columns:
        df_full_show = df_full_show.drop(columns=[link_col])
    st.dataframe(df_full_show, use_container_width=True, hide_index=True, column_config=None, key="full_table")

with tab_export:
    st.subheader("Descargas")
    if doc_choice == "SAT (Impuestos)":
        cols_export = [c for c in ["Placa", "Trimestre", "Estatus", "Año"] if c in tmp.columns]
    else:
        cols_export = [c for c in ["Placa", "Fecha inicio", "Fecha fin", "Días restantes", "Estado"] if c in tmp.columns]
    csv_alertas = (tmp[cols_export] if cols_export else tmp).to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar detalle (alertas) — CSV",
        data=csv_alertas,
        file_name=("soat" if doc_choice=="SOAT" else ("sat" if doc_choice.startswith("SAT") else "itv")) + "_alertas_filtrado.csv",
        mime="text/csv",
        key="dl_alertas_csv"
    )

    df_full_export = df_full.copy()
    link_col = find_col(df_full_export, ["link"])
    if link_col and link_col in df_full_export.columns:
        df_full_export = df_full_export.drop(columns=[link_col])
    csv_full = df_full_export.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar hoja completa — CSV",
        data=csv_full,
        file_name=("soat" if doc_choice=="SOAT" else ("sat" if doc_choice.startswith("SAT") else "itv")) + "_hoja_completa.csv",
        mime="text/csv",
        key="dl_full_csv"
    )

# Depurador opcional
if SHOW_DEBUG and dbg_info:
    with st.expander("Depurar (lo que encontré)", expanded=False):
        st.json(dbg_info)
