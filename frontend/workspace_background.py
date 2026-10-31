"""Small CSS ambience layer with visibility-aware animation playback."""
from pathlib import Path
import streamlit as st

_background = st.components.v2.component(
    'workspace_background',
    js=Path(__file__).with_name('workspace_background.js').read_text(encoding='utf-8'),
    isolate_styles=False,
)


def mount_workspace_background(motion):
    _background(data={'motion': bool(motion)}, key='workspace_background', height=0)
