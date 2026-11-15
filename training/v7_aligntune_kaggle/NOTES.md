# Tally fine-tune v7 — Kaggle push notes

Pushed **14 Nov 2026, 8:39 PM Africa/Accra (UTC+0)** as kernel version 9 of `renhuang01/tally-sft`.

- Dataset: https://www.kaggle.com/datasets/renhuang01/tally-sft-v7-data (new, private, version 1, ready). Existing datasets were not overwritten.
- Kernel: https://www.kaggle.com/code/renhuang01/tally-sft (private, GPU T4, internet on, 12-hour timeout). Status after push: **RUNNING**.
- Queued kernel version 8 (v6 data) did not stop on its own after the v9 push, so it was cancelled. Status: **CANCEL_ACKNOWLEDGED**. Version 9 kept running.
- `renhuang01/tally-kaggle` was not touched (last run still 11 Nov 2026, 11:31 PM Accra).

## Data

- Source: quote-checked Claude Code labels (all 809 chunks, unreviewed) plus 58 unique non-overlapping v5 examples (Kasigau, Mai-Ndombe, Bale). New labels replaced 96 overlapping v5 chunks. 716 stated 7-field quotes passed the in-chunk check; 3 chunks were trimmed.
- Full-extraction: 407 positive + 136 empty (25.0%).
- Single-field were capped for T4 runtime: 801 stated + 200 not_stated down to 406 + 101, for 1050 examples total.
- Train: 893 examples from 44 project groups. Val: 157 examples from 8 project groups (1055, 1340, 1622, 1740, 1775, 562, 737_899_993, 977_981), 14.95%. No project in both.
- Held-out 5172, 5432, 4329, 2928 excluded. Miro (2410) and Bandai (2929) reserved for document-level scoring (same 23 chunks and answer key as v4/v5).
- Files: `/workspace/tally/curated_v7/` and the Kaggle upload copy `/workspace/tally/sft_v7/kaggle_dataset/`.

## Training config

2 epochs, same QLoRA as v5 (r=16 / α=32 on q/k/v/o, answer-only loss, batch 1 / accum 8 / LR 2e-4 / max length 8704 / seed 42). TRL-fallback `WARMUP_STEPS` is 22 (`warmup_ratio` 0.1 on ~223 optimiser steps).

Estimated runtime: about 4.5–6 hours (roughly 3.5–5 hours of training plus 15–25 minutes to rescore Miro and Bandai).
