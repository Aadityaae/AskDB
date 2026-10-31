from time import perf_counter
from math import isfinite
from decimal import Decimal
from sqlalchemy import text
from app.db import analytical_engine
from app.config import settings
from app.guardrails import Blocked


def check_plan(plan: dict) -> None:
    cfg = settings()
    pending = [plan]
    while pending:
        node = pending.pop()
        if node.get('Plan Rows', 0) > cfg.max_estimated_rows or node.get('Total Cost', 0) > cfg.max_estimated_cost:
            raise Blocked('Estimated query work exceeds configured thresholds.', 'cost')
        pending.extend(node.get('Plans', []))


def execute(sql: str) -> tuple[list[dict], list[str], float, dict]:
    """Execute only validated SQL using a SELECT-only account and read-only transaction."""
    cfg = settings()
    start = perf_counter()
    with analytical_engine().connect() as connection, connection.begin():
        if connection.dialect.name == 'sqlite':
            plan = {'dialect': 'sqlite', 'timeout_seconds': cfg.max_query_seconds}
        else:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            connection.execute(text("SELECT set_config('statement_timeout', :timeout, true)"), {'timeout': str(cfg.max_query_seconds * 1000)})
            connection.execute(text("SET LOCAL search_path = public"))
            connection.execute(text("SELECT set_config('lock_timeout', '2000', true)"))
            plan = connection.execute(text('EXPLAIN (FORMAT JSON) ' + sql)).scalar_one()[0]['Plan']
            check_plan(plan)
        cursor = connection.execution_options(stream_results=True, max_row_buffer=100).execute(text(sql))
        columns = list(cursor.keys())
        if len(set(columns)) != len(columns):
            raise Blocked('Result columns have duplicate names. Give each selected column a unique AS alias.', 'duplicate_columns')
        rows, result_bytes = [], 0
        for row in cursor:
            mapped = dict(row._mapping)
            result_bytes += sum(len(v.encode('utf-8')) if isinstance(v, str) else len(v) if isinstance(v, bytes) else 32 for v in mapped.values())
            if result_bytes > 8 * 1024 * 1024:
                raise Blocked('The result exceeds 8 MB. Select fewer columns or a smaller LIMIT.', 'result_size')
            rows.append(mapped)
            if len(rows) >= cfg.max_result_rows:
                break
        non_finite = 0
        for row in rows:
            for key, value in row.items():
                if (isinstance(value, float) and not isfinite(value)) or (isinstance(value, Decimal) and not value.is_finite()):
                    row[key] = None
                    non_finite += 1
        if non_finite:
            plan['non_finite_values'] = non_finite
    return rows, columns, (perf_counter() - start) * 1000, plan
