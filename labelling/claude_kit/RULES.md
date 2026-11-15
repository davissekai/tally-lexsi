# Tally labelling rules

You are labelling **real** chunks cut from real Verra VCS documents (PD = project description, MR = monitoring report, VR = verification report, VAL = validation report). Your job is to find the fields below in the chunk you were given, and to copy the exact sentence or table row each value comes from.

**Never invent a document, a sentence, a number, or a quote.** If a field is not in this chunk, it is `not_stated`. That is the expected answer for most chunks.

Label each chunk **on its own**. Use only that chunk's text, even if you have already seen another chunk from the same project.

---

## Fields (follow Verra VCS definitions)

1. **baseline** — the business-as-usual scenario without the project, as a quantity: baseline emissions in tCO2e (or a baseline deforestation rate if that is the only figure). PD: the total over the crediting period / projection. MR or VR: the current monitoring period.

2. **additionality** — how the project shows it only happens because of carbon finance: the tool or test used (e.g. VT0001, CDM additionality tool, investment / barrier analysis, common practice) and its conclusion. Community or biodiversity co-benefits are **not** additionality.

3. **leakage** — emissions displaced outside the project, in **tCO2e only** (a stated 0 counts: `"0"` with unit `tCO2e`). A leakage percentage alone is **not** a value: put it in `conflicts` and mark leakage `not_stated`.

4. **permanence_buffer** — the percentage of credits put in the AFOLU non-permanence buffer pool, as a **percentage only** (e.g. 13%). If the chunk gives both a risk-tool score and a different applied/held percentage, use the applied one and list the other in `conflicts`.

5. **crediting_period** — the **full** crediting period as a date range (start and end; include the stated number of years if given). Not a monitoring period, not a baseline period.

6. **area** — the **credited project area** (project accounting area) in hectares. A total that includes the leakage belt goes in `area_incl_leakage_belt` instead. Ignore reference-region and leakage-belt-only areas. Never add project area and leakage belt yourself.

7. **estimated_reductions** — net GHG emission reductions/removals **after the buffer deduction**, in tCO2e. PD: the crediting-period total (use an annual figure only if no total is in the chunk, and set unit `tCO2e/yr`). MR or VR: the current monitoring period.

### Auxiliary fields

8. **area_incl_leakage_belt** — total hectares of project area plus leakage belt, **only if stated as such**. Do not compute it.

9. **estimated_reductions_pre_buffer** — if the chunk states only a total **before** the buffer is deducted, put it here and set `estimated_reductions` to `not_stated`. If both are stated, fill both.

---

## Strict rules

- Every value needs a `"quote"`: an exact passage copied **character-for-character** from the chunk (same words, numbers, punctuation, symbols and spelling, typos included; only spacing and line breaks may differ). One contiguous passage, at most 50 words. For tables, copy the row or header text as it appears.
- The value must appear inside its quote: copy the number/date/words **exactly as written in the quote** (keep its separators, e.g. `"31'212'644"` or `"551 338"`). Put the unit in `"unit"`, not in `"value"`.
- **Never infer, convert, sum, round or compute anything.** Never use outside knowledge or other chunks. If the document has an obvious typo, copy it as written and describe it in `conflicts`.
- If a field is absent from the chunk, or only implied, write exactly `"not_stated"` for it. Most chunks have no values at all; that is expected and fine. Do not guess.
- **Conflicts:** if the chunk gives two or more different candidate figures for one field (e.g. 6,213 ha vs 6,212 ha, 10% vs 13%), pick the best one per the rules above as the value and list every alternative in `"conflicts"` with its own verbatim quote.
- **Units:**
  - baseline: `tCO2e` (or `tCO2e/yr`, `ha/yr`, `%/yr`)
  - additionality: `null`
  - leakage: `tCO2e`
  - permanence_buffer: `%`
  - crediting_period: `dates`
  - area and area_incl_leakage_belt: `ha`
  - estimated_reductions and estimated_reductions_pre_buffer: `tCO2e` or `tCO2e/yr`

---

## Rule illustrations from real chunks

These are short excerpts from real documents, to show how the rules apply. They are not invitations to invent similar text.

**Leakage as a percentage only.** In `1201_PD::chunk-001` the chunk says:

