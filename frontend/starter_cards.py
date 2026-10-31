"""Single-element suggestion cards with stable layout and native button behavior."""
from pathlib import Path
import streamlit as st

_cards = st.components.v2.component(
    'starter_cards', html='<div class="starter-cards" aria-label="Suggested questions"></div>',
    js=Path(__file__).with_name('starter_cards.js').read_text(encoding='utf-8'),
    isolate_styles=False,
)


def select_question():
    event = st.session_state.get('starter_cards', {}).get('selected')
    current = st.session_state.get('_starter_questions', {})
    if not isinstance(event, dict) or event.get('source') != st.session_state.get('active_source', 'demo'):
        return
    index = event.get('index')
    questions = current.get('questions', [])
    if current.get('source') == event['source'] and type(index) is int and 0 <= index < len(questions):
        st.session_state['question_input'] = questions[index]


def render_starter_cards(suggestions):
    source = st.session_state.get('active_source', 'demo')
    st.session_state['_starter_questions'] = {'source': source, 'questions': [q for _, q in suggestions]}
    _cards(key='starter_cards', data={'source': source, 'items': [{'title': t, 'question': q} for t, q in suggestions]},
           on_selected_change=select_question)
