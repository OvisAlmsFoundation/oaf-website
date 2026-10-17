# Windows PowerShell 5.1. Owner-approved DEVELOPMENT record-only checkpoint.
# Exactly two new prerequisite records; existing corrected artifact approval reused.
[CmdletBinding(DefaultParameterSetName = 'Record')]
param(
    [Parameter(ParameterSetName = 'Validate')][switch]$ValidateOnly,
    [Parameter(ParameterSetName = 'Verify')][switch]$VerifyOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskRoot = 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskAttestationId = 'f3b7a1f2-6d38-4f02-8050-b658b53a9b45'
$taskApprovalId = '0483e311-c76d-426c-a492-09d423f49314'
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
    # Load only the existing alert definition; never execute unrelated profile code.
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

# ASCII stdin avoids Windows native -c quoting. Every mode uses a fresh process.
$taskPythonCode = @'
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys

REPO = Path(r'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website')
AUDIT = Path(r'C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit\MigrationAudit')
SCRIPT_NAME = 'ops/Record-Development0003Prerequisites.ps1'
ATTESTATION_ID = 'f3b7a1f2-6d38-4f02-8050-b658b53a9b45'
APPROVAL_ID = '0483e311-c76d-426c-a492-09d423f49314'
REVIEWER = '01ed5b95-c24e-402e-a547-c24447303ed5'
TESTING_RUN = '51415d12-dbd1-4b69-8234-1c532c0bbee8'
TESTING_ATTESTATION = '512c06c5-d958-4c3a-87e8-41a9418852d7'
TESTING_APPROVAL = '5ab2c84c-fd51-4c6a-966a-ef4019488c1d'
DEVELOPMENT_RUN = '545553f6-0367-4116-89dd-eb3945fd38ce'
ARTIFACT_REF = {'id': '32b1bf6f-39f7-47d9-b098-e470c39c384b',
                'sha256': '2489196206ec85785aa326f19f6238bb05731b6523d3afa141fe998ea5aedf2b'}
PREDECESSOR = {'sequence': 2,
               'sha256': '64d28271fc319552e51e85a06809089559b5dfb42f039f654c85ba925ede8b93'}
SCOPE = {'action': 'upgrade', 'environment': 'development',
         'expected_start': '0002_state_requests', 'target': '0003_notifications',
         'manifest_hash': 'e85d1951fb6ea2fd46ed6ab116460c9033637acc66127cacb330233d907868db',
         'revision_hash': '1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452'}
SNAPSHOT = {
    "audit": {
        "artifact-approval-32b1bf6f-39f7-47d9-b098-e470c39c384b.json": "2489196206ec85785aa326f19f6238bb05731b6523d3afa141fe998ea5aedf2b",
        "artifact-approval-6ddae102-027c-4ef3-8041-fdb499ca1b32.json": "3cdcd7ed687885d8af5e6beda238466c3eab84d1ae7940e804d910cdb7559668",
        "artifact-approval-75755e44-1423-4ffb-8b67-8ebb1a205072.json": "30293bcce535ddee16f8cc4e5d39bff25bebcef4aabaffb6233b30c366a17b01",
        "artifact-approval-b0d4b5a9-3b86-46d3-9e7e-67268a2f3897.json": "4ed6a218b8c4eda2f1e6b5b25a9df9025c3b0025efe48d34d2d3f40f15337e11",
        "authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "6bf6d5b0e282e6ca95a31a389908f897057a5e1cb253ee20fb762e13449607e7",
        "authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "d7a5eeb67b0e9e70a3c16bf58ef830479dc3dd6fdf30b2e06f2e9e00c20b6fb2",
        "authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "c43d5eacbf1d8d78a9ac5b178a8b4d4aff766bb05a7ec7544c1aa5ac0ab78621",
        "authorization-86d2ea44-8136-4bef-b818-6971d022410c.json": "514bace5ead17fe3a3ab44ef055ecf0af07067f0ca929e3b2ab1926eeb84943b",
        "authorization-d41cffd6-683a-4b06-8910-4a155376a2b0.json": "b4bcbca12712f22e75a8dff11312aa6f41233127a005219e17e4557a6629dba7",
        "authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "7b51d8a86fe6d82863bd86a7450d9063ccd302b18d10c858fb91432fed4db101",
        "claim-development-00000001.json": "207d41a387a793d5fea113dd2f020de12493d482d8556ae88e3c9f71c3db38db",
        "claim-development-00000002.json": "64d28271fc319552e51e85a06809089559b5dfb42f039f654c85ba925ede8b93",
        "claim-testing-00000001.json": "642c6452a0b2ad6068a2d00534977985d2d081cd787a30489e9772b13075728c",
        "claim-testing-00000002.json": "09a2149025e903a403baac9b89a9e34aaf2a2aa0b6fd1818f83db8d7301166df",
        "claim-testing-00000003.json": "487d63542090eae32cb26e0ecf33f1d9657320cf33c5bc7cbab091e895fe1730",
        "claim-testing-00000004.json": "c3d173ca573199816d0133fde86c528829bf02b361a044eebd739261d48c1eb1",
        "completed-authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "cb3d08d15a917aa9040f0806fc965feb7049b0bdd2e31a7e60927af08d9e9b39",
        "completed-authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "a05817e9e23b8fe02d440781560a9150d1bf9685c30c1b0772dc444494dbab7e",
        "completed-authorization-5eda74a5-3257-4bae-bfbf-304587a151b7.json": "aae5c4b471b4fd1eb01713f996e73007a5209e225f5c7c2432db31c425baa5f7",
        "completed-authorization-86d2ea44-8136-4bef-b818-6971d022410c.json": "c0a3a042ad4b83a257e4400879d39fcf237f37e0988bebd6c2eefb8410522b44",
        "completed-authorization-d41cffd6-683a-4b06-8910-4a155376a2b0.json": "af8f0896ff4f5e5f695d4580eedbc0352631e1180cfd5f4985f3d71654b79c93",
        "completed-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "completed-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "completed-terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "872311fc6dc0062618c10683857c09562ac3778acb3c0640c8ec1bca11df0ae7",
        "completed-terminal-51415d12-dbd1-4b69-8234-1c532c0bbee8.json": "39e098c69e0514ad1b4c65360f5574acec30d8dda8eadb16e7128eaa962f1e09",
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
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000001.json": "c1330b20b68b8dcd31250066dcc8e028c1642e7d47adf74eeea3ab2982207f71",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000002.json": "95617dd63159080cebca4e5c39ec4520c3d2d88c3850f65865a6eb3bc848b2db",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000003.json": "68ffe424fb1a66e0ca8b4688889d0a16f46bca2ace709b55139f6620e54cf5e0",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000004.json": "7b0871942f1848a6d5fac6aa4bbd855fd6869fd7897680144f220494c6711055",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000005.json": "aee64edb1b0c318bebd7051f2862f44f37a72632c7e52dddd32755d7e4e34625",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000006.json": "682ce03a5ee4051c72ea9ccf903edf88c72cd99db2ac8adde35f8f349b93e356",
        "event-51415d12-dbd1-4b69-8234-1c532c0bbee8-00000007.json": "afd7c0a500c8fae90d9a8ce17442e2fc735d306d35c925f9977d97fed1485c5d",
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
        "pending-authorization-d41cffd6-683a-4b06-8910-4a155376a2b0.json": "af8f0896ff4f5e5f695d4580eedbc0352631e1180cfd5f4985f3d71654b79c93",
        "pending-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "pending-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "pending-terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "872311fc6dc0062618c10683857c09562ac3778acb3c0640c8ec1bca11df0ae7",
        "pending-terminal-51415d12-dbd1-4b69-8234-1c532c0bbee8.json": "39e098c69e0514ad1b4c65360f5574acec30d8dda8eadb16e7128eaa962f1e09",
        "pending-terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "f17b38bb9a2240131843c52f4f8624ad1aad192a34341aad8e86bd59fa7fc020",
        "pending-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "pending-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "prerequisite-approval-27286b07-9855-40ed-889f-f9913d910af6.json": "141e3d88b5953f84d547375ca4bbb7048d896b2de8eaeea88d8bc585382f7fff",
        "prerequisite-approval-2c42eb66-2155-4762-8692-a7170512ae3d.json": "6a95a3a8ec1effc8d28524ad0d61338c042bc49a67dd4a93431d4cfa99e1fba2",
        "prerequisite-approval-55fd6fee-b2b2-40fb-bab0-a0c87c35462a.json": "ce89b823c83246e1f464883b6e4123e2cb1989e6a382f8d3192d2b7928090833",
        "prerequisite-approval-5ab2c84c-fd51-4c6a-966a-ef4019488c1d.json": "f52e6a0d19c8b1ef074cf2de91836bb477d102256b558fa47c428f3cb0fff29f",
        "prerequisite-approval-853a9204-da09-405a-856f-2725eb541657.json": "b45db8f2c870d462615a51fcefb829f8defe25298c7a11cefa8e2524c0a1551c",
        "prerequisite-approval-fa98f647-7757-45a5-9634-37322383237e.json": "1f3f0bac8e9dd28aa90c84bdcf610761aa59a7ed38f8d85d7895bed9f50f6e6e",
        "prerequisite-attestation-512c06c5-d958-4c3a-87e8-41a9418852d7.json": "22d72bfb04c83da3ee07b4415df9ec02b67546b5196c548dd8b52c421f828321",
        "prerequisite-attestation-8b388045-48f2-4e32-bd5d-6756ee004791.json": "1b70ad606db4b5fd2146a4e50d100d341e0483afafe0d292b227459cbc9deef1",
        "prerequisite-attestation-eddbe068-234b-43b5-b08f-c8e7cc3c7681.json": "4c2807137a1e83cc336073c81410fab4af4019c8286a7a3c3e1b24aa07217e7c",
        "prerequisite-attestation-fe53d5d1-8e82-409e-a8ee-265d18f95d31.json": "9e994e1d27ebec0d35796c24885aa633c973afb2b6844bf6260dfe18f5e7c19f",
        "terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "c7c4296c78437b63063d0489ee7c672ab14ee3a76783ec233063a6678a264311",
        "terminal-2ef06612-7b7d-4be0-af95-d9cf9d48f378.json": "6928c7e34207d0556c71066fd2b76b2fdf8234d6b71db507cb284578b2c2923e",
        "terminal-51415d12-dbd1-4b69-8234-1c532c0bbee8.json": "90f3be4c1c940450b4ee6025454e99913409b77a8030c0abe172437ee42f20d0",
        "terminal-545553f6-0367-4116-89dd-eb3945fd38ce.json": "b62546bb5bf1d5dce47c5abdc6dfd3039cefa591f5993fb027160b62fc74ef6a",
        "terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "3bd8e351c6e70a667c9fe430367ca064f14b503112027291b4ec47d2a6b42a27",
        "terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "e3114c601e7d8aa0cc0ff65664c32eedf4322dbc2b5be593fabdbf6763421a04"
    },
    "inventory": {
        "branch": "main",
        "files": [
            ".gitignore",
            ".vscode/settings.json",
            ".vscode/tasks.json",
            "README.md",
            "about.html",
            "alembic.ini",
            "assets/images/gramanna-logo.png",
            "assets/images/hero-gifts.webp",
            "assets/notifications.js",
            "assets/state-requests.js",
            "config/database.example.toml",
            "docs/WEBSITE_PLAN.md",
            "docs/WORKFLOW.md",
            "gramanna.html",
            "index.html",
            "migrations/env.py",
            "migrations/manifest.json",
            "migrations/script.py.mako",
            "migrations/versions/0001_migration_baseline.py",
            "migrations/versions/0002_state_requests.py",
            "migrations/versions/0003_notifications.py",
            "oaf_website/__init__.py",
            "oaf_website/database_config.py",
            "oaf_website/local_development.py",
            "oaf_website/local_testing.py",
            "oaf_website/migrate.py",
            "oaf_website/migration_authority.py",
            "oaf_website/migration_config.py",
            "oaf_website/migration_validation.py",
            "oaf_website/notification_schema.py",
            "oaf_website/notification_validation.py",
            "oaf_website/notifications.py",
            "oaf_website/state_request_schema.py",
            "oaf_website/state_request_validation.py",
            "oaf_website/state_requests.py",
            "ops/Invoke-NotificationLiveValidation.ps1",
            "ops/Invoke-StateRequestLiveValidation.ps1",
            "ops/Record-Development0002Prerequisites.ps1",
            "ops/Record-Development0003Prerequisites.ps1",
            "ops/Record-Testing0003Approvals.ps1",
            "ops/Record-Testing0003Reconciliation.ps1",
            "ops/Start-DevelopmentWebsite.ps1",
            "ops/local_postgres_bootstrap/01_roles.sql",
            "ops/local_postgres_bootstrap/02_dev_schema.sql",
            "ops/local_postgres_bootstrap/03_test_schema.sql",
            "ops/local_postgres_bootstrap/04_verify.sql",
            "ops/local_postgres_bootstrap/05_activate_dev.py",
            "ops/local_postgres_bootstrap/06_activate_test.py",
            "ops/local_postgres_bootstrap/README.md",
            "ops/notification_live_check.py",
            "ops/state_request_live_check.py",
            "requirements-dev.txt",
            "requirements-migrations.txt",
            "requirements.txt",
            "styles.css",
            "tests/conftest.py",
            "tests/migration_offline.py",
            "tests/notification_browser_check.py",
            "tests/notification_live_browser.py",
            "tests/state_request_browser_check.py",
            "tests/state_request_live_browser.py",
            "tests/test_database_config.py",
            "tests/test_migration_artifacts.py",
            "tests/test_migration_authorization.py",
            "tests/test_migration_catalog.py",
            "tests/test_migration_config.py",
            "tests/test_migration_operational.py",
            "tests/test_migration_provenance.py",
            "tests/test_migration_runner.py",
            "tests/test_notification_migration.py",
            "tests/test_notifications.py",
            "tests/test_state_request_migration.py",
            "tests/test_state_requests.py"
        ],
        "head": "f95db80d0d69d974ce5af096dfa085ab6ede0ea2",
        "status": " M .vscode/settings.json\n M README.md\n M docs/WEBSITE_PLAN.md\n M docs/WORKFLOW.md\n M gramanna.html\n M migrations/manifest.json\n M oaf_website/local_testing.py\n M oaf_website/migration_authority.py\n M oaf_website/migration_validation.py\n M oaf_website/state_requests.py\n M tests/migration_offline.py\n M tests/state_request_browser_check.py\n M tests/test_migration_artifacts.py\n M tests/test_migration_authorization.py\n?? .vscode/tasks.json\n?? assets/notifications.js\n?? migrations/versions/0003_notifications.py\n?? oaf_website/local_development.py\n?? oaf_website/notification_schema.py\n?? oaf_website/notification_validation.py\n?? oaf_website/notifications.py\n?? ops/Invoke-NotificationLiveValidation.ps1\n?? ops/Record-Development0002Prerequisites.ps1\n?? ops/Record-Development0003Prerequisites.ps1\n?? ops/Record-Testing0003Approvals.ps1\n?? ops/Record-Testing0003Reconciliation.ps1\n?? ops/Start-DevelopmentWebsite.ps1\n?? ops/notification_live_check.py\n?? tests/notification_browser_check.py\n?? tests/notification_live_browser.py\n?? tests/test_notification_migration.py\n?? tests/test_notifications.py\n"
    },
    "repository": {
        ".gitignore": "2f5d5d95a1b03d0e94630e138e15982dea34e836c626a8ebfb52415012f27d3d",
        ".vscode/settings.json": "bceb4f155f6ad2e45062f3bc40e28bce0d750f1fc464434b11f9e7dda7292e46",
        ".vscode/tasks.json": "b5d6228e6642d634b4d32523df4d500e16fe562b1abcddd85ecffbe0c79683e6",
        "README.md": "ae5d1cad5f93c22cbbeecde6c5ae8839134e294e449c81b099e64266673cec46",
        "about.html": "f2982ec74c6125cc9f5a0d165a449efbfd5941d7cc714a2adf316e8e2c02d504",
        "alembic.ini": "c72a8cc54828755974765ab8df60c03744cd448b7d16bed81b1157569548f736",
        "assets/images/gramanna-logo.png": "52063b300d78a645aca21a7209e6153b36987c9864d6a94978dbb534b89085f9",
        "assets/images/hero-gifts.webp": "29497ebe32548a5e05238fe6bfb750df170784fc7009a538598e8a17f5ece885",
        "assets/notifications.js": "da7fe327c3eb8c15248dc2dc3b34b70097e3cad5c0ceda068496291bff7e7b9e",
        "assets/state-requests.js": "06aae901fe95eac98c35647b68420644c569529f510ca07fb8e5827f04705a1f",
        "config/database.example.toml": "5c83c5004d4a57a563c04479154f7875cffcfad67c9dcfccc5a3c96319b95a4a",
        "docs/WEBSITE_PLAN.md": "1d639ced0cf70d3338e644aca536b037918481773e7e0a831b1f5a8daf6cd161",
        "docs/WORKFLOW.md": "a5e7381f2887b30478e110ffc393705efe1e205cb9142de229955759e73e6250",
        "gramanna.html": "991c2875139325a51325c4ca478e1f33e1aa4a8479f571994adde328dea70b14",
        "index.html": "73167dbbf833bbd2df0708904de1abe7154b1fcb36c321078d688f051c986405",
        "migrations/env.py": "09fcd94121f9ba0287d33d9b779f2b7845be56f23fea23aaafb5ae891fe661d4",
        "migrations/manifest.json": "6b803dc0a581b66161a9ba4f9c473cc7958d1903c80a54943d78b5dabb4ac9a7",
        "migrations/script.py.mako": "ed31327e01d48ec1ba1e91f5dc5b347fed7e9a8c9733b50d49c8085e86815bdc",
        "migrations/versions/0001_migration_baseline.py": "bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3",
        "migrations/versions/0002_state_requests.py": "c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad",
        "migrations/versions/0003_notifications.py": "1c575d679981556a782c0f279097fd6f0fd47d6c2b7613d3a323424f0e61f452",
        "oaf_website/__init__.py": "ad4cfd8e9137a2e69abe6fdad18114a9918fccf918cbe59e181a9edd78436eb5",
        "oaf_website/database_config.py": "bffc9d41024c7d562944d67c55cff254e63c0f5c83f54ec4b2384c64ab51ed60",
        "oaf_website/local_development.py": "62aa6e6efd603d2e5543b8ca4db035683405013de3ce971b1079d3e03f7639a3",
        "oaf_website/local_testing.py": "fb3278a903edca5d877e9f88e0f5767e53b670ea65c328592baba929398b52f1",
        "oaf_website/migrate.py": "706a6fefaca086f43bd2729c1cafefdb5bfe3bbd2f71e7a404e2e922454ae1e0",
        "oaf_website/migration_authority.py": "7654a552106b7ef3ec5827decf0ea9f61b317b2265c4364a0d5d7278549da6ce",
        "oaf_website/migration_config.py": "9c537cceaed6c84b3050f4db0a2510e6588e4259e927b35322e86cab91ab3587",
        "oaf_website/migration_validation.py": "a5ef986aae4515d0f39c416dad812a0479c094b9d5b81a37c04d298f88b05b23",
        "oaf_website/notification_schema.py": "8609e44436663db7d7a99ec7964ebaec4658b0491412d366b17f4d7850bd77e4",
        "oaf_website/notification_validation.py": "939200c718fa5131427315ce6b7f10ebe4177653c7744d54c3e593d263a26267",
        "oaf_website/notifications.py": "0351ff15539a974f73478365846fde18673b847c31b62ad18459ca741b40c24b",
        "oaf_website/state_request_schema.py": "440924c43651c6b7d1e5c8745de705dd0ceeb589eb10422e805131ede51f9647",
        "oaf_website/state_request_validation.py": "a04e8a50bf353dd1de03a3f310445adb9392a33d0ae8c441ebd877d03d32db5d",
        "oaf_website/state_requests.py": "b80a9f5bb7d75f198f4f5eae4832315197bb1f407a8820c22eea1ac9a014cf60",
        "ops/Invoke-NotificationLiveValidation.ps1": "8b3f5a19785c7cdc716ef523a0a44ba1e8e7fc10f2eb83604f131c52f78401b7",
        "ops/Invoke-StateRequestLiveValidation.ps1": "54ae0b033dab82eac3307ea8f655d1dcfa9b0ebf31dcee27cc5d570b67d76ead",
        "ops/Record-Development0002Prerequisites.ps1": "d1e3b59e54f7a37129b3bd1a17e1fb4063733c90ab626b19bce9a199df230292",
        "ops/Record-Testing0003Approvals.ps1": "558a7b85712162f859970da0dbb2f4d764cb6363ad46ef9d0a42b00783be5db3",
        "ops/Record-Testing0003Reconciliation.ps1": "16af86d75a859514e7376def1e083018c09ab92d4dd010d0bb4441615e27bc57",
        "ops/Start-DevelopmentWebsite.ps1": "122f981289db6cb18837fd748fc3ec595579303889d277d8f2748a16fe7db98b",
        "ops/local_postgres_bootstrap/01_roles.sql": "cf314c1c946564282262564befb6831b49289f4280352d998a4da7bc7f0f0c3b",
        "ops/local_postgres_bootstrap/02_dev_schema.sql": "8392d858d61cd609c97a3cd2211bcec005601accd87b2b162faa17db6a339338",
        "ops/local_postgres_bootstrap/03_test_schema.sql": "e980a521e24d5b9f3c2642268029cd19a9156e9068243987fac6238fe687d7e2",
        "ops/local_postgres_bootstrap/04_verify.sql": "848220a0bd24a4a8c1ee24aeb315728fba92ea23b0c309dbe47580e7af57427d",
        "ops/local_postgres_bootstrap/05_activate_dev.py": "88223d93a4f53ac57793d82c72762aa2cce257e9e3fc44d30c98dd514a896dfb",
        "ops/local_postgres_bootstrap/06_activate_test.py": "02886412b59b3f9eb3d0f061986586598eda275de4d11f47fb62765abe449498",
        "ops/local_postgres_bootstrap/README.md": "476d3f3b80da7b716c9c6db7a88e1970be1bae7b822ee2a747aeb4fe13edfc9b",
        "ops/notification_live_check.py": "f4814236a70e2718413283b33833b3afe4bac57ad1f8de3117c7ab7ba23e07c0",
        "ops/state_request_live_check.py": "12dfbac2e1c6ebba38e9e2927415aa498fcda40a0bda3e76605276b260abc3ed",
        "requirements-dev.txt": "764ba9735ba1c6882bbc19225f6eaa76fead5ac98a3a314e97d2f89828d6d740",
        "requirements-migrations.txt": "3154eef6a20748636332276d9a39e13b1d03585df55ab681b706362d294de33e",
        "requirements.txt": "3f8e4f324231e88e0c7a9e1be05c9a26be0a1d5628a5b9947b2ee7794b96fb9d",
        "styles.css": "7849d98246efbba141c25628a87cd9c54f8aad51de76eacdecd9b7eead447c2d",
        "tests/conftest.py": "dfd544811f7010357d9fea8c3921ca892f4b2e1f1e700ab72a17a84411bf1967",
        "tests/migration_offline.py": "9bff47388ffd364704f251b8643edd7fdfe56d9b76681ffa2639422ffa8e1fd7",
        "tests/notification_browser_check.py": "90a9e409b2f349567e39129df36639657e58f82b9bd2999c98d7c440716be4e7",
        "tests/notification_live_browser.py": "b3b45288856323966274e00dff207a31271823190a093ec71f5272f16c04c48e",
        "tests/state_request_browser_check.py": "f0ce308927ff3d61b47d5ec5fb370259057185dc24c534a0f83eedfca8b8da81",
        "tests/state_request_live_browser.py": "6b7272db5d159ee0930fa0cbcd78e7010c2895b7e68eae70e7c250d8faf8bf8d",
        "tests/test_database_config.py": "e6b2078a333e93580a495ecaf709e098e574d1fb2705e2413500894f6b713e82",
        "tests/test_migration_artifacts.py": "480d3488fa45ee9f9352c4f1d4e72c55e9ff3023ff46afe1c35b94dba558bdbf",
        "tests/test_migration_authorization.py": "075a1091b6d212d047ced023b21a350930f9cb87154f913258b291eae0df50a0",
        "tests/test_migration_catalog.py": "b5677305f1edfd8ea11c6284777ccb76238a2b70394d93f8035eb2c2cc7f6cf9",
        "tests/test_migration_config.py": "84150cb7553858c7e6ee252abda64207bfe70e7a64a2106df9599209d6a10507",
        "tests/test_migration_operational.py": "bbde79df63f41b2be68fa100c6f1a138d3865c567f4f5e078e1b26fdf2c5e3a8",
        "tests/test_migration_provenance.py": "6f73d0f09ae5c735a128d3cf0e0f6d33d8090898e680caed44c18cd8759330e2",
        "tests/test_migration_runner.py": "eac7927edf1d631578820a42d977017242f0968019036a2b948c1ab6ff87e627",
        "tests/test_notification_migration.py": "9ce566f96139a71ad6f8b71570c0fb6e5359ac2d1015b5dfe8af0a4ddb0955c1",
        "tests/test_notifications.py": "61c13313be8394601eacf189458358d85e4fab5a66d515550e9512e75c3cc50c",
        "tests/test_state_request_migration.py": "d7c05bea36a61a393f66d2fa13a0f95922a89331acaa1b2c859f89799a44d260",
        "tests/test_state_requests.py": "5bcb57dce96ddcd14018c8ff8913147fe853fe78a5e3b3ef9f3600b87994f048"
    }
}
NEW_NAMES = ('prerequisite-attestation-' + ATTESTATION_ID + '.json',
             'prerequisite-approval-' + APPROVAL_ID + '.json')
PREFLIGHT = {
    'source': 'owner_supplied_completed_development_read_only_preflight_in_task',
    'status': 'PASS', 'database': 'oaf_website_dev', 'login': 'oaf_website_dev_migrator',
    'effective_role': 'oaf_website_dev_schema_owner', 'revision': '0002_state_requests',
    'exact_catalog': 'PASS', 'state_requests': 'PRESENT', 'notifications': 'ABSENT',
    'predecessor': 'VERIFIED', 'read_only': 'YES', 'rerun_now': False,
    'assurance': 'Owner supplied result; no invented preflight UUID, timestamp or signed evidence file.'
}
LIVE_EVIDENCE = {
    'source': 'owner_supplied_completed_testing_evidence_in_task',
    'testing_validation_run': TESTING_RUN,
    'independent_postgresql_verification': 'PASS',
    'live_flask_chromium_playwright_postgresql_notification_subscription_validation': 'PASS',
    'rerun_now': False,
    'assurance': 'Owner reported completed validations; migration completion separately checked with Stage 5 validators.'
}


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
                not (getattr(component.lstat(), 'st_file_attributes', 0) & 0x400), 'Redirected path component.')
    require(path.is_dir() if directory else path.is_file(), 'Required evidence path unavailable.')


