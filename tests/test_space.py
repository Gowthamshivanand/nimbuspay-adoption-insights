"""Hugging Face Docker Space: front-matter, Dockerfile port and brain, and the text-only upload folder."""
import os, re, sys
from conftest import ROOT
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_readme_front_matter():
    s = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    fm = re.match(r"^---\n(.*?)\n---\n", s, re.S).group(1)
    assert "sdk: docker" in fm and "app_port: 7860" in fm
    sd = re.search(r"short_description: (.*)", fm).group(1)
    assert len(sd) <= 60


def test_dockerfile_rules_brain_on_7860_no_secrets():
    d = open(os.path.join(ROOT, "Dockerfile")).read()
    assert "PORT=7860" in d and "EXPOSE 7860" in d and "NP_BRAIN=rules" in d and "USER user" in d
    assert not re.search(r"(API_KEY|TOKEN|SECRET|PASSWORD)\s*=", d)


def test_make_space_folder_is_clean():
    import make_space as M
    M.build()
    assert M.check() == []
    files = {os.path.relpath(os.path.join(d, f), M.OUT).replace(os.sep, "/") for d, _, fs in os.walk(M.OUT) for f in fs}
    assert {"README.md", "Dockerfile", "requirements.txt", "app/server.py", "app/static/index.html"} <= files
    assert not any(f.endswith((".db", ".pyc")) for f in files)
