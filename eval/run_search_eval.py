#!/usr/bin/env python3
"""Search evaluation harness for Fylr.

Builds the synthetic corpus (if missing), indexes every file, runs all
queries from queries.yaml against each search mode, and reports:
  - Recall@5, Recall@10
  - Mean Reciprocal Rank (MRR)
  - p50 / p95 query latency
  - Index build time

Results are saved to eval/results/<timestamp>.json and eval/results/latest.md.

Usage:
    python eval/run_search_eval.py
    # or:  make eval-search
"""

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Ensure project root and backend dir are on sys.path so that
# `from llm import ...` inside backend modules resolves correctly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from eval.build_corpus import build_corpus

# We import the individual components directly rather than SearchManager
# so we can control index paths and avoid writing to the user's data dir.
from backend.search.bm25 import BM25Index
from backend.search.embeddings import EmbeddingsGenerator
from backend.search.faiss_index import FaissIndexManager
from backend.search.hybrid import HybridSearcher

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
QUERIES_PATH = EVAL_DIR / "queries.yaml"
RESULTS_DIR = EVAL_DIR / "results"

SEARCH_MODES = ["keyword", "embedding", "hybrid"]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant docs found in the top-k results."""
    if not relevant:
        return 0.0
    found = sum(1 for r in retrieved[:k] if r in relevant)
    return found / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    """1 / rank of the first relevant result (0 if none found)."""
    for i, r in enumerate(retrieved):
        if r in relevant:
            return 1.0 / (i + 1)
    return 0.0


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def ensure_corpus() -> list[str]:
    """Build corpus if the directory is missing or empty. Returns file list."""
    if CORPUS_DIR.exists() and any(CORPUS_DIR.rglob("*")):
        # Already there -- collect relative paths
        return [
            str(p.relative_to(CORPUS_DIR))
            for p in CORPUS_DIR.rglob("*")
            if p.is_file()
        ]
    print("Corpus not found -- building ...")
    return build_corpus(str(CORPUS_DIR))


def load_queries() -> list[dict]:
    with open(QUERIES_PATH, "r") as f:
        return yaml.safe_load(f)


def build_index(file_paths: list[str]):
    """Index all corpus files. Returns (hybrid_searcher, build_time_s)."""
    # Use a temp directory for the FAISS index so we don't pollute data/
    import tempfile
    idx_dir = tempfile.mkdtemp(prefix="fylr_eval_idx_")
    idx_path = os.path.join(idx_dir, "eval_index")

    bm25 = BM25Index()
    embeddings = EmbeddingsGenerator()
    faiss_mgr = FaissIndexManager(index_path=idx_path)

    t0 = time.perf_counter()

    # Read all files and index them
    all_paths = []
    all_contents = []
    for rel in file_paths:
        full = CORPUS_DIR / rel
        try:
            content = full.read_text(encoding="utf-8")
        except Exception:
            continue
        all_paths.append(rel)
        all_contents.append(content)

    # BM25 batch add
    bm25.add_documents(all_paths, all_contents)

    # Embeddings + FAISS batch add
    vecs = embeddings.generate_embeddings_batch(all_contents)
    faiss_mgr.add_vectors(vecs, all_paths)

    build_time = time.perf_counter() - t0

    searcher = HybridSearcher(
        bm25_index=bm25,
        embeddings_generator=embeddings,
        faiss_index_manager=faiss_mgr,
    )
    return searcher, build_time


def run_eval(searcher: HybridSearcher, queries: list[dict]):
    """Run all queries in every mode. Returns per-mode metrics dict."""
    results = {}

    for mode in SEARCH_MODES:
        recall5_list = []
        recall10_list = []
        mrr_list = []
        latencies = []

        for q in queries:
            query_text = q["query"]
            relevant = set(q["relevant"])

            t0 = time.perf_counter()
            hits = searcher.search(query_text, k=10, mode=mode)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            retrieved = [path for path, _score in hits]

            recall5_list.append(recall_at_k(retrieved, relevant, 5))
            recall10_list.append(recall_at_k(retrieved, relevant, 10))
            mrr_list.append(reciprocal_rank(retrieved, relevant))
            latencies.append(elapsed_ms)

        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        results[mode] = {
            "recall_at_5": round(statistics.mean(recall5_list), 4),
            "recall_at_10": round(statistics.mean(recall10_list), 4),
            "mrr": round(statistics.mean(mrr_list), 4),
            "latency_p50_ms": round(latencies_sorted[n // 2], 2),
            "latency_p95_ms": round(latencies_sorted[int(n * 0.95)], 2),
            "num_queries": len(queries),
        }

    return results


def save_results(metrics: dict, build_time: float, num_files: int):
    """Persist results as JSON and a markdown summary."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "timestamp": ts,
        "num_corpus_files": num_files,
        "index_build_time_s": round(build_time, 2),
        "modes": metrics,
    }

    # JSON
    json_path = RESULTS_DIR / f"{ts}.json"
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)

    # Markdown table
    lines = [
        "# Search Eval Results",
        "",
        f"Run: {ts}",
        f"Corpus: {num_files} files",
        f"Index build: {build_time:.2f}s",
        "",
        "| Mode | Recall@5 | Recall@10 | MRR | p50 (ms) | p95 (ms) |",
        "|------|----------|-----------|-----|----------|----------|",
    ]
    for mode in SEARCH_MODES:
        m = metrics[mode]
        lines.append(
            f"| {mode} | {m['recall_at_5']:.4f} | {m['recall_at_10']:.4f} "
            f"| {m['mrr']:.4f} | {m['latency_p50_ms']:.2f} | {m['latency_p95_ms']:.2f} |"
        )
    lines.append("")

    md_path = RESULTS_DIR / "latest.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Fylr Search Eval ===\n")

    # 1. Corpus
    print("Step 1: Ensuring corpus exists ...")
    file_paths = ensure_corpus()
    print(f"  {len(file_paths)} files in corpus\n")

    # 2. Load queries
    print("Step 2: Loading queries ...")
    queries = load_queries()
    print(f"  {len(queries)} queries loaded\n")

    # 3. Build index
    print("Step 3: Building index (BM25 + embeddings + FAISS) ...")
    searcher, build_time = build_index(file_paths)
    print(f"  Index built in {build_time:.2f}s\n")

    # 4. Run eval
    print("Step 4: Running queries across modes ...")
    metrics = run_eval(searcher, queries)
    print()

    # 5. Report
    for mode in SEARCH_MODES:
        m = metrics[mode]
        print(f"  [{mode}]")
        print(f"    Recall@5:  {m['recall_at_5']:.4f}")
        print(f"    Recall@10: {m['recall_at_10']:.4f}")
        print(f"    MRR:       {m['mrr']:.4f}")
        print(f"    Latency p50/p95: {m['latency_p50_ms']:.1f}ms / {m['latency_p95_ms']:.1f}ms")
        print()

    json_path, md_path = save_results(metrics, build_time, len(file_paths))
    print(f"Results saved to:\n  {json_path}\n  {md_path}")


if __name__ == "__main__":
    main()