def byte_hash(path):
    safe_path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mutation_guard(mode):
    allowed = {str(AUDIT / name) for name in NEW_NAMES}
    opened = set()
    def guard(event, args):
        if event == 'open':
            path, _, flags = args
            write = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if write:
                require(mode == 'create' and isinstance(path, (str, bytes, os.PathLike)) and
                        os.fsdecode(path) in allowed and os.fsdecode(path) not in opened and
                        flags & os.O_EXCL and flags & os.O_CREAT and
                        not flags & (os.O_TRUNC | os.O_APPEND),
                        'Only two exact exclusive prerequisite destinations may be written once.')
                opened.add(os.fsdecode(path))
        if event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink',
                     'os.chmod', 'os.utime', 'os.truncate', 'subprocess.Popen', 'os.system',
                     'socket.connect', 'socket.getaddrinfo'}:
            deny_external_access()
    sys.addaudithook(guard)


def prepare_modules(mode):
    require(os.name == 'nt' and Path.cwd() == REPO, 'Use the specified native Windows repository.')
    safe_path(REPO, directory=True)
    require(sys.version_info[:2] == (3, 11), 'Existing website Python 3.11 is required.')
    require(Path(sys.executable) == REPO / '.venv/Scripts/python.exe', 'Unexpected interpreter.')
    # Only these fixed read-only Git probes occur before all subprocess access is denied.
    def git(*arguments):
        return subprocess.check_output(['git', '--no-optional-locks', *arguments], cwd=REPO).decode('utf-8')
    inventory = dict(head=git('rev-parse', 'HEAD').strip(), branch=git('branch', '--show-current').strip(),
                     status=git('status', '--porcelain=v1', '--untracked-files=all'),
                     files=sorted(filter(None, git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split('\0'))))
    require(inventory == SNAPSHOT['inventory'], 'Repository inventory changed since preparation; stop.')
    platform.uname()  # Cache stdlib Windows version probe before blocking subprocesses.
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
    authority.issue_authorization = authority._publish_completion = authority.audit_destination = deny_external_access
    if mode != 'create':
        authority._save = deny_external_access
    return authority, validation, IDENTITIES


