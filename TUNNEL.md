# Tunnel guide — expose your local llama-server to the public backend

When babel is deployed somewhere public (Vercel frontend + a hosted backend),
the backend still needs a way to call your machine's `llama-server`. The
machine is behind NAT and won't accept inbound connections directly, so we
use an outbound-initiated tunnel.

Recommended: **cloudflared quick tunnel** — free, no signup, 5 minutes.
For a stable `tunnel.babeltower.lat` URL, use a **cloudflared named tunnel**
(also free, requires a Cloudflare account).

Works identically on macOS and Linux.

---

## 1. Install cloudflared

### macOS

```bash
brew install cloudflared
```

### Linux (Ubuntu 24.04)

```bash
# GPG key + repo
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared noble main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared
```

For other distros / ARM: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

Verify:

```bash
cloudflared --version
```

---

## 2. Start babel locally

On your GPU/Mac box, run babel normally. The tunnel only needs to know
about `llama-server` (port 8080) — the backend and frontend stay on the
same machine where the tunnel is terminated:

```bash
cd ~/babel
./dev.sh
```

Wait for `llama-server` to boot (first run downloads the GGUF, ~2.6 GB).

Confirm from the same machine:

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok"}
```

---

## 3a. Quick tunnel (ephemeral URL, zero config)

In a second terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8080
```

Output includes a line like:

```
Your quick tunnel has been created! Visit it at (it may take up to 3
minutes to propagate): https://something-random-1234.trycloudflare.com
```

That URL now proxies to your local `llama-server`. Test from any other
machine:

```bash
curl https://something-random-1234.trycloudflare.com/health
```

The URL survives until you Ctrl+C the tunnel. Fine for testing and demos;
for production you want a named tunnel (next section).

---

## 3b. Named tunnel (stable URL like `tunnel.babeltower.lat`)

Assuming `babeltower.lat` is managed in your Cloudflare account.

```bash
# One-time: log in + let cloudflared store your credentials
cloudflared tunnel login
# browser opens → pick the babeltower.lat zone

# Create a named tunnel (one-time)
cloudflared tunnel create babel-llama

# Route the DNS name tunnel.babeltower.lat to it (one-time)
cloudflared tunnel route dns babel-llama tunnel.babeltower.lat

# Config file — save as ~/.cloudflared/config.yml
cat > ~/.cloudflared/config.yml <<'YAML'
tunnel: babel-llama
credentials-file: /Users/YOU/.cloudflared/<tunnel-id>.json  # edit to your path

ingress:
  - hostname: tunnel.babeltower.lat
    service: http://127.0.0.1:8080
  - service: http_status:404
YAML

# Run the tunnel
cloudflared tunnel run babel-llama
```

Now `https://tunnel.babeltower.lat` always proxies to your local
`llama-server` whenever this process is running.

### Run as a system service (survives reboots)

**macOS (launchd):**

```bash
sudo cloudflared service install
```

**Linux (systemd):**

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Check status:

```bash
sudo systemctl status cloudflared   # Linux
sudo launchctl list | grep cloudflared   # macOS
```

---

## 4. Point the deployed backend at the tunnel

In your hosted backend's environment (Vercel, Fly, whatever):

```
BABEL_LLAMACPP_HOST=tunnel.babeltower.lat
BABEL_LLAMACPP_PORT=443
```

Two small adapter tweaks are needed for HTTPS tunnels — the current adapter
assumes `http://`. If you run into issues, set:

```
BABEL_LLAMACPP_HOST=tunnel.babeltower.lat
BABEL_LLAMACPP_PORT=443
BABEL_LLAMACPP_SCHEME=https   # TODO: wire this into adapters/llamacpp.py
```

(Track this as an issue — the adapter currently hardcodes `http://`.)

---

## 5. Protect the tunnel

A raw public URL to your `llama-server` means **anyone** who discovers it can
burn your GPU. Cloudflare has two builtin defenses:

### Zero-trust access (free tier up to 50 users)

1. Cloudflare dashboard → Zero Trust → Access → Applications → Add
2. Pick `tunnel.babeltower.lat`
3. Policy: require a specific email domain (e.g. your backend's service
   account) or a shared auth token

### IP allow-list via firewall rule

Cloudflare dashboard → Security → WAF → create a rule that blocks every
request except those from your hosted backend's egress IPs (Vercel publishes
these: https://vercel.com/docs/security/vercel-ip-ranges).

Either path keeps casual scrapers and botnets off the tunnel.

---

## 6. Verify end to end

From the deployed backend's perspective:

```bash
# on the hosted box (Vercel/Fly shell)
curl -H "Authorization: Bearer $YOUR_ACCESS_TOKEN" \
     https://tunnel.babeltower.lat/health
```

Then in the babel UI: upload → analyze → translate. Watch
`cloudflared` logs on your GPU box — you'll see requests flowing through.

If translations fail with `ConnectError: name or service not known`:
- The tunnel process died — restart `cloudflared tunnel run babel-llama`.
- DNS hasn't propagated yet — wait 5 min, then retry.

If translations fail with `httpx.ReadTimeout`:
- `llama-server` is swamped; check queue depth in the admin panel and
  reduce concurrency or scale to a bigger model host.
