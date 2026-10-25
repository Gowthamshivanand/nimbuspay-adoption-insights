# Deploy the full app to a free Hugging Face Space (Docker, CPU)

> You do this yourself with your own Hugging Face account. Nothing here creates an account or stores a token. The app runs on synthetic data with the **rules brain** (no model, no API key), so the free **CPU basic** hardware is enough.

## What's already in the repo
- **`README.md` front-matter** (the block at the very top): `sdk: docker`, `app_port: 7860`, title, emoji and `license: mit`. Hugging Face reads it; GitHub just shows it as a small table.
- **`Dockerfile`**: `python:3.12-slim`. It runs as a non-root user (uid 1000, as Spaces expects) and listens on **0.0.0.0:7860**. The environment is `NP_BRAIN=rules`, and the audit log lives in `/tmp` (writable; it resets when the Space restarts). It copies `requirements.txt`, `app/` (including the committed v2 UI build in `app/web/`, so no Node is needed) and the three files the app reads outside `app/`: `src/data.json` (metric dictionary for "Explain this number"), `tools/` and `tests/data/probes.json` (the rules eval on the Models tab). Fixed in v2: earlier images copied only `app/`, so those two features failed in the Space. **No secrets, keys or tokens are baked in.**
- **`.dockerignore`**: keeps tests, docs, videos, zips, any `.env` and any `*.gguf` model file out of the image.
- **`tools/make_space.py`**: builds the small text-only folder you upload to the Space (see below).

## Important: don't push this whole repo to the Space
Hugging Face **rejects git pushes that contain binary files** (PNG, MP4, ZIP, PDF) anywhere in the history unless they're stored with Git LFS/Xet. This repo's history has screenshots and `docs/demo.mp4`, so `git push space main` would be refused. Fixing that means rewriting history and force-pushing, which we don't do. The Space only needs the app, so ship a small text-only folder instead:

```bash
python tools/make_space.py
```
This writes `dist/hf-space/` with `README.md` (front-matter + a short Space description), `Dockerfile`, `.dockerignore`, `requirements.txt`, `LICENSE`, `app/`, `src/data.json`, `tools/` and `tests/data/probes.json`. It then checks that the folder has no binary files, nothing over 10 MB, nothing that looks like a token or key, no `.env` or `.gguf`, port 7860 and the rules brain. `dist/` is git-ignored.

## Step 1: create the Space (2 minutes, in the browser)
1. Sign in at https://huggingface.co and click **New** > **Space**.
2. Fill in **Owner**: your username. **Space name**: `nimbuspay-adoption-insights`. **License**: MIT. **SDK**: **Docker**, **Blank** template. **Hardware**: **CPU basic (free)**. **Visibility**: Public (for a live link) or Private.
3. Create a token at https://huggingface.co/settings/tokens. Choose **Fine-grained** with write access to this one Space, or **Write**. Never paste it into a file in the repo.

## Step 2, option A: upload with the `hf` command (simplest)
On your laptop, from the repo folder:
```bash
pip install -U huggingface_hub
hf auth login                                   # paste the token when asked; it's stored in your own HF cache, not the repo
python tools/make_space.py
hf upload <your-hf-username>/nimbuspay-adoption-insights dist/hf-space . --repo-type space --commit-message "Deploy app"
```
The upload replaces the Space's starter README with ours. Run the same last two lines again to redeploy after a change.

## Step 2, option B: plain git
```bash
git clone https://huggingface.co/spaces/<your-hf-username>/nimbuspay-adoption-insights ../np-space
python tools/make_space.py
cp -r dist/hf-space/. ../np-space/
cd ../np-space && git add -A && git commit -m "Deploy app" && git push
```
When git asks, the username is your HF username and the password is the token. It's a normal push onto the Space's own history, so there's no force-push.

## Step 2, option C: redeploy automatically from GitHub
Hugging Face doesn't build from a GitHub repo by itself, so you add a sync job:
1. In GitHub, go to **Settings > Secrets and variables > Actions** and add the secret `HF_TOKEN` (the token from step 1.3) and the secret `HF_SPACE`, set to `<your-hf-username>/nimbuspay-adoption-insights`.
2. Add `.github/workflows/hf-space.yml`:
   ```yaml
   name: Deploy to Hugging Face Space
   on: { workflow_dispatch: {}, workflow_run: { workflows: [Tests], types: [completed], branches: [main] } }
   jobs:
     deploy:
       if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: { python-version: "3.12" }
         - run: pip install -U huggingface_hub && python tools/make_space.py
         - run: hf upload "$HF_SPACE" dist/hf-space . --repo-type space --commit-message "Deploy ${GITHUB_SHA::7}"
           env: { HF_TOKEN: "${{ secrets.HF_TOKEN }}", HF_SPACE: "${{ secrets.HF_SPACE }}" }
   ```
   It deploys only after the Tests workflow passes on `main`, and the token stays in GitHub's encrypted secrets. It isn't committed, so CI can't fail before the secrets exist. Add it once the Space is created.

## Step 3: check it's live
The Space shows **Building**, then **Running** (the first build takes a few minutes). Then:
- Health: `https://<your-hf-username>-nimbuspay-adoption-insights.hf.space/api/health` should return `{"ok":true, ... "brain":{"kind":"rules", ...}, "label":"Synthetic data"}`
- App: `https://huggingface.co/spaces/<your-hf-username>/nimbuspay-adoption-insights`
- Adversarial set over HTTP: `python tools/break_it.py --url https://<your-hf-username>-nimbuspay-adoption-insights.hf.space` should pass 22/22 (only if the Space is public)

## Settings to leave alone (and optional ones)
- Leave `NP_BRAIN` as `rules` on the free CPU Space. There's no Ollama in the image, and the agent would fall back to rules anyway.
- To try a hosted model later, add **Space secrets** (Settings > Variables and secrets): `NP_BRAIN=openai`, `LLM_API_KEY=...` (and optionally `LLM_MODEL`). Secrets stay out of the image and the repo. Re-run `tools/eval_agent.py` first; the guards still run before the model.
- Free CPU Spaces sleep after a period without visitors. Open the link a few minutes before the pitch to wake it up, and keep the laptop copy (`python -m app`) as the primary.

## Check the image locally first (if you have Docker)
```bash
docker build -t nimbuspay-insights .
docker run --rm -p 7860:7860 nimbuspay-insights
curl http://127.0.0.1:7860/api/health
python tools/break_it.py --url http://127.0.0.1:7860     # all 22 adversarial cases over HTTP
```
`make docker` does the first two steps.

### What was verified on 18 Oct 2026 (IST)
Docker isn't available on the build machine, so the image itself wasn't built there. The next-closest check was run instead, with the same inputs as the Dockerfile:
- `python tools/make_space.py` built `dist/hf-space/` (59 files, text only, no secrets). The server was then run from that folder in a fresh virtualenv, installed with `pip install --no-cache-dir -r requirements.txt` (Python 3.13 there; the image uses 3.12).
- `python -m app` with the image's environment (`HOST=0.0.0.0 PORT=7860 NP_BRAIN=rules AUDIT_DB=/tmp/nimbuspay_audit.db`) and nothing else set.
- Results: `GET /api/health` returned **HTTP 200** with `"brain":{"kind":"rules"}`. `GET /` returned **200**. `POST /api/ask` answered with the cited M01 answer. `tools/break_it.py --url http://127.0.0.1:7860` passed **22/22**, and a headless Chrome check of the UI showed the HTML-injection case is rendered as text.

Run the `docker build` once on your laptop or let the Space build it. That's the remaining check.
