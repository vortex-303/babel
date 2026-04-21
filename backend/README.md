# babel backend

Local-first document translation service.

## Setup

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e .
uvicorn app.main:app --reload --port 8765
```

## Tests

```bash
uv pip install pytest pytest-asyncio
.venv/bin/python -m pytest tests/ -q
```

## Architecture

- FastAPI + SQLModel + SQLite
- Model adapter pattern: `llamacpp` (local, implemented), `ollama`/`gemini`/`claude` (profiles only — adapters TBD)
- Translation runs as an in-process FastAPI BackgroundTask; progress is polled via `GET /jobs/{id}`.

## Running llama.cpp locally (Phase 2)

The `llamacpp` adapter talks to `llama-server` over its OpenAI-compatible
`/v1/chat/completions` endpoint.

### 1. Install llama.cpp

```bash
brew install llama.cpp
```

### 2. Start llama-server (auto-downloads the model)

```bash
llama-server -hf mradermacher/translategemma-4b-it-GGUF:Q4_K_M --host 127.0.0.1 --port 8080 --ctx-size 8192 --n-gpu-layers 999 --chat-template gemma
```

Run as a single line — shell line-continuations (`\`) are fragile with
inline comments or trailing whitespace. First run downloads
`translategemma-4b-it.Q4_K_M.gguf` (~2.6 GB) to
`~/Library/Caches/llama.cpp/` on macOS.

**Why `--chat-template gemma`?** TranslateGemma's embedded Jinja template
expects structured content with `source_lang_code`/`target_lang_code` fields on
each message, which the OpenAI chat endpoint doesn't send. Overriding with the
built-in Gemma C++ formatter makes the server accept standard string content;
our adapter passes the language pair in the system prompt instead.

**Alternative — manual download** into the project's `model_cache/`:

```bash
uv pip install -U "huggingface_hub[cli]"
hf download mradermacher/translategemma-4b-it-GGUF \
  translategemma-4b-it.Q4_K_M.gguf \
  --local-dir ../model_cache

llama-server \
  --model ../model_cache/translategemma-4b-it.Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers 999
```

Health check: `curl http://127.0.0.1:8080/health`

### 4. Env overrides

The adapter reads from `app.config.settings`. Override via `BABEL_*` env:

```
BABEL_LLAMACPP_HOST=127.0.0.1
BABEL_LLAMACPP_PORT=8080
BABEL_LLAMACPP_MODEL=translategemma-4b-it.Q4_K_M.gguf
BABEL_CHUNK_TOKENS=1500
BABEL_CHUNK_OVERLAP=200
```

## End-to-end smoke test

```bash
# 1. Upload a small .txt
curl -F "file=@sample.txt" http://127.0.0.1:8765/api/documents

# 2. Create a job for doc 1
curl -X POST http://127.0.0.1:8765/api/jobs \
  -H 'content-type: application/json' \
  -d '{"document_id": 1}'

# 3. Analyze → chunks + estimate
curl -X POST http://127.0.0.1:8765/api/jobs/1/analyze

# 4. Translate (needs llama-server up)
curl -X POST http://127.0.0.1:8765/api/jobs/1/translate

# 5. Poll progress
curl http://127.0.0.1:8765/api/jobs/1

# 6. Read translated chunks
curl http://127.0.0.1:8765/api/jobs/1/chunks
```
