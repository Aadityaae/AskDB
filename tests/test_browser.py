import pytest
from fastapi.testclient import TestClient
pytestmark = pytest.mark.usefixtures('signed_in')
from sqlalchemy.dialects.postgresql import dialect
from app import browser
from app.main import app


def test_unknown_and_injected_table_names_never_execute(monkeypatch):
    monkeypatch.setattr(browser, 'extract_schema', lambda: {'customers': {}})
    def forbidden(*args):
        raise AssertionError('Unknown identifier reached execution')
    monkeypatch.setattr(browser, 'execute', forbidden)
    for name in ('missing', 'customers; DROP TABLE customers', 'pg_catalog.pg_authid'):
        with pytest.raises(KeyError):
            browser.browse_records(name, 50, 0)


def test_rows_use_primary_key_order_and_pagination(monkeypatch):
    schema = {'customers': {'columns': {'id': {'type': 'INTEGER'}}, 'primary_key': ['id']}}
    monkeypatch.setattr(browser, 'extract_schema', lambda: schema)
    class Engine:
        dialect = dialect()
    monkeypatch.setattr(browser, 'analytical_engine', lambda: Engine())
    queries = []
    def execute(sql):
        queries.append(sql)
        rows = [{'total_rows': 600}] if 'COUNT(' in sql else [{'id': 51}]
        return rows, list(rows[0]), 1, {}
    monkeypatch.setattr(browser, 'execute', execute)
    result = browser.browse_records('customers', 50, 50)
    assert result.rows == [{'id': 51}]
    assert result.total_rows == 600
    assert 'ORDER BY' in queries[1] and 'LIMIT 50' in queries[1] and 'OFFSET 50' in queries[1]


def test_api_rejects_unbounded_pagination():
    with TestClient(app) as client:
        for params in ('limit=501', 'limit=0', 'offset=-1'):
            assert client.get('/v1/data/customers?' + params).status_code == 422
