---
license: apache-2.0
base_model: {{BASE_MODEL}}
language: [en]
tags: [lora, routing, tool-use, refusal, synthetic-data, gguf, ollama]
datasets: [{{HF_USER}}/nimbuspay-router-data]
---
# nimbuspay-router ({{BASE_MODEL}} + {{METHOD}})

**Hobby project, synthetic data only.** This is the router and answer writer for the NimbusPay Adoption Insights Agent, a case-study app at
https://github.com/mohithraghava/nimbuspay-adoption-insights. It has no link to the real NimbusPay or any real company.

## What it does
1. **Route:** question + role (+ previous question) -> `{"tool": ..., "args": {...}}`, one of 30 governed tools, `refuse` with a reason, or `none`.
2. **Answer:** governed SQL result + citations -> short answer text using only numbers in that result.

It is **not** a general assistant. Use it only behind the app's code, because the app keeps the controls:
- the code guards run before the model;
- the model's JSON is schema-checked and its args are validated against the data and the caller's role scope;
- every number in a model answer must appear in the governed result, otherwise the template answer is shown;
- any failure falls back to the deterministic rules engine.

## Training
- Base: `{{BASE_MODEL}}` (Apache 2.0). Method: {{METHOD}}, r=16, alpha=32, all attention and MLP projections, {{EPOCHS}} epoch(s), lr 2e-4 cosine, max length 768.
- Data: {{TRAIN_ROWS}} English rows: synthetic NimbusPay rows (`finetune/make_dataset.py`) plus, if enabled, an attributed public sample (`finetune/make_public.py`; licences and attributions in the dataset card, combined public file CC-BY-SA-4.0). Loss on the assistant reply only.
- Hardware: Google Colab free T4.

## Evaluation (held-out test set, model only, no guards in front)
| Metric | Value |
|---|---|
| Tool accuracy | {{TOOL_ACC}}% (rules engine on the same rows: {{RULES_ACC}}%) |
| Exact (tool + args) | {{EXACT_ACC}}% |
| Refusal precision / recall | {{REF_P}}% / {{REF_R}}% |
| Unsafe routes (should refuse, picked a data tool) | {{UNSAFE}} |
| Answer number faithfulness | {{FAITHFUL}}% |
| End-to-end release gate (golden, probes, unscripted >= rules, 0 unsafe, 100% faithful) | **{{GATE}}** |

## Use with Ollama
```
ollama create nimbuspay-router -f Modelfile
set NP_BRAIN=finetuned        (PowerShell: $env:NP_BRAIN="finetuned")
python -m app
```

## Limits
- English only. Trained on templates, so real-world wording will score lower than the test set.
- It can still mis-route. The code checks catch unsafe and unfaithful output, but a wrong-but-safe tool choice gives a correct answer to a different question.
- Numbers written as words ("fifteen") are not caught by the number check. The app rejects only digit numbers that are not in the result.
