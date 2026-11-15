# Tally Claude Code project

You are labelling training data for Tally, a model that extracts fields from real Verra VCS carbon-project documents.

This folder is the whole workspace. Start by reading `START_HERE.md` if a human is getting set up, and always read `TASK.md` and `RULES.md` before labelling or reviewing.

## Non-negotiable

- Label **real chunks only**. Never invent a document, a sentence, a number, or a quote.
- Every quote must be copied character-for-character from the chunk file (typos included). Only spacing and line breaks may differ.
- Never infer, convert, sum, round, or compute a value. Absent or only implied → `"not_stated"`.
- Never edit `chunks/` or `backlog/` files, and never rewrite `chunks_index.csv`.
- Work in small groups (about 5 chunks) so context stays small. Append to `labels.jsonl` or `review.jsonl` and update the matching progress file after each group.
- Skip any chunk already listed in the progress file or already present as a complete line in the output jsonl. Safe to stop and resume with the same prompt.
- Ignore `backlog/` unless the user explicitly asks to label it after the 809 main chunks are done.
- Do not start the reviewer pass in the labeller session unless the user asks. The reviewer should be a fresh session or a separate subagent.
- You may run `python check_quotes.py` or `py check_quotes.py` (and `--review` during the reviewer pass) as an optional check. It only flags quotes that are not substrings of the chunk. Real verification happens later, off this machine.

Follow the schemas in `RULES.md` and the loop in `TASK.md`.
