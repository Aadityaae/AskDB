"""Landscape background for the authenticated workspace only."""
from pathlib import Path
import streamlit as st

_background = st.components.v2.component('dashboard_background',
    js=Path(__file__).with_name('dashboard_background.js').read_text(),
    isolate_styles=False) if hasattr(st.components, 'v2') else None


def mount_dashboard_background(motion=True, light=False):
    if _background:
        _background(data={'motion': bool(motion), 'light': bool(light)},
                    key='dashboard_background', height=0)
