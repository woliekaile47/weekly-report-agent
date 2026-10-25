// Only built-in UI surfaces are translated. Uploaded files and report content are untouched.
export default function () {
  const words = new Map(Object.entries({
    "Drag and drop files here": "将文件拖到这里",
    "Drag and drop a file here": "将文件拖到这里",
    "Drag and drop directories here": "将文件夹拖到这里",
    "Browse files": "选择文件", "Browse file": "选择文件", "Upload": "上传文件",
    "Upload files": "上传文件", "Upload file": "上传文件", "Upload directories": "上传文件夹",
    "Remove file": "移除文件", "Delete": "删除", "Cancel": "取消", "Clear": "清空",
    "Choose an option": "请选择", "No results": "没有匹配项", "No results found": "没有匹配项", "No options": "没有可选项",
    "Select all": "全选", "Search": "搜索", "Today": "今天", "Yesterday": "昨天",
    "Previous month": "上个月", "Next month": "下个月", "Choose date": "选择日期",
    "Open calendar": "打开日历", "Close calendar": "关闭日历", "Clear date": "清空日期",
    "January": "一月", "February": "二月", "March": "三月", "April": "四月",
    "May": "五月", "June": "六月", "July": "七月", "August": "八月",
    "September": "九月", "October": "十月", "November": "十一月", "December": "十二月",
    "Sunday": "星期日", "Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三",
    "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六",
    "Sun": "日", "Mon": "一", "Tue": "二", "Wed": "三", "Thu": "四", "Fri": "五", "Sat": "六",
    "Su": "日", "Mo": "一", "Tu": "二", "We": "三", "Th": "四", "Fr": "五", "Sa": "六",
    "Press Enter to submit form": "按回车键提交表单", "Press Enter to apply": "按回车键确认",
    "Press Ctrl+Enter to submit form": "按 Ctrl＋回车键提交表单",
    "Press Ctrl+Enter to apply": "按 Ctrl＋回车键确认",
    "Press ⌘+Enter to submit form": "按 ⌘＋回车键提交表单", "Press ⌘+Enter to apply": "按 ⌘＋回车键确认",
    "Running...": "正在处理…", "Stop": "停止", "Rerun": "重新运行", "Deploy": "部署",
    "Download": "下载", "Download as CSV": "下载表格", "Fullscreen": "全屏",
  }));
  const selector = [
    '[data-testid="stFileUploader"]', '[data-testid="InputInstructions"]',
    '[data-testid="stDateInput"]', '[data-testid*="DateInput"][data-testid*="Popover"]',
    '[data-testid="stSelectbox"]', '[data-testid="stStatusWidget"]',
    '[data-testid="stAppDeployButton"]', '[data-testid="stToolbar"]',
    '[role="dialog"]', '[role="listbox"]', '[role="tooltip"]', '[role="grid"]',
  ].join(',');
  function translate(text) {
    if (words.has(text)) return words.get(text);
    return text
      .replace(/(?:Limit\s+)?([\d.]+\s*[KMGT]?B) per file/g, '每个文件最多 $1')
      .replace(/File must be (.+?) or smaller\.?/g, '文件大小不能超过 $1')
      .replace(/(.+?) files are not allowed\.?/g, '不支持此文件类型：$1')
      .replace(/File is too large\.?/g, '文件过大，请选择较小的文件')
      .replace(/Too many files\.?/g, '文件数量超过限制')
      .replace(/(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})/g,
        (_, month, year) => `${year}年${words.get(month)}`);
  }
  function update() {
    document.documentElement.lang = 'zh-CN';
    for (const root of document.querySelectorAll(selector)) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.parentElement?.closest('script,style,textarea')) continue;
        const translated = translate(node.nodeValue.trim());
        if (translated !== node.nodeValue.trim()) node.nodeValue = translated;
      }
      for (const element of [root, ...root.querySelectorAll('[aria-label],[title],[placeholder]')]) {
        for (const attr of ['aria-label', 'title', 'placeholder']) {
          const value = element.getAttribute(attr);
          if (value && translate(value) !== value) element.setAttribute(attr, translate(value));
        }
      }
    }
  }
  update();
  let queued = false;
  const observer = new MutationObserver(() => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(() => { queued = false; update(); });
    }
  });
  observer.observe(document.body, {childList: true, subtree: true, characterData: true});
  return () => observer.disconnect();
}
