import sqlparse
from sqlparse import tokens
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from app.config import settings


class Blocked(ValueError):
    def __init__(self, reason: str, rule: str):
        super().__init__(reason)
        self.rule = rule


# Positive function allowlist: unknown/user-defined functions fail closed.
SAFE_FUNCTIONS = {
    'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'NULLIF', 'ROUND', 'ABS',
    'LOWER', 'UPPER', 'LENGTH', 'TRIM', 'SUBSTRING', 'EXTRACT', 'DATE_TRUNC',
    'CURRENT_DATE', 'CURRENT_TIMESTAMP', 'CAST', 'CASE', 'IF', 'ROW_NUMBER',
    'RANK', 'DENSE_RANK', 'LAG', 'LEAD', 'CONCAT', 'CEIL', 'FLOOR',
    'STDDEV', 'STDDEV_SAMP', 'VARIANCE', 'VAR_SAMP', 'GREATEST', 'LEAST',
    'TO_CHAR', 'DATE_PART',
}


def validate_sql(sql: str, schema: dict) -> str:
    """Parse, resolve schema references, reject side effects and cap output via AST."""
    from app.sources import dialect
    sql_dialect = dialect()
    cfg = settings()
    if not sql.strip():
        raise Blocked('SQL is empty.', 'empty')
    parsed = sqlparse.parse(sql)
    if len(parsed) != 1:
        raise Blocked('Exactly one statement is allowed.', 'stacked_statements')
    if any(t.ttype in tokens.Comment for t in parsed[0].flatten()):
        raise Blocked('SQL comments are not allowed.', 'comments')
    try:
        trees = sqlglot.parse(sql, read=sql_dialect)
        tree = trees[0]
    except Exception as exc:
        raise Blocked('SQL could not be parsed.', 'syntax') from exc
    if len(trees) != 1 or not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise Blocked('Only analytical SELECT statements are allowed.', 'select_only')
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
                 exp.Command, exp.Into, exp.Lock, exp.Transaction)
    for node in tree.walk():
        if isinstance(node, exp.With) and node.args.get('recursive'):
            raise Blocked('Recursive CTEs are forbidden.', 'recursive')
        if isinstance(node, (exp.Placeholder, exp.Parameter)):
            raise Blocked('SQL parameters are not supported in generated queries.', 'parameter')
        if isinstance(node, forbidden):
            raise Blocked('Side effects and locking are forbidden.', 'side_effect')
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
            if name not in SAFE_FUNCTIONS | ({'DATE', 'DATETIME', 'STRFTIME', 'JULIANDAY', 'TIME_TO_STR', 'TIME_STR_TO_TIME', 'TS_OR_DS_TO_TIMESTAMP', 'DATE_ADD', 'TS_OR_DS_ADD'} if sql_dialect == 'sqlite' else set()):
                raise Blocked(f'Function {name} is not allowed.', 'function')
        if isinstance(node, exp.Subquery):
            depth, parent = 1, node.parent
            while parent is not None:
                depth += isinstance(parent, exp.Subquery)
                parent = parent.parent
            if depth > cfg.max_subquery_depth:
                raise Blocked('Subquery nesting exceeds the configured limit.', 'depth')
        if isinstance(node, exp.Join) and (node.args.get('kind') == 'CROSS' or not (node.args.get('on') or node.args.get('using'))):
            raise Blocked('JOINs require explicit conditions.', 'join')
    ctes = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise Blocked('Table functions are forbidden.', 'table_function')
        allowed_schemas = ('', 'public') if sql_dialect == 'postgres' else ('', 'main')
        if table.catalog or table.db not in allowed_schemas:
            raise Blocked('Only tables in the active database are allowed.', 'schema')
        if table.name not in schema and table.name not in ctes:
            raise Blocked(f'Unknown table: {table.name}', 'table')
    try:
        qualified = qualify(tree.copy(), dialect=sql_dialect,
                            schema={n: {c: info['type'] for c, info in t['columns'].items()} for n, t in schema.items()},
                            validate_qualify_columns=True)
        if any(isinstance(c.this, exp.Star) for c in qualified.find_all(exp.Column)):
            raise ValueError('Unresolved star')
    except Exception as exc:
        raise Blocked('A column is unknown, ambiguous, or cannot be resolved.', 'column') from exc
    limit = tree.args.get('limit')
    if limit:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int:
            raise Blocked('LIMIT must be a positive integer.', 'limit')
        if int(value.this) < 0:
            raise Blocked('LIMIT cannot be negative.', 'limit')
        tree = tree.limit(min(int(value.this), cfg.max_result_rows))
    else:
        tree = tree.limit(cfg.max_result_rows)
    return tree.sql(dialect=sql_dialect)
