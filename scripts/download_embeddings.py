"""Explicit one-time model download; query handling never downloads model weights."""
from sentence_transformers import SentenceTransformer
from app.config import settings

if __name__ == '__main__':
    SentenceTransformer(settings().embedding_model)
    print('Local embedding model is ready.')
