"""Ingest Opus replies, verify them against the source chunks, and compare with the v5 labels.

  python3 ingest.py                    # reads replies/*.json|*.txt|*.md (reply_001.json, reply_001_part2.json, ...)
  python3 ingest.py path/to/file ...   # or specific files
  OPUS_OUT=/tmp/x python3 ingest.py f  # write outputs elsewhere (used by test_ingest.py)

A reply file may hold the raw chat reply: markdown fences, text around them, several ```json blocks
(e.g. after "continue"), trailing commas, smart quotes as JSON delimiters, or a truncated last object.

Checks per field value:
  1. quote is a literal substring of its chunk (whitespace normalised only, nothing else);
  2. the value appears in its quote (numbers compared with separators stripped, words case-insensitive);
  3. unit is allowed for the field (e.g. leakage must be tCO2e, buffer must be %).
Failures are dropped and logged. Outputs (in opus_batches/):
  opus_labels.jsonl      one row per verified chunk: chunk_id, fields (value/quote/unit or not_stated), conflicts
  ingest_log.jsonl       every dropped value / unknown chunk / missing chunk, with the reason
  disagreements.md/.csv  Opus vs v5 per chunk and field
  ingest_summary.json    counts
Later replies for the same chunk_id overwrite earlier ones.
"""
import csv, json, os, re, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

UNITS = {
    "baseline": {"tco2e", "tco2e/yr", "ha/yr", "%/yr", "%"},
    "additionality": {None, "", "null", "none", "text"},
    "leakage": {"tco2e", "tco2e/yr"},
    "permanence_buffer": {"%"},
    "crediting_period": {"dates", "date", "years", "date range"},
    "area": {"ha"}, "area_incl_leakage_belt": {"ha"},
    "estimated_reductions": {"tco2e", "tco2e/yr"}, "estimated_reductions_pre_buffer": {"tco2e", "tco2e/yr"},
}
MONTHS = "january february march april may june july august september october november december".split()

# ---------- tolerant parsing ----------
def _clean(s):
    s = s.replace("\ufeff", "")
    s = re.sub(r",\s*([\]}])", r"\1", s)                          # trailing commas
    s = re.sub(r'(?<=[\[{,:]\s)[“”]|[“”](?=\s*[:,}\]])', '"', s)  # smart quotes used as delimiters
    s = re.sub(r'(?<=[\[{,:])[“”]', '"', s)
    return s

def _objects(s):
    """Salvage: raw_decode every {...} that starts with a chunk_id key (handles truncated / broken lists)."""
    dec = json.JSONDecoder(); out = []
    for m in re.finditer(r'\{\s*"chunk_id"', s):
        try: obj, _ = dec.raw_decode(s, m.start()); out.append(obj)
        except json.JSONDecodeError:
            try: obj, _ = dec.raw_decode(_clean(s[m.start():])); out.append(obj)
            except json.JSONDecodeError: pass
    return out

def parse_reply(text):
    blocks = re.findall(r"```(?:json|JSON)?\s*\n?(.*?)```", text, re.S)
    if not blocks:
        i = min([k for k in (text.find("["), text.find("{")) if k >= 0], default=-1)
        blocks = [text[i:]] if i >= 0 else []
    elif text.count("```") % 2 == 1:                       # unterminated last fence (cut-off reply)
        blocks.append(text[text.rfind("```") + 3:].lstrip("json").lstrip("JSON"))
    items, notes = [], []
    for b in blocks:
        got = None
        for cand in (b, _clean(b)):
            try: got = json.loads(cand); break
            except json.JSONDecodeError: pass
        if got is None:
            got = _objects(b); notes.append(f"salvaged {len(got)} objects from a malformed block")
        if isinstance(got, dict):
            got = got.get("results") or got.get("chunks") or got.get("labels") or ([got] if "chunk_id" in got else [])
        items += [g for g in got if isinstance(g, dict) and "chunk_id" in g]
    return items, notes

# ---------- verification ----------
SEP = r"[ ,'’\u00a0\u202f\u2009]"
def numbers(s):
    """Numbers with thousands separators removed: "31'212'644" -> 31212644, "551 338" -> 551338, "3244,31" kept as 3244,31 -> 324431."""
    s = re.sub(rf"(?<=\d){SEP}(?=\d)", "", s)
    return re.findall(r"\d+(?:\.\d+)?", s)

