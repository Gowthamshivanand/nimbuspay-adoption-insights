#!/usr/bin/env bash
# Static GitHub Pages demo of the v2 front end (served at /nimbuspay-adoption-insights/). Usage: tools/build_pages_demo.sh [out_dir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; OUT="$(realpath -m "${1:-$ROOT/pages-dist}")"
cd "$ROOT/web"
npx tsc --noEmit
VITE_STATIC=1 VITE_OUT_DIR="$OUT" npx vite build --emptyOutDir
python3 "$ROOT/tools/build_static_api.py" "$OUT"
cp "$OUT/index.html" "$OUT/404.html"   # any deep link falls back to the app (routing is in-memory)
touch "$OUT/.nojekyll"
echo "pages demo: $OUT"
