"""Score merged Tally extractions against the answer key.

This is the same matching and scoring used to produce
ground_truth/tinyaya_scores.json (see /tmp/build_answer_key.py).
Numeric match allows formatting differences and 0.51 abs / 0.01% rel
tolerance. Dates match on start and end (day-default of 1 allowed).
Additionality matches on the tool/conclusion family, not exact wording.
A merge that left the field as 'conflict' is conflict-unresolved even
if gold is among the candidates.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

FIELDS = [
    "baseline",
    "additionality",
    "leakage",
    "permanence_buffer",
    "crediting_period",
    "area",
    "estimated_reductions",
]

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def load_jsonl(path):
    """Load a JSONL file. Split only on '\\n', not unicode line separators."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_answer_key(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_status_and_value(merged_field):
    """Return (status, value_str, candidates)."""
    if merged_field is None:
        return "not_stated", "not stated", []
    if isinstance(merged_field, str):
        s = merged_field.strip()
        if s.lower() in {"not stated", "not_stated", ""}:
            return "not_stated", "not stated", []
        return "clean", s, [{"value": s}]
    if isinstance(merged_field, dict):
        val = merged_field.get("value")
        if val == "conflict" or merged_field.get("conflicts"):
            cands = merged_field.get("conflicts") or []
            return "conflict", "conflict", cands
        if val is None or str(val).strip().lower() in {"not stated", "not_stated"}:
            return "not_stated", "not stated", []
        return "clean", str(val), [{
            "value": val,
            "page": merged_field.get("page"),
            "quote": merged_field.get("quote"),
        }]
    return "not_stated", "not stated", []


def parse_number(text):
    if text is None:
        return None
    s = str(text).replace("\u00a0", " ").replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def numbers_close(a, b, rel=1e-4, abs_tol=0.51):
    if a is None or b is None:
        return False
    if abs(a - b) <= abs_tol:
        return True
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= rel


def parse_percent(text):
    if text is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(text))
    if m:
        return float(m.group(1))
    return None


def parse_dates(text):
    if text is None:
        return []
    s = str(text).replace("–", "-").replace("—", "-").replace(" thru ", " to ").replace("/", "-")
    dates = []
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?[.\- ]+([A-Za-z]+)[.\- ]+(\d{4})\b", s, re.I):
        mon = MONTHS.get(m.group(2).lower()[:3] if len(m.group(2)) == 3 else m.group(2).lower())
        if mon is None:
            mon = MONTHS.get(m.group(2).lower())
        if mon:
            dates.append((int(m.group(1)), mon, int(m.group(3))))
    for m in re.finditer(r"\b([A-Za-z]+)[.\- ]+(\d{1,2})(?:st|nd|rd|th)?[,\- ]+(\d{4})\b", s, re.I):
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            dates.append((int(m.group(2)), mon, int(m.group(3))))
    for m in re.finditer(r"\b([A-Za-z]+)[.\- ]+(\d{4})\b", s, re.I):
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            dates.append((1, mon, int(m.group(2))))
    for m in re.finditer(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b", s):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if mo <= 12:
            dates.append((d, mo, y))
        elif d <= 12:
            dates.append((mo, d, y))
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s):
        dates.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    seen = []
    for dt in dates:
        if dt not in seen:
            seen.append(dt)
    return seen