> This estimation includes avoided emissions minus 20% annual leakage (conservative estimate of leakage), and does not include the 10% buffer deduction.

- `leakage` = `not_stated`. Put `20%` in `conflicts` with that quote. A percentage is not a tCO2e value.
- `permanence_buffer` = `10` with unit `%`, quote: `does not include the 10% buffer deduction`.

**Pre-buffer totals.** The same chunk later gives `Total estimated Ers 9,267,387 (2018-2028)` and has already said that figure does not include the buffer deduction. So:

- `estimated_reductions_pre_buffer` = `9,267,387` with unit `tCO2e` and that quote
- `estimated_reductions` = `not_stated` (do not treat a pre-buffer total as the after-buffer answer)

If a chunk states both the pre-buffer total and the after-buffer (net / VCU) total, fill both fields.

**Area vs leakage belt.** In `1566_PD_2017::chunk-003` the chunk says:

> The Project Area (PA) has an area of 1,150,212 hectares. - The Leakage Belt (LB) has an area of 486,211 hectares. - The Region Reference to project the location of deforestation (RRL) has an area of 2,028,439 hectares

- `area` = `1,150,212` with unit `ha` (the credited project area)
- Do **not** put 486,211 or 2,028,439 in `area`
- `area_incl_leakage_belt` = `not_stated` (the chunk never states the sum; do not add 1,150,212 + 486,211)

**Annual figure when a total exists.** In `993_PD::chunk-000` the table ends with `Total estimated ERs 580,246` and also `Average annual ERs 19,342`. Use the total 580,246 for `estimated_reductions`, not the annual figure.

---

## JSON output schema (labeller)

Write **one JSON object per chunk**, as a single line in `labels.jsonl`. Use straight double quotes. If a quote contains a `"` character, escape it as `\"`. Every object must have `chunk_id`, `fields` (all nine fields present), and `conflicts` (use `[]` when there are none).

```json
{
  "chunk_id": "<id from the chunk file header>",
  "fields": {
    "baseline": {"value": "...", "quote": "...", "unit": "tCO2e"},
    "additionality": "not_stated",
    "leakage": "not_stated",
    "permanence_buffer": {"value": "13", "quote": "...", "unit": "%"},
    "crediting_period": "not_stated",
    "area": "not_stated",
    "estimated_reductions": "not_stated",
    "area_incl_leakage_belt": "not_stated",
    "estimated_reductions_pre_buffer": "not_stated"
  },
  "conflicts": [
    {"field": "permanence_buffer", "value": "10", "quote": "...", "note": "risk-tool score vs applied"}
  ]
}
```

A stated field is always an object with `value`, `quote`, and `unit`. An absent field is the string `"not_stated"`, not an object and not `null`.

---

## Worked examples (from real v5 labels)

These labels were checked against the source chunks. Values are written in the schema above (unit in `"unit"`, not inside `"value"`). The chunk files themselves contain the full text; only the relevant passages are shown here.

### Example 1 — `993_PD::chunk-000` (PD, TIST Uganda)

The chunk states a 30-year crediting period, a credited area of 722.6 ha, and a total of 580,246 estimated ERs. The average annual figure is present but must not be used, because a total is stated.

```json
{
  "chunk_id": "993_PD::chunk-000",
  "fields": {
    "baseline": "not_stated",
    "additionality": "not_stated",
    "leakage": "not_stated",
    "permanence_buffer": "not_stated",
    "crediting_period": {
      "value": "30 years starting 01-January-2003 and ending to 31-December-2032",
      "quote": "30 years starting 01-January-2003 and ending to 31-December-2032",
      "unit": "dates"
    },
    "area": {
      "value": "722.6",
      "quote": "initially applies to 301 of the Small Groups, 1,799 members, 953 project areas and 722.6 ha.",
      "unit": "ha"
    },
    "estimated_reductions": {
      "value": "580,246",
      "quote": "Total estimated ERs 580,246",
      "unit": "tCO2e"
    },
    "area_incl_leakage_belt": "not_stated",
    "estimated_reductions_pre_buffer": "not_stated"
  },
  "conflicts": []
}
```

