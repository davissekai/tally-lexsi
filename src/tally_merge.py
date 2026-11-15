"""Tally merge helpers (no notebook side effects).

Copied from src/chunk_merge.py so the Kaggle fine-tune
notebook can import merge_notes without running the original file's
optional chunking loop.
"""
import re

FIELDS = [
    "baseline",
    "additionality",
    "leakage",
    "permanence_buffer",
    "crediting_period",
    "area",
    "estimated_reductions",
]

# Extraction prompt. Example values are obvious placeholders so the
# model has nothing real-looking to copy (the old example,
# "169,741 hectares", is Kasigau II's area and leaked into other docs).
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


def run_extraction(chunk, prompt):
    """Send one chunk to Tiny Aya and parse the JSON it returns.

    `ask` and `parse_json` are the helpers defined earlier in this
    notebook. `ask` does the chat-style generate call; `parse_json`
    pulls the first {...} out of the reply, even if the model wrapped
    it in a markdown fence (as the smoke test showed).
    """
    message = (
        f"{prompt}\n\n"
        f"Pages {chunk['start_page']}–{chunk['end_page']}:\n\n"
        f"{chunk['text']}"
    )
    reply = ask(message)
    return parse_json(reply)


# --------------------------------------------------------------------
# Merge helpers
# --------------------------------------------------------------------

def _stated(item):
    """Turn one field into {value, page, quote}, or None if not stated."""
    if item is None or item == "not stated":
        return None
    if isinstance(item, dict):
        value = item.get("value", "not stated")
        if value is None or value == "not stated" or str(value).strip() == "":
            return None
        return {
            "value": value,
            "page": item.get("page"),
            "quote": item.get("quote"),
            "quote_found": item.get("quote_found"),
        }
    # Sometimes the model returns a bare string instead of the dict.
    if str(item).strip() == "":
        return None
    return {"value": item, "page": None, "quote": None, "quote_found": False}


def _norm_ws(text):
    """Collapse any whitespace (newlines, tabs, double spaces) to one space."""
    return re.sub(r"\s+", " ", str(text)).strip()


def _strip_thousands(text):
    """Drop commas/spaces used as thousands separators, e.g. 169,741 → 169741."""
    return re.sub(r"(?<=\d)[, \u00a0\u202f](?=\d)", "", str(text))


def _extract_numbers(text):
    """Return the numbers in `text`, with commas/spaces already stripped.

    Leading zeros on whole numbers are dropped ("01" → "1") so a date
    written as "01 January 2012" still matches "1 January 2012".
    Decimals such as "30,168.66" are kept as "30168.66".

    Digits that are part of a unit (the "2" in "tCO2e") are ignored,
    otherwise "221,205 tCO2e" would look like the numbers 221205 and 2
    and would not collapse with "221205".
    """
    s = re.sub(r"(?i)\bt?\s*co2e?\b", " ", str(text))
    s = _strip_thousands(s)
    raw = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?:st|nd|rd|th)?(?![A-Za-z])", s)
    out = []
    for n in raw:
        n = re.sub(r"(?:st|nd|rd|th)$", "", n, flags=re.I)
        if "." in n:
            out.append(n)
        else:
            out.append(str(int(n)))
    return out


def _numbers_in_text(nums, text):
    """True iff every number in `nums` appears as a whole number in `text`.

    "20" will not match inside "2020", but "169741" will match
    "169741.38" (the same area, with extra decimal places).
    """
    hay = _strip_thousands(text)
    for n in nums:
        if not re.search(r"(?<![\d.])" + re.escape(n) + r"(?![\d])", hay):
            return False
    return True


