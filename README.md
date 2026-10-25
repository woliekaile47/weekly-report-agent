# 经营周报员工

基于 **LangGraph + Agent Skills + MCP 官方 Python SDK + Agnes AI + promptfoo** 的本地数字员工。
读取销售 Excel/CSV 与周会纪要，生成包含图表、指标和证据的 Word 周报；自动质检通过后进入人工审核，退回意见在同一任务内返工，审核通过后交付文件包。

## 启动

Windows 安装 Python 3.12，双击 `start.bat`。首次会安装锁定依赖，随后打开：

<http://127.0.0.1:8501>

也可以在项目根目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env   # 仅在尚无 .env 时执行
.\start.ps1
```

配置本地 `.env`：

```dotenv
LLM_BASE_URL=https://apihub.agnes-ai.com/v1
LLM_MODEL=agnes-3.0-flash
LLM_API_KEY=填写自己的密钥
LLM_MODE=live
DATA_DIR=runtime
```

`.env` 和运行数据已加入 `.gitignore`。密钥仅用于模型 HTTP 请求，不传给 MCP 工具进程，不写入任务状态、评测输出或事件记录。程序不会在真实模型失败时偷偷切换为模拟输出。

Linux/macOS 可使用 Python 3.12 创建 `.venv` 并安装依赖，然后执行 `.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1`。图表需要可用的中文字体，如 Noto Sans CJK SC。当前主要验证环境为 Windows。

## 第一次演示

1. 新建任务，统计周期选择 **2026-10-26 至 2026-11-01**。
2. 勾选“使用项目自带的模拟样例数据”。真实模型模式会调用 Agnes；离线演示使用固定模型替身。
3. 执行后查看指标、图表、纪要引用、Word 文件与质检记录。
4. 填写审核人，选择“退回修改”，输入“华东区下滑原因没说清楚，请结合周会纪要补充”。
5. 查看第二版修改说明及新的质检结果。通过当前版本后下载完整交付包。

无网络演示：`powershell -ExecutionPolicy Bypass -File .\start.ps1 -Mock`。

命令行也支持恢复与审核：

```powershell
.\.venv\Scripts\python.exe -m weekly_report.cli --mode live demo
.\.venv\Scripts\python.exe -m weekly_report.cli state <任务ID>
.\.venv\Scripts\python.exe -m weekly_report.cli review <任务ID> reject --version 1 --reviewer 张三 --feedback "请补充华东区原因"
.\.venv\Scripts\python.exe -m weekly_report.cli review <任务ID> approve --version 2 --reviewer 张三
.\.venv\Scripts\python.exe -m weekly_report.cli resume <任务ID>
```

命令行 `--mode mock demo --approve` 仅用于自动化演示模拟审核，不适用于真实模型任务。

## 输入约定

销售文件支持 `.xlsx` 和 `.csv`，必需列为 `日期、门店、区域、品类、销售额`，也支持 `date、store、region、category、amount`。列名映射可在 `config/employee.yaml` 调整。Excel 读取第一个工作表；CSV 支持 UTF-8 和 GB18030。

周会纪要支持 `.docx`、UTF-8 `.txt`、`.md`。每份上传文件最多 20 MB；销售明细最多十万行；纪要最多六万字符。统计周期为一至三十一天，默认需要环比，比较期是紧邻本期的前一个同长度周期。

销售额以元输入，程序转换为整数分计算；负数视为退货或冲减。无上期记录与上期金额为零分开处理。疑似重复明细保留并提示核实。分组没有记录不等于零销售。所有分析仅覆盖上传数据范围。

## 工程结构

```text
app.py                       本地操作界面
weekly_report/
  graph.py                   LangGraph 状态、暂停、审核、返工与交付
  service.py                 任务入口、互斥锁、输入版本、审核守卫
  mcp_server.py              官方 SDK 实现的六个工具
  mcp_client.py              MCP 会话、工具白名单、重试与缓存
  analysis.py                数据读取与确定性指标计算
  model.py                   Agnes 接入与明确标记的离线替身
  report.py                  图表、Word 和自动质检
  store.py                   SQLite 审计、缓存、路径校验
config/employee.yaml         工具许可、限制、质检与字段映射
skills/weekly-report/        Agent Skills 岗位配置与参考资料
samples/                    自造模拟输入，不是企业官方公开用例
tests/                      程序、故障恢复与界面测试
evals/                      promptfoo 工作流测评与真实模型测评
docs/                       架构、技术报告、验证与演示说明
runtime/                    本地状态、输入与交付文件，不入 Git
```

## 配置与质量控制

员工职责、步骤、分析原则在 `skills/weekly-report/SKILL.md`；指标口径和报告要求在对应 `references/`、`assets/`。每个新任务保存完整员工配置快照和版本摘要，避免正在审核的任务受到配置改动影响。修改配置后请创建新任务。

程序负责关键控制：工具白名单、状态流转、预算、质检和当前版本审批，模型仅生成结构化分析。图的执行顺序由程序固定，工具调用走真实 MCP 协议，不依赖模型是否支持原生 Function Calling。

默认限制：每轮最多十二次模型请求，单次请求六十秒，活动执行累计六百秒，工具最多重试两次，模型执行错误最多重试两次，质检最多修正两轮。人工等待不计时；人工明确恢复或退回修改后开启新一轮预算，完整历史不清空。模型请求开始前持久化记录，进程中断的请求同样消耗轮次预算。

质检包括章节、字数、数值引用和表格、证据原文、图表文件、禁用词、退回意见响应。确定性检查能验证引用存在和原文匹配，不能证明业务因果成立或意见已充分落实；最终由人工审核判断。

## 测试和测评

Python 测试与检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

promptfoo 需要 Node.js 22 或更新版本，首次运行安装锁定的 npm 依赖：

```powershell
powershell -ExecutionPolicy Bypass -File .\eval.ps1
powershell -ExecutionPolicy Bypass -File .\eval.ps1 -Live
```

离线测评运行真实 LangGraph、SQLite、MCP 子进程、图表与 Word 工具，只替换模型输出。真实测评调用 `agnes-3.0-flash`，覆盖正常分析、审核退回和纪要指令干扰。测试过程中的审核决定由测试驱动模拟，真实应用不会自动审批。结果写入 `evals/results/`；运行 `npm run eval:view` 可查看 promptfoo 结果。

## 断点恢复与交付

每个任务使用独立 `thread_id`；SQLite 保存 LangGraph 检查点，工具按任务、参数和技能版本记录成功结果。重启后从历史任务点击继续；故障暂停后点击恢复。已经完成并记录的步骤不重复执行；如果进程恰好在外部调用完成但记录前退出，重放可能重新执行该调用，写文件工具通过确定路径和原子替换保持同一逻辑产物。

交付包包含经营周报、历次质检、审核意见及批准记录、执行事件、文件摘要。审批绑定任务版本和 Word SHA-256，未经质检或内容在审核后发生变化不能交付。

## 范围与限制

这是本地单用户竞赛演示版，绑定回环地址；审核人姓名用于记录，尚未接企业登录与权限系统。运行数据包含业务材料，保存在本地 `runtime/`。不提供生产多租户、定时调度或在线协作。

免费模型服务可能限流或不可用，程序按限制重试后暂停。硬退出时已完成检查点和模型请求次数能恢复；中断中的调用无法保证只执行一次，也无法完整还原其活动耗时。模型对原因的业务理解和建议质量仍需人工复核。

企业公开样例尚未提供，当前模拟测试不能代表企业十五条盲测成绩。详见 `docs/verification.md`。
