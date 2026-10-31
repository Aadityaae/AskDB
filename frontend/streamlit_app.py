"""A calm local analytics workbench with progressive disclosure of technical detail."""
import os
import uuid
import math
from time import monotonic
from urllib.parse import quote
from html import escape
from pathlib import Path
import httpx
import pandas as pd
import streamlit as st
from voice import transcribe_voice as update_voice_draft
from voice_capture import mount_voice_capture
from starter_cards import render_starter_cards
from navigation_motion import mount_navigation_motion
from exports import export_csv
from charts import render_charts
from accounts import require_login, sign_out
from brand import MARK_PATH
from api_client import request as api_request
from workspace_shortcuts import mount_workspace_shortcuts
from entrypoint import enter_from_homepage

st.set_page_config(page_title='AskDB · Your data. Just ask.', page_icon=str(MARK_PATH), layout='wide', initial_sidebar_state='collapsed')
enter_from_homepage()
API = os.getenv('API_BASE_URL', 'http://localhost:8000')
with st.container(key='base_style_assets'):
    st.markdown('<style>.st-key-base_style_assets{display:none!important;}'
                + Path(__file__).with_name('styles.css').read_text(encoding='utf-8')
                + Path(__file__).with_name('brand.css').read_text(encoding='utf-8')
                + '</style>', unsafe_allow_html=True)
require_login(API)
st.session_state.setdefault('session_id', str(uuid.uuid4()))
st.session_state.setdefault('page', 'Query')
st.session_state.setdefault('active_source', 'demo')
if st.session_state['page'] == 'Evaluation':
    st.session_state['page'] = 'Query'


def markup(content):
    st.markdown(content, unsafe_allow_html=True)


def page_heading(kicker, title, description):
    markup(f'<div class="page-heading"><div class="eyebrow">{escape(kicker)}</div>'
           f'<h1>{escape(title)}</h1><p>{escape(description)}</p></div>')


def call(method, path, payload=None):
    # Keep schema/status reads local to this authenticated Streamlit session.
    # Records and personal history remain live, and auth is checked on every rerun.
    source_id = st.session_state.get('active_source', 'demo')
    if method == 'POST' and path == '/v1/query':
        payload = {**payload, 'source_id': source_id}
    if method == 'GET' and (path == '/v1/schema' or path.startswith('/v1/data/')) and source_id != 'demo':
        path += ('&' if '?' in path else '?') + 'source_id=' + source_id
    route = path.split('?', 1)[0]
    ttl = {'/v1/schema': 60, '/v1/health': 15, '/v1/sources': 20}.get(route, 0) if method == 'GET' else 0
    if route == '/v1/sources' and (st.session_state.get('page') == 'Sources' or 'pending_source' in st.session_state):
        ttl = 0  # Imports and the database-management page always fetch a fresh list.
    cache = st.session_state.setdefault('_api_read_cache', {})
    if ttl and path in cache and monotonic() - cache[path][0] < ttl:
        return cache[path][1]
    try:
        response = api_request(method, API, path, json=payload, headers={'Authorization': 'Bearer ' + st.session_state['auth_token']}, timeout=600 if path == '/v1/query' else 25)
        response.raise_for_status()
        result = response.json()
        if ttl:
            cache[path] = (monotonic(), result)
        return result
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get('detail', 'The request could not be completed.')
        except ValueError:
            detail = 'The request could not be completed.'
        st.error(detail)
    except httpx.RequestError:
        st.error('The workspace cannot reach the API. Check that the backend is running.')
    return None


def set_question(question):
    st.session_state['question_input'] = question


def transcribe_voice():
    # Callbacks finish before Streamlit can paint progress. Queue the work instead.
    st.session_state['voice_pending'] = True


def reopen(item):
    item = call('GET', f'/v1/history/{item["id"]}')
    if not item:
        return
    st.session_state['active_source'] = item.get('source_id', 'demo')
    source_changed()
    st.session_state['result'] = item
    st.session_state['question_input'] = item['question']
    st.session_state['page'] = 'Query'
    st.session_state['clarification'] = item.get('clarification')


