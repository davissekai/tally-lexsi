# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "aligntune==0.1.35",
#   "trl==1.7.1",
#   "transformers==5.20.2",
#   "peft==0.21.2",
#   "datasets==4.8.5",
#   "accelerate==1.15.0",
#   "bitsandbytes==0.50.2",
#   "huggingface_hub",
#   "torch<2.14",
# ]
# ///
"""Tally v8: AlignTune (TRL backend) bf16 LoRA SFT of CohereLabs/tiny-aya-global on HF Jobs A100.
Same recipe as v7 (r16/a32 q,k,v,o, answer-only loss, LR 2e-4, cosine, warmup 0.1, eff. batch 8,
seed 42, best-by-eval_loss) except: bf16 full-precision base (no 4-bit), v8 data, max_len 4096.
Env: MAX_STEPS (smoke test), EPOCHS, HUB_REPO, PUSH_PREFIX, DATA_REPO, DATA_SUBDIR."""
import gc, inspect, json, os, shutil, sys, time, traceback
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
import torch.nn.functional as F
from huggingface_hub import HfApi, snapshot_download, create_repo
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback

T0 = time.time()
MID = "CohereLabs/tiny-aya-global"
# The original run read renhuang001/tally-v8-sft (private mirror of the same v8 files).
# Public copy: renhuang001/tally-sft-data, folder v8/ (contact details redacted, otherwise identical).
DATA_REPO = os.environ.get("DATA_REPO", "renhuang001/tally-sft-data")
DATA_SUBDIR = os.environ.get("DATA_SUBDIR", "v8").strip("/")
HUB_REPO = os.environ.get("HUB_REPO", "renhuang001/tally-v8-lora")
PREFIX = os.environ.get("PUSH_PREFIX", "").strip("/")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "0") or 0)
NUM_EPOCHS = float(os.environ.get("EPOCHS", "2"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "4"))
GRAD_ACCUM = int(os.environ.get("GRAD_ACCUM", "2"))   # effective batch 8, as v7
LEARNING_RATE = 2e-4
MAX_SEQ_LENGTH = 4096   # v8 max example ~2.6K tokens (stats.json); checked below
LORA_R, LORA_ALPHA, LORA_DROPOUT = 16, 32, 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj"]
SEED = 42
WORK = Path("/tmp/tally"); RUN_DIR = WORK / "finetune_runs"; ADAPTER_DIR = WORK / "tally-v8-lora"
for d in (WORK, RUN_DIR, ADAPTER_DIR): d.mkdir(parents=True, exist_ok=True)

def log(*a): print(f"[{(time.time()-T0)/60:6.1f} min]", *a, flush=True)

api = HfApi()
log("whoami:", api.whoami().get("name"))
assert torch.cuda.is_available(), "no GPU"
log("GPU:", torch.cuda.get_device_name(0), f"{torch.cuda.get_device_properties(0).total_memory/2**30:.0f} GiB",
    "bf16:", torch.cuda.is_bf16_supported(), "torch", torch.__version__)
import importlib.metadata as md
for p in ("transformers", "trl", "peft", "datasets", "accelerate", "aligntune", "curatorkit", "bitsandbytes"):
    try: log(f"{p}=={md.version(p)}")
    except Exception: log(p, "not installed")

create_repo(HUB_REPO, repo_type="model", private=True, exist_ok=True)
assert api.model_info(HUB_REPO).private, "target repo is not private; refusing to push"

def push(folder, path_in_repo, msg):
    try:
        p = "/".join(x for x in (PREFIX, path_in_repo) if x)
        api.upload_folder(folder_path=str(folder), repo_id=HUB_REPO, repo_type="model",
                          path_in_repo=p or ".", commit_message=msg,
                          ignore_patterns=["optimizer.pt", "*.pt", "rng_state*", "scheduler.pt"])
        log("pushed", folder, "->", HUB_REPO, p or "/")
    except Exception as exc:
        log("push failed:", type(exc).__name__, exc)

