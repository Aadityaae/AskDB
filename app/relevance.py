import re
from functools import lru_cache
from collections import deque
from app.config import settings


@lru_cache
def embedding_model():
    from sentence_transformers import SentenceTransformer
    # Never download weights during a query. Preload them explicitly during setup.
    return SentenceTransformer(settings().embedding_model, local_files_only=True)


def similarity(left: str, right: str) -> float:
    model = embedding_model()
    vectors = model.encode([left, right], normalize_embeddings=True)
    return max(0.0, min(1.0, float(vectors[0] @ vectors[1])))


def select_schema(question: str, schema: dict) -> tuple[dict, list[str]]:
    names = list(schema)
    descriptions = [n + ' ' + ' '.join(schema[n]['columns']) for n in names]
    warnings = []
    try:
        vectors = embedding_model().encode([question] + descriptions, normalize_embeddings=True)
        scores = [float(vectors[0] @ v) for v in vectors[1:]]
    except Exception:
        warnings.append('Local embeddings unavailable; schema selection uses lexical overlap. Meaning validation is unavailable.')
        terms = set(re.findall(r'\w+', question.lower()))
        scores = [len(terms & set(re.findall(r'\w+', d.lower().replace('_', ' ')))) for d in descriptions]
    chosen = set(sorted(names, key=lambda n: scores[names.index(n)], reverse=True)[:4])
    graph = {n: set() for n in names}
    for n, info in schema.items():
        for fk in info['foreign_keys']:
            other = fk['referred_table']
            if other in graph:
                graph[n].add(other)
                graph[other].add(n)
    # Include shortest foreign-key paths between selected tables.
    for source in list(chosen):
        queue = deque([(source, [source])])
        seen = {source}
        while queue:
            node, path = queue.popleft()
            if node in chosen:
                chosen.update(path)
            for neighbor in graph[node] - seen:
                seen.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return {n: schema[n] for n in names if n in chosen}, warnings
