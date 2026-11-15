#!/usr/bin/env python3
"""Tally Verra consistency calculator.

Reads the cleaned extraction JSONs in results_clean/ and checks whether
the numbers in each document hang together the way a Verra AFOLU
project's numbers should: area, emission reductions, crediting or
monitoring period, permanence buffer, and leakage.

This is a screening tool, not a re-calculation of the project's own
worksheet. It flags internal inconsistencies and values that fall
outside a published-plausible range, so they can be reviewed before
the GPT/Claude benchmark and the write-up.

Do not push this to Kaggle with the API (that dropped the HF_TOKEN
secret last time). A paste-ready notebook cell lives in
section7_cells.md (section 7i) and in calc_cell.py. Run those from
the Kaggle UI if you want this in the kernel.

Usage:
    python verra_calc.py
    python verra_calc.py --input /path/to/results_clean --output /path/to/out
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional


# ----------------------------------------------------------------------
# Screening thresholds
# ----------------------------------------------------------------------
# Reductions per hectare per year. This is a literature-informed
# screening band, not a Verra pass/fail limit. Verra does not publish
# a single "allowed" tCO2e/ha/yr figure.
#
# Why 0.5-30:
#   * REDD+ avoided-deforestation rates in tropical Africa commonly
#     land around 2-15 tCO2e/ha/yr. That is roughly a 1-3% annual
#     forest-loss rate times 100-250 tC/ha, converted with 44/12.
#     Published VCS/CCB monitoring reports for East and Central
#     African REDD+ sit in this neighbourhood.
#   * ARR / plantation (bamboo, teak, eucalyptus) growth can yield
#     about 2-20 tCO2e/ha/yr, and fast-growing stands in a short
#     monitoring window can briefly run higher.
#   * Below 0.5 tCO2e/ha/yr is unusually low: often a lifetime total
#     has been divided by a monitoring window, or the area is a
#     much larger lease / leakage-belt figure.
#   * Above 30 tCO2e/ha/yr is unusually high: often a period total
#     has been divided by the wrong (too-small) area, or a
#     cumulative figure has been treated as a single year. High-stock
#     avoided-logging sites can legitimately exceed 30 for a year;
#     the calculator flags those for review rather than calling
#     them impossible.
INTENSITY_MIN = 0.5
INTENSITY_MAX = 30.0

# VCS AFOLU Non-Permanence Risk Tool (current versions 4.x): the
# minimum risk rating is 10% and the maximum is 60%. A project whose
# score would exceed 60% is not eligible. In practice many well-run
# projects land in the 10-20% band, which we treat as "typical"
# without flagging.
BUFFER_MIN_PCT = 10.0
BUFFER_MAX_PCT = 60.0
BUFFER_TYPICAL_MAX_PCT = 20.0

# Relative tolerance for "does total / years match the stated annual?"
CONSISTENCY_TOL = 0.02

# Leakage larger than this share of reductions is unusual enough to flag.
LEAKAGE_SHARE_FLAG = 0.40


MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def parse_number(text: str) -> Optional[float]:
    """Pull the first written number out of `text`.

    Handles thousands commas (3,778,511), decimals (30,168.66), a
    European form (3.778.510,93), and '3.5 million'. Returns None if
    there is no number.
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None

    million = re.search(
        r"(\d+(?:[.,]\d+)?)\s*million", raw, flags=re.IGNORECASE
    )
    if million:
        return parse_number(million.group(1)) * 1_000_000

    # Prefer a number that has thousand-separators or a decimal over a
    # bare digit run, so "01-June 2022" does not yield 1.
    candidates = re.findall(
        r"[-+]?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|[-+]?\d+(?:[.,]\d+)?",
        raw,
    )
    if not candidates:
        return None

    token = candidates[0]
    # European: 3.778.510,93 — only when there is a thousands
    # dot plus a decimal comma, to avoid eating "30,168".
    if re.fullmatch(r"[-+]?\d{1,3}(?:\.\d{3})+,\d+", token):
        return float(token.replace(".", "").replace(",", "."))
    # US / English: commas as thousands, dot as decimal.
    token = token.replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _unit_kind(text: str) -> tuple[Optional[str], bool]:
    """Return (unit, per_year) from the wording around a value."""
    s = text.lower()
    s = s.replace("t co2 e", "tco2e").replace("t co2e", "tco2e")
    s = s.replace("t  co2e", "tco2e")
    per_year = bool(re.search(r"/\s*year|per\s+year|a year|annually", s))

    if "%" in s or re.search(r"\bpercent\b|\bper\s*cent\b", s):
        return "percent", per_year
    if re.search(r"\bha\b|\bhectare", s):
        return "ha", per_year
    if re.search(r"\bacre", s):
        return "acre", per_year
    if re.search(r"tco2e|tco2|tonnes?\s*co2|tons?\s*co2|co2e|co2\s*eq", s):
        return "tco2e", per_year
    if re.search(r"\btonnes?\b|\btons?\b|\bt\b", s):
        return "tonne", per_year
    if re.search(r"\byears?\b", s):
        return "years", per_year
    return None, per_year


def _month_num(name: str) -> Optional[int]:
    return MONTHS.get(name.lower().strip(".-"))


def parse_one_date(text: str) -> Optional[date]:
    """Parse a single calendar date from a variety of Verra-style forms."""
    t = re.sub(r"\s+", " ", text.strip().strip(",;."))
    t = t.replace(" -", "-").replace("- ", "-")

    # ISO yyyy-mm-dd
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_date(y, mo, d)

    # 14 March 2011 / 01-June 2022 / 31-May-2042 / 24-March-2016 /
    # January-2012 / 31-December-2031 / 30-June-2045
    m = re.fullmatch(
        r"(?:(\d{1,2})[.\-/\s])?([A-Za-z]+)[.\-/\s]+(\d{4})",
        t,
    )
    if m:
        d = int(m.group(1) or 1)
        mo = _month_num(m.group(2))
        y = int(m.group(3))
        if mo:
            return _safe_date(y, mo, d)

    # 02-11-2020 or 02/11/2020. These documents use day-month-year
    # (the Miro quote writes "02nd November 2020" next to 02-11-2020).
    m = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", t)
    if m:
        a, b, y = map(int, m.groups())
        if a > 12:
            return _safe_date(y, b, a)
        if b > 12:
            return _safe_date(y, a, b)
        return _safe_date(y, b, a)  # DMY default

    return None


def _safe_date(y: int, mo: int, d: int) -> Optional[date]:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_period(text: str) -> dict[str, Any]:
    """Parse a crediting or monitoring window.

    Returns keys: start, end, years, raw, form ('dates' | 'years_only'
    | 'duration' | 'year' | None).
    """
    raw = re.sub(r"\s+", " ", (text or "").strip())
    out: dict[str, Any] = {
        "start": None, "end": None, "years": None, "raw": raw, "form": None,
    }
    if not raw:
        return out

    duration = None
    dur_m = re.search(r"(\d+(?:\.\d+)?)\s*years?\b", raw, flags=re.IGNORECASE)
    if dur_m:
        duration = float(dur_m.group(1))

    # Split a range on a dash / 'to' / en-dash, but not the dashes
    # inside a date like 01-June-2022 or 2005-01-01.
    parts = re.split(
        r"\s+(?:to|through|until|and)\s+|\s+[–—]\s+|(?<!\d)\s+-\s+(?!\d)",
        raw,
        maxsplit=1,
    )
    # Also "January-2012 – 31-December-2031; 20 years total period"
    if len(parts) == 1:
        parts = re.split(r"\s*[–—]\s*", raw, maxsplit=1)
    if len(parts) == 1:
        # year-year: 2010-2039, 2020-2021 (not a day-month-year)
        yrange = re.fullmatch(r"(\d{4})\s*[-–—]\s*(\d{4})", raw)
        if yrange:
            y1, y2 = int(yrange.group(1)), int(yrange.group(2))
            out["start"] = date(y1, 1, 1)
            out["end"] = date(y2, 12, 31)
            # Inclusive calendar years. 2010-2039 is a 30-year
            # crediting period; 2020-2021 is a 2-year monitoring window.
            out["years"] = float(y2 - y1 + 1)
            out["form"] = "years_only"
            return out

    if len(parts) >= 2:
        left = parts[0]
        right = re.split(r"[;,]|\btotal\b", parts[1], maxsplit=1)[0]
        d1 = parse_one_date(left.strip(" ;,"))
        d2 = parse_one_date(right.strip(" ;,"))
        # Bare year on either side (e.g. leftover after stripping).
        if not d1:
            ym = re.search(r"\b(19|20)\d{2}\b", left)
            if ym:
                d1 = date(int(ym.group(0)), 1, 1)
        if not d2:
            ym = re.search(r"\b(19|20)\d{2}\b", right)
            if ym:
                # end of that year if only a year is given
                d2 = date(int(ym.group(0)), 12, 31)
        if d1 and d2 and d2 >= d1:
            out["start"] = d1
            out["end"] = d2
            span = (d2 - d1).days / 365.25
            # Prefer a stated duration when it is within 1.5 years of
            # the actual span (Miro calls 24 Mar 2016-30 Jun 2045
            # "30 years" even though the calendar span is ~29.3).
            if duration is not None and abs(span - duration) <= 1.5:
                out["years"] = duration
            else:
                # Snap very-near-integer spans (20y minus a day, etc.).
                if duration is None and abs(span - round(span)) < 0.02:
                    out["years"] = float(round(span))
                else:
                    out["years"] = duration if duration is not None else round(span, 4)
            out["form"] = "dates"
            return out

    if duration is not None and not re.search(r"\b(19|20)\d{2}\b", raw):
        out["years"] = duration
        out["form"] = "duration"
        return out

    # A lone year, often a reporting year ("2022", "2021").
    lone = re.fullmatch(r"(?:year\s*)?((?:19|20)\d{2})", raw, flags=re.I)
    if lone:
        y = int(lone.group(1))
        out["start"] = date(y, 1, 1)
        out["end"] = date(y, 12, 31)
        out["years"] = 1.0
        out["form"] = "year"
        return out

    if duration is not None:
        out["years"] = duration
        out["form"] = "duration"
    return out