def year_span(text):
    if text is None:
        return None
    s = str(text).replace("–", "-").replace("—", "-")
    m = re.search(r"\b((?:19|20)\d{2})\s*[-/toTO]+\s*((?:19|20)\d{2})\b", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a < b:
            return (a, b)
    dts = parse_dates(text)
    if len(dts) >= 2:
        years = [dt[2] for dt in dts]
        return (min(years), max(years))
    return None


def date_ranges_match(gold, pred):
    gy, py = year_span(gold), year_span(pred)
    if gy and py and gy == py:
        return True
    gd = parse_dates(gold)
    pd = parse_dates(pred)
    if len(gd) >= 2 and len(pd) >= 2:
        def key(dt):
            d, m, y = dt
            return (y, m, d)
        g_start, g_end = key(gd[0]), key(gd[-1])
        p_start, p_end = key(pd[0]), key(pd[-1])

        def close(a, b):
            ay, am, ad = a
            by, bm, bd = b
            if (ay, am) != (by, bm):
                return False
            return ad == bd or ad == 1 or bd == 1

        return close(g_start, p_start) and close(g_end, p_end)
    return False


ADDITION_HINTS = [
    (re.compile(r"VT0001", re.I), "vt0001"),
    (re.compile(r"Combined tool to identify the baseline scenario and demonstrate additionality", re.I), "combined_tool"),
    (re.compile(r"financial additionality tool", re.I), "financial_tool"),
]


def additionality_match(gold, pred):
    if not pred or str(pred).strip().lower() in {"not stated", "not_stated", "conflict"}:
        return False
    g = str(gold).lower()
    p = str(pred).lower()
    for rx, tag in ADDITION_HINTS:
        if rx.search(str(gold) or "") and rx.search(str(pred) or ""):
            return True
    if "vt0001" in g and "vt0001" in p:
        return True
    if "combined tool" in g and "combined tool" in p:
        return True
    if "financial additionality" in g and "financial additionality" in p:
        return True
    if "combined tool" in g or "additional" in g:
        conclusion_bits = [
            "not a common practice" in p or "not be a common practice" in p,
            "is not the baseline scenario" in p,
            re.search(r"is additional\b", p) is not None,
        ]
        if sum(bool(x) for x in conclusion_bits) >= 1 and (
            "common practice" in p or "baseline scenario" in p or "is additional" in p
        ):
            if "common practice" in p or "baseline scenario" in p or "is additional" in p:
                return True
    return False


def is_not_stated(val):
    if val is None:
        return True
    return str(val).strip().upper().replace(" ", "_") in {"NOT_STATED", "NOT_STATED.", "NOT STATED", ""}


def values_match(field, gold, pred):
    if is_not_stated(gold) or is_not_stated(pred) or pred == "conflict":
        return False
    if field == "additionality":
        return additionality_match(gold, pred)
    if field == "crediting_period":
        if date_ranges_match(gold, pred):
            return True

        def norm(s):
            s = str(s).lower()
            s = s.replace("–", "-").replace("—", "-").replace(" thru ", " to ")
            s = re.sub(r"[.,]", " ", s)
            s = re.sub(r"\b0+(\d)", r"\1", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        return norm(gold) == norm(pred)
    if field == "permanence_buffer":
        gp = parse_percent(gold)
        pp = parse_percent(pred)
        if gp is not None and pp is not None:
            return numbers_close(gp, pp)
        return False
    gn = parse_number(gold)
    pn = parse_number(pred)
    if gn is not None and pn is not None:
        return numbers_close(gn, pn)

    def norm2(s):
        return re.sub(r"[\s,]", "", str(s).lower())

    return norm2(gold) == norm2(pred)


def score_pair(field, gold_val, merged_field):
    status, pred, cands = extract_status_and_value(merged_field)
    gold_is_ns = is_not_stated(gold_val)
    pred_is_ns = status == "not_stated" or is_not_stated(pred)
    match_gold = values_match(field, gold_val, pred)
    if status == "conflict":
        any_cand = any(
            values_match(field, gold_val, c.get("value") if isinstance(c, dict) else c)
            for c in cands
        )
        category = "conflict-unresolved"
        note = "gold is among conflict candidates" if any_cand else "gold not among conflict candidates"
    elif gold_is_ns and pred_is_ns:
        category = "correctly-abstained"
        note = ""
    elif gold_is_ns and not pred_is_ns:
        category = "hallucinated"
        note = "predicted a value but gold is NOT_STATED"
    elif (not gold_is_ns) and pred_is_ns:
        category = "wrong"
        note = "missed a value that is in the document"
    elif match_gold:
        category = "correct"
        note = ""
    else:
        category = "wrong"
        note = "extracted value does not match gold"
    return {
        "field": field,
        "gold_value": gold_val,
        "extract_status": status,
        "extract_value": pred,
        "category": category,
        "note": note,
    }


def _summarise(pairs):
    overall = Counter(r["category"] for r in pairs)
    n = len(pairs)
    acc = (overall.get("correct", 0) + overall.get("correctly-abstained", 0)) / n if n else 0
    stated = [r for r in pairs if not is_not_stated(r["gold_value"])]
    stated_correct = sum(1 for r in stated if r["category"] == "correct")
    per_field = {}
    fields = []
    for r in pairs:
        if r["field"] not in fields:
            fields.append(r["field"])
    for f in fields:
        rows = [r for r in pairs if r["field"] == f]
        c = Counter(r["category"] for r in rows)
        nf = len(rows)
        acc_f = (c.get("correct", 0) + c.get("correctly-abstained", 0)) / nf if nf else 0
        stated_f = [r for r in rows if not is_not_stated(r["gold_value"])]
        stated_correct_f = sum(1 for r in stated_f if r["category"] == "correct")
        per_field[f] = {
            "n": nf,
            "correct": c.get("correct", 0),
            "wrong": c.get("wrong", 0),
            "conflict-unresolved": c.get("conflict-unresolved", 0),
            "correctly-abstained": c.get("correctly-abstained", 0),
            "hallucinated": c.get("hallucinated", 0),
            "accuracy_incl_abstention": round(acc_f, 4),
            "stated_n": len(stated_f),
            "stated_correct": stated_correct_f,
            "stated_accuracy": round(stated_correct_f / len(stated_f), 4) if stated_f else None,
        }
    return {
        "n_pairs": n,
        "overall": {
            "correct": overall.get("correct", 0),
            "wrong": overall.get("wrong", 0),
            "conflict-unresolved": overall.get("conflict-unresolved", 0),
            "correctly-abstained": overall.get("correctly-abstained", 0),
            "hallucinated": overall.get("hallucinated", 0),
            "accuracy_incl_abstention": round(acc, 4),
            "stated_n": len(stated),
            "stated_correct": stated_correct,
            "stated_accuracy": round(stated_correct_all(stated_correct, stated), 4) if stated else None,
        },
        "per_field": per_field,
        "pairs": pairs,
    }


def stated_correct_all(stated_correct, stated):
    return stated_correct / len(stated) if stated else 0


def score_documents(merged_by_doc, answer_key, docs=None):
    """Score merged extractions. merged_by_doc maps doc stem -> merged dict."""
    if docs is None:
        docs = list(merged_by_doc)
    pairs = []
    for doc in docs:
        gold_doc = answer_key[doc]
        merged = merged_by_doc[doc]
        for field in FIELDS:
            gold_val = gold_doc[field]["gold_value"] if isinstance(gold_doc[field], dict) else gold_doc[field]
            row = score_pair(field, gold_val, merged.get(field) if merged else None)
            row["doc"] = doc
            pairs.append(row)
    return _summarise(pairs)


def filter_scores_to_docs(score_obj, docs):
    """Re-summarise an existing tinyaya_scores.json object on a doc subset."""
    docs = set(docs)
    pairs = [p for p in score_obj["pairs"] if p["doc"] in docs]
    return _summarise(pairs)


def format_summary_table(score_obj, title=""):
    lines = []
    if title:
        lines.append(title)
    header = f"{'field':<22} {'n':>3} {'ok':>5} {'wrong':>5} {'conf':>5} {'abst':>5} {'hall':>5} {'acc+abs':>8} {'stated':>10}"
    lines.append(header)
    for f, p in score_obj["per_field"].items():
        sa = f"{p['stated_accuracy']:.0%}" if p["stated_accuracy"] is not None else "n/a"
        lines.append(
            f"{f:<22} {p['n']:>3} {p['correct']:>5} {p['wrong']:>5} "
            f"{p['conflict-unresolved']:>5} {p['correctly-abstained']:>5} "
            f"{p['hallucinated']:>5} {p['accuracy_incl_abstention']:>8.0%} {sa:>10}"
        )
    o = score_obj["overall"]
    sa = f"{o['stated_accuracy']:.0%}" if o["stated_accuracy"] is not None else "n/a"
    lines.append(
        f"{'OVERALL':<22} {score_obj['n_pairs']:>3} {o['correct']:>5} {o['wrong']:>5} "
        f"{o['conflict-unresolved']:>5} {o['correctly-abstained']:>5} "
        f"{o['hallucinated']:>5} {o['accuracy_incl_abstention']:>8.0%} {sa:>10}"
    )
    return "\n".join(lines)
