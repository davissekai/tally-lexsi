# Tally: a small model that reads carbon-credit documents and quotes its evidence

**Claim:** A LoRA fine-tune of Tiny Aya Global (about 3B parameters) pulls seven key figures out of Verra carbon-credit project documents, quoting the line each one came from. On three unseen projects it scores better than Qwen3-8B and Gemma 3 12B, and none of the models tested invented a number.

## Track and problem statements

Track 1: Fine-tuning and Data Curation.
- Structured output and extraction
- Grounded answers and fewer hallucinations

## Abstract

Forest carbon credits are sold on the strength of long Verra project documents, often over a hundred pages and full of tables. The figures that decide whether a credit is sound, such as credited area, crediting period, leakage, the non-permanence buffer and estimated reductions, sit next to look-alikes: leakage-belt area beside project area, monitoring periods beside crediting periods, gross beside net reductions. A model that picks the wrong one produces an audit that looks careful and is wrong.

Tally fine-tunes CohereLabs Tiny Aya Global to read document chunks and return seven Verra fields as JSON. Each value comes with a verbatim quote, or the model says "not stated". A rule-based merge combines the chunks into one record per document and keeps a value only if its quote is in the document, the number is in the quote, and the unit fits the field.

Training data came from public Verra documents. Teacher models labelled chunks (Claude Opus for v5 to v7, Gemini 3.8 Flash for v8), and a program checked every label against the source text. Data passed through CuratorKIT checks and was trained with AlignTune's SFT trainer. The final adapter, v8, was trained on 3,206 examples from 43 project groups, including 1,035 examples that teach it to choose between conflicting figures.

On a held-out test of three unseen projects (20 stated values), all models ran on one A100 in bf16 with the same prompt and scorer. Base Tiny Aya scored 2/20 and v8 scored 6/20. After an error analysis I added general Verra rules to the merge step. With them, base scores 3/20 and v8 scores 8/20, ahead of Qwen3-8B (6/20) and Gemma 3 12B (3/20). No model produced a hallucinated value. The new merge rules were written after looking at held-out errors, so I report both numbers. On validation documents the rules did not turn any correct answer wrong.

The test is small: one answer moves the score by 5 points. The error analysis shows where the remaining points are. Most misses are values the model never extracts, mainly additionality, leakage and table totals, so the next step is targeted training data for those fields.

## Headline: before and after

Same base model, held-out test, 20 stated values:

- **Base Tiny Aya 3/20 (15%) → Tally v8 8/20 (40%)**, with the current merge (v2).
- Base 2/20 → v8 6/20 with the original merge (v1).
- Hallucinated values: 0 → 0.

## Base model and method

CohereLabs/tiny-aya-global, bf16 LoRA supervised fine-tuning (rank 16, attention layers, answer-only loss, 2 epochs) through AlignTune 0.1.35, on quote-checked, CuratorKIT-gated data split by project.

## Problem and approach

**Why this problem.** Buyers, journalists and registries need a fast first check of these documents, including in Ghana, where several new forestry projects are listed. A small model you can run yourself, which shows its evidence or admits a gap, is more useful for this than a larger one that guesses fluently. For an auditor, an invented number is the worst error, so grounding is the core requirement, not an extra.

**Approach.**
1. **Chunking.** Each document is split into 3,500-token windows with 300 tokens of overlap.
2. **Extraction.** The model returns JSON for seven fields: baseline, additionality, leakage, permanence buffer, crediting period, area and estimated reductions. Each field has a value and a quote, or "not stated".
3. **Grounded merge.** A value survives only if its quote is in the document, the number is in the quote, and the unit fits. If chunks still disagree, the merge reports a *conflict* rather than guessing. Merge v2 adds general Verra preferences for choosing between candidates (see Results).
4. **Scoring.** A fixed program compares the merged record with a hand-built answer key.

## Kits used and how they connect

- **CuratorKIT 0.1.27.** Schema and length checks, exact and near-duplicate removal, and text cleaning on the first labelled set, then export to chat format with a provenance record. Its schema check also ran inside AlignTune for the v7 and v8 training runs.
- **AlignTune 0.1.35.** `TRLSFTTrainer` (TRL backend) for both v7 and v8. It wrote a provenance file for each run.
- **AuditKIT 1.1.12.** Before-and-after evaluation of base Tiny Aya and v8 on a validation slice (field F1, exact match, JSON validity, groundedness), plus its built-in red-team probes on v8.

Pipeline: Verra PDFs → text → chunks → teacher labels → quote check → CuratorKIT → AlignTune SFT → LoRA adapter → AuditKIT check → extraction → grounded merge → scorer.