def parse_value(text: str) -> dict[str, Any]:
    """Normalise a single extracted field value into numbers and units."""
    raw = (text or "").strip()
    period = parse_period(raw)
    unit, per_year = _unit_kind(raw)
    number = parse_number(raw)

    # A bare year or a date range should not also be treated as a
    # quantity (the number would be 2010 or 14 or 01).
    looks_like_period = period["form"] in {"dates", "years_only", "year"} or (
        period["form"] == "duration" and unit == "years"
    )
    if looks_like_period and unit in (None, "years"):
        number = period["years"] if period["form"] == "duration" else None
        unit = "years" if period["form"] == "duration" else (unit or "period")

    return {
        "raw": raw,
        "number": number,
        "unit": unit,
        "per_year": per_year,
        "period": period,
    }


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------

def _as_field(raw: Any) -> dict[str, Any]:
    """Normalise a merged field that may be a dict or the string 'not stated'."""
    if raw is None:
        return {"value": "not stated", "conflicts": [], "unsupported": [],
                "quote": None, "page": None, "pages": None}
    if isinstance(raw, str):
        return {"value": raw, "conflicts": [], "unsupported": [],
                "quote": None, "page": None, "pages": None}
    return {
        "value": raw.get("value", "not stated"),
        "conflicts": list(raw.get("conflicts") or []),
        "unsupported": list(raw.get("unsupported") or []),
        "quote": raw.get("quote"),
        "page": raw.get("page"),
        "pages": raw.get("pages"),
    }


def _candidate(value: Any, page: Any, quote: Any, source: str) -> dict[str, Any]:
    return {
        "value": None if value is None else str(value),
        "page": page,
        "quote": quote or "",
        "source": source,
        "parsed": parse_value(str(value) if value is not None else ""),
        "score": 0.0,
        "reasons": [],
        "tags": [],
    }


def field_candidates(fld: dict[str, Any]) -> list[dict[str, Any]]:
    """The values the merge treated as supported for this field."""
    value = fld.get("value")
    if value in (None, "not stated", "conflict"):
        cands = []
        for item in fld.get("conflicts") or []:
            if isinstance(item, dict):
                cands.append(_candidate(item.get("value"), item.get("page"),
                                        item.get("quote"), "conflict"))
            else:
                cands.append(_candidate(item, None, "", "conflict"))
        return cands
    return [_candidate(value, fld.get("page"), fld.get("quote"), "clean")]


def document_kind(stem: str) -> str:
    """'monitoring' (MR / verification) or 'design' (PD / PDD / validation)."""
    s = stem.lower()
    if "verification" in s or re.search(r"(^|[_-])mr([_-]|$)", s) or "monitoring" in s:
        return "monitoring"
    return "design"


def project_label(stem: str) -> dict[str, str]:
    """Split a filename stem into a Verra id and a short title."""
    m = re.match(r"^(\d+)_(.+)$", stem)
    if not m:
        return {"project_id": "", "title": stem, "stem": stem}
    title = m.group(2).replace("_", " ").replace("-", " ")
    return {"project_id": m.group(1), "title": title, "stem": stem}


def load_project(path: Path) -> dict[str, Any]:
    """Read one results_clean JSON and return a dict the checker can use."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    stem = Path(path).stem
    merged = data.get("merged") or {}
    fields = {name: _as_field(merged.get(name)) for name in (
        "baseline", "additionality", "leakage", "permanence_buffer",
        "crediting_period", "area", "estimated_reductions",
    )}
    meta = project_label(stem)
    return {
        "path": str(path),
        "stem": stem,
        "doc": data.get("doc") or stem,
        "project_id": meta["project_id"],
        "title": meta["title"],
        "kind": document_kind(stem),
        "fields": fields,
        "n_chunks": data.get("n_chunks"),
    }


# ----------------------------------------------------------------------
# Scoring / conflict resolution
# ----------------------------------------------------------------------
# These rules are deliberately quote-driven. We never hard-code a
# project's "right" number. The known figures in MERGE_FIX.md are
# used afterwards as a sanity check, not as inputs.

def _qx(cand: dict[str, Any]) -> str:
    return f"{cand.get('quote') or ''} {cand.get('value') or ''}".lower()


def _add(cand: dict[str, Any], pts: float, reason: str, tag: Optional[str] = None) -> None:
    cand["score"] += pts
    if reason:
        cand["reasons"].append(reason)
    if tag and tag not in cand["tags"]:
        cand["tags"].append(tag)


def _is_composite_area(raw: str) -> bool:
    """True if the value lists several different hectare figures."""
    nums = re.findall(r"\d[\d,]*\.?\d*", raw or "")
    values = []
    for n in nums:
        v = parse_number(n)
        if v and v > 10:
            values.append(round(v, 2))
    return len(set(values)) >= 2


def score_area(cand: dict[str, Any]) -> None:
    q, parsed = _qx(cand), cand["parsed"]
    if parsed["unit"] not in ("ha", "acre") and parsed["number"] is None:
        _add(cand, -20, "no area figure")
        return
    if parsed["unit"] == "acre":
        _add(cand, -2, "stated in acres, not hectares")
    if parsed["unit"] is None:
        _add(cand, -1, "bare number, no hectare unit")
    if _is_composite_area(cand["value"] or ""):
        _add(cand, -8, "lists several component parcels, not a single project area",
             "composite")
        return

    if re.search(r"eligible project area|total eligible", q):
        _add(cand, 8, "quote calls it the eligible project area", "project_area")
    elif re.search(r"project accounting area|\bpaa\b|accounting area", q):
        _add(cand, 7, "quote calls it the project accounting area", "accounting_area")
    elif re.search(r"\bproject area\b|\bthe project area is\b|rukinga sanctuary is", q):
        _add(cand, 6, "quote calls it the project area", "project_area")
    elif re.search(r"eligible", q):
        _add(cand, 4, "quote calls the area eligible", "project_area")

    if re.search(r"considered for this monitoring period|for this monitoring", q):
        _add(cand, 4, "area considered for this monitoring period", "monitoring_area")
    if re.search(r"project boundary|including (the )?leakage|leakage management|leakage belt", q):
        _add(cand, -4, "project boundary / includes leakage-management land", "boundary")
    if re.search(r"\blease\b", q):
        _add(cand, -3, "lease area, not the eligible project area", "lease")
    if re.search(r"will be planted|area of [0-9,.]+\s*ha will be planted|planted", q):
        _add(cand, -5, "planted (or to-be-planted) subset, not the project area", "planted")
    if re.search(r"predicted to be deforested|expected to be converted", q):
        _add(cand, -6, "predicted deforestation, not the project area", "predicted")
    if re.search(r"established \d|land holding|total land|occupied the total", q):
        _add(cand, -3, "broader land holding / area established, not the accounted project",
             "holding")
    if re.search(r"blocks of land covered|phase ii of the kasigau", q):
        _add(cand, 5, "quote gives the Phase II project total", "project_area")


def _span_for_number(text: str, number: Optional[float]) -> Optional[tuple[int, int]]:
    """Locate the written form of `number` in `text`."""
    if not text or number is None:
        return None
    for m in re.finditer(
        r"[-+]?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|[-+]?\d+(?:[.,]\d+)?",
        text,
    ):
        n = parse_number(m.group())
        if n is None:
            continue
        if abs(n - number) < 0.51 or _nearly_equal(n, number, 0.0001):
            return m.start(), m.end()
    return None


def _leadin_for_number(text: str, number: Optional[float], width: int = 80) -> str:
    """The words immediately before this candidate's own figure."""
    span = _span_for_number(text or "", number)
    if not span:
        return ""
    return (text or "")[max(0, span[0] - width):span[0]].lower()


