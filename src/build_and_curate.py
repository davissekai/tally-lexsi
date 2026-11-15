#!/usr/bin/env python3
"""Build a chunk-level SFT dataset from the Tally answer key, then curate it
with Lexsi CuratorKIT (clean + exact/MinHash dedup, no LLM generation).

The 3 held-out documents (5172, 5432, 4329) are never included.
Train/val splits are assigned at the project level, not by shuffling chunks.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from paths import first_existing, prepend_import_paths

ROOT = prepend_import_paths()

from chunk_merge import (
    FIELDS,
    _ZERO_WORDS,
    _extract_numbers,
    _locate_quote,
    _norm_ws,
    _numbers_in_text,
    _page_in_doc,
    _quote_in_doc,
    chunk_doc,
)

TEXT_DIR = first_existing(
    ROOT / "run_output" / "tally" / "text",
    ROOT / "data" / "text",
) or (ROOT / "data" / "text")
RESULTS_CLEAN = first_existing(ROOT / "results_clean", ROOT / "results" / "extraction") or (ROOT / "results_clean")
# Keep the historical name used later in this file.
RESULTS_DIR = RESULTS_CLEAN
KEY_PATH = first_existing(
    ROOT / "data" / "answer_key.json",
    ROOT / "ground_truth" / "answer_key.json",
) or (ROOT / "data" / "answer_key.json")
CURATED = first_existing(ROOT / "data" / "curated", ROOT / "curated") or (ROOT / "data" / "curated")
RAW_DIR = CURATED / "raw"
CK_DIR = CURATED / "curatorkit_run"

HELD_OUT_PREFIXES = ("5172", "5432", "4329")
MAX_TOKENS = 3500
OVERLAP = 300

# Projects that must stay in the same split (shared figures / shared text).
PROJECT_OF = {
    "1340_Bale-Mountains_MR_2020-2021": "bale",
    "2410_Miro-Ghana_Verification_2020-2022": "miro",
    "2929_Bandai-Hills-Ghana_Validation_2024": "bandai",
    "562_Kasigau-I-Rukinga_PDD_2011-01-31": "kasigau_i",
    "562_Kasigau-I-Rukinga_PD_short_2011-01-25": "kasigau_i",
    "612_Kasigau-II-Community-Ranches_MR-M9_2022": "kasigau_ii",
    "612_Kasigau-II-Community-Ranches_PD_excerpt": "kasigau_ii",
    "612_Kasigau-II-Community-Ranches_Verification_2024": "kasigau_ii",
    "934_Mai-Ndombe_MR-M4_2021": "mai_ndombe",
}
# ~18% of chunks; one verification and one validation document, no shared
# numbers with the training projects.
VAL_PROJECTS = {"miro", "bandai"}

# Exact prompt used in the Kaggle extraction run (notebook cell 7d).
PROMPT = """\
You are extracting facts from part of a carbon project document (Verra VCS).
Read the text below and fill in the 7 fields.
FIELDS:
- baseline: The counterfactual/business-as-usual scenario that plays out if the project does not happen (usually a deforestation rate or baseline emissions in tCO2e)
- additionality: Proof that the project only happens because of carbon finance, and doesn't happen anyway (the test used, e.g. VT0001, investment or barrier analysis, common practice, and its conclusion)
- leakage: Emissions generated from emission-causing activities that would've been merely moved from the project site to another site (a percentage or tCO2e)
- permanence_buffer: A percentage of carbon credits reserved for insurance against project risks
- crediting_period: The period in which the project earns carbon credits, with a start and end date, often measured in years
- area: The geographical scope of the project measured in hectares
- estimated_reductions: The tCO2e avoided, per year or in total, after leakage and the buffer are deducted
RULES:
- Only use facts written in the text below. Never guess or use outside knowledge.
- Copy numbers, units and dates exactly as written (e.g. "<number> hectares", "<start year>–<end year>"). Never copy placeholder examples from these instructions.
- "quote" is the exact sentence the value came from, copied word for word, max 40 words.
- The quote must contain the value itself (the numbers and units). If no sentence supports it, the field is "not stated".
- If a field is not in the text, write only "not stated" for it: no value, page or quote.
- Keep each value short: a number with its unit, a date range, or one sentence.
- additionality is only about whether the project needs carbon finance (e.g. an additionality tool, investment or barrier analysis). Community or biodiversity co-benefits are NOT additionality.
Reply with JSON only, in exactly this shape:
{
  "baseline": {"value": "...", "page": 0, "quote": "..."},
  "additionality": {"value": "...", "page": 0, "quote": "..."},
  "leakage": {"value": "...", "page": 0, "quote": "..."},
  "permanence_buffer": {"value": "...", "page": 0, "quote": "..."},
  "crediting_period": {"value": "...", "page": 0, "quote": "..."},
  "area": {"value": "<number> hectares", "page": 0, "quote": "..."},
  "estimated_reductions": {"value": "<number> tCO2e", "page": 0, "quote": "..."}
}
If a field is not in the text, write "not stated" instead of the object, e.g. "leakage": "not stated"
"""

_AREA_UNIT = re.compile(r"\b(ha|hectares?|acres?)\b", re.I)
_PERCENT = re.compile(r"%|\bpercent(?:age)?\b", re.I)
_TCO2 = re.compile(
    r"\bt\s*co2e?\b|\btco2e\b|\btonnes?\b|\btons?\b|\bm\.?t\.?\b|\bghg\b",
    re.I,
)
_VALUE_UNIT_NEAR = {
    "area": _AREA_UNIT,
    "estimated_reductions": _TCO2,
    "baseline": _TCO2,
    "permanence_buffer": _PERCENT,
    "leakage": re.compile(
        r"%|\bpercent(?:age)?\b|\bt\s*co2e?\b|\btco2e\b|\btonnes?\b|\bzero\b|\bnone\b|\bnil\b",
        re.I,
    ),
}


class CharSpanTokenizer:
    """Reversible character-group tokenizer used to reconstruct the 3,500-token
    windows when the gated Tiny Aya tokenizer is not available.

    `chars_per_token` is calibrated per document so the number of windows
    matches the extraction run (see expected_chunks()).
    """

    def __init__(self, chars_per_token: float):
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self.chars_per_token = float(chars_per_token)
        self.table: list[str] = []

    def reset(self) -> None:
        self.table = []

    def encode(self, text, add_special_tokens=False):
        if not text:
            return []
        n = max(1, int(round(len(text) / self.chars_per_token)))
        # Split into n nearly equal character spans so decode() is exact.
        ids = []
        length = len(text)
        for i in range(n):
            start = int(round(i * length / n))
            end = int(round((i + 1) * length / n))
            if end <= start:
                end = min(length, start + 1)
            self.table.append(text[start:end])
            ids.append(len(self.table) - 1)
        return ids

    def decode(self, ids, skip_special_tokens=False):
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        return "".join(self.table[i] for i in ids)


def expected_chunks() -> dict[str, int]:
    out = {}
    for path in sorted(RESULTS_DIR.glob("*.json")):
        if path.name == "summary.csv":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        out[path.stem] = int(data["n_chunks"])
    return out


def is_held_out(stem: str) -> bool:
    return stem.startswith(HELD_OUT_PREFIXES) or any(
        stem.startswith(p + "_") or stem == p for p in HELD_OUT_PREFIXES
    )


def gold_is_stated(entry: dict) -> bool:
    value = entry.get("gold_value")
    if value is None:
        return False
    text = str(value).strip()
    return text != "" and text.upper() not in {"NOT_STATED", "NOT STATED", "NONE", "N/A"}


def distinctive_numbers(value: str) -> list[str]:
    """Numbers that are unique enough to search for in a chunk without a quote.

    4+ digit numbers (areas, tCO2e totals, years) qualify. Short figures
    such as 0, 10, 13, 20 are too common and must be tied to the gold quote
    (or to an exact '13%' / '0 tCO2e' / 'zero' phrasing).
    """
    nums = _extract_numbers(value)
    years = [n for n in nums if re.fullmatch(r"\d{4}", n)]
    if years:
        return years
    long_nums = [n for n in nums if len(n.split(".")[0]) >= 4]
    return long_nums


# Short figures such as 10% or 0 tCO2e appear in many unrelated sentences.
# Require a field-specific cue before treating them as a positive.
_FIELD_CONTEXT = {
    "permanence_buffer": re.compile(
        r"\bbuffer\b|\brisk (?:rating|score|assessment)\b|\bnon-?permanence\b|\bwithhold",
        re.I,
    ),
    "leakage": re.compile(r"\bleakage\b|\bdisplacement\b", re.I),
    "baseline": re.compile(r"\bbaseline\b", re.I),
    "area": _AREA_UNIT,
    "estimated_reductions": _TCO2,
}


def is_short_common_value(value: str) -> bool:
    nums = _extract_numbers(value)
    if not nums:
        return False
    return all(len(n.split(".")[0]) <= 2 and not re.fullmatch(r"\d{4}", n) for n in nums)


def value_phrase_in_chunk(field: str, value: str, chunk_text: str) -> bool:
    """True if the gold value itself (with units) appears in the chunk."""
    chunk_n = _norm_ws(chunk_text)
    val_n = _norm_ws(value)
    if not val_n:
        return False
    found = val_n.lower() in chunk_n.lower()
    if not found:
        compact = re.sub(r"(?<=\d)[, \u00a0\u202f](?=\d)", "", val_n)
        found = compact.lower() != val_n.lower() and compact.lower() in chunk_n.lower()
    if not found and field in ("leakage", "baseline") and _extract_numbers(value) == ["0"]:
        found = bool(_ZERO_WORDS.search(chunk_n))
    if not found:
        return False
    # Common short values need a nearby field cue so "10%" in a land-use
    # table is not labelled as the permanence buffer.
    if is_short_common_value(value):
        cue = _FIELD_CONTEXT.get(field)
        if cue is not None and not cue.search(chunk_n):
            return False
    return True


def field_target(field: str, gold: dict, chunk_text: str) -> tuple[object, str]:
    """Return (target_json_value, match_reason)."""
    if not gold_is_stated(gold):
        return "not stated", "gold_not_stated"

    value = str(gold["gold_value"])
    quote = gold.get("quote")
    page = gold.get("page")

    if _quote_in_doc(quote, chunk_text):
        if page is None:
            page = _page_in_doc(chunk_text, quote)
        return {"value": value, "page": page, "quote": quote}, "quote"

    if value_phrase_in_chunk(field, value, chunk_text):
        # Prefer the gold quote when it is also present; otherwise leave it
        # as the gold quote only if we actually found the value phrase.
        if page is None:
            page = _page_in_doc(chunk_text, value) or _page_in_doc(chunk_text, quote or "")
        return {"value": value, "page": page, "quote": quote}, "value_phrase"

    nums = distinctive_numbers(value)
    if nums and _numbers_in_text(nums, chunk_text):
        unit_re = _VALUE_UNIT_NEAR.get(field)
        if unit_re is None or unit_re.search(chunk_text):
            if page is None:
                page = _page_in_doc(chunk_text, quote or "")
            return {"value": value, "page": page, "quote": quote}, "distinctive_number"

    return "not stated", "absent"


def count_chunks(text: str, cpt: float) -> int:
    tok = CharSpanTokenizer(cpt)
    return len(chunk_doc(text, tok, max_tokens=MAX_TOKENS, overlap=OVERLAP))


def calibrate_cpt(text: str, expected: int) -> float:
    """Binary-search a chars-per-token ratio that yields `expected` windows."""
    # Higher cpt → fewer tokens → fewer chunks.
    lo, hi = 1.0, 40.0
    n_lo, n_hi = count_chunks(text, lo), count_chunks(text, hi)
    if expected > n_lo or expected < n_hi:
        raise RuntimeError(
            f"cannot hit {expected} chunks (bounds {n_lo} at cpt={lo}, {n_hi} at cpt={hi})"
        )
    matched: list[float] = []
    for _ in range(48):
        mid = (lo + hi) / 2
        n = count_chunks(text, mid)
        if n > expected:
            lo = mid
        elif n < expected:
            hi = mid
        else:
            matched.append(mid)
            # Widen a little around this hit and keep searching for a
            # midpoint, but we already have a valid value.
            break
    if not matched:
        # Walk a fine grid around the bracket.
        for cpt in [lo + (hi - lo) * i / 200 for i in range(201)]:
            if count_chunks(text, cpt) == expected:
                matched.append(cpt)
                break
    if not matched:
        raise RuntimeError(f"calibration failed for expected={expected}")
    # Prefer a cpt near 4–6 (typical for a multilingual BPE on English prose).
    target = 5.0
    return min(matched, key=lambda c: abs(c - target))


def user_message(chunk: dict) -> str:
    return (
        f"{PROMPT}\n\nPages {chunk['start_page']}-{chunk['end_page']}:\n\n"
        f"{chunk['text']}"
    )


def build_examples() -> tuple[list[dict], dict]:
    key = json.loads(KEY_PATH.read_text(encoding="utf-8"))
    expected = expected_chunks()
    examples = []
    calib = {}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "chunks").mkdir(parents=True, exist_ok=True)

    for stem, n_exp in expected.items():
        if is_held_out(stem):
            print(f"skip held-out {stem}")
            continue
        if stem not in key:
            raise SystemExit(f"no answer key for {stem}")
        text_path = TEXT_DIR / f"{stem}.txt"
        if not text_path.exists():
            raise SystemExit(f"missing text: {text_path}")
        text = text_path.read_text(encoding="utf-8")
        cpt = calibrate_cpt(text, n_exp)
        tok = CharSpanTokenizer(cpt)
        chunks = chunk_doc(text, tok, max_tokens=MAX_TOKENS, overlap=OVERLAP)
        if len(chunks) != n_exp:
            raise SystemExit(f"{stem}: got {len(chunks)} chunks, expected {n_exp}")
        calib[stem] = {
            "chars_per_token": cpt,
            "n_chunks": len(chunks),
            "mean_chunk_chars": int(sum(len(c["text"]) for c in chunks) / len(chunks)),
        }
        (RAW_DIR / "chunks" / f"{stem}.json").write_text(
            json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        project = PROJECT_OF[stem]
        split = "val" if project in VAL_PROJECTS else "train"
        gold_doc = key[stem]
        for i, chunk in enumerate(chunks):
            targets = {}
            reasons = {}
            positive = []
            for field in FIELDS:
                target, reason = field_target(field, gold_doc[field], chunk["text"])
                targets[field] = target
                reasons[field] = reason
                if target != "not stated":
                    positive.append(field)
            example_class = "has_positive" if positive else "all_negative"
            rec = {
                "id": f"{stem}::chunk-{i:03d}",
                "source_uri": str(text_path),
                "instruction": user_message(chunk),
                "input": "",
                "output": json.dumps(targets, ensure_ascii=False),
                "task_type": "instruction_following",
                "source_dataset": example_class,
                "doc": stem,
                "project": project,
                "split": split,
                "chunk_index": i,
                "start_page": chunk["start_page"],
                "end_page": chunk["end_page"],
                "n_tokens_reconstructed": chunk["n_tokens"],
                "chunk_chars": len(chunk["text"]),
                "positive_fields": positive,
                "n_positive": len(positive),
                "example_class": example_class,
                "match_reasons": reasons,
            }
            examples.append(rec)
        print(f"{stem}: {len(chunks)} chunks  cpt={cpt:.3f}  split={split}")
    return examples, calib


def field_stats(examples: list[dict]) -> dict:
    per_field = {
        f: {"positive": 0, "negative": 0, "reasons": Counter()} for f in FIELDS
    }
    by_split = defaultdict(lambda: {"examples": 0, "has_positive": 0, "all_negative": 0})
    by_doc = {}
    for ex in examples:
        by_split[ex["split"]]["examples"] += 1
        by_split[ex["split"]][ex["example_class"]] += 1
        doc_row = by_doc.setdefault(
            ex["doc"],
            {
                "split": ex["split"],
                "project": ex["project"],
                "examples": 0,
                "has_positive": 0,
                "all_negative": 0,
                "positives_by_field": Counter(),
            },
        )
        doc_row["examples"] += 1
        doc_row[ex["example_class"]] += 1
        targets = json.loads(ex["output"])
        for field in FIELDS:
            stated = targets[field] != "not stated"
            bucket = "positive" if stated else "negative"
            per_field[field][bucket] += 1
            per_field[field]["reasons"][ex["match_reasons"][field]] += 1
            if stated:
                doc_row["positives_by_field"][field] += 1
    # JSON-safe
    per_field = {
        f: {**v, "reasons": dict(v["reasons"])} for f, v in per_field.items()
    }
    by_doc = {
        d: {**v, "positives_by_field": dict(v["positives_by_field"])}
        for d, v in by_doc.items()
    }
    return {
        "n_examples": len(examples),
        "n_positive_examples": sum(1 for e in examples if e["example_class"] == "has_positive"),
        "n_negative_examples": sum(1 for e in examples if e["example_class"] == "all_negative"),
        "per_field": per_field,
        "by_split": {k: dict(v) for k, v in by_split.items()},
        "by_doc": by_doc,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def to_alpaca(row: dict) -> dict:
    return {
        "instruction": row["instruction"],
        "input": row.get("input") or "",
        "output": row["output"],
    }


def to_messages(row: dict) -> dict:
    return {
        "messages": [
            {"role": "user", "content": row["instruction"]},
            {"role": "assistant", "content": row["output"]},
        ]
    }


def to_sharegpt(row: dict) -> dict:
    return {
        "conversations": [
            {"from": "human", "value": row["instruction"]},
            {"from": "gpt", "value": row["output"]},
        ]
    }


def run_curatorkit(raw_path: Path):
    from curatorkit import Curator, CuratorConfig

    if CK_DIR.exists():
        # Fresh output_dir each run — exporters overwrite, but rejected
        # leftovers from a previous config could confuse the audit trail.
        import shutil

        shutil.rmtree(CK_DIR)
    CK_DIR.mkdir(parents=True)

    # Mask the shared extraction prompt so MinHash compares the chunk and
    # the target JSON, not the identical instructions on every row.
    ignore = [re.escape(PROMPT), r"Pages \d+-\d+:"]

    config = CuratorConfig(
        name="tally_tinyaya_sft_curation",
        dataset=str(raw_path),
        format="alpaca",
        clean=True,
        dedup="minhash",
        minhash_threshold=0.85,
        minhash_ngram=3,
        minhash_num_perm=128,
        minhash_seed=42,
        dedup_ignore_patterns=ignore,
        schema_gate=True,
        min_tokens=10,
        max_tokens=8192,  # instruction is a 3,500-token chunk plus the prompt
        use_tiktoken=False,
        # Keep <number> / <start year> placeholders in the extraction prompt.
        # CuratorKIT's default strip_html treats them as tags and deletes them.
        clean_transforms={
            "normalise_unicode": True,
            "fix_encoding_artifacts": True,
            "collapse_whitespace": True,
            "remove_control_chars": True,
            "strip_html": False,
        },
        # Hygiene / generation / random output_split are intentionally off.
        # PII replacement would rewrite gold quotes; toxicity classifiers
        # false-flag conservation text about illegal logging; a random
        # shuffle would leak chunks from the same project across splits.
        secrets_gate=False,
        pii_pseudonymize=False,
        toxicity_gate=False,
        resample=False,
        generation_task=None,
        export_formats=["alpaca", "sharegpt", "messages"],
        output_split=None,
        write_hf_readme=True,
        output_dir=str(CK_DIR),
    )
    curator = Curator(config)
    result = curator.run()
    result.print_summary()
    return result


def index_by_id(examples: list[dict]) -> dict[str, dict]:
    return {e["id"]: e for e in examples}


def export_split_files(accepted: list[dict], rejected_ids: list[str], stats_before: dict) -> dict:
    """Write train/val jsonl (AlignTune / TRL) from accepted rows, by pre-assigned split."""
    by_split = defaultdict(list)
    for row in accepted:
        by_split[row["split"]].append(row)
    for split, rows in by_split.items():
        rows.sort(key=lambda r: (r["doc"], r["chunk_index"]))
        out_dir = CURATED / split
        write_jsonl(out_dir / "sft_alpaca.jsonl", [to_alpaca(r) for r in rows])
        write_jsonl(out_dir / "sft_messages.jsonl", [to_messages(r) for r in rows])
        write_jsonl(out_dir / "sft_sharegpt.jsonl", [to_sharegpt(r) for r in rows])
        write_jsonl(out_dir / "sft_with_metadata.jsonl", rows)
        print(f"wrote {len(rows)} {split} examples → {out_dir}")

    after = field_stats(accepted)
    after["rejected_ids"] = rejected_ids
    after["n_rejected"] = len(rejected_ids)
    (CURATED / "stats_after.json").write_text(
        json.dumps(after, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (CURATED / "stats_before.json").write_text(
        json.dumps(stats_before, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return after


def main() -> None:
    print("=== 1. Build labelled SFT examples ===")
    examples, calib = build_examples()
    # Train first, then val, so exact/MinHash keep the train copy of any
    # cross-split near-duplicate.
    examples.sort(key=lambda r: (0 if r["split"] == "train" else 1, r["doc"], r["chunk_index"]))
    stats_before = field_stats(examples)
    stats_before["calibration"] = calib
    stats_before["held_out_documents"] = list(HELD_OUT_PREFIXES)
    stats_before["val_projects"] = sorted(VAL_PROJECTS)
    stats_before["chunking"] = {
        "max_tokens": MAX_TOKENS,
        "overlap": OVERLAP,
        "tokenizer": (
            "CharSpanTokenizer, calibrated per document to reproduce the "
            "131-chunk layout of the Tiny Aya extraction run. The gated "
            "CohereLabs/tiny-aya-global tokenizer was not available on this box."
        ),
    }
    raw_path = RAW_DIR / "sft_raw.jsonl"
    write_jsonl(raw_path, examples)
    (RAW_DIR / "stats.json").write_text(
        json.dumps(stats_before, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"raw dataset: {len(examples)} examples "
        f"({stats_before['n_positive_examples']} has_positive, "
        f"{stats_before['n_negative_examples']} all_negative) → {raw_path}"
    )
    print("per-field positives:", {f: stats_before["per_field"][f]["positive"] for f in FIELDS})
    print("splits:", stats_before["by_split"])

    print("\n=== 2. CuratorKIT clean + exact/MinHash dedup ===")
    result = run_curatorkit(raw_path)
    by_id = index_by_id(examples)
    accepted = []
    accepted_ids = set()
    for sample in result.passed:
        rec = by_id.get(sample.id)
        if rec is None:
            # Fall back: match on output + start of instruction (after cleaning,
            # whitespace may change; id should normally survive).
            print(f"WARNING: curated sample id not in raw set: {sample.id}")
            continue
        # Keep the cleaned instruction/output from CuratorKIT so training
        # text matches what passed the hygiene/clean stages.
        cleaned = deepcopy(rec)
        cleaned["instruction"] = sample.instruction
        cleaned["input"] = sample.input or ""
        cleaned["output"] = sample.output
        accepted.append(cleaned)
        accepted_ids.add(sample.id)
    rejected = []
    if getattr(result, "rejected", None):
        for sample in result.rejected:
            rejected.append(
                {
                    "id": getattr(sample, "id", None),
                    "reason": getattr(sample, "rejection_reason", None),
                    "step": getattr(sample, "rejecting_step", None),
                    "doc": by_id.get(getattr(sample, "id", ""), {}).get("doc"),
                    "split": by_id.get(getattr(sample, "id", ""), {}).get("split"),
                }
            )
    rejected_ids = [r["id"] for r in rejected if r["id"]]
    # Anything that went in but is in neither passed nor rejected.
    missing = [e["id"] for e in examples if e["id"] not in accepted_ids and e["id"] not in set(rejected_ids)]
    if missing:
        print("unaccounted ids:", missing)
    (CURATED / "rejected_summary.json").write_text(
        json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== 3. Write project-level train/val exports ===")
    after = export_split_files(accepted, rejected_ids, stats_before)
    print("after curation:", after["n_examples"], "accepted,", after["n_rejected"], "rejected")
    print("after splits:", after["by_split"])
    print("done.")


if __name__ == "__main__":
    main()