def _locate_quote(quote, doc_text):
    """Find a quote in the document. Return (norm_doc, pos, length) or None.

    Matching ignores case and whitespace, because PDF text often breaks
    a sentence across lines and the model may change capitalisation.
    Very short quotes ("0", "221205") are rejected: they appear all
    over a document and are not reliable evidence on their own.
    """
    if not quote or not doc_text:
        return None
    q = _norm_ws(quote)
    if not q or q.lower() == "not stated":
        return None
    # A real quote is a sentence, or at least a short clause. Anything
    # shorter than 16 characters is usually just the value itself.
    if len(q) < 16:
        return None
    d = _norm_ws(doc_text)
    dl, ql = d.lower(), q.lower()
    pos, q_len = dl.find(ql), len(q)
    if pos == -1:
        for n in (80, 60, 40):
            if len(q) > n:
                pos = dl.find(ql[:n])
                if pos != -1:
                    q_len = n
                    break
    if pos == -1:
        return None
    return d, pos, q_len


def _quote_in_doc(quote, doc_text):
    """True iff the quote appears in the document, ignoring case/whitespace."""
    return _locate_quote(quote, doc_text) is not None


def _page_in_doc(doc_text, quote):
    """Best-effort page number for a quote, using --- page N --- markers."""
    loc = _locate_quote(quote, doc_text)
    if not loc:
        return None
    d, pos, _ = loc
    pages = re.findall(r"--- page (\d+) ---", d[:pos])
    return int(pages[-1]) if pages else None


def _sentence_breaks(d, left, right):
    """Positions of sentence-ending punctuation in d[left:right]."""
    breaks = []
    for i in range(max(0, left), min(len(d), right)):
        if d[i] in ".?!" and (i + 1 >= len(d) or d[i + 1] == " "):
            breaks.append(i)
    return breaks


_ANAPHORA = re.compile(
    r"^\s*(This|These|The above|Applying this|Hence|Therefore|Thus)\b",
    re.I,
)


def _evidence_span(doc_text, quote):
    """The document sentence that contains the quote, or the quote itself.

    The prompt caps quotes at 40 words, so the number is often cut off
    ("...Kasigau Corridor REDD P" instead of "...total 169,741 hectares").
    We therefore read the rest of that same sentence, but not the
    sentences around it — those often contain other figures.

    Exception: if the sentence starts with a back-reference such as
    "Applying this factor...", we also include the previous sentence,
    because that is usually where the number sits.
    """
    if not quote:
        return ""
    q = _norm_ws(quote)
    loc = _locate_quote(quote, doc_text) if doc_text else None
    if not loc:
        return q
    d, pos, q_len = loc
    # Start at the quote itself. A short look-back (one clause, not a
    # whole form or table) is allowed if the model skipped a few words
    # at the start of the sentence.
    breaks_before = _sentence_breaks(d, max(0, pos - 120), pos)
    start = breaks_before[-1] + 1 if breaks_before else pos
    # If the quote already ends at a sentence boundary, stop there.
    # Otherwise look forward just far enough to finish a truncated
    # 40-word quote, and stop at the first sentence break.
    matched = d[pos:pos + q_len].rstrip()
    if matched[-1:] in ".?!":
        end = pos + q_len
    else:
        cap = min(len(d), pos + q_len + 280)
        breaks_after = _sentence_breaks(d, pos + q_len, cap)
        end = breaks_after[0] + 1 if breaks_after else cap
    sentence = d[start:end].strip()
    if _ANAPHORA.search(sentence):
        prev_breaks = _sentence_breaks(d, max(0, start - 400), start)
        if prev_breaks:
            sentence = d[prev_breaks[-1] + 1:end].strip()
        else:
            sentence = d[max(0, start - 400):end].strip()
    return sentence


_ZERO_WORDS = re.compile(
    r"\b(?:zero|none|nil)\b|"
    r"no displacement|no leakage|"
    r"leakage (?:emissions )?are accounted as zero|"
    r"leakage is considered as (?:0|zero)|"
    r"accounted as zero",
    re.I,
)


