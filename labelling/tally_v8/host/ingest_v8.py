#!/usr/bin/env python3
"""Ingest the Antigravity v8 return zip and build /workspace/tally/curated_v8.

    python3 ingest_v8.py [path/to/tally_v8_return.zip] [--out DIR]

Steps (any failure stops with a non-zero exit; nothing is uploaded anywhere):
 1. Unpack the return zip into a scratch copy of the package (tools/work/sources come from OUR package,
    only labels/ and out/ come from the zip, so returned code can never run).
 2. Run the package validator --final there: quote substrings, schema, held-out leak, split, rebuild match.
 3. Box-only checks: no labelled quote occurs in the held-out or Miro/Bandai texts; no labelled chunk is a
    near-copy (>50% 12-word shingles) of those texts.
 4. Rebuild the sets with the same v8lib code, count real Tiny Aya tokens, drop anything over MAX_SEQ.
 5. Build the Miro+Bandai eval set with the v8 chunker (doc-level scoring, no labels needed), keep the v7-chunk
    copy for apples-to-apples, and build v8-chunked held-out prompts in /workspace/tally/heldout_v8/ (not in curated_v8).
 6. Compare v8 labels with the v7 Claude labels at document level (agreement report).
 7. Write curated_v8/ in the layout the training notebook expects. HF_TOKEN is never read or printed.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE / "package" / "tally_v8"
TALLY = Path("/workspace/tally")
sys.path.insert(0, str(PKG / "tools"))
import v8lib as L  # noqa: E402

TOK_PATH = TALLY / "sft_out" / "tally-lora" / "tokenizer.json"
MAX_SEQ = 4096
TEMPLATE_OVERHEAD = 24  # chat-template special tokens around user + assistant turns
EVAL_DOCS = {
    "2410_Miro-Ghana_Verification_2020-2022": TALLY / "run_output/tally/text/2410_Miro-Ghana_Verification_2020-2022.txt",
    "2929_Bandai-Hills-Ghana_Validation_2024": TALLY / "run_output/tally/text/2929_Bandai-Hills-Ghana_Validation_2024.txt",
}
HELDOUT_TEXT = TALLY / "heldout" / "text"
HELDOUT_KEY = TALLY / "heldout" / "answer_key_heldout.json"
V7_LABELS = TALLY / "incoming_v7" / "labels_fixed.jsonl"
V7_DIR = TALLY / "curated_v7"


def fail(msg):
    print("INGEST FAILED:", msg)
    sys.exit(1)


def shingles(t, n=12):
    w = re.findall(r"\w+", t.lower())
    return {" ".join(w[i:i + n]) for i in range(0, max(0, len(w) - n + 1))}


def tokenizer():
    try:
        from tokenizers import Tokenizer
    except ImportError:
        venv = TALLY / ".venv-curator" / "bin" / "python3"
        if venv.exists() and Path(sys.executable) != venv:
            print("re-running with", venv, "(has `tokenizers`)")
            sys.exit(subprocess.call([str(venv)] + sys.argv))
        fail("python package `tokenizers` not available")
    return Tokenizer.from_file(str(TOK_PATH))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", nargs="?", default=str(HERE / "incoming" / "tally_v8_return.zip"))
    ap.add_argument("--out", default=str(TALLY / "curated_v8"))
    ap.add_argument("--scratch", default=str(HERE / "incoming" / "scratch"))
    a = ap.parse_args()
    zp, out, scratch = Path(a.zip), Path(a.out), Path(a.scratch)
    if not zp.is_file():
        fail(f"zip not found: {zp}")

    # 1. scratch = our package + returned labels/out only
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(PKG, scratch, ignore=shutil.ignore_patterns("labels", "out", "__pycache__", "*.zip"))
    (scratch / "labels").mkdir()
    taken = collections.Counter()
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            name = info.filename
            if info.is_dir():
                continue
            parts = Path(name).parts
            if ".." in parts or name.startswith("/"):
                fail(f"unsafe path in zip: {name}")
            if re.fullmatch(r"labels/batch_\d{4}\.jsonl", name) or re.fullmatch(r"out/[A-Za-z0-9_.]+\.(jsonl|json)", name):
                dest = scratch / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(info))
                taken[parts[0]] += 1
            elif name == "work/manifest.json":
                if json.loads(z.read(info).decode("utf-8")) != json.loads(L.read_text(PKG / "expected" / "manifest_expected.json")):
                    fail("returned work/manifest.json differs from the package manifest")
            elif name == "AGENT_NOTES.md":
                (HERE / "incoming").mkdir(exist_ok=True)
                (HERE / "incoming" / "AGENT_NOTES.md").write_bytes(z.read(info))
    print("from zip:", dict(taken))

    # 2. package validator (our copy of the code)
    r = subprocess.run([sys.executable, "tools/validate_v8.py", "--final"], cwd=scratch, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-500:])
    if r.returncode != 0:
        print(r.stdout[-4000:])
        fail("package validator --final reported errors (see above)")

    sys.path.insert(0, str(scratch / "tools"))
    import validate_v8 as V  # noqa: E402
    V.ROOT = scratch
    state = V.load_state()
    labels = []
    for b in state["index"]:
        e, objs = V.check_batch(state, b)
        if not e:
            labels += objs
    chunks = state["chunks"]

    # 3. held-out / eval content checks
    banned_texts = [L.read_text(p) for p in sorted(HELDOUT_TEXT.glob("*.txt"))] + [L.read_text(p) for p in EVAL_DOCS.values()]
    banned_flat = [L.flat(t) for t in banned_texts]
    banned_sh = set()
    for t in banned_texts:
        banned_sh |= shingles(t)
    dropped_quote, dropped_copy = [], []
    clean = []
    for lab in labels:
        c = chunks[lab["chunk_id"]]
        sh = shingles(L.chunk_body(c["text"]))
        if sh and len(sh & banned_sh) / len(sh) > 0.5:
            dropped_copy.append(lab["chunk_id"])
            continue
        lab = json.loads(json.dumps(lab))
        for f in L.ALL_FIELDS:
            v = lab["fields"][f]
            if isinstance(v, dict) and any(L.flat(v["quote"]) in bt for bt in banned_flat) and re.search(r"\d", v["value"]):
                dropped_quote.append(f"{lab['chunk_id']}:{f}")
                lab["fields"][f] = "not_stated"
                lab["conflicts"] = [k for k in lab["conflicts"] if k["field"] != f]
        clean.append(lab)
    print(f"held-out checks: {len(dropped_copy)} near-copy chunks dropped, {len(dropped_quote)} values with a quote found in held-out/eval text dropped")

    # 4. rebuild + real token counts
    train, val, stats = L.build_sets(chunks, clean)
    tok = tokenizer()

    def ntok(e):
        return sum(len(tok.encode(m["content"], add_special_tokens=False).ids) for m in e["messages"]) + TEMPLATE_OVERHEAD

    over = []
    for rows in (train, val):
        keep = []
        for e in rows:
            e["n_tokens"] = ntok(e)
            (keep if e["n_tokens"] <= MAX_SEQ else over).append(e)
        rows[:] = keep
    toks = [e["n_tokens"] for e in train + val]
    print(f"tokens: max {max(toks)}, mean {sum(toks) / len(toks):.0f}, dropped over {MAX_SEQ}: {len(over)}")

    # 5. eval sets
    out.mkdir(parents=True, exist_ok=True)
    v7_train = json.loads(L.read_text(V7_DIR / "train_sft_messages.jsonl").split("\n", 1)[0])["messages"][0]["content"]
    if v7_train[: v7_train.find("\n\nPages ")] != L.PROMPT:
        fail("v8 PROMPT is not byte-identical to the v7 training prompt header")
    ev_msgs, ev_meta = [], []
    for doc, p in EVAL_DOCS.items():
        for c in L.chunk_document(doc, L.read_text(p)):
            u = L.user_message(L.PROMPT, c["start_page"], c["end_page"], c["text"])
            ev_msgs.append({"messages": [{"role": "user", "content": u}, {"role": "assistant", "content": "{}"}]})
            ev_meta.append({"id": c["chunk_id"], "doc": doc, "project": c["project"], "split": "eval", "chunk_index": c["chunk_index"],
                            "start_page": c["start_page"], "end_page": c["end_page"], "section": c["section"],
                            "n_tokens": len(tok.encode(u, add_special_tokens=False).ids)})
    L.write_jsonl(out / "val_miro_bandai_messages.jsonl", ev_msgs)
    L.write_jsonl(out / "val_miro_bandai_with_metadata.jsonl", ev_meta)
    shutil.copy2(V7_DIR / "val_miro_bandai_messages.jsonl", out / "val_miro_bandai_v7chunks_messages.jsonl")
    shutil.copy2(V7_DIR / "val_miro_bandai_with_metadata.jsonl", out / "val_miro_bandai_v7chunks_with_metadata.jsonl")
    for fn in ["answer_key.json", "tinyaya_scores.json", "tally_merge.py", "score_extractions.py", "lexsi_provenance.json"]:
        if (V7_DIR / fn).exists():
            shutil.copy2(V7_DIR / fn, out / fn)
    # held-out prompts, v8 chunking, kept OUTSIDE curated_v8
    ho_dir = TALLY / "heldout_v8"
    ho_dir.mkdir(exist_ok=True)
    key = json.loads(L.read_text(HELDOUT_KEY))
    hm, hmeta = [], []
    for doc in key:
        p = HELDOUT_TEXT / f"{doc}.txt"
        if not p.exists():
            continue
        for c in L.chunk_document(doc, L.read_text(p)):
            hm.append({"messages": [{"role": "user", "content": L.user_message(L.PROMPT, c["start_page"], c["end_page"], c["text"])}]})
            hmeta.append({"doc": doc, "chunk_index": c["chunk_index"], "start_page": c["start_page"], "end_page": c["end_page"]})
    L.write_jsonl(ho_dir / "heldout_messages.jsonl", hm)
    L.write_jsonl(ho_dir / "heldout_meta.jsonl", hmeta)

    # 6. agreement with v7 Claude labels (document level, normalised numbers)
    def nv(x):
        return re.sub(r"[\s,'\u2019]", "", str(x)).lower()
    v7 = collections.defaultdict(set)
    for line in L.read_text(V7_LABELS).split("\n"):
        if line.strip():
            o = json.loads(line)
            for f, v in o["fields"].items():
                if isinstance(v, dict) and f in L.FIELDS:
                    v7[(o["chunk_id"].split("::")[0], f)].add(nv(v["value"]))
    v8 = collections.defaultdict(set)
    for lab in clean:
        doc = lab["chunk_id"].split("::")[0]
        for f in L.FIELDS:
            v = lab["fields"][f]
            if isinstance(v, dict):
                v8[(doc, f)].add(nv(v["value"]))
    agree = collections.Counter()
    rows = []
    for k in sorted(set(v7) | set(v8)):
        a7, a8 = v7.get(k, set()), v8.get(k, set())
        if not a7 or not a8:
            agree["only_v7" if a7 else "only_v8"] += 1
        elif a7 & a8:
            agree["overlap"] += 1
        else:
            agree["disagree"] += 1
            rows.append(f"| {k[0]} | {k[1]} | {', '.join(sorted(a7))[:80]} | {', '.join(sorted(a8))[:80]} |")
    rep = ["# v8 (Gemini) vs v7 (Claude) labels, document level", "", f"{dict(agree)}", "",
           "| doc | field | v7 values | v8 values |", "|---|---|---|---|"] + rows
    L.write_text(out / "agreement_v7_v8.md", "\n".join(rep) + "\n")
    print("agreement with v7:", dict(agree))

    # 7. write curated_v8
    for e in train + val:
        e.pop("est_tokens", None)
    L.write_sets(out, train, val, stats)
    for fn, src in (("train.jsonl", "train_sft_messages.jsonl"), ("val.jsonl", "val_sft_messages.jsonl"), ("validation.jsonl", "val_sft_messages.jsonl")):
        shutil.copy2(out / src, out / fn)
    stats.update({
        "n_train": len(train), "n_val": len(val),
        "ingest": {"zip": str(zp), "dropped_near_copy_chunks": dropped_copy, "dropped_heldout_quotes": dropped_quote,
                   "dropped_over_max_seq": [e["id"] for e in over], "max_seq": MAX_SEQ,
                   "max_tokens": max(toks), "mean_tokens": round(sum(toks) / len(toks)),
                   "eval_miro_bandai_v8_chunks": len(ev_msgs), "heldout_v8_prompts": len(hm),
                   "agreement_v7": dict(agree), "tokenizer": str(TOK_PATH)},
    })
    L.write_text(out / "stats.json", json.dumps(stats, indent=2, ensure_ascii=False) + "\n")
    g_tr = {e["project_group"] for e in train}
    g_va = {e["project_group"] for e in val}
    assert not g_tr & g_va, "group overlap"
    for e in train + val:
        assert e["project"] not in L.BANNED_PROJECTS
    readme = f"""# Tally SFT v8

