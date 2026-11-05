# Technical Decisions

Key choices made during the Fylr upgrade, with rationale.

## Gemini as the default online provider

Fylr targets Google's ecosystem. Gemini models are available through a single API key with generous free tiers. Keeping OpenAI as a fallback is simple since the provider abstraction supports both, but Gemini is the default path for new users.

## Model choices

**gemini-2.5-flash** for chat and vision tasks. It handles both text and image inputs in a single model, which simplifies the provider layer (no separate vision model needed). Cost per token is low and latency is acceptable for a desktop app.

**sentence-transformers (all-MiniLM-L6-v2)** for local embeddings. Runs on CPU without a GPU requirement, produces 384-dim vectors that are compact enough for FAISS flat indexes, and has no API key dependency. This keeps the search feature usable in offline mode.

## MCP over stdio, not SSE

Stdio transport was chosen for the MCP server because:

- No port conflicts or firewall issues on the user's machine.
- Claude Desktop, Gemini CLI, and Google ADK all support stdio natively.
- The server lifecycle is tied to the client process, so there is nothing to clean up.
- SSE would add HTTP server dependencies and complicate the startup flow for a local desktop app.

## RRF with k=60 for hybrid search fusion

Reciprocal Rank Fusion merges the BM25 and vector search result lists into a single ranking. The k parameter controls how much weight tail results receive. k=60 is the standard default from the original RRF paper (Cormack et al.) and works well without per-query tuning. It gives a balanced blend where neither lexical nor semantic matches dominate.

## Provider layer: abstract base with lazy initialization

Each LLM provider (Gemini, OpenAI, Ollama) extends a common base class. Providers are initialized lazily on first use rather than at import time. This avoids import errors when a provider's SDK is not installed (e.g., a user who only uses Gemini never needs the openai package). It also keeps startup fast since no API connections are opened until a feature actually needs one.

## BM25 from scratch

The BM25 implementation is a small standalone module rather than a dependency on rank-bm25 or similar libraries. The algorithm is straightforward (term frequency, inverse document frequency, length normalization) and the corpus is small enough that performance is not a concern. Avoiding the extra dependency keeps the install lighter and makes the scoring logic easy to inspect and test.

## No LangChain in the chat agent

The refactored chat agent uses direct API calls through the provider layer instead of LangChain. LangChain adds substantial dependency weight and abstraction layers that are unnecessary here. The chat agent's needs are simple: maintain a message history, call the LLM, and parse tool-use responses. Doing this directly results in fewer dependencies, clearer control flow, and easier debugging.
