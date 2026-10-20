---
title: NimbusPay Adoption Insights
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Hobby demo on synthetic data, governed AI agent
---
# NimbusPay AI adoption insights: live product + interactive prototype

> **Hobby case study, synthetic data only.** This is a personal hobby project built for a campus case-study competition (HashedIn by Deloitte Campus PM Hiring 2026, "The Adoption Mirage"). "NimbusPay" is the fictional company from that case brief. Every number, team, user and event here is synthetic and labelled. It is **not affiliated with, endorsed by, or about any real company**, including nimbuspay.io, HashedIn or Deloitte, and contains no real company or personal data.

**Author:** Gowtham S · **Licence:** MIT · **Live demo:** https://Gowthamshivanand.github.io/nimbuspay-adoption-insights/

A self-contained, offline, single-file prototype for the NimbusPay "Adoption Mirage" case (HashedIn by Deloitte DPM case, deliverable 7: a prototype of the agent interface and workflow). Its idea: **measure the work, not the clicks.**

> Every number is **illustrative synthetic data** that follows the rules in the supporting workbook (metrics M01 to M21, licence funnel LF1 to LF6, interaction rules IR1 to IR8). No real NimbusPay data is used.

## Before the pitch
Run these on the laptop you will present from, the night before. The full list is in `prep/PITCH_DAY_CHECKLIST.md` in the pitch pack.

