"""Isolated fault demonstration: real MCP tools, no model response substitution or production writes."""
import os
import asyncio
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/fault-demo'
os.environ['REPORT_AGENT_DATA']=str(OUT/'data')
sys.path.insert(0,str(ROOT))
from report_agent.service import Service
from report_agent.models import WorkflowError

async def stop_before_model(*args,**kwargs):
    raise WorkflowError('工具恢复演示结束；未调用模型，不生成模拟报告','execution')

async def main():
    data=next((ROOT.parent/'赛题').rglob('销售明细.xlsx')).parent
    service=Service(model=stop_before_model,faults={'compute_metrics':-1})
    task=service.create({'year':2026,'week':44},{'sales':('sales.xlsx',(data/'销售明细.xlsx').read_bytes()),'minutes':('minutes.docx',(data/'周会纪要_2026W44.docx').read_bytes())})
    before=await service.operate(task)
    assert before['status']=='paused' and before['resume_node']=='calculate'
    events=service.store.events(task)
    assert len([e for e in events if e['kind']=='tool_failed'])==3
    print('Injected tool failure: 3 bounded attempts, paused at calculate',flush=True)
    restored=Service(model=stop_before_model)
    after=await restored.operate(task,action='resume')
    events=restored.store.events(task)
    assert sum(e['kind']=='tool_completed' and e['payload']['tool']=='read_sales' for e in events)==1
    assert any(e['kind']=='tool_completed' and e['payload']['tool']=='compute_metrics' for e in events)
    OUT.mkdir(exist_ok=True)
    (OUT/'evidence.json').write_text(json.dumps({'task':task,'before':before,'after':after,'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
    print('New service instance recovered checkpoint; completed input read was not repeated; stopped before model',flush=True)

if __name__=='__main__': asyncio.run(main())