# ---- data ----
_pat = [f"{DATA_SUBDIR}/*.jsonl", f"{DATA_SUBDIR}/stats.json"] if DATA_SUBDIR else ["*.jsonl", "stats.json"]
ddir = Path(snapshot_download(DATA_REPO, repo_type="dataset", allow_patterns=_pat))
ddir = ddir / DATA_SUBDIR if DATA_SUBDIR else ddir
def load_jsonl(p): return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
train_rows = load_jsonl(ddir / "train.jsonl"); val_rows = load_jsonl(ddir / "validation.jsonl")
log("data: train", len(train_rows), "val", len(val_rows))
HELDOUT = {"5172", "5432", "4329", "2928"}
for fn in ("train_with_metadata.jsonl", "val_sft_with_metadata.jsonl"):
    meta = load_jsonl(ddir / fn)
    bad = [m.get("project_group") for m in meta if str(m.get("project")) in HELDOUT or any(h == g for g in str(m.get("project_group")).split("_") for h in HELDOUT)]
    assert not bad, f"held-out project in {fn}: {bad[:5]}"
log("held-out check OK")

tok = AutoTokenizer.from_pretrained(MID)
START_RESPONSE_ID = tok.convert_tokens_to_ids("<|START_RESPONSE|>")
assert START_RESPONSE_ID is not None and START_RESPONSE_ID != tok.unk_token_id
def _ntok(msgs):
    o = tok.apply_chat_template(msgs, tokenize=True)
    if hasattr(o, "keys"): o = o["input_ids"]
    return len(o)
lens = [_ntok(r["messages"]) for r in train_rows + val_rows]
log(f"token lengths: max {max(lens)}, mean {sum(lens)/len(lens):.0f}, over {MAX_SEQ_LENGTH}: {sum(l > MAX_SEQ_LENGTH for l in lens)}; padding_side={tok.padding_side}")
if max(lens) > MAX_SEQ_LENGTH:
    MAX_SEQ_LENGTH = int(max(lens) + 64); log("raised MAX_SEQ_LENGTH to", MAX_SEQ_LENGTH)

# ---- answer-only loss (same as v7) ----
def tally_compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
    self.loss_is_scaled_for_ga = False
    self.model_accepts_loss_kwargs = False
    inputs.pop("_prediction_loss_only", None)
    ids = inputs["input_ids"]; attn = inputs.get("attention_mask")
    if attn is None: attn = torch.ones_like(ids)
    B, L = ids.shape
    pos = torch.arange(L, device=ids.device).unsqueeze(0).expand(B, L)
    is_start = (ids == START_RESPONSE_ID) & (attn > 0)
    last_start = torch.where(is_start, pos, torch.full_like(pos, -1)).max(dim=1).values
    has_ans = last_start >= 0
    if not bool(has_ans.any()):
        zero = sum(p.sum() for p in model.parameters() if p.requires_grad) * 0.0
        return (zero, {"loss": zero}) if return_outputs else zero
    first_ans = torch.where(has_ans, last_start + 1, torch.full_like(last_start, L))
    K = max(2, min(int(L - int(first_ans[has_ans].min().item()) + 1), L))
    fwd = {"input_ids": ids, "attention_mask": attn, "use_cache": False, "logits_to_keep": K}
    if "position_ids" in inputs: fwd["position_ids"] = inputs["position_ids"]
    out = model(**fwd)
    logits = out.logits[:, :-1, :].float()
    tgt = ids[:, L - K + 1:]; tpos = pos[:, L - K + 1:]
    mask = (tpos >= first_ans.unsqueeze(1)) & (attn[:, L - K + 1:] > 0)
    ce = F.cross_entropy(logits.reshape(-1, logits.size(-1)), tgt.reshape(-1), reduction="none").view_as(tgt)
    loss = (ce * mask).sum() / mask.sum().clamp(min=1)
    if not getattr(self, "_tally_logged", False):
        self._tally_logged = True
        log(f"[answer-only loss] batch {B}, seq len {L}, answer tokens {int(mask.sum())}, logits kept {K}")
    return (loss, {"loss": loss, "logits": logits[:, -1:, :]}) if return_outputs else loss

import trl
from trl import SFTTrainer
_ORIG_TRAIN, _ORIG_STEP = SFTTrainer.train, SFTTrainer.training_step
OOM_SKIPS = []
def cast_trainable_fp32(model):
    n = 0
    for p in model.parameters():
        if p.requires_grad and p.dtype != torch.float32: p.data = p.data.float(); n += 1
    return n
