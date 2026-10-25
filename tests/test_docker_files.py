"""Docker image completeness (static: no Docker needed). The image used to copy only app/, so in Docker /api/lineage returned 500
('Explain this number' did nothing) and the Models tab showed the rules engine as 'not available'. The app also reads
src/data.json, tools/ (rules eval) and tests/data/probes.json; this fails if any of them drops out of the image again."""
import fnmatch, os, re, shutil, subprocess, sys, tempfile
from conftest import ROOT
sys.path.insert(0, os.path.join(ROOT, "tools"))

NEEDED = ("src/data.json", "tools", "tests/data/probes.json")


def _copies():
    d = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    return [m.group(1) for m in re.finditer(r"^COPY\s+(?:--\S+\s+)*(\S+)\s+\S+\s*$", d, re.M)]


def _ignored(path):
    """Docker .dockerignore semantics for our simple patterns: last match wins, '!' re-includes, a dir pattern covers its children."""
    pats = [l.strip() for l in open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8") if l.strip() and not l.startswith("#")]
    out = False
    for p in pats:
        neg = p.startswith("!"); p = p.lstrip("!")
        if fnmatch.fnmatch(path, p) or path.startswith(p.rstrip("/") + "/"): out = not neg
    return out


def test_dockerfile_copies_every_file_the_app_reads():
    c = _copies()
    for f in NEEDED + ("app",):
        assert f in c, f"Dockerfile must COPY {f}"


def test_dockerignore_does_not_exclude_the_copied_files():
    for f in NEEDED:
        probe = f if not os.path.isdir(os.path.join(ROOT, f)) else f + "/eval_agent.py"
        assert not _ignored(probe), f".dockerignore excludes {probe}"
    assert _ignored("docs/demo.mp4") and _ignored("tests/test_api.py") and _ignored("src/app.js")   # still lean


def test_make_space_ships_the_same_extra_files():
    import make_space as M
    assert tuple(M.DOCKER_EXTRA) == NEEDED


def test_image_layout_explains_numbers_and_runs_the_rules_eval():
    """Rebuild the image's /srv layout (app + the COPY extras only) and check lineage and the Models rules eval work there."""
    srv = os.path.join(tempfile.mkdtemp(prefix="np-img-"), "srv")
    shutil.copytree(os.path.join(ROOT, "app"), os.path.join(srv, "app"), ignore=shutil.ignore_patterns("var", "__pycache__"))
    for f in NEEDED:
        s, d = os.path.join(ROOT, f), os.path.join(srv, f); os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__")) if os.path.isdir(s) else shutil.copy2(s, d)
    env = dict(os.environ, NP_BRAIN="rules", AUDIT_DB=os.path.join(srv, "audit.db"), FT_WARMUP="0", PYTHONPATH=srv)
    code = "from fastapi.testclient import TestClient; from app.server import app; c=TestClient(app); r=c.get('/api/lineage/M01'); print(r.status_code, r.json()['name'])"
    r = subprocess.run([sys.executable, "-c", code], cwd=srv, env=env, capture_output=True, text=True, timeout=120)
    assert "\n200 " in "\n" + r.stdout, r.stdout + r.stderr
    out = os.path.join(srv, "eval_rules.json")
    r = subprocess.run([sys.executable, os.path.join(srv, "tools", "eval_agent.py"), "--brain", "rules", "--save", out], cwd=srv, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and os.path.isfile(out), r.stdout[-500:] + r.stderr[-500:]
