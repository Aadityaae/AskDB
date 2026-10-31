"""Voice-to-draft handling. Transcription updates the editor and never submits a query."""
import hashlib
import httpx
import base64
import binascii
from io import BytesIO


def accept_recording(state, payload) -> None:
    """Accept one bounded WAV event from the browser, before the editor mounts."""
    state['voice_capture_revision'] = state.get('voice_capture_revision', 0) + 1
    try:
        encoded = payload['wav']
        if not isinstance(encoded, str) or len(encoded) > 8 * 1024 * 1024:
            raise ValueError('Recording too large')
        audio = base64.b64decode(encoded, validate=True)
        if not audio or len(audio) > 6 * 1024 * 1024:
            raise ValueError('Recording too large or empty')
    except (KeyError, TypeError, ValueError, binascii.Error):
        state.pop('voice_pending', None)
        state['voice_notice'] = ('error', 'Could not read this recording. Please try recording again.')
        return
    state['voice_recording'] = BytesIO(audio)
    state['voice_pending'] = True


def transcribe_voice(state, api_base: str) -> None:
    recording = state.get('voice_recording')
    if recording is None:
        state.pop('voice_notice', None)
        state.pop('voice_digest', None)
        return
    audio = recording.getvalue()
    digest = hashlib.sha256(audio).hexdigest()
    if digest == state.get('voice_digest'):
        return
    state['voice_digest'] = digest
    try:
        headers = {'Authorization': 'Bearer ' + state['auth_token']} if state.get('auth_token') else {}
        response = httpx.post(api_base + '/v1/transcribe', files={'audio': ('question.wav', audio, 'audio/wav')}, headers=headers, timeout=120)
        response.raise_for_status()
        transcript = response.json()['text'].strip()
        if transcript:
            state['question_input'] = transcript
            state['voice_notice'] = ('success', 'Transcribed. Review your question, then press Search.')
        else:
            state['voice_notice'] = ('info', 'No speech detected. Try again in a quiet space.')
    except httpx.HTTPStatusError as exc:
        state.pop('voice_digest', None)
        try:
            detail = exc.response.json().get('detail', 'Voice transcription is unavailable.')
        except ValueError:
            detail = 'Voice transcription is unavailable.'
        state['voice_notice'] = ('error', detail)
    except (httpx.RequestError, ValueError, KeyError):
        state.pop('voice_digest', None)
        state['voice_notice'] = ('error', 'Could not transcribe this recording. Please record again or type your question.')
