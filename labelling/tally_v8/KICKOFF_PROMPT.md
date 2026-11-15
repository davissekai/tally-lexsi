# Paste this into the Antigravity agent (model: Gemini 3.8 Flash)

Open this folder as the workspace first (the folder that contains TASK.md).

---

You are executing a fixed data-labelling procedure. Read `TASK.md` and follow it exactly, step by step, starting at Step 1. Then read `RULES_V8.md` in full before labelling.

Hard rules: do not write or run any code of your own, do not label with scripts or regex, and only run the `python tools/...` commands that TASK.md lists. Do not edit anything in tools/, sources/, expected/, schema/ or work/. Label every chunk by reading its text and copying quotes character for character. Never invent or compute a value: if it is not written in the chunk, it is "not_stated".

Work one batch at a time in order (`python tools/next_batch.py`), validate each batch (`python tools/validate_v8.py --batch NNNN`) until it says `VALID: 0 errors`, then continue with the next batch without asking me. Keep going until `next_batch.py` prints ALL DONE, then do Steps 4 to 7 and tell me when `tally_v8_return.zip` exists. If you hit a limit, stop after a valid batch and tell me which batch is next.

---

## To resume in a new session

Paste the same prompt and add: "Labelling has already started. Skip Step 1 and continue Step 3 from `python tools/next_batch.py`."
