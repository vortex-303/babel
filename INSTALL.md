# Install guide

Step-by-step walkthroughs for setting up babel on a fresh machine. Pick your OS below. Both paths end at `./dev.sh` running all three services on localhost.

- [macOS (Apple Silicon)](#macos-apple-silicon)
- [Linux (Ubuntu 24.04 + NVIDIA)](#linux-ubuntu-2404--nvidia)
- [Linux (CPU-only or AMD)](#linux-cpu-only-or-amd)

---

## macOS (Apple Silicon)

~10 minutes. Metal GPU acceleration is baked into the llama.cpp brew formula — no extra config.

### 1. Homebrew (skip if already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 2. All native tools in one go

```bash
brew install llama.cpp node pnpm git
```

### 3. uv (Python toolchain)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc
```

### 4. Sanity checks

```bash
llama-server --version
node --version        # should be 20+
pnpm --version
uv --version
```

### 5. Clone and run

```bash
git clone git@github.com:vortex-303/babel.git
cd babel
./setup.sh
./dev.sh
```

Open http://127.0.0.1:3838. On first run `llama-server` downloads the TranslateGemma GGUF (~2.6 GB) into `~/Library/Caches/llama.cpp/`.

---

## Linux (Ubuntu 24.04 + NVIDIA)

~15 minutes. Tested on RTX 4000 Blackwell (Blackwell / `sm_100` — needs CUDA 12.8+ and driver 570+).

### 1. System basics

```bash
sudo apt update
sudo apt install -y git curl unzip ca-certificates
```

### 2. Check your NVIDIA driver (may already be fine)

```bash
nvidia-smi
```

Look at the top-right of the output:
- **Driver Version** must be `570.xx` or newer
- **CUDA Version** must be `12.8` or newer

If both are ≥ that, **skip to step 4**.

### 3. Install driver (only if step 2 wasn't enough)

```bash
sudo apt install -y ubuntu-drivers-common
ubuntu-drivers devices                     # see what's recommended
sudo ubuntu-drivers install nvidia:590     # or latest "recommended"
sudo reboot
# after reboot, re-run nvidia-smi and confirm
```

For Blackwell specifically, use the `-open` kernel module variant (`nvidia-driver-590-open`) — NVIDIA requires open modules for Turing and newer.

### 4. Install llama.cpp (prebuilt CUDA 13.1 binary — no build step needed)

Grab the latest CUDA 13.1 release. Visit https://github.com/ggml-org/llama.cpp/releases/latest in a browser to confirm the current `bXXXX` tag, then substitute it below:

```bash
cd ~
mkdir -p bin/llama.cpp && cd bin/llama.cpp
curl -LO https://github.com/ggml-org/llama.cpp/releases/download/bXXXX/llama-bXXXX-bin-ubuntu-cuda-13.1-x64.zip
unzip llama-bXXXX-bin-ubuntu-cuda-13.1-x64.zip
ls build/bin/ | head -5

echo 'export PATH="$HOME/bin/llama.cpp/build/bin:$PATH"' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH="$HOME/bin/llama.cpp/build/bin:$LD_LIBRARY_PATH"' >> ~/.bashrc
source ~/.bashrc

llama-server --version
```

If your system has only CUDA 12.x drivers, use the `cuda-12.4-x64.zip` asset instead.

### 5. Node + pnpm

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm
```

### 6. uv (Python toolchain)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 7. Clone and run

```bash
cd ~
git clone git@github.com:vortex-303/babel.git
cd babel
./setup.sh
./dev.sh
```

Open http://127.0.0.1:3838. First run downloads the GGUF (~2.6 GB) into `~/.cache/huggingface/hub/`.

**Accessing from a laptop** (if babel is on a remote GPU box):

```bash
# from your laptop
ssh -L 3838:127.0.0.1:3838 -L 8765:127.0.0.1:8765 you@gpu-box
```

Then open http://127.0.0.1:3838 in your laptop's browser.

---

## Linux (CPU-only or AMD)

Follow the Ubuntu NVIDIA walkthrough with two changes:

- **Step 2–3 (driver)**: skip entirely for CPU, or install ROCm packages for AMD
- **Step 4 (llama.cpp)**: swap the archive for `llama-bXXXX-bin-ubuntu-x64.zip` (CPU) or `llama-bXXXX-bin-ubuntu-rocm-x64.zip` (AMD)
- **Edit `dev.sh`**: change `--n-gpu-layers 999` to `--n-gpu-layers 0` for CPU

Expected tok/s on the 4B Q4_K_M model:
- Apple M-series Metal: **35–50 tok/s**
- NVIDIA RTX 4000+ CUDA: **60–100 tok/s**
- AMD 7900 XT ROCm: **40–60 tok/s**
- Modern x86 CPU: **5–15 tok/s** (fine for testing, painful for books)

---

## Troubleshooting

**`llama-server: command not found` after step 4**
Your `PATH` didn't update — run `source ~/.bashrc` or open a new shell.

**`error while loading shared libraries: libcudart.so.13`**
CUDA runtime mismatch. Install `libcudart12` (Ubuntu) or use the matching `cuda-12.x` llama.cpp archive.

**`pnpm: command not found`**
`sudo npm install -g pnpm` didn't persist — try `npm install -g pnpm` without sudo, or use `corepack enable pnpm`.

**Frontend loads but uploads fail with `ECONNRESET`**
Backend crashed or restarted mid-upload. Check `jobs/backend.log`. If a job is stuck in `TRANSLATING`, the startup hook in `backend/app/main.py` will mark it FAILED on next boot.

**Translations come back as hallucinated Python / echoed English**
`llama-server` was started with `--chat-template gemma` (bypasses TranslateGemma's required template). `dev.sh` ships with this already removed; verify `ps aux | grep llama-server` shows no `--chat-template` flag.

**Port already in use**
`dev.sh` reuses anything on the port rather than killing it. To start fresh: `pkill -9 -f llama-server; pkill -9 -f uvicorn; pkill -9 -f "next dev"` then re-run.