1. **Put the real link and QR code into the pitch files (one command).** Once your site or repo is public:
   ```bash
   pip install segno python-pptx
   python tools/set_domain.py https://YOUR-REAL-DOMAIN --repo https://github.com/<you>/nimbuspay-adoption-insights
   ```
   It finds the pack folder (the one with `deck/` and `extras/`; pass `--pack PATH` if it can't), makes `extras/qr_final.png` and `.svg` (plus `qr_repo_final.*` with `--repo`), and writes new files ending in `_final`: the TPM deck with slide 10's QR, label and links filled in (`deck/..._final.pptx`, plus a PDF if LibreOffice is installed), `extras/LEAVE_BEHIND_TPM_final.pdf` and `extras/CHEAT_SHEET_TPM_final.pdf` (needs Chrome, Edge or Chromium; otherwise it leaves an `_final.html` to print). Originals are never touched. It refuses placeholder links. Scan the new QR with your phone before you print. For the repo's own `assets/qr.png`, use `python tools/make_qr.py URL --out assets`.
2. **Test the small open model:** `ollama pull qwen2.5:3b-instruct`, then `python tools/eval_agent.py --brain ollama`. If it scores below the rules brain, present with `NP_BRAIN=rules python -m app` (the rules fallback, same numbers).
3. **Run the tests:** `make test` (313 tests in CI plus 2 browser walkthroughs via `make test-ui`, then the agent test gate).
4. **Rehearse the demo:** `docs/DEMO_SCRIPT.md` (TPM-led, 4 minutes); backup video `docs/demo.mp4`.

## Live product (`app/`): a real, runnable Adoption Insights product

**Model licence:** the demo default `qwen2.5:3b-instruct` is research-licence only (no commercial use). Production uses an Apache 2.0 Qwen 2.5 size (1.5B or 7B), chosen by re-running the agent test:

```bash
ollama pull qwen2.5:7b-instruct
OLLAMA_MODEL=qwen2.5:7b-instruct NP_BRAIN=ollama python tools/eval_agent.py --brain ollama   # must pass before switching
OLLAMA_MODEL=qwen2.5:7b-instruct python -m app
```

**Safety, model and deploy docs:** [docs/BREAK_IT.md](docs/BREAK_IT.md) (22 adversarial questions, real responses, `python tools/break_it.py`), [docs/MODEL_CARD.md](docs/MODEL_CARD.md) (fine-tuned router: intended use, data, release gate, measured 3B baseline) and [docs/DEPLOY_HF_SPACES.md](docs/DEPLOY_HF_SPACES.md) (free Hugging Face Docker Space on port 7860, rules brain, no secrets).

**Operations:** see [docs/RUNBOOK.md](docs/RUNBOOK.md) for SLOs, alerts, on-call playbooks, rollback and the DEV -> staging -> prod release flow. The live app has a **Cost and scale** tab (`/api/cost`, `app/costcalc.py`): every default is a labelled assumption and every price is a cited public list price.

The repo now holds two things:
1. **The live product** (`app/`): a Python backend with a real data pipeline, a local SQL warehouse, a working read-only **Adoption Insights Agent**, dashboards, alerts, scenario compare, a one-click board pack and an audit log. Runs on a laptop with no internet, no API key and no paid service.
2. **The static prototype** (`index.html`): the single-file demo for GitHub Pages and offline use (unchanged, see below).

### Run it (one command)
```bash
pip install -r requirements.txt && python -m app      # then open http://127.0.0.1:8000
# or: make install run      # or: docker build -t nimbuspay-insights . && docker run -p 7860:7860 nimbuspay-insights  (then open http://127.0.0.1:7860)
```
Python 3.10+. Dependencies: FastAPI, Uvicorn, python-multipart. The warehouse is SQLite from the standard library.

**Web UI (v2).** The UI is a React + Vite + TypeScript + Tailwind app in `web/`. Its build is **committed** in `app/web/` (text-only JS/CSS), so `python -m app`, Docker and the Hugging Face Space need **no Node**. Only after changing `web/src` do you rebuild: `cd web && npm ci && npm run build` (Node 20+), or `make web`. For live front-end work run `python -m app` (port 8000) and, in a second window, `cd web && npm run dev` (http://127.0.0.1:5173, proxies `/api` to 8000). Same screens, numbers, agent answers and API as v1: only the look and the front-end code changed.
**Fallback to the v1 UI:** it is kept byte-identical in `app/static/` and always served at `/legacy`; `NP_UI=legacy python -m app` also serves it at `/`. If `app/web/` is missing, `/` falls back to it automatically.

**Fixed (v2): the Docker image was missing `src/data.json`, `tools/` and `tests/data/probes.json`.** The image copied only `app/`, so in Docker (and the Hugging Face Space) "Explain this number" did nothing (`/api/lineage` returned 500) and the Models tab showed the rules engine as "not available". The Dockerfile now copies them (`.dockerignore` and `tools/make_space.py` match), and `tests/test_docker_files.py` fails if any is dropped. This is the only intentional behaviour change in v2. See `CHANGELOG.md`.

### Architecture
```mermaid
flowchart LR
  subgraph Inputs["Inputs (CSV, synthetic)"]
    E[events.csv<br/>raw agent + login events]
    S[seats.csv<br/>purchased / assigned / provisioned]
    G[registry.csv<br/>agent registry + build type]
    O[outcomes<br/>verified hours, cost index, critical risk]
  end
  E & S & G & O --> V[Validate<br/>schema, types, unknown agents]
  V --> C[Clean<br/>dedupe event_id, late flag,<br/>period close + restatement]
  C --> I[Group into logical interactions<br/>IR5 interaction ID = exact<br/>IR6 sessionisation 120 s = approximate]
  I --> F[Licence funnel LF1-LF6]
  I --> M[Governed metrics M01-M21<br/>headline: M01 M02 M04 M07 M10 M17 M18 M19]
  F --> M
  M --> SC[M19 value score<br/>Reach 20 / Depth 15 / Outcome 40 / Reliability 15 / Trust 10<br/>no silent imputation, critical-risk override, interim 33/25/25/17]
  SC --> RN[Renewal engine<br/>4 evidence areas to 5 outcomes]
  M --> WH[(SQLite warehouse<br/>events_clean, interactions,<br/>user_funnel, seats, agent_registry)]
  WH --> AG[Adoption Insights Agent<br/>guards then intent router then SQL<br/>cites metric ID + version + data-as-of]
  LLM[Brain: local open model via Ollama<br/>fallback: rules router<br/>optional: OpenAI-compatible] -.picks a governed tool only.-> AG
  WH --> FT[Features: lineage, what-if,<br/>seat reclaim, bill reconciler]
  FT --> UI
  RN & SC & M & AG --> UI[Web UI: Executive, Regional, Engineering,<br/>What-if, Seats and bill, Agent, Alerts, Compare, Board pack, Audit log]
  AG --> AU[(Audit log)]
```

| Folder / file | What it does |
|---|---|
| `app/pipeline.py` | Ingest, validate, clean, group, funnel, metrics, M19, renewal engine, alerts; loads the SQLite warehouse |
| `app/agent.py` | The agent: safety guards, intent router, SQL-backed answers with citations, optional LLM router |
| `app/server.py` | FastAPI REST API + serves the web UI |
| `app/features.py` | Seat reclaim finder, what-if simulator, metric lineage, vendor bill reconciler |
| `app/config.py` | Every threshold and weight in one place (placeholders, to agree) |
| `web/` | The v2 web UI source: React + Vite + TypeScript + Tailwind. Design tokens in `web/tokens.cjs` (one file) |
| `app/web/` | The v2 UI build, committed, served at `/` and `/assets/*` |
| `app/static/` | The v1 web UI (vanilla JS), kept unchanged as the fallback at `/legacy` (and read by some tests) |
| `app/data/base/` | The v10 workbook's synthetic data as CSVs + the workbook's expected results |
| `app/data/scenarios/` | 8 synthetic scenarios, each a real CSV data set |
| `tools/export_workbook.py`, `tools/make_scenarios.py` | Rebuild the CSVs from the workbook (`make data`) |
| `tests/` | pytest: pipeline, agent, brain, features, API, Playwright UI smoke test |

### What the pipeline proves (asserted in `tests/test_pipeline.py`)
On the workbook's extended synthetic set it reproduces **all 35 Expected_Results_Extended values exactly**: 210 raw rows, 6 duplicates, 4 after close, 200 clean events, 44 interactions (22 exact, 22 approximate), 43 qualifying, vendor-style MAU 21 vs 16 active (31.2% overstatement), funnel 31 / 23 / 22 / 16 / 11 / 6, M01 69.6%, M02 26.1%, M10 4.3%, M11 17.5%, M20 0% vs 100% by build type, 1 unregistered agent, regional funnels and the restatement. On the 9-event golden set: 9 events = 2 interactions (4.5x). All synthetic.

### Features
| Tab | What it does |
|---|---|
| Data | Load any of the 8 synthetic scenarios, or upload your own events, seats and registry CSVs (validated; bad files are rejected with the reason) |
| Executive | Renewal recommendation with its 4 evidence areas, M19 beside its 5 pillars, 7 more headline metrics, the LF1-LF6 funnel. **Click any metric card to explain the number.** |
| **Explain this number (lineage)** | For any metric: formula, version, owner (proposed role), freshness (data-as-of, late rows, restatement), source tables, pipeline steps, missing-data rule, tests, and the SQL, re-run live on the warehouse |
| **What-if** | Renewal simulator: change the seat count at renewal, fix connector failures, or raise interaction-ID coverage. It re-runs the full pipeline and shows today vs what-if for the funnel, M19 pillars and renewal outcome. It is not a forecast. |
| **Seats and bill** | **Seat reclaim finder**: never-assigned and idle seats by team, with 10% headroom kept, and a reclaim figure at a placeholder price (100 price units a seat, labelled synthetic). Team-level only. **Vendor bill reconciler**: upload the vendor invoice CSV (sample in `app/data/samples/vendor_invoice_sample.csv`) to compare billed vs purchased vs assigned vs active seats per team. Overbilling, unknown teams, unassigned billed seats and missing teams are flagged. |
| Regional | Funnel and M01, M02, M11 by region; teams under 5 assigned seats are suppressed |
| Engineering | M10, M11, M12, M16, M20; agent registry with build type and its source (registry or backfill) |
| Agent | Read-only chat with the 21 golden questions as chips; the brain shown in the header; citations, SQL, refusals with safe alternatives. Answers **stream in** (typing effect) and each one shows **which brain answered** (rules, Ollama, fine-tuned, hosted LLM), its **latency in ms** and a **confidence**. **Follow-ups** work ("and Region B?", "what about the fraud one?", "what about last month?"). Vague asks get a **clarifying question** with 2-3 clickable options. **Why this number?** opens one panel with the SQL run, the metric definition, ID and version, data-as-of and rows returned. **Thumbs up/down** on every answer. **Ask as Manager / Analyst / Guest** re-asks the same question under another role |
| **Role switch** (header) | Manager, Analyst (Region A) and Guest buttons plus every persona in the dropdown. The UI only sends a role name; scope and deny-by-default are enforced on the server (an unknown or mistyped role is Guest) |
| **Models** | Model comparison: the same agent test per brain (rules always; the stock Ollama model and the fine-tuned model only if reachable, otherwise **not available**, never estimated). Golden, panel and extra scores, unsafe answers, number faithfulness, p50/p95 latency, release gate. Load a saved `tools/eval_agent.py --save` JSON from another machine |
| Alerts | Rule-based alerts from the governed metrics |
| Compare | All 8 scenarios side by side |
| Board pack | One click: printable HTML (save as PDF) or Markdown |
| Audit log | Every agent question with persona, result, metrics cited and brain |

The v2 UI follows the Figma hi-fi tokens (light consulting, Apple-clean): white and neutral greys (`#4B5563` secondary text), navy `#0B2E59` for primary actions and selected states, orange `#E8751A` only as a fill (bars, markers) and `#C2410C` for orange text, teal `#0F5E63` only for verified items, Inter (system font fallback, no font files shipped), 150-180 ms transitions, WCAG AA contrast. Red is used only for critical risk. Every value lives in `web/tokens.cjs`. (The v1 UI at `/legacy` keeps the deck brand: charcoal, orange `#F28C28`, Arial.)

### The agent and its "brain"
- **Safety guards are always deterministic** and run first. There are 9: prompt injection, individual surveillance, raw events or PII, small groups (< 5), out-of-scope regions (row-level security by persona), forecasts, causal claims, writes or actions, and ungoverned metrics are refused with a safe alternative. After the answer, a **claim check** means the agent never confirms a number the user typed unless its own SQL computed the same figure. Anything it can't match is never guessed: it says so and offers the 3 closest governed questions it can answer.
- **Deny by default on role.** A missing or unrecognised persona resolves to the least-privileged `guest` role (no data scope; definitions only), in the API, the agent and the static prototype. It never falls back to Executive. In production the role is an SSO token claim, not a request field.
- **Broad but governed coverage.** Beyond the 21 golden questions it answers panel-style paraphrases: a named agent's health or time saved (M17 study status plus its governed usage), reliability by agent, which agents are used most, engineer-built vs drag-and-drop, team usage (teams under 5 seats suppressed), region comparison, weekly trend inside the closed period, data freshness, alerts, seat reclaim, and outcome metrics that need study data (M06 to M09, refused with the reason).
- **The brain only routes.** It picks one governed tool (for example `m01`, `m19`, `renewal`). The tool then runs real SQL on the warehouse and returns the answer with metric ID + version + data-as-of and the SQL. The model never states a number.
- **Default brain: a small open model running locally at zero cost through [Ollama](https://ollama.com).** If Ollama isn't reachable, or the model returns anything outside the tool list, the agent falls back automatically to the **deterministic rules router**, which covers everything on its own. The chat header shows which brain is active.

| Brain | When it is used | Setup |
|---|---|---|
| Open model (default when available) | Ollama answers at `OLLAMA_HOST` and `OLLAMA_MODEL` is pulled | Install Ollama, then `ollama pull qwen2.5:3b-instruct` (about 2 GB) or `ollama pull llama3.2:3b`. On a low-memory laptop use `qwen2.5:1.5b-instruct` or `qwen2.5:0.5b-instruct` and set `OLLAMA_MODEL` to match. |
| OpenAI-compatible API (optional) | No Ollama, and `LLM_API_KEY` or `OPENAI_API_KEY` is set | Optional `LLM_BASE_URL`, `LLM_MODEL` |
| Fine-tuned router (opt-in) | `NP_BRAIN=finetuned` and `FT_MODEL` (default `gowtham-nimbuspay-agent`) is in Ollama | Train it on a free Colab T4 with [`finetune/`](finetune/README.md), then `ollama create gowtham-nimbuspay-agent -f Modelfile`. It ships only if it passes the release gate. Hybrid by default: guards and confident rules matches stay on rules, the model only routes the questions rules can't place (`FT_MODE=pure` to compare; settings in the finetune README). |
| Rules engine (always available) | Otherwise, or `NP_BRAIN=rules` | Nothing |

```bash
ollama pull qwen2.5:3b-instruct          # one time
ollama serve                             # if it isn't already running as a service
OLLAMA_MODEL=qwen2.5:3b-instruct python -m app
# env: NP_BRAIN=auto|ollama|openai|finetuned|rules (default auto), OLLAMA_HOST (default http://127.0.0.1:11434), OLLAMA_TIMEOUT (s)
```
The model gets the question plus the list of governed tools, and Ollama's structured output (a JSON schema with an enum of tool names) forces its reply to be one tool name or `none`.

**Evaluate whichever brain is active:** `python tools/eval_agent.py` (or `--brain rules|ollama|openai`) runs the 21 golden questions, 8 guard and paraphrase probes, and the 64-question unscripted probe set in `tests/data/probes.json` (a 24-question panel set with 17 should-answer and 7 should-refuse, plus 40 extra paraphrases, adversarial asks and role checks), and prints the pass rates. The rules brain scores 21/21 on the golden questions, 29/29 on the guard probes, 24/24 on the panel set and 40/40 on the extras. Run it with your model before the interview; if the model scores lower, start the app with `NP_BRAIN=rules`.

**Conversation, confidence and feedback** (`app/conversation.py`, `app/feedback.py`, `app/modelcompare.py`):
- **Follow-ups.** Send a `session_id` to `/api/ask` (the UI does) and a short follow-up reuses the previous governed tool with the new slot: a region (`and Region B?` rewrites the utilisation question for Region B), an agent (`what about the KYC one?`) or a time (`what about last month?` says the data set holds one closed period and never invents a prior one). The session is in memory, 15 min TTL (`NP_SESSION_TTL`), capped at 500 sessions, and stores only the previous question and tool: **never a role**. Every turn goes through the guards and the role check again. Without a `session_id`, `/api/ask` behaves exactly as before (it only gains extra fields).
- **Streaming.** `POST /api/ask/stream` (same body) returns server-sent events: `meta` (brain, mode, confidence, latency), `token` chunks, then `done` with the full response. The answer is computed in full first, so numbers still come only from governed SQL; streaming is presentation. The UI falls back to `/api/ask` if streaming fails.
- **Confidence and clarifying questions.** The rules engine scores its own match (specific pattern 0.95, named agent 0.9, general pattern 0.85 minus 0.1 for each other tool that also matched, floor 0.6, no match 0). A model brain's confidence is the model's own if it reports one, else agreement with the rules router (agree 0.95, rules no match 0.6, disagree 0.45). Below `NP_CONFIDENCE_MIN` (0.5), or when a required slot is missing ("is the agent saving time?" with no agent named), it returns `type: clarify` with 2-3 options instead of guessing.
- **Why this number?** Every response carries `sql_executed`, `row_count`, `latency_ms`, `brain` and `confidence`. Figures that come from the pipeline (for example the funnel) say so instead of claiming a SQL re-run.
- **Feedback.** `POST /api/feedback` appends to `data/feedback/feedback.jsonl` (gitignored; `NP_FEEDBACK` to move it): question, answer, rating, brain, mode, role label, dataset, timestamp, no user identity. `python tools/export_feedback.py list | review <id> --tool m01 | review <id> --refuse pii | review <id> --reject | export` turns **human-reviewed** misses into `data/feedback/finetune_candidates.jsonl`. Nothing trains automatically.
- **Model comparison.** `python tools/eval_agent.py --brain <rules|ollama|finetuned> --save eval.json` writes a `nimbuspay-eval/1` file; the **Models** tab runs it per reachable brain (`GET /api/models`, `POST /api/models/run/{brain}`) or loads a saved file (`POST /api/models/upload`). A run whose brain fell back to rules is shown as not available, not as that model's score. Number faithfulness is strict: a number counts as faithful only if it appears in the governed result, its SQL rows (or a share of two row values), the SQL, the question or the fixed answer templates. The rules engine scores 97.8%: one answer (engineer-built vs drag-and-drop) computes an error rate from summed runs, which the strict check can't trace.

**Golden questions:** all 21 Agent_Test_Questions get the expected behaviour (answer, answer with caveat, or refuse) in the workbook's own state, with no verified outcome data yet. pytest always runs against the rules brain, and `tests/test_brain.py` checks Ollama routing, guard order and fallback against a fake Ollama server.

### Scenarios (real CSV data through the same pipeline)
| Scenario | What changes in the data | Renewal outcome |
|---|---|---|
| Baseline | The workbook's 210-row set | Renew and right-size (M01 69.6% < 70%) |
| Healthy adoption | Idle seats activated weekly | Expand |
| Overstated usage | Everyone logs in, few return, high unit cost | Renegotiate |
| Shelfware | 6 users stop, purchased seats grow | Renew and right-size |
| New-country launch | New Region D cohort, no verified study yet | Continue limited pilot |
| Reliability incident | Drag-and-drop connector calls fail | Renew with remediation conditions |
| Missing interaction IDs | SDK drops IDs, all sessionised, impact not attributable | Continue limited pilot |
| Critical-risk breach | Card data outside the masked zone | Renew with remediation conditions (score RED) |

Upload your own `events.csv`, `seats.csv` and `registry.csv` on the **Data** tab (download any scenario's CSVs there as a template).

### Tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # 313 tests in CI plus 2 browser walkthroughs (Playwright), then the agent test gate: tools/eval_agent.py
```
`tests/test_improvements.py` (29 tests) covers follow-ups, streaming, the Models screen, confidence and clarifying questions, the why-panel fields, feedback and its review export, and the role switch. `tests/test_ui_features_playwright.py` walks those features in a browser and saves `docs/screenshots/app-14..20`. The UI tests need a Chrome/Chromium (set `CHROME_PATH` if it isn't at `/usr/bin/google-chrome`) and write `docs/screenshots/app-*.png`; they skip if Playwright is missing.

### Hosting the live product for free (you do this; nothing here deploys anything)
- **Primary for the interview: your laptop.** `python -m app`, present from `http://127.0.0.1:8000`. Works with no internet.
- **Public link: Render free web service.** New Web Service, then connect the repo. Build command `pip install -r requirements.txt`, start command `HOST=0.0.0.0 python -m app` (or choose Docker). Free instances sleep after 15 minutes idle and take about a minute to wake, so open the link 2 minutes before your slot. The filesystem is ephemeral, so the audit log resets on restart. Check Render's current free-tier terms.
- **Any Docker host:** the `Dockerfile` runs anywhere.
- **Offline fallback:** the static `index.html` (GitHub Pages or double-click) and `docs/demo.mp4`.

### How it maps to the case deliverables
| Case ask | Where it lives in the product |
|---|---|
| Define adoption properly (interactions, not events) | `pipeline.compute_core`: IR5 exact + IR6 approximate, qualifying = run + response; Data and Engineering tabs |
| Licence funnel and shelfware | LF1-LF6 on the Executive tab; regional funnels with small-group suppression |
| Governed metric set | M01-M21 dictionary (`src/data.json`), 8 headline metrics computed in `pipeline.run`, each with ID + version |
| AI value score | M19 with 5 pillars, no silent imputation, critical-risk override, interim index |
| Dashboards for each persona | Executive, Regional adoption and intervention, Engineering reliability |
| Adoption Insights Agent | `app/agent.py`: 21 golden questions, refusals, SQL, citations, audit log |
| Renewal decision | Renewal engine (4 evidence areas to 5 outcomes), Compare tab, board pack export |
| Trust and governance | Read-only agent, persona scope, PII guards, audit log, metric versions, data-as-of, restatement |

---

## Static prototype (`index.html`)

### What it shows
| Screen | What it demonstrates |
|---|---|
| 1 Executive view | AI value score (M19) beside its 5 pillars (Reach 20, Depth 15, Outcome 40, Reliability 15, Trust 10); no silent imputation; critical-risk override; habitual users, verified hours, utilisation, cost per verified hour (an index against a placeholder cost); the renewal recommendation |
| 2 Regional adoption | Licence funnel by region and launch cohort, row-level security, small groups hidden, intervention list |
| 3 Engineering reliability | Error rates, connector health, unregistered agents, freshness, events missing an interaction ID |
| 4 How we count | Golden events grouped into interactions live: 9 events = 2 interactions, a 4.5x overstatement; Expected_Results checks |
| 5 Adoption Insights Agent | Role-scoped chat over governed metrics only; citations (metric, version, owner, data-as-of); refusals with safe alternatives; reasoning and SQL; a "why" breakdown (Q07) with a drill-down |
| 6 Governance | Metric catalogue, owners, versions, live tests, audit trail |

**Scenario switcher** (top bar): every preset changes the synthetic data coherently across all screens and personas.

| Scenario | Renewal outcome |
|---|---|
| Baseline demo | Renew and right-size |
| Healthy adoption | Expand |
| Overstated usage (vendor MAU high) | Renegotiate |
| Shelfware (paid seats unused) | Renew and right-size |
| New-country launch cohort | Continue limited pilot |
| Reliability incident (connector outage) | Renew with remediation conditions |
| Missing interaction IDs (drag-and-drop heavy) | Continue limited pilot |
| Critical-risk breach (privacy) | Renew with remediation conditions (score flagged red) |

Personas: Executive sponsor, Regional lead A, Regional lead B, Platform engineer, Fraud operations lead, plus "Unrecognised role (least privilege)" to show deny by default (any unknown role lands there). A **Guided demo** button runs a 6-step story. A walkthrough video is in `docs/demo.mp4`. The live product (`app/`) uses its own role list in `app/agent.py`: Executive, Regional lead (Region A), Platform engineer, Fraud operations lead (Region A), Finance and Procurement, Manager (all regions), Analyst (Region A) and the same least-privilege fallback (definitions only, no data).

### Screenshots
![Live product: executive view](docs/screenshots/app-02-executive.png)
![Live product: agent](docs/screenshots/app-05-agent.png)
![Live product: scenario compare](docs/screenshots/app-07-compare.png)
![Explain this number](docs/screenshots/app-11-lineage.png)
![What-if simulator](docs/screenshots/app-12-whatif.png)
![Seat reclaim and vendor bill](docs/screenshots/app-13-seats-bill.png)
![Streaming answer with brain, latency and confidence](docs/screenshots/app-14-streaming.png)
![Follow-up question](docs/screenshots/app-15-followup.png)
![Why this number?](docs/screenshots/app-16-why-this-number.png)
![Clarifying question](docs/screenshots/app-17-clarify.png)
![Thumbs feedback](docs/screenshots/app-18-feedback.png)
![Role switch: guest denied](docs/screenshots/app-19-role-switch.png)
![Model comparison](docs/screenshots/app-20-models.png)
![Executive view](docs/screenshots/1-exec.png)
![Agent answering a why question](docs/screenshots/5b-agent-q07.png)
![How we count](docs/screenshots/4-count.png)
![Regional adoption, new-country scenario](docs/screenshots/scenario-newcountry-regional.png)
![Engineering, reliability incident](docs/screenshots/scenario-incident-eng.png)
![Governance](docs/screenshots/6-gov.png)

### Run the static prototype locally
Double-click `index.html`. It needs no server, build or internet. Or run `python3 -m http.server 8000` and open http://localhost:8000.

Rebuild after editing `src/`:
```bash
cd src && python3 build.py   # writes ../index.html from shell.html + style.css + data.json + app.js
```
`src/extract.py` regenerates `data.json` from the workbook (edit the workbook path in it first).

Test (optional): `pip install playwright` and use a Chrome or Chromium binary, then run `python tests/qa_final.py file://$PWD/index.html /tmp/`. It clicks through every scenario, persona, screen and golden question, plus the guided demo, and fails on console errors.

## Deploy the static prototype free on GitHub Pages
1. Create a public repository, for example `nimbuspay-adoption-insights`, and push this folder to the `main` branch.
2. Open **Settings → Pages → Build and deployment → Source: GitHub Actions**. The included workflow `.github/workflows/pages.yml` publishes on each push to `main`.
3. The site goes live at `https://<username>.github.io/nimbuspay-adoption-insights/`.

### Custom domain
1. Copy `CNAME.example` to `CNAME` and put your domain in it (one line, for example `adoption.example.com`). The workflow copies it into the site.
2. In **Settings → Pages → Custom domain**, enter the same domain and save. With Actions deployments, this setting is what counts.
3. At your DNS provider:
   - **Subdomain** (for example `adoption.example.com`): add a `CNAME` record from `adoption` to `<username>.github.io`.
   - **Apex** (for example `example.com`): add four `A` records pointing to `185.199.108.153`, `185.199.109.153`, `185.199.110.153` and `185.199.111.153`. Optionally add the AAAA records `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153` and `2606:50c0:8003::153`, plus a `CNAME` from `www` to `<username>.github.io`.
4. Wait for DNS to propagate (minutes to hours), then tick **Enforce HTTPS**.
5. Make the QR code: `pip install segno pillow && python tools/make_qr.py https://adoption.example.com --out assets`. The QR files in `assets/` point to the GitHub Pages site, https://Gowthamshivanand.github.io/nimbuspay-adoption-insights/.

### Alternatives
- **Netlify:** drag the folder onto app.netlify.com/drop, or connect the repository with no build command and publish directory `.`. For a custom domain, go to Domain settings, then add a CNAME to `<site>.netlify.app` (or an apex `A` record to `75.2.60.5`, or use Netlify DNS).
- **Vercel:** import the repository and choose framework "Other" with no build command. Add the domain in Project → Domains, then add a CNAME to `cname.vercel-dns.com` (or an apex `A` record to `76.76.21.21`).

Check the provider docs for the latest DNS values.

## Sources for synthetic ranges and definitions
These are used only to keep synthetic values plausible. No figures are copied as NimbusPay data.
- GitHub Docs, *Tracking license activation and initial usage*: healthy early adoption is about 60 to 80% of assigned users active in the first month. https://docs.github.com/en/copilot/tutorials/roll-out-at-scale/assign-licenses/track-usage-and-adoption
- GitHub Docs, *Interpreting usage and adoption metrics*: a WAU-to-licence ratio above 60% indicates strong usage. https://docs.github.com/en/copilot/reference/copilot-usage-metrics/interpret-copilot-metrics
- GitHub Docs, *Copilot usage metrics*: engaged means 2+ distinct days in 28. https://docs.github.com/en/copilot/reference/copilot-usage-metrics/copilot-usage-metrics
- Microsoft Learn, *Microsoft 365 Copilot usage report*: active users ÷ enabled users; opening a pane is not use. https://learn.microsoft.com/en-us/microsoft-365/admin/activity-reports/microsoft-365-copilot-usage
- Microsoft Learn, *Copilot adoption report (Viva Insights)*: a habitual user is active in 9 of 12 weeks. https://learn.microsoft.com/en-us/viva/insights/advanced/analyst/templates/microsoft-365-copilot-adoption
- Faros AI blog: high performers reach about 80% MAU and 60% DAU after six months (vendor blog; treat with care). https://www.faros.ai/blog/increase-github-copilot-adoption-and-usage-best-practices

## Credits
Concept, case solution and prototype: **Gowtham S**. Definitions come from his supporting workbook for the NimbusPay case. Not affiliated with NimbusPay (a fictional case company), HashedIn or Deloitte.
