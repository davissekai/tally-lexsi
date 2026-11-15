"""Build the v5 Tally SFT set: v4's 62 train examples + chunk examples from 13 new Verra PDs.
Same chunker (chunk_merge.chunk_doc, 3,500 tokens, 300 overlap, Tiny Aya tokenizer), same prompt,
same answer JSON shape, same CuratorKIT 0.1.27 clean+dedup config, same v4 trim (<=5,400 tokens).
Validation is copied byte-for-byte from the v4 dataset. No LLM calls."""
import json, re, sys, random, shutil, collections, hashlib
from pathlib import Path
from paths import prepend_import_paths
ROOT = prepend_import_paths()
import build_and_curate as B
import rebalance as R  # split_user, trim, ntok (Tiny Aya tokenizer), MAX_CONTENT_TOKENS=5400
from tokenizers import Tokenizer

FIELDS = R.FIELDS; SEED = 42; NEG_SHARE = 0.175
V5 = ROOT / "sft_v5"; OUT = V5 / "dataset"; WORK = V5 / "work"
V4 = ROOT / "sft_rebalance" / "dataset_v2"
KEY = json.loads((ROOT / "data_expansion/answer_key_v5.json").read_text(encoding="utf-8"))
CHUNKS = json.loads((V5 / "chunks_new.json").read_text(encoding="utf-8"))
norm = lambda s: re.sub(r"\s+", " ", s).strip()
assert R.TOK is not None, "Tiny Aya tokenizer not loaded"

def page_of(chunk_text, quote):
    n = norm(chunk_text); i = n.find(quote)
    pgs = re.findall(r"--- page (\d+) ---", n[:i]); return int(pgs[-1]) if pgs else None

def targets_for(stem, text):
    gold = KEY[stem]; tg = {}; why = {}
    nt = norm(text)
    for f in FIELDS:
        g = gold[f]
        if g["quote"] is None: tg[f] = "not stated"; why[f] = "gold_not_stated"; continue
        cands = [g["quote"]] + [a["quote"] for a in g.get("alt_quotes", [])]
        hit = next((q for q in cands if q in nt), None)
        if hit is None: tg[f] = "not stated"; why[f] = "quote_not_in_chunk"; continue
        tg[f] = {"value": g["gold_value"], "page": page_of(text, hit), "quote": hit}
        why[f] = "primary_quote" if hit == g["quote"] else "alt_quote"
    return tg, why

# ---- 1. new raw examples ------------------------------------------------------------
new = []
for stem, chunks in CHUNKS.items():
    for i, ch in enumerate(chunks):
        tg, why = targets_for(stem, ch["text"])
        pos = [f for f in FIELDS if tg[f] != "not stated"]
        new.append({"id": f"{stem}::chunk-{i:03d}", "doc": stem, "project": stem.split("_")[0], "split": "train",
                    "chunk_index": i, "start_page": ch["start_page"], "end_page": ch["end_page"],
                    "instruction": B.user_message(ch), "input": "", "output": json.dumps(tg, ensure_ascii=False),
                    "task_type": "instruction_following", "source_dataset": "has_positive" if pos else "all_negative",
                    "source_uri": f"data_expansion/text/{stem}.txt",
                    "positive_fields": pos, "match_reasons": why})
# v4 train (62 rows incl. 4 intentional additionality duplicates)
v4_meta = [json.loads(l) for l in open(V4 / "train_rebalanced_with_metadata.jsonl", encoding="utf-8")]
v4_ids = [r["id"] for r in v4_meta]
v4_unique = {}
for r in v4_meta: v4_unique.setdefault(r["id"], r)
v4_rows = [{"id": "v4::" + r["id"], "instruction": r["messages"][0]["content"], "input": "", "output": r["messages"][1]["content"],
            "task_type": "instruction_following", "source_dataset": "v4_train"} for r in v4_unique.values()]
WORK.mkdir(parents=True, exist_ok=True)
raw = WORK / "merged_raw_alpaca.jsonl"
with open(raw, "w", encoding="utf-8") as f:
    for r in v4_rows + new:
        f.write(json.dumps({k: r[k] for k in ("id", "instruction", "input", "output", "task_type", "source_dataset")}, ensure_ascii=False) + "\n")
print("raw pool:", len(v4_rows), "v4 unique +", len(new), "new chunks")

