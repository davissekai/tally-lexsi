# Tally v8 training plan: one A100 on Hugging Face Jobs (DRAFT, nothing launched)

Status: draft only. Nothing has been uploaded, launched or spent. Every step marked **[needs Renhuang's yes]** spends credit or publishes data.

## Hardware and budget

- Flavor `a100-large`: 1x A100 80 GB, 12 vCPU, $2.50/hr, billed per minute while Starting/Running (https://huggingface.co/docs/hub/jobs-pricing). Credit available: about $20 (about 8 GPU-hours), to be confirmed on https://huggingface.co/settings/billing.
- HF Jobs has no 2x A100 flavor (1x, 4x at $10/hr, 8x at $20/hr). For a set of about 5k examples, 4x A100 would finish about 3x faster for about the same total cost, and needs multi-GPU (DDP) code. **One A100 is the right choice.**
- Default Job timeout is 30 minutes, so always pass `--timeout`.

## Expected data (after a full labelling run)

Estimated from the dry run on 1,200 chunks: about 4,500 to 5,500 train examples, about 600 to 800 val examples. Mean of about 1,560 tokens per example (prompt plus chunk plus answer), max about 3,300 (`ingest_v8.py` drops anything over 4,096). That is about 7 to 8.5M tokens per epoch.

## Configuration (changes from v7 in bold)

| setting | v7 (Kaggle T4) | v8 (A100 80 GB) | why |
|---|---|---|---|
| precision | 4-bit QLoRA, fp16 | **bf16 LoRA, no 4-bit** | 3.35B in bf16 is about 7 GB, so it fits easily. No dequantisation means faster steps and slightly better quality |
| LoRA rank / alpha | r16 / α32 | **r32 / α64**, dropout 0.05 | more capacity for the new conflict-resolution behaviour |
| target modules | q,k,v,o | **q,k,v,o + gate,up,down** | MLP adapters help factual-pattern learning; the run prints the exact trainable count |
| max sequence | 8,704 | **4,096** | v8 chunks are smaller; nothing is cut (ingest drops anything over) |
| batch | 1 x accum 8 | **8 x accum 2 = 16**, `group_by_length=True` | GPU utilisation; similar-length batches cut padding |
| LR / schedule | 2e-4, warmup 0.1 | **1e-4 cosine, warmup 0.05** | larger rank + all-linear targets; lower LR is safer |
| epochs | 2 | **up to 3, with early stopping** | best checkpoint by val loss decides, not the epoch count |
| loss | answer only | answer only (`completion_only_loss` / assistant-only mask) | same |
| eval / save | per epoch | **every ~0.25 epoch** (`eval_steps = save_steps ≈ steps_per_epoch/4`) | finer checkpoint choice |
| best checkpoint | load_best_model_at_end | `load_best_model_at_end=True`, `metric_for_best_model="eval_loss"`, `greater_is_better=False`, `save_total_limit=3`, `EarlyStoppingCallback(early_stopping_patience=3)` | stop when val loss stops improving for 3 evals |
| seed | 42 | 42 | same |
| gradient checkpointing | on | **off** (turn on only if OOM) | speed; 80 GB is plenty at batch 8 x 4k |

Best-val-checkpoint selection, in plain terms: the val set is a project-group split (no project in both sets), so `eval_loss` measures generalisation to unseen projects. We keep the checkpoint with the lowest `eval_loss`. If the best one is the last eval, val loss was still falling, and a later run could go one more epoch. If val loss rises for 3 evals in a row, training stops early. The v4 pattern (train about 0.2, val about 1.0) would show up as exactly that rise.

## Time and cost estimate (per run)

- Training: about 25 to 35 min per epoch (about 6 to 8k tokens/s for LoRA on a 3.35B model on an A100), so 3 epochs take about 1.5 to 1.75 h including evals.
- Rescoring: base vs v8 on the Miro+Bandai prompts with v8 chunks, plus the v7 23-chunk set for comparison: about 20 to 30 min with greedy `generate`.
- Total about 2 to 2.5 h, about **$5 to $6.25**. Use `--timeout 3h` (hard cap $7.50).
- Budget plan: run A, as above. Run B only if needed (for example 1 more epoch, or r16 if run A overfits). Keep at least $5 spare. Held-out test: once, on the final chosen adapter only, with prompts from `/workspace/tally/heldout_v8/` (v8 chunking), on a T4 (`t4-small`, $0.40/hr) or the same A100 job.

## Steps (none done yet)

1. Labelling run, then `python3 /workspace/tally/antigravity_v8/ingest_v8.py <tally_v8_return.zip>`, giving `/workspace/tally/curated_v8/` (box only).
2. **[needs Renhuang's yes]** Check the credit balance on the billing page.
3. **[needs Renhuang's yes]** Upload `curated_v8/` as a **private** HF dataset (for example `renhuang001/tally-sft-v8-data`). This does not include held-out data.
4. Adapt `sft_push_v7/tally-sft.ipynb` into a `uv` script `train_v8.py` (PEP 723 header: torch, transformers>=5, trl, peft, datasets, accelerate). It keeps the v7 loading, scoring and merge code unchanged. The only changes are the config table above, reading the dataset from the Hub, and pushing the adapter to a private model repo at the end. HF_TOKEN comes from `--secrets HF_TOKEN` and is never printed.
5. **[needs Renhuang's yes]** Launch:
   `hf jobs uv run --flavor a100-large --timeout 3h --secrets HF_TOKEN train_v8.py`
   Monitor with `hf jobs logs <id>`. Cancel with `hf jobs cancel <id>` if loss diverges.
6. Read `comparison.json` (base vs v8 on Miro+Bandai). If better than v7, run the held-out test once.

## Inference note

v8 is trained on v8 chunks, so the extraction notebook and the held-out run must chunk documents with `v8lib.chunk_document` (section line, page markers, whitespace normalised). Feeding it v7 fixed-size chunks would understate the result. The v7 23-chunk Miro+Bandai set is kept only as a continuity check.
