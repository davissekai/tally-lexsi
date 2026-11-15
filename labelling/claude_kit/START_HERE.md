# Start here (Windows, Claude Code)

This folder is a labelling kit for Tally. You will point Claude Code at it and let it work through real document chunks, one small group at a time. It writes labels to files in this folder. You can stop at any point and pick it up later.

It must **label the real chunks in `chunks/`**. It must not invent documents.

## What you need

- A Windows laptop with [Claude Code](https://code.claude.com/docs) installed and a **Claude Pro** login.
- This folder, unzipped. You should see `START_HERE.md`, `TASK.md`, `RULES.md`, `CLAUDE.md`, `chunks_index.csv`, a `chunks` folder, `check_quotes.py`, and empty `labels.jsonl` / `review.jsonl`.

Python is only needed if you (or Claude Code) want to run the optional quote check. That is not required.

## Steps

1. Unzip `claude_kit.zip` somewhere convenient, for example `Downloads\claude_kit`.
2. Open a terminal in that folder. In File Explorer, you can click into the folder, then type `cmd` or `powershell` in the address bar and press Enter. You should be inside the folder that contains `START_HERE.md`.
3. Start Claude Code:

   ```bat
   claude
   ```

4. Paste **Prompt A** below and send it. That starts the labeller pass. Let it run.
5. When it finishes, or when you stop it, or when Pro hits a usage limit, you can close the session. Progress is saved in `progress.json` and `labels.jsonl`. To continue later, open the same folder, run `claude` again, and paste **Prompt A** again. It will skip chunks already done.
6. When the 809 main chunks are labelled, start a **new** Claude Code session in the same folder (do not continue the long labeller chat) and paste **Prompt B**. That is the reviewer pass. It can also be stopped and resumed the same way, using `review_progress.json` and `review.jsonl`.
7. When you are done, or when you want to hand work back mid-way, zip just these two files and send them back:

   - `labels.jsonl`
   - `review.jsonl`

   In PowerShell, from this folder:

   ```powershell
   Compress-Archive -Path labels.jsonl,review.jsonl -DestinationPath tally_labels.zip -Force
   ```

   You do not need to send the chunk files back.

## Usage limits

Claude Pro caps how much you can use in a rolling window. This job is a long loop, so it may pause or refuse further work part-way through. That is fine. Stop, wait until the limit resets, open the same folder, run `claude`, and paste the same prompt. Do not start over, and do not delete `labels.jsonl` or `progress.json`.

If Claude Code asks to run `python check_quotes.py` or `py check_quotes.py`, you can allow it. It only reads the chunks and flags mistyped quotes. If `python` is not installed, skip the check; the labels are still useful.

## Optional backlog

The `backlog` folder has extra real chunks that were not in the main 809. Leave it alone unless you have finished the main set and want to do more. Those files are clearly marked as optional in their headers.

## Prompt A — labeller (paste this)

```
You are labelling real Verra document chunks for the Tally project. Read TASK.md and RULES.md first.

Then start the LABELLER pass:
- Open chunks_index.csv and progress.json.
- Work in order, in groups of about 5 chunks.
- For each chunk_id not already listed in progress.json completed_ids, and not already present as a complete line in labels.jsonl, read only that chunk file plus RULES.md.
- Append one JSON line to labels.jsonl with {chunk_id, fields, conflicts}. All nine fields must be present. Follow the schema and examples in RULES.md.
- After each group, update progress.json (add the completed chunk_ids and set n_completed).
- Never edit files in chunks/ or backlog/. Never invent documents, sentences, numbers, or quotes. If a field is not in the chunk, write "not_stated".
- After each group you may run: python check_quotes.py   (or: py check_quotes.py). If a quote is flagged, copy it again from the chunk or mark the field not_stated.
- If you hit a usage limit or I stop you, just stop. Progress is saved. The same prompt will resume where you left off.
- When all 809 rows in chunks_index.csv are done, stop and tell me the counts (chunks labelled, fields with values vs not_stated). Do not start the reviewer pass in this session unless I ask.
- Ignore the backlog/ folder unless I explicitly ask you to label it after the 809 are done.
```

## Prompt B — reviewer (paste this in a new session)

```
You are reviewing labels for the Tally project. Read TASK.md and RULES.md first.

Then start the REVIEWER pass in this fresh session (or as a separate subagent — do not reuse the labeller conversation):
- Read labels.jsonl and review_progress.json.
- For each labelled chunk_id not already in review_progress.json completed_ids (and not already fully reviewed in review.jsonl), read that chunk file and RULES.md, and check every field against the rules, including fields marked not_stated.
- Append one JSON line per chunk to review.jsonl, with a "reviews" array covering all nine fields. Each item is {field, verdict, reason}, where verdict is accept, fix, or reject. On fix, also include the corrected value, quote, and unit. On reject, the field will be set to not_stated.
- After each group of about 5 chunks, update review_progress.json (completed_ids, n_completed, n_total).
- Never edit chunk files or labels.jsonl, and never invent text. A quote must be copied character-for-character from the chunk.
- You may run: python check_quotes.py --review   (or: py check_quotes.py --review). Fix any corrected quote it flags if you mistyped it.
- Stop and resume later with this same prompt if needed. Do not start over.
- When every labelled chunk has been reviewed, stop and tell me the counts (accepted / fixed / rejected).
```
