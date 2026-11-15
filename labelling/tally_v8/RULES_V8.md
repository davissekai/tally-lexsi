# Tally v8 labelling rules (read fully before batch 1)

You label **real** chunks cut from real Verra VCS documents. `doc_type` is in each chunk header: **PD** = project description, **MR** = monitoring report, **VR** = verification report.

**Never invent anything.** Every value and every quote is copied from the chunk text. If a field is not in the chunk, it is `"not_stated"`. Most fields in most chunks are `"not_stated"`. That is expected and correct.

Label each chunk **on its own**: only the text between `<<<TEXT` and `TEXT>>>` of that chunk. Never use other chunks, earlier batches, the hints, or outside knowledge.

---

## 1. The nine fields (Verra VCS definitions)

| # | field | what it is | unit (write exactly) |
|---|---|---|---|
| 1 | `baseline` | Business-as-usual scenario without the project, as a quantity: baseline emissions in tCO2e (or a baseline deforestation rate if that is the only figure). PD: total over the crediting period. MR/VR: the current monitoring period. | `tCO2e`, `tCO2e/yr`, `ha/yr` or `%/yr` |
| 2 | `additionality` | The test used to show the project needs carbon finance (VT0001, CDM additionality tool, investment analysis, barrier analysis, common practice analysis) **and its conclusion**, as one short phrase copied from the text. Co-benefits are NOT additionality. | `null` |
| 3 | `leakage` | Emissions displaced outside the project, **in tCO2e only**. A stated 0 counts (`"0"`). | `tCO2e` |
| 4 | `permanence_buffer` | Percentage of credits put into the AFOLU non-permanence buffer pool. | `%` |
| 5 | `crediting_period` | The **full** crediting period: start date and end date (keep the number of years if written in the same passage). | `dates` |
| 6 | `area` | The **credited project area** (project accounting area) in hectares. | `ha` |
| 7 | `estimated_reductions` | Net GHG emission reductions/removals **after leakage and after the buffer deduction**. PD: the crediting-period total (an annual figure only if no total is in the chunk, then unit `tCO2e/yr`). MR/VR: the current monitoring period. | `tCO2e` or `tCO2e/yr` |
| 8 | `area_incl_leakage_belt` | Hectares of project area plus leakage belt, **only if the text states that total**. Never add it up yourself. | `ha` |
| 9 | `estimated_reductions_pre_buffer` | Net reductions **before** the buffer deduction. If the chunk gives only a pre-buffer total, put it here and set `estimated_reductions` to `"not_stated"`. If both are given, fill both. | `tCO2e` or `tCO2e/yr` |

---

## 2. Value and quote rules (the validator checks every one)

1. `quote` = one passage copied **character for character** from the chunk text, **at most 50 words**, on one line.
   - Where the text breaks a line, write exactly **one space** (also after a hyphen at a line end: `Bahuaja-` + newline + `Sonene` becomes `Bahuaja- Sonene`).
   - Never put two spaces in a row. No leading or trailing spaces.
   - Keep spelling, typos, symbols, punctuation and number separators exactly as written.
   - Never quote the `[Section: ...]` line, a `--- page N ---` line, or the hints. A quote must not cross a page marker.
   - For a table, copy the row as it appears in the chunk (cells separated by single spaces).
2. `value` = the figure **exactly as it appears inside the quote** (e.g. `31'212'644`, `551 338`, `1,150,212`). It must be a substring of the quote. The unit goes in `unit`, not in `value`.
   - Numeric fields (baseline, leakage, permanence_buffer, area, estimated_reductions, the two auxiliary fields): `value` is just the number as written, at most 4 words.
   - `crediting_period`: the date span as written, containing both a start year and an end year (two 4-digit years). If the chunk does not give both, the field is `"not_stated"`.
   - `additionality`: a short phrase copied from the quote (at most 40 words) naming the test and/or its conclusion.
3. **Never infer, convert, sum, round or compute.** If it is not written, it is `"not_stated"`.
4. A field that is absent, only implied, or only described in words without the figure is `"not_stated"` (the exact string, never `null`, never an object).
5. `permanence_buffer` is a percentage between 0 and 100. `leakage` must be tCO2e: a leakage percentage alone is **not** a value.

---

## 3. Conflicts: the fixed procedure (do this for every field, every chunk)

A **conflict** is a *different figure* in the same chunk that someone could mistake for this field. The same figure repeated is **not** a conflict. Do these steps in order.

**Step A: find candidates.** Every figure in the chunk that could be read as this field.

**Step B: reject wrong-type candidates.** Each one goes into `conflicts` with this code:

| candidate | code |
|---|---|
| leakage given as a % or rate (not tCO2e) | `R_LEAKAGE_PERCENT` |
| leakage belt area | `R_LEAKAGE_BELT_AREA` |
| reference region, proxy area, or reference area | `R_REFERENCE_REGION_AREA` |
| project area plus leakage belt total (then also fill `area_incl_leakage_belt`) | `R_AREA_INCL_BELT` |
| reductions before the buffer deduction (then also fill `estimated_reductions_pre_buffer`) | `R_PRE_BUFFER` |
| gross reductions before leakage/deductions, or baseline emissions offered as reductions | `R_GROSS_NOT_NET` |
| non-permanence risk score/rating, different from the applied/withheld buffer % | `R_RISK_SCORE` |
| a monitoring period or other sub-period (first period, baseline validity period) offered as the crediting period | `R_MONITORING_PERIOD` |
| a historical reference/baseline period offered as the crediting period | `R_HISTORICAL_PERIOD` |
| a figure for another project, instance, stratum, parcel or sub-area | `R_DIFFERENT_SCOPE` |

