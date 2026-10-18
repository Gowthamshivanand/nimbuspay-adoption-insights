"""Fetch the small public-data sample used by the fine-tune mix (see finetune/data/README.md for licences).
  python finetune/fetch_public.py            # -> finetune/.public_cache/<source>.jsonl + manifest.json (gitignored)
  python finetune/make_public.py             # -> finetune/data/public_train.jsonl + public_eval.jsonl (committed, attributed)
* Every file is read from a PINNED dataset revision (resolve/<sha>/...), anonymously: no login, no token.
* Only the rows we need are kept: line-based files are streamed and the download stops after a fixed scan window;
  parquet files are read by HTTP range requests, row group by row group (needs pyarrow; skipped with a message if absent);
  small JSON/CSV files are read whole. The cache keeps only the sampled rows, never the raw file.
* Sampling is deterministic (seeded per source). A source that can't be reached is skipped with a clear message."""
import csv, io, json, os, random, re, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, ".public_cache")
SEED = 20261018
HF = "https://huggingface.co/datasets/{repo}/resolve/{sha}/{path}"

# name: repo, pinned revision, file, reader, keep (rows to sample), scan window, licence, use
SOURCES = {
    "when2call":        ("nvidia/When2Call", "0582f7749df63a96fdc3070932e83e72396ace53", "train/when2call_train_sft.jsonl", "jsonl", 600, 6000, "CC-BY-4.0", "train"),
    "when2call_test":   ("nvidia/When2Call", "0582f7749df63a96fdc3070932e83e72396ace53", "test/when2call_test_mcq.jsonl", "jsonl", 100, 1500, "CC-BY-4.0", "eval"),
    "xlam_irrelevance": ("MadeAgents/xlam-irrelevance-7.5k", "34323bf09efc7e4a394998a0fa91ff997617c369", "xlam-7.5k-irrelevancek.json", "json", 400, None, "CC-BY-4.0", "train"),
    "clinc_oos":        ("clinc/clinc_oos", "155b9c710419136e17307b80d0a13e68cd46b4ec", "plus/train-00000-of-00001.parquet", "parquet", 300, None, "CC-BY-3.0", "train"),
    "clinc_test":       ("clinc/clinc_oos", "155b9c710419136e17307b80d0a13e68cd46b4ec", "plus/test-00000-of-00001.parquet", "parquet", 150, None, "CC-BY-3.0", "eval"),
    "glaive_fc_v2":     ("glaiveai/glaive-function-calling-v2", "e7f4b6456019f5d8bcb991ef0dd67d8ff23221ac", "glaive-function-calling-v2.json", "json_stream", 300, 4000, "Apache-2.0", "train"),
    "deepset_injections": ("deepset/prompt-injections", "4f61ecb038e9c3fb77e21034b22511b523772cdd", "data/train-00000-of-00001-9564e8b05b4757ab.parquet", "parquet", 150, None, "Apache-2.0", "train"),
    "gandalf":          ("Lakera/gandalf_ignore_instructions", "04737b65e90a6794ec227012e4a255a7def6344b", "data/train-00000-of-00001-ded53be747ff55cd.parquet", "parquet", 200, None, "MIT", "train"),
    "or_bench":         ("bench-llm/or-bench", "e36d8b80e81837c8a8f264bbb2a49f1b32c7e272", "or-bench-80k.csv", "csv_stream", 150, 6000, "CC-BY-4.0", "train"),
    "aegis2":           ("nvidia/Aegis-AI-Content-Safety-Dataset-2.0", "d86bb8bedff51d25ac834ab7838f1cc61acb7a2c", "train.json", "json", 150, None, "CC-BY-4.0", "train"),
    "fetaqa":           ("DongfuJiang/FeTaQA", "75dbfcbb12ae1b608d1c564f177054c3885487c9", "fetaQA-v1_train.jsonl", "jsonl", 400, 3000, "CC-BY-SA-4.0", "train"),
    "smol_smoltalk":    ("HuggingFaceTB/smol-smoltalk", "f73fe857d519ff6ac5af2ea67c4d3834da7b8bcc", "data/train-00000-of-00004.parquet", "parquet", 600, 6000, "Apache-2.0", "train"),
    "xstest":           ("Paul/XSTest", "f600c994b256f12867dfa5b3eb3d545a3e62f8b5", "xstest_prompts.csv", "csv", 100, None, "CC-BY-4.0", "eval"),
}
EN_STOP = set("the a an and or to of in is are was what how why can could would you your i my me we our it this that for on with do does please".split())
DE_STOP = set("der die das und ist nicht ich du wie was ein eine mit für auf sie wir zu den von".split())