def run(question, sql=None, clarification=None):
    pending = st.empty()
    pending.markdown('''<div class="query-loading" role="status" aria-live="polite"><div class="loader-art" aria-hidden="true">
    <div class="loader-track"></div><div class="loader-core"><i></i><i></i><i></i><i></i></div>
    <span class="loader-particle particle-one"></span><span class="loader-particle particle-two"></span></div>
    <div class="loader-copy"><div class="loader-eyebrow">CURIOSITY IN MOTION</div><h3>Connecting the dots<span class="loading-dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></h3>
    <p>Generating SQL and checking your answer against the database.</p><span class="loader-note">Good answers are worth a little investigation.</span></div>
    <div class="loader-signal" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div></div>''', unsafe_allow_html=True)
    try:
        result = call('POST', '/v1/query', {'question': question, 'sql': sql,
                      'clarification': clarification, 'session_id': st.session_state.session_id})
    finally:
        pending.empty()
    if result:
        st.session_state['result'] = result
        st.session_state['clarification'] = clarification
        st.rerun()


def status_label(status):
    return {'success': 'Ready', 'low_confidence': 'Needs review', 'blocked': 'Blocked',
            'clarification_required': 'Clarification needed', 'validation_failed': 'Validation failed',
            'execution_failed': 'Could not complete'}.get(status, status.replace('_', ' ').title())


