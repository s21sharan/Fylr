# Fylr - Intelligent File Organization System

Fylr is a desktop app that uses AI to organize, rename, and search files. It combines an Electron frontend with a Python backend that supports multiple LLM providers (Google Gemini, OpenAI, Ollama) and exposes its tools through the Model Context Protocol (MCP) so external agents can use it too.

## Demo

Watch Fylr in action: [Demo Video](https://www.youtube.com/watch?v=EPlgKWeQvMo&t=10s&ab_channel=Fylr)

## Screenshots
<img width="1326" height="941" alt="Screenshot 2025-04-13 at 1 24 22 AM" src="https://github.com/user-attachments/assets/17850af8-dcc3-41c9-9c4a-708f17a3957f" />
<img width="1383" height="941" alt="Screenshot 2025-04-13 at 1 16 59 AM" src="https://github.com/user-attachments/assets/f075f614-0a7e-46f1-a17c-293c7a352877" />
<img width="750" height="680" alt="fylr organize demo" src="https://github.com/user-attachments/assets/3b5e5db6-2e49-432e-a6f0-f6276087a7cb" />

## Features

- **Smart File Organization**: Analyzes file contents with AI and proposes logical folder structures
- **Intelligent Renaming**: Generates descriptive filenames from file content using vision and text models
- **Multi-Provider AI**: Google Gemini (default), OpenAI, or local Ollama -- switch from the UI dropdown
- **MCP Server**: Expose search and organization tools to any MCP client (Claude Desktop, Gemini CLI, ADK agents)
- **Hybrid Search**: BM25 keyword + FAISS embedding + reciprocal rank fusion for accurate file retrieval
- **Chat Interface**: Ask questions and reorganize files through natural language
- **Multi-Format Support**: PDFs, images (via vision models), text files, CSVs, code files
- **File Preview**: Click files to preview images, PDFs, and text content in-app
- **Offline Mode**: Full functionality with local Ollama models, no data leaves your machine
- **Rate Limiting**: Built-in token and call limits per provider for cost control
- **Undo Support**: Revert file moves with a single click
- **Cross-platform**: Works on Windows, macOS, and Linux

## Architecture

```
fylr/
├── main.js                          # Electron main process, IPC handlers
├── renderer/                        # Frontend UI (vanilla JS, no framework)
│   ├── index.html
│   ├── renderer.js
│   └── styles.css
├── backend/
│   ├── llm/                         # Provider layer
│   │   ├── base.py                  #   Abstract LLMProvider interface
│   │   ├── gemini_provider.py       #   Google Gemini (google-genai SDK)
│   │   ├── openai_provider.py       #   OpenAI GPT models
│   │   └── ollama_provider.py       #   Ollama local models
│   ├── search/                      # Search system
│   │   ├── bm25.py                  #   BM25 keyword index
│   │   ├── embeddings.py            #   Sentence-transformer embeddings
│   │   ├── faiss_index.py           #   FAISS vector index
│   │   ├── hybrid.py                #   RRF fusion + reranking
│   │   └── search_manager.py        #   Unified search interface
│   ├── mcp_server.py                # MCP server (FastMCP, stdio)
│   ├── file_organizer.py            # Directory analysis + organization
│   ├── rename_files.py              # Content-based file renaming
│   ├── initial_organize_electron.py # Initial organize tab backend
│   ├── chat_agent.py                # Chat-based file management
│   └── live_watcher.py              # Watch directory for new files
├── eval/                            # Evaluation framework
│   ├── build_corpus.py              #   Synthetic corpus generator
│   ├── queries.yaml                 #   Labeled search queries
│   ├── run_search_eval.py           #   Search retrieval eval
│   └── run_organize_eval.py         #   Organization acceptance eval
├── examples/
│   └── adk_agent.py                 # Google ADK agent example
├── docs/
│   ├── MCP.md                       # MCP server setup guide
│   └── DECISIONS.md                 # Technical decision log
└── tests/                           # 48 pytest tests
```

### How it works

1. The Electron main process (`main.js`) handles IPC and spawns Python scripts via `python-shell`
2. Python scripts receive a JSON config file path as `argv[1]` and print JSON results to stdout
3. The provider layer (`backend/llm/`) abstracts model calls so any feature works with any provider
4. Real-time progress is streamed to the UI via `PROGRESS:` prefixed stdout lines

## LLM Providers

Fylr supports three providers, selectable from a dropdown in the UI header:

| Provider | Mode | Models | Key |
|----------|------|--------|-----|
| **Google Gemini** | Online (default) | `gemini-2.5-flash` for chat + vision | `GEMINI_API_KEY` |
| **OpenAI** | Online | `gpt-4o-mini` for chat + vision | `OPENAI_API_KEY` |
| **Ollama** | Offline | `mistral` (text), `llama3.2-vision` (images) | None |

The provider layer uses lazy initialization -- clients are only created on first use. When online mode is selected, Gemini is preferred. If no Gemini key is configured, it falls back to OpenAI automatically.

## MCP Server

Fylr exposes its core functionality through the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio. Any MCP-compatible client can connect: Claude Desktop, Gemini CLI, Google ADK agents.

| Tool | Description |
|------|-------------|
| `search_files(query, k)` | Hybrid search over indexed files |
| `summarize_file(path)` | Summarize a file (text, PDF, or image via vision) |
| `propose_organization(dir)` | Dry-run: propose a folder structure, returns a plan_id |
| `apply_plan(plan_id, confirm)` | Apply a proposed plan (only when confirm=True) |
| `undo_last()` | Reverse the most recently applied plan |

**Safety**: All paths are confined to a configured root folder (rejects `..` and symlink escapes). Nothing is ever deleted. Destructive actions require explicit confirmation. Undo is always available.

Start the server:
```bash
cd backend && python mcp_server.py
```

See [docs/MCP.md](docs/MCP.md) for client configuration (Claude Desktop, Gemini CLI, ADK).

## Hybrid Search

The search system combines three approaches for accurate file retrieval:

- **BM25**: Keyword matching with TF-IDF weighting
- **FAISS Embeddings**: Semantic similarity via `all-MiniLM-L6-v2` sentence-transformers
- **Reciprocal Rank Fusion**: Merges rankings from both systems (k=60)

### Eval Results

195 synthetic files, 53 labeled queries, local embeddings (no API keys):

| Mode | Recall@5 | Recall@10 | MRR | p50 (ms) | p95 (ms) |
|------|----------|-----------|-----|----------|----------|
| keyword | 0.5649 | 0.6465 | 0.5660 | 0.03 | 0.07 |
| embedding | 0.5690 | 0.7354 | 0.7168 | 6.15 | 44.83 |
| **hybrid** | **0.7059** | **0.7691** | **0.7233** | 7.24 | 17.26 |

Hybrid improves Recall@5 by 24% over embedding-only and 25% over keyword-only.

## Installation

### Prerequisites
- Node.js (v14+)
- Python 3.10+
- For offline mode: [Ollama](https://ollama.ai) installed locally

### Setup

```bash
# Clone
git clone https://github.com/s21sharan/Fylr.git
cd Fylr

# Install Node dependencies
npm install

# Install Python dependencies
pip install -r requirements.txt

# Configure API keys (at least one for online mode)
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and/or OPENAI_API_KEY

# Start
npm start
```

### Offline setup (no API keys needed)

```bash
# Install and start Ollama
ollama pull mistral
ollama pull llama3.2-vision

# Start Fylr and toggle to Offline mode in the UI
npm start
```

## Usage

1. **Organize**: Select a directory, Fylr analyzes contents and proposes a folder structure. Review and apply.
2. **Rename**: Select files or a folder, Fylr generates descriptive names from content. Edit and apply.
3. **Search**: Index a directory, then search with natural language queries across all file types.
4. **Chat**: Ask questions like "move all PDFs into a documents folder" and Fylr modifies the structure.
5. **Live Mode**: Watch a directory for new files and auto-categorize them as they arrive.

## Development

```bash
make test            # Run 48 pytest tests
make eval-search     # Search retrieval eval (local, no API keys)
make eval-organize   # Organization acceptance eval (needs a provider)
```

### Running evals

The search eval runs entirely locally using sentence-transformers:
```bash
make eval-search
# Results written to eval/results/latest.md
```

The organize eval needs an LLM provider to propose folder structures:
```bash
python eval/run_organize_eval.py --provider gemini   # or openai, ollama
# Results written to eval/results/organize_latest.md
```

## Privacy and Security

- **Offline mode**: All processing happens locally with Ollama, nothing leaves your machine
- **MCP path confinement**: The MCP server rejects any path outside its configured root folder
- **No deletions**: Fylr never deletes files, only moves and renames
- **Undo support**: Every batch of moves can be reversed
- **Rate limiting**: Built-in token and call limits prevent unexpected API costs
- **No data storage**: Files are analyzed in-memory, no content is persisted

## License

MIT License - see LICENSE file for details
