"""Box-side: ids of v8 chunks that contain a v7-labelled quote (ids only, no values)."""
import json, sys, collections
sys.path.insert(0, "package/tally_v8/tools"); import v8lib as L
PKG = "package/tally_v8"
chunks, errs = L.build_corpus(PKG); assert not errs
v7 = [json.loads(l) for l in open("/workspace/tally/incoming_v7/labels_fixed.jsonl") if l.strip()]
bydoc = collections.defaultdict(list)
for c in chunks: bydoc[c["doc"]].append((c["chunk_id"], L.flat(L.chunk_body(c["text"]))))
ids = set()
for lab in v7:
    doc = lab["chunk_id"].split("::")[0]
    for f, v in lab["fields"].items():
        if isinstance(v, dict) and v.get("quote"):
            q = L.flat(v["quote"])
            for cid, b in bydoc.get(doc, []):
                if q in b: ids.add(cid); break
ids = sorted(i for i in ids if L.project_of_doc(i) not in L.BANNED_PROJECTS)
L.write_text(f"{PKG}/expected/priority_chunk_ids.json", json.dumps(ids, indent=0) + "\n")
print(len(ids), "priority ids")
