"""Decorative effects; no user data is sent to JavaScript."""
from pathlib import Path
import streamlit as st

effect_component = st.components.v2.component('studio_effects',
    js=Path(__file__).with_name('effects.js').read_text(), isolate_styles=False) if hasattr(st.components, 'v2') else None


def mount_effects(enabled):
    if effect_component:
        effect_component(data={'enabled': bool(enabled)}, key='studio_effects', height=0)
