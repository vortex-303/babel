# babel

Local-first long-document translation — PDFs, EPUBs, DOCX → coherent translations with locked glossaries. Runs fully offline against [TranslateGemma](https://blog.google/innovation-and-ai/technology/developers-tools/translategemma/) via `llama.cpp` (Metal/CUDA), with optional cloud adapters.

LATAM-first: Spanish variant picker (es-AR rioplatense, es-MX, es-ES, es-US, etc.) feeds style hints into the prompt so regional vocabulary and grammar carry through.

- **Backend**: FastAPI + SQLModel + SQLite — `backend/`, port `:8765`
- **Frontend**: Next.js 16 + Tailwind v4 — `frontend/`, port `:3838`
- **Inference**: `llama-server` on `:8080` with TranslateGemma 4B Q4_K_M (~2.6 GB)

**Product roadmap + the "why":** see **[PLAN.md](./PLAN.md)** — ultimate goal, privacy story, pricing, open questions.

## Install

Full step-by-step walkthroughs are in **[INSTALL.md](./INSTALL.md)** — pick macOS (Apple Silicon), Linux + NVIDIA, or Linux CPU/AMD. Quick summary below.

**Running a pull-worker on your Mac / Linux box** (so jobs posted to babeltower.lat actually translate on your GPU) — see **[docs/WORKERS.md](./docs/WORKERS.md)**. Works on macOS (Metal) and Ubuntu 22.04 / 24.04 (NVIDIA), same flow.

**Deploying your own babeltower-style website from scratch**? See **[DEPLOY-UBUNTU.md](./DEPLOY-UBUNTU.md)** for the Ubuntu + tunnel setup that predates the pull-worker split.

### macOS (Apple Silicon)

```bash
brew install llama.cpp node pnpm
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone git@github.com:vortex-303/babel.git && cd babel
./setup.sh
```

Metal GPU acceleration works out of the box.

### Linux (Ubuntu 24.04 + NVIDIA)

```bash
# Verify driver 570+ and CUDA 12.8+
nvidia-smi

# Grab prebuilt CUDA llama.cpp (see INSTALL.md for latest b-tag)
curl -LO https://github.com/ggml-org/llama.cpp/releases/download/bXXXX/llama-bXXXX-bin-ubuntu-cuda-13.1-x64.zip
unzip llama-bXXXX-bin-ubuntu-cuda-13.1-x64.zip -d ~/bin/llama.cpp
echo 'export PATH="$HOME/bin/llama.cpp/build/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

# Node + pnpm + uv
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
sudo npm install -g pnpm
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone git@github.com:vortex-303/babel.git && cd babel
./setup.sh
```

No cmake/build toolchain required — the prebuilt binary is ~100 MB.

**Other setups** (CPU-only, AMD ROCm, older Ubuntu, custom GPU tiers) — see [INSTALL.md](./INSTALL.md).

## Run everything

```bash
./dev.sh
```

One command starts all three services. On first run `llama-server` downloads the GGUF (~2.6 GB) into `~/Library/Caches/llama.cpp/`. Ctrl+C stops all three. Logs go to `jobs/{llama-server,backend,frontend}.log`.

- Frontend: <http://127.0.0.1:3838>
- Backend health: <http://127.0.0.1:8765/health>
- Llama-server health: <http://127.0.0.1:8080/health>

## Use it

1. Open the frontend, drop a PDF/EPUB/DOCX/TXT/MD in.
2. On the document page, pick source + target language (and the Spanish/Portuguese variant if relevant), click **Analyze**.
3. Review chunks, chunk count, token cost estimate, ETA.
4. Click **Start translation** — a background task walks the chunks sequentially; progress streams live in the UI.
5. When status is `done`, download as `.md`, `.docx`, or `.epub`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

## Architecture at a glance

```
frontend (Next.js)  ─┐
  :3838              │ rewrite /api/* →  backend (FastAPI)
                     │                     :8765
                     └──────────────────>  ├── services/ingest.py       PDF/EPUB/DOCX → paragraphs
                                           ├── services/analyzer.py     token count, chunking, ETA
                                           ├── services/translate.py    orchestrator, polls status
                                           ├── services/assemble.py     md / docx / epub assembly
                                           ├── adapters/llamacpp.py  ──┐
                                           └── SQLite (backend/jobs/)  │
                                                                       │  /completion
                                                                       ▼
                                                             llama-server  :8080
                                                             (TranslateGemma 4B Q4_K_M)
```

Adapter pattern makes it trivial to swap in Ollama, Gemini, or Claude later — only `llamacpp` is wired today.

## Project layout

```
babel/
├── dev.sh               — one-command launcher (llama + backend + frontend)
├── setup.sh             — first-time install on a fresh machine
├── backend/             — FastAPI service, SQLModel, adapters
├── frontend/            — Next.js UI
├── jobs/                — dev.sh log dropzone (gitignored)
└── CLAUDE.md            — AI-assistant playbook (read this before coding)
```

## License

Private. Sole author: Nicolas Ruggieri (vortex-303).
