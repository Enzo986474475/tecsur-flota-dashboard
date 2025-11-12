from pathlib import Path
import streamlit as st

def header(title: str):
    app_dir = Path(__file__).resolve().parents[1]  # .../streamlit_app
    logo = app_dir / "assets" / "logo_tecsur.png"

    c1, c2, c3 = st.columns([1,5,2], gap="small")
    with c1:
        if logo.exists():
            st.image(str(logo), use_container_width=True)
        else:
            st.write("**TECSUR**")
    with c2:
        st.markdown("### Tecsur · Flota EV")
        st.markdown(f"## **{title}**")
    with c3:
        st.caption("Última actualización: **hoy**")
    st.divider()
