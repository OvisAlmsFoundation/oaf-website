# Standalone offline harness, Windows PowerShell 5.1; no Pester or extra packages.
# Loads function definitions through the AST, NEVER the operational entry point.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$helper = Join-Path $repository 'ops\Set-DevelopmentIntegrationCredentials.ps1'
$python = Join-Path $repository '.venv\Scripts\python.exe'
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($helper, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Helper syntax failed offline validation.' }
$definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false))
if ($definitions.Count -ne 4) { throw 'Unexpected helper function inventory.' }
foreach ($definition in $definitions) {
    if ($definition.Name -eq 'Initialize-OafDevelopmentCredentialApi') {
        $source = @($definition.FindAll({ param($node)
            $node -is [Management.Automation.Language.StringConstantExpressionAst] -and $node.Value.Contains('namespace OafDevelopmentCredentials')
        }, $true))[0].Value
        # Compile the actual native struct/codec with all credential entry points
        # replaced by hard denials BEFORE compilation. No advapi32 imports survive.
        $source = [regex]::Replace($source, '\[DllImport\([^\r\n]+\)\]\s*private static extern bool ReadCredential\([^;]+;',
            'private static bool ReadCredential(string target, UInt32 type, UInt32 flags, out IntPtr result) { throw new InvalidOperationException("Offline native access denied."); }')
        $source = [regex]::Replace($source, '\[DllImport\([^\r\n]+\)\]\s*private static extern bool WriteCredential\([^;]+;',
            'private static bool WriteCredential(ref Credential value, UInt32 flags) { throw new InvalidOperationException("Offline native access denied."); }')
        $source = [regex]::Replace($source, '\[DllImport\([^\r\n]+\)\]\s*private static extern void FreeCredential\([^;]+;',
            'private static void FreeCredential(IntPtr value) { throw new InvalidOperationException("Offline native access denied."); }')
        # An accidental use of the operational generator must also fail offline.
        $source = $source.Replace('RandomNumberGenerator.Create()', 'OfflineGeneratorDenied()')
        $source = $source.Replace('public static string NewSecret() {',
            'private static RandomNumberGenerator OfflineGeneratorDenied() { throw new InvalidOperationException("Offline generation denied."); } public static string NewSecret() {')
        if ($source.Contains('DllImport') -or $source.Contains('RandomNumberGenerator.Create()')) {
            throw 'Native/RNG isolation transformation failed.'
        }
        Add-Type -TypeDefinition $source | Out-Null
    } else { . ([scriptblock]::Create($definition.Extent.Text)) }
}

$count = 0
$syntheticSubmission = '1' * 64
$syntheticReporting = '2' * 64
$privateMarker = 'SYNTHETIC-PRIVATE-DO-NOT-PRINT'
$originalEnvironment = @{}
foreach ($entry in Get-ChildItem Env:) {
    if ($entry.Name -like 'OAF_*') { $originalEnvironment[$entry.Name] = $entry.Value }
}
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('oaf-handoff-offline-' + [Guid]::NewGuid().ToString('N'))
$rootPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
if (-not [IO.Path]::GetFullPath($testRoot).StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Offline temporary path escaped its expected directory.'
}

function Assert-Offline([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw ('Offline assertion failed: ' + $Message) }
}

function New-SyntheticRecord([string]$Target, [string]$Account, [string]$Value) {
    return [pscustomobject]@{ TargetName = $Target; UserName = $Account; Type = 1; Persist = 2
        Blob = [OafDevelopmentCredentials.Native]::Encode($Value) }
}

