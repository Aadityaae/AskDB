"""Video decoration scoped to the account gate, with explicit cleanup."""
from pathlib import Path
import streamlit as st

_component = st.components.v2.component(
    'auth_background', js=Path(__file__).with_name('auth_background.js').read_text(),
    isolate_styles=False) if hasattr(st.components, 'v2') else None


def mount_auth_background(light=False):
    if _component:
        _component(data={'light': bool(light)}, key='auth_background', height=0)
