# Tally fine-tune v7 — run notes

These notes describe the v7 training run that this branch packages. They are not a live kernel log.

- Dataset: private Kaggle dataset `renhuang01/tally-sft-v7-data` version 1 (893 train / 157 val examples, plus the reserved 23-chunk Miro + Bandai scoring set). The JSONL is not in git; see [`data/curated_v7/README.md`](../data/curated_v7/README.md).
- Kernel: private `renhuang01/tally-sft` **version 9**, GPU T4, internet on. Pushed 14 Nov 2026, 8:39 PM Africa/Accra (UTC+0). Finished just before 3:00 AM on 15 Nov 2026. Wall time about **6.33 hours** (22,802 s), 224 optimiser steps, 2 epochs.
- `renhuang01/tally-kaggle` was not used or changed for this run.
- Training notebook in this repo: [`tally_sft.ipynb`](tally_sft.ipynb) (path-portable copy of the v7 kernel). The earlier v5 notebook is kept as [`tally_sft_v5.ipynb`](tally_sft_v5.ipynb).
- Held-out scoring notebook: [`tally_heldout.ipynb`](tally_heldout.ipynb), run as private kernel `renhuang01/tally-heldout` versions 1 (base) and 2 (v7) on 15 Nov 2026.

## Config

2 epochs, QLoRA r=16 / α=32 on `q_proj`, `k_proj`, `v_proj`, `o_proj` (~7.67M trainable parameters), answer-only loss, batch 1, gradient accumulation 8, learning rate 2e-4 with cosine decay, max length 8,704, seed 42, warmup_ratio 0.1 (about 22 steps).

## Losses

| | Train loss | Val (eval) loss |
|---|---|---|
| After step 1 | 1.094 | — |
| After epoch 1 | — | 0.123 |
| After epoch 2 / step 224 | 0.056 (last step); mean 0.125 | 0.116 |

Validation loss was still improving slightly at the end of epoch 2. This is unlike v4, where train loss fell to ~0.15–0.20 while val loss stalled near 0.98–1.00.

## Scores

See [`results/comparison_v7.json`](../results/comparison_v7.json) (Miro + Bandai) and [`results/heldout_scores.json`](../results/heldout_scores.json) (held-out aggregates only; gold answers are not in this repository).