**Step C: if no candidate is left**, the field is `"not_stated"` (keep the conflicts you listed).

**Step D: if two or more are left**, keep exactly one using the first rule that separates them; each loser goes into `conflicts` with the code shown:

1. One is described as original, previous, superseded or replaced, the other as current/revised → keep the current one. Loser: `R_SUPERSEDED`.
2. MR/VR only: one is for the current monitoring period, the other cumulative or another period → keep the current period. Loser: `R_OTHER_PERIOD`.
3. One is a total for the crediting period (or for the whole monitoring period), the other annual/average/one year → keep the total. Loser: `R_ANNUAL_OR_AVERAGE`.
4. One is in a summary table, totals row, or the section dedicated to this field (see the `[Section: ...]` line and headings), the other is a passing mention → keep the summary/dedicated one. Loser: `R_PASSING_MENTION`.
5. Still tied → keep the one that appears **first** in the chunk. Loser: `R_DUPLICATE_LOWER_PRIORITY`.

**Limits.** At most **4** conflicts per field. Never list every row of a per-year or per-stratum table: list at most one annual/average figure (prefer a row labelled "average" or "annual") and at most one stratum figure. Each conflict has its own verbatim quote containing its value.

Every conflict item has exactly these keys: `field`, `value`, `quote`, `unit` (a string such as `"%"`, `"ha"`, `"tCO2e"`, or `null`), `code`.

---

## 4. Output: one JSON line per chunk

Write `labels/batch_NNNN.jsonl` with **exactly one line per chunk, in the batch order**. Each line is one JSON object with exactly the keys `chunk_id`, `fields`, `conflicts`:

```json
{"chunk_id": "<id>", "fields": {"baseline": "not_stated", "additionality": "not_stated", "leakage": "not_stated", "permanence_buffer": {"value": "13", "quote": "...", "unit": "%"}, "crediting_period": "not_stated", "area": "not_stated", "estimated_reductions": "not_stated", "area_incl_leakage_belt": "not_stated", "estimated_reductions_pre_buffer": "not_stated"}, "conflicts": []}
```

- All nine field keys are always present. A stated field is an object with exactly `value`, `quote`, `unit`. An absent field is the string `"not_stated"`.
- Use straight double quotes. Escape a `"` inside a quote as `\"` and a backslash as `\\`.
- `conflicts` is `[]` when there are none.
- No other keys, no comments, no trailing commas, no blank lines between objects.

---

## 5. Worked examples (real passages from Verra documents)

**Leakage only as a percentage** (PD). Text: `This estimation includes avoided emissions minus 20% annual leakage (conservative estimate of leakage), and does not include the 10% buffer deduction.`
- `leakage` = `"not_stated"`; conflict `{"field": "leakage", "value": "20%", "quote": "This estimation includes avoided emissions minus 20% annual leakage (conservative estimate of leakage), and does not include the 10% buffer deduction.", "unit": "%", "code": "R_LEAKAGE_PERCENT"}`
- `permanence_buffer` = `{"value": "10", "quote": "does not include the 10% buffer deduction", "unit": "%"}`

**Pre-buffer total.** The same chunk gives `Total estimated Ers 9,267,387 (2018-2028)` and says it does not include the buffer deduction:
- `estimated_reductions_pre_buffer` = `{"value": "9,267,387", "quote": "Total estimated Ers 9,267,387 (2018-2028)", "unit": "tCO2e"}`
- `estimated_reductions` = `"not_stated"`; conflict `{"field": "estimated_reductions", "value": "9,267,387", "quote": "Total estimated Ers 9,267,387 (2018-2028)", "unit": "tCO2e", "code": "R_PRE_BUFFER"}`

**Area vs leakage belt vs reference region** (PD). Text: `The Project Area (PA) has an area of 1,150,212 hectares. - The Leakage Belt (LB) has an area of 486,211 hectares. - The Region Reference to project the location of deforestation (RRL) has an area of 2,028,439 hectares`
- `area` = `{"value": "1,150,212", "quote": "The Project Area (PA) has an area of 1,150,212 hectares.", "unit": "ha"}`
- conflicts: `486,211` with `R_LEAKAGE_BELT_AREA`, and `2,028,439` with `R_REFERENCE_REGION_AREA`, each with its own quote.
- `area_incl_leakage_belt` = `"not_stated"` (the sum is never stated; never add).

**Total vs annual** (PD). Table ends with `Total estimated ERs 580,246` and `Average annual ERs 19,342`:
- `estimated_reductions` = `{"value": "580,246", "quote": "Total estimated ERs 580,246", "unit": "tCO2e"}`
- conflict: `19,342` with `R_ANNUAL_OR_AVERAGE`, quote `Average annual ERs 19,342`.

**Crediting period vs a sub-period** (PD). Text: `Project crediting period: 20 years (July 01, 2010 – June 30, 2030).` and `First period to quantify GHG emission reductions: 10 years (July 01, 2010 – June 30, 2020)`
- `crediting_period` = `{"value": "20 years (July 01, 2010 – June 30, 2030)", "quote": "Project crediting period: 20 years (July 01, 2010 – June 30, 2030).", "unit": "dates"}`
- conflict: `{"field": "crediting_period", "value": "10 years (July 01, 2010 – June 30, 2020)", "quote": "First period to quantify GHG emission reductions: 10 years (July 01, 2010 – June 30, 2020)", "unit": "dates", "code": "R_MONITORING_PERIOD"}`

**Typos are kept.** `30 years starting 01-January-2003 and ending to 31-December-2032` is copied exactly, `ending to` included.

**Empty chunk.** Most chunks: all nine fields `"not_stated"`, `"conflicts": []`.
