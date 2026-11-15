"""Box-side: assemble the Antigravity v8 package sources (run once by Indi)."""
import json, re, shutil, sys
from pathlib import Path
ROOT = Path("/workspace/tally")
PKG = ROOT / "antigravity_v8/package/tally_v8"
sys.path.insert(0, str(PKG / "tools"))
import v8lib as L

reg_groups = {}
for line in open(ROOT / "opus_batches/chunks_registry.jsonl", encoding="utf-8"):
    o = json.loads(line)
    reg_groups[o["project"]] = o["project_group"]
EXTRA_GROUPS = {"562": "562_612", "612": "562_612", "934": "934", "1340": "1340"}

src_dirs = [ROOT / "data_expansion/text", ROOT / "data_expansion/text_wide", ROOT / "run_output/tally/text"]
out = PKG / "sources"
if out.exists():
    shutil.rmtree(out)
out.mkdir(parents=True)
rows = []
for d in src_dirs:
    for p in sorted(d.glob("*.txt")):
        doc = p.stem
        proj = L.project_of_doc(doc)
        if proj in L.BANNED_PROJECTS or L.BANNED_NAME_RE.search(doc):
            continue
        group = EXTRA_GROUPS.get(proj) or reg_groups.get(proj)
        assert group, doc
        if group in ("562_612",) or proj in reg_groups or proj in EXTRA_GROUPS:
            pass
        m = re.search(r"_(PD|PDD|MR|VR|Verification|Validation|MR-M\d+)", doc)
        dt = m.group(1) if m else "PD"
        dt = {"PDD": "PD", "Verification": "VR", "Validation": "VAL"}.get(dt, dt)
        if dt.startswith("MR"): dt = "MR"
        if "PD_short" in doc or "PD_excerpt" in doc: dt = "PD"
        shutil.copy2(p, out / p.name)
        rows.append({"doc": doc, "file": f"sources/{p.name}", "project": proj, "project_group": group,
                     "doc_type": dt, "sha256": L.sha256_file(p)})
# 562_612 group: if registry had 562/612 groups differently, our map wins (they are absent from registry)
L.write_text(PKG / "sources/SOURCES.json", json.dumps({"version": L.V8_VERSION, "documents": rows}, indent=1, ensure_ascii=False) + "\n")
print(len(rows), "docs")
import collections
print(collections.Counter(r["doc_type"] for r in rows))
print(len({r["project_group"] for r in rows}), "groups")
