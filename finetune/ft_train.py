"""Shared training / eval / export pipeline for the NimbusPay router fine-tune, used by finetune/modal/train_modal.py
(Modal GPU) and runnable locally as a CPU dry run (python finetune/ft_train.py --smoke).

It mirrors the Colab notebook (finetune/build_notebook.py) step for step, so a Modal run is comparable with Colab run 2:
same v4 data files (train / val / test / public_train / public_eval), same chat format (Qwen2.5 chat template, loss only on
the assistant reply), same LoRA targets, same early stopping on validation loss every EVAL_EVERY steps with the best
checkpoint restored, and the same evaluation code (ft_eval.score / fresh_summary / hybrid_preds and the end-to-end release
gate in eval_finetuned.run_suite). Differences from Colab, on purpose:
  * bf16 LoRA (A100 / H100 support bf16; the T4 needed fp16). QLORA=True keeps the 4-bit option.
  * The full planned epochs run (2 by default), with a configurable time cap instead of Colab's 88-minute session cap.
  * 7B is merged into the base before GGUF export (enough GPU memory on Modal), so Ollama gets one self-contained file.
Heavy imports (torch, transformers, peft) happen inside functions, so this file imports on a machine without them."""
import os
import argparse, json, os, shutil, subprocess, sys, time
from dataclasses import dataclass, field, asdict

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
BASE_MODELS = {"1.5B": "Qwen/Qwen2.5-1.5B-Instruct", "7B": "Qwen/Qwen2.5-7B-Instruct"}
OLLAMA_NAMES = {"1.5B": "gowtham-nimbuspay-agent", "7B": "gowtham-nimbuspay-agent-7b"}
# Modal GPU prices per second (modal.com/pricing, read 19 Oct 2026). GPU only: CPU and RAM are billed on top (small).
GPU_USD_PER_S = {"H100": 0.001097, "A100-80GB": 0.000694, "A100-40GB": 0.000583, "L40S": 0.000542, "A10": 0.000306,
                 "L4": 0.000222, "CPU": 0.0}
CPU_CORE_USD_PER_S, MEM_GIB_USD_PER_S = 0.0000131, 0.00000222      # same page: per physical core / per GiB, billed on what is requested
# Colab run 2 (1.5B, T4) measured results: the 7B must beat these to replace it (see finetune/modal/README.md).
RUN2_BASELINE = dict(heldout_tool_acc=88.2, fresh_tool_acc=83.5, unsafe_routes=19)
CHAT_TEMPLATE_OLLAMA = 'TEMPLATE """{{- range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{ end }}<|im_start|>assistant\n"""\n'


@dataclass
class Config:
    model_choice: str = "7B"            # "7B" or "1.5B"
    qlora: bool = False                 # 4-bit QLoRA (optional; bf16 LoRA is the default on A100 / H100)
    epochs: int = 2
    use_public: bool = True
    lr: float = 2e-4
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    max_len: int = 768
    eval_every: int = 100
    patience: int = 3                   # evals without a better val loss before stopping
    val_eval_rows: int = 400
    batch: int = 4
    grad_acc: int = 4                   # effective batch 16, same as Colab 1.5B
    max_steps: int = -1
    time_budget_min: float = 150.0      # training stops cleanly here (best checkpoint kept); the Modal timeout is separate
    gen_batch: int = 16
    smoke: bool = False
    smoke_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    work: str = "ft_work"
    repo_dir: str = ROOT
    data_dir: str = ""
    gpu: str = "A100-80GB"
    seed: int = 7
    ollama_name: str = ""
    base_model: str = ""
    extra: dict = field(default_factory=dict)

    def finalize(self):
        if self.model_choice not in BASE_MODELS: raise ValueError("model_choice must be 7B or 1.5B")
        self.base_model = self.base_model or (self.smoke_model if self.smoke else BASE_MODELS[self.model_choice])
        self.ollama_name = self.ollama_name or OLLAMA_NAMES[self.model_choice]
        self.data_dir = self.data_dir or os.path.join(self.repo_dir, "finetune", "data")
        if self.smoke:
            self.batch, self.grad_acc, self.max_steps, self.eval_every, self.gen_batch, self.qlora = 2, 1, 12, 6, 4, False
        if self.qlora and self.batch * self.grad_acc == 16 and self.batch == 4: self.batch, self.grad_acc = 2, 8
        os.makedirs(self.work, exist_ok=True)
        return self


