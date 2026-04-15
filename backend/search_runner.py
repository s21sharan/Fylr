"""CLI entry point for semantic search: indexing and querying."""
import json
import os
import sys
import tempfile

from search.embeddings import EmbeddingsGenerator
from search.faiss_index import FaissIndexManager


def read_text_file(file_path):
    """Read plain-text content from a .txt file."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def read_pdf_file(file_path):
    """Extract text from a PDF using PyPDF2."""
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def index_directory(directory, index_path):
    """Walk *directory*, embed .txt/.pdf files, build a FAISS index at *index_path*."""
    embeddings = EmbeddingsGenerator()
    index_manager = FaissIndexManager(index_path=index_path)

    indexed = 0
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".txt", ".pdf"):
                continue

            file_path = os.path.join(root, fname)
            try:
                if ext == ".txt":
                    content = read_text_file(file_path)
                else:
                    content = read_pdf_file(file_path)

                if not content.strip():
                    continue

                vector = embeddings.generate_embedding(content)
                index_manager.add_vectors([vector], [file_path])
                indexed += 1
            except Exception as exc:
                print(f"Skipping {file_path}: {exc}", file=sys.stderr)

    return indexed


def search_index(query, index_path, k=5):
    """Load the FAISS index at *index_path* and return the top-k results."""
    embeddings = EmbeddingsGenerator()
    index_manager = FaissIndexManager(index_path=index_path)

    query_vector = embeddings.generate_embedding(query)
    raw_results = index_manager.search(query_vector, k)

    results = []
    for file_path, distance in raw_results:
        score = round(1.0 / (1.0 + distance), 4)
        results.append({"file_path": file_path, "score": score})
    return results


def main():
    with open(sys.argv[1], "r") as f:
        config = json.load(f)

    action = config["action"]
    index_path = config.get("index_path", os.path.join(tempfile.gettempdir(), "fylr_search_index"))

    if action == "index":
        directory = config["directory"]
        count = index_directory(directory, index_path)
        print(json.dumps({"success": True, "indexed": count}))

    elif action == "search":
        query = config["query"]
        k = config.get("k", 5)
        results = search_index(query, index_path, k)
        print(json.dumps({"success": True, "results": results}))

    else:
        print(json.dumps({"success": False, "error": f"Unknown action: {action}"}))


if __name__ == "__main__":
    main()
