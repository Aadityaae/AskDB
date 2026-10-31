"""A decorative sliding selection indicator; native navigation stays in control."""
from pathlib import Path
import streamlit as st

_motion = st.components.v2.component(
    'navigation_motion', js=Path(__file__).with_name('navigation_motion.js').read_text(encoding='utf-8'),
    isolate_styles=False,
)


def mount_navigation_motion(page, enabled):
    _motion(key='navigation_motion', data={'page': page, 'enabled': bool(enabled)}, height=0)