def audit_root():
    local = os.environ.get('LOCALAPPDATA')
    require(isinstance(local, str) and bool(local) and Path(local).is_absolute(), 'LOCALAPPDATA must be absolute.')
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
    now = datetime.now(timezone.utc)
    artifact = authority._reference(root, 'artifact-approval', ARTIFACT_REF)
    authority._approval(artifact, 'artifact_approval', ARTIFACT_REF, {'manifest_hash', 'revision_hash'}, now)
    require(artifact['reviewer_id'] == REVIEWER and
            all(artifact[key] == SCOPE[key] for key in ('manifest_hash', 'revision_hash')),
            'Reusable corrected artifact approval or reviewer differs.')
    require(authority._previous(root, 'development') == PREDECESSOR, 'DEVELOPMENT predecessor advanced.')
    require(authority._ordinary_predecessor(root, 'development', PREDECESSOR, SCOPE['expected_start']),
            'DEVELOPMENT predecessor requires reconciliation.')
    dev_event, dev_history = authority._completed_run(root, root / 'claim-development-00000002.json')
    require(dev_event['run_id'] == DEVELOPMENT_RUN and dev_event['target'] == SCOPE['expected_start'] and
            dev_event['outcome'] == 'applied_and_verified' and dev_event['validation_outcome'] == 'postcommit_passed',
            'Published completed DEVELOPMENT 0002 provenance differs.')
    authority._testing_validation(root, SCOPE, TESTING_RUN)
    claim, _ = authority._read(root / 'claim-testing-00000004.json')
    authorization, _ = authority._authorization(root, claim['authorization_id'])
    require(claim['run_id'] == TESTING_RUN and authorization['artifact_approval'] == ARTIFACT_REF and
            authorization['prerequisite_approval']['id'] == TESTING_APPROVAL,
            'TESTING completion does not reference the approved corrected records.')
    old, _ = authority._read(root / ('prerequisite-attestation-' + TESTING_ATTESTATION + '.json'))
    previous = authority._reference(root, 'prerequisite-approval', authorization['prerequisite_approval'])
    require(old['id'] == TESTING_ATTESTATION and old['kind'] == 'prerequisite_applicability_attestation' and
            old['decision'] == 'approved' and old['environment'] == 'testing' and
            old['reviewer_id'] == previous['reviewer_id'] == REVIEWER and
            old['artifact_approval'] == ARTIFACT_REF and old['prerequisite_approval_id'] == TESTING_APPROVAL and
            all(old[key] == SCOPE[key] for key in ('expected_start', 'target', 'manifest_hash', 'revision_hash')) and
            set(old['categories']) == authority.PREREQUISITES and
            previous['approvals'] == {key: TESTING_ATTESTATION for key in authority.PREREQUISITES},
            'Existing corrected six-category TESTING evidence differs.')
    for name, reference in old['revision_specific_evidence'].items():
        if reference['location'] == 'repository':
            require(SNAPSHOT['repository'].get(name) == reference['sha256'], 'Existing reviewed source differs: ' + name)
        elif reference['location'] == 'MigrationAudit':
            require(SNAPSHOT['audit'].get(name.removeprefix('MigrationAudit/')) == reference['sha256'],
                    'Existing retained review evidence differs: ' + name)
    identity = identities['development']
    require((identity.database, identity.migrator, identity.owner, identity.runtime,
             identity.schema, identity.host, identity.port, identity.postgres_major) ==
            ('oaf_website_dev', 'oaf_website_dev_migrator', 'oaf_website_dev_schema_owner',
             'oaf_website_app', 'oaf_website', '127.0.0.1', 5432, 17), 'Fixed DEVELOPMENT identity differs.')
    require(now.timestamp() >= (root / 'claim-development-00000002.json').stat().st_mtime,
            'Approval time predates DEVELOPMENT predecessor.')
    preserved_checks(root, NEW_NAMES if saved else ())
    return now


