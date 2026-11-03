$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw '未找到 Python 环境。请先运行 .\install.ps1 完成首次安装。'
}
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    throw '未找到前端构建。请先运行 .\install.ps1 完成首次安装。'
}
& .\.venv\Scripts\python.exe -m uvicorn report_agent.api:app --host 127.0.0.1 --port 8501
