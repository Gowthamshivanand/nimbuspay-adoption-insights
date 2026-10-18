"""FastAPI server: REST API + the web UI. Local, read-only analytics over SYNTHETIC data."""
import datetime as dt, html, json, os, re, sqlite3, threading, time
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import pipeline as P, agent as A, features as F, costcalc as CC, __version__
from . import conversation as CV, feedback as FB, modelcompare as MC

HERE = os.path.dirname(__file__)
SCEN = os.path.join(HERE, "data", "scenarios")
FILES = ("events.csv", "seats.csv", "registry.csv")


def _read(p):
    with open(p, encoding="utf-8") as f: return f.read()


def scenario_index():
    return json.load(open(os.path.join(SCEN, "index.json")))


def scenario_data(key):
    if key not in {s["key"] for s in scenario_index()}:
        raise HTTPException(404, "Unknown scenario")
    d = os.path.join(SCEN, key)
    return P.load(*[_read(os.path.join(d, f)) for f in FILES], json.load(open(os.path.join(d, "outcomes.json"))))


def run_scenario(key):
    return P.run(scenario_data(key))


class State:
    def __init__(self):
        self.lock = threading.Lock(); self.load("baseline")
        path = os.environ.get("AUDIT_DB", os.path.join(HERE, "var", "audit.db"))
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.audit = sqlite3.connect(path, check_same_thread=False)
        self.audit.execute("CREATE TABLE IF NOT EXISTS audit(ts TEXT, dataset TEXT, persona TEXT, question TEXT, type TEXT, intent TEXT, metrics TEXT, mode TEXT)")

    def load(self, key, data=None, label=None):
        data = data or scenario_data(key)
        res, db = P.run(data)
        self.data, self.db = data, db
        meta = next((s for s in scenario_index() if s["key"] == key), None)
        self.key, self.res, self.agent = key, res, A.Agent(res, db)
        self.label = label or (meta["label"] if meta else key)


S = State()
app = FastAPI(title="NimbusPay Adoption Insights", version=__version__)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


def _warm_finetuned():
    """NP_BRAIN=finetuned: load the model in the background at startup so the first question isn't slow (keep_alive keeps it)."""
    import threading
    from . import finetuned as FT
    if os.environ.get("NP_BRAIN", "").lower() == "finetuned" and os.environ.get("FT_WARMUP", "1") != "0":
        threading.Thread(target=lambda: FT.ready() and FT.warmup(), daemon=True).start()


_warm_finetuned()


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/health")
def health():
    return dict(ok=True, version=__version__, dataset=S.key, brain=A.brain_info(), label="Synthetic data")


@app.get("/api/brain")
def brain(refresh: bool = False):
    A.brain(refresh); return A.brain_info()


@app.get("/api/scenarios")
def scenarios():
    return scenario_index()


@app.post("/api/load/{key}")
def load(key: str):
    with S.lock: S.load(key)
    return state()


@app.get("/api/state")
def state():
    return dict(dataset=S.key, dataset_label=S.label, **S.res)


@app.post("/api/upload")
async def upload(events: UploadFile = File(...), seats: UploadFile = File(...), registry: UploadFile = File(...),
                 verified_hours_week: str = Form(""), cost_index: str = Form(""), critical_risk: str = Form("")):
    try:
        texts = [(await f.read()).decode("utf-8-sig") for f in (events, seats, registry)]
        data = P.load(*texts, dict(verified_hours_week=verified_hours_week, cost_index=cost_index, critical_risk=critical_risk))
        with S.lock: S.load("upload", data, "Uploaded CSVs")
    except P.ValidationError as e:
        raise HTTPException(422, str(e))
    except (UnicodeDecodeError, ValueError, KeyError) as e:
        raise HTTPException(422, f"Could not read the files: {e}")
    return state()


@app.get("/api/sample/{key}/{name}")
def sample(key: str, name: str):
    if name not in FILES + ("outcomes.json",) or key not in {s["key"] for s in scenario_index()}:
        raise HTTPException(404)
    return FileResponse(os.path.join(SCEN, key, name), filename=f"{key}_{name}")


class Ask(BaseModel):
    question: str
    persona: str | None = None      # missing or unknown -> least-privileged persona (deny by default)
    session_id: str | None = None   # optional: enables follow-ups ('and Region B?'); carries no role or permission
    previous: str | None = None     # optional previous question (stateless clients); the session is used if absent


def _answer(body):
    q = body.question.strip()[:500]
    if not q: raise HTTPException(422, "Empty question")
    persona = A.resolve_persona(body.persona)
    prev = (body.previous or "").strip()[:500] or None
    r = CV.respond(S.agent, q, persona, body.session_id, previous=prev)   # guards + role check run on every turn inside
    logged = persona if persona == body.persona else f"{persona} (requested: {body.persona or 'none'})"
    S.audit.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?,?)", (dt.datetime.now().isoformat(timespec="seconds"), S.key, logged, q,
                    r["type"], r["intent"], ",".join(c["metric"] for c in r["citations"]), r["mode"]))
    S.audit.commit()
    return r


