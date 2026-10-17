# Windows PowerShell 5.1. Record-only owner-approved DEVELOPMENT checkpoint.
# Uses existing website Python and Stage 5 validators. Never executes a migration.
[CmdletBinding(DefaultParameterSetName = 'Record')]
param(
    [Parameter(ParameterSetName = 'Validate')][switch]$ValidateOnly,
    [Parameter(ParameterSetName = 'Verify')][switch]$VerifyOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$taskLines = New-Object 'System.Collections.Generic.List[string]'
$taskExitCode = 2
$taskRoot = 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskAttestationId = '8b388045-48f2-4e32-bd5d-6756ee004791'
$taskApprovalId = 'fa98f647-7757-45a5-9634-37322383237e'
$taskAudit = $null
$taskAttestationPath = $null
$taskApprovalPath = $null
$taskAlertReady = $false

function Write-TaskLine([string]$Text) {
    $taskLines.Add($Text)
    Write-Host $Text
}

# ASCII code is supplied through stdin, avoiding Windows native -c quoting.
$taskPythonCode = @'
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import socket
import sys

REPO = Path(r'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website')
ATTESTATION_ID = '8b388045-48f2-4e32-bd5d-6756ee004791'
APPROVAL_ID = 'fa98f647-7757-45a5-9634-37322383237e'
REVIEWER = '01ed5b95-c24e-402e-a547-c24447303ed5'
TESTING_RUN = 'cd8521b7-eb3d-412f-8ac1-188cabd04b30'
TESTING_ATTESTATION = 'fe53d5d1-8e82-409e-a8ee-265d18f95d31'
TESTING_APPROVAL = '853a9204-da09-405a-856f-2725eb541657'
ARTIFACT_REF = {'id': 'b0d4b5a9-3b86-46d3-9e7e-67268a2f3897',
                'sha256': '4ed6a218b8c4eda2f1e6b5b25a9df9025c3b0025efe48d34d2d3f40f15337e11'}
PREDECESSOR = {'sequence': 1,
               'sha256': '207d41a387a793d5fea113dd2f020de12493d482d8556ae88e3c9f71c3db38db'}
SCOPE = {'action': 'upgrade', 'environment': 'development',
         'expected_start': '0001_migration_baseline', 'target': '0002_state_requests',
         'manifest_hash': '41fff9427895ac584d34664dd1c6400ae5772eb6297910392d98751bfde5710e',
         'revision_hash': 'c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad'}
SNAPSHOT = {
    "audit": {
        "artifact-approval-75755e44-1423-4ffb-8b67-8ebb1a205072.json": "30293bcce535ddee16f8cc4e5d39bff25bebcef4aabaffb6233b30c366a17b01",
        "artifact-approval-b0d4b5a9-3b86-46d3-9e7e-67268a2f3897.json": "4ed6a218b8c4eda2f1e6b5b25a9df9025c3b0025efe48d34d2d3f40f15337e11",
        "authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "6bf6d5b0e282e6ca95a31a389908f897057a5e1cb253ee20fb762e13449607e7",
        "authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "d7a5eeb67b0e9e70a3c16bf58ef830479dc3dd6fdf30b2e06f2e9e00c20b6fb2",
        "authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "7b51d8a86fe6d82863bd86a7450d9063ccd302b18d10c858fb91432fed4db101",
        "claim-development-00000001.json": "207d41a387a793d5fea113dd2f020de12493d482d8556ae88e3c9f71c3db38db",
        "claim-testing-00000001.json": "642c6452a0b2ad6068a2d00534977985d2d081cd787a30489e9772b13075728c",
        "claim-testing-00000002.json": "09a2149025e903a403baac9b89a9e34aaf2a2aa0b6fd1818f83db8d7301166df",
        "completed-authorization-11337b62-98ed-418f-9633-c2b8f6cee097.json": "cb3d08d15a917aa9040f0806fc965feb7049b0bdd2e31a7e60927af08d9e9b39",
        "completed-authorization-25c9bd53-e02c-4ee9-9275-a08134917d2f.json": "a05817e9e23b8fe02d440781560a9150d1bf9685c30c1b0772dc444494dbab7e",
        "completed-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "completed-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "completed-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "completed-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000001.json": "574b8f7f8e9b102ef9e30b95d7e76771e5ca90d70d4dc0913a3d78bc1f98852f",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000002.json": "83568e5f0e603e9b08f5757c6443fc56a9ebb560b4b800f2fed70ad68d6365f2",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000003.json": "98187b3def61298fadabeebe48e66112eef8a9c9c2195a7da9d109568e6cf9ce",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000004.json": "365922b04a761c4bf3d84378ef9560e741495598b95706452b6faef509bbe99e",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000005.json": "0d17ba565d7029e364cc9c8a351d23d910502fe95dc13835f5c91da91d78ae48",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000006.json": "f556c33ed84c00aa948a14c92f0aa51f8d8c5b4ebbacaa88b1c57174062af052",
        "event-009c30b6-87e4-4d86-aa2e-5b36eb91796e-00000007.json": "7f912cfc11889587f3a90ddcb4af3b315632e9f2ca71c9bf0f8f8f60da47ac6c",
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
        "pending-authorization-dcaa8eb1-7a2e-409b-88d3-3fcfdd2c7b86.json": "57919f96df45d5d4a048163f0e21a0ee8b2b1e53ed1dfa5ef4579f4949b7afff",
        "pending-terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "7da1df1cd32d0712ada19262e22dcbf88829aacfc58e38e29952442fc23020d9",
        "pending-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "a44bbd4e3f8ee6d72719cc67a23c79b3dd1b2ed3e9f81668876a350fd596e549",
        "pending-terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "550449395355ab1297c0372c065076221e506167a98ce6c8c633c81dbd5f347a",
        "prerequisite-approval-2c42eb66-2155-4762-8692-a7170512ae3d.json": "6a95a3a8ec1effc8d28524ad0d61338c042bc49a67dd4a93431d4cfa99e1fba2",
        "prerequisite-approval-55fd6fee-b2b2-40fb-bab0-a0c87c35462a.json": "ce89b823c83246e1f464883b6e4123e2cb1989e6a382f8d3192d2b7928090833",
        "prerequisite-approval-853a9204-da09-405a-856f-2725eb541657.json": "b45db8f2c870d462615a51fcefb829f8defe25298c7a11cefa8e2524c0a1551c",
        "prerequisite-attestation-fe53d5d1-8e82-409e-a8ee-265d18f95d31.json": "9e994e1d27ebec0d35796c24885aa633c973afb2b6844bf6260dfe18f5e7c19f",
        "terminal-009c30b6-87e4-4d86-aa2e-5b36eb91796e.json": "c7c4296c78437b63063d0489ee7c672ab14ee3a76783ec233063a6678a264311",
        "terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json": "3bd8e351c6e70a667c9fe430367ca064f14b503112027291b4ec47d2a6b42a27",
        "terminal-cd8521b7-eb3d-412f-8ac1-188cabd04b30.json": "e3114c601e7d8aa0cc0ff65664c32eedf4322dbc2b5be593fabdbf6763421a04"
    },
    "repository": {
        "alembic.ini": "c72a8cc54828755974765ab8df60c03744cd448b7d16bed81b1157569548f736",
        "docs/WEBSITE_PLAN.md": "323959c0eba86180fc0a179fa4c630777b49112baeb5ebd412b07f7399f1cbb5",
        "docs/WORKFLOW.md": "73933b55df18de08808128cc1b66b325744b6ac66b74ff8163d37f927478f005",
        "migrations/env.py": "09fcd94121f9ba0287d33d9b779f2b7845be56f23fea23aaafb5ae891fe661d4",
        "migrations/manifest.json": "c980c802702a8fe4c83fe4de8523f974dae154c37434ceb300154634c75605a4",
        "migrations/script.py.mako": "ed31327e01d48ec1ba1e91f5dc5b347fed7e9a8c9733b50d49c8085e86815bdc",
        "migrations/versions/0001_migration_baseline.py": "bb51b33f3e064a02b8463593440820d65d01537f48a46b487b7cc327f0ea89a3",
        "migrations/versions/0002_state_requests.py": "c450ca44b71b8fa830e9fc231412f786952133d02ac8eb9db065fdb521fe01ad",
        "oaf_website/__init__.py": "ad4cfd8e9137a2e69abe6fdad18114a9918fccf918cbe59e181a9edd78436eb5",
        "oaf_website/database_config.py": "bffc9d41024c7d562944d67c55cff254e63c0f5c83f54ec4b2384c64ab51ed60",
        "oaf_website/migrate.py": "706a6fefaca086f43bd2729c1cafefdb5bfe3bbd2f71e7a404e2e922454ae1e0",
        "oaf_website/migration_authority.py": "120270246bafd7b86daf5e8f8b696153725b949b901b6a14b4bcc3e39ee37af9",
        "oaf_website/migration_config.py": "9c537cceaed6c84b3050f4db0a2510e6588e4259e927b35322e86cab91ab3587",
        "oaf_website/migration_validation.py": "4f284e509574a27a3b56194cbad60b6fa929f1f77e2c2c7a650ac3c8a8e5d542",
        "oaf_website/state_request_schema.py": "440924c43651c6b7d1e5c8745de705dd0ceeb589eb10422e805131ede51f9647",
        "oaf_website/state_request_validation.py": "a04e8a50bf353dd1de03a3f310445adb9392a33d0ae8c441ebd877d03d32db5d",
        "ops/local_postgres_bootstrap/01_roles.sql": "cf314c1c946564282262564befb6831b49289f4280352d998a4da7bc7f0f0c3b",
        "ops/local_postgres_bootstrap/02_dev_schema.sql": "8392d858d61cd609c97a3cd2211bcec005601accd87b2b162faa17db6a339338",
        "ops/local_postgres_bootstrap/04_verify.sql": "848220a0bd24a4a8c1ee24aeb315728fba92ea23b0c309dbe47580e7af57427d",
        "requirements-migrations.txt": "3154eef6a20748636332276d9a39e13b1d03585df55ab681b706362d294de33e",
        "requirements.txt": "3f8e4f324231e88e0c7a9e1be05c9a26be0a1d5628a5b9947b2ee7794b96fb9d",
        "tests/test_migration_operational.py": "bbde79df63f41b2be68fa100c6f1a138d3865c567f4f5e078e1b26fdf2c5e3a8",
        "tests/test_state_request_migration.py": "d7c05bea36a61a393f66d2fa13a0f95922a89331acaa1b2c859f89799a44d260",
        "tests/test_state_requests.py": "5bcb57dce96ddcd14018c8ff8913147fe853fe78a5e3b3ef9f3600b87994f048"
    }
}
NEW_NAMES = {f'prerequisite-attestation-{ATTESTATION_ID}.json',
             f'prerequisite-approval-{APPROVAL_ID}.json'}
PREFLIGHT = {
    'source': 'owner_supplied_completed_development_read_only_preflight_in_task',
    'status': 'PASS', 'database': 'oaf_website_dev',
    'login': 'oaf_website_dev_migrator', 'effective_role': 'oaf_website_dev_schema_owner',
    'revision': '0001_migration_baseline', 'version_rows': 1,
    'state_requests_table': 'ABSENT', 'read_only': 'YES',
    'rerun_now': False,
    'assurance': 'Completed result supplied by owner; no invented run UUID, timestamp or signed evidence file.'
}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def deny_external_access(*args, **kwargs):
    raise RuntimeError('Database, network and credential access are outside this record-only checkpoint.')


def safe_path(path, directory=False):
    require(path.is_absolute() and path.resolve() == path, 'Missing or redirected absolute path.')
    for component in (path, *path.parents):
        require(not component.is_symlink() and
                not (getattr(component.lstat(), 'st_file_attributes', 0) & 0x400), 'Redirected path component.')
    require(path.is_dir() if directory else path.is_file(), 'Required evidence path unavailable.')


def byte_hash(path):
    safe_path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_modules():
    require(os.name == 'nt' and Path.cwd() == REPO, 'Use the specified native Windows website repository.')
    safe_path(REPO, directory=True)
    require(sys.version_info[:2] == (3, 11), 'Existing website Python 3.11 is required.')
    require(Path(sys.executable) == REPO / '.venv/Scripts/python.exe', 'Unexpected Python interpreter.')
    # Bootstrap module bytes are checked BEFORE importing the trusted validators.
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Reviewed repository evidence changed: ' + name)
    socket.create_connection = deny_external_access
    socket.socket.connect = deny_external_access
    socket.socket.connect_ex = deny_external_access
    import sqlalchemy
    import psycopg
    import keyring
    sqlalchemy.create_engine = deny_external_access
    sqlalchemy.engine.create_engine = deny_external_access
    psycopg.connect = deny_external_access
    psycopg.Connection.connect = deny_external_access
    keyring.get_password = deny_external_access
    keyring.set_password = deny_external_access
    keyring.delete_password = deny_external_access
    from oaf_website import database_config as db
    db._windows_password = deny_external_access
    from oaf_website import migration_authority as authority
    authority.issue_authorization = deny_external_access
    authority._publish_completion = deny_external_access
    from oaf_website import migration_validation as validation
    from oaf_website.migration_config import IDENTITIES
    return authority, validation, IDENTITIES


def audit_root():
    local = os.environ.get('LOCALAPPDATA')
    require(bool(local) and Path(local).is_absolute(), 'LOCALAPPDATA must be an absolute existing directory.')
    root = Path(local) / 'OAF Website/BootstrapAudit/MigrationAudit'
    safe_path(root, directory=True)
    require(root == Path(r'C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit\MigrationAudit'),
            'Unexpected established MigrationAudit destination.')
    return root


def evidence_map():
    result = {}
    for name, digest in SNAPSHOT['repository'].items():
        result[name] = {'location': 'repository', 'hash_mode': 'exact_bytes', 'sha256': digest}
    for name, digest in SNAPSHOT['audit'].items():
        result['MigrationAudit/' + name] = {'location': 'MigrationAudit', 'hash_mode': 'exact_bytes', 'sha256': digest}
    return result


def categories():
    previous = 'MigrationAudit/prerequisite-attestation-' + TESTING_ATTESTATION + '.json'
    testing = 'MigrationAudit/terminal-' + TESTING_RUN + '.json'
    completed = 'MigrationAudit/completed-terminal-' + TESTING_RUN + '.json'
    def category(statement, references):
        return {'applicability': 'approved_for_exact_development_transition',
                'statement': statement, 'evidence': references + [previous, testing, completed]}
    return {
        'dependency_acceptance': category(
            'The accepted exact pinned toolchain and revision-specific offline evidence apply to DEVELOPMENT. '
            'The successful same-artifact TESTING 0002 run demonstrates migration toolchain execution and exact '
            'postconditions there. DEVELOPMENT uses the existing website interpreter and PostgreSQL 17 at '
            '127.0.0.1:5432. No dependency installation, version change or new compatibility experiment is performed.',
            ['requirements.txt', 'requirements-migrations.txt', 'docs/WORKFLOW.md',
             'tests/test_state_request_migration.py', 'tests/test_state_requests.py']),
        'bootstrap_validation': category(
            'The completed DEVELOPMENT read-only preflight supplied by the owner reports PASS, database '
            'oaf_website_dev, authenticated login oaf_website_dev_migrator, effective '
            'oaf_website_dev_schema_owner, exactly one 0001_migration_baseline row and absent state_requests. '
            'Published completed DEVELOPMENT baseline evidence independently supports ordinary continuation at 0001. '
            'The existing database owner remains oaf_website_owner; schema and managed-object ownership is '
            'oaf_website_dev_schema_owner; matching runtime is oaf_website_app. Matching database CONNECT and '
            'schema USAGE, restricted migrator SET ROLE membership, restrictive defaults, no runtime schema CREATE '
            'and no metadata access remain required runtime authority checks. This checkpoint does not claim '
            'a fresh live ACL inspection beyond the supplied preflight.',
            ['owner_supplied_development_preflight', 'MigrationAudit/claim-development-00000001.json',
             'MigrationAudit/terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json',
             'MigrationAudit/completed-terminal-aeb43928-be3b-44e5-9fa0-2527761fc9e3.json',
             'oaf_website/migration_config.py', 'oaf_website/migration_validation.py',
             'ops/local_postgres_bootstrap/01_roles.sql', 'ops/local_postgres_bootstrap/02_dev_schema.sql',
             'ops/local_postgres_bootstrap/04_verify.sql']),
        'lock_and_timeouts': category(
            'The same reviewed runner controls apply in oaf_website_dev: database-scoped session advisory lock '
            '(0x4F414657, 4), acquisition bounded to 5 seconds with a 5-second acquisition-query timeout, '
            '5-second lock_timeout and 60-second statement_timeout. Lock survival across setup rollback and '
            'the same backend are verified; the session lock spans commit and independent postcommit validation. '
            'Runner and Alembic recheck controls. Existing completed runs record release_confirmed. '
            'No new DEVELOPMENT contention or timeout exercise is asserted.',
            ['oaf_website/migrate.py', 'migrations/env.py', 'oaf_website/migration_validation.py',
             'tests/test_state_request_migration.py']),
        'search_path_and_postconditions': category(
            'Use pg_catalog, oaf_website, pg_temp and schema-qualified objects under '
            'oaf_website_dev_schema_owner. 0002 must retain the exact baseline metadata and advance exactly one '
            'alembic_version row to 0002_state_requests. Add only state_requests, its state_requests_pk '
            'primary key/index, state_requests_state_check, created_at default, row type and array type. '
            'Require non-null state varchar(2), browser_key uuid, created_at timestamptz DEFAULT CURRENT_TIMESTAMP; '
            'primary key (state, browser_key), exact 50-state check and exact btree definition. '
            'Grant only SELECT/INSERT to oaf_website_app without grant options; no UPDATE/DELETE/TRUNCATE or '
            'other nonowner data privileges, no runtime metadata privileges, no PUBLIC data/schema exposure '
            'and no testing-role grants. Request row type has explicit owner-only USAGE; its array follows '
            'the element ACL, with no PUBLIC/runtime USAGE. Preserve the baseline generated-type exception '
            'only for alembic_version/_alembic_version. Verify exact catalog inventory, ownership, dependency '
            'edges, absence of extra objects/extension membership, no nonowner grant options, and restrictive '
            'global/schema defaults before commit and again after commit. TESTING completion proves these '
            'checks for the same artifacts in TESTING; DEVELOPMENT 0002 postconditions await separate execution.',
            ['migrations/manifest.json', 'migrations/env.py', 'oaf_website/migration_validation.py',
             'oaf_website/state_request_schema.py', 'oaf_website/state_request_validation.py',
             'tests/test_state_request_migration.py']),
        'recovery_procedure': category(
            'The exact DEVELOPMENT sequence-1 predecessor has completed consistent acknowledged-commit and '
            'postcommit-pass evidence, so expected_start=0001_migration_baseline and '
            'owner_reconciliation=not_applicable are applicable. The supplied read-only preflight agrees. '
            'Preserve claims and acknowledged commits. Stop on uncertainty, incomplete/contradictory evidence '
            'or postcommit audit failure; exact-predecessor owner reconciliation is mandatory for exceptional '
            'outcomes. No blind retries, claim deletion, downgrade, stamp, repair or credential rotation. '
            'The testing run remains a valid same-artifact successful 0002 citation under the Stage 5 '
            'successor-chain validator. Every future operation needs distinct owner issuance; this approval '
            'neither issues nor reuses execution authority.',
            ['owner_supplied_development_preflight', 'MigrationAudit/claim-development-00000001.json',
             'docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migrate.py',
             'oaf_website/migration_authority.py', 'tests/test_migration_operational.py']),
        'audit_policies': category(
            'Owner-approved policies A-D apply to this exact DEVELOPMENT transition: exclusive UTF-8/LF '
            'MigrationAudit records with flush/fsync; retain all history until separate archival approval; '
            'distinct bounded environment/artifact/prerequisite/predecessor-bound owner authorization; '
            'fail-closed persistence and uncertainty handling. Published completion is mandatory for '
            'authorization and terminal evidence. This record-only checkpoint uses exclusive approval '
            'writes and preserves partial writes without retry or cleanup. No new artifact approval or '
            'migration authorization is issued. Reviewer UUIDs and hashes are local administrative '
            'references; no signatures, cryptographic identity proof or new independent review action is claimed.',
            ['docs/WORKFLOW.md', 'docs/WEBSITE_PLAN.md', 'oaf_website/migration_authority.py'])
    }


def common_checks(root, authority, validation, identities, saved):
    expected_names = set(SNAPSHOT['audit']) | (NEW_NAMES if saved else set())
    require({p.name for p in root.glob('*.json')} == expected_names,
            'Audit inventory changed or a target record already exists; stop without retry.')
    for name, expected in SNAPSHOT['audit'].items():
        require(byte_hash(root / name) == expected, 'Reviewed audit evidence changed: ' + name)
    for name, expected in SNAPSHOT['repository'].items():
        require(byte_hash(REPO / name) == expected, 'Reviewed repository evidence changed: ' + name)
    validation.validate_artifacts(**{key: SCOPE[key] for key in
        ('expected_start', 'target', 'manifest_hash', 'revision_hash')})
    now = datetime.now(timezone.utc)
    artifact = authority._reference(root, 'artifact-approval', ARTIFACT_REF)
    authority._approval(artifact, 'artifact_approval', ARTIFACT_REF, {'manifest_hash', 'revision_hash'}, now)
    require(artifact['reviewer_id'] == REVIEWER, 'Established artifact reviewer identity changed.')
    require(all(artifact[key] == SCOPE[key] for key in ('manifest_hash', 'revision_hash')),
            'Existing approved artifact scope differs.')
    require(authority._previous(root, 'development') == PREDECESSOR, 'DEVELOPMENT predecessor changed.')
    require(authority._ordinary_predecessor(root, 'development', PREDECESSOR, SCOPE['expected_start']),
            'DEVELOPMENT predecessor requires reconciliation.')
    authority._testing_validation(root, SCOPE, TESTING_RUN)
    identity = identities['development']
    require((identity.database, identity.migrator, identity.owner, identity.runtime,
             identity.schema, identity.host, identity.port, identity.postgres_major) ==
            ('oaf_website_dev', 'oaf_website_dev_migrator', 'oaf_website_dev_schema_owner',
             'oaf_website_app', 'oaf_website', '127.0.0.1', 5432, 17), 'DEVELOPMENT identity differs.')
    old, _ = authority._read(root / f'prerequisite-attestation-{TESTING_ATTESTATION}.json')
    previous, _ = authority._read(root / f'prerequisite-approval-{TESTING_APPROVAL}.json')
    require(old['id'] == TESTING_ATTESTATION and old['kind'] == 'prerequisite_applicability_attestation'
            and old['decision'] == 'approved' and old['environment'] == 'testing'
            and old['reviewer_id'] == REVIEWER and set(old['categories']) == authority.PREREQUISITES,
            'Existing reviewed six-category TESTING attestation differs.')
    require(all(old[key] == SCOPE[key] for key in ('expected_start', 'target', 'manifest_hash', 'revision_hash')),
            'Existing TESTING applicability artifacts differ.')
    require(previous['approvals'] == {key: TESTING_ATTESTATION for key in authority.PREREQUISITES},
            'Existing TESTING category references differ.')
    return now


def build_records(approved_utc):
    common = {'format': 1, 'reviewer_id': REVIEWER, 'approved_utc': approved_utc,
              'decision': 'approved', 'environment': SCOPE['environment'],
              'expected_start': SCOPE['expected_start'], 'predecessor': PREDECESSOR,
              'owner_reconciliation': 'not_applicable', 'testing_validation_run': TESTING_RUN}
    attestation = dict(common, kind='prerequisite_applicability_attestation', id=ATTESTATION_ID,
        artifact_approval_id=ARTIFACT_REF['id'], artifact_approval=ARTIFACT_REF,
        prerequisite_approval_id=APPROVAL_ID, target=SCOPE['target'],
        manifest_hash=SCOPE['manifest_hash'], revision_hash=SCOPE['revision_hash'],
        categories=categories(), revision_specific_evidence=evidence_map(),
        owner_supplied_development_preflight=PREFLIGHT,
        development_identity={'database': 'oaf_website_dev', 'database_owner': 'oaf_website_owner',
            'login': 'oaf_website_dev_migrator', 'effective_role': 'oaf_website_dev_schema_owner',
            'schema': 'oaf_website', 'schema_owner': 'oaf_website_dev_schema_owner',
            'application_role': 'oaf_website_app', 'host': '127.0.0.1', 'port': 5432, 'postgres_major': 17},
        approval_basis={
            'authority': 'explicit_owner_approval_for_development_record_only_checkpoint',
            'statement': 'Owner approved DEVELOPMENT applicability recording using the existing reviewed '
                         'artifacts and six-category TESTING evidence, completed DEVELOPMENT read-only '
                         'preflight and successful same-artifact TESTING 0002 completion.',
            'reviewer_identity': 'existing_verified_local_reviewer_uuid',
            'assurance': 'Administrative recording under explicit owner approval; no new independent '
                         'review action, signature or cryptographic identity proof.'},
        validation_boundary={
            'existing_testing_0002_validation': 'published_completed_consistent_same_artifact_run',
            'development_baseline_validation': 'published_completed_baseline_plus_owner_supplied_preflight',
            'development_0002_postconditions': 'required_at_future_separately_authorized_execution',
            'independent_review_performed_now': False, 'offline_checks_rerun_now': False,
            'new_artifact_approval_issued': False, 'migration_authorization_issued': False,
            'postgresql_or_credential_access_performed_now': False})
    approval = dict(common, kind='prerequisite_approval', id=APPROVAL_ID,
                    approvals={key: ATTESTATION_ID for key in categories()})
    return attestation, approval


def encoded(record):
    return (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def validate_documents(attestation, approval, authority, now):
    require(authority._uuid(ATTESTATION_ID) and authority._uuid(APPROVAL_ID)
            and ATTESTATION_ID != APPROVAL_ID, 'Invalid new record UUIDs.')
    require(attestation == build_records(attestation['approved_utc'])[0], 'Attestation fields or evidence differ.')
    require(approval == build_records(attestation['approved_utc'])[1], 'Prerequisite approval fields differ.')
    authority._approval(approval, 'prerequisite_approval', {'id': APPROVAL_ID},
        {'environment', 'expected_start', 'approvals', 'predecessor',
         'owner_reconciliation', 'testing_validation_run'}, now)
    require(set(attestation['categories']) == authority.PREREQUISITES, 'All six categories are required.')
    require(approval['approvals'] == {key: ATTESTATION_ID for key in authority.PREREQUISITES},
            'Every category must reference the new DEVELOPMENT attestation.')
    require(authority._utc(attestation['approved_utc']) <= now, 'Future approval time.')
    for category in attestation['categories'].values():
        require(category['applicability'] == 'approved_for_exact_development_transition', 'Wrong applicability.')
        for reference in category['evidence']:
            require(reference == 'owner_supplied_development_preflight' or
                    reference in attestation['revision_specific_evidence'], 'Unbound category evidence.')
    for record in (attestation, approval):
        require(len(encoded(record)) <= 64000, 'Record exceeds Stage 5 read limit.')


def print_results(root, attestation, approval, authority, independently_verified=False):
    for label, prefix, record in [('Attestation', 'prerequisite-attestation', attestation),
                                 ('Prerequisite approval', 'prerequisite-approval', approval)]:
        path = root / (prefix + '-' + record['id'] + '.json')
        print(label + ' UUID: ' + record['id'])
        print(label + ' path: ' + str(path))
        print(label + ' SHA-256 (exact bytes): ' + byte_hash(path))
    print('Approval UTC: ' + approval['approved_utc'])
    print('Categories: ' + ', '.join(sorted(authority.PREREQUISITES)))
    print('Testing validation run: ' + TESTING_RUN)
    print('Predecessor: sequence=1 sha256=' + PREDECESSOR['sha256'])
    print('owner_reconciliation=not_applicable; expected_start=0001_migration_baseline')
    print('Verification: ' + ('PASS in a separate read-only Python process.' if independently_verified
                             else 'Saved; separate read-only verification is required.'))


def main(mode):
    authority, validation, identities = prepare_modules()
    root = audit_root()
    now = common_checks(root, authority, validation, identities, saved=(mode == 'verify'))
    if mode == 'inspect':
        attestation, approval = build_records(now.isoformat())
        validate_documents(attestation, approval, authority, now)
        require(now.timestamp() >= (root / 'claim-development-00000001.json').stat().st_mtime,
                'Approval time predates DEVELOPMENT predecessor.')
        print('Read-only guards: PASS; approved artifacts and reviewed evidence match.')
        print('Stage 5 DEVELOPMENT continuation and published TESTING 0002 validation: PASS.')
        print('DEVELOPMENT applicability: all six categories reviewed and bound to evidence.')
        print('Proposed attestation UUID: ' + ATTESTATION_ID)
        print('Proposed prerequisite approval UUID: ' + APPROVAL_ID)
        print('Records remain UNSAVED until the owner runs this script without -ValidateOnly.')
    elif mode == 'create':
        # Actual approval time is taken at the save checkpoint, never preassigned.
        now = datetime.now(timezone.utc)
        attestation, approval = build_records(now.isoformat())
        validate_documents(attestation, approval, authority, now)
        require(now.timestamp() >= (root / 'claim-development-00000001.json').stat().st_mtime,
                'Approval time predates DEVELOPMENT predecessor.')
        common_checks(root, authority, validation, identities, saved=False)
        first = root / f'prerequisite-attestation-{ATTESTATION_ID}.json'
        second = root / f'prerequisite-approval-{APPROVAL_ID}.json'
        # _save is the existing exclusive UTF-8/LF + flush/fsync Stage 5 writer.
        authority._save(first, attestation)
        require(first.read_bytes() == encoded(attestation), 'Saved attestation bytes differ; stop.')
        authority._save(second, approval)
        require(second.read_bytes() == encoded(approval), 'Saved approval bytes differ; stop.')
        print_results(root, attestation, approval, authority)
    elif mode == 'verify':
        first = root / f'prerequisite-attestation-{ATTESTATION_ID}.json'
        second = root / f'prerequisite-approval-{APPROVAL_ID}.json'
        attestation, attestation_hash = authority._read(first)
        approval, approval_hash = authority._read(second)
        validate_documents(attestation, approval, authority, now)
        require(first.read_bytes() == encoded(attestation) and second.read_bytes() == encoded(approval),
                'Saved files are not exact canonical UTF-8/LF bytes.')
        require(byte_hash(first) == attestation_hash and byte_hash(second) == approval_hash,
                'Independent exact-byte digest disagreement.')
        authority._approvals(root, SCOPE, ARTIFACT_REF, {'id': APPROVAL_ID, 'sha256': approval_hash},
                             PREDECESSOR, now)
        common_checks(root, authority, validation, identities, saved=True)
        print_results(root, attestation, approval, authority, independently_verified=True)
        print('Record-only checkpoint: PASS. All prior evidence is preserved.')
    else:
        raise RuntimeError('Unsupported mode.')


try:
    require(len(sys.argv) == 2 and sys.argv[1] in {'inspect', 'create', 'verify'}, 'Expected one bounded mode.')
    main(sys.argv[1])
except BaseException as error:
    # No raw provider/SQL error text or traceback is emitted.
    classification = getattr(error, 'classification', None)
    detail = classification if classification else (str(error) if type(error) is RuntimeError else type(error).__name__)
    print('BLOCKED: ' + detail)
    print('Stop. Preserve any existing/partial records. Do not rerun creation after an uncertain outcome.')
    raise SystemExit(2)
'@

function Invoke-TaskPython([string]$Mode) {
    $taskPythonCode | & $taskPython -B - $Mode 2>&1 | ForEach-Object { Write-TaskLine ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw ('Record-only ' + $Mode + ' failed; stop without retry.') }
}

try {
    Write-TaskLine 'OAF WEBSITE - DEVELOPMENT 0002 PREREQUISITE RECORDING'
    Write-TaskLine ('Started UTC: ' + [DateTime]::UtcNow.ToString('o'))
    Write-TaskLine 'Scope: current OAF Website repository; two MigrationAudit records only.'
    if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion -lt [Version]'5.1') {
        throw 'Run with existing Windows PowerShell 5.1.'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Native Windows is required.' }
    if ([IO.Path]::GetFullPath((Get-Location).Path) -cne $taskRoot) { throw 'Run from the specified OAF Website repository.' }
    if ([IO.Path]::GetFullPath($PSScriptRoot) -cne (Join-Path $taskRoot 'ops')) { throw 'Unexpected script location.' }
    if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) { throw 'Existing website interpreter is unavailable.' }
    if (-not $env:LOCALAPPDATA -or -not [IO.Path]::IsPathRooted($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is unavailable.' }
    $taskAudit = Join-Path $env:LOCALAPPDATA 'OAF Website\BootstrapAudit\MigrationAudit'
    $taskAttestationPath = Join-Path $taskAudit ('prerequisite-attestation-' + $taskAttestationId + '.json')
    $taskApprovalPath = Join-Path $taskAudit ('prerequisite-approval-' + $taskApprovalId + '.json')
    if (-not (Test-Path -LiteralPath $taskAudit -PathType Container)) { throw 'Existing MigrationAudit directory is unavailable.' }
    # ValidateOnly deliberately leaves clipboard and alert UI untouched.
    if (-not $ValidateOnly) {
        $taskProfile = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
        if (-not (Test-Path -LiteralPath $taskProfile -PathType Leaf)) { throw 'Existing OAF alert profile is unavailable.' }
        . $taskProfile
        if (-not (Get-Command Show-OAFPowerShellAlert -CommandType Function -ErrorAction SilentlyContinue)) {
            throw 'Existing Show-OAFPowerShellAlert function is unavailable.'
        }
        $taskAlertReady = $true
        if (-not (Get-Command Set-Clipboard -ErrorAction SilentlyContinue)) { throw 'Existing clipboard support is unavailable.' }
    }
    if ($VerifyOnly) {
        Invoke-TaskPython 'verify'
    } else {
        Invoke-TaskPython 'inspect'
        if (-not $ValidateOnly) {
            Invoke-TaskPython 'create'
            # Fresh process: reread both files, their exact bytes, every evidence
            # reference and all six category bindings; run Stage 5 _approvals.
            Invoke-TaskPython 'verify'
        }
    }
    if (-not $ValidateOnly) {
        # Independent native PowerShell byte hashes must agree with the Python report.
        foreach ($taskPath in @($taskAttestationPath, $taskApprovalPath)) {
            $taskHash = (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not ($taskLines -contains ('Attestation SHA-256 (exact bytes): ' + $taskHash)) -and
                -not ($taskLines -contains ('Prerequisite approval SHA-256 (exact bytes): ' + $taskHash))) {
                throw 'PowerShell and Python saved-record byte hashes disagree.'
            }
            Write-TaskLine ('PowerShell exact-byte SHA-256 PASS: ' + $taskHash)
        }
    }
    $taskExitCode = 0
    Write-TaskLine $(if ($ValidateOnly) { 'READ-ONLY VALIDATION: PASS; recording remains pending.' } else { 'RESULT: PASS' })
} catch {
    Write-TaskLine ('RESULT: BLOCKED - ' + $_.Exception.Message)
    $taskExitCode = 2
    Write-TaskLine 'Stop without retry. Existing records and partial writes must remain intact.'
    if ($taskAudit) {
        foreach ($taskPath in @($taskAttestationPath, $taskApprovalPath)) {
            if ($taskPath) {
                Write-TaskLine ('Target path: ' + $taskPath)
                try {
                    if (Test-Path -LiteralPath $taskPath -PathType Leaf) {
                        Write-TaskLine ('Retained bytes SHA-256 (not approval verification): ' +
                            (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash.ToLowerInvariant())
                    } else { Write-TaskLine 'Target record: ABSENT' }
                } catch { Write-TaskLine 'Target record outcome: UNCERTAIN; inspect read-only before further action.' }
            }
        }
    }
} finally {
    Write-TaskLine ('Finished UTC: ' + [DateTime]::UtcNow.ToString('o'))
    if (-not $ValidateOnly) {
        Write-TaskLine 'Clipboard: copying this complete report; green/red uses the existing OAF visual alert.'
        $taskClipboardFailure = $null
        try {
            $taskFullReport = $taskLines -join [Environment]::NewLine
            Set-Clipboard -Value $taskFullReport
            if ((Get-Clipboard -Raw).TrimEnd() -cne $taskFullReport.TrimEnd()) { throw 'Clipboard verification failed.' }
        } catch {
            $taskExitCode = 2
            $taskClipboardFailure = $_.Exception.Message
            Write-TaskLine ('RESULT: BLOCKED - report/clipboard: ' + $taskClipboardFailure)
            # Retry only clipboard publication, never record creation or writes.
            try { Set-Clipboard -Value ($taskLines -join [Environment]::NewLine) } catch { }
        }
        if ($taskAlertReady) {
            try {
                $taskAlertStatus = if ($taskExitCode -eq 0) { 'success' } else { 'failure' }
                $taskAlertTitle = 'OAF DEVELOPMENT 0002 PREREQUISITES'
                $taskAlertMessage = if ($taskExitCode -eq 0) {
                    'PASS. Both record UUIDs, exact-byte hashes and paths are in the terminal and clipboard.'
                } else {
                    'BLOCKED. Stop without retry. Check the complete terminal/clipboard report.'
                }
                Show-OAFPowerShellAlert -Status $taskAlertStatus -Title $taskAlertTitle -Message $taskAlertMessage
            } catch {
                $taskExitCode = 2
                Write-TaskLine 'RESULT: BLOCKED - existing visual alert invocation failed.'
                try { Set-Clipboard -Value ($taskLines -join [Environment]::NewLine) } catch { }
            }
        } else {
            $taskExitCode = 2
            Write-TaskLine 'RESULT: BLOCKED - existing OAF visual alert is unavailable.'
            try { Set-Clipboard -Value ($taskLines -join [Environment]::NewLine) } catch { }
        }
    }
}

# Invoke with & as shown in the report; propagate the bounded script result.
exit $taskExitCode
