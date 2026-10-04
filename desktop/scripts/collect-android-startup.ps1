[CmdletBinding()]
param(
    [string]$AdbPath,
    [string]$DeviceId,
    [ValidateRange(3, 45)]
    [int]$CaptureSeconds = 12,
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$taskPackage = 'io.concurse.desktop'

if (-not $AdbPath) {
    $taskCandidates = @(
        (Join-Path $env:TEMP 'concurse-android-diagnostics\platform-tools\adb.exe'),
        (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe')
    )
    if ($env:ANDROID_HOME) {
        $taskCandidates += Join-Path $env:ANDROID_HOME 'platform-tools\adb.exe'
    }
    $taskOnPath = Get-Command adb.exe -ErrorAction SilentlyContinue
    if ($taskOnPath) { $taskCandidates += $taskOnPath.Source }
    $AdbPath = $taskCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $AdbPath -or -not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw 'ADB nao encontrado. Informe -AdbPath com o caminho de platform-tools\adb.exe.'
}
$AdbPath = (Resolve-Path -LiteralPath $AdbPath).Path

$taskInventory = & $AdbPath devices -l 2>&1
if ($LASTEXITCODE -ne 0) { throw "Falha ao consultar o ADB: $taskInventory" }
$taskDevices = @(
    foreach ($taskLine in $taskInventory) {
        if ("$taskLine" -match '^(\S+)\s+(device|unauthorized|offline)(?:\s|$)') {
            [pscustomobject]@{ Id = $Matches[1]; State = $Matches[2] }
        }
    }
)
if ($DeviceId) {
    $taskSelected = @($taskDevices | Where-Object { $_.Id -eq $DeviceId })
} else {
    $taskSelected = $taskDevices
}
if ($taskSelected.Count -eq 0) {
    throw 'Nenhum celular encontrado. Conecte o USB, ative Depuracao USB e aceite a autorizacao no celular.'
}
if ($taskSelected.Count -gt 1) {
    throw 'Ha mais de um dispositivo conectado. Informe -DeviceId para selecionar o celular.'
}
if ($taskSelected[0].State -ne 'device') {
    throw "Celular $($taskSelected[0].State). Desbloqueie-o e aceite a autorizacao de Depuracao USB."
}
$taskSerial = $taskSelected[0].Id
# Start-Process joins its argument array on Windows; only accept simple ADB IDs.
if ($taskSerial -notmatch '^[A-Za-z0-9_.:\-]+$') {
    throw 'Identificador ADB inesperado. Use uma conexao USB com identificador simples.'
}

function Invoke-TaskAdb {
    param([string[]]$AdbArguments)
    $taskReply = & $AdbPath -s $taskSerial @AdbArguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ADB falhou ($($AdbArguments -join ' ')): $($taskReply -join [Environment]::NewLine)"
    }
    return (($taskReply | ForEach-Object { "$_" }) -join [Environment]::NewLine).Trim()
}

# Check installation before creating an output folder or restarting the app.
$taskPackagePaths = Invoke-TaskAdb -AdbArguments @('shell', 'pm', 'path', $taskPackage)
$taskBaseApk = @($taskPackagePaths -split '\r?\n' | Where-Object { $_ -match '^package:.+/base\.apk$' })
if ($taskBaseApk.Count -ne 1) {
    throw 'O aplicativo io.concurse.desktop nao esta instalado, ou seu APK base nao foi localizado.'
}
$taskBaseApkPath = $taskBaseApk[0].Substring('package:'.Length)
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $taskRepo ('desktop\src-tauri\gen\android\app\build\outputs\diagnostics\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$taskMetadata = [ordered]@{
    capturedAt = (Get-Date).ToString('o')
    package = $taskPackage
    properties = [ordered]@{}
}
foreach ($taskProperty in @(
    'ro.product.manufacturer', 'ro.product.model', 'ro.product.device',
    'ro.build.version.release', 'ro.build.version.sdk', 'ro.build.version.incremental',
    'ro.product.cpu.abilist', 'ro.product.cpu.abilist64', 'ro.product.cpu.abilist32'
)) {
    $taskMetadata.properties[$taskProperty] = Invoke-TaskAdb -AdbArguments @('shell', 'getprop', $taskProperty)
}
$taskMetadata.pageSize = Invoke-TaskAdb -AdbArguments @('shell', 'getconf', 'PAGE_SIZE')
$taskPackageInfo = Invoke-TaskAdb -AdbArguments @('shell', 'dumpsys', 'package', $taskPackage)
$taskMetadata.packageInfo = @($taskPackageInfo -split '\r?\n' | Where-Object {
    $_ -match '^\s*(versionCode=|versionName=|minSdk=|targetSdk=|primaryCpuAbi=|secondaryCpuAbi=|codePath=|nativeLibraryDir=)'
} | ForEach-Object { $_.Trim() })
Invoke-TaskAdb -AdbArguments @('shell', 'dumpsys', 'webviewupdate') |
    Set-Content -LiteralPath (Join-Path $OutputDirectory 'webview-provider.txt') -Encoding UTF8

# Pull only the installed public application binary, never app data or credentials.
$taskInstalledApk = Join-Path $OutputDirectory 'installed-base.apk'
Invoke-TaskAdb -AdbArguments @('pull', $taskBaseApkPath, $taskInstalledApk) | Out-Null
$taskMetadata.installedApkSha256 = (Get-FileHash -LiteralPath $taskInstalledApk -Algorithm SHA256).Hash.ToLowerInvariant()
$taskPublishedApk = Join-Path $taskRepo 'downloads\concurse-mobile-aarch64-release-v0.1.2-code3-16k.apk'
if (Test-Path -LiteralPath $taskPublishedApk) {
    $taskMetadata.publishedApkSha256 = (Get-FileHash -LiteralPath $taskPublishedApk -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskMetadata.matchesPublishedApk = $taskMetadata.installedApkSha256 -eq $taskMetadata.publishedApkSha256
}
$taskMetadata | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $OutputDirectory 'device-and-package.json') -Encoding UTF8

# No logcat clearing, data clearing, installation, or device settings changes.
Invoke-TaskAdb -AdbArguments @('shell', 'am', 'force-stop', $taskPackage) | Out-Null
$taskLogPath = Join-Path $OutputDirectory 'startup-logcat.txt'
$taskLogErrors = Join-Path $OutputDirectory 'logcat-errors.txt'
$taskLogArguments = @(
    '-s', $taskSerial, 'logcat', '-b', 'main', '-b', 'system', '-b', 'crash', '-v', 'threadtime', '-T', '1'
)
$taskLogProcess = Start-Process -FilePath $AdbPath -ArgumentList $taskLogArguments -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $taskLogPath -RedirectStandardError $taskLogErrors
try {
    Start-Sleep -Milliseconds 500
    if ($taskLogProcess.HasExited) { throw 'A coleta logcat encerrou antes da abertura do aplicativo. Consulte logcat-errors.txt.' }
    Invoke-TaskAdb -AdbArguments @('shell', 'am', 'start', '-W', '-n', "$taskPackage/.MainActivity") |
        Set-Content -LiteralPath (Join-Path $OutputDirectory 'launch-result.txt') -Encoding UTF8
    Write-Host "Coletando $CaptureSeconds segundos da inicializacao. Se aparecer um aviso, confirme-o no celular."
    Start-Sleep -Seconds $CaptureSeconds
} finally {
    if (-not $taskLogProcess.HasExited) {
        Stop-Process -Id $taskLogProcess.Id -Force -ErrorAction SilentlyContinue
        $taskLogProcess.WaitForExit()
    }
}
$taskExitInfo = & $AdbPath -s $taskSerial shell dumpsys activity exit-info $taskPackage 2>&1
if ($LASTEXITCODE -eq 0) {
    $taskExitInfo | Set-Content -LiteralPath (Join-Path $OutputDirectory 'app-exit-info.txt') -Encoding UTF8
}
Write-Host "Diagnostico salvo em: $OutputDirectory"
Write-Host 'Leia startup-logcat.txt para encontrar a primeira excecao antes do abort.'