@app.post("/api/ask")
def ask(body: Ask):
    return _answer(body)


STREAM_DELAY_S = float(os.environ.get("NP_STREAM_DELAY_MS", "18")) / 1000


@app.post("/api/ask/stream")
def ask_stream(body: Ask):
    """Server-sent events: 'meta' (brain, mode, confidence, latency), then 'token' chunks of the answer text, then 'done'
    with the full response. The answer is computed in full first (numbers from governed SQL), then streamed."""
    r = _answer(body)
    def gen():
        meta = {k: r.get(k) for k in ("type", "intent", "mode", "brain", "confidence", "confidence_basis", "latency_ms", "persona", "followup", "session_id")}
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"
        for tok in re.findall(r"\S+\s*", r["text"]):
            yield f"event: token\ndata: {json.dumps(tok)}\n\n"
            if STREAM_DELAY_S: time.sleep(STREAM_DELAY_S)
        yield f"event: done\ndata: {json.dumps(r, default=str)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.delete("/api/session/{sid}")
def end_session(sid: str):
    CV.STORE.clear(CV.valid_sid(sid) or "-"); return dict(ok=True)


class Feedback(BaseModel):
    question: str
    answer: str = ""
    rating: str
    brain: str = ""
    mode: str = ""
    intent: str = ""
    type: str = ""
    persona: str = ""
    comment: str = ""


@app.post("/api/feedback")
def feedback(body: Feedback):
    try:
        row = FB.record(body.question, body.answer, body.rating, body.brain, body.mode, body.intent, body.type,
                        A.resolve_persona(body.persona), S.key, body.comment)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return dict(ok=True, id=row["id"])


@app.get("/api/feedback")
def feedback_summary():
    return FB.summary()


@app.get("/api/models")
def models():
    return MC.overview()


@app.post("/api/models/run/{key}")
def models_run(key: str):
    if key not in dict(MC.BRAINS): raise HTTPException(404, "Unknown brain")
    ok, why = MC.available(key)
    if not ok: raise HTTPException(409, f"Not available: {why}")
    return MC.start(key)


