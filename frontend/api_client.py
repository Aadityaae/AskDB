"""One shared connection pool; user credentials are supplied on each request."""
import httpx
import streamlit as st


@st.cache_resource(show_spinner=False)
def connection_pool():
    return httpx.Client(limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=30),
                        timeout=httpx.Timeout(25, connect=5))


def request(method, api, path, **kwargs):
    return connection_pool().request(method, api + path, **kwargs)
