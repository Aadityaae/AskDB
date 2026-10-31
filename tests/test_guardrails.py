import pytest
from app.guardrails import validate_sql, Blocked

SCHEMA = {
    'customers': {'columns': {'id': {'type': 'INTEGER'}, 'name': {'type': 'TEXT'}, 'region_id': {'type': 'INTEGER'}}},
    'orders': {'columns': {'id': {'type': 'INTEGER'}, 'customer_id': {'type': 'INTEGER'}, 'status': {'type': 'TEXT'}}},
}


@pytest.mark.parametrize('sql', [
    'DROP TABLE customers', 'DELETE FROM customers', 'UPDATE customers SET name = \'x\'',
    'INSERT INTO customers VALUES (1)', 'ALTER TABLE customers ADD COLUMN x TEXT',
    'CREATE TABLE x (id INT)', 'TRUNCATE customers', 'GRANT SELECT ON customers TO public',
    'COPY customers TO STDOUT', 'CALL anything()', 'BEGIN', 'VACUUM customers',
    'SELECT id FROM customers; SELECT id FROM orders',
    'SELECT id FROM customers -- comment', 'SELECT /* hidden */ id FROM customers',
    'SELECT * FROM pg_catalog.pg_authid', 'SELECT * FROM information_schema.tables',
    'SELECT pg_sleep(10)', 'SELECT set_config(\'x\', \'y\', false)',
    'SELECT pg_read_file(\'/etc/passwd\')', 'SELECT custom_function()',
    'SELECT id INTO stolen FROM customers',
    'WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x',
    'SELECT * FROM customers FOR UPDATE', 'SELECT * FROM imaginary',
    'SELECT missing_column FROM customers',
    'SELECT id FROM customers c JOIN orders o ON c.id = o.customer_id',
    'SELECT * FROM customers CROSS JOIN orders',
    'SELECT * FROM customers, orders',
    'SELECT * FROM customers LIMIT ALL',
    'SELECT * FROM customers LIMIT -1',
    'SELECT * FROM generate_series(1,1000000)',
    'WITH RECURSIVE x AS (SELECT 1 AS n UNION ALL SELECT n+1 FROM x) SELECT * FROM x',
])
def test_dangerous_or_hallucinated_sql_is_blocked(sql):
    with pytest.raises(Blocked):
        validate_sql(sql, SCHEMA)


@pytest.mark.parametrize('sql', [
    'SELECT id, name FROM customers', 'SELECT COUNT(*) AS count FROM customers',
    'SELECT c.name, COUNT(o.id) AS orders FROM customers c LEFT JOIN orders o ON c.id=o.customer_id GROUP BY c.name',
    'WITH totals AS (SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY customer_id) SELECT customer_id, n FROM totals',
    'SELECT id FROM customers UNION SELECT customer_id FROM orders',
    'SELECT * FROM public.customers',
    "SELECT name FROM customers WHERE name = 'DROP TABLE customers'",
])
def test_safe_sql_is_accepted_and_limited(sql):
    result = validate_sql(sql, SCHEMA)
    assert 'LIMIT 1000' in result


def test_large_limit_is_capped():
    assert 'LIMIT 1000' in validate_sql('SELECT id FROM customers LIMIT 999999', SCHEMA)
