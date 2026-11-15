"""Build self-contained Opus labelling prompts (batch_NNN.txt) for claude.ai.

  python3 build_batches.py                       # first run: the 359 chunks of the 13 new PDs (sft_v5/chunks_new.json)
  python3 build_batches.py --text-dir DIR        # later: chunk every DIR/*.txt with the v5 chunker and APPEND batches
  python3 build_batches.py --chunks-json FILE    # later: append from a chunks json shaped like chunks_new.json

Re-runs never renumber or rewrite existing batches: chunk ids already in chunks_registry.jsonl are skipped,
new batches continue from the last number. Chunk ids match build_v5.py: "<stem>::chunk-<i:03d>".
"""
import argparse, json, re, sys, zipfile, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

TARGET_TOK, MAX_TOK, MIN_CH, MAX_CH = 70_000, 80_000, 15, 25
EMPTIES_PER_BATCH = 3

INSTRUCTIONS = """\
TALLY LABELLING TASK (batch {batch_no} of {n_batches_note}; {n_chunks} chunks)

You are labelling training data for a model that reads Verra VCS carbon-project documents. Below are {n_chunks} text chunks cut from real documents (PD = project description, MR = monitoring report, VR = verification report). Each chunk sits between a "<<<CHUNK id=...>>>" line and an "<<<END CHUNK id=...>>>" line. Label every chunk ON ITS OWN: use only that chunk's text, even if another chunk from the same document says more.

FIELDS (follow Verra VCS definitions)
1. baseline: the business-as-usual scenario without the project, as a quantity: baseline emissions in tCO2e (or a baseline deforestation rate if that is the only figure). PD: the total over the crediting period / projection; MR or VR: the current monitoring period.
2. additionality: how the project shows it only happens because of carbon finance: the tool or test used (e.g. VT0001, CDM additionality tool, investment / barrier analysis, common practice) and its conclusion. Community or biodiversity co-benefits are NOT additionality.
3. leakage: emissions displaced outside the project, in tCO2e only (a stated 0 counts: "0" with unit tCO2e). A leakage percentage alone is NOT a value: put it in conflicts and mark leakage not_stated.
4. permanence_buffer: the percentage of credits put in the AFOLU non-permanence buffer pool, as a percentage only (e.g. 13%). If the chunk gives both a risk-tool score and a different applied/held percentage, use the applied one and list the other in conflicts.
5. crediting_period: the FULL crediting period as a date range (start and end; include the stated number of years if given). Not a monitoring period, not a baseline period.
6. area: the CREDITED project area (project accounting area) in hectares. A total that includes the leakage belt goes in area_incl_leakage_belt instead. Ignore reference-region and leakage-belt-only areas.
7. estimated_reductions: net GHG emission reductions/removals AFTER the buffer deduction, in tCO2e. PD: the crediting-period total (use an annual figure only if no total is in the chunk, and set unit "tCO2e/yr"); MR or VR: the current monitoring period.
Auxiliary fields:
8. area_incl_leakage_belt: total hectares of project area plus leakage belt, only if stated as such.
9. estimated_reductions_pre_buffer: if the chunk states only a total BEFORE the buffer is deducted, put it here and set estimated_reductions to not_stated. If both are stated, fill both.

STRICT RULES
- Every value needs a "quote": an exact passage copied character-for-character from the chunk (same words, numbers, punctuation, symbols and spelling, typos included; only spacing and line breaks may differ). One contiguous passage, at most 50 words. For tables, copy the row or header text as it appears.
- The value must appear inside its quote: copy the number/date/words exactly as written in the quote (keep its separators, e.g. "31'212'644" or "551 338"). Put the unit in "unit", not in "value".
- Never infer, convert, sum, round or compute anything. Never use outside knowledge or other chunks. If the document has an obvious typo, copy it as written and describe it in conflicts.
- If a field is absent from the chunk, or only implied, write exactly "not_stated" for it. Most chunks have no values at all; that is expected and fine. Do not guess.
- Conflicts: if the chunk gives two or more different candidate figures for one field (e.g. 6,213 ha vs 6,212 ha, 10% vs 13%), pick the best one per the rules above as the value and list every alternative in "conflicts" with its own verbatim quote.
- Units: baseline "tCO2e" (or "tCO2e/yr", "ha/yr", "%/yr"); additionality null; leakage "tCO2e"; permanence_buffer "%"; crediting_period "dates"; area and area_incl_leakage_belt "ha"; estimated_reductions and estimated_reductions_pre_buffer "tCO2e" or "tCO2e/yr".

REPLY FORMAT
Reply with ONE ```json code block and nothing else: a JSON list with exactly one object per chunk, in the order given, covering all {n_chunks} chunk_ids. Use straight double quotes for JSON; if a quote contains a " character, escape it as \\". Shape:
```json
[
  {{"chunk_id": "<id>",
    "fields": {{
      "baseline": {{"value": "...", "quote": "...", "unit": "tCO2e"}},
      "additionality": "not_stated",
      "leakage": "not_stated",
      "permanence_buffer": {{"value": "13", "quote": "...", "unit": "%"}},
      "crediting_period": "not_stated",
      "area": "not_stated",
      "estimated_reductions": "not_stated",
      "area_incl_leakage_belt": "not_stated",
      "estimated_reductions_pre_buffer": "not_stated"}},
    "conflicts": [{{"field": "permanence_buffer", "value": "10", "quote": "...", "note": "risk-tool score vs applied"}}]}}
]
```
Use "conflicts": [] when there are none. If you run out of room, stop after a complete chunk object, close the list, and write CONTINUE after the code block; you will be asked to continue with the remaining chunks in a second ```json block.

CHUNKS
"""

