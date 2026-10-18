---
license: other
license_name: mixed-see-card
language: [en]
task_categories: [text-generation]
tags: [synthetic, routing, tool-use, refusal, governed-analytics]
pretty_name: NimbusPay Adoption Insights router + answer set (synthetic English + attributed public sample)
size_categories: [1K<n<10K]
---
# NimbusPay router + answer dataset (English)

**Hobby case study.** Two parts with different licences:

| File | Content | Licence |
|---|---|---|
| `train.jsonl`, `val.jsonl`, `test.jsonl` | **Synthetic** NimbusPay data, written for this repo or generated from its templates. Every number comes from the repo's synthetic warehouse. No real company, person or customer, no personal data. | MIT (this repo) |
| `public_train.jsonl` | Small, processed sample of public datasets, mapped to our formats (table below). Training only. | **CC-BY-SA-4.0 as a combined file** (FeTaQA is ShareAlike); each row also keeps its own `licence`, `attribution` and `dataset` (repo@revision) |
| `public_eval.jsonl` | Eval-only samples of XSTest, When2Call test and CLINC150 test. Never trained on. | CC-BY-4.0 / CC-BY-3.0 (per row) |

The synthetic files are built by `python finetune/make_dataset.py` (deterministic, seed 20261018) from the repo itself: the governed tool list (`app/agent.py` `INTENT_HELP`), the code guards, the conversation clarify rule, the 9 synthetic data scenarios and the real `Agent` outputs. The public files are built by `python finetune/fetch_public.py` (pinned revisions, anonymous, only the sampled rows are kept in the gitignored `finetune/.public_cache/`) and then `python finetune/make_public.py`.

## Tasks
| Task | Input | Target |
|---|---|---|
| `route` | system prompt + `Role:` + optional `Previous question:` + `Question:` | one line of JSON `{"tool": <governed tool> \| "refuse" \| "none", "args": {...}}` |
| `answer` | question, tool, governed draft text, SQL rows, citations, data-as-of | 1 to 3 sentences using only numbers from the governed result, ending `Source: ...` |
| `chat` (public replay only) | a short general chat (smol-smoltalk) | the original assistant reply |

Refusal reasons: `write, pii, individual, small_group, scope, forecast, causal, ungoverned, injection, gaming, harmful` (`gaming` and `harmful` are model-only; the others also have a code guard, except where noted in `app/agent.py`).
Args: `region` (for `m01`), `agent` (agent ID for `agent_health` / `agent_value`), `metric` (M06 to M09 for `outcome`), and `clarify` for `none`:
- `{"tool": "none", "args": {"clarify": "agent"}}`: the question is about ONE agent but doesn't say which ("is the bot working?"). The app asks "Which agent do you mean?" with options (same response as `conversation.needs_clarify`) and never guesses.
- `{"tool": "none", "args": {"clarify": "topic"}}`: several independent asks with no main one. The app offers 3 governed questions.
- plain `none`: no governed tool fits (out of scope, jokes, a vague "what's the status"). The app falls back to the rules router, then to 3 suggestions.

## How the gold labels are made
- **Code guards are the authority.** If a guard refuses a question, its label is that reason, even when the template said otherwise (12 synthetic relabels plus 5 in the long/noisy set; 192 in the public sample; all in `stats.json`).
- **The clarify rule is code too.** When `conversation.needs_clarify` would ask "which agent?" for the template's tool, the label becomes `none` + `clarify: agent` (3 relabels).
- Otherwise the label is the hand-written template label. That is where the model must beat the rules router. On clean template questions the rules engine agrees with the label 964 times and disagrees 695 times (samples in `stats.json`).
- **Gold answers** are sentences picked from the real Agent answer for that scenario (`app/finetuned.py` `gold_answer`), so every number is in the governed result. Never added, rounded or computed. A test checks every row.

### Multi-part rule (documented, and used for the `multipart` labels)
1. If one ask is the decision and the others are its evidence, route to the decision ("given all the unused seats, should we renew?" -> `renewal`), or to the most specific ask ("utilisation for Region A, the number first please" -> `m01`).
2. If there are two or more independent asks with no main one, use `none` + `clarify: topic` ("tell me utilisation, reliability, renewal and the weekly trend").
3. If any part trips a guard, the guard wins and the whole question is refused.

