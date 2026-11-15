# Tally Verra consistency calculator

Screening check of the seven extracted fields, run on the cleaned merge in `results_clean/`. This is not a re-run of each project's own calculation worksheet. It asks whether the numbers in a document hang together, and whether the implied reductions per hectare per year look like a published REDD+ / ARR project.

## Method

For each document:

1. **Load** the `merged` object. A field value is either a clean string, `conflict` (with a `conflicts` list of candidates), or `not stated`. Bare `not stated` strings are treated the same as the dict form.
2. **Parse** numbers and units: thousands commas, hectare / tCO2e / percent / year units, annual-vs-total wording, and the date and duration forms used in these PDDs and monitoring reports.
3. **Resolve conflicts** with a transparent, quote-driven score. The calculator never hard-codes a project's 'right' number. Area prefers 'eligible project area' / 'project accounting area' over a lease, a planted subset, a leakage-belt boundary, or a list of component ranches. Reductions prefer a figure whose quote actually describes emission reductions, and a monitoring-period total on an MR / verification document (or a lifetime total on a PD / validation). A date range labelled 'crediting period' is kept separately from a monitoring / verification window. A buffer percent and a buffer tCO2e mass are two views of the same thing, not a conflict. Candidates that the merge already rejected (`unsupported`) are not used as primary figures.
4. **Check** the following, then issue a verdict of PASS, FLAG, or INSUFFICIENT DATA.

Checks:

* **Annual consistency.** If the document states both a total and an annual figure, they should agree within 2% once the matching period length is applied.
* **Intensity.** Reductions divided by area divided by years should fall in **0.5-30 tCO2e/ha/yr**. This is a literature-informed screening band, not a Verra threshold. Tropical African REDD+ often lands around 2-15 tCO2e/ha/yr (roughly a 1-3% annual loss rate times 100-250 tC/ha, times 44/12). ARR / plantation growth is commonly about 2-20 tCO2e/ha/yr, and fast-growing stands in a short window can run higher. Below 0.5 usually means a lifetime total has been paired with the wrong area or a too-long period; above 30 usually means a period total has been paired with a too-small area or a too-short period. High-stock avoided-logging years can legitimately exceed 30 — those are flagged for review, not declared impossible.
* **Permanence buffer.** The VCS AFOLU Non-Permanence Risk Tool allows **10-60%** (above 60% the project is not eligible). 10-20% is typical and is not flagged; 21-60% is noted as elevated but still eligible. If only a tCO2e mass is extracted, an implied rate is computed from the chosen reductions.
* **Leakage.** A tCO2e leakage deduction is reported as a share of the chosen reductions and flagged above 40%. A leakage percentage factor is reported when no mass is available.
* **Net identity.** Where possible, net is approximated as gross minus leakage minus buffer. The calculator does not subtract again if the chosen reductions are already described as issuance after the buffer, or as net of a stated buffer rate.

A document **PASSes** when the needed figures can be resolved and every numeric check holds. It is a **FLAG** when a check fails, a material conflict cannot be resolved, or the extracted 'reductions' figure is clearly something else (for example baseline emissions). It is **INSUFFICIENT DATA** when area, reductions, or a matching period length is missing, so tCO2e/ha/yr cannot be formed, and no other hard contradiction was found.

## Results