def cost_usd(seconds, gpu, cores=0, mem_gib=0):
    """Estimate from elapsed seconds: GPU + requested CPU cores + requested RAM (Modal bills the higher of requested and used)."""
    per_s = GPU_USD_PER_S.get(gpu, 0.0) + cores * CPU_CORE_USD_PER_S + mem_gib * MEM_GIB_USD_PER_S
    return round(seconds * per_s, 2)


def cost_line(seconds, gpu, what="this run", cores=0, mem_gib=0):
    extra = f" + {cores} cores + {mem_gib} GiB RAM" if cores or mem_gib else ""
    return (f"Estimated cost for {what}: {seconds / 60:.1f} min on {gpu}{extra} = ${cost_usd(seconds, gpu, cores, mem_gib):.2f} "
            f"(GPU alone ${cost_usd(seconds, gpu):.2f}). Estimate from list prices; the Modal dashboard Usage page is the real figure.")


def sh(cmd, check=True):
    print("$", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    print((r.stdout or "")[-3000:], (r.stderr or "")[-3000:], flush=True)
    if check: r.check_returncode()
    return r.stdout


def _paths(cfg):
    for p in (cfg.repo_dir, os.path.join(cfg.repo_dir, "finetune"), os.path.join(cfg.repo_dir, "tools")):
        if p not in sys.path: sys.path.insert(0, p)
    os.environ["NP_BRAIN"] = "rules"


# ---------- data (same as notebook cell 3) ----------
def load_data(cfg):
    import random
    _paths(cfg)
    load = lambda n: [json.loads(l) for l in open(os.path.join(cfg.data_dir, n + ".jsonl"), encoding="utf-8")]
    train, val, test, public_eval = load("train"), load("val"), load("test"), load("public_eval")
    if cfg.use_public:
        train = train + load("public_train"); random.Random(1).shuffle(train)
    if cfg.smoke:
        random.Random(0).shuffle(train)
        train, val, public_eval = train[:48], val[:12], public_eval[:6]
        test = ([r for r in test if r["source"] == "golden"][:6] + [r for r in test if r.get("source") == "fresh_wording" and r["task"] == "route"][:4]
                + [r for r in test if r["task"] == "answer"][:3])
    from collections import Counter
    for n, rows in (("train", train), ("val", val), ("test", test), ("public_eval", public_eval)):
        print(n, len(rows), dict(Counter(r["task"] for r in rows)), flush=True)
    return train, val, test, public_eval


# ---------- tokenise (same as notebook cell 5: loss only on the assistant reply) ----------
END = "<|im_end|>"


def encode_fn(tok, max_len):
    def encode(rec):
        prompt = tok.apply_chat_template(rec["messages"][:-1], tokenize=False, add_generation_prompt=True)
        p = tok(prompt, add_special_tokens=False)["input_ids"]
        t = tok(rec["messages"][-1]["content"] + END + "\n", add_special_tokens=False)["input_ids"]
        ids, labels = (p + t)[:max_len], ([-100] * len(p) + t)[:max_len]
        return dict(input_ids=ids, attention_mask=[1] * len(ids), labels=labels)
    return encode


class Collate:
    def __init__(self, pad_id): self.pad = pad_id

    def __call__(self, batch):
        import torch
        n = max(len(b["input_ids"]) for b in batch)
        f = lambda k, v: torch.tensor([b[k] + [v] * (n - len(b[k])) for b in batch])
        return dict(input_ids=f("input_ids", self.pad), attention_mask=f("attention_mask", 0), labels=f("labels", -100))


# ---------- model ----------
def load_model(cfg):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    tok = AutoTokenizer.from_pretrained(cfg.base_model)
    if tok.pad_token is None: tok.pad_token = tok.eos_token
    cuda = torch.cuda.is_available()
    bf16 = cuda and torch.cuda.is_bf16_supported()
    # CPU (smoke only): fp32, and cap threads to the cores we pay for; a
    # container sees all host cores and bf16 on old CPUs is emulated (slow).
    dtype = torch.bfloat16 if bf16 else (torch.float16 if cuda else torch.float32)
    if not cuda:
        torch.set_num_threads(int(os.environ.get("NP_CPU_THREADS", "4")))
    if cfg.qlora:
        from transformers import BitsAndBytesConfig
        from peft import prepare_model_for_kbit_training
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
        model = AutoModelForCausalLM.from_pretrained(cfg.base_model, quantization_config=bnb, device_map={"": 0}, dtype=dtype)
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(cfg.base_model, dtype=dtype, device_map={"": 0} if cuda else None, low_cpu_mem_usage=True)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False}); model.enable_input_require_grads()
    model.config.use_cache = False
    lcfg = LoraConfig(r=cfg.lora_r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lcfg)
    if dtype == torch.float16:                        # fp16 AMP needs fp32 master LoRA weights (Colab T4 path)
        for _, p in model.named_parameters():
            if p.requires_grad: p.data = p.data.float()
    model.print_trainable_parameters()
    return model, tok, dict(cuda=cuda, bf16=bf16, dtype=str(dtype))