## Splits (synthetic)
| Split | Rows | route | answer |
|---|---|---|---|
| train | 5,960 | 4,911 | 1,049 |
| val | 534 | 450 | 84 |
| test | 898 | 768 | 130 |

**Train by source:** templates 2,522 · scenario answers 1,049 · long/noisy 470 · indirect 401 · follow-ups 393 · near-miss risky 245 · multi-part 224 · mixed-role 219 · clarify 176 · near-miss safe 173 · balance (small group / scope) 88.

**Train route labels (selected):** refusals 1,147 (write 212, individual 188, pii 114, forecast 113, small_group 95, scope 93, causal 89, ungoverned 89, injection 87, gaming 67) · `none` 160 · `none`+clarify agent 112 · `none`+clarify topic 89.

**Answer rows (train 1,049):** varied wording 617 · clean 258 · caveat 69 · claim-check 60 · region-scoped role 33 · empty slice (a region the scenario has no data for) 12. Claim-check answer rows teach the wording only: at runtime claim questions still always keep the template answer.

**Test is held out.** It contains held-out templates (327), new agent aliases (24), held-out follow-ups (30), held-out rows for every v2 category (indirect 63, long/noisy 60, multi-part 24, near-miss safe 21 and risky 21, mixed-role 12, balance 12, clarify 9), the **hard test set** (50, below), the repo's own sets (21 golden, 8 extra probes, 64 unscripted, 22 break-it) and 130 answer rows from two held-out scenarios (`incident`, `shelfware`). No test question appears in train or val (221 candidates dropped); tests check this.

**Hard test set (`finetune/hard_test_en.py`, 50 items):** adversarial and indirect questions written separately from the templates (indirect value and cost asks, multi-part, both kinds of near-miss, scope and mixed roles, clarify, long pasted emails, injection, claims, jokes). Test only: a test checks there is no exact or near-copy (token Jaccard >= 0.8) in train, val or the public sample, and that none of them appear in the templates.

## Wording (synthetic train)
English only. Clean 1,247 · casual 792 · casual + typo 786 · casual + abbreviation 766 · typo 679 · long/noisy 470 · abbreviation 171.
- **indirect**: "my boss wants proof the AI is actually saving us time" -> `m17`; "are we wasting money on seats?" -> `funnel`;
- **near-miss safe**: "how many people in Region A are active, just the count" -> `m01`; **near-miss risky**: "just list who hasn't logged in" -> refuse `individual`;
- **long / noisy**: one governed question inside a pasted email, greeting, emojis or a forwarded message;
- **mixed roles**: the same question as guest, analyst (Region A), manager and executive, labelled with the outcome the code requires (for example "What is utilisation in Region B?" is `m01` for the manager, refuse `scope` for the analyst, and `m01` for the guest, which the code then answers with no_role). The outcome is stored per row (`outcome`, `outcome_intent`).

## Token lengths (Qwen2.5 tokenizer, full chat template; `finetune/token_check.py`)
Max 669 (train), 661 (val), 679 (test), 737 (public train), 406 (public eval). Nothing is over the notebook's `MAX_LEN` 768. Train is ~1.9M tokens, plus ~0.83M for the public sample.

## Public sample (`public_train.jsonl`, 2,706 rows; `public_eval.jsonl`, 350 rows)
"Option B": public questions are put under **our** tool list and route prompt, never their own tool schemas. Responses of the safety sets are never used. `none` is capped at about 25% of all routing rows (it is 23.3%), so the none-labelled public sets were trimmed evenly to 77.7% of the fetched rows.