def tally_train(self, *a, **k):
    n = cast_trainable_fp32(self.model)
    log(f"[pre-train] cast {n} trainable tensors to fp32; bf16={self.args.bf16} fp16={self.args.fp16} "
        f"max_steps={self.args.max_steps} epochs={self.args.num_train_epochs} bs={self.args.per_device_train_batch_size} "
        f"ga={self.args.gradient_accumulation_steps} max_length={getattr(self.args,'max_length',None)} eval={self.args.eval_strategy}")
    return _ORIG_TRAIN(self, *a, **k)
def tally_training_step(self, model, inputs, *a, **k):
    try:
        out = _ORIG_STEP(self, model, inputs, *a, **k)
    except torch.OutOfMemoryError:
        OOM_SKIPS.append(int(inputs["input_ids"].shape[-1])); log("[OOM] skipped micro-batch", OOM_SKIPS[-1])
        gc.collect(); torch.cuda.empty_cache()
        return torch.tensor(0.0, device=inputs["input_ids"].device)
    if not getattr(self, "_mem_logged", False):
        self._mem_logged = True; log(f"[mem] peak after first micro-batch {torch.cuda.max_memory_allocated()/2**30:.1f} GiB")
    return out
SFTTrainer.compute_loss = tally_compute_loss
SFTTrainer.train = tally_train
SFTTrainer.training_step = tally_training_step

class ProgressAndPush(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kw):
        if logs and state.global_step % 10 == 0 or (logs and "eval_loss" in logs):
            el = time.time() - T0
            eta = (el / max(state.global_step, 1)) * (state.max_steps - state.global_step) / 60 if state.max_steps else 0
            log(f"step {state.global_step}/{state.max_steps} epoch {state.epoch:.2f} {json.dumps({k: round(v, 4) if isinstance(v, float) else v for k, v in logs.items()})} ETA~{eta:.0f} min")
    def on_save(self, args, state, control, **kw):
        ck = Path(args.output_dir) / f"checkpoint-{state.global_step}"
        if ck.is_dir(): push(ck, f"checkpoints/checkpoint-{state.global_step}", f"v8 checkpoint step {state.global_step}")

def history_metrics(hf):
    hist = list(getattr(getattr(hf, "state", None), "log_history", []) or [])
    return {"train_loss_log": [(h.get("step"), h.get("epoch"), h["loss"]) for h in hist if "loss" in h],
            "eval_loss_by_epoch": [(h.get("epoch"), h["eval_loss"]) for h in hist if "eval_loss" in h],
            "train_summary": ([h for h in hist if "train_runtime" in h] or [{}])[-1],
            "best_model_checkpoint": getattr(hf.state, "best_model_checkpoint", None)}

COMMON = dict(eval_strategy="epoch" if not MAX_STEPS else "steps", save_strategy="epoch" if not MAX_STEPS else "steps",
              save_total_limit=2, load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
              seed=SEED, packing=False, report_to="none", warmup_ratio=0.1)

