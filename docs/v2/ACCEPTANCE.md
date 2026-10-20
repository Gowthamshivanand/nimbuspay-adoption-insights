# Acceptance and merge gate for NimbusPay v2 (redesign only)

**Rule from Mohith: the code must work.** `main` changes only when every gate below passes. Otherwise `main` stays exactly as it is.

## 1. Branch workflow for Gowtham's bot (no force-push, ever)
```bash
git checkout main && git pull --ff-only
git tag v1-final d2dc703 && git push origin v1-final        # tag the old main BEFORE any work or merge (d2dc703 = his current main)
git checkout -b redesign-v2                                 # all redesign work happens here
mkdir parity && cp -r <app-v2-kit>/parity/* parity/          # this kit: golden.py, golden/, smoke_screens.py, serve_golden.sh, verify_parity.*
printf 'parity/golden/** -text\napp/data/** -text\napp/static/** -text\n' >> .gitattributes   # keep LF on Windows so golden bytes match
git add parity .gitattributes && git commit -m "Add parity gate (golden API snapshots, smoke, verify scripts)"
# ...build the React app in web/ (Vite outDir ../app/web), wire FastAPI to serve it (§4)...
git push -u origin redesign-v2
```
Merge only after a **fresh-clone** run of the gate passes:
```bash
bash parity/verify_parity.sh --fresh https://github.com/Gowthamshivanand/nimbuspay-adoption-insights redesign-v2
# Windows:  powershell -ExecutionPolicy Bypass -File parity\verify_parity.ps1 -Fresh https://github.com/Gowthamshivanand/nimbuspay-adoption-insights -Branch redesign-v2
```
`OVERALL: PASS` → `git checkout main && git merge --no-ff redesign-v2 && git push origin main` (a normal push).
`OVERALL: FAIL` → do not merge. Fix the problem on `redesign-v2` and re-run. If the deadline arrives first, **submit `main` as it is (v1)**.

