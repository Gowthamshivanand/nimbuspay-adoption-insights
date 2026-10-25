# NimbusPay Adoption Insights — design spec

Visual source of truth for the v2 shell on branch `ui-redesign`. Numbers, metric IDs, citations, and test ids are unchanged. This file is what a Figma hi-fi file should match.

## Themes

- Light and dark. `html.dark` switches every colour variable.
- Boot script in `web/index.html` reads `localStorage.np-theme` (`light` | `dark`). Missing key follows `prefers-color-scheme`.
- Header control (sun / moon) writes an explicit choice. Shortcut `T` does the same.
- `color-scheme` is set so native controls match.

## Colour tokens

Defined once in [web/src/tokens.css](web/src/tokens.css). Tailwind names in `web/tokens.cjs` point at the variables.

| Token | Light | Dark | Use |
|---|---|---|---|
| canvas `--np-canvas` | `#F7F7F5` | `#0E0F12` | Page background |
| surface `--np-surface` | `#FFFFFF` | `#16181D` | Cards, sidebar fill |
| elevated `--np-elevated` | `#FFFFFF` | `#1E2026` | Inputs, raised chips |
| ink `--np-ink` | `#16181D` | `#F5F5F4` | Primary text |
| heading `--np-heading` | `#0B2E59` | `#F5F5F4` | h1, h2, wordmark |
| slate `--np-slate` | `#334155` | `#CBD5E1` | Secondary series label |
| text-2 / muted `--np-muted` | `#4B5563` | `#A1A1AA` | Secondary text (AA) |
| text-3 `--np-text-3` | `#6B7280` | `#A1A1AA` | Tertiary, not for small body |
| line `--np-line` | `#E3E3DF` | `rgba(255,255,255,0.08)` | Hairlines |
| line strong `--np-line-strong` | `#D2D2CC` | `rgba(255,255,255,0.14)` | Input and control borders |
| track `--np-track` | `#EEEDE8` | `rgba(255,255,255,0.06)` | Bar tracks |
| grid `--np-grid` | `rgba(22,24,29,0.08)` | `rgba(255,255,255,0.06)` | Chart grid inset |
| tag `--np-tag` | `#F3F2EE` | `rgba(255,255,255,0.06)` | Neutral chips |
| accent text `--np-accent` | `#C2410C` | `#E8751A` | Accent text (AA on canvas) |
| accent fill `--np-accent-fill` | `#E8751A` | `#E8751A` | Marks, bars, focus. Not body text on light |
| accent press `--np-accent-press` | `#C2410C` | `#C2410C` | Pressed accent |
| accent soft `--np-accent-soft` | `#FDF0E4` | `rgba(232,117,26,0.16)` | Selected tint |
| navy `--np-navy` | `#0B2E59` | `#0B2E59` | Primary buttons, selected role. White label |
| series 2 `--np-series-2` | `#0B2E59` | `#93B4E8` | Chart series 2 (navy, lifted in dark for 3:1) |
| series 3 `--np-series-3` | `#64748B` | `#A1A1AA` | Chart series 3 |
| success text `--np-verified` | `#166534` | `#4ADE80` | AA text. Fill stays `#16A34A` |
| success fill `--np-verified-fill` | `#16A34A` | `#16A34A` | Verified chips |
| warning text `--np-warning` | `#B45309` | `#FBBF24` | AA text. Fill `#D97706` |
| danger text `--np-critical` | `#DC2626` | `#FCA5A5` | AA text |
| danger fill `--np-critical-fill` | `#DC2626` | `#DC2626` | Guest role, solid danger (white label) |
| danger soft `--np-danger-soft` | `#FEF2F2` | `rgba(220,38,38,0.14)` | Refusal card |
| glass `--np-glass` | white 78% | surface 78% | Header, sidebar, command bar, panel only |
| shadow `--np-shadow` | `0 1px 2px rgba(22,24,29,0.04), 0 8px 24px rgba(22,24,29,0.05)` | darker | Cards |
| shadow pop `--np-shadow-pop` | `0 16px 50px rgba(22,24,29,0.16)` | `0 18px 60px rgba(0,0,0,0.5)` | Command bar, panel, modal |

Chart fills (accent, series 2, series 3) are at least 3:1 against canvas and surface in both themes. Text tokens above are at least 4.5:1 against canvas and surface. Accent fill `#E8751A` is not used as small text on light canvas.

## Type

- Family: `-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", Inter, sans-serif`
- Mono: `SFMono-Regular, ui-monospace, Menlo, Consolas, monospace`
- All metrics: `font-variant-numeric: tabular-nums`
- Tracking on headings: `-0.01em`. Hero figures: `-0.03em`. KPI value: `-0.02em`
- Scale: 12 eyebrow and meta, 13 controls and table, 15 body, 17 section title, 22 outcome, 28 page title and KPI, 40 hero figure (32 under 768px)

## Space, radius, elevation

- Base unit 8px. Card padding 16px. Page padding 32px desktop (`lg:px-10` is 40px), 24px tablet, 16px under 768px. Section gap 16px. Stack gap inside cards 8–12px.
- Card radius 14px. Control radius 10px. Pills 999px.
- Cards are solid surfaces with `--np-shadow`. No glass on cards.
- Backdrop blur 18px (header, sidebar) or 22px (command bar, panel), saturate 140–160%. Only those four surfaces.

