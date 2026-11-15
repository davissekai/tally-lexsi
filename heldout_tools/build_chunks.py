import json,sys
sys.path.insert(0,'/workspace/tally')
from chunk_merge import chunk_doc
from tokenizers import Tokenizer
T=Tokenizer.from_file('/workspace/tally/sft_out/v7/tally-lora/tokenizer.json')
class W:
    def encode(self,s,add_special_tokens=False): return T.encode(s,add_special_tokens=False).ids
    def decode(self,ids): return T.decode(ids,skip_special_tokens=False)
w=W()
m=json.loads(open('sft_v7/kaggle_dataset/val_miro_bandai_messages.jsonl').readline())['messages'][0]['content']
HEADER=m[:m.find('\n\nPages ')]
miro=open('run_output/tally/text/2410_Miro-Ghana_Verification_2020-2022.txt').read()
mc=chunk_doc(miro,w,3500,300)
meta=[json.loads(l) for l in open('sft_v7/kaggle_dataset/val_miro_bandai_with_metadata.jsonl')]
mm=[x for x in meta if x['doc'].startswith('2410')]
print('miro rechunk',len(mc),'orig',len(mm), [(c['start_page'],c['end_page']) for c in mc][:6], [(x['start_page'],x['end_page']) for x in mm][:6])
key=json.load(open('heldout/answer_key_heldout.json'))
msgs=open('heldout_run/data/heldout_messages.jsonl','w'); md=open('heldout_run/data/heldout_meta.jsonl','w')
for doc in key:
    txt=open(f'heldout/text/{doc}.txt').read()
    cs=chunk_doc(txt,w,3500,300)
    print(doc,len(cs),'max tokens',max(c['n_tokens'] for c in cs))
    for i,c in enumerate(cs):
        u=f"{HEADER}\n\nPages {c['start_page']}-{c['end_page']}:\n\n{c['text']}"
        msgs.write(json.dumps({'messages':[{'role':'user','content':u}]},ensure_ascii=False)+'\n')
        md.write(json.dumps({'doc':doc,'chunk_index':i,'start_page':c['start_page'],'end_page':c['end_page'],'n_tokens':c['n_tokens']})+'\n')
