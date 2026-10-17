# 4-minute demo script

All values are illustrative synthetic data. Part A uses the static prototype (`index.html` or the GitHub Pages link). Part B uses the live product (`python -m app`, then http://127.0.0.1:8000). Open both tabs before you start.

## Part A: static prototype (0:00 to 1:30)

| Time | Do | Say |
|---|---|---|
| 0:00 | Open `index.html` on the **Executive view**, scenario *Baseline demo* | "Leadership sees only vendor MAU. This view shows an AI value score, always beside its five pillars." |
| 0:10 | Tick **Simulate critical-risk breach**, then untick. Tick **Simulate missing** on Outcome, then untick | "A breach flags the score red whatever its value. A missing pillar withholds the score: no silent guessing." |
| 0:20 | **How we count** → switch to logical-interaction counting | "Nine raw events are two real interactions. Vendor-style counting overstates usage 4.5 times." |
| 0:35 | **Adoption Insights Agent** → click **Q07** | "A why question gets a breakdown, an honest correlation caveat and next steps." |
| 0:50 | Back in the agent, type a card number | "Unsafe or out-of-scope questions are refused, with a safe alternative." |
| 1:00 | Change **Scenario**: Healthy → Shelfware → Critical-risk breach | "The same rules give a different renewal call: expand, right-size, remediate." |
| 1:20 | Switch **Viewing as** to Regional lead B | "Row-level security: each persona sees only their scope." |

## Part B: live product (1:30 to 4:00)

| Time | Do | Say |
|---|---|---|
| 1:30 | Switch to the live product, **Data** tab | "This isn't a mock-up. It's a running product: a Python pipeline, a SQL warehouse and an agent, on my laptop, with no internet and no paid service." |
| 1:40 | Point at the **Pipeline result** line | "The workbook's 210 raw rows: duplicates and late rows handled, 200 clean events, 44 interactions, 22 exact and 22 approximate. My tests check all 35 expected results in the workbook exactly." |
| 1:55 | Click **Load** on *Baseline*, which opens the **Executive** tab | "Utilisation is 69.6% against a 70% threshold, so the engine says renew and right-size. Every figure carries its metric ID and version." |
| 2:10 | **Agent** tab → click **Q01**, then open **SQL used** | "The agent answers from governed metrics only. It cites M01 version 1.0, the data-as-of time, and shows the exact SQL it ran." |
| 2:25 | Click **Q12** (fraud analysts least), then **Q14** (card numbers) | "It refuses to single out people or show card data, and offers a safe alternative." |
| 2:40 | Type: *What renewal outcome do you recommend?* | "Ask in plain English. The header shows the brain: a small open model running locally on Ollama if it is installed, otherwise the rules engine. It only picks a governed tool; numbers always come from SQL. If the model is not running, it falls back to the rules engine automatically." |
| 2:55 | **What-if** tab: drag seats to 20, then **Simulate** | "Right-size to 20 seats and the same rules move us from right-size to expand, with no new data invented. Every number on screen also has an 'explain this number' panel with its SQL and owner." |
| 3:15 | **Data** → Load *Critical-risk breach* → Executive | "A privacy incident turns the score red and forces remediation, even though usage looks fine." |
| 3:30 | **Board pack** → *Open printable pack* | "One click gives a board-ready pack: recommendation, evidence, score with pillars, headline metrics, alerts." |
| 3:45 | **Audit log** | "Every question I just asked is logged with persona, outcome and metrics cited. That's how this stays trustworthy." |
| 3:55 | Stop | "Measure the work, not the clicks." |

## Fallbacks
- Wi-Fi drops: everything above runs on localhost. Only the GitHub Pages link needs internet.
- Laptop issue: play `docs/demo.mp4`, or open the screenshots in `docs/screenshots/app-*.png`.
- A question fails live: say "it refuses rather than guesses", then click a golden-question chip.
