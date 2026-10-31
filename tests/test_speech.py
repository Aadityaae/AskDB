from io import BytesIO
import wave
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import speech
pytestmark = pytest.mark.usefixtures('signed_in')


def wav(seconds=1):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b'\0\0' * 16000 * seconds)
    return buffer.getvalue()


@pytest.mark.parametrize('data', [b'', b'not audio', wav(61), wav()[:-10]])
def test_invalid_recordings_are_rejected(data):
    with pytest.raises(speech.InvalidAudio):
        speech.validate_recording(data)


def test_valid_pcm_wav_duration():
    assert speech.validate_recording(wav(2)) == 2


def test_voice_endpoint_returns_only_transcript(monkeypatch):
    monkeypatch.setattr(speech, 'transcribe', lambda data: {'text': 'How many customers are there?', 'language': 'en', 'duration_seconds': 2})
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', files={'audio': ('question.wav', wav(), 'audio/wav')})
        assert response.status_code == 200
        assert response.json()['text'] == 'How many customers are there?'
        assert 'sql' not in response.json()


def test_bad_audio_has_clean_error():
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', files={'audio': ('question.wav', b'bad', 'audio/wav')})
        assert response.status_code == 400


def test_missing_voice_model_has_helpful_error(monkeypatch):
    def unavailable(data):
        raise speech.SpeechUnavailable('Install the local voice model.')
    monkeypatch.setattr(speech, 'transcribe', unavailable)
    with TestClient(app) as client:
        response = client.post('/v1/transcribe', files={'audio': ('question.wav', wav(), 'audio/wav')})
        assert response.status_code == 503
        assert response.json()['detail'] == 'Install the local voice model.'


def test_busy_voice_does_not_queue_another_inference(monkeypatch):
    monkeypatch.setattr(speech, 'speech_model', lambda: object())
    speech.inference_lock.acquire()
    try:
        with pytest.raises(speech.SpeechUnavailable, match='busy'):
            speech.transcribe(wav())
    finally:
        speech.inference_lock.release()
