import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DOCS_PATH = os.path.join(BASE_DIR, "data", "legal_docs")

def load_legal_documents():
    documents = []

    for filename in os.listdir(DOCS_PATH):
        if filename.endswith(".txt"):
            file_path = os.path.join(DOCS_PATH, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
                documents.append({
                    "source": filename,
                    "content": text
                })

    return documents
