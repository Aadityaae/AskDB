from app.validation import confidence, agreement, sanity
from app.executor import check_plan
from app.guardrails import Blocked
import pytest


def test_confidence_uses_documented_weights():
    assert confidence({'syntax': 1, 'back_translation': 1, 'sanity': 1, 'agreement': 1, 'schema_coverage': 1})['overall'] == 100
    assert confidence({'syntax': 1})['overall'] == 15


def test_missing_signals_are_not_passes():
    assert confidence({'syntax': 1, 'agreement': None})['overall'] == 15


def test_agreement_preserves_duplicate_rows():
    assert agreement([{'n': 1}, {'n': 1}], [{'count': 1}]) == 0
    assert agreement([{'n': 1}, {'n': 2}], [{'count': 2}, {'count': 1}]) == 1


def test_empty_results_warn():
    score, warnings = sanity([])
    assert score < 1 and warnings


def test_expensive_nested_plan_is_blocked():
    with pytest.raises(Blocked):
        check_plan({'Plan Rows': 1, 'Total Cost': 1, 'Plans': [{'Plan Rows': 2000000}]})
