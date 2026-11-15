"""Run Tally (Tiny Aya Global + LoRA adapter) on one document's text.

Usage:
  pip install -r requirements.txt
  export HF_TOKEN=...   # Tiny Aya Global is gated on Hugging Face; never commit it
  python inference/run_extraction.py doc.txt --out doc_extraction.json
  python inference/run_extraction.py doc.txt --no-adapter   # base Tiny Aya

`doc.txt` is plain text of a Verra project document, e.g. from
`pdftotext -layout doc.pdf doc.txt` (form feeds mark page breaks).

Output: per-chunk JSON replies plus a merged document record in the shape that
scorer/score_extractions.py expects (see schema/output_schema.json).

Merging uses the same grounded merge as every reported result
(`src/tally_merge.py::merge_notes`): a chunk's value is kept only if its quote
is found in the document text, the value appears in the quote and the unit
fits the field; surviving candidates that still disagree become a `conflict`.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from tally_merge import merge_notes  # noqa: E402  grounded merge used for all results

BASE_ID = "CohereLabs/tiny-aya-global"
ADAPTER_ID = "renhuang001/tally-v7-lora"
FIELDS = ["baseline", "additionality", "leakage", "permanence_buffer",
          "crediting_period", "area", "estimated_reductions"]
PROMPT = (Path(__file__).parent / "prompt.txt").read_text(encoding="utf-8").rstrip("\n")
CHUNK_TOKENS, OVERLAP_TOKENS = 3500, 300


def pages_of(text: str) -> list[str]:
    pages = text.split("\f")
    return pages if len(pages) > 1 else [text]


def chunk_document(text: str, tok) -> list[str]:
    """Fixed token windows (3,500 tokens, 300 overlap) with page markers."""
    marked = "".join(f"\n--- page {i} ---\n{p}" for i, p in enumerate(pages_of(text), 1))
    ids = tok(marked, add_special_tokens=False)["input_ids"]
    chunks, start = [], 0
    while start < len(ids):
        piece = tok.decode(ids[start:start + CHUNK_TOKENS])
        nums = [int(n) for n in re.findall(r"--- page (\d+) ---", piece)] or [0]
        chunks.append(f"Pages {min(nums)}-{max(nums)}:\n{piece}")
        if start + CHUNK_TOKENS >= len(ids):
            break
        start += CHUNK_TOKENS - OVERLAP_TOKENS
    return chunks


def parse_json(text: str):
    start = text.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return None


def load(adapter: str | None):
    tok = AutoTokenizer.from_pretrained(BASE_ID)
    model = AutoModelForCausalLM.from_pretrained(BASE_ID, torch_dtype=torch.float16, device_map="auto")
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    model.eval()
    return tok, model


@torch.no_grad()
def generate(tok, model, prompt: str, max_new_tokens: int = 900) -> str:
    text = tok.apply_chat_template([{"role": "user", "content": prompt}],
                                   add_generation_prompt=True, tokenize=False)
    inputs = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return tok.decode(out[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--adapter", default=ADAPTER_ID)
    ap.add_argument("--no-adapter", action="store_true")
    a = ap.parse_args()
    tok, model = load(None if a.no_adapter else a.adapter)
    chunks = chunk_document(a.doc.read_text(encoding="utf-8", errors="replace"), tok)
    replies, texts = [], []
    for i, ch in enumerate(chunks, 1):
        raw = generate(tok, model, f"{PROMPT}\n\n\n{ch}")
        parsed = parse_json(raw)
        replies.append(parsed if parsed is not None else {"_error": "unparseable", "raw": raw[:2000]})
        texts.append(ch.split("\n", 1)[1] if "\n" in ch else ch)
        print(f"chunk {i}/{len(chunks)} parsed={parsed is not None}", flush=True)
    merged = merge_notes(replies, doc_text="\n\n".join(texts))
    result = {"doc": a.doc.stem, "chunks": replies, "merged": merged}
    out = a.out or a.doc.with_suffix(".tally.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
