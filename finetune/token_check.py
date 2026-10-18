"""Token-length check for the fine-tune files (needs transformers + the Qwen2.5 tokenizer; not part of CI).
  python finetune/token_check.py [model]     # default Qwen/Qwen2.5-1.5B-Instruct; writes stats.json["tokens"]
Renders each row with the same chat template the notebook uses and reports max / p99 / mean against MAX_LEN 768."""
import json, os, sys
from transformers import AutoTokenizer
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data"); MAX_LEN = 768


def main():
    tok = AutoTokenizer.from_pretrained(sys.argv[1] if len(sys.argv) > 1 else "Qwen/Qwen2.5-1.5B-Instruct")
    out = {}
    for name in ("train", "val", "test", "public_train", "public_eval"):
        p = os.path.join(DATA, name + ".jsonl")
        if not os.path.exists(p): continue
        lens, total, longest = [], 0, None
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            n = len(tok(tok.apply_chat_template(r["messages"], tokenize=False), add_special_tokens=False)["input_ids"])
            lens.append(n); total += n
            if longest is None or n > longest[0]: longest = (n, r["id"], r["task"], r["source"])
        lens.sort()
        out[name] = dict(rows=len(lens), max=lens[-1], p99=lens[int(0.99 * (len(lens) - 1))], mean=round(total / len(lens), 1),
                         total_tokens=total, over_max_len=sum(x > MAX_LEN for x in lens), longest=dict(tokens=longest[0], id=longest[1], task=longest[2], source=longest[3]))
    sp = os.path.join(DATA, "stats.json"); st = json.load(open(sp)); st["tokens"] = dict(tokenizer=tok.name_or_path, max_len=MAX_LEN, **out)
    json.dump(st, open(sp, "w"), indent=1); print(json.dumps(st["tokens"], indent=1))
    return 1 if any(v["over_max_len"] for v in out.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
