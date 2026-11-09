param(
  [Parameter(Mandatory = $true)][string]$Installer
)
$ErrorActionPreference = 'Stop'
$logFile = Join-Path $env:TEMP 'deskpet-install.log'
if (Test-Path $logFile) { Remove-Item $logFile -Force }

function Write-Log($m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

try {
  $productCode = '{C48135F6-CBD0-4C47-A141-2E25FA28F296}'

  # 1. 停止进程
  Write-Log '停止桌宠/网关进程'
  Get-Process -Name desktop-pet-gateway,lingmeng-desktop-pet -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 2

  # 2. 卸载旧 MSI（若已不存在则忽略 1605）
  Write-Log "卸载旧 MSI $productCode"
  $uninstall = Start-Process -FilePath 'msiexec.exe' `
    -ArgumentList @('/X', $productCode, '/passive', '/norestart') -Wait -PassThru
  Write-Log ("MSI 卸载退出码: {0}" -f $uninstall.ExitCode)
  if ($uninstall.ExitCode -notin 0,1605,3010) { throw "MSI 卸载失败，退出码 $($uninstall.ExitCode)" }
  Start-Sleep -Seconds 2

  # 3. 安装新 NSIS（静默、每机器；/D 必须是最后一个参数且不带引号）
  if (-not (Test-Path -LiteralPath $Installer)) { throw "找不到安装包: $Installer" }
  Write-Log "安装新 NSIS: $Installer"
  $install = Start-Process -FilePath $Installer `
    -ArgumentList '/S','/D=C:\Program Files\灵梦桌宠' -Wait -PassThru
  Write-Log ("NSIS 安装退出码: {0}" -f $install.ExitCode)
  if ($install.ExitCode -ne 0) { throw "NSIS 安装失败，退出码 $($install.ExitCode)" }

  # 4. 校验
  $gateway = 'C:\Program Files\灵梦桌宠\gateway\desktop-pet-gateway.exe'
  $yunet = 'C:\Program Files\灵梦桌宠\gateway\models\face_detection_yunet_2023mar.onnx'
  $sface = 'C:\Program Files\灵梦桌宠\gateway\models\face_recognition_sface_2021dec.onnx'
  Write-Log ("gateway 存在: {0}" -f (Test-Path $gateway))
  Write-Log ("yunet 存在: {0}" -f (Test-Path $yunet))
  Write-Log ("sface 存在: {0}" -f (Test-Path $sface))
  if (-not ((Test-Path $gateway) -and (Test-Path $yunet) -and (Test-Path $sface))) {
    throw '安装后关键文件缺失'
  }
  Write-Log '全部完成'
  exit 0
}
catch {
  Write-Log ("[致命错误] {0}" -f $_.Exception.Message)
  exit 1
}

