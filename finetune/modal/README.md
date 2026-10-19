# Training and serving the router on Modal (1.5B run 3, then 7B)

Hobby case study. The data is synthetic. Everything here runs in **your own** Modal containers, billed per second. Modal's shared / per-token endpoints are **not** used (the $30/month Starter credit doesn't cover those).

| File | What it does |
|---|---|
| `train_modal.py` | Train (GPU), export the GGUF files (CPU), **evaluate every exported GGUF in Ollama** (GPU, in parallel), package the zip. |
| `serve_modal.py` | One GPU container running Ollama behind a bearer-token proxy: Ollama-compatible `/api/chat` and OpenAI-compatible `/v1/chat/completions`. |
| `remote_check.py` | Warms the endpoint up and times it from the laptop. Uses only the standard library. |
| `../ft_train.py` | The shared training, eval, export and parity code. The notebook logic is reused here, so Modal and Colab numbers can be compared. `python finetune/ft_train.py --smoke` is a local CPU dry run. |

## Why "test what you ship"
Run 2 was evaluated in Colab with the Hugging Face model (88.2% held-out tool accuracy, pure gate PASS). The q4_k_m GGUF of the same run then failed the pure gate in Ollama on the laptop. Two things are now checked automatically:

1. **The JSON schema lock changed the model's output.** Ollama re-orders the schema's properties alphabetically, so the constrained decoder forced `{"args": ..., "tool": ...}`. The model was trained to write `"tool"` first. On the exported smoke model, schema mode agreed with the HF model on **0 of 40** routes, and plain `"json"` mode on 9 of 40. **`FT_JSON_SCHEMA` now defaults to `0`** (format `"json"`). The output is still always valid JSON, and `parse_route()` still rejects unknown tools or args, which falls back to rules. Requests also send `repeat_penalty 1.0`, the same plain greedy decoding the HF eval uses.
2. **The release decision uses the GGUF numbers.** `gguf_eval` runs the full `eval_finetuned.py --mode both` against each exported GGUF in Ollama: route test, fresh wording, answers, and the hybrid and pure gates. It also reports how often the GGUF's route matches the HF model's route. The HF numbers are shown alongside for comparison.

The template was checked and is fine. The Modelfile `TEMPLATE` renders exactly what `apply_chat_template` renders. Raw prompts and chat prompts gave identical outputs (20/20) with identical token counts. The GGUF has no BOS and its EOS is `<|im_end|>`. These checks run again on every export (`template_parity.json`, `chat_vs_raw`).

## Cost and time (estimates, not measured; list prices from modal.com/pricing, 19 Oct 2026)
GPU per second: H100 $0.001097, A100-80GB $0.000694, L4 $0.000222. CPU is $0.0000131 per core per second and RAM $0.00000222 per GiB per second, billed on what is requested. `python finetune/modal/train_modal.py --estimate` prints the table below.

| Run | Steps | Estimate | Worst case (all timeouts hit) |
|---|---|---|---|
| Smoke (CPU only) | tiny model, 12 steps, 40-row GGUF eval | 10-20 min, about $0.05-0.20 | $0.30 |
| **Run 3: 1.5B** | A100-80GB train 20-32 min; CPU export 3-6 min; 4 GGUF evals (f16, q8_0, q5_k_m, q4_k_m) on L4 in parallel, 6-12 min each | **$1.46-2.53** | $4.01 |
| 7B | H100 train 35-55 min; CPU export 12-20 min; 3 GGUF evals (q8_0, q5_k_m, q4_k_m) on L4, 15-30 min each | $3.53-5.91 | $7.39 |
| Serve 7B for the pitch | L4 + 2 cores + 12 GiB, per hour awake | $0.99/h (A10 $1.29/h) | |

Approved budget: **$10 total**. Run 3 goes first. The 7B timeouts are set so that run 3 plus the 7B stays near that budget even if every step hits its timeout. Training also stops itself earlier (`budget_min`) and keeps the best checkpoint. **Set a workspace budget in the Modal dashboard** (Settings > Usage / Billing > budget) before the first run.

## Steps for Mohith (Windows PowerShell 5.1, one command per line, no `&&` / `||`)
```powershell
$env:PYTHONUTF8 = "1"
python -m pip install --upgrade modal
modal setup
```
`modal setup` opens the browser and saves your token in `%USERPROFILE%\.modal.toml`. Nothing is written into the repo. Then, from the repo folder:
```powershell
python finetune\modal\train_modal.py --estimate
modal run finetune\modal\train_modal.py --smoke
modal run --detach finetune\modal\train_modal.py --model 1.5B
```
The whole pipeline runs in a small Modal orchestrator container (1 CPU). With `--detach` you can close the window, and the run keeps going: follow it with `modal app logs <app id>`. It writes `runs/<run>/run_summary.json` at the end. To rebuild only the zip and eval_report.json from an existing run, with no training and CPU only: `modal run finetune\modal\train_modal.py --model 1.5B --package-only 1.5b-20261019-131131`. The last command prints the side-by-side table (HF against each GGUF), the shipped quant (q8_0 by default for 1.5B, about 1.6 GB) and the decision. It also prints the estimated cost from container seconds and the download command:
```powershell
modal volume get gowtham-nimbuspay-models runs/1.5b-latest/gowtham-nimbuspay-agent-export.zip .
Expand-Archive -Path ".\gowtham-nimbuspay-agent-export.zip" -DestinationPath ".\run3" -Force
Set-Location ".\run3"
ollama create gowtham-nimbuspay-agent -f Modelfile
Set-Location ".."
```
The zip holds the shipped GGUF, a `Modelfile`, `eval_report.json` (the decision, the side-by-side table and every report), `eval_report_hf.json`, `eval_report_gguf_<quant>.json` and `template_parity.json`. The other quants stay on the Volume (`modal volume ls gowtham-nimbuspay-models runs/<run>/export`).

