param([switch]$Mock)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '请先安装 Python 3.12。' }
    & $taskPython -m pip install -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
    & $taskPython -m pip install --no-deps -e .
}
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
if ($Mock) { $env:LLM_MODE = 'mock' }
& $taskPython -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
