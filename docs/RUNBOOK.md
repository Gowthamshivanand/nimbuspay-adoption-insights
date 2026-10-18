# Production runbook: Adoption Insights (one page)

> Synthetic-data MVP. Targets are **proposed, to agree** with the platform and analytics leads (assumption A5). Nothing here describes NimbusPay's real systems.
> Kill switch: `NP_BRAIN=rules`. Rollback: previous image + previous metric version. Model: demo default `qwen2.5:3b-instruct` is under a research licence (no commercial use); **production uses an Apache 2.0 Qwen 2.5 size (1.5B or 7B), chosen by re-running the agent test** (`eval_agent.py --brain ollama`).
> Owner on-call: platform (pipeline, app), analytics engineering (metric definitions).

## 1. SLOs (proposed)
| SLO | Target | Measured by |
|---|---|---|
| Availability (API + UI, business hours) | 99.5% monthly (assumption) | `/api/health` synthetic probe every 60 s |
| Agent answer latency | p95 <= 3 s with the local model; p95 <= 0.5 s on the rules brain (measured today: 0.09 ms, synthetic) | request histogram per `mode` |
| Dashboard latency | p95 <= 2 s on pre-aggregated tables | request histogram |
| Freshness (`data_as_of`) | curated tables ready by 09:00 local on 99% of days | `data_as_of` vs clock |
| Pipeline success | 99% of daily runs succeed | run log |
| Release quality | 100% golden (21/21) + probes (29/29, 64/64) at every release | `tools/eval_agent.py` in CI |

## 2. Signals and alert thresholds
| Signal | Warn | Page |
|---|---|---|
| Health probe failures | 2 in a row | 5 min down |
| Agent p95 latency (15 min window) | > 3 s | > 6 s or model timeouts > 5% |
| Fallback-to-rules rate (1 h) | > 10% | > 50% (brain effectively down) |
| Unmatched rate (1 day) | > 15% | n/a (drift review) |
| Refusal rate change vs 7-day mean | +/- 50% | guard bypass detected (any) |
| `data_as_of` age | > 26 h | > 50 h (past period close + 48 h restatement window) |
| Pipeline validation errors / row-count drop | any schema error; rows < 70% of 7-day mean | load published with failed checks |
| Cost (hosted model) | > 150% of the monthly budget run-rate | > 300% or tokens/question > 2x baseline (550 in / 10 out) |

All thresholds above are assumptions to tune after the first live month.

## 3. Dashboards
1. Service: availability, request rate, error rate, p50/p95 by endpoint.
2. Agent: questions by `mode` (ollama / rules), fallback and unmatched rate, refusals by guard, latency per brain, top unmatched questions.
3. Data: `data_as_of`, run status per step, row counts, late rows, restatements, interaction-ID coverage (exact vs approximate share).
4. Cost: questions/day, LLM share, tokens in/out, $/day vs budget (same formulas as the in-app **Cost and scale** tab, `app/costcalc.py`).
5. Audit: `/api/audit` volume by persona, deny-by-default fallbacks (unknown role -> guest).

## 4. Severities
| Sev | Meaning | Response |
|---|---|---|
| SEV1 | Wrong number shown as governed, data leak, or guard bypass that returned restricted data | Page now; freeze releases; exec + Risk informed within 1 h |
| SEV2 | Service down, or data stale past 50 h, or brain down without fallback | Page; fix or mitigate within 4 h |
| SEV3 | Degraded: slow model, fallback > 10%, single check failing | Next business day |
| SEV4 | Cosmetic, docs, drift review items | Backlog |

## 5. On-call playbooks (top failure modes)
**A. LLM brain down or slow** (p95 > 3 s, timeouts, fallback > 50%).
1. Confirm: `GET /api/brain?refresh=true` shows `kind` and model status; check `OLLAMA_HOST` reachability (`/api/tags`).
2. Mitigate: set `NP_BRAIN=rules` and restart (rules router answers every governed question; no hallucination risk).
3. Fix: restart Ollama / pull `OLLAMA_MODEL`; check host CPU/GPU saturation vs the instance count in the Cost tab. Lower `OLLAMA_TIMEOUT` (20 s today, 3 s target).
4. Restore `NP_BRAIN=auto` only after `python tools/eval_agent.py --brain ollama` passes.

**B. Bad data load** (schema error, row drop, duplicate spike, wrong period).
1. Do not publish: the load fails validation and keeps the last good `data_as_of`. If already published, mark affected metrics "restating".
2. Re-run the day (loads are idempotent); if the source is wrong, roll back to the previous partition.
3. Reconcile against the golden expectations and the vendor seat bill (`/api/reconcile`) before lifting the label.

**C. Eval gate failing** (CI red on golden or probes).
1. Release is blocked by design. Never skip the gate or edit expected results to pass.
2. Diff: `python tools/eval_agent.py --brain rules --json` vs last green; identify the prompt, model, tool or guard change.
3. Revert the change or fix it; add the failing case to `tests/data/probes.json` if new.

**D. Guardrail bypass attempt** (prompt injection, PII ask, named-person or small-group ask).
1. Guards run before the model, so the expected result is a refusal; confirm in `/api/audit`.
2. If any restricted data was returned: SEV1. Set `NP_BRAIN=rules`, preserve the audit rows, inform Risk / DPO (DPDP and GDPR breach assessment).
3. Add the prompt to the probe set as a should-refuse case; release only when it passes.

**E. Cost spike** (hosted model only).
1. Check questions/day, LLM share and tokens/question on the cost dashboard; look for a loop or a scraper persona.
2. Mitigate: rate-limit per persona, raise the rules share, or switch to `NP_BRAIN=rules` / the local model.
3. Recompute the forecast in the Cost tab with the new inputs and update the budget.

## 6. Rollback
1. Kill switch first: `NP_BRAIN=rules` (seconds, no deploy).
2. App: redeploy the previous Docker image tag (one image for all environments; config via env vars).
3. Metrics: pin the previous metric version (e.g. v1.0); restatements carry a note, never a silent change.
4. Data: restore the previous partition and re-run downstream steps (idempotent).
5. Verify: `/api/health`, eval gate green, `data_as_of` correct, then close the incident.

## 7. Release flow: DEV -> staging -> prod
1. **DEV:** feature branch; `make test` locally: 303 tests in CI plus 2 browser walkthroughs (`make test-ui`), then the agent test gate (`eval_agent.py --brain rules`).
2. **CI (GitHub Actions `tests.yml`):** unit, API, cost, probe tests + eval gate; merge blocked unless all pass.
3. **Staging:** same image on masked data; `eval_agent.py --brain ollama` against the production model; latency check vs SLO; red-team probes.
4. **Prod:** manual approval; canary to one role group; watch dashboards 1 and 2 for 24 h; widen.
5. Any model, prompt, tool or guard change goes through the same gate as code.

## 8. Post-incident template (within 10 working days)
```
Title / Sev / Date-time (IST) / Duration / Incident lead
Impact: who saw what (personas, metrics, numbers affected, data_as_of)
Timeline: detect -> mitigate -> resolve
Root cause (5 whys) and contributing factors
What worked / what didn't (alerts, runbook, fallback)
Actions: owner, due, and the regression test or probe added
Restatement or comms needed (board pack, Finance, Risk)
```
