"""Build a minimal, text-only folder for a Hugging Face Docker Space: dist/hf-space/.
Hugging Face rejects git pushes that contain binary files (PNG, MP4, ZIP...) anywhere in history unless they use LFS/Xet,
and this repo's history has screenshots and a video. The Space only needs the app, so ship just that.
  python tools/make_space.py            # writes dist/hf-space/ and checks it (no binaries, no secrets, port 7860)
Then upload it yourself (see docs/DEPLOY_HF_SPACES.md). Nothing here talks to the network or reads a token."""
import os, re, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dist", "hf-space")
REPO_URL = "https://github.com/Gowthamshivanand/nimbuspay-adoption-insights"
SECRET = re.compile(r"(hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
SKIP_DIRS = {"__pycache__", "var"}
DOCKER_EXTRA = ("src/data.json", "tools", "tests/data/probes.json")   # must match the Dockerfile COPY lines


def front_matter():
    s = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    m = re.match(r"^---\n.*?\n---\n", s, re.S)
    if not m: sys.exit("README.md has no Hugging Face front-matter block")
    fm = m.group(0)
    for need in ("sdk: docker", "app_port: 7860"):
        if need not in fm: sys.exit(f"front-matter lacks '{need}'")
    return fm


def build():
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT)
    for f in ("Dockerfile", ".dockerignore", "requirements.txt", "LICENSE"):
        shutil.copy2(os.path.join(ROOT, f), OUT)
    shutil.copytree(os.path.join(ROOT, "app"), os.path.join(OUT, "app"), ignore=lambda d, names: [n for n in names if n in SKIP_DIRS or n.endswith((".pyc", ".db"))])
    ign = lambda d, names: [n for n in names if n in SKIP_DIRS or n.endswith((".pyc", ".db"))]
    for f in DOCKER_EXTRA:                          # the Dockerfile COPYs these too (lineage + Models rules eval)
        src, dst = os.path.join(ROOT, f), os.path.join(OUT, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(src, dst, ignore=ign) if os.path.isdir(src) else shutil.copy2(src, dst)
    readme = front_matter() + f"""
# NimbusPay Adoption Insights (live demo)

> **Hobby case study, synthetic data only.** Built for a campus case-study competition (HashedIn by Deloitte Campus PM Hiring 2026, "The Adoption Mirage"). "NimbusPay" is the fictional company from the case brief. Not affiliated with any real company, and it holds no real company or personal data.

A read-only Adoption Insights Agent over governed metrics. Code guards run first, every number comes from SQL, every answer cites its metric ID, version and data-as-of, and unsafe asks are refused with a safe alternative. This Space runs the **rules brain** on free CPU (no model, no API key).

Source, tests and docs: {REPO_URL}
Author: Gowtham S · Licence: MIT
"""
    open(os.path.join(OUT, "README.md"), "w", encoding="utf-8").write(readme)


def check():
    problems = []
    for d, _, files in os.walk(OUT):
        for f in files:
            p = os.path.join(d, f); b = open(p, "rb").read()
            rel = os.path.relpath(p, OUT)
            if b"\x00" in b: problems.append(f"binary file: {rel}")
            if len(b) > 10 * 1024 * 1024: problems.append(f"over 10 MB: {rel}")
            if SECRET.search(b.decode("utf-8", "ignore")): problems.append(f"looks like a secret: {rel}")
            if f == ".env" or f.endswith(".gguf"): problems.append(f"must not ship: {rel}")
    df = open(os.path.join(OUT, "Dockerfile")).read()
    if "PORT=7860" not in df or "EXPOSE 7860" not in df: problems.append("Dockerfile does not listen on 7860")
    if "NP_BRAIN=rules" not in df: problems.append("Dockerfile does not default to the rules brain")
    return problems


if __name__ == "__main__":
    build(); probs = check()
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    if probs:
        print("\n".join(probs)); sys.exit(1)
    print(f"OK: {os.path.relpath(OUT, ROOT)} ({n} files, text only, no secrets, port 7860, rules brain)")
