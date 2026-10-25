param(
    [string]$PlayerDirectory,
    [string]$PythonExecutable,
    [switch]$PrepareOnly,
    [switch]$ForceBuild,
    [switch]$NoGlass,
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$setupArguments = @{ PrepareOnly=$true; Json=$true }
foreach ($name in @('PlayerDirectory','PythonExecutable','ForceBuild')) {
    if ($PSBoundParameters.ContainsKey($name)) { $setupArguments[$name] = $PSBoundParameters[$name] }
}
$setupJson = & (Join-Path $PSScriptRoot 'install.ps1') @setupArguments
$setup = $setupJson | ConvertFrom-Json
if ($PrepareOnly) {
    if ($Json) { $setup | ConvertTo-Json -Compress }
    else { Write-Output '本地安装已准备好；未启动播放器。' }
    return
}
if ($setup.restartRequired) {
    throw '新版本已构建。请先关闭本项目预览播放器，再重新双击预览皮肤.cmd；运行中的文件和设置未被覆盖。'
}
$previewDirectory = [string]$setup.runtimeDirectory
$previewExe = [string]$setup.playerExe

function Start-WindowEffects([int]$PreviewProcessId,[bool]$AlreadyRunning) {
    try {
        $existingMutex = [Threading.Mutex]::OpenExisting('Local\FluentGlass-' + $PreviewProcessId)
        $existingMutex.Dispose()
        $modeKnown = $false
        $activeNoGlass = $false
        try {
            $statusFile = Join-Path $previewDirectory 'window-effects.json'
            $effectStatus = Get-Content -LiteralPath $statusFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([int]$effectStatus.pid -eq $PreviewProcessId) {
                if ($effectStatus.mode -eq 'bounds only') {
                    $modeKnown = $true
                    $activeNoGlass = $true
                } elseif ($effectStatus.mode -in @('startup acrylic','opaque playback')) {
                    $modeKnown = $true
                }
            }
        } catch { }
        if (-not $modeKnown) {
            Write-Warning '现有窗口增强器的状态未知或记录已过期；本次保持现有模式不变。如需确认或切换模式，请关闭预览后重新启动。'
        } elseif ($activeNoGlass -ne [bool]$NoGlass) {
            Write-Warning '现有窗口增强器与本次请求的毛玻璃 / -NoGlass 模式不同；本次保持原模式。请先关闭预览，再重新启动以切换模式。'
        }
        return
    } catch [Threading.WaitHandleCannotBeOpenedException] { }
    $effectsScript = Join-Path $PSScriptRoot 'window_effects.py'
    $arguments = @('"' + $effectsScript + '"',[string]$PreviewProcessId)
    if ($NoGlass) { $arguments += '--no-glass' }
    $null = Start-Process -FilePath ([string]$setup.pythonExecutable) -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $previewDirectory 'glass-output.log') -RedirectStandardError (Join-Path $previewDirectory 'glass-errors.log') -PassThru
}

$existing = Get-Process -Name PotPlayerMini64 -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -eq $previewExe } catch { $false }
} | Select-Object -First 1
if ($existing) {
    $shell = New-Object -ComObject WScript.Shell
    $null = $shell.AppActivate($existing.Id)
    Write-Output "预览已在运行（PID $($existing.Id)）。"
    Start-WindowEffects $existing.Id $true
    return
}
$preview = Start-Process -FilePath $previewExe -ArgumentList '/new' -WorkingDirectory $previewDirectory -WindowStyle Normal -PassThru
Write-Output "已启动本地预览（PID $($preview.Id)）。"
Start-WindowEffects $preview.Id $false
