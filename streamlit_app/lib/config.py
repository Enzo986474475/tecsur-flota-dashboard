# streamlit_app/lib/config.py
from pathlib import Path
import yaml
import streamlit as st

# Carpeta de la app: .../Automatizaciones-APP/streamlit_app
APP_DIR = Path(__file__).resolve().parents[1]
SETTINGS_FILE = APP_DIR / "config" / "settings.yaml"

@st.cache_resource(show_spinner=False)
def load_settings() -> dict:
    if not SETTINGS_FILE.exists() or not SETTINGS_FILE.is_file():
        raise FileNotFoundError(f"No encuentro settings.yaml en: {SETTINGS_FILE}")
    with SETTINGS_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def resolve_path(p: str | Path) -> Path:
    """Convierte rutas relativas del YAML a absolutas dentro de streamlit_app."""
    p = Path(p)
    return p if p.is_absolute() else (APP_DIR / p)