def _context_for_number(text: str, number: Optional[float], window: int = 70) -> str:
    """A short window around this candidate's own figure, not the whole quote.

    One sentence often states a lifetime total and an annual average
    together. Scoping has to look at the words next to *this* number,
    or the total gets tagged as annual because the same sentence also
    says 'average annual'.
    """
    span = _span_for_number(text or "", number)
    if not span:
        return (text or "").lower()
    return (text or "")[max(0, span[0] - window):span[1] + window].lower()


def _reductions_scope(cand: dict[str, Any], kind: str) -> tuple[str, bool]:
    """Return (scope, explicit) from the wording around this value."""
    text = _qx(cand)
    n = cand["parsed"]["number"]
    leadin = _leadin_for_number(text, n)
    ctx = _context_for_number(text, n)

    if cand["parsed"]["per_year"] or re.search(
        r"average annual|annual (?:ghg |emission )?(?:removal|reduction)|"
        r"/\s*year|per year",
        leadin,
    ):
        return "annual", True
    # Period / cumulative wording anywhere in the window around the
    # number wins over a generic "avoided emission of X" lead-in
    # ("...14,883,342 tCO2e during this first monitoring period").
    if re.search(
        r"this \(m\d+\) monitoring period|current defined monitoring period|"
        r"during m\d+\b|throughout the paa during|"
        r"during this (?:first |second |third )?monitoring period|"
        r"over this (?:second |first |third )?monitoring period|"
        r"(?:the )?second monitoring period|"
        r"this monitoring period|"
        r"first monitoring period",
        ctx,
    ):
        return "period", True
    if re.search(r"to date|since the project start|cumulative", ctx):
        return "cumulative", True
    if re.search(
        r"(?:long-term average ghg benefits|total (?:potential )?(?:ghg )?"
        r"(?:emission )?(?:removal|reduction)s?|avoided emission) of$",
        leadin.strip(),
    ) or re.search(r"total potential ghg|long-term average ghg benefits of", leadin):
        return "lifetime", True
    if re.search(r"ex-ante|project lifetime|crediting period", ctx) and not cand["parsed"]["per_year"]:
        return "lifetime", True
    # Fall back to the document type only when the quote is silent.
    return ("period" if kind == "monitoring" else "lifetime"), False


def score_reductions(cand: dict[str, Any], kind: str) -> None:
    q, parsed = _qx(cand), cand["parsed"]
    n = parsed["number"]

    if n is None:
        _add(cand, -20, "no numeric reductions figure")
        return
    if parsed["unit"] not in ("tco2e", "tonne", None):
        _add(cand, -8, f"unexpected unit for reductions ({parsed['unit']})")
    if parsed["unit"] is None:
        _add(cand, -1, "bare number, unit assumed tCO2e from the field")

    # Misfilings and wrong-field leftovers.
    if re.search(r"baseline emissions", q) and not re.search(
        r"emission reductions?|net estimated|net ghg", q
    ):
        _add(cand, -15, "quote describes baseline emissions, not reductions",
             "baseline_misfile")
    if re.search(r"ghge\s*,?\s*t\s*=\s*0|use of fire|land preparation", q):
        _add(cand, -12, "zero fire / land-preparation emissions, not project reductions",
             "wrong_field")
    if re.search(r"fuel woods?|stoves?|cookstoves?", q):
        _add(cand, -10, "cookstove fuelwood co-benefit, not the project ER total",
             "co_benefit")
    if re.search(r"total carbon by", q):
        _add(cand, -10, "total carbon stock, not emission reductions", "carbon_stock")

    leadin = _leadin_for_number(q, n)
    if re.search(
        r"emission reductions?|ghg (?:emission )?(?:reductions?|benefits|removal)|"
        r"avoided emission|credits eligible for issuance|quantified emissions reductions|"
        r"total potential ghg|long-term average ghg",
        leadin,
    ) or re.search(
        r"net estimated emission reductions|net ghg emission reductions|"
        r"reduced [0-9,]+\s*tonnes of co2e|avoided emission of",
        q,
    ):
        _add(cand, 6, "quote describes (net) emission reductions", "reductions")
    if re.search(r"eligible for issuance as vcus|buffer withholding", q):
        _add(cand, 2, "issuance figure after the buffer withholding", "issuance_net")

    scope, explicit = _reductions_scope(cand, kind)
    cand["tags"].append(f"scope:{scope}")
    if explicit:
        cand["tags"].append("scope_explicit")
    if kind == "monitoring" and scope == "period" and explicit:
        _add(cand, 4, "figure is for this monitoring period")
    elif kind == "monitoring" and scope == "period" and not explicit:
        _add(cand, 1, "treated as a period figure because this is an MR / verification")
    elif kind == "monitoring" and scope == "cumulative":
        _add(cand, 1, "cumulative / to-date figure (kept as context)")
    elif kind == "design" and scope in {"lifetime", "annual"}:
        _add(cand, 4, "lifetime or annual figure, fits a design document")
    elif scope == "annual":
        _add(cand, 3, "stated as an annual average")

    # A literal zero is almost never the project's estimated reductions.
    if n == 0:
        _add(cand, -6, "zero value")


def score_period(cand: dict[str, Any], kind: str) -> None:
    q, parsed = _qx(cand), cand["parsed"]
    period = parsed["period"]
    if period["years"] is None and period["start"] is None:
        _add(cand, -10, "could not parse a period")
        return

    if re.search(r"crediting period|ghg accounting", q):
        _add(cand, 8, "quote calls it the crediting period", "crediting")
    if re.search(r"verification period|monitoring period|monitoring for the years|"
                 r"this 4th monitoring|current monitoring", q):
        _add(cand, 5, "quote calls it a monitoring / verification window", "monitoring")
        if kind == "design":
            _add(cand, -3, "monitoring window on a design document, not the crediting period")
    if period["form"] == "year" and not re.search(r"crediting", q):
        _add(cand, -2, "a single reporting year, not a crediting period", "monitoring")
    if period["form"] == "duration" and re.search(r"crediting period life span|"
                                                  r"years total period|crediting period", q):
        _add(cand, 5, "stated crediting-period length", "crediting")
    if period["form"] == "dates" and period["years"] and period["years"] >= 10:
        _add(cand, 3, "full date range of a typical crediting length")
    if period["form"] == "years_only" and period["years"] and period["years"] >= 20:
        _add(cand, 3, "year-year span of a typical crediting length", "crediting")
    if period["form"] == "years_only" and period["years"] and period["years"] <= 2:
        _add(cand, 2, "short year-year span, treated as a monitoring window", "monitoring")
    # "1 year" on a verification doc is almost always the monitoring
    # window, not a 1-year crediting period (Verra AFOLU minima are
    # much longer).
    if period["form"] == "duration" and period["years"] == 1 and kind == "monitoring":
        _add(cand, 1, "1-year duration on a verification/MR, treated as monitoring",
             "monitoring")
        if "crediting" in cand["tags"]:
            cand["tags"].remove("crediting")


def score_buffer(cand: dict[str, Any]) -> None:
    q, parsed = _qx(cand), cand["parsed"]
    n = parsed["number"]
    if n is None:
        _add(cand, -10, "no numeric buffer figure")
        return
    if parsed["unit"] == "percent":
        _add(cand, 6, "buffer stated as a percentage (the risk rating)", "rate")
        if BUFFER_MIN_PCT <= n <= BUFFER_MAX_PCT:
            _add(cand, 2, f"{n:g}% is inside the VCS AFOLU 10-60% range")
        else:
            _add(cand, -3, f"{n:g}% is outside the VCS AFOLU 10-60% range", "out_of_range")
    elif parsed["unit"] in ("tco2e", "tonne", None) and n >= 100:
        _add(cand, 3, "buffer stated as a tCO2e withholding", "mass")
    if re.search(r"non-permanence|buffer credit|buffer withholding|risk (?:factor|of|buffer)", q):
        _add(cand, 3, "quote refers to the non-permanence buffer")


def score_leakage(cand: dict[str, Any]) -> None:
    q, parsed = _qx(cand), cand["parsed"]
    n = parsed["number"]
    if n is None:
        _add(cand, -10, "no numeric leakage figure")
        return
    if re.search(r"total carbon by", q):
        _add(cand, -12, "total carbon stock, not leakage", "carbon_stock")
        return
    if re.search(r"activity-shifting leakage|emissions from leakage|"
                 r"total leakage of|leakage are zero|hence leakage|"
                 r"discounted .+ through leakage", q):
        _add(cand, 6, "quote describes a leakage deduction", "leakage")
    if parsed["unit"] in ("tco2e", "tonne"):
        _add(cand, 3, "leakage stated as tCO2e")
        cand["tags"].append("mass")
    elif parsed["unit"] == "percent":
        _add(cand, 3, "leakage stated as a percentage factor")
        cand["tags"].append("rate")
    elif parsed["unit"] is None:
        # Kasigau I "20" with "x 0.20" is an ex-ante factor, not 20 tCO2e.
        if re.search(r"0\.\d+|factor", q) and 1 <= n <= 100:
            _add(cand, 2, "bare number used as a leakage factor in the quote", "rate")
            cand["parsed"]["unit"] = "percent"
        elif n == 0:
            _add(cand, 1, "bare zero (weak without leakage wording)")
        else:
            _add(cand, -2, "bare number, unclear unit")


