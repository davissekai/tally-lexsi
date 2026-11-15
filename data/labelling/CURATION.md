# CuratorKIT and the Tally fine-tuning set

This note is about the research process, not the code. The short version: we turned the nine labelled documents into a training set Tiny Aya can learn from, then ran that set through Lexsi’s CuratorKIT. No examples were thrown out. Nothing was pushed to Kaggle, GitHub or Hugging Face.

## What CuratorKIT actually is

CuratorKIT is Lexsi Labs’ open-source library for building post-training datasets (the same group as AlignTune and AuditKIT). The official sources are:

- Code: [github.com/Lexsi-Labs/CuratorKIT](https://github.com/Lexsi-Labs/CuratorKIT)
- Docs: [lexsi-labs.github.io/CuratorKIT](https://lexsi-labs.github.io/CuratorKIT/)
- Papers: [arXiv:2606.21631](https://arxiv.org/abs/2606.21631) (library) and [arXiv:2606.11127](https://arxiv.org/abs/2606.11127) (gating and recovery)
- Installed here: CuratorKIT 0.1.27 from PyPI, in `/workspace/tally/.venv-curator`

Its full pipeline can also *generate* synthetic questions and answers with an LLM, then check that each answer is grounded in the source chunk, score quality, and try to repair failures. We did **not** use that half. We already have an answer key, and calling a paid generator would cost money and invent new answers we have not checked.

What we did use is the part that needs no API key: ingest a dataset, check that each row has the right shape and length, remove exact and near-duplicates, clean the text, and export trainer-ready files (Alpaca, ShareGPT, and the chat `messages` format that AlignTune and TRL’s SFT trainer consume).

We also left three optional hygiene gates off, on purpose:

- **PII replacement** would have swapped names in the documents for fake ones, which would have rewritten the gold quotes the model is supposed to copy.
- **Toxicity filtering** flags words like “illegal logging” even when they are ordinary conservation text.
- **Secrets detection** was not needed; these are public Verra PDFs.

Those gates are real CuratorKIT features. We skipped them because they would have hurt this particular dataset, not because they were missing.

## How the training examples were built

Tiny Aya is trained at *chunk* level, which is how it already extracts: it reads one 3,500-token window at a time and fills in the seven fields. The job of the fine-tune is to teach it two habits:

1. When the gold value is actually in this window, copy that value and its quote.
2. When it is not, say `"not stated"` instead of guessing. This is the important one. The raw model already finds numbers; it struggles to choose, and sometimes invents.

For each of the 131 chunks from the nine documents we already ran:

- The *input* is the same extraction prompt used on Kaggle, plus the chunk text.
- The *target* is a JSON object with all seven fields, taken from the answer key.

A field is labelled with the gold value only if the chunk actually supports it: the gold quote appears in the chunk, or the distinctive number (with its units) does. Short, common figures such as `10%` or `0 tCO2e` also need a nearby cue word (for example “buffer” or “leakage”), so a random “10%” in a land-use table is not treated as the permanence buffer. Otherwise the field is `"not stated"`. Fields the answer key itself marks as not stated stay not stated in every chunk.

The three held-out documents (5172, 5432, 4329) were left out entirely. They have not been extracted yet, and they are reserved to test whether the fine-tune generalises.

One practical wrinkle: the original windows were cut with Tiny Aya’s own tokenizer, which is gated on Hugging Face and was not available on this machine. We therefore rebuilt the same number of windows per document (21 + 13 + 10 + 12 + 2 + 31 + 1 + 11 + 30 = 131) with a character-span tokenizer calibrated so each file still has the same chunk count, at about four characters per token. The boundaries will not be identical to the Kaggle run, but they cover the same documents at the same grain.

## Train and validation were split by project, not by chunk

If we had shuffled chunks at random, text from the same report — and worse, from Kasigau I’s two files or Kasigau II’s three files, which repeat the same figures — would have leaked into both sides. The model could then “succeed” on validation by memorising a number it had already seen.

So the split is at project level:

- **Validation (23 chunks):** Miro (2410) and Bandai Hills (2929). One verification report and one validation report, no shared numbers with the training projects.
- **Training (108 chunks):** Bale, Kasigau I (both documents), Kasigau II (all three documents), and Mai-Ndombe.

That is about 18% validation, which is a reasonable share of a small set.

## Dataset counts (before and after curation)

These counts did not change in curation, because CuratorKIT kept every row. They are the labelled set itself.

| | Train | Validation | Total |
|---|---:|---:|---:|
| Examples (chunks) | 108 | 23 | 131 |
| With at least one gold value in the chunk | 51 | 21 | 72 |
| All seven fields “not stated” (negatives) | 57 | 2 | 59 |

Positives and negatives per field, out of 131 chunks:

| Field | Positive (gold value in the chunk) | Negative (“not stated”) |
|---|---:|---:|
| baseline | 22 | 109 |
| additionality | 5 | 126 |
| leakage | 18 | 113 |
| permanence_buffer | 25 | 106 |
| crediting_period | 19 | 112 |
| area | 33 | 98 |
| estimated_reductions | 23 | 108 |

Two things stand out, and both are features of the documents rather than bugs:

- **Additionality is rare.** Only four of the nine documents restate an additionality tool or conclusion, and it only appears in five chunks. The model will see “not stated” for this field far more often than a real answer. That is honest — monitoring reports often do not repeat the original additionality test — but it means we should not expect a big jump on additionality after a fine-tune of this size.
- **Validation has only two all-negative chunks.** Miro and Bandai mention at least one of the seven fields on almost every window. Training is better balanced (51 positives, 57 negatives), so the model still sees plenty of “say not stated” practice. We did not downsample or rebalance: 131 examples is already small, and throwing negatives away would weaken the abstention lesson.

## What CuratorKIT did, step by step

The run used only the official Python API (`Curator` + `CuratorConfig`), with no generation and no random shuffle. The logged steps, from `manifest.json`, were:

1. **Ingest.** It read the 131 labelled rows from a JSONL file. All 131 parsed.
2. **Schema check.** It checked that each row had an instruction and an output, and that the text was between 10 and 8,192 tokens (the upper bound has to be high, because each example already contains a 3,500-token chunk plus the prompt). All 131 passed. Nothing was too short or too long.
3. **Exact deduplication.** It hashed each example (ignoring the shared prompt, so it was really comparing the chunk and the target JSON). No two rows were identical. 131 remained.
4. **MinHash near-deduplication.** This catches paraphrases and heavy overlap, using a Jaccard threshold of 0.85, which is CuratorKIT’s documented default. Overlapping windows share only 300 of 3,500 tokens, so they are not near-duplicates, and the Kasigau files that repeat the same area figure still have different surrounding text. Nothing was removed. 131 remained.
5. **Text cleaning.** Unicode normalisation, encoding fixes, whitespace cleanup, and control-character removal. We turned off HTML-tag stripping: the extraction prompt itself contains placeholders such as `<number> hectares`, and CuratorKIT’s default cleaner treats those as tags and deletes them. With stripping off, the prompt the model will train on is the same prompt it will see at inference.

Result: **131 in, 131 out, 0 rejected.** That is not a failure of CuratorKIT. It is evidence that the set we handed it was already clean, one example per chunk, with no accidental copies. The provenance files (manifest, dataset card, checksums, `lexsi_provenance.json`) are still useful for the write-up: they record exactly what was done.

CuratorKIT can also split train/val itself, but it shuffles rows at random. We did not use that, because of the leakage issue above. We assigned the splits first, then exported them afterwards.

## Where the files are

All under `/workspace/tally/`:

- `CURATION.md` — this note
- `build_and_curate.py` — the script that built the set and called CuratorKIT
- `curated/train/sft_messages.jsonl` and `curated/val/sft_messages.jsonl` — the files to fine-tune with (chat format for AlignTune / TRL)
- `curated/train/sft_alpaca.jsonl` and `curated/val/sft_alpaca.jsonl` — the same rows in Alpaca format
- `curated/train/sft_with_metadata.jsonl` and `curated/val/sft_with_metadata.jsonl` — same rows plus document name, chunk index, which fields are positive, and why
- `curated/curatorkit_run/` — CuratorKIT’s own output, including `manifest.json`, `dataset_card.md`, `lexsi_provenance.json`, `checksums.txt`, and the unsplit 131-row exports
- `curated/raw/sft_raw.jsonl` and `curated/raw/stats.json` — the labelled set before cleaning
- `curated/stats_before.json` and `curated/stats_after.json` — counts before and after curation
- `ground_truth/answer_key.json` — the answer key the labels came from

Nothing in this folder has been pushed anywhere.

## Recommended next step: AlignTune on a Kaggle T4

AlignTune is the Lexsi fine-tuning library ([github.com/Lexsi-Labs/aligntune](https://github.com/Lexsi-Labs/aligntune)). CuratorKIT’s `sft_messages` export is one of its native inputs. A run on Kaggle should look like this:

- **Model:** `CohereLabs/tiny-aya-global`, the same 3.35B model we extract with.
- **Method:** LoRA or QLoRA supervised fine-tuning, not a full-weight update. A full Adam run on 3.35B would not fit comfortably next to a 4,000-token context on a 16 GB T4.
- **Data:** `curated/train/sft_messages.jsonl` for training, `curated/val/sft_messages.jsonl` for the validation loss. Use the `sft_messages` config, which is what TRL’s `SFTTrainer` expects.
- **Context length:** keep 8,192 (Tiny Aya’s window). Each example is roughly the 3,500-token chunk plus a short prompt and a short JSON answer, so about 4,000–4,500 tokens in total. That fits, but only with a micro-batch of 1.
- **GPU:** one T4 (16 GB) is enough. Tiny Aya in float16 is about 7 GB; LoRA adapters and a 4,000-token batch of 1, with gradient checkpointing, should leave headroom. QLoRA in 4-bit (~2–2.5 GB for the frozen weights) is the safer option if memory is tight. The second T4 on the Kaggle machine can stay unused unless we later decide to extract in parallel.
- **Schedule:** 1 or 2 epochs, not more. There are only 108 training examples, so three long epochs will memorise them. Watch the validation loss and stop when it flattens or rises. A LoRA rank of 16 (or 32) and a light dropout (0.05–0.1) are a reasonable starting point. Effective batch size of 8 via gradient accumulation, learning rate around 1e-4 to 2e-4 for LoRA, is typical.
- **Time:** on the order of 15–40 minutes for 1–2 epochs, much less than the 71-minute extraction run.
- **Backend:** AlignTune’s TRL backend, which Kaggle already has the stack for. Unsloth is faster and more memory-efficient, but only if it installs cleanly on that machine; it is optional.
- **After training:** run the fine-tuned model on the same nine documents and compare the 38% / 23% scores against the answer key. The honest test is still the three held-out documents, once those have been extracted with the same prompt. Then, if there is time, AuditKIT can score the same outputs in a form Lexsi will accept.

Do not push the fine-tuned weights, the dataset, or a Kaggle notebook with `kaggle kernels push` unless you ask to. The usual rule about the HF token still applies.
