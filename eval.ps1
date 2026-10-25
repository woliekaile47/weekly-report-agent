param([switch]$Live)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PROMPTFOO_PYTHON = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$env:PYTHONUTF8 = '1'
$env:PROMPTFOO_DISABLE_TELEMETRY = '1'
if (-not (Test-Path -LiteralPath 'node_modules\promptfoo')) {
    npm.cmd ci --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw '测评依赖安装失败。' }
}
if ($Live) { npm.cmd run eval:live } else { npm.cmd run eval }
exit $LASTEXITCODE
