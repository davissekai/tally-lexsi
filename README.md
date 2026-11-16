# Tally

Tally reads Verra carbon-credit project documents and pulls out seven figures that decide whether a credit holds up: baseline, additionality, leakage, permanence buffer, crediting period, area and estimated reductions. Every value comes with the exact line it was taken from, or Tally says the document does not state it. It is a LoRA adapter on Cohere Labs' Tiny Aya Global (about 3B parameters), built for the Lexsi AI Safety Hackathon, Track 1.

## Problem

Forest carbon credits are sold on long, table-heavy documents where the figures that matter sit next to look-alikes: project area beside leakage-belt area, crediting period beside monitoring period, net beside gross reductions. A model that confidently picks the wrong one produces an audit that looks right and is not. For this job, inventing a number is the worst possible error.

## Approach

1. Split each document into overlapping chunks.
2. The fine-tuned model returns JSON for the seven fields, each with a verbatim quote or "not stated".
3. A rule-based merge keeps a value only if its quote is in the document, the number is in the quote and the unit fits. It then applies general Verra rules to choose between candidates, and reports a conflict instead of guessing when it still cannot choose.

Training data came from public Verra documents, labelled by teacher models, checked against the source text, curated with CuratorKIT, trained with AlignTune and checked with AuditKIT.

## Results

Three unseen projects, 20 stated values, all models in bf16 on one A100:

| Model | Stated values correct | Hallucinated values |
|---|---|---|
| **Tally v8** | **8/20** | 0 |
| Qwen3-8B | 6/20 | 0 |
| Tally v7 | 5/20 | 0 |
| Base Tiny Aya | 3/20 | 0 |
| Gemma 3 12B | 3/20 | 0 |

Scores use merge v2. With the original merge (v1), v8 scored 6/20 and base Tiny Aya 2/20. The test is small, so one answer is worth 5 points. The [write-up](WRITEUP.md) covers method, data, error analysis and limitations.

## Usage

```bash
pip install -r requirements.txt
export HF_TOKEN=...   # Tiny Aya Global is gated on Hugging Face
pdftotext -layout project.pdf project.txt
python inference/run_extraction.py project.txt
```

This writes `project.tally.json` with per-chunk answers and the merged record. To score against your own answer key:

```bash
python scorer/score_file.py --pred project.tally.json --key your_answer_key.json
```

## Links

- Write-up: [WRITEUP.md](https://github.com/davissekai/tally-lexsi/blob/main/WRITEUP.md)
- Adapter: [renhuang001/tally-v8-lora](https://huggingface.co/renhuang001/tally-v8-lora)
- Models: [Tally models collection](https://huggingface.co/collections/renhuang001/tally-models-6afa44295934fb19bb00fbb4)
- Data and logs: [Tally data and logs collection](https://huggingface.co/collections/renhuang001/tally-data-and-logs-6afa44297c71d80cb8aca723)

Code is MIT licensed. The adapters follow Tiny Aya's CC-BY-NC-4.0 (non-commercial) license.