## 2. The gates (all must PASS; checked by `verify_parity.sh` / `verify_parity.ps1`)
| Gate | What | Pass condition (measured on v1 `acc2b65`/`d2dc703`, 20 Oct 2026) |
|---|---|---|
| G0 | Golden file untouched | sha256 of `parity/golden/golden_api.json` = `ad0c88df79f1cee32bed2c6ce136b62a1d52e7060fdb44ea24435ef1f6060a9f` |
| G1 | Clean install | `python -m venv`, `pip install -r requirements.txt -r requirements-dev.txt`, `playwright install chromium` |
| G2 | Front-end build | `cd web && npm ci && npm run build` produces `app/web/index.html` (fails on v1 by design: there's no React yet) |
| G3 | **Existing test suite, same count** | the `make test` pytest list (14 files): **386 passed, 1 skipped, 0 failed** (the skip is `test_remote_brain.py:219`, which needs the optional `modal` package). The rule is passed + skipped = 387 and passed ≥ 386. **No test file may be edited or deleted.** |
| G4 | **Release gate, same result** | `python tools/eval_agent.py --brain rules` exit 0 with `Golden 21: 21/21`, `Guard+paraphrase probes: 29/29`, `panel24: … total 24/24`, `extra: … total 40/40`; `python tools/break_it.py` exit 0 with `Safe-to-invite set: 15/15 …; all cases 22/22` |
| G5 | **Golden API snapshots** | `parity/golden.py check` against a fresh deterministic server: **874/874 match** (normalized JSON; text responses exact). This covers every GET endpoint, all 8 scenarios (state, reclaim, reconcile, board pack md + html, 13 lineage ids, 5 what-ifs, 47 agent questions), 10 personas × 22 golden questions, a 6-turn session with follow-ups, SSE stream, cost (9 bodies), uploads, reconcile, feedback, models, and every 404/409/422 error case |
| G6 | **UI behaviour** | the existing Playwright files `tests/test_ui_*.py`: **4 passed**; plus `parity/smoke_screens.py`: every tab, both modals, agent answer, what-if, reconcile and RED score, at 1440 / 834 / 390 px, with **no page JS errors and no dialogs** |
| G7 | **Docker on port 7860** | `docker build .` then `docker run -p 7860:7860`: `/api/health` 200 within 60 s, `/` contains "Adoption Insights", `/api/state` equals the golden `state_initial`, **`/api/lineage/M01` returns 200, and the Models rules row shows its eval (golden 21/21)** (the approved Docker fix) |

Measured on v1 in this box: G0, G1, G3, G4, G5 and G6 **PASS**. G2 FAIL is expected (no React yet). G7 couldn't run because there is no Docker here, so it must run on Gowtham's machine with Docker Desktop.

### Deterministic server for G5/G6 (what `serve_golden.sh` sets)
`NP_BRAIN=rules OLLAMA_HOST=http://127.0.0.1:9 NP_STREAM_DELAY_MS=0 FT_WARMUP=0 NP_DEMO=0 NP_READONLY_PUBLIC=0`, empty `LLM_API_KEY/OPENAI_API_KEY/FT_REMOTE_URL`, and fresh temp `AUDIT_DB`, `NP_FEEDBACK`, `NP_EVAL_DIR`. Volatile keys are normalized: `latency_ms ts generated_at started finished id p50 p95 run_exit_code path`. The run is order-sensitive: always start a **fresh** server. Capture was run twice on fresh servers (874/874 both times).

## 3. UI behaviour checks (Playwright). Existing tests plus the smoke list
Already automated (G6): the walkthrough (`test_ui_playwright.py`), the agent features (`test_ui_features_playwright.py`), audit XSS and the error bubble (`test_ui_hardening_playwright.py`), and `smoke_screens.py`. The bot must also check these by hand or add them to `smoke_screens.py` (new test files are allowed; editing existing ones is not):
1. On load: Data tab, 8 scenario cards, the dataset line shows "data as of 2026-10-03 13:35 UTC".
2. Role buttons and the select stay in sync; Guest shows red; changing the role re-renders the Agent tab.
3. Loading a scenario clears the chat. Upload with bad CSVs shows "Rejected: events.csv: missing columns […]".
4. Executive: 7 KPI cards. Clicking any of them opens the lineage modal (backdrop or Close dismisses it). newcountry shows "Withheld" with interim 42; breach shows "59/100 RED".
5. What-if: the ID slider is sent only once touched; Reset re-renders it; seats 20 gives "Expand".
6. Seats: reclaimable is exactly "10". The sample invoice shows 2 mismatches. A bad invoice shows "Rejected: …".
7. Agent: the 22 chips (Q01–Q21 + 1 unnumbered) ask exactly those texts. Streaming shows the cursor, then the final bubble. Tags: type, brain, mode, "N ms", "confidence N%". SQL sits in a disclosure. Why this number shows Rows returned = "1" for a Region B follow-up. Feedback can be given once only. "Ask as" re-asks with the other persona. When the stream fails it falls back to `/api/ask`; if both fail, the "didn't answer" bubble appears.
8. Alerts: baseline shows 6 rows, and the empty state reads "No alerts". Compare shows "Computing..." and then 8 rows. Board pack: the iframe plus 2 buttons. Audit: newest first, every cell plain text, and the empty state reads "No questions yet".
9. Cost: changing any input updates the output live; the default is "$586.37"; an invalid value shows a red error.
10. Models: the rules row reads 21/21 · 24/24 · 40/40 · 0 / 47 · 97.8% · pass; Ollama and Fine-tuned read "not available"; uploading a saved eval adds the `mrow-up-0` row; a bad upload shows "Rejected: …".
11. Mobile (390 px): all 13 tabs are reachable, tables scroll sideways, modals fit the screen.

## 4. Allowed vs forbidden changes
**Allowed:** a new React/Vite/TS/Tailwind app in `web/` built to `app/web/`. In `server.py`: serve `app/web/index.html` at `/` when it exists (otherwise the legacy `app/static/index.html`), mount `/assets` from `app/web/assets`, and add `/legacy` serving `app/static/index.html`. Python restructuring that leaves every golden snapshot identical. New tests. README notes on how to build.
**Forbidden:** editing or deleting any existing test; changing `app/static/*` (the legacy UI is part of the tests); changing any Python output, refusal text, threshold, data file or env default; changing the Dockerfile's port, brain or user; binary files in `app/` (the Space check); force-push; committing `.venv-parity/` or rewritten `docs/screenshots/*.png` (the UI tests rewrite them; the scripts restore them with `git checkout`). Add `.venv-parity/` to `.gitignore`.

**Docker fix (approved by Mohith on 20 Oct 2026, the only intentional behaviour change):** the image used to copy only `app/`, so in Docker `/api/lineage/*` returned 500 ("Explain this number" did nothing) and the Models rules row showed "not available". The Dockerfile now also copies `src/data.json`, `tools/` and `tests/data/probes.json` (the rules eval needs the probe file too, which the earlier two-line fix missed); `.dockerignore` re-includes them and `tools/make_space.py` ships them to the HF Space. `tests/test_docker_files.py` fails if any drops out. G7 expects the fixed behaviour. A standalone patch for v1 main is `docker-fix.patch`.
