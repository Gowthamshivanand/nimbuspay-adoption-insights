"""Builds finetune/NimbusPay_FineTune_Colab.ipynb (run: python finetune/build_notebook.py). Edit the cells here, not the .ipynb."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
cells = []
def md(s): cells.append(dict(cell_type="markdown", metadata={}, source=s.strip("\n")))
def code(s): cells.append(dict(cell_type="code", metadata={}, execution_count=None, outputs=[], source=s.strip("\n")))

md("""
# NimbusPay agent brain: LoRA fine-tune on a free Colab T4

Synthetic hobby case study. All data is synthetic and English only; no NimbusPay data is used.

**What this trains:** a small open model (default `Qwen/Qwen2.5-1.5B-Instruct`, Apache 2.0) to do two jobs for the Adoption Insights Agent:
1. **ROUTE / REFUSE**: question + role (+ optional previous question) -> `{"tool": ..., "args": {...}}`, or `refuse` with a reason (write actions, personal data, singling out people, forecasts, causal claims, ungoverned metrics, prompt injection, score gaming), or `none`.
2. **ANSWER**: governed SQL result + citations -> a short answer that uses only numbers in that result.

The app keeps the safety architecture: code guards run first, the JSON is schema-checked, every number in an answer must be in the governed result, and anything that fails falls back to the rules engine.

