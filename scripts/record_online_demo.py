"""Read-only recording of saved, real online sample results; never submits approvals."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/submission';OUT.mkdir(exist_ok=True)
BASE='https://wlklqnz.xyz'
password=dict(line.split('=',1) for line in (ROOT/'runtime/deploy/service.env').read_text().splitlines() if '=' in line)['REPORT_ADMIN_PASSWORD']
results=json.loads((ROOT/'runtime/public-samples-20261106/results.json').read_text(encoding='utf-8'))
ids={r['case']:r['task'] for r in results}
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 c=b.new_context(http_credentials={'username':'admin','password':password},viewport={'width':1440,'height':1000},record_video_dir=str(OUT/'raw'),record_video_size={'width':1440,'height':1000})
 c.request.get(BASE+'/admin')
 page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def show(title,detail):
  page.evaluate('''([title,detail])=>{document.getElementById('demo-caption')?.remove();let e=document.createElement('div');e.id='demo-caption';e.style='position:fixed;bottom:20px;left:15%;width:70%;padding:20px;z-index:99999;background:#142d4fee;color:white;border-radius:12px;font:18px sans-serif;pointer-events:none';let t=document.createElement('b');t.textContent=title;let d=document.createElement('p');d.textContent=detail;e.append(t,d);document.body.append(e)}''',[title,detail]);page.wait_for_timeout(9000)
 page.goto(BASE,wait_until='networkidle');show('经营周报员工｜真实线上成果回放','展示已保存的真实模型样例结果，非实时生成录像。访客免登录；管理配置需登录。')
 page.goto(BASE+'/runs/'+ids['A-01'],wait_until='networkidle');show('第44周真实成果','程序计算金额，模型解释异常；质检通过后，经标注为测试的审核生成交付包。')
 for tab,detail in [('材料识别','销售与纪要识别结果，原始记录和来源可追溯。'),('周报内容','结构化指标、异常原因及行动项；模型陈述须通过程序质检。'),('质检记录','查看实际质检结果与返工记录，不跳过失败检查。'),('修改台账','逐项记录生成与修改，正式业务审核须由使用者完成。'),('执行记录','模型调用、工具执行、质检及暂停均记录事件。'),('执行图谱','工作流控制状态流转，失败保留检查点。')]:
  page.get_by_role('tab',name=tab,exact=True).click();show(tab,detail)
 page.goto(BASE+'/runs/'+ids['A-03'],wait_until='networkidle');show('缺材料后恢复｜同一任务','A-03只上传纪要后暂停；补传销售后继续，已完成质检与测试交付。')
 page.goto(BASE+'/runs/'+ids['A-05'],wait_until='networkidle');show('无数据周期｜明确暂停','第46周不在销售文件覆盖范围内；系统解释原因，没有编造周报。')
 page.goto(BASE+'/settings/employee',wait_until='networkidle');show('管理员配置','职责、业务规则、列映射和质检可配置；普通访客不能修改全局配置。')
 page.goto(BASE+'/settings/limits',wait_until='networkidle');show('有界执行','每日任务额度已取消；单轮模型次数、超时、工具重试和质检返工仍有上限。')
 page.goto(BASE,wait_until='networkidle');show('提交与复现','源码已公开；五条样例及故障恢复证据另存。此录像不替代现场盲测与业务验收。')
 video=page.video;c.close();video.save_as(str(OUT/'产品演示.webm'));b.close()
 (OUT/'video-result.json').write_text(json.dumps({'source':'real online saved results','errors':errors,'automatic_approvals':False},ensure_ascii=False),encoding='utf-8');assert not errors
 print('Recorded runtime/submission/产品演示.webm')
