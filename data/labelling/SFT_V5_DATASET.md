# Tally SFT v5 dataset report

Built 13 Nov 2026 (Africa/Accra). Nothing pushed to Kaggle and nothing trained.

## What changed from v4

- 13 new Verra PDs (`data_expansion/pdfs/`) were labelled by hand at document level in `data_expansion/answer_key_v5.json`, with no LLM calls. Open calls are in `data_expansion/AMBIGUOUS.md`.
- Each PD was chunked with the same chunker (`chunk_merge.chunk_doc`, 3,500 tokens, 300 overlap, real Tiny Aya `tokenizer.json`), giving 359 chunks.
- Per-chunk labels: a field gets a value only if one of its grounding quotes (primary, manual alternative, or an automatic alternative that restates the same distinctive number) is a literal substring of the whitespace-collapsed chunk. Otherwise it is `"not stated"`.
- Prompt, answer JSON shape and CuratorKIT 0.1.27 config (clean + exact + MinHash 0.85, `strip_html` off) are identical to v4. The v4 trim to ≤5,400 tokens was applied, but no new chunk needed it.
- Train = all 62 v4 examples, unchanged (including the 4 additionality duplicates) + every new chunk with at least one value + new all-`not stated` chunks sampled with `random.Random(42)` so empties make up about 17.5% of the total.
- Validation is byte-identical to v4 (23 Miro + Bandai chunks, md5 `d3dba9ba2ec087d31914cad5597e8ac2`).

## Counts

| | Examples | With ≥1 value | All not stated |
|---|---:|---:|---:|
| v4 carried over | 62 | 52 | 10 |
| v5 new chunks used | 96 | 78 | 18 (of 281 available) |
| **Train total** | **158** | **130** | **28** (17.7%) |
| Validation (unchanged) | 23 | 21 | 2 |

The 13 new PDs give 359 chunks in total: 78 with a value and 281 empty. CuratorKIT passed all 417 pool rows (58 unique v4 + 359 new) and rejected 0. Longest example: 5297 tokens.

## Examples per project (train)

| Project | Chunks in PD | Train examples | With value | Empty |
|---|---:|---:|---:|---:|
| 673 Kibale, Uganda | 12 | 7 | 6 | 1 |
| 987 Ghana degraded forest reserves ARR | 14 | 4 | 4 | 0 |
| 993 TIST Uganda | 14 | 7 | 6 | 1 |
| 1168 Kulera, Malawi | 28 | 12 | 8 | 4 |
| 1201 Gola, Sierra Leone | 22 | 7 | 7 | 0 |
| 1202 Lower Zambezi, Zambia | 18 | 7 | 6 | 1 |
| 1215 Makira, Madagascar | 40 | 15 | 11 | 4 |
| 1311 CAZ, Madagascar | 26 | 6 | 6 | 0 |
| 1408 Chyulu Hills, Kenya | 41 | 10 | 5 | 5 |
| 1775 Luangwa, Zambia | 31 | 4 | 3 | 1 |
| 1897 Ntakata, Tanzania | 27 | 5 | 5 | 0 |
| 1900 Makame, Tanzania | 35 | 7 | 7 | 0 |
| 2510 Chinko, CAR | 51 | 5 | 4 | 1 |
| v4:1340_Bale-Mountains_MR_2020-2021 | – | 12 | 8 | 4 |
| v4:562_Kasigau-I-Rukinga_PDD_2011-01-31 | – | 9 | 6 | 3 |
| v4:562_Kasigau-I-Rukinga_PD_short_2011-01-25 | – | 3 | 3 | 0 |
| v4:612_Kasigau-II-Community-Ranches_MR-M9_2022 | – | 12 | 12 | 0 |
| v4:612_Kasigau-II-Community-Ranches_PD_excerpt | – | 1 | 1 | 0 |
| v4:612_Kasigau-II-Community-Ranches_Verification_2024 | – | 10 | 9 | 1 |
| v4:934_Mai-Ndombe_MR-M4_2021 | – | 15 | 13 | 2 |

That makes 20 projects in training (7 from v4, 13 new), up from 7.