def v5_labels_for_new13():
    """Recompute build_v5.targets_for for every chunk (same rule: a gold/alt quote is a literal substring
    of the whitespace-collapsed chunk). Saved so ingest.py can compare without importing build_v5."""
    key = json.loads((ROOT / "data_expansion/answer_key_v5.json").read_text(encoding="utf-8"))
    chunks = json.loads((ROOT / "sft_v5/chunks_new.json").read_text(encoding="utf-8"))
    out = {}
    for stem, chs in chunks.items():
        for i, ch in enumerate(chs):
            nt = norm_ws(ch["text"]); tg = {}
            for f in FIELDS:
                g = key[stem][f]
                if g["quote"] is None: tg[f] = NOT_STATED; continue
                cands = [g["quote"]] + [a["quote"] for a in g.get("alt_quotes", [])]
                hit = next((q for q in cands if q in nt), None)
                tg[f] = {"value": g["gold_value"], "quote": hit} if hit else NOT_STATED
            out[f"{stem}::chunk-{i:03d}"] = tg
    return out

KW = {
    "permanence_buffer": r"buffer|non-permanence|risk rating|AFOLU pooled",
    "leakage": r"leakage",
    "crediting_period": r"crediting period|start date|end date|project crediting",
    "area": r"hectares|\bha\b|project area|accounting area",
    "estimated_reductions": r"estimated (?:net )?(?:ghg )?emission reductions|net (?:ghg )?emission reductions|total estimated|VCUs?|tCO2e?",
    "baseline": r"baseline emissions|baseline scenario|deforestation rate",
    "additionality": r"additionality|additional\b|investment analysis|barrier analysis|common practice|VT0001",
}

def score(text, v5):
    s = 0.0
    if v5: s += 100 * sum(1 for f in FIELDS if v5.get(f, NOT_STATED) != NOT_STATED)
    low = text.lower()
    for f, rx in KW.items():
        s += min(4, len(re.findall(rx, low, re.I))) * 2
    s += min(40, len(re.findall(r"\b\d{1,3}(?:[ ,'’]\d{3})+\b|\b\d{4,}\b|\d+(?:\.\d+)?\s?%", text))) * 0.5
    return s

def chunk_text_dir(d: Path):
    sys.path.insert(0, str(ROOT))
    from chunk_merge import chunk_doc
    from tokenizers import Tokenizer
    T = Tokenizer.from_file(str(ROOT / "sft_out/tally-lora/tokenizer.json"))
    class Tok:
        def encode(self, s, add_special_tokens=False): return T.encode(s, add_special_tokens=False).ids
        def decode(self, ids, skip_special_tokens=False): return T.decode(list(ids), skip_special_tokens=False)
    return {p.stem: chunk_doc(p.read_text(encoding="utf-8"), Tok(), max_tokens=3500, overlap=300) for p in sorted(d.glob("*.txt"))}

def render_chunk(r):
    return (f"<<<CHUNK id={r['chunk_id']} | doc={r['doc']} | type={r['doc_type']} | pages {r['start_page']}-{r['end_page']}>>>\n"
            f"{compact(r['text'])}\n<<<END CHUNK id={r['chunk_id']}>>>\n")