def write_sft_dir():
    d = WORK / "aligntune_data"
    if d.exists(): shutil.rmtree(d)
    d.mkdir(parents=True)
    for name, rows in (("train.jsonl", train_rows), ("validation.jsonl", val_rows if not MAX_STEPS else val_rows[:40])):
        with open(d / name, "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
    return d

def try_aligntune():
    from aligntune.core.backend_factory import create_sft_trainer
    kw = dict(model_name=MID, dataset_name=str(write_sft_dir()), backend="trl", output_dir=str(RUN_DIR),
              num_epochs=NUM_EPOCHS, batch_size=BATCH_SIZE, learning_rate=LEARNING_RATE, max_seq_length=MAX_SEQ_LENGTH,
              peft_enabled=True, lora_r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT, target_modules=LORA_TARGETS,
              quantization={}, precision="bf16", fp16=False, bf16=True, gradient_accumulation_steps=GRAD_ACCUM,
              use_gradient_checkpointing=True, gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
              assistant_only_loss=False, task_type="chat_completion", curator_schema_gate=True, curator_clean=False,
              curator_dedup="none", curator_max_tokens=1_000_000, logging_steps=1, log_interval=1, lr_scheduler="cosine",
              device_map={"": 0}, compute_rouge=False, compute_bleu=False, compute_perplexity=False,
              attn_implementation="sdpa", group_by_length=True, per_device_eval_batch_size=BATCH_SIZE, **COMMON)
    if MAX_STEPS: kw.update(max_steps=MAX_STEPS, eval_interval=MAX_STEPS, save_interval=MAX_STEPS, eval_steps=MAX_STEPS, save_steps=MAX_STEPS)
    log("Creating AlignTune SFT trainer (backend=trl, bf16 LoRA, answer-only loss)...")
    tr = create_sft_trainer(**kw)
    log("AlignTune trainer:", type(tr).__name__)
    tr.setup_model()
    log("cast", cast_trainable_fp32(tr.model), "trainable tensors to fp32; base dtype", next(tr.model.parameters()).dtype)
    if hasattr(tr.model, "print_trainable_parameters"): tr.model.print_trainable_parameters()
    tr.setup_data(); tr.dataset = tr.train_dataset
    log("AlignTune data: train", len(tr.train_dataset), "val", len(tr.eval_dataset) if tr.eval_dataset is not None else 0)
    # attach progress/checkpoint-push callback
    _orig_cb = tr.get_hf_callbacks
    tr.get_hf_callbacks = lambda: list(_orig_cb() or []) + [ProgressAndPush()]
    result = tr.train()
    m = {"aligntune_result": {k: v for k, v in (result or {}).items() if k != "metrics"}}
    hf = getattr(tr, "trainer", None)
    if hf is not None:
        try: m["final_eval"] = dict(hf.evaluate()); log("final eval:", m["final_eval"])
        except Exception as exc: log("evaluate() skipped:", exc)
        m.update(history_metrics(hf))
    return tr, m

def try_trl_fallback():
    from datasets import Dataset
    from peft import LoraConfig
    from trl import SFTConfig
    log("TRL fallback: loading Tiny Aya bf16...")
    ftok = AutoTokenizer.from_pretrained(MID)
    if ftok.pad_token is None: ftok.pad_token = ftok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MID, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa")
    model.config.use_cache = False
    raw = dict(output_dir=str(RUN_DIR / "trl_fallback"), num_train_epochs=NUM_EPOCHS, per_device_train_batch_size=BATCH_SIZE,
               per_device_eval_batch_size=BATCH_SIZE, gradient_accumulation_steps=GRAD_ACCUM, learning_rate=LEARNING_RATE,
               lr_scheduler_type="cosine", warmup_steps=0.1, logging_steps=1, bf16=True, fp16=False,
               gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False}, max_length=MAX_SEQ_LENGTH,
               assistant_only_loss=False, group_by_length=True, **{k: v for k, v in COMMON.items() if k != "warmup_ratio"})
    if MAX_STEPS: raw.update(max_steps=MAX_STEPS, eval_steps=MAX_STEPS, save_steps=MAX_STEPS)
    sig = inspect.signature(SFTConfig.__init__)
    dropped = [k for k in raw if k not in sig.parameters]
    if dropped: log("SFTConfig dropping", dropped)
    args = SFTConfig(**{k: v for k, v in raw.items() if k in sig.parameters})
    tr = SFTTrainer(model=model, args=args, train_dataset=Dataset.from_list([{"messages": r["messages"]} for r in train_rows]),
                    eval_dataset=Dataset.from_list([{"messages": r["messages"]} for r in (val_rows if not MAX_STEPS else val_rows[:40])]),
                    peft_config=LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT, bias="none",
                                           task_type="CAUSAL_LM", target_modules=LORA_TARGETS),
                    processing_class=ftok, callbacks=[ProgressAndPush()])
    tr.model.print_trainable_parameters()
    res = tr.train()
    m = {"train": dict(getattr(res, "metrics", {}) or {})}
    try: m["final_eval"] = dict(tr.evaluate()); log("final eval:", m["final_eval"])
    except Exception as exc: log("evaluate() skipped:", exc)
    m.update(history_metrics(tr))
    return tr, m

USED_BACKEND, TRAIN_ERRORS, TRAIN_METRICS, trainer = None, {}, {}, None
try:
    trainer, TRAIN_METRICS = try_aligntune(); USED_BACKEND = "aligntune-trl"
