# Tally labelling task (Claude Code)

This folder is a self-contained kit for labelling **real** Verra document chunks. You will do two passes:

1. **Labeller** — read each chunk, write one JSON line to `labels.jsonl`.
2. **Reviewer** — a fresh session or a separate subagent re-reads each labelled chunk and writes `review.jsonl`.

Do not start the reviewer pass in the same session as the labeller unless the user asks you to. The two passes should not share a long conversation history.

Read `RULES.md` before you label or review anything. Follow it exactly.

---

## What you must never do

- **Never invent documents, sentences, numbers, or quotes.** Every quote must be copied character-for-character from the chunk file.
- **Never edit** files in `chunks/` or `backlog/`. Never rename them. Never rewrite `chunks_index.csv`.
- **Never infer, convert, sum, round, or compute** a value. If it is not written in the chunk, it is `not_stated`.
- **Never use another chunk**, a previous label, or outside knowledge to fill a field.
- **Never dump all 809 chunks into context.** Work in small groups (about 5 chunks at a time). After each group, flush results to disk and move on. Do not re-read earlier chunk texts.
- **Ignore `backlog/`** unless the user explicitly asks you to label it after the 809 main chunks are done. Backlog files are optional and clearly marked.

---

## Files

| File | Role |
|---|---|
| `chunks_index.csv` | The work list, already in priority order. 809 rows. |
| `chunks/<safe_id>.txt` | One real chunk per file, with a short header then the text. |
| `RULES.md` | Field definitions, strict rules, schema, worked examples. |
| `labels.jsonl` | You append one JSON object per chunk here. |
| `progress.json` | You update this after each group so a later session can resume. |
| `review.jsonl` | Reviewer appends verdicts here. |
| `review_progress.json` | Reviewer progress, same idea as `progress.json`. |
| `check_quotes.py` | Optional local check: flags quotes that are not substrings of the chunk. |
| `backlog/` | Optional later work. Do not touch it unless asked. |

A chunk is already done if its `chunk_id` is in `progress.json`'s `completed_ids`, **or** if `labels.jsonl` already has a complete JSON line for that `chunk_id`. Skip it. Do not relabel it.

---

## Labeller pass

1. Read `RULES.md` and `progress.json`.
2. Open `chunks_index.csv`. The `order` column is the priority: rows 1… are batches 001–007 (already have v5 answer-key labels, most important), then 008–023, then 024–053 (worldwide).
3. Take the next **5** not-yet-done rows (fewer is fine near the end, or if a chunk is very long).
4. For each of those rows:
   - Read **only** that chunk file (the path is the `file` column) and, if you need to recap a rule, `RULES.md`.
   - Label every field from that chunk alone, following `RULES.md`.
   - **Append** one JSON line to `labels.jsonl` with `{chunk_id, fields, conflicts}`. All nine fields must be present. Use straight double quotes. Do not rewrite earlier lines in `labels.jsonl`.
5. After the group, add those `chunk_id`s to `progress.json`'s `completed_ids`, set `n_completed` to the new length, and optionally set `last_updated`. Keep existing completed ids.
6. Optionally run `python check_quotes.py` (on Windows, `py check_quotes.py` is also fine). If it flags a quote, fix **that line only** if the quote was mistyped, by copying it again from the chunk. If the value is simply not in the chunk, change the field to `not_stated`. Then move on.
7. Repeat from step 3 until every row in `chunks_index.csv` is done.
8. Stop. Print a short count: how many chunks labelled, how many remain, how many fields were values vs `not_stated`. Do not start the reviewer pass unless asked.

If you hit a usage limit, get an error, or the user stops you, just stop. Progress is on disk. The next session with the same kickoff prompt will resume from `progress.json` / `labels.jsonl`.

### Labeller line shape

```json
{"chunk_id": "1897_PD::chunk-014", "fields": {"baseline": {"value": "8,953,829", "quote": "Total 8,953,829 2,008,032 6,945,797 1,180,149 13% 902,954 5,727,542", "unit": "tCO2e"}, "additionality": "not_stated", "leakage": {"value": "1,180,149", "quote": "a total expected emission reduction of 5,727,542 t CO2e after accounting for leakage (1,180,149 t CO2e).", "unit": "tCO2e"}, "permanence_buffer": {"value": "13", "quote": "Total 8,953,829 2,008,032 6,945,797 1,180,149 13% 902,954 5,727,542", "unit": "%"}, "crediting_period": "not_stated", "area": "not_stated", "estimated_reductions": {"value": "5,727,542", "quote": "a total expected emission reduction of 5,727,542 t CO2e after accounting for leakage (1,180,149 t CO2e).", "unit": "tCO2e"}, "area_incl_leakage_belt": "not_stated", "estimated_reductions_pre_buffer": "not_stated"}, "conflicts": []}
```

See `RULES.md` for the full schema and three worked examples.

---

## Reviewer pass

Run this in a **new Claude Code session** in this folder, or as a **separate subagent** that does not inherit the labeller's conversation. Give it the reviewer kickoff prompt from `START_HERE.md`.

1. Read `RULES.md`, `labels.jsonl`, and `review_progress.json`.
2. A chunk is already reviewed if its `chunk_id` is in `review_progress.json`'s `completed_ids`, or if `review.jsonl` already has a complete review for that id. Skip it.
3. Take the next **5** labelled but not-yet-reviewed chunks.
4. For each one:
   - Read **only** that chunk file and `RULES.md`.
   - Re-check every field (including `not_stated` and `conflicts`) against the chunk and the rules.
   - Append to `review.jsonl`. Prefer **one JSON line per chunk** with a `reviews` array covering all nine fields. `verdict` is `accept`, `fix`, or `reject`. On `fix`, include the corrected `value`, `quote`, and `unit`. On `reject`, the field will become `not_stated`. Give a short `reason` every time.
5. After the group, update `review_progress.json` (`completed_ids`, `n_completed`, `n_total` = number of labelled chunks).
6. Optionally run `python check_quotes.py --review` (or `py check_quotes.py --review`) to flag corrected quotes that are not in the chunk. Fix those review lines if you mistyped a quote.
7. Repeat until every labelled chunk has been reviewed.
8. Stop. Print counts: accepted / fixed / rejected, and any chunks still unreviewed.

The reviewer must also never invent text or edit chunk files. Do not edit `labels.jsonl` during the review pass; corrections belong in `review.jsonl`.

---

## Resuming

It is always fine to stop and resume later. Use the same kickoff prompt in a new session in this folder. Trust `progress.json` / `review_progress.json` and the existing jsonl files. Do not start over.