# ---- 2. CuratorKIT (same config as build_and_curate.run_curatorkit) -----------------
B.CK_DIR = V5 / "curatorkit_run"
res = B.run_curatorkit(raw)
passed = {s.id: s for s in res.passed}
rejected = [{"id": getattr(s, "id", None), "reason": getattr(s, "rejection_reason", None), "step": getattr(s, "rejecting_step", None)}
            for s in (getattr(res, "rejected", None) or [])]
print("curatorkit passed", len(passed), "rejected", len(rejected))
(WORK / "curatorkit_rejected.json").write_text(json.dumps(rejected, indent=1, ensure_ascii=False))

# ---- 3. take cleaned new rows, re-verify quotes against the cleaned chunk, trim ------
HEADER_V4 = R.split_user(v4_meta[0]["messages"][0]["content"])[0]
qstats = collections.Counter(); kept_new = []
for r in new:
    s = passed.get(r["id"])
    if s is None: qstats["rejected_by_curatorkit"] += 1; continue
    prompt, sp, ep, chunk = R.split_user(s.instruction)
    assert prompt == HEADER_V4, "prompt header differs from v4"
    out = json.loads(s.output); nchunk = norm(chunk)
    for f in FIELDS:
        if isinstance(out[f], dict):
            qstats["positive_targets"] += 1
            if out[f]["quote"] in nchunk: qstats["quote_in_cleaned_chunk"] += 1
            else: qstats["quote_FAIL"] += 1; out[f] = "not stated"
    pos = [f for f in FIELDS if isinstance(out[f], dict)]
    ev = {out[f]["page"] for f in pos}
    chunk2, sp2, ep2 = R.trim(chunk, ev, prompt, sp, ep)
    if chunk2 != chunk: qstats["trimmed"] += 1
    for f in pos:  # trimming only drops evidence-free pages, but re-check
        if out[f]["quote"] not in norm(chunk2): qstats["quote_lost_in_trim"] += 1; out[f] = "not stated"
    pos = [f for f in FIELDS if isinstance(out[f], dict)]
    user = f"{prompt}\n\nPages {sp2}-{ep2}:\n\n{chunk2}"
    kept_new.append({**{k: r[k] for k in ("id", "doc", "project", "chunk_index")}, "start_page": sp2, "end_page": ep2,
                     "positive_fields": pos, "n_tokens": R.ntok(user), "source": "v5_new",
                     "messages": [{"role": "user", "content": user}, {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)}]})
v4_rej = [i for i in v4_unique if "v4::" + i not in passed]
print("v4 rows rejected by curatorkit:", v4_rej)

# ---- 4. rebalance: all positives + sampled negatives, seed 42 ------------------------
v4_final = [{"id": r["id"], "doc": r["id"].split("::")[0], "project": r["id"].split("_")[0], "positive_fields": r["positive_fields"],
             "n_tokens": r["n_tokens"], "source": "v4_train", "messages": r["messages"]} for r in v4_meta]  # all 62 kept verbatim
npos_v4 = sum(1 for r in v4_final if r["positive_fields"]); nneg_v4 = len(v4_final) - npos_v4
posn = [r for r in kept_new if r["positive_fields"]]; negn = [r for r in kept_new if not r["positive_fields"]]
P = npos_v4 + len(posn)
n_neg_total = round(NEG_SHARE * P / (1 - NEG_SHARE))
n_neg_new = max(0, min(len(negn), n_neg_total - nneg_v4))
rng = random.Random(SEED)
neg_s = rng.sample(negn, n_neg_new)
final = v4_final + posn + neg_s
rng.shuffle(final)

# ---- 5. leak checks ------------------------------------------------------------------
def shingles(t, n=12):
    w = norm(t).split(); return {" ".join(w[i:i + n]) for i in range(0, max(0, len(w) - n + 1))}
banned = {}
for p in list((ROOT / "run_output/tally/text").glob("2410_*.txt")) + list((ROOT / "run_output/tally/text").glob("2929_*.txt")) + list((ROOT / "heldout/text").glob("*.txt")):
    banned[p.stem] = shingles(p.read_text(encoding="utf-8"))
PROMPT_SH = shingles(HEADER_V4)
leak = {}
for r in final:
    if r["source"] != "v5_new": continue
    sh = shingles(R.split_user(r["messages"][0]["content"])[3]) - PROMPT_SH
    for k, b in banned.items():
        n = len(sh & b)
        if n: leak.setdefault(k, collections.Counter())[r["id"]] = n
