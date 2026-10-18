# Fine-tuning the agent's brain (LoRA on a free Colab T4)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohithraghava/nimbuspay-adoption-insights/blob/main/finetune/NimbusPay_FineTune_Colab.ipynb)

Hobby case study, English only. The NimbusPay data is synthetic; a small attributed public sample is mixed in (see `data/README.md`).

## Why fine-tune
The stock small model is worse than the rules engine today. On Mohith's PC, `qwen2.5:3b-instruct` (not fine-tuned) scored:

| Test | Stock 3B via Ollama | Rules engine |
|---|---|---|
| Golden questions | 19/21 | 21/21 |
| Guard + paraphrase probes | 27/29 | 29/29 |
| Unscripted probes | 50/64 | 64/64 |

The rules engine is perfect on those sets because they were written alongside it, but it misses messy English. On this kit's held-out test (768 route rows) the rules router picks the right tool only **40.6%** of the time. By source:

| Test source | Rows | Rules tool accuracy |
|---|---|---|
| golden / extra probes / unscripted / break-it | 21 / 8 / 64 / 22 | 100% (written alongside the rules) |
| mixed-role (held out) | 12 | 100% |
| clarify (held out) | 9 | 88.9% (tool only; the rules never emit the `clarify` slot) |
| new agent aliases | 24 | 66.7% |
| near-miss safe | 21 | 61.9% |
| **hard test set** (50 hand-written adversarial / indirect) | 50 | **46.0%** |
| indirect | 63 | 39.7% |
| multi-part | 24 | 37.5% |
| small group / scope balance | 12 | 33.3% |
| held-out templates | 327 | 24.5% |
| long / noisy | 60 | 11.7% |
| near-miss risky | 21 | **0%** |
| follow-ups | 30 | **0%** (it never sees the previous question) |

Refusal recall of the rules router on this test is 32.8% (63 should-refuse rows routed to a data tool by the router alone; in the app the guards still catch the ones they match). On the eval-only public file (XSTest / When2Call / CLINC, 350 rows) it scores 82.0% (XSTest 48%).

**Goal:** a fine-tuned `Qwen2.5-1.5B-Instruct` that **matches the rules engine on the golden, probe and unscripted sets** and **does much better on messy English** (typos, casual and indirect wording, near-miss refusals, multi-entity questions, follow-ups), while never writing a number that isn't in the governed result.

## What the model does, and what stays in code
| Step | Who |
|---|---|
| Safety guards (injection, write, PII, individuals, small groups, scope, forecast, causal, ungoverned), with markup stripped | **Code, always first.** The model never sees a question a guard refused. |
| Route: question -> `{"tool", "args"}`, or `refuse` with a reason (also catches injection the regex misses, `gaming` and `harmful`), or `none`, or `none` + `clarify` | **Model** |
| Clarify: `none` + `clarify: agent` asks "Which agent do you mean?" (options, confidence 0.4, same as `conversation.needs_clarify`); `clarify: topic` offers 3 governed questions | **Code** builds the question; the model only flags the missing slot |
| Schema check, arg validation (agent IDs, regions in the data, M06 to M09), scope re-check on the model's region | **Code.** Any failure falls back to the rules router. |
| Numbers: SQL on the governed warehouse | **Code** |
| Answer text from the tool's rows + citations | **Model**, then code rejects any number not in the result and falls back to the template answer |
| Claim check ("confirm 40% savings"): a user-typed number is never echoed | **Code.** Claim questions always use the template answer. |

The integration is `NP_BRAIN=finetuned` in `app/agent.py` + `app/finetuned.py`. The model name comes from `FT_MODEL` (default `nimbuspay-router`), and `FT_ANSWER=0` turns off the answer step. In a chat session the previous question is passed to the model (`app/conversation.py`), so it can resolve follow-ups the rules rewrite doesn't cover.

## Steps for Mohith
1. Open the notebook with the **Open in Colab** badge above.
2. `Runtime > Change runtime type > T4 GPU > Save`.
3. `Runtime > Run all`. **Time is an estimate, not measured on a T4 yet.** The mix is 5,960 synthetic + 2,706 public train rows, about 2.7M tokens per epoch (round 1 was 1.15M). With 2 epochs the 1.5B run is roughly **45 to 90 minutes**: about 35 to 75 minutes of training, about 5 to 10 minutes of evaluation (898 test + 350 public eval rows) and about 5 minutes for llama.cpp and export. Set `EPOCHS = 1` to roughly halve training (a reasonable first run; 2 epochs is the default because the router labels are short), or `USE_PUBLIC = False` to drop about a third of the tokens.
4. Read the output of cell 9 (the release gate). If it says **FAIL**, stop there and keep the rules engine.
5. Cell 12 downloads `nimbuspay-router-export.zip`, which contains `nimbuspay-router-q4_k_m.gguf` (about 1 GB), the `Modelfile` and `eval_report.json`.
6. On Windows, unzip it, open PowerShell in that folder and run:
   ```powershell
   ollama create nimbuspay-router -f Modelfile
   ollama run nimbuspay-router "hi"          # quick check, Ctrl+D to exit
   cd <repo folder>
   python finetune\eval_finetuned.py          # test set + release gate + latency p50/p95 on YOUR PC
   python tools\eval_agent.py --brain finetuned
   $env:NP_BRAIN="finetuned"; python -m app   # only if the gate passed
   ```
7. Optional: set `PUSH_TO_HF = True` in cell 1 to upload the model, the adapter and the dataset to your own Hugging Face account. Colab asks for a write token; nothing is saved in the notebook.

