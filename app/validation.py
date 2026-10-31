from collections import Counter
from datetime import date, datetime
from decimal import Decimal
import json

WEIGHTS = {'syntax': .15, 'back_translation': .30, 'sanity': .20, 'agreement': .25, 'schema_coverage': .10}


def confidence(signals: dict[str, float | None]) -> dict:
    # Missing validations contribute zero; do not silently renormalize the score.
    return {**signals, 'overall': round(sum((signals.get(k) or 0) * w for k, w in WEIGHTS.items()) * 100, 1)}


def sanity(rows: list[dict]) -> tuple[float, list[str]]:
    warnings = []
    if not rows:
        return .5, ['No rows returned; this may be legitimate or a mismatched filter.']
    columns = list(rows[0])
    if any(sum(row.get(name) is None for row in rows) / len(rows) > .5 for name in columns):
        warnings.append('More than half of a result column is NULL.')
    serialized = [json.dumps(row, sort_keys=True, default=str) for row in rows]
    if len(rows) > 1 and (len(rows) - len(set(serialized))) / len(rows) > .5:
        warnings.append('Many duplicate result rows; review JOIN cardinality.')
    for name in columns:
        if any(term in name.lower() for term in ('count', 'quantity', 'price')):
            try:
                if any(float(row[name]) < 0 for row in rows if row.get(name) is not None):
                    warnings.append(f'Unexpected negative values in {name}.')
            except (ValueError, TypeError):
                pass
    return max(0, 1 - .2 * len(warnings)), warnings


def canonical_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (Decimal, float, int)) and not isinstance(value, bool):
        return str(Decimal(str(value)).quantize(Decimal('.000001')))
    return value


def agreement(left: list[dict], right: list[dict]) -> float:
    """Compare multisets of values independent of aliases and row order, retaining duplicates."""
    def canonical(rows):
        return Counter(json.dumps([canonical_value(v) for v in row.values()], default=str) for row in rows)
    if left and right and len(left[0]) != len(right[0]):
        return 0
    return float(canonical(left) == canonical(right))
