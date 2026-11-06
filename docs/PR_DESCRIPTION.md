# PR: Google Upgrades -- Gemini provider, MCP server, hybrid search

## What changed

This branch adds three major capabilities to Fylr:

### 1. Provider layer + Gemini integration

- New `backend/llm/` package with an abstract `LLMProvider` interface and three implementations: `GeminiProvider` (google-genai SDK), `OpenAIProvider`, `OllamaProvider`.
- All backend modules (rename_files, file_organizer, initial_organize_electron, chat_agent, live_watcher) refactored to use the provider layer instead of direct API calls.
- Gemini is the default online provider. OpenAI is available as a fallback. Ollama handles offline mode.
- UI dropdown in the header lets users pick their provider. The selection is passed through to Python via the config JSON.
- Fixed a bug in `SearchManager.__init__` that passed an unused `client` arg to `EmbeddingsGenerator`.

### 2. MCP server (5 tools)

`backend/mcp_server.py` exposes Fylr as an MCP server over stdio, usable from Gemini CLI, Google ADK agents, or Claude Desktop.

| Tool | What it does |
|------|-------------|
| `search_files(query, k)` | Hybrid search over indexed files |
| `summarize_file(path)` | Text/PDF/image summary via LLM |
| `propose_organization(dir)` | Dry-run folder structure proposal (returns a plan_id) |
| `apply_plan(plan_id, confirm)` | Apply a proposed plan only when confirm=True |
| `undo_last()` | Reverse the last applied plan |

Safety: all paths confined to a root folder (rejects `..` and symlink escapes). Nothing is ever deleted. Destructive actions require explicit confirmation.

### 3. Hybrid search + eval

- BM25 keyword search (`backend/search/bm25.py`) alongside existing FAISS embeddings.
- Reciprocal Rank Fusion combines both into a hybrid mode.
- `SearchManager` now supports `keyword`, `embedding`, `hybrid`, and `hybrid_rerank` modes.

**Search eval results** (195 synthetic files, 53 queries, local sentence-transformers):

| Mode | Recall@5 | Recall@10 | MRR | p50 (ms) | p95 (ms) |
|------|----------|-----------|-----|----------|----------|
| keyword | 0.5649 | 0.6465 | 0.5660 | 0.03 | 0.07 |
| embedding | 0.5690 | 0.7354 | 0.7168 | 6.15 | 44.83 |
| hybrid | 0.7059 | 0.7691 | 0.7233 | 7.24 | 17.26 |

Hybrid improves Recall@5 by 24% over embedding-only and 25% over keyword-only.

### Also included

- `eval/build_corpus.py`: deterministic synthetic corpus generator (195 files, 10 categories)
- `eval/run_search_eval.py` and `eval/run_organize_eval.py`: automated eval scripts
- `examples/adk_agent.py`: Google ADK agent that connects to the Fylr MCP server
- `docs/MCP.md`: setup guide for Gemini CLI, ADK, and Claude Desktop
- `docs/DECISIONS.md`: technical decision log
- 48 pytest tests covering providers, MCP tools, search modes, and RRF math
- `Makefile` with `test`, `eval-search`, `eval-organize` targets

## How to run

### Gemini mode
1. Add `GEMINI_API_KEY=...` to `.env`
2. `npm start` -- select "Gemini" in the provider dropdown

### OpenAI mode
1. Add `OPENAI_API_KEY=...` to `.env`
2. `npm start` -- select "OpenAI" in the provider dropdown

### Offline mode
1. Start Ollama (`ollama serve`)
2. `npm start` -- toggle to Offline

### MCP server
```bash
cd backend && python mcp_server.py
```
See `docs/MCP.md` for client configuration.

### Tests and evals
```bash
make test          # 48 tests
make eval-search   # search eval (no API keys needed)
make eval-organize # organize eval (needs a provider)
```

## Things for Sharan to check

- The provider layer refactor touches every backend module. The JSON-config-in, JSON-out contract with main.js is unchanged, but worth verifying the app works end-to-end in both online and offline modes.
- MCP server path confinement logic in `_validate_path()`.
- The organize eval shows errors when no provider is available (expected when no API key is set). Run with `--provider openai` or `--provider gemini` with a valid key to get real results.
- Dependabot flagged 44 vulnerabilities on the default branch (pre-existing, not from this PR).