def digits_blob(s):
    return re.sub(rf"(?<=\d){SEP}+(?=\d)", "", s)

def words(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 or w.isdigit()]

def value_in_quote(value, quote):
    v, q = norm_ws(str(value)), norm_ws(quote)
    if v.lower() in q.lower(): return True, "verbatim"
    vn = numbers(v)
    if vn:
        qb = digits_blob(q)
        miss = [n for n in vn if n not in qb and n.lstrip("0") not in qb]
        if miss: return False, f"numbers {miss} not in quote"
        mo = [m for m in MONTHS if m in v.lower() or m[:3] in re.findall(r"[a-z]+", v.lower())]
        mq = [m for m in mo if m not in q.lower() and m[:3] not in re.findall(r"[a-z]+", q.lower())]
        if mq: return False, f"months {mq} not in quote"
        return True, "numbers_match"
    vw = set(words(v)); qw = set(words(q))
    if not vw: return False, "empty value"
    ov = len(vw & qw) / len(vw)
    return (ov >= 0.8, f"word_overlap={ov:.2f}")

def unit_ok(field, unit):
    u = (unit or "").strip().lower().replace("₂", "2").replace(" ", "")
    u = {"tco2": "tco2e", "tco2eq": "tco2e", "tonnesco2e": "tco2e", "hectares": "ha", "percent": "%"}.get(u, u)
    allowed = UNITS[field]
    return (u in allowed) or (not u and None in allowed), u

