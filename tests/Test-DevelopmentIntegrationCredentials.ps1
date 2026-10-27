# Standalone offline harness, Windows PowerShell 5.1; no Pester or extra packages.
# Loads function definitions through the AST, NEVER the operational entry point.
param([switch]$DevelopmentReleaseOnly)
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
if ($definitions.Count -ne 5) { throw 'Unexpected helper function inventory.' }
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
    # GetNewClosure captures this function's locals, not its caller's script scope.
    # Keep standalone invocation equivalent to dot-sourcing the harness.
    $submissionFixture = $syntheticSubmission
    $reportingFixture = $syntheticReporting
    $failureFixture = $privateMarker
    $recordFactory = ${function:New-SyntheticRecord}
    foreach ($entry in @(Get-ChildItem Env:)) {
        if ($entry.Name -like 'OAF_*') { [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process') }
    }
    $caseRoot = Join-Path $testRoot ([Guid]::NewGuid().ToString('N'))
    $local = Join-Path $caseRoot 'config\local'
    [IO.Directory]::CreateDirectory($local) | Out-Null
    $case = @{ Root = $caseRoot; Path = (Join-Path $local 'integrations.toml'); Records = @{}
        Reads = (New-Object 'System.Collections.Generic.List[string]'); Writes = 0; Generations = 0
        FailWrite = 0; ReadbackFailure = $false; ProviderFailure = $false; Race = $false; RecordFactory = $recordFactory }
    $case.Store = @{
        Read = { param($target)
            $case.Reads.Add($target)
            if ($case.ProviderFailure) { throw $failureFixture }
            if ($case.ReadbackFailure -and $case.Writes -eq 2) { throw $failureFixture }
            return $case.Records[$target]
        }.GetNewClosure()
        Create = { param($target, $account, $secret)
            $case.Writes++
            if ($case.Race) { $case.Records[$target] = & $recordFactory $target 'other-owner' $reportingFixture }
            if ($case.Records.ContainsKey($target)) { throw $failureFixture }
            if ($case.FailWrite -eq $case.Writes) { throw $failureFixture }
            $case.Records[$target] = & $recordFactory $target $account $secret
        }.GetNewClosure()
    }
    $case.Factory = {
        $case.Generations++
            if ($case.Generations -eq 1) { return $submissionFixture }
            return $reportingFixture
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
        Invoke-OafDevelopmentCredentialHandoff -Operation $Operation -Root $Case.Root -Python $python `
            -Store $Case.Store -SecretFactory $Case.Factory *>&1 | ForEach-Object { $output += $_ }
    } catch {
        $failed = $true
        $output += ($_ | Out-String)
        $output += ($_ | Format-List * -Force | Out-String)
    }
    $text = $output | Out-String
    if ($failed -ne $Fails.IsPresent) {
        $sanitized = $text
        foreach ($value in @($syntheticSubmission, $syntheticReporting, $privateMarker)) {
            $sanitized = $sanitized.Replace($value, '[REDACTED SYNTHETIC VALUE]')
        }
        [ordered]@{ utc=[DateTime]::UtcNow.ToString('o'); case_index=$script:count; operation=$Operation
            expected_failure=$Fails.IsPresent; observed_failure=$failed; writes=$Case.Writes; generations=$Case.Generations
            diagnostic=$sanitized
        } | ConvertTo-Json -Compress | Write-Output
    }
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

function Invoke-TestingOfflineCase($Case, [switch]$Fails) {
    $environmentBefore = @{}
    foreach ($entry in Get-ChildItem Env:) { $environmentBefore[$entry.Name] = $entry.Value }
    $output = @()
    $failed = $false
    try {
        Invoke-OafReleaseCredentialProvision -Root $Case.Root -Python $python `
            -Store $Case.Store -SecretFactory $Case.Factory *>&1 | ForEach-Object { $output += $_ }
    } catch {
        $failed = $true
        $output += ($_ | Format-List * -Force | Out-String)
    }
    Assert-Offline ($failed -eq $Fails.IsPresent) 'TESTING expected success/failure differs'
    $text = $output | Out-String
    foreach ($value in @($syntheticSubmission, $syntheticReporting, $privateMarker)) {
        Assert-Offline (-not $text.Contains($value)) 'TESTING secret/provider value escaped into diagnostics'
    }
    if ($Fails) {
        Assert-Offline ($text.Contains('"predicate":"testing_release_') -and
            $text.Contains('"credential_write_uncertain":') -and -not $text.Contains('PASS:')) 'TESTING first failure evidence missing'
    } else { Assert-Offline ($text.Contains('PASS:')) 'TESTING success evidence missing' }
    $environmentAfter = @(Get-ChildItem Env:)
    Assert-Offline ($environmentAfter.Count -eq $environmentBefore.Count) 'TESTING changed environment inventory'
    foreach ($entry in $environmentAfter) {
        Assert-Offline ($entry.Value -ceq $environmentBefore[$entry.Name]) 'TESTING changed environment or activation'
    }
    foreach ($target in $Case.Reads) { Assert-Offline ($target -ceq $testingTarget) 'TESTING read a different credential' }
    $script:count++
}

$submissionTarget = 'OAF Website/development/Integrations/Submission'
$reportingTarget = 'OAF Website/development/Integrations/Reporting'
$testingTarget = 'OAF Website/testing/Integrations/Release'
$testingMetadata = "[testing]`nclient_id = `"gramanna`"`nrelease_credential_service = `"OAF Website/testing/Integrations/Release`"`nrelease_credential_account = `"gramanna`"`n"

function Invoke-DevelopmentReleaseOfflineCase($Case, [switch]$Fails) {
    $before = @{}
    foreach ($entry in Get-ChildItem Env:) { $before[$entry.Name] = $entry.Value }
    $output = @()
    $failed = $false
    try {
        Invoke-OafReleaseCredentialProvision -Root $Case.Root -Python $python `
            -Store $Case.Store -SecretFactory $Case.Factory -IntegrationProfile 'development' *>&1 |
            ForEach-Object { $output += $_ }
    } catch {
        $failed = $true
        $output += ($_ | Format-List * -Force | Out-String)
    }
    $text = $output | Out-String
    Assert-Offline ($failed -eq $Fails.IsPresent) 'DEVELOPMENT Release expected success/failure differs'
    foreach ($value in @($syntheticSubmission, $syntheticReporting, $privateMarker)) {
        Assert-Offline (-not $text.Contains($value)) 'DEVELOPMENT Release secret/provider value escaped'
    }
    if ($Fails) {
        Assert-Offline ($text.Contains('"predicate":"development_release_') -and
            $text.Contains('"credential_write_uncertain":') -and -not $text.Contains('PASS:')) 'DEVELOPMENT first failure evidence missing'
    } else { Assert-Offline ($text.Contains('PASS:')) 'DEVELOPMENT success evidence missing' }
    $after = @(Get-ChildItem Env:)
    Assert-Offline ($after.Count -eq $before.Count) 'DEVELOPMENT Release changed environment inventory'
    foreach ($entry in $after) { Assert-Offline ($entry.Value -ceq $before[$entry.Name]) 'DEVELOPMENT Release changed activation' }
    foreach ($target in $Case.Reads) {
        Assert-Offline ($target -ceq $developmentReleaseTarget) 'DEVELOPMENT Release read another credential'
    }
    $script:count++
}

try {
    if (-not $DevelopmentReleaseOnly) {
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

    # The new TESTING operation reuses the same guarded native codec/store seam.
    $case = New-OfflineCase
    Set-OfflineMetadata $case "# owner DEVELOPMENT metadata`n[development]`nclient_id='owner_client'`n"
    $ownerMetadata = [IO.File]::ReadAllText($case.Path)
    Invoke-TestingOfflineCase $case
    $testingPath = Join-Path (Split-Path -Parent $case.Path) 'integrations.testing.toml'
    Assert-Offline ($case.Writes -eq 1 -and $case.Generations -eq 1) 'TESTING generated/wrote more than Release'
    Assert-Offline ([IO.File]::ReadAllText($case.Path) -ceq $ownerMetadata) 'TESTING replaced DEVELOPMENT metadata'
    Assert-Offline ([IO.File]::ReadAllText($testingPath) -ceq $testingMetadata) 'TESTING explicit metadata differs'
    Assert-Offline ((Read-OafDevelopmentClientId $testingPath $python 'testing') -ceq 'gramanna') 'TESTING metadata parser differs'
    Invoke-TestingOfflineCase $case
    Assert-Offline ($case.Writes -eq 1 -and $case.Generations -eq 1) 'TESTING idempotence replaced credential'

    $case = New-OfflineCase
    $testingPath = Join-Path (Split-Path -Parent $case.Path) 'integrations.testing.toml'
    [IO.File]::WriteAllText($testingPath, $testingMetadata)
    Invoke-TestingOfflineCase $case
    Assert-Offline ($case.Writes -eq 1) 'TESTING existing valid metadata prevented provisioning'

    foreach ($metadata in @('', '[testing', "testing='invalid'", $testingMetadata.Replace('[testing]', '[development]'),
        $testingMetadata.Replace('gramanna', 'Gramanna'), $testingMetadata.Replace('/testing/', '/production/'),
        $testingMetadata.Replace('/Release', '/Submission'), $testingMetadata.Replace('/Release', '/Reporting'),
        ($testingMetadata + "secret='$privateMarker'"))) {
        $case = New-OfflineCase
        $testingPath = Join-Path (Split-Path -Parent $case.Path) 'integrations.testing.toml'
        [IO.File]::WriteAllText($testingPath, $metadata)
        Invoke-TestingOfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0 -and $case.Writes -eq 0 -and $case.Generations -eq 0) 'TESTING invalid metadata reached credential effects'
    }

    foreach ($invalid in @('metadata', 'account', 'target', 'type', 'persistence', 'utf8', 'uppercase', 'bom', 'nul', 'surrogate', 'short')) {
        $case = New-OfflineCase
        $testingPath = Join-Path (Split-Path -Parent $case.Path) 'integrations.testing.toml'
        if ($invalid -ne 'metadata') { [IO.File]::WriteAllText($testingPath, $testingMetadata) }
        $record = New-SyntheticRecord $testingTarget 'gramanna' $syntheticSubmission
        switch ($invalid) {
            account { $record.UserName = 'Gramanna' }
            target { $record.TargetName = $testingTarget.Replace('testing', 'development') }
            type { $record.Type = 2 }
            persistence { $record.Persist = 3 }
            utf8 { $record.Blob = [Text.Encoding]::UTF8.GetBytes($syntheticSubmission) }
            uppercase { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(('A' * 64)) }
            bom { $record.Blob = [byte[]](@(255,254) + $record.Blob) }
            nul { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(($syntheticSubmission + [char]0)) }
            surrogate { $record.Blob[1] = 216 }
            short { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(('1' * 63)) }
        }
        $case.Records[$testingTarget] = $record
        Invoke-TestingOfflineCase $case -Fails
        Assert-Offline ($case.Writes -eq 0 -and $case.Generations -eq 0) 'TESTING conflicting credential replaced'
    }

    foreach ($failure in @('provider', 'write', 'readback', 'race', 'generation', 'format', 'mismatch')) {
        $case = New-OfflineCase
        switch ($failure) {
            provider { $case.ProviderFailure = $true }
            write { $case.FailWrite = 1 }
            readback {
                $case.Store.Read = { param($target)
                    $case.Reads.Add($target)
                    if ($case.Writes -eq 1) { throw $privateMarker }
                    return $null
                }.GetNewClosure()
            }
            race { $case.Race = $true }
            generation { $case.Factory = { throw $privateMarker } }
            format { $case.Factory = { 'A' * 64 } }
            mismatch {
                $case.Store.Read = { param($target)
                    $case.Reads.Add($target)
                    if ($case.Writes -eq 1) { return (& $case.RecordFactory $target 'gramanna' $syntheticReporting) }
                    return $null
                }.GetNewClosure()
            }
        }
        Invoke-TestingOfflineCase $case -Fails
    }
    foreach ($setting in @('OAF_ENV', 'OAF_INTEGRATION_ENABLED', 'OAF_TESTING_RELEASE_CREDENTIAL', 'PYTHON_KEYRING_BACKEND', 'KEYRING_PROPERTY_TEST')) {
        $case = New-OfflineCase
        [Environment]::SetEnvironmentVariable($setting, 'conflicting-owner-value', 'Process')
        try { Invoke-TestingOfflineCase $case -Fails } finally { [Environment]::SetEnvironmentVariable($setting, $null, 'Process') }
        Assert-Offline ($case.Reads.Count -eq 0) 'TESTING environment conflict reached credentials'
    }
    $case = New-OfflineCase
    $env:OAF_ENV = 'testing'
    $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.Windows.WinVaultKeyring'
    try { Invoke-TestingOfflineCase $case } finally { Remove-Item Env:PYTHON_KEYRING_BACKEND }

    $case = New-OfflineCase
    $heldLock = [IO.File]::Open((Join-Path (Split-Path -Parent $case.Path) 'integrations.operator.lock'),
        [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Invoke-TestingOfflineCase $case -Fails } finally { $heldLock.Dispose() }
    Assert-Offline ($case.Reads.Count -eq 0) 'TESTING operator lock bypassed'
    $case = New-OfflineCase
    $missingPython = $python
    try { $python = Join-Path $case.Root 'absent.exe'; Invoke-TestingOfflineCase $case -Fails } finally { $python = $missingPython }
    Assert-Offline ($case.Reads.Count -eq 0) 'TESTING missing interpreter reached credentials'
    $case = New-OfflineCase
    $junction = Join-Path $testRoot ('junction-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Junction -Path $junction -Target $case.Root | Out-Null
    try {
        $case.Root = $junction
        Invoke-TestingOfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0) 'TESTING redirect reached credentials'
    } finally { [IO.Directory]::Delete($junction) }

    }

    $developmentReleaseTarget = 'OAF Website/development/Integrations/Release'
    $developmentReleaseMetadata = $testingMetadata.Replace('testing', 'development')
    $case = New-OfflineCase
    Invoke-DevelopmentReleaseOfflineCase $case
    Assert-Offline ($case.Writes -eq 1 -and $case.Generations -eq 1 -and $case.Records.Count -eq 1) 'DEVELOPMENT Release wrote more than one record'
    Assert-Offline ([IO.File]::ReadAllText($case.Path) -ceq $developmentReleaseMetadata) 'DEVELOPMENT Release metadata differs'
    Invoke-DevelopmentReleaseOfflineCase $case
    Assert-Offline ($case.Writes -eq 1 -and $case.Generations -eq 1) 'DEVELOPMENT Release idempotence replaced record'

    $case = New-OfflineCase
    Set-OfflineMetadata $case ("# owner metadata preserved`n" + $developmentReleaseMetadata)
    $ownerMetadata = [IO.File]::ReadAllText($case.Path)
    $testingPath = Join-Path (Split-Path -Parent $case.Path) 'integrations.testing.toml'
    [IO.File]::WriteAllText($testingPath, $testingMetadata)
    $case.Records[$testingTarget] = New-SyntheticRecord $testingTarget 'gramanna' $syntheticReporting
    Invoke-DevelopmentReleaseOfflineCase $case
    Assert-Offline ([IO.File]::ReadAllText($case.Path) -ceq $ownerMetadata -and
        [IO.File]::ReadAllText($testingPath) -ceq $testingMetadata -and $case.Records.Count -eq 2) 'DEVELOPMENT changed owner metadata/TESTING'
    Assert-Offline ((Read-OafDevelopmentClientId $case.Path $python) -ceq 'gramanna') 'existing parser rejected DEVELOPMENT Release metadata'

    foreach ($metadata in @('', '[development', "development='invalid'", "[development]`nclient_id='gramanna'`n",
        $testingMetadata, $developmentReleaseMetadata.Replace('gramanna', 'Gramanna'),
        $developmentReleaseMetadata.Replace('/development/', '/testing/'),
        $developmentReleaseMetadata.Replace('/development/', '/production/'),
        $developmentReleaseMetadata.Replace('/Release', '/Submission'),
        $developmentReleaseMetadata.Replace('/Release', '/Reporting'),
        $developmentReleaseMetadata.Replace('/Release', '/Brevo'),
        $developmentReleaseMetadata.Replace('release_credential_account', 'other_account'),
        ($developmentReleaseMetadata + "secret='$privateMarker'"))) {
        $case = New-OfflineCase
        Set-OfflineMetadata $case $metadata
        Invoke-DevelopmentReleaseOfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0 -and $case.Writes -eq 0 -and $case.Generations -eq 0) 'DEVELOPMENT invalid binding reached credential effects'
    }

    foreach ($invalid in @('metadata', 'account', 'target', 'type', 'persistence', 'utf8', 'uppercase', 'bom', 'nul', 'surrogate', 'short')) {
        $case = New-OfflineCase
        if ($invalid -ne 'metadata') { Set-OfflineMetadata $case $developmentReleaseMetadata }
        $record = New-SyntheticRecord $developmentReleaseTarget 'gramanna' $syntheticSubmission
        switch ($invalid) {
            account { $record.UserName = 'Gramanna' }
            target { $record.TargetName = $testingTarget }
            type { $record.Type = 2 }
            persistence { $record.Persist = 3 }
            utf8 { $record.Blob = [Text.Encoding]::UTF8.GetBytes($syntheticSubmission) }
            uppercase { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(('A' * 64)) }
            bom { $record.Blob = [byte[]](@(255,254) + $record.Blob) }
            nul { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(($syntheticSubmission + [char]0)) }
            surrogate { $record.Blob[1] = 216 }
            short { $record.Blob = [OafDevelopmentCredentials.Native]::Encode(('1' * 63)) }
        }
        $case.Records[$developmentReleaseTarget] = $record
        Invoke-DevelopmentReleaseOfflineCase $case -Fails
        Assert-Offline ($case.Writes -eq 0 -and $case.Generations -eq 0) 'DEVELOPMENT conflicting credential replaced'
    }

    foreach ($failure in @('provider', 'write', 'readback', 'race', 'generation', 'format', 'mismatch', 'metadata-readback')) {
        $case = New-OfflineCase
        switch ($failure) {
            provider { $case.ProviderFailure = $true }
            write { $case.FailWrite = 1 }
            readback {
                $case.Store.Read = { param($target)
                    $case.Reads.Add($target)
                    if ($case.Writes -eq 1) { throw $privateMarker }
                    return $null
                }.GetNewClosure()
            }
            race { $case.Race = $true }
            generation { $case.Factory = { throw $privateMarker } }
            format { $case.Factory = { 'A' * 64 } }
            mismatch {
                $case.Store.Read = { param($target)
                    $case.Reads.Add($target)
                    if ($case.Writes -eq 1) { return (& $case.RecordFactory $target 'gramanna' $syntheticReporting) }
                    return $null
                }.GetNewClosure()
            }
            metadata-readback {
                $case.Store.Read = { param($target)
                    $case.Reads.Add($target)
                    if ($case.Writes -eq 1) { [IO.File]::WriteAllText($case.Path, '[development]') }
                    return $case.Records[$target]
                }.GetNewClosure()
            }
        }
        Invoke-DevelopmentReleaseOfflineCase $case -Fails
    }

    foreach ($setting in @('OAF_ENV', 'OAF_INTEGRATION_ENABLED', 'OAF_RELEASE_HANDOFF_ENABLED',
        'OAF_DEVELOPMENT_RELEASE_CREDENTIAL', 'OAF_TESTING_RELEASE_CREDENTIAL', 'PYTHON_KEYRING_BACKEND', 'KEYRING_PROPERTY_TEST')) {
        $case = New-OfflineCase
        [Environment]::SetEnvironmentVariable($setting, 'conflicting-owner-value', 'Process')
        try { Invoke-DevelopmentReleaseOfflineCase $case -Fails } finally { [Environment]::SetEnvironmentVariable($setting, $null, 'Process') }
        Assert-Offline ($case.Reads.Count -eq 0) 'DEVELOPMENT environment conflict reached credentials'
    }
    $case = New-OfflineCase
    $env:OAF_ENV = 'development'
    $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.Windows.WinVaultKeyring'
    try { Invoke-DevelopmentReleaseOfflineCase $case } finally { Remove-Item Env:PYTHON_KEYRING_BACKEND }

    $case = New-OfflineCase
    $heldLock = [IO.File]::Open((Join-Path (Split-Path -Parent $case.Path) 'integrations.operator.lock'),
        [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try { Invoke-DevelopmentReleaseOfflineCase $case -Fails } finally { $heldLock.Dispose() }
    Assert-Offline ($case.Reads.Count -eq 0) 'DEVELOPMENT operator lock bypassed'
    $case = New-OfflineCase
    $savedPython = $python
    try { $python = Join-Path $case.Root 'absent.exe'; Invoke-DevelopmentReleaseOfflineCase $case -Fails } finally { $python = $savedPython }
    Assert-Offline ($case.Reads.Count -eq 0) 'DEVELOPMENT missing interpreter reached credentials'
    $case = New-OfflineCase
    $junction = Join-Path $testRoot ('junction-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Junction -Path $junction -Target $case.Root | Out-Null
    try {
        $case.Root = $junction
        Invoke-DevelopmentReleaseOfflineCase $case -Fails
        Assert-Offline ($case.Reads.Count -eq 0) 'DEVELOPMENT redirect reached credentials'
    } finally { [IO.Directory]::Delete($junction) }

    # The changed parser must keep the existing client-only provisioning path.
    $case = New-OfflineCase
    Set-OfflineMetadata $case
    Assert-Offline ((Read-OafDevelopmentClientId $case.Path $python) -ceq 'owner_client') 'client-only parser compatibility changed'
    $count++
    # Directly affected TESTING dispatch/parser dependency: one create + replay.
    $case = New-OfflineCase
    Invoke-TestingOfflineCase $case
    Invoke-TestingOfflineCase $case
    Assert-Offline ($case.Writes -eq 1 -and $case.Generations -eq 1) 'shared provisioner changed TESTING idempotence'

    # Verify the real owner parameter/dispatch/transcript boundary using its
    # unmodified AST text in a synthetic repository. Only operational leaves
    # are replaced; the native API/RNG in this process remain hard-denied.
    $entryText = $ast.Extent.Text.Substring($ast.Extent.Text.IndexOf('$releaseTranscript = $false'))
    foreach ($profileName in @('development', 'testing')) {
        $case = New-OfflineCase
        $dispatchDirectory = Join-Path $case.Root 'ops'
        [IO.Directory]::CreateDirectory($dispatchDirectory) | Out-Null
        $dispatchPath = Join-Path $dispatchDirectory 'Set-DevelopmentIntegrationCredentials.ps1'
        $leafText = @'
function Initialize-OafDevelopmentCredentialApi { }
function Invoke-OafReleaseCredentialProvision {
    param($Root, $Python, $Store, $SecretFactory, $IntegrationProfile)
    if ($IntegrationProfile -cne 'EXPECTED_PROFILE' -or
        $Root -cne (Split-Path -Parent $PSScriptRoot) -or
        $Python -cne (Join-Path $Root '.venv\Scripts\python.exe')) {
        throw 'Offline owner dispatch mismatch.'
    }
    Write-Output 'PASS: Offline owner dispatch; no credential API or generator invoked.'
}
'@
        $dispatchText = $ast.ParamBlock.Extent.Text + "`n" +
            $leafText.Replace('EXPECTED_PROFILE', $profileName) + "`n" + $entryText
        [IO.File]::WriteAllText($dispatchPath, $dispatchText)
        $operationName = 'ProvisionTestingRelease'
        if ($profileName -ceq 'development') { $operationName = 'ProvisionDevelopmentRelease' }
        $dispatchOutput = (& $dispatchPath -Operation $operationName | Out-String)
        Assert-Offline ($dispatchOutput.Contains('PASS: Offline owner dispatch')) 'owner operation did not reach intended profile'
        $transcripts = @(Get-ChildItem -LiteralPath (Join-Path $case.Root '.pytest_cache') -Filter 'execution.log' -Recurse)
        Assert-Offline ($transcripts.Count -eq 1 -and
            $transcripts[0].Directory.Name.StartsWith($profileName + '-release-provision-')) 'owner transcript location/profile differs'
        $transcript = [IO.File]::ReadAllText($transcripts[0].FullName)
        Assert-Offline ($transcript.Contains('PowerShell transcript end') -and
            -not $transcript.Contains($syntheticSubmission) -and -not $transcript.Contains($privateMarker)) 'owner transcript not finalized/sanitized'
        $count++
    }

    Write-Output ("PASS: $count focused offline cases; synthetic credentials, isolated store, native credential APIs and operational RNG disabled; no secret output.")
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
