"""Rebalance + re-ground the Tally SFT train split (val untouched).

1. Re-ground positive labels: 58/95 positive field targets carried the answer-key
   quote/page from a page OUTSIDE the chunk (match by value/number only). We
   replace quote+page with the in-chunk sentence window that contains the value,
   so every target quote is copyable from the text the model sees. If no
   in-chunk window containing the value is found, the field becomes "not stated".
2. Rebalance: keep every example with >=1 positive field, plus N_NEG
   all-"not stated" examples sampled with a fixed seed. Duplicate examples whose
   additionality is positive once (only 4 of them).
3. Trim over-long examples (> MAX_CONTENT_TOKENS) by dropping evidence-free
   pages from the chunk ends, so no example is OOM-skipped on a T4.
"""
import json, random, re, sys, collections
from pathlib import Path

from paths import first_existing, find_tokenizer, prepend_import_paths

ROOT = prepend_import_paths()
SRC = first_existing(ROOT / "kaggle_sft_dataset", ROOT / "data" / "curated") or (ROOT / "data" / "curated")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else (ROOT / "sft_rebalance" / "out"))
SEED, N_NEG, MAX_CONTENT_TOKENS = 42, 10, 5400
FIELDS = ["baseline", "additionality", "leakage", "permanence_buffer", "crediting_period", "area", "estimated_reductions"]
PAGE_RE = re.compile(r"--- page (\d+) ---")

try:
    from tokenizers import Tokenizer
    _tok_path = find_tokenizer()
    if _tok_path is None:
        raise FileNotFoundError("tokenizer.json not found; set TALLY_TOKENIZER")
    TOK = Tokenizer.from_file(str(_tok_path))
    ntok = lambda s: len(TOK.encode(s, add_special_tokens=False).ids)
except Exception:
    TOK = None
    ntok = lambda s: len(s) // 2


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8").read().split("\n") if l.strip()]


def split_user(u):
    m = re.search(r"\n\nPages (\d+)-(\d+):\n\n", u)
    return u[: m.start()], int(m.group(1)), int(m.group(2)), u[m.end():]


def num_pattern(n):
    # 169741 / 169,741 / 169 741 ; decimals kept
    ip, _, dp = n.partition(".")
    digits = ip.replace(",", "")
    parts = []
    s = digits
    while len(s) > 3:
        parts.insert(0, s[-3:]); s = s[:-3]
    parts.insert(0, s)
    body = r"[,\s\u00a0\u202f]?".join(map(re.escape, parts))
    if dp:
        body += r"\." + re.escape(dp)
    return r"(?<![\d.,])" + body + r"(?![\d])"


def nums_of(value):
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", value)]


def page_at(text, pos):
    last = None
    for m in PAGE_RE.finditer(text):
        if m.start() > pos:
            break
        last = int(m.group(1))
    return last


