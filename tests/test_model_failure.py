import httpx
import pytest
from app.llm import OllamaProvider, ModelUnavailable
from app.models import Generation


@pytest.mark.parametrize('error,expected', [
    ('error loading model: std::bad_alloc', 'insufficient available memory'),
    ('model requires more system memory', 'insufficient available memory'),
    ('internal failure at private path', 'Check the Ollama server logs'),
])
def test_model_failures_are_actionable_and_hide_internal_details(monkeypatch, error, expected):
    monkeypatch.setattr(httpx.Client, 'post', lambda *args, **kwargs: httpx.Response(500, json={'error': error}))
    with pytest.raises(ModelUnavailable) as failure:
        OllamaProvider().structured('test', Generation)
    assert expected in str(failure.value)
    assert 'private path' not in str(failure.value)
