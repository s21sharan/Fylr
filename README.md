# Fylr - Intelligent File Organization System

Fylr is a desktop application that uses AI to automatically organize and rename files in your directories. It combines the power of large language models with a sleek Electron-based interface to make file management effortless.

## 🎥 Demo

Watch Fylr in action: [Demo Video](https://www.youtube.com/watch?v=EPlgKWeQvMo&t=10s&ab_channel=Fylr)

## Screenshots
<img width="1326" height="941" alt="Screenshot 2025-04-13 at 1 24 22 AM" src="https://github.com/user-attachments/assets/17850af8-dcc3-41c9-9c4a-708f17a3957f" />
<img width="1383" height="941" alt="Screenshot 2025-04-13 at 1 16 59 AM" src="https://github.com/user-attachments/assets/f075f614-0a7e-46f1-a17c-293c7a352877" />
<img width="750" height="680" alt="fylr organize demo" src="https://github.com/user-attachments/assets/3b5e5db6-2e49-432e-a6f0-f6276087a7cb" />

## 🚀 Features

- **Intelligent File Organization**: Automatically categorizes files into logical folder structures
- **Smart File Renaming**: Generates meaningful filenames based on file content
- **Dual Mode Operation**: 
  - Online mode with OpenAI GPT models for maximum accuracy
  - Offline mode using local Ollama models for privacy
- **Multi-format Support**: Handles PDFs, images, text files, and more
- **Interactive Chat Interface**: Ask questions about your file organization
- **Semantic Search**: Find files using natural language queries
- **Rate Limiting**: Built-in token and API call limits for cost control
- **Cross-platform**: Works on Windows, macOS, and Linux

## 🛠️ Technology Stack

### Frontend (Electron)
- **Electron**: Desktop application framework
- **HTML/CSS/JavaScript**: Modern web technologies for the UI
- **Node.js**: Runtime environment for the main process

### Backend (Python)
- **Python 3.x**: Core backend language
- **LangChain**: Framework for building LLM applications
- **OpenAI API**: GPT models for online mode
- **Ollama**: Local LLM inference for offline mode
- **FAISS**: Vector database for semantic search
- **PyPDF2**: PDF text extraction
- **Pillow (PIL)**: Image processing
- **python-magic**: File type detection

### AI/ML Components
- **OpenAI GPT-4**: Primary language model for file analysis
- **Local Ollama Models**: Privacy-focused offline processing
- **Embeddings**: Vector representations for semantic search
- **FAISS Index**: Efficient similarity search

### Key Libraries
```python
# Core AI/ML
langchain>=0.1.0
openai>=1.1.0
ollama>=0.1.4
faiss-cpu==1.7.4

# File Processing
PyPDF2
Pillow
python-magic
tqdm

# Utilities
python-dotenv
aiofiles
numpy
```

```javascript
// Electron Dependencies
"electron": "^22.3.27"
"python-shell": "^3.0.1"
"node-fetch": "^3.3.2"
"electron-serve": "^1.3.0"
```

## 🏗️ Architecture

### Application Structure
```
fylr/
├── main.js                 # Electron main process
├── renderer/               # Frontend UI
│   ├── index.html
│   ├── renderer.js
│   └── styles.css
├── backend/                # Python backend
│   ├── file_organizer.py   # Core organization logic
│   ├── chat_agent.py       # Conversational interface
│   ├── rename_files.py     # File renaming functionality
│   └── search/             # Semantic search system
│       ├── embeddings.py
│       ├── faiss_index.pyls -a
│       └── search_manager.py
└── preload.js              # Electron preload script
```

### Data Flow
1. **File Analysis**: Extracts content from various file types
2. **AI Processing**: Sends content to LLM for categorization
3. **Organization**: Creates folder structure based on AI recommendations
4. **Indexing**: Builds searchable embeddings for future queries
5. **User Interaction**: Provides chat interface for refinements

### Mode Switching
- **Online Mode**: Uses OpenAI API for high-accuracy processing
- **Offline Mode**: Falls back to local Ollama models
- **Automatic Fallback**: Switches to offline when rate limits are reached

## Gemini / Gemma Modes

Fylr supports three LLM providers, selectable from a dropdown in the UI header:

- **Google Gemini** (default online) -- uses `gemini-2.0-flash` for text and vision analysis. Requires `GOOGLE_API_KEY` in `.env`.
- **OpenAI** (online fallback) -- uses GPT-4o / GPT-4o-mini. Requires `OPENAI_API_KEY` in `.env`.
- **Ollama** (offline) -- runs locally with `mistral` for text and `llama3.2-vision` for images. No API key needed.

## MCP Server

Fylr exposes its tools through the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) over stdio, so any MCP-compatible client (Claude Desktop, Gemini CLI, Google ADK) can connect.

Available tools:

| Tool | Description |
|------|-------------|
| `search_files` | Search indexed files by text query |
| `summarize_file` | Read a file and return a short summary |
| `propose_organization` | Dry-run: propose a folder structure without moving anything |
| `apply_plan` | Apply a previously proposed plan (requires explicit confirm) |
| `undo_last` | Reverse the most recently applied plan |

See [docs/MCP.md](docs/MCP.md) for setup instructions and client configuration.

## Search

Fylr uses hybrid search combining BM25 keyword matching, FAISS embedding similarity, and reciprocal rank fusion to merge results.

Eval results on a 195-file corpus (index build: 1.27s):

| Mode | Recall@5 | Recall@10 | MRR | p50 (ms) | p95 (ms) |
|------|----------|-----------|-----|----------|----------|
| keyword | 0.5649 | 0.6465 | 0.5660 | 0.03 | 0.07 |
| embedding | 0.5690 | 0.7354 | 0.7168 | 6.15 | 44.83 |
| hybrid | 0.7059 | 0.7691 | 0.7233 | 7.24 | 17.26 |

Hybrid mode improves Recall@5 by ~24% over keyword-only and MRR by ~28%.

## Eval

Run evaluation suites with:

```bash
make eval-search     # search eval -- runs locally, no API keys needed
make eval-organize   # organize eval -- requires a configured LLM provider
```

Results are written to `eval/results/`.

## Development

```bash
make test   # run the test suite
```

## Installation & Setup

### Prerequisites
- Node.js (v14 or higher)
- Python 3.8+
- For offline mode: Ollama installed locally

### Installation Steps
1. Clone the repository
2. Install Node.js dependencies:
   ```bash
   npm install
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   ```bash
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   ```
5. Start the application:
   ```bash
   npm start
   ```

## 💡 How It Works

1. **Select Directory**: Choose a folder you want to organize
2. **AI Analysis**: Fylr analyzes file contents using computer vision and text extraction
3. **Smart Categorization**: Creates logical folder structures based on file types and content
4. **Intelligent Renaming**: Generates descriptive filenames that reflect actual content
5. **Review & Apply**: Preview changes before applying them to your files

## 🎯 Use Cases

- **Document Management**: Organize research papers, reports, and documents
- **Media Libraries**: Sort photos and videos by content and date
- **Download Folders**: Clean up messy download directories
- **Project Files**: Structure development projects and assets
- **Archive Organization**: Systematically organize old files and backups

## 🔒 Privacy & Security

- **Offline Mode**: Process files locally without sending data to external services
- **Rate Limiting**: Built-in controls to manage API usage and costs
- **No Data Storage**: Files are analyzed temporarily without permanent storage
- **Local Processing**: Sensitive files can be processed entirely offline

## 📄 License

MIT License - see LICENSE file for details


