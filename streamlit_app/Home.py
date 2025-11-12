# streamlit_app/Home.py
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st

from components.ui import header
from lib.config import load_settings
from lib.data import load_excel, kpis_home
from lib.sync import sync_from_settings

# --------- intentar importar resolve_path; si no existe, definimos uno local ----------
try:
    from lib.config import resolve_path  # type: ignore
except Exception:
    APP_DIR_FALLBACK = Path(__file__).resolve().parent
    def resolve_path(p):  # fallback mínimo
        p = Path(p)
        return p if p.is_absolute() else (APP_DIR_FALLBACK / p)
# -------------------------------------------------------------------------------------

# --- Config de página ---
st.set_page_config(
    page_title="Tecsur · Flota EV — Home",
    page_icon="🚗",
    layout="wide",
)

# --- Carga settings + sync ---
settings = load_settings()
sync_from_settings(settings)

APP_DIR = Path(__file__).resolve().parent
ASSETS = APP_DIR / "assets"
VIDEO = ASSETS / "home_demo.mp4"

# --- Header ---
header("Inicio (Home)")

# --- Sidebar: filtros globales ---
with st.sidebar:
    st.subheader("Filtros")
    fecha_ini, fecha_fin = st.date_input(
        "Rango de fechas",
        value=(date.today().replace(day=1), date.today()),
    )
    st.selectbox("Cliente", ["Todos", "Luz del Sur", "Los Andes"])
    st.text_input("Buscar por placa (opcional)")
    st.toggle("Usar datos de ejemplo", value=True)
    st.button("Actualizar datos")

# --- Rutas desde settings.yaml (¡claves correctas!) ---
rec_rel  = settings.get("data", {}).get("recorridos_maestro", "")
soat_rel = settings.get("data", {}).get("soats_src", "")  # <- esta es la buena

rec_path  = resolve_path(rec_rel)  if rec_rel  else None
soat_path = resolve_path(soat_rel) if soat_rel else None

def safe_load_xlsx(p: Path | None) -> pd.DataFrame:
    """Devuelve DF vacío y muestra mensaje si la ruta no es válida."""
    if not p:
        st.warning("Ruta no configurada en settings.yaml.")
        return pd.DataFrame()
    if p.is_dir():
        st.error(f"Esperaba un archivo, pero es carpeta: {p}")
        return pd.DataFrame()
    if not p.exists():
        st.error(f"No existe el archivo: {p}")
        return pd.DataFrame()
    return load_excel(str(p))

rec_df  = safe_load_xlsx(rec_path)
soat_df = safe_load_xlsx(soat_path)

# --- Umbral SOAT ---
warn_days = settings.get("thresholds", {}).get("soat_warning_days", 30)

# --- KPIs ---
kpis = kpis_home(rec_df, soat_df, fecha_ini, fecha_fin, soat_warn_days=warn_days)

# --- Sección HERO: KPIs + Video ---
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("KPIs rápidos")
    c1, c2, c3, c4 = st.columns(4)
    disp_txt = "—" if kpis["disp_pct"] is None else f'{kpis["disp_pct"]:.1%}'
    c1.metric("Disponibilidad % (mes)", disp_txt)
    c2.metric("Km recorridos (mes)", f'{kpis["km_mes"]:.0f}')
    c3.metric(f"SOAT ≤{warn_days} días", f'{kpis["soat_alertas"]}')
    c4.metric("km/kWh promedio", "—" if kpis["km_por_kwh"] is None else f'{kpis["km_por_kwh"]:.2f}')

with right:
    st.subheader("Video de bienvenida")
    if VIDEO.exists():
        st.video(str(VIDEO))
    else:
        st.info("No encontré assets/home_demo.mp4. Añade el MP4 o pega un enlace de YouTube.")

st.divider()
st.subheader("Gráficos rápidos (pendiente)")
st.write("• Línea: Disponibilidad diaria (últimos 30 días)")
st.write("• Barras: Km por familia de vehículo (mes filtrado)")

st.subheader("Alertas rápidas")
st.write("• SOAT ≤30 días: —  • CITV ≤30 días: —  • Mantenimientos vencidos: —")

st.caption("v0.1 · Contacto: soporte Tecsur")
