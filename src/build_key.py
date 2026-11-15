import json,re,sys
from pathlib import Path
sys.path.insert(0,'.')
from key_draft import K,STEMS
FIELDS=["baseline","additionality","leakage","permanence_buffer","crediting_period","area","estimated_reductions"]
from paths import prepend_import_paths, first_existing
ROOT=prepend_import_paths()
TXT=first_existing(ROOT/'data_expansion'/'text', ROOT/'data'/'text')
if TXT is None:
    raise SystemExit('data_expansion/text not found; set TALLY_ROOT')
def pages(stem):
    t=(TXT/f'{stem}.txt').read_text(encoding='utf-8'); p=re.split(r'--- page (\d+) ---',t)
    return {int(p[i]):re.sub(r'\s+',' ',p[i+1]) for i in range(1,len(p),2)}
def nums(v): return [n.replace(',','').replace('.','') for n in re.findall(r'\d[\d,.]*\d|\d',v)]
key={}; fails=[]; checks=0
for d,fs in K.items():
    stem=STEMS[d]; P=pages(stem); key[stem]={}
    for f in FIELDS:
        e=fs.get(f)
        if e is None:
            key[stem][f]={"gold_value":"NOT_STATED","page":None,"quote":None,"alt_quotes":[],"decision_note":"not stated / not found as a clean statement"}; continue
        v,q,alts,note=e; out=[]
        for qq in [q]+alts:
            checks+=1
            hit=[pg for pg,s in P.items() if qq in s]
            if len(qq)<16 or not hit: fails.append((stem,f,qq[:80],'not found' if not hit else 'short')); continue
            out.append({"quote":qq,"page":hit[0],"n_pages_with_quote":len(hit)})
        if not out: fails.append((stem,f,'NO VALID QUOTE','')); continue
        key[stem][f]={"gold_value":v,"page":out[0]["page"],"quote":out[0]["quote"],"alt_quotes":[{"quote":o["quote"],"page":o["page"]} for o in out[1:]],"decision_note":note}
print('quotes checked',checks,'fails',len(fails))
for x in fails: print(x)
json.dump({"_meta":{"version":"v5","drafted":"2026-11-13 (Africa/Accra)","method":"hand-drafted from data_expansion/text (pdftotext -layout); quotes are literal substrings of the whitespace-collapsed page text","rules":"Verra definitions; area = credited project area; estimated_reductions = after buffer where the PD gives it (else the PD's stated net total, flagged); crediting period = full date range; PD totals; buffer %; leakage tCO2e"},**key},open(ROOT/'data_expansion'/'answer_key_v5.json','w'),ensure_ascii=False,indent=1)

# ---- auto alt quotes: other literal places where the same distinctive number is restated ----
import rebalance as R
auto_n=0
for stem,v in key.items():
    if stem=='_meta': continue
    P=pages(stem)
    for f in ["area","estimated_reductions","baseline","leakage"]:
        e=v[f]
        if e['quote'] is None: continue
        long=[n for n in re.findall(r'\d[\d,. ]*\d',e['gold_value']) if len(re.sub(r'\D','',n))>=5]
        if not long: continue
        n=long[0].strip()
        digits=re.sub(r'\D','',n)
        # match the number with , . or space as separators, as it appears in this doc
        pat=re.compile(r'(?<![\d.,])-?'+r"[,.\s']?".join(digits[i] for i in range(len(digits)))+r'(?![\d])')
        if (stem,f) in {('673_PD','baseline')}: continue
        have=[e['quote']]+[a['quote'] for a in e['alt_quotes']]
        added=[]
        for pg,s in sorted(P.items()):
            for m in pat.finditer(s):
                tok=s[m.start():m.end()]
                if re.sub(r'\D','',tok)!=digits: continue
                if any(tok in h and h in s for h in have+added): continue
                q=R.window(s,m.start(),m.end())
                if len(q)<16 or q not in s: continue
                if (stem,pg) in {('1311_PD',137)}: continue
                if f=='area' and not re.search(r'\bha\b|hectare',q,re.I): continue
                if f!='area' and not re.search(r't\s*CO2|tCO2|tonnes|tons|Total|ERs|VCU|leakage|baseline|emission',q,re.I): continue
                added.append(q); e['alt_quotes'].append({"quote":q,"page":pg,"source":"auto_number_match"}); auto_n+=1
print('auto alt quotes added',auto_n)
json.dump(key,open(ROOT/'data_expansion'/'answer_key_v5.json','w'),ensure_ascii=False,indent=1)