def english(text):
    """Cheap English check (no extra dependency): ASCII-ish, has English function words, few German ones."""
    t = str(text or "")
    if not t.strip() or sum(ord(c) > 127 for c in t) > 0.05 * len(t): return False
    w = re.findall(r"[a-zäöüß]+", t.lower())
    return bool(w) and sum(x in EN_STOP for x in w) >= max(1, 0.08 * len(w)) and sum(x in DE_STOP for x in w) <= 0.03 * len(w)


def _open(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "nimbuspay-finetune/1.0", **(headers or {})})
    return urllib.request.urlopen(req, timeout=60)


class RangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, so pyarrow fetches only the footer and the row groups we read."""
    def __init__(self, url):
        self.url, self.pos = url, 0
        with _open(url, {"Range": "bytes=0-0"}) as r: self.size = int(r.headers["Content-Range"].split("/")[-1])
        self.fetched = 0
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off); return self.pos
    def read(self, n=-1):
        if n is None or n < 0: n = self.size - self.pos
        if n == 0 or self.pos >= self.size: return b""
        end = min(self.size, self.pos + n) - 1
        with _open(self.url, {"Range": f"bytes={self.pos}-{end}"}) as r: data = r.read()
        self.pos += len(data); self.fetched += len(data); return data
    def readinto(self, b):
        d = self.read(len(b)); b[:len(d)] = d; return len(d)


def read_rows(kind, url, scan):
    """Yield raw records; for streamed kinds stop after `scan` records (fixed window, so the sample is deterministic)."""
    if kind == "jsonl":
        with _open(url) as r:
            for i, line in enumerate(r):
                if scan and i >= scan: break
                if line.strip(): yield json.loads(line)
    elif kind == "json":
        with _open(url) as r: yield from json.load(r)
    elif kind == "json_stream":                          # a big JSON array: decode records one by one, stop early
        dec, buf, n = json.JSONDecoder(), "", 0
        with _open(url) as r:
            buf = r.read(1 << 16).decode("utf-8").lstrip().lstrip("[")
            while n < scan:
                buf = buf.lstrip().lstrip(",").lstrip()
                try: obj, end = dec.raw_decode(buf)
                except json.JSONDecodeError:
                    more = r.read(1 << 16)
                    if not more: break
                    buf += more.decode("utf-8", errors="ignore"); continue
                yield obj; n += 1; buf = buf[end:]
    elif kind in ("csv", "csv_stream"):
        with _open(url) as r:
            for i, row in enumerate(csv.DictReader(io.TextIOWrapper(r, encoding="utf-8"))):
                if scan and i >= scan: break
                yield row
    elif kind == "parquet":
        import pyarrow.parquet as pq                     # ImportError -> caller skips this source with a message
        f = RangeFile(url); pf = pq.ParquetFile(f)
        names = None
        meta = pf.schema_arrow.metadata or {}
        if b"huggingface" in meta:                       # class-label names (e.g. CLINC intents)
            feats = json.loads(meta[b"huggingface"]).get("info", {}).get("features", {})
            for k, v in feats.items():
                if isinstance(v, dict) and v.get("names"): names = (k, v["names"])
        n = 0
        for g in range(pf.num_row_groups):
            for rec in pf.read_row_group(g).to_pylist():
                if names: rec[names[0] + "_name"] = names[1][rec[names[0]]]
                yield rec; n += 1
            if scan and n >= scan: break
        print(f"    (parquet: fetched {f.fetched / 1e6:.1f} MB of {f.size / 1e6:.1f} MB by range requests)")


def keep(name, rec):
    """Per-source filter: English, short, and the slice we need. Returns a small normalised dict or None."""
    if name == "when2call":
        u = next((m["content"] for m in rec.get("messages", []) if m.get("role") == "user"), None)
        return dict(q=u) if u and english(u) and len(u) < 600 else None
    if name == "when2call_test":
        return dict(q=rec["question"], correct_answer=rec["correct_answer"]) if english(rec.get("question")) and len(rec["question"]) < 600 else None
    if name == "xlam_irrelevance":
        return dict(q=rec["query"]) if english(rec.get("query")) and len(rec["query"]) < 600 else None
    if name in ("clinc_oos", "clinc_test"):
        return dict(q=rec["text"], intent=rec.get("intent_name", rec.get("intent"))) if english(rec.get("text")) else None
    if name == "glaive_fc_v2":
        m = re.search(r"USER:\s*(.+?)(?:\n|$)", rec.get("chat", ""))
        return dict(q=m.group(1).strip()) if m and english(m.group(1)) and len(m.group(1)) < 600 else None
    if name == "deepset_injections":
        return dict(q=rec["text"]) if rec.get("label") == 1 and english(rec.get("text")) and len(rec["text"]) < 1200 else None
    if name == "gandalf":
        return dict(q=rec["text"]) if english(rec.get("text")) and len(rec["text"]) < 1200 else None
    if name == "or_bench":
        return dict(q=rec["prompt"], category=rec.get("category")) if english(rec.get("prompt")) and len(rec["prompt"]) < 600 else None
    if name == "aegis2":
        p = rec.get("prompt") or ""
        if rec.get("prompt_label") != "unsafe" or p == "REDACTED" or not english(p) or len(p) > 1200: return None
        return dict(q=p, categories=rec.get("violated_categories"))
    if name == "fetaqa":
        return {k: rec[k] for k in ("feta_id", "page_wikipedia_url", "table_page_title", "table_section_title", "table_array", "highlighted_cell_ids", "question", "answer")}
    if name == "smol_smoltalk":
        msgs = rec.get("messages") or []
        txt = " ".join(m["content"] for m in msgs)
        if not (2 <= len(msgs) <= 4) or len(txt) > 1800 or not english(txt) or msgs[-1]["role"] != "assistant": return None
        return dict(messages=[dict(role=m["role"], content=m["content"]) for m in msgs], source=rec.get("source"))
    if name == "xstest":
        return dict(q=rec["prompt"], label=rec["label"], type=rec["type"]) if rec.get("prompt") else None
    return None


def sample(name, rows, k, rng):
    if name == "xstest":                                 # half safe, half unsafe contrast prompts
        safe = [r for r in rows if r["label"] == "safe"]; unsafe = [r for r in rows if r["label"] != "safe"]
        return rng.sample(safe, min(k // 2, len(safe))) + rng.sample(unsafe, min(k - k // 2, len(unsafe)))
    if name == "clinc_oos":
        rows = [r for r in rows if r["intent"] == "oos"]
    if name == "clinc_test":                             # 100 out-of-scope + 50 in-scope (all are 'none' for our tool list)
        oos = [r for r in rows if r["intent"] == "oos"]; ins = [r for r in rows if r["intent"] != "oos"]
        return rng.sample(oos, min(100, len(oos))) + rng.sample(ins, min(50, len(ins)))
    return rng.sample(rows, min(k, len(rows)))


def main(only=None):
    os.makedirs(CACHE, exist_ok=True)
    mpath = os.path.join(CACHE, "manifest.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    for name, (repo, sha, path, kind, k, scan, lic, use) in SOURCES.items():
        if only and name not in only: continue
        url = HF.format(repo=repo, sha=sha, path=path)
        print(f"- {name}: {repo}@{sha[:7]} {path}")
        rng = random.Random(f"{SEED}:{name}")
        try:
            rows, seen = [], set()
            for rec in read_rows(kind, url, scan):
                x = keep(name, rec)
                if not x: continue
                key = json.dumps(x.get("q") or x.get("question") or x.get("messages"), sort_keys=True)
                if key in seen: continue
                seen.add(key); rows.append(x)
            picked = sample(name, rows, k, rng)
        except ImportError as e:
            print(f"  SKIPPED {name}: {e}. Install pyarrow (pip install pyarrow) to read parquet sources."); continue
        except Exception as e:                           # network, 404, gated, format drift: skip, never fail the whole run
            print(f"  SKIPPED {name}: could not fetch/parse ({type(e).__name__}: {e})."); continue
        with open(os.path.join(CACHE, name + ".jsonl"), "w", encoding="utf-8") as f:
            for r in picked: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        manifest[name] = dict(repo=repo, revision=sha, file=path, licence=lic, use=use, eligible=len(rows), kept=len(picked), url=f"https://huggingface.co/datasets/{repo}")
        print(f"  kept {len(picked)} of {len(rows)} eligible")
    json.dump(manifest, open(mpath, "w"), indent=1)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
