# Windows PowerShell 5.1. Existing dependencies only; TESTING runtime only.
# Browser submissions are retained. No migrations, cleanup, Git writes, or resets.
[CmdletBinding()]
param(
    [switch]$AlertOnly,
    [ValidateSet('success', 'failure')][string]$AlertStatus = 'failure'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ($AlertOnly) {
    $taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
    . $taskProfile
    if ($AlertStatus -eq 'success') {
        Show-OAFPowerShellAlert -Status success -Title 'OAF STATE REQUEST LIVE VALIDATION' -Message 'Live TESTING validation passed. The complete report is on the clipboard.'
    } else {
        Show-OAFPowerShellAlert -Status failure -Title 'OAF STATE REQUEST VALIDATION NEEDS ATTENTION' -Message 'Validation is blocked. The complete report is on the clipboard; check the terminal.'
    }
    exit
}

$taskLines = New-Object 'System.Collections.Generic.List[string]'
$taskExitCode = 2
$taskOldEnvironment = $env:OAF_ENV
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskReportPath = $null

function Write-TaskReportLine([string]$Text) {
    $taskLines.Add($Text)
    Write-Host $Text
}

try {
    Write-TaskReportLine 'OAF WEBSITE - LIVE STATE REQUEST VALIDATION'
    Write-TaskReportLine ('Started: ' + [DateTime]::UtcNow.ToString('o'))
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'Windows PowerShell 5.1 or later is required.' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows execution is required.' }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -ne $taskRoot) { throw 'Run from the OAF Website repository root.' }
    if ((Split-Path -Leaf $taskRoot) -ne 'OAF Website') { throw 'Unexpected repository directory.' }
    foreach ($taskPath in @($taskRoot, (Join-Path $taskRoot 'config'), (Join-Path $taskRoot 'config\local'))) {
        $taskItem = Get-Item -LiteralPath $taskPath
        if (($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Redirected workspace/configuration is prohibited.' }
    }
    if ($taskOldEnvironment -and $taskOldEnvironment -ne 'testing') { throw 'Existing OAF_ENV conflicts with TESTING; no override performed.' }
    $taskWebsitePython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    $taskBrowserPython = Join-Path (Split-Path -Parent $taskRoot) 'GraManna\.venv\Scripts\python.exe'
    $taskHarness = Join-Path $taskRoot 'ops\state_request_live_check.py'
    foreach ($taskFile in @($taskWebsitePython, $taskBrowserPython, $taskHarness, (Join-Path $taskRoot 'config\local\database.toml'))) {
        if (-not (Test-Path -LiteralPath $taskFile -PathType Leaf)) { throw 'An existing interpreter, harness, or local configuration is missing.' }
    }
    $taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
    if (-not (Test-Path -LiteralPath $taskProfile -PathType Leaf)) { throw 'Existing OAF visual-alert profile is unavailable.' }
    $env:OAF_ENV = 'testing'
    Write-TaskReportLine 'Scope: oaf_website_test / oaf_website_test_app; existing WinVault credential; SCRAM authentication.'
    Write-TaskReportLine 'Real Chromium A-J tests. Counts use the initial baseline. Four browser rows are retained on a full pass.'
    & $taskWebsitePython -B $taskHarness --browser-python $taskBrowserPython 2>&1 | ForEach-Object {
        Write-TaskReportLine ([string]$_)
    }
    $taskExitCode = $LASTEXITCODE
    if ($taskExitCode -ne 0) { Write-TaskReportLine 'Validation BLOCKED; inspect the printed evidence. Existing records have not been cleaned up.' }
} catch {
    Write-TaskReportLine ('BLOCKED: ' + $_.Exception.Message)
    $taskExitCode = 2
} finally {
    $env:OAF_ENV = $taskOldEnvironment
    Write-TaskReportLine ('Native harness exit code: ' + $taskExitCode)
    Write-TaskReportLine ('Finished: ' + [DateTime]::UtcNow.ToString('o'))
    try {
        $taskCache = Join-Path $taskRoot '.pytest_cache'
        if (-not (Test-Path -LiteralPath $taskCache -PathType Container)) { [void](New-Item -ItemType Directory -Path $taskCache) }
        $taskReportPath = Join-Path $taskCache ('state-request-native-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [Guid]::NewGuid().ToString('N') + '.txt')
        Write-TaskReportLine ('Native transcript: ' + $taskReportPath)
        $taskTranscript = $taskLines -join [Environment]::NewLine
        [IO.File]::WriteAllText($taskReportPath, $taskTranscript, (New-Object Text.UTF8Encoding($false)))
        Set-Clipboard -Value $taskTranscript
        if ((Get-Clipboard -Raw).TrimEnd() -ne $taskTranscript.TrimEnd()) { throw 'Clipboard verification failed.' }
        Write-Host 'Complete report copied to clipboard and saved locally.'
    } catch {
        $taskExitCode = 2
        Write-Host ('Report/clipboard BLOCKED: ' + $_.Exception.Message)
    }
    try {
        $taskAlert = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
        $taskPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        # Display the existing alert without holding browser/server cleanup open.
        $taskArguments = @('-NoProfile', '-STA', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + $PSCommandPath + '"'), '-AlertOnly', '-AlertStatus', $taskAlert)
        Start-Process -FilePath $taskPowerShell -ArgumentList $taskArguments -WindowStyle Hidden | Out-Null
    } catch {
        Write-Host 'Existing visual alert could not be launched; see the printed report.'
        $taskExitCode = 2
    }
}

exit $taskExitCode
