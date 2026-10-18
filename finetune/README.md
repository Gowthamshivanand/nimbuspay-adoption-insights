# Fine-tuning the agent's brain (LoRA on a free Colab T4)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mohithraghava/nimbuspay-adoption-insights/blob/main/finetune/NimbusPay_FineTune_Colab.ipynb)

Hobby case study, synthetic data only, English only.

## Why fine-tune
The stock small model is worse than the rules engine today. On Mohith's PC, `qwen2.5:3b-instruct` (not fine-tuned) scored:

| Test | Stock 3B via Ollama | Rules engine |
|---|---|---|
| Golden questions | 19/21 | 21/21 |
| Guard + paraphrase probes | 27/29 | 29/29 |
| Unscripted probes | 50/64 | 64/64 |

The rules engine is perfect on those sets because they were written alongside it, but it misses messy English. On this kit's held-out test (new phrasings, typos, casual wording, follow-ups) the rules router picks the right tool only **about 42%** of the time overall and about 24% on the held-out templates. Follow-ups like "and Region B?" score 0%, because it never sees the previous question.

**Goal:** a fine-tuned `Qwen2.5-1.5B-Instruct` that **matches the rules engine on the golden, probe and unscripted sets** and **does much better on messy English** (typos, casual and indirect wording, near-miss refusals, multi-entity questions, follow-ups), while never writing a number that isn't in the governed result.

## What the model does, and what stays in code
| Step | Who |
|---|---|
| Safety guards (injection, write, PII, individuals, small groups, scope, forecast, causal, ungoverned), with markup stripped | **Code, always first.** The model never sees a question a guard refused. |
| Route: question -> `{"tool", "args"}`, or `refuse` with a reason (also catches injection the regex misses, and `gaming`), or `none` | **Model** |
| Schema check, arg validation (agent IDs, regions in the data, M06 to M09), scope re-check on the model's region | **Code.** Any failure falls back to the rules router. |
| Numbers: SQL on the governed warehouse | **Code** |
| Answer text from the tool's rows + citations | **Model**, then code rejects any number not in the result and falls back to the template answer |
| Claim check ("confirm 40% savings"): a user-typed number is never echoed | **Code.** Claim questions always use the template answer. |

The integration is `NP_BRAIN=finetuned` in `app/agent.py` + `app/finetuned.py`. The model name comes from `FT_MODEL` (default `nimbuspay-router`), and `FT_ANSWER=0` turns off the answer step. In a chat session the previous question is passed to the model (`app/conversation.py`), so it can resolve follow-ups the rules rewrite doesn't cover.

## Steps for Mohith
1. Open the notebook with the **Open in Colab** badge above.
2. `Runtime > Change runtime type > T4 GPU > Save`.
3. `Runtime > Run all`. The 1.5B default takes about **15 to 30 minutes**: about 10 to 20 minutes of training, about 5 minutes of evaluation, and about 5 minutes to build llama.cpp and export.
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

**7B option:** set `MODEL_CHOICE = "7B"` in cell 1. It trains `Qwen2.5-7B-Instruct` with 4-bit QLoRA, which takes about 1.5 to 2.5 hours on a T4, and runs 1 epoch by default. A free T4 can't merge 7B, so the notebook exports a LoRA adapter GGUF instead. The Modelfile then uses `FROM qwen2.5:7b-instruct` + `ADAPTER`, so run `ollama pull qwen2.5:7b-instruct` first. It runs slowly on a 16 GB laptop.

## Release gate (ship only if all pass)
Checked end to end through the real Agent, with the guards in front, by `finetune/eval_finetuned.py` and notebook cell 9:
1. Golden 21 and the 29 guard + paraphrase probes: fine-tuned **>=** rules engine (currently 21/21 and 29/29).
2. Unscripted 64 and the 22 try-to-break-it cases: fine-tuned **>=** rules (64/64, 22/22).
3. **0 unsafe answers**, meaning no should-refuse question got data.
4. **100% number faithfulness** of every answer shown. The code check enforces this, and the gate double-checks it.

It also reports model-only metrics on the 495 held-out route rows and 110 answer rows: tool and exact accuracy, refusal precision and recall, unsafe routes, over-refusals, number faithfulness and accuracy by source and wording style, plus latency p50/p95. If the gate fails, the app keeps working on the rules engine and nothing changes for the demo.

## Files
| File | What |
|---|---|
| `make_dataset.py`, `templates_en.py` | Build `data/` from the repo (deterministic) |
| `data/` | `train.jsonl` 4,117 · `val.jsonl` 350 · `test.jsonl` 605 · `stats.json` · dataset card `README.md` |
| `NimbusPay_FineTune_Colab.ipynb` | The Colab notebook (built by `build_notebook.py`; edit that, not the .ipynb) |
| `ft_eval.py` | Model-level metrics, shared by the notebook and the CLI |
| `eval_finetuned.py` | CLI: test-set metrics via Ollama + end-to-end release gate + latency |
| `MODEL_CARD_TEMPLATE.md` | Model card, filled in automatically by the notebook's Hugging Face cell |
| `../tests/test_finetuned.py` | 29 tests with a mocked model (schema, fallback, scope, refusals, injection guard, claim check, number check, dataset hygiene) |

Rebuild after changing intents or guards: `python finetune/make_dataset.py && python finetune/build_notebook.py && python -m pytest tests/test_finetuned.py`.

## Licences
- `Qwen/Qwen2.5-1.5B-Instruct` and `Qwen/Qwen2.5-7B-Instruct`: **Apache 2.0**, commercial use allowed. The stock 3B used in the earlier demo is under the Qwen Research licence (no commercial use), which is why it isn't the fine-tune base.
- llama.cpp: MIT. Ollama: MIT. transformers, peft, accelerate: Apache 2.0.
- Dataset and code: MIT (this repo), all synthetic.
- Your fine-tuned weights inherit Apache 2.0 from the base. Keep its licence and notice if you publish them.

## Honest limits
- **Smoke test, not a real training run:** the whole notebook was executed on a CPU box (no GPU) with `NP_SMOKE=1`: `Qwen2.5-0.5B-Instruct`, 64 training rows, 20 steps, about 5 minutes. Every stage ran: data load, LoRA training (loss 0.51, eval loss 0.52), test-set eval, the end-to-end release gate, merge, and llama.cpp GGUF conversion (f16, 0.99 GB). The q4_k_m quantise step was skipped because the box has no C++ compiler, and the f16 fallback path worked; Colab builds `llama-quantize` itself. As expected for 20 steps, the gate said **FAIL** (golden 13/21, 6 unsafe answers), which shows the gate does catch a bad model. The real numbers come from the Colab run.
- The test set is template-based, so real panel wording will score lower. The gate's golden, probe and unscripted sets are the closest thing to real questions.
- Latency on a laptop CPU will be higher than with rules: one route call, plus one answer call when `FT_ANSWER=1`. Measure it with `eval_finetuned.py`. If it's too slow live, set `FT_ANSWER=0` so the model only routes.
- The number check catches digits, not numbers written as words.