function New-OfflineCase {
    foreach ($entry in @(Get-ChildItem Env:)) {
        if ($entry.Name -like 'OAF_*') { [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process') }
    }
    $caseRoot = Join-Path $testRoot ([Guid]::NewGuid().ToString('N'))
    $local = Join-Path $caseRoot 'config\local'
    [IO.Directory]::CreateDirectory($local) | Out-Null
    $case = @{ Root = $caseRoot; Path = (Join-Path $local 'integrations.toml'); Records = @{}
        Reads = (New-Object 'System.Collections.Generic.List[string]'); Writes = 0; Generations = 0
        FailWrite = 0; ReadbackFailure = $false; ProviderFailure = $false; Race = $false }
    $case.Store = @{
        Read = { param($target)
            $case.Reads.Add($target)
            if ($case.ProviderFailure) { throw $privateMarker }
            if ($case.ReadbackFailure -and $case.Writes -eq 2) { throw $privateMarker }
            return $case.Records[$target]
        }.GetNewClosure()
        Create = { param($target, $account, $secret)
            $case.Writes++
            if ($case.Race) { $case.Records[$target] = New-SyntheticRecord $target 'other-owner' $syntheticReporting }
            if ($case.Records.ContainsKey($target)) { throw $privateMarker }
            if ($case.FailWrite -eq $case.Writes) { throw $privateMarker }
            $case.Records[$target] = New-SyntheticRecord $target $account $secret
        }.GetNewClosure()
    }
    $case.Factory = {
        $case.Generations++
        if ($case.Generations -eq 1) { return $syntheticSubmission }
        return $syntheticReporting
    }.GetNewClosure()
    return $case
}

function Set-OfflineMetadata($Case, [string]$Text = "[development]`nclient_id = 'owner_client'`n") {
    [IO.File]::WriteAllText($Case.Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

function Set-OfflinePair($Case) {
    Set-OfflineMetadata $Case
    $Case.Records[$submissionTarget] = New-SyntheticRecord $submissionTarget 'owner_client' $syntheticSubmission
    $Case.Records[$reportingTarget] = New-SyntheticRecord $reportingTarget 'owner_client' $syntheticReporting
}

function Invoke-OfflineCase($Case, [string]$Operation = 'Provision', [switch]$Fails, [switch]$FailStatus) {
    $beforeEnvironment = @{}
    foreach ($entry in Get-ChildItem Env:) {
        if ($entry.Name -like 'OAF_*') { $beforeEnvironment[$entry.Name] = $entry.Value }
    }
    # Fail after activation assignments to exercise the actual rollback path.
    # This local override never affects the helper source or the final test status.
    if ($FailStatus) { function Write-Output { throw $privateMarker } }
    $output = @()
    $failed = $false
    try {
        $output = @(Invoke-OafDevelopmentCredentialHandoff -Operation $Operation -Root $Case.Root -Python $python `
            -Store $Case.Store -SecretFactory $Case.Factory *>&1)
    } catch {
        $failed = $true
        $output += ($_ | Out-String)
        $output += ($_ | Format-List * -Force | Out-String)
    }
    $text = $output | Out-String
    Assert-Offline ($failed -eq $Fails.IsPresent) 'expected success/failure differs'
    foreach ($value in @($syntheticSubmission, $syntheticReporting, $privateMarker)) {
        Assert-Offline (-not $text.Contains($value)) 'credential/provider value escaped into diagnostics'
    }
    if ($Fails) {
        Assert-Offline (-not $text.Contains('provisioned and verified') -and -not $text.Contains('reporting activated') -and
            -not $text.Contains('shared services activated')) 'misleading success on failure'
        $afterEnvironment = @{}
        foreach ($entry in Get-ChildItem Env:) {
            if ($entry.Name -like 'OAF_*') { $afterEnvironment[$entry.Name] = $entry.Value }
        }
        Assert-Offline ($afterEnvironment.Count -eq $beforeEnvironment.Count) 'failure added or removed process settings'
        foreach ($name in $beforeEnvironment.Keys) {
            Assert-Offline ($afterEnvironment.ContainsKey($name) -and $afterEnvironment[$name] -ceq $beforeEnvironment[$name]) 'failure changed prior process settings'
        }
    } else { Assert-Offline ($output.Count -eq 1) 'unexpected output beyond fixed status' }
    if ($Operation -ceq 'ActivateSharedServices') {
        Assert-Offline ($Case.Writes -eq 0 -and $Case.Generations -eq 0) 'shared activation wrote or generated credentials'
    }
    $script:count++
}

$submissionTarget = 'OAF Website/development/Integrations/Submission'
$reportingTarget = 'OAF Website/development/Integrations/Reporting'
try {
    $case = New-OfflineCase
    Invoke-OfflineCase $case
    Assert-Offline ($case.Writes -eq 2 -and $case.Generations -eq 2) 'fresh pair generation/writes'
    Assert-Offline ((Read-OafDevelopmentClientId $case.Path $python) -ceq 'gramanna') 'stable default client ID'
    foreach ($target in @($submissionTarget, $reportingTarget)) {
        $value = Get-OafDevelopmentSecret $case.Records[$target] $target 'gramanna'
        Assert-Offline ($case.Records[$target].Blob.Length -eq 128 -and $value.Length -eq 64) 'canonical UTF-16LE round trip'
    }
    $before = [IO.File]::ReadAllBytes($case.Path)
    Invoke-OfflineCase $case
    Assert-Offline ($case.Writes -eq 2 -and $case.Generations -eq 2) 'idempotent provision replaced credentials'
    Assert-Offline ([Convert]::ToBase64String($before) -ceq [Convert]::ToBase64String([IO.File]::ReadAllBytes($case.Path))) 'metadata rewritten'

    $case = New-OfflineCase
    Set-OfflineMetadata $case "# owner comment`n[development]`nclient_id = 'custom_owner' # retain`n"
    $before = [IO.File]::ReadAllText($case.Path)
    Invoke-OfflineCase $case
    Assert-Offline ($case.Records[$reportingTarget].UserName -ceq 'custom_owner') 'owner account not preserved'
    Assert-Offline ([IO.File]::ReadAllText($case.Path) -ceq $before) 'owner configuration changed'

    foreach ($text in @('', "[testing]`nclient_id='owner_client'", "[production]`nclient_id='owner_client'",
        "[development]`nclient_id='INVALID'", "[development]`nclient_id='owner_client'`nsecret='$privateMarker'",
        "[development]`nclient_id='$privateMarker", "[development]`nclient_id='owner_client'`nclient_id='other'")) {
        $case = New-OfflineCase
        Set-OfflineMetadata $case $text
        Invoke-OfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0 -and $case.Generations -eq 0) 'invalid metadata reached credentials'
    }

    foreach ($missing in @('metadata', 'submission', 'reporting')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        if ($missing -eq 'metadata') { Remove-Item -LiteralPath $case.Path }
        else { $case.Records.Remove($(if ($missing -eq 'submission') { $submissionTarget } else { $reportingTarget })) }
        Invoke-OfflineCase $case -Fails
        Assert-Offline ($case.Writes -eq 0 -and $case.Generations -eq 0) 'incomplete setup modified'
    }

    foreach ($field in @('UserName', 'TargetName', 'Type', 'Persist', 'Blob')) {
        foreach ($target in @($submissionTarget, $reportingTarget)) {
            $case = New-OfflineCase
            Set-OfflinePair $case
            $record = $case.Records[$target]
            switch ($field) {
                UserName { $record.UserName = 'wrong_owner' }
                TargetName { $record.TargetName = $target.Replace('development', 'testing') }
                Type { $record.Type = 2 }
                Persist { $record.Persist = 3 }
                Blob { $record.Blob = [Text.Encoding]::UTF8.GetBytes($syntheticReporting) }
            }
            Invoke-OfflineCase $case -Fails
            Assert-Offline ($case.Writes -eq 0 -and $case.Generations -eq 0) 'conflicting record modified'
        }
    }
    $case = New-OfflineCase
    Set-OfflinePair $case
    $case.Records[$reportingTarget].Blob = [OafDevelopmentCredentials.Native]::Encode($syntheticSubmission)
    Invoke-OfflineCase $case -Fails

    foreach ($failure in @('first', 'second', 'readback', 'provider', 'race')) {
        $case = New-OfflineCase
        switch ($failure) {
            first { $case.FailWrite = 1 }
            second { $case.FailWrite = 2 }
            readback { $case.ReadbackFailure = $true }
            provider { $case.ProviderFailure = $true }
            race { $case.Race = $true }
        }
        Invoke-OfflineCase $case -Fails
        if ($failure -eq 'second') {
            Assert-Offline ($case.Records.Count -eq 1) 'partial record not retained for reconciliation'
            $case.FailWrite = 0
            Invoke-OfflineCase $case -Fails
            Assert-Offline ($case.Writes -eq 2 -and $case.Generations -eq 2) 'retry repaired/replaced partial setup'
        }
    }
    $case = New-OfflineCase
    $case.Factory = { '1' * 64 }
    Invoke-OfflineCase $case -Fails
    Assert-Offline ($case.Writes -eq 0) 'identical generated pair written'

    foreach ($initialEnabled in @($null, 'true', '1')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        $case.Records.Remove($submissionTarget) # Reporting activation must not inspect submission.
        [Environment]::SetEnvironmentVariable('OAF_INTEGRATION_ENABLED', $initialEnabled, 'Process')
        Invoke-OfflineCase $case 'ActivateReporting'
        Assert-Offline ($case.Reads.Count -eq 1 -and $case.Reads[0] -ceq $reportingTarget) 'activation read another permission'
        Assert-Offline ($case.Writes -eq 0 -and $case.Generations -eq 0) 'activation generated or wrote credentials'
        Assert-Offline ($env:OAF_INTEGRATION_ENABLED -ceq '1' -and $env:OAF_INTEGRATION_ENVIRONMENT -ceq 'development' -and
            $env:OAF_DEVELOPMENT_ORIGIN -ceq 'http://127.0.0.1:5055' -and $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ceq $syntheticReporting) 'process handoff differs'
        Invoke-OfflineCase $case 'ActivateReporting' # Matching reactivation is safe.
        Assert-Offline ($env:OAF_INTEGRATION_ENABLED -ceq '1' -and $case.Reads.Count -eq 2 -and
            $case.Reads[1] -ceq $reportingTarget -and $case.Writes -eq 0 -and $case.Generations -eq 0) 'reactivation changed the flag or credential access'
    }

    foreach ($activation in @(
        @{ Operation = 'ActivateReporting'; Target = $reportingTarget },
        @{ Operation = 'ActivateSharedServices'; Target = $submissionTarget },
        @{ Operation = 'ActivateSharedServices'; Target = $reportingTarget }
    )) {
        foreach ($invalid in @('missing', 'metadata', 'account', 'target', 'type', 'persistence', 'utf8', 'uppercase', 'bom', 'nul', 'surrogate', 'short', 'provider')) {
            $case = New-OfflineCase
            Set-OfflinePair $case
            $target = $activation.Target
            switch ($invalid) {
                missing { $case.Records.Remove($target) }
                metadata { Remove-Item -LiteralPath $case.Path }
                account { $case.Records[$target].UserName = 'Owner_Client' }
                target { $case.Records[$target].TargetName = $target.Replace('development', 'testing') }
                type { $case.Records[$target].Type = 2 }
                persistence { $case.Records[$target].Persist = 3 }
                utf8 { $case.Records[$target].Blob = [Text.Encoding]::UTF8.GetBytes($syntheticReporting) }
                uppercase { $case.Records[$target].Blob = [OafDevelopmentCredentials.Native]::Encode(('A' * 64)) }
                bom { $case.Records[$target].Blob = [byte[]](@(255, 254) + [OafDevelopmentCredentials.Native]::Encode($syntheticReporting)) }
                nul { $case.Records[$target].Blob = [OafDevelopmentCredentials.Native]::Encode(($syntheticReporting + [char]0)) }
                surrogate { $case.Records[$target].Blob[1] = 216 }
                short { $case.Records[$target].Blob = [OafDevelopmentCredentials.Native]::Encode(('2' * 63)) }
                provider { $case.ProviderFailure = $true }
            }
            Invoke-OfflineCase $case $activation.Operation -Fails
        }
    }
    foreach ($setting in @('OAF_ENV', 'OAF_INTEGRATION_ENVIRONMENT', 'OAF_DEVELOPMENT_ORIGIN', 'OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        [Environment]::SetEnvironmentVariable($setting, 'conflicting-owner-value', 'Process')
        Invoke-OfflineCase $case 'ActivateReporting' -Fails
        Assert-Offline ($case.Reads.Count -eq 0) 'environment conflict reached credentials'
        Assert-Offline ([Environment]::GetEnvironmentVariable($setting, 'Process') -ceq 'conflicting-owner-value') 'owner environment replaced'
    }
    $case = New-OfflineCase
    Set-OfflinePair $case
    $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL = '3' * 64
    Invoke-OfflineCase $case 'ActivateReporting' -Fails
    Assert-Offline ($env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ceq ('3' * 64)) 'existing process credential replaced'

    # Shared activation keeps the two permissions in their corresponding settings.
    $case = New-OfflineCase
    Set-OfflinePair $case
    $before = [IO.File]::ReadAllText($case.Path)
    $env:OAF_ENV = 'development'
    $env:OAF_INTEGRATION_ENABLED = 'true'
    Invoke-OfflineCase $case 'ActivateSharedServices'
    Assert-Offline ($case.Reads.Count -eq 2 -and $case.Reads[0] -ceq $submissionTarget -and
        $case.Reads[1] -ceq $reportingTarget) 'shared activation read unexpected targets'
    Assert-Offline ($env:OAF_ENV -ceq 'development' -and $env:OAF_INTEGRATION_ENABLED -ceq '1' -and
        $env:OAF_INTEGRATION_ENVIRONMENT -ceq 'development' -and $env:OAF_DEVELOPMENT_ORIGIN -ceq 'http://127.0.0.1:5055' -and
        $env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL -ceq $syntheticSubmission -and
        $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ceq $syntheticReporting) 'shared process handoff differs'
    Invoke-OfflineCase $case 'ActivateSharedServices'
    Assert-Offline ($case.Reads.Count -eq 4 -and $case.Reads[2] -ceq $submissionTarget -and
        $case.Reads[3] -ceq $reportingTarget -and $env:OAF_INTEGRATION_ENABLED -ceq '1' -and
        $env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL -ceq $syntheticSubmission -and
        $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ceq $syntheticReporting) 'shared reactivation differs'
    Assert-Offline ([IO.File]::ReadAllText($case.Path) -ceq $before) 'shared activation changed owner metadata'

    $case = New-OfflineCase
    Set-OfflinePair $case
    Invoke-OfflineCase $case 'ActivateReporting'
    Invoke-OfflineCase $case 'ActivateSharedServices'
    Assert-Offline ($case.Reads.Count -eq 3 -and $case.Reads[0] -ceq $reportingTarget -and
        $case.Reads[1] -ceq $submissionTarget -and $case.Reads[2] -ceq $reportingTarget -and
        $env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL -ceq $syntheticSubmission -and
        $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ceq $syntheticReporting) 'reporting-to-shared activation differs'

    foreach ($invalid in @('both-missing', 'equal', 'testing-metadata', 'production-metadata')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        switch ($invalid) {
            both-missing { $case.Records.Clear() }
            equal { $case.Records[$reportingTarget].Blob = [OafDevelopmentCredentials.Native]::Encode($syntheticSubmission) }
            testing-metadata { Set-OfflineMetadata $case "[testing]`nclient_id = 'owner_client'`n" }
            production-metadata { Set-OfflineMetadata $case "[production]`nclient_id = 'owner_client'`n" }
        }
        Invoke-OfflineCase $case 'ActivateSharedServices' -Fails
        if ($invalid -like '*-metadata') { Assert-Offline ($case.Reads.Count -eq 0) 'non-development metadata reached credentials' }
    }

    foreach ($setting in @('OAF_ENV', 'OAF_INTEGRATION_ENVIRONMENT', 'OAF_DEVELOPMENT_ORIGIN', 'OAF_UNEXPECTED_SETTING')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        [Environment]::SetEnvironmentVariable($setting, 'conflicting-owner-value', 'Process')
        Invoke-OfflineCase $case 'ActivateSharedServices' -Fails
        Assert-Offline ($case.Reads.Count -eq 0) 'shared environment conflict reached credentials'
    }
    foreach ($credentialName in @('OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL', 'OAF_DEVELOPMENT_REPORTING_CREDENTIAL')) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        $env:OAF_INTEGRATION_ENABLED = 'true'
        $env:OAF_INTEGRATION_ENVIRONMENT = 'development'
        $env:OAF_DEVELOPMENT_ORIGIN = 'http://127.0.0.1:5055'
        $env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL = $syntheticSubmission
        $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL = $syntheticReporting
        [Environment]::SetEnvironmentVariable($credentialName, ('3' * 64), 'Process')
        Invoke-OfflineCase $case 'ActivateSharedServices' -Fails
    }
    foreach ($restoreActive in @($false, $true)) {
        $case = New-OfflineCase
        Set-OfflinePair $case
        if ($restoreActive) {
            $env:OAF_INTEGRATION_ENABLED = 'true'
            $env:OAF_INTEGRATION_ENVIRONMENT = 'development'
            $env:OAF_DEVELOPMENT_ORIGIN = 'http://127.0.0.1:5055'
            $env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL = $syntheticSubmission
            $env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL = $syntheticReporting
        }
        Invoke-OfflineCase $case 'ActivateSharedServices' -Fails -FailStatus
        Assert-Offline ($case.Reads.Count -eq 2) 'rollback case did not reach activation'
    }

    $case = New-OfflineCase
    Set-OfflinePair $case
    $heldLock = [IO.File]::Open((Join-Path (Split-Path -Parent $case.Path) 'integrations.operator.lock'),
        [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Invoke-OfflineCase $case -Fails } finally { $heldLock.Dispose() }
    Assert-Offline ($case.Reads.Count -eq 0) 'exclusive operator lock bypassed'

    # A directory junction requires no symlink privilege. Both sides stay in temp.
    $case = New-OfflineCase
    $junction = Join-Path $testRoot ('junction-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Junction -Path $junction -Target $case.Root | Out-Null
    try {
        $case.Root = $junction
        Invoke-OfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0) 'redirect reached credentials'
    } finally { [IO.Directory]::Delete($junction) }

    Write-Output ("PASS: $count offline cases; synthetic credentials, isolated store, native credential APIs and operational RNG disabled; no secret output.")
} finally {
    foreach ($entry in @(Get-ChildItem Env:)) {
        if ($entry.Name -like 'OAF_*') { [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process') }
    }
    foreach ($name in $originalEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $originalEnvironment[$name], 'Process') }
    # Verify the resolved deletion target is the exact harness-owned temp directory.
    $resolvedRoot = [IO.Path]::GetFullPath($testRoot)
    if ($resolvedRoot.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetFileName($resolvedRoot) -match '\Aoaf-handoff-offline-[0-9a-f]{32}\z' -and
        (Test-Path -LiteralPath $resolvedRoot)) { Remove-Item -LiteralPath $resolvedRoot -Recurse -Force }
}
