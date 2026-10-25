"""Thumbs up / down on agent answers. Stored locally as JSONL under data/feedback/ (gitignored), never sent anywhere.
No user identity is stored: only the question, the answer, which brain answered, the role label and a timestamp.
Nothing here trains a model: tools/export_feedback.py turns HUMAN-REVIEWED misses into a candidate file for the
fine-tune dataset, and a person decides whether to merge it."""
import datetime as dt, json, os, threading, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCK = threading.Lock()
RATINGS = ("up", "down")


def path():
    return os.environ.get("NP_FEEDBACK", os.path.join(ROOT, "data", "feedback", "feedback.jsonl"))


def record(question, answer, rating, brain="", mode="", intent="", type_="", persona="", dataset="", comment=""):
    if rating not in RATINGS: raise ValueError("rating must be 'up' or 'down'")
    if not str(question).strip(): raise ValueError("question is required")
    row = dict(id=uuid.uuid4().hex[:12], ts=dt.datetime.now().astimezone().isoformat(timespec="seconds"), rating=rating,
               question=str(question)[:500], answer=str(answer)[:2000], brain=str(brain)[:40], mode=str(mode)[:80],
               intent=str(intent)[:40], type=str(type_)[:20], persona=str(persona)[:40], dataset=str(dataset)[:40],
               comment=str(comment or "")[:500], reviewed=False)
    p = path(); os.makedirs(os.path.dirname(p), exist_ok=True)
    with _LOCK, open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load(p=None):
    p = p or path()
    if not os.path.exists(p): return []
    out = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except ValueError: continue                       # a corrupt line never breaks the app
    return out


def summary():
    rows = load()
    return dict(total=len(rows), up=sum(r["rating"] == "up" for r in rows), down=sum(r["rating"] == "down" for r in rows),
                recent=list(reversed(rows[-10:])), path=os.path.relpath(path(), ROOT))