Note the typo in the source (`ending to 31-December-2032`): the quote and the value keep it. Do not tidy it up.

### Example 2 — `1897_PD::chunk-014` (PD, Ntakata REDD)

A totals row and a following sentence give baseline, leakage in tCO2e, a 13% buffer, and after-buffer estimated reductions. Leakage is taken from the prose (where the unit is explicit); the same number also appears in the totals row.

```json
{
  "chunk_id": "1897_PD::chunk-014",
  "fields": {
    "baseline": {
      "value": "8,953,829",
      "quote": "Total 8,953,829 2,008,032 6,945,797 1,180,149 13% 902,954 5,727,542",
      "unit": "tCO2e"
    },
    "additionality": "not_stated",
    "leakage": {
      "value": "1,180,149",
      "quote": "a total expected emission reduction of 5,727,542 t CO2e after accounting for leakage (1,180,149 t CO2e).",
      "unit": "tCO2e"
    },
    "permanence_buffer": {
      "value": "13",
      "quote": "Total 8,953,829 2,008,032 6,945,797 1,180,149 13% 902,954 5,727,542",
      "unit": "%"
    },
    "crediting_period": "not_stated",
    "area": "not_stated",
    "estimated_reductions": {
      "value": "5,727,542",
      "quote": "a total expected emission reduction of 5,727,542 t CO2e after accounting for leakage (1,180,149 t CO2e).",
      "unit": "tCO2e"
    },
    "area_incl_leakage_belt": "not_stated",
    "estimated_reductions_pre_buffer": "not_stated"
  },
  "conflicts": []
}
```

The 13% is a buffer percentage, so it belongs in `permanence_buffer`, not in `leakage`. The 5,727,542 figure is the total after leakage and the buffer, so it belongs in `estimated_reductions`.

### Example 3 — `2510_PD::chunk-050` (PD, a later bibliography chunk)

This chunk is a short references/methods passage. It contains no baseline, additionality, leakage, buffer, crediting period, area, or estimated reductions. The correct label is all `not_stated`. Most chunks look like this. That is fine.

```json
{
  "chunk_id": "2510_PD::chunk-050",
  "fields": {
    "baseline": "not_stated",
    "additionality": "not_stated",
    "leakage": "not_stated",
    "permanence_buffer": "not_stated",
    "crediting_period": "not_stated",
    "area": "not_stated",
    "estimated_reductions": "not_stated",
    "area_incl_leakage_belt": "not_stated",
    "estimated_reductions_pre_buffer": "not_stated"
  },
  "conflicts": []
}
```

---

## JSON output schema (reviewer)

Write to `review.jsonl`. Either **one line per field**, or **one line per chunk** with a `reviews` array. Both are accepted.

Per field:

```json
{
  "chunk_id": "993_PD::chunk-000",
  "field": "area",
  "verdict": "accept",
  "reason": "722.6 ha is the credited project area and appears in the quote."
}
```

```json
{
  "chunk_id": "993_PD::chunk-000",
  "field": "estimated_reductions",
  "verdict": "fix",
  "value": "580,246",
  "quote": "Total estimated ERs 580,246",
  "unit": "tCO2e",
  "reason": "The labeller used the annual figure; the chunk also states the total, which takes priority."
}
```

```json
{
  "chunk_id": "1201_PD::chunk-001",
  "field": "leakage",
  "verdict": "reject",
  "reason": "Only a 20% leakage rate is stated, not a tCO2e amount."
}
```

Per chunk (preferred, one atomic line):

```json
{
  "chunk_id": "993_PD::chunk-000",
  "reviews": [
    {"field": "baseline", "verdict": "accept", "reason": "not stated in this chunk"},
    {"field": "area", "verdict": "accept", "reason": "722.6 ha is the credited area"},
    {"field": "estimated_reductions", "verdict": "fix", "value": "580,246", "quote": "Total estimated ERs 580,246", "unit": "tCO2e", "reason": "total takes priority over annual"}
  ]
}
```

`verdict` must be one of `accept`, `fix`, or `reject`. On `fix`, include the corrected `value`, `quote`, and `unit`. On `reject`, the field will be set to `not_stated`. Review every field, including those already marked `not_stated` (a miss is a `fix`).
