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
$taskFirstFailure = $null
$taskNativeExit = $null
$taskPredicate = 'configuration'
$taskRunId = [Guid]::NewGuid().ToString('N')
$taskLog = $null

function Write-TaskLine([string]$Line) {
    $taskLines.Add($Line)
    Write-Host $Line
    if ($null -ne $taskLog) {
        try {
            $taskLog.WriteLine($Line)
            $taskLog.Flush()
            $taskLog.BaseStream.Flush($true)
        } catch {
            $script:taskPredicate = 'terminal_publication'
            Write-Host 'BLOCKED: terminal_publication; sanitized terminal evidence remains available.'
            throw 'terminal_publication'
        }
    }
}

function Save-TaskFailure($Record) {
    if ($null -eq $script:taskFirstFailure) { $script:taskFirstFailure = $Record }
}

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
    $taskPredicate = 'terminal_publication'
    $taskLogDirectory = Join-Path $taskRoot 'instance'
    if (-not (Test-Path -LiteralPath $taskLogDirectory)) { [IO.Directory]::CreateDirectory($taskLogDirectory) | Out-Null }
    if ((Get-Item -LiteralPath $taskLogDirectory).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'terminal_publication' }
    $taskLogPath = Join-Path $taskLogDirectory ('development-launcher-' + $taskRunId + '.log')
    $taskLogFile = [IO.File]::Open($taskLogPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $taskLog = New-Object IO.StreamWriter($taskLogFile, (New-Object Text.UTF8Encoding($false)))
    Write-TaskLine ('{0} STARTED configuration evidence_ref={1}' -f [DateTime]::UtcNow.ToString('o'), $taskRunId)
    $taskPredicate = 'configuration'
    $taskPredicate = 'powershell_version'
    if ($PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'Windows PowerShell 5.1 or later is required.' }
    $taskPredicate = 'windows_required'
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows execution is required.' }
    $taskPredicate = 'workspace_required'
    if ([IO.Path]::GetFullPath((Get-Location).Path) -ne $taskRoot) { throw 'Run from the OAF Website repository root.' }
    $taskPredicate = 'environment_profile_match'
    if ($taskOldEnvironment -and $taskOldEnvironment -ne 'development') { throw 'Existing OAF_ENV conflicts with DEVELOPMENT; no override performed.' }
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    $taskPredicate = 'runtime_files_present'
    foreach ($taskFile in @($taskPython, (Join-Path $taskRoot 'config\local\database.toml'))) {
        if (-not (Test-Path -LiteralPath $taskFile -PathType Leaf)) { throw 'Existing website interpreter or local database configuration is missing.' }
    }
    $taskPredicate = 'visual_alert_available'
    if (-not $NoAlert -and -not (Test-Path -LiteralPath $taskProfile -PathType Leaf)) { throw 'Existing OAF visual-alert profile is unavailable.' }
    $taskPredicate = 'browser_available'
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
    $taskPredicate = 'child_execution'
    # Windows PowerShell 5.1 promotes native stderr to ErrorRecord. Preserve the
    # sanitized child record and native exit before restoring fail-closed reporting.
    $taskNativePreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
    & $taskPython @taskPythonArguments 2>&1 | ForEach-Object {
        $taskLine = [string]$_
        if ($taskLine.StartsWith('Notification operation failed: ')) {
            try {
                $taskChild = $taskLine.Substring('Notification operation failed: '.Length) | ConvertFrom-Json
                # Child is the pinned local Python producer; consume only its bounded record.
                if ($taskChild.first_failure.evidence_ref -cmatch '^[0-9a-f]{32}$' -and
                    $taskChild.first_failure.predicate -cmatch '^[a-z][a-z0-9_]{0,95}$') {
                    Save-TaskFailure $taskChild.first_failure
                } else { throw 'child_evidence_invalid' }
            } catch { $taskPredicate = 'child_evidence_invalid'; throw 'child_evidence_invalid' }
        }
        Write-TaskLine $taskLine
        if ($taskLine -eq ('DEVELOPMENT READY: ' + $taskAddress)) {
            $taskReady = $true
            $taskExitCode = 0
            Publish-TaskReport 'success'
            if (-not $NoBrowser) { Start-Process -FilePath $taskChrome -ArgumentList $taskAddress | Out-Null }
        }
    }
    $taskNativeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $taskNativePreference }
    Write-TaskLine ('{0} child_exit={1}' -f [DateTime]::UtcNow.ToString('o'), $taskNativeExit)
    if (-not $taskReady -or $taskNativeExit -notin @(0, 130, -1073741510)) { throw 'DEVELOPMENT server failed; inspect the startup details above.' }
} catch {
    $taskExitCode = 2
    $taskError = $_.Exception.GetBaseException()
    Save-TaskFailure ([ordered]@{
        timestamp_utc=[DateTime]::UtcNow.ToString('o'); stage='startup'; operation='configuration';
        predicate=$taskPredicate; expected='required_operation_acknowledged'; observed='unavailable_or_rejected';
        exception_class=$taskError.GetType().Name; sqlstate=$null; hresult=('0x{0:X8}' -f $taskError.HResult);
        exit_code=$taskNativeExit; side_effects=$(if ($taskReady) {'UNKNOWN'} else {'NOT_STARTED'});
        dependent_not_run=$(if ($taskReady) {@()} else {@('application_initialization')}); evidence_ref=$taskRunId
    })
    $taskLine = 'Notification operation failed: ' + ([ordered]@{operation='configuration';
        first_failure=$taskFirstFailure; native_exit=$taskNativeExit} | ConvertTo-Json -Depth 6 -Compress)
    try { Write-TaskLine $taskLine } catch { Write-Host $taskLine }
    try { Publish-TaskReport 'failure' } catch { Write-Host 'Startup report/visual alert could not be delivered; see the terminal.' }
} finally {
    $env:OAF_ENV = $taskOldEnvironment
    if ($null -ne $taskLog) {
        try { $taskLog.Flush(); $taskLog.BaseStream.Flush($true); $taskLog.Dispose() }
        catch { Write-Host 'BLOCKED: reporting cleanup unavailable; originating result retained.'; $taskExitCode = 2 }
    }
}

exit $taskExitCode