def main(paths):
    out_dir = Path(os.environ.get("OPUS_OUT", OB)); out_dir.mkdir(parents=True, exist_ok=True)
    reg = load_registry()
    v5 = json.loads(V5_LABELS.read_text()) if V5_LABELS.exists() else {}
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"batches": []}
    files = [Path(p) for p in paths] or sorted(p for p in (OB / "replies").iterdir() if p.suffix in (".json", ".txt", ".md"))
    labels = {}
    log, stats = [], collections.Counter()
    def L(**k): log.append(k); stats["drop:" + k["reason"].split(" ")[0]] += 1
    for fp in files:
        items, notes = parse_reply(fp.read_text(encoding="utf-8", errors="replace"))
        for n in notes: log.append({"file": fp.name, "reason": "parse_note", "detail": n})
        stats["files"] += 1; stats["objects"] += len(items)
        for it in items:
            cid = str(it.get("chunk_id", "")).strip()
            if cid not in reg: L(file=fp.name, chunk_id=cid, reason="unknown_chunk_id"); continue
            chunk = norm_ws(reg[cid]["text"])
            fields_in = it.get("fields") or {k: it[k] for k in ALL_FIELDS if k in it}
            out = {}
            for f in ALL_FIELDS:
                v = fields_in.get(f, NOT_STATED)
                if v is None or (isinstance(v, str) and v.strip().lower().replace(" ", "_") in ("not_stated", "notstated", "n/a", "")):
                    out[f] = NOT_STATED; continue
                if not isinstance(v, dict) or not v.get("value") or not v.get("quote"):
                    L(file=fp.name, chunk_id=cid, field=f, reason="malformed_field", got=v); out[f] = NOT_STATED; continue
                stats["values_in"] += 1
                q = norm_ws(str(v["quote"]))
                if q not in chunk:
                    L(file=fp.name, chunk_id=cid, field=f, reason="quote_not_in_chunk", value=v["value"], quote=v["quote"]); out[f] = NOT_STATED; continue
                ok, how = value_in_quote(v["value"], q)
                if not ok:
                    L(file=fp.name, chunk_id=cid, field=f, reason=f"value_not_in_quote ({how})", value=v["value"], quote=v["quote"]); out[f] = NOT_STATED; continue
                uok, u = unit_ok(f, v.get("unit"))
                if not uok:
                    L(file=fp.name, chunk_id=cid, field=f, reason=f"bad_unit ({u!r})", value=v["value"], quote=v["quote"]); out[f] = NOT_STATED; continue
                out[f] = {"value": str(v["value"]).strip(), "quote": q, "unit": v.get("unit"), "check": how}
                stats["values_kept"] += 1
            conf = []
            for c in it.get("conflicts") or []:
                if isinstance(c, dict) and c.get("quote") and norm_ws(str(c["quote"])) in chunk: conf.append({**c, "quote_verified": True})
                elif isinstance(c, dict): conf.append({**c, "quote_verified": False})
                else: conf.append({"note": str(c), "quote_verified": False})
            labels[cid] = {"chunk_id": cid, "doc": reg[cid]["doc"], "doc_type": reg[cid]["doc_type"], "fields": out,
                           "conflicts": conf, "reply_file": fp.name}
    # chunks of any batch that has a reply but where this chunk is missing
    seen_batches = set()
    for cid in labels:
        for b in manifest["batches"]:
            if cid in b["chunk_ids"]: seen_batches.add(b["batch"])
    missing = []
    for b in manifest["batches"]:
        if b["batch"] in seen_batches:
            missing += [{"batch": b["batch"], "chunk_id": c} for c in b["chunk_ids"] if c not in labels]
    for m in missing: L(chunk_id=m["chunk_id"], batch=m["batch"], reason="missing_from_reply")
    with open(out_dir / "opus_labels.jsonl", "w", encoding="utf-8") as f:
        for cid in sorted(labels): f.write(json.dumps(labels[cid], ensure_ascii=False) + "\n")
    with open(out_dir / "ingest_log.jsonl", "w", encoding="utf-8") as f:
        for r in log: f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    # ---------- disagreement report vs v5 ----------
    rows = []; agg = collections.Counter()
    for cid in sorted(labels):
        if cid not in v5: continue
        for f in FIELDS:
            o, g = labels[cid]["fields"][f], v5[cid][f]
            if o == NOT_STATED and g == NOT_STATED: kind = "both_not_stated"
            elif o == NOT_STATED: kind = "v5_only"
            elif g == NOT_STATED: kind = "opus_only"
            else:
                z = lambda t: re.sub(r"\b(zero|nil|none|insignificant)\b", " 0 ", t, flags=re.I)
                on, gn = set(numbers(z(o["value"]))), set(numbers(z(g["value"])))
                kind = "agree" if (on and on <= gn | set(numbers(g.get("quote") or ""))) or (not on and set(words(o["value"])) & set(words(g["value"]))) else "value_differs"
            agg[(f, kind)] += 1
            if f == "estimated_reductions" and kind == "v5_only" and labels[cid]["fields"]["estimated_reductions_pre_buffer"] != NOT_STATED:
                kind = "v5_only_opus_says_pre_buffer"
            if kind not in ("both_not_stated", "agree"):
                rows.append({"chunk_id": cid, "field": f, "kind": kind,
                             "opus_value": o if o == NOT_STATED else o["value"], "opus_quote": "" if o == NOT_STATED else o["quote"],
                             "v5_value": g if g == NOT_STATED else g["value"], "v5_quote": "" if g == NOT_STATED else (g.get("quote") or "")})
    with open(out_dir / "disagreements.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["chunk_id", "field", "kind", "opus_value", "opus_quote", "v5_value", "v5_quote"]); w.writeheader(); w.writerows(rows)
    md = ["# Opus vs v5 labels", "", f"Chunks compared: {sum(1 for c in labels if c in v5)}. Kinds: agree, value_differs, "
          "opus_only (Opus found a value v5 marked not stated: possible v5 miss), v5_only (Opus said not stated).", "",
          "| field | agree | value_differs | opus_only | v5_only | both_not_stated |", "|---|---:|---:|---:|---:|---:|"]
    for f in FIELDS:
        md.append(f"| {f} | " + " | ".join(str(agg[(f, k)]) for k in ("agree", "value_differs", "opus_only", "v5_only", "both_not_stated")) + " |")
    md += ["", "## Rows to review", ""]
    for r in rows:
        md.append(f"- **{r['chunk_id']}** `{r['field']}` {r['kind']}: Opus `{r['opus_value']}` vs v5 `{r['v5_value']}`"
                  + (f"\n  - Opus quote: \"{r['opus_quote'][:220]}\"" if r["opus_quote"] else ""))
    (out_dir / "disagreements.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    summ = {"files": stats["files"], "chunks_labelled": len(labels), "missing_from_replies": len(missing),
            "values_in": stats["values_in"], "values_kept": stats["values_kept"],
            "drops": {k[5:]: v for k, v in stats.items() if k.startswith("drop:")},
            "batches_with_replies": sorted(seen_batches), "batches_total": len(manifest["batches"]),
            "disagreement_rows": len(rows)}
    (out_dir / "ingest_summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))

if __name__ == "__main__":
    main(sys.argv[1:])
