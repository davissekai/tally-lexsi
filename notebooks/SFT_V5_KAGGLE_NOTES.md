# Tally fine-tune v5 — Kaggle push notes

Pushed **13 Nov 2026, 9:19 AM Africa/Accra (UTC+0)** as kernel version 7 of `renhuang01/tally-sft`.

- Dataset: https://www.kaggle.com/datasets/renhuang01/tally-sft-v5 (new, private, version 1, ready). `renhuang01/tally-sft-curated` was not overwritten (last updated 12 Nov 2026, 10:51 PM Accra).
- Kernel: https://www.kaggle.com/code/renhuang01/tally-sft (private, GPU T4, internet on). Status after push: **QUEUED**, then **RUNNING** by 9:19 AM Accra.
- `renhuang01/tally-kaggle` was not touched (last run still 11 Nov 2026, 11:31 PM Accra).

## What changed vs v4

### Data
- Training data is the v5 set: **158 examples from 20 projects** (62 carried over from v4 + 96 new chunks from 13 Verra PDs). 130 have at least one value; 28 are all-`not stated` (17.7%).
- The notebook's `find_data_dir` still rglob-searches for `train_sft_messages.jsonl`. On v5 it loads **`train_sft_messages_rebalanced.jsonl`** when that file is present (same preference as v4). Both `train_sft_messages.jsonl` and `train_sft_messages_rebalanced.jsonl` are the same 158 rows (md5 `f2ed57bd0311784aa7844877a6052c08`).
- Validation is unchanged: the same 23 Miro (`2410`) + Bandai (`2929`) chunks, scored the same way against the same answer key / `tinyaya_scores.json`.
- Attached inputs are now `renhuang01/tally-sft-v5` and `renhuang01/tally-hf-token`. The HF token is still read from that private dataset (or the kernel secret) and is never printed.

### Training config
Only the schedule changed. Everything else matches v4:

| Setting | v4 | v5 |
|---|---|---|
| `NUM_EPOCHS` | 3 | **2** |
| `WARMUP_STEPS` | 3 | **6** |
| `warmup_ratio` (AlignTune and TRL) | 0.1 | 0.1 (unchanged) |
| Optimiser steps (approx.) | 62 × 3 / 8 ≈ 24 | 158 × 2 / 8 ≈ 40 |
| Precision | fp16, bf16 off | same |
| LoRA | r=16, α=32, dropout 0.05, targets `q_proj`, `k_proj`, `v_proj`, `o_proj` | same |
| Loss | answer span only (after `<\|START_RESPONSE\|>`) | same |
| Batch / accum / LR / max length / seed | 1 / 8 / 2e-4 / 8704 / 42 | same |
| Quantization | 4-bit NF4 QLoRA | same |
| Val / scoring | Miro + Bandai, base vs fine-tuned | same |

Two epochs and a short warmup are meant to limit the overfitting seen in v4 (train loss 0.54 → 0.20, val loss stuck at ~0.98, stated accuracy 3/13 → 0/13).

### Local check before push
Notebook JSON is valid (16 cells, nbformat 4). A local dry-run of the data cell resolved to `/workspace/tally/sft_v5/dataset`, loaded 158 train / 23 val rows, confirmed the two train message files are identical, and confirmed the val documents are only Miro and Bandai.

## Files
- Push folder: `/workspace/tally/sft_push_v5/` (`tally-sft.ipynb`, `kernel-metadata.json`, this note).
- Dataset upload copy: `/workspace/tally/sft_v5/kaggle_dataset/` (source files plus `dataset-metadata.json`; the original `/workspace/tally/sft_v5/dataset/` was not used as the upload root).
