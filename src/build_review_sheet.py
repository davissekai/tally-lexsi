"""Build a draft ground-truth review sheet: one row per (document, field) with every
candidate value the extractor found, its page and quote, plus the calculator's pick.
gold_value / decision columns are left blank for Renhuang to fill (except where a
rule he already set applies). This is a DRAFT for review, not an answer key."""
import json, csv, glob, os
calc = {c["stem"]: c for c in json.load(open("calc_results.json"))}
pick_map = {"project_area":"area_value","area":"area_value","estimated_reductions":"reductions_value",
            "permanence_buffer":"buffer_value","leakage":"leakage_value","crediting_period":"crediting_value"}
rows=[]
for f in sorted(glob.glob("results_clean/*.json")):
    d=json.load(open(f)); stem=os.path.basename(f)[:-5]; c=calc.get(stem,{})
    for field,v in d["merged"].items():
        cands=[]
        if isinstance(v,str):
            status = "not_stated" if v=="not stated" else "clean"
            if v!="not stated": cands=[{"value":v}]
        else:
            if v.get("value")=="conflict": status="conflict"; cands=v.get("conflicts",[])
            else: status="clean"; cands=[v]
        pick = c.get(pick_map.get(field,""),"") if field in pick_map else ""
        gold=""; note=""
        if stem.startswith("1340") and field in ("project_area","area"):
            gold="261,053 ha"; note="Rule set 2026-11-12: credited project area; leakage-belt figure 333,924 ha goes in area_incl_leakage_belt"
        base={"doc":stem,"field":field,"extract_status":status,"calculator_pick":pick,
              "gold_value":gold,"decision_note":note}
        if not cands:
            rows.append({**base,"cand_no":"","cand_value":"","cand_page":"","cand_quote":""})
        for i,k in enumerate(cands,1):
            rows.append({**base,"cand_no":i,"cand_value":k.get("value",""),
                "cand_page":k.get("page",""),"cand_quote":(k.get("quote") or "")[:400]})
keys=["doc","field","extract_status","cand_no","cand_value","cand_page","cand_quote","calculator_pick","gold_value","decision_note"]
with open("ground_truth/answer_key_review_DRAFT.csv","w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=keys); w.writeheader(); w.writerows(rows)
docs=len({r["doc"] for r in rows}); pairs={(r["doc"],r["field"]) for r in rows}
conf={(r["doc"],r["field"]) for r in rows if r["extract_status"]=="conflict"}
ns={(r["doc"],r["field"]) for r in rows if r["extract_status"]=="not_stated"}
print(docs,"docs",len(pairs),"doc-field pairs",len(conf),"conflicts",len(ns),"not stated",len(rows),"rows")
print(sorted({r['field'] for r in rows}))
