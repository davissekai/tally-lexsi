#!/usr/bin/env python3
"""Optional local check: flag labeller/reviewer quotes that are not substrings of the chunk.

Standard-library only. Run from the kit folder:

    python check_quotes.py
    python check_quotes.py --review
    py check_quotes.py          (Windows, if `python` is not on PATH)

Whitespace and line breaks may differ; everything else in the quote must appear
character-for-character in the chunk. This is a convenience check for Claude Code.
The real verification (value-in-quote, units, reviewer application) happens later.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
NOT_STATED = {"not_stated", "notstated", "n/a", ""}
FIELDS = [
    "baseline", "additionality", "leakage", "permanence_buffer", "crediting_period",
    "area", "estimated_reductions", "area_incl_leakage_belt", "estimated_reductions_pre_buffer",
]


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_index():
    path = KIT / "chunks_index.csv"
    backlog = KIT / "backlog" / "backlog_index.csv"
    rows = []
    for p in (path, backlog):
        if not p.exists():
            continue
        with p.open(encoding="utf-8", newline="") as f:
            rows.extend(csv.DictReader(f))
    by_id = {}
    for r in rows:
        by_id[r["chunk_id"]] = r
    return by_id


def chunk_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Header lines start with '#'; body follows a blank line or '---'
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or lines[i].strip() in ("", "---")):
        i += 1
    return "\n".join(lines[i:])


def word_count(s: str) -> int:
    return len(norm_ws(s).split()) if s.strip() else 0


def iter_jsonl(path: Path):
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield lineno, json.loads(line)
            except json.JSONDecodeError as e:
                yield lineno, {"__parse_error__": str(e), "__raw__": line[:200]}


def check_quote(quote, body_norm, where):
    q = norm_ws(str(quote))
    problems = []
    if not q:
        problems.append((where, "empty quote"))
        return problems
    if q not in body_norm:
        preview = q[:160] + ("…" if len(q) > 160 else "")
        problems.append((where, f"quote not in chunk: {preview}"))
    wc = word_count(q)
    if wc > 50:
        problems.append((where, f"quote has {wc} words (limit 50)"))
    return problems


def check_labels(index):
    problems = []
    n_lines = 0
    n_values = 0
    path = KIT / "labels.jsonl"
    for lineno, obj in iter_jsonl(path) or []:
        n_lines += 1
        if "__parse_error__" in obj:
            problems.append((f"labels.jsonl:{lineno}", f"invalid JSON: {obj['__parse_error__']}"))
            continue
        cid = str(obj.get("chunk_id", "")).strip()
        if not cid:
            problems.append((f"labels.jsonl:{lineno}", "missing chunk_id"))
            continue
        info = index.get(cid)
        if not info:
            problems.append((f"labels.jsonl:{lineno} {cid}", "chunk_id not in chunks_index.csv or backlog index"))
            continue
        cpath = KIT / info["file"]
        if not cpath.exists():
            problems.append((f"{cid}", f"chunk file missing: {info['file']}"))
            continue
        body = norm_ws(chunk_body(cpath))
        fields = obj.get("fields") or {}
        for f in FIELDS:
            v = fields.get(f, "not_stated")
            if v is None or (isinstance(v, str) and v.strip().lower().replace(" ", "_") in NOT_STATED):
                continue
            if not isinstance(v, dict):
                problems.append((f"labels.jsonl:{lineno} {cid} {f}", f"expected object or not_stated, got {type(v).__name__}"))
                continue
            n_values += 1
            if not v.get("quote") or not v.get("value"):
                problems.append((f"labels.jsonl:{lineno} {cid} {f}", "missing value or quote"))
                continue
            problems.extend(check_quote(v["quote"], body, f"labels.jsonl:{lineno} {cid} {f}"))
        for i, c in enumerate(obj.get("conflicts") or []):
            if isinstance(c, dict) and c.get("quote"):
                problems.extend(check_quote(c["quote"], body, f"labels.jsonl:{lineno} {cid} conflicts[{i}]"))
    return problems, n_lines, n_values


def _review_items(obj):
    """Yield (field, verdict, quote, value) from either schema."""
    if "reviews" in obj and isinstance(obj["reviews"], list):
        for r in obj["reviews"]:
            if isinstance(r, dict):
                yield r
        return
    if "field" in obj:
        yield obj


def check_reviews(index):
    problems = []
    n_lines = 0
    n_fixes = 0
    path = KIT / "review.jsonl"
    for lineno, obj in iter_jsonl(path) or []:
        n_lines += 1
        if "__parse_error__" in obj:
            problems.append((f"review.jsonl:{lineno}", f"invalid JSON: {obj['__parse_error__']}"))
            continue
        cid = str(obj.get("chunk_id", "")).strip()
        if not cid:
            problems.append((f"review.jsonl:{lineno}", "missing chunk_id"))
            continue
        info = index.get(cid)
        if not info:
            problems.append((f"review.jsonl:{lineno} {cid}", "chunk_id not in index"))
            continue
        cpath = KIT / info["file"]
        if not cpath.exists():
            problems.append((f"{cid}", f"chunk file missing: {info['file']}"))
            continue
        body = norm_ws(chunk_body(cpath))
        for r in _review_items(obj):
            verdict = str(r.get("verdict", "")).strip().lower()
            field = r.get("field", "?")
            if verdict not in {"accept", "fix", "reject"}:
                problems.append((f"review.jsonl:{lineno} {cid} {field}", f"bad verdict {verdict!r}"))
            if verdict == "fix":
                n_fixes += 1
                quote = r.get("quote") or r.get("corrected_quote")
                value = r.get("value") or r.get("corrected_value")
                if not quote or not value:
                    problems.append((f"review.jsonl:{lineno} {cid} {field}", "fix is missing value or quote"))
                    continue
                problems.extend(check_quote(quote, body, f"review.jsonl:{lineno} {cid} {field}"))
    return problems, n_lines, n_fixes


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", action="store_true", help="check review.jsonl corrected quotes instead of labels.jsonl")
    ap.add_argument("--both", action="store_true", help="check labels.jsonl and review.jsonl")
    ap.add_argument("--kit", default=None, help="kit folder (default: this script's directory)")
    args = ap.parse_args(argv)
    global KIT
    KIT = Path(args.kit).resolve() if args.kit else Path(__file__).resolve().parent
    index = load_index()
    if not index:
        print("No chunks_index.csv found. Run this from the kit folder.", file=sys.stderr)
        return 2
    all_problems = []
    summaries = []
    do_labels = args.both or not args.review
    do_review = args.review or args.both
    if do_labels:
        probs, n_lines, n_values = check_labels(index)
        all_problems.extend(probs)
        summaries.append(f"labels.jsonl: {n_lines} chunks, {n_values} stated fields, {len(probs)} issue(s)")
    if do_review:
        probs, n_lines, n_fixes = check_reviews(index)
        all_problems.extend(probs)
        summaries.append(f"review.jsonl: {n_lines} lines, {n_fixes} fixes, {len(probs)} issue(s)")
    for where, msg in all_problems:
        print(f"FLAG  {where}\n      {msg}")
    print()
    for s in summaries:
        print(s)
    if all_problems:
        print(f"{len(all_problems)} issue(s) found.")
        return 1
    print("OK: all checked quotes are substrings of their chunks.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
