import json,time,hashlib
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1];out=root/'runtime/public-samples-20261106';out.mkdir(exist_ok=True);data=next((root.parent/'赛题').rglob('销售明细.xlsx')).parent
results=[]
with httpx.Client(base_url='https://wlklqnz.xyz',timeout=45) as c:
 c.get('/api/session')
 def wait(t):
  for i in range(140):
   s=c.get('/api/runs/'+t).json()
   if not s.get('worker_active') and s.get('status') in ['paused','awaiting_human','completed']:return s
   if i%12==0:print(t[:6],s.get('status'),s.get('current_node'),flush=True)
   time.sleep(5)
  raise TimeoutError(t)
 for case,week in [('A-05',46),('A-02',43),('A-04',42),('A-01',44),('A-03',44)]:
  folder=out/case;folder.mkdir(exist_ok=True)
  files={}
  if case!='A-03': files['sales']=('sales.xlsx',(data/'销售明细.xlsx').read_bytes())
  if case!='A-05': files['minutes']=('minutes.docx',(data/f'周会纪要_2026W{week}.docx').read_bytes())
  for role,(name,blob) in files.items():(folder/name).write_bytes(blob)
  spec={'title':case+' 公开样例验收','year':2026,'week':week};(folder/'spec.json').write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
  r=c.post('/api/runs',data={'spec':json.dumps(spec)},files=files);r.raise_for_status();t=r.json()['id'];s=wait(t)
  if case=='A-03':
   (folder/'missing-material.json').write_text(json.dumps(s,ensure_ascii=False),encoding='utf-8');assert s['status']=='paused' and not s.get('artifact')
   r=c.post('/api/runs/'+t+'/resume',files={'sales':('sales.xlsx',(data/'销售明细.xlsx').read_bytes())});r.raise_for_status();s=wait(t)
  if s['status']=='awaiting_human':
   r=c.post('/api/runs/'+t+'/review',json={'decision':'approve','reviewer':'自动化样例验收（非业务审批）','version':s['version'],'feedback':'仅验证测试任务交付流程'});r.raise_for_status();s=wait(t)
  events=c.get('/api/runs/'+t+'/events').json();manifest=c.get('/api/runs/'+t+'/files').json()
  for name,value in [('state',s),('events',events),('files',manifest)]: (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
  for f in manifest['files']:
   r=c.get(f['url']);r.raise_for_status();(folder/f['name']).write_bytes(r.content)
  assert s['total_model_calls']==sum(e['kind']=='model_started' for e in events['events'])
  result={'case':case,'task':t,'status':s['status'],'reason':s.get('reason'),'calls':s['total_model_calls'],'seconds':s['total_active_seconds'],'quality':s.get('quality',{}).get('passed')};results.append(result)
  (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(result,flush=True)