def evidence_map():
    result = {name: {'location': 'repository', 'hash_mode': 'exact_bytes', 'sha256': digest}
              for name, digest in SNAPSHOT['repository'].items()}
    result.update({'MigrationAudit/' + name: {'location': 'MigrationAudit', 'hash_mode': 'exact_bytes', 'sha256': digest}
                   for name, digest in SNAPSHOT['audit'].items()})
    return result


def categories():
    previous = 'MigrationAudit/prerequisite-attestation-' + TESTING_ATTESTATION + '.json'
    testing = ['MigrationAudit/claim-testing-00000004.json', 'MigrationAudit/terminal-' + TESTING_RUN + '.json',
               'MigrationAudit/completed-terminal-' + TESTING_RUN + '.json']
    development = ['MigrationAudit/claim-development-00000002.json',
                   'MigrationAudit/terminal-' + DEVELOPMENT_RUN + '.json',
                   'MigrationAudit/completed-terminal-' + DEVELOPMENT_RUN + '.json']
    def category(statement, references):
        return {'applicability': 'approved_for_exact_development_transition',
                'adoption': 'administrative_owner_adoption_of_existing_completed_evidence',
                'statement': statement, 'evidence': references + [previous] + testing}
    return {
        'dependency_acceptance': category(
            'Adopt existing accepted pinned toolchain and completed corrected-artifact evidence for DEVELOPMENT. '
            'The same-artifact completed TESTING 0003 migration proves toolchain execution there; the owner reports '
            'independent PostgreSQL and live Flask/Chromium/Playwright/PostgreSQL notification validation PASS. '
            'Use the existing website Python 3.11 interpreter, Flask 3.1.3, SQLAlchemy 2.0.54, psycopg 3.3.6, '
            'keyring 25.7.0, Alembic 1.20.0 and PostgreSQL 17 at 127.0.0.1:5432. No completed reviews or tests '
            'are repeated; no dependency install or change. Migration evidence and owner-reported live checks '
            'retain their distinct provenance.',
            ['requirements.txt', 'requirements-migrations.txt', 'docs/WORKFLOW.md',
             'tests/test_notification_migration.py', 'tests/test_notifications.py', 'owner_supplied_completed_testing_evidence']),
        'bootstrap_validation': category(
            'Owner-supplied completed DEVELOPMENT read-only preflight is PASS: oaf_website_dev, authenticated '
            'oaf_website_dev_migrator, effective oaf_website_dev_schema_owner, revision 0002_state_requests, exact '
            'catalog PASS, state_requests PRESENT, notifications ABSENT, predecessor VERIFIED. Published DEVELOPMENT '
            '0002 completion supports ordinary continuation. Database owner remains oaf_website_owner; schema '
            'oaf_website and all managed objects belong to oaf_website_dev_schema_owner. Matching runtime '
            'oaf_website_app requires CONNECT and schema USAGE only, without schema CREATE or metadata access. '
            'Restricted migrator SET ROLE membership, restrictive defaults, SCRAM and exact database/server/role '
            'matching remain required. This checkpoint adopts the supplied preflight and existing bootstrap '
            'evidence without fresh database or credential access.',
            ['owner_supplied_development_preflight', 'oaf_website/migration_config.py',
             'oaf_website/migration_validation.py', 'ops/local_postgres_bootstrap/01_roles.sql',
             'ops/local_postgres_bootstrap/02_dev_schema.sql', 'ops/local_postgres_bootstrap/04_verify.sql'] + development),
        'lock_and_timeouts': category(
            'Existing reviewed controls apply to oaf_website_dev: database-scoped session advisory lock '
            '(0x4F414657,4), 5-second bounded acquisition and acquisition-query timeout, 5-second lock_timeout, '
            '60-second statement_timeout. The same backend and lock survival across setup rollback are verified; '
            'lock spans the one-revision transaction, commit and independent postcommit validation. Runner and '
            'Alembic recheck controls and execution authority at their established boundaries. Completed TESTING '
            '0003 and DEVELOPMENT 0002 evidence record release_confirmed. No new contention or timeout review '
            'or live exercise is performed for this recording.',
            ['oaf_website/migrate.py', 'migrations/env.py', 'oaf_website/migration_validation.py'] + development),
        'search_path_and_postconditions': category(
            'Use pg_catalog, oaf_website, pg_temp and schema-qualified objects under oaf_website_dev_schema_owner. '
            'Exactly one 0002_state_requests -> 0003_notifications revision transaction must preserve baseline '
            'metadata and state_requests definitions/grants, advance exactly one alembic_version row to '
            '0003_notifications, and add only the manifest notification inventory. notifications has nine columns: '
            'unsubscribe_digest varchar(64) NOT NULL; email varchar(254) NOT NULL; web_launch, android_launch, '
            'ios_launch boolean NOT NULL; nullable state varchar(2); consent_version varchar(40) NOT NULL; '
            'created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP; nullable unsubscribed_at timestamptz. '
            'Require notifications_pk PRIMARY KEY (unsubscribe_digest) and exact unique btree index; '
            'notifications_active_email unique btree(email) WHERE unsubscribed_at IS NULL. Six named checks '
            'notifications_token_check (64 lowercase hex), notifications_email_check (lowercase trimmed length>=3), '
            'notifications_preferences_check (any launch or non-null state), notifications_state_check '
            '(null or registered 50-state code), notifications_consent_check (gramanna-announcements-v1), '
            'notifications_lifecycle_check (null withdrawal or unsubscribed_at>=created_at, conkey [9,8]). '
            'Require exact types, collation/nullability/defaults, constraint flags and column order, index '
            'definitions/predicate, object inventory/owners and all manifest dependency edges without extras '
            'or extension membership. Grant oaf_website_app SELECT/INSERT on notifications and UPDATE only '
            'on unsubscribed_at, without grant options; no other nonowner data grants, table UPDATE, DELETE, '
            'TRUNCATE or testing-role access. Notification row type has explicit owner-only USAGE; array type '
            'follows element ACL, with no PUBLIC/runtime USAGE. Preserve restrictive global/schema defaults, '
            'no PUBLIC schema/data exposure, no runtime metadata access, and generated-type exception solely '
            'for alembic_version/_alembic_version. Verify every exact revision 0003 postcondition before commit '
            'and again afterward while locked. Same-artifact TESTING completed successfully; DEVELOPMENT '
            '0003 postconditions await separately authorized execution.',
            ['migrations/manifest.json', 'migrations/versions/0001_migration_baseline.py',
             'migrations/versions/0002_state_requests.py', 'migrations/versions/0003_notifications.py',
             'migrations/env.py', 'oaf_website/migration_validation.py', 'oaf_website/notification_schema.py',
             'oaf_website/notification_validation.py', 'tests/test_notification_migration.py']),
        'recovery_procedure': category(
            'Exact DEVELOPMENT predecessor sequence=2 with supplied raw claim SHA-256 has completed consistent '
            'acknowledged-commit and postcommit-pass evidence, supporting expected_start=0002_state_requests '
            'and owner_reconciliation=not_applicable. Supplied read-only preflight agrees. The cited successful '
            'TESTING 0003 run follows the retained reconciled failed TESTING claim 3; Stage 5 validates the '
            'actual predecessor-bound recovery approvals and published event/terminal completion. The failed '
            'run is retained and historical TESTING 0002 evidence is not substituted for fresh 0003 success. '
            'Preserve every claim and acknowledged commit. Stop on partial/uncertain outcomes, missing or '
            'contradictory evidence, or postcommit audit failure; exceptional outcomes need exact-predecessor '
            'owner reconciliation. No blind retries, claim deletion, downgrade, stamp, repair or credential '
            'rotation. Future execution requires distinct deliberate owner issuance; this checkpoint issues none.',
            ['owner_supplied_development_preflight', 'docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md',
             'oaf_website/migrate.py', 'oaf_website/migration_authority.py', 'tests/test_migration_operational.py'] + development),
        'audit_policies': category(
            'Owner-approved policies A-D apply to this exact DEVELOPMENT transition: sanitized exclusive UTF-8/LF '
            'MigrationAudit records with flush/fsync; retain all history until separate archival authorization; '
            'distinct bounded environment/artifact/prerequisite/predecessor-bound owner execution authorization; '
            'fail-closed persistence and recovery. Published completion is mandatory for authorization/terminal '
            'evidence. Save exactly two new prerequisite records exclusively in the existing destination; '
            'retain partial writes and never retry creation. Reuse corrected artifact approval UUID and exact '
            'byte hash; no new artifact approval or execution authorization. Established reviewer reference '
            'is preserved as an administrative local reference. Owner adoption/recording is distinct from '
            'historical independently performed reviews; no corrected-artifact independent certification is '
            'invented and no independent review is repeated now. UUIDs and hashes do not provide signatures '
            'or proof of reviewer independence. Runtime/launcher owner changes and all existing audit bytes remain preserved.',
            ['docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migration_authority.py',
             'tests/test_migration_authorization.py', 'tests/test_migration_operational.py'])
    }


