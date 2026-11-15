"""Build the Tally SFT v7 set from the full Claude Code labels (809 chunks) + non-overlapping v5 examples.

Requires a working tree that holds incoming labels, the chunk registry, and the
v5 leftovers (not all of these are in git). Set TALLY_ROOT if that tree is not
the repository root, and TALLY_TOKENIZER if tokenizer.json is not in sft_out/.

Full-extraction examples use the v5 7-field prompt and answer JSON shape
("not stated", value/page/quote). Single-field question examples are added
for every stated field, plus a modest sample of not_stated fields.
Empty full examples are capped at 25% of the full-extraction set.
New labels replace v5 on overlapping chunk_ids. Held-out projects
5172, 5432, 4329, 2928 (and reserved Miro 2410 / Bandai 2929) are excluded.
Train/val are split by project_group (~15% val).
"""
from __future__ import annotations

import collections
import hashlib
import json
import random
import re
import shutil
import sys
from pathlib import Path

from tokenizers import Tokenizer

from paths import find_tokenizer, prepend_import_paths

ROOT = prepend_import_paths()
OUT = ROOT / "curated_v7"
KAGGLE_OUT = ROOT / "sft_v7" / "kaggle_dataset"
LABELS = ROOT / "incoming_v7" / "out" / "opus_labels.jsonl"
REGISTRY = ROOT / "opus_batches" / "chunks_registry.jsonl"
V5_META = ROOT / "sft_v5" / "dataset" / "train_rebalanced_with_metadata.jsonl"
V5_DIR = ROOT / "sft_v5" / "dataset"
TOK_PATH = find_tokenizer() or (ROOT / "sft_out" / "tally-lora" / "tokenizer.json")
SEED = 42
NEG_SHARE = 0.25  # empty full examples as a share of all full examples, at most
VAL_FRAC = 0.15
NOT_STATED_SF_RATIO = 0.25  # not_stated single-field count vs stated single-field
# Comfortable T4 budget: v5 (~158 ex, 2 epochs) was estimated at 20-45 min training.
# Using the conservative 45 min / 158 examples, 1050 examples is about 5 hours of
# training+eval; plus 15-25 min Miro/Bandai scoring stays under 6 hours (limit ~9).
TARGET_MAX_EXAMPLES = 1050
MAX_CONTENT_TOKENS = 5400
HELD_OUT = {"5172", "5432", "4329", "2928", "2410", "2929"}
FIELDS = [
    "baseline",
    "additionality",
    "leakage",
    "permanence_buffer",
    "crediting_period",
    "area",
    "estimated_reductions",
]
SKIP_UNITS = {"", "dates", "date", "none", "n/a", "null"}

FIELD_DEFS = {
    "baseline": "The counterfactual/business-as-usual scenario that plays out if the project does not happen (usually a deforestation rate or baseline emissions in tCO2e)",
    "additionality": "Proof that the project only happens because of carbon finance, and doesn't happen anyway (the test used, e.g. VT0001, investment or barrier analysis, common practice, and its conclusion)",
    "leakage": "Emissions generated from emission-causing activities that would've been merely moved from the project site to another site (a percentage or tCO2e)",
    "permanence_buffer": "A percentage of carbon credits reserved for insurance against project risks",
    "crediting_period": "The period in which the project earns carbon credits, with a start and end date, often measured in years",
    "area": "The geographical scope of the project measured in hectares",
    "estimated_reductions": "The tCO2e avoided, per year or in total, after leakage and the buffer are deducted",
}

