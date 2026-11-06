import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'runtime/online-user-qa';data=next((ROOT.parent/'赛题').rglob('销售明细.xlsx')).parent
with sync_playwright() as p:
 browser=p.chromium.launch(channel='msedge',headless=True)
 ctx=browser.new_context(locale='zh-CN');page=ctx.new_page();errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('https://wlklqnz.xyz/');page.get_by_label('任务名称').fill('访客验收：补材料与生成')
 page.get_by_label('年份',exact=True).fill('2026');page.get_by_label('周次',exact=True).fill('44')
 page.locator('input[name=minutes]').set_input_files(str(data/'周会纪要_2026W44.docx'))
 page.get_by_role('button',name='发起任务',exact=True).click();page.wait_for_url('**/runs/*',timeout=30000)
 task=page.url.rsplit('/',1)[1];print('task',task,flush=True)
 (out/'visitor-task.txt').write_text(task);ctx.storage_state(path=str(out/'visitor-session.json'))
 for _ in range(30):
  s=ctx.request.get('https://wlklqnz.xyz/api/runs/'+task).json()
  if s.get('status')=='paused' and not s.get('worker_active'):break
  page.wait_for_timeout(1000)
 expect(page.get_by_role('button',name='上传销售明细并继续')).to_be_visible(timeout=15000)
 page.get_by_role('button',name='刷新任务',exact=True).click();expect(page.get_by_role('status').filter(has_text='已刷新')).to_be_visible()
 other=browser.new_context();assert other.request.get('https://wlklqnz.xyz/api/runs/'+task).status==404;other.close()
 page.reload();expect(page.get_by_role('button',name='上传销售明细并继续')).to_be_visible()
 page.get_by_label('替换或补充销售明细',exact=True).set_input_files(str(data/'销售明细.xlsx'))
 page.get_by_role('button',name='上传销售明细并继续').click()
 for i in range(60):
  page.wait_for_timeout(5000);s=ctx.request.get('https://wlklqnz.xyz/api/runs/'+task).json()
  if i%4==0:print(s.get('status'),s.get('current_node'),flush=True)
  if not s.get('worker_active') and s.get('status') in ['paused','awaiting_human','completed']:break
 files=ctx.request.get('https://wlklqnz.xyz/api/runs/'+task+'/files').json()
 checks=[]
 for f in files['files']:
  r=ctx.request.get('https://wlklqnz.xyz'+f['url']);assert r.status==200;checks.append([f['id'],len(r.body())])
 page.get_by_role('button',name='刷新任务',exact=True).click();expect(page.get_by_role('status').filter(has_text='已刷新')).to_be_visible()
 for tab in ['周报内容','质检记录','修改台账','材料识别','执行记录','执行图谱']:
  page.get_by_role('tab',name=tab,exact=True).click();page.wait_for_timeout(200)
 page.screenshot(path=str(out/'visitor-final.png'))
 (out/'visitor-result.json').write_text(json.dumps({'task':task,'status':s.get('status'),'reason':s.get('reason'),'files':checks,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
 print('finished',s.get('status'),checks,errors,flush=True);browser.close()
