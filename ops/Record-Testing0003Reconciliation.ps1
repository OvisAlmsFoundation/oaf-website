# Windows PowerShell 5.1; owner-approved TESTING claim 3 reconciliation/reapproval.
# Exactly three approval records. No authorization issuance or database access.
[CmdletBinding(DefaultParameterSetName = 'Record')]
param(
    [Parameter(ParameterSetName = 'Validate')][switch]$ValidateOnly,
    [Parameter(ParameterSetName = 'Verify')][switch]$VerifyOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskArtifactId = '32b1bf6f-39f7-47d9-b098-e470c39c384b'
$taskAttestationId = '512c06c5-d958-4c3a-87e8-41a9418852d7'
$taskApprovalId = '5ab2c84c-fd51-4c6a-966a-ef4019488c1d'
$taskLines = New-Object 'System.Collections.Generic.List[string]'
$taskExitCode = 2
$taskAlertReady = $false
$taskRecordsVerified = $false
$taskPaths = @()

function Write-TaskLine([string]$Text) {
    $taskLines.Add($Text)
    Write-Host $Text
}

function Initialize-TaskUI {
    # Extract only the existing alert function; never execute unrelated profile code.
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
    if ($taskAlertDefinitions.Count -ne 1) { throw 'Expected one existing OAF visual alert function.' }
    . ([ScriptBlock]::Create($taskAlertDefinitions[0].Extent.Text))
    Set-Item -Path Function:script:Show-OAFPowerShellAlert -Value (Get-Item Function:Show-OAFPowerShellAlert).ScriptBlock
    $script:taskAlertReady = $true
    if (-not (Get-Command Set-Clipboard -ErrorAction SilentlyContinue) -or
        -not (Get-Command Get-Clipboard -ErrorAction SilentlyContinue)) { throw 'Existing clipboard support is unavailable.' }
}

# ASCII stdin avoids Windows native -c quoting. Each mode has a fresh process.
$taskPythonCode = @'
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import platform
import socket
import sys

REPO = Path(r'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website')
AUDIT = Path(r'C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit\MigrationAudit')
ARTIFACT_ID = '32b1bf6f-39f7-47d9-b098-e470c39c384b'
ATTESTATION_ID = '512c06c5-d958-4c3a-87e8-41a9418852d7'
APPROVAL_ID = '5ab2c84c-fd51-4c6a-966a-ef4019488c1d'
REVIEWER = '01ed5b95-c24e-402e-a547-c24447303ed5'
FAILED_RUN = '2ef06612-7b7d-4be0-af95-d9cf9d48f378'
FAILED_AUTHORIZATION = '86d2ea44-8136-4bef-b818-6971d022410c'
OLD_ARTIFACT = '6ddae102-027c-4ef3-8041-fdb499ca1b32'
OLD_ATTESTATION = 'eddbe068-234b-43b5-b08f-c8e7cc3c7681'
OLD_APPROVAL = '27286b07-9855-40ed-889f-f9913d910af6'
PREPARED_UTC = '2026-10-12T03:24:21.762097+00:00'
PREDECESSOR = {'sequence': 3,
    'sha256': '487d63542090eae32cb26e0ecf33f1d9657320cf33c5bc7cbab091e895fe1730'}
SCOPE = {'action': 'upgrade', 'environment': 'testing',
    'expected_start': '0002_state_requests', 'target': '0003_notifications',
    'manifest_hash': 'e85d1951fb6ea2fd46ed6ab116460c9033637acc66127cacb330233d907868db',
    'revision_hash': '1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452'}
OLD_SCOPE = dict(SCOPE, manifest_hash='5aa7ef4b007282e8d543fed090471fd181368be1ad6d600469c440fbbf5929de')
SCHEMA_HASH = '8609e44436663db7d7a99ec7964ebaec4658b0491412d366b17f4d7850bd77e4'
OLD_SCHEMA_HASH = '765e295c8b579b5441829fcf944f3bb92c2d13d92cb5d510ee4667e8bd6baa44'
CHANGED = {'migrations/manifest.json', 'oaf_website/notification_schema.py',
           'tests/test_notification_migration.py'}
SNAPSHOT = {
    "audit": {
        "artifact-approval-6ddae102-027c-4ef3-8041-fdb499ca1b32.json": "3cdcd7ed687885d8af5e6beda238466c3eab84d1ae7940e804d910cdb7559668",
        "artifact-approval-75755e44-1423-4ffb-8b67-8ebb1a205072.json": "30293bcce535ddee16f8cc4e5d39bff25bebcef4aabaffb6233b30c366a17b01",
        "artifact-approval-b0d4b5a9-3b86-46d3-9e7e-67268a2f3897.json": "4ed6a218b8c4eda2f1e6b5b25a9df9025c3b0025efe48d34d2d3f40f15337e11",
        "authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "6bf6d5b0e282e6ca95a31a389908f897057a5e1cb253ee20fb762e13449607e7",
        "authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "d7a5eeb67b0e9e70a3c16bf58ef830479dc3dd6fdf30b2e06f2e9e00c20b6fb2",
        "authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "c43d5eacbf1d8d78a9ac5b178a8b4d4aff766bb05a7ec7544c1aa5ac0ab78621",
        "authorization-86d2ea44-8136-4bef-b818-6971d022410c.json": "514bace5ead17fe3a3ab44ef055ecf0af07067f0ca929e3b2ab1926eeb84943b",
        "authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "7b51d8a86fe6d82863bd86a7450d9063ccd302b18d10c858fb91432fed4db101",
        "claim-development-00000001.json": "207d41a387a793d5fea113dd2f020de12493d482d8556ae88e3c9f71c3db38db",
        "claim-development-00000002.json": "64d28271fc319552e51e85a06809089559b5dfb42f039f654c85ba925ede8b93",
        "claim-testing-00000001.json": "642c6452a0b2ad6068a2d00534977985d2d081cd787a30489e9772b13075728c",
        "claim-testing-00000002.json": "09a2149025e903a403baac9b89a9e34aaf2a2aa0b6fd1818f83db8d7301166df",
        "claim-testing-00000003.json": "487d63542090eae32cb26e0ecf33f1d9657320cf33c5bc7cbab091e895fe1730",
        "completed-authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "cb3d08d15a917aa9040f0806fc965feb7049b0bdd2e31a7e60927af08d9e9b39",
        "completed-authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "a05817e9e23b8fe02d440781560a9150d1bf9685c30c1b0772dc444494dbab7e",
        "completed-authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "aae5c4b471b4fd1eb01713f996e73007a5209e225f5c7c2432db31c425baa5f7",
        "completed-authorization-86d2ea44-8136-4bef-b818-6971d022410c.json": "c0a3a042ad4b83a257e4400879d39fcf237f37e0988bebd6c2eefb8410522b44",
        "completed-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "completed-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "completed-terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "872311fc6dc0062618c10683857c09562ac3778acb3c0640c8ec1bca11df0ae7",
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
        "event-2ef06612-7b7d-4be0-af95-d9cf9d48f378-00000001.json": "2c1ce7c32face115b7d47e15b663dc3fe53a514030c1e44fab5c1b3b1c0e23ea",
        "event-2ef06612-7b7d-4be0-af95-d9cf9d48f378-00000002.json": "b2023c71137e6d8bfa3174d32b2d1832a142c044208936b83c16725c2a352976",
        "event-2ef06612-7b7d-4be0-af95-d9cf9d48f378-00000003.json": "187b1f8b64355acef90a807ef6b5dba295ec169b4f03c51a2757393eebe7898b",
        "event-2ef06612-7b7d-4be0-af95-d9cf9d48f378-00000004.json": "b67a9279e681d9c7de38597e0034281d0d57db8f5cec27ce8a4f66697fb24be2",
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
        "pending-authorization-86d2ea44-8136-4bef-b818-6971d022410c.json": "c0a3a042ad4b83a257e4400879d39fcf237f37e0988bebd6c2eefb8410522b44",
        "pending-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "pending-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "pending-terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "872311fc6dc0062618c10683857c09562ac3778acb3c0640c8ec1bca11df0ae7",
        "pending-terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "f17b38bb9a2240131843c52f4f8624ad1aad192a34341aad8e86bd59fa7fc020",
        "pending-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "pending-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "prerequisite-approval-27286b07-9855-40ed-889f-f9913d910af6.json": "141e3d88b5953f84d547375ca4bbb7048d896b2de8eaeea88d8bc585382f7fff",
        "prerequisite-approval-2c42eb66-2155-4762-8692-a7170512ae3d.json": "6a95a3a8ec1effc8d28524ad0d61338c042bc49a67dd4a93431d4cfa99e1fba2",
        "prerequisite-approval-55fd6fee-b2b2-40fb-bab0-a0c87c35462a.json": "ce89b823c83246e1f464883b6e4123e2cb1989e6a382f8d3192d2b7928090833",
        "prerequisite-approval-853a9204-da09-405a-856f-2725eb541657.json": "b45db8f2c870d462615a51fcefb829f8defe25298c7a11cefa8e2524c0a1551c",
        "prerequisite-approval-fa98f647-7757-45a5-9634-37322383237e.json": "1f3f0bac8e9dd28aa90c84bdcf610761aa59a7ed38f8d85d7895bed9f50f6e6e",
        "prerequisite-attestation-8b388045-48f2-4e32-bd5d-6756ee004791.json": "1b70ad606db4b5fd2146a4e50d100d341e0483afafe0d292b227459cbc9deef1",
        "prerequisite-attestation-eddbe068-234b-43b5-b08f-c8e7cc3c7681.json": "4c2807137a1e83cc336073c81410fab4af4019c8286a7a3c3e1b24aa07217e7c",
        "prerequisite-attestation-fe53d5d1-8e82-409e-a8ee-265d18f95d31.json": "9e994e1d27ebec0d35796c24885aa633c973afb2b6844bf6260dfe18f5e7c19f",
        "terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "c7c4296c78437b63063d0489ee7c672ab14ee3a76783ec233063a6678a264311",
        "terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "6928c7e34207d0556c71066fd2b76b2fdf8234d6b71db507cb284578b2c2923e",
        "terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "b62546bb5bf1d5dce47c5abdc6dfd3039cefa591f5993fb027160b62fc74ef6a",
        "terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "3bd8e351c6e70a667c9fe430367ca064f14b503112027291b4ec47d2a6b42a27",
        "terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "e3114c601e7d8aa0cc0ff65664c32eedf4322dbc2b5be593fabdbf6763421a04"
    },
    "repository": {
        "alembic.ini": "c72a8cc54828755974765ab8df60c03744cd448b7d16bed81b1157569548f736",
        "docs/WEBSITE_PLAN.md": "1d639ced0cf70d3338e644aca536b037918481773e7e0a831b1f5a8daf6cd161",
        "docs/WORKFLOW.md": "a5e7381f2887b30478e110ffc393705efe1e205cb9142de229955759e73e6250",
        "migrations/env.py": "09fcd94121f9ba0287d33d9b779f2b7845be56f23fea23aaafb5ae891fe661d4",
        "migrations/manifest.json": "6b803dc0a581b66161a9ba4f9c473cc7958d1903c80a54943d78b5dabb4ac9a7",
        "migrations/script.py.mako": "ed31327e01d48ec1ba1e91f5dc5b347fed7e9a8c9733b50d49c8085e86815bdc",
        "migrations/versions/0001_migration_baseline.py": "bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3",
        "migrations/versions/0002_state_requests.py": "c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad",
        "migrations/versions/0003_notifications.py": "1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452",
        "oaf_website/__init__.py": "ad4cfd8e9137a2e69abe6fdad18114a9918fccf918cbe59e181a9edd78436eb5",
        "oaf_website/database_config.py": "bffc9d41024c7d562944d67c55cff254e63c0f5c83f54ec4b2384c64ab51ed60",
        "oaf_website/migrate.py": "706a6fefaca086f43bd2729c1cafefdb5bfe3bbd2f71e7a404e2e922454ae1e0",
        "oaf_website/migration_authority.py": "7654a552106b7ef3ec5827decf0ea9f61b317b2265c4364a0d5d7278549da6ce",
        "oaf_website/migration_config.py": "9c537cceaed6c84b3050f4db0a2510e6588e4259e927b35322e86cab91ab3587",
        "oaf_website/migration_validation.py": "a5ef986aae4515d0f39c416dad812a0479c094b9d5b81a37c04d298f88b05b23",
        "oaf_website/notification_schema.py": "8609e44436663db7d7a99ec7964ebaec4658b0491412d366b17f4d7850bd77e4",
        "oaf_website/notification_validation.py": "939200c718fa5131427315ce6b7f10ebe4177653c7744d54c3e593d263a26267",
        "oaf_website/state_request_schema.py": "440924c43651c6b7d1e5c8745de705dd0ceeb589eb10422e805131ede51f9647",
        "oaf_website/state_request_validation.py": "a04e8a50bf353dd1de03a3f310445adb9392a33d0ae8c441ebd877d03d32db5d",
        "ops/Record-Testing0003Approvals.ps1": "558a7b85712162f859970da0dbb2f4d764cb6363ad46ef9d0a42b00783be5db3",
        "ops/local_postgres_bootstrap/01_roles.sql": "cf314c1c946564282262564befb6831b49289f4280352d998a4da7bc7f0f0c3b",
        "ops/local_postgres_bootstrap/03_test_schema.sql": "e980a521e24d5b9f3c2642268029cd19a9156e9068243987fac6238fe687d7e2",
        "ops/local_postgres_bootstrap/04_verify.sql": "848220a0bd24a4a8c1ee24aeb315728fba92ea23b0c309dbe47580e7af57427d",
        "requirements-migrations.txt": "3154eef6a20748636332276d9a39e13b1d03585df55ab681b706362d294de33e",
        "requirements.txt": "3f8e4f324231e88e0c7a9e1be05c9a26be0a1d5628a5b9947b2ee7794b96fb9d",
        "tests/migration_offline.py": "9bff47388ffd364704f251b8643edd7fdfe56d9b76681ffa2639422ffa8e1fd7",
        "tests/test_migration_artifacts.py": "480d3488fa45ee9f9352c4f1d4e72c55e9ff3023ff46afe1c35b94dba558bdbf",
        "tests/test_migration_authorization.py": "075a1091b6d212d047ced023b21a350930f9cb87154f913258b291eae0df50a0",
        "tests/test_migration_operational.py": "bbde79df63f41b2be68fa100c6f1a138d3865c567f4f5e078e1b26fdf2c5e3a8",
        "tests/test_notification_migration.py": "9ce566f96139a71ad6f8b71570c0fb6e5359ac2d1015b5dfe8af0a4ddb0955c1",
        "tests/test_notifications.py": "61c13313be8394601eacf189458358d85e4fab5a66d515550e9512e75c3cc50c"
    }
}
NEW_NAMES = ('artifact-approval-' + ARTIFACT_ID + '.json',
             'prerequisite-attestation-' + ATTESTATION_ID + '.json',
             'prerequisite-approval-' + APPROVAL_ID + '.json')
OWNER_EVIDENCE = (
    'OWNER APPROVAL: GRANTED.\n'
    'OBJECTIVE: Complete formal reconciliation of failed TESTING claim 3 and record '
    'three fresh approvals for the corrected 0003_notifications migration artifacts.\n'
    'Failed run: 2ef06612-7b7d-4be0-af95-d9cf9d48f378.\n'
    'Failed claim: claim-testing-00000003.json.\n'
    'Exact-byte claim SHA-256: 487d63542090eae32cb26e0ecf33f1d9657320cf33c5bc7cbab091e895fe1730.\n'
    'Failure: precommit / drift_detected. Database commit: never invoked. '
    'Transaction rollback: confirmed. Audit completion: confirmed. Recovery lock release: confirmed.\n'
    'Owner pgAdmin verification: PASS. Owner native locked exact-catalog verification: PASS.\n'
    'TESTING revision: 0002_state_requests. Notifications table: absent. '
    'Schema, ownership, permissions and dependencies: PASS. '
    'No database modifications during reconciliation checks.\n'
    'Manifest normalized SHA-256: e85d1951fb6ea2fd46ed6ab116460c9033637acc66127cacb330233d907868db.\n'
    'Revision 0003 normalized SHA-256, unchanged: '
    '1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452.\n'
    'Notification schema normalized SHA-256: '
    '8609e44436663db7d7a99ec7964ebaec4658b0491412d366b17f4d7850bd77e4.\n'
    'Validated bounded correction: PostgreSQL lifecycle conkey corrected from [8,9] to [9,8]. '
    'Independent PostgreSQL-order test fixture added. '
    '260 focused tests and 949 regression tests passed. Revisions 0001, 0002 and 0003 unchanged.\n'
    'Established local reviewer reference: 01ed5b95-c24e-402e-a547-c24447303ed5.\n'
    'Represent owner_reconciliation=completed in the required governing records. '
    'testing_validation_run=null. Distinguish owner adoption from independent certification. '
    'Do not invent new independent review evidence.\n'
    'No migration execution/retry, authorization issuance, PostgreSQL modifications, credential '
    'or role changes, alteration/deletion of existing audit records, Git staging/commits/pushes, '
    'broad reviews/completed test reruns, or approved migration source modifications.\n'
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def deny_external_access(*args, **kwargs):
    raise RuntimeError('Credential, database, network, migration or authorization access blocked.')


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
    allowed = {str(AUDIT / name) for name in NEW_NAMES}
    def guard(event, args):
        if event == 'open':
            path, _, flags = args
            write = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if write and not (isinstance(path, str) and path.lower() == os.devnull.lower()):
                require(mode == 'create' and isinstance(path, (str, bytes, os.PathLike)) and
                        os.fsdecode(path) in allowed and flags & os.O_EXCL and
                        flags & os.O_CREAT and not flags & (os.O_TRUNC | os.O_APPEND),
                        'Only three exact exclusive approval destinations may be written.')
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link',
                     'os.symlink', 'os.chmod', 'os.utime', 'os.truncate',
                     'subprocess.Popen', 'os.system', 'socket.connect', 'socket.getaddrinfo'}:
            deny_external_access()
    sys.addaudithook(guard)


def prepare_modules(mode):
    require(os.name == 'nt' and Path.cwd() == REPO, 'Use the specified native Windows repository.')
    safe_path(REPO, directory=True)
    require(sys.version_info[:2] == (3, 11), 'Existing website Python 3.11 is required.')
    require(Path(sys.executable) == REPO / '.venv/Scripts/python.exe', 'Unexpected interpreter.')
    # Cache the stdlib Windows version probe before blocking subprocesses.
    platform.uname()
    mutation_guard(mode)
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Repository evidence changed: ' + name)
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
    return root


def preserved_checks(root, present=()):
    require({p.name for p in root.iterdir()} == set(SNAPSHOT['audit']) | set(present),
            'Audit inventory changed or targets exist; stop without retry.')
    for name, expected in SNAPSHOT['audit'].items():
        require(byte_hash(root / name) == expected, 'Retained audit bytes changed: ' + name)
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Bound source bytes changed: ' + name)


def common_checks(root, authority, validation, identities, saved=False):
    preserved_checks(root, NEW_NAMES if saved else ())
    validation.validate_artifacts(**{key: SCOPE[key] for key in
        ('expected_start', 'target', 'manifest_hash', 'revision_hash')})
    require(validation.digest((REPO / 'oaf_website/notification_schema.py').read_bytes()) == SCHEMA_HASH,
            'Corrected notification schema normalized hash differs.')
    schema_bytes = (REPO / 'oaf_website/notification_schema.py').read_bytes()
    corrected_key = b'"notifications_lifecycle_check": [9, 8]'
    require(schema_bytes.count(corrected_key) == 1 and validation.digest(schema_bytes.replace(
            corrected_key, b'"notifications_lifecycle_check": [8, 9]')) == OLD_SCHEMA_HASH,
            'Schema correction exceeds the approved lifecycle conkey change.')
    # Conkey order also determines the four lifecycle dependency entries in the manifest.
    manifest_bytes = (REPO / 'migrations/manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes, object_pairs_hook=authority._unique)
    require(validation.digest((json.dumps(manifest, indent=2) + '\n').encode('utf-8')) ==
            SCOPE['manifest_hash'], 'Manifest canonical serialization differs.')
    manifest['framework']['oaf_website/notification_schema.py'] = OLD_SCHEMA_HASH
    edges = manifest['security']['dependencies']['notification_edges']
    indices = [index for index, edge in enumerate(edges)
               if edge[0] == 'notification_notifications_lifecycle_check']
    require([edges[index][3:] for index in indices] == [[9, 'a'], [9, 'n'], [8, 'a'], [8, 'n']],
            'Corrected lifecycle dependency order differs.')
    for index, old_column in zip(indices, (8, 8, 9, 9)):
        edges[index][3] = old_column
    require(validation.digest((json.dumps(manifest, indent=2) + '\n').encode('utf-8')) ==
            OLD_SCOPE['manifest_hash'], 'Manifest correction exceeds schema hash and derived lifecycle edge order.')
    require(authority._previous(root, 'testing') == PREDECESSOR, 'Exact TESTING predecessor changed.')
    claim_path = root / 'claim-testing-00000003.json'
    claim, claim_hash = authority._read(claim_path)
    require(set(claim) == {'format', 'kind', 'utc', 'authorization_id', 'authorization_sha256',
                           'run_id', 'request', 'predecessor', 'recovery'} and
            type(claim['format']) is int and claim['format'] == 1 and
            claim['kind'] == 'authorization_claimed' and claim_hash == PREDECESSOR['sha256'] and
            claim['run_id'] == FAILED_RUN and claim['authorization_id'] == FAILED_AUTHORIZATION and
            claim['request'] == OLD_SCOPE and claim['recovery'] ==
            'classify_completed_evidence_or_require_owner_reconciliation', 'Failed claim binding differs.')
    prior_claim, prior_hash = authority._read(root / 'claim-testing-00000002.json')
    require(claim['predecessor'] == {'sequence': 2, 'sha256': prior_hash},
            'Failed claim predecessor chain differs.')
    authorization, authorization_hash = authority._authorization(root, FAILED_AUTHORIZATION)
    issued, expires = authority._utc(authorization['issued_utc']), authority._utc(authorization['expires_utc'])
    require(issued <= authority._utc(claim['utc']) < expires <= issued + timedelta(hours=24) and
            claim['authorization_sha256'] == authorization_hash, 'Retained authorization binding differs.')
    authority._approvals(root, OLD_SCOPE, authorization['artifact_approval'],
                        authorization['prerequisite_approval'], claim['predecessor'], issued)
    event, history = authority._completed_run(root, claim_path)
    require(all(event[key] == OLD_SCOPE[key] for key in OLD_SCOPE) and event['run_id'] == FAILED_RUN,
            'Failed completed run scope differs.')
    require(event['outcome'] == 'failed' and event['failure'] == 'drift_detected' and
            event['failed_phase'] == 'precommit' and event['commit_certainty'] == 'not_invoked' and
            event['database_commit_confirmed'] is False and event['mutation_started'] is True and
            event['transaction_outcome'] == 'rollback_confirmed' and
            event['lock_outcome'] == 'release_confirmed' and
            event['audit_write_outcome'] == 'confirmed_successful' and
            event['observed_start'] == SCOPE['expected_start'] and event['verified_identity'] is True and
            event['secondary_failures'] == [] and event['validation_outcome'] == 'failed' and
            event['interruption_phase'] is None and
            all(event['cleanup'][key] == 'confirmed_successful' for key in
                ('rollback', 'advisory_unlock', 'connection_close', 'engine_dispose')) and
            [item['phase'] for item in history] == ['authorization', 'lock', 'preflight', 'revision'],
            'Retained failure, rollback, audit completion or recovery evidence differs.')
    require(authority._continuation_state(event, history) is None and not
            authority._ordinary_predecessor(root, 'testing', PREDECESSOR, SCOPE['expected_start']),
            'Exceptional reconciliation classification differs.')
    # The completion record acknowledges finalization; the terminal describes its attempt.
    terminal = root / ('terminal-' + FAILED_RUN + '.json')
    require(terminal.with_name('completed-' + terminal.name).samefile(
            terminal.with_name('pending-' + terminal.name)), 'Retained terminal publication differs.')
    prior_event, prior_history = authority._completed_run(root, root / 'claim-testing-00000002.json')
    require(authority._continuation_state(prior_event, prior_history) == SCOPE['expected_start'] and
            prior_event['run_id'] == prior_claim['run_id'], 'Historical 0002 provenance differs.')
    # Do not call _testing_validation for historical 0002: exceptional claim 3 invalidated it.
    require(authorization['artifact_approval']['id'] == OLD_ARTIFACT and
            authorization['prerequisite_approval']['id'] == OLD_APPROVAL, 'Prior approval IDs differ.')
    old, _ = authority._read(root / ('prerequisite-attestation-' + OLD_ATTESTATION + '.json'))
    previous, _ = authority._read(root / ('prerequisite-approval-' + OLD_APPROVAL + '.json'))
    artifact = authority._reference(root, 'artifact-approval', authorization['artifact_approval'])
    require(all(record['reviewer_id'] == REVIEWER for record in (old, previous, artifact)) and
            old['id'] == OLD_ATTESTATION and old['kind'] == 'prerequisite_applicability_attestation' and
            old['format'] == 1 and old['decision'] == 'approved' and
            all(old[key] == OLD_SCOPE[key] for key in OLD_SCOPE) and
            old['predecessor'] == claim['predecessor'] and old['owner_reconciliation'] == 'not_applicable' and
            old['testing_validation_run'] is None and old['artifact_approval'] == authorization['artifact_approval'] and
            old['prerequisite_approval_id'] == OLD_APPROVAL and
            set(old['categories']) == authority.PREREQUISITES and
            previous['approvals'] == {key: OLD_ATTESTATION for key in authority.PREREQUISITES},
            'Established reviewer or prior six-category evidence differs.')
    now = datetime.now(timezone.utc)
    require(authority._utc(old['approved_utc']) <= issued <= now, 'Retained approval time differs.')
    changed = set()
    for name, ref in old['revision_specific_evidence'].items():
        if ref['location'] == 'repository':
            require(name in SNAPSHOT['repository'], 'Prior source binding missing from current snapshot.')
            if ref['sha256'] != SNAPSHOT['repository'][name]:
                changed.add(name)
        elif ref['location'] == 'MigrationAudit':
            require(SNAPSHOT['audit'][name.removeprefix('MigrationAudit/')] == ref['sha256'],
                    'Prior retained evidence binding differs.')
    require(changed == CHANGED, 'Source change exceeds the three bounded corrected bindings.')
    identity = identities['testing']
    require((identity.database, identity.migrator, identity.owner, identity.runtime,
             identity.schema, identity.host, identity.port, identity.postgres_major) ==
            ('oaf_website_test', 'oaf_website_test_migrator', 'oaf_website_test_schema_owner',
             'oaf_website_test_app', 'oaf_website', '127.0.0.1', 5432, 17), 'Fixed TESTING identity differs.')
    preserved_checks(root, NEW_NAMES if saved else ())
    return now


def evidence_map():
    result = {name: {'location': 'repository', 'hash_mode': 'exact_bytes', 'sha256': digest}
              for name, digest in SNAPSHOT['repository'].items()}
    result.update({'MigrationAudit/' + name:
        {'location': 'MigrationAudit', 'hash_mode': 'exact_bytes', 'sha256': digest}
        for name, digest in SNAPSHOT['audit'].items()})
    result['owner_recording_instruction'] = {
        'location': 'embedded_owner_instruction', 'hash_mode': 'sha256-utf8-lf',
        'sha256': hashlib.sha256(OWNER_EVIDENCE.encode('utf-8')).hexdigest(),
        'content': OWNER_EVIDENCE,
        'source': 'Selected statements from the current owner task; administrative attestation, not a signed report.'}
    return result


def categories():
    prior = 'MigrationAudit/prerequisite-attestation-' + OLD_ATTESTATION + '.json'
    failed = ['MigrationAudit/claim-testing-00000003.json',
              'MigrationAudit/terminal-' + FAILED_RUN + '.json',
              'MigrationAudit/completed-terminal-' + FAILED_RUN + '.json']
    def category(statement, references):
        return {'applicability': 'approved_for_exact_testing_transition',
                'adoption': 'administrative_owner_adoption_of_completed_revision_specific_evidence',
                'statement': statement,
                'evidence': references + [prior, 'owner_recording_instruction']}
    return {
        'dependency_acceptance': category(
            'Carry forward the accepted pinned toolchain and applicable dependency review from the retained '
            '0003 attestation. Owner adopts the bounded lifecycle conkey correction [8,9] -> [9,8] and '
            'independent PostgreSQL-order fixture for the corrected hashes. The owner reports 260 focused '
            'and 949 regression tests passed; these results are not rerun or independently certified here. '
            'No dependency installation or change. Prior independent review is historical for prior bytes.',
            ['requirements.txt', 'requirements-migrations.txt', 'tests/test_notification_migration.py',
             'oaf_website/notification_schema.py', 'migrations/manifest.json']),
        'bootstrap_validation': category(
            'Carry forward the fixed TESTING identity and applicable bootstrap evidence. The owner reports '
            'completed pgAdmin and native locked exact-catalog PASS after failed claim 3: revision '
            '0002_state_requests, notifications absent, schema/ownership/permissions/dependencies PASS, '
            'with no database modifications. Adopt that verified starting state under the approved recovery '
            'procedure. Historical completed 0002 supports provenance only; claim 3 is the governing predecessor. '
            'Database oaf_website_test, migrator oaf_website_test_migrator, schema owner '
            'oaf_website_test_schema_owner, runtime oaf_website_test_app, schema oaf_website and '
            'PostgreSQL 17 at 127.0.0.1:5432 remain fixed; database owner remains oaf_website_owner.',
            failed + ['oaf_website/migration_config.py', 'ops/local_postgres_bootstrap/01_roles.sql',
                      'ops/local_postgres_bootstrap/03_test_schema.sql', 'ops/local_postgres_bootstrap/04_verify.sql']),
        'lock_and_timeouts': category(
            'Carry forward the approved database-scoped session advisory lock (0x4F414657,4), '
            '5-second bounded acquisition/query timeout, 5-second lock_timeout and 60-second '
            'statement_timeout. Same-backend lock survival across setup rollback and coverage through '
            'commit/postcommit validation remain required. Retained failed-run evidence confirms lock release; '
            'the owner reports native locked recovery verification PASS. No fresh database checks here.',
            failed + ['oaf_website/migrate.py', 'migrations/env.py', 'oaf_website/migration_validation.py']),
        'search_path_and_postconditions': category(
            'Refresh exact-catalog bindings to the corrected manifest/schema and independent PostgreSQL-order '
            'fixture. notifications_lifecycle_check conkey is [9,8]; revisions 0001/0002/0003 are unchanged. '
            'Adopt owner-reported locked exact-catalog PASS at 0002 with notifications absent. Preserve '
            'pg_catalog,oaf_website,pg_temp and schema-qualified objects. Future exact 0003 checks retain '
            'notifications table, PK/index, active-email partial unique index, private row/array types, '
            'six checks, created_at default, exact ownership/ACL/dependencies, SELECT/INSERT and UPDATE '
            'only on unsubscribed_at, no grant options, restrictive defaults and only the existing '
            'alembic_version generated-type exception. Target 0003 live validation remains pending.',
            ['migrations/manifest.json', 'migrations/versions/0001_migration_baseline.py',
             'migrations/versions/0002_state_requests.py', 'migrations/versions/0003_notifications.py',
             'oaf_website/notification_schema.py', 'oaf_website/notification_validation.py',
             'oaf_website/migration_validation.py', 'migrations/env.py', 'tests/test_notification_migration.py']),
        'recovery_procedure': category(
            'Refresh the Stage 5 exceptional reconciliation binding to exact failed sequence 3 and its raw '
            'claim hash. Published failure remains precommit/drift_detected: commit never invoked, '
            'rollback confirmed, completion published and lock released. This remains an exceptional '
            'outcome despite safe cleanup. Owner adopts completed pgAdmin/native locked exact-catalog '
            'verification at 0002 and formally attests owner_reconciliation=completed in this attestation '
            'and the fresh prerequisite approval. Preserve failure and every prior record. No separate '
            'reconciliation record, retry, stamp, repair, downgrade, role or credential change. '
            'A distinct deliberate owner authorization is still the next checkpoint.',
            failed + ['docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migration_authority.py',
                      'oaf_website/migrate.py', 'tests/test_migration_operational.py']),
        'audit_policies': category(
            'Carry forward approved policies A-D: sanitized exclusive UTF-8/LF writes with flush/fsync, '
            'retention, distinct bounded environment/artifact/prerequisite/predecessor-bound owner '
            'authorizations, published completion for issuance/finalization, and fail-closed recovery. '
            'Exactly three fresh records are permitted and all prior bytes are checked and preserved. '
            'Stop on a mismatch or partial/uncertain outcome; never retry creation. Owner administrative '
            'adoption is separate from prior independent certification. No new independent review '
            'evidence or authorization is created; UUIDs and hashes are local references, not signatures.',
            ['docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migration_authority.py',
             'tests/test_migration_authorization.py', 'tests/test_migration_operational.py']),
    }


def build_records(approved_utc):
    common = {'format': 1, 'reviewer_id': REVIEWER, 'approved_utc': approved_utc, 'decision': 'approved'}
    artifact = dict(common, kind='artifact_approval', id=ARTIFACT_ID,
                    manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'])
    artifact_ref = {'id': ARTIFACT_ID, 'sha256': hashlib.sha256(encoded(artifact)).hexdigest()}
    prerequisite_common = dict(common, environment='testing', expected_start=SCOPE['expected_start'],
        predecessor=PREDECESSOR, owner_reconciliation='completed', testing_validation_run=None)
    # Existing exact Stage 5 schemas deliberately have no extra scope fields.
    prerequisite = dict(prerequisite_common, kind='prerequisite_approval', id=APPROVAL_ID,
                        approvals={key: ATTESTATION_ID for key in categories()})
    prerequisite_ref = {'id': APPROVAL_ID, 'sha256': hashlib.sha256(encoded(prerequisite)).hexdigest()}
    attestation = dict(prerequisite_common, kind='prerequisite_applicability_attestation',
        id=ATTESTATION_ID, action=SCOPE['action'], target=SCOPE['target'],
        manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'],
        notification_schema_hash=SCHEMA_HASH, artifact_approval_id=ARTIFACT_ID,
        artifact_approval=artifact_ref, prerequisite_approval_id=APPROVAL_ID,
        prerequisite_approval=prerequisite_ref, categories=categories(),
        revision_specific_evidence=evidence_map(),
        approval_identities={'artifact_approval_id': ARTIFACT_ID, 'attestation_id': ATTESTATION_ID,
            'prerequisite_approval_id': APPROVAL_ID, 'recorded_reviewer_reference': REVIEWER,
            'prior_artifact_approval_id': OLD_ARTIFACT, 'prior_attestation_id': OLD_ATTESTATION,
            'prior_prerequisite_approval_id': OLD_APPROVAL},
        approval_basis={
            'authority': 'explicit_owner_approval_for_corrected_0003_reconciliation_and_reapproval',
            'administrative_adoption': 'Owner approves corrected artifacts and adopts applicable prior '
                'six-category evidence with refreshed changed-artifact, catalog and exceptional recovery bindings.',
            'independent_certification': {
                'prior_evidence': 'MigrationAudit/prerequisite-attestation-' + OLD_ATTESTATION + '.json',
                'status': 'historical_owner_reported_PASS_for_prior_artifacts_only',
                'corrected_artifact_independent_certification_claimed': False,
                'new_independent_evidence_created': False, 'performed_or_repeated_now': False},
            'assurance': 'Owner adoption, distinct from independent certification. Established reviewer '
                'UUID and exact-byte hashes do not provide signatures or reviewer independence.'},
        exceptional_reconciliation={
            'representation': 'existing_prerequisite_approval_and_six_category_attestation',
            'owner_reconciliation': 'completed', 'predecessor': PREDECESSOR,
            'failed_run_id': FAILED_RUN, 'failed_authorization_id': FAILED_AUTHORIZATION,
            'retained_outcome': 'failed', 'failure': 'drift_detected', 'failed_phase': 'precommit',
            'commit_certainty': 'not_invoked', 'transaction_outcome': 'rollback_confirmed',
            'audit_completion': 'published_completed_exact_claim_and_event_bytes',
            'recovery_lock_release': 'confirmed',
            'verified_database_state': {'environment': 'testing', 'revision': SCOPE['expected_start'],
                'notifications_table': 'absent', 'schema_ownership_permissions_dependencies': 'PASS',
                'owner_pgadmin_verification': 'PASS', 'owner_native_locked_exact_catalog_verification': 'PASS',
                'database_modifications_during_verification': False,
                'source': 'owner_reported_completed_verification_in_current_task',
                'verification_timestamp': None,
                'verification_timestamp_basis': 'not_supplied_by_owner; no timestamp inferred'},
            'adopted_recording_utc': approved_utc,
            'owner_evidence_reference': 'owner_recording_instruction'},
        bounded_correction={'lifecycle_conkey_before': [8, 9], 'lifecycle_conkey_after': [9, 8],
            'manifest_change': 'notification_schema framework digest and derived lifecycle dependency edge order only',
            'independent_postgresql_order_fixture': 'tests/test_notification_migration.py',
            'changed_bound_source_files': sorted(CHANGED), 'revisions_0001_0002_0003': 'unchanged',
            'reported_tests': {'focused_passed': 260, 'regression_passed': 949,
                               'source': 'owner_reported_completed_runs', 'rerun_now': False}},
        carried_forward_evidence={
            'prior_attestation': {'id': OLD_ATTESTATION,
                'sha256': SNAPSHOT['audit']['prerequisite-attestation-' + OLD_ATTESTATION + '.json']},
            'categories': sorted(categories()),
            'use': 'applicable_dependency_timeout_recovery_and_audit_policy_evidence; '
                   'changed_artifact_catalog_and_exceptional_bindings_refreshed'},
        validation_boundary={'testing_validation_run': None,
            'historical_0002_success': 'provenance_only; exceptional_claim_3_invalidates_prior_testing_citation',
            'live_corrected_0003_validation': 'pending_separately_authorized_testing_operation',
            'independent_review_performed_now': False, 'broad_offline_suite_rerun_now': False,
            'migration_authorization_issued': False, 'postgresql_or_credential_access_performed_now': False,
            'development_approval_issued': False})
    return artifact, attestation, prerequisite


def validate_documents(records, authority, now, claim_mtime):
    artifact, attestation, prerequisite = records
    ids = (ARTIFACT_ID, ATTESTATION_ID, APPROVAL_ID)
    require(len(set(ids)) == 3 and all(authority._uuid(value) for value in ids), 'Invalid fresh UUIDs.')
    for identifier in ids:
        require(not any(identifier in name for name in SNAPSHOT['audit']), 'UUID already exists in audit history.')
    approved = authority._utc(artifact['approved_utc'])
    require(approved <= now and approved.timestamp() >= claim_mtime and
            approved >= authority._utc(PREPARED_UTC), 'Approval UTC is stale or future-dated.')
    require(records == build_records(artifact['approved_utc']), 'Record fields or adopted bindings differ.')
    authority._approval(artifact, 'artifact_approval', {'id': ARTIFACT_ID},
                        {'manifest_hash', 'revision_hash'}, now)
    authority._approval(prerequisite, 'prerequisite_approval', {'id': APPROVAL_ID},
        {'environment', 'expected_start', 'approvals', 'predecessor',
         'owner_reconciliation', 'testing_validation_run'}, now)
    require(set(attestation['categories']) == authority.PREREQUISITES and
            prerequisite['approvals'] == {key: ATTESTATION_ID for key in authority.PREREQUISITES},
            'Exactly six categories must reference the fresh attestation.')
    for category in attestation['categories'].values():
        require(category['applicability'] == 'approved_for_exact_testing_transition' and
                all(ref in attestation['revision_specific_evidence'] for ref in category['evidence']),
                'Unbound category applicability or evidence.')
    for record in (attestation, prerequisite):
        require(record['predecessor'] == PREDECESSOR and record['owner_reconciliation'] == 'completed'
                and record['testing_validation_run'] is None, 'Exceptional reconciliation binding differs.')
    for reference, record in ((attestation['artifact_approval'], artifact),
                              (attestation['prerequisite_approval'], prerequisite)):
        require(reference == {'id': record['id'], 'sha256': hashlib.sha256(encoded(record)).hexdigest()},
                'Fresh approval reference exact-byte binding differs.')
    for record in records:
        require(len(encoded(record)) <= 64000, 'Record exceeds the Stage 5 read limit.')


def validate_saved(root, records, authority, now, claim_mtime):
    validate_documents(records, authority, now, claim_mtime)
    references = []
    for name, record in zip(NEW_NAMES, records):
        require((root / name).read_bytes() == encoded(record), 'Saved UTF-8/LF bytes differ.')
        references.append({'id': record['id'], 'sha256': byte_hash(root / name)})
    require(records[1]['artifact_approval'] == references[0] and
            records[1]['prerequisite_approval'] == references[2], 'Saved record cross-binding differs.')
    authority._approvals(root, SCOPE, references[0], references[2], PREDECESSOR, now)


def print_results(root, records, saved=False):
    for label, name, record in zip(('Artifact approval', 'Attestation', 'Prerequisite approval'), NEW_NAMES, records):
        print(label + ' UUID: ' + record['id'])
        print(label + ' path: ' + str(root / name))
        if saved:
            print(label + ' SHA-256 (exact bytes): ' + byte_hash(root / name))
        print(label + (' saved UTC: ' if saved else ' preview UTC (UNSAVED): ') + record['approved_utc'])
    print('Binding: testing / upgrade / 0002_state_requests -> 0003_notifications')
    print('Predecessor: sequence=3 sha256=' + PREDECESSOR['sha256'])
    print('owner_reconciliation=completed; testing_validation_run=null')
    print('Established local reviewer: ' + REVIEWER + '; owner adoption; no new independent certification.')
    print('All previous audit bytes and approved migration source bytes: preserved.')
    print('Next single authorization checkpoint: distinct owner-issued TESTING upgrade authorization '
          'bound to these saved approvals, corrected artifact hashes and exact claim 3.')


def main(mode):
    authority, validation, identities = prepare_modules(mode)
    root = audit_root()
    now = common_checks(root, authority, validation, identities, saved=(mode == 'verify'))
    claim_mtime = (root / 'claim-testing-00000003.json').stat().st_mtime
    if mode == 'inspect':
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        print('Prerequisite, corrected artifact, failed completion and Stage 5 document checks: PASS.')
        print('Fresh record byte lengths: ' + ', '.join(str(len(encoded(record))) for record in records))
        print_results(root, records)
        print('PASS / PREPARED ONLY; exactly three records UNSAVED.')
    elif mode == 'create':
        # Timestamp is actual UTC at the recording checkpoint, after prerequisites pass.
        now = datetime.now(timezone.utc)
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        for index, (name, record) in enumerate(zip(NEW_NAMES, records)):
            preserved_checks(root, NEW_NAMES[:index])
            require(authority._previous(root, 'testing') == PREDECESSOR, 'Predecessor advanced during recording.')
            authority._save(root / name, record)  # Existing exclusive UTF-8/LF writer; flush/fsync/close.
            require((root / name).read_bytes() == encoded(record), 'Saved bytes differ; stop without retry.')
            print('Exclusively saved: ' + name)
        now = common_checks(root, authority, validation, identities, saved=True)
        validate_saved(root, records, authority, now, claim_mtime)
        print_results(root, records, saved=True)
        print('SAVED; independent read-only process verification still required.')
    elif mode == 'verify':
        records = tuple(authority._read(root / name)[0] for name in NEW_NAMES)
        validate_saved(root, records, authority, now, claim_mtime)
        common_checks(root, authority, validation, identities, saved=True)
        print_results(root, records, saved=True)
        print('PASS / SAVED; exactly three records independently verified with Stage 5 validators.')
    else:
        raise RuntimeError('Unsupported bounded mode.')


try:
    require(len(sys.argv) == 2 and sys.argv[1] in {'inspect', 'create', 'verify'}, 'Expected one bounded mode.')
    main(sys.argv[1])
except BaseException as error:
    classification = getattr(error, 'classification', None)
    detail = classification if classification else (str(error) if type(error) is RuntimeError else type(error).__name__)
    print('BLOCKED: ' + detail)
    print('Stop. Preserve every existing/partial record. Do not rerun creation after partial or uncertain outcomes.')
    raise SystemExit(2)
'@

function Invoke-TaskPython([string]$Mode) {
    $taskPythonCode | & $taskPython -B - $Mode 2>&1 | ForEach-Object { Write-TaskLine ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw ('Record-only ' + $Mode + ' failed; stop without retry.') }
}

try {
    Write-TaskLine 'OAF WEBSITE - TESTING CLAIM 3 RECONCILIATION AND REAPPROVAL'
    Write-TaskLine ('Started UTC: ' + [DateTime]::UtcNow.ToString('o'))
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {
        throw 'Use native Windows PowerShell 5.1.'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows is required.' }
    # ValidateOnly is entirely read-only, including no clipboard or visual UI.
    if (-not $ValidateOnly) { Initialize-TaskUI }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -cne $taskRoot) { throw 'Run from the specified repository.' }
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
        # Independently rehash saved bytes using native PowerShell.
        $taskLabels = @('Artifact approval', 'Attestation', 'Prerequisite approval')
        for ($taskIndex = 0; $taskIndex -lt $taskPaths.Count; $taskIndex++) {
            $taskHash = (Get-FileHash -LiteralPath $taskPaths[$taskIndex] -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not ($taskLines -contains ($taskLabels[$taskIndex] + ' SHA-256 (exact bytes): ' + $taskHash))) {
                throw 'Native PowerShell and Python exact-byte hashes disagree.'
            }
            Write-TaskLine ($taskLabels[$taskIndex] + ' native exact-byte verification: PASS')
        }
        $taskRecordsVerified = $true
    }
    $taskExitCode = 0
    Write-TaskLine $(if ($ValidateOnly) { 'RESULT: PASS / PREPARED ONLY; records UNSAVED.' }
                    else { 'RESULT: PASS / SAVED; exactly three records independently verified.' })
} catch {
    Write-TaskLine ('RESULT: BLOCKED - ' + $_.Exception.Message)
    $taskExitCode = 2
    Write-TaskLine 'Stop without retry. Preserve every existing record and partial write.'
    foreach ($taskPath in $taskPaths) {
        Write-TaskLine ('Target path: ' + $taskPath)
        try {
            if (Test-Path -LiteralPath $taskPath -PathType Leaf) {
                Write-TaskLine ('Retained exact-byte SHA-256 (not verified approval): ' +
                    (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant())
            } else { Write-TaskLine 'Target record: ABSENT' }
        } catch { Write-TaskLine 'Target outcome: UNCERTAIN; inspect read-only before further action.' }
    }
} finally {
    Write-TaskLine ('Finished UTC: ' + [DateTime]::UtcNow.ToString('o'))
    if (-not $ValidateOnly) {
        Write-TaskLine $(if ($taskRecordsVerified) { 'Record status: SAVED and independently verified.' }
                        else { 'Record status: NOT CONFIRMED; retain partial records and inspect read-only.' })
        # Invoke the existing green/red alert first so its failure also appears in the clipboard report.
        if ($taskAlertReady) {
            try {
                $taskAlertStatus = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
                $taskAlertMessage = if ($taskExitCode -eq 0) {
                    'PASS. Three fresh approvals saved and verified. Claim 3 reconciled. Report and hashes are in the terminal; clipboard copy follows.'
                } else { 'BLOCKED. Stop without retry; retain partial records. Read the terminal report; clipboard copy follows.' }
                Show-OAFPowerShellAlert -Status $taskAlertStatus -Title 'OAF TESTING 0003 RECONCILIATION' -Message $taskAlertMessage
            } catch {
                $taskExitCode = 2
                Write-TaskLine 'RESULT: BLOCKED - existing OAF visual alert invocation failed.'
            }
        } else {
            $taskExitCode = 2
            Write-TaskLine 'RESULT: BLOCKED - existing OAF visual alert unavailable.'
        }
        Write-TaskLine $(if ($taskExitCode -eq 0) { 'FINAL RESULT: PASS / SAVED.' }
                        else { 'FINAL RESULT: BLOCKED; record status as stated above.' })
        try {
            $taskFullReport = $taskLines -join [Environment]::NewLine
            Set-Clipboard -Value $taskFullReport
            if ((Get-Clipboard -Raw).TrimEnd() -cne $taskFullReport.TrimEnd()) { throw 'Clipboard verification failed.' }
        } catch {
            $taskExitCode = 2
            Write-TaskLine 'RESULT: BLOCKED - clipboard publication failed; report remains in the terminal.'
            if ($taskAlertReady) {
                try {
                    Show-OAFPowerShellAlert -Status 'failure' -Title 'OAF TESTING 0003 REPORT BLOCKED' -Message 'Clipboard report failed. Keep terminal output. Do not rerun recording.'
                } catch { Write-TaskLine 'Existing red alert invocation failed.' }
            }
        }
    }
}

# Run with & in a separate native PowerShell process; exit stays in that process.
exit $taskExitCode
