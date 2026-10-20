#!/usr/bin/env bash
# Start a fresh, deterministic server for golden capture/check. Usage: serve_golden.sh <repo_root> <port> ; prints PID
set -e
ROOT="$1"; PORT="${2:-7861}"; T=$(mktemp -d)
cd "$ROOT"
HOST=127.0.0.1 PORT=$PORT NP_BRAIN=rules OLLAMA_HOST=http://127.0.0.1:9 NP_STREAM_DELAY_MS=0 FT_WARMUP=0 \
AUDIT_DB=$T/audit.db NP_FEEDBACK=$T/fb/feedback.jsonl NP_EVAL_DIR=$T/evals NP_DEMO=0 NP_READONLY_PUBLIC=0 \
LLM_API_KEY= OPENAI_API_KEY= FT_REMOTE_URL= nohup "${PYTHON:-python}" -m app > $T/server.log 2>&1 &
echo $!
for i in $(seq 1 80); do curl -sf http://127.0.0.1:$PORT/api/health >/dev/null && exit 0; sleep 0.25; done
echo "server did not start; see $T/server.log" >&2; exit 1
