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
appear in train or val. Labels follow the current code guards (9 guards incl. injection) and the claim check.
v2 adds (templates_en.CATS etc.): indirect phrasing, multi-part (rule in data/README.md), near-misses both ways, clarify
(none + clarify agent|topic; the conversation.needs_clarify rule relabels too), small_group / scope balance, long and
noisy wrappers, mixed roles (guest / analyst / manager / executive, outcome stored), more answer rows (caveats, empty
slices, scoped roles, claim-check wording) and the separate hard test set (hard_test_en.py, test only).
The public sample is a separate step (fetch_public.py, make_public.py) and never enters these three files."""
import json, os, random, re, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
from app import pipeline as P, agent as A, finetuned as FT, conversation as CV
from templates_en import T, AGENT_REFS, REGION_REFS, FOLLOWUPS, CLAIMS, CATS, WRAPPERS, MIXED_ROLE, MIXED_PERSONAS
from templates_en import AGENT_REFS_V3, CATS_V3, MIXED_ROLE_V3, MIXED_PERSONAS_V3
from hard_test_en import HARD_TEST                       # test split only; overlap with train/val is filtered and tested

SEED = 20261018
PERSONAS = ["executive", "regional_lead", "platform_engineer", "fraud_ops_lead", "finance", "manager", "analyst"]
SCOPED = {"regional_lead", "fraud_ops_lead", "analyst"}   # all scoped to Region A in app.agent.PERSONAS
CLARIFY_TOOLS = CV.AGENT_TOOLS + ("m17", "reliability", "m10")   # where conversation.needs_clarify asks "which agent?"
SCEN_SPLIT = {"train": ["workbook", "baseline", "breach", "healthy", "newcountry", "overstated"], "val": ["noids"], "test": ["incident", "shelfware"]}
OUT = os.path.join(HERE, "data")


def rd(p): return open(p, encoding="utf-8").read()


def load(name):
    if name == "workbook":
        d, o = os.path.join(ROOT, "app", "data", "base"), {}
    else:
        d = os.path.join(ROOT, "app", "data", "scenarios", name); o = json.load(open(os.path.join(d, "outcomes.json"), encoding="utf-8"))
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
    if persona != A.LEAST_PRIVILEGE and CV.needs_clarify(ag, q, fn): return "none", {"clarify": "agent"}   # same as conversation.respond
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
    if "{other_region}" in tpl:                         # scope cases: a region outside the caller's Region A
        reg = rng.choice(["Region B", "Region C"]); tpl = tpl.replace("{other_region}", rng.choice(REGION_REFS[reg]))
    if "{region}" in tpl:
        reg = rng.choice(list(region_pool)); args["region"] = reg; tpl = tpl.replace("{region}", rng.choice(region_pool[reg]))
    q = tpl[0].upper() + tpl[1:] if tpl[:1].islower() and rng.random() < 0.5 else tpl
    return q, args


def base_label(label, args, q, persona, src_label_args=True):
    """Template label -> (tool, args), applying the role scope rule for region mentions."""
    if label.startswith("refuse:"): return "refuse", {"reason": label.split(":", 1)[1]}
    if label.startswith("none:"): return "none", {"clarify": label.split(":", 1)[1]}
    mentioned = set(A._regions_in(q.lower())) | ({args["region"]} if "region" in args else set())
    if persona in SCOPED and any(r != "Region A" for r in mentioned): return "refuse", {"reason": "scope"}
    keep = {k: v for k, v in args.items() if k in FT.ARG_KEYS.get(label, set())}
    return label, keep


def label_key(r):
    if r["label"] == "refuse": return "refuse:" + r["args"]["reason"]
    if r["label"] == "none" and r["args"].get("clarify"): return "none:" + r["args"]["clarify"]
    return r["label"]


def route_rec(q, persona, tool, args, split, source, style, prev=None, extra=None):
    msgs = FT.route_messages(q, persona, prev) + [{"role": "assistant", "content": FT.route_target(tool, args)}]
    return dict(task="route", split=split, source=source, style=style, persona=persona, question=q, previous=prev,
                label=tool, args=args, messages=msgs, **(extra or {}))


def main():
    rng = random.Random(SEED)
    wb = load("workbook")
    agent_train = {k: v[0] for k, v in AGENT_REFS.items()}; agent_test = {k: v[1] for k, v in AGENT_REFS.items()}
    agent_v3 = {k: v[0] + AGENT_REFS_V3.get(k, []) for k, v in AGENT_REFS.items()}     # v3: more train-only alias forms
    stats = Counter(); disagree = []; relabelled = []

    # ---- held-out evaluation sets from the repo: golden 21, extra probes 8, unscripted 64 ----
    sys.path.insert(0, os.path.join(ROOT, "tools")); import probe_check as PC
    held = [(cid, q, per, "golden" if cid.startswith("Q") else "probe_extra", t) for cid, q, per, t, _ in PC.golden_cases()]
    pr = json.load(open(os.path.join(ROOT, "tests", "data", "probes.json"), encoding="utf-8"))
    held += [(p["id"], p["q"], p.get("persona", "executive"), "unscripted", p["expect"]) for p in pr["panel24"] + pr["extra"]]
    bi = json.load(open(os.path.join(ROOT, "tests", "data", "break_it.json"), encoding="utf-8"))["cases"]
    held += [(c["id"], c["q"], c["persona"], "break_it", c["expect_type"]) for c in bi]
    test = []
    for hid, q, per, src, expect in held:
        tool, args = rules_label(wb, q, per)
        test.append(route_rec(q, A.resolve_persona(per), tool, args, "test", src, "repo", extra=dict(ref_id=hid, expect=expect)))
    banned = {norm(r["question"]) for r in test}
    pe = os.path.join(OUT, "public_eval.jsonl")             # never train on (near-)copies of the eval-only public items either
    pub_eval_norm = [set(norm(json.loads(l)["question"]).split()) for l in open(pe, encoding="utf-8")] if os.path.exists(pe) else []

    hard_norm = []
    for item in HARD_TEST:
        hid, q, per, lab = item[:4]; hargs = item[4] if len(item) > 4 else {}
        tool, args = base_label(lab, hargs, q, per)
        g = wb.guards(q, per)
        if g and (tool, args.get("reason")) != ("refuse", g["intent"]):
            stats["hard_test_relabelled_by_guard"] += 1; tool, args = "refuse", {"reason": g["intent"]}
        test.append(route_rec(q, per, tool, args, "test", "hard_test", "hard", extra=dict(ref_id=hid)))
        banned.add(norm(q)); hard_norm.append(set(norm(q).split()))

    def label_for(q, label, args, persona):
        """Template label -> gold (tool, args), with the code authoritative: guards first, then the agent clarify rule."""
        tool, a2 = base_label(label, args, q, persona)
        g = wb.guards(q, persona)
        if g and (tool, a2.get("reason")) != ("refuse", g["intent"]): return "refuse", {"reason": g["intent"]}, "guard:" + g["intent"]
        if not g and tool in CLARIFY_TOOLS and persona != A.LEAST_PRIVILEGE and not a2.get("agent") and CV.needs_clarify(wb, q, tool):
            return "none", {"clarify": "agent"}, "clarify"
        return tool, a2, None

    # ---- template questions ----
    def gen(label, tpl, split, source, k, agent_pool, region_pool, out, personas=None, nvar=3, rng=rng):
        if isinstance(tpl, tuple): tpl, metric = tpl
        else: metric = None
        for _ in range(max(1, k // nvar)):
            q0, args = fill(tpl, rng, agent_pool, region_pool)
            if metric: args["metric"] = metric
            if norm(q0) in banned: stats["dropped_overlap_with_test"] += 1; continue
            persona = rng.choice(personas or PERSONAS)
            tool, a2, why = label_for(q0, label, args, persona)
            if why:
                stats["relabelled_by_guard" if why.startswith("guard") else "relabelled_clarify"] += 1
                relabelled.append(dict(q=q0, persona=persona, template=label, now=why))
            rt, ra = rules_label(wb, q0, persona)
            stats["rules_agree_clean" if (rt, ra) == (tool, a2) else "rules_disagree_clean"] += 1
            if (rt, ra) != (tool, a2) and len(disagree) < 400: disagree.append(dict(q=q0, persona=persona, label=[tool, a2], rules=[rt, ra]))
            for v, style in variants(q0, nvar, rng):
                if norm(v) in banned: continue
                t, a, _ = label_for(v, label, args, persona) if style != "clean" else (tool, a2, None)
                out.append(route_rec(v, persona, t, a, split, source, style))

    train_val = []
    for label, (tr, te) in T.items():
        reps = 11 if label.startswith("refuse:") or label == "none" else 10
        for tpl in tr:
            gen(label, tpl, "trainval", "template", reps, agent_train, REGION_REFS, train_val)
        for tpl in te:
            gen(label, tpl, "test", "heldout_template", 3, agent_train, REGION_REFS, test)
        if label in ("agent_health", "agent_value"):
            for tpl in tr[:4]:
                gen(label, tpl, "test", "new_alias", 3, agent_test, REGION_REFS, test)
    # v2 categories: indirect, multi-part, near-misses, clarify, balance (small_group / scope)
    CAT_REPS = dict(indirect=10, multipart=15, nearmiss_safe=15, nearmiss_risky=15, clarify=18, balance=9)
    LABEL_REPS = {"refuse:small_group": 10, "refuse:scope": 3}   # tuned so each lands near 80-100 train rows in total
    for cat, d in CATS.items():
        for label, (tr, te) in d.items():
            per = sorted(SCOPED) if label == "refuse:scope" else None
            for tpl in tr:
                gen(label, tpl, "trainval", cat, LABEL_REPS.get(label, CAT_REPS[cat]), agent_train, REGION_REFS, train_val, personas=per)
            for tpl in te:
                gen(label, tpl, "test", "heldout_" + cat, 3, agent_test, REGION_REFS, test, personas=per)
    # long / noisy: one governed question inside an email, greeting or emoji wrapper
    tool_labels = [l for l in T if l != "none"]
    for split, wrappers, n, which in (("trainval", WRAPPERS[0], 520, 0), ("test", WRAPPERS[1], 60, 1)):
        for _ in range(n):
            label = rng.choice(tool_labels); pool = T[label][which] or T[label][0]
            tpl = rng.choice(pool); metric = None
            if isinstance(tpl, tuple): tpl, metric = tpl
            q0, args = fill(tpl, rng, agent_train if which == 0 else agent_test, REGION_REFS)
            if metric: args["metric"] = metric
            q = rng.choice(wrappers).replace("{q}", q0 if rng.random() < 0.6 else casual(q0, rng))
            persona = rng.choice(PERSONAS)
            tool, a2, why = label_for(q, label, args, persona)
            if why: stats["long_noisy_relabelled"] += 1
            (train_val if split == "trainval" else test).append(route_rec(q, persona, tool, a2, split, "long_noisy" if which == 0 else "heldout_long_noisy", "noisy"))
    # mixed roles: the same clean question for guest / analyst (Region A) / manager / executive; outcome stored as meta
    os.environ["NP_BRAIN"] = "rules"
    for split, qs, nvar in (("trainval", MIXED_ROLE[0], 4), ("test", MIXED_ROLE[1], 1)):
        for q0 in qs:
            for persona in MIXED_PERSONAS:
                tool, args = rules_label(wb, q0, persona)
                assert tool != "none", q0
                lab = "refuse:" + args["reason"] if tool == "refuse" else tool
                r = wb.ask(q0, persona)
                meta = dict(outcome=r["type"], outcome_intent=r["intent"])
                for v, style in variants(q0, nvar, rng):
                    if norm(v) in banned: continue
                    t, a, _ = label_for(v, lab, args, persona) if style != "clean" else (tool, args, None)
                    (train_val if split == "trainval" else test).append(route_rec(v, persona, t, a, split, "mixed_role" if split == "trainval" else "heldout_mixed_role", style, extra=meta))
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

    # ---- dedupe: nothing in train/val may equal a test question (or be a near-copy of a hard-test one) ----
    test_keys = {norm(r["question"]) + "|" + str(r["previous"]) for r in test}
    seen, tv = set(), []
    for r in train_val:
        key = norm(r["question"]) + "|" + str(r["previous"])
        if key in test_keys or norm(r["question"]) in banned: stats["dropped_overlap_with_test"] += 1; continue
        w = set(norm(r["question"]).split())
        if any(len(w & h) / max(1, len(w | h)) >= 0.8 for h in hard_norm): stats["dropped_near_hard_test"] += 1; continue
        if key + r["persona"] in seen: continue
        seen.add(key + r["persona"]); tv.append(r)
    rng.shuffle(tv)
    n_val = 450
    val = [dict(r, split="val") for r in tv[:n_val]]; train = [dict(r, split="train") for r in tv[n_val:]]
    seen_t, test2 = set(), []
    for r in test:
        key = norm(r["question"]) + "|" + str(r["previous"]) + r["persona"]
        if key in seen_t and r["source"] not in ("golden", "probe_extra", "unscripted", "break_it", "hard_test"): continue
        seen_t.add(key); test2.append(r)
    test = test2

    # ---- ANSWER task: real Agent outputs per synthetic scenario ----
    def answer_rec(ag, sname, split, label, q, persona, a, style, full_ask=False):
        if full_ask:
            r = ag.ask(q, persona)                       # claim questions: governed answer incl. the claim-check sentence
        else:
            ag._ctx.args = a
            try: r = getattr(ag, label)(q, persona)
            finally: ag._ctx.args = None
        if r["type"] not in ("answer", "caveat"): return None
        r["rows"] = [list(x) for x in (r.get("rows") or [])]
        gold = FT.gold_answer(r)
        assert not FT.unfaithful_numbers(gold, r), (label, gold)
        if full_ask: assert "claim check" in gold.lower(), gold
        msgs = FT.answer_messages(q, persona, r) + [{"role": "assistant", "content": gold}]
        if r["type"] == "caveat" and style == "clean": style = "caveat"
        return dict(task="answer", split=split, source="scenario:" + sname, style=style, persona=persona, question=q, previous=None,
                    label=label, args=a, messages=msgs,
                    governed=dict(text=r["text"], rows=r["rows"], citations=r["citations"], data_as_of=r["data_as_of"], type=r["type"]))

    def answer_recs(split, scen_names, templates_idx, per_tool, n_claim, n_scoped):
        out, seen_a = [], set()
        def add(rec):
            if rec is None: return
            key = (rec["source"], norm(rec["question"]), rec["persona"])
            if key in seen_a: return
            seen_a.add(key); out.append(rec)
        for sname in scen_names:
            ag = load(sname)
            for label, (tr, te) in T.items():
                if label.startswith("refuse:") or label == "none": continue
                pool = tr if templates_idx == 0 else (te or tr)
                for _ in range(per_tool):
                    tpl = rng.choice(pool); metric = None
                    if isinstance(tpl, tuple): tpl, metric = tpl
                    q, args = fill(tpl, rng, agent_train if templates_idx == 0 else agent_test, REGION_REFS)
                    q, style = rng.choice(variants(q, 3, rng))
                    if metric: args["metric"] = metric
                    persona = rng.choice(["executive", "executive", "manager", "platform_engineer", "finance", "regional_lead", "analyst"])
                    if persona in SCOPED and (args.get("region", "Region A") != "Region A" or set(A._regions_in(q.lower())) - {"Region A"}): persona = "executive"
                    if ag.guards(q, persona) or A.claimed_numbers(q): continue      # claim questions: see the claim rows below
                    if CV.needs_clarify(ag, q, label): continue
                    a = {k: v for k, v in args.items() if k in FT.ARG_KEYS.get(label, set())}
                    add(answer_rec(ag, sname, split, label, q, persona, a, style))
            # empty / missing slice: a region this scenario has no data for -> governed caveat, the model must keep it
            for reg in ("Region D", "Region E"):
                if reg not in ag.regions():
                    q = rng.choice([f"What is utilisation in {reg}?", f"how is {reg} doing on adoption", f"{reg} utilisation please"])
                    add(answer_rec(ag, sname, split, "m01", q, "executive", {"region": reg}, "empty"))
            # region-scoped roles: the governed answer only covers Region A
            for _ in range(n_scoped):
                label = rng.choice(["m01", "region_compare", "team_usage", "funnel", "m02_regions", "reclaim"])
                if label not in T: continue
                q = rng.choice(T[label][templates_idx] or T[label][0])
                if isinstance(q, tuple) or "{" in q: continue
                persona = rng.choice(sorted(SCOPED))
                if ag.guards(q, persona): continue
                add(answer_rec(ag, sname, split, label, q, persona, {}, "scoped"))
            # claim-check rows (TRAINING ONLY for wording: at runtime claim questions always keep the template answer)
            for label, (tr, te) in CLAIMS.items():
                if label == "none": continue
                for q in (tr if templates_idx == 0 else (te or tr))[:n_claim]:
                    if ag.guards(q, "executive") or not A.claimed_numbers(q): continue
                    try: add(answer_rec(ag, sname, split, label, q, "executive", {}, "claim", full_ask=True))
                    except AssertionError: stats["claim_answer_skipped"] += 1
        return out
    ans_train = answer_recs("train", SCEN_SPLIT["train"], 0, 6, 3, 6)
    ans_val = answer_recs("val", SCEN_SPLIT["val"], 0, 3, 2, 3)
    ans_test = answer_recs("test", SCEN_SPLIT["test"], 1, 2, 2, 3)
    train += ans_train; val += ans_val; test += ans_test
    rng.shuffle(train)

    # ---- v3 weak-spot boost (after Colab run 1). Own RNG and appended LAST, so every row above (and so the whole run-1
    # test set) is byte-for-byte unchanged and run 1 vs run 2 stay comparable. New held-out rows are added to test. ----
    rng3 = random.Random(SEED + 3); add_tv, add_test = [], []
    V3_REPS = dict(boost=8, roles=8, clarify_v3=8, refusals_v3=8, adversarial=8, safe_scary=4)
    for cat, d in CATS_V3.items():
        for label, (tr_, te_) in d.items():
            per = sorted(SCOPED) if label == "refuse:scope" else None
            for tpl in tr_:      # 4 variants each, so casual+typo wording gets more rows
                gen(label, tpl, "trainval", cat, V3_REPS[cat], agent_v3, REGION_REFS, add_tv, personas=per, nvar=4, rng=rng3)
            for tpl in te_:
                gen(label, tpl, "test", "heldout_" + cat, 3, agent_test, REGION_REFS, add_test, personas=per, rng=rng3)
    for qs, pers in ((MIXED_ROLE_V3, MIXED_PERSONAS_V3), (MIXED_ROLE[0], [p for p in MIXED_PERSONAS_V3 if p not in MIXED_PERSONAS])):
        for q0 in qs:            # mixed roles with every role incl. regional lead / fraud ops lead / finance
            for persona in pers:
                tool, args = rules_label(wb, q0, persona)
                assert tool != "none", q0
                lab = "refuse:" + args["reason"] if tool == "refuse" else tool
                r = wb.ask(q0, persona); meta = dict(outcome=r["type"], outcome_intent=r["intent"])
                for v, style in variants(q0, 4, rng3):
                    t, a, _ = label_for(v, lab, args, persona) if style != "clean" else (tool, args, None)
                    add_tv.append(route_rec(v, persona, t, a, "trainval", "mixed_role_v3", style, extra=meta))
    test_keys = {norm(r["question"]) + "|" + str(r["previous"]) for r in test}
    seen = {norm(r["question"]) + "|" + str(r["previous"]) + r["persona"] for r in train + val}
    for r in add_test:
        k = norm(r["question"]) + "|" + str(r["previous"])
        if k + r["persona"] in seen or k in test_keys: continue
        test_keys.add(k); test.append(r)
    v3 = []
    for r in add_tv:
        key = norm(r["question"]) + "|" + str(r["previous"]); w = set(norm(r["question"]).split())
        if key in test_keys or norm(r["question"]) in banned: stats["v3_dropped_overlap_with_test"] += 1; continue
        if any(len(w & h) / max(1, len(w | h)) >= 0.8 for h in hard_norm + pub_eval_norm): stats["v3_dropped_near_hard_or_public_eval"] += 1; continue
        if key + r["persona"] in seen: continue
        seen.add(key + r["persona"]); v3.append(dict(r, split="train"))
    stats["v3_train_rows"] = len(v3)
    train = train + v3; rng3.shuffle(train)

    os.makedirs(OUT, exist_ok=True)
    for name, rows in (("train", train), ("val", val), ("test", test)):
        with open(os.path.join(OUT, name + ".jsonl"), "w", encoding="utf-8") as f:
            for i, r in enumerate(rows):
                r = {"id": f"{name}-{i:05d}", **r}
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    def summ(rows):
        return dict(total=len(rows), by_task=dict(Counter(r["task"] for r in rows)), by_source=dict(Counter(r["source"].split(":")[0] for r in rows)),
                    by_style=dict(Counter(r["style"] for r in rows if r["task"] == "route")),
                    by_label=dict(sorted(Counter(label_key(r) for r in rows if r["task"] == "route").items())),
                    answer_by_style=dict(Counter(r["style"] for r in rows if r["task"] == "answer")),
                    language={"en": len(rows)})
    st = dict(seed=SEED, language="English only (synthetic)", train=summ(train), val=summ(val), test=summ(test),
              notes=dict(stats), sizes_bytes={n: os.path.getsize(os.path.join(OUT, n + ".jsonl")) for n in ("train", "val", "test")},
              sample_rules_disagreements=disagree[:60], relabelled_by_guard=relabelled)
    json.dump(st, open(os.path.join(OUT, "stats.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: st[k] for k in ("train", "val", "test", "notes", "sizes_bytes")}, indent=1))


if __name__ == "__main__":
    main()