**How to run:** `Runtime > Change runtime type > T4 GPU`, then `Runtime > Run all`. About 15 to 30 minutes for 1.5B. At the end you get a GGUF file and an Ollama `Modelfile`.
""")
md("## 1. Settings (the model switch is here)")
code(r'''
MODEL_CHOICE = "1.5B"     # "1.5B" (default: fp16 LoRA, ~15-30 min)  or  "7B" (4-bit QLoRA, ~1.5-2.5 h, needs a laptop with ~8 GB free RAM to run)
EPOCHS = None             # None = 2 for 1.5B, 1 for 7B
PUSH_TO_HF = False        # True = upload model + dataset to YOUR Hugging Face account (asks for a token, never stored here)
HF_MODEL_REPO = "nimbuspay-router-qwen2.5-" + MODEL_CHOICE.lower()   # created under your HF username
HF_DATASET_REPO = "nimbuspay-router-data"
REPO = "mohithraghava/nimbuspay-adoption-insights"; BRANCH = "main"
OLLAMA_NAME = "nimbuspay-router"

import os, sys, json, time, subprocess
SMOKE = os.environ.get("NP_SMOKE") == "1"          # local CPU smoke test only (tiny model, 20 steps); leave unset on Colab
BASE_MODEL = {"1.5B": "Qwen/Qwen2.5-1.5B-Instruct", "7B": "Qwen/Qwen2.5-7B-Instruct"}[MODEL_CHOICE]
if SMOKE: BASE_MODEL = os.environ.get("NP_SMOKE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
QLORA = MODEL_CHOICE == "7B" and not SMOKE
EPOCHS = EPOCHS or (2 if MODEL_CHOICE == "1.5B" else 1)
LR, LORA_R, LORA_ALPHA, LORA_DROPOUT, MAX_LEN = 2e-4, 16, 32, 0.05, 768
BATCH, GRAD_ACC = (2, 1) if SMOKE else ((4, 4) if not QLORA else (2, 8))
MAX_STEPS = 20 if SMOKE else -1
WORK = os.environ.get("NP_WORK", "/content" if os.path.isdir("/content") else os.path.abspath("ft_work"))
os.makedirs(WORK, exist_ok=True)
def sh(cmd):
    print("$", cmd); r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    print((r.stdout or "")[-3000:], (r.stderr or "")[-3000:]); r.check_returncode(); return r.stdout
print(dict(MODEL_CHOICE=MODEL_CHOICE, BASE_MODEL=BASE_MODEL, QLORA=QLORA, EPOCHS=EPOCHS, SMOKE=SMOKE, WORK=WORK))
''')
md("## 2. GPU check and installs")
code(r'''
import shutil
if shutil.which("nvidia-smi"): print(sh("nvidia-smi --query-gpu=name,memory.total --format=csv"))
elif not SMOKE: raise SystemExit("No GPU. In Colab: Runtime > Change runtime type > T4 GPU, then Run all again.")
if not SMOKE:
    # Versions this notebook was tested with. Colab's own torch (CUDA) is kept.
    sh("pip install -q transformers==5.20.1 peft==0.21.2 accelerate==1.15.0 datasets huggingface_hub" + (" bitsandbytes" if QLORA else ""))
import torch, transformers, peft
print("torch", torch.__version__, "| transformers", transformers.__version__, "| peft", peft.__version__, "| cuda", torch.cuda.is_available())
''')
md("## 3. Get the repo code (prompt builders, number check, eval gate) and the dataset (raw URLs)")
code(r'''
import urllib.request
REPO_DIR = os.environ.get("NP_REPO_DIR") or os.path.join(WORK, "repo")
if not os.path.isdir(os.path.join(REPO_DIR, "app")):
    sh(f"git clone -q --depth 1 -b {BRANCH} https://github.com/{REPO}.git {REPO_DIR}")
DATA = os.path.join(WORK, "data"); os.makedirs(DATA, exist_ok=True)
for name in ("train", "val", "test"):
    dst = os.path.join(DATA, name + ".jsonl")
    if os.path.exists(dst): continue
    local = os.path.join(REPO_DIR, "finetune", "data", name + ".jsonl")
    if SMOKE and os.path.exists(local): shutil.copy(local, dst); continue
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/finetune/data/{name}.jsonl"
    print("downloading", url); urllib.request.urlretrieve(url, dst)
sys.path[:0] = [REPO_DIR, os.path.join(REPO_DIR, "finetune"), os.path.join(REPO_DIR, "tools")]
os.environ["NP_BRAIN"] = "rules"
from app import finetuned as FT, agent as A
import ft_eval as E
load = lambda n: [json.loads(l) for l in open(os.path.join(DATA, n + ".jsonl"), encoding="utf-8")]
train, val, test = load("train"), load("val"), load("test")
if SMOKE:
    import random; random.Random(0).shuffle(train)
    train, val = train[:64], val[:16]
    test = [r for r in test if r["source"] in ("golden",)][:12] + [r for r in test if r["task"] == "answer"][:4]
from collections import Counter
for n, rows in (("train", train), ("val", val), ("test", test)):
    print(n, len(rows), dict(Counter(r["task"] for r in rows)))
print("Test sources:", dict(Counter(r["source"].split(":")[0] for r in test)))
''')
md("## 4. Look at one training example (prompt format)")
code(r'''
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(BASE_MODEL)
if tok.pad_token is None: tok.pad_token = tok.eos_token
ex = next(r for r in train if r["task"] == "route")
print(tok.apply_chat_template(ex["messages"], tokenize=False)[-600:])
ex = next(r for r in train if r["task"] == "answer")
print(ex["messages"][1]["content"][:700], "\n--- target ---\n", ex["messages"][2]["content"])
''')
md("## 5. Tokenise (loss only on the assistant reply)")
code(r'''
END = "<|im_end|>"          # Qwen2.5 chat turn terminator (also the eos token of the Instruct models)
def encode(rec):
    prompt = tok.apply_chat_template(rec["messages"][:-1], tokenize=False, add_generation_prompt=True)
    p = tok(prompt, add_special_tokens=False)["input_ids"]
    t = tok(rec["messages"][-1]["content"] + END + "\n", add_special_tokens=False)["input_ids"]
    ids, labels = (p + t)[:MAX_LEN], ([-100] * len(p) + t)[:MAX_LEN]
    return dict(input_ids=ids, attention_mask=[1] * len(ids), labels=labels)
train_enc = [encode(r) for r in train]; val_enc = [encode(r) for r in val]
lens = sorted(len(x["input_ids"]) for x in train_enc)
print("train tokens:", sum(lens), "| max len", lens[-1], "| truncated rows", sum(l >= MAX_LEN for l in lens))

class Collate:
    def __call__(self, batch):
        n = max(len(b["input_ids"]) for b in batch); pad = tok.pad_token_id
        f = lambda k, v: torch.tensor([b[k] + [v] * (n - len(b[k])) for b in batch])
        return dict(input_ids=f("input_ids", pad), attention_mask=f("attention_mask", 0), labels=f("labels", -100))
''')
md("## 6. Load the base model and add LoRA")
code(r'''
from transformers import AutoModelForCausalLM
from peft import LoraConfig, get_peft_model
use_cuda = torch.cuda.is_available()
if QLORA:
    from transformers import BitsAndBytesConfig
    from peft import prepare_model_for_kbit_training
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=bnb, device_map={"": 0}, dtype=torch.float16)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
else:
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.float16 if use_cuda else torch.bfloat16,
                                                 device_map={"": 0} if use_cuda else None, low_cpu_mem_usage=True)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False}); model.enable_input_require_grads()
model.config.use_cache = False
lcfg = LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT, bias="none", task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lcfg)
for n_, p_ in model.named_parameters():          # LoRA weights in fp32 so fp16 mixed precision can unscale gradients
    if p_.requires_grad: p_.data = p_.data.float()
model.print_trainable_parameters()
''')
md("## 7. Train")
code(r'''
import inspect
from transformers import Trainer, TrainingArguments
steps_per_epoch = max(1, len(train_enc) // (BATCH * GRAD_ACC))
total = MAX_STEPS if MAX_STEPS > 0 else steps_per_epoch * EPOCHS
kw = dict(output_dir=os.path.join(WORK, "ckpt"), per_device_train_batch_size=BATCH, per_device_eval_batch_size=BATCH,
          gradient_accumulation_steps=GRAD_ACC, num_train_epochs=EPOCHS, max_steps=MAX_STEPS, learning_rate=LR,
          lr_scheduler_type="cosine", warmup_steps=max(1, int(0.03 * total)), weight_decay=0.0, logging_steps=5 if SMOKE else 10,
          eval_strategy="steps", eval_steps=10 if SMOKE else max(20, total // 6), save_strategy="no", report_to="none",
          fp16=use_cuda, remove_unused_columns=False, dataloader_num_workers=0, seed=7, use_cpu=not use_cuda)
sig = inspect.signature(TrainingArguments.__init__).parameters
if "train_sampling_strategy" in sig: kw["train_sampling_strategy"] = "group_by_length"   # transformers 5
elif "group_by_length" in sig: kw["group_by_length"] = True
args = TrainingArguments(**{k: v for k, v in kw.items() if k in sig})
trainer = Trainer(model=model, args=args, train_dataset=train_enc, eval_dataset=val_enc, data_collator=Collate())
t0 = time.time(); out = trainer.train(); TRAIN_MIN = (time.time() - t0) / 60
print(f"trained {out.global_step} steps in {TRAIN_MIN:.1f} min, final train loss {out.training_loss:.4f}")
print("eval:", trainer.evaluate())
ADAPTER_DIR = os.path.join(WORK, "adapter"); model.save_pretrained(ADAPTER_DIR); tok.save_pretrained(ADAPTER_DIR)
''')
md("## 8. Evaluate on the held-out test set (model only, no guards in front)\nRouting accuracy, refusal precision / recall, unsafe routes, number faithfulness of answers, broken down by source and wording style. The rules engine is scored on the same rows for comparison.")
code(r'''
model.eval(); model.config.use_cache = True
if hasattr(model, "gradient_checkpointing_disable"): model.gradient_checkpointing_disable()
tok.padding_side = "left"
@torch.no_grad()
def generate_batch(msgs_list, max_new):
    texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in msgs_list]
    enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
    out = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id)
    return [tok.decode(o[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for o in out]
MAXNEW = {"route": 48, "answer": 200}
preds = [None] * len(test); t0 = time.time(); B = 4 if SMOKE else 16
for task in ("route", "answer"):
    idx = [i for i, r in enumerate(test) if r["task"] == task]
    for s in range(0, len(idx), B):
        chunk = idx[s:s + B]
        for i, p in zip(chunk, generate_batch([test[i]["messages"][:-1] for i in chunk], MAXNEW[task])): preds[i] = p
print(f"generated {len(test)} in {time.time() - t0:.0f}s")
REPORT = dict(base_model=BASE_MODEL, qlora=QLORA, epochs=EPOCHS, train_rows=len(train), smoke=SMOKE, model=E.score(test, preds),
              rules_on_same_route_rows=E.rules_baseline(test))
E.print_report(REPORT["model"])
print("\nRules engine on the same route rows: tool acc", REPORT["rules_on_same_route_rows"]["tool_acc"], "%")
for r, p in list(zip(test, preds))[:6]: print(f"[{r['task']}] {r['question'][:70]!r}\n   gold: {r['messages'][-1]['content'][:120]}\n   pred: {p[:120]}")
''')
md("## 9. Release gate, end to end through the real Agent (guards first)\nShip only if: golden and the 29 probes >= rules, the 64 unscripted >= rules, 0 unsafe answers, 100% number faithfulness. Latency here is on the Colab GPU with transformers, not on your PC.")
code(r'''
import eval_finetuned as EF
FT.FT_GENERATE = lambda messages, kind: generate_batch([messages], MAXNEW[kind])[0]   # plug this model into the app's finetuned brain
if SMOKE: os.environ["FT_ANSWER"] = "0"      # CPU smoke run: routing only, to keep it short
rules = EF.run_suite("rules"); ft = EF.run_suite("finetuned")
GATE_PASS = EF.print_gate(ft, rules)
REPORT.update(gate_rules=rules, gate_finetuned=ft, gate=EF.gate(ft, rules)[1], gate_pass=GATE_PASS)
json.dump(REPORT, open(os.path.join(WORK, "eval_report.json"), "w"), indent=1)
FT.FT_GENERATE = None; os.environ["NP_BRAIN"] = "rules"
''')
md("## 10. Merge and export GGUF (q4_k_m) for Ollama\n1.5B: LoRA is merged into the base, converted with llama.cpp and quantised to q4_k_m (~1 GB). 7B: the 4-bit base cannot be merged on a free T4, so the LoRA adapter is converted to GGUF and Ollama applies it on top of its own `qwen2.5:7b-instruct`.")
code(r'''
EXPORT = os.path.join(WORK, "export"); os.makedirs(EXPORT, exist_ok=True)
LCPP = os.path.join(WORK, "llama.cpp")
if not os.path.isdir(LCPP): sh(f"git clone -q --depth 1 https://github.com/ggml-org/llama.cpp {LCPP}")
sh(f"pip install -q {LCPP}/gguf-py sentencepiece protobuf")
if not QLORA:
    merged = model.merge_and_unload(); MERGED = os.path.join(WORK, "merged")
    merged.save_pretrained(MERGED, safe_serialization=True); tok.save_pretrained(MERGED)
    del merged
    F16 = os.path.join(WORK, f"{OLLAMA_NAME}-f16.gguf")
    sh(f"python {LCPP}/convert_hf_to_gguf.py {MERGED} --outfile {F16} --outtype f16")
    GGUF = os.path.join(EXPORT, f"{OLLAMA_NAME}-q4_k_m.gguf")
    try:
        if not SMOKE:
            sh(f"cmake -S {LCPP} -B {LCPP}/build -DGGML_CUDA=OFF -DLLAMA_CURL=OFF > /dev/null && cmake --build {LCPP}/build --target llama-quantize -j 4 > /dev/null")
        sh(f"{LCPP}/build/bin/llama-quantize {F16} {GGUF} Q4_K_M")
    except Exception as e:
        print("q4_k_m quantise step failed or skipped:", e, "\nFalling back to the f16 GGUF; quantise it on your PC with: ollama create -q q4_K_M ...")
        GGUF = os.path.join(EXPORT, os.path.basename(F16)); shutil.move(F16, GGUF)
    modelfile = f'FROM ./{os.path.basename(GGUF)}\n'
    modelfile += 'TEMPLATE """{{- range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{ end }}<|im_start|>assistant\n"""\n'
else:
    GGUF = os.path.join(EXPORT, f"{OLLAMA_NAME}-7b-lora.gguf")
    sh(f"python {LCPP}/convert_lora_to_gguf.py {ADAPTER_DIR} --base-model-id {BASE_MODEL} --outfile {GGUF} --outtype f16")
    modelfile = f"FROM qwen2.5:7b-instruct\nADAPTER ./{os.path.basename(GGUF)}\n"
modelfile += 'PARAMETER temperature 0\nPARAMETER stop "<|im_end|>"\nPARAMETER num_ctx 2048\n'
open(os.path.join(EXPORT, "Modelfile"), "w").write(modelfile)
shutil.copy(os.path.join(WORK, "eval_report.json"), EXPORT)
print(modelfile); print(sh(f"ls -la {EXPORT}"))
''')
md("## 11. (Optional) Push the model and dataset to your Hugging Face account\nSet `PUSH_TO_HF = True` in cell 1. You will be asked for a **write** token from https://huggingface.co/settings/tokens. Nothing is hard-coded or saved in this notebook.")
code(r'''
if PUSH_TO_HF and not SMOKE:
    from huggingface_hub import login, whoami, HfApi
    login()                                   # paste your token in the prompt
    user = whoami()["name"]; api = HfApi()
    card = open(os.path.join(REPO_DIR, "finetune", "MODEL_CARD_TEMPLATE.md"), encoding="utf-8").read()
    rm, ra = REPORT["model"]["route"], REPORT["model"]["answer"]
    fill = {"{{BASE_MODEL}}": BASE_MODEL, "{{METHOD}}": "QLoRA 4-bit" if QLORA else "LoRA fp16", "{{EPOCHS}}": str(EPOCHS),
            "{{TRAIN_ROWS}}": str(len(train)), "{{TOOL_ACC}}": str(rm["tool_acc"]), "{{EXACT_ACC}}": str(rm["exact_acc"]),
            "{{REF_P}}": str(rm["refusal_precision"]), "{{REF_R}}": str(rm["refusal_recall"]), "{{UNSAFE}}": str(rm["unsafe_routes"]),
            "{{FAITHFUL}}": str(ra["number_faithful_pct"]), "{{RULES_ACC}}": str(REPORT["rules_on_same_route_rows"]["tool_acc"]),
            "{{GATE}}": "PASS" if REPORT.get("gate_pass") else "FAIL", "{{HF_USER}}": user}
    for k, v in fill.items(): card = card.replace(k, v)
    open(os.path.join(EXPORT, "README.md"), "w").write(card)
    mid = f"{user}/{HF_MODEL_REPO}"; api.create_repo(mid, exist_ok=True)
    api.upload_folder(folder_path=EXPORT, repo_id=mid); api.upload_folder(folder_path=ADAPTER_DIR, repo_id=mid, path_in_repo="lora_adapter")
    did = f"{user}/{HF_DATASET_REPO}"; api.create_repo(did, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=DATA, repo_id=did, repo_type="dataset")
    api.upload_file(path_or_fileobj=os.path.join(REPO_DIR, "finetune", "data", "README.md"), path_in_repo="README.md", repo_id=did, repo_type="dataset")
    print("Model:", f"https://huggingface.co/{mid}", "\nDataset:", f"https://huggingface.co/datasets/{did}")
else:
    print("Skipped (PUSH_TO_HF is False).")
''')
md("## 12. Download the GGUF + Modelfile to your PC\nThen on Windows, in the folder with both files: `ollama create nimbuspay-router -f Modelfile` and test with `python finetune/eval_finetuned.py` in the repo.")
code(r'''
if not SMOKE:
    sh(f"cd {WORK} && zip -j -0 nimbuspay-router-export.zip {EXPORT}/*")
    try:
        from google.colab import files
        files.download(os.path.join(WORK, "nimbuspay-router-export.zip"))
    except Exception as e:
        print("Download from the Files panel on the left instead:", os.path.join(WORK, "nimbuspay-router-export.zip"), e)
''')

nb = dict(cells=cells, metadata={"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
          "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}}, nbformat=4, nbformat_minor=5)
for i, c in enumerate(nb["cells"]): c["id"] = f"cell-{i:02d}"
json.dump(nb, open(os.path.join(HERE, "NimbusPay_FineTune_Colab.ipynb"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("wrote", os.path.join(HERE, "NimbusPay_FineTune_Colab.ipynb"), len(cells), "cells")