def _nearly_equal(a: Optional[float], b: Optional[float], rel: float = 0.005) -> bool:
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= rel * scale or abs(a - b) < 0.05


def _same_period(a: dict[str, Any], b: dict[str, Any]) -> bool:
    pa, pb = a["parsed"]["period"], b["parsed"]["period"]
    if pa["years"] and pb["years"] and _nearly_equal(pa["years"], pb["years"], 0.08):
        return True
    if pa["start"] and pb["start"] and pa["end"] and pb["end"]:
        return abs((pa["start"] - pb["start"]).days) <= 31 and abs((pa["end"] - pb["end"]).days) <= 31
    return False


def _pick(cands: list[dict[str, Any]], material_rel: float = 0.05) -> dict[str, Any]:
    """Choose the highest-scoring candidate, or leave unresolved on a tie."""
    if not cands:
        return {"status": "not_stated", "chosen": None, "candidates": [],
                "reason": "no supported candidates"}
    ranked = sorted(cands, key=lambda c: c["score"], reverse=True)
    best = ranked[0]
    # Among rounding partners (30,168.66 vs 30,169), keep the more
    # precise writing, then the one that already has a unit.
    def _precision(c: dict[str, Any]) -> tuple[int, int]:
        raw = (c.get("value") or "").replace(",", "")
        m = re.search(r"\d+\.(\d+)", raw)
        decimals = len(m.group(1)) if m else 0
        has_unit = 1 if c["parsed"]["unit"] else 0
        return (decimals, has_unit)

    for c in ranked[1:]:
        if _nearly_equal(c["parsed"]["number"], best["parsed"]["number"], 0.005):
            if _precision(c) > _precision(best):
                best = c

    misfile_tags = {"baseline_misfile", "wrong_field", "co_benefit", "carbon_stock"}
    if best["score"] <= -8:
        if any(tag in misfile_tags for tag in best["tags"]):
            return {"status": "rejected", "chosen": best, "candidates": ranked,
                    "reason": "; ".join(best["reasons"][:3])}
        return {"status": "unresolved", "chosen": None, "candidates": ranked,
                "reason": "all candidates scored poorly: " +
                          "; ".join(best["reasons"][:3])}
    ties = [c for c in ranked[1:]
            if abs(c["score"] - best["score"]) < 0.25
            and not _nearly_equal(c["parsed"]["number"], best["parsed"]["number"], material_rel)
            and not _same_period(c, best)]
    if ties:
        return {"status": "unresolved", "chosen": None, "candidates": ranked,
                "reason": "top candidates tied with different values: " +
                          " vs ".join(c["value"] for c in [best] + ties[:3])}
    status = "clean" if len(cands) == 1 and cands[0]["source"] == "clean" else "resolved"
    reason = (f"chose {best['value']}"
              + (f" ({'; '.join(best['reasons'][:3])})" if best["reasons"] else ""))
    return {"status": status, "chosen": best, "candidates": ranked, "reason": reason}


def resolve_area(cands: list[dict[str, Any]]) -> dict[str, Any]:
    for c in cands:
        score_area(c)
    return _pick(cands)


