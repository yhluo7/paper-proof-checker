# render_report_preview.ps1
#
# Render a paper-proof-checker Markdown report into a PNG preview image.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/render_report_preview.ps1 `
#     -ReportPath examples/quick-demo/expected/paper-proof-report.md `
#     -OutPath docs/assets/report-preview.png
#
# Notes:
#   - Windows only. Uses the built-in .NET System.Drawing API; installs nothing.
#   - The report itself is plain text; this script only draws it. It never rewrites content,
#     so the image cannot contain anything the report does not already contain.
#   - ASCII-only script body on purpose: Windows PowerShell 5.1 reads script files without a
#     BOM using the system ANSI code page, which would corrupt non-ASCII literals. The report
#     is read explicitly as UTF-8 instead.
#   - The caption is deliberately ASCII so provenance stays readable in any locale.

param(
    [Parameter(Mandatory = $true)][string]$ReportPath,
    [Parameter(Mandatory = $true)][string]$OutPath,
    [string]$Caption = '',
    [int]$BodySize = 15,
    [int]$Padding = 28
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not (Test-Path -LiteralPath $ReportPath)) {
    throw "Report not found: $ReportPath"
}

$lines = @(Get-Content -LiteralPath $ReportPath -Encoding UTF8)

$captionFont = New-Object System.Drawing.Font('Consolas', 11, [System.Drawing.FontStyle]::Regular)
$bodyFont = New-Object System.Drawing.Font('NSimSun', $BodySize, [System.Drawing.FontStyle]::Regular)
$h1Font = New-Object System.Drawing.Font('NSimSun', ($BodySize + 9), [System.Drawing.FontStyle]::Bold)
$h2Font = New-Object System.Drawing.Font('NSimSun', ($BodySize + 4), [System.Drawing.FontStyle]::Bold)

# --- layout pass -------------------------------------------------------------
$probe = New-Object System.Drawing.Bitmap 1, 1
$probeGraphics = [System.Drawing.Graphics]::FromImage($probe)
$textRendering = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
$probeGraphics.TextRenderingHint = $textRendering

$caption = $Caption
if ([string]::IsNullOrWhiteSpace($caption)) {
    $caption = "paper-proof-checker 0.2.0 - preview rendered from $ReportPath"
}

$rows = @()
$maxWidth = 0.0
foreach ($line in $lines) {
    $font = $bodyFont
    $text = $line
    if ($line -match '^# ') {
        $font = $h1Font
        $text = $line -replace '^#\s+', ''
    }
    elseif ($line -match '^## ') {
        $font = $h2Font
        $text = $line -replace '^#+\s+', ''
    }
    elseif ($line -match '^-\s') {
        # Bullet marker: keep it visually light without pretending to be a rendered list.
        $bullet = ([string][char]0x00B7) + ' '
        $text = $line -replace '^-\s', $bullet
    }
    $size = $probeGraphics.MeasureString($text, $font)
    if ($size.Width -gt $maxWidth) { $maxWidth = $size.Width }
    $rows += [pscustomobject]@{ Text = $text; Font = $font; Height = [math]::Ceiling($size.Height) }
}

$captionSize = $probeGraphics.MeasureString($caption, $captionFont)
if ($captionSize.Width -gt $maxWidth) { $maxWidth = $captionSize.Width }

$width = [int][math]::Ceiling($maxWidth) + (2 * $Padding)
$height = [int][math]::Ceiling($captionSize.Height) + 16 + $Padding
foreach ($row in $rows) { $height += $row.Height }
$height += $Padding

$probeGraphics.Dispose()
$probe.Dispose()

# --- draw pass ---------------------------------------------------------------
$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.TextRenderingHint = $textRendering
$graphics.Clear([System.Drawing.Color]::White)

$captionBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(110, 110, 110))
$headingBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(20, 20, 20))
$bodyBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(35, 35, 35))
$rulePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(225, 225, 225)), 1

$y = [single]$Padding
$graphics.DrawString($caption, $captionFont, $captionBrush, [single]$Padding, $y)
$y += [single]([math]::Ceiling($captionSize.Height) + 10)
$graphics.DrawLine($rulePen, $Padding, $y, ($width - $Padding), $y)
$y += [single]12

foreach ($row in $rows) {
    $brush = $bodyBrush
    if ($row.Font -eq $h1Font -or $row.Font -eq $h2Font) { $brush = $headingBrush }
    $graphics.DrawString($row.Text, $row.Font, $brush, [single]$Padding, $y)
    $y += [single]$row.Height
}

$outDirectory = Split-Path -Parent $OutPath
if ($outDirectory -and -not (Test-Path -LiteralPath $outDirectory)) {
    New-Item -ItemType Directory -Force -Path $outDirectory | Out-Null
}

$bitmap.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()

Write-Output "rendered: $OutPath"
Write-Output "size: ${width}x${height}"
