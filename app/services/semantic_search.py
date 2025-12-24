import numpy as np
from app.services.embeddings import embed_texts

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_most_relevant_chunk(query: str, chunks, vectors):
    query_vector = embed_texts([query])[0]

    best_score = -1
    best_chunk = None

    for chunk, vector in zip(chunks, vectors):
        score = cosine_similarity(query_vector, vector)
        if score > best_score:
            best_score = score
            best_chunk = chunk

    return best_chunk