@app.post("/api/models/upload")
async def models_upload(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 5_000_000: raise HTTPException(413, "File too large")
    try:
        return MC.add_upload(raw.decode("utf-8-sig"), file.filename)
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(422, f"Not a saved eval: {e}")


@app.get("/api/audit")
def audit(limit: int = 100):
    rows = S.audit.execute("SELECT * FROM audit ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
    return [dict(zip(["ts", "dataset", "persona", "question", "type", "intent", "metrics", "mode"], r)) for r in rows]


@app.get("/api/personas")
def personas():
    return {k: v["label"] for k, v in A.PERSONAS.items()}


@app.get("/api/compare")
def compare():
    out = []
    for s in scenario_index():
        r, _ = run_scenario(s["key"]); M = r["metrics"]
        out.append(dict(key=s["key"], label=s["label"], outcome=r["renewal"]["outcome"], evidence=r["renewal"]["evidence"],
                        M01=M["M01"]["value"], M02=M["M02"]["value"], M04=M["M04"]["value"], M10=M["M10"]["value"], M11=M["M11"]["value"],
                        M17=M["M17"]["value"], M18=M["M18"]["value"], M19=r["score"]["value"], score_state=r["score"]["state"],
                        interim=r["score"]["interim_index"], vendor_mau=r["users"]["vendor_mau_proxy"], active=len(r["users"]["active"]),
                        exact_share=r["grouping"]["exact_share"], alerts=len(r["alerts"])))
    return out


def boardpack_md():
    r = S.res; M = r["metrics"]; s = r["score"]; f = r["funnel"]
    L = [f"# NimbusPay AI Adoption: Board pack", "", f"**SYNTHETIC DATA - illustrative, not NimbusPay figures.** Dataset: {S.label}. Data as of {r['data_as_of']}. Period {r['period']}. Metric version {M['M01']['version']}.", "",
         f"## Recommendation: {r['renewal']['outcome']}", "", r["renewal"]["why"], "",
         "| Evidence area | Status |", "|---|---|"]
    names = dict(e1="1. Licence utilisation", e2="2. Verified business impact", e3="3. Unit economics", e4="4. Reliability and governance")
    L += [f"| {names[k]} | {v} |" for k, v in r["renewal"]["evidence"].items()]
    sc = f"{s['value']}/100" + (" (RED: critical-risk override)" if s["state"] == "red" else "") if s["value"] is not None else f"Withheld (no silent imputation). Interim index {s['interim_index']}/100"
    L += ["", f"## AI value score (M19): {sc}", "", "| Pillar | Weight | Score |", "|---|---|---|"]
    L += [f"| {k} | {s['weights'][k]} | {v if v is not None else 'no data'} |" for k, v in s["pillars"].items()]
    L += ["", "## Headline metrics", "", "| ID | Metric | Value | Note |", "|---|---|---|---|"]
    for mid in ("M01", "M02", "M04", "M07", "M10", "M17", "M18", "M19"):
        m = M[mid]; v = "withheld" if m["value"] is None else f"{m['value']}{'' if m['unit'] in ('/100',) else ' ' + m['unit']}"
        L.append(f"| {mid} | {m['label']}{' (approx.)' if m['approximate'] else ''} | {v} | {m['note']} |")
    L += ["", "## Licence funnel", "", f"Purchased {f['LF1']} -> Assigned {f['LF2']} -> Provisioned {f['LF3']} -> Active {f['LF4']} -> Engaged {f['LF5']} -> Habitual {f['LF6']}. "
          f"Vendor-style MAU proxy: {r['users']['vendor_mau_proxy']} (overstates Active by {r['users']['mau_overstatement']}).", "",
          "## Counting", "", f"{r['quality']['clean_events']} clean events -> {r['grouping']['interactions']} interactions ({r['grouping']['exact']} exact, {r['grouping']['approximate']} approximate); {r['grouping']['qualifying']} qualifying.", "",
          "## Alerts", ""]
    L += [f"- **{a['severity']}** ({a['metric']}): {a['text']}" for a in r["alerts"]] or ["- None"]
    L += ["", "_Generated by the read-only Adoption Insights product. Thresholds and weights are placeholders to agree in advance._"]
    return "\n".join(L)


@app.get("/api/boardpack")
def boardpack(format: str = "md"):
    md = boardpack_md()
    if format == "md":
        return PlainTextResponse(md, media_type="text/markdown", headers={"Content-Disposition": "attachment; filename=nimbuspay_board_pack.md"})
    body = []
    rows = []
    for line in md.split("\n"):
        e = html.escape(line).replace("**", "")
        if line.startswith("|"):
            if set(line) <= set("|-"): continue
            rows.append("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in e.strip("|").split("|")) + "</tr>"); continue
        if rows: body.append("<table>" + "".join(rows) + "</table>"); rows = []
        if line.startswith("# "): body.append(f"<h1>{e[2:]}</h1>")
        elif line.startswith("## "): body.append(f"<h2>{e[3:]}</h2>")
        elif line.startswith("- "): body.append(f"<li>{e[2:]}</li>")
        elif line: body.append(f"<p>{e}</p>")
    if rows: body.append("<table>" + "".join(rows) + "</table>")
    page = ("<!doctype html><meta charset=utf-8><title>NimbusPay board pack</title><style>body{font:14px Arial;max-width:860px;margin:30px auto;color:#222222}button{background:#F28C28;color:#fff;border:0;padding:6px 12px;border-radius:6px}"
            "h1{font-size:24px}h2{font-size:17px;margin-top:22px;border-bottom:2px solid #F28C28}table{border-collapse:collapse;width:100%}"
            "td{border:1px solid #ccc;padding:5px 8px}tr:first-child td{font-weight:bold;background:#fdf1e5}@media print{button{display:none}}</style>"
            "<button onclick='print()'>Print / Save as PDF</button>" + "".join(body))
    return HTMLResponse(page)


@app.get("/api/reclaim")
def reclaim():
    return F.seat_reclaim(S.data, S.res)


class WhatIf(BaseModel):
    seats: int | None = None
    connector_fix: bool = False
    id_coverage: float | None = None


@app.post("/api/whatif")
def whatif(body: WhatIf):
    return F.whatif(S.data, body.seats, body.connector_fix, body.id_coverage)


@app.get("/api/lineage/{mid}")
def lineage(mid: str):
    r = F.lineage(mid.upper(), S.res, S.db)
    if not r: raise HTTPException(404, "Not a governed metric in this view")
    return r


@app.post("/api/reconcile")
async def reconcile(invoice: UploadFile = File(...)):
    try:
        return F.reconcile((await invoice.read()).decode("utf-8-sig"), S.data, S.res)
    except P.ValidationError as e:
        raise HTTPException(422, str(e))


@app.get("/api/reconcile/sample")
def reconcile_sample():
    return F.reconcile(_read(os.path.join(HERE, "data", "samples", "vendor_invoice_sample.csv")), S.data, S.res)


@app.get("/api/reconcile/sample.csv")
def reconcile_sample_csv():
    return FileResponse(os.path.join(HERE, "data", "samples", "vendor_invoice_sample.csv"), filename="vendor_invoice_sample.csv")


class CostIn(BaseModel):
    users: float | None = None
    queries_per_user_day: float | None = None
    rules_share: float | None = None
    model: str | None = None
    tokens_in: float | None = None
    tokens_out: float | None = None


@app.get("/api/cost")
def cost_meta():
    return CC.meta()


@app.post("/api/cost")
def cost(body: CostIn):
    try:
        return CC.calculate(**body.model_dump())
    except CC.CalcError as e:
        raise HTTPException(422, str(e))