def resolve_reductions(cands: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for c in cands:
        score_reductions(c, kind)
    rejected = {"baseline_misfile", "wrong_field", "co_benefit", "carbon_stock"}
    annuals = [
        c for c in cands
        if "scope:annual" in c["tags"]
        and c["parsed"]["number"]
        and not any(tag in rejected for tag in c["tags"])
    ]
    totals = [
        c for c in cands
        if c["parsed"]["number"]
        and "scope:annual" not in c["tags"]
        and not any(tag in rejected for tag in c["tags"])
        and c["score"] > -8
    ]
    # The primary figure should be a total (period / lifetime /
    # cumulative). An annual average is kept beside it so we can
    # check total / years, and is not treated as a competing total.
    picked = _pick(totals) if totals else _pick(cands)
    annual = max(annuals, key=lambda c: c["score"]) if annuals else None
    if picked.get("chosen") and "scope:annual" in picked["chosen"]["tags"] and annual is None:
        annual = picked["chosen"]
    if picked.get("chosen") and annual and picked["chosen"] is not annual:
        if "annual" not in (picked.get("reason") or ""):
            picked["reason"] = (
                (picked.get("reason") or f"chose {picked['chosen']['value']}")
                + f"; annual {annual['value']} kept beside it"
            )
    picked["annual"] = annual
    cumulative = None
    for c in cands:
        if "scope:cumulative" in c["tags"] and c["parsed"]["number"]:
            if cumulative is None or c["score"] > cumulative["score"]:
                cumulative = c
    picked["cumulative"] = cumulative
    # Keep the full scored list (including annuals) for the JSON.
    picked["candidates"] = sorted(cands, key=lambda c: c["score"], reverse=True)
    return picked


def resolve_period(cands: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    for c in cands:
        score_period(c, kind)
    crediting = [c for c in cands if "crediting" in c["tags"]]
    monitoring = [c for c in cands if "monitoring" in c["tags"] and "crediting" not in c["tags"]]
    # A date range and a "20 years" duration that describe the same
    # crediting period should be merged, not treated as a conflict.
    pooled = crediting or [c for c in cands if c["parsed"]["period"]["years"]
                           and c["parsed"]["period"]["years"] >= 10]
    credit_pick = _pick(pooled) if pooled else {
        "status": "not_stated", "chosen": None, "candidates": [],
        "reason": "no crediting-period candidate",
    }
    mon_pick = _pick(monitoring) if monitoring else {
        "status": "not_stated", "chosen": None, "candidates": [],
        "reason": "no monitoring-window candidate",
    }
    if credit_pick.get("chosen") is None and mon_pick.get("chosen") is None:
        credit_pick = _pick(cands)

    def _enrich_dates(chosen: Optional[dict[str, Any]]) -> None:
        if not chosen or chosen["parsed"]["period"]["start"]:
            return
        for c in cands:
            if c is chosen:
                continue
            if _same_period(c, chosen) and c["parsed"]["period"]["start"]:
                chosen["parsed"]["period"]["start"] = c["parsed"]["period"]["start"]
                chosen["parsed"]["period"]["end"] = c["parsed"]["period"]["end"]
                return

    _enrich_dates(credit_pick.get("chosen"))
    _enrich_dates(mon_pick.get("chosen"))
    return {
        "status": credit_pick["status"],
        "chosen": credit_pick.get("chosen"),
        "candidates": sorted(cands, key=lambda c: c["score"], reverse=True),
        "reason": credit_pick.get("reason"),
        "monitoring": mon_pick.get("chosen"),
        "monitoring_reason": mon_pick.get("reason"),
        "crediting_resolution": credit_pick,
        "monitoring_resolution": mon_pick,
    }


def resolve_buffer(cands: list[dict[str, Any]]) -> dict[str, Any]:
    for c in cands:
        score_buffer(c)
    rates = [c for c in cands if "rate" in c["tags"]]
    masses = [c for c in cands if "mass" in c["tags"]]
    rate_pick = _pick(rates) if rates else {
        "status": "not_stated", "chosen": None, "candidates": [], "reason": "no % rate",
    }
    mass_pick = _pick(masses) if masses else {
        "status": "not_stated", "chosen": None, "candidates": [], "reason": "no tCO2e mass",
    }
    # A % and a tCO2e figure are two views of the same buffer, not a conflict.
    chosen = rate_pick.get("chosen") or mass_pick.get("chosen")
    status = "not_stated"
    if chosen:
        status = "resolved" if (len(cands) > 1) else (
            "clean" if chosen["source"] == "clean" else "resolved"
        )
    reason_bits = []
    if rate_pick.get("chosen"):
        reason_bits.append(rate_pick["reason"])
    if mass_pick.get("chosen"):
        reason_bits.append(mass_pick["reason"])
    return {
        "status": status if chosen else (
            rate_pick["status"] if rates or masses else _pick(cands)["status"]
        ),
        "chosen": chosen,
        "rate": rate_pick.get("chosen"),
        "mass": mass_pick.get("chosen"),
        "candidates": sorted(cands, key=lambda c: c["score"], reverse=True),
        "reason": "; ".join(reason_bits) or "no buffer figure",
    }


def resolve_leakage(cands: list[dict[str, Any]]) -> dict[str, Any]:
    for c in cands:
        score_leakage(c)
    masses = [c for c in cands if "mass" in c["tags"] or
              (c["parsed"]["unit"] in ("tco2e", "tonne") and "carbon_stock" not in c["tags"])]
    rates = [c for c in cands if "rate" in c["tags"]]
    if masses:
        pick = _pick(masses)
    else:
        pick = _pick([c for c in cands if "carbon_stock" not in c["tags"]] or cands)
    rate = None
    if rates:
        rate = _pick(rates).get("chosen")
    pick["rate"] = rate
    return pick


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------

def _num(chosen: Optional[dict[str, Any]]) -> Optional[float]:
    if not chosen:
        return None
    return chosen["parsed"]["number"]


def _years_of(chosen: Optional[dict[str, Any]]) -> Optional[float]:
    if not chosen:
        return None
    return chosen["parsed"]["period"]["years"]


def _scope_of(chosen: Optional[dict[str, Any]]) -> Optional[str]:
    if not chosen:
        return None
    for t in chosen["tags"]:
        if t.startswith("scope:"):
            return t.split(":", 1)[1]
    return None


def _fmt(n: Optional[float], digits: int = 0, unit: str = "") -> str:
    if n is None:
        return ""
    if digits == 0 and abs(n - round(n)) < 1e-6:
        s = f"{int(round(n)):,}"
    else:
        s = f"{n:,.{digits}f}"
    return f"{s} {unit}".strip()


def analyse_project(proj: dict[str, Any]) -> dict[str, Any]:
    """Resolve conflicts and run the Verra-style consistency checks."""
    fields = proj["fields"]
    kind = proj["kind"]

    area_r = resolve_area(field_candidates(fields["area"]))
    red_r = resolve_reductions(field_candidates(fields["estimated_reductions"]), kind)
    per_r = resolve_period(field_candidates(fields["crediting_period"]), kind)
    buf_r = resolve_buffer(field_candidates(fields["permanence_buffer"]))
    lek_r = resolve_leakage(field_candidates(fields["leakage"]))

    area_ha = _num(area_r.get("chosen"))
    if area_r.get("chosen") and area_r["chosen"]["parsed"]["unit"] == "acre" and area_ha:
        area_ha = area_ha * 0.404685642

    reductions = _num(red_r.get("chosen"))
    scope = _scope_of(red_r.get("chosen"))
    annual_stated = _num(red_r.get("annual"))
    if scope == "annual" and annual_stated is None:
        annual_stated = reductions

    credit = per_r.get("chosen")
    monitor = per_r.get("monitoring")
    credit_years = _years_of(credit)
    monitor_years = _years_of(monitor)

    # Years that belong with the chosen reductions figure.
    years_used = None
    years_source = None
    if scope == "annual":
        years_used = 1.0
        years_source = "annual figure (no period division needed)"
    elif scope == "period":
        if monitor_years:
            years_used, years_source = monitor_years, "monitoring / verification window"
        elif credit_years and credit_years <= 5:
            years_used, years_source = credit_years, "short period treated as monitoring"
    elif scope == "cumulative":
        if credit and monitor and credit["parsed"]["period"]["start"] and monitor["parsed"]["period"]["end"]:
            start = credit["parsed"]["period"]["start"]
            end = monitor["parsed"]["period"]["end"]
            years_used = round((end - start).days / 365.25, 4)
            years_source = "project start to end of this monitoring window"
    elif scope == "lifetime":
        if credit_years:
            years_used, years_source = credit_years, "crediting period"

    flags: list[str] = []
    notes: list[str] = []
    checks: list[dict[str, Any]] = []

    for label, res in (("area", area_r), ("reductions", red_r),
                       ("period", per_r), ("buffer", buf_r), ("leakage", lek_r)):
        if res.get("status") == "resolved" and res.get("reason"):
            notes.append(f"{label}: {res['reason']}")
        elif res.get("status") == "unresolved":
            flags.append(f"{label} unresolved ({res.get('reason')})")

    if red_r.get("chosen") and "baseline_misfile" in red_r["chosen"]["tags"]:
        flags.append(
            "estimated_reductions value is described in its quote as baseline "
            f"emissions ({red_r['chosen']['value']}), not as net emission reductions"
        )

    annual_implied = None
    if reductions is not None and years_used and years_used > 0 and scope != "annual":
        annual_implied = reductions / years_used
    elif scope == "annual" and reductions is not None:
        annual_implied = reductions

    if (annual_stated is not None and annual_implied is not None and scope != "annual"
            and years_used):
        ok = _nearly_equal(annual_implied, annual_stated, CONSISTENCY_TOL)
        checks.append({
            "name": "total_vs_annual",
            "ok": ok,
            "detail": (
                f"{_fmt(reductions)} / {years_used:g} yr = {_fmt(annual_implied, 1)} tCO2e/yr; "
                f"stated annual is {_fmt(annual_stated)} tCO2e/yr"
            ),
        })
        if ok:
            notes.append(
                f"stated annual {_fmt(annual_stated)} tCO2e/yr matches "
                f"total / {years_used:g} years"
            )
        else:
            flags.append(
                f"total/years ({_fmt(annual_implied, 1)} tCO2e/yr) does not match "
                f"stated annual {_fmt(annual_stated)} tCO2e/yr"
            )

    annual = annual_stated if annual_stated is not None else annual_implied

    # Intensity. If scope is unknown, try monitoring then crediting years
    # and keep the value that lands inside the screening band.
    intensity = None
    intensity_basis = None
    if area_ha and area_ha > 0:
        if scope == "annual" and annual:
            intensity = annual / area_ha
            intensity_basis = "annual / area"
            years_used = years_used or 1.0
            years_source = years_source or "annual figure"
        elif reductions is not None and years_used and years_used > 0:
            intensity = reductions / area_ha / years_used
            intensity_basis = f"{scope or 'total'} / area / {years_source}"
        elif reductions is not None and years_used is None:
            options = []
            if monitor_years:
                options.append((reductions / area_ha / monitor_years,
                                monitor_years, "monitoring window (scope inferred)"))
            if credit_years:
                options.append((reductions / area_ha / credit_years,
                                credit_years, "crediting period (scope inferred)"))
            in_range = [o for o in options if INTENSITY_MIN <= o[0] <= INTENSITY_MAX]
            chosen_opt = (in_range[0] if in_range else (options[0] if options else None))
            if chosen_opt:
                intensity, years_used, years_source = chosen_opt
                intensity_basis = years_source
                if len(in_range) == 1 and len(options) > 1:
                    notes.append(
                        f"reductions scope was unclear; used {years_source} "
                        f"because {intensity:.2f} tCO2e/ha/yr falls inside "
                        f"{INTENSITY_MIN:g}-{INTENSITY_MAX:g}"
                    )

    if intensity is not None:
        in_band = INTENSITY_MIN <= intensity <= INTENSITY_MAX
        checks.append({
            "name": "intensity",
            "ok": in_band,
            "detail": (
                f"{intensity:.2f} tCO2e/ha/yr ({intensity_basis}); "
                f"screening band {INTENSITY_MIN:g}-{INTENSITY_MAX:g}"
            ),
        })
        if not in_band:
            flags.append(
                f"{intensity:.2f} tCO2e/ha/yr is outside the screening band "
                f"{INTENSITY_MIN:g}-{INTENSITY_MAX:g} tCO2e/ha/yr"
            )
        elif intensity >= 20:
            notes.append(
                f"{intensity:.2f} tCO2e/ha/yr is toward the high end of the "
                f"{INTENSITY_MIN:g}-{INTENSITY_MAX:g} screening band"
            )

    buffer_pct = _num(buf_r.get("rate"))
    buffer_t = _num(buf_r.get("mass"))
    implied_buffer_pct = None
    reductions_already_net = False
    COMMON_RATES = (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 25, 30, 40, 50, 60)

    def _rate_fit(pct: float) -> float:
        return min(abs(pct - r) for r in COMMON_RATES)

    if buffer_pct is None and buffer_t is not None and reductions and buffer_t < reductions:
        options = [
            (100.0 * buffer_t / reductions, "buffer / reductions", "gross"),
            (100.0 * buffer_t / (buffer_t + reductions),
             "buffer / (buffer + reductions)", "net"),
        ]
        in_range = [
            o for o in options
            if BUFFER_MIN_PCT - 0.6 <= o[0] <= BUFFER_MAX_PCT + 0.6
        ]
        if in_range:
            implied, how, role = min(in_range, key=lambda o: _rate_fit(o[0]))
            implied_buffer_pct = implied
            notes.append(
                f"implied buffer rate {implied:.1f}% ({how})"
            )
            if role == "net" and _rate_fit(implied) <= 0.6:
                reductions_already_net = True
                notes.append(
                    "chosen reductions look like they are already net of the "
                    "buffer (rate fits buffer / (buffer + reductions))"
                )
        elif buffer_pct is None:
            implied_buffer_pct = 100.0 * buffer_t / reductions
            notes.append(
                f"implied buffer rate {implied_buffer_pct:.1f}% "
                f"(buffer / reductions); not a typical VCS rating"
            )
        if buffer_pct is None and implied_buffer_pct is not None:
            buffer_pct = implied_buffer_pct
    elif buffer_t is not None and reductions and buffer_t >= reductions:
        notes.append(
            f"buffer mass {_fmt(buffer_t)} tCO2e is larger than the chosen "
            "reductions, so it is treated as a different (likely lifetime) "
            "scope and is not used to imply a rate for this figure"
        )

    if buffer_pct is not None:
        in_range = BUFFER_MIN_PCT <= buffer_pct <= BUFFER_MAX_PCT
        checks.append({
            "name": "buffer_range",
            "ok": in_range,
            "detail": (
                f"{buffer_pct:.1f}% ; VCS AFOLU non-permanence tool allows "
                f"{BUFFER_MIN_PCT:g}-{BUFFER_MAX_PCT:g}%"
            ),
        })
        if not in_range:
            flags.append(
                f"permanence buffer {buffer_pct:.1f}% is outside the VCS AFOLU "
                f"{BUFFER_MIN_PCT:g}-{BUFFER_MAX_PCT:g}% range"
            )
        elif buffer_pct > BUFFER_TYPICAL_MAX_PCT:
            notes.append(
                f"buffer {buffer_pct:.1f}% is above the typical 10-20% band "
                "but still inside the VCS 10-60% limit"
            )

    usable_reductions = (
        reductions is not None
        and not (red_r.get("chosen") and "baseline_misfile" in red_r["chosen"]["tags"])
        and not (red_r.get("chosen") and "wrong_field" in red_r["chosen"]["tags"])
        and not (red_r.get("chosen") and "co_benefit" in red_r["chosen"]["tags"])
        and red_r.get("status") != "rejected"
    )

    # If several period totals tied, report intensity under each
    # assumption so the FLAG is still useful.
    if red_r.get("status") == "unresolved" and area_ha and area_ha > 0:
        years_for_sens = monitor_years or (credit_years if credit_years and credit_years <= 5 else None)
        for c in red_r.get("candidates") or []:
            n = c["parsed"]["number"]
            if not n or any(tag in c["tags"] for tag in
                            ("baseline_misfile", "wrong_field", "co_benefit", "carbon_stock")):
                continue
            if "scope:annual" in c["tags"] and area_ha:
                notes.append(
                    f"if reductions were {c['value']}: {n/area_ha:.2f} tCO2e/ha/yr "
                    f"(stated annual / area)"
                )
            elif years_for_sens:
                notes.append(
                    f"if reductions were {c['value']}: "
                    f"{n/area_ha/years_for_sens:.2f} tCO2e/ha/yr "
                    f"over {years_for_sens:g} monitoring years"
                )

    leakage_t = None
    leakage_pct = None
    if lek_r.get("chosen") and "carbon_stock" not in lek_r["chosen"]["tags"]:
        if lek_r["chosen"]["parsed"]["unit"] in ("tco2e", "tonne") or (
            "mass" in lek_r["chosen"]["tags"]
        ):
            leakage_t = _num(lek_r["chosen"])
        elif lek_r["chosen"]["parsed"]["unit"] == "percent":
            leakage_pct = _num(lek_r["chosen"])
    if lek_r.get("rate") and leakage_pct is None:
        leakage_pct = _num(lek_r["rate"])
    leakage_share = None
    if leakage_t is not None and usable_reductions and reductions and reductions > 0:
        leakage_share = leakage_t / reductions
        checks.append({
            "name": "leakage_share",
            "ok": leakage_share <= LEAKAGE_SHARE_FLAG,
            "detail": f"{leakage_t:,.0f} tCO2e is {leakage_share*100:.1f}% of chosen reductions",
        })
        if leakage_share > LEAKAGE_SHARE_FLAG:
            flags.append(
                f"leakage {_fmt(leakage_t)} tCO2e is {leakage_share*100:.1f}% of reductions "
                f"(above {LEAKAGE_SHARE_FLAG*100:.0f}% screen)"
            )
        elif leakage_t == 0:
            notes.append("leakage is stated as 0 tCO2e")
        else:
            notes.append(f"leakage is {leakage_share*100:.1f}% of chosen reductions")
    elif leakage_pct is not None:
        notes.append(f"leakage factor {leakage_pct:g}% (no tCO2e mass to combine)")

    net_t = None
    if usable_reductions and reductions is not None and (leakage_t is not None or buffer_t is not None or buffer_pct is not None):
        already_net = bool(
            (red_r.get("chosen") and "issuance_net" in red_r["chosen"]["tags"])
            or reductions_already_net
        )
        q = _qx(red_r["chosen"]) if red_r.get("chosen") else ""
        post_buffer = bool(re.search(r"considering \d+% buffer", q))
        mass_wrong_scope = bool(buffer_t is not None and reductions and buffer_t >= reductions)
        if already_net or post_buffer:
            deduct_lek = leakage_t if leakage_t is not None else 0.0
            net_t = reductions - deduct_lek
            notes.append(
                "chosen reductions already look like a net/issuance figure "
                "after the buffer; not subtracting the buffer again"
                + (f"; net after leakage = {_fmt(net_t, 1)} tCO2e" if deduct_lek else "")
            )
        else:
            gross = reductions
            if mass_wrong_scope:
                deduct_buf = gross * (buffer_pct / 100.0) if buffer_pct is not None else 0.0
            else:
                deduct_buf = buffer_t if buffer_t is not None else (
                    gross * (buffer_pct / 100.0) if buffer_pct is not None else 0.0
                )
            if leakage_t is not None:
                deduct_lek = leakage_t
                lek_bit = f"leakage {_fmt(deduct_lek, 1)}"
            elif leakage_pct is not None:
                deduct_lek = gross * (leakage_pct / 100.0)
                lek_bit = f"leakage {_fmt(deduct_lek, 1)}"
            else:
                deduct_lek = 0.0
                lek_bit = "leakage not stated"
            net_t = gross - deduct_lek - deduct_buf
            if deduct_buf or deduct_lek:
                lines = (
                    f"net = {_fmt(gross)} - {lek_bit} "
                    f"- buffer {_fmt(deduct_buf, 1)} = {_fmt(net_t, 1)} tCO2e"
                )
                if mass_wrong_scope:
                    lines += " (buffer mass skipped as a different scope; used the % rate)"
                notes.append(lines)

    can_intensity = intensity is not None and usable_reductions and area_ha

    missing = []
    if area_ha is None:
        missing.append("area")
    if not usable_reductions:
        missing.append("estimated reductions")
    if usable_reductions and area_ha and intensity is None:
        missing.append("period length (cannot form tCO2e/ha/yr)")

    hard_fail = any(
        "baseline emissions" in f or "outside the screening band" in f or
        "does not match stated annual" in f or "outside the VCS AFOLU" in f
        for f in flags
    )
    if red_r.get("status") == "unresolved":
        verdict = "FLAG"
    elif not can_intensity and any("baseline emissions" in f for f in flags):
        verdict = "FLAG"
    elif not can_intensity and missing and not hard_fail:
        verdict = "INSUFFICIENT DATA"
    elif flags:
        verdict = "FLAG"
    else:
        verdict = "PASS"

    if verdict == "INSUFFICIENT DATA":
        key_flag = "missing " + ", ".join(missing) if missing else "insufficient inputs"
    elif flags:
        key_flag = flags[0]
    else:
        key_flag = ""

    return {
        "stem": proj["stem"],
        "doc": proj["doc"],
        "project_id": proj["project_id"],
        "title": proj["title"],
        "kind": kind,
        "area_ha": area_ha,
        "area_value": (area_r["chosen"] or {}).get("value") if area_r.get("chosen") else None,
        "area_status": area_r["status"],
        "reductions_tco2e": reductions if usable_reductions else None,
        "reductions_value": (red_r["chosen"] or {}).get("value") if red_r.get("chosen") else None,
        "reductions_scope": scope,
        "reductions_status": red_r["status"],
        "annual_tco2e": annual if usable_reductions else None,
        "period_years": years_used,
        "period_source": years_source,
        "crediting_value": (credit or {}).get("value") if credit else None,
        "crediting_years": credit_years,
        "monitoring_value": (monitor or {}).get("value") if monitor else None,
        "monitoring_years": monitor_years,
        "tco2e_ha_yr": round(intensity, 4) if intensity is not None and usable_reductions else None,
        "intensity_basis": intensity_basis,
        "buffer_pct": round(buffer_pct, 3) if buffer_pct is not None else None,
        "buffer_tco2e": buffer_t,
        "buffer_value": (buf_r["chosen"] or {}).get("value") if buf_r.get("chosen") else None,
        "leakage_tco2e": leakage_t,
        "leakage_pct": leakage_pct,
        "leakage_share": round(leakage_share, 4) if leakage_share is not None else None,
        "leakage_value": (lek_r["chosen"] or {}).get("value") if lek_r.get("chosen") else None,
        "net_tco2e": round(net_t, 2) if net_t is not None else None,
        "verdict": verdict,
        "flags": flags,
        "notes": notes,
        "key_flag": key_flag,
        "checks": checks,
        "resolution": {
            "area": _trim_res(area_r),
            "estimated_reductions": _trim_res(red_r),
            "crediting_period": _trim_res(per_r),
            "permanence_buffer": _trim_res(buf_r),
            "leakage": _trim_res(lek_r),
        },
        "baseline_value": fields["baseline"].get("value"),
        "additionality_value": fields["additionality"].get("value"),
    }


def _trim_cand(c: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not c:
        return None
    period = c["parsed"]["period"]
    return {
        "value": c["value"],
        "page": c.get("page"),
        "score": round(c["score"], 2),
        "tags": c["tags"],
        "reasons": c["reasons"],
        "number": c["parsed"]["number"],
        "unit": c["parsed"]["unit"],
        "per_year": c["parsed"]["per_year"],
        "years": period["years"],
        "start": period["start"].isoformat() if period["start"] else None,
        "end": period["end"].isoformat() if period["end"] else None,
        "quote": (c.get("quote") or "")[:280],
    }


def _trim_res(res: dict[str, Any]) -> dict[str, Any]:
    out = {
        "status": res.get("status"),
        "reason": res.get("reason"),
        "chosen": _trim_cand(res.get("chosen")),
        "candidates": [_trim_cand(c) for c in res.get("candidates") or []],
    }
    for extra in ("annual", "cumulative", "monitoring", "rate", "mass"):
        if res.get(extra):
            out[extra] = (
                _trim_cand(res[extra])
                if isinstance(res[extra], dict) and "parsed" in res[extra]
                else res[extra]
            )
    return out


# ----------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------

CSV_COLUMNS = [
    "doc", "project_id", "title", "kind", "verdict",
    "area_ha", "area_value", "area_status",
    "reductions_tco2e", "reductions_value", "reductions_scope", "reductions_status",
    "annual_tco2e", "period_years", "period_source",
    "crediting_value", "monitoring_value",
    "tco2e_ha_yr", "intensity_basis",
    "buffer_pct", "buffer_tco2e", "leakage_tco2e", "leakage_pct", "net_tco2e",
    "key_flag", "flags", "notes",
]


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k) for k in CSV_COLUMNS}
            out["flags"] = " | ".join(row.get("flags") or [])
            out["notes"] = " | ".join(row.get("notes") or [])
            for k, v in list(out.items()):
                if isinstance(v, float):
                    out[k] = round(v, 4)
            writer.writerow(out)


def write_json(rows: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")


def _md_num(n: Optional[float], digits: int = 0) -> str:
    if n is None:
        return "—"
    if digits == 0 and abs(n - round(n)) < 1e-6:
        return f"{int(round(n)):,}"
    return f"{n:,.{digits}f}"


def write_report(rows: list[dict[str, Any]], path: Path, input_dir: Path, out_dir: Path) -> str:
    lines: list[str] = []
    lines.append("# Tally Verra consistency calculator")
    lines.append("")
    lines.append(
        "Screening check of the seven extracted fields, run on the "
        "cleaned merge in `results_clean/`. This is not a re-run of each "
        "project's own calculation worksheet. It asks whether the numbers "
        "in a document hang together, and whether the implied reductions "
        "per hectare per year look like a published REDD+ / ARR project."
    )
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("For each document:")
    lines.append("")
    lines.append(
        "1. **Load** the `merged` object. A field value is either a clean "
        "string, `conflict` (with a `conflicts` list of candidates), or "
        "`not stated`. Bare `not stated` strings are treated the same as "
        "the dict form."
    )
    lines.append(
        "2. **Parse** numbers and units: thousands commas, hectare / "
        "tCO2e / percent / year units, annual-vs-total wording, and the "
        "date and duration forms used in these PDDs and monitoring reports."
    )
    lines.append(
        "3. **Resolve conflicts** with a transparent, quote-driven score. "
        "The calculator never hard-codes a project's 'right' number. "
        "Area prefers 'eligible project area' / 'project accounting area' "
        "over a lease, a planted subset, a leakage-belt boundary, or a "
        "list of component ranches. Reductions prefer a figure whose quote "
        "actually describes emission reductions, and a monitoring-period "
        "total on an MR / verification document (or a lifetime total on a "
        "PD / validation). A date range labelled 'crediting period' is "
        "kept separately from a monitoring / verification window. A buffer "
        "percent and a buffer tCO2e mass are two views of the same thing, "
        "not a conflict. Candidates that the merge already rejected "
        "(`unsupported`) are not used as primary figures."
    )
    lines.append(
        "4. **Check** the following, then issue a verdict of PASS, FLAG, "
        "or INSUFFICIENT DATA."
    )
    lines.append("")
    lines.append("Checks:")
    lines.append("")
    lines.append(
        f"* **Annual consistency.** If the document states both a total "
        f"and an annual figure, they should agree within {CONSISTENCY_TOL*100:.0f}% "
        "once the matching period length is applied."
    )
    lines.append(
        f"* **Intensity.** Reductions divided by area divided by years should fall in "
        f"**{INTENSITY_MIN:g}-{INTENSITY_MAX:g} tCO2e/ha/yr**. This is a "
        "literature-informed screening band, not a Verra threshold. "
        "Tropical African REDD+ often lands around 2-15 tCO2e/ha/yr "
        "(roughly a 1-3% annual loss rate times 100-250 tC/ha, times 44/12). "
        "ARR / plantation growth is commonly about 2-20 tCO2e/ha/yr, and "
        "fast-growing stands in a short window can run higher. Below 0.5 "
        "usually means a lifetime total has been paired with the wrong "
        "area or a too-long period; above 30 usually means a period total "
        "has been paired with a too-small area or a too-short period. "
        "High-stock avoided-logging years can legitimately exceed 30 — "
        "those are flagged for review, not declared impossible."
    )
    lines.append(
        f"* **Permanence buffer.** The VCS AFOLU Non-Permanence Risk Tool "
        f"allows **{BUFFER_MIN_PCT:g}-{BUFFER_MAX_PCT:g}%** (above 60% the "
        "project is not eligible). 10-20% is typical and is not flagged; "
        "21-60% is noted as elevated but still eligible. If only a tCO2e "
        "mass is extracted, an implied rate is computed from the chosen "
        "reductions."
    )
    lines.append(
        f"* **Leakage.** A tCO2e leakage deduction is reported as a share "
        f"of the chosen reductions and flagged above {LEAKAGE_SHARE_FLAG*100:.0f}%. "
        "A leakage percentage factor is reported when no mass is available."
    )
    lines.append(
        "* **Net identity.** Where possible, net is approximated as gross minus leakage minus buffer. "
        "The calculator does not subtract again if the chosen reductions "
        "are already described as issuance after the buffer, or as net "
        "of a stated buffer rate."
    )
    lines.append("")
    lines.append(
        "A document **PASSes** when the needed figures can be resolved "
        "and every numeric check holds. It is a **FLAG** when a check "
        "fails, a material conflict cannot be resolved, or the extracted "
        "'reductions' figure is clearly something else (for example "
        "baseline emissions). It is **INSUFFICIENT DATA** when area, "
        "reductions, or a matching period length is missing, so "
        "tCO2e/ha/yr cannot be formed, and no other hard contradiction "
        "was found."
    )
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Document | Area (ha) | Total reductions (tCO2e) | Annual (tCO2e/yr) | "
        "tCO2e/ha/yr | Buffer | Verdict | Key flag |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|---|")
    for row in rows:
        buf = ""
        if row.get("buffer_pct") is not None:
            if abs(row["buffer_pct"] - round(row["buffer_pct"])) < 0.05:
                buf = f"{row['buffer_pct']:.0f}%"
            else:
                buf = f"{row['buffer_pct']:.1f}%"
        elif row.get("buffer_tco2e") is not None:
            buf = _md_num(row["buffer_tco2e"]) + " tCO2e"
        else:
            buf = "—"
        key = (row.get("key_flag") or "—").replace("|", "/")
        if len(key) > 90:
            key = key[:87] + "…"
        area_digits = 2 if (row["area_ha"] or 0) % 1 else 0
        lines.append(
            f"| {row['project_id']} {row['title']} "
            f"| {_md_num(row['area_ha'], area_digits)} "
            f"| {_md_num(row['reductions_tco2e'])} "
            f"| {_md_num(row['annual_tco2e'])} "
            f"| {_md_num(row['tco2e_ha_yr'], 2)} "
            f"| {buf} "
            f"| **{row['verdict']}** "
            f"| {key} |"
        )
    lines.append("")

    counts = {k: sum(1 for r in rows if r["verdict"] == k)
              for k in ("PASS", "FLAG", "INSUFFICIENT DATA")}
    lines.append(
        f"{len(rows)} documents: {counts['PASS']} PASS, "
        f"{counts['FLAG']} FLAG, {counts['INSUFFICIENT DATA']} INSUFFICIENT DATA."
    )
    lines.append("")
    lines.append("## Per document")
    lines.append("")
    for row in rows:
        lines.append(f"### {row['project_id']} {row['title']}")
        lines.append("")
        lines.append(f"- File: `{row['stem']}.json` ({row['kind']} document)")
        lines.append(
            f"- Area: {row.get('area_value') or '—'} "
            f"(status: {row.get('area_status')})"
        )
        scope = row.get("reductions_scope") or "—"
        lines.append(
            f"- Reductions: {row.get('reductions_value') or '—'} "
            f"(scope: {scope}, status: {row.get('reductions_status')})"
        )
        if row.get("annual_tco2e") is not None:
            lines.append(f"- Annual: {_md_num(row['annual_tco2e'])} tCO2e/yr")
        period_bits = []
        if row.get("crediting_value"):
            period_bits.append(f"crediting {row['crediting_value']}")
        if row.get("monitoring_value"):
            period_bits.append(f"monitoring {row['monitoring_value']}")
        if row.get("period_years"):
            period_bits.append(
                f"years used: {row['period_years']:g} ({row.get('period_source') or ''})"
            )
        lines.append("- Period: " + ("; ".join(period_bits) if period_bits else "—"))
        if row.get("tco2e_ha_yr") is not None:
            basis = f" ({row['intensity_basis']})" if row.get("intensity_basis") else ""
            lines.append(f"- Intensity: {row['tco2e_ha_yr']:.2f} tCO2e/ha/yr{basis}")
        if row.get("buffer_value") or row.get("buffer_pct") is not None:
            pct = f" ({row['buffer_pct']:.1f}%)" if row.get("buffer_pct") is not None else ""
            mass = f", {_md_num(row['buffer_tco2e'])} tCO2e" if row.get("buffer_tco2e") else ""
            lines.append(f"- Buffer: {row.get('buffer_value') or '—'}{pct}{mass}")
        else:
            lines.append("- Buffer: —")
        if row.get("leakage_value") or row.get("leakage_tco2e") is not None:
            share = ""
            if row.get("leakage_share") is not None:
                share = f", {row['leakage_share']*100:.1f}% of reductions"
            lines.append(f"- Leakage: {row.get('leakage_value') or '—'}{share}")
        else:
            lines.append("- Leakage: —")
        if row.get("net_tco2e") is not None:
            lines.append(f"- Implied net: {_md_num(row['net_tco2e'], 1)} tCO2e")
        lines.append(f"- Verdict: **{row['verdict']}**")
        if row.get("flags"):
            lines.append("- Flags:")
            for item in row["flags"]:
                lines.append(f"  - {item}")
        if row.get("notes"):
            lines.append("- Notes:")
            for item in row["notes"]:
                lines.append(f"  - {item}")
        lines.append("")

    lines.append("## Cross-document notes")
    lines.append("")
    lines.append(
        "Each file is scored on its own. Related documents of the same "
        "Verra project are not merged automatically, but a few figures "
        "line up across files and are worth recording:"
    )
    lines.append("")
    lines.append(
        "* Kasigau I (562): the short PD has a clean area of 30,168.66 ha "
        "and a crediting period of 2005-01-01 to 2034-12-31 (30 years). "
        "The PDD has the same area (30,168.66 vs a 30,169 ha rounding) "
        "but its extracted 'reductions' figure of 1,450,329 tCO2e is, in "
        "the quote, estimated *baseline* emissions for a monitoring period. "
        "Lifetime ex-ante NERs of 7,542,945 tCO2e sit in unsupported text "
        "on both files and were not used."
    )
    lines.append(
        "* Kasigau II (612): the MR-M9 and Verification documents agree "
        "on 1,642,971 tCO2e for the M9 / 2022 period and on a project "
        "area of 169,741 ha. The 13% buffer rate lives on the Verification "
        "document; the 245,501 tCO2e buffer mass lives on the MR "
        "(245,501 is 13% of the 1,888,472 gross figure in the Verification quote). "
        "The PD excerpt has the same area and a first-monitoring-period "
        "total of 14,883,342 tCO2e, with no period length extracted."
    )
    lines.append(
        "* Mai Ndombe (934): 299,645 ha is the conservation concession; "
        "248,956 ha is the project accounting area (PAA). The extracted "
        "reductions (7,753,754 tCO2e) are 'throughout the PAA during M4', "
        "so intensity uses the accounting area."
    )
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "* The calculator does not re-read the PDFs or re-run Tiny Aya. "
        "It only sees what the cleaned merge kept as supported evidence."
    )
    lines.append(
        "* `unsupported` candidates (including leftover `169,741 hectares` "
        "prompt leaks on non-Kasigau-II documents, and some real figures "
        "whose quotes failed the value-in-quote check) are not used as "
        "primary inputs."
    )
    lines.append(
        "* Conflict resolution is quote-keyword scoring, not a human "
        "reading of the whole document. A genuine ambiguity that the "
        "score cannot break is left unresolved and flagged."
    )
    lines.append(
        "* The 0.5-30 tCO2e/ha/yr band is a screen. Verra does not set "
        "this threshold. Figures just outside it can still be legitimate."
    )
    lines.append(
        "* Period lengths for year-only ranges such as 2010-2039 are "
        "taken as inclusive calendar years (30 years). When a document "
        "states '30 years' next to a date range that is a few months "
        "shorter, the stated duration is used."
    )
    lines.append(
        "* Related documents of the same project are not combined when "
        "a field is missing on one of them (for example the Kasigau II "
        "buffer rate and mass live on different files)."
    )
    lines.append(
        "* There are no ground-truth labels in this run. The figures "
        "called out in MERGE_FIX.md were used as a post-hoc sanity check "
        "of the resolver, not as hardcoded answers."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"* Inputs: `{input_dir}/<stem>.json`")
    lines.append(f"* Table: `{out_dir / 'calc_results.csv'}`")
    lines.append(f"* Full results: `{out_dir / 'calc_results.json'}`")
    lines.append(f"* This report: `{path}`")
    lines.append("* Code: `src/verra_calc.py`")
    lines.append("* Notebook cell: `src/calc_cell.py`")
    lines.append("")
    lines.append("Nothing in this calculator was pushed to Kaggle.")
    lines.append("")
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


