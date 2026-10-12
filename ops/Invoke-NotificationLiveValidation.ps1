# Existing native Windows TESTING infrastructure only. Preserve all submitted rows.
[CmdletBinding()]
param(
    [switch]$AlertOnly,
    [ValidateSet('success', 'failure')][string]$AlertStatus = 'failure'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Initialize-TaskAlert {
    # Reuse only the established alert function, without running profile startup code.
    $taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
    $taskTokens = $null
    $taskErrors = $null
    $taskAst = [System.Management.Automation.Language.Parser]::ParseFile($taskProfile, [ref]$taskTokens, [ref]$taskErrors)
    if ($taskErrors.Count -ne 0) { throw 'Existing OAF alert profile syntax is invalid.' }
    $taskDefinitions = @($taskAst.FindAll({
        param($taskNode)
        $taskNode -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $taskNode.Name -ceq 'Show-OAFPowerShellAlert'
    }, $false))
    if ($taskDefinitions.Count -ne 1) { throw 'Existing OAF alert function unavailable.' }
    . ([ScriptBlock]::Create($taskDefinitions[0].Extent.Text))
    Set-Item -Path Function:script:Show-OAFPowerShellAlert -Value (Get-Item Function:Show-OAFPowerShellAlert).ScriptBlock
}

if ($AlertOnly) {
    Initialize-TaskAlert
    Show-OAFPowerShellAlert -Status $AlertStatus -Title 'OAF LIVE NOTIFICATION VALIDATION' -Message $(
        if ($AlertStatus -eq 'success') { 'Live TESTING checks passed. The complete sanitized report is on the clipboard.' }
        else { 'Validation needs attention. The sanitized report is on the clipboard and in the terminal.' })
    exit
}

$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskOldEnvironment = $env:OAF_ENV
$taskExitCode = 2
$taskReportPath = $null
$taskLines = New-Object 'System.Collections.Generic.List[string]'
try {
    if ([IO.Path]::GetFullPath((Get-Location).Path) -ne $taskRoot) { throw 'Run from the OAF Website workspace.' }
    if ($taskOldEnvironment -and $taskOldEnvironment -ne 'testing') { throw 'Conflicting OAF_ENV; no override performed.' }
    foreach ($taskPath in @($taskRoot, (Join-Path $taskRoot 'config'), (Join-Path $taskRoot 'config\local'))) {
        if (((Get-Item -LiteralPath $taskPath).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Redirected workspace/configuration prohibited.'
        }
    }
    Initialize-TaskAlert
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    $taskBrowserPython = Join-Path (Split-Path -Parent $taskRoot) 'GraManna\.venv\Scripts\python.exe'
    $env:OAF_ENV = 'testing'
    $taskLines.Add('OAF WEBSITE - LIVE NOTIFICATION SUBSCRIPTION VALIDATION')
    & $taskPython -B (Join-Path $taskRoot 'ops\notification_live_check.py') --browser-python $taskBrowserPython 2>&1 | ForEach-Object {
        $taskLines.Add([string]$_)
        Write-Host ([string]$_)
        if ([string]$_ -like 'Complete sanitized report: *') {
            $taskReportPath = ([string]$_).Substring('Complete sanitized report: '.Length)
        }
    }
    $taskExitCode = $LASTEXITCODE
} catch {
    $taskLines.Add('BLOCKED: ' + $_.Exception.Message)
    Write-Host $taskLines[$taskLines.Count - 1]
} finally {
    $env:OAF_ENV = $taskOldEnvironment
    try {
        if ($taskReportPath) {
            $taskFullReport = Get-Content -LiteralPath $taskReportPath -Raw
        } else { $taskFullReport = $taskLines -join [Environment]::NewLine }
        Set-Clipboard -Value $taskFullReport
        if ((Get-Clipboard -Raw).TrimEnd() -cne $taskFullReport.TrimEnd()) { throw 'Clipboard verification failed.' }
        Write-Host 'Complete sanitized report copied to clipboard and verified.'
        $taskPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $taskAlert = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
        $taskArguments = @('-NoProfile', '-STA', '-ExecutionPolicy', 'RemoteSigned', '-File',
            ('"' + $PSCommandPath + '"'), '-AlertOnly', '-AlertStatus', $taskAlert)
        Start-Process -FilePath $taskPowerShell -ArgumentList $taskArguments -WindowStyle Hidden | Out-Null
        Write-Host 'Existing OAF visual alert launched.'
    } catch {
        $taskExitCode = 2
        Write-Host ('Report/clipboard/alert BLOCKED: ' + $_.Exception.Message)
    }
}
exit $taskExitCode
