"""Build the router + answer fine-tuning set (ENGLISH only, synthetic) from the repo itself.
  python finetune/make_dataset.py            # writes finetune/data/{train,val,test}.jsonl + stats.json
Gold labels come from the code, not from guesses:
  * the code guards are the authority: if a guard refuses a question, its label IS that refusal reason;
  * otherwise the label is the hand-written template label (that is where the model must beat the rules router, which
    misses typos, casual wording and follow-ups); disagreements with the rules router are counted in stats.json;
  * gold ANSWERS are built from the real Agent output on each synthetic scenario (FT.gold_answer: sentences of the
    governed template answer only), so every number in a gold answer is in the governed result by construction.
The test split holds out whole templates (new phrasings), new agent aliases, two whole scenarios for answers, and
the existing 21 golden questions, 8 extra probes, 64 unscripted probes and the 22 try-to-break-it cases. None of those
appear in train or val. Labels follow the current code guards (9 guards incl. injection) and the claim check."""
import json, os, random, re, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
from app import pipeline as P, agent as A, finetuned as FT
from templates_en import T, AGENT_REFS, REGION_REFS, FOLLOWUPS

SEED = 20261018
PERSONAS = ["executive", "regional_lead", "platform_engineer", "fraud_ops_lead", "finance"]
SCOPED = {"regional_lead", "fraud_ops_lead"}           # both are scoped to Region A in app.agent.PERSONAS
SCEN_SPLIT = {"train": ["workbook", "baseline", "breach", "healthy", "newcountry", "overstated"], "val": ["noids"], "test": ["incident", "shelfware"]}
OUT = os.path.join(HERE, "data")


def rd(p): return open(p, encoding="utf-8").read()


def load(name):
    if name == "workbook":
        d, o = os.path.join(ROOT, "app", "data", "base"), {}
    else:
        d = os.path.join(ROOT, "app", "data", "scenarios", name); o = json.load(open(os.path.join(d, "outcomes.json")))
    return A.Agent(*P.run(P.load(rd(os.path.join(d, "events.csv")), rd(os.path.join(d, "seats.csv")), rd(os.path.join(d, "registry.csv")), o)))


def norm(q): return re.sub(r"[^a-z0-9]+", " ", q.lower()).strip()


def rules_label(ag, q, persona):
    """What the deterministic engine does: guard refusal reason, or routed tool + the args it would extract."""
    persona = A.resolve_persona(persona)
    g = ag.guards(q, persona)
    if g: return "refuse", {"reason": g["intent"]}
    q = re.sub(r"<[^<>]{0,300}>", " ", q).strip() or q        # same markup stripping as Agent.ask
    fn = ag.route(q); ql = q.lower()
    if not fn: return "none", {}
    args = {}
    if fn == "m01":
        regs = A._regions_in(ql)
        if len(regs) == 1: args["region"] = regs[0]
    if fn in ("agent_health", "agent_value"):
        aid = ag._agent_in(ql)
        if aid: args["agent"] = aid
    if fn == "outcome":
        args["metric"] = next((m for p, m, *_ in A.OUTCOME if re.search(p, ql)), "M07")
    return fn, args


# ---------- English variety: casual wording, typos, abbreviations ----------
PRE = ["", "", "hey, ", "quick one: ", "so ", "ok ", "can you tell me ", "i was wondering, ", "hi! ", "question: ", "pls tell me ", "real quick, "]
SUF = ["", "", "?", "??", " pls", " thanks", " for the board", " please", " this period", " right now", " - need it for a deck"]
ABBR = [(r"\butilisation\b", "utilization"), (r"\butilisation\b", "util"), (r"\blicence\b", "license"), (r"\byou\b", "u"), (r"\bare\b", "r"),
        (r"\bplease\b", "pls"), (r"\bpeople\b", "ppl"), (r"\bwhat is\b", "whats"), (r"\bwhat's\b", "wats"), (r"\bbecause\b", "cuz"), (r"\bthe\b", "da")]
KEYB = {c: n for c, n in zip("qwertyuiopasdfghjklzxcvbnm", "wqeryutoipsadgfhkjlxzvcnbm")}


