> 历史记录：当前上线状态、权限和回滚方法以 [2026-11-10 检查记录](review-20261110.md) 为准。下文“尚未完成”和旧额度描述仅适用于当时。

# 公开部署进度（2026-11-04）

目标：Ubuntu ECS 8.163.118.195，域名 wlklqnz.xyz；保留已有 SalesPilot 服务。

## 已完成

- SSH 主机指纹经用户在阿里云 Workbench 核实，本机 known_hosts 已更新并备份。
- 域名 A 记录已解析到服务器。
- 服务器已安装 Python venv、LibreOffice Writer、Noto CJK 字体、Poppler、Certbot；已创建 /srv/weekly-report/venv。
- 本地增加可选公开访问边界（REPORT_PUBLIC=1）：签名浏览器会话、SQLite 任务归属、管理员配置和审核权限、同源写操作校验、按 IP 与全站日额度、单任务并发。
- 访客额度：新建 3/IP/日、全站 20/日；所有任务操作 12/IP/日、全站 60/日。按 UTC 计日，请求失败也计入额度。匿名访客清除会话不能找回任务。
- 管理员通过 /admin 的 HTTP Basic 登录（用户名 admin）取得 8 小时 Cookie；访客 Cookie 30 天。仅可在 HTTPS 上使用。管理员密码至少 16 字符，REPORT_SESSION_SECRET 至少 32 字符。
- Linux 渲染使用 LibreOffice 和 pdfinfo，保留 Windows Microsoft Word 分支。

## 尚未完成，不能视为上线

SSH 在 TCP 连接后等待 banner 超时，相关待执行命令已停止。上传包是否完整、解压和 pip 安装是否开始需重新检查。TLS 配置脚本未确认上传或执行，恢复后必须检查实际状态，不能盲目重复追加 Nginx include。

尚需：依赖安装验证、非 root systemd 服务、独立持久数据目录、管理员凭据在本机安全保存、Nginx 域名路由、HTTPS 证书和自动续期、线上跨会话验证、真实模型连接及 Linux 文档生成验证。

现有 Nginx 容器 salespilot-nginx-1 已占用 80/443：
- /srv/salespilot/infra/nginx/https.conf 单文件只读挂载到 /etc/nginx/conf.d/default.conf。
- snippets 和 certs 目录均只读挂载。修改挂载的单文件要保留 inode。
- 现有证书属于 crm.jaxson.bond，不能用于新域名。
- 新服务仅应监听 Docker 网络可访问的内部地址，并由 Nginx 代理。不得直接对公网暴露后端，以防伪造转发 IP 绕过额度。
- 可信代理 IP 配置后才可启用 uvicorn proxy headers。

本地 runtime/deploy/app.tar.gz 包含 .env，不得提交仓库或公开分发。该包在最终代码修订前生成，恢复部署时必须重新打包。

## 后续更新

SSH 恢复后完成最终代码同步、systemd weekly-report 服务、Nginx 独立域名配置、Let's Encrypt 证书签发（2027-02-02 到期）和续期复制/reload hook。管理员凭据位于 runtime/deploy/管理员登录信息.txt。

线上已验证：首页 GET 200、HTTPS、访客 session、上传 API 200、跨会话任务不可见、管理员登录、真实模型接口 200；现有 SalesPilot 容器当时保持运行。

未通过：Linux LibreOffice 简单文档渲染 65 秒超时。测试启动后 SSH banner 和 HTTP 再次超时。无法确认完整任务生成成功，不能认定部署验收通过。正在尝试停止新服务及 weekly-report 用户下的 soffice；如 SSH 仍失败，需用户从 VNC 执行停止命令。停止与恢复后需检查服务、残留进程及磁盘 I/O，避免继续叠加测试负载。

## 恢复可用（2026-11-04 10:54，Asia/Shanghai）

服务已恢复且已验证重启后可用。线上首页、访客任务隔离、管理员登录、Word/PDF 下载均通过，下载样例 Word 76180 字节、PDF 240513 字节。现有 SalesPilot 容器保持运行。

定位到内存压力下文件缓存反复回收：原 vm.swappiness=0，调整为 60，写入 /etc/sysctl.d/90-weekly-report-memory.conf。恢复旧值需删除该单项配置并 sysctl -w vm.swappiness=0。此项为整机调优。测试磁盘硬限速会拖慢启动和渲染，最终已通过 systemctl set-property 将四项 IO 限额设为 infinity（systemd.system.control 覆盖 io.conf）。服务 I/O 调度从 idle 改为 best-effort；内存和 CPU 限制保留。

本地与线上同步：绘图库改为按需加载、中文图表补 Noto CJK、MCP 保留 HOME 和持久 Matplotlib 缓存、Linux 渲染超时终止进程组以避免残留。最新针对性测试 12 项和权限测试 1 项通过。

完整真实模型样例任务 bb18d970bd6049dcb503154046973ffb 已生成 Word/PDF；文案仍含未知指标占位符及未溯源数字，质检正确暂停等待人工处理。不能宣称正式审核交付通过，也未绕过质检。最终第三版 PDF 渲染成功，下载有效。该任务仅管理员可见。

用户明确此为低访问量赛题，优先单人完整可用，勿继续扩展高并发架构。

## 线上使用者验收（2026-11-04）

修复并发布：手动刷新同步任务、文件和执行记录，增加加载与完成/失败反馈，执行中也允许刷新；访客首页不请求管理员配置；访客超额不再展示无权限的恢复表单；会话初始化失败显示重连入口而不静默误判为访客。

实际 Edge 浏览器验证：1440/390 宽度、访客/管理员首页历史设置任务页，未见页面 JS 错误或横向溢出。访客新建 a10228edff6842b195abf8317546a0db，先仅上传纪要，缺销售表暂停，再从界面补表继续，生成可下载 Word/PDF；刷新后任务保留，另一会话访问返回404。管理员已有完成任务仅做只读测试：PDF 翻页、五类下载、六个详情页签通过，未修改已有审批。会话503故障注入与重连通过。前端21测试通过。

剩余内容质量限制：本轮真实模型输出未完整覆盖纪要“持平”与实际变化之间的冲突，程序质检暂停，草稿可下载；不能宣称每次生成均自动通过审核。原始浏览器测试记录在 runtime/online-user-qa（含会话文件，不得公开或提交）。

2026-11-05：账号密码登录已取消，自己的任务可免登录审核恢复下载，全局配置只在服务器维护。已完成七类上线检查、发布前备份、隔离启动回滚验证和续期dry-run。详情见 final-deployment-check.md。本轮发现旧io.conf重启复活限速，已移除并重启验证。旧管理员登录凭据不再使用。