def _value_in_quote(value, evidence):
    """True iff `value` is actually supported by the quote/sentence.

    For values that contain numbers (including a period "2011 to 2041"),
    every number must appear in the evidence. "0 tCO2e" is also accepted
    when the sentence says "zero" rather than the digit 0.
    For descriptive values with no digits, a substantial piece of the
    wording must appear.
    """
    if not evidence:
        return False
    ev = _norm_ws(evidence)
    val = _norm_ws(value)
    if not val:
        return False
    nums = _extract_numbers(val)
    if nums:
        # For a period such as "2005-01-01 to 2034-12-31" or
        # "14 March 2011 – 13 March 2041", the years are what matter.
        # Day and month numbers often appear as words ("December") in
        # the sentence, so we do not require those.
        years = [n for n in nums if re.fullmatch(r"\d{4}", n)]
        if years:
            return _numbers_in_text(years, ev)
        if _numbers_in_text(nums, ev):
            return True
        # "emissions from leakage are zero" supports a value of 0.
        if nums == ["0"] and _ZERO_WORDS.search(ev):
            return True
        return False
    ev_l, val_l = ev.lower(), val.lower()
    if val_l in ev_l:
        return True
    if len(val_l) >= 40 and val_l[:40] in ev_l:
        return True
    words = [w for w in re.findall(r"[a-z]{4,}", val_l)]
    if not words:
        return val_l in ev_l
    hits = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", ev_l))
    return hits >= max(3, int(0.6 * len(words)))


# What a valid value is allowed to look like, by field.
# Kept simple on purpose: we only reject obvious mismatches
# (a hectare figure filed under baseline, a % filed as area, etc.).
_AREA_UNIT = re.compile(r"\b(ha|hectares?|acres?)\b", re.I)
_PERCENT = re.compile(r"%|\bpercent(?:age)?\b", re.I)
_TCO2 = re.compile(
    r"\bt\s*co2e?\b|\btco2e\b|\btonnes?\b|\btons?\b|\bm\.?t\.?\b|\bghg\b",
    re.I,
)
_PERIOD = re.compile(
    r"\b(?:years?|year|months?|days?|"
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b|"
    r"\d{4}\s*[-–—/to]+\s*\d{4}|"
    r"\b\d{4}\b|"
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}",
    re.I,
)
_RATE = re.compile(r"/year|\bper year\b|\bper yr\b|\brate\b|\bdeforestation\b", re.I)
_BARE_PERCENT = re.compile(r"^[\d,.\s]+\s*(%|percent|percentage)\s*$", re.I)
_BARE_AREA = re.compile(
    r"^[\d,.\s]+\s*(ha|hectares?|acres?)\s*$", re.I
)


def _field_units_ok(field, value, evidence=""):
    """True iff `value` looks like the right kind of thing for `field`.

    Units may sit on the value or in the supporting sentence, because
    the model sometimes drops them ("3,871" with a quote that says
    "3,871 ha").
    """
    v = str(value)
    blob = f"{v} {evidence}"
    if field == "area":
        return bool(_extract_numbers(v) and _AREA_UNIT.search(blob))
    if field in ("permanence_buffer", "leakage"):
        # A percentage, a tCO2e / tonne deduction, or an explicit zero.
        if re.search(r"\bzero\b", v, re.I) or _extract_numbers(v) == ["0"]:
            return True
        if _extract_numbers(v) and (_PERCENT.search(blob) or _TCO2.search(blob)):
            return True
        return False
    if field == "estimated_reductions":
        return bool(_extract_numbers(v) and _TCO2.search(blob))
    if field == "crediting_period":
        return bool(_PERIOD.search(v))
    if field in ("baseline", "additionality"):
        # These are descriptive. Reject a bare area ("169,741 hectares"),
        # a bare percentage ("39.90%"), or a bare number with no words
        # ("55,244.75", often a table parameter). A rate such as
        # "10,738.9 hectares/year" is allowed for baseline.
        if re.fullmatch(r"[+\-]?[\d,.\s]+", v.strip()):
            return False
        if re.search(r"value applied\s*:", evidence, re.I):
            return False
        if _BARE_AREA.search(v.strip()) and not _RATE.search(v):
            return False
        if _BARE_PERCENT.search(v.strip()):
            return False
        # A bare tCO2e figure is only a baseline if the evidence
        # actually talks about baseline emissions, not project benefits.
        if field == "baseline" and _TCO2.search(v) and not re.search(r"baseline", blob, re.I):
            return False
        return True
    return True