def build_records(approved_utc):
    common = dict(format=1, reviewer_id=REVIEWER, approved_utc=approved_utc, decision='approved',
                  environment='development', expected_start=SCOPE['expected_start'], predecessor=PREDECESSOR,
                  owner_reconciliation='not_applicable', testing_validation_run=TESTING_RUN)
    approval = dict(common, kind='prerequisite_approval', id=APPROVAL_ID,
                    approvals={key: ATTESTATION_ID for key in categories()})
    approval_ref = dict(id=APPROVAL_ID, sha256=hashlib.sha256(encoded(approval)).hexdigest())
    attestation = dict(common, kind='prerequisite_applicability_attestation', id=ATTESTATION_ID,
        action='upgrade', target=SCOPE['target'], manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'],
        artifact_approval_id=ARTIFACT_REF['id'], artifact_approval=ARTIFACT_REF,
        prerequisite_approval_id=APPROVAL_ID, prerequisite_approval=approval_ref,
        categories=categories(), revision_specific_evidence=evidence_map(),
        repository_inventory=SNAPSHOT['inventory'], owner_supplied_development_preflight=PREFLIGHT,
        owner_supplied_completed_testing_evidence=LIVE_EVIDENCE,
        development_identity={'database': 'oaf_website_dev', 'database_owner': 'oaf_website_owner',
            'login': 'oaf_website_dev_migrator', 'effective_role': 'oaf_website_dev_schema_owner',
            'schema': 'oaf_website', 'schema_owner': 'oaf_website_dev_schema_owner',
            'application_role': 'oaf_website_app', 'host': '127.0.0.1', 'port': 5432, 'postgres_major': 17},
        approval_basis={
            'authority': 'explicit_owner_approval_for_development_0003_record_only_checkpoint',
            'administrative_adoption': 'Owner adopts existing corrected-artifact approval and applicable completed '
                'six-category evidence, DEVELOPMENT read-only preflight and same-artifact TESTING 0003 success.',
            'established_reviewer_reference': REVIEWER,
            'independent_certification': {'prior_evidence': 'MigrationAudit/prerequisite-attestation-' + TESTING_ATTESTATION + '.json',
                'performed_or_repeated_now': False, 'new_independent_evidence_created': False,
                'corrected_artifact_independent_certification_claimed': False,
                'assurance': 'Preserve existing evidence distinction between owner adoption and historical independent reviews.'},
            'assurance': 'Administrative owner adoption/recording; UUIDs and hashes are local references, not signatures.'},
        validation_boundary={
            'existing_testing_0003_migration_validation': 'published_completed_consistent_same_artifact_run',
            'additional_testing_live_validation': 'owner_reported_completed_PASS_not_rerun',
            'development_0002_validation': 'published_completed_0002_plus_owner_supplied_read_only_preflight',
            'development_0003_postconditions': 'required_at_future_separately_authorized_execution',
            'independent_review_performed_now': False, 'completed_tests_rerun_now': False,
            'new_artifact_approval_issued': False, 'migration_authorization_issued': False,
            'postgresql_or_credential_access_performed_now': False})
    return attestation, approval