PROMPT = (
    "You are extracting facts from part of a carbon project document (Verra VCS).\n"
    "Read the text below and fill in the 7 fields.\n"
    "FIELDS:\n"
    + "\n".join(f"- {f}: {FIELD_DEFS[f]}" for f in FIELDS)
    + """
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
)

ADD_RULE = (
    "- additionality is only about whether the project needs carbon finance "
    "(e.g. an additionality tool, investment or barrier analysis). "
    "Community or biodiversity co-benefits are NOT additionality.\n"
)

TOK = Tokenizer.from_file(str(TOK_PATH))


def ntok(s: str) -> int:
    return len(TOK.encode(s, add_special_tokens=False).ids)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def project_id(chunk_id: str) -> str:
    return chunk_id.split("_")[0]


def quote_in_text(quote: str, text: str) -> bool:
    if not quote:
        return False
    if quote in text:
        return True
    nq, nt = norm(quote), norm(text)
    return bool(nq) and nq in nt


def page_of(text: str, quote: str, fallback=None):
    if not quote:
        return fallback
    nt, nq = norm(text), norm(quote)
    i = nt.find(nq)
    src = nt
    if i < 0:
        i = text.find(quote)
        src = text
    if i < 0:
        return fallback
    pages = re.findall(r"--- page (\d+) ---", src[:i])
    return int(pages[-1]) if pages else fallback


def format_value(value, unit) -> str:
    v = str(value).strip()
    if unit is None:
        return v
    u = str(unit).strip()
    if not u or u.lower() in SKIP_UNITS:
        return v
    if u == "%":
        return v if v.rstrip().endswith("%") else v + "%"
    if u.lower() in v.lower():
        return v
    if u.lower() == "ha" and re.search(r"\bhectares?\b", v, re.I):
        return v
    return f"{v} {u}"


def fields_from_label(lab: dict, text: str, start_page: int) -> tuple[dict, dict]:
    """Return (answer_json, reasons) for the 7 training fields."""
    out = {}
    why = {}
    raw = lab.get("fields") or {}
    for f in FIELDS:
        v = raw.get(f, "not_stated")
        if v == "not_stated" or v == "not stated" or not isinstance(v, dict):
            out[f] = "not stated"
            why[f] = "not_stated"
            continue
        quote = v.get("quote") or ""
        if not quote_in_text(quote, text):
            out[f] = "not stated"
            why[f] = "quote_not_in_chunk"
            continue
        page = page_of(text, quote, fallback=start_page)
        out[f] = {
            "value": format_value(v.get("value", ""), v.get("unit")),
            "page": page,
            "quote": quote,
        }
        why[f] = "label_quote"
    return out, why


def trim_chunk(chunk: str, evidence_pages, header: str, sp: int, ep: int):
    """Drop evidence-free pages from the ends until under MAX_CONTENT_TOKENS."""
    parts = re.split(r"(?=--- page \d+ ---)", chunk)
    segs = [p for p in parts if p.strip()]
    if not segs:
        return chunk, sp, ep

    def pages_of(seg: str):
        found = [int(x) for x in re.findall(r"--- page (\d+) ---", seg)]
        return found

    def build(ss):
        return "".join(ss)

    ev = {p for p in evidence_pages if p is not None}
    while ntok(header) + ntok(build(segs)) > MAX_CONTENT_TOKENS and len(segs) > 1:
        first_pages, last_pages = pages_of(segs[0]), pages_of(segs[-1])
        first_has = ev.intersection(first_pages)
        last_has = ev.intersection(last_pages)
        if not first_has and (last_has or not ev):
            segs = segs[1:]
        elif not last_has:
            segs = segs[:-1]
        else:
            break
    text2 = build(segs)
    pages = [int(x) for x in re.findall(r"--- page (\d+) ---", text2)]
    sp2 = pages[0] if pages else sp
    ep2 = pages[-1] if pages else ep
    return text2, sp2, ep2


def user_full(sp, ep, chunk, header=PROMPT):
    return f"{header}\n\nPages {sp}-{ep}:\n\n{chunk}"


def single_field_header(field: str) -> str:
    extra = ADD_RULE if field == "additionality" else ""
    shape = (
        '{\n'
        f'  "{field}": {{"value": "...", "page": 0, "quote": "..."}}\n'
        "}"
    )
    return (
        "You are extracting one fact from part of a carbon project document (Verra VCS).\n"
        f"Read the text below and fill in the {field} field.\n"
        "FIELD:\n"
        f"- {field}: {FIELD_DEFS[field]}\n"
        "RULES:\n"
        "- Only use facts written in the text below. Never guess or use outside knowledge.\n"
        "- Copy numbers, units and dates exactly as written. Never copy placeholder examples from these instructions.\n"
        '- "quote" is the exact sentence the value came from, copied word for word, max 40 words.\n'
        '- The quote must contain the value itself (the numbers and units). If no sentence supports it, the field is "not stated".\n'
        '- If the field is not in the text, write only "not stated" for it: no value, page or quote.\n'
        "- Keep the value short: a number with its unit, a date range, or one sentence.\n"
        f"{extra}"
        "Reply with JSON only, in exactly this shape:\n"
        f"{shape}\n"
        f'If the field is not in the text, write "not stated" instead of the object, e.g. "{field}": "not stated"\n'
    )


def make_example(eid, doc, project, project_group, chunk_index, sp, ep, user, output_obj,
                 positive_fields, source, example_kind, field=None, reasons=None, n_tokens=None):
    messages = [
        {"role": "user", "content": user},
        {"role": "assistant", "content": json.dumps(output_obj, ensure_ascii=False)},
    ]
    return {
        "id": eid,
        "doc": doc,
        "project": project,
        "project_group": project_group,
        "chunk_index": chunk_index,
        "start_page": sp,
        "end_page": ep,
        "positive_fields": positive_fields,
        "n_tokens": n_tokens if n_tokens is not None else ntok(user),
        "source": source,
        "example_kind": example_kind,
        "field": field,
        "match_reasons": reasons or {},
        "messages": messages,
    }


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def pick_val_projects(counts: dict, total: int, pos_full_by_proj: dict, rng: random.Random):
    """Choose a set of project_groups whose examples are about VAL_FRAC of the pool."""
    projects = list(counts)
    target = VAL_FRAC * total
    best = None
    best_score = None
    for _ in range(400):
        order = projects[:]
        rng.shuffle(order)
        chosen, n = [], 0
        for p in order:
            c = counts[p]
            # leave at least some train mass
            if n + c > total * 0.35:
                continue
            if n < target * 0.7:
                chosen.append(p)
                n += c
            elif abs(n + c - target) < abs(n - target) and n + c <= target * 1.35:
                chosen.append(p)
                n += c
        if n == 0 or not chosen:
            continue
        n_pos = sum(pos_full_by_proj.get(p, 0) for p in chosen)
        if n_pos < 5:
            continue
        # prefer close to 15%, with some positive full examples
        score = abs(n / total - VAL_FRAC) - 0.002 * min(n_pos, 40)
        if best is None or score < best_score:
            best, best_score = chosen, score
    if not best:
        # fallback: largest projects until ~15%
        chosen, n = [], 0
        for p, c in sorted(counts.items(), key=lambda kv: -kv[1]):
            if n + c <= target * 1.4 and n < target:
                chosen.append(p)
                n += c
        best = chosen
    return set(best)


def split_user(u: str):
    m = re.search(r"\n\nPages (\d+)-(\d+):\n\n", u)
    if not m:
        return u, None, None, ""
    return u[: m.start()], int(m.group(1)), int(m.group(2)), u[m.end() :]


def main():
    rng = random.Random(SEED)
    registry = {}
    with open(REGISTRY, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            registry[o["chunk_id"]] = o

    labels = load_jsonl(LABELS)
    v5_all = load_jsonl(V5_META)
    new_ids = {lab["chunk_id"] for lab in labels}

    qstats = collections.Counter()
    full_pos, full_neg = [], []

    # ---- new labels -> full examples ------------------------------------
    missing_reg = []
    held_dropped = []
    for lab in labels:
        cid = lab["chunk_id"]
        pid = project_id(cid)
        if pid in HELD_OUT:
            held_dropped.append(cid)
            continue
        rec = registry.get(cid)
        if rec is None:
            missing_reg.append(cid)
            continue
        text = rec["text"]
        sp, ep = rec["start_page"], rec["end_page"]
        pg = rec.get("project_group") or rec.get("project") or pid
        out, why = fields_from_label(lab, text, sp)
        for f in FIELDS:
            if why[f] == "quote_not_in_chunk":
                qstats["quote_FAIL"] += 1
            elif why[f] == "label_quote":
                qstats["quote_ok"] += 1
            else:
                qstats["not_stated"] += 1
        pos = [f for f in FIELDS if isinstance(out[f], dict)]
        ev_pages = {out[f]["page"] for f in pos}
        chunk2, sp2, ep2 = trim_chunk(text, ev_pages, PROMPT, sp, ep)
        if chunk2 != text:
            qstats["trimmed"] += 1
        # re-check quotes after trim
        for f in list(pos):
            if not quote_in_text(out[f]["quote"], chunk2):
                qstats["quote_lost_in_trim"] += 1
                out[f] = "not stated"
        pos = [f for f in FIELDS if isinstance(out[f], dict)]
        user = user_full(sp2, ep2, chunk2)
        ex = make_example(
            cid, lab["doc"], pid, str(pg), rec.get("chunk_index"),
            sp2, ep2, user, out, pos, "v6_label", "full", reasons=why,
        )
        # keep the trimmed chunk for single-field reuse
        ex["_chunk"] = chunk2
        ex["_out"] = out
        (full_pos if pos else full_neg).append(ex)

    # ---- leftover unique v5 examples (no overlap) -----------------------
    seen_v5 = set()
    v5_kept = []
    for r in v5_all:
        cid = r["id"]
        if cid in seen_v5:
            continue
        seen_v5.add(cid)
        if cid in new_ids:
            continue
        pid = project_id(cid)
        if pid in HELD_OUT:
            held_dropped.append(cid)
            continue
        user = r["messages"][0]["content"]
        header, sp, ep, chunk = split_user(user)
        out = json.loads(r["messages"][1]["content"])
        pos = list(r.get("positive_fields") or [f for f in FIELDS if isinstance(out.get(f), dict)])
        pg = pid
        ex = make_example(
            cid, r.get("doc") or cid.split("::")[0], pid, str(pg),
            r.get("chunk_index"),
            r.get("start_page") if r.get("start_page") is not None else sp,
            r.get("end_page") if r.get("end_page") is not None else ep,
            user, out, pos, "v5_leftover", "full",
            n_tokens=r.get("n_tokens") or ntok(user),
        )
        ex["_chunk"] = chunk
        ex["_out"] = out
        v5_kept.append(ex)
        (full_pos if pos else full_neg).append(ex)

    # ---- sample empties so they are at most NEG_SHARE of full examples --
    n_pos = len(full_pos)
    # empty / (pos + empty) <= NEG_SHARE  => empty <= NEG_SHARE/(1-NEG_SHARE) * pos
    n_neg_cap = int(round(NEG_SHARE * n_pos / (1 - NEG_SHARE)))
    n_neg = min(len(full_neg), n_neg_cap)
    neg_sampled = rng.sample(full_neg, n_neg) if n_neg < len(full_neg) else list(full_neg)
    rng.shuffle(neg_sampled)
    full_kept = full_pos + neg_sampled
    empty_share = (len(neg_sampled) / len(full_kept)) if full_kept else 0

    # ---- single-field examples from kept full chunks --------------------
    stated_sf = []
    not_stated_pool = []
    for ex in full_kept:
        out = ex["_out"]
        header_by_field_cache = {}
        sp, ep, chunk = ex["start_page"], ex["end_page"], ex["_chunk"]
        for f in FIELDS:
            tgt = out.get(f, "not stated")
            hdr = header_by_field_cache.get(f)
            if hdr is None:
                hdr = single_field_header(f)
                header_by_field_cache[f] = hdr
            # trim already applied on chunk for the 7-field prompt length;
            # single-field header is shorter, so it still fits.
            user = user_full(sp, ep, chunk, header=hdr)
            ans = {f: tgt}
            kind_pos = isinstance(tgt, dict)
            item = make_example(
                f"{ex['id']}::sf-{f}",
                ex["doc"], ex["project"], ex["project_group"], ex["chunk_index"],
                sp, ep, user, ans,
                [f] if kind_pos else [],
                ex["source"],
                "single_field_stated" if kind_pos else "single_field_not_stated",
                field=f,
            )
            if kind_pos:
                stated_sf.append(item)
            elif ex["positive_fields"]:
                # hard negatives: abstain on a field in a chunk that has other values
                not_stated_pool.append(item)

    n_sf_neg = min(len(not_stated_pool), int(round(NOT_STATED_SF_RATIO * len(stated_sf))))
    # spread not_stated sample across fields when possible
    by_f = collections.defaultdict(list)
    for item in not_stated_pool:
        by_f[item["field"]].append(item)
    for f in by_f:
        rng.shuffle(by_f[f])
    sf_neg = []
    while len(sf_neg) < n_sf_neg:
        progressed = False
        for f in FIELDS:
            if len(sf_neg) >= n_sf_neg:
                break
            if by_f[f]:
                sf_neg.append(by_f[f].pop())
                progressed = True
        if not progressed:
            break


    # ---- cap single-field examples so 2-epoch T4 runtime stays under ~6 hours
    sf_stated_before = len(stated_sf)
    sf_neg_before = len(sf_neg)
    n_full = len(full_kept)
    sf_budget = max(0, TARGET_MAX_EXAMPLES - n_full)
    # keep most of the budget for stated single-field; ~20% for not_stated
    n_sf_neg_cap = min(len(sf_neg), int(round(0.20 * sf_budget)), int(round(NOT_STATED_SF_RATIO * sf_stated_before)))
    n_sf_pos_cap = min(len(stated_sf), max(0, sf_budget - n_sf_neg_cap))
    if len(stated_sf) > n_sf_pos_cap:
        by_f = collections.defaultdict(list)
        for item in stated_sf:
            by_f[item["field"]].append(item)
        for f in by_f:
            rng.shuffle(by_f[f])
        picked = []
        while len(picked) < n_sf_pos_cap:
            progressed = False
            for f in FIELDS:
                if len(picked) >= n_sf_pos_cap:
                    break
                if by_f[f]:
                    picked.append(by_f[f].pop())
                    progressed = True
            if not progressed:
                break
        stated_sf = picked
    if len(sf_neg) > n_sf_neg_cap:
        sf_neg = sf_neg[:n_sf_neg_cap]
    sf_capped = (sf_stated_before != len(stated_sf)) or (sf_neg_before != len(sf_neg))

    all_examples = full_kept + stated_sf + sf_neg

    # ---- split by project_group ----------------------------------------
    counts = collections.Counter(ex["project_group"] for ex in all_examples)
    pos_full_by_proj = collections.Counter(
        ex["project_group"] for ex in full_kept if ex["positive_fields"]
    )
    # use a dedicated rng so the empty/sf sampling above stays reproducible
    split_rng = random.Random(SEED + 1)
    val_projects = pick_val_projects(dict(counts), len(all_examples), pos_full_by_proj, split_rng)

    train, val = [], []
    for ex in all_examples:
        (val if ex["project_group"] in val_projects else train).append(ex)
    rng.shuffle(train)
    rng.shuffle(val)

    # ---- write outputs --------------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    KAGGLE_OUT.mkdir(parents=True, exist_ok=True)

    def msgs(rows):
        return [{"messages": r["messages"]} for r in rows]

    def alpaca(rows):
        return [
            {"instruction": r["messages"][0]["content"], "input": "", "output": r["messages"][1]["content"]}
            for r in rows
        ]

    def clean_meta(rows):
        keep = [
            "id", "doc", "project", "project_group", "chunk_index", "start_page", "end_page",
            "positive_fields", "n_tokens", "source", "example_kind", "field", "match_reasons",
            "messages",
        ]
        out = []
        for r in rows:
            item = {k: r[k] for k in keep}
            item["split"] = "val" if r["project_group"] in val_projects else "train"
            out.append(item)
        return out

    write_jsonl(OUT / "train.jsonl", msgs(train))
    write_jsonl(OUT / "val.jsonl", msgs(val))
    write_jsonl(OUT / "train_sft_messages.jsonl", msgs(train))
    write_jsonl(OUT / "train_sft_messages_rebalanced.jsonl", msgs(train))
    write_jsonl(OUT / "train_sft_alpaca.jsonl", alpaca(train))
    write_jsonl(OUT / "train_with_metadata.jsonl", clean_meta(train))
    write_jsonl(OUT / "validation.jsonl", msgs(val))
    write_jsonl(OUT / "val_sft_messages.jsonl", msgs(val))
    write_jsonl(OUT / "val_sft_alpaca.jsonl", alpaca(val))
    write_jsonl(OUT / "val_sft_with_metadata.jsonl", clean_meta(val))

    # reserved Miro + Bandai scoring set, unchanged from v5
    shutil.copy2(V5_DIR / "val_sft_messages.jsonl", OUT / "val_miro_bandai_messages.jsonl")
    shutil.copy2(V5_DIR / "val_sft_with_metadata.jsonl", OUT / "val_miro_bandai_with_metadata.jsonl")
    for fn in [
        "answer_key.json",
        "tinyaya_scores.json",
        "tally_merge.py",
        "score_extractions.py",
        "lexsi_provenance.json",
        "answer_key_v5.json",
    ]:
        src = V5_DIR / fn
        if src.exists():
            shutil.copy2(src, OUT / fn)

    def kind_counts(rows):
        c = collections.Counter(r["example_kind"] for r in rows)
        return {
            "full_positive": sum(1 for r in rows if r["example_kind"] == "full" and r["positive_fields"]),
            "full_empty": sum(1 for r in rows if r["example_kind"] == "full" and not r["positive_fields"]),
            "full_total": sum(1 for r in rows if r["example_kind"] == "full"),
            "single_field_stated": c["single_field_stated"],
            "single_field_not_stated": c["single_field_not_stated"],
            "single_field_total": c["single_field_stated"] + c["single_field_not_stated"],
            "total": len(rows),
        }

    def projects_of(rows):
        d = collections.defaultdict(lambda: collections.Counter())
        for r in rows:
            d[r["project_group"]][r["example_kind"]] += 1
            if r["example_kind"] == "full" and r["positive_fields"]:
                d[r["project_group"]]["full_positive"] += 1
            if r["example_kind"] == "full" and not r["positive_fields"]:
                d[r["project_group"]]["full_empty"] += 1
        return {k: dict(v) for k, v in sorted(d.items(), key=lambda kv: kv[0])}

    field_pos = collections.Counter(
        f for r in full_kept for f in r["positive_fields"]
    )
    sf_field_pos = collections.Counter(
        r["field"] for r in stated_sf
    )
    max_tok = max((r["n_tokens"] for r in all_examples), default=0)
    # rough chat-template overhead used in v5 (~8400 vs 5400 content) — report content tokens

    stats = {
        "version": "v7",
        "seed": SEED,
        "labels_file": str(LABELS),
        "labels_chunks": len(labels),
        "labels_missing_registry": missing_reg,
        "held_out_dropped": held_dropped,
        "held_out_projects": sorted(HELD_OUT),
        "v5_overlap_replaced": len(new_ids & seen_v5),
        "v5_leftover_unique": len(v5_kept),
        "v5_leftover_positive": sum(1 for r in v5_kept if r["positive_fields"]),
        "v5_leftover_empty_pool": sum(1 for r in v5_kept if not r["positive_fields"]),
        "new_positive_full": sum(1 for r in full_pos if r["source"] == "v6_label"),
        "new_empty_pool": sum(1 for r in full_neg if r["source"] == "v6_label"),
        "full_positive": n_pos,
        "full_empty_pool": len(full_neg),
        "full_empty_sampled": len(neg_sampled),
        "full_empty_share": round(empty_share, 3),
        "single_field_stated": len(stated_sf),
        "single_field_not_stated": len(sf_neg),
        "n_train": len(train),
        "n_val": len(val),
        "val_frac": round(len(val) / len(all_examples), 4) if all_examples else 0,
        "train_counts": kind_counts(train),
        "val_counts": kind_counts(val),
        "overall_counts": kind_counts(all_examples),
        "train_projects": sorted({r["project_group"] for r in train}),
        "val_projects": sorted({r["project_group"] for r in val}),
        "n_train_projects": len({r["project_group"] for r in train}),
        "n_val_projects": len({r["project_group"] for r in val}),
        "project_overlap_train_val": sorted(
            {r["project_group"] for r in train} & {r["project_group"] for r in val}
        ),
        "train_by_project": projects_of(train),
        "val_by_project": projects_of(val),
        "field_positive_counts_full": dict(field_pos),
        "field_positive_counts_single_field": dict(sf_field_pos),
        "quote_checks": dict(qstats),
        "max_content_tokens": max_tok,
        "tokenizer": str(TOK_PATH),
        "neg_share_cap": NEG_SHARE,
        "not_stated_sf_ratio": NOT_STATED_SF_RATIO,
        "target_max_examples": TARGET_MAX_EXAMPLES,
        "single_field_capped": sf_capped,
        "single_field_stated_before_cap": sf_stated_before,
        "single_field_not_stated_before_cap": sf_neg_before,
        "prompt": "v5 7-field extraction prompt",
        "answer_shape": "value/page/quote or 'not stated'",
        "miro_bandai_reserved_eval": 23,
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    readme = f"""# Tally SFT v7

Private training and validation chat examples for fine-tuning CohereLabs/tiny-aya-global.

- Full-extraction examples use the same 7-field prompt and answer JSON as v5.
- New Claude Code labels (809 chunks, quote-checked, unreviewed) replace overlapping v5 labels.
- Non-overlapping unique v5 examples (Kasigau, Mai-Ndombe, Bale) are carried over.
- Single-field question examples: one per stated field, plus a modest sample of not_stated fields from chunks that have other values.
- Empty full examples are at most 25% of the full-extraction set.
- Held-out projects 5172, 5432, 4329, 2928 are excluded. Miro (2410) and Bandai (2929) stay out of train/val and are shipped as a reserved 23-chunk eval set (`val_miro_bandai_*.jsonl`) so the notebook can still score them against the original answer key.
- Train/val split is by `project_group` (~15% val). No project appears in both.

Train: {len(train)} examples from {len({r['project_group'] for r in train})} projects.
Val: {len(val)} examples from {len({r['project_group'] for r in val})} projects.
See stats.json for the breakdown.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    # kaggle upload copy
    if KAGGLE_OUT.exists():
        for p in KAGGLE_OUT.iterdir():
            if p.is_file():
                p.unlink()
    for p in OUT.iterdir():
        if p.is_file():
            shutil.copy2(p, KAGGLE_OUT / p.name)

    meta = {
        "title": "tally-sft-v7-data",
        "id": "renhuang01/tally-sft-v7-data",
        "licenses": [{"name": "other"}],
        "subtitle": "Private Tally SFT v7 data (full Claude labels + v5 leftovers, project_group split)",
        "description": (
            "Private training and validation chat examples for fine-tuning "
            "CohereLabs/tiny-aya-global on Tally field extraction. v7 uses "
            "quote-checked Claude Code labels (all 809 chunks) plus non-overlapping "
            "v5 examples, with single-field question examples and a project_group "
            "train/val split. Includes the reserved Miro+Bandai eval set, answer "
            "key, and scoring helpers. Not for public release."
        ),
        "isPrivate": True,
        "keywords": [],
        "collaborators": [],
        "data": [],
    }
    (KAGGLE_OUT / "dataset-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (OUT / "dataset-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # sanity
    assert not stats["project_overlap_train_val"]
    assert stats["full_empty_share"] <= NEG_SHARE + 0.001
    print(json.dumps({k: stats[k] for k in [
        "labels_chunks", "v5_overlap_replaced", "v5_leftover_unique",
        "full_positive", "full_empty_sampled", "full_empty_share",
        "single_field_stated", "single_field_not_stated",
        "n_train", "n_val", "val_frac",
        "n_train_projects", "n_val_projects",
        "train_projects", "val_projects",
        "train_counts", "val_counts",
        "field_positive_counts_full",
        "quote_checks", "max_content_tokens",
        "labels_missing_registry", "held_out_dropped",
    ]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
