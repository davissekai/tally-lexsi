# Tally: a quote-grounded carbon-credit auditor on Tiny Aya

**Lexsi AI Safety Hackathon, Stage 1. Track 1: Fine-tuning and Data Curation.**
Problem statements: *Structured output and extraction* · *Grounded answers and fewer hallucinations*.
Author: Davis Dey (GitHub [`davissekai`](https://github.com/davissekai), HF [`renhuang001`](https://huggingface.co/renhuang001)).

> **One-line claim:** a QLoRA fine-tune of Tiny Aya Global extracts Verra carbon-credit fields with a verbatim quote or an honest "not stated". On unseen projects it beats base Tiny Aya and an 8B open model, with **zero hallucinated values**. ⟦V8⟧

## Headline before → after
**Held-out (3 unseen Verra projects, 20 stated values): stated-value accuracy 15% → 20% (3/20 → 4/20). Hallucinated values: 0 → 0.** ⟦V8⟧

**Base model and method:** `CohereLabs/tiny-aya-global`, QLoRA SFT (4-bit NF4 base, LoRA r=16 on attention projections, answer-only loss, 2 epochs) with AlignTune 0.1.35 `TRLSFTTrainer`, on CuratorKIT-gated, quote-grounded, project-split data. ⟦V8⟧

## For judges: one minute
- **Task:** 7 Verra fields from long project documents, each with a verbatim quote or "not stated".
- **Safety angle:** an auditor must not invent numbers. The fine-tune produced **0 hallucinated values** on held-out data.
- **Result:** held-out 3/20 → 4/20 stated; reserved validation documents 3/13 → 5/13. Qwen3-8B (4-bit) scored 3/20 in the same setup. ⟦V8⟧
- **Honest caveat:** 20 values is a small test. One answer = 5 points.
- **Insight:** the model usually *finds* the right number (it is among its own conflict candidates 5 of 6 times on area and crediting period) but fails to *choose*. ⟦V8⟧ v8 targets exactly that.

## Abstract
Forest carbon credits are sold on long, table-heavy Verra project documents in which the numbers that decide whether a credit is real (credited area, crediting period, leakage, non-permanence buffer, estimated reductions) sit beside look-alike figures. A small model that confidently picks the wrong one produces an audit that looks authoritative but is false. Tally fine-tunes Cohere Labs' Tiny Aya Global to extract seven Verra fields from long document chunks. Each field comes with a verbatim quote, or the model says "not stated". A grounded merge accepts a value only when its evidence checks out against the document, and a Verra consistency calculator then checks whether the numbers hang together.

We built a project-split SFT set of 1,050 examples (893 train / 157 validation, from 44 + 8 projects) from verified, quote-grounded labels. Hygiene ran through CuratorKIT; QLoRA SFT ran through AlignTune's `TRLSFTTrainer`. On three unseen Verra projects (20 stated values), v7 improved stated-value accuracy from 15% to 20% (3/20 → 4/20) and accuracy including correct abstentions from 14.3% to 23.8%, with **zero hallucinated values**. On two reserved validation documents it went from 23% to 38% (3/13 → 5/13). In the same setup, Qwen3-8B (4-bit) scored 3/20. The held-out set is small: one answer moves the rate by 5 points. Our main finding is the shape of the errors: choosing between look-alike numbers, not reading, is the bottleneck. ⟦V8⟧

## Problem and approach
**Why this problem.** Verra project descriptions and monitoring reports often run past 100 pages. The integrity-deciding figures sit beside look-alikes: leakage-belt areas, gross vs net reductions, monitoring vs crediting periods. Buyers, journalists and registries (including in Ghana, where several new ARR projects are listed) need fast first-pass checks. A small, cheap, self-hostable model that quotes its evidence or abstains is more useful here than a large one that guesses fluently.

**Approach (high level).**
1. **Extraction.** Tiny Aya reads fixed-size chunks and returns JSON for 7 fields, each with a verbatim quote (`schema/output_schema.json`, prompt in `inference/prompt.txt`).
2. **Grounded merge.** Chunk answers are combined into one document record. A value only counts if its evidence checks out against the document; disagreeing chunks produce a `conflict` with candidates rather than a guess.
3. **Verra consistency calculator.** Screens whether the extracted figures are mutually plausible.
4. **QLoRA SFT** on verified, quote-grounded, project-split training data built from public Verra registry documents.

## Hackathon kits used
- **CuratorKIT 0.1.27:** schema/shape and length gates, exact and near-duplicate removal, and text cleaning on the labelled set; messages-format export with a provenance record. Its schema gate also ran inside AlignTune during v7 training.
- **AlignTune 0.1.35:** `TRLSFTTrainer` (backend `trl`, chat-completion task, PEFT/QLoRA). The plain-TRL fallback was never needed. AlignTune wrote [`provenance/lexsi_provenance.json`](provenance/lexsi_provenance.json).

```
Verra documents → text → chunks → verified, quote-grounded labels
  → CuratorKIT (gates, dedup, clean; export + provenance)
  → AlignTune TRLSFTTrainer (QLoRA SFT on Tiny Aya; provenance)
  → LoRA adapter → extraction → grounded merge → scorer + Verra calculator
```

## Models and licenses
- **Base:** `CohereLabs/tiny-aya-global`, CC-BY-NC-4.0 (gated). The adapter inherits the non-commercial terms.
- **Adapter:** [`renhuang001/tally-v7-lora`](https://huggingface.co/renhuang001/tally-v7-lora). ⟦V8⟧ `tally-v8-lora`.
- **Training labels:** produced by a teacher LLM and then machine-verified against the source text; anything that failed verification was dropped, never guessed.
- **Comparison models (same prompt, decoding and scorer, 4-bit NF4):** Qwen3-8B (Apache-2.0); Gemma 3 12B IT (Gemma terms; result pending). No closed-model baseline.

## Data
- **Source:** public Verra VCS registry documents for forest/AFOLU projects. The documents remain their authors' copyright and are not redistributed.
- **v7 SFT set:** 1,050 examples (893 train from 44 projects / 157 validation from 8 projects); full-document-chunk extraction plus single-field questions, including "not stated" cases. ⟦V8⟧ v8: 3,206 train / 396 validation.
- **Splits:** by project group, not by chunk, so near-identical documents never cross train/validation. Validation documents and held-out projects are excluded from training and labelling.
- **Held-out test:** 3 project descriptions never seen in training or labelling (Verra 5172, 5432, 4329): 126 chunks, 21 field-pairs, 20 with a stated gold value. The answer key was hand-built from Verra definitions.

## Metrics
| Metric | Direction | Why |
|---|---|---|
| Stated-value accuracy | higher | Right number, right field |
| Accuracy incl. abstention | higher | Rewards honest "not stated" |
| Hallucinated values | **lower** | The safety property an auditor needs most |
| Conflicts left unresolved | lower | "Found but couldn't choose" |
| Validation loss (project-split) | lower | Overfit check |

Scoring is deterministic and rule-based ([`scorer/score_extractions.py`](scorer/score_extractions.py)); no LLM judge.

## Training (v7)
2 epochs, 224 optimiser steps, LR 2e-4 cosine, effective batch 8, seed 42; LoRA r=16, α=32 (~7.7M trainable parameters); 4-bit NF4 base, fp16. Free Kaggle T4, ≈6.3 h. Eval loss 0.1226 (epoch 1) → **0.1157** (epoch 2), best checkpoint kept; final mean train loss 0.125. Full logs: [`renhuang001/tally-eval-logs`](https://huggingface.co/datasets/renhuang001/tally-eval-logs). ⟦V8⟧ v8: HF Jobs A100, bf16.

An earlier run (v4: 62 examples, 3 epochs) overfit (validation loss ≈1.0, 0/13 stated on validation), which is why v5–v7 focused on more, cleaner, project-split data rather than more epochs.

## Results
**Held-out (3 unseen projects, 21 pairs, 20 stated)** ⟦V8⟧
| Model | Stated correct | Acc. incl. abstention | Hallucinated | Conflicts open |
|---|---|---|---|---|
| Base Tiny Aya (fp16) | 3/20 (15%) | 3/21 (14.3%) | 0 | 10 |
| **Tally v7** (fp16 + LoRA) | **4/20 (20%)** | **5/21 (23.8%)** | **0** | 9 |
| Qwen3-8B (4-bit NF4, thinking off) | 3/20 (15%) | 3/21 (14.3%) | 0 | 13 |
| Gemma 3 12B IT (4-bit NF4) | pending | | | |
| Tally v8 ⟦V8⟧ | pending | | | |

**Reserved validation documents (Miro 2410, Bandai Hills 2929; 14 pairs, 13 stated)**
| Model | Stated correct | Acc. incl. abstention | Hallucinated | Conflicts open |
|---|---|---|---|---|
| Base Tiny Aya | 3/13 (23.1%) | 4/14 (28.6%) | 0 | 4 |
| Tally v7 | **5/13 (38.5%)** | **6/14 (42.9%)** | 0 | 3 |

Aggregate and per-field counts: [`results/scores_aggregate.json`](results/scores_aggregate.json).

**Findings**
- *Finding ≠ choosing.* On held-out area and crediting period, the correct value was among v7's own conflict candidates in 5 of 6 cases.
- *No hallucinations.* No evaluated run produced a hallucinated value on held-out data; when unsure, models left a conflict or abstained.
- *Size isn't the fix.* Qwen3-8B (~2.5× larger) tied base Tiny Aya and left more conflicts open.
- *Weak fields:* leakage, additionality, baseline, area. Permanence buffer is strong (3/3 for v7).
- With n=20, a 95% Wilson interval on 4/20 is roughly 8–42%; 3/20 → 4/20 is not significant on its own.

## Cost
v7 training: free Kaggle T4, ≈6.3 h. Held-out inference: base 51 min, v7 ≈21 min (Kaggle T4). Qwen3-8B benchmark: 87 min on Kaggle T4s. ⟦V8⟧ v8: HF Jobs A100, ≈$3 estimated.

## Limitations
- 20% stated accuracy on held-out is far too low for unsupervised use; Tally is a first-pass triage tool.
- Small held-out set (3 projects, 20 values); single seed; no general-capability retention benchmark; no closed-model baseline; AuditKIT not used.
- Teacher labels were machine-verified but not fully human-reviewed.
- Precision differs: Tiny Aya held-out runs used fp16; comparison models ran in 4-bit.

## With more credits
1. ⟦V8⟧ v8: better evidence windows plus training examples that target choosing between look-alike candidates, ~3.6× the data, A100 bf16.
2. A candidate-selection step after the merge.
3. RL with a verifiable, quote-grounded reward through AlignTune's RL trainers.
4. A larger held-out set (10+ projects); AuditKIT evaluation; cost-per-1k vs API.

## What's in this repo (Stage 1 release)
```
inference/run_extraction.py   run base Tiny Aya or Tally (base + LoRA) on a document's text
inference/prompt.txt          the extraction prompt used for every result above
schema/output_schema.json     per-chunk output schema and merged-record shape
scorer/score_extractions.py   rule-based scorer used for every result
scorer/score_file.py          CLI: score merged outputs against your own answer key
results/scores_aggregate.json aggregate held-out and validation scores
provenance/lexsi_provenance.json  AlignTune provenance record from the v7 run
```
Quick start:
```bash
pip install -r requirements.txt
export HF_TOKEN=...            # Tiny Aya Global is gated
pdftotext -layout project.pdf project.txt
python inference/run_extraction.py project.txt
python scorer/score_file.py --pred project.tally.json --key my_answer_key.json
```

**Withheld for IP (available to the organisers on request):** training and validation data, labels and the labelling pipeline, the grounded-merge / quote-verification code, training scripts, data builders, and the held-out answer key and per-answer outputs (kept private so the test set stays clean). `run_extraction.py` ships a simple merge baseline, so its merged output will not exactly reproduce the grounded-merge numbers above; the adapter, prompt, decoding settings and scorer are the same.

## Declaration of work done outside the hackathon
TODO (Renhuang to confirm): all Tally code, data, labels and models were created during the hackathon; public Verra documents and open-source libraries were used as permitted.

## Acknowledgements and LLM usage
Thanks to Lexsi Labs (AlignTune, CuratorKIT), Cohere Labs (Tiny Aya), Kaggle and Hugging Face for compute. Parts of the code and write-up were drafted with AI assistants; training labels were produced by a teacher LLM and machine-verified.

## Changelog
- **v1 (Stage 1):** Tally v7 adapter, held-out 4/20.
- ⟦V8⟧ **v2:** v8 adapter; held-out TODO/20.

License: code MIT (see `LICENSE`); the adapter follows the base model's CC-BY-NC-4.0.
