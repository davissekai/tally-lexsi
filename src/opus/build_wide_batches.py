"""Build batches 024+ from worldwide (text_wide) chunks, without touching 001-023.

Uses the same Tiny Aya chunker, keyword/number score, prompt instructions and
rendering as build_batches.py. All wide chunks are registered; only the top
ranked, diversity-spread subset is batched (at most 30 batches, ~15 chunks,
~3 likely-empty each). The rest go to backlog_wide.jsonl in rank order.

  /tmp/at-venv/bin/python build_wide_batches.py
  python src/opus/build_wide_batches.py --chunks-json data_expansion/wide_work/chunks_wide.json
"""
from __future__ import annotations

import argparse, csv, json, math, zipfile
from collections import Counter, defaultdict
from pathlib import Path

from common import *
from build_batches import (
    INSTRUCTIONS, score, render_chunk, est_claude_tokens, compact,
    TARGET_TOK, MAX_TOK, EMPTIES_PER_BATCH,
)

TEXT_WIDE = ROOT / "data_expansion/text_wide"
WIDE_MANIFEST_CSV = ROOT / "data_expansion/pdfs_wide/MANIFEST.csv"
CHUNKS_CACHE = ROOT / "data_expansion/wide_work/chunks_wide.json"
BACKLOG = OB / "backlog_wide.jsonl"
WIDE_ZIP = OB / "batches_wide.zip"
SUMMARY = OB / "wide_batch_summary.json"

MAX_BATCHES = 30
CHUNKS_PER_BATCH = 15
EMPTIES = 3
VAL_PER_BATCH = CHUNKS_PER_BATCH - EMPTIES  # 12
MAX_VAL_PER_GROUP = 8
MAX_VAL_PER_DOC = 5  # 80 docs * 5 >= 360; 4 was too tight and forced a relax to 8
MAX_EMPTY_PER_GROUP = 3
MAX_EMPTY_PER_DOC = 2
EMPTY_SCORE_MAX = 16.0  # around the 10th-15th percentile of the wide scores
MIN_VAL_SCORE = 28.0    # don't call mid/low-score chunks "valuable"

# CarbonDecode country -> region (matches the worldwide download notes)
REGION_OF = {
    "Peru": "Latin America", "Brazil": "Latin America", "Uruguay": "Latin America",
    "Colombia": "Latin America", "Mexico": "Latin America", "Chile": "Latin America",
    "Guatemala": "Latin America",
    "Kenya": "Africa", "Tanzania": "Africa", "Uganda": "Africa", "Zambia": "Africa",
    "Madagascar": "Africa", "Ghana": "Africa", "Malawi": "Africa",
    "Central African Republic": "Africa", "Zimbabwe": "Africa",
    "Indonesia": "Asia", "China": "Asia", "India": "Asia", "Cambodia": "Asia",
    "Pakistan": "Asia", "Malaysia": "Asia",
    "Canada": "North America",
}


def load_meta():
    meta = {}
    with WIDE_MANIFEST_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            stem = Path(r["local_file"]).stem
            meta[stem] = {"country": r["country"], "region": REGION_OF[r["country"]],
                          "project_name": r["project_name"], "pages": int(r["pages"])}
    return meta



def max_val_per_doc(row, docs_in_group):
    """Single-document groups may fill the group cap from that one doc; otherwise 5."""
    n_docs = docs_in_group.get(row["project_group"], 1)
    if n_docs <= 1:
        return MAX_VAL_PER_GROUP
    return MAX_VAL_PER_DOC

def max_val_per_project(group: str) -> int:
    n_members = group.count("_") + 1  # "977_981" -> 2; singleton "1202" -> 1
    if n_members >= 4:
        return 2
    if n_members >= 2:
        return 3
    return 4


