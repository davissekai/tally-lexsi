"""Chunk expansion-set PD text with the Tiny Aya tokenizer (3,500 / 300)."""
import json
import sys
from pathlib import Path

from paths import find_tokenizer, first_existing, prepend_import_paths

ROOT = prepend_import_paths()
from chunk_merge import chunk_doc
from tokenizers import Tokenizer

tok_path = find_tokenizer()
if tok_path is None:
    raise SystemExit("tokenizer.json not found; set TALLY_TOKENIZER")
T = Tokenizer.from_file(str(tok_path))


class Tok:
    def encode(self, s, add_special_tokens=False):
        return T.encode(s, add_special_tokens=False).ids

    def decode(self, ids, skip_special_tokens=False):
        return T.decode(list(ids), skip_special_tokens=False)


text_dir = first_existing(ROOT / "data_expansion" / "text", ROOT / "data" / "text")
if text_dir is None:
    raise SystemExit("no text directory found; set TALLY_ROOT to the working tree that holds data_expansion/text")

out = {}
for p in sorted(text_dir.glob("*.txt")):
    ch = chunk_doc(p.read_text(encoding="utf-8"), Tok(), max_tokens=3500, overlap=300)
    out[p.stem] = ch
    print(p.stem, len(ch))
Path("chunks_new.json").write_text(json.dumps(out, ensure_ascii=False))
print(sum(len(v) for v in out.values()))