def typo(q, rng, n=None):
    words = q.split(" "); idx = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha() and w.islower()]
    for i in rng.sample(idx, min(len(idx), n or rng.choice([1, 1, 2]))):
        w = list(words[i]); j = rng.randrange(1, len(w) - 1); op = rng.choice("swap drop dup key".split())
        if op == "swap": w[j], w[j + 1 if j + 1 < len(w) else j - 1] = w[j + 1 if j + 1 < len(w) else j - 1], w[j]
        elif op == "drop": del w[j]
        elif op == "dup": w.insert(j, w[j])
        else: w[j] = KEYB.get(w[j], w[j])
        words[i] = "".join(w)
    return " ".join(words)


def casual(q, rng):
    q2 = q.rstrip("?.!") if rng.random() < 0.6 else q
    if rng.random() < 0.5: q2 = q2[0].lower() + q2[1:]
    return (rng.choice(PRE) + q2 + rng.choice(SUF)).strip()


def abbrev(q, rng):
    out = q
    for pat, rep in rng.sample(ABBR, 3):
        out = re.sub(pat, rep, out, flags=re.I)
    return out


def variants(q, k, rng):
    out = [(q, "clean")]
    styles = ["casual", "typo", "casual+typo", "abbrev", "lower", "casual+abbrev"]
    tries = 0
    while len(out) < k and tries < 40:
        tries += 1; s = rng.choice(styles); v = q
        if "casual" in s: v = casual(v, rng)
        if "abbrev" in s: v = abbrev(v, rng)
        if "typo" in s: v = typo(v.lower() if rng.random() < 0.5 else v, rng)
        if s == "lower": v = re.sub(r"[?.!]+$", "", v.lower())
        if norm(v) not in {norm(x) for x, _ in out}: out.append((v, s))
    return out


def fill(tpl, rng, agent_pool, region_pool):
    """Return (question, args) for one template. agent_pool/region_pool: which alias lists to draw from."""
    args = {}
    if "{agent}" in tpl:
        aid = rng.choice(list(agent_pool)); args["agent"] = aid; tpl = tpl.replace("{agent}", rng.choice(agent_pool[aid]))
    if "{region}" in tpl:
        reg = rng.choice(list(region_pool)); args["region"] = reg; tpl = tpl.replace("{region}", rng.choice(region_pool[reg]))
    q = tpl[0].upper() + tpl[1:] if tpl[:1].islower() and rng.random() < 0.5 else tpl
    return q, args


def base_label(label, args, q, persona, src_label_args=True):
    """Template label -> (tool, args), applying the role scope rule for region mentions."""
    if label.startswith("refuse:"): return "refuse", {"reason": label.split(":", 1)[1]}
    mentioned = set(A._regions_in(q.lower())) | ({args["region"]} if "region" in args else set())
    if persona in SCOPED and any(r != "Region A" for r in mentioned): return "refuse", {"reason": "scope"}
    keep = {k: v for k, v in args.items() if k in FT.ARG_KEYS.get(label, set())}
    return label, keep


def route_rec(q, persona, tool, args, split, source, style, prev=None, extra=None):
    msgs = FT.route_messages(q, persona, prev) + [{"role": "assistant", "content": FT.route_target(tool, args)}]
    return dict(task="route", split=split, source=source, style=style, persona=persona, question=q, previous=prev,
                label=tool, args=args, messages=msgs, **(extra or {}))


