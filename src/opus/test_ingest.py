"""Self-test for ingest.py with a fake Opus reply built from batch_001 (no network, no real labels written).
Run: python3 test_ingest.py   -> outputs go to /tmp/opus_ingest_test/"""
import json, os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from common import *

man = json.loads(MANIFEST.read_text()); reg = load_registry(); v5 = json.loads(V5_LABELS.read_text())
ids = man["batches"][0]["chunk_ids"]
UNIT = {"baseline": "tCO2e", "additionality": None, "leakage": "tCO2e", "permanence_buffer": "%", "crediting_period": "dates",
        "area": "ha", "estimated_reductions": "tCO2e"}
def good_value(f, g):
    # a value taken from inside the gold quote (the way Opus is told to answer)
    q = g["quote"]; nums = re.findall(r"\d[\d ,'’.]*\d|\d", q)
    if f == "additionality": return " ".join(q.split()[:8])
    if f == "crediting_period": return q
    return max(nums, key=len) if nums else q
items = []
for cid in ids[:-1]:                                   # last chunk deliberately missing
    fields = {}
    for f in FIELDS:
        g = v5[cid][f]
        fields[f] = NOT_STATED if g == NOT_STATED else {"value": good_value(f, g), "quote": g["quote"], "unit": UNIT[f]}
    fields["area_incl_leakage_belt"] = NOT_STATED; fields["estimated_reductions_pre_buffer"] = NOT_STATED
    items.append({"chunk_id": cid, "fields": fields, "conflicts": []})
pos = [it for it in items if any(v != NOT_STATED for v in it["fields"].values())]
# injected failures
a, b, c, d = pos[0], pos[1], pos[2], pos[3]
fa = next(f for f in FIELDS if a["fields"][f] != NOT_STATED); a["fields"][fa]["quote"] += " and this sentence was invented"
fb = next(f for f in FIELDS if b["fields"][f] != NOT_STATED and re.search(r"\d", b["fields"][f]["value"]))
b["fields"][fb]["value"] = "987654321"
c["fields"]["leakage"] = {"value": "20", "quote": norm_ws(reg[c["chunk_id"]]["text"])[:60], "unit": "%"}
# Opus finds a value v5 missed (quote really in chunk) -> should be kept and flagged opus_only
txt = norm_ws(reg[d["chunk_id"]]["text"]); m = re.search(r"[^.]{0,80}\b(\d{1,3}(?:,\d{3})+)\s*(?:ha|hectares)\b[^.]{0,40}", txt)
if m and d["fields"]["area"] == NOT_STATED: d["fields"]["area"] = {"value": m.group(1), "quote": m.group(0).strip(), "unit": "ha"}
d["conflicts"] = [{"field": "area", "value": "1", "quote": "not in chunk at all", "note": "test"}]
items.insert(0, {"chunk_id": "9999_PD::chunk-000", "fields": {}, "conflicts": []})
half = len(items) // 2
blk1 = json.dumps(items[:half], ensure_ascii=False, indent=1)
blk1 = blk1.replace('"conflicts": []\n }', '"conflicts": [],\n }', 1)          # trailing comma slip
blk2 = json.dumps(items[half:], ensure_ascii=False, indent=1)
blk2 = blk2[:-200]                                                             # truncated reply
reply = ("Here are the labels for batch 001.\n\n```json\n" + blk1 + "\n```\n\nCONTINUE\n\nContinuing:\n```json\n" + blk2)
tmp = Path("/tmp/opus_ingest_test"); tmp.mkdir(exist_ok=True)
(tmp / "reply_001.json").write_text(reply, encoding="utf-8")
env = {**os.environ, "OPUS_OUT": str(tmp)}
r = subprocess.run([sys.executable, str(OB / "ingest.py"), str(tmp / "reply_001.json")], env=env, capture_output=True, text=True)
print(r.stdout, r.stderr)
summ = json.loads((tmp / "ingest_summary.json").read_text())
log = [json.loads(l) for l in (tmp / "ingest_log.jsonl").read_text().splitlines()]
reasons = [l["reason"] for l in log]
assert any(x == "quote_not_in_chunk" for x in reasons), reasons
assert any(x.startswith("value_not_in_quote") for x in reasons), reasons
assert any(x.startswith("bad_unit") for x in reasons), reasons
assert "unknown_chunk_id" in reasons
assert summ["missing_from_replies"] >= 1
lab = {json.loads(l)["chunk_id"]: json.loads(l) for l in (tmp / "opus_labels.jsonl").read_text().splitlines()}
assert lab[a["chunk_id"]]["fields"][fa] == NOT_STATED and lab[b["chunk_id"]]["fields"][fb] == NOT_STATED
assert lab[c["chunk_id"]]["fields"]["leakage"] == NOT_STATED
kept = summ["values_kept"]; assert kept >= summ["values_in"] - 6, summ
print("PASS:", summ["chunks_labelled"], "chunks parsed,", kept, "of", summ["values_in"], "values kept; drops", summ["drops"])
print(open(tmp / "disagreements.md").read()[:1800])
