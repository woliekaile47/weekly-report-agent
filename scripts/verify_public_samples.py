"""Verify downloaded live sample evidence against published numeric expectations."""
import json
import zipfile
from pathlib import Path
import pymupdf
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/public-samples-20261106'
expected={'A-01':(573635,-9.3,61.1,31.8),'A-02':(632486,4.4,60.1,31.3),'A-04':(605909,-11.7,61.0,31.5)}
for case,values in expected.items():
 folder=OUT/case;s=json.loads((folder/'state.json').read_text(encoding='utf-8'));m=s['metrics'];t=m['total']
 assert abs(t['cents']/100-values[0])<1
 assert (t['change'],t['margin'],t['delivery_share'])==values[1:]
 assert s['quality']['passed'] and s['status']=='completed'
 with pymupdf.open(next(folder.glob('*.pdf'))) as doc:assert len(doc)<=3
 with zipfile.ZipFile(next(folder.glob('*.zip'))) as z:assert z.testzip() is None
 if case=='A-01':
  assert m['quality']['return_count']==11 and m['quality']['return_cents']==-26000
  assert [r['product_id'] for r in m['top_products']]==['D02','D03','D01','C04','C01']
 if case=='A-02':
  assert m['quality']['removed_count']==29 and m['quality']['removed_cents']==562941
  assert [r['product_id'] for r in m['top_products']]==['D02','D03','D01','C04','C05']
 if case=='A-04':
  assert m['quality']['return_count']==15 and m['quality']['return_cents']==-65600
  assert m['quality']['missing_days']==[{'store_id':'GZ02','store':'广州海珠店','date':'2026-10-14'}]
 print(case,'published core figures, quality, PDF page count, delivery ZIP: PASS')
s=json.loads((OUT/'A-03/state.json').read_text(encoding='utf-8'));before=json.loads((OUT/'A-03/missing-material.json').read_text(encoding='utf-8'));assert before['task_id']==s['task_id'] and before['status']=='paused' and s['status']=='completed' and not before.get('artifact')
s=json.loads((OUT/'A-05/state.json').read_text(encoding='utf-8'));assert s['status']=='paused' and not s.get('artifact') and '2026-11-01' in s['reason'] and s['total_model_calls']==0
print('A-03 same-task recovery, A-05 no fabricated report: PASS')