def window(text, pos, end, max_words=40):
    # Expand to sentence-ish boundaries, then cap at max_words around the match.
    left = max(text.rfind(". ", 0, pos), text.rfind("\n\n", 0, pos), text.rfind("--- page", 0, pos))
    left = 0 if left < 0 else left + 1
    rb = [i for i in (text.find(". ", end), text.find("\n\n", end), text.find("--- page", end)) if i >= 0]
    right = min(rb) + 1 if rb else len(text)
    pre = text[left:pos].split(); mid = text[pos:end].split(); post = text[end:right].split()
    budget = max(0, max_words - len(mid))
    nb = min(len(pre), budget // 2); na = min(len(post), budget - nb)
    nb = min(len(pre), budget - na)
    q = " ".join(pre[len(pre) - nb:] + mid + post[:na]).strip()
    return re.sub(r"-*\s*page \d+ -+", " ", q).strip()


CUE = {
    "permanence_buffer": r"buffer|non-?permanence|risk rating|withh[eo]ld",
    "leakage": r"leakage",
    "baseline": r"baseline",
}


def locate_short(field, value, text):
    # Short figures (0, 13%, 20) only count next to a field cue.
    cue = CUE.get(field)
    if not cue:
        return None
    nums = nums_of(value)
    if nums == ["0"]:
        vpat = r"(?<![\d.,])0(?:\.0+)?\s*(?:t\s*CO2e?|tCO2e?|%)|\bzero\b|\bnil\b|\bno leakage\b|\bnot (?:expected|anticipated)\b"
    else:
        unit = r"\s*%" if "%" in value else ""
        vpat = r"(?<![\d.,])" + r"[^\d]{1,3}".join(map(re.escape, nums)) + r"(?![\d])" + unit
    best = None
    for c in re.finditer(cue, text, re.I):
        for v in re.finditer(vpat, text[c.start(): c.start() + 250], re.I):
            s, e = c.start(), c.start() + v.end()
            if best is None or e - s < best[1] - best[0]:
                best = (s, e)
            break
    return None if best is None else ("raw",) + best


def locate(field, value, text):
    """Return (start, end) of the strongest in-chunk evidence for value, or None."""
    nums = nums_of(value)
    long_nums = [n for n in nums if len(n.split(".")[0]) >= 4]
    if nums and not long_nums:
        return locate_short(field, value, text)
    if not long_nums:
        # textual values (additionality) - look for the phrase itself
        m = re.search(re.escape(" ".join(value.split()[:6])), " ".join(text.split()), re.I)
        return None if not m else ("norm", m.start(), m.end())
    pats = [re.compile(num_pattern(n)) for n in long_nums]
    best = None
    for m in pats[0].finditer(text):
        lo, hi = m.start(), m.end()
        ok = True
        for p in pats[1:]:
            near = [x for x in p.finditer(text, max(0, lo - 400), min(len(text), hi + 400))]
            if not near:
                ok = False; break
            x = min(near, key=lambda x: abs(x.start() - lo))
            lo, hi = min(lo, x.start()), max(hi, x.end())
        if ok and (best is None or hi - lo < best[1] - best[0]):
            best = (lo, hi)
    return None if best is None else ("raw",) + best


def reground(field, tgt, start_page, chunk):
    pg = tgt.get("page")
    q = tgt.get("quote") or ""
    qn = " ".join(q.split())
    if qn and qn[:80] in " ".join(chunk.split()) and pg is not None and start_page <= pg:
        return tgt, "quote_in_chunk"
    loc = locate(field, str(tgt["value"]), chunk)
    if loc is None:
        return "not stated", "dropped_no_evidence"
    kind, s, e = loc
    if kind == "norm":
        flat = " ".join(chunk.split())
        quote = " ".join(flat[max(0, s - 120): e + 120].split()[1:-1][:40])
        page = tgt.get("page")
        return {"value": tgt["value"], "page": page, "quote": quote}, "regrounded_text"
    return {"value": tgt["value"], "page": page_at(chunk, s) or start_page, "quote": window(chunk, s, e)}, "regrounded"


def trim(chunk, evidence_pages, header_prompt, sp, ep):
    pages = [(int(m.group(1)), m.start()) for m in PAGE_RE.finditer(chunk)]
    if not pages:
        return chunk, sp, ep
    bounds = [(pg, st, pages[i + 1][1] if i + 1 < len(pages) else len(chunk)) for i, (pg, st) in enumerate(pages)]
    pre = chunk[: bounds[0][1]]
    segs = list(bounds)
    def build(segs):
        return pre + "".join(chunk[st:en] for _, st, en in segs)
    while ntok(header_prompt) + ntok(build(segs)) > MAX_CONTENT_TOKENS and len(segs) > 1:
        ev = [i for i, (pg, _, _) in enumerate(segs) if pg in evidence_pages]
        if not ev:
            segs = segs[:-1]; continue
        head_free, tail_free = ev[0], len(segs) - 1 - ev[-1]
        if tail_free == 0 and head_free == 0:
            # last resort: drop an evidence-free page from the middle
            mids = [i for i in range(1, len(segs) - 1) if segs[i][0] not in evidence_pages]
            if not mids:
                break
            segs = segs[:mids[-1]] + segs[mids[-1] + 1:]
            continue
        segs = segs[1:] if head_free >= tail_free else segs[:-1]
    return build(segs), segs[0][0], segs[-1][0]


def main():
    meta = load(SRC / "train_sft_with_metadata.jsonl")
    msgs = load(SRC / "train_sft_messages.jsonl")
    assert len(meta) == len(msgs) == 108
    stats = collections.Counter(); rows = []
    for r, m in zip(meta, msgs):
        prompt, sp, ep, chunk = split_user(m["messages"][0]["content"])
        out = json.loads(m["messages"][1]["content"])
        new = {}
        for f in FIELDS:
            v = out[f]
            if isinstance(v, dict):
                v, why = reground(f, v, sp, chunk); stats[(f, why)] += 1
            new[f] = v
        pos = [f for f in FIELDS if isinstance(new[f], dict)]
        ev_pages = {new[f]["page"] for f in pos if new[f].get("page") is not None}
        chunk2, sp2, ep2 = trim(chunk, ev_pages, prompt, sp, ep)
        if chunk2 != chunk:
            stats["trimmed_examples"] += 1
        user = f"{prompt}\n\nPages {sp2}-{ep2}:\n\n{chunk2}"
        rows.append({"id": r["id"], "positive_fields": pos, "orig_positive": r["positive_fields"],
                     "n_tokens": ntok(user), "messages": [{"role": "user", "content": user},
                     {"role": "assistant", "content": json.dumps(new, ensure_ascii=False)}]})
    posr = [x for x in rows if x["positive_fields"]]
    negr = [x for x in rows if not x["positive_fields"]]
    rng = random.Random(SEED)
    negs = rng.sample(negr, N_NEG)
    dup = [x for x in posr if "additionality" in x["positive_fields"]]
    final = posr + negs + dup
    rng.shuffle(final)
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "train_sft_messages_rebalanced.jsonl", "w", encoding="utf-8") as f:
        for x in final:
            f.write(json.dumps({"messages": x["messages"]}, ensure_ascii=False) + "\n")
    with open(OUT / "train_rebalanced_with_metadata.jsonl", "w", encoding="utf-8") as f:
        for x in final:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    fc = collections.Counter(f for x in final for f in x["positive_fields"])
    report = {"seed": SEED, "n_pos_examples": len(posr), "n_neg_pool": len(negr), "n_neg_sampled": N_NEG,
              "n_additionality_dups": len(dup), "n_train": len(final),
              "neg_ids": [x["id"] for x in negs], "dup_ids": [x["id"] for x in dup],
              "field_positive_counts": dict(fc),
              "reground_stats": {f"{k[0]}:{k[1]}" if isinstance(k, tuple) else k: v for k, v in stats.items()},
              "max_tokens_after_trim": max(x["n_tokens"] for x in final),
              "tokenizer": "tiny-aya tokenizer.json" if TOK else "chars/2 estimate"}
    (OUT / "rebalance_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
