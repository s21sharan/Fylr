# Fylr — CLAUDE.md

## What is this project?

Fylr is a desktop file management app that uses AI to rename, organize, and search files. Built with Electron (frontend) + Python (backend).

## Architecture

- **main.js** — Electron main process, all IPC handlers (~20), spawns Python via `python-shell`
- **renderer/** — Single-page frontend (index.html, renderer.js, styles.css). No framework, vanilla JS.
- **backend/** — Python modules for file analysis, renaming, organizing, chat, search, live watch
- **Communication** — Main process writes JSON config to temp file, runs Python script with `PythonShell`, reads JSON result from stdout. Real-time progress via `PROGRESS:` and `TOKEN_USAGE:` prefixed stdout lines.

## Key commands

```bash
npm start          # Run the app (electron .)
```

Python backend requires: `pip install -r requirements.txt` and a `.env` with `OPENAI_API_KEY` for online mode. Offline mode uses Ollama at `localhost:11434`.

## Tabs / Features

| Tab | Backend file | What it does |
|-----|-------------|--------------|
| File Rename | `backend/rename_files.py` | Vision analysis + LLM naming |
| Initial Organize | `backend/initial_organize_electron.py` | Analyze dir, suggest folder structure |
| Live Mode | `backend/live_watcher.py` | Watchdog monitors dir for new files |
| Agentic Search | `backend/search/` | Embeddings + FAISS vector search |

Chat agent (`backend/chat_agent.py`) allows natural language file structure modification.

## Dual mode system

- **Online mode** — OpenAI GPT-4 / GPT-4o-mini for text + vision
- **Offline mode** — Ollama with `mistral` (text), `llama3.2-vision` (images)
- Toggle in UI header. Rate limits: 30k tokens, 10 calls per session.

## Code conventions

- Frontend is one large `renderer.js` file. Functions are organized by tab/feature.
- IPC channel names: kebab-case (`generate-filenames`, `apply-changes`, `start-live-watch`)
- Python scripts accept a JSON config file path as argv[1], print JSON result to stdout
- Python logging goes to stdout (captured by PythonShell) and to `.log` files
- CSS uses custom properties defined at top of styles.css (warm color palette)

## Things to know

- `moondream` pip package (v0.1.0+) is cloud-only now. Local image analysis uses Ollama `llama3.2-vision`.
- `find_python.js` locates the Python interpreter — checks venv, system paths, common install locations.
- Undo support is single-level: stores a manifest of original → new paths.
- No test suite. `test_openai_vision.py` and `test_limits.py` are manual validation scripts.
- The `.env` file is at the project root (not in `backend/`).
