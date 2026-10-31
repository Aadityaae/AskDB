"""Keep bare workspace visits on the public homepage."""
import streamlit as st


def enter_from_homepage():
    if st.query_params.get('entry') in ('signin', 'signup', 'workspace'):
        return
    redirect = st.components.v2.component(
        'homepage_redirect',
        js="""export default function() {
          const home = new URL(window.location.href);
          home.port = '8000'; home.pathname = '/landing/';
          home.search = ''; home.hash = '';
          window.location.replace(home.href);
        }""",
        isolate_styles=False,
    )
    redirect(key='homepage_redirect', height=0)
    st.info('Opening the AskDB homepage…')
    st.stop()
