"""Bounded table browsing with introspected identifiers and the safe query executor."""
from sqlalchemy import column, func, select, table
from fastapi.encoders import jsonable_encoder
from app.config import settings
from app.db import analytical_engine
from app.schema import extract_schema
from app.guardrails import validate_sql
from app.executor import execute
from app.models import TableRecordsResponse


def browse_records(table_name: str, limit: int, offset: int) -> TableRecordsResponse:
    schema = extract_schema()
    if table_name not in schema:
        raise KeyError(table_name)
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError('Invalid pagination')
    limit = min(limit, settings().max_result_rows)
    info = schema[table_name]
    source = table(table_name, *(column(name) for name in info['columns']), schema='public' if analytical_engine().dialect.name == 'postgresql' else None)
    order = info['primary_key'] or list(info['columns'])[:1]
    statement = select(source).order_by(*(source.c[name] for name in order)).limit(limit).offset(offset)
    count = select(func.count().label('total_rows')).select_from(source)
    dialect = analytical_engine().dialect
    def sql(statement):
        compiled = str(statement.compile(dialect=dialect, compile_kwargs={'literal_binds': True}))
        return validate_sql(compiled, schema)
    counts, _, _, _ = execute(sql(count))
    rows, columns, _, plan = execute(sql(statement))
    warnings = [] if info['primary_key'] else ['This table has no primary key; tied rows may move between pages.']
    if plan.get('non_finite_values'):
        warnings.append('Non-finite numeric values (NaN or infinity) are shown as NULL because JSON cannot represent them.')
    return TableRecordsResponse(table=table_name, columns=columns, rows=jsonable_encoder(rows),
                                total_rows=counts[0]['total_rows'], limit=limit, offset=offset,
                                warnings=warnings)
