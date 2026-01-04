from sentence_transformers import SentenceTransformer
from functools import lru_cache

@lru_cache(maxsize=1)
def get_model():
    return SentenceTransformer("BAAI/bge-m3")

def embed_texts(texts: list[str]):
    model = get_model()
    embeddings = model.encode(
        texts,
        normalize_embeddings=True
    )
    return embeddings.tolist()
