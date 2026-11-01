# 开源复用与改动记录

本项目是场景 A 的适配实现，不把上游项目、库或其代码声称为原创。许可证原文保存在 `third_party/licenses/`，主要适配差异见 `third_party/patches/`。

| 来源与版本 | 许可 | 实际复用位置 | 改动与边界 |
|---|---|---|---|
| [ByteDance DeerFlow](https://github.com/bytedance/deer-flow/tree/e0f5483fdf4466c3c9b3d19d01f6c7e6f4ed641f) | MIT，Copyright 2025 ByteDance Ltd. and/or its affiliates；2025–2026 DeerFlow Authors | `components/ui/`、`components/ai-elements/` 的侧栏/弹窗/菜单/提示/分屏/InputGroup/成果/步骤组件，`styles/deerflow-theme.css`、`hooks/use-mobile.ts`、`lib/utils.ts`；工作区侧栏、设置弹窗、任务/成果分屏按其原布局适配 | 直接复用纯UI组件及主题变量；Next.js路由与通用Agent API替换为现有React Router/FastAPI接口。文件面板读取真实材料和报告，新增PDF.js排版预览。移除通用聊天、浏览器、项目、渠道及示例等无业务接口的入口。文本提示改为移开即关闭，窄屏切换时不自动弹出遮挡抽屉。保留上游版权及差异记录，不声称集成DeerFlow完整后端。 |
| [manuelbomi Invoice & Receipt Audit Assistant](https://github.com/manuelbomi/LangGraph-based-Invoice-Receipt-Audit-Reconciliation-Assistant/tree/a0a0fc5) | MIT，Copyright 2026 Emmanuel Oyekanlu | 历史列表查询/条目、按需展示的 `GraphView.tsx`、`hooks/useRunStream.ts`；`report_agent/workflow.py` 的显式图与强制 interrupt 审核结构；`report_agent/api.py` 的 REST/后台运行/SSE 编码结构 | 顶部导航与原详情页布局已被DeerFlow工作区替代。保留实际使用的图谱、SSE、历史及后端结构适配。发票字段改为经营周报；持久事件游标、有限返工、超限处理与版本校验为本项目适配。 |
| [mehdimo GenSlide](https://github.com/mehdimo/GenSlide/tree/3b847fc) | 上游 MIT 许可文本 | `report_agent/third_party/genslide_text.py` 的 `_normalize`、`_parse_text` 函数；审核通过/返工的路由结构用于周报版本流转 | 实际复用文本规范化函数；不沿用 PPTX 生成器、默认模型或内存检查点。DOCX 读取补充表格行级证据ID。 |
| [python-docx-template / docxtpl](https://github.com/elapouya/python-docx-template) | LGPL-2.1，作为独立依赖使用 | `report_agent/documents.py` 的 DocxTemplate、InlineImage、Jinja 表格循环 | 不自写 Word 模板引擎；运营人员可以直接编辑 `templates/weekly-report.docx`。本项目未修改 docxtpl 源码。 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | StateGraph、interrupt、Command、SQLite 检查点 | 不自写工作流引擎。 |
| [LangGraph AgentOps Studio](https://github.com/hyf020908/langgraph-agentops-studio/tree/2a12d8095ea19f79c54a5395792f4e8045eb3aec) | MIT，Copyright 2026 hyf020908 | `report_agent/third_party/agentops_ledger.py` 适配 `services/context_compaction.py` 中的 `_unique` 和 `update_revision_ledger` 增量台账算法 | 保留新增、未解决、已解决分类；以稳定意见 ID 代替模糊文本匹配。仅程序验证实际修改后关闭问题，遗漏意见不会自动解决；不引入无关搜索、压缩、治理与多智能体服务。 |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | MIT | 官方 FastMCP、ClientSession、stdio 传输 | 工具实现与授权策略按场景配置；没有自造 MCP 协议。 |
| [Mozilla PDF.js](https://github.com/mozilla/pdf.js) | Apache-2.0，作为独立依赖使用 | `components/workspace/pdf-preview.tsx` | 复用PDF解析、Worker和Canvas渲染；页面控件接入实际报告PDF，不自写PDF渲染引擎。 |
| pandas / openpyxl / python-docx / matplotlib | 各依赖发行版许可 | 工作簿、精确汇总输入、Word 初始化及绘图 | 业务公式、质检及案例适配属于本项目新增工作。 |

其他已评估来源：星图工作台、GPT Researcher、yyw1122 Deep-Research-Agent、Excel Agent 仅作为候选评估或早期参考，不宣称已经集成。当前工作区主题、侧栏、设置与成果分屏统一基于 DeerFlow 适配。2026-11-01 再次检索 GitHub 的 LangGraph 审核返工与台账实现，采用上表 AgentOps 台账，并继续复用既有工作流及 SDK；场景返工依赖规则写入员工配置。

新增代码的必要性：现有上游均不包含赛题的记录ID去重、区域目标、退货冲减、ISO周、毛利率、外卖占比、指定周纪要冲突、三页两图和五条企业用例。这些场景规则无法靠替换提示词获得，采用配置和确定性计算补齐。
