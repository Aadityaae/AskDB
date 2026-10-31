from typing import Protocol, TypeVar
import httpx
from pydantic import BaseModel
from app.config import settings

T = TypeVar('T', bound=BaseModel)


class ModelUnavailable(RuntimeError):
    """A safe, actionable model error suitable for display in the UI."""


class Provider(Protocol):
    def structured(self, prompt: str, model: type[T]) -> T: ...


def strict_schema(model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    def normalize(node):
        if isinstance(node, dict):
            node.pop('default', None)
            if node.get('type') == 'object':
                node['additionalProperties'] = False
                node['required'] = list(node.get('properties', {}))
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)
    normalize(schema)
    return schema


class GroqProvider:
    def structured(self, prompt: str, model: type[T]) -> T:
        cfg = settings()
        key = cfg.groq_api_key.get_secret_value().strip()
        if not key:
            raise ModelUnavailable('Add GROQ_API_KEY to your .env file, then restart the API with docker compose up -d api.')
        try:
            with httpx.Client(timeout=90) as client:
                response = client.post('https://api.groq.com/openai/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + key}, json={
                        'model': cfg.groq_model,
                        'messages': [{'role': 'user', 'content': prompt}],
                        'temperature': 0, 'max_completion_tokens': 2048,
                        'response_format': {'type': 'json_schema', 'json_schema': {
                            'name': model.__name__, 'strict': True, 'schema': strict_schema(model)}}})
        except httpx.RequestError:
            raise ModelUnavailable('Could not reach Groq. Check your internet connection and try again.') from None
        if response.status_code in (401, 403):
            raise ModelUnavailable('Groq rejected the API key or model access. Check GROQ_API_KEY and your Groq account permissions.')
        if response.status_code == 429:
            raise ModelUnavailable('Groq free-tier quota or rate limit reached. Wait before retrying; check usage in the Groq console.')
        if response.is_error:
            raise ModelUnavailable('Groq could not complete the request. Check the configured model and service status.')
        try:
            return model.model_validate_json(response.json()['choices'][0]['message']['content'])
        except (ValueError, KeyError, IndexError, TypeError):
            raise ModelUnavailable('Groq returned an incomplete or invalid structured answer. Please retry.') from None


def get_provider() -> Provider:
    return GroqProvider() if settings().llm_provider == 'groq' else OllamaProvider()


class OllamaProvider:
    """Local structured generation; no cloud fallback or automatic model download."""
    def structured(self, prompt: str, model: type[T]) -> T:
        cfg = settings()
        with httpx.Client(timeout=180) as client:
            response = client.post(f'{cfg.ollama_base_url}/api/chat', json={
                'model': cfg.ollama_model, 'stream': False,
                'format': model.model_json_schema(),
                'messages': [{'role': 'user', 'content': prompt}],
                'options': {'temperature': 0}, 'think': False,
            })
            if response.is_error:
                try:
                    error = str(response.json().get('error', '')).lower()
                except ValueError:
                    error = ''
                if any(marker in error for marker in ('bad_alloc', 'out of memory', 'not enough memory', 'requires more system memory')):
                    raise ModelUnavailable(f'Ollama could not load {cfg.ollama_model}: insufficient available memory. Close memory-heavy applications or select a smaller model. No query was executed.')
                if response.status_code == 404:
                    raise ModelUnavailable(f'Ollama model {cfg.ollama_model} is unavailable. Install it with: ollama pull {cfg.ollama_model}')
                raise ModelUnavailable(f'Ollama could not run {cfg.ollama_model}. Check the Ollama server logs and available memory.')
            return model.model_validate_json(response.json()['message']['content'])
