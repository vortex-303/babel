# CLAUDE.md

Repo guide for AI coding assistants (Claude Code, Cursor, etc.). Read this before making changes — contains non-obvious context that will save you hours.

## What is this

Local-first long-document translation service. PDFs/EPUBs/DOCX → coherent translations via `llama.cpp` running [TranslateGemma](https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/). Frontend (Next.js 16) + backend (FastAPI) + inference server, all on localhost.

## Layout

```
babel/
├── backend/
│   ├── app/
│   │   ├── main.py                 FastAPI app, lifespan hook
│   │   ├── config.py               BABEL_* env settings (pydantic-settings)
│   │   ├── db.py                   SQLModel engine, new_session() for bg tasks
│   │   ├── models.py               Document, Job, Chunk, GlossaryTerm + JobStatus
│   │   ├── routers/
│   │   │   ├── documents.py        POST /documents (upload + ingest)
│   │   │   └── jobs.py             analyze, translate, chunks, cancel, download
│   │   ├── services/
│   │   │   ├── ingest.py           PDF/EPUB/DOCX/TXT/MD parsers
│   │   │   ├── analyzer.py         tiktoken chunking + ETA + cost estimate
│   │   │   ├── translate.py        BackgroundTask that walks chunks
│   │   │   └── assemble.py         md / docx (python-docx) / epub (ebooklib)
│   │   └── adapters/
│   │       ├── base.py             TranslationAdapter protocol
│   │       └── llamacpp.py         /completion client with exact prompt template
│   ├── tests/                      pytest — run before shipping
│   ├── pyproject.toml              deps via uv
│   └── README.md                   backend-specific notes
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx                upload + recent docs
│   │   ├── _components/            UploadCard, RecentDocuments, HealthBadge
│   │   ├── _lib/languages.ts       40 TranslateGemma langs + Spanish/PT variants
│   │   └── documents/[id]/
│   │       ├── page.tsx            server component, fetches document
│   │       └── _analyze-panel.tsx  the main UX: analyze, translate, progress, download
│   ├── next.config.ts              rewrite /api/* → :8765, proxyClientMaxBodySize 500mb
│   ├── AGENTS.md                   "this is Next.js 16 — read node_modules/next/dist/docs/ first"
│   └── package.json                next dev on 127.0.0.1:3838
├── dev.sh                          starts all 3 services, reuses anything already on port
├── setup.sh                        first-time install (brew/uv/pnpm prereq check + deps)
└── .gitignore                      excludes venv, node_modules, sqlite, logs, user uploads, GGUFs
```

## Commands

```bash
# Start everything (recommended during dev)
./dev.sh

# Backend tests
cd backend && .venv/bin/python -m pytest tests/ -q

# Manually interact with backend
curl http://127.0.0.1:8765/health
sqlite3 backend/jobs/babel.sqlite "SELECT * FROM job ORDER BY id DESC LIMIT 5;"

# Inspect llama-server state
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/props | python3 -m json.tool
```

## Critical learnings (don't repeat my mistakes)

### TranslateGemma requires its exact prompt template

`--chat-template gemma` on `llama-server` strips the training instructions, and the model falls back to autocomplete mode — you'll see echoed English source followed by hallucinated Python code. The model will not translate.

**Fix already in place:** `adapters/llamacpp.py` hits the `/completion` endpoint (not `/v1/chat/completions`) with a hand-rendered prompt that matches the model's embedded Jinja template byte-for-byte. The template lives in GGUF metadata; reproduce below.

### Inspecting the model's chat template

`llama-server /props` returns the *active* template, not the one embedded in the GGUF. To inspect the real template:

```bash
.venv/bin/python -c "
from gguf import GGUFReader
r = GGUFReader('<path-to-gguf>')
f = r.fields['tokenizer.chat_template']
print(bytes(f.parts[f.data[0]]).decode())
"
```

The cached GGUF from llama-server `-hf` lives at:
`~/.cache/huggingface/hub/models--mradermacher--translategemma-4b-it-GGUF/blobs/<hash>`

Find the active path via `lsof -p $(pgrep llama-server) | grep gguf`.

### Language code normalization

The model's `languages` dict has BCP-47 country codes (`es-AR`, `es-MX`, `pt-BR`, …) but NOT macro-regional codes like `es-419` or `zh-Hans`. `adapters/llamacpp.py::_LANG_ALIASES` maps the latter to the base code before rendering the prompt.

### BackgroundTasks + --reload is fragile

`uvicorn --reload` kills background tasks when a watched file changes. If you edit backend code mid-translation, the orchestrator is canceled, the job stays `TRANSLATING` in the DB, and the UI polls forever. Mitigations in place:

- Startup hook (`main.py::_mark_stale_translations_failed`) marks any stuck `TRANSLATING` job as FAILED on boot.
- Orchestrator checks job status before each chunk and exits cleanly if canceled.
- `POST /jobs/{id}/cancel` endpoint lets users abort in-flight work.

If you see `translated_chunks` counter out of sync with actual translated chunks, recompute:
```sql
UPDATE job SET translated_chunks =
  (SELECT COUNT(*) FROM chunk WHERE chunk.job_id = job.id AND chunk.translated_text IS NOT NULL)
WHERE status = 'TRANSLATING';
```

### Next.js 16 quirks

- **Read `frontend/node_modules/next/dist/docs/` before writing frontend code.** APIs have changed from Next 15.
- Proxy request body cap defaults to 10 MB — raised to 500 MB in `next.config.ts` via `experimental.proxyClientMaxBodySize` (renamed from `middlewareClientMaxBodySize` in Next 16).
- Dev server binds to `127.0.0.1` explicitly in `package.json` so HMR websockets from the browser connect cleanly.

### File picker pattern

Use native `<label>` wrapping the `<input type="file">` rather than programmatic `inputRef.current?.click()`. The native pattern works across all browsers; the ref pattern was occasionally being blocked by browser policy.

## Testing

Run before any commit:

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Tests use:
- `httpx.MockTransport` for the llama-server adapter (no real network)
- In-memory SQLite for the orchestrator (no disk)
- python-docx + ebooklib round-trips for assembly

## Memory files

If you're Claude Code with auto-memory, check `~/.claude/projects/-Users-n/memory/babel_project.md` for the latest phase status and what's been shipped.

## What's next (not implemented)

- **Phase 3**: glossary extraction + user review before long runs
- **Phase 4**: SSE streaming progress (currently 2s polling)
- **Cloud adapters**: Gemini, Claude, Ollama stubs exist in the analyzer cost table but no runtime
- **Language auto-detect** on `/analyze` to catch source/target mismatches before a long run
- **Source-format bug**: PDF ingestion uses `doc.page_count` which gets surfaced as "Chapters" in the UI — it's actually pages. Real chapter detection needs PDF outline parsing.
