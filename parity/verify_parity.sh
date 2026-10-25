#!/usr/bin/env bash
# NimbusPay v2 merge gate. Prints PASS/FAIL per gate and an overall verdict. Exit 0 only if every gate passes.
#   bash parity/verify_parity.sh --fresh https://github.com/<owner>/nimbuspay-adoption-insights redesign-v2   # (d) fresh clone
#   bash parity/verify_parity.sh --repo .                                                                      # current checkout
# Optional: --kit DIR (default: the folder of this script), --no-docker (reports gate G7 as FAIL, not skipped).
set -u
KIT="$(cd "$(dirname "$0")" && pwd)"; REPO=""; URL=""; BR=""; DOCKER=1
while [ $# -gt 0 ]; do case "$1" in
  --repo) REPO="$2"; shift 2;; --fresh) URL="$2"; BR="$3"; shift 3;; --kit) KIT="$2"; shift 2;; --no-docker) DOCKER=0; shift;;
  *) echo "unknown arg $1"; exit 2;; esac; done
if [ -n "$URL" ]; then REPO="$(mktemp -d)/repo"; git clone -q --branch "$BR" "$URL" "$REPO" || { echo "FAIL clone"; exit 1; }
  [ -d "$REPO/parity" ] && KIT="$REPO/parity"; fi
REPO="$(cd "${REPO:-.}" && pwd)"; cd "$REPO"; LOG="$(mktemp -d)"; declare -A R; ORDER=()
gate() { ORDER+=("$1"); R["$1"]="$2"; echo "[$2] $1"; }
PY_SYS="$(command -v python3 || command -v python)"
EXPECT_SHA="$(cat "$KIT/golden/golden_api.json.sha256")"
[ "$(sha256sum "$KIT/golden/golden_api.json" | cut -d' ' -f1)" = "$EXPECT_SHA" ] && [ "$EXPECT_SHA" = "ad0c88df79f1cee32bed2c6ce136b62a1d52e7060fdb44ea24435ef1f6060a9f" ] \
  && gate "G0 golden file untouched" PASS || gate "G0 golden file untouched" FAIL

# G1 install (clean venv)
"$PY_SYS" -m venv .venv-parity && V=.venv-parity/bin && $V/pip install -q -r requirements.txt -r requirements-dev.txt > "$LOG/pip.log" 2>&1 \
  && $V/python -m playwright install chromium > "$LOG/pw.log" 2>&1 && gate "G1 install" PASS || gate "G1 install" FAIL
PY="$REPO/.venv-parity/bin/python"

# G2 front-end build (React app in web/, output app/web). Required on redesign-v2.
if [ -f web/package.json ]; then
  (cd web && npm ci > "$LOG/npm.log" 2>&1 && npm run build >> "$LOG/npm.log" 2>&1) && [ -f app/web/index.html ] \
    && gate "G2 front-end build" PASS || gate "G2 front-end build" FAIL
else gate "G2 front-end build (no web/ folder: legacy UI only)" FAIL; fi

# G3 existing test suite: 386 passed, 1 skipped (modal not installed), 0 failed
$PY -m pytest -q -p no:cacheprovider tests/test_pipeline.py tests/test_agent.py tests/test_probes.py tests/test_persona.py tests/test_api.py tests/test_features.py tests/test_brain.py tests/test_cost.py tests/test_improvements.py tests/test_break_it.py tests/test_space.py tests/test_finetuned.py tests/test_remote_brain.py tests/test_demo_hardening.py > "$LOG/pytest.log" 2>&1
T="$(tail -1 "$LOG/pytest.log")"; PASSED=$(echo "$T" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+'); SK=$(echo "$T" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+')
{ ! echo "$T" | grep -qE 'failed|error'; } && [ $(( ${PASSED:-0} + ${SK:-0} )) -eq 387 ] && [ "${PASSED:-0}" -ge 386 ] \
  && gate "G3 tests ($T)" PASS || gate "G3 tests ($T)" FAIL

# G4 release gate + break-it
$PY tools/eval_agent.py --brain rules > "$LOG/eval.log" 2>&1; E1=$?
$PY tools/break_it.py > "$LOG/break.log" 2>&1; E2=$?
[ $E1 -eq 0 ] && [ $E2 -eq 0 ] && grep -qE 'Golden 21: 21/21 +Guard\+paraphrase probes: 29/29' "$LOG/eval.log" \
  && grep -q 'panel24: should-answer 17/17, should-refuse 7/7, total 24/24' "$LOG/eval.log" \
  && grep -q 'extra: should-answer 17/17, should-refuse 23/23, total 40/40' "$LOG/eval.log" \
  && grep -q 'Safe-to-invite set: 15/15 handled correctly; all cases 22/22' "$LOG/break.log" \
  && gate "G4 release gate 21/21 29/29 24/24 40/40, break-it 22/22" PASS || gate "G4 release gate" FAIL

