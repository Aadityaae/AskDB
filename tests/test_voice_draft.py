from io import BytesIO
import httpx
from frontend import voice
import base64
import pytest


def test_browser_recording_queues_once_without_changing_question():
    state = {'question_input': 'Keep my draft', 'result': {'id': 9}}
    voice.accept_recording(state, {'wav': base64.b64encode(b'WAV bytes').decode()})
    assert state['voice_recording'].getvalue() == b'WAV bytes'
    assert state['voice_pending'] is True
    assert state['voice_capture_revision'] == 1
    assert state['question_input'] == 'Keep my draft'
    assert state['result'] == {'id': 9}


@pytest.mark.parametrize('payload', [None, {}, {'wav': 5}, {'wav': '!invalid!'}, {'wav': ''}, {'wav': 'A' * (8 * 1024 * 1024 + 1)}])
def test_bad_browser_recording_preserves_draft(payload):
    state = {'question_input': 'Keep my draft', 'voice_pending': True}
    voice.accept_recording(state, payload)
    assert state['question_input'] == 'Keep my draft'
    assert state['voice_notice'][0] == 'error'
    assert 'voice_pending' not in state


def test_transcript_fills_editor_without_running_query(monkeypatch):
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={'text': 'How many customers are there?'}, request=httpx.Request('POST', url))
    monkeypatch.setattr(voice.httpx, 'post', post)
    state = {'voice_recording': BytesIO(b'audio'), 'question_input': 'old draft', 'result': {'id': 9}}
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'How many customers are there?'
    assert state['result'] == {'id': 9}
    assert calls == ['http://localhost:8000/v1/transcribe']
    state['question_input'] = 'My manual correction'
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'My manual correction'
    assert len(calls) == 1


def test_silent_recording_preserves_typed_draft(monkeypatch):
    monkeypatch.setattr(voice.httpx, 'post', lambda url, **kw: httpx.Response(200, json={'text': ''}, request=httpx.Request('POST', url)))
    state = {'voice_recording': BytesIO(b'silence'), 'question_input': 'My typed question'}
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'My typed question'
    assert state['voice_notice'][0] == 'info'


def test_voice_service_failure_preserves_typed_draft(monkeypatch):
    monkeypatch.setattr(voice.httpx, 'post', lambda url, **kw: httpx.Response(503, json={'detail': 'Model unavailable'}, request=httpx.Request('POST', url)))
    state = {'voice_recording': BytesIO(b'audio'), 'question_input': 'My typed question'}
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'My typed question'
    assert state['voice_notice'] == ('error', 'Model unavailable')
    assert 'voice_digest' not in state


def test_same_recording_can_retry_after_temporary_failure(monkeypatch):
    responses = iter([503, 200])
    def post(url, **kwargs):
        status = next(responses)
        return httpx.Response(status, json={'detail': 'Temporary failure'} if status == 503 else {'text': 'Retry worked'}, request=httpx.Request('POST', url))
    monkeypatch.setattr(voice.httpx, 'post', post)
    state = {'voice_recording': BytesIO(b'audio'), 'question_input': 'Original question'}
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'Original question'
    voice.transcribe_voice(state, 'http://localhost:8000')
    assert state['question_input'] == 'Retry worked'