# ---------- train (same as notebook cell 7, full epochs + time cap) ----------
def train(cfg, model, tok, train_rows, val_rows, hw):
    import inspect, random
    from transformers import Trainer, TrainingArguments, EarlyStoppingCallback, TrainerCallback
    encode = encode_fn(tok, cfg.max_len)
    train_enc = [encode(r) for r in train_rows]; val_enc = [encode(r) for r in val_rows]
    lens = sorted(len(x["input_ids"]) for x in train_enc)
    print("train tokens:", sum(lens), "| max len", lens[-1], "| truncated rows", sum(l >= cfg.max_len for l in lens), flush=True)
    steps_per_epoch = max(1, len(train_enc) // (cfg.batch * cfg.grad_acc))
    total = cfg.max_steps if cfg.max_steps > 0 else steps_per_epoch * cfg.epochs
    kw = dict(output_dir=os.path.join(cfg.work, "ckpt"), per_device_train_batch_size=cfg.batch, per_device_eval_batch_size=cfg.batch * 2,
              gradient_accumulation_steps=cfg.grad_acc, num_train_epochs=cfg.epochs, max_steps=cfg.max_steps, learning_rate=cfg.lr,
              lr_scheduler_type="cosine", warmup_steps=max(1, int(0.03 * total)), weight_decay=0.01, logging_steps=5 if cfg.smoke else 10,
              eval_strategy="steps", eval_steps=cfg.eval_every, save_strategy="steps", save_steps=cfg.eval_every,
              save_total_limit=2, load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False, report_to="none",
              bf16=hw["cuda"] and hw["bf16"], fp16=hw["cuda"] and not hw["bf16"], remove_unused_columns=False, dataloader_num_workers=0,
              seed=cfg.seed, use_cpu=not hw["cuda"])
    sig = inspect.signature(TrainingArguments.__init__).parameters
    if "train_sampling_strategy" in sig: kw["train_sampling_strategy"] = "group_by_length"
    elif "group_by_length" in sig: kw["group_by_length"] = True
    args = TrainingArguments(**{k: v for k, v in kw.items() if k in sig})

    class TimeBudget(TrainerCallback):
        def on_train_begin(self, a, state, control, **k): self.t0 = time.time(); self.hit = False
        def on_step_end(self, a, state, control, **k):
            if not self.hit and (time.time() - self.t0) / 60 >= cfg.time_budget_min:
                self.hit = True; control.should_evaluate = True; control.should_save = True; control.should_training_stop = True
            return control

    val_eval = random.Random(3).sample(val_enc, min(cfg.val_eval_rows, len(val_enc)))
    budget = TimeBudget()
    trainer = Trainer(model=model, args=args, train_dataset=train_enc, eval_dataset=val_eval, data_collator=Collate(tok.pad_token_id),
                      callbacks=[EarlyStoppingCallback(early_stopping_patience=cfg.patience), budget])
    t0 = time.time(); out = trainer.train(); minutes = (time.time() - t0) / 60
    stop = "time budget" if budget.hit else ("early stopping" if out.global_step < total else "all epochs")
    print(f"trained {out.global_step}/{total} steps in {minutes:.1f} min ({stop}), final train loss {out.training_loss:.4f}", flush=True)
    print("best checkpoint:", trainer.state.best_model_checkpoint, "best val loss:", trainer.state.best_metric, flush=True)
    adapter = os.path.join(cfg.work, "adapter"); model.save_pretrained(adapter); tok.save_pretrained(adapter)
    return dict(train_minutes=round(minutes, 1), train_tokens=sum(lens), train_steps=out.global_step, planned_steps=total,
                steps_per_epoch=steps_per_epoch, stop_reason=stop, best_val_loss=trainer.state.best_metric,
                final_train_loss=round(out.training_loss, 4), adapter_dir=adapter, log_history=trainer.state.log_history[-40:])


# ---------- generation + eval (same as notebook cells 8 and 9) ----------
MAXNEW = {"route": 48, "answer": 200}


def make_generator(model, tok):
    import torch
    model.eval(); model.config.use_cache = True
    if hasattr(model, "gradient_checkpointing_disable"): model.gradient_checkpointing_disable()
    tok.padding_side = "left"

    @torch.no_grad()
    def generate_batch(msgs_list, max_new):
        texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in msgs_list]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        out = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id)
        return [tok.decode(o[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip() for o in out]
    return generate_batch


def evaluate(cfg, generate_batch, test, public_eval, meta):
    """Model metrics on the held-out test (incl. fresh wording), public eval, hybrid tool accuracy, then the rules / hybrid /
    pure release gates end to end through the real Agent. Returns the report dict (same keys as the Colab eval_report.json)."""
    _paths(cfg)
    from app import finetuned as FT
    import ft_eval as E, eval_finetuned as EF
    preds = [None] * len(test); t0 = time.time(); B = cfg.gen_batch
    for task in ("route", "answer"):
        idx = [i for i, r in enumerate(test) if r["task"] == task]
        for s in range(0, len(idx), B):
            chunk = idx[s:s + B]
            for i, p in zip(chunk, generate_batch([test[i]["messages"][:-1] for i in chunk], MAXNEW[task])): preds[i] = p
    gen_s = time.time() - t0
    print(f"generated {len(test)} test rows in {gen_s:.0f}s", flush=True)
    pub = []
    for s in range(0, len(public_eval), B): pub += generate_batch([r["messages"][:-1] for r in public_eval[s:s + B]], MAXNEW["route"])
    rep = dict(meta, test_generation_s=round(gen_s, 1), model=E.score(test, preds), rules_on_same_route_rows=E.rules_baseline(test),
               public_eval=E.score(public_eval, pub)["route"])
    E.print_report(rep["model"])
    rep["fresh_wording"] = E.fresh_summary(test, preds); E.print_fresh(rep["fresh_wording"])
    rep["hybrid_route"] = E.score(test, E.hybrid_preds(test, preds))["route"]
    pe = rep["public_eval"]; print(f"Public eval (n={pe['n']}): tool acc {pe['tool_acc']}%, refusal recall {pe['refusal_recall']}%", flush=True)
    print("Hybrid tool acc", rep["hybrid_route"]["tool_acc"], "% | rules", rep["rules_on_same_route_rows"]["tool_acc"], "%", flush=True)
    FT.FT_GENERATE = lambda messages, kind: generate_batch([messages], MAXNEW[kind])[0]
    os.environ["FT_ANSWER"] = "0"
    try:
        rules = EF.run_suite("rules"); ft = EF.run_suite("finetuned", "hybrid"); ft_pure = EF.run_suite("finetuned", "pure")
        gp, gpp = EF.print_gate(ft, rules), EF.print_gate(ft_pure, rules)
    finally:
        FT.FT_GENERATE = None; os.environ["NP_BRAIN"] = "rules"; os.environ["FT_MODE"] = "hybrid"
    rep.update(gate_rules=rules, gate_finetuned=ft, gate_finetuned_pure=ft_pure, gate=EF.gate(ft, rules)[1], gate_pass=gp,
               gate_pure=EF.gate(ft_pure, rules)[1], gate_pure_pass=gpp)
    rep["vs_run2"] = compare_run2(rep)
    print_run2(rep["vs_run2"])
    rep["_preds"] = preds                     # popped by the caller (saved as hf_preds.json for the HF-vs-GGUF agreement)
    return rep


def compare_run2(rep):
    """Release rule for the 7B: pure gate PASS and better than Colab run 2 (1.5B) on held-out tool acc, fresh wording and
    unsafe routes (fewer is better; ties on unsafe count as not worse)."""
    m = rep.get("model", {}).get("route", {}); fr = rep.get("fresh_wording") or {}
    checks = {"pure release gate PASS": bool(rep.get("gate_pure_pass")),
              f"held-out tool acc > {RUN2_BASELINE['heldout_tool_acc']}%": (m.get("tool_acc") or 0) > RUN2_BASELINE["heldout_tool_acc"],
              f"fresh-wording tool acc > {RUN2_BASELINE['fresh_tool_acc']}%": (fr.get("tool_acc") or 0) > RUN2_BASELINE["fresh_tool_acc"],
              f"unsafe routes <= {RUN2_BASELINE['unsafe_routes']}": m.get("unsafe_routes", 10 ** 6) <= RUN2_BASELINE["unsafe_routes"]}
    return dict(baseline=RUN2_BASELINE, checks=checks, use_this_model=all(checks.values()))


def print_run2(v):
    print("\n== Use this model instead of the 1.5B run 2? ==")
    for k, ok in v["checks"].items(): print(("PASS " if ok else "FAIL ") + k)
    print("DECISION:", "USE IT (passes the pure gate and beats run 2)" if v["use_this_model"] else "KEEP the 1.5B run 2 model", flush=True)


# ---------- export (notebook cell 10, merged for both sizes) ----------
def merge_to_dir(cfg, model, tok, adapter_dir):
    """Merged bf16/fp16 HF model. QLoRA: reload the base in 16-bit and apply the saved adapter (4-bit weights can't merge cleanly)."""
    import torch
    merged_dir = os.path.join(cfg.work, "merged")
    if cfg.qlora:
        from transformers import AutoModelForCausalLM
        from peft import PeftModel
        del model; torch.cuda.empty_cache()
        base = AutoModelForCausalLM.from_pretrained(cfg.base_model, dtype=torch.bfloat16, device_map={"": 0} if torch.cuda.is_available() else None)
        merged = PeftModel.from_pretrained(base, adapter_dir).merge_and_unload()
    else:
        merged = model.merge_and_unload()
    merged.save_pretrained(merged_dir, safe_serialization=True); tok.save_pretrained(merged_dir)
    del merged
    return merged_dir


def modelfile_text(gguf_name):
    """Ollama Modelfile. The TEMPLATE renders exactly what tokenizer.apply_chat_template(..., add_generation_prompt=True) renders
    for our [system, user] messages (checked by template_parity). repeat_penalty 1 = plain greedy, like the HF eval."""
    return (f"FROM ./{gguf_name}\n" + CHAT_TEMPLATE_OLLAMA +
            'PARAMETER temperature 0\nPARAMETER repeat_penalty 1\nPARAMETER stop "<|im_end|>"\nPARAMETER num_ctx 2048\n')


QUANT_TYPES = {"q8_0": "Q8_0", "q5_k_m": "Q5_K_M", "q4_k_m": "Q4_K_M", "f16": None}
SHIP_DEFAULT = {"1.5B": "q8_0", "7B": "q8_0"}
EVAL_QUANTS_DEFAULT = {"1.5B": ["f16", "q8_0", "q4_k_m"], "7B": ["q8_0", "q5_k_m", "q4_k_m"]}


def gguf_name(cfg_or_name, quant):
    name = cfg_or_name if isinstance(cfg_or_name, str) else cfg_or_name.ollama_name
    return f"{name}-{quant}.gguf"


def export_ggufs(name, merged_dir, out_dir, llama_cpp, quants=("q8_0",)):
    """f16 GGUF (convert_hf_to_gguf.py) + each requested quant (llama-quantize) + one Modelfile per file (Modelfile.<quant>).
    Returns {quant: path}. f16 is always kept: it is the reference for the quantisation-loss comparison."""
    os.makedirs(out_dir, exist_ok=True); out = {}
    f16 = os.path.join(out_dir, gguf_name(name, "f16"))
    if not os.path.exists(f16):
        sh(f"{sys.executable} {llama_cpp}/convert_hf_to_gguf.py {merged_dir} --outfile {f16} --outtype f16")
    out["f16"] = f16
    qbin = next((p for p in (os.path.join(llama_cpp, "build", "bin", "llama-quantize"), shutil.which("llama-quantize") or "") if p and os.path.exists(p)), None)
    for q in quants:
        if q == "f16": continue
        dst = os.path.join(out_dir, gguf_name(name, q))
        if not qbin: print("llama-quantize not built; skipping", q); continue
        if not os.path.exists(dst): sh(f"{qbin} {f16} {dst} {QUANT_TYPES[q]}")
        out[q] = dst
    for q, path in out.items():
        open(os.path.join(out_dir, f"Modelfile.{q}"), "w").write(modelfile_text(os.path.basename(path)))
    for q, path in out.items(): print(f"  {q:7} {os.path.getsize(path) / 2 ** 30:.2f} GiB  {os.path.basename(path)}")
    return out


# ---------- serving parity: is what Ollama runs the same thing we evaluated? ----------
def render_ollama_template(messages):
    """Python rendering of CHAT_TEMPLATE_OLLAMA (range over messages, then the assistant header)."""
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages) + "<|im_start|>assistant\n"


def gguf_metadata(path):
    from gguf import GGUFReader
    r = GGUFReader(path); out = {}
    for k in ("general.architecture", "tokenizer.ggml.add_bos_token", "tokenizer.ggml.bos_token_id", "tokenizer.ggml.eos_token_id",
              "tokenizer.ggml.padding_token_id", "tokenizer.chat_template", "general.file_type"):
        f = r.fields.get(k)
        try: out[k] = f.contents() if f else None
        except Exception: out[k] = None
    return out


def llama_tokenize(llama_cpp, gguf, text):
    """Token ids from llama.cpp's own tokenizer (llama-tokenize, vocab only, special tokens parsed, BOS as the model wants)."""
    import tempfile
    exe = os.path.join(llama_cpp, "build", "bin", "llama-tokenize")
    if not os.path.exists(exe): return None
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f: f.write(text); fn = f.name
    r = subprocess.run([exe, "-m", gguf, "-f", fn, "--ids", "--log-disable"], capture_output=True, text=True)
    line = next((l for l in reversed(r.stdout.strip().splitlines()) if l.startswith("[")), None)
    return json.loads(line) if line else None


def template_parity(tok, rows, gguf=None, llama_cpp=None, n=5):
    """(c) For n test prompts: HF apply_chat_template string == Modelfile TEMPLATE rendering, HF token ids == llama.cpp token ids,
    and the GGUF's BOS / EOS / chat template agree with the HF tokenizer. Returns a dict with ok and details."""
    res = dict(n=0, string_equal=0, ids_equal=0, ids_checked=0, examples=[])
    for r in rows[:n]:
        msgs = r["messages"][:-1]
        hf = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ol = render_ollama_template(msgs)
        hf_ids = tok(hf, add_special_tokens=False)["input_ids"]
        res["n"] += 1; res["string_equal"] += hf == ol
        ll = llama_tokenize(llama_cpp, gguf, hf) if gguf and llama_cpp else None
        if ll is not None:
            res["ids_checked"] += 1; res["ids_equal"] += ll == hf_ids
        if len(res["examples"]) < 1:
            res["examples"].append(dict(hf_prompt_tail=hf[-160:], ollama_prompt_tail=ol[-160:], hf_ids_tail=hf_ids[-12:],
                                        llama_ids_tail=(ll or [])[-12:], hf_len=len(hf_ids), llama_len=len(ll) if ll else None))
    meta = gguf_metadata(gguf) if gguf else {}
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    res["gguf"] = {k: (v if k != "tokenizer.chat_template" else (v == tok.chat_template if v else None)) for k, v in meta.items()}
    res["checks"] = {"HF prompt string == Modelfile template": res["string_equal"] == res["n"],
                     "HF token ids == llama.cpp token ids": (res["ids_equal"] == res["ids_checked"]) if res["ids_checked"] else None,
                     "GGUF adds no BOS (Qwen2.5 has none)": meta.get("tokenizer.ggml.add_bos_token") in (False, None) if gguf else None,
                     "GGUF EOS is <|im_end|>": (meta.get("tokenizer.ggml.eos_token_id") == im_end) if gguf else None,
                     "GGUF chat_template == HF chat_template": res["gguf"].get("tokenizer.chat_template") if gguf else None}
    res["ok"] = all(v is not False for v in res["checks"].values())
    for k, v in res["checks"].items(): print(("PASS " if v else "SKIP " if v is None else "FAIL ") + k)
    if res["examples"]: print("HF prompt tail:", repr(res["examples"][0]["hf_prompt_tail"]), "\nTEMPLATE tail:", repr(res["examples"][0]["ollama_prompt_tail"]))
    return res


def agreement(test, hf_preds, gguf_preds):
    """Share of rows where the GGUF output equals the HF output (normalised JSON for route rows), plus route-label agreement."""
    from app import finetuned as FT
    import ft_eval as E
    exact = label = n = 0
    for r, a, b in zip(test, hf_preds, gguf_preds):
        if r["task"] != "route" or a is None or b is None: continue
        n += 1
        da, db = FT.parse_route(a, E.AGENTS, E.REGIONS), FT.parse_route(b, E.AGENTS, E.REGIONS)
        exact += da == db
        label += (da or {}).get("tool") == (db or {}).get("tool") and (da or {}).get("args", {}).get("reason") == (db or {}).get("args", {}).get("reason")
    return dict(route_rows=n, same_route_pct=round(100 * exact / n, 1) if n else None, same_tool_pct=round(100 * label / n, 1) if n else None)


def side_by_side(hf, ggufs):
    """Compact HF-vs-GGUF table: {name: {held-out tool acc, fresh, unsafe, invalid JSON, answer faithful/recall, hybrid acc, gates}}."""
    def row(rep, model_key="model"):
        m = (rep.get(model_key) or {}).get("route", {}); a = (rep.get(model_key) or {}).get("answer", {}); fr = rep.get("fresh_wording") or {}
        hy = rep.get("hybrid_route") or {}
        gp = rep.get("gate_pass") if "gate_pass" in rep else (rep.get("hybrid") or {}).get("gate_pass")
        gpp = rep.get("gate_pure_pass") if "gate_pure_pass" in rep else (rep.get("pure") or {}).get("gate_pass")
        return dict(tool_acc=m.get("tool_acc"), fresh_tool_acc=fr.get("tool_acc"), unsafe_routes=m.get("unsafe_routes"), invalid_json=m.get("invalid_json"),
                    over_refusals=m.get("over_refusals"), answer_faithful=a.get("number_faithful_pct"), answer_recall=a.get("gold_number_recall_pct"),
                    hybrid_tool_acc=hy.get("tool_acc"), gate_hybrid=gp, gate_pure=gpp)
    t = {"HF (training eval)": row(hf)}
    for q, rep in ggufs.items(): t[f"GGUF {q} (Ollama)"] = dict(row(rep), **{"same_route_as_HF_pct": (rep.get("agreement") or {}).get("same_route_pct")})
    return t


def print_side_by_side(t):
    cols = ["tool_acc", "fresh_tool_acc", "unsafe_routes", "invalid_json", "answer_faithful", "answer_recall", "hybrid_tool_acc", "gate_hybrid", "gate_pure", "same_route_as_HF_pct"]
    print("\n" + "model".ljust(24) + "".join(c[:12].rjust(13) for c in cols))
    for k, v in t.items(): print(k[:24].ljust(24) + "".join(str(v.get(c, "")).rjust(13) for c in cols))


def pick_ship(model_choice, gguf_reports, wanted=None):
    """Ship the requested quant (default q8_0). For 7B, a smaller quant is shipped only if it passes the pure gate and is within
    1 point of q8_0 on held-out tool accuracy with no more unsafe routes."""
    wanted = wanted or SHIP_DEFAULT[model_choice]
    if model_choice != "7B" or "q8_0" not in gguf_reports: return wanted if wanted in gguf_reports else next(iter(gguf_reports), None)
    ref = gguf_reports["q8_0"]["model"]["route"]
    for q in ("q4_k_m", "q5_k_m"):
        g = gguf_reports.get(q)
        if g and (g.get("pure") or {}).get("gate_pass") and g["model"]["route"]["tool_acc"] >= ref["tool_acc"] - 1 and g["model"]["route"]["unsafe_routes"] <= ref["unsafe_routes"]:
            return q
    return "q8_0"


def eval_gguf_in_ollama(model_name, modelfile_dir, quant, tokenizer_dir, hf_preds_path, out_path, repo_dir=ROOT,
                        host="127.0.0.1:11434", limit=0, workers=4, ollama_bin="ollama"):
    """(a) Test what you ship. Needs `ollama serve` running at host. Creates model_name from Modelfile.<quant>, checks chat
    (Modelfile TEMPLATE) vs raw (exact HF-rendered prompt) outputs and prompt token counts, runs finetune/eval_finetuned.py
    --mode both against it and adds the agreement with the HF predictions. Writes and returns the report."""
    import urllib.request
    from transformers import AutoTokenizer
    env = dict(os.environ, OLLAMA_HOST=host)
    subprocess.run([ollama_bin, "create", model_name, "-f", f"Modelfile.{quant}"], cwd=modelfile_dir, env=env, check=True)
    tok = AutoTokenizer.from_pretrained(tokenizer_dir)
    test = [json.loads(l) for l in open(os.path.join(repo_dir, "finetune", "data", "test.jsonl"), encoding="utf-8")]
    route_rows = [r for r in test if r["task"] == "route"]
    rows = route_rows[:: max(1, len(route_rows) // 20)][:20]
    def post(path, body):
        req = urllib.request.Request(f"http://{host}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=600))
    same = cnt_ok = 0; opts = {"temperature": 0, "repeat_penalty": 1.0, "num_predict": 64}; diffs = []
    for r in rows:
        msgs = r["messages"][:-1]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        n_ids = len(tok(prompt, add_special_tokens=False)["input_ids"])
        c = post("/api/chat", {"model": model_name, "messages": msgs, "stream": False, "options": opts})
        g = post("/api/generate", {"model": model_name, "raw": True, "stream": False, "options": opts, "prompt": prompt})
        ok = c["message"]["content"].strip() == g["response"].strip(); same += ok
        cnt_ok += g.get("prompt_eval_count") == n_ids
        if not ok and len(diffs) < 3: diffs.append(dict(chat=c["message"]["content"][:100], raw=g["response"][:100]))
    chat_vs_raw = dict(n=len(rows), same_output=same, raw_prompt_token_count_matches_hf=cnt_ok, diffs=diffs)
    print("chat vs raw:", chat_vs_raw, flush=True)
    preds_path = out_path + ".preds.json"
    e2 = dict(env, FT_MODEL=model_name, OLLAMA_HOST="http://" + host, FT_TIMEOUT_S="120", FT_ANSWER_TIMEOUT_S="240", FT_WARMUP="0", NP_BRAIN="rules")
    for k in ("FT_REMOTE_URL", "FT_REMOTE_KEY"): e2.pop(k, None)
    cmd = [sys.executable, os.path.join(repo_dir, "finetune", "eval_finetuned.py"), "--mode", "both", "--out", out_path,
           "--save-preds", preds_path, "--workers", str(workers)] + (["--limit", str(limit)] if limit else [])
    t = time.time(); p = subprocess.run(cmd, cwd=repo_dir, env=e2)
    rep = json.load(open(out_path)); rep.update(exit_code=p.returncode, chat_vs_raw=chat_vs_raw, quant=quant, eval_minutes=round((time.time() - t) / 60, 1))
    gp = json.load(open(preds_path)); recs = test[:len(gp)]
    if hf_preds_path and os.path.exists(hf_preds_path):
        hf = json.load(open(hf_preds_path)); by_id = dict(zip(hf["ids"], hf["preds"]))
        rep["agreement"] = agreement(recs, [by_id.get(r["id"]) for r in recs], gp)
        print("agreement with HF:", rep["agreement"], flush=True)
    json.dump(rep, open(out_path, "w"), indent=1, default=str)
    return rep


def zip_files(paths, z):
    import zipfile
    with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:   # stored: GGUF doesn't compress
        for p, arc in paths: zf.write(p, arc)
    print("zip:", z, round(os.path.getsize(z) / 2 ** 30, 2), "GiB", flush=True)
    return z


def gguf_as_report(g):
    """Map an eval_finetuned.py report onto the keys compare_run2 expects (gate decision uses the GGUF numbers)."""
    return dict(model=g.get("model", {}), fresh_wording=g.get("fresh_wording"), gate_pure_pass=(g.get("pure") or {}).get("gate_pass"),
                gate_pass=(g.get("hybrid") or {}).get("gate_pass"))


# ---------- local dry run ----------
def main():
    ap = argparse.ArgumentParser(description="Local CPU dry run of the Modal training pipeline (tiny model, a few steps).")
    ap.add_argument("--smoke", action="store_true", help="tiny model (Qwen2.5-0.5B), 12 steps, a small test subset, CPU ok")
    ap.add_argument("--model", default="1.5B", choices=["1.5B", "7B"]); ap.add_argument("--work", default=os.path.abspath("ft_work_dry"))
    ap.add_argument("--llama-cpp", default=os.environ.get("LLAMA_CPP_DIR", "")); ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-public", action="store_true"); ap.add_argument("--skip-gates", action="store_true")
    a = ap.parse_args()
    if not a.smoke: sys.exit("Use --smoke locally. Real runs go through Modal: modal run finetune/modal/train_modal.py")
    cfg = Config(model_choice=a.model, smoke=True, work=a.work, use_public=not a.no_public, gpu="CPU").finalize()
    t0 = time.time()
    train_rows, val_rows, test, public_eval = load_data(cfg)
    model, tok, hw = load_model(cfg)
    tr = train(cfg, model, tok, train_rows, val_rows, hw)
    gen = make_generator(model, tok)
    meta = dict(base_model=cfg.base_model, qlora=cfg.qlora, epochs=cfg.epochs, train_rows=len(train_rows), use_public=cfg.use_public,
                smoke=True, gpu=cfg.gpu, config=asdict(cfg), **{k: v for k, v in tr.items() if k != "log_history"})
    rep = evaluate(cfg, gen, test, public_eval, meta); hf_preds = rep.pop("_preds")
    rp = os.path.join(cfg.work, "eval_report.json"); json.dump(rep, open(rp, "w"), indent=1, default=str)
    if not a.no_export and a.llama_cpp:
        merged = merge_to_dir(cfg, model, tok, tr["adapter_dir"])
        files = export_ggufs(cfg.ollama_name, merged, os.path.join(cfg.work, "export"), a.llama_cpp, quants=("q8_0",))
        template_parity(tok, [r for r in test if r["task"] == "route"], files["f16"], a.llama_cpp)
        json.dump(hf_preds, open(os.path.join(cfg.work, "hf_preds.json"), "w"))
    el = time.time() - t0
    print(f"dry run done in {el / 60:.1f} min"); print(cost_line(el, "A100-80GB", "the same seconds on an A100-80GB (illustration only)"))


if __name__ == "__main__":
    main()
