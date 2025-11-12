from pathlib import Path
from shutil import copy2

def _sync_if_newer(src: Path, dst: Path) -> bool:
    """Copia src→dst solo si src es más nuevo o dst no existe. Devuelve True si copió."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if (not dst.exists()) or (src.stat().st_mtime > dst.stat().st_mtime):
        copy2(src, dst)  # conserva fechas
        return True
    return False

def sync_from_settings(settings: dict) -> dict[str, bool]:
    """
    Lee settings['sources'] y copia a settings['data'] si hay cambios.
    Retorna {clave: True/False} según si copió.
    """
    results = {}
    sources = (settings or {}).get("sources", {})
    targets = (settings or {}).get("data", {})
    for key, src in sources.items():
        if key in targets:
            src_p = Path(src)
            # 'targets[key]' es relativo a streamlit_app/
            dst_p = Path("streamlit_app") / targets[key]
            results[key] = _sync_if_newer(src_p, dst_p)
    return results
