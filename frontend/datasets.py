"""Private uploads with an explicit import action and active-source handoff."""
import httpx
import streamlit as st
from api_client import request


def render_sources(api, items):
    st.subheader('Your data. Your questions.')
    st.write('Upload a CSV or SQLite database, then choose it as your active database. The demo stays available.')
    with st.container(border=True):
        st.markdown('### Bring your data')
        with st.form('dataset_upload', clear_on_submit=False):
            name = st.text_input('Dataset name', max_chars=80, placeholder='For example: October sales')
            file = st.file_uploader('CSV or SQLite database', type=['csv', 'db'], max_upload_size=50,
                                    help='CSV: UTF-8 with a header row. SQLite: export/checkpoint a complete .db file before uploading.')
            st.caption('Up to 50 MB per file · 200,000 total records · 50 tables · 200 columns per table. Up to 10 datasets / 200 MB per account.')
            submitted = st.form_submit_button('Import & explore ↗', type='primary', width='stretch')
        st.caption('Uploads are private to your account and stored on the AskDB server. Questions and table/column descriptions are sent to the configured SQL model provider when you ask a question.')
        if submitted:
            if file is None:
                st.info('Choose a file first.')
            else:
                try:
                    with st.spinner('Preparing your database…'):
                        response = request('POST', api, '/v1/sources', headers={'Authorization': 'Bearer ' + st.session_state['auth_token']},
                                           files={'file': (file.name, file.getvalue(), file.type)}, data={'name': name}, timeout=120)
                    if response.is_success:
                        source = response.json()
                        st.session_state['pending_source'] = source['id']
                        st.session_state['pending_page'] = 'Data'
                        st.rerun()
                    else:
                        st.error(response.json().get('detail', 'Import could not complete.'))
                except (httpx.HTTPError, ValueError):
                    st.error('Import could not complete. Check the API connection, then refresh your source list before retrying.')
    st.markdown('### Available databases')
    for item in items:
        with st.container(border=True):
            title, action = st.columns([3, 1])
            with title:
                st.markdown('**' + item['name'].replace('*', '').replace('<', '').replace('>', '') + '**')
                st.caption('Demo · shared business data' if item['kind'] == 'demo' else f"{item['kind'].upper()} · {item['table_count']} tables · {item['size_bytes'] / 1024:,.0f} KB · private")
            with action:
                if st.button('Explore →', key='explore_' + item['id'], width='stretch'):
                    st.session_state['pending_source'] = item['id']
                    st.session_state['pending_page'] = 'Data'
                    st.rerun()
    with st.expander('How imports work'):
        st.write('CSV becomes a table named data. Headers are normalized to lowercase_with_underscores; blank cells become NULL. Numbers are detected across the entire column; mixed values and leading-zero identifiers remain text. Dates remain text.')
        st.write('SQLite ordinary tables, primary keys and relationship descriptions are copied into a clean read-only snapshot. Original views, virtual tables and binary BLOB columns are unsupported. Triggers, executable defaults and custom functions are not imported. Keep your original file as the master copy; uploads are snapshots, not live connections.')
