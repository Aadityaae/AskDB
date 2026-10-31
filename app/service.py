import logging
import re
import sqlglot
from sqlglot import exp
from fastapi.encoders import jsonable_encoder
from app.models import QueryRequest, QueryResponse, Generation, Interpretation
from app.schema import extract_schema
from app.relevance import select_schema, similarity
from app.prompts import build_prompt
from app.llm import get_provider, ModelUnavailable
from app.guardrails import validate_sql, Blocked
from app.executor import execute
from app.validation import sanity, agreement, confidence
from app.config import settings
from app.db import save_history

log = logging.getLogger(__name__)


def run_query(request: QueryRequest) -> QueryResponse:
    from app.sources import source_info, dialect, current_source
    response = QueryResponse(**source_info(), status='execution_failed', question=request.question.strip(), clarification=request.clarification)
    try:
        schema = extract_schema()
        focused, warnings = select_schema(response.question, schema)
        response.warnings.extend(warnings)
        provider = get_provider()
        prompt = build_prompt(response.question, focused, request.clarification)
        # Explicit revenue ambiguity is resolved before SQL execution, including edited SQL.
        words = response.question.lower()
        revenue_defined = re.search(r'\b(net|gross|discounts?)\b', words) and re.search(r'\b(completed|pending|cancelled|canceled)\b|\ball orders\b', words)
        if not current_source.get() and 'revenue' in words and not request.clarification and not revenue_defined:
            response.status = 'clarification_required'
            response.options = ['Net revenue from completed orders after discounts', 'Gross value of all orders before discounts']
        else:
            generation = Generation(sql=request.sql, explanation='User-edited SQL; all guardrails still apply.') if request.sql else provider.structured(prompt, Generation)
            if generation.clarification_options or not generation.sql:
                response.status = 'clarification_required'
                response.options = generation.clarification_options
            else:
                response.sql = generation.sql
                response.explanation = generation.explanation
                response.warnings.extend(generation.assumptions)
                response.sql = validate_sql(response.sql, schema)
                rows, columns, elapsed, plan = execute(response.sql)
                response.results = jsonable_encoder(rows)
                response.columns, response.row_count, response.execution_time_ms = columns, len(rows), round(elapsed, 2)
                if plan.get('non_finite_values'):
                    response.warnings.append('Non-finite numeric values (NaN or infinity) are shown as NULL because JSON cannot represent them.')
                sanity_score, sanity_warnings = sanity(rows)
                response.warnings.extend(sanity_warnings)
                signals = {'syntax': 1.0, 'sanity': sanity_score, 'back_translation': None, 'agreement': None, 'schema_coverage': None}
                if settings().validation_mode != 'fast':
                    try:
                        interpretation = provider.structured('Describe exactly what this ' + dialect() + ' SQL answers, including filters and grouping. Return JSON question. SQL: ' + response.sql, Interpretation)
                        signals['back_translation'] = similarity(response.question + ' ' + (request.clarification or ''), interpretation.question)
                    except Exception:
                        response.warnings.append('Meaning validation unavailable; its confidence contribution is zero.')
                if settings().validation_mode == 'strict':
                    try:
                        alternate = provider.structured(build_prompt(response.question, focused, request.clarification, independent=True), Generation)
                        alternate_sql = validate_sql(alternate.sql, schema)
                        alternate_rows, _, _, _ = execute(alternate_sql)
                        signals['agreement'] = agreement(rows, alternate_rows)
                        if signals['agreement'] == 0:
                            response.warnings.append('Independent queries disagree. Review the SQL and result.')
                        if sqlglot.parse_one(alternate_sql, read=dialect()).sql() == sqlglot.parse_one(response.sql, read=dialect()).sql():
                            signals['agreement'] = min(signals['agreement'], .5)
                            response.warnings.append('Independent generation repeated the same SQL; agreement is limited evidence.')
                    except Exception:
                        response.warnings.append('Independent query validation failed; its confidence contribution is zero.')
                referenced = {t.name for t in sqlglot.parse_one(response.sql, read=dialect()).find_all(exp.Table)} & set(schema)
                signals['schema_coverage'] = len(referenced & set(focused)) / max(1, len(focused))
                response.warnings.append('Schema coverage measures selected-table overlap; it does not prove semantic correctness or JOIN cardinality.')
                response.confidence = confidence(signals)
                response.validation = {'syntax': 'passed', 'guardrails': 'passed', 'schema': 'passed', 'cost': 'bounded by timeout and upload limits' if dialect() == 'sqlite' else 'passed', 'estimated_cost': plan.get('Total Cost'), 'mode': settings().validation_mode}
                response.status = 'success' if response.confidence['overall'] >= 75 and signals['agreement'] != 0 else 'low_confidence'
                response.answer = f'Returned {len(rows)} row(s).'
                if len(rows) == 1:
                    response.answer += ' ' + '; '.join(f'{k}: {v}' for k, v in rows[0].items())
                if len(rows) == settings().max_result_rows:
                    response.warnings.append('Result reached the configured row limit; additional rows may exist.')
    except Blocked as exc:
        response.status, response.reason, response.guardrail = 'blocked', str(exc), exc.rule
        log.warning('query_blocked rule=%s', exc.rule)
    except ModelUnavailable as exc:
        log.error('query_failed type=ModelUnavailable')
        response.reason = str(exc)
    except Exception as exc:
        log.error('query_failed type=%s', type(exc).__name__)
        response.reason = 'Query could not complete. Check database connectivity, SQL model provider status, and server logs.'
    try:
        save_history(request, response)
    except Exception:
        log.error('history_storage_failed')
        response.id = None
        response.warnings.append('History could not be saved; check the metadata database.')
    return response
