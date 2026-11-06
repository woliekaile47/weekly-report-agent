from pathlib import Path
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 for width in [390,1440]:
  c=b.new_context(timezone_id='Asia/Shanghai',viewport={'width':width,'height':1000});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.clock.install(time=__import__('datetime').datetime.fromisoformat('2026-11-06T12:00:00+08:00'))
  page.goto('https://wlklqnz.xyz');expect(page.get_by_label('周次',exact=True)).to_have_value('45')
  expect(page.get_by_text('统计周期：2026 年第 45 周（11 月 2 日—11 月 8 日）',exact=True)).to_be_visible()
  page.clock.set_system_time(__import__('datetime').datetime.fromisoformat('2026-11-09T00:01:00+08:00'));page.evaluate("window.dispatchEvent(new Event('focus'))");expect(page.get_by_label('周次',exact=True)).to_have_value('46')
  page.get_by_label('周次',exact=True).fill('44');page.clock.set_system_time(__import__('datetime').datetime.fromisoformat('2026-11-16T12:00:00+08:00'));page.evaluate("window.dispatchEvent(new Event('focus'))");expect(page.get_by_label('周次',exact=True)).to_have_value('44')
  page.reload();expect(page.get_by_label('周次',exact=True)).to_have_value('47')
  assert not page.evaluate('document.documentElement.scrollWidth > innerWidth+1');assert not errors;c.close()
 print('Desktop/mobile: current week, rollover, manual override, reload passed');b.close()
