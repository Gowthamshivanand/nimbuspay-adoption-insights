"""Human review of thumbs-down answers -> candidate rows for the fine-tune dataset. NOTHING is trained automatically.
  python tools/export_feedback.py list                        # thumbs-down items not yet reviewed
  python tools/export_feedback.py review <id> --tool m01 [--args '{"region": "Region B"}'] [--note "..."]
  python tools/export_feedback.py review <id> --refuse pii    # the right behaviour was a refusal
  python tools/export_feedback.py review <id> --reject        # not a real miss; never exported
  python tools/export_feedback.py export [--out data/feedback/finetune_candidates.jsonl]
Reviews go to data/feedback/reviews.jsonl (gitignored). Export writes ONLY reviewed, accepted misses, in the router's
target shape {"question", "tool", "args"}, each tagged source=feedback and needs_merge_review=true."""
import argparse, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from app import feedback as FB, agent as A


def reviews_path():
    return os.path.join(os.path.dirname(FB.path()), "reviews.jsonl")


def load_reviews():
    return {r["id"]: r for r in FB.load(reviews_path())}


def main(argv=None):
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    rv = sub.add_parser("review"); rv.add_argument("id"); g = rv.add_mutually_exclusive_group(required=True)
    g.add_argument("--tool"); g.add_argument("--refuse"); g.add_argument("--reject", action="store_true")
    rv.add_argument("--args", default="{}"); rv.add_argument("--note", default=""); rv.add_argument("--reviewer", default="human")
    ex = sub.add_parser("export"); ex.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    items = {r["id"]: r for r in FB.load()}; done = load_reviews()
    if a.cmd == "list":
        todo = [r for r in items.values() if r["rating"] == "down" and r["id"] not in done]
        for r in todo: print(f"{r['id']}  [{r['brain']}/{r['intent']}/{r['type']}]  {r['question']}\n    -> {r['answer'][:160]}")
        print(f"{len(todo)} thumbs-down item(s) to review"); return 0
    if a.cmd == "review":
        if a.id not in items: print("unknown id", file=sys.stderr); return 2
        if a.tool and a.tool not in A.INTENT_HELP: print(f"unknown tool {a.tool}; use one of: {', '.join(A.INTENT_HELP)}", file=sys.stderr); return 2
        args = json.loads(a.args)
        row = dict(id=a.id, accepted=not a.reject, tool=a.tool or ("refuse" if a.refuse else None),
                   args=(dict(reason=a.refuse) if a.refuse else args), note=a.note, reviewer=a.reviewer)
        os.makedirs(os.path.dirname(reviews_path()), exist_ok=True)
        with open(reviews_path(), "a", encoding="utf-8") as f: f.write(json.dumps(row) + "\n")
        print("reviewed", a.id, "accepted" if row["accepted"] else "rejected"); return 0
    out = a.out or os.path.join(os.path.dirname(FB.path()), "finetune_candidates.jsonl")
    rows = [dict(question=items[i]["question"], tool=r["tool"], args=r["args"], source="feedback", feedback_id=i,
                 was=dict(brain=items[i]["brain"], intent=items[i]["intent"], type=items[i]["type"]), note=r["note"],
                 reviewer=r["reviewer"], needs_merge_review=True)
            for i, r in done.items() if r["accepted"] and i in items]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} reviewed candidate(s) to {out}. Merge into finetune data by hand after review; nothing was trained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