**7B option:** set `MODEL_CHOICE = "7B"` in cell 1. It trains `Qwen2.5-7B-Instruct` with 4-bit QLoRA and runs 1 epoch by default. With the bigger mix that is an estimated **3.5 to 6 hours**, which is often past a free Colab session, so use `USE_PUBLIC = False` for 7B (about 2.5 to 4 hours). A free T4 can't merge 7B, so the notebook exports a LoRA adapter GGUF instead. The Modelfile then uses `FROM qwen2.5:7b-instruct` + `ADAPTER`, so run `ollama pull qwen2.5:7b-instruct` first. It runs slowly on a 16 GB laptop.

## Release gate (ship only if all pass)
Checked end to end through the real Agent, with the guards in front, by `finetune/eval_finetuned.py` and notebook cell 9:
1. Golden 21 and the 29 guard + paraphrase probes: fine-tuned **>=** rules engine (currently 21/21 and 29/29).
2. Unscripted 64 and the 22 try-to-break-it cases: fine-tuned **>=** rules (64/64, 22/22).
3. **0 unsafe answers**, meaning no should-refuse question got data.
4. **100% number faithfulness** of every answer shown. The code check enforces this, and the gate double-checks it.

It also reports model-only metrics on the 768 held-out route rows and 130 answer rows, plus the 350-row public eval-only file (over-refusal on XSTest, out-of-scope on CLINC / When2Call): tool and exact accuracy, refusal precision and recall, unsafe routes, over-refusals, number faithfulness and accuracy by source and wording style, plus latency p50/p95. If the gate fails, the app keeps working on the rules engine and nothing changes for the demo.

## Files
| File | What |
|---|---|
| `make_dataset.py`, `templates_en.py` | Build the synthetic `data/` from the repo (deterministic) |
| `hard_test_en.py` | 50 hand-written hard test questions (test only, checked for overlap) |
| `fetch_public.py`, `make_public.py` | Fetch the pinned public sample (anonymous, gitignored cache) and map it to our formats |
| `token_check.py` | Token lengths with the Qwen tokenizer vs `MAX_LEN` 768 (writes `stats.json["tokens"]`) |
| `data/` | `train.jsonl` 5,960 · `val.jsonl` 534 · `test.jsonl` 898 · `public_train.jsonl` 2,706 · `public_eval.jsonl` 350 · `stats.json` · dataset card `README.md` |
| `NimbusPay_FineTune_Colab.ipynb` | The Colab notebook (built by `build_notebook.py`; edit that, not the .ipynb) |
| `ft_eval.py` | Model-level metrics, shared by the notebook and the CLI |
| `eval_finetuned.py` | CLI: test-set metrics via Ollama + end-to-end release gate + latency |
| `MODEL_CARD_TEMPLATE.md` | Model card, filled in automatically by the notebook's Hugging Face cell |
| `../tests/test_finetuned.py` | 39 tests with a mocked model (schema incl. clarify, fallback, clarify flow, scope, refusals, injection guard, claim check, number check, dataset hygiene, v2 categories and balance, hard-test overlap, public mix attribution / cap / test separation) |

Rebuild after changing intents or guards: `python finetune/make_dataset.py && python finetune/make_public.py && python finetune/build_notebook.py && python -m pytest tests/test_finetuned.py` (`make_public.py` needs the cache from `python finetune/fetch_public.py`, which needs internet and pyarrow; without it the committed public files are kept). `python finetune/token_check.py` needs transformers.

## Licences
- `Qwen/Qwen2.5-1.5B-Instruct` and `Qwen/Qwen2.5-7B-Instruct`: **Apache 2.0**, commercial use allowed. The stock 3B used in the earlier demo is under the Qwen Research licence (no commercial use), which is why it isn't the fine-tune base.
- llama.cpp: MIT. Ollama: MIT. transformers, peft, accelerate: Apache 2.0.
- Synthetic dataset and code: MIT (this repo). Public sample: per-source licences in `data/README.md`; the combined `public_train.jsonl` is CC-BY-SA-4.0 because FeTaQA is ShareAlike. Not legal advice; review before production.
- Your fine-tuned weights inherit Apache 2.0 from the base. Keep its licence and notice if you publish them.

## Honest limits
- **Smoke test, not a real training run:** the whole notebook was executed on a CPU box (no GPU) with `NP_SMOKE=1`: `Qwen2.5-0.5B-Instruct`, 64 training rows, 20 steps, about 5 minutes. Every stage ran: data load, LoRA training (loss 0.51, eval loss 0.52), test-set eval, the end-to-end release gate, merge, and llama.cpp GGUF conversion (f16, 0.99 GB). The q4_k_m quantise step was skipped because the box has no C++ compiler, and the f16 fallback path worked; Colab builds `llama-quantize` itself. As expected for 20 steps, the gate said **FAIL** (golden 13/21, 6 unsafe answers), which shows the gate does catch a bad model. The real numbers come from the Colab run.
- Training time for the bigger mix is an estimate from token counts, not a measured T4 run.
- The test set is mostly template-based, so real panel wording will score lower. The 50-question hard test set is the best proxy here. The gate's golden, probe and unscripted sets are the closest thing to real questions.
- Latency on a laptop CPU will be higher than with rules: one route call, plus one answer call when `FT_ANSWER=1`. Measure it with `eval_finetuned.py`. If it's too slow live, set `FT_ANSWER=0` so the model only routes.
- The number check catches digits, not numbers written as words.
