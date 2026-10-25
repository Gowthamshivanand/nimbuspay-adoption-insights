"""Static demo data for the GitHub Pages build (VITE_STATIC=1).
Turns parity/golden/golden_api.json (874 responses recorded from the real backend) into dist/static-api/.
Nothing is invented: every response is a recorded one; '<volatile>' fields (latency, ids, timestamps) were not recorded, so they are left out.
Usage: python tools/build_static_api.py <dist_dir>"""
import hashlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = ["baseline", "healthy", "overstated", "shelfware", "newcountry", "incident", "noids", "breach"]
COST_DEFAULTS = None


def unvol(x):
    if isinstance(x, dict):   # not recorded -> not shown; a model eval's latency object stays an (empty) object so the table shows "-"
        if x.get("schema") == "nimbuspay-eval/1" and x.get("latency_ms") == "<volatile>": x = {**x, "latency_ms": {}}
        return {k: unvol(v) for k, v in x.items() if v != "<volatile>"}
    if isinstance(x, list): return [unvol(v) for v in x]
    return None if x == "<volatile>" else x


def canon(method, path, body):
    """Same rules as web/src/api/client.ts canonBody(): drop nulls and session_id; what-if drops connector_fix=false;
    cost fills the server's own defaults (CostIn None -> DEFAULTS, app/costcalc.py), so {} == the default form."""
    b = {k: v for k, v in (body or {}).items() if v is not None and k != "session_id"}
    if path == "/api/whatif" and b.get("connector_fix") is False: b.pop("connector_fix")
    if path == "/api/cost" and method == "POST": b = {**COST_DEFAULTS, **b}
    return method + " " + path + "|" + json.dumps(b, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(dist):
    global COST_DEFAULTS
    G = json.load(open(os.path.join(ROOT, "parity/golden/golden_api.json"), encoding="utf-8"))
    COST_DEFAULTS = G["cost_meta"]["response"]["json"]["defaults"]
    out = os.path.join(dist, "static-api"); os.makedirs(out, exist_ok=True)
    idx, sse, files = {}, {}, 0
    for name, c in G.items():
        m, p, r = c["method"], c["path"], c["response"]
        head = name.split("/")[0]
        if head in ("upload", "session") or name in ("ask_previous_field", "ui_index"): continue   # depend on an uploaded file or a session
        scope = "*" if p.startswith("/api/load/") else head if head in SCEN else "baseline" if head == "personas" or name.startswith("stream_") else "*"
        if "text" in r:   # CSV / board pack: write the recorded bytes as a static file (checked against the recorded sha256)
            raw = r["text"].encode("utf-8")
            if hashlib.sha256(raw).hexdigest() != r["sha256"] or r["status"] != 200: continue
            if p.startswith("/api/sample/"): rel = "sample/" + p[len("/api/sample/"):]
            elif p.startswith("/api/boardpack"): rel = f"boardpack/{scope}.{p.rsplit('=', 1)[1]}"
            elif p == "/api/reconcile/sample.csv": rel = "reconcile-sample.csv"
            else: continue
            fp = os.path.join(out, rel); os.makedirs(os.path.dirname(fp), exist_ok=True)
            open(fp, "wb").write(raw); files += 1
            continue
        key = scope + "|" + canon(m, p, c.get("request") if m != "GET" else None)
        if "sse" in r: sse[key] = unvol(r["sse"]); continue
        if "json" not in r: continue
        idx.setdefault(key, {"s": r["status"], "j": unvol(r["json"])})   # first recording wins (e.g. initial empty audit)
    json.dump({"source": "parity/golden/golden_api.json", "scenarios": SCEN, "json": idx, "sse": sse},
              open(os.path.join(out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"static-api: {len(idx)} json, {len(sse)} streams, {files} files")


if __name__ == "__main__":
    main(sys.argv[1])
