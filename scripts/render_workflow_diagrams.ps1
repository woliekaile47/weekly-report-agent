$ErrorActionPreference = 'Stop'
$rootDir = Split-Path $PSScriptRoot -Parent
$toolDir = Join-Path $rootDir 'runtime\workflow-diagrams'
$diagramDir = Join-Path $rootDir 'docs\diagrams'
$cli = Join-Path $toolDir 'node_modules\.bin\mmdc.cmd'
$browserExecutable = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browserExecutable) { throw '需要本机 Microsoft Edge 或 Google Chrome 来渲染流程图。' }

New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
if (-not (Test-Path -LiteralPath $cli)) {
    $previousSkipDownload = $env:PUPPETEER_SKIP_DOWNLOAD
    try {
        $env:PUPPETEER_SKIP_DOWNLOAD = 'true'
        & npm.cmd install --prefix $toolDir --no-audit --no-fund --save-exact '@mermaid-js/mermaid-cli@12.0.0'
        if ($LASTEXITCODE -ne 0) { throw '安装 Mermaid CLI 失败。' }
    } finally {
        $env:PUPPETEER_SKIP_DOWNLOAD = $previousSkipDownload
    }
}

$browserConfig = Join-Path $toolDir 'puppeteer.json'
$mermaidConfig = Join-Path $toolDir 'mermaid.json'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($browserConfig, (@{
    executablePath = $browserExecutable
    headless = $true
} | ConvertTo-Json), $utf8)
[System.IO.File]::WriteAllText($mermaidConfig, (@{
    theme = 'base'
    look = 'classic'
    htmlLabels = $true
    themeVariables = @{
        fontFamily = 'Microsoft YaHei, Segoe UI, sans-serif'
        fontSize = '16px'
        primaryColor = '#fafaf8'
        primaryTextColor = '#20241f'
        primaryBorderColor = '#777c74'
        lineColor = '#777c74'
        edgeLabelBackground = '#ffffff'
    }
    flowchart = @{ curve = 'linear'; nodeSpacing = 36; rankSpacing = 42; wrappingWidth = 320 }
} | ConvertTo-Json -Depth 4), $utf8)

foreach ($source in Get-ChildItem -LiteralPath $diagramDir -Filter '*.mmd') {
    foreach ($format in @('svg', 'png')) {
        $outputFile = Join-Path $diagramDir ($source.BaseName + '.' + $format)
        & $cli -p $browserConfig -c $mermaidConfig -i $source.FullName -o $outputFile -b white --size 2400 --no-font-embed
        if ($LASTEXITCODE -ne 0) { throw "流程图渲染失败：$($source.Name) → $format" }
    }
}
