def split_text(text: str, chunk_size: int = 200, overlap: int = 50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap

    return chunks


def chunk_documents(documents):
    all_chunks = []

    for doc in documents:
        chunks = split_text(doc["content"])
        for idx, chunk in enumerate(chunks):
            all_chunks.append({
                "source": doc["source"],
                "chunk_id": idx,
                "content": chunk
            })

    return all_chunks