def show_result(result):
    st.caption("DATA SOURCE · " + result.get("source_name", "Demo database"))
    markup('<div class="section-divider"></div>')
    if result['status'] == 'clarification_required':
        st.subheader('A little more context')
        st.caption('Choose the interpretation you intended before we run a query.')
        option = st.radio('Interpretation', result['options'], index=None) if len(result['options']) > 1 else None
        if len(result['options']) == 1:
            st.info(result['options'][0])
        context = st.text_input('Additional context', placeholder='For example: completed orders, after discounts, for 2025', key=f'context_{result.get("id")}')
        if st.button('Continue', type='primary'):
            if option or context.strip():
                run(result['question'], clarification=' '.join(part for part in (option, context.strip()) if part))
            else:
                st.info('Choose an interpretation or add the missing details first.')
        return
    left, right = st.columns([4, 1], vertical_alignment='center')
    with left:
        markup('<div class="eyebrow">QUERY RESULT</div>')
        st.subheader('Here’s what we found' if result['results'] else 'Query details')
        st.caption('Results for: ' + result['question'])
        if result.get('clarification'):
            st.caption('Context: ' + result['clarification'])
    with right:
        tone = 'success' if result['status'] == 'success' else ('danger' if result['status'] in ('blocked', 'execution_failed', 'validation_failed') else 'review')
        markup(f'<div class="status-pill {tone}">{escape(status_label(result["status"]))}</div>')
    if result['reason']:
        st.error(result['reason'])
    rows = result['results']
    frame = pd.DataFrame(rows) if rows else None
    if len(rows) == 1 and len(rows[0]) == 1:
        label, value = next(iter(rows[0].items()))
        with st.container(border=True, key='scalar_result'):
            formatted = f'{value:,}' if isinstance(value, (int, float)) else str(value)
            markup(f'<div class="scalar-label">{escape(label.replace("_", " ").title())}</div>'
                   f'<div class="scalar-value">{escape(formatted)}</div>')
    elif result['answer']:
        st.write(result['answer'])
    if result['status'] == 'low_confidence':
        st.caption('Needs review: the result ran safely, but the validation evidence is limited. See Validation for details.')
    visuals_tab, results_tab, sql_tab, validation_tab = st.tabs(['Visuals', 'Data', 'SQL', 'Validation'])
    with visuals_tab:
        if rows:
            render_charts(frame, f'{result.get("id")}_{hash(tuple(rows[0]))}')
            st.caption('Visuals reflect the query result, including its filters and row limit. Check SQL and Validation when an answer needs review.')
        else:
            st.caption('Run a question that returns records to see a visual.')
    with results_tab:
        if rows:
            st.dataframe(frame, width='stretch', hide_index=True)
            meta, download = st.columns([4, 1], vertical_alignment='center')
            meta.caption(f"{result['row_count']:,} rows · {result['execution_time_ms']:,.0f} ms database execution")
            with download:
                st.download_button('Export CSV', export_csv(frame), 'results.csv', 'text/csv', width='stretch', on_click='ignore')
        else:
            st.caption('No result rows to display.')
    with sql_tab:
        if result['explanation']:
            st.write(result['explanation'])
        st.caption('Inspect or refine the SQL. Edited queries go through the same safety checks.')
        edited = st.text_area('SQL editor', result['sql'], height=230, key=f"sql_{result.get('id')}_{hash(result['sql'])}")
        if st.button('Validate & run', type='primary'):
            run(result['question'], sql=edited, clarification=st.session_state.get('clarification'))
    with validation_tab:
        signals = result['confidence']
        if signals:
            score, explanation = st.columns([1, 3], vertical_alignment='center')
            score.metric('Confidence', f"{signals['overall']:g} / 100")
            explanation.caption('An evidence score, not a probability of correctness. Unavailable checks contribute zero.')
            labels = [('syntax', 'SQL safety', '15%'), ('back_translation', 'Meaning match', '30%'),
                      ('sanity', 'Result sanity', '20%'), ('agreement', 'Query agreement', '25%'),
                      ('schema_coverage', 'Schema coverage', '10%')]
            for name, label, weight in labels:
                value = signals.get(name)
                text, bar, number = st.columns([2, 3, 1], vertical_alignment='center')
                text.write(label)
                bar.progress(min(1.0, max(0.0, value or 0)))
                number.caption(f'{value * 100:.0f}% · {weight} weight' if value is not None else 'Unavailable')
        checks = {name: value for name, value in result['validation'].items() if name in ('syntax', 'guardrails', 'schema', 'cost')}
        if checks:
            st.caption(' · '.join(f'{name.title()}: {value}' for name, value in checks.items()))
        for warning in result['warnings']:
            st.warning(warning)
    if result.get('id'):
        with st.expander('Give feedback'):
            with st.form(f"feedback_{result['id']}"):
                correct = st.radio('Was this answer correct?', ['Correct', 'Incorrect'], horizontal=True, index=None)
                comment = st.text_input('Optional comment', placeholder='What worked, or what should change?')
                if st.form_submit_button('Save feedback'):
                    if correct is None:
                        st.info('Choose Correct or Incorrect before saving feedback.')
                    elif call('POST', '/v1/feedback', {'query_id': result['id'], 'correct': correct == 'Correct', 'comment': comment}):
                        st.success('Feedback saved. Thank you.')


def source_changed():
    for key in list(st.session_state):
        if key in ('result', 'clarification', 'question_input', 'data_table', 'data_limit_cap', 'voice_digest', 'voice_notice', 'voice_recording', 'voice_pending', 'voice_open', '_api_read_cache') or key.startswith('data_page_'):
            st.session_state.pop(key, None)


sources = call('GET', '/v1/sources')
source_items = sources['items'] if sources else [{'id': 'demo', 'name': 'Demo database', 'kind': 'demo'}]
source_names = {item['id']: item['name'] for item in source_items}
if 'pending_page' in st.session_state:
    st.session_state['page'] = st.session_state.pop('pending_page')
if 'pending_source' in st.session_state:
    st.session_state['active_source'] = st.session_state.pop('pending_source')
    source_changed()
if st.session_state['active_source'] not in source_names:
    if not sources:
        st.error('Your data sources could not be loaded. Retry when the API is connected.')
        st.stop()
    st.session_state['active_source'] = 'demo'
    source_changed()


if st.session_state.get('workspace_theme_version') != 'sunny-dark-default-v1':
    st.session_state['light_mode'] = False
    st.session_state['workspace_theme_version'] = 'sunny-dark-default-v1'
