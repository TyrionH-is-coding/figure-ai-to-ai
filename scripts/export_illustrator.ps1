[CmdletBinding()]
param(
    [string]$SvgPath,
    [string]$AiPath,
    [string]$PngPath,
    [int]$ExpectedText = -1,
    [ValidateRange(72, 1200)][int]$Dpi = 300,
    [string]$PythonExe,
    [string]$ProgId = 'Illustrator.Application.30',
    [switch]$Probe
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

if ($Probe) {
    [ordered]@{
        progId = $ProgId
        registered = (Test-Path -LiteralPath "Registry::HKEY_CLASSES_ROOT\$ProgId\CLSID")
        running = @((Get-Process Illustrator -ErrorAction SilentlyContinue) | Select-Object Id, Responding)
        mutationPerformed = $false
    } | ConvertTo-Json -Depth 4
    exit 0
}

if (-not $SvgPath -or -not $AiPath -or -not $PngPath) {
    throw 'Specify -SvgPath, -AiPath and -PngPath, or use -Probe.'
}
if ($ExpectedText -lt 0) { throw 'Specify the actual SVG text count with -ExpectedText (0 is valid).' }
$source = (Resolve-Path -LiteralPath $SvgPath).Path
$aiFile = [IO.Path]::GetFullPath($AiPath)
$pngFile = [IO.Path]::GetFullPath($PngPath)
$reportFile = "$aiFile.qa.json"
if ([IO.Path]::GetExtension($source) -ine '.svg' -or
    [IO.Path]::GetExtension($aiFile) -ine '.ai' -or
    [IO.Path]::GetExtension($pngFile) -ine '.png') {
    throw 'Input/output extensions must be .svg, .ai and .png.'
}
foreach ($file in @($aiFile, $pngFile, $reportFile)) {
    if ($file -ieq $source -or (Test-Path -LiteralPath $file)) {
        throw "Refusing to overwrite: $file"
    }
    $parent = Split-Path -Parent $file
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }
}

$checker = Join-Path $PSScriptRoot 'svg_pipeline.py'
if ($PythonExe) {
    $auditLines = & $PythonExe $checker inspect $source --expected-text $ExpectedText
} else {
    $auditLines = & py -3.12 $checker inspect $source --expected-text $ExpectedText
}
if ($LASTEXITCODE -ne 0) { throw "SVG validation failed; Illustrator was not invoked.`n$($auditLines -join "`n")" }
$svgAudit = ($auditLines -join "`n") | ConvertFrom-Json

$config = @{
    svg = $source; ai = $aiFile; png = $pngFile
    expectedText = $ExpectedText; dpi = $Dpi
    sourceTexts = @($svgAudit.text_contents)
}
$runtime = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'export_illustrator.jsx') -Raw -Encoding UTF8
Write-Verbose "Connecting to $ProgId"
$app = New-Object -ComObject $ProgId
Write-Verbose 'Connected; importing SVG into a separate document.'
function Invoke-FigureStage([string]$Stage) {
    $config.stage = $Stage
    $json = $config | ConvertTo-Json -Compress -Depth 8
    $result = $app.DoJavaScript($runtime + "`nexportScientificFigure(" + $json + ');')
    if (-not $result.StartsWith('OK|')) { throw "Illustrator export failed: $result" }
    return ($result.Substring(3) | ConvertFrom-Json)
}
Invoke-FigureStage 'validate' | Out-Null
# Host Open calls allow Illustrator to finish import before inspecting its DOM.
$createdDoc = $app.Open($source)
$saved = Invoke-FigureStage 'save'
$config.imported = $saved.imported
Invoke-FigureStage 'close-created' | Out-Null
$reopenedDoc = $app.Open($aiFile)
$native = Invoke-FigureStage 'verify-export'
if (-not (Test-Path -LiteralPath $aiFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pngFile -PathType Leaf)) { throw 'Native export returned without both files.' }

# Read PNG IHDR to verify actual pixel dimensions, independent of requested DPI.
$bytes = [IO.File]::ReadAllBytes($pngFile)
if ($bytes.Length -lt 24 -or $bytes[0] -ne 137 -or $bytes[1] -ne 80) { throw 'Invalid PNG output.' }
$width = [int64]$bytes[16] * 16777216 + [int64]$bytes[17] * 65536 + [int64]$bytes[18] * 256 + $bytes[19]
$height = [int64]$bytes[20] * 16777216 + [int64]$bytes[21] * 65536 + [int64]$bytes[22] * 256 + $bytes[23]
$expectedWidth = [Math]::Round($native.widthPt * $Dpi / 72)
$expectedHeight = [Math]::Round($native.heightPt * $Dpi / 72)
if ([Math]::Abs($width - $expectedWidth) -gt 2 -or [Math]::Abs($height - $expectedHeight) -gt 2) {
    throw "PNG dimensions differ from artboard/DPI: $width x $height vs $expectedWidth x $expectedHeight."
}
$report = [ordered]@{
    svg = $source; ai = $aiFile; png = $pngFile; dpi = $Dpi
    pngWidth = $width; pngHeight = $height
    svgAudit = $svgAudit; illustrator = $native
    visualReview = 'pending: inspect the exported PNG before claiming completion'
} | ConvertTo-Json -Depth 12
# Exclusive creation is also enforced for the report.
$stream = [IO.File]::Open($reportFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try {
    $encoded = [Text.Encoding]::UTF8.GetBytes($report)
    $stream.Write($encoded, 0, $encoded.Length)
} finally { $stream.Dispose() }
$report
