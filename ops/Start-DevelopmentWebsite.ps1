# Windows PowerShell 5.1. Foreground DEVELOPMENT server; existing dependencies only.
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoAlert,
    [switch]$AlertOnly,
    [ValidateSet('success', 'failure')][string]$AlertStatus = 'success',
    [switch]$EnableIntegrations
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'

if ($AlertOnly) {
    . $taskProfile
    $taskMessage = if ($AlertStatus -eq 'success') {
        'DEVELOPMENT website is ready at http://127.0.0.1:5055/gramanna.html. Startup details are on the clipboard. Stop with Ctrl+C in the server terminal.'
    } else {
        'DEVELOPMENT startup is blocked. Details are on the clipboard; check the terminal.'
    }
    Show-OAFPowerShellAlert -Status $AlertStatus -Title 'OAF DEVELOPMENT WEBSITE' -Message $taskMessage
    exit
}

$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskOldEnvironment = $env:OAF_ENV
$taskAddress = 'http://127.0.0.1:5055/gramanna.html'
$taskLines = New-Object 'System.Collections.Generic.List[string]'
$taskReady = $false
$taskExitCode = 2

function Publish-TaskReport([string]$Status) {
    $taskReport = $taskLines -join [Environment]::NewLine
    Set-Clipboard -Value $taskReport
    if ((Get-Clipboard -Raw).TrimEnd() -ne $taskReport.TrimEnd()) { throw 'Clipboard verification failed.' }
    if (-not $NoAlert) {
        $taskPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $taskArguments = @('-NoProfile', '-STA', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + $PSCommandPath + '"'), '-AlertOnly', '-AlertStatus', $Status)
        Start-Process -FilePath $taskPowerShell -ArgumentList $taskArguments -WindowStyle Hidden | Out-Null
    }
}

try {
    if ($PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'Windows PowerShell 5.1 or later is required.' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows execution is required.' }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -ne $taskRoot) { throw 'Run from the OAF Website repository root.' }
    if ($taskOldEnvironment -and $taskOldEnvironment -ne 'development') { throw 'Existing OAF_ENV conflicts with DEVELOPMENT; no override performed.' }
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    foreach ($taskFile in @($taskPython, (Join-Path $taskRoot 'config\local\database.toml'))) {
        if (-not (Test-Path -LiteralPath $taskFile -PathType Leaf)) { throw 'Existing website interpreter or local database configuration is missing.' }
    }
    if (-not $NoAlert -and -not (Test-Path -LiteralPath $taskProfile -PathType Leaf)) { throw 'Existing OAF visual-alert profile is unavailable.' }
    $taskChrome = $null
    if (-not $NoBrowser) {
        foreach ($taskCandidate in @((Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
                (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
                (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'))) {
            if (Test-Path -LiteralPath $taskCandidate -PathType Leaf) { $taskChrome = $taskCandidate; break }
        }
        if (-not $taskChrome) { throw 'Google Chrome is unavailable in its standard installation locations.' }
    }
    $env:OAF_ENV = 'development'
    $taskPythonArguments = @('-B', '-m', 'oaf_website.local_development')
    if ($EnableIntegrations) { $taskPythonArguments += '--integrations' }
    & $taskPython @taskPythonArguments 2>&1 | ForEach-Object {
        $taskLine = [string]$_
        $taskLines.Add($taskLine)
        Write-Host $taskLine
        if ($taskLine -eq ('DEVELOPMENT READY: ' + $taskAddress)) {
            $taskReady = $true
            $taskExitCode = 0
            Publish-TaskReport 'success'
            if (-not $NoBrowser) { Start-Process -FilePath $taskChrome -ArgumentList $taskAddress | Out-Null }
        }
    }
    $taskNativeExit = $LASTEXITCODE
    if (-not $taskReady -or $taskNativeExit -notin @(0, 130, -1073741510)) { throw 'DEVELOPMENT server failed; inspect the startup details above.' }
} catch {
    $taskExitCode = 2
    $taskLine = 'BLOCKED: ' + $_.Exception.Message
    $taskLines.Add($taskLine)
    Write-Host $taskLine
    try { Publish-TaskReport 'failure' } catch { Write-Host 'Startup report/visual alert could not be delivered; see the terminal.' }
} finally {
    $env:OAF_ENV = $taskOldEnvironment
}

exit $taskExitCode
