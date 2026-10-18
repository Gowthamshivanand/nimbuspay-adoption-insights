"""Turn the cached public sample (finetune/fetch_public.py) into training / eval rows in OUR formats.
  python finetune/make_public.py     # needs finetune/.public_cache; writes data/public_train.jsonl, data/public_eval.jsonl
Run after make_dataset.py (it dedupes against data/test.jsonl and the hard test set, and caps 'none').
Option B: public questions are put under OUR fixed tool list and route prompt, never their own tool schemas:
  * When2Call, xlam-irrelevance, CLINC out-of-scope, Glaive v2, OR-Bench (safe but scary-sounding) -> "none";
  * deepset prompt-injections (label 1, English), Gandalf -> refuse:injection;  Aegis 2.0 unsafe PROMPTS -> refuse:harmful
    (refuse:pii for its PII/Privacy category). Responses from those sets are never used;
  * FeTaQA -> ANSWER task in our "governed draft + SQL rows" format; kept only if every number in the answer is in the rows;
  * smol-smoltalk -> short general chats (replay against forgetting), trained as-is.
The code guards stay authoritative: if a guard refuses a public question, its label is that guard's reason.
'none' is capped at ~25% of all routing rows (synthetic + public) by trimming the none-labelled public sources evenly."""
import json, os, random, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path[:0] = [ROOT, HERE]
from app import finetuned as FT
import make_dataset as MD
from fetch_public import SOURCES, CACHE, SEED
from hard_test_en import HARD_TEST
DATA = os.path.join(HERE, "data"); NONE_CAP = 0.25
NONE_SRC = ["when2call", "xlam_irrelevance", "clinc_oos", "glaive_fc_v2", "or_bench"]
REFUSE_SRC = {"deepset_injections": "injection", "gandalf": "injection", "aegis2": "harmful"}
ATTRIB = {
    "when2call": "When2Call, NVIDIA (Ross et al., 2025), CC-BY-4.0", "when2call_test": "When2Call test (mcq), NVIDIA, CC-BY-4.0",
    "xlam_irrelevance": "xlam-irrelevance-7.5k, MadeAgents / Hammer (Lin et al., 2024), CC-BY-4.0",
    "clinc_oos": "CLINC150 (Larson et al., 2019), CC-BY-3.0", "clinc_test": "CLINC150 test (Larson et al., 2019), CC-BY-3.0",
    "glaive_fc_v2": "glaive-function-calling-v2, Glaive AI, Apache-2.0", "deepset_injections": "prompt-injections, deepset, Apache-2.0",
    "gandalf": "gandalf_ignore_instructions, Lakera AI, MIT", "or_bench": "OR-Bench 80k (Cui et al., 2024), CC-BY-4.0",
    "aegis2": "Aegis AI Content Safety Dataset 2.0, NVIDIA (Ghosh et al., 2025), CC-BY-4.0 (prompts only)",
    "fetaqa": "FeTaQA (Nan et al., 2022), CC-BY-SA-4.0, tables from Wikipedia (CC-BY-SA)",
    "smol_smoltalk": "smol-smoltalk, Hugging Face (Allal et al., 2025), Apache-2.0", "xstest": "XSTest (Röttger et al., 2024), CC-BY-4.0",
}


