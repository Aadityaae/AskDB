"""The studio's account entrance; session credentials stay in server-side session state."""
from pathlib import Path
import httpx
import streamlit as st
from effects import mount_effects
from auth_background import mount_auth_background
from api_client import request


def auth_request(api, route, payload=None):
    try:
        response = request('POST', api, '/v1/auth/' + route, json=payload, timeout=25)
        if response.is_success:
            return response.json()
        detail = response.json().get('detail', 'Could not sign in. Please try again.')
        if isinstance(detail, list):
            detail = '; '.join(item['msg'].removeprefix('Value error, ') for item in detail)
        st.error(detail)
    except (httpx.RequestError, ValueError):
        st.error('The account service is taking a break. Check your API connection and try again.')
    return None


def accept_login(result):
    st.session_state['auth_token'] = result['token']
    st.session_state['auth_user'] = result['user']
    st.session_state['page'] = 'Query'
    for key in ('result', 'clarification', 'question_input', 'voice_digest', 'voice_notice', '_api_read_cache'):
        st.session_state.pop(key, None)
    st.rerun()


def sign_out(api):
    try:
        response = request('POST', api, '/v1/auth/logout', headers={'Authorization': 'Bearer ' + st.session_state.get('auth_token', '')}, timeout=10)
        if response.status_code not in (200, 401):
            st.error('Could not sign out securely. Please retry.')
            return
    except httpx.RequestError:
        st.error('Could not sign out securely. Please retry once the API is connected.')
        return
    theme = st.session_state.get('light_mode', False)
    st.session_state.clear()
    st.session_state['light_mode'] = theme
    st.rerun()


def require_login(api):
    entry = st.query_params.get('entry')
    if entry in ('signup', 'signin'):
        st.session_state['auth_mode'] = 'Sign up' if entry == 'signup' else 'Sign in'
        st.query_params['entry'] = 'workspace'
    if st.session_state.get('auth_token'):
        try:
            response = request('GET', api, '/v1/auth/me', headers={'Authorization': 'Bearer ' + st.session_state['auth_token']}, timeout=10)
            if response.is_success:
                st.session_state['auth_user'] = response.json()
                for key in ('auth_password', 'auth_confirm'):
                    st.session_state.pop(key, None)
                return
            if response.status_code != 401:
                st.error('The account service is temporarily unavailable. Please retry.')
                st.stop()
        except httpx.RequestError:
            st.error('Cannot reach the account service. Please check the backend.')
            st.stop()
        st.session_state.clear()
        st.warning('Your session expired. Welcome back—please sign in again.')

    css = Path(__file__).with_name('accounts.css').read_text()
    with st.container(key='auth_gate'):
        with st.container(key='auth_style_assets'):
            st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
            light = st.session_state.get('light_mode', False)
            mount_auth_background(light)
            if light:
                st.markdown('<span class="auth-light-marker" hidden></span>', unsafe_allow_html=True)
                st.markdown(f'<style>{Path(__file__).with_name("light.css").read_text()}</style>', unsafe_allow_html=True)
            st.markdown(f'<style>{Path(__file__).with_name("effects.css").read_text()}</style>', unsafe_allow_html=True)
            mount_effects(True)
        with st.container(key='auth_form_wrap'):
            with st.container(key='account_form', border=True):
                st.session_state.setdefault('auth_mode', 'Sign in')
                mode = st.segmented_control('Your invitation', ['Sign in', 'Sign up'], key='auth_mode', label_visibility='collapsed') or 'Sign in'
                signup = mode == 'Sign up'
                st.markdown(f'<div class="auth-form-intro"><h2>{"Join the plot." if signup else "Back for more aha?"}</h2><p>{"Create your account. Bring your questions." if signup else "Sign in. Your next discovery is waiting."}</p></div>', unsafe_allow_html=True)
                with st.form('credentials', border=False):
                    name = st.text_input('What should we call you?', placeholder='Your name', max_chars=80) if signup else ''
                    email = st.text_input('Email address', placeholder='you@something.great', max_chars=254)
                    password = st.text_input('Password', type='password', key='auth_password', max_chars=128,
                                             help='Use at least 10 characters. A memorable passphrase works well.')
                    confirm = st.text_input('One more time, for the password', type='password', key='auth_confirm', max_chars=128) if signup else ''
                    if signup:
                        st.caption('Use at least 10 characters.')
                    submitted = st.form_submit_button('Let me in ↗' if not signup else 'Make me a member ↗', type='primary', width='stretch')
                if submitted:
                    if signup and password != confirm:
                        st.error('Those passwords don’t match. Let’s get them on the same page.')
                    else:
                        payload = {'email': email, 'password': password}
                        if signup:
                            payload['name'] = name
                        result = auth_request(api, 'signup' if signup else 'login', payload)
                        if result:
                            accept_login(result)
    st.stop()