except Exception as exc:
    TRAIN_ERRORS["aligntune"] = f"{type(exc).__name__}: {exc}"; log("AlignTune failed:", TRAIN_ERRORS["aligntune"]); traceback.print_exc()
    trainer = None
if USED_BACKEND is None:
    gc.collect(); torch.cuda.empty_cache()
    try:
        trainer, TRAIN_METRICS = try_trl_fallback(); USED_BACKEND = "trl-peft-fallback"
    except Exception as exc2:
        TRAIN_ERRORS["trl_fallback"] = f"{type(exc2).__name__}: {exc2}"; log("TRL fallback failed:", TRAIN_ERRORS["trl_fallback"]); traceback.print_exc()
TRAIN_METRICS["oom_skipped_microbatches"] = OOM_SKIPS
log("USED_BACKEND =", USED_BACKEND)

# ---- save adapter (best by eval_loss, loaded at end) + provenance ----
hf = getattr(trainer, "trainer", None) or trainer
def adapter_present(d): return (d / "adapter_config.json").is_file() and any(d.glob("adapter_model*"))
if hf is not None:
    for how in ("save_model", "model.save_pretrained"):
        if adapter_present(ADAPTER_DIR): break
        try:
            hf.save_model(str(ADAPTER_DIR)) if how == "save_model" else hf.model.save_pretrained(str(ADAPTER_DIR))
        except Exception as exc: log(how, "failed:", exc)
if not adapter_present(ADAPTER_DIR):
    c = sorted((p.parent for p in RUN_DIR.rglob("adapter_config.json")), key=lambda p: p.stat().st_mtime)
    if c:
        for item in c[-1].iterdir():
            if item.is_file(): shutil.copy2(item, ADAPTER_DIR / item.name)
try: tok.save_pretrained(str(ADAPTER_DIR))
except Exception: pass
prov = sorted(RUN_DIR.rglob("lexsi_provenance.json"))
if prov:
    shutil.copy2(prov[0], ADAPTER_DIR / "lexsi_provenance.json")
else:
    (ADAPTER_DIR / "lexsi_provenance.json").write_text(json.dumps({
        "schema": "lexsi.provenance/1", "library": "aligntune" if USED_BACKEND == "aligntune-trl" else "trl",
        "version": md.version("aligntune"), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_model": MID, "method": "chat_completion",
        "inputs": [{"kind": "model", "ref": MID}, {"kind": "dataset", "ref": DATA_REPO}],
        "params": {"trainer": "TRLSFTTrainer" if USED_BACKEND == "aligntune-trl" else "trl.SFTTrainer", "note": "written by train script"}}, indent=2))
(ADAPTER_DIR / "train_metrics.json").write_text(json.dumps({
    "backend": USED_BACKEND, "errors": TRAIN_ERRORS, "metrics": TRAIN_METRICS,
    "hyperparameters": {"base_model": MID, "data": DATA_REPO, "epochs": NUM_EPOCHS, "max_steps": MAX_STEPS or None,
        "per_device_batch": BATCH_SIZE, "grad_accum": GRAD_ACCUM, "lr": LEARNING_RATE, "scheduler": "cosine", "warmup_ratio": 0.1,
        "max_seq_length": MAX_SEQ_LENGTH, "lora_r": LORA_R, "lora_alpha": LORA_ALPHA, "lora_dropout": LORA_DROPOUT,
        "targets": LORA_TARGETS, "precision": "bf16 (no quantization)", "loss": "answer-only (after last <|START_RESPONSE|>)",
        "seed": SEED, "hardware": "HF Jobs a100-large"},
    "wall_minutes": round((time.time() - T0) / 60, 1)}, indent=2, default=str))
log("adapter dir:", sorted(p.name for p in ADAPTER_DIR.iterdir()))
if adapter_present(ADAPTER_DIR):
    push(ADAPTER_DIR, "", f"Tally v8 LoRA adapter ({USED_BACKEND})")
else:
    push(ADAPTER_DIR, "failed_run", "Tally v8 failed run metrics"); log("NO ADAPTER PRODUCED"); sys.exit(1)
log("DONE")
