# web/: NimbusPay Adoption Insights UI (v2)

React 18 + Vite 5 + TypeScript + Tailwind 3. Built into `../app/web/` (committed), which FastAPI serves at `/`.

```
npm ci && npm run build      # after editing src/ ; then commit app/web/ too
npm run dev                  # http://127.0.0.1:5173, proxies /api to python -m app on :8000
```

## Layout
| Path | What |
|---|---|
| `src/api/client.ts` | **The only place that talks to the backend.** One typed function per endpoint of `app/server.py` (same method, path and body as v1). |
| `src/api/types.ts` | Response and request shapes (named fields the UI reads; objects can carry more). |
| `src/pages/*.tsx` | One page per tab, routed by react-router (`/data`, `/exec`, `/whatif`, `/seats`, `/region`, `/eng`, `/agent`, `/alerts`, `/compare`, `/pack`, `/audit`, `/cost`, `/models`). A `MemoryRouter` keeps the URL bar unchanged, like v1. |
| `src/App.tsx` | Shell (header, role switch, sidebar), app state (dataset, persona, chat), the ask/stream flow, the two pop-ups. |
| `src/components/` | `Kpi`, `Bars`, `Header`, `Modal`, lineage and "Why this number?" pop-ups. |
| `tokens.cjs` | **All design tokens** (colours, font, radii, motion), fed into `tailwind.config.cjs`. Swap values here to apply a new Figma look. |

## Parity rules (do not break)
- Keep every `id` and `data-testid` (list: `docs/v2/PARITY_SPEC.md` §4.3); the Playwright tests drive this UI.
- No numbers are computed here; values are rendered as the backend returns them, with the v1 formatting (`src/lib/format.ts`).
- Inputs the tests `fill()` (sliders, cost inputs) are uncontrolled with `onInput`, as in v1.

## Swapping in Figma Make components
A Make export (`make-export/`) whose `src/api/client.ts` calls the real endpoints can be integrated page by page: copy a Make page's
markup into the matching `src/pages/<Tab>.tsx`, keep its data calls on **this** `src/api/client.ts` (same function names per endpoint;
Make's `USE_MOCK` data must stay off in the build), keep the ids/testids, run `npm run build`, then `bash parity/verify_parity.sh --repo .`.
