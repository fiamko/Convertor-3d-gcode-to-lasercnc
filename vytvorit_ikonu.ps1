# Original vector-style icon rendered with Windows System.Drawing; no extra dependencies.
Add-Type -AssemblyName System.Drawing
$iconRoot = $PSScriptRoot
$iconSizes = @(16, 24, 32, 48, 64, 128, 256)
$iconImages = @()
foreach ($iconSize in $iconSizes) {
    $bitmap = [System.Drawing.Bitmap]::new($iconSize, $iconSize)
    $g = [System.Drawing.Graphics]::FromImage($bitmap)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.ScaleTransform($iconSize / 256.0, $iconSize / 256.0)
    $shape = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $shape.AddArc(4,4,80,80,180,90); $shape.AddArc(172,4,80,80,270,90)
    $shape.AddArc(172,172,80,80,0,90); $shape.AddArc(4,172,80,80,90,90)
    $shape.CloseFigure()
    $navy = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#142D43'))
    $silver = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#DBE7EE'))
    $red = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#FF654E'))
    $green = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#59D7B0'),10)
    $light = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#F4F7FA'),7)
    $beam = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#FF8665'),7)
    $g.FillPath($navy,$shape)
    $g.FillRectangle($silver,48,47,45,56)
    $points = [System.Drawing.PointF[]]@([System.Drawing.PointF]::new(48,103),[System.Drawing.PointF]::new(93,103),[System.Drawing.PointF]::new(70.5,157))
    $g.FillPolygon($silver,$points)
    $g.FillRectangle($red,157,47,47,54)
    $g.FillRectangle($silver,168,101,25,14)
    $g.DrawLine($beam,180.5,120,180.5,170)
    $g.DrawLine($light,108,126,139,126)
    $g.DrawLine($light,129,115,140,126)
    $g.DrawLine($light,140,126,129,137)
    $g.DrawLine($green,38,188,217,188)
    $g.DrawLine($green,58,188,58,210)
    $g.DrawLine($green,58,210,119,210)
    $g.DrawEllipse($green,125,199,21,21)
    $g.DrawLine($green,166,188,166,211)
    $g.DrawLine($green,166,211,209,211)
    $g.FillEllipse($red,168,163,25,25)
    $g.FillEllipse($silver,176,171,9,9)
    $stream = [System.IO.MemoryStream]::new()
    $bitmap.Save($stream,[System.Drawing.Imaging.ImageFormat]::Png)
    $iconImages += ,$stream.ToArray()
    if ($iconSize -eq 256) { $bitmap.Save((Join-Path $iconRoot 'PrevodnikNC.png'),[System.Drawing.Imaging.ImageFormat]::Png) }
    $stream.Dispose(); $g.Dispose(); $bitmap.Dispose(); $shape.Dispose()
    $navy.Dispose(); $silver.Dispose(); $red.Dispose(); $green.Dispose(); $light.Dispose(); $beam.Dispose()
}
$file = [System.IO.File]::Create((Join-Path $iconRoot 'PrevodnikNC.ico'))
$writer = [System.IO.BinaryWriter]::new($file)
$writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$iconSizes.Length)
$offset = 6 + 16 * $iconSizes.Length
for ($i=0; $i -lt $iconSizes.Length; $i++) {
    $sizeByte = if ($iconSizes[$i] -eq 256) { 0 } else { $iconSizes[$i] }
    $writer.Write([byte]$sizeByte); $writer.Write([byte]$sizeByte)
    $writer.Write([byte]0); $writer.Write([byte]0)
    $writer.Write([uint16]1); $writer.Write([uint16]32)
    $writer.Write([uint32]$iconImages[$i].Length); $writer.Write([uint32]$offset)
    $offset += $iconImages[$i].Length
}
foreach ($bytes in $iconImages) { $writer.Write([byte[]]$bytes) }
$writer.Dispose(); $file.Dispose()
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut((Join-Path $iconRoot 'PrevodnikNC.lnk'))
$shortcut.TargetPath = Join-Path $iconRoot 'spustit_PrevodnikNC.cmd'
$shortcut.WorkingDirectory = $iconRoot
$shortcut.IconLocation = (Join-Path $iconRoot 'PrevodnikNC.ico') + ',0'
$shortcut.Description = 'PrevodnikNC - PCB a laser'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output 'Created PrevodnikNC.ico, PrevodnikNC.png and PrevodnikNC.lnk in the project directory.'