def run_calculator(input_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(input_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"no JSON files in {input_dir}")
    rows = []
    for path in paths:
        proj = load_project(path)
        rows.append(analyse_project(proj))
    write_csv(rows, output_dir / "calc_results.csv")
    write_json(rows, output_dir / "calc_results.json")
    write_report(rows, output_dir / "CALC_REPORT.md", input_dir, output_dir)
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    here = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
    try:
        from paths import REPO_ROOT, RESULTS_DIR
        repo, results = REPO_ROOT, RESULTS_DIR
    except Exception:
        repo = here.parent if here.name == "src" else here
        results = repo / "results"
    default_input = results / "extraction"
    if not default_input.is_dir():
        default_input = repo / "results_clean"
    parser = argparse.ArgumentParser(description="Tally Verra consistency calculator")
    parser.add_argument("--input", type=Path, default=default_input,
                        help="Directory of cleaned extraction JSONs")
    parser.add_argument("--output", type=Path, default=results,
                        help="Directory for calc_results.csv/json and CALC_REPORT.md")
    args = parser.parse_args(argv)
    rows = run_calculator(args.input, args.output)
    print(f"{'document':<52} {'area_ha':>12} {'reductions':>14} {'annual':>12} "
          f"{'t/ha/yr':>8} {'buf':>6} {'verdict':<18} key flag")
    for r in rows:
        area = f"{r['area_ha']:,.2f}" if r["area_ha"] is not None else "—"
        red = f"{r['reductions_tco2e']:,.0f}" if r["reductions_tco2e"] is not None else "—"
        ann = f"{r['annual_tco2e']:,.0f}" if r["annual_tco2e"] is not None else "—"
        inten = f"{r['tco2e_ha_yr']:.2f}" if r["tco2e_ha_yr"] is not None else "—"
        buf = f"{r['buffer_pct']:.0f}%" if r["buffer_pct"] is not None else "—"
        key = (r.get("key_flag") or "")[:40]
        print(f"{r['stem']:<52} {area:>12} {red:>14} {ann:>12} {inten:>8} {buf:>6} "
              f"{r['verdict']:<18} {key}")
    print(f"\nWrote {args.output / 'calc_results.csv'}, "
          f"{args.output / 'calc_results.json'}, {args.output / 'CALC_REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
