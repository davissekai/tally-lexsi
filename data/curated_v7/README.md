# Tally SFT v7 dataset (rebuild notes)

The v7 training and validation JSONL files are **not in git**. They contain long verbatim excerpts from copyrighted project documents and are about 100 MB together. They live on the private Kaggle dataset `renhuang01/tally-sft-v7-data`.

Rebuild from a working tree that has the quote-checked labels, the chunk registry, the v5 leftovers, and a Tiny Aya `tokenizer.json`:

```bash
export TALLY_ROOT=/path/to/working/tree
export TALLY_TOKENIZER=/path/to/tokenizer.json   # if it is not under $TALLY_ROOT/sft_out
python src/build_v7.py
```

## Contents of the built set

- Full-extraction examples use the same 7-field prompt and answer JSON as v5.
- New labels (809 chunks, quote-checked, unreviewed) replace overlapping v5 labels.
- Non-overlapping unique v5 examples (Kasigau, Mai-Ndombe, Bale) are carried over (58 examples).
- Single-field question examples: one per stated field, plus a modest sample of not_stated fields, capped so two T4 epochs stay under ~6 hours.
- Empty full examples are at most 25% of the full-extraction set.
- Held-out projects 5172, 5432, 4329, 2928 are excluded. Miro (2410) and Bandai (2929) stay out of train/val and ship as a reserved 23-chunk eval set (`val_miro_bandai_*.jsonl`) so the notebook can score them against `data/answer_key.json`.
- Train/val split is by `project_group` (~15% val). No project appears in both.

Train: **893 examples from 44 project groups**.  
Val: **157 examples from 8 project groups** (1055, 1340, 1622, 1740, 1775, 562, 737_899_993, 977_981).

See `stats.json` for the field and project breakdown.