labels = {'Query': 'Ask', 'Data': 'Explore', 'Schema': 'Schema',
          'History': 'Archive', 'Sources': 'Databases', 'System': 'Status'}


def navigate_workspace():
    destination = st.session_state.get('workspace_destination')
    if destination in labels:
        st.session_state['page'] = destination
    else:
        st.session_state['workspace_destination'] = st.session_state['page']


st.session_state['workspace_destination'] = st.session_state['page']
with st.container(key='workspace_nav'):
    brand_col, nav_col, theme_col, account_col = st.columns([1.1, 4.7, .9, 1.1], vertical_alignment='center', gap='small')
    with brand_col:
        markup('<div class="workspace-wordmark" aria-label="AskDB">Ask<span>DB</span><i aria-hidden="true">.</i></div>')
    with nav_col:
        st.segmented_control('Navigation', list(labels), key='workspace_destination', format_func=labels.get,
                             on_change=navigate_workspace, label_visibility='collapsed')
        page = st.session_state['page']
    with theme_col:
        light_mode = st.toggle('Light mode', key='light_mode')
    with account_col:
        with st.popover('Account', icon=':material/tune:', width='stretch'):
            st.caption('SIGNED IN AS')
            st.write(st.session_state['auth_user']['name'])
            motion = st.toggle('Motion effects', value=True, key='motion_effects')
            st.button('Sign out', on_click=sign_out, args=(API,), width='stretch')
with st.container(key='workspace_style_assets'):
    if light_mode:
        markup('<span class="studio-light-marker" hidden></span>')
    markup(f'<style>{Path(__file__).with_name("neo_brutalism.css").read_text(encoding="utf-8")}</style>')
    markup(f'<style>{Path(__file__).with_name("workspace_refinements.css").read_text(encoding="utf-8")}</style>')
    markup(f'<style>{Path(__file__).with_name("sunny_theme.css").read_text(encoding="utf-8")}</style>')
    markup(f'<style>{Path(__file__).with_name("mobile.css").read_text(encoding="utf-8")}</style>')
    if not motion:
        markup('<span class="workspace-motion-off" hidden></span>')
        markup('<style>*, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }</style>')
    mount_workspace_shortcuts()
with st.container(key='workspace_context'):
    location_col, source_col = st.columns([2, 1], vertical_alignment='center')
    with location_col:
        markup(f'<div class="workspace-location"><span class="location-dot"></span> YOUR WORKSPACE <i>/</i> {escape(labels[page].upper())}</div>')
    with source_col:
        st.selectbox('Active database', list(source_names), format_func=source_names.get,
                     key='active_source', on_change=source_changed, label_visibility='collapsed')

