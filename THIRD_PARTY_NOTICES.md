# 开源复用与改动记录

本项目是场景 A 的适配实现，不把上游项目、库或其代码声称为原创。许可证原文保存在 `third_party/licenses/`，主要适配差异见 `third_party/patches/`。

| 来源与版本 | 许可 | 实际复用位置 | 改动与边界 |
|---|---|---|---|
| [manuelbomi Invoice & Receipt Audit Assistant](https://github.com/manuelbomi/LangGraph-based-Invoice-Receipt-Audit-Reconciliation-Assistant/tree/a0a0fc5) | MIT，Copyright 2026 Emmanuel Oyekanlu | `frontend/src/components/GraphView.tsx`、`frontend/src/hooks/useRunStream.ts`、前端项目构建配置；`report_agent/workflow.py` 的显式图构建与强制 interrupt 审核结构；`report_agent/api.py` 的 REST/后台运行/SSE 编码结构 | 发票字段改为经营周报；Postgres 改为本地 SQLite；事件队列改为按持久事件游标读取；非法审核默认通过改为拒绝；新增有限返工、超限处理及版本校验。业务节点和本地服务适配并非原项目自带功能。 |
| [mehdimo GenSlide](https://github.com/mehdimo/GenSlide/tree/3b847fc) | 上游 MIT 许可文本 | `report_agent/third_party/genslide_text.py` 的 `_normalize`、`_parse_text` 函数；审核通过/返工的路由结构用于周报版本流转 | 实际复用文本规范化函数；不沿用 PPTX 生成器、默认模型或内存检查点。DOCX 读取补充表格行级证据ID。 |
| [python-docx-template / docxtpl](https://github.com/elapouya/python-docx-template) | LGPL-2.1，作为独立依赖使用 | `report_agent/documents.py` 的 DocxTemplate、InlineImage、Jinja 表格循环 | 不自写 Word 模板引擎；运营人员可以直接编辑 `templates/weekly-report.docx`。本项目未修改 docxtpl 源码。 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | StateGraph、interrupt、Command、SQLite 检查点 | 不自写工作流引擎。 |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT | 官方 FastMCP、ClientSession、stdio 传输 | 工具实现与授权策略按场景配置；没有自造 MCP 协议。 |
| pandas / openpyxl / python-docx / matplotlib | 各依赖发行版许可 | 工作簿、精确汇总输入、Word 初始化及绘图 | 业务公式、质检及案例适配属于本项目新增工作。 |

其他已评估来源：星图工作台用于三栏信息布局参考，未复制其代码（本轮未核实可复用许可证）；AgentOps Studio、GPT Researcher、yyw1122 Deep-Research-Agent、Excel Agent 仅作为候选评估或架构参考，不宣称已经集成。

新增代码的必要性：现有上游均不包含赛题的记录ID去重、区域目标、退货冲减、ISO周、毛利率、外卖占比、指定周纪要冲突、三页两图和五条企业用例。这些场景规则无法靠替换提示词获得，采用配置和确定性计算补齐。