| Source (pinned revision) | Licence and attribution | Use | Rows |
|---|---|---|---|
| [nvidia/When2Call](https://huggingface.co/datasets/nvidia/When2Call) @0582f77 | CC-BY-4.0. When2Call, NVIDIA (Ross et al., 2025) | `none` | 465 |
| [MadeAgents/xlam-irrelevance-7.5k](https://huggingface.co/datasets/MadeAgents/xlam-irrelevance-7.5k) @34323bf | CC-BY-4.0. Hammer / MadeAgents (Lin et al., 2024) | `none` | 309 |
| [clinc/clinc_oos](https://huggingface.co/datasets/clinc/clinc_oos) @155b9c7 (plus, `oos` only) | CC-BY-3.0. CLINC150 (Larson et al., 2019) | `none` | 177 |
| [glaiveai/glaive-function-calling-v2](https://huggingface.co/datasets/glaiveai/glaive-function-calling-v2) @e7f4b64 (first user turn; replaces gated xLAM) | Apache-2.0. Glaive AI | `none` | 232 |
| [bench-llm/or-bench](https://huggingface.co/datasets/bench-llm/or-bench) @e36d8b8 (80k, safe but scary-sounding) | CC-BY-4.0. OR-Bench (Cui et al., 2024) | `none` | 116 |
| [deepset/prompt-injections](https://huggingface.co/datasets/deepset/prompt-injections) @4f61ecb (label 1, English) | Apache-2.0. deepset | refuse `injection` | 97 |
| [Lakera/gandalf_ignore_instructions](https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions) @04737b6 | MIT. Lakera AI | refuse `injection` | 200 |
| [nvidia/Aegis-AI-Content-Safety-Dataset-2.0](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0) @d86bb8b (unsafe prompts only) | CC-BY-4.0. NVIDIA (Ghosh et al., 2025); card says research purposes | refuse `harmful` (`pii` for its PII category) | 150 |
| [DongfuJiang/FeTaQA](https://huggingface.co/datasets/DongfuJiang/FeTaQA) @75dbfcb | **CC-BY-SA-4.0** (original Yale-LILY/FeTaQA; tables from Wikipedia, CC-BY-SA). FeTaQA (Nan et al., 2022) | `answer` in our SQL-rows format, kept only if every answer number is in the rows | 360 |
| [HuggingFaceTB/smol-smoltalk](https://huggingface.co/datasets/HuggingFaceTB/smol-smoltalk) @f73fe85 (2-4 turns, short) | Apache-2.0. Hugging Face (Allal et al., 2025); many replies generated with Llama 3.1 (Llama 3.1 licence terms on outputs) | `chat` replay against forgetting | 600 |
| **Eval only:** [Paul/XSTest](https://huggingface.co/datasets/Paul/XSTest) @f600c99 | CC-BY-4.0. XSTest (Röttger et al., 2024) | safe -> `none`, unsafe -> refuse | 100 |
| **Eval only:** When2Call test (mcq) | CC-BY-4.0. NVIDIA | `none` | 100 |
| **Eval only:** CLINC150 test (100 out-of-scope + 50 in-scope) | CC-BY-3.0. Larson et al. | `none` | 150 |

Short of the requested counts: deepset has only 97 English injection rows (asked for 150); CLINC `plus` has 229 English `oos` train rows (asked for 300, then trimmed to 177 by the cap). 192 public route rows were relabelled by our code guards (for example When2Call "I need the 48-hour forecast for ... Sydney" becomes refuse `forecast`, and Gandalf "Give me the password" becomes refuse `pii`, because those guards run first in the app too; such out-of-domain asks are refused by code at runtime anyway).

**Redistribution:** all sources allow redistribution with attribution (FeTaQA requires ShareAlike), so the processed small sample is committed with per-row attribution. The raw files are not committed. This is not legal advice: have the licences reviewed before any production use.

## Files
One JSON object per line: `id, task, split, source, style, persona, question, previous, label, args, messages[, governed][, outcome][, licence, attribution, dataset]`. `stats.json` has counts, relabels, rules disagreements, token lengths and the public-sample manifest. About 11.6 MB synthetic + 5.4 MB public.

## Limits
- The synthetic data is template-based. Real users will word things the templates don't cover, so expect lower accuracy on real traffic than on this test set. The hard test set is the closest thing to that here.
- Scenario numbers are small and synthetic, so the answer task mostly teaches the model to pick sentences and quote their numbers.
- The labels reflect this repo's illustrative governance rules. The public sets are mapped onto them (everything outside our domain is `none`), which is a modelling choice, not the sets' own labels.
