#!/usr/bin/env python3
"""Re-merge saved chunk outputs with merge v1 and merge v2, and rescore both.

No GPU needed. The v1 merge is replayed on the same document text, so the
before/after comparison changes only the merge step.

This public copy ships no held-out documents, answers or outputs. Point it at
your own copies:

  HELDOUT_DATA_DIR   heldout_messages.jsonl, heldout_meta.jsonl, answer_key_heldout.json
  RESULTS_DIR        <model>_heldout_scores.json from benchmark/bench_a100.py
  VAL_DIR            optional: val_messages.jsonl, val_meta.jsonl, answer_key.json,
                     finetuned_val_scores.json, base_val_scores.json
  OUT_DIR            default ./rescore_merge_v2

Local output files contain per-pair results and gold values; keep them private.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import os

REPO = Path(__file__).resolve().parent.parent
HELDOUT = Path(os.environ["HELDOUT_DATA_DIR"])
RESULTS = Path(os.environ["RESULTS_DIR"])
VAL = Path(os.environ["VAL_DIR"]) if os.environ.get("VAL_DIR") else None
OUT = Path(os.environ.get("OUT_DIR", "rescore_merge_v2"))
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO / "scorer"))
sys.path.insert(0, str(REPO / "src"))

import tally_merge as merge_v1  # noqa: E402
import tally_merge_v2 as merge_v2  # noqa: E402
from score_extractions import score_documents  # noqa: E402


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def extract_chunk_text(user_content: str) -> str:
    """Same helper as bench_a100.py."""
    pos = user_content.find("\nPages ")
    if pos == -1:
        return user_content
    rest = user_content[pos + 1 :]
    nl = rest.find("\n")
    return rest[nl + 1 :].lstrip() if nl != -1 else rest


def doc_texts_from_messages(messages, meta):
    per_doc = defaultdict(list)
    for row, m in zip(messages, meta):
        content = row["messages"][0]["content"]
        per_doc[m["doc"]].append(extract_chunk_text(content))
    return {d: "\n\n".join(texts) for d, texts in per_doc.items()}


def notes_by_doc(raw):
    per_doc = defaultdict(list)
    for r in raw:
        per_doc[r["doc"]].append(r.get("parsed") or {"_error": r.get("error") or "missing parsed"})
    return dict(per_doc)


def overall_of(scores):
    o = scores.get("overall") or {}
    return {
        "stated_correct": o.get("stated_correct"),
        "stated_n": o.get("stated_n"),
        "stated_accuracy": o.get("stated_accuracy"),
        "correct": o.get("correct"),
        "wrong": o.get("wrong"),
        "conflict-unresolved": o.get("conflict-unresolved"),
        "correctly-abstained": o.get("correctly-abstained"),
        "hallucinated": o.get("hallucinated"),
        "accuracy_incl_abstention": o.get("accuracy_incl_abstention"),
    }


def pair_key(p):
    return (p.get("doc"), p.get("field"))


def pair_brief(p):
    return {
        "doc": p.get("doc"),
        "field": p.get("field"),
        "category": p.get("category"),
        "extract_status": p.get("extract_status"),
        "extract_value": p.get("extract_value"),
        "note": p.get("note"),
        # gold is kept in the local JSON only
        "gold_value": p.get("gold_value"),
    }


def merge_and_score(raw, texts, answer_key, merge_fn, docs=None):
    notes = notes_by_doc(raw)
    docs = docs or sorted(notes)
    merged = {}
    for d in docs:
        merged[d] = merge_fn(notes[d], doc_text=texts.get(d))
    scores = score_documents(merged, answer_key, docs=docs)
    return merged, scores


def compare_pairs(before, after):
    b = {pair_key(p): p for p in before["pairs"]}
    a = {pair_key(p): p for p in after["pairs"]}
    changes = []
    for k in b:
        if k not in a:
            continue
        pb, pa = b[k], a[k]
        if pb.get("category") != pa.get("category") or str(pb.get("extract_value")) != str(pa.get("extract_value")):
            changes.append({
                "doc": k[0],
                "field": k[1],
                "before_category": pb.get("category"),
                "after_category": pa.get("category"),
                "before_value": pb.get("extract_value"),
                "after_value": pa.get("extract_value"),
                "before_note": pb.get("note"),
                "after_note": pa.get("note"),
                "gold_value": pb.get("gold_value"),
            })
    return changes


def regression_rows(changes):
    """A stated-correct that became anything else, or a new hallucination."""
    out = []
    for c in changes:
        b, a = c["before_category"], c["after_category"]
        if b == "correct" and a != "correct":
            out.append(c)
        elif b == "correctly-abstained" and a != "correctly-abstained":
            out.append(c)
        elif a == "hallucinated" and b != "hallucinated":
            out.append(c)
    return out


def run_bundle(name, raw_path, messages, meta, answer_key, label=None):
    saved = load_json(raw_path)
    raw = saved["raw"]
    texts = doc_texts_from_messages(messages, meta)
    # only the docs present in this bundle
    docs = sorted({r["doc"] for r in raw})
    # filter answer key to those docs
    ak = {d: answer_key[d] for d in docs if d in answer_key}

    merged_v1, scores_v1 = merge_and_score(raw, texts, ak, merge_v1.merge_notes, docs=docs)
    merged_v2, scores_v2 = merge_and_score(raw, texts, ak, merge_v2.merge_notes, docs=docs)

    # Replay check: v1 vs the scores stored with the raw outputs
    saved_overall = (saved.get("scores") or {}).get("overall") or saved.get("summary") or {}
    replay = overall_of(scores_v1)
    saved_brief = {
        "stated_correct": saved_overall.get("stated_correct"),
        "stated_n": saved_overall.get("stated_n") or saved_overall.get("stated_n"),
        "conflict-unresolved": saved_overall.get("conflict-unresolved"),
        "hallucinated": saved_overall.get("hallucinated"),
    }

    changes = compare_pairs(scores_v1, scores_v2)
    regressions = regression_rows(changes)
    record = {
        "name": name,
        "label": label or saved.get("summary", {}).get("label") or saved.get("label") or name,
        "source": str(raw_path),
        "n_chunks": len(raw),
        "docs": docs,
        "v1_replay_of_saved": {
            "saved": saved_brief,
            "replay": {k: replay[k] for k in ("stated_correct", "stated_n", "conflict-unresolved", "hallucinated")},
            "matches_stated": replay.get("stated_correct") == saved_brief.get("stated_correct")
            and replay.get("conflict-unresolved") == saved_brief.get("conflict-unresolved")
            and replay.get("hallucinated") == saved_brief.get("hallucinated"),
        },
        "before": overall_of(scores_v1),
        "after": overall_of(scores_v2),
        "n_pair_changes": len(changes),
        "changes": changes,
        "regressions": [
            {"doc": r["doc"], "field": r["field"],
             "before_category": r["before_category"], "after_category": r["after_category"]}
            for r in regressions
        ],
        "scores_v1": scores_v1,
        "scores_v2": scores_v2,
        "merged_v1": merged_v1,
        "merged_v2": merged_v2,
    }
    return record


def public_view(record):
    """Gold-free summary for reporting."""
    def strip_gold(changes):
        out = []
        for c in changes:
            out.append({k: v for k, v in c.items() if k != "gold_value"})
        return out
    return {
        "name": record["name"],
        "label": record["label"],
        "docs": record["docs"],
        "n_chunks": record["n_chunks"],
        "v1_replay_of_saved": record["v1_replay_of_saved"],
        "before": record["before"],
        "after": record["after"],
        "n_pair_changes": record["n_pair_changes"],
        "changes": strip_gold(record["changes"]),
        "regressions": record["regressions"],
    }


def main():
    heldout_msgs = load_jsonl(HELDOUT / "heldout_messages.jsonl")
    heldout_meta = load_jsonl(HELDOUT / "heldout_meta.jsonl")
    heldout_ak = load_json(HELDOUT / "answer_key_heldout.json")

    models = ["v8", "v7", "base", "qwen3-8b", "gemma-3-12b"]
    heldout_records = []
    for m in models:
        path = RESULTS / f"{m}_heldout_scores.json"
        rec = run_bundle(f"heldout_{m}", path, heldout_msgs, heldout_meta, heldout_ak, label=m)
        heldout_records.append(rec)
        # write per-model local file (includes gold in scores)
        (OUT / f"{m}_heldout_merge_v2.json").write_text(
            json.dumps({
                "label": rec["label"],
                "before": rec["before"],
                "after": rec["after"],
                "changes": rec["changes"],
                "regressions": rec["regressions"],
                "scores": rec["scores_v2"],
                "merged": rec["merged_v2"],
                "v1_replay_of_saved": rec["v1_replay_of_saved"],
            }, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"HELDOUT {m}: {rec['before']['stated_correct']}/{rec['before']['stated_n']} -> "
              f"{rec['after']['stated_correct']}/{rec['after']['stated_n']}  "
              f"conflicts {rec['before']['conflict-unresolved']} -> {rec['after']['conflict-unresolved']}  "
              f"hallu {rec['before']['hallucinated']} -> {rec['after']['hallucinated']}  "
              f"replay_ok={rec['v1_replay_of_saved']['matches_stated']}")

    # Validation documents (not used to design the rules): v7 and base
    val_sources = []
    if VAL:
        val_msgs = load_jsonl(VAL / "val_messages.jsonl")
        val_meta = load_jsonl(VAL / "val_meta.jsonl")
        val_ak = load_json(VAL / "answer_key.json")
        val_sources = [
            ("val_v7_finetuned", VAL / "finetuned_val_scores.json", "v7_finetuned"),
            ("val_v7_base", VAL / "base_val_scores.json", "v7_base"),
        ]
    val_records = []
    for name, path, label in val_sources:
        rec = run_bundle(name, path, val_msgs, val_meta, val_ak, label=label)
        val_records.append(rec)
        (OUT / f"{name}_merge_v2.json").write_text(
            json.dumps({
                "label": rec["label"],
                "before": rec["before"],
                "after": rec["after"],
                "changes": rec["changes"],
                "regressions": rec["regressions"],
                "scores": rec["scores_v2"],
                "merged": rec["merged_v2"],
                "v1_replay_of_saved": rec["v1_replay_of_saved"],
            }, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"VAL {label}: {rec['before']['stated_correct']}/{rec['before']['stated_n']} -> "
              f"{rec['after']['stated_correct']}/{rec['after']['stated_n']}  "
              f"conflicts {rec['before']['conflict-unresolved']} -> {rec['after']['conflict-unresolved']}  "
              f"hallu {rec['before']['hallucinated']} -> {rec['after']['hallucinated']}  "
              f"replay_ok={rec['v1_replay_of_saved']['matches_stated']}")

    summary = {
        "rules": [
            "Crediting period: prefer a dated start–end over a bare duration or an unchecked VCS template checkbox.",
            "Crediting period: prefer dates labelled as the crediting period over a verification, monitoring, or historical-reference window.",
            "Area: prefer the credited project area over the project zone, a leakage belt, a reference region, a land holding, or a concession (do not demote ‘leased’ project-area wording).",
            "Estimated reductions: collapse European and US number formats so 1.234,567 and 1,234,567 count as the same value.",
            "Estimated reductions: prefer a project or document-scope total over an annual average or a single vintage-year row; do not prefer a lifetime total over a labelled monitoring-period total.",
            "Baseline: do not reject a tCO2e total only because the quote lacks the word ‘baseline’; still reject bare areas, bare percentages, bare numbers, and clearly project-benefit figures (VCU issuance, net removals, sequestration) when no baseline cue is present.",
            "Quote-must-appear-in-the-document and value-must-appear-in-the-quote grounding is unchanged from merge v1.",
        ],
        "heldout": [public_view(r) for r in heldout_records],
        "validation": [public_view(r) for r in val_records],
    }
    (OUT / "comparison_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print("wrote", OUT / "comparison_summary.json")


if __name__ == "__main__":
    main()
