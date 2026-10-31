from functools import lru_cache
from sqlalchemy import inspect
from app.db import analytical_engine


@lru_cache
def demo_schema() -> dict:
    """Introspect only the public schema accessible to the analyst role."""
    inspector = inspect(analytical_engine())
    result = {}
    for name in inspector.get_table_names(schema='public'):
        result[name] = {
            'columns': {c['name']: {'type': str(c['type']), 'nullable': c['nullable']} for c in inspector.get_columns(name, schema='public')},
            'primary_key': inspector.get_pk_constraint(name, schema='public')['constrained_columns'],
            'foreign_keys': inspector.get_foreign_keys(name, schema='public'),
            'indexes': inspector.get_indexes(name, schema='public'),
        }
    return result


def extract_schema() -> dict:
    from app.sources import current_source
    source = current_source.get()
    return source['schema'] if source else demo_schema()