Private chat examples for fine-tuning CohereLabs/tiny-aya-global. Built by ingest_v8.py from the Antigravity (Gemini) labels.

- Section-aware chunks (v8 chunker: headings, whole tables, 200-token overlap on mid-section cuts, about 1,000 real tokens per chunk, max {max(toks)} tokens per example incl. prompt and answer).
- Example kinds: full 7-field extraction (same prompt as v7), single-field (stated, hard negatives from rejected candidates, plain not-stated), and conflict_pick (candidate list + reason + correct pick).
- Weak fields ({', '.join(L.WEAK_FIELDS)}) oversampled x{L.WEAK_OVERSAMPLE} in train only. Empty full examples at most {int(L.NEG_SHARE * 100)}% of full examples.
- Train/val split by project_group: train {len(train)} examples / {len(g_tr)} groups, val {len(val)} examples / {len(g_va)} groups, no overlap.
- Held-out 5172, 5432, 4329, 2928 and eval-only Miro 2410 / Bandai 2929 are excluded from train and val.
- `val_miro_bandai_*.jsonl` = Miro+Bandai prompts chunked with the v8 chunker (doc-level scoring against answer_key.json); `val_miro_bandai_v7chunks_*` = the v7 23-chunk set for an apples-to-apples comparison.
- At inference, documents must be chunked with the v8 chunker (`antigravity_v8/package/tally_v8/tools/v8lib.py: chunk_document`).
"""
    L.write_text(out / "README.md", readme)
    meta = {"title": "tally-sft-v8-data", "id": "renhuang01/tally-sft-v8-data", "licenses": [{"name": "other"}],
            "isPrivate": True, "keywords": [], "collaborators": [], "data": [],
            "subtitle": "Private Tally SFT v8 data (section-aware chunks, Gemini labels, project_group split)",
            "description": "Private. Not for public release."}
    L.write_text(out / "dataset-metadata.json", json.dumps(meta, indent=2) + "\n")
    print(json.dumps({k: stats[k] for k in ["labelled_chunks", "n_train", "n_val", "train_kinds", "val_kinds", "val_groups"]}, indent=1))
    print("curated_v8 written to", out, "(nothing uploaded)")


if __name__ == "__main__":
    main()
