---
license: mit
language: [en]
task_categories: [text-generation]
tags: [synthetic, routing, tool-use, refusal, governed-analytics]
pretty_name: NimbusPay Adoption Insights router + answer set (synthetic, English)
size_categories: [1K<n<10K]
---
# NimbusPay router + answer dataset (synthetic, English only)

**Synthetic hobby case study.** Every question was written by hand for this repo or generated from those templates, and every
number comes from the repo's synthetic warehouse. It has no link to any real company, person or customer, and no personal data.

Built by `python finetune/make_dataset.py` (deterministic, seed 20261018) from the repo itself: the governed tool list
(`app/agent.py` `INTENT_HELP`), the code guards, the 9 synthetic data scenarios and the real `Agent` outputs.

## Tasks
| Task | Input | Target |
|---|---|---|
| `route` | system prompt + `Role:` + optional `Previous question:` + `Question:` | one line of JSON `{"tool": <governed tool> \| "refuse" \| "none", "args": {...}}` |
| `answer` | question, tool, governed draft text, SQL rows, citations, data-as-of | 1 to 3 sentences using only numbers from the governed result, ending `Source: ...` |

Refusal reasons: `write, pii, individual, small_group, scope, forecast, causal, ungoverned, injection, gaming`.
Args: `region` (for `m01`), `agent` (agent ID for `agent_health` / `agent_value`), `metric` (M06 to M09 for `outcome`).

## How the gold labels are made
- **Code guards are the authority.** If a guard in `app/agent.py` refuses a question, its label is that refusal reason, even when the template said otherwise (16 such relabels, listed in `stats.json`). Labels follow the current guards: 9 code guards, with injection checked first, plus the claim check.
- Otherwise the label is the hand-written template label. That is where the model is meant to beat the rules router, which misses casual wording, typos and follow-ups. On the clean template questions the rules engine agrees with the label 989 times and disagrees 422 times (samples in `stats.json`).
- **Gold answers** are sentences picked from the real Agent answer for that scenario (`app/finetuned.py` `gold_answer`), so every number in a gold answer is in the governed result. A test checks this for every row.

## Splits
| Split | Rows | route | answer | Notes |
|---|---|---|---|---|
| train | 4,117 | 3,646 | 471 | templates 3,263 · follow-ups 383 · scenario answers 471 (6 scenarios) |
| val | 350 | 300 | 50 | same templates as train, different variants · answers from the `noids` scenario |
| test | 605 | 495 | 110 | see below |

**Test is held out.** It contains:
- 327 rows from **held-out templates**: new phrasings that never appear in train or val;
- 24 rows using **new agent aliases** ("the fraud copilot", "the doc summarizer tool");
- 29 **held-out follow-ups**;
- the repo's own evaluation sets: **21 golden questions, 8 extra guard and paraphrase probes, 64 unscripted probes and the 22 try-to-break-it cases** (labels from the rules engine, which scores 100% on them);
- 110 answer rows from two **held-out scenarios** (`incident`, `shelfware`), so the numbers are new too.

No golden, probe, unscripted or break-it question, and no exact test question, appears in train or val (282 candidates were dropped). A test checks this.

## Language and wording
English only. Wording styles in train: clean 970, casual 656, casual + typo 718, casual + abbreviation 622, typo 574, abbreviation 106.
Hard English cases are included on purpose:
- **near-miss refusals**: they look harmless but are not, for example "how active is Priya in fraud ops?", "raise a ticket to fix the KYC connector", "what would adoption look like if we trained everyone?";
- **near-miss answers**: they sound risky but are fine, for example "which group of analysts uses it least, team level only", "how many people use each agent";
- **multi-entity questions**: "Region A vs Region B utilisation", "How are the KYC checker and the summariser doing?";
- **claim checks**: "confirm utilisation is 90%", "sign off on 200 hours saved per week" (145 train rows). The model routes to the governed tool, or `none` for a vague "confirm 40% savings". The code's claim check then refuses to echo the user's number. Claim questions never get a model-written answer.
- **follow-ups**: "and Region B?", "what about the KYC one?", "ok remove them" (refuse), with the previous question in the prompt.

Refusals are 841 of 3,646 train route rows, and `none` (out of scope or vague claims) is 116.

## Files
`train.jsonl`, `val.jsonl`, `test.jsonl` (one JSON object per line: `id, task, split, source, style, persona, question, previous, label, args, messages[, governed]`), `stats.json` (counts, relabels, rules disagreements). About 7.1 MB in total.

## Limits
- The data is template-based. Real users will word things in ways the templates don't cover, so expect lower accuracy on real traffic than on this test set.
- Scenario numbers are small and synthetic, so the answer task mostly teaches the model to pick sentences and quote their numbers.
- The labels reflect this repo's governance rules, which are illustrative.
