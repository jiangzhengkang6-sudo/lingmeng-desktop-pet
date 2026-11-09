param(
  [Parameter(Mandatory = $true)]
  [string]$Source,
  [Parameter(Mandatory = $true)]
  [string]$Output,
  [int]$Columns = 8,
  [int]$Rows = 13,
  [int]$FrameSize = 512
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

function Clamp([int]$value, [int]$minimum, [int]$maximum) {
  return [Math]::Max($minimum, [Math]::Min($maximum, $value))
}

function IsBackgroundPixel([byte[]]$pixels, [int]$offset) {
  $b = [int]$pixels[$offset]
  $g = [int]$pixels[$offset + 1]
  $r = [int]$pixels[$offset + 2]
  $a = [int]$pixels[$offset + 3]
  if ($a -eq 0) { return $true }

  $maximum = [Math]::Max($r, [Math]::Max($g, $b))
  $minimum = [Math]::Min($r, [Math]::Min($g, $b))
  $spread = $maximum - $minimum
  $lightNeutral = $minimum -ge 215 -and $spread -le 45
  # The source sheet includes pale blue watermark text at the cell edges.
  # Only edge-connected pixels use this broader rule, so character details stay intact.
  $lightPastel = $minimum -ge 175 -and $spread -le 95
  $grayGrid = $minimum -ge 165 -and $spread -le 18
  $blackCanvas = $maximum -le 18 -and $spread -le 12
  return $lightNeutral -or $lightPastel -or $grayGrid -or $blackCanvas
}

$sourceBitmap = [System.Drawing.Bitmap]::new($Source)
$sourceArgb = [System.Drawing.Bitmap]::new($sourceBitmap.Width, $sourceBitmap.Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$copyGraphics = [System.Drawing.Graphics]::FromImage($sourceArgb)
$copyGraphics.DrawImageUnscaled($sourceBitmap, 0, 0)
$copyGraphics.Dispose()
$sourceBitmap.Dispose()

$sourceRect = [System.Drawing.Rectangle]::new(0, 0, $sourceArgb.Width, $sourceArgb.Height)
$sourceData = $sourceArgb.LockBits($sourceRect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$sourceStride = [Math]::Abs($sourceData.Stride)
$sourceBytes = [byte[]]::new($sourceStride * $sourceArgb.Height)
[Runtime.InteropServices.Marshal]::Copy($sourceData.Scan0, $sourceBytes, 0, $sourceBytes.Length)
$sourceArgb.UnlockBits($sourceData)

$outputWidth = $Columns * $FrameSize
$outputHeight = $Rows * $FrameSize
$outputBitmap = [System.Drawing.Bitmap]::new($outputWidth, $outputHeight, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$outputRect = [System.Drawing.Rectangle]::new(0, 0, $outputWidth, $outputHeight)
$outputData = $outputBitmap.LockBits($outputRect, [System.Drawing.Imaging.ImageLockMode]::WriteOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$outputStride = [Math]::Abs($outputData.Stride)
$outputBytes = [byte[]]::new($outputStride * $outputHeight)
$validFrames = [System.Collections.Generic.List[int]]::new()
$blankFrames = [System.Collections.Generic.List[int]]::new()

try {
  for ($row = 0; $row -lt $Rows; $row++) {
    for ($column = 0; $column -lt $Columns; $column++) {
      $frameIndex = $row * $Columns + $column
      $left = [int][Math]::Round($sourceArgb.Width * $column / $Columns)
      $right = [int][Math]::Round($sourceArgb.Width * ($column + 1) / $Columns)
      $top = [int][Math]::Round($sourceArgb.Height * $row / $Rows)
      $bottom = [int][Math]::Round($sourceArgb.Height * ($row + 1) / $Rows)
      $margin = 5
      $cropLeft = $left + $margin
      $cropTop = $top + $margin
      $cropWidth = [Math]::Max(1, $right - $left - ($margin * 2))
      $cropHeight = [Math]::Max(1, $bottom - $top - ($margin * 2))

      $visited = [bool[]]::new($cropWidth * $cropHeight)
      $background = [bool[]]::new($cropWidth * $cropHeight)
      $queue = [System.Collections.Generic.Queue[int]]::new()

      for ($y = 0; $y -lt $cropHeight; $y++) {
        for ($x = 0; $x -lt $cropWidth; $x++) {
          if ($x -ne 0 -and $y -ne 0 -and $x -ne ($cropWidth - 1) -and $y -ne ($cropHeight - 1)) { continue }
          $localIndex = $y * $cropWidth + $x
          if ($visited[$localIndex]) { continue }
          $sourceOffset = ($cropTop + $y) * $sourceStride + (($cropLeft + $x) * 4)
          if (IsBackgroundPixel $sourceBytes $sourceOffset) {
            $visited[$localIndex] = $true
            $background[$localIndex] = $true
            $queue.Enqueue($localIndex)
          }
        }
      }

      while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        $x = $current % $cropWidth
        $y = [int]($current / $cropWidth)
        $neighbors = @(
          ($current - 1),
          ($current + 1),
          ($current - $cropWidth),
          ($current + $cropWidth)
        )
        foreach ($neighbor in $neighbors) {
          if ($neighbor -lt 0 -or $neighbor -ge $background.Length) { continue }
          $neighborX = $neighbor % $cropWidth
          $neighborY = [int]($neighbor / $cropWidth)
          if ([Math]::Abs($neighborX - $x) + [Math]::Abs($neighborY - $y) -ne 1) { continue }
          if ($visited[$neighbor]) { continue }
          $neighborOffset = ($cropTop + $neighborY) * $sourceStride + (($cropLeft + $neighborX) * 4)
          if (IsBackgroundPixel $sourceBytes $neighborOffset) {
            $visited[$neighbor] = $true
            $background[$neighbor] = $true
            $queue.Enqueue($neighbor)
          }
        }
      }

      $foregroundCount = 0
      for ($y = 0; $y -lt $cropHeight; $y++) {
        for ($x = 0; $x -lt $cropWidth; $x++) {
          $localIndex = $y * $cropWidth + $x
          if (-not $background[$localIndex]) { $foregroundCount++ }
        }
      }

      # Sample the cropped source frame into one fixed-size output cell.
      for ($outputY = 0; $outputY -lt $FrameSize; $outputY++) {
        $sourceLocalY = [int]($outputY * $cropHeight / $FrameSize)
        $sourceLocalY = Clamp $sourceLocalY 0 ($cropHeight - 1)
        for ($outputX = 0; $outputX -lt $FrameSize; $outputX++) {
          $sourceLocalX = [int]($outputX * $cropWidth / $FrameSize)
          $sourceLocalX = Clamp $sourceLocalX 0 ($cropWidth - 1)
          $localIndex = $sourceLocalY * $cropWidth + $sourceLocalX
          $sourceX = $cropLeft + $sourceLocalX
          $sourceY = $cropTop + $sourceLocalY
          $sourceOffset = $sourceY * $sourceStride + ($sourceX * 4)
          $outputOffset = ($row * $FrameSize + $outputY) * $outputStride + (($column * $FrameSize + $outputX) * 4)
          $outputBytes[$outputOffset] = $sourceBytes[$sourceOffset]
          $outputBytes[$outputOffset + 1] = $sourceBytes[$sourceOffset + 1]
          $outputBytes[$outputOffset + 2] = $sourceBytes[$sourceOffset + 2]
          $outputBytes[$outputOffset + 3] = if ($background[$localIndex]) { [byte]0 } else { $sourceBytes[$sourceOffset + 3] }
        }
      }

      if ($foregroundCount -ge 2000) { $validFrames.Add($frameIndex) } else { $blankFrames.Add($frameIndex) }
    }
  }

  [Runtime.InteropServices.Marshal]::Copy($outputBytes, 0, $outputData.Scan0, $outputBytes.Length)
}
finally {
  $outputBitmap.UnlockBits($outputData)
  $sourceArgb.Dispose()
}

$parent = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$outputBitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
$outputBitmap.Dispose()

[pscustomobject]@{
  Source = $Source
  Output = $Output
  Width = $outputWidth
  Height = $outputHeight
  Columns = $Columns
  Rows = $Rows
  ValidFrameIndices = ($validFrames -join ',')
  BlankFrameIndices = ($blankFrames -join ',')
}