def plan(rows):
    """rows sorted by score desc. Valuable chunks fill batches in score order; the lowest-score chunks are
    the 'likely empty' pool, and EMPTIES_PER_BATCH of them are interleaved into every batch."""
    tot = sum(r["est_tokens"] for r in rows) + 2500
    nb = max(1, math.ceil(tot / TARGET_TOK))
    n_empty = min(len(rows) // 4, nb * EMPTIES_PER_BATCH)
    main, empties = rows[:len(rows) - n_empty], rows[len(rows) - n_empty:]
    per_batch_tok = sum(r["est_tokens"] for r in rows) / nb
    batches, cur, ctok = [], [], 0
    ei = 0
    def close():
        nonlocal cur, ctok
        if cur: batches.append(cur)
        cur, ctok = [], 0
    for r in main:
        if cur and (ctok + r["est_tokens"] > MAX_TOK - 3 * 5500 or len(cur) >= MAX_CH - EMPTIES_PER_BATCH
                    or (ctok >= per_batch_tok - EMPTIES_PER_BATCH * 5000 and len(cur) >= MIN_CH - EMPTIES_PER_BATCH)):
            for _ in range(EMPTIES_PER_BATCH):
                if ei < len(empties): cur.append(empties[ei]); ctok += empties[ei]["est_tokens"]; ei += 1
            close()
        cur.append(r); ctok += r["est_tokens"]
    while ei < len(empties): cur.append(empties[ei]); ei += 1
    close()
    # interleave: spread the empties through the batch instead of putting them at the end
    out = []
    for b in batches:
        val = [r for r in b if r["tier"] != "likely_empty"]; emp = [r for r in b if r["tier"] == "likely_empty"]
        if emp and val:
            step = max(1, len(val) // (len(emp) + 1)); merged = []
            for i, r in enumerate(val):
                merged.append(r)
                if emp and (i + 1) % step == 0 and i + 1 < len(val): merged.append(emp.pop(0))
            merged += emp; b = merged
        out.append(b)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-dir"); ap.add_argument("--chunks-json")
    a = ap.parse_args()
    reg = load_registry()
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"batches": []}
    v5 = json.loads(V5_LABELS.read_text()) if V5_LABELS.exists() else {}
    if a.text_dir: src = chunk_text_dir(Path(a.text_dir)); src_name = a.text_dir
    elif a.chunks_json: src = json.loads(Path(a.chunks_json).read_text(encoding="utf-8")); src_name = a.chunks_json
    else:
        src = json.loads((ROOT / "sft_v5/chunks_new.json").read_text(encoding="utf-8")); src_name = "sft_v5/chunks_new.json"
        if not V5_LABELS.exists():
            v5 = v5_labels_for_new13(); V5_LABELS.write_text(json.dumps(v5, ensure_ascii=False, indent=0))
    rows = []
    for stem, chs in src.items():
        proj = stem.split("_")[0]
        if proj in EXCLUDED_PROJECTS: print(f"SKIP {stem}: validation/held-out project"); continue
        for i, ch in enumerate(chs):
            cid = f"{stem}::chunk-{i:03d}"
            if cid in reg and reg[cid].get("batched", True): continue
            if cid in reg and not reg[cid].get("batched", True):
                # already registered (e.g. wide backlog) but not yet in a batch: reuse stored text
                ch_text = reg[cid]["text"]; start_p = reg[cid]["start_page"]; end_p = reg[cid]["end_page"]
            else:
                ch_text, start_p, end_p = ch["text"], ch["start_page"], ch["end_page"]
            r = {"chunk_id": cid, "doc": stem, "project": proj, "project_group": project_group(proj),
                 "doc_type": doc_type_wide(stem), "chunk_index": i,
                 "start_page": start_p, "end_page": end_p, "text": ch_text, "source": src_name}
            r["est_tokens"] = est_claude_tokens(render_chunk(r))
            r["score"] = score(ch["text"], v5.get(cid))
            rows.append(r)
    if not rows: print("nothing new to batch"); return
    rows.sort(key=lambda r: -r["score"])
    for k, r in enumerate(rows):
        r["tier"] = "v5_has_value" if v5.get(r["chunk_id"]) and any(v != NOT_STATED for v in v5[r["chunk_id"]].values()) else "keyword"
    nb_guess = max(1, math.ceil(sum(r["est_tokens"] for r in rows) / TARGET_TOK))
    n_empty = min(len(rows) // 4, nb_guess * EMPTIES_PER_BATCH)
    for r in rows[len(rows) - n_empty:]: r["tier"] = "likely_empty"
    batches = plan(rows)
    start = len(manifest["batches"]) + 1
    with open(REGISTRY, "a", encoding="utf-8") as f:
        for b in batches:
            for r in b:
                rec = {k: r[k] for k in ("chunk_id", "doc", "project", "project_group", "doc_type", "chunk_index", "start_page",
                                         "end_page", "source", "text") if k in r}
                rec["batched"] = True
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for j, b in enumerate(batches):
        no = start + j
        head = INSTRUCTIONS.format(batch_no=f"{no:03d}", n_batches_note=f"{start + len(batches) - 1:03d}", n_chunks=len(b))
        body = head + "\n" + "\n".join(render_chunk(r) for r in b) + \
            f"\nEND OF BATCH {no:03d}. Reply with the single ```json block covering all {len(b)} chunk_ids listed above.\n"
        p = OB / f"batch_{no:03d}.txt"; p.write_text(body, encoding="utf-8")
        manifest["batches"].append({"batch": f"{no:03d}", "file": p.name, "source": src_name, "n_chunks": len(b),
                                    "est_input_tokens": est_claude_tokens(body), "chars": len(body),
                                    "n_v5_has_value": sum(r["tier"] == "v5_has_value" for r in b),
                                    "n_likely_empty": sum(r["tier"] == "likely_empty" for r in b),
                                    "chunk_ids": [r["chunk_id"] for r in b]})
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    with zipfile.ZipFile(OB / "batches_all.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for m in manifest["batches"]: z.write(OB / m["file"], m["file"])
        z.write(OB / "README.md", "README.md") if (OB / "README.md").exists() else None
    for m in manifest["batches"][start - 1:]:
        print(m["batch"], m["n_chunks"], "chunks", m["est_input_tokens"], "est tok", "v5+", m["n_v5_has_value"], "empty", m["n_likely_empty"])

if __name__ == "__main__":
    main()
