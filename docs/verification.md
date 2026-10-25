# 验证记录

验证日期：2026-10-25（Asia/Shanghai）。环境：Windows、Python 3.12、Node.js 25；依赖版本见 Python 与 npm 锁文件。

| 验证项 | 结果 | 说明 |
|---|---|---|
| pytest | 21 / 21 通过 | 数据边界、审核、故障、强制退出恢复、预算、并发、文件篡改、UI 操作 |
| Ruff | 通过 | 语法、未使用变量与导入检查 |
| pip check | 通过 | 已安装依赖无冲突 |
| promptfoo 离线工作流 | 19 / 19 通过 | 真实 LangGraph、MCP、SQLite、Word，只替换模型 |
| Agnes 真实测评首次 | 2 / 3 通过 | 退回修改、纪要指令干扰通过；正常分析因引用编号误判失败 |
| 正常分析修正后复测 | 1 / 1 通过 | 有效纪要编号不再误判为未引用数字，无效编号仍拦截 |
| Word 可视化 | 通过 | 使用本机 Microsoft Word 导出并检查全部页面，模拟样例两页、真实模型样例三页，中文、图表与表格正常 |
| 应用健康检查 | HTTP 200 | 本地地址 `http://127.0.0.1:8501/_stcore/health` |
| 密钥检查 | 通过 | `.env` 被忽略，暂存文件不包含真实密钥 |

真实模型的三个场景均有通过记录，但不是最终版本单次完整运行的 3/3；保留首次失败与复测结果，不将其合并包装成一次满分运行。免费服务联调中出现过网络错误和结构化输出不合规，程序有限重试后暂停或继续，不以模拟结果冒充成功。

## 关键证据

- 正常样例：本期 39,000 元，上期 42,000 元，环比 -7.14%；华东区 20,000 元、华南区 19,000 元。
- 工具持续故障：共尝试三次后暂停；新服务实例恢复后继续计算，销售读取成功事件仍只有一次。
- 真正进程退出：测试在模型节点调用 `os._exit(93)`，重启后从未完成节点继续；已完成的数据读取不重复，已开始的模型请求仍计入预算。
- 人工审核：退回必须有意见，版本递增后重新质检；旧版本审核、未经审核交付和修改后文件通过审核均被拦截。
- 界面测试：通过 Streamlit AppTest 创建模拟任务、读取待审核状态、提交退回意见并检查第二版。
- 引用回归：正文中的有效 `M002` 引用可通过，无效 `M999` 不通过；修改 Word 中的金额会导致正文一致性检查失败。
- 真实返工：Agnes 在修改说明中响应华东区意见，并在行动建议中明确区域负责人牵头核实补货进度。

详细测评摘要见 `evaluation-summary.json`。完整原始结果保存在本地 `evals/results/offline.json`、`live.json`、`live-recheck.json`，任务证据和生成文件位于 `runtime/evals/`，均不提交 Git。

## 复现

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
powershell -ExecutionPolicy Bypass -File .\eval.ps1
powershell -ExecutionPolicy Bypass -File .\eval.ps1 -Live
```

可选 Word 排版复核需要本机 Microsoft Word、pywin32 和 PyMuPDF，后者不属于应用必要依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install pymupdf
.\.venv\Scripts\python.exe scripts\preview_report.py <报告.docx路径>
```

## 尚未验证的范围

企业未提供五条公开样例及十五条盲测输入，因此不能报告企业验收通过率。当前样例为自造模拟数据。未进行多用户、生产身份认证、大规模性能或跨平台完整验收。

审核语义充分性、因果判断和建议业务价值仍由人工判断；数字检查主要约束指标占位符及阿拉伯数字，不能证明所有自然语言表述都正确。程序提供退回机制供人修改。

浏览器截图启动被本机自动审批拦截，未生成浏览器截图；界面功能用自动交互测试验证。提交用演示视频尚未录制，五分钟演示脚本在 `demo.md`。
