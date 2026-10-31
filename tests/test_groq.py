from types import SimpleNamespace
import httpx
import pytest
from pydantic import SecretStr
from app import llm
from app.models import Generation, Interpretation


@pytest.fixture
def groq_config(monkeypatch):
    cfg = SimpleNamespace(groq_api_key=SecretStr('test-key'), groq_model='openai/gpt-oss-120b', llm_provider='groq')
    monkeypatch.setattr(llm, 'settings', lambda: cfg)
    return cfg


def test_strict_schema_preserves_original_model_defaults():
    schema = llm.strict_schema(Generation)
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == set(schema['properties'])
    assert 'default' not in schema['properties']['sql']
    assert Generation.model_json_schema()['properties']['sql']['default'] == ''


def test_groq_structured_request_and_parsing(monkeypatch, groq_config):
    def post(client, url, **kwargs):
        assert url == 'https://api.groq.com/openai/v1/chat/completions'
        assert kwargs['headers']['Authorization'] == 'Bearer test-key'
        payload = kwargs['json']
        assert payload['response_format']['json_schema']['strict'] is True
        assert payload['model'] == groq_config.groq_model
        assert 'think' not in payload
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"question":"Count Sales employees"}'}}]})
    monkeypatch.setattr(httpx.Client, 'post', post)
    assert llm.get_provider().structured('test', Interpretation).question == 'Count Sales employees'


@pytest.mark.parametrize('status,message', [(401, 'API key'), (403, 'API key'), (429, 'quota'), (500, 'service status')])
def test_groq_errors_are_safe(monkeypatch, groq_config, status, message):
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **k: httpx.Response(status, json={'error': 'private details test-key'}))
    with pytest.raises(llm.ModelUnavailable) as error:
        llm.GroqProvider().structured('test', Generation)
    assert message in str(error.value)
    assert 'test-key' not in str(error.value)


def test_missing_key_never_sends_request(monkeypatch, groq_config):
    groq_config.groq_api_key = SecretStr('')
    monkeypatch.setattr(httpx.Client, 'post', lambda *a, **k: pytest.fail('No request without a key'))
    with pytest.raises(llm.ModelUnavailable, match='GROQ_API_KEY'):
        llm.GroqProvider().structured('test', Generation)
