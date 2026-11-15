# Tally v8: label real document chunks and build the SFT sets (execution only)

You are executing a fixed procedure. **Every design decision is already made.** Do not redesign, improve, or "optimise" anything. Run the given commands, label each chunk by reading it, fix what the validator reports, and hand back the zip.

Run every command from this folder (the one containing this TASK.md). Use `python`; if that is not found, use `py` (Windows) or `python3`. Python 3.9 or newer, standard library only, no installs.

## Never do these

1. Never write, generate or run any code, script or regex of your own, and never label with a program. Every label comes from **you reading the chunk**. The only commands you run are the `python tools/...` commands in this file.
2. Never edit, rename, move or delete anything in `tools/`, `sources/`, `expected/`, `schema/`, `work/`, `RULES_V8.md` or `TASK.md` (the tools themselves write `work/validation_report.json`; that is expected).
3. Never invent, guess, compute, convert, round or sum a value. Never use outside knowledge or other chunks.
4. Never add documents or text from anywhere else. Never search the web for these projects.
5. Never label a chunk twice or change the batch order. Never put more or fewer lines in a labels file than the batch lists.
6. Never upload these files anywhere. The only output leaves via `tally_v8_return.zip` (step 7), which you hand to Renhuang.

## Step 1: chunk the documents (once)

```
python tools/chunk_v8.py
```

It re-runs the chunker on `sources/` and checks the result against the shipped, canonical chunks in `work/`. It must end with:
- `OK: 7720 chunks in total, 2250 to label in 282 batches of up to 8.`

Before that line it prints either `Manifest matches expected/manifest_expected.json` (normal) or a `NOTE:` that this computer's output differs slightly. Both are fine: the shipped `work/` files are used either way.

If it prints `CHUNKER FAILED` or `STOP`, **stop**: write the exact output into `AGENT_NOTES.md` and tell Renhuang. Do not continue.

## Step 2: read the rules

Read `RULES_V8.md` completely. Re-read sections 2 and 3 whenever unsure.

## Step 3: label, one batch at a time, in order

Repeat this loop:

1. `python tools/next_batch.py` prints `NEXT batch_NNNN` with the file to read and the file to write, or `ALL DONE`.
2. Open **only** `work/batches/batch_NNNN.md`. It lists 8 chunk ids, then each chunk: a header, some HINT lines, and the text between `<<<TEXT` and `TEXT>>>`.
3. For each chunk, in the listed order, apply RULES_V8.md to its text: all nine fields, then the conflict procedure (section 3) for every field.
4. Create `labels/batch_NNNN.jsonl` with exactly one JSON line per chunk, in the listed order (RULES_V8.md section 4).
5. `python tools/validate_v8.py --batch NNNN`
6. If it prints `ERROR` lines, fix **only** the lines named, using the fix table below, then run step 5 again. Repeat until it prints `VALID: 0 errors`.
7. Go back to 1.

Every 20 batches, run the full check `python tools/validate_v8.py` and fix anything it reports before continuing.

### Fix table (do exactly this)

| validator says | do this |
|---|---|
| `quote is not an exact substring of the chunk text` | Find the passage in the chunk text and copy it again, character for character, one space at each line break. Second failure: use a shorter contiguous piece of the same passage that still contains the value. Third failure: set that field to `"not_stated"` (or delete that conflict item). |
| `value ... is not an exact substring of its quote` | Make `value` exactly the characters as they appear inside the quote. |
| `crediting_period value must contain a start year and an end year` | If the chunk gives both years, put the full date span in `value` (and in the quote). Otherwise set `crediting_period` to `"not_stated"`. |
| `unit ... not allowed` | Use one of the units the message lists. |
| `value must contain a number` / `value must be just the number` | Put only the number as written in `value`; the unit goes in `unit`. If there is no number, set the field to `"not_stated"`. |
| `quote has N words (max 50)` | Use a shorter contiguous piece of the same passage that still contains the value. |
| `conflict value equals the chosen value` | Delete that conflict item. |
| `R_PRE_BUFFER used, so fill estimated_reductions_pre_buffer` | Fill `estimated_reductions_pre_buffer` with that figure, its quote and unit `tCO2e`. |
| `R_AREA_INCL_BELT used, so fill area_incl_leakage_belt` | Fill `area_incl_leakage_belt` with that figure, its quote and unit `ha`. |
| `N conflicts listed; at most 4` | Keep the first 4 conflict items for that field in order of appearance in the text; delete the rest. |
| `code ... not allowed for <field>` | Use a code from the list in the message (RULES_V8.md section 3). |
| `invalid JSON` | Rewrite that line as valid JSON; escape `"` inside text as `\"`. |
| `has N non-empty lines, expected exactly 8` / `chunk_id ... must be` | One line per chunk id, in the batch order. |
| `pick_rule` or other unknown keys | Remove the extra keys. Stated fields have exactly `value`, `quote`, `unit`. |
| anything else | Follow the message literally. If it still fails after 3 tries, set the named field to `"not_stated"` and delete its conflicts. |

### Pace and stopping

- Do all 282 batches if you can. The minimum for a usable result is **batches 0001 to 0140 complete and valid, with no gaps**.
- If you must stop (limits, time), stop after a batch shows `VALID: 0 errors`. To resume later, start again from step 3 (`next_batch.py` finds where you were). Never re-run step 1 after labelling has started.

## Step 4: full label check

```
python tools/validate_v8.py
```
Fix until it prints `VALID: 0 errors`.

## Step 5: build the train and val sets

```
python tools/build_sets_v8.py
```
This writes `out/train_sft_messages.jsonl`, `out/val_sft_messages.jsonl`, `out/train_with_metadata.jsonl`, `out/val_sft_with_metadata.jsonl` and `out/stats.json`. Do not edit them. If you fix any label after this, run step 5 again.

## Step 6: final check

```
python tools/validate_v8.py --final
```
It must print `VALID: 0 errors`. This checks: every quote is an exact substring of its chunk, the schema, no held-out or eval project anywhere (5172, 5432, 4329, 2928, Miro 2410, Bandai 2929), no unexpected source files, train and val share no project group, and `out/` matches the labels.

## Step 7: zip and hand back

```
python tools/make_return_zip.py
```
This creates `tally_v8_return.zip` in this folder. Give that file to Renhuang. Optionally write `AGENT_NOTES.md` (it is included) with: how many batches you completed, and anything that blocked you.

## Acceptance checks (all must hold)

1. `python tools/chunk_v8.py` printed `OK: 7720 chunks ... 2250 to label in 282 batches`.
2. `labels/` holds only `batch_NNNN.jsonl` files, contiguous from `batch_0001`, at least 140 of them, each with exactly as many lines as its batch lists.
3. `python tools/validate_v8.py --final` prints `VALID: 0 errors`.
4. `out/` contains the 5 files from step 5, built after the last label change.
5. `tally_v8_return.zip` exists and was made by `tools/make_return_zip.py`.
