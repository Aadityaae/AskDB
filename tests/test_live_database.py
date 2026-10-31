"""Opt-in real PostgreSQL checks. No fake service results."""
import os
import pytest
from sqlalchemy import text
from app.db import analytical_engine
from app.schema import extract_schema
from app.guardrails import validate_sql
from app.executor import execute

pytestmark = pytest.mark.skipif(os.getenv('RUN_LIVE_TESTS') != '1', reason='Set RUN_LIVE_TESTS=1 with seeded PostgreSQL running')


def test_seed_and_safe_execution():
    schema = extract_schema()
    sql = validate_sql('SELECT COUNT(*) AS count FROM customers', schema)
    rows, _, _, _ = execute(sql)
    assert rows == [{'count': 600}]


def test_postgres_oversized_results_are_bounded():
    from app.guardrails import Blocked
    sql = validate_sql("SELECT '" + 'x' * 15000 + "' AS payload FROM customers", extract_schema())
    with pytest.raises(Blocked, match='exceeds 8 MB'):
        execute(sql)


def test_duplicate_column_names_fail_cleanly_instead_of_losing_data():
    from app.guardrails import Blocked
    sql = validate_sql('SELECT id AS duplicate, name AS duplicate FROM customers', extract_schema())
    with pytest.raises(Blocked, match='unique AS alias'):
        execute(sql)


def test_non_finite_numbers_are_json_safe():
    sql = validate_sql("SELECT CAST('NaN' AS DOUBLE PRECISION) AS value", extract_schema())
    rows, _, _, plan = execute(sql)
    assert rows == [{'value': None}]
    assert plan['non_finite_values'] == 1


def test_database_role_has_no_write_privileges():
    with analytical_engine().connect() as conn:
        assert conn.execute(text("SELECT has_table_privilege(current_user, 'customers', 'SELECT')")).scalar_one()
        assert not conn.execute(text("SELECT has_table_privilege(current_user, 'customers', 'INSERT,UPDATE,DELETE,TRUNCATE')")).scalar_one()
        assert not conn.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()


def test_readonly_transaction_enforcement():
    with analytical_engine().connect() as conn, conn.begin():
        conn.execute(text('SET TRANSACTION READ ONLY'))
        with pytest.raises(Exception):
            conn.execute(text("DELETE FROM customers WHERE false"))


def test_database_browser_pages_are_complete_and_ordered():
    from app.browser import browse_records
    first = browse_records('customers', 50, 0)
    second = browse_records('customers', 50, 50)
    last = browse_records('customers', 50, 599)
    assert first.total_rows == second.total_rows == 600
    assert [row['id'] for row in first.rows] == list(range(1, 51))
    assert [row['id'] for row in second.rows] == list(range(51, 101))
    assert [row['id'] for row in last.rows] == [600]


def test_database_browser_supports_every_business_table():
    from app.browser import browse_records
    for name in extract_schema():
        result = browse_records(name, 25, 0)
        assert result.table == name
        assert len(result.rows) <= 25
        assert result.total_rows >= len(result.rows)