def load(name):
    p = os.path.join(CACHE, name + ".jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else None


def fetaqa_rec(x):
    """FeTaQA example -> our ANSWER row. Rows = table title + header + highlighted rows; gold = human answer + Source."""
    tab = x["table_array"]; hl = sorted({r for r, _ in x["highlighted_cell_ids"]})
    rows = [["Table", x["table_page_title"], x["table_section_title"]], tab[0]] + [tab[i] for i in hl if 0 < i < len(tab)][:10]
    r = dict(intent="table_qa", type="answer", text="No governed draft: answer only from the SQL rows below.", rows=rows, citations=[], data_as_of="n/a")
    gold = x["answer"].strip() + f" Source: Wikipedia, {x['table_page_title']} ({x['table_section_title']})."
    if FT.unfaithful_numbers(gold, r) or len(FT._rows_txt(rows)) > 1200: return None
    msgs = FT.answer_messages(x["question"], "executive", r) + [{"role": "assistant", "content": gold}]
    return dict(task="answer", persona="executive", question=x["question"], previous=None, label="table_qa", args={}, messages=msgs,
                governed=dict(text=r["text"], rows=rows, citations=[], data_as_of="n/a", type="answer"), ref_id=f"feta-{x['feta_id']}")


def main():
    man = json.load(open(os.path.join(CACHE, "manifest.json"))) if os.path.exists(os.path.join(CACHE, "manifest.json")) else {}
    if not man: print("No public cache: run finetune/fetch_public.py first (needs internet). Nothing written."); return 1
    wb = MD.load("workbook"); rng = random.Random(SEED)
    test = [json.loads(l) for l in open(os.path.join(DATA, "test.jsonl"), encoding="utf-8")]
    train = [json.loads(l) for l in open(os.path.join(DATA, "train.jsonl"), encoding="utf-8")]
    banned = {MD.norm(r["question"]) for r in test} | {MD.norm(h[1]) for h in HARD_TEST}
    banned |= {MD.norm(r["question"]) for r in train}
    hard = [set(MD.norm(h[1]).split()) for h in HARD_TEST]
    personas = [p for p in MD.PERSONAS]
    stats = dict(skipped_sources=[n for n in SOURCES if n not in man], dropped_overlap=0, relabelled_by_guard=0)

    erng = random.Random(SEED + 1)     # eval-only rows get their own RNG, so they don't shift when the train mix grows

    def route_row(name, q, label, use):
        nq = MD.norm(q); w = set(nq.split())
        if not nq or nq in banned or any(len(w & h) / max(1, len(w | h)) >= 0.8 for h in hard): stats["dropped_overlap"] += 1; return None
        banned.add(nq)
        persona = (erng if use == "eval" else rng).choice(personas)
        tool, args, why = MD.base_label(label, {}, q, persona) + (None,)
        g = wb.guards(q, persona)
        if g and (tool, args.get("reason")) != ("refuse", g["intent"]):
            tool, args = "refuse", {"reason": g["intent"]}; stats["relabelled_by_guard"] += 1
        return dict(task="route", persona=persona, question=q, previous=None, label=tool, args=args,
                    messages=FT.route_messages(q, persona) + [{"role": "assistant", "content": FT.route_target(tool, args)}])

    out, evalrows = [], []
    def add(dst, name, rec, use):
        if rec: dst.append(dict(split=use, source="public:" + name, style="public", licence=man[name]["licence"], attribution=ATTRIB[name],
                                dataset=f"{man[name]['repo']}@{man[name]['revision'][:7]}", **rec))
    # refusals first (they don't count toward 'none')
    for name, reason in REFUSE_SRC.items():
        for x in load(name) or []:
            lab = "refuse:pii" if name == "aegis2" and re.search(r"PII|Privacy", x.get("categories") or "") else "refuse:" + reason
            add(out, name, route_row(name, x["q"], lab, "train"), "train")
    # 'none' sources, trimmed evenly so none <= NONE_CAP of all routing rows
    syn_route = [r for r in train if r["task"] == "route"]
    syn_none = sum(r["label"] == "none" for r in syn_route)
    pub_ref = sum(1 for r in out if r["task"] == "route")
    pub_none_ref = sum(1 for r in out if r["label"] == "none")       # guard-free none from refusal sets (should be 0)
    avail = {n: load(n) or [] for n in NONE_SRC}
    total_avail = sum(len(v) for v in avail.values())
    n_max = int((NONE_CAP * (len(syn_route) + pub_ref) - syn_none - pub_none_ref) / (1 - NONE_CAP))
    frac = max(0.0, min(1.0, n_max / max(1, total_avail)))
    stats["none_cap"] = dict(cap=NONE_CAP, synthetic_none=syn_none, public_none_requested=total_avail, public_none_allowed=n_max, kept_fraction=round(frac, 3))
    for name in NONE_SRC:
        for x in avail[name][:int(len(avail[name]) * frac)]:
            add(out, name, route_row(name, x["q"], "none", "train"), "train")
    for x in load("fetaqa") or []:
        add(out, "fetaqa", fetaqa_rec(x), "train")
    for x in load("smol_smoltalk") or []:
        add(out, "smol_smoltalk", dict(task="chat", persona=None, question=x["messages"][0]["content"], previous=None, label="chat", args={},
                                       messages=x["messages"]), "train")
    # eval-only file (never trained on)
    for x in load("xstest") or []:
        lab = "none" if x["label"] == "safe" else ("refuse:pii" if "privacy" in x["type"] else "refuse:harmful")
        add(evalrows, "xstest", route_row("xstest", x["q"], lab, "eval"), "eval")
    for name in ("when2call_test", "clinc_test"):
        for x in load(name) or []:
            add(evalrows, name, route_row(name, x["q"], "none", "eval"), "eval")
    rng.shuffle(out)
    for fname, rows, pre in (("public_train.jsonl", out, "pub"), ("public_eval.jsonl", evalrows, "pubeval")):
        with open(os.path.join(DATA, fname), "w", encoding="utf-8") as f:
            for i, r in enumerate(rows): f.write(json.dumps({"id": f"{pre}-{i:05d}", **r}, ensure_ascii=False) + "\n")
    from collections import Counter
    lab = lambda r: MD.label_key(r) if r["task"] == "route" else r["task"]
    allroute = syn_route + [r for r in out if r["task"] == "route"]
    stats.update(train=dict(total=len(out), by_source=dict(Counter(r["source"].split(":")[1] for r in out)), by_task=dict(Counter(r["task"] for r in out)),
                            by_label=dict(Counter(lab(r) for r in out))),
                 eval=dict(total=len(evalrows), by_source=dict(Counter(r["source"].split(":")[1] for r in evalrows)), by_label=dict(Counter(lab(r) for r in evalrows))),
                 none_share_of_routing=round(sum(r["label"] == "none" for r in allroute) / len(allroute), 3),
                 sources={n: dict(m, attribution=ATTRIB.get(n)) for n, m in man.items()},
                 licence_of_public_train="CC-BY-SA-4.0 (combined file inherits ShareAlike from FeTaQA); each row keeps its own licence + attribution",
                 sizes_bytes={f: os.path.getsize(os.path.join(DATA, f)) for f in ("public_train.jsonl", "public_eval.jsonl")})
    sp = os.path.join(DATA, "stats.json"); st = json.load(open(sp)); st["public"] = stats; json.dump(st, open(sp, "w"), indent=1)
    print(json.dumps({k: stats[k] for k in ("train", "eval", "none_cap", "none_share_of_routing", "dropped_overlap", "relabelled_by_guard", "skipped_sources", "sizes_bytes")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