def _same_value(a, b):
    """True iff two values are the same number (or the same wording).

    "3,871", "3,871 ha" and "3,871 hectares" collapse together.
    "01 January 2010 – 31 December 2039" and "2010-2039" collapse
    because they share the same year endpoints. "30 years" and
    "2016-2045" do not, because one has no years.
    """
    if _norm_ws(a).lower() == _norm_ws(b).lower():
        return True
    na, nb = _extract_numbers(a), _extract_numbers(b)
    if not na or not nb:
        return False
    years_a = tuple(n for n in na if re.fullmatch(r"\d{4}", n))
    years_b = tuple(n for n in nb if re.fullmatch(r"\d{4}", n))
    if years_a and years_b:
        return years_a == years_b
    return na == nb


def _collapse(items):
    """Group candidates that are the same number; keep the richest wording."""
    groups = []
    for item in items:
        placed = False
        for group in groups:
            if _same_value(group[0]["value"], item["value"]):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    collapsed = []
    for group in groups:
        keep = dict(max(
            group,
            key=lambda x: (
                len(str(x.get("value") or "")),
                len(str(x.get("quote") or "")),
            ),
        ))
        pages = []
        for x in group:
            if x.get("page") is not None and x["page"] not in pages:
                pages.append(x["page"])
            for p in x.get("pages") or []:
                if p not in pages:
                    pages.append(p)
        keep["pages"] = pages
        collapsed.append(keep)
    return collapsed


def _classify(item, field, doc_text=None):
    """Return (bucket, reason, item) where bucket is supported|unsupported."""
    item = dict(item)
    quote = item.get("quote")
    value = item.get("value")

    if doc_text:
        quote_ok = _quote_in_doc(quote, doc_text)
        if quote_ok and item.get("page") is None:
            item["page"] = _page_in_doc(doc_text, quote)
        item["quote_found"] = quote_ok
    else:
        # No document text: fall back to the flag set at extraction time.
        quote_ok = item.get("quote_found") is True

    if not quote_ok:
        return "unsupported", "quote not in document", item

    evidence = _evidence_span(doc_text, quote) if doc_text else _norm_ws(quote)
    if not _value_in_quote(value, evidence):
        return "unsupported", "value not in quote", item
    if not _field_units_ok(field, value, evidence):
        return "unsupported", "wrong unit or type for field", item
    return "supported", None, item


def merge_notes(chunk_results, doc_text=None):
    """Merge a list of per-chunk dicts into one record for the document.

    Pass `doc_text` (the extracted PDF text) whenever you have it.
    That lets us re-check quotes across line breaks and recover a
    page number for candidates the original quote_found flag missed.
    """
    merged = {}
    for field in FIELDS:
        found, unsupported = [], []
        for result in chunk_results:
            if not isinstance(result, dict) or "_error" in result:
                continue
            item = _stated(result.get(field))
            if not item:
                continue
            bucket, reason, item = _classify(item, field, doc_text)
            if bucket == "supported":
                found.append(item)
            else:
                item["reject"] = reason
                unsupported.append(item)

        # Filters run before any conflict decision.
        found = _collapse(found)

        if not found:
            merged[field] = (
                {"value": "not stated", "unsupported": unsupported}
                if unsupported else "not stated"
            )
            continue

        if len(found) == 1:
            keep = dict(found[0])
            if unsupported:
                keep["unsupported"] = unsupported
            merged[field] = keep
        else:
            rec = {"value": "conflict", "conflicts": found}
            if unsupported:
                rec["unsupported"] = unsupported
            merged[field] = rec

    return merged
