$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$nodeVersion = [Version] ((& node --version).TrimStart('v'))
if ($nodeVersion -lt [Version] '22.12.0') { throw '前端需要 Node.js 22.12 或更高版本' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw '锁定依赖安装失败' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败' }
npm.cmd ci --prefix frontend --no-fund --no-audit
if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
npm.cmd run build --prefix frontend
if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
& .\.venv\Scripts\python.exe -m uvicorn report_agent.api:app --host 127.0.0.1 --port 8501
