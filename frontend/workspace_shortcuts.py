"""Keyboard navigation for the authenticated query editor."""
from pathlib import Path
import streamlit as st

_shortcuts = st.components.v2.component('workspace_shortcuts',
    js=Path(__file__).with_name('workspace_shortcuts.js').read_text(),
    isolate_styles=False) if hasattr(st.components, 'v2') else None


def mount_workspace_shortcuts():
    if _shortcuts:
        _shortcuts(key='workspace_shortcuts', height=0)