def validate_documents(records, authority, now, claim_mtime):
    attestation, approval = records
    require(ATTESTATION_ID != APPROVAL_ID and all(authority._uuid(value) for value in (ATTESTATION_ID, APPROVAL_ID)),
            'Invalid new record UUIDs.')
    require(records == build_records(attestation['approved_utc']), 'Record fields, evidence or cross-bindings differ.')
    authority._approval(approval, 'prerequisite_approval', {'id': APPROVAL_ID},
        {'environment', 'expected_start', 'approvals', 'predecessor', 'owner_reconciliation', 'testing_validation_run'}, now)
    require(set(attestation['categories']) == authority.PREREQUISITES and
            approval['approvals'] == {key: ATTESTATION_ID for key in authority.PREREQUISITES},
            'All six categories must reference the new DEVELOPMENT attestation.')
    require(claim_mtime <= authority._utc(approval['approved_utc']).timestamp() <= now.timestamp(),
            'Approval time is future-dated or predates predecessor.')
    for category in attestation['categories'].values():
        require(category['applicability'] == 'approved_for_exact_development_transition', 'Wrong applicability.')
        for reference in category['evidence']:
            require(reference in {'owner_supplied_development_preflight', 'owner_supplied_completed_testing_evidence'} or
                    reference in attestation['revision_specific_evidence'], 'Unbound category evidence.')
    for record in records:
        require(len(encoded(record)) <= 64000, 'Record exceeds Stage 5 read limit.')