# G5 golden API snapshots (fresh deterministic server)
PORT=7871; SP=$(PYTHON=$PY bash "$KIT/serve_golden.sh" "$REPO" $PORT)
$PY "$KIT/golden.py" check --base http://127.0.0.1:$PORT --root "$REPO" --golden "$KIT/golden" > "$LOG/golden.log" 2>&1 \
  && gate "G5 golden API ($(tail -1 "$LOG/golden.log"))" PASS || gate "G5 golden API ($(tail -1 "$LOG/golden.log")) see $LOG/golden.log" FAIL
# G6 UI: existing Playwright tests + every-screen smoke at 3 widths
$PY "$KIT/smoke_screens.py" --base http://127.0.0.1:$PORT > "$LOG/smoke.log" 2>&1; S1=$?
kill $SP 2>/dev/null
$PY -m pytest -q -p no:cacheprovider tests/test_ui_playwright.py tests/test_ui_features_playwright.py tests/test_ui_hardening_playwright.py > "$LOG/ui.log" 2>&1
U="$(tail -1 "$LOG/ui.log")"; git checkout -q -- docs/screenshots 2>/dev/null   # UI tests rewrite screenshots; never commit them from here
[ $S1 -eq 0 ] && echo "$U" | grep -qE '^4 passed' && gate "G6 UI (playwright: $U; smoke: $(tail -1 "$LOG/smoke.log"))" PASS || gate "G6 UI ($U / $(tail -1 "$LOG/smoke.log"))" FAIL

# G7 Docker image on port 7860
if [ $DOCKER -eq 1 ] && command -v docker >/dev/null; then
  docker build -q -t nimbuspay-parity . > "$LOG/docker.log" 2>&1 && CID=$(docker run -d --rm -p 7860:7860 nimbuspay-parity) && ok=0
  for i in $(seq 1 60); do curl -sf http://127.0.0.1:7860/api/health >/dev/null && { ok=1; break; }; sleep 1; done
  H=$(curl -s http://127.0.0.1:7860/ | grep -c "Adoption Insights"); curl -s http://127.0.0.1:7860/api/state > "$LOG/dstate.json"
  $PY - "$KIT/golden/golden_api.json" "$LOG/dstate.json" <<'PYEOF'
import json, sys; sys.path.insert(0, sys.argv[1].rsplit("/golden/", 1)[0]); import golden as G
want = json.load(open(sys.argv[1]))["state_initial"]["response"]["json"]; got = json.loads(json.dumps(G.norm(json.load(open(sys.argv[2]))), sort_keys=True))
sys.exit(0 if got == want else 1)
PYEOF
  DS=$?
  # Docker fix (approved by the project owner): "Explain this number" works (lineage 200) and the Models tab's rules engine row has its 21/21 eval
  LIN=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:7860/api/lineage/M01); RL=0
  for i in $(seq 1 90); do curl -s http://127.0.0.1:7860/api/models | $PY -c "import json,sys; b=[x for x in json.load(sys.stdin)['brains'] if x['key']=='rules'][0]; r=b['result']; sys.exit(0 if r and r['golden']['passed']==21 and r['golden']['total']==21 else 1)" && { RL=1; break; }; sleep 1; done
  docker stop "$CID" >/dev/null 2>&1
  [ "${ok:-0}" -eq 1 ] && [ "$H" -ge 1 ] && [ $DS -eq 0 ] && [ "$LIN" = 200 ] && [ $RL -eq 1 ] \
    && gate "G7 Docker :7860 health + UI + state + lineage 200 + rules eval 21/21" PASS || gate "G7 Docker :7860 (health=${ok:-0} ui=$H state=$DS lineage=$LIN rules_eval=$RL)" FAIL
else gate "G7 Docker :7860 (docker not available: run on a machine with Docker)" FAIL; fi

echo; echo "Logs: $LOG"; FAILS=0; for g in "${ORDER[@]}"; do [ "${R[$g]}" = PASS ] || FAILS=$((FAILS+1)); done
if [ $FAILS -eq 0 ]; then echo "OVERALL: PASS - redesign-v2 may be merged (tag v1-final first)"; exit 0
else echo "OVERALL: FAIL ($FAILS gate(s)) - do NOT merge; main stays as-is"; exit 1; fi