| Document | Area (ha) | Total reductions (tCO2e) | Annual (tCO2e/yr) | tCO2e/ha/yr | Buffer | Verdict | Key flag |
|---|---:|---:|---:|---:|---:|---|---|
| 1340 Bale Mountains MR 2020 2021 | 261,053 | 3,196,344 | 1,598,172 | 6.12 | 10% | **PASS** | — |
| 2410 Miro Ghana Verification 2020 2022 | 3,871 | — | — | — | 10% | **FLAG** | reductions unresolved (top candidates tied with different values: 221,205 tCO2e vs 326,… |
| 2929 Bandai Hills Ghana Validation 2024 | 7,372 | 3,778,511 | 188,926 | 25.63 | — | **PASS** | — |
| 562 Kasigau I Rukinga PDD 2011 01 31 | 30,168.66 | — | — | — | — | **FLAG** | estimated_reductions value is described in its quote as baseline emissions (1,450,329 t… |
| 562 Kasigau I Rukinga PD short 2011 01 25 | 30,168.66 | — | — | — | — | **INSUFFICIENT DATA** | missing estimated reductions |
| 612 Kasigau II Community Ranches MR M9 2022 | 169,741 | 1,642,971 | 1,642,971 | 9.68 | 13% | **PASS** | — |
| 612 Kasigau II Community Ranches PD excerpt | 169,741 | 14,883,342 | — | — | — | **INSUFFICIENT DATA** | missing period length (cannot form tCO2e/ha/yr) |
| 612 Kasigau II Community Ranches Verification 2024 | 169,741 | 1,642,971 | 1,642,971 | 9.68 | 13% | **PASS** | — |
| 934 Mai Ndombe MR M4 2021 | 248,956 | 7,753,754 | 7,753,754 | 31.15 | 10% | **FLAG** | 31.15 tCO2e/ha/yr is outside the screening band 0.5-30 tCO2e/ha/yr |

9 documents: 4 PASS, 3 FLAG, 2 INSUFFICIENT DATA.

## Per document

### 1340 Bale Mountains MR 2020 2021

- File: `1340_Bale-Mountains_MR_2020-2021.json` (monitoring document)
- Area: 261,053 ha (status: resolved)
- Reductions: 3,196,344 t CO2 e (scope: period, status: resolved)
- Annual: 1,598,172 tCO2e/yr
- Period: crediting January-2012 – 31-December-2031; 20 years total period; monitoring 2020-2021; years used: 2 (monitoring / verification window)
- Intensity: 6.12 tCO2e/ha/yr (period / area / monitoring / verification window)
- Buffer: 10% (10.0%), 3,866,463 tCO2e
- Leakage: —
- Implied net: 2,876,709.6 tCO2e
- Verdict: **PASS**
- Notes:
  - area: chose 261,053 ha (quote calls it the project area)
  - reductions: chose 3,196,344 t CO2 e (quote describes (net) emission reductions; treated as a period figure because this is an MR / verification)
  - period: chose January-2012 – 31-December-2031; 20 years total period (quote calls it the crediting period; full date range of a typical crediting length)
  - buffer: chose 10% (buffer stated as a percentage (the risk rating); 10% is inside the VCS AFOLU 10-60% range; quote refers to the non-permanence buffer); chose 3,866,463 tCO2e (buffer stated as a tCO2e withholding; quote refers to the non-permanence buffer)
  - buffer mass 3,866,463 tCO2e is larger than the chosen reductions, so it is treated as a different (likely lifetime) scope and is not used to imply a rate for this figure
  - net = 3,196,344 - leakage not stated - buffer 319,634.4 = 2,876,709.6 tCO2e (buffer mass skipped as a different scope; used the % rate)

### 2410 Miro Ghana Verification 2020 2022

- File: `2410_Miro-Ghana_Verification_2020-2022.json` (monitoring document)
- Area: 3,871 hectares (status: resolved)
- Reductions: — (scope: —, status: unresolved)
- Period: crediting 30 years; monitoring 02-11-2020 to 19-09-2022
- Buffer: 10% (10.0%)
- Leakage: 15,758 tCO2e
- Verdict: **FLAG**
- Flags:
  - reductions unresolved (top candidates tied with different values: 221,205 tCO2e vs 326,399 tCO2e)
- Notes:
  - area: chose 3,871 hectares (quote calls it the project area; area considered for this monitoring period; lease area, not the eligible project area)
  - period: chose 30 years (quote calls it the crediting period; stated crediting-period length)
  - leakage: chose 15,758 tCO2e (quote describes a leakage deduction; leakage stated as tCO2e)
  - if reductions were 221,205 tCO2e: 30.42 tCO2e/ha/yr over 1.8782 monitoring years
  - if reductions were 326,399 tCO2e: 44.89 tCO2e/ha/yr over 1.8782 monitoring years
  - if reductions were 52,402 tCO2e: 13.54 tCO2e/ha/yr (stated annual / area)
  - leakage factor 10% (no tCO2e mass to combine)

### 2929 Bandai Hills Ghana Validation 2024

- File: `2929_Bandai-Hills-Ghana_Validation_2024.json` (design document)
- Area: 7372 ha (status: resolved)
- Reductions: 3,778,511 tCO2e (scope: lifetime, status: resolved)
- Annual: 188,926 tCO2e/yr
- Period: crediting 20 years; years used: 20 (crediting period)
- Intensity: 25.63 tCO2e/ha/yr (lifetime / area / crediting period)
- Buffer: —
- Leakage: 0 tCO2e, 0.0% of reductions
- Implied net: 3,778,511.0 tCO2e
- Verdict: **PASS**
- Notes:
  - area: chose 7372 ha (quote calls it the eligible project area)
  - reductions: chose 3,778,511 tCO2e (quote describes (net) emission reductions; lifetime or annual figure, fits a design document)
  - period: chose 20 years (quote calls it the crediting period; stated crediting-period length)
  - stated annual 188,926 tCO2e/yr matches total / 20 years
  - 25.63 tCO2e/ha/yr is toward the high end of the 0.5-30 screening band
  - leakage is stated as 0 tCO2e

### 562 Kasigau I Rukinga PDD 2011 01 31

- File: `562_Kasigau-I-Rukinga_PDD_2011-01-31.json` (design document)
- Area: 30,168.66 ha (status: resolved)
- Reductions: 1,450,329 tonnes CO2e (scope: period, status: rejected)
- Period: —
- Buffer: —
- Leakage: 0 tCO2e
- Verdict: **FLAG**
- Flags:
  - estimated_reductions value is described in its quote as baseline emissions (1,450,329 tonnes CO2e), not as net emission reductions
- Notes:
  - area: chose 30,168.66 ha
  - leakage: chose 0 tCO2e (quote describes a leakage deduction; leakage stated as tCO2e)
  - leakage factor 20% (no tCO2e mass to combine)

### 562 Kasigau I Rukinga PD short 2011 01 25

- File: `562_Kasigau-I-Rukinga_PD_short_2011-01-25.json` (design document)
- Area: 30,168.66 ha (status: clean)
- Reductions: — (scope: —, status: not_stated)
- Period: crediting 2005-01-01 to 2034-12-31
- Buffer: —
- Leakage: —
- Verdict: **INSUFFICIENT DATA**

### 612 Kasigau II Community Ranches MR M9 2022

- File: `612_Kasigau-II-Community-Ranches_MR-M9_2022.json` (monitoring document)
- Area: 169,741 hectares (status: resolved)
- Reductions: 1,642,971 t CO2e (scope: period, status: resolved)
- Annual: 1,642,971 tCO2e/yr
- Period: crediting 2010-2039; monitoring 2022; years used: 1 (monitoring / verification window)
- Intensity: 9.68 tCO2e/ha/yr (period / area / monitoring / verification window)
- Buffer: 245,501 tCO2e (13.0%), 245,501 tCO2e
- Leakage: —
- Implied net: 1,642,971.0 tCO2e
- Verdict: **PASS**
- Notes:
  - area: chose 169,741 hectares (quote calls it the project area)
  - reductions: chose 1,642,971 t CO2e (quote describes (net) emission reductions; figure is for this monitoring period)
  - period: chose 2010-2039 (quote calls it the crediting period; year-year span of a typical crediting length)
  - implied buffer rate 13.0% (buffer / (buffer + reductions))
  - chosen reductions look like they are already net of the buffer (rate fits buffer / (buffer + reductions))
  - chosen reductions already look like a net/issuance figure after the buffer; not subtracting the buffer again

### 612 Kasigau II Community Ranches PD excerpt

- File: `612_Kasigau-II-Community-Ranches_PD_excerpt.json` (design document)
- Area: 169,741 hectares (status: clean)
- Reductions: 14,883,342 tCO2e (scope: period, status: clean)
- Period: —
- Buffer: —
- Leakage: —
- Verdict: **INSUFFICIENT DATA**

### 612 Kasigau II Community Ranches Verification 2024

- File: `612_Kasigau-II-Community-Ranches_Verification_2024.json` (monitoring document)
- Area: 169,741 hectares (status: clean)
- Reductions: 1,642,971 tCO2e (scope: period, status: resolved)
- Annual: 1,642,971 tCO2e/yr
- Period: monitoring 1 year; years used: 1 (monitoring / verification window)
- Intensity: 9.68 tCO2e/ha/yr (period / area / monitoring / verification window)
- Buffer: 13% (13.0%)
- Leakage: —
- Implied net: 1,642,971.0 tCO2e
- Verdict: **PASS**
- Notes:
  - reductions: chose 1,642,971 tCO2e (issuance figure after the buffer withholding; treated as a period figure because this is an MR / verification)
  - chosen reductions already look like a net/issuance figure after the buffer; not subtracting the buffer again

### 934 Mai Ndombe MR M4 2021

- File: `934_Mai-Ndombe_MR-M4_2021.json` (monitoring document)
- Area: 248,956 ha (status: resolved)
- Reductions: 7,753,754 (scope: period, status: clean)
- Annual: 7,753,754 tCO2e/yr
- Period: crediting 14 March 2011 – 13 March 2041; monitoring 2021; years used: 1 (monitoring / verification window)
- Intensity: 31.15 tCO2e/ha/yr (period / area / monitoring / verification window)
- Buffer: 10% (10.0%)
- Leakage: 34,325 tCO2e, 0.4% of reductions
- Implied net: 6,944,053.6 tCO2e
- Verdict: **FLAG**
- Flags:
  - 31.15 tCO2e/ha/yr is outside the screening band 0.5-30 tCO2e/ha/yr
- Notes:
  - area: chose 248,956 ha (quote calls it the project accounting area)
  - period: chose 14 March 2011 – 13 March 2041 (quote calls it the crediting period; full date range of a typical crediting length)
  - leakage: chose 34,325 tCO2e (quote describes a leakage deduction; leakage stated as tCO2e)
  - leakage is 0.4% of chosen reductions
  - net = 7,753,754 - leakage 34,325.0 - buffer 775,375.4 = 6,944,053.6 tCO2e

## Cross-document notes

Each file is scored on its own. Related documents of the same Verra project are not merged automatically, but a few figures line up across files and are worth recording:

* Kasigau I (562): the short PD has a clean area of 30,168.66 ha and a crediting period of 2005-01-01 to 2034-12-31 (30 years). The PDD has the same area (30,168.66 vs a 30,169 ha rounding) but its extracted 'reductions' figure of 1,450,329 tCO2e is, in the quote, estimated *baseline* emissions for a monitoring period. Lifetime ex-ante NERs of 7,542,945 tCO2e sit in unsupported text on both files and were not used.
* Kasigau II (612): the MR-M9 and Verification documents agree on 1,642,971 tCO2e for the M9 / 2022 period and on a project area of 169,741 ha. The 13% buffer rate lives on the Verification document; the 245,501 tCO2e buffer mass lives on the MR (245,501 is 13% of the 1,888,472 gross figure in the Verification quote). The PD excerpt has the same area and a first-monitoring-period total of 14,883,342 tCO2e, with no period length extracted.
* Mai Ndombe (934): 299,645 ha is the conservation concession; 248,956 ha is the project accounting area (PAA). The extracted reductions (7,753,754 tCO2e) are 'throughout the PAA during M4', so intensity uses the accounting area.

## Limitations

* The calculator does not re-read the PDFs or re-run Tiny Aya. It only sees what the cleaned merge kept as supported evidence.
* `unsupported` candidates (including leftover `169,741 hectares` prompt leaks on non-Kasigau-II documents, and some real figures whose quotes failed the value-in-quote check) are not used as primary inputs.
* Conflict resolution is quote-keyword scoring, not a human reading of the whole document. A genuine ambiguity that the score cannot break is left unresolved and flagged.
* The 0.5-30 tCO2e/ha/yr band is a screen. Verra does not set this threshold. Figures just outside it can still be legitimate.
* Period lengths for year-only ranges such as 2010-2039 are taken as inclusive calendar years (30 years). When a document states '30 years' next to a date range that is a few months shorter, the stated duration is used.
* Related documents of the same project are not combined when a field is missing on one of them (for example the Kasigau II buffer rate and mass live on different files).
* There are no ground-truth labels in this run. The figures called out in MERGE_FIX.md were used as a post-hoc sanity check of the resolver, not as hardcoded answers.

## Files

* Inputs: `/workspace/tally/results_clean/<stem>.json`
* Table: `/workspace/tally/calc_results.csv`
* Full results: `/workspace/tally/calc_results.json`
* This report: `/workspace/tally/CALC_REPORT.md`
* Code: `/workspace/tally/verra_calc.py`
* Notebook cell: `/workspace/tally/calc_cell.py` and section 7i of `section7_cells.md`

Nothing in this calculator was pushed to Kaggle.