def validate_proposed_approvals(root, records, authority, now):
    # Resolve only the UNSAVED proposal in memory; all existing refs use the real reader.
    # The independent saved-file verifier below always uses the unmodified Stage 5 reader.
    reference = records[0]['prerequisite_approval']
    original = authority._reference
    def proposed_reference(destination, prefix, candidate):
        if prefix == 'prerequisite-approval' and candidate.get('id') == APPROVAL_ID:
            require(destination == root and candidate == reference, 'Proposed approval binding differs.')
            return records[1]
        return original(destination, prefix, candidate)
    authority._reference = proposed_reference
    try:
        authority._approvals(root, SCOPE, ARTIFACT_REF, reference, PREDECESSOR, now)
    finally:
        authority._reference = original


def validate_saved(root, records, authority, now, claim_mtime):
    validate_documents(records, authority, now, claim_mtime)
    hashes = []
    for name, record in zip(NEW_NAMES, records):
        loaded, digest = authority._read(root / name)
        require(loaded == record and (root / name).read_bytes() == encoded(record) and
                byte_hash(root / name) == digest, 'Saved fields, canonical UTF-8/LF bytes or exact digest differ.')
        hashes.append(digest)
    require(records[0]['prerequisite_approval'] == {'id': APPROVAL_ID, 'sha256': hashes[1]},
            'Saved prerequisite approval exact-byte cross-binding differs.')
    authority._approvals(root, SCOPE, ARTIFACT_REF, {'id': APPROVAL_ID, 'sha256': hashes[1]}, PREDECESSOR, now)


