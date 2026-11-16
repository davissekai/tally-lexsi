# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "transformers==5.20.2",
#   "peft==0.21.2",
#   "accelerate==1.15.0",
#   "huggingface_hub",
#   "torch<2.14",
# ]
# ///
"""Tally held-out bench on one A100, all bf16.

Protocol: the same extraction prompt already stored on each chunk row, greedy
decoding, max_new_tokens=900, batched generate with left padding, then the same
parse / merge / score path used for every public result.

This script scores with merge v1 (`tally_merge.py`). To get the merge v2
numbers, run scripts/rescore_merge_v2.py on the saved outputs.

This public copy contains no held-out documents, answers, or model outputs.
Point it at a local data directory that you already have:

  HELDOUT_DATA_DIR/
    heldout_messages.jsonl
    heldout_meta.jsonl
    answer_key_heldout.json
    tally_merge.py
    score_extractions.py

Env:
  HELDOUT_DATA_DIR   required, path to the directory above
  OUT_DIR            default ./results_a100_bf16
  V7_ADAPTER         default renhuang001/tally-v7-lora
  V8_ADAPTER         default renhuang001/tally-v8-lora
  SMOKE=N            first N chunks only
  MODELS             comma list from: v8,v7,base,qwen3-8b,gemma-3-12b
  BATCH              default 16
"""
import gc, json, os, re, sys, time, traceback
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

T0 = time.time()
def log(*a):
    print(f"[{(time.time()-T0)/60:6.1f} min]", *a, flush=True)

DATA = Path(os.environ.get("HELDOUT_DATA_DIR", "")).expanduser()
if not DATA.is_dir():
    sys.exit("Set HELDOUT_DATA_DIR to a local folder with the held-out inputs (not published).")

AYA = "CohereLabs/tiny-aya-global"
V7_ADAPTER = os.environ.get("V7_ADAPTER", "renhuang001/tally-v7-lora")
V8_ADAPTER = os.environ.get("V8_ADAPTER", "renhuang001/tally-v8-lora")
SMOKE = int(os.environ.get("SMOKE", "0") or 0)
BATCH = int(os.environ.get("BATCH", "16"))
ALL = ["v8", "v7", "base", "qwen3-8b", "gemma-3-12b"]
MODELS = [m for m in os.environ.get("MODELS", ",".join(ALL)).split(",") if m]
OUT = Path(os.environ.get("OUT_DIR", "results_a100_bf16"))
OUT.mkdir(parents=True, exist_ok=True)

log("GPU:", torch.cuda.get_device_name(0), "torch", torch.__version__,
    "MODELS", MODELS, "SMOKE", SMOKE, "BATCH", BATCH)
import importlib.metadata as md
for p in ("transformers", "peft", "accelerate"):
    log(f"{p}=={md.version(p)}")

sys.path.insert(0, str(DATA))
from tally_merge import merge_notes
from score_extractions import score_documents, format_summary_table

def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

rows = load_jsonl(DATA / "heldout_messages.jsonl")
meta = load_jsonl(DATA / "heldout_meta.jsonl")
answer_key = json.loads((DATA / "answer_key_heldout.json").read_text(encoding="utf-8"))
if SMOKE:
    rows, meta = rows[:SMOKE], meta[:SMOKE]
log("chunks", len(rows), "docs", len(answer_key))

def parse_json(text):
    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0))

def extract_chunk_text(u):
    pos = u.find("\nPages ")
    if pos == -1:
        return u
    rest = u[pos + 1:]
    nl = rest.find("\n")
    return rest[nl + 1:].lstrip() if nl != -1 else rest

def ids_aya(tok, prompt):
    enc = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        add_generation_prompt=True, return_tensors="pt", return_dict=True,
    )
    return enc["input_ids"][0].tolist(), None

def ids_bench(tok, prompt):
    text, thinking, last = None, None, None
    for conv in (
        [{"role": "user", "content": prompt}],
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    ):
        try:
            text = tok.apply_chat_template(
                conv, tokenize=False, add_generation_prompt=True, enable_thinking=False,
            )
            thinking = False
            break
        except TypeError as e:
            last = e
            try:
                text = tok.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
                thinking = "unsupported"
                break
            except Exception as e2:
                last = e2
    if text is None:
        raise last
    return tok(text, add_special_tokens=False)["input_ids"], thinking

def stop_ids(tok, model, aya):
    if aya:
        return [i for i in (tok.convert_tokens_to_ids("<|END_RESPONSE|>"), tok.eos_token_id) if i is not None]
    s = set()
    if tok.eos_token_id is not None:
        s.add(tok.eos_token_id)
    g = getattr(model, "generation_config", None)
    ge = getattr(g, "eos_token_id", None) if g else None
    if isinstance(ge, int):
        s.add(ge)
    elif ge:
        s.update(ge)
    for t in ("<|im_end|>", "<end_of_turn>"):
        i = tok.convert_tokens_to_ids(t)
        if isinstance(i, int) and i != tok.unk_token_id:
            s.add(i)
    return sorted(s)

def gen_batch(model, tok, id_lists, eos, pad):
    L = max(len(x) for x in id_lists)
    inp = torch.full((len(id_lists), L), pad, dtype=torch.long)
    att = torch.zeros_like(inp)
    for j, x in enumerate(id_lists):
        inp[j, L - len(x):] = torch.tensor(x)
        att[j, L - len(x):] = 1
    with torch.no_grad():
        out = model.generate(
            input_ids=inp.to(model.device), attention_mask=att.to(model.device),
            max_new_tokens=900, do_sample=False, eos_token_id=eos, pad_token_id=pad,
            temperature=None, top_p=None, top_k=None,
        )
    return [tok.decode(o[L:], skip_special_tokens=True) for o in out]