def select_round_robin(candidates, n_target, max_group, max_doc_fn, max_proj_fn,
                       already, label):
    """Pick up to n_target chunks, spreading across project_group / project / doc.

    At each step take the best remaining chunk from the eligible group that
    currently has the fewest picks (tie-break: higher next-chunk score).
    Caps are hard until we would fall short, then they relax once in order.
    `already` is a set of chunk_ids already reserved (e.g. valuable vs empty).
    """
    already_ids = {r["chunk_id"] if isinstance(r, dict) else r for r in already}
    remaining = [r for r in candidates if r["chunk_id"] not in already_ids]
    remaining.sort(key=lambda r: (-r["score"], r["chunk_id"]))
    by_group = defaultdict(list)
    for r in remaining:
        by_group[r["project_group"]].append(r)  # already score-desc

    picked, used = [], set(already_ids)
    counts_g, counts_p, counts_d = Counter(), Counter(), Counter()
    # Count already-picked rows so seeding a doc does not blow the group cap later
    already_rows = already if already and isinstance(next(iter(already), None), dict) else []
    if not already_rows:
        # `already` may be a set of ids; recover rows from candidates (and leftover seed)
        by_id = {r["chunk_id"]: r for r in candidates}
        already_rows = [by_id[i] for i in already_ids if i in by_id]
    for r in already_rows:
        counts_g[r["project_group"]] += 1
        counts_p[r["project"]] += 1
        counts_d[r["doc"]] += 1

    def doc_cap(r):
        return max_doc_fn(r) if callable(max_doc_fn) else max_doc_fn

    def next_from_group(g, cap_g, relax_proj=False):
        cap_p = 999 if relax_proj else max_proj_fn(g)
        for r in by_group[g]:
            if r["chunk_id"] in used:
                continue
            if counts_g[g] >= cap_g:
                return None
            if counts_d[r["doc"]] >= doc_cap(r):
                continue
            if counts_p[r["project"]] >= cap_p:
                continue
            return r
        return None

    def step(cap_g, relax_proj=False):
        progress = True
        while len(picked) < n_target and progress:
            progress = False
            choices = []
            for g, lst in by_group.items():
                nxt = next_from_group(g, cap_g, relax_proj)
                if nxt is not None:
                    choices.append((counts_g[g], -nxt["score"], nxt["chunk_id"], nxt, g))
            if not choices:
                break
            choices.sort()
            _cg, _ns, _id, r, g = choices[0]
            picked.append(r)
            used.add(r["chunk_id"])
            counts_g[g] += 1
            counts_p[r["project"]] += 1
            counts_d[r["doc"]] += 1
            progress = True

    # Never raise the group cap: one family must not dominate. Only relax the
    # per-project-within-family cap if we would otherwise fall short.
    step(max_group, relax_proj=False)
    if len(picked) < n_target:
        step(max_group, relax_proj=True)
    return picked