def print_results(root, records, saved=False):
    for label, name, record in zip(('Attestation', 'Prerequisite approval'), NEW_NAMES, records):
        print(label + ' UUID: ' + record['id'])
        print(label + ' path: ' + str(root / name))
        if saved:
            print(label + ' SHA-256 (exact bytes): ' + byte_hash(root / name))
        print(label + (' saved UTC: ' if saved else ' preview UTC (UNSAVED): ') + record['approved_utc'])
    print('Binding: development / upgrade / 0002_state_requests -> 0003_notifications')
    print('Predecessor: sequence=2 sha256=' + PREDECESSOR['sha256'])
    print('owner_reconciliation=not_applicable; testing_validation_run=' + TESTING_RUN)
    print('Reused artifact approval: ' + ARTIFACT_REF['id'] + ' exact-byte sha256=' + ARTIFACT_REF['sha256'])
    print('Manifest/revision hashes: ' + SCOPE['manifest_hash'] + ' / ' + SCOPE['revision_hash'])
    print('All six DEVELOPMENT categories: PASS; established reviewer=' + REVIEWER)
    print('Approval basis: owner adoption; no independent review performed or repeated now.')
    print('Pre-existing repository/launcher and audit bytes: preserved.')
    print('No new artifact approval/authorization; no database access/modification or credential/role change.')


def main(mode):
    authority, validation, identities = prepare_modules(mode)
    root = audit_root()
    now = common_checks(root, authority, validation, identities, saved=(mode == 'verify'))
    claim_mtime = (root / 'claim-development-00000002.json').stat().st_mtime
    if mode == 'inspect':
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        validate_proposed_approvals(root, records, authority, now)
        print('Read-only artifacts, inventory, existing six-category evidence and Stage 5 dependency checks: PASS.')
        print('Published same-artifact TESTING 0003 and ordinary DEVELOPMENT predecessor: PASS.')
        print('Proposed record byte lengths: ' + ', '.join(str(len(encoded(record))) for record in records))
        print_results(root, records)
        print('PASS / PREPARED ONLY; exactly two prerequisite records UNSAVED.')
    elif mode == 'create':
        # Actual UTC approval timestamp is captured at native recording, after checks pass.
        now = datetime.now(timezone.utc)
        records = build_records(now.isoformat())
        validate_documents(records, authority, now, claim_mtime)
        validate_proposed_approvals(root, records, authority, now)
        for index, (name, record) in enumerate(zip(NEW_NAMES, records)):
            preserved_checks(root, NEW_NAMES[:index])
            require(authority._previous(root, 'development') == PREDECESSOR, 'Predecessor advanced during recording.')
            authority._testing_validation(root, SCOPE, TESTING_RUN)
            authority._save(root / name, record)  # Existing exclusive UTF-8/LF writer; flush/fsync/close.
            require((root / name).read_bytes() == encoded(record), 'Saved bytes differ; stop without retry.')
            print('Exclusively saved: ' + name)
        now = common_checks(root, authority, validation, identities, saved=True)
        validate_saved(root, records, authority, now, claim_mtime)
        print('SAVED; separate read-only process verification still required.')
    elif mode == 'verify':
        records = tuple(authority._read(root / name)[0] for name in NEW_NAMES)
        validate_saved(root, records, authority, now, claim_mtime)
        common_checks(root, authority, validation, identities, saved=True)
        print_results(root, records, saved=True)
        print('PASS / SAVED; exactly two records independently verified with Stage 5 validators.')
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
    Write-TaskLine 'OAF WEBSITE - DEVELOPMENT 0003 PREREQUISITE RECORDING'
    Write-TaskLine ('Started UTC: ' + [DateTime]::UtcNow.ToString('o'))
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or
        $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use native Windows PowerShell 5.1.' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows is required.' }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -cne $taskRoot) { throw 'Run from the specified OAF Website repository.' }
    if ([IO.Path]::GetFullPath($PSScriptRoot) -cne (Join-Path $taskRoot 'ops')) { throw 'Unexpected script location.' }
    if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Existing website interpreter is unavailable.' }
    if (-not $env:LOCALAPPDATA -or -not [IO.Path]::IsPathRooted($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is unavailable.' }
    $taskAudit = Join-Path $env:LOCALAPPDATA 'OAF Website\BootstrapAudit\MigrationAudit'
    $taskPaths = @(
        (Join-Path $taskAudit ('prerequisite-attestation-' + $taskAttestationId + '.json')),
        (Join-Path $taskAudit ('prerequisite-approval-' + $taskApprovalId + '.json'))
    )
    if (-not (Test-Path -LiteralPath $taskAudit -PathType Container)) { throw 'Existing MigrationAudit is unavailable.' }
    # ValidateOnly has no record writes, clipboard access or visual UI.
    if (-not $ValidateOnly) { Initialize-TaskUI }
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
        # Native PowerShell independently rehashes the saved bytes by their specific labels.
        $taskLabels = @('Attestation', 'Prerequisite approval')
        for ($taskIndex = 0; $taskIndex -lt $taskPaths.Count; $taskIndex++) {
            $taskHash = (Get-FileHash -LiteralPath $taskPaths[$taskIndex] -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not ($taskLines -contains ($taskLabels[$taskIndex] + ' SHA-256 (exact bytes): ' + $taskHash))) {
                throw 'Native PowerShell and independent Python exact-byte hashes disagree.'
            }
            Write-TaskLine ($taskLabels[$taskIndex] + ' native exact-byte verification: PASS')
        }
        $taskRecordsVerified = $true
    }
    $taskExitCode = 0
    Write-TaskLine $(if ($ValidateOnly) { 'RESULT: PASS / PREPARED ONLY; records UNSAVED.' }
                    else { 'RESULT: PASS / SAVED; exactly two records independently verified.' })
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
        # Alert first, so any alert failure is included in the complete clipboard report.
        if ($taskAlertReady) {
            try {
                $taskAlertStatus = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
                $taskAlertMessage = if ($taskExitCode -eq 0) {
                    'PASS. Two DEVELOPMENT prerequisites saved and verified. UUIDs and exact hashes are in the terminal; clipboard copy follows.'
                } else { 'BLOCKED. Stop without retry and retain partial records. Read the terminal report; clipboard copy follows.' }
                Show-OAFPowerShellAlert -Status $taskAlertStatus -Title 'OAF DEVELOPMENT 0003 PREREQUISITES' -Message $taskAlertMessage
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
                    Show-OAFPowerShellAlert -Status 'failure' -Title 'OAF DEVELOPMENT 0003 REPORT BLOCKED' -Message 'Clipboard report failed. Keep terminal output. Do not rerun recording.'
                } catch { Write-TaskLine 'Existing red alert invocation failed.' }
            }
        }
    }
}

# Run with & in a separate native PowerShell process; exit stays in that process.
exit $taskExitCode
