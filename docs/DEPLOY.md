# Hosting the demo

The hosted demo is the same code and the same committed Relate store as a local run, in one container
(`Dockerfile`). Every surface works there: the landing page (`/`), the checker (`/app`), the HTTP API
(`/api/...`) and MCP over HTTP (`/mcp/`), so an agent anywhere can use Redline by URL.

Test it locally first:

```bash
docker build -t redline .
docker run --rm -p 7860:7860 redline        # http://localhost:7860
```

## Hugging Face Spaces (free, recommended)

1. Create a Space at <https://huggingface.co/new-space>: SDK **Docker**, template **Blank**, hardware
   **CPU basic** (free). Name it `redline`.
2. A Space reads its settings from the front matter of its own `README.md`, so upload the repository
   with a Space-only README in place of ours:

```bash
pip install -U huggingface_hub && huggingface-cli login
SPACE=<your-hf-user>/redline
tmp=$(mktemp -d) && git archive HEAD | tar -x -C "$tmp"
cat > "$tmp/README.md" <<'EOF'
---
title: Redline
emoji: ⚖️
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: true
short_description: Catch fabricated and overruled case citations before you file.
---
Redline checks every case citation in a brief against a Relate graph of 170,651 US cases.
Code and documentation: https://github.com/PrinceJha-Qua/Redline
EOF
huggingface-cli upload "$SPACE" "$tmp" . --repo-type space
```

3. In the Space's **Settings → Variables**, add
   `REDLINE_ALLOWED_HOSTS` = `<your-hf-user>-redline.hf.space,<your-hf-user>-redline.hf.space:*`
   so that MCP over HTTP answers on the public host name (it refuses unknown hosts, against DNS
   rebinding).

The Space builds in a few minutes. Then:

- Demo: `https://<your-hf-user>-redline.hf.space`
- MCP: `claude mcp add --transport http redline https://<your-hf-user>-redline.hf.space/mcp/`

## Render (alternative)

New → Web Service → connect the GitHub repository → Runtime **Docker**, instance **Free**. Add the
environment variables `PORT=7860` and `REDLINE_ALLOWED_HOSTS=<service>.onrender.com,<service>.onrender.com:*`.
A free Render service sleeps when idle, so the first request after a pause takes about a minute.

## What a public deployment exposes

The store is opened read-only, and `what_if_overruled` runs in a transaction that Relate refuses to
commit, so no request can change the graph. Briefs sent to a hosted copy do leave the user's machine:
the landing page says Redline "runs on your machine", which is true of the local install. For real
client documents, run it locally.
