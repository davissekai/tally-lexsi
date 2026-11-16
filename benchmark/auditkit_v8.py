# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "auditkit[transformers]==1.1.12",
#   "transformers==5.20.2",
#   "peft==0.21.2",
#   "accelerate==1.15.0",
#   "torch<2.14",
#   "huggingface_hub",
# ]
# ///
"""AuditKIT 1.1.12 eval of Tally v8 LoRA vs Tiny Aya Global on a stratified
slice of the v8 validation set (not the held-out projects), plus built-in
red-team probes on v8. Writes aggregates and private per-sample scores.
"""
from __future__ import annotations

import json, os, random, re, sys, time, traceback
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

T0 = time.time()
BASE = "CohereLabs/tiny-aya-global"
ADAPTER_REPO = "renhuang001/tally-v8-lora"
DATA_REPO = "renhuang001/tally-v8-sft"
HELDOUT = {"5172", "5432", "4329", "2928"}
SEED = 42
MAX_TOKENS = 900
BATCH_SIZE = 4
KIND_QUOTAS = {
    "full": 16,
    "single_field_stated": 12,
    "conflict_pick": 8,
    "single_field_hard_negative": 4,
}
STAGE_DEADLINE_S = 28 * 60  # leave time to flush artifacts before 35m job timeout
JOB_ID = os.environ.get("HF_JOB_ID") or os.environ.get("JOB_ID") or "local"

def log(*a):
    print(f"[{(time.time() - T0) / 60:6.1f} min]", *a, flush=True)

def elapsed():
    return time.time() - T0

# ---- output dirs (bucket mount preferred) ----
OUT_NAME = f"auditkit-v8-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}"
CANDIDATES = [Path("/artifacts"), Path("/tmp/auditkit-out")]
ART_ROOT = next((p for p in CANDIDATES if p.exists() and os.access(p, os.W_OK)), Path("/tmp/auditkit-out"))
ART_ROOT.mkdir(parents=True, exist_ok=True)
OUT = ART_ROOT / OUT_NAME
OUT.mkdir(parents=True, exist_ok=True)
LOCAL_FALLBACK = Path("/tmp/auditkit-out") / OUT_NAME
LOCAL_FALLBACK.mkdir(parents=True, exist_ok=True)
log("output dir:", OUT, "mounted_bucket:", str(ART_ROOT) == "/artifacts")

def write_json(path: Path, obj):
    text = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
    for dest in {path, LOCAL_FALLBACK / path.name}:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")

def document_body(user: str) -> str:
    m = re.search(r"\n\nPages \d+", user)
    if m:
        return user[m.start():].strip()
    m = re.search(r"\n--- page ", user)
    if m:
        return user[m.start():].strip()
    return user

def assert_no_heldout(rows):
    bad = []
    for m in rows:
        proj = str(m.get("project") or "")
        grp = str(m.get("project_group") or "")
        if proj in HELDOUT or any(h == g for g in grp.split("_") for h in HELDOUT):
            bad.append((proj, grp, m.get("id")))
    assert not bad, f"held-out project in audit sample: {bad[:5]}"

def headline_of(result) -> dict:
    h = getattr(result, "headline", None) or {}
    return {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in dict(h).items()}

def stats_of(result) -> dict:
    s = getattr(result, "stats", None)
    if s is None:
        return {}
    if hasattr(s, "items"):
        out = {}
        for k, v in dict(s).items():
            if hasattr(v, "__dict__") or hasattr(v, "mean"):
                out[k] = {
                    "mean": getattr(v, "mean", None),
                    "std": getattr(v, "std", None),
                    "min": getattr(v, "min", None),
                    "max": getattr(v, "max", None),
                    "count": getattr(v, "count", None),
                }
            else:
                out[k] = v
        return out
    return {"repr": str(s)}

def perf_of(result) -> dict:
    out = {}
    for name in ("perf", "model_size", "token_usage"):
        v = getattr(result, name, None)
        if v is not None:
            out[name] = v if isinstance(v, (dict, str, int, float, list)) else str(v)
    return out