Laptop check (CPU, slower than the L4 numbers):
```powershell
$env:FT_MODEL = "gowtham-nimbuspay-agent"
$env:FT_TIMEOUT_S = "8"
$env:FT_ANSWER_TIMEOUT_S = "20"
python finetune\eval_finetuned.py --mode both
```

**7B** (only after run 3 is reviewed):
```powershell
modal run finetune\modal\train_modal.py --model 7B
modal volume get gowtham-nimbuspay-models runs/7b-latest/gowtham-nimbuspay-agent-7b-export.zip .
```
On the 16 GB laptop, q8_0 (about 8 GB) or q4_k_m (about 4.7 GB) loads but runs slowly on CPU. Expect several seconds per route call. Use `$env:FT_MODEL = "gowtham-nimbuspay-agent-7b"` and `$env:FT_TIMEOUT_S = "30"` to try it. The pitch should use the Modal endpoint below for the 7B.

Options: `--gpu H100|A100-80GB`, `--eval-gpu L4|A10`, `--quants f16,q8_0,q4_k_m`, `--ship q8_0`, `--qlora`, `--no-use-public`, `--epochs 2`. `--skip-train <run name>` re-runs export and GGUF eval on an existing run. `--push-hf` first needs `modal secret create huggingface HF_TOKEN=<your write token>`; the token is never put in the repo.

## Release rule (decided on the shipped GGUF, not on the HF model)
Use a new model instead of 1.5B run 2 only if **all** of these hold for its GGUF in Ollama:
1. The pure release gate passes (golden, probes, unscripted, break-it >= rules; 0 unsafe answers; 100% number faithfulness).
2. Held-out tool accuracy is above **88.2%**.
3. Fresh-wording tool accuracy is above **83.5%**.
4. There are at most **19** unsafe routes.
These are run 2's Colab numbers, and the decision is printed as `DECISION`. For the 7B, a q5_k_m or q4_k_m file is shipped instead of q8_0 only if it also passes the pure gate, is within 1 point of q8_0 and has no more unsafe routes.

## Pitch day: serve the 7B from Gowtham's Modal account
One-time setup, run on Gowtham's machine after `modal setup` with his account. `remote_check.py` and the app read the key from the environment.
```powershell
$key = -join ((48..57) + (97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
modal secret create nimbuspay-serve-key NP_SERVE_KEY=$key
modal volume create gowtham-nimbuspay-models
modal volume put gowtham-nimbuspay-models gowtham-nimbuspay-agent-7b-export.zip runs/7b-latest/gowtham-nimbuspay-agent-7b-export.zip
modal deploy finetune\modal\serve_modal.py
```
`modal deploy` prints the URL, which looks like `https://<workspace>--gowtham-nimbuspay-serve-serve-web.modal.run`. The default is an L4 that scales to zero after 5 idle minutes. For an A10, deploy with `$env:NP_SERVE_GPU = "A10"` set first.

About 10 minutes before the slot:
```powershell
modal run finetune\modal\serve_modal.py::keep_warm --n 1
$env:FT_REMOTE_URL = "https://<workspace>--gowtham-nimbuspay-serve-serve-web.modal.run"
$env:FT_REMOTE_KEY = $key
python finetune\modal\remote_check.py --wait 600
$env:NP_BRAIN = "finetuned"
$env:FT_MODEL = "gowtham-nimbuspay-agent"
python -m app
```
The app tries the Modal 7B first. If that times out (`FT_REMOTE_TIMEOUT_S`, default 6 s) or errors, it falls back to the laptop 1.5B (`FT_MODEL`), and then to the rules engine. After a failure the remote is skipped for 30 s. Each chat answer shows **answered by Modal 7B / laptop 1.5B / rules**. The Models tab shows the chain and per-source counts. The safety guards always run first, in code.

Right after the slot:
```powershell
modal run finetune\modal\serve_modal.py::keep_warm --n 0
modal app stop gowtham-nimbuspay-serve
```
Check the dashboard shows no running containers. An awake L4 costs about $0.99 per hour (estimate).

To evaluate the remote 7B alone: `$env:FT_FALLBACK_LOCAL = "0"`, then `python finetune\eval_finetuned.py --mode both`. The report counts who answered each call.

## App settings added
| Variable | Default | What |
|---|---|---|
| `FT_REMOTE_URL` | unset | Ollama-compatible endpoint tried first (e.g. the Modal 7B). Unset means nothing changes. |
| `FT_REMOTE_KEY` | unset | Bearer token for it. It is never logged or shown. |
| `FT_REMOTE_MODEL` / `FT_REMOTE_LABEL` | `gowtham-nimbuspay-agent-7b` / `Modal 7B` | Model name sent, and the label shown in the UI. |
| `FT_REMOTE_TIMEOUT_S` | `6` | Timeout per remote route call. It includes the internet round trip. |
| `FT_REMOTE_COOLDOWN_S` | `30` | How long to skip the remote after a failure. |
| `FT_FALLBACK_LOCAL` | `1` | `0` turns off the laptop step. |
| `FT_ANSWER_TIMEOUT_S` | `10` | Timeout per answer call. The route call keeps `FT_TIMEOUT_S` (4). |
| `FT_JSON_SCHEMA` | **`0`** (was 1) | `1` passes the JSON schema as `format`. See above for why that is off. |
