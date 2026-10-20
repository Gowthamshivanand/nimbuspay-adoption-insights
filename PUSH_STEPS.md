# PUSH_STEPS: redesign-v2 for Gowtham's bot (Windows)

Rules: **never force-push** (no `--force`, no `-f`, no `--force-with-lease`), never rewrite `main` history, never commit tokens.
`main` only changes if `verify_parity.ps1` prints `OVERALL: PASS`. Otherwise `main` stays as v1 for the 12:00 IST submission.

You get one file from Mohith: `redesign-v2.bundle` (a git bundle with branch `redesign-v2`, built on top of `main` at `d2dc703`).
A `redesign-v2.zip` (the full tree) and `redesign-v2.patch` are also provided, as backups only.

Needs: Git, Python 3.12, Node 20+ (for the `npm ci` build gate), Docker Desktop running (for gate G7).

```powershell
# 0. Get the repo and make sure main is the expected v1 commit
cd $HOME\nimbuspay-adoption-insights            # or: git clone https://github.com/Gowthamshivanand/nimbuspay-adoption-insights; cd nimbuspay-adoption-insights
git checkout main
git pull --ff-only origin main
git log -1 --format=%H                          # expect d2dc703f8f600031534763164a73ace8fa475b9f (if different, STOP and tell Mohith)
git status --short                              # must be empty

# 1. Tag v1 and push the tag (the safe fallback for the pitch)
git tag -a v1-final -m "v1 as presented before the redesign"
git push origin v1-final

# 2. Bring in the redesign branch from the bundle and push it (a new branch: normal push)
git bundle verify $HOME\Downloads\redesign-v2.bundle
git fetch $HOME\Downloads\redesign-v2.bundle redesign-v2:redesign-v2
git checkout redesign-v2
git push -u origin redesign-v2

# 3. Verify a FRESH clone of the pushed branch (all 8 gates, including Docker)
powershell -ExecutionPolicy Bypass -File parity\verify_parity.ps1 -Fresh https://github.com/Gowthamshivanand/nimbuspay-adoption-insights -Branch redesign-v2
```

Read the last lines. Merge **only** on `OVERALL: PASS` (G0 to G7 all `[PASS]`):

```powershell
# 4a. All PASS: fast-forward main to redesign-v2 (normal push, no force needed: redesign-v2 is built on top of main)
git checkout main
git merge --ff-only redesign-v2
git push origin main
```

```powershell
# 4b. Any FAIL: do NOT merge. main stays v1. Report the failing gate lines and the "Logs:" folder to Mohith.
git checkout main
```

If `git merge --ff-only` refuses (main moved), stop and tell Mohith; don't use any other merge mode without his OK.

**Rollback** after a merge (no force-push, no history rewrite): `git checkout main; git revert --no-edit d2dc703..HEAD; git push origin main`. For the pitch you can also run v1 straight from the tag: `git checkout v1-final`.

## What to expect
- G0 golden file untouched, G1 install, G2 front-end build (`npm ci && npm run build` -> `app/web/index.html`), G3 386 passed / 1 skipped, G4 release gate 21/21 29/29 24/24 40/40 + break-it 22/22, G5 golden API 874/874, G6 UI (4 Playwright tests + every-screen smoke at 3 widths), G7 Docker on 7860 (health, UI, state, **lineage 200 and the rules eval 21/21**, the approved Docker fix).
- The app runs with no Node: `python -m app` serves the committed build in `app/web/`. The v1 UI is at `/legacy`, or at `/` with `.\run_demo.ps1 -Legacy` (or `$env:NP_UI="legacy"`).
- The UI tests rewrite `docs/screenshots/*.png`; the verify script restores them. Never commit rewritten screenshots or `.venv-parity/`.