def pack_batches(valuable, empties, n_batches):
    """Deal valuable and empty chunks into n_batches with group/region/type spread.

    No batch should get two chunks from the same project_group if it can be
    avoided. Empties are interleaved through the batch (not dumped at the end).
    """
    # Order each group's valuable chunks by score so the first deal is the cream
    by_g = defaultdict(list)
    for r in valuable:
        by_g[r["project_group"]].append(r)
    for g in by_g:
        by_g[g].sort(key=lambda r: (-r["score"], r["chunk_id"]))
    # Deal one-from-each-group cycles, groups ordered by their best score
    group_order = sorted(by_g, key=lambda g: (-by_g[g][0]["score"], g))
    val_dealt = [[] for _ in range(n_batches)]
    gi, bi = 0, 0
    # Take up to VAL_PER_BATCH per batch
    remaining_g = {g: list(by_g[g]) for g in group_order}
    # Cycle: for each pass, walk groups and place each group's next chunk
    # into the batch that does not yet have that group and has the fewest vals.
    val_left = list(valuable)
    # Use an assignment helper
    assigned_val = set()

    def batch_groups(i):
        return {r["project_group"] for r in val_dealt[i]}

    # Multiple passes over groups
    changed = True
    while changed:
        changed = False
        for g in group_order:
            pool = [r for r in remaining_g[g] if r["chunk_id"] not in assigned_val]
            if not pool:
                continue
            # candidate batches: under capacity, preferably without this group
            under = [i for i in range(n_batches) if len(val_dealt[i]) < VAL_PER_BATCH]
            if not under:
                continue
            free = [i for i in under if g not in batch_groups(i)]
            if not free:
                # Do not place a second valuable chunk from this group in a batch.
                continue
            r = pool[0]

            def key(i):
                regs = sum(1 for x in val_dealt[i] if x["region"] == r["region"])
                typ = sum(1 for x in val_dealt[i] if x["doc_type"] == r["doc_type"])
                return (len(val_dealt[i]), regs, typ, i)
            i = min(free, key=key)
            val_dealt[i].append(r)
            assigned_val.add(r["chunk_id"])
            changed = True

    unassigned = [r for r in valuable if r["chunk_id"] not in assigned_val]
    if unassigned:
        # Swap: find a batch without this group that can trade a chunk whose
        # group is missing from a batch that still has room, or simply sits in
        # a batch that already has 2+ of some other group (shouldn't happen).
        for r in list(unassigned):
            free = [i for i in range(n_batches)
                    if r["project_group"] not in batch_groups(i) and len(val_dealt[i]) < VAL_PER_BATCH]
            if free:
                i = min(free, key=lambda i: (len(val_dealt[i]), i))
                val_dealt[i].append(r)
                assigned_val.add(r["chunk_id"])
                continue
            # All batches without this group are full: swap with a chunk that
            # can move into a batch which lacks *that* chunk's group and still
            # has room, or into a batch we will free by this swap.
            placed = False
            for i in range(n_batches):
                if r["project_group"] in batch_groups(i):
                    continue
                # batch i is full and lacks r's group. Try to move one of its
                # chunks to some other batch that lacks that chunk's group.
                for k, other in enumerate(val_dealt[i]):
                    dests = [j for j in range(n_batches)
                             if j != i and other["project_group"] not in batch_groups(j)
                             and (len(val_dealt[j]) < VAL_PER_BATCH or j == i)]
                    # after we remove `other` from i, i has room and lacks r's group;
                    # dests for `other` must lack other's group and have room
                    dests = [j for j in range(n_batches) if j != i
                             and other["project_group"] not in batch_groups(j)
                             and len(val_dealt[j]) < VAL_PER_BATCH]
                    if dests:
                        j = min(dests, key=lambda j: (len(val_dealt[j]), j))
                        val_dealt[i].pop(k)
                        val_dealt[j].append(other)
                        val_dealt[i].append(r)
                        assigned_val.add(r["chunk_id"])
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                print(f"WARNING: could not place valuable {r['chunk_id']} without a group collision")

    # Deal empties: 3 per batch, avoid groups already in the batch if possible
    emp_dealt = [[] for _ in range(n_batches)]
    assigned_e = set()
    emp_sorted = sorted(empties, key=lambda r: (r["score"], r["chunk_id"]))
    for r in emp_sorted:
        need = [i for i in range(n_batches) if len(emp_dealt[i]) < EMPTIES]
        if not need:
            break
        groups_plus = lambda i: batch_groups(i) | {x["project_group"] for x in emp_dealt[i]}
        free = [i for i in need if r["project_group"] not in groups_plus(i)]
        dests = free or need
        i = min(dests, key=lambda i: (len(emp_dealt[i]), i))
        emp_dealt[i].append(r)
        assigned_e.add(r["chunk_id"])

    # Interleave empties through the valuable list (same idea as build_batches.plan)
    batches = []
    for i in range(n_batches):
        val = val_dealt[i]
        emp = list(emp_dealt[i])
        if emp and val:
            step = max(1, len(val) // (len(emp) + 1))
            merged, ej = [], 0
            for k, r in enumerate(val):
                merged.append(r)
                if ej < len(emp) and (k + 1) % step == 0 and k + 1 < len(val):
                    merged.append(emp[ej]); ej += 1
            merged += emp[ej:]
            batches.append(merged)
        else:
            batches.append(val + emp)
    return batches


def registry_core_keys(r, batched, batch_no=None):
    rec = {k: r[k] for k in (
        "chunk_id", "doc", "project", "project_group", "doc_type", "chunk_index",
        "start_page", "end_page", "source", "text", "score", "rank", "tier",
        "region", "country",
    ) if k in r}
    rec["batched"] = batched
    if batch_no is not None:
        rec["batch"] = batch_no
    return rec


def write_registry(old_rows, new_rows):
    """Rewrite registry: existing 001-023 rows (plus project_group), then all wide rows."""
    tmp = REGISTRY.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in old_rows:
            rec = {k: r[k] for k in r}  # preserve original keys + project_group
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(REGISTRY)


def update_readme(manifest, n_wide, n_batched, n_backlog, n_batches, n_projects, n_groups):
    readme = OB / "README.md"
    text = readme.read_text(encoding="utf-8")
    # Keep the original 001-023 body; refresh the opening count and append a wide section.
    marker = "## Worldwide extension (batches 024+)"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    # The first paragraph originally said "23 batches, 359 chunks...". Point to 024+.
    old_intro = "23 batches, 359 chunks from the 13 new project descriptions."
    new_intro = ("53 batches in total. Batches 001–023 are 359 chunks from the 13 new project descriptions; "
                 "batches 024–053 are a ranked worldwide extension (see below).")
    if old_intro in text:
        text = text.replace(old_intro, new_intro, 1)
    elif "53 batches in total" not in text.split(marker)[0] if marker in text else True:
        pass
    new_batches = [b for b in manifest["batches"] if int(b["batch"]) >= 24]
    rows = []
    for b in new_batches:
        kb = max(1, round(b["chars"] / 1024))
        rows.append(f"| {b['batch']} | {b['n_chunks']} | ~{b['est_input_tokens']//1000}k | {kb} KB | {b.get('priority', 'wide ranked')} |")
    table = "\n".join(rows)
    # token range
    toks = [b["est_input_tokens"] for b in new_batches]
    tmin, tmax = (min(toks), max(toks)) if toks else (0, 0)
    section = f"""

{marker}

{len(new_batches)} further batches, {n_batched} chunks, taken from the worldwide documents ({n_wide} chunks in total from 80 files / {n_projects} projects / {n_groups} project-groups). Existing batches 001–023 and their chunk ids are unchanged.

These are the **highest-ranked** chunks for containing one of the seven fields (same keyword and number score as 001–023), spread so no project or near-template family dominates. Each batch mixes in 3 chunks that are probably empty. The remaining {n_backlog} unbatched chunks are in `backlog_wide.jsonl` (rank order) and in `chunks_registry.jsonl` with `"batched": false`, so later waves can pick them up without re-chunking.

**Template families** (one `project_group`, kept together in a later train/val split): 977+981 (Portel-Pará), 959+960+961+962 (Carbosur Uruguay), 737+899+993 (TIST Kenya/Uganda), 1847+1855+1865+2070 (Shanghai Libra China).

Do 001–007 first if you have not already. Then these, still **one new Claude chat per batch**, attaching the `.txt` file (don't paste). Estimated input per batch is about {tmin//1000}k–{tmax//1000}k tokens, same as before, so Pro's 5-hour window will still only allow a few batches at a time.

The phone-friendly zip of just this wave is `batches_wide.zip`. `batches_all.zip` has 001–023 plus 024+.

| Batch | Chunks | Est. input tokens | File size | Priority |
|---|---:|---:|---:|---|
{table}

Token counts are the same 3.2 characters-per-token estimate as batches 001–023.
"""
    readme.write_text(text.rstrip() + section, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks-json", default=str(CHUNKS_CACHE))
    ap.add_argument("--text-dir", default="")
    ap.add_argument("--max-batches", type=int, default=MAX_BATCHES)
    ap.add_argument("--chunks-per-batch", type=int, default=CHUNKS_PER_BATCH)
    ap.add_argument("--replace-wide", action="store_true",
                    help="Replace batches 024+ if they already exist; never touch 001-023")
    args = ap.parse_args()

    # Safety: never rewrite 001-023 on disk
    existing_files = {f"batch_{i:03d}.txt": (OB / f"batch_{i:03d}.txt").read_bytes()
                      for i in range(1, 24) if (OB / f"batch_{i:03d}.txt").exists()}
    assert len(existing_files) == 23, f"expected 23 existing batches, found {len(existing_files)}"

    if args.text_dir:
        from build_batches import chunk_text_dir
        src = chunk_text_dir(Path(args.text_dir))
        src_name = args.text_dir
    else:
        src = json.loads(Path(args.chunks_json).read_text(encoding="utf-8"))
        src_name = str(Path(args.chunks_json).relative_to(ROOT) if Path(args.chunks_json).is_absolute() else args.chunks_json)

    meta = load_meta()
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"batches": []}
    existing_batches = [b for b in manifest["batches"] if int(b["batch"]) <= 23]
    extra_already = [b for b in manifest["batches"] if int(b["batch"]) >= 24]
    if extra_already and not args.replace_wide:
        raise SystemExit(f"manifest already has batches 024+: {[b['batch'] for b in extra_already]}. Pass --replace-wide to rebuild them.")
    if extra_already and args.replace_wide:
        for b in extra_already:
            fp = OB / b["file"]
            if int(b["batch"]) <= 23:
                raise SystemExit("refusing to delete a 001-023 file")
            if fp.exists():
                fp.unlink()
        # also remove any batch_024+ that might have been left behind
        for fp in OB.glob("batch_*.txt"):
            n = int(fp.stem.split("_")[1])
            if n >= 24:
                fp.unlink()
        print(f"replace-wide: removed {len(extra_already)} existing 024+ manifest entries")
    if len(existing_batches) != 23:
        raise SystemExit(f"expected 23 batches in manifest, found {len(existing_batches)}")

    # Existing registry rows that belong to batches 001-023 only. On a --replace-wide
    # re-run the file also contains wide rows, which we drop and rewrite.
    ids_001_023 = {cid for b in existing_batches for cid in b["chunk_ids"]}
    old_reg_list = []
    old_ids = set()
    if REGISTRY.exists():
        for ln in REGISTRY.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["chunk_id"] not in ids_001_023:
                continue
            r.setdefault("project_group", project_group(r["project"]))
            r.setdefault("batched", True)
            old_reg_list.append(r)
            old_ids.add(r["chunk_id"])
    if len(old_reg_list) != 359:
        print(f"WARNING: existing 001-023 registry has {len(old_reg_list)} rows, expected 359")

    rows = []
    skipped = []
    for stem, chs in src.items():
        proj = stem.split("_")[0]
        if proj in EXCLUDED_PROJECTS:
            skipped.append(stem)
            print(f"SKIP {stem}: validation/held-out project")
            continue
        if stem not in meta:
            print(f"WARNING: {stem} not in wide MANIFEST.csv")
        country = meta.get(stem, {}).get("country", "unknown")
        region = meta.get(stem, {}).get("region", "unknown")
        for i, ch in enumerate(chs):
            cid = f"{stem}::chunk-{i:03d}"
            if cid in old_ids:
                continue  # already in 001-023 (should not happen for text_wide)
            r = {
                "chunk_id": cid, "doc": stem, "project": proj,
                "project_group": project_group(proj),
                "doc_type": doc_type_wide(stem), "chunk_index": i,
                "start_page": ch["start_page"], "end_page": ch["end_page"],
                "text": ch["text"], "source": src_name,
                "n_tokens": ch.get("n_tokens"),
                "country": country, "region": region,
            }
            r["est_tokens"] = est_claude_tokens(render_chunk(r))
            r["score"] = score(ch["text"], None)
            rows.append(r)

    if not rows:
        print("nothing new to batch")
        return

    rows.sort(key=lambda r: (-r["score"], r["chunk_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["tier"] = "keyword"  # overwritten for selected empties / leftovers

    n_batches = args.max_batches
    n_val = n_batches * (args.chunks_per_batch - EMPTIES)
    n_empty = n_batches * EMPTIES

    # Valuable pool: high-score chunks. Every project_group has max>=44 so all can contribute.
    val_pool = [r for r in rows if r["score"] >= MIN_VAL_SCORE]
    empty_pool = [r for r in rows if r["score"] <= EMPTY_SCORE_MAX]

    docs_in_group = {g: len({r["doc"] for r in rows if r["project_group"] == g})
                     for g in {r["project_group"] for r in rows}}
    doc_cap_fn = lambda r, _d=docs_in_group: max_val_per_doc(r, _d)

    # Seed one best-scoring chunk from every document that has a valuable
    # candidate, so a family cap cannot drop a whole document (e.g. 737_PD).
    seed, seen_docs = [], set()
    for r in sorted(val_pool, key=lambda r: (-r["score"], r["chunk_id"])):
        if r["doc"] in seen_docs:
            continue
        g, proj = r["project_group"], r["project"]
        if sum(x["project_group"] == g for x in seed) >= MAX_VAL_PER_GROUP:
            continue
        if sum(x["project"] == proj for x in seed) >= max_val_per_project(g):
            continue
        if sum(x["doc"] == r["doc"] for x in seed) >= doc_cap_fn(r):
            continue
        seed.append(r)
        seen_docs.add(r["doc"])
    valuable = list(seed)
    valuable += select_round_robin(
        val_pool, n_val - len(valuable), MAX_VAL_PER_GROUP, doc_cap_fn,
        max_val_per_project, valuable, "val")
    for r in valuable:
        r["tier"] = "keyword"
    empty = select_round_robin(
        empty_pool, n_empty, MAX_EMPTY_PER_GROUP, MAX_EMPTY_PER_DOC, lambda g: 2,
        {r["chunk_id"] for r in valuable}, "empty")
    for r in empty:
        r["tier"] = "likely_empty"

    if len(valuable) < n_val:
        print(f"WARNING: only selected {len(valuable)}/{n_val} valuable chunks")
    if len(empty) < n_empty:
        print(f"WARNING: only selected {len(empty)}/{n_empty} likely-empty chunks")

    batches = pack_batches(valuable, empty, n_batches)
    # Drop any empty trailing batches (shouldn't happen)
    batches = [b for b in batches if b]
    selected_ids = {r["chunk_id"] for b in batches for r in b}

    # Assign batch numbers starting at 024
    start = 24
    batch_recs = []
    written = []
    for j, b in enumerate(batches):
        no = start + j
        # Don't write more than max
        if j >= n_batches:
            break
        head = INSTRUCTIONS.format(
            batch_no=f"{no:03d}",
            n_batches_note=f"{start + len(batches) - 1:03d}",
            n_chunks=len(b),
        )
        body = (head + "\n" + "\n".join(render_chunk(r) for r in b) +
                f"\nEND OF BATCH {no:03d}. Reply with the single ```json block covering all {len(b)} chunk_ids listed above.\n")
        # If somehow over MAX_TOK, drop the lowest-score non-empty? We aim for 15 so should be fine.
        est = est_claude_tokens(body)
        if est > MAX_TOK:
            print(f"WARNING: batch {no:03d} est {est} tokens > {MAX_TOK}")
        path = OB / f"batch_{no:03d}.txt"
        if path.exists() and no <= 23:
            raise SystemExit(f"refusing to overwrite existing batch {path}")
        path.write_text(body, encoding="utf-8")
        written.append(path)
        rec = {
            "batch": f"{no:03d}", "file": path.name, "source": src_name,
            "wave": "wide", "n_chunks": len(b),
            "est_input_tokens": est, "chars": len(body),
            "n_v5_has_value": 0,
            "n_likely_empty": sum(r["tier"] == "likely_empty" for r in b),
            "chunk_ids": [r["chunk_id"] for r in b],
            "projects": sorted({r["project"] for r in b}),
            "project_groups": sorted({r["project_group"] for r in b}),
            "regions": dict(Counter(r["region"] for r in b)),
            "doc_types": dict(Counter(r["doc_type"] for r in b)),
            "priority": f"wide ranked, {sum(r['tier']=='likely_empty' for r in b)} likely-empty",
        }
        batch_recs.append(rec)
        print(rec["batch"], rec["n_chunks"], "chunks", rec["est_input_tokens"], "est tok",
              "empty", rec["n_likely_empty"],
              "groups", len(rec["project_groups"]),
              "regions", rec["regions"], "types", rec["doc_types"])

    # Registry rows for every wide chunk (batched and backlog)
    batch_of = {}
    for rec, b in zip(batch_recs, batches):
        for r in b:
            batch_of[r["chunk_id"]] = rec["batch"]

    new_reg = []
    for r in rows:
        batched = r["chunk_id"] in selected_ids
        if not batched:
            r["tier"] = "backlog" if r["tier"] != "likely_empty" else r["tier"]
        rec = registry_core_keys(r, batched=batched, batch_no=batch_of.get(r["chunk_id"]))
        new_reg.append(rec)

    write_registry(old_reg_list, new_reg)

    # Backlog in rank order
    backlog_rows = [r for r in rows if r["chunk_id"] not in selected_ids]
    with BACKLOG.open("w", encoding="utf-8") as f:
        for r in backlog_rows:
            f.write(json.dumps({
                k: r[k] for k in (
                    "rank", "score", "chunk_id", "doc", "project", "project_group",
                    "doc_type", "region", "country", "chunk_index", "start_page",
                    "end_page", "est_tokens", "n_tokens", "source",
                ) if k in r
            }, ensure_ascii=False) + "\n")

    # Manifest: keep 001-023 exactly, append 024+
    manifest["batches"] = existing_batches + batch_recs
    manifest["wide"] = {
        "n_wide_chunks": len(rows),
        "n_batched": len(selected_ids),
        "n_backlog": len(backlog_rows),
        "n_batches": len(batch_recs),
        "n_projects": len({r["project"] for r in rows}),
        "n_project_groups": len({r["project_group"] for r in rows}),
        "excluded": skipped,
        "template_groups": ["_".join(g) for g in TEMPLATE_GROUPS],
        "source": src_name,
        "backlog": BACKLOG.name,
        "zip": WIDE_ZIP.name,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    update_readme(manifest, n_wide=len(rows), n_batched=len(selected_ids),
                  n_backlog=len(backlog_rows), n_batches=len(batch_recs),
                  n_projects=len({r["project"] for r in rows}),
                  n_groups=len({r["project_group"] for r in rows}))

    # Zips
    with zipfile.ZipFile(WIDE_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for rec in batch_recs:
            z.write(OB / rec["file"], rec["file"])
        z.write(OB / "README.md", "README.md")
    with zipfile.ZipFile(OB / "batches_all.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for rec in manifest["batches"]:
            z.write(OB / rec["file"], rec["file"])
        z.write(OB / "README.md", "README.md")

    # Verify 001-023 bytes unchanged
    for name, raw in existing_files.items():
        now = (OB / name).read_bytes()
        if now != raw:
            raise SystemExit(f"FATAL: {name} was modified")

    # Summary for the parent agent
    batched_rows = [r for r in rows if r["chunk_id"] in selected_ids]
    summary = {
        "n_wide_chunks": len(rows),
        "n_batched": len(batched_rows),
        "n_valuable": sum(r["tier"] == "keyword" for r in batched_rows),
        "n_likely_empty": sum(r["tier"] == "likely_empty" for r in batched_rows),
        "n_backlog": len(backlog_rows),
        "n_batches": len(batch_recs),
        "est_tokens_per_batch": {
            "min": min(b["est_input_tokens"] for b in batch_recs),
            "max": max(b["est_input_tokens"] for b in batch_recs),
            "mean": round(sum(b["est_input_tokens"] for b in batch_recs) / len(batch_recs)),
        },
        "chunks_per_batch": dict(Counter(b["n_chunks"] for b in batch_recs)),
        "batched_by_region": dict(Counter(r["region"] for r in batched_rows)),
        "batched_by_doc_type": dict(Counter(r["doc_type"] for r in batched_rows)),
        "batched_projects": len({r["project"] for r in batched_rows}),
        "batched_project_groups": len({r["project_group"] for r in batched_rows}),
        "valuable_per_group": dict(Counter(r["project_group"] for r in batched_rows if r["tier"] == "keyword")),
        "zip_wide": str(WIDE_ZIP),
        "zip_all": str(OB / "batches_all.zip"),
        "backlog": str(BACKLOG),
        "skipped": skipped,
        "val_stems_marked": sorted(VAL_STEMS),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
