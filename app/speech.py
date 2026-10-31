"""Local speech recognition. Audio is never logged or persisted as application data."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock
from math import gcd
import logging
import wave
from app.config import settings

MAX_AUDIO_BYTES = 6 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
inference_lock = Lock()
model_load_lock = Lock()


class InvalidAudio(ValueError):
    pass


class SpeechUnavailable(RuntimeError):
    pass


def validate_recording(data: bytes) -> float:
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise InvalidAudio('Record a short question, up to 60 seconds and 6 MB.')
    try:
        with wave.open(BytesIO(data)) as recording:
            rate = recording.getframerate()
            if not 8000 <= rate <= 48000 or recording.getnchannels() not in (1, 2) or recording.getsampwidth() not in (1, 2, 4):
                raise InvalidAudio('Use a standard PCM WAV recording.')
            frames = recording.getnframes()
            duration = frames / rate
            if not 0 < duration <= MAX_AUDIO_SECONDS:
                raise InvalidAudio('Record a question lasting between 0 and 60 seconds.')
            pcm = recording.readframes(frames)
            if len(pcm) != frames * recording.getnchannels() * recording.getsampwidth():
                raise InvalidAudio('The recording is incomplete. Please record it again.')
            return duration
    except (wave.Error, EOFError) as exc:
        raise InvalidAudio('The recording must be a valid PCM WAV file.') from exc


@lru_cache(maxsize=1)
def _load_model():
    path = Path(settings().speech_model_dir).expanduser() / settings().speech_model
    if not (path / 'model.bin').is_file():
        raise SpeechUnavailable('Voice model not installed. Run: docker compose exec api python -m scripts.download_speech_model')
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(str(path), device='cpu', compute_type='int8', cpu_threads=2,
                            num_workers=1, local_files_only=True)
    except Exception as exc:
        raise SpeechUnavailable('The local voice model could not load. Check the model installation.') from exc


def speech_model():
    # Startup warmup and a first recording must share one model allocation.
    with model_load_lock:
        return _load_model()


def warmup():
    """Load existing local assets off the request path; never download a model."""
    path = Path(settings().speech_model_dir).expanduser() / settings().speech_model
    if not (path / 'model.bin').is_file():
        return
    try:
        import numpy  # noqa: F401 - import cost belongs to startup, not recording.
        from scipy.signal import resample_poly  # noqa: F401
        speech_model()
    except Exception:
        logging.warning('Local voice warmup unavailable; recording will report installation errors.')


def transcribe(data: bytes) -> dict:
    duration = validate_recording(data)
    # The recorder supplies PCM WAV: decode it directly rather than relying on
    # multimedia container codecs, and normalize to Whisper's 16 kHz mono input.
    import numpy as np
    from scipy.signal import resample_poly
    with wave.open(BytesIO(data)) as recording:
        width = recording.getsampwidth()
        rate = recording.getframerate()
        pcm = recording.readframes(recording.getnframes())
        audio = np.frombuffer(pcm, dtype={1: 'u1', 2: '<i2', 4: '<i4'}[width]).astype(np.float32)
        audio = (audio - 128) / 128 if width == 1 else audio / float(2 ** (8 * width - 1))
        audio = audio.reshape(-1, recording.getnchannels()).mean(axis=1)
        if rate != 16000:
            divisor = gcd(rate, 16000)
            audio = resample_poly(audio, 16000 // divisor, rate // divisor).astype(np.float32)
    model = speech_model()
    if not inference_lock.acquire(blocking=False):
        raise SpeechUnavailable('Voice transcription is busy. Try again in a moment.')
    try:
        segments, info = model.transcribe(audio, language='en', beam_size=3,
                                          vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(segment.text.strip() for segment in segments if segment.no_speech_prob < .6).strip()
    finally:
        inference_lock.release()
    return {'text': text, 'language': info.language, 'duration_seconds': round(duration, 2)}