def run(model, tok, label, model_id, aya):
    t = time.time()
    enc = [(ids_aya if aya else ids_bench)(tok, r["messages"][0]["content"]) for r in rows]
    eos = stop_ids(tok, model, aya)
    pad = tok.pad_token_id if tok.pad_token_id is not None else eos[0]
    log(label, "stop ids", eos, "pad", pad, "max prompt toks", max(len(e[0]) for e in enc))
    order = sorted(range(len(rows)), key=lambda i: -len(enc[i][0]))
    replies = [None] * len(rows)
    bs = BATCH
    k = 0
    while k < len(order):
        idx = order[k:k + bs]
        try:
            outs = gen_batch(model, tok, [enc[i][0] for i in idx], eos, pad)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            bs = max(1, bs // 2)
            log("OOM -> batch", bs)
            continue
        for i, o in zip(idx, outs):
            replies[i] = o
        k += len(idx)
        log(f"[{label}] {k}/{len(order)} chunks")
    gen_sec = time.time() - t
    per_doc_notes, per_doc_text = defaultdict(list), defaultdict(list)
    n_err = 0
    for r, m, reply in zip(rows, meta, replies):
        try:
            parsed = parse_json(reply)
            err = None
        except Exception as exc:
            parsed = {"_error": f"{type(exc).__name__}: {exc}"}
            err = str(exc)
            n_err += 1
        per_doc_notes[m["doc"]].append(parsed)
        per_doc_text[m["doc"]].append(extract_chunk_text(r["messages"][0]["content"]))
    merged = {d: merge_notes(n, doc_text="\n\n".join(per_doc_text[d])) for d, n in per_doc_notes.items()}
    try:
        scores = score_documents(merged, answer_key, docs=sorted(merged))
        print(format_summary_table(scores, f"{label} held-out"))
    except Exception as exc:
        scores = {"_error": repr(exc)}
        log("scoring error", exc)
    o = scores.get("overall", {})
    summary = {
        "label": label, "model_id": model_id, "dtype": "bfloat16",
        "gen_sec": round(gen_sec, 1), "batch": BATCH, "parse_errors": n_err,
        "n_chunks": len(rows),
        **{k: o.get(k) for k in (
            "stated_correct", "stated_n", "stated_accuracy", "hallucinated",
            "correct", "wrong", "conflict-unresolved", "correctly-abstained",
            "accuracy_incl_abstention",
        )},
    }
    log("SUMMARY", json.dumps(summary))
    # Public-safe default: write the aggregate summary only, not per-pair outputs.
    (OUT / f"{label}_summary.json").write_text(json.dumps(summary, indent=1))
    return summary

def load(mid):
    tok = AutoTokenizer.from_pretrained(mid)
    model = AutoModelForCausalLM.from_pretrained(mid, dtype=torch.bfloat16, device_map={"": 0})
    model.eval()
    return tok, model

def free():
    gc.collect()
    torch.cuda.empty_cache()

summaries = {}
aya = [m for m in MODELS if m in ("v8", "v7", "base")]
if aya:
    if "v8" in aya and not V8_ADAPTER:
        log("skipping v8: V8_ADAPTER is empty")
        aya = [m for m in aya if m != "v8"]
    if aya:
        try:
            from huggingface_hub import snapshot_download
            from peft import PeftModel
            t = time.time()
            tok, base = load(AYA)
            if tok.pad_token is None:
                tok.pad_token = tok.eos_token
            pm = None
            if "v8" in aya:
                v8 = snapshot_download(
                    V8_ADAPTER,
                    allow_patterns=["adapter_config.json", "adapter_model.safetensors"],
                    local_dir="/tmp/v8",
                )
                pm = PeftModel.from_pretrained(base, v8, adapter_name="v8")
            if "v7" in aya:
                v7 = snapshot_download(
                    V7_ADAPTER,
                    allow_patterns=["adapter_config.json", "adapter_model.safetensors"],
                    local_dir="/tmp/v7",
                )
                if pm is None:
                    pm = PeftModel.from_pretrained(base, v7, adapter_name="v7")
                else:
                    pm.load_adapter(v7, adapter_name="v7")
            if pm is None:
                pm = base
            else:
                pm.eval()
            log("aya loaded in %.1f s" % (time.time() - t))
            for lab in aya:
                try:
                    mid = AYA if lab == "base" else f"{AYA} + {V8_ADAPTER if lab == 'v8' else V7_ADAPTER}"
                    if lab == "base" and hasattr(pm, "disable_adapter"):
                        with pm.disable_adapter():
                            summaries[lab] = run(pm, tok, lab, mid, True)
                    else:
                        if hasattr(pm, "set_adapter"):
                            pm.set_adapter(lab)
                        summaries[lab] = run(pm, tok, lab, mid, True)
                except Exception as exc:
                    log(lab, "FAILED", exc)
                    traceback.print_exc()
            del pm, base
            free()
        except Exception as exc:
            log("aya FAILED", exc)
            traceback.print_exc()

for lab, mid in (("qwen3-8b", "Qwen/Qwen3-8B"), ("gemma-3-12b", "google/gemma-3-12b-it")):
    if lab not in MODELS:
        continue
    try:
        t = time.time()
        tok, model = load(mid)
        tok.padding_side = "left"
        log(lab, "loaded in %.1f s" % (time.time() - t), type(model).__name__)
        summaries[lab] = run(model, tok, lab, mid, False)
        del model
        free()
    except Exception as exc:
        log(lab, "FAILED", exc)
        traceback.print_exc()
        free()

(OUT / "all_summaries.json").write_text(json.dumps(summaries, indent=1))
log("ALL DONE", json.dumps({k: (v.get("stated_correct"), v.get("stated_n")) for k, v in summaries.items()}))
