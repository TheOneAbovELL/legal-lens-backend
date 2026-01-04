from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("BAAI/bge-m3")

def embed_texts(texts: list[str]):
    embeddings = _model.encode(
        texts,
        normalize_embeddings=True
    )
    return embeddings.tolist()
