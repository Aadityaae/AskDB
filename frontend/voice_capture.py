"""A single browser Start/Stop action, backed by the existing local speech API."""
from pathlib import Path
import streamlit as st
from voice import accept_recording

_capture = st.components.v2.component(
    'voice_capture',
    html='''<div class="voice-capture"><button class="voice-capture-button" type="button" aria-pressed="false">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></svg>
    <span>Use your voice</span></button><div class="voice-capture-status" role="status" aria-live="polite"></div></div>''',
    js=Path(__file__).with_name('voice_capture.js').read_text(encoding='utf-8'),
    isolate_styles=False,
)


def receive_audio():
    event = st.session_state.get('voice_capture', {})
    accept_recording(st.session_state, event.get('audio'))


def mount_voice_capture():
    _capture(key='voice_capture', data={'source': st.session_state.get('active_source', 'demo'),
                                     'revision': st.session_state.get('voice_capture_revision', 0)},
             on_audio_change=receive_audio)
