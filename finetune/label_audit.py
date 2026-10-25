"""Label audit: run every route row (train, val, test, public_train) through the app's code guards, clarify rule and rules engine.
  python finetune/label_audit.py        # writes finetune/data/label_audit.json, exit 1 if a hard contradiction is left in train/val
Hard contradictions (must be 0 in train/val; make_dataset fixes them, the code is the authority):
  guard_conflict    a code guard refuses the question but the gold label is something else
  clarify_conflict  gold is an agent tool with no agent while conversation.needs_clarify would ask "which agent?"
  scope_conflict    a region-scoped role (analyst / regional lead / fraud ops lead) is given another region's data
  target_mismatch   the assistant target is not exactly route_target(label, args) or does not parse
Informational (reviewed, not errors):
  rules_confident_disagree  the rules router is confident (>= 0.86) and picks another tool: where the model must beat the rules
  model_only_refusal        gold refusal with no guard hit (the model must learn it; gaming / harmful are always model-only)"""
import json, os, re, sys
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path[:0] = [ROOT, HERE]
os.environ.setdefault("NP_BRAIN", "rules")
from app import agent as A, finetuned as FT, conversation as CV
import make_dataset as MD
import ft_eval as E


def audit(files=("train", "val", "test", "public_train")):
    wb = MD.load("workbook"); out = {}; examples = defaultdict(list)
    for name in files:
        p = os.path.join(HERE, "data", name + ".jsonl")
        if not os.path.exists(p): continue
        c = Counter()
        for l in open(p, encoding="utf-8"):
            r = json.loads(l)
            if r["task"] != "route": continue
            c["route_rows"] += 1
            q, per = r["question"], A.resolve_persona(r["persona"]); lab, args = r["label"], r["args"]
            def hit(kind, **kw):
                c[kind] += 1
                if len(examples[name + ":" + kind]) < 15: examples[name + ":" + kind].append(dict(id=r["id"], q=q[:160], persona=per, gold=MD.label_key(r), source=r["source"], **kw))
            if r["messages"][-1]["content"] != FT.route_target(lab, args) or FT.parse_route(r["messages"][-1]["content"], E.AGENTS, E.REGIONS) is None:
                hit("target_mismatch")
            g = wb.guards(q, per)
            if g and (lab, args.get("reason")) != ("refuse", g["intent"]): hit("guard_conflict", guard=g["intent"])
            if not g and lab in MD.CLARIFY_TOOLS and not args.get("agent") and per != A.LEAST_PRIVILEGE and not r.get("previous"):
                qs = re.sub(r"<[^<>]{0,300}>", " ", q).strip() or q
                if CV.needs_clarify(wb, qs, lab): hit("clarify_conflict")
            if per in MD.SCOPED and args.get("region") not in (None, "Region A"): hit("scope_conflict")
            if lab == "refuse" and not g and args.get("reason") in ("write", "pii", "individual", "small_group", "scope", "forecast", "causal", "ungoverned", "injection"):
                c["model_only_refusal:" + args["reason"]] += 1
            if lab not in ("refuse", "none") and not g and not r.get("previous"):
                fn, conf = CV.route_scored(wb, re.sub(r"<[^<>]{0,300}>", " ", q).strip() or q)
                if fn and conf >= 0.86 and fn != lab: hit("rules_confident_disagree", rules=fn, conf=round(conf, 2))
        out[name] = dict(sorted(c.items()))
    return out, dict(examples)


def main():
    res, ex = audit()
    hard = {f: {k: v for k, v in c.items() if k in ("guard_conflict", "clarify_conflict", "scope_conflict", "target_mismatch")} for f, c in res.items()}
    json.dump(dict(counts=res, hard_contradictions=hard, examples=ex), open(os.path.join(HERE, "data", "label_audit.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps(dict(counts=res), indent=1))
    bad = sum(v for f in ("train", "val") for v in hard.get(f, {}).values())
    print("HARD CONTRADICTIONS in train/val:", bad); return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
