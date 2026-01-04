from sentence_transformers import SentenceTransformer

# MUST MATCH QDRANT INGESTION MODEL
_model = SentenceTransformer("BAAI/bge-m3")

def embed_texts(texts):
    embeddings = _model.encode(
        texts,
        normalize_embeddings=True
    )
    return embeddings.tolist()