## Layout

- Laptop first: 1440 and 1280. Then 1024, 768, 390. `html, body, #root` use `overflow-x: clip`. Wide tables scroll inside their card.
- Header (glass): wordmark, dataset + data-as-of (`#ds`), role switch (unchanged test ids), scrollable 8-preset segmented control, theme, command, agent panel, `data: synthetic` pill.
- Sidebar (glass), 220px, collapses to 72px icons on desktop (`localStorage.np-side`). Groups: Dataset, Insights, Agent, Reporting, Platform. Tab buttons keep `#tab-{id}`.
- Under 1024px the sidebar becomes a fixed 64px bottom nav. Labels stay visible. Main gets 88px bottom padding. Preset control scrolls inside itself.
- Main max width 1180px. In-page subnav scrolls horizontally and jumps to sections. It does not hide content.
- Footer stays: read-only line and metric version `#ver` `v1.0`.

## Components

- **Tile / card** `.tile` — surface, 1px line, 14px radius, soft shadow, 16px padding.
- **KPI** `.kpi` — eyebrow or metric id in accent, 28px value, 12px label. `data-metric` + `data-testid=kpi-{id}` unchanged. Click still opens lineage.
- **Outcome card** `.outcard` — 3px accent left border. Outcome text keeps `data-testid=outcome`.
- **Hero** — Vendor MAU vs habitual vs paid seats from the live funnel (`LF1`, `LF6`, `users.vendor_mau_proxy`). Hero figures count up. The sentence under the funnel still prints the raw proxy, active count, and `paid_unused`.
- **Bars** — label, track, fill, tabular value. Tones: accent, navy (series 2), slate (series 3). Hover brightens the fill. `title` carries the same value. Optional legend.
- **Buttons** — `.btn` navy fill, white label. `.ghost` elevated surface, line border. Disabled 40% opacity.
- **Role switch** — four segments plus `#persona`. Selected segment has class `on`. Guest selected uses danger fill, not the dark-theme danger text colour.
- **Presets** — header buttons `data-preset={key}`, `aria-pressed`. Keys: baseline, breach, healthy, incident, newcountry, noids, overstated, shelfware. Data screen keeps `data-testid=scen-{key}`.
- **Tags** — 11px pill. Brain tags unchanged (`Rules engine`, and so on). Extra `Rules fallback` or `Model` tag beside them.
- **Citation chips** — metric id, version, `data as of`, `synthetic`, as separate pills. Copy writes `ID version, … | data as of …` and toasts.
- **Chat** — user bubble navy, right aligned. Answer bubble elevated. Refusal: danger-soft fill, danger border. Caveat: accent left border. Clarify: series-2 left border. Streaming caret is a 7×14 accent block. Golden chips and `gq-*` test ids unchanged.
- **Command bar** — centred, max 640px, 16vh from the top. Scale 0.98 and 6px blur on enter. Esc or backdrop closes.
- **Agent panel** — right drawer, max 420px, full width under 1024px. Same chat thread, no duplicate test ids.
- **Modal** — lineage `#lin`, why `#why`. 46% scrim. Card max 86vh.
- **Skeleton** — 14px bars plus a 96px card, shimmer 1.2s. Replaced by real test-id nodes when data arrives. Empty copy stays: `No alerts`, `No questions yet`, chat hint.
- **Toast** — ink pill, canvas text, bottom centre (80px up when the bottom nav is showing). Preset change, citation copy, agent or upload failure. 2.8s. `role=status`.
- **Shortcut sheet** — `?` when not typing.

## Motion

Easing `--np-ease`: `cubic-bezier(0.32, 0.72, 0, 1)`.

| Name | Duration | What |
|---|---|---|
| fast | 200ms | colour, buttons, toast |
| base | 280ms | screen rise (8px + fade), modal, panel slide (16px + blur), sidebar width |
| bar-in | 280ms | chart fill `scaleX(0 → 1)` from the left |
| count | 700ms | hero integers only, ease-out cubic. Final text is not delayed on tested values |
| blink | 1s steps | streaming caret |
| shimmer | 1.2s | skeletons |
| pop | 240ms | command bar scale + blur |

`prefers-reduced-motion: reduce` zeros transitions and animations, including the hero count.

## Keyboard

| Key | Action |
|---|---|
| ⌘K / Ctrl+K | Command bar |
| ⌘J / Ctrl+J | Toggle agent panel |
| 1–8 | Presets, in API order, when not typing |
| T | Theme |
| ? | Shortcut sheet |
| Esc | Close command bar, panel, sheet |

Focus: 2px accent-fill ring, 2px offset, on `:focus-visible`.

## Responsive

| Width | Behaviour |
|---|---|
| ≥1024 | Sidebar left, hero two columns, what-if two columns |
| 768–1023 | Bottom nav, hero stacks, preset scroller |
| ≤767 | 22px titles, 32px hero figures, 16px page inset, panel full screen |

## Files

- Tokens: `web/src/tokens.css`, `web/tokens.cjs`, `web/tailwind.config.cjs`
- Shell: `web/src/App.tsx`, `web/src/components/chrome.tsx`, `web/src/index.css`
- Screens: `web/src/pages/*` (copy and test ids preserved)
- Build output served by FastAPI: `app/web/`
