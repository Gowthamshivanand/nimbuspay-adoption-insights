# Changelog

## v2.0.0 (redesign-v2, 20 Oct 2026)
Scope agreed with the project owner: a redesign and code clean-up only. Every feature, screen, number, agent answer, refusal, release-gate result, alert, cost figure, board pack, audit row, the offline/no-key behaviour and the Docker/HF Space on port 7860 work as in v1.

- **New web UI:** React 18 + Vite 5 + TypeScript + Tailwind 3 in `web/`, built into `app/web/` (committed, text-only). Same 13 screens, 2 pop-ups, controls, requests, ids and `data-testid`s as v1. Sidebar navigation, one page per tab under react-router (`web/src/pages/`), every request through a typed client (`web/src/api/client.ts`, one function per endpoint), Figma hi-fi tokens in one file (`web/tokens.cjs`). See `web/README.md` for swapping in Figma Make components.
- **Serving:** `/` serves the v2 build, `/assets/*` its files. The v1 UI is unchanged in `app/static/`, served at `/legacy`, and also at `/` with `NP_UI=legacy` or when `app/web/` is missing. No API endpoint was added or changed.
- **Fixed: the Docker image was missing `src/data.json`, `tools/` and `tests/data/probes.json`.** In Docker and the HF Space, "Explain this number" failed (`/api/lineage` 500) and the Models tab showed the rules engine as "not available". The Dockerfile copies them now; `.dockerignore` re-includes them and `tools/make_space.py` ships them. This is the only intentional behaviour change.
- **Tests:** added `tests/test_docker_files.py` (4) and `tests/test_ui_v2_playwright.py` (5). The existing tests are unchanged and pass with the same counts (386 passed, 1 skipped; release gate 21/21, 29/29, 24/24, 40/40; break-it 22/22; 4 browser tests).
- **Design review fixes (dizzi 42/60 round), front end only:** one role control (Executive, Manager, Analyst, Guest segments + "More roles" select; same testids); Data "Load" buttons as secondary; 6 grouped golden questions with "Show all 22" (same chips and testids); full-height sidebar, one scrolling tab row on mobile with 44 px targets; 4-column headline metrics; styled file pickers; board pack preview restyled on display (Inter, navy headings, hairline rules, in-preview print button hidden; the new-tab pack gets a navy print button), the backend HTML is unchanged; display-only copy: plurals, en dashes, human labels for cost keys, internal host/file/slide references hidden (hosts kept in tooltips), timestamps as "YYYY-MM-DD HH:MM UTC" (audit times have no zone in the data, so they show as server time); tab fade starts at 60% opacity. No API response, number or test changed.
- **Backend Python:** unchanged apart from the three serving routes in `app/server.py`. Restructuring was skipped on purpose: zero-risk parity came first.

## v1-final
The version presented before the redesign (tag `v1-final`).