with st.container(key=f'workspace_page_{page}'):
    if page == 'Sources':
        from datasets import render_sources
        render_sources(API, source_items)
    elif page == 'Query':
        fresh = 'result' not in st.session_state
        with st.container(key='query_stage'):
            if fresh:
                markup('<section class="agent-hero"><div class="poster-topline"><span class="agent-eyebrow">THE DISCOVERY DESK <span>/ 01</span></span>'
                       '<span class="poster-edition">LESS GUESSWORK. MORE AHA.</span></div>'
                       '<div class="poster-headline"><h1><span class="headline-strip strip-paper">A little curiosity.</span><br>'
                       '<span class="headline-strip strip-ink">A clearer picture.</span></h1>'
                       '<span class="poster-arrow" aria-hidden="true">&#8599;</span></div>'
                       '<div class="poster-band"><p>Go from “I wonder” to “now I know.”<br>Ask your data. See the story behind the answer.</p>'
                       '<span class="poster-stamp">READ-ONLY.<br>ALWAYS.</span></div></section>')
            workbench = st.container()
            with workbench:
                with st.container(border=True, key='composer'):
                    markup('<div class="composer-label"><span>NEW QUESTION</span><span class="composer-mode">SQL / READ ONLY</span></div>')
                    if st.session_state.pop('voice_pending', False):
                        with st.spinner('Transcribing locally… Your question will appear below.'):
                            update_voice_draft(st.session_state, API)
                    question = st.text_area('Ask a question about your database', key='question_input',
                                            placeholder='Ask a question, compare results, or find a pattern…',
                                            height=140, label_visibility='collapsed')
                    if st.session_state.get('voice_notice'):
                        tone, message = st.session_state['voice_notice']
                        getattr(st, tone)(message)
                        if tone == 'error':
                            st.button('Retry transcription', on_click=transcribe_voice)
                    voice_col, action_col = st.columns([1.15, 1], vertical_alignment='top')
                    with voice_col:
                        mount_voice_capture()
                    with action_col:
                        submitted = st.button('Search ↗', type='primary', width='stretch', key='query_send')
                    markup('<div class="composer-foot"><span>READ-ONLY. ALWAYS.</span><span>Ctrl / ⌘ + Enter</span></div>')
                    if submitted:
                        if question.strip():
                            run(question)
                        else:
                            st.info('Enter a question to get started.')
        if 'result' not in st.session_state:
            markup('<div class="suggestion-label">TRY A STARTING POINT <span>OR ASK YOUR OWN</span></div>')
            suggestions = [
                ('Order pulse', 'How many completed orders are there?'),
                ('Regional reach', 'How many customers are in each region?'),
                ('Product spotlight', 'Show the five most expensive products.')]
            if st.session_state['active_source'] != 'demo':
                source_schema = call('GET', '/v1/schema')
                tables = list((source_schema or {}).get('tables', {}))
                suggestions = [(f'Explore {t}', f'How many records are in the table \"{t}\"?') for t in tables[:3]]
            render_starter_cards(suggestions)
        else:
            show_result(st.session_state['result'])
    elif page == 'Data':
        page_heading('DATABASE BROWSER', 'A closer look at your data.',
                     'Browse tables in your active database. No question or model needed.')
        schema = call('GET', '/v1/schema')
        if schema and schema['tables']:
            table_picker, size_picker = st.columns([3, 1])
            with table_picker:
                selected = st.selectbox('Table', sorted(schema['tables']), key='data_table')
            with size_picker:
                size = st.selectbox('Rows per page', [25, 50, 100, 250, 500], index=1, key='data_size')
            # Scope the page widget to table and size so changing either returns to page one.
            page_key = f'data_page_{selected}_{size}'
            data_page = st.number_input('Page', min_value=1, value=1, step=1, key=page_key)
            effective_size = min(size, st.session_state.get('data_limit_cap', size))
            records = call('GET', f'/v1/data/{quote(selected, safe="")}?limit={size}&offset={(data_page - 1) * effective_size}')
            if records:
                total = records['total_rows']
                actual_size = records['limit']
                if actual_size < size:
                    st.session_state['data_limit_cap'] = actual_size
                pages = max(1, math.ceil(total / actual_size))
                st.caption(f"{total:,} records · {len(records['columns'])} columns · Page {data_page:,} of {pages:,} · Read-only")
                if records['rows']:
                    frame = pd.DataFrame(records['rows'], columns=records['columns'])
                    st.dataframe(frame, width='stretch', hide_index=True, height=450)
                    first = records['offset'] + 1
                    last = records['offset'] + len(records['rows'])
                    st.caption(f'Showing records {first:,}–{last:,} of {total:,}. Table sorting and search apply to this page.')
                    st.download_button('Export this page as CSV', export_csv(frame),
                                       f'{selected}_page_{data_page}.csv', 'text/csv', on_click='ignore')
                elif total:
                    st.info(f'This page is past the last record. Choose a page between 1 and {pages:,}.')
                else:
                    st.info('This table has no records.')
                for warning in records['warnings']:
                    st.warning(warning)
                st.caption('Records are fetched live. Live database changes can shift pagination; uploaded files are fixed snapshots.')
        elif schema:
            st.info('No tables are available.')
    elif page == 'Schema':
        page_heading('DATABASE', 'Know your data.', 'Tables, columns, and the relationships that connect them.')
        data = call('GET', '/v1/schema')
        if data:
            st.caption(f"{len(data['tables'])} tables in the active database")
            for name, table in data['tables'].items():
                with st.expander(f"{name} · {len(table['columns'])} columns"):
                    st.dataframe(pd.DataFrame([{'Column': n, 'Type': c['type'], 'Nullable': c['nullable']} for n, c in table['columns'].items()]), width='stretch', hide_index=True)
                    for fk in table['foreign_keys']:
                        st.caption(f"{', '.join(fk['constrained_columns'])} → {fk['referred_table']}.{', '.join(fk['referred_columns'])}")
    elif page == 'History':
        page_heading('YOUR WORK', 'Your questions, through time.', 'A dated archive of what you asked and the answers you explored. All times shown in IST.')
        dates = st.date_input('Filter by date range (IST)', value=(), key='history_dates')
        history_page = st.number_input('Page', min_value=1, value=1, step=1, key=f'history_page_{dates}')
        date_filter = ''
        if dates:
            date_filter = f'&start_date={dates[0].isoformat()}&end_date={dates[-1].isoformat()}'
        data = call('GET', f'/v1/history?limit=20&offset={(history_page - 1) * 20}{date_filter}')
        if data and not data['items']:
            st.info('No queries on this page. Ask a question to begin your history.')
        if data:
            st.caption(f"{data.get('total', len(data['items'])):,} saved questions · newest first · page {history_page}")
            current_day = None
            for item in data['items']:
                asked_at = pd.Timestamp(item['timestamp'])
                asked_at = asked_at.tz_localize('UTC') if asked_at.tzinfo is None else asked_at
                asked_at = asked_at.tz_convert('Asia/Kolkata')
                day = asked_at.date()
                if day != current_day:
                    markup(f'<div class="archive-day"><span>{escape(asked_at.strftime("%A, %d %B %Y"))}</span><i></i></div>')
                    current_day = day
                with st.container(border=True):
                    summary, action = st.columns([5, 1], vertical_alignment='center')
                    with summary:
                        st.write(item['question'])
                        timestamp = asked_at.strftime('%I:%M:%S %p IST')
                        overall = item.get('confidence', {}).get('overall')
                        score = f" · {overall:g}/100" if overall is not None else ''
                        st.caption(f"{timestamp} · {status_label(item['status'])}{score}")
                        if item.get('sql'):
                            with st.expander('What data was queried?'):
                                st.code(item['sql'], language='sql')
                                st.caption(f"{item.get('row_count', 0):,} returned rows · saved result from when this question was asked")
                    with action:
                        st.caption('Database: ' + item.get('source_name', 'Demo database'))
                        st.button('Open →', key=f"history_{item['id']}", on_click=reopen, args=(item,), width='stretch')
    else:
        page_heading('SYSTEM', 'Everything in its place.', 'Connection status for your workspace. Checks are reused for up to 15 seconds.')
        if st.button('Refresh connections ↻'):
            st.session_state.get('_api_read_cache', {}).pop('/v1/health', None)
        data = call('GET', '/v1/health')
        if data:
            names = [('api', 'Application API'), ('database', 'Business database'), ('metadata', 'History & feedback'),
                     ('llm', 'SQL model'), ('schema_status', 'Schema')]
            with st.container(border=True):
                for key, label in names:
                    text, status = st.columns([4, 1])
                    text.write(label)
                    value = data[key]
                    tone = 'success' if value == 'ok' else 'review'
                    with status:
                        markup(f'<div class="status-pill {tone}">{"Connected" if value == "ok" else escape(value.replace("_", " ").title())}</div>')
            st.caption(f"Model: {data['model']} · Provider: {data['provider']}")
            if data['message']:
                st.info(data['message'])

markup('<footer class="workspace-footer"><span>QUESTION → SQL → EVIDENCE</span><span>AskDB / Your data. Just ask.</span></footer>')
with st.container(key='navigation_motion_assets'):
    mount_navigation_motion(page, motion)