def main():
    rng = random.Random(SEED)
    wb = load("workbook")
    agent_train = {k: v[0] for k, v in AGENT_REFS.items()}; agent_test = {k: v[1] for k, v in AGENT_REFS.items()}
    stats = Counter(); disagree = []; relabelled = []

    # ---- held-out evaluation sets from the repo: golden 21, extra probes 8, unscripted 64 ----
    sys.path.insert(0, os.path.join(ROOT, "tools")); import probe_check as PC
    held = [(cid, q, per, "golden" if cid.startswith("Q") else "probe_extra", t) for cid, q, per, t, _ in PC.golden_cases()]
    pr = json.load(open(os.path.join(ROOT, "tests", "data", "probes.json")))
    held += [(p["id"], p["q"], p.get("persona", "executive"), "unscripted", p["expect"]) for p in pr["panel24"] + pr["extra"]]
    bi = json.load(open(os.path.join(ROOT, "tests", "data", "break_it.json"), encoding="utf-8"))["cases"]
    held += [(c["id"], c["q"], c["persona"], "break_it", c["expect_type"]) for c in bi]
    test = []
    for hid, q, per, src, expect in held:
        tool, args = rules_label(wb, q, per)
        test.append(route_rec(q, A.resolve_persona(per), tool, args, "test", src, "repo", extra=dict(ref_id=hid, expect=expect)))
    banned = {norm(r["question"]) for r in test}

    # ---- template questions ----
    def gen(label, tpl, split, source, k, agent_pool, region_pool, out):
        if isinstance(tpl, tuple): tpl, metric = tpl
        else: metric = None
        for _ in range(max(1, k // 3)):
            q0, args = fill(tpl, rng, agent_pool, region_pool)
            if metric: args["metric"] = metric
            if norm(q0) in banned: stats["dropped_overlap_with_test"] += 1; continue
            persona = rng.choice(PERSONAS)
            tool, a2 = base_label(label, args, q0, persona)
            g = wb.guards(q0, persona)
            if g and (tool, a2.get("reason")) != ("refuse", g["intent"]):
                stats["relabelled_by_guard"] += 1; relabelled.append(dict(q=q0, persona=persona, template=label, guard=g["intent"]))
                tool, a2 = "refuse", {"reason": g["intent"]}
            rt, ra = rules_label(wb, q0, persona)
            stats["rules_agree_clean" if (rt, ra) == (tool, a2) else "rules_disagree_clean"] += 1
            if (rt, ra) != (tool, a2) and len(disagree) < 400: disagree.append(dict(q=q0, persona=persona, label=[tool, a2], rules=[rt, ra]))
            for v, style in variants(q0, 3, rng):
                if norm(v) in banned: continue
                gv = wb.guards(v, persona)
                t, a = ("refuse", {"reason": gv["intent"]}) if gv else (tool, a2)
                out.append(route_rec(v, persona, t, a, split, source, style))

    train_val = []
    for label, (tr, te) in T.items():
        reps = 13 if label.startswith("refuse:") or label == "none" else 12
        for tpl in tr:
            gen(label, tpl, "trainval", "template", reps, agent_train, REGION_REFS, train_val)
        for tpl in te:
            gen(label, tpl, "test", "heldout_template", 3, agent_train, REGION_REFS, test)
        if label in ("agent_health", "agent_value"):
            for tpl in tr[:4]:
                gen(label, tpl, "test", "new_alias", 3, agent_test, REGION_REFS, test)
    for split, items, k in (("trainval", FOLLOWUPS[0], 12), ("test", FOLLOWUPS[1], 4)):
        for prev, q, label, args in items:
            for _ in range(k // 3 + 1):
                persona = rng.choice([p for p in PERSONAS if p not in SCOPED] if "region" in args and args["region"] != "Region A" else PERSONAS)
                tool, a2 = (("refuse", {"reason": label.split(":")[1]}) if label.startswith("refuse:") else (label, args))
                for v, style in variants(q, 3, rng):
                    g = wb.guards(v, persona)
                    t, a = ("refuse", {"reason": g["intent"]}) if g else (tool, a2)
                    rec = route_rec(v, persona, t, a, split, "followup" if split == "trainval" else "heldout_followup", style, prev=prev)
                    (train_val if split == "trainval" else test).append(rec)

    # ---- dedupe: nothing in train/val may equal a test question; no duplicate prompts inside a split ----
    test_keys = {norm(r["question"]) + "|" + str(r["previous"]) for r in test}
    seen, tv = set(), []
    for r in train_val:
        key = norm(r["question"]) + "|" + str(r["previous"])
        if key in test_keys or norm(r["question"]) in banned: stats["dropped_overlap_with_test"] += 1; continue
        if key + r["persona"] in seen: continue
        seen.add(key + r["persona"]); tv.append(r)
    rng.shuffle(tv)
    n_val = 300
    val = [dict(r, split="val") for r in tv[:n_val]]; train = [dict(r, split="train") for r in tv[n_val:]]
    seen_t, test2 = set(), []
    for r in test:
        key = norm(r["question"]) + "|" + str(r["previous"]) + r["persona"]
        if key in seen_t and r["source"] not in ("golden", "probe_extra", "unscripted", "break_it"): continue
        seen_t.add(key); test2.append(r)
    test = test2

    # ---- ANSWER task: real Agent outputs per synthetic scenario ----
    def answer_recs(split, scen_names, templates_idx, per_tool):
        out = []
        for sname in scen_names:
            ag = load(sname)
            for label, (tr, te) in T.items():
                if label.startswith("refuse:") or label == "none": continue
                pool = tr if templates_idx == 0 else (te or tr)
                for _ in range(per_tool):
                    tpl = rng.choice(pool); metric = None
                    if isinstance(tpl, tuple): tpl, metric = tpl
                    q, args = fill(tpl, rng, agent_train if templates_idx == 0 else agent_test, REGION_REFS)
                    if metric: args["metric"] = metric
                    persona = rng.choice(["executive", "executive", "platform_engineer", "finance", "regional_lead"])
                    if persona in SCOPED and (args.get("region", "Region A") != "Region A" or set(A._regions_in(q.lower())) - {"Region A"}): persona = "executive"
                    if ag.guards(q, persona) or A.claimed_numbers(q): continue      # claim questions never get a model-written answer
                    a = {k: v for k, v in args.items() if k in FT.ARG_KEYS.get(label, set())}
                    ag._ctx.args = a
                    try: r = getattr(ag, label)(q, persona)
                    finally: ag._ctx.args = None
                    if r["type"] not in ("answer", "caveat"): continue
                    r["rows"] = [list(x) for x in (r.get("rows") or [])]
                    gold = FT.gold_answer(r)
                    assert not FT.unfaithful_numbers(gold, r), (label, gold)
                    msgs = FT.answer_messages(q, persona, r) + [{"role": "assistant", "content": gold}]
                    out.append(dict(task="answer", split=split, source="scenario:" + sname, style="clean", persona=persona, question=q, previous=None,
                                    label=label, args=a, messages=msgs,
                                    governed=dict(text=r["text"], rows=r["rows"], citations=r["citations"], data_as_of=r["data_as_of"], type=r["type"])))
        return out
    ans_train = answer_recs("train", SCEN_SPLIT["train"], 0, 3)
    ans_val = answer_recs("val", SCEN_SPLIT["val"], 0, 2)
    ans_test = answer_recs("test", SCEN_SPLIT["test"], 1, 2)
    train += ans_train; val += ans_val; test += ans_test
    rng.shuffle(train)

    os.makedirs(OUT, exist_ok=True)
    for name, rows in (("train", train), ("val", val), ("test", test)):
        with open(os.path.join(OUT, name + ".jsonl"), "w", encoding="utf-8") as f:
            for i, r in enumerate(rows):
                r = {"id": f"{name}-{i:05d}", **r}
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    def summ(rows):
        return dict(total=len(rows), by_task=dict(Counter(r["task"] for r in rows)), by_source=dict(Counter(r["source"].split(":")[0] for r in rows)),
                    by_style=dict(Counter(r["style"] for r in rows if r["task"] == "route")),
                    by_label=dict(sorted(Counter(r["label"] if r["label"] != "refuse" else "refuse:" + r["args"]["reason"] for r in rows if r["task"] == "route").items())),
                    language={"en": len(rows)})
    st = dict(seed=SEED, language="English only (synthetic)", train=summ(train), val=summ(val), test=summ(test),
              notes=dict(stats), sizes_bytes={n: os.path.getsize(os.path.join(OUT, n + ".jsonl")) for n in ("train", "val", "test")},
              sample_rules_disagreements=disagree[:60], relabelled_by_guard=relabelled)
    json.dump(st, open(os.path.join(OUT, "stats.json"), "w"), indent=1)
    print(json.dumps({k: st[k] for k in ("train", "val", "test", "notes", "sizes_bytes")}, indent=1))


if __name__ == "__main__":
    main()