## Positive targets per field (train)

| Field | v4 | v5 new | Total |
|---|---:|---:|---:|
| baseline | 15 | 13 | 28 |
| additionality | 8 | 13 | 21 |
| leakage | 5 | 9 | 14 |
| permanence_buffer | 10 | 8 | 18 |
| crediting_period | 14 | 17 | 31 |
| area | 25 | 32 | 57 |
| estimated_reductions | 17 | 26 | 43 |
| **all** | 94 | 118 | 212 |

## Quote checks

- Document level: 88 of 88 hand-picked quotes (primary + manual alternatives) are literal substrings of the whitespace-collapsed page text, and each one's page was located automatically. The 33 automatic alternative quotes are cut from the page text itself, so they are literal by construction. No primary quote is longer than 40 words.
- Answer key: 73 of 91 document fields are stated (baseline 8, additionality 13, leakage 8, buffer 7, crediting period 13, area 12, estimated reductions 12) and 18 are not stated.
- Chunk level: 118 of 118 new positive targets (100%) have a quote that is a literal substring of the chunk the model sees, re-checked after CuratorKIT cleaning and after trimming. The v4 targets were already re-grounded by `rebalance.py`.

## Leakage check (validation and held-out)

- No training row comes from 2410 Miro, 2929 Bandai, 2928 North Bandai, 5172, 5432 or 4329. No training chunk mentions Miro, Bandai, Akwaaba, Kwahu, CRCF or those project IDs.
- None of the 10 distinctive (5+ digit) gold numbers from the Miro, Bandai and held-out keys appears in any training chunk.
- 12-word shingle overlap with those documents is only Verra/CCB template boilerplate: page headers, the CCB benefits-table footnote definitions (forest, REDD, full-time equivalency, well-being), and CDM tool titles. Share of each document's 12-grams found in the new training chunks: 4329 2.1%, Akwaaba PD 0.5%, Kwahu 0.4%, Bandai 0.4%, Miro 0.2%. The longest shared runs (178 and 143 words) are the CCB template footnotes. One 75-word generic risk paragraph is shared between Ntakata (1897) and 4329. It contains no project values.
- 2928 North Bandai has no local text, so the check against it is by name and ID only.

## Problems and caveats

- The set is smaller than the earlier 220–360 estimate. Strict in-chunk grounding on long PDs (on average 28 chunks each) leaves about 6 positive chunks per PD. Most chunks are rightly empty, so only 18 of the 281 new empties were sampled to stay near 17.5%.
- Leakage (14) and buffer (18) are still the thinnest fields.
- Many new quotes are table rows, e.g. `Total 5,121,660 75,238 488,214 ...`, not sentences. They are literal, but the same row grounds several fields at once.
- 1215's after-buffer total is printed `31'212'644` (apostrophes) and 673 uses `4.450.862`. Values copy the PD as written, so the Verra calculator's number parser has to handle both.
- The Kaggle notebook's v4 hyperparameters were tuned for 62 examples (3 epochs, 3 warmup steps). At 158 examples, 3 epochs is about 60 optimiser steps, so consider 2 epochs and about 6 warmup steps. I didn't edit the notebook.

## Files (`/workspace/tally/sft_v5/`)

- `dataset/train.jsonl`, `validation.jsonl`: messages format (AlignTune local folder).
- `dataset/train_sft_messages.jsonl` and `train_sft_messages_rebalanced.jsonl`: the same 158 rows, so the notebook's discovery and its rebalanced path both load v5. Also `train_sft_alpaca.jsonl` and `train_rebalanced_with_metadata.jsonl` (id, project, positive fields, tokens, source).
- `dataset/val_sft_*.jsonl`, `answer_key.json`, `tinyaya_scores.json`, `tally_merge.py`, `score_extractions.py`: copied unchanged from v4, so scoring stays comparable. `answer_key_v5.json` is added. `rebalance_report.json` has every key the notebook prints.
- `curatorkit_run/`: CuratorKIT manifest, dataset card, checksums and exports.
- Scripts: `chunk_new.py`, `key_draft.py`, `build_key.py`, `build_v5.py`.
