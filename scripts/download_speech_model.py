"""One-time explicit model download; normal transcription is offline."""
from pathlib import Path
from faster_whisper.utils import download_model
from app.config import settings

if __name__ == '__main__':
    cfg = settings()
    target = Path(cfg.speech_model_dir).expanduser() / cfg.speech_model
    target.parent.mkdir(parents=True, exist_ok=True)
    download_model(cfg.speech_model, output_dir=str(target))
    print(f'Local voice model ready: {cfg.speech_model}')
