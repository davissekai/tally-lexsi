"""Score merged Tally outputs against your own answer key.

python scorer/score_file.py --pred a.tally.json b.tally.json --key answer_key.json

answer_key.json: {doc_stem: {field: gold_value or {"gold_value": ...}}} with
"NOT_STATED" for fields the document does not state. Keys are not shipped here.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from score_extractions import score_documents, format_summary_table, load_answer_key

ap = argparse.ArgumentParser()
ap.add_argument("--pred", nargs="+", required=True)
ap.add_argument("--key", required=True)
a = ap.parse_args()
merged = {}
for p in a.pred:
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    merged[d["doc"]] = d["merged"]
scores = score_documents(merged, load_answer_key(a.key))
print(format_summary_table(scores, "Tally scores"))
