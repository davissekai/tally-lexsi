> The 53 `batch_###.txt` prompt files and the two zip archives are **not** in this repository (each batch is ~200 KB of document text). Rebuild them with `src/opus/build_batches.py` and `src/opus/build_wide_batches.py` after you have downloaded and chunked the PDFs. The instruction header is saved here as `prompt_template.txt`.

# Tally: labelling with Claude Opus (claude.ai)

53 batches in total. Batches 001–023 are 359 chunks from the 13 new project descriptions; batches 024–053 are a ranked worldwide extension (see below). Each batch is one self-contained prompt: instructions, then 15 to 17 chunks, about 60k to 75k tokens.

**Do them in order.** Batches 001 to 007 hold all 78 chunks we already know contain values, so they're the most valuable. Every batch also mixes in 3 chunks that are probably empty, so the model also learns to say "not stated".

## On your iPhone, per batch

1. Open the **Claude** app, start a **new chat**, and pick **Opus** in the model menu.
2. Tap **+**, then **Add files** (or **Files**), and choose `batch_001.txt`. Don't paste it: at about 220 KB it's too long to paste.
3. Send it with no other text needed (or just type "go").
4. Wait for the reply. It should be one ```json code block.
   - If it ends with **CONTINUE**, type `continue` and send. Copy both code blocks.
5. Copy the reply with the copy button on the code block, and do one of these:
   - **Easiest:** paste it into the Grok Bot chat with a line saying `reply 001`, and Indi saves it as `replies/reply_001.json`.
   - Or save it as `reply_001.json` (and `reply_001_part2.json` if there was a continue) and send the file.
6. Next batch, **in a new chat** each time, so earlier batches don't eat into the context or your usage.

Mess-ups are fine: extra text around the JSON, a missing comma, or a cut-off reply all get handled. Anything that doesn't check out is dropped, never guessed.

**Usage limits:** Claude Pro caps how much Opus you can use in each 5-hour window, and each batch is a big message. If Claude says you've hit the limit, stop and carry on after it resets. Whatever batches are done can be used straight away.

## Batches

| Batch | Chunks | Est. input tokens | File size | Priority |
|---|---:|---:|---:|---|
| 001 | 16 | ~69k | 217 KB | high: 13 known-value chunks |
| 002 | 15 | ~68k | 212 KB | high: 12 known-value chunks |
| 003 | 16 | ~71k | 223 KB | high: 13 known-value chunks |
| 004 | 15 | ~69k | 215 KB | high: 12 known-value chunks |
| 005 | 15 | ~71k | 222 KB | high: 12 known-value chunks |
| 006 | 15 | ~70k | 219 KB | high: 12 known-value chunks |
| 007 | 15 | ~64k | 201 KB | high: 4 known-value chunks |
| 008 | 16 | ~66k | 206 KB | keyword-ranked |
| 009 | 16 | ~73k | 228 KB | keyword-ranked |
| 010 | 16 | ~68k | 211 KB | keyword-ranked |
| 011 | 16 | ~71k | 222 KB | keyword-ranked |
| 012 | 16 | ~70k | 219 KB | keyword-ranked |
| 013 | 16 | ~72k | 224 KB | keyword-ranked |
| 014 | 16 | ~70k | 218 KB | keyword-ranked |
| 015 | 15 | ~67k | 209 KB | keyword-ranked |
| 016 | 16 | ~75k | 235 KB | keyword-ranked |
| 017 | 15 | ~72k | 224 KB | keyword-ranked |
| 018 | 15 | ~72k | 226 KB | keyword-ranked |
| 019 | 17 | ~69k | 215 KB | keyword-ranked |
| 020 | 15 | ~70k | 219 KB | keyword-ranked |
| 021 | 15 | ~65k | 202 KB | keyword-ranked |
| 022 | 15 | ~59k | 185 KB | keyword-ranked |
| 023 | 17 | ~72k | 224 KB | keyword-ranked |

Token counts are estimates at about 3.2 characters per token, with no Claude tokenizer offline. Each reply should come to about 3k to 8k tokens.

## What happens to the replies (Indi's side)

`python3 ingest.py` reads `replies/*`. For every value it checks that (1) the quote is copied exactly from that chunk, with only spacing allowed to differ; (2) the value appears in the quote; and (3) the unit fits the field (buffer %, leakage tCO2e, area ha). Values that fail are dropped and logged in `ingest_log.jsonl`. The outputs are `opus_labels.jsonl`, `disagreements.md`/`.csv` (Opus vs the v5 labels) and `ingest_summary.json`. `python3 test_ingest.py` runs a self-test on a fake reply.

## Adding new documents later

Batches 024–053 are already built (see the worldwide section below). Do not re-run `build_batches.py --text-dir` on `text_wide/`: that would try to batch the whole 2,154-chunk corpus. Further waves should be taken from `backlog_wide.jsonl` (rank order; also stored in `chunks_registry.jsonl` with `"batched": false`) and will continue from 054. Use `build_wide_batches.py` (ranked, spread across project-groups, cap 30 batches). `build_batches.py --text-dir DIR` still works for a *new* folder of texts: it uses the same Tiny Aya chunker (3,500 tokens, 300 overlap), never renumbers existing batches or chunk ids, and skips validation (Miro 2410, Bandai 2929) and held-out (5172, 5432, 4329) projects. Every chunk is recorded in `chunks_registry.jsonl`, and `manifest.json` maps each batch to its chunk ids. Each registry row has a `project_group` so a later train/val split can keep near-template families together.

## Worldwide extension (batches 024+)

30 further batches, 450 chunks, taken from the worldwide documents (2154 chunks in total from 80 files / 56 projects / 47 project-groups). Existing batches 001–023 and their chunk ids are unchanged.

These are the **highest-ranked** chunks for containing one of the seven fields (same keyword and number score as 001–023), spread so no project or near-template family dominates. Each batch mixes in 3 chunks that are probably empty. The remaining 1704 unbatched chunks are in `backlog_wide.jsonl` (rank order) and in `chunks_registry.jsonl` with `"batched": false`, so later waves can pick them up without re-chunking.

**Template families** (one `project_group`, kept together in a later train/val split): 977+981 (Portel-Pará), 959+960+961+962 (Carbosur Uruguay), 737+899+993 (TIST Kenya/Uganda), 1847+1855+1865+2070 (Shanghai Libra China).

Do 001–007 first if you have not already. Then these, still **one new Claude chat per batch**, attaching the `.txt` file (don't paste). Estimated input per batch is about 57k–70k tokens, same as before, so Pro's 5-hour window will still only allow a few batches at a time.

The phone-friendly zip of just this wave is `batches_wide.zip`. `batches_all.zip` has 001–023 plus 024+.

| Batch | Chunks | Est. input tokens | File size | Priority |
|---|---:|---:|---:|---|
| 024 | 15 | ~62k | 196 KB | wide ranked, 3 likely-empty |
| 025 | 15 | ~59k | 187 KB | wide ranked, 3 likely-empty |
| 026 | 15 | ~65k | 204 KB | wide ranked, 3 likely-empty |
| 027 | 15 | ~67k | 212 KB | wide ranked, 3 likely-empty |
| 028 | 15 | ~61k | 191 KB | wide ranked, 3 likely-empty |
| 029 | 15 | ~64k | 201 KB | wide ranked, 3 likely-empty |
| 030 | 15 | ~65k | 204 KB | wide ranked, 3 likely-empty |
| 031 | 15 | ~69k | 216 KB | wide ranked, 3 likely-empty |
| 032 | 15 | ~61k | 192 KB | wide ranked, 3 likely-empty |
| 033 | 15 | ~66k | 207 KB | wide ranked, 3 likely-empty |
| 034 | 15 | ~60k | 188 KB | wide ranked, 3 likely-empty |
| 035 | 15 | ~61k | 191 KB | wide ranked, 3 likely-empty |
| 036 | 15 | ~63k | 200 KB | wide ranked, 3 likely-empty |
| 037 | 15 | ~61k | 193 KB | wide ranked, 3 likely-empty |
| 038 | 15 | ~68k | 214 KB | wide ranked, 3 likely-empty |
| 039 | 15 | ~66k | 207 KB | wide ranked, 3 likely-empty |
| 040 | 15 | ~67k | 210 KB | wide ranked, 3 likely-empty |
| 041 | 15 | ~57k | 178 KB | wide ranked, 3 likely-empty |
| 042 | 15 | ~66k | 209 KB | wide ranked, 3 likely-empty |
| 043 | 15 | ~66k | 208 KB | wide ranked, 3 likely-empty |
| 044 | 15 | ~70k | 220 KB | wide ranked, 3 likely-empty |
| 045 | 15 | ~60k | 190 KB | wide ranked, 3 likely-empty |
| 046 | 15 | ~65k | 206 KB | wide ranked, 3 likely-empty |
| 047 | 15 | ~62k | 195 KB | wide ranked, 3 likely-empty |
| 048 | 15 | ~62k | 195 KB | wide ranked, 3 likely-empty |
| 049 | 15 | ~60k | 188 KB | wide ranked, 3 likely-empty |
| 050 | 15 | ~64k | 203 KB | wide ranked, 3 likely-empty |
| 051 | 15 | ~70k | 221 KB | wide ranked, 3 likely-empty |
| 052 | 15 | ~62k | 195 KB | wide ranked, 3 likely-empty |
| 053 | 15 | ~68k | 214 KB | wide ranked, 3 likely-empty |

Token counts are the same 3.2 characters-per-token estimate as batches 001–023.
