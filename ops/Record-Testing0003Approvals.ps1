# Native Windows PowerShell 5.1; owner-approved record-only TESTING 0003 checkpoint.
# This script prepares/saves exactly three approvals, using existing website Python.
# Run from this OAF Website repository. No authorization issuance or database access.
[CmdletBinding(DefaultParameterSetName = 'Record')]
param(
    [Parameter(ParameterSetName = 'Validate')][switch]$ValidateOnly,
    [Parameter(ParameterSetName = 'Verify')][switch]$VerifyOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskArtifactId = '6ddae102-027c-4ef3-8041-fdb499ca1b32'
$taskAttestationId = 'eddbe068-234b-43b5-b08f-c8e7cc3c7681'
$taskApprovalId = '27286b07-9855-40ed-889f-f9913d910af6'
$taskLines = New-Object 'System.Collections.Generic.List[string]'
$taskExitCode = 2
$taskAlertReady = $false
$taskRecordsVerified = $false
$taskAudit = $null
$taskPaths = @()

function Write-TaskLine([string]$Text) {
    $taskLines.Add($Text)
    Write-Host $Text
}

function Initialize-TaskUI {
    # Load only the existing alert function, without executing unrelated profile code.
    $taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
    if (-not (Test-Path -LiteralPath $taskProfile -PathType Leaf)) { throw 'Existing OAF alert profile is unavailable.' }
    $taskProfileTokens = $null
    $taskProfileErrors = $null
    $taskProfileAst = [System.Management.Automation.Language.Parser]::ParseFile(
        $taskProfile, [ref]$taskProfileTokens, [ref]$taskProfileErrors)
    if ($taskProfileErrors.Count -ne 0) { throw 'Existing OAF profile syntax is invalid.' }
    $taskAlertDefinitions = @($taskProfileAst.FindAll({
        param($taskNode)
        $taskNode -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $taskNode.Name -ceq 'Show-OAFPowerShellAlert'
    }, $false))
    if ($taskAlertDefinitions.Count -ne 1) { throw 'Expected exactly one existing OAF visual alert function.' }
    . ([ScriptBlock]::Create($taskAlertDefinitions[0].Extent.Text))
    # Retain the existing definition in script scope after this helper returns.
    Set-Item -Path Function:script:Show-OAFPowerShellAlert -Value (Get-Item Function:Show-OAFPowerShellAlert).ScriptBlock
    $script:taskAlertReady = $true
    if (-not (Get-Command Set-Clipboard -ErrorAction SilentlyContinue) -or
        -not (Get-Command Get-Clipboard -ErrorAction SilentlyContinue)) { throw 'Existing clipboard support is unavailable.' }
}

# ASCII stdin avoids native Windows -c quoting. Each mode runs in a fresh process.
$taskPythonCode = @'
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import socket
import sys

REPO = Path(r'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website')
AUDIT = Path(r'C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit\MigrationAudit')
ARTIFACT_ID = '6ddae102-027c-4ef3-8041-fdb499ca1b32'
ATTESTATION_ID = 'eddbe068-234b-43b5-b08f-c8e7cc3c7681'
APPROVAL_ID = '27286b07-9855-40ed-889f-f9913d910af6'
REVIEWER = '01ed5b95-c24e-402e-a547-c24447303ed5'
TESTING_RUN = 'cd8521b7-eb3d-412f-8ac1-188cabd04b30'
OLD_ARTIFACT = 'b0d4b5a9-3b86-46d3-9e7e-67268a2f3897'
OLD_ATTESTATION = 'fe53d5d1-8e82-409e-a8ee-265d18f95d31'
OLD_APPROVAL = '853a9204-da09-405a-856f-2725eb541657'
PREPARED_UTC = '2026-10-12T01:51:37.873041+00:00'
PREDECESSOR = {'sequence': 2,
    'sha256': '09a2149025e903a403baac9b89a9e34aaf2a2aa0b6fd1818f83db8d7301166df'}
SCOPE = {'action': 'upgrade', 'environment': 'testing',
    'expected_start': '0002_state_requests', 'target': '0003_notifications',
    'manifest_hash': '5aa7ef4b007282e8d543fed090471fd181368be1ad6d600469c440fbbf5929de',
    'revision_hash': '1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452'}
PRIOR_SCOPE = {'action': 'upgrade', 'environment': 'testing',
    'expected_start': '0001_migration_baseline', 'target': '0002_state_requests',
    'manifest_hash': '41fff9427895ac584d34664dd1c6400ae5772eb6297910392d98751bfde5710e',
    'revision_hash': 'c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad'}
SNAPSHOT = {
    "repository": {
        "docs/WORKFLOW.md": "a5e7381f2887b30478e110ffc393705efe1e205cb9142de229955759e73e6250",
        "docs/WEBSITE_PLAN.md": "1d639ced0cf70d3338e644aca536b037918481773e7e0a831b1f5a8daf6cd161",
        "alembic.ini": "c72a8cc54828755974765ab8df60c03744cd448b7d16bed81b1157569548f736",
        "requirements.txt": "3f8e4f324231e88e0c7a9e1be05c9a26be0a1d5628a5b9947b2ee7794b96fb9d",
        "requirements-migrations.txt": "3154eef6a20748636332276d9a39e13b1d03585df55ab681b706362d294de33e",
        "migrations/env.py": "09fcd94121f9ba0287d33d9b779f2b7845be56f23fea23aaafb5ae891fe661d4",
        "migrations/script.py.mako": "ed31327e01d48ec1ba1e91f5dc5b347fed7e9a8c9733b50d49c8085e86815bdc",
        "migrations/manifest.json": "a6de6003623100f6246b03f1eafcd698411beabaa28cd1b5cf68a0fc8af84c52",
        "migrations/versions/0001_migration_baseline.py": "bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3",
        "migrations/versions/0002_state_requests.py": "c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad",
        "migrations/versions/0003_notifications.py": "1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452",
        "oaf_website/__init__.py": "ad4cfd8e9137a2e69abe6fdad18114a9918fccf918cbe59e181a9edd78436eb5",
        "oaf_website/database_config.py": "bffc9d41024c7d562944d67c55cff254e63c0f5c83f54ec4b2384c64ab51ed60",
        "oaf_website/migration_config.py": "9c537cceaed6c84b3050f4db0a2510e6588e4259e927b35322e86cab91ab3587",
        "oaf_website/migrate.py": "706a6fefaca086f43bd2729c1cafefdb5bfe3bbd2f71e7a404e2e922454ae1e0",
        "oaf_website/migration_authority.py": "7654a552106b7ef3ec5827decf0ea9f61b317b2265c4364a0d5d7278549da6ce",
        "oaf_website/migration_validation.py": "a5ef986aae4515d0f39c416dad812a0479c094b9d5b81a37c04d298f88b05b23",
        "oaf_website/state_request_schema.py": "440924c43651c6b7d1e5c8745de705dd0ceeb589eb10422e805131ede51f9647",
        "oaf_website/state_request_validation.py": "a04e8a50bf353dd1de03a3f310445adb9392a33d0ae8c441ebd877d03d32db5d",
        "oaf_website/notification_schema.py": "765e295c8b579b5441829fcf944f3bb92c2d13d92cb5d510ee4667e8bd6baa44",
        "oaf_website/notification_validation.py": "939200c718fa5131427315ce6b7f10ebe4177653c7744d54c3e593d263a26267",
        "tests/test_notifications.py": "61c13313be8394601eacf189458358d85e4fab5a66d515550e9512e75c3cc50c",
        "tests/test_notification_migration.py": "882db4c617e1814679bcff965c944950c9812e09764ce1947ad44559eb72c81d",
        "tests/test_migration_artifacts.py": "480d3488fa45ee9f9352c4f1d4e72c55e9ff3023ff46afe1c35b94dba558bdbf",
        "tests/test_migration_authorization.py": "075a1091b6d212d047ced023b21a350930f9cb87154f913258b291eae0df50a0",
        "tests/test_migration_operational.py": "bbde79df63f41b2be68fa100c6f1a138d3865c567f4f5e078e1b26fdf2c5e3a8",
        "tests/migration_offline.py": "9bff47388ffd364704f251b8643edd7fdfe56d9b76681ffa2639422ffa8e1fd7",
        "ops/local_postgres_bootstrap/01_roles.sql": "cf314c1c946564282262564befb6831b49289f4280352d998a4da7bc7f0f0c3b",
        "ops/local_postgres_bootstrap/03_test_schema.sql": "e980a521e24d5b9f3c2642268029cd19a9156e9068243987fac6238fe687d7e2",
        "ops/local_postgres_bootstrap/04_verify.sql": "848220a0bd24a4a8c1ee24aeb315728fba92ea23b0c309dbe47580e7af57427d"
    },
    "audit": {
        "artifact-approval-75755e44-1423-4ffb-8b67-8ebb1a205072.json": "30293bcce535ddee16f8cc4e5d39bff25bebcef4aabaffb6233b30c366a17b01",
        "artifact-approval-b0d4b5a9-3b86-46d3-9e7e-67268a2f3897.json": "4ed6a218b8c4eda2f1e6b5b25a9df9025c3b0025efe48d34d2d3f40f15337e11",
        "authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "6bf6d5b0e282e6ca95a31a389908f897057a5e1cb253ee20fb762e13449607e7",
        "authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "d7a5eeb67b0e9e70a3c16bf58ef830479dc3dd6fdf30b2e06f2e9e00c20b6fb2",
        "authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "c43d5eacbf1d8d78a9ac5b178a8b4d4aff766bb05a7ec7544c1aa5ac0ab78621",
        "authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "7b51d8a86fe6d82863bd86a7450d9063ccd302b18d10c858fb91432fed4db101",
        "claim-development-00000001.json": "207d41a387a793d5fea113dd2f020de12493d482d8556ae88e3c9f71c3db38db",
        "claim-development-00000002.json": "64d28271fc319552e51e85a06809089559b5dfb42f039f654c85ba925ede8b93",
        "claim-testing-00000001.json": "642c6452a0b2ad6068a2d00534977985d2d081cd787a30489e9772b13075728c",
        "claim-testing-00000002.json": "09a2149025e903a403baac9b89a9e34aaf2a2aa0b6fd1818f83db8d7301166df",
        "completed-authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "cb3d08d15a917aa9040f0806fc965feb7049b0bdd2e31a7e60927af08d9e9b39",
        "completed-authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "a05817e9e23b8fe02d440781560a9150d1bf9685c30c1b0772dc444494dbab7e",
        "completed-authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "aae5c4b471b4fd1eb01713f996e73007a5209e225f5c7c2432db31c425baa5f7",
        "completed-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "completed-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "completed-terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "f17b38bb9a2240131843c52f4f8624ad1aad192a34341aad8e86bd59fa7fc020",
        "completed-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "completed-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000001.json": "574b8f7f8e9b102ef9e30b95d7e76771e5ca90d70d4dc0913a3d78bc1f98852f",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000002.json": "83568e5f0e603e9b08f5757c6443fc56a9ebb560b4b800f2fed70ad68d6365f2",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000003.json": "98187b3def61298fadabeebe48e66112eef8a9c9c2195a7da9d109568e6cf9ce",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000004.json": "365922b04a761c4bf3d84378ef9560e741495598b95706452b6faef509bbe99e",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000005.json": "0d17ba565d7029e364cc9c8a351d23d910502fe95dc13835f5c91da91d78ae48",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000006.json": "f556c33ed84c00aa948a14c92f0aa51f8d8c5b4ebbacaa88b1c57174062af052",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000007.json": "7f912cfc11889587f3a90ddcb4af3b315632e9f2ca71c9bf0f8f8f60da47ac6c",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000001.json": "d1bdf34f560d54e5e7831c42797b248453d1865f2d39d3cf8e97ef710fa75f6a",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000002.json": "b36da14b821a751f3170a09466c675d28e1217bbcc7634337a9b26aa4db5c5b9",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000003.json": "5d9892cce78c6990bf8bc6319aae66e036ffb4b53df2ba1894704e89e59467d9",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000004.json": "199f43340d88eb777c1c55736537ec6c136a19e6958116166639775da62f329f",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000005.json": "e6788f60a426b5cc45ace93f62b2c569bddf5b950dbfffa233eadc395a7ba57e",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000006.json": "3d41888f14510efa71adc76755af1a8c16063a50072dcf662b8b81ca329c1e53",
        "event-545553f6-0367-4116-89dd-eb3945fd38ce-00000007.json": "847b06ade84769eeaa437141fbf331722cc5b5ed74e58d44c159cdb3fc43f939",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000001.json": "4a58532bff9f852b4814a243caed7860f492331fe1bee133605acf610e050d95",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000002.json": "8bbf2e95fde585dd685b3b9bd39cff015d8c721f68c544ee0840ae4fd1294e18",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000003.json": "f1cc54daa3a144f79215e81c5244bf9f408c20d2460a5e3bc51d79383a234825",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000004.json": "7babc55bf8ce7d30e00ee2213de0dc8fb4d6dc7a07100f4a11a07969ef4c43fd",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000005.json": "a84cbebb91319988edd16bc8cc98ddc2f62f91300a66a30c85d1baabb8c91387",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000006.json": "403301ca3a0e37cd05773bf50a2a0908363f796bc36b64548ed6660eba8da52d",
        "event-aeb43928-be3b-44e5-9fa0-2527761fc9e3-00000007.json": "a65b15a64f32b34018a60aeeb9ede7fa03a304dfc6ed90da1883c27b1faacab2",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000001.json": "f4af7c08cee867cb9ec7d02a5208999a0fd91aa3bf5e0a11c76f196961cf8cd8",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000002.json": "7bc7eb8f35a552621b5dd8d1410dfde962a5f2495af7e5aa81e76e015fca8e0c",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000003.json": "e90e4e53c7b4e1fec794e847b1fd6b82d267dffd6b266c4e4388705d797a42ad",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000004.json": "7f0695db8001aadb6abf1654c52bf78359add194ac70dfe6d8be1368e5e3e304",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000005.json": "e2cbcae341c8e72ee43969d60b92b287cd468cc633b27fccd47fc5243ce1ebbf",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000006.json": "b3ebaebeb75ff34ddc98348f026464d2d6c2b6413c09b3d5b9cc2383426d410f",
        "event-cd8521b7-eb3d-412f-8ac1-188cabd04b30-00000007.json": "2a6dd9438f25003691962931a96e010aaeec8e04c4551a755c05fde891e3c2a4",
        "pending-authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "cb3d08d15a917aa9040f0806fc965feb7049b0bdd2e31a7e60927af08d9e9b39",
        "pending-authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "a05817e9e23b8fe02d440781560a9150d1bf9685c30c1b0772dc444494dbab7e",
        "pending-authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "aae5c4b471b4fd1eb01713f996e73007a5209e225f5c7c2432db31c425baa5f7",
        "pending-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "pending-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "pending-terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "f17b38bb9a2240131843c52f4f8624ad1aad192a34341aad8e86bd59fa7fc020",
        "pending-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "pending-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "prerequisite-approval-2c42eb66-2155-4762-8692-a7170512ae3d.json": "6a95a3a8ec1effc8d28524ad0d61338c042bc49a67dd4a93431d4cfa99e1fba2",
        "prerequisite-approval-55fd6fee-b2b2-40fb-bab0-a0c87c35462a.json": "ce89b823c83246e1f464883b6e4123e2cb1989e6a382f8d3192d2b7928090833",
        "prerequisite-approval-853a9204-da09-405a-856f-2725eb541657.json": "b45db8f2c870d462615a51fcefb829f8defe25298c7a11cefa8e2524c0a1551c",
        "prerequisite-approval-fa98f647-7757-45a5-9634-37322383237e.json": "1f3f0bac8e9dd28aa90c84bdcf610761aa59a7ed38f8d85d7895bed9f50f6e6e",
        "prerequisite-attestation-8b388045-48f2-4e32-bd5d-6756ee004791.json": "1b70ad606db4b5fd2146a4e50d100d341e0483afafe0d292b227459cbc9deef1",
        "prerequisite-attestation-fe53d5d1-8e82-409e-a8ee-265d18f95d31.json": "9e994e1d27ebec0d35796c24885aa633c973afb2b6844bf6260dfe18f5e7c19f",
        "terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "c7c4296c78437b63063d0489ee7c672ab14ee3a76783ec233063a6678a264311",
        "terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "b62546bb5bf1d5dce47c5abdc6dfd3039cefa591f5993fb027160b62fc74ef6a",
        "terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "3bd8e351c6e70a667c9fe430367ca064f14b503112027291b4ec47d2a6b42a27",
        "terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "e3114c601e7d8aa0cc0ff65664c32eedf4322dbc2b5be593fabdbf6763421a04"
    }
}
NEW_NAMES = (
    'artifact-approval-' + ARTIFACT_ID + '.json',
    'prerequisite-attestation-' + ATTESTATION_ID + '.json',
    'prerequisite-approval-' + APPROVAL_ID + '.json',
)
OWNER_EVIDENCE = (
    'OWNER APPROVAL: GRANTED.\n'
    'OBJECTIVE: Complete the record-only approval checkpoint for:\n'
    'TESTING 0002_state_requests -> 0003_notifications.\n'
    'Independent Astra review: PASS.\n'
    'Approval preparation: PASS.\n'
    'No material defects or outstanding design decisions.\n'
    'Adopt the completed revision-specific evidence for:\n'
    'dependency_acceptance, bootstrap_validation,\n'
    'lock_and_timeouts, search_path_and_postconditions,\n'
    'recovery_procedure, and audit_policies.\n'
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def deny_external_access(*args, **kwargs):
    raise RuntimeError('Credential, network, database, authorization or migration access is blocked.')


def encoded(record):
    return (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def safe_path(path, directory=False):
    require(path.is_absolute() and path.resolve() == path, 'Unexpected or redirected absolute path.')
    for component in (path, *path.parents):
        require(not component.is_symlink() and
                not (getattr(component.lstat(), 'st_file_attributes', 0) & 0x400),
                'Redirected path component.')
    require(path.is_dir() if directory else path.is_file(), 'Required evidence path unavailable.')


def byte_hash(path):
    safe_path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutation_guard(mode):
    # Defense in depth: read-only modes cannot write even through a validator.
    # Creation permits ONLY exclusive creation of these three exact destinations.
    allowed = {str(AUDIT / name) for name in NEW_NAMES}
    def guard(event, args):
        if event == 'open':
            path, _, flags = args
            write = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if write and not (isinstance(path, str) and path.lower() == os.devnull.lower()):
                require(mode == 'create' and isinstance(path, (str, bytes, os.PathLike)) and
                        os.fsdecode(path) in allowed and flags & os.O_EXCL and
                        flags & os.O_CREAT and not flags & (os.O_TRUNC | os.O_APPEND),
                        'File write outside the three exclusive approval destinations is blocked.')
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link',
                     'os.symlink', 'os.chmod', 'os.utime', 'os.truncate',
                     'subprocess.Popen', 'os.system', 'socket.connect'}:
            deny_external_access()
    sys.addaudithook(guard)


def prepare_modules(mode):
    require(os.name == 'nt' and Path.cwd() == REPO, 'Use the specified native Windows website repository.')
    safe_path(REPO, directory=True)
    require(sys.version_info[:2] == (3, 11), 'Existing website Python 3.11 is required.')
    require(Path(sys.executable) == REPO / '.venv/Scripts/python.exe', 'Unexpected Python interpreter.')
    # Cache the stdlib's read-only Windows version probe before blocking subprocesses.
    # SQLAlchemy asks platform.machine() at import; this otherwise invokes cmd /c ver.
    platform.uname()
    mutation_guard(mode)
    # Check exact framework/source evidence BEFORE importing trusted validators.
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Adopted repository evidence changed: ' + name)
    socket.create_connection = socket.socket.connect = socket.socket.connect_ex = deny_external_access
    import sqlalchemy
    import psycopg
    import keyring
    sqlalchemy.create_engine = sqlalchemy.engine.create_engine = deny_external_access
    psycopg.connect = psycopg.Connection.connect = deny_external_access
    keyring.get_password = keyring.set_password = keyring.delete_password = deny_external_access
    from oaf_website import database_config as db
    db._windows_password = deny_external_access
    from oaf_website import migration_authority as authority
    from oaf_website import migration_validation as validation
    from oaf_website.migration_config import IDENTITIES
    authority.issue_authorization = authority._publish_completion = deny_external_access
    authority.audit_destination = deny_external_access
    if mode != 'create':
        authority._save = deny_external_access
    return authority, validation, IDENTITIES


def audit_root():
    local = os.environ.get('LOCALAPPDATA')
    require(isinstance(local, str) and bool(local) and Path(local).is_absolute(),
            'LOCALAPPDATA must be absolute and available.')
    root = Path(local) / 'OAF Website/BootstrapAudit/MigrationAudit'
    require(root == AUDIT, 'Unexpected established MigrationAudit destination.')
    safe_path(root.parent, directory=True)
    safe_path(root, directory=True)
    return root  # No directory creation.


def common_checks(root, authority, validation, identities, saved=False):
    expected_names = set(SNAPSHOT['audit']) | (set(NEW_NAMES) if saved else set())
    require({p.name for p in root.iterdir()} == expected_names,
            'Audit inventory changed or target records already exist; stop without retry.')
    for name, expected in SNAPSHOT['audit'].items():
        require(byte_hash(root / name) == expected, 'Existing audit evidence changed: ' + name)
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Adopted repository evidence changed: ' + name)
    validation.validate_artifacts(**{key: SCOPE[key] for key in
        ('expected_start', 'target', 'manifest_hash', 'revision_hash')})
    require(authority._previous(root, 'testing') == PREDECESSOR, 'TESTING predecessor changed.')
    require(authority._ordinary_predecessor(root, 'testing', PREDECESSOR, SCOPE['expected_start']),
            'TESTING predecessor is incomplete, contradictory or requires reconciliation.')
    claim, _ = authority._read(root / 'claim-testing-00000002.json')
    require(claim['run_id'] == TESTING_RUN and claim['request'] == PRIOR_SCOPE,
            'Completed TESTING 0002 run binding differs.')
    # Validate 0002 against its OWN artifacts, never claim that it validates 0003.
    authority._testing_validation(root, PRIOR_SCOPE, TESTING_RUN)
    authorization, _ = authority._authorization(root, claim['authorization_id'])
    now = datetime.now(timezone.utc)
    for prefix, kind, reference, fields in (
        ('artifact-approval', 'artifact_approval', authorization['artifact_approval'],
         {'manifest_hash', 'revision_hash'}),
        ('prerequisite-approval', 'prerequisite_approval', authorization['prerequisite_approval'],
         {'environment', 'expected_start', 'approvals', 'predecessor',
          'owner_reconciliation', 'testing_validation_run'}),
    ):
        record = authority._reference(root, prefix, reference)
        authority._approval(record, kind, reference, fields, now)
        require(record['reviewer_id'] == REVIEWER, 'Established local reviewer reference differs.')
    require(authorization['artifact_approval']['id'] == OLD_ARTIFACT and
            authorization['prerequisite_approval']['id'] == OLD_APPROVAL,
            'Existing approval identities differ.')
    old, _ = authority._read(root / ('prerequisite-attestation-' + OLD_ATTESTATION + '.json'))
    previous, _ = authority._read(root / ('prerequisite-approval-' + OLD_APPROVAL + '.json'))
    require(old['id'] == OLD_ATTESTATION and old['kind'] == 'prerequisite_applicability_attestation'
            and old['decision'] == 'approved' and old['reviewer_id'] == REVIEWER
            and old['environment'] == 'testing' and set(old['categories']) == authority.PREREQUISITES
            and all(old[key] == PRIOR_SCOPE[key] for key in
                    ('expected_start', 'target', 'manifest_hash', 'revision_hash')),
            'Prior six-category TESTING evidence or identities differ.')
    require(previous['approvals'] == {key: OLD_ATTESTATION for key in authority.PREREQUISITES},
            'Prior category references differ.')
    identity = identities['testing']
    require((identity.database, identity.migrator, identity.owner, identity.runtime,
             identity.schema, identity.host, identity.port, identity.postgres_major) ==
            ('oaf_website_test', 'oaf_website_test_migrator', 'oaf_website_test_schema_owner',
             'oaf_website_test_app', 'oaf_website', '127.0.0.1', 5432, 17),
            'Fixed TESTING identity differs.')
    return now


def evidence_map():
    result = {}
    for name, digest in SNAPSHOT['repository'].items():
        result[name] = {'location': 'repository', 'hash_mode': 'exact_bytes', 'sha256': digest}
    for name, digest in SNAPSHOT['audit'].items():
        result['MigrationAudit/' + name] = {
            'location': 'MigrationAudit', 'hash_mode': 'exact_bytes', 'sha256': digest}
    result['owner_recording_instruction'] = {
        'location': 'embedded_owner_instruction', 'hash_mode': 'sha256-utf8-lf',
        'sha256': hashlib.sha256(OWNER_EVIDENCE.encode('utf-8')).hexdigest(),
        'content': OWNER_EVIDENCE,
        'source': 'Owner task instruction; selected statements, not a signed review report.',
    }
    return result


def categories():
    claim = 'MigrationAudit/claim-testing-00000002.json'
    terminal = 'MigrationAudit/terminal-' + TESTING_RUN + '.json'
    completed = 'MigrationAudit/completed-terminal-' + TESTING_RUN + '.json'
    def category(statement, references):
        return {'applicability': 'approved_for_exact_testing_transition',
                'adoption': 'administrative_owner_adoption_of_completed_revision_specific_evidence',
                'statement': statement, 'evidence': references + ['owner_recording_instruction']}
    return {
        'dependency_acceptance': category(
            'Owner adopts the completed 0003 source/offline dependency acceptance and PASS review '
            'for this exact TESTING transition. The accepted pinned toolchain, revision-specific '
            'notification/migration tests and governing source validation results are bound by exact bytes. '
            'No installation, dependency change, repeat review or compatibility experiment is performed. '
            'Completed TESTING 0002 is starting-state provenance; it is not live 0003 validation.',
            ['requirements.txt', 'requirements-migrations.txt', 'docs/WORKFLOW.md',
             'tests/test_notifications.py', 'tests/test_notification_migration.py']),
        'bootstrap_validation': category(
            'Owner adopts completed revision-specific bootstrap applicability evidence. Published '
            'completed TESTING 0002 and its exact sequence-2 claim prove ordinary continuation at '
            '0002_state_requests. The fixed database oaf_website_test, login oaf_website_test_migrator, '
            'effective/schema owner oaf_website_test_schema_owner, runtime oaf_website_test_app, '
            'schema oaf_website and PostgreSQL 17 at 127.0.0.1:5432 remain mandatory future runner checks. '
            'Database owner remains oaf_website_owner. No fresh live identity/ACL inspection is claimed.',
            [claim, terminal, completed, 'oaf_website/migration_config.py',
             'ops/local_postgres_bootstrap/01_roles.sql',
             'ops/local_postgres_bootstrap/03_test_schema.sql',
             'ops/local_postgres_bootstrap/04_verify.sql']),
        'lock_and_timeouts': category(
            'Owner adopts completed 0003 lock/timeout applicability review: the database-scoped '
            'session advisory lock (0x4F414657, 4), 5-second bounded acquisition/query timeout, '
            '5-second lock_timeout and 60-second statement_timeout remain required. The same backend '
            'and lock survival across setup rollback are checked; lock coverage spans commit and '
            'postcommit validation. Runner and Alembic recheck controls. Existing completed 0002 '
            'evidence records confirmed lock release. No new live 0003 contention/timeout test is claimed.',
            ['oaf_website/migrate.py', 'migrations/env.py', 'oaf_website/migration_validation.py',
             'tests/test_notification_migration.py', terminal, completed]),
        'search_path_and_postconditions': category(
            'Owner adopts completed exact-0003 schema/catalog/ACL review. Use pg_catalog, oaf_website, '
            'pg_temp and schema-qualified objects under the matching TESTING schema owner. Preserve '
            'exact 0001/0002 objects and advance exactly one version row from 0002 to 0003. Add only '
            'the manifest notifications inventory: table, notifications_pk primary key/index, '
            'notifications_active_email partial unique index, private row/array types, six named '
            'checks and created_at default, with exact definitions, ownership and dependency edges. '
            'Matching runtime grants are SELECT/INSERT on notifications and UPDATE solely on '
            'unsubscribed_at, without grant options. No other nonowner data privileges, PUBLIC '
            'schema/data exposure or runtime metadata access. Preserve restrictive defaults and '
            'the baseline generated-type exception solely for alembic_version/_alembic_version. '
            'Exact catalogs, constraints, index predicate, types, ACLs and dependencies must be checked '
            'before and after any separately authorized future commit. No live 0003 proof is claimed.',
            ['migrations/manifest.json', 'migrations/versions/0003_notifications.py', 'migrations/env.py',
             'oaf_website/migration_validation.py', 'oaf_website/notification_schema.py',
             'oaf_website/notification_validation.py', 'tests/test_notification_migration.py']),
        'recovery_procedure': category(
            'Owner adopts the completed revision-specific recovery review. Exact sequence-2 '
            'predecessor and published completed 0002 evidence support expected_start=0002_state_requests '
            'and owner_reconciliation=not_applicable. Preserve every claim and acknowledged commit; '
            'stop on uncertainty, incomplete/contradictory evidence or postcommit audit failure. '
            'Exceptional outcomes require exact-predecessor owner reconciliation. No blind retries, '
            'claim deletion, downgrade, stamp, repair or credential rotation. Live 0003 rollback and '
            'uncertain-result behavior remain for future separately authorized validation. Each future '
            'operation requires a distinct deliberate owner authorization; this checkpoint issues none.',
            [claim, terminal, completed, 'docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md',
             'oaf_website/migrate.py', 'oaf_website/migration_authority.py',
             'tests/test_notification_migration.py', 'tests/test_migration_operational.py']),
        'audit_policies': category(
            'Owner adopts completed 0003 applicability evidence for approved policies A-D: sanitized '
            'exclusive UTF-8/LF evidence in the existing MigrationAudit destination with flush/fsync, '
            'retention until separate archival approval, distinct bounded environment/artifact/'
            'prerequisite/predecessor-bound owner authorizations and fail-closed recovery. Published '
            'completion remains mandatory for authorization/terminal evidence. This checkpoint saves '
            'only three approval records exclusively, retains partial writes and never retries '
            'creation. Local UUIDs and hashes are administrative references, not signatures or proof '
            'of reviewer independence. The completed Astra PASS is owner-reported prior certification; '
            'owner adoption and recording are separate, and no new independent certification is performed.',
            ['docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migration_authority.py',
             'tests/test_migration_authorization.py', 'tests/test_migration_operational.py']),
    }


def build_records(approved_utc):
    common = {'format': 1, 'reviewer_id': REVIEWER, 'approved_utc': approved_utc, 'decision': 'approved'}
    artifact = dict(common, kind='artifact_approval', id=ARTIFACT_ID,
                    manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'])
    artifact_ref = {'id': ARTIFACT_ID, 'sha256': hashlib.sha256(encoded(artifact)).hexdigest()}
    prerequisite_common = dict(common, environment='testing', expected_start=SCOPE['expected_start'],
                               predecessor=PREDECESSOR, owner_reconciliation='not_applicable',
                               testing_validation_run=None)
    attestation = dict(prerequisite_common, kind='prerequisite_applicability_attestation',
        id=ATTESTATION_ID, action='upgrade', target=SCOPE['target'],
        manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'],
        artifact_approval_id=ARTIFACT_ID, artifact_approval=artifact_ref,
        prerequisite_approval_id=APPROVAL_ID, categories=categories(),
        revision_specific_evidence=evidence_map(),
        prior_completed_testing_run={'run_id': TESTING_RUN, 'request': PRIOR_SCOPE,
            'use': '0002_starting_state_and_existing_operational_provenance_only'},
        approval_identities={'artifact_approval_id': ARTIFACT_ID, 'attestation_id': ATTESTATION_ID,
            'prerequisite_approval_id': APPROVAL_ID, 'recorded_reviewer_reference': REVIEWER,
            'owner_adoption_authority': 'explicit_owner_approval_in_current_task',
            'prior_artifact_approval_id': OLD_ARTIFACT,
            'prior_attestation_id': OLD_ATTESTATION, 'prior_prerequisite_approval_id': OLD_APPROVAL},
        approval_basis={
            'authority': 'explicit_owner_approval_for_testing_0003_record_only_checkpoint',
            'administrative_adoption': 'Owner adopts completed revision-specific applicability evidence '
                'for all six categories and authorizes recording the previously passed exact-artifact review.',
            'independent_certification': {'reported_result': 'PASS', 'review': 'Independent Astra review',
                'source': 'owner_reported_completed_review_in_task',
                'performed_or_repeated_now': False},
            'approval_preparation': 'PASS as reported by owner',
            'material_defects_or_design_decisions': 'none as reported by owner',
            'reviewer_identity': 'established_local_reference_verified_against_existing_approvals',
            'assurance': 'Administrative owner adoption and recording, distinct from the completed '
                'independent reviewer certification. UUIDs/hashes provide no signature, cryptographic '
                'identity assurance or proof that a different human performed review.'},
        validation_boundary={
            'prior_0002_validation': 'published_completed_consistent_own_artifact_run',
            'live_0003_postgresql_validation': 'pending_separately_authorized_testing_execution',
            'development_0003_approval': 'not_issued',
            'independent_review_performed_now': False, 'broad_offline_suite_rerun_now': False,
            'migration_authorization_issued': False,
            'postgresql_or_credential_access_performed_now': False})
    prerequisite = dict(prerequisite_common, kind='prerequisite_approval', id=APPROVAL_ID,
                        approvals={key: ATTESTATION_ID for key in categories()})
    return artifact, attestation, prerequisite


def validate_documents(records, authority, now, claim_mtime):
    artifact, attestation, prerequisite = records
    ids = (ARTIFACT_ID, ATTESTATION_ID, APPROVAL_ID)
    require(len(set(ids)) == 3 and all(authority._uuid(value) for value in ids), 'Invalid record UUIDs.')
    approved_utc = artifact['approved_utc']
    require(records == build_records(approved_utc), 'Approval fields, identities or bound evidence differ.')
    require(authority._utc(approved_utc) <= now and
            authority._utc(approved_utc).timestamp() >= claim_mtime,
            'Approval time is future-dated or predates TESTING predecessor.')
    require(authority._utc(approved_utc) >= authority._utc(PREPARED_UTC),
            'Recording timestamp predates this preparation.')
    authority._approval(artifact, 'artifact_approval', {'id': ARTIFACT_ID},
                        {'manifest_hash', 'revision_hash'}, now)
    authority._approval(prerequisite, 'prerequisite_approval', {'id': APPROVAL_ID},
        {'environment', 'expected_start', 'approvals', 'predecessor',
         'owner_reconciliation', 'testing_validation_run'}, now)
    require(set(attestation['categories']) == authority.PREREQUISITES, 'Exactly six categories are required.')
    require(prerequisite['approvals'] == {key: ATTESTATION_ID for key in authority.PREREQUISITES},
            'All six categories must reference this exact 0003 attestation.')
    for category in attestation['categories'].values():
        require(category['applicability'] == 'approved_for_exact_testing_transition',
                'Wrong category applicability.')
        require(all(ref in attestation['revision_specific_evidence'] for ref in category['evidence']),
                'Unbound category evidence.')
    require(attestation['artifact_approval']['sha256'] == hashlib.sha256(encoded(artifact)).hexdigest(),
            'Attestation artifact approval byte binding differs.')
    for record in records:
        require(len(encoded(record)) <= 64000, 'Record exceeds the Stage 5 read limit.')


def print_results(root, records, saved=False, verified=False):
    labels = ('Artifact approval', 'Attestation', 'Prerequisite approval')
    for label, name, record in zip(labels, NEW_NAMES, records):
        print(label + ' UUID: ' + record['id'])
        print(label + ' path: ' + str(root / name))
        digest = byte_hash(root / name) if saved else hashlib.sha256(encoded(record)).hexdigest()
        print(label + (' SHA-256 (exact bytes): ' if saved else ' preview SHA-256 (UNSAVED): ') + digest)
        print(label + (' actual recording UTC: ' if saved else ' preview UTC (UNSAVED): ') + record['approved_utc'])
        print(label + (' saved JSON:' if saved else ' prepared JSON (UNSAVED):'))
        print(encoded(record).decode('utf-8'), end='')
    print('Transition: TESTING 0002_state_requests -> 0003_notifications (upgrade)')
    print('Manifest normalized SHA-256: ' + SCOPE['manifest_hash'])
    print('Revision 0003 normalized SHA-256: ' + SCOPE['revision_hash'])
    print('Predecessor: sequence=2 sha256=' + PREDECESSOR['sha256'])
    print('Prior completed TESTING 0002 run: ' + TESTING_RUN + '; starting-state provenance only.')
    print('Established local reviewer reference: ' + REVIEWER)
    print('Categories: ' + ', '.join(sorted(records[1]['categories'])))
    print('owner_reconciliation=not_applicable; TESTING testing_validation_run=null')
    print('Owner adoption: administrative; independent Astra PASS: previously completed, owner-reported.')
    print('Saved-record verification: ' + ('PASS in a separate read-only Python process.' if verified else
          ('PENDING separate read-only process.' if saved else 'not applicable; records UNSAVED.')))
    print('No migration authorization, credentials, PostgreSQL or Git mutation performed.')


def main(mode):
    authority, validation, identities = prepare_modules(mode)
    root = audit_root()
    now = common_checks(root, authority, validation, identities, saved=(mode == 'verify'))
    claim_mtime = (root / 'claim-testing-00000002.json').stat().st_mtime
    if mode == 'inspect':
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        print('Read-only artifact, predecessor, evidence, format and six-category preflight: PASS.')
        print_results(root, records)
        print('Records remain UNSAVED until the owner runs this script without -ValidateOnly.')
    elif mode == 'create':
        # All checks precede creation; timestamps are actual UTC at the save checkpoint.
        common_checks(root, authority, validation, identities, saved=False)
        now = datetime.now(timezone.utc)
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        for name, record in zip(NEW_NAMES, records):
            path = root / name
            # Existing Stage 5 exclusive UTF-8/LF writer, flush, fsync, close.
            authority._save(path, record)
            require(path.read_bytes() == encoded(record), 'Saved approval bytes differ; stop without retry.')
            print('Exclusively saved: ' + name)
        common_checks(root, authority, validation, identities, saved=True)
        print_results(root, records, saved=True)
    elif mode == 'verify':
        records = tuple(authority._read(root / name)[0] for name in NEW_NAMES)
        validate_documents(records, authority, now, claim_mtime)
        for name, record in zip(NEW_NAMES, records):
            require((root / name).read_bytes() == encoded(record), 'Saved UTF-8/LF bytes differ.')
        artifact_ref = {'id': ARTIFACT_ID, 'sha256': byte_hash(root / NEW_NAMES[0])}
        prerequisite_ref = {'id': APPROVAL_ID, 'sha256': byte_hash(root / NEW_NAMES[2])}
        require(records[1]['artifact_approval'] == artifact_ref, 'Saved artifact reference differs.')
        authority._approvals(root, SCOPE, artifact_ref, prerequisite_ref, PREDECESSOR, now)
        common_checks(root, authority, validation, identities, saved=True)
        print_results(root, records, saved=True, verified=True)
        print('Record-only checkpoint: PASS. Exactly three records saved; all previous evidence preserved.')
    else:
        raise RuntimeError('Unsupported bounded mode.')


try:
    require(len(sys.argv) == 2 and sys.argv[1] in {'inspect', 'create', 'verify'}, 'Expected one bounded mode.')
    main(sys.argv[1])
except BaseException as error:
    classification = getattr(error, 'classification', None)
    detail = classification if classification else (
        str(error) if type(error) is RuntimeError else type(error).__name__)
    print('BLOCKED: ' + detail)
    print('Stop. Preserve any existing/partial records. Never rerun creation after an uncertain outcome.')
    raise SystemExit(2)
'@

function Invoke-TaskPython([string]$Mode) {
    $taskPythonCode | & $taskPython -B - $Mode 2>&1 | ForEach-Object { Write-TaskLine ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw ('Record-only ' + $Mode + ' failed; stop without retry.') }
}

try {
    Write-TaskLine 'OAF WEBSITE - TESTING 0003 APPROVAL RECORDING'
    Write-TaskLine ('Started UTC: ' + [DateTime]::UtcNow.ToString('o'))
    Write-TaskLine 'Scope: current OAF Website repository; exactly three external MigrationAudit approval records.'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use native Windows PowerShell 5.1.'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows is required.' }
    # ValidateOnly performs no profile execution, clipboard operation or visual UI.
    if (-not $ValidateOnly) { Initialize-TaskUI }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -cne $taskRoot) { throw 'Run from the specified OAF Website repository.' }
    if ([IO.Path]::GetFullPath($PSScriptRoot) -cne (Join-Path $taskRoot 'ops')) { throw 'Unexpected script location.' }
    if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Existing website interpreter is unavailable.' }
    if (-not $env:LOCALAPPDATA -or -not [IO.Path]::IsPathRooted($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is unavailable.' }
    $taskAudit = Join-Path $env:LOCALAPPDATA 'OAF Website\BootstrapAudit\MigrationAudit'
    $taskPaths = @(
        (Join-Path $taskAudit ('artifact-approval-' + $taskArtifactId + '.json')),
        (Join-Path $taskAudit ('prerequisite-attestation-' + $taskAttestationId + '.json')),
        (Join-Path $taskAudit ('prerequisite-approval-' + $taskApprovalId + '.json'))
    )
    if (-not (Test-Path -LiteralPath $taskAudit -PathType Container)) { throw 'Existing MigrationAudit is unavailable.' }
    if ($VerifyOnly) {
        Invoke-TaskPython 'verify'
    } else {
        Invoke-TaskPython 'inspect'
        if (-not $ValidateOnly) {
            Invoke-TaskPython 'create'
            Invoke-TaskPython 'verify'
        }
    }
    if (-not $ValidateOnly) {
        # Native PowerShell rehashes each saved file independently of Python.
        $taskLabels = @('Artifact approval', 'Attestation', 'Prerequisite approval')
        for ($taskIndex = 0; $taskIndex -lt $taskPaths.Count; $taskIndex++) {
            $taskHash = (Get-FileHash -LiteralPath $taskPaths[$taskIndex] -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not ($taskLines -contains ($taskLabels[$taskIndex] + ' SHA-256 (exact bytes): ' + $taskHash))) {
                throw 'PowerShell and Python saved-record exact-byte hashes disagree.'
            }
            Write-TaskLine ($taskLabels[$taskIndex] + ' native PowerShell exact-byte SHA-256 PASS: ' + $taskHash)
        }
        $taskRecordsVerified = $true
    }
    $taskExitCode = 0
    Write-TaskLine $(if ($ValidateOnly) { 'READ-ONLY PREFLIGHT: PASS; all three records remain UNSAVED.' }
                    else { 'SAVED-RECORD VALIDATION: PASS; three records independently verified.' })
} catch {
    Write-TaskLine ('RESULT: BLOCKED - ' + $_.Exception.Message)
    $taskExitCode = 2
    Write-TaskLine 'Stop without retry. Preserve existing records and partial writes.'
    foreach ($taskPath in $taskPaths) {
        Write-TaskLine ('Target path: ' + $taskPath)
        try {
            if (Test-Path -LiteralPath $taskPath -PathType Leaf) {
                Write-TaskLine ('Retained bytes SHA-256 (not approval verification): ' +
                    (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant())
            } else { Write-TaskLine 'Target record: ABSENT' }
        } catch { Write-TaskLine 'Target record outcome: UNCERTAIN; inspect read-only before further action.' }
    }
} finally {
    Write-TaskLine ('Finished UTC: ' + [DateTime]::UtcNow.ToString('o'))
    if (-not $ValidateOnly) {
        Write-TaskLine $(if ($taskRecordsVerified) { 'Record status: SAVED and independently verified.' }
                        else { 'Record status: NOT CONFIRMED; retain any partial records and inspect read-only.' })
        Write-TaskLine 'Report: complete terminal output is copied to the clipboard; existing OAF green/red alert follows.'
        try {
            $taskFullReport = $taskLines -join [Environment]::NewLine
            Set-Clipboard -Value $taskFullReport
            if ((Get-Clipboard -Raw).TrimEnd() -cne $taskFullReport.TrimEnd()) { throw 'Clipboard verification failed.' }
        } catch {
            $taskExitCode = 2
            Write-TaskLine 'RESULT: BLOCKED - clipboard publication failed; complete report remains in the terminal.'
            # No automatic retries, including publication.
        }
        if ($taskAlertReady) {
            try {
                $taskAlertStatus = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
                $taskAlertMessage = if ($taskExitCode -eq 0) {
                    'PASS. Three approval records saved and verified. Full JSON, UUIDs, timestamps, hashes and paths are in the terminal and clipboard.'
                } else {
                    'BLOCKED. Stop without retry; retain partial records. Check the complete terminal report and clipboard.'
                }
                Show-OAFPowerShellAlert -Status $taskAlertStatus -Title 'OAF TESTING 0003 APPROVALS' -Message $taskAlertMessage
            } catch {
                $taskExitCode = 2
                Write-TaskLine 'RESULT: BLOCKED - existing OAF visual alert invocation failed.'
            }
        } else {
            $taskExitCode = 2
            Write-TaskLine 'RESULT: BLOCKED - existing OAF visual alert is unavailable.'
        }
    }
}

# Invoke with &; exit is confined to the owner-launched native PowerShell process.
exit $taskExitCode

