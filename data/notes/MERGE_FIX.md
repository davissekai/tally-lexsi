# Tally merge fix

## What was wrong

The merge treated a quote as proof of a value whenever the quote text appeared in the document. It never checked whether the *value itself* was in that quote.

The extraction prompt also used a real-looking example, `"169,741 hectares"` (Kasigau II's actual area). When the model could not find an area in a chunk, it often copied that example and attached some real but unrelated sentence. `quote_found` was then True, and the leak was treated as supported evidence.

That is how Bandai Hills ended up with 169,741 ha as its final area, while its real figure of 7,372 ha was parked under `unsupported` — the model's quote was "The total eligible project area is 7372 ha.", but a line break in the PDF (`eligible \nproject area`) made the raw substring search fail.

A second problem: many values sat in the wrong field (a hectare figure filed as a baseline, "39.90%" as a baseline, an area filed as leakage). And when two candidates were the same number written slightly differently ("3,871" vs "3,871 ha"), the merge counted them as a conflict.

## What changed

All of this is in `merge_notes` (in `chunk_merge.py` and notebook cell 7f). The raw per-chunk model outputs were not re-run; only the merge was rerun, with no GPU.

1. **Value-in-quote.** Before a candidate can be supported, its numbers must appear in its quote, or in the rest of that same sentence in the document (quotes are capped at 40 words, so the number is often cut off). Commas and spaces in numbers are ignored, so "169,741" and "169741" match, but "20" will not match inside "2020". For a date range such as "2011 to 2041", only the years have to be present (days and months often show up as words like "December"). If the value has no digits, a substantial piece of the wording must appear. Failures go under `unsupported`, never `supported`.

2. **Per-field units.** After the quote check, we reject values that are the wrong type for the field:
   - area: a number with ha / hectare(s) / acre(s)
   - permanence buffer and leakage: a % or a tCO2e/tonne deduction (or an explicit zero)
   - estimated reductions: tCO2e / tonnes / tons
   - crediting period: years or dates
   - baseline and additionality: descriptive; a bare hectare figure, a bare percentage, a bare number, or a tCO2e figure that never mentions "baseline" is rejected

3. **Conflicts.** Filters run first. If one distinct value survives, it is promoted. If several survivors are the same number ("3,871" and "3,871 ha", or "2010-2039" and "01 January 2010 – 31 December 2039"), they are collapsed into one, keeping the richer wording and the list of pages.

4. **Quote matching.** Quotes are re-checked against the full document, ignoring case and whitespace, so a line-break no longer hides a real quote. Very short quotes such as "0" or "221205" are ignored (they appear all over a document). `merge_notes` now takes an optional `doc_text` so it can do this and recover a page number.

5. **The prompt (cell 7d).** The example `"169,741 hectares"` was replaced with obvious placeholders (`"<number> hectares"`, `"<start year>–<end year>"`). This does not change the results already on disk, but it stops the leak at the source the next time you extract.

The Kaggle notebook still uses `max_tokens=3500` and `torch.cuda.empty_cache()` before each chunk. Nothing was pushed to Kaggle.

## Before and after (63 field-slots: 9 documents × 7 fields)

| status       | before | after |
|--------------|--------|-------|
| clean        | 18     | 19    |
| conflict     | 28     | 21    |
| not stated   | 17     | 23    |

"Not stated" went up on purpose: invented or wrong-field values that had been marked clean (Bandai's 169,741 ha area, Kasigau II Verification's 169,741 ha "baseline", Bale's 398,532 ha "leakage") are now unsupported. The 169,741 leak appeared in 28 supported/conflict candidates before; after the fix it remains only as the area of the three Kasigau II documents.

Spot checks:
- Bandai Hills area is no longer 169,741 ha. The real eligible project area, 7,372 ha, is back. It conflicts with two other real figures from the same document (see below).
- 169,741 ha is supported only for the Kasigau II docs.

## Still ambiguous (for the Verra calculator)

These are genuine disagreements in the documents, or two ways of stating the same thing, not leftover leaks. A suggested reading is in parentheses.

- **Bandai Hills area:** 7,372 ha (eligible project area) vs 7,804.56 ha (lease) vs 3,500 ha (area to be planted). Use **7,372 ha**.
- **Bandai Hills reductions:** 3,778,511 tCO2e (20-year total) vs 188,926 tCO2e (annual average) vs 0 tCO2e (fire emissions, wrong field). Use **3,778,511 tCO2e** total, or 188,926 / year.
- **Bandai Hills crediting period:** 20 years and 01 June 2022 – 31 May 2042 (the same period).
- **Bandai Hills baseline:** not stated after the filters (the previous "clean" / conflict candidates were a prompt-definition leak, a land-use phrase whose quote did not support it, or the reductions figure filed in the wrong field).
- **Miro area:** 3,871 ha (verified project / monitoring area) vs 10,495 ha (land established in Ghana). Use **3,871 ha** for the project.
- **Miro leakage:** 15,758 tCO2e vs 10% vs 481,955 (the last looks like total carbon, not leakage).
- **Miro reductions:** 221,205 / 326,399 / 52,402 / 481,955 tCO2e (different periods or totals).
- **Miro crediting period:** 24 March 2016 – 30 June 2045 and "30 years" (same period); a verification window is also listed.
- **Kasigau I PDD area:** 30,168.66 ha vs 30,169 ha (rounding). Leakage is 0 tCO2e for the monitoring period vs a 20% ex-ante factor. Reductions came out as 1,450,329 tCO2e, which the quote describes as estimated *baseline* emissions — treat with care.
- **Kasigau I short PD:** area 30,168.66 ha and crediting period 2005-01-01 to 2034-12-31 came out clean. Baseline and additionality dropped because their quotes did not contain the claimed wording.
- **Kasigau II MR area:** 169,741 ha (project total) vs individual ranch sizes (5,076 ha, 1,030 ha). Use **169,741 ha**. Reductions: 1,642,971 tCO2e (this monitoring period, M9) vs 18,163,638 and 20,948,108 (cumulative / lifetime). Crediting period: 2010–2039 vs 2022 (a reporting year). Buffer is 245,501 tCO2e; the 13% rate is on the Verification document.
- **Kasigau II Verification reductions:** 1,642,971 tCO2e (period) vs 18,163,638 tCO2e (to date). Crediting period came out as "1 year" (the monitoring period, not the 30-year crediting period).
- **Mai Ndombe area:** 299,645 ha (conservation concession) vs 248,956 ha (project accounting area). Leakage: 34,325 tCO2e vs 0. Crediting period: 14 March 2011 – 13 March 2041 vs the 2011–2021 / 2021 monitoring window. Reductions: 7,753,754 (the quote says tonnes of CO2e). Baseline "3.5 million cubic meters of merchantable hardwood" is a resource figure, not a BAU emissions scenario.
- **Bale Mountains** is still the messiest: several real but different area figures (261,053 ha project area, 333,924 ha project boundary including leakage management, 289,083 ha predicted to be deforested), a buffer of 10% vs 3,866,463 tCO2e, and a crediting period of 2012–2031 / 20 years vs the 2020–2021 monitoring window. Additionality came out as a cookstoves co-benefit, which is not an additionality test. Leakage is not stated (the old "398,532 hectares" was an area in the wrong field).

## Files

- Cleaned results: `/workspace/tally/results_clean/<stem>.json` (each file keeps the original chunks and a `merged_before` for comparison)
- Summary table: `/workspace/tally/results_clean/summary.csv`
- Merge code: `/workspace/tally/chunk_merge.py` and cell 7f of `/workspace/tally/tally_kaggle.ipynb`
- Prompt: cell 7d of the notebook, and `/workspace/tally/section7_cells.md`
- Original Kaggle outputs, unchanged: `/workspace/tally/run_output/tally/results/`

This notebook was not pushed to Kaggle.
