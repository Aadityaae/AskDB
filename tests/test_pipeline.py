from app.models import QueryRequest, Generation, Interpretation
from app import service
import pytest

SCHEMA = {'customers': {'columns': {'id': {'type': 'INTEGER'}}, 'foreign_keys': []}}


def configure(monkeypatch):
    monkeypatch.setattr(service, 'extract_schema', lambda: SCHEMA)
    monkeypatch.setattr(service, 'select_schema', lambda *args: (SCHEMA, []))
    monkeypatch.setattr(service, 'build_prompt', lambda *args, **kwargs: 'prompt')
    monkeypatch.setattr(service, 'save_history', lambda *args: None)


def test_blocked_sql_never_reaches_executor(monkeypatch):
    configure(monkeypatch)
    def forbidden(*args):
        raise AssertionError('Unsafe SQL reached execution')
    monkeypatch.setattr(service, 'execute', forbidden)
    result = service.run_query(QueryRequest(question='Delete all customers', sql='DELETE FROM customers'))
    assert result.status == 'blocked'


def test_ambiguity_never_executes(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(service, 'execute', lambda *args: (_ for _ in ()).throw(AssertionError('Executed ambiguous query')))
    result = service.run_query(QueryRequest(question='What is revenue?'))
    assert result.status == 'clarification_required'


def test_successful_pipeline_with_fake_provider_and_executor(monkeypatch):
    configure(monkeypatch)
    class FakeProvider:
        def structured(self, prompt, model):
            if model is Interpretation:
                return Interpretation(question='How many customers exist?')
            return Generation(sql='SELECT COUNT(*) AS n FROM customers')
    monkeypatch.setattr(service, 'get_provider', FakeProvider)
    monkeypatch.setattr(service, 'similarity', lambda *args: 1.0)
    monkeypatch.setattr(service, 'execute', lambda *args: ([{'n': 600}], ['n'], 1.0, {'Total Cost': 10}))
    result = service.run_query(QueryRequest(question='How many customers exist?'))
    assert result.status == 'success'
    assert result.results == [{'n': 600}]
    assert result.confidence['agreement'] == .5


def test_repeated_sql_cannot_turn_disagreement_into_a_pass(monkeypatch):
    configure(monkeypatch)
    class FakeProvider:
        def structured(self, prompt, model):
            return Interpretation(question='How many customers exist?') if model is Interpretation else Generation(sql='SELECT COUNT(*) AS n FROM customers')
    monkeypatch.setattr(service, 'get_provider', FakeProvider)
    monkeypatch.setattr(service, 'similarity', lambda *args: 1)
    results = iter([600, 601])
    monkeypatch.setattr(service, 'execute', lambda *args: ([{'n': next(results)}], ['n'], 1, {}))
    result = service.run_query(QueryRequest(question='How many customers exist?'))
    assert result.confidence['agreement'] == 0
    assert result.status == 'low_confidence'


def test_clarification_survives_storage_and_empty_generation_requests_context(monkeypatch):
    configure(monkeypatch)
    class EmptyProvider:
        def structured(self, *args):
            return Generation()
    monkeypatch.setattr(service, 'get_provider', EmptyProvider)
    result = service.run_query(QueryRequest(question='What is revenue?', clarification='Net revenue from completed orders'))
    assert result.clarification == 'Net revenue from completed orders'
    assert result.status == 'clarification_required'
    assert result.options == []


def test_history_failure_does_not_leave_a_nonexistent_record_id(monkeypatch):
    configure(monkeypatch)
    def fail(request, response):
        response.id = 99
        raise RuntimeError('Commit failed')
    monkeypatch.setattr(service, 'save_history', fail)
    result = service.run_query(QueryRequest(question='What is revenue?'))
    assert result.id is None
    assert any('History could not be saved' in w for w in result.warnings)


@pytest.mark.parametrize('question', ['Gross revenue from all orders before discounts', 'Net revenue from completed orders'])
def test_already_defined_revenue_is_not_clarified_again(monkeypatch, question):
    configure(monkeypatch)
    class Provider:
        def structured(self, *args):
            return Generation(sql='DELETE FROM customers')
    monkeypatch.setattr(service, 'get_provider', Provider)
    assert service.run_query(QueryRequest(question=question)).status == 'blocked'


def test_revenue_clarity_uses_words_not_net_inside_internet(monkeypatch):
    configure(monkeypatch)
    class Provider:
        def structured(self, *args):
            raise AssertionError('Ambiguous question reached the model')
    monkeypatch.setattr(service, 'get_provider', Provider)
    result = service.run_query(QueryRequest(question='Internet revenue from all orders'))
    assert result.status == 'clarification_required'
    assert len(result.options) == 2