name_hits = collections.Counter()
for r in final:
    c = R.split_user(r["messages"][0]["content"])[3]
    for pat in [r"\bMiro\b", r"\bBandai\b", r"\bAkwaaba\b", r"\bKwahu\b", r"\bCRCF\b", r"\b(?:VCS|ID|project)\s*#?\s*(?:2410|2929|2928|5172|5432|4329)\b"]:
        if re.search(pat, c): name_hits[(pat, r["id"])] += 1
bad_docs = [r["id"] for r in final if re.match(r"(2410|2929|2928|5172|5432|4329)_", r["doc"])]

# ---- 6. write -------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)
def wj(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for x in rows: f.write(json.dumps(x, ensure_ascii=False) + "\n")
msgs = [{"messages": r["messages"]} for r in final]
wj(OUT / "train.jsonl", msgs); wj(OUT / "train_sft_messages.jsonl", msgs); wj(OUT / "train_sft_messages_rebalanced.jsonl", msgs)
wj(OUT / "train_rebalanced_with_metadata.jsonl", final)
wj(OUT / "train_sft_alpaca.jsonl", [{"instruction": r["messages"][0]["content"], "input": "", "output": r["messages"][1]["content"]} for r in final])
for fn in ["val_sft_messages.jsonl", "val_sft_with_metadata.jsonl", "val_sft_alpaca.jsonl", "answer_key.json", "tinyaya_scores.json",
           "tally_merge.py", "score_extractions.py", "lexsi_provenance.json"]:
    shutil.copy2(V4 / fn, OUT / fn)
shutil.copy2(V4 / "val_sft_messages.jsonl", OUT / "validation.jsonl")
shutil.copy2(ROOT / "data_expansion/answer_key_v5.json", OUT / "answer_key_v5.json")
for fn in ["manifest.json", "dataset_card.md", "checksums.txt"]:
    p = B.CK_DIR / fn
    if p.exists(): shutil.copy2(p, OUT / ("curatorkit_" + fn))
md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
assert md5(OUT / "validation.jsonl") == md5(V4 / "val_sft_messages.jsonl") == md5(ROOT / "kaggle_sft_dataset/val_sft_messages.jsonl")

fc = collections.Counter(f for r in final for f in r["positive_fields"])
fc_new = collections.Counter(f for r in final if r["source"] == "v5_new" for f in r["positive_fields"])
per_proj = collections.defaultdict(lambda: {"examples": 0, "positive": 0, "empty": 0})
for r in final:
    k = r["project"] if r["source"] == "v5_new" else "v4:" + r["doc"]
    per_proj[k]["examples"] += 1; per_proj[k]["positive" if r["positive_fields"] else "empty"] += 1
n_empty = sum(1 for r in final if not r["positive_fields"])
pool_reasons = collections.Counter((f, why) for r in new for f, why in r["match_reasons"].items())
report = {"seed": SEED, "n_train": len(final), "n_pos_examples": P, "n_neg_sampled": nneg_v4 + n_neg_new,
          "n_additionality_dups": 4, "empty_share": round(n_empty / len(final), 3),
          "v4_examples": len(v4_final), "new_chunks_total": len(new), "new_chunks_passed_curatorkit": len(kept_new),
          "new_positive_chunks": len(posn), "new_negative_pool": len(negn), "new_negatives_sampled": n_neg_new,
          "field_positive_counts": dict(fc), "field_positive_counts_new_only": dict(fc_new),
          "per_project": dict(per_proj), "quote_checks": dict(qstats),
          "max_tokens_after_trim": max(r["n_tokens"] for r in final), "n_val": sum(1 for _ in open(OUT / "validation.jsonl")),
          "curatorkit_rejected": rejected, "v4_rows_rejected_by_curatorkit": v4_rej,
          "leak_shingle_overlap_12gram": {k: dict(v) for k, v in leak.items()},
          "name_mentions": [f"{p} in {i}" for (p, i) in name_hits], "banned_doc_rows": bad_docs,
          "new_pool_match_reasons": {f"{a}:{b}": c for (a, b), c in pool_reasons.items()},
          "tokenizer": "tiny-aya tokenizer.json", "neg_ids_new": [r["id"] for r in neg_s]}
(OUT / "rebalance_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k not in ("neg_ids_new", "per_project", "curatorkit_rejected")}, indent=1, ensure_ascii=False))