## Models and licenses

- **Base:** CohereLabs/tiny-aya-global, CC-BY-NC-4.0 (non-commercial). The adapters follow the same terms.
- **Labellers (teacher models):** Claude Opus 5.5 for v5 to v7 labels; Gemini 3.8 Flash for v8 labels. They were used only to label training chunks, never on the test set. I chose them because they were strong at reading long documents and quoting exactly, and both were available on my existing subscriptions.
- **Comparison models:** Qwen3-8B (Apache-2.0) and Gemma 3 12B IT (Gemma license), run unchanged with the same prompt and scorer.

## Data, splits and leak check

- **Source:** public Verra VCS registry documents for forest and land-use projects. URLs and SHA-256 hashes are in `data/sources/`. The PDFs are not re-hosted; rights stay with their owners.
- **Labels:** a label is kept only if its quote is an exact substring of the chunk, the value appears in the quote, and the unit fits. Failures are dropped, never repaired by guesswork.
- **v8 set:** 3,206 train and 396 validation examples. Train covers 43 project groups and validation 8. It mixes full extractions, single-field questions, hard negatives and 1,035 conflict-pick examples. Published in [tally-sft-data](https://huggingface.co/datasets/renhuang001/tally-sft-data) (configs `v7` and `v8`)
- **Languages:** English only.
- **Splits:** by project group, so related documents never cross between train and validation. Group overlap: none.
- **Held-out test:** three project descriptions never used in labelling or training (Verra 5172, 5432 and 4329), 126 chunks, 21 field pairs, 20 with a stated value. A neighbouring project, 2928, was also excluded. The answer key follows Verra definitions and stays private so the test can be reused.

## Metrics

- **Stated-value accuracy:** of the 20 fields that have a real value in the document, how many the model got right. This is the main score.
- **Accuracy including abstention:** also credits a correct "not stated" (21 pairs).
- **Hallucinated values:** values that do not appear in the document. Lower is better. This is the safety measure.
- **Conflicts left open:** the merge found candidates but could not choose. A conflict is better than a confident wrong answer, but it is still a miss.

The scorer is code, not a language model, so results are deterministic.

## Training setup (v8)

v8 is a LoRA fine-tune of Tiny Aya, trained with AlignTune's SFT trainer on one A100 for 49 minutes. The base model ran at full bf16 precision with no quantization, and the loss was computed only on the answer tokens. Training ran for two epochs, and validation loss fell from 0.0447 to 0.0405.

| Setting | Value |
|---|---|
| LoRA rank / alpha / dropout | 16 / 32 / 0.05 (q, k, v, o) |
| Learning rate | 2e-4, cosine, 10% warmup |
| Effective batch size | 8 |
| Steps | 802 |
| Max length | 4,096 tokens |
| Seed | 42 |

## Results

Held-out test, one A100, all models in bf16, greedy decoding, `max_new_tokens=900`. Merge v1 and v2 scores use the same saved model outputs; only the merge step differs.

| Model | Size | Stated, merge v1 | Stated, merge v2 | Incl. abstention (v2) | Hallucinated | Conflicts open (v2) |
|---|---|---|---|---|---|---|
| **Tally v8** | ~3B + LoRA | 6/20 | **8/20 (40%)** | 9/21 | 0 | 2 |
| Qwen3-8B | 8B | 4/20 | 6/20 (30%) | 6/21 | 0 | 10 |
| Tally v7 | ~3B + LoRA | 3/20 | 5/20 (25%) | 6/21 | 0 | 6 |
| Base Tiny Aya | ~3B | 2/20 | 3/20 (15%) | 3/21 | 0 | 9 |
| Gemma 3 12B | 12B | 3/20 | 3/20 (15%) | 3/21 | 0 | 13 |

**Merge v2.** I sorted every v8 miss by cause and then wrote merge rules that apply to any Verra document: prefer a dated crediting period over a bare duration or a monitoring window; prefer the credited area over the project zone or leakage belt; prefer a project total over an annual or single-year figure; treat "1.234,567" and "1,234,567" as the same number; and accept a tCO2e table total as a baseline. Because the held-out errors informed these rules, I report v1 and v2 side by side. I checked them on two validation documents that played no part in designing them: no correct answer became wrong, and the base model gained one (v7 5/13 → 5/13, base 3/13 → 4/13). No held-out answer was lost for any model either.

**AuditKIT check.** I ran Lexsi's AuditKIT on v8 and on the untuned base, using the same 40 examples drawn from the validation set, not the held-out documents. On field-level F1, v8 scored 0.71 and the base model 0.12. All 40 of v8's answers were valid JSON and 17 matched the labelled answer exactly; the base model had 37 valid JSON answers and no exact matches. Word overlap with the source page was a little higher for the base model (0.82 against 0.75), because it copies more of the page even when the fields are wrong. On AuditKIT's built-in red-team checks, v8 passed 39 of 47: it refused every jailbreak and did not refuse harmless requests, but it followed a few prompts telling it to ignore its instructions.

**Error breakdown** (v8, merge v1, 14 misses):
- 9 extraction misses: the value is in the text but the model never pulls it out. Mostly additionality and leakage on all three projects, plus some table totals.
- 4 conflicts: the right value was extracted but the merge dropped it or kept a look-alike. Merge v2 fixed 2 of these.
- 1 out of reach: one project's crediting dates come from the registry and are not in the document.

## Limitations

- 40% is far too low for unsupervised use. Tally is a first-pass triage tool that points a person to the right page.
- The test is small: three projects, 20 values, one seed. A 95% interval on 8/20 is roughly 22% to 61%. Read the ranking as indicative.
- The merge v2 rules were written after seeing held-out errors. The validation check reduces, but does not remove, the risk of fitting to the test.
- English, forest and land-use Verra documents only. No test of general ability after fine-tuning, no closed-model baseline, and AuditKIT was run only on a validation slice, not on the held-out documents. v8 can be steered by prompt injection.
- Teacher labels were checked by program against the source text, not fully reviewed by a person.

## With more credits

The error analysis points to two fixes, in this order:

1. **Targeted extraction data.** Most of the remaining misses are fields the model skips. I would label several hundred examples focused on additionality (the test used and its verdict), leakage stated as a percentage or as zero, and table totals with their headers kept in the same chunk. Then retrain with several seeds.
2. **A document-level picker.** A second step that sees every candidate for a field across the whole document and picks one, trained on conflict-pick examples or written as rules.

Expected result, as a forecast rather than a measurement: the error analysis puts the ceiling at 19/20 on this test and a realistic target at 16 to 17/20, with hallucinations kept at zero. To make that number meaningful I would also grow the held-out set to at least ten projects and add a general-ability check.

## Artifacts

- Code: [github.com/davissekai/tally-lexsi](https://github.com/davissekai/tally-lexsi)
- Models collection: [Tally models](https://huggingface.co/collections/renhuang001/tally-models-6afa44295934fb19bb00fbb4), containing [tally-v8-lora](https://huggingface.co/renhuang001/tally-v8-lora) (submission model) and [tally-v7-lora](https://huggingface.co/renhuang001/tally-v7-lora)
- Data and logs collection: [Tally data and logs](https://huggingface.co/collections/renhuang001/tally-data-and-logs-6afa44297c71d80cb8aca723), containing [tally-sft-data](https://huggingface.co/datasets/renhuang001/tally-sft-data) and [tally-eval-logs](https://huggingface.co/datasets/renhuang001/tally-eval-logs)
- Aggregate scores: `results/scores_a100_bf16_aggregate.json` in the repo

Kept private: the held-out answer key and per-answer held-out outputs, so the test stays usable, and credentials.

## Reproduction

```bash
pip install -r requirements.txt
export HF_TOKEN=...   # Tiny Aya Global is gated
pdftotext -layout project.pdf project.txt
python inference/run_extraction.py project.txt            # v8 adapter, merge v2
python scorer/score_file.py --pred project.tally.json --key your_answer_key.json
```

- Training data: download `tally-sft-data`, or rebuild it from `labels/` with `labelling/tally_v8/`.
- Training: `hf jobs uv run --flavor a100-large --secrets HF_TOKEN training/v8_hf_jobs/train_v8_hfjobs.py` (set `HUB_REPO` to your own repo).
- Benchmark: `benchmark/bench_a100.py` runs all five models; `scripts/rescore_merge_v2.py` rescores saved outputs with merge v1 and v2. Both need your own test documents and answer key.

## Declaration of work outside the hackathon

All Tally code, data, labels and adapters were created during the hackathon. It uses public Verra registry documents, the open models listed above, and open-source libraries.

## LLM usage

Most of the code was written by an AI coding assistant working under my direction. I chose the problem, set the answer-key rules, made the design and data decisions, and reviewed the results. Training labels were produced by Claude Opus 5.5 (v5 to v7) and Gemini 3.8 Flash (v8) and then checked by programme against the source text. No language model was used to score results.

## Teammates

Solo entry by Davis

## Acknowledgements

Thanks to Lexsi Labs for AlignTune and CuratorKIT, Cohere Labs for Tiny Aya, and Kaggle and Hugging Face for compute.
