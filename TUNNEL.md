# Tunnel guide — expose your local machine to the public backend

When babel is deployed publicly (Vercel frontend), the hosted frontend still
needs a way to reach the babel backend running on your home/office machine.
The machine is behind NAT and won't accept inbound connections directly, so
we use an outbound-initiated tunnel.

Two paths, pick one:

- **Option A — Tailscale Funnel** (free, 1 account, no DNS transfer required).
  Use if you don't want to move DNS to Cloudflare, or if you already use
  Tailscale. See `scripts/tunnel-tailscale.sh` and the [Tailscale Funnel](#tailscale-funnel) section below.

- **Option B — Cloudflare tunnel** (free, 1 account, requires your domain's
  DNS to be on Cloudflare). Use if you want a custom subdomain like
  `api.babeltower.lat`. See `scripts/tunnel-setup.sh` and the [Cloudflare named tunnel](#cloudflare-named-tunnel) section below.

Both work identically well on macOS and Linux.

## Tailscale Funnel

One-time setup: **5 minutes, one free Tailscale account**. Gives you a stable
public HTTPS URL like `https://your-box.tailXYZ.ts.net`. DNS stays on Vercel.

```bash
./scripts/tunnel-tailscale.sh
```

That script installs Tailscale, authenticates (browser), and exposes
`localhost:8765` publicly with a Tailscale-issued cert. At the end it prints
the URL and the Vercel env command to wire it up:

```bash
vercel env rm NEXT_PUBLIC_BABEL_BACKEND production
echo "https://your-box.tailXYZ.ts.net" | vercel env add NEXT_PUBLIC_BABEL_BACKEND production
vercel --prod
```

**If Funnel refuses to enable** with "not authorized" / "attr:funnel": open
the [Tailscale admin ACL editor](https://login.tailscale.com/admin/acls) and
add Funnel to your policy:

```json
"nodeAttrs": [
  { "target": ["autogroup:admin"], "attr": ["funnel"] }
]
```

Save, re-run the script. One-time per tailnet.

**Limits on the free tier:**
- 1 TB/month of Funnel bandwidth (plenty for a beta).
- URL is `*.ts.net` — no custom domain. If you want `api.babeltower.lat`
  specifically, you'd need to put a reverse proxy with its own cert in
  front, which negates most of the simplicity. For a beta, the `.ts.net`
  URL as the API endpoint is fine — users never see it (the UI at
  `babeltower.lat` just proxies through it server-side).

**Stop exposing the port later:**

```bash
sudo tailscale funnel --bg 8765 off
```

---

## Cloudflare named tunnel

Recommended when you want `api.babeltower.lat` (a subdomain of your own
domain) as the API endpoint. Requires:

- A free Cloudflare account (for the tunnel credentials).
- Your domain's DNS moved to Cloudflare nameservers — Vercel stays as the
  registrar, but Cloudflare becomes the DNS host. See the [DNS-move section](#moving-dns-from-vercel-to-cloudflare) below.

Most of the setup is automated by `scripts/tunnel-setup.sh`; the raw steps
below are for reference or debugging.

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

---

## Moving DNS from Vercel to Cloudflare

If `babeltower.lat` is registered at Vercel but you want Cloudflare-tunnel
automation, move only the **nameservers** (Vercel stays as registrar, you
keep billing there):

1. Sign up free at https://dash.cloudflare.com/sign-up.
2. Dashboard → **Add Site** → `babeltower.lat` → pick Free plan.
3. Cloudflare scans your existing DNS records and imports them (your Vercel
   A/CNAME records stay, pointing at Vercel's edge).
4. Cloudflare shows 2 nameservers, e.g. `ava.ns.cloudflare.com` and
   `rick.ns.cloudflare.com`.
5. Vercel dashboard → Domains → `babeltower.lat` → **Nameservers** → paste
   Cloudflare's two.
6. Wait 5–60 min. `babeltower.lat` keeps serving from Vercel the whole time
   because the A record didn't change, only who publishes it.

Once Cloudflare is authoritative, `scripts/tunnel-setup.sh` can auto-create
`api.babeltower.lat` via `cloudflared tunnel route dns`.

If you can't move the nameservers for some reason, there's a fallback: run
the tunnel setup anyway, ignore the `route dns` error, and manually add a
CNAME in Vercel's DNS pointing `api.babeltower.lat` → `<tunnel-uuid>.cfargotunnel.com`.

---

## Which one should I pick?

| | Tailscale Funnel | Cloudflare tunnel |
|---|---|---|
| New account | Tailscale (free) | Cloudflare (free) |
| DNS move required | No | Yes (to Cloudflare) |
| URL | `*.ts.net` | Your own subdomain |
| Cert | Tailscale | Let's Encrypt via Cloudflare |
| Setup time | 5 min | 10 min (including DNS) |
| Bandwidth cap (free) | 1 TB/mo | None advertised |
| Best for | Fast starts, private infra, don't want to touch DNS | Production-looking setup with custom subdomain |

For a babel beta where you want the fastest path to "my friend can hit the
URL": **Tailscale Funnel**. Revisit Cloudflare later when you want the
`api.babeltower.lat` polish.
