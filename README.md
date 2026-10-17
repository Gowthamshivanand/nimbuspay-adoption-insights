# NimbusPay AI adoption insights: interactive prototype

**Author:** Gowtham S · **Licence:** MIT · **Live demo:** https://YOUR-DOMAIN (placeholder)

A self-contained, offline, single-file prototype for the NimbusPay "Adoption Mirage" case (HashedIn by Deloitte DPM case, deliverable 7: a prototype of the agent interface and workflow). Its idea: **measure the work, not the clicks.**

> Every number is **illustrative synthetic data** that follows the rules in the supporting workbook (metrics M01 to M21, licence funnel LF1 to LF6, interaction rules IR1 to IR8). No real NimbusPay data is used.

## What it shows
| Screen | What it demonstrates |
|---|---|
| 1 Executive view | AI value score (M19) beside its 5 pillars (Reach 20, Depth 15, Outcome 40, Reliability 15, Trust 10); no silent imputation; critical-risk override; habitual users, verified hours, utilisation, cost per verified hour (an index against a placeholder cost); the renewal recommendation |
| 2 Regional adoption | Licence funnel by region and launch cohort, row-level security, small groups hidden, intervention list |
| 3 Engineering reliability | Error rates, connector health, unregistered agents, freshness, events missing an interaction ID |
| 4 How we count | Golden events grouped into interactions live: 9 events = 2 interactions, a 4.5x overstatement; Expected_Results checks |
| 5 Adoption Insights Agent | Role-scoped chat over governed metrics only; citations (metric, version, owner, data-as-of); refusals with safe alternatives; reasoning and SQL; a "why" breakdown (Q07) with a drill-down |
| 6 Governance | Metric catalogue, owners, versions, live tests, audit trail |

**Scenario switcher** (top bar): every preset changes the synthetic data coherently across all screens and personas.

| Scenario | Renewal outcome |
|---|---|
| Baseline demo | Renew and right-size |
| Healthy adoption | Expand |
| Overstated usage (vendor MAU high) | Renegotiate |
| Shelfware (paid seats unused) | Renew and right-size |
| New-country launch cohort | Continue limited pilot |
| Reliability incident (connector outage) | Renew with remediation conditions |
| Missing interaction IDs (drag-and-drop heavy) | Continue limited pilot |
| Critical-risk breach (privacy) | Renew with remediation conditions (score flagged red) |

Personas: Executive sponsor, Regional lead A, Regional lead B, Platform engineer, Fraud operations lead. A **Guided demo** button runs a 6-step story. A walkthrough video is in `docs/demo.mp4`.

## Screenshots
![Executive view](docs/screenshots/1-exec.png)
![Agent answering a why question](docs/screenshots/5b-agent-q07.png)
![How we count](docs/screenshots/4-count.png)
![Regional adoption, new-country scenario](docs/screenshots/scenario-newcountry-regional.png)
![Engineering, reliability incident](docs/screenshots/scenario-incident-eng.png)
![Governance](docs/screenshots/6-gov.png)

## Run locally
Double-click `index.html`. It needs no server, build or internet. Or run `python3 -m http.server 8000` and open http://localhost:8000.

Rebuild after editing `src/`:
```bash
cd src && python3 build.py   # writes ../index.html from shell.html + style.css + data.json + app.js
```
`src/extract.py` regenerates `data.json` from the workbook (edit the workbook path in it first).

Test (optional): `pip install playwright` and use a Chrome or Chromium binary, then run `python tests/qa_final.py file://$PWD/index.html /tmp/`. It clicks through every scenario, persona, screen and golden question, plus the guided demo, and fails on console errors.

## Deploy free on GitHub Pages
1. Create a public repository, for example `nimbuspay-adoption-insights`, and push this folder to the `main` branch.
2. Open **Settings → Pages → Build and deployment → Source: GitHub Actions**. The included workflow `.github/workflows/pages.yml` publishes on each push to `main`.
3. The site goes live at `https://<username>.github.io/nimbuspay-adoption-insights/`.

### Custom domain
1. Copy `CNAME.example` to `CNAME` and put your domain in it (one line, for example `adoption.example.com`). The workflow copies it into the site.
2. In **Settings → Pages → Custom domain**, enter the same domain and save. With Actions deployments, this setting is what counts.
3. At your DNS provider:
   - **Subdomain** (for example `adoption.example.com`): add a `CNAME` record from `adoption` to `<username>.github.io`.
   - **Apex** (for example `example.com`): add four `A` records pointing to `185.199.108.153`, `185.199.109.153`, `185.199.110.153` and `185.199.111.153`. Optionally add the AAAA records `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153` and `2606:50c0:8003::153`, plus a `CNAME` from `www` to `<username>.github.io`.
4. Wait for DNS to propagate (minutes to hours), then tick **Enforce HTTPS**.
5. Make the QR code: `pip install segno pillow && python tools/make_qr.py https://adoption.example.com --out assets`. The QR files in `assets/` now are **placeholders** for https://YOUR-DOMAIN.

### Alternatives
- **Netlify:** drag the folder onto app.netlify.com/drop, or connect the repository with no build command and publish directory `.`. For a custom domain, go to Domain settings, then add a CNAME to `<site>.netlify.app` (or an apex `A` record to `75.2.60.5`, or use Netlify DNS).
- **Vercel:** import the repository and choose framework "Other" with no build command. Add the domain in Project → Domains, then add a CNAME to `cname.vercel-dns.com` (or an apex `A` record to `76.76.21.21`).

Check the provider docs for the latest DNS values.

## Sources for synthetic ranges and definitions
These are used only to keep synthetic values plausible. No figures are copied as NimbusPay data.
- GitHub Docs, *Tracking license activation and initial usage*: healthy early adoption is about 60 to 80% of assigned users active in the first month. https://docs.github.com/en/copilot/tutorials/roll-out-at-scale/assign-licenses/track-usage-and-adoption
- GitHub Docs, *Interpreting usage and adoption metrics*: a WAU-to-licence ratio above 60% indicates strong usage. https://docs.github.com/en/copilot/reference/copilot-usage-metrics/interpret-copilot-metrics
- GitHub Docs, *Copilot usage metrics*: engaged means 2+ distinct days in 28. https://docs.github.com/en/copilot/reference/copilot-usage-metrics/copilot-usage-metrics
- Microsoft Learn, *Microsoft 365 Copilot usage report*: active users ÷ enabled users; opening a pane is not use. https://learn.microsoft.com/en-us/microsoft-365/admin/activity-reports/microsoft-365-copilot-usage
- Microsoft Learn, *Copilot adoption report (Viva Insights)*: a habitual user is active in 9 of 12 weeks. https://learn.microsoft.com/en-us/viva/insights/advanced/analyst/templates/microsoft-365-copilot-adoption
- Faros AI blog: high performers reach about 80% MAU and 60% DAU after six months (vendor blog; treat with care). https://www.faros.ai/blog/increase-github-copilot-adoption-and-usage-best-practices

## Credits
Concept, case solution and prototype: **Gowtham S**. Definitions come from his supporting workbook for the NimbusPay case. Not affiliated with NimbusPay (a fictional case company), HashedIn or Deloitte.