def predictions_slim(result, samples):
    rows = []
    preds = list(getattr(result, "predictions", None) or result.samples())
    by_id = {s.id: s for s in samples}
    for p in preds:
        sid = getattr(p, "id", None) or getattr(p, "sample_id", None)
        sample = by_id.get(sid)
        scores = getattr(p, "scores", None) or getattr(p, "metrics", None) or {}
        if hasattr(scores, "items"):
            score_map = {}
            for k, v in dict(scores).items():
                if hasattr(v, "value"):
                    score_map[k] = v.value
                else:
                    score_map[k] = v
        else:
            score_map = {}
        output = getattr(p, "output", None) or getattr(p, "actual_output", None) or getattr(p, "prediction", None)
        target = getattr(p, "target", None) or getattr(p, "expected", None)
        if sample is not None:
            sid = sid or sample.id
            target = target if target is not None else sample.target
        meta = (sample.metadata if sample is not None else {}) or {}
        rows.append({
            "id": sid,
            "example_kind": meta.get("example_kind"),
            "project": meta.get("project"),
            "field": meta.get("field"),
            "target": target,
            "output": output,
            "scores": score_map,
        })
    return rows

def kind_breakdown(slim_rows):
    by = defaultdict(list)
    for r in slim_rows:
        by[r.get("example_kind") or "unknown"].append(r)
    out = {}
    for kind, rows in by.items():
        metrics = defaultdict(list)
        json_ok = 0
        for r in rows:
            for k, v in (r.get("scores") or {}).items():
                if isinstance(v, (int, float)):
                    metrics[k].append(float(v))
            outp = r.get("output") or ""
            try:
                json.loads(outp.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
                json_ok += 1
            except Exception:
                pass
        out[kind] = {
            "n": len(rows),
            "means": {k: (sum(vs) / len(vs) if vs else None) for k, vs in metrics.items()},
            "json_parse_rate": json_ok / len(rows) if rows else None,
        }
    return out

# ---- env / versions ----
import torch
from huggingface_hub import HfApi, snapshot_download

api = HfApi()
log("whoami:", api.whoami().get("name"))
assert torch.cuda.is_available(), "no GPU"
log("GPU:", torch.cuda.get_device_name(0),
    f"{torch.cuda.get_device_properties(0).total_memory / 2**30:.0f} GiB",
    "bf16:", torch.cuda.is_bf16_supported(), "torch", torch.__version__)
import importlib.metadata as md
for p in ("auditkit", "transformers", "peft", "accelerate", "torch"):
    try:
        log(f"{p}=={md.version(p)}")
    except Exception:
        log(p, "not installed")
import transformers
assert transformers.__version__.startswith("5."), f"need transformers 5.x, got {transformers.__version__}"

import auditkit as ak
from auditkit.model.hf_gen import HFGenModel
from auditkit.redteam import RedTeamRunner
from auditkit.runspec import RunConfig

# ---- data: private v8 validation, stratified, no held-out ----
ddir = Path(snapshot_download(DATA_REPO, repo_type="dataset",
                              allow_patterns=["validation.jsonl", "val_sft_with_metadata.jsonl", "stats.json"]))
meta = [json.loads(l) for l in (ddir / "val_sft_with_metadata.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
log("val rows:", len(meta), "kinds:", dict(Counter(m["example_kind"] for m in meta)))
assert_no_heldout(meta)

rng = random.Random(SEED)
picked = []
for kind, quota in KIND_QUOTAS.items():
    pool = [m for m in meta if m.get("example_kind") == kind]
    rng.shuffle(pool)
    take = pool[:quota]
    if len(take) < quota:
        log("WARN: only", len(take), "of", quota, "for", kind)
    picked.extend(take)
assert_no_heldout(picked)
log("sample:", len(picked), dict(Counter(m["example_kind"] for m in picked)),
    "projects:", sorted({str(m.get("project")) for m in picked}))

samples = []
for m in picked:
    user = m["messages"][0]["content"]
    target = m["messages"][-1]["content"]
    samples.append(ak.Sample(
        input=user,
        target=target,
        id=str(m.get("id")),
        retrieval_context=[document_body(user)],
        metadata={
            "example_kind": m.get("example_kind"),
            "project": m.get("project"),
            "project_group": m.get("project_group"),
            "field": m.get("field"),
            "doc": m.get("doc"),
        },
        tags=[str(m.get("example_kind") or "")],
    ))

write_json(OUT / "sample_ids.json", {
    "seed": SEED,
    "quotas": KIND_QUOTAS,
    "n": len(samples),
    "ids": [s.id for s in samples],
    "kinds": dict(Counter(s.metadata["example_kind"] for s in samples)),
    "projects": sorted({str(s.metadata["project"]) for s in samples}),
    "heldout_check": "ok",
    "note": "ids only; no document text",
})

# ---- models ----
adapter_dir = Path(snapshot_download(ADAPTER_REPO))
assert (adapter_dir / "adapter_config.json").is_file(), adapter_dir
cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
log("adapter base:", cfg.get("base_model_name_or_path"), "dir:", adapter_dir)
assert cfg.get("base_model_name_or_path") == BASE

def make_model(path_or_id: str, name: str) -> HFGenModel:
    return HFGenModel(
        model=str(path_or_id),
        device="cuda",
        token=os.environ.get("HF_TOKEN"),
        name=name,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        batch_size=BATCH_SIZE,
    )

CFG = RunConfig(temperature=0.0, max_tokens=MAX_TOKENS, seed=SEED, batch_size=BATCH_SIZE, track_performance=True)
SCORERS = [
    "exact_match",
    "f1_score",
    ak.FieldF1(normalize_numbers=True, case_sensitive=False, strip_fences=True),
    ak.LexicalGroundedness(),
    ak.IsJson(),
]

def run_eval(model, label: str):
    log("evaluate start:", label, "n=", len(samples))
    result = ak.evaluate(
        samples,
        model=model,
        scorers=SCORERS,
        config=CFG,
        cache=False,
        verbose=True,
    )
    log("evaluate done:", label)
    try:
        log(result.summary())
    except Exception as exc:
        log("summary failed:", type(exc).__name__, exc)
    slim = predictions_slim(result, samples)
    payload = {
        "label": label,
        "headline": headline_of(result),
        "stats": stats_of(result),
        "perf": perf_of(result),
        "fingerprint": getattr(result, "fingerprint", None),
        "errors": list(getattr(result, "errors", None) or []) or None,
        "kind_breakdown": kind_breakdown(slim),
        "n": len(slim),
    }
    write_json(OUT / f"{label}_summary.json", payload)
    write_json(OUT / f"{label}_predictions.json", slim)
    try:
        result.save(str(OUT / f"{label}_runresult.json"))
        # also copy to fallback if different
        if OUT != LOCAL_FALLBACK:
            result.save(str(LOCAL_FALLBACK / f"{label}_runresult.json"))
    except Exception as exc:
        log("RunResult.save failed:", type(exc).__name__, exc)
    return result, payload, slim

def redteam_to_dict(rt):
    by_probe = defaultdict(lambda: {"n": 0, "passed": 0, "failed": 0, "invalid": 0})
    rows = []
    for r in rt.results:
        rec = {
            "probe": r.probe_name,
            "detector": r.detector_name,
            "passed": bool(r.passed),
            "invalid": bool(getattr(r, "invalid", False)),
            "prompt_preview": (r.prompt or "")[:80],
            "output_preview": (r.output or "")[:200],
        }
        rows.append(rec)
        b = by_probe[r.probe_name]
        b["n"] += 1
        if rec["invalid"]:
            b["invalid"] += 1
        elif rec["passed"]:
            b["passed"] += 1
        else:
            b["failed"] += 1
    judged = rt.total_probes - rt.invalid_probes
    return {
        "model_name": rt.model_name,
        "probes_used": list(rt.probes_used),
        "detectors_used": list(rt.detectors_used),
        "total": rt.total_probes,
        "passed": rt.passed_probes,
        "failed": rt.failed_probes,
        "invalid": rt.invalid_probes,
        "pass_rate": rt.pass_rate,
        "judged": judged,
        "by_probe": dict(by_probe),
        "summary": rt.summary(),
        "rows": rows,
    }

summary = {
    "job_id": JOB_ID,
    "auditkit": md.version("auditkit"),
    "transformers": transformers.__version__,
    "peft": md.version("peft"),
    "torch": torch.__version__,
    "base_model": BASE,
    "adapter": ADAPTER_REPO,
    "data": DATA_REPO,
    "n_val_total": len(meta),
    "n_sample": len(samples),
    "seed": SEED,
    "max_tokens": MAX_TOKENS,
    "batch_size": BATCH_SIZE,
    "temperature": 0.0,
    "hardware": str(torch.cuda.get_device_name(0)),
    "stages": {},
    "ok": False,
}
write_json(OUT / "run_summary.json", summary)

v8_result = base_result = None
v8_payload = base_payload = None

try:
    v8_model = make_model(adapter_dir, "hf:renhuang001/tally-v8-lora")
    v8_result, v8_payload, v8_slim = run_eval(v8_model, "v8")
    summary["stages"]["v8_eval"] = {"ok": True, "headline": v8_payload["headline"], "minutes": round(elapsed() / 60, 2)}
    write_json(OUT / "run_summary.json", summary)

    if elapsed() < STAGE_DEADLINE_S:
        log("red-team v8 start")
        try:
            rt = RedTeamRunner(model=v8_model).run()
            rt_payload = redteam_to_dict(rt)
            write_json(OUT / "v8_redteam.json", rt_payload)
            log(rt.summary())
            summary["stages"]["v8_redteam"] = {
                "ok": True,
                "total": rt_payload["total"],
                "passed": rt_payload["passed"],
                "failed": rt_payload["failed"],
                "invalid": rt_payload["invalid"],
                "pass_rate": rt_payload["pass_rate"],
                "by_probe": rt_payload["by_probe"],
                "minutes": round(elapsed() / 60, 2),
            }
        except Exception as exc:
            log("red-team failed:", type(exc).__name__, exc)
            traceback.print_exc()
            summary["stages"]["v8_redteam"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        write_json(OUT / "run_summary.json", summary)
    else:
        log("skip red-team: past stage deadline")
        summary["stages"]["v8_redteam"] = {"ok": False, "error": "skipped, past stage deadline"}

    # free v8 before loading base
    try:
        v8_model.unload()
    except Exception as exc:
        log("unload v8:", type(exc).__name__, exc)
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    if elapsed() < STAGE_DEADLINE_S:
        base_model = make_model(BASE, "hf:CohereLabs/tiny-aya-global")
        base_result, base_payload, base_slim = run_eval(base_model, "base")
        summary["stages"]["base_eval"] = {"ok": True, "headline": base_payload["headline"], "minutes": round(elapsed() / 60, 2)}
        try:
            base_model.unload()
        except Exception:
            pass
        if v8_result is not None and base_result is not None:
            try:
                cmp = ak.compare(base_result, v8_result)
                cmp_text = cmp.summary() if hasattr(cmp, "summary") else str(cmp)
                log("compare base vs v8:\n", cmp_text)
                write_json(OUT / "compare_base_vs_v8.json", {
                    "summary": cmp_text,
                    "base_headline": headline_of(base_result),
                    "v8_headline": headline_of(v8_result),
                })
                summary["stages"]["compare"] = {"ok": True, "summary": cmp_text}
            except Exception as exc:
                log("compare failed:", type(exc).__name__, exc)
                traceback.print_exc()
                summary["stages"]["compare"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                write_json(OUT / "compare_base_vs_v8.json", {
                    "base_headline": headline_of(base_result),
                    "v8_headline": headline_of(v8_result),
                })
        write_json(OUT / "run_summary.json", summary)
    else:
        log("skip base eval: past stage deadline")
        summary["stages"]["base_eval"] = {"ok": False, "error": "skipped, past stage deadline"}

    summary["ok"] = bool(summary["stages"].get("v8_eval", {}).get("ok"))
    summary["wall_minutes"] = round(elapsed() / 60, 2)
    write_json(OUT / "run_summary.json", summary)
    log("DONE ok=", summary["ok"], "minutes=", summary["wall_minutes"], "dir=", OUT)

except Exception as exc:
    log("FATAL:", type(exc).__name__, exc)
    traceback.print_exc()
    summary["ok"] = False
    summary["fatal"] = f"{type(exc).__name__}: {exc}"
    summary["wall_minutes"] = round(elapsed() / 60, 2)
    write_json(OUT / "run_summary.json", summary)
    sys.exit(1)
