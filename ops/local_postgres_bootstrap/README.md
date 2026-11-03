# Local PostgreSQL bootstrap review files

Checkpoint 4 / Stage 4B: source implementation and offline review only. Stages 1-3
remain CLOSED/PASS and Stage 4A remains PASS as supplied by the owner; this work
does not reopen or independently revalidate them. Nothing here has been run
against PostgreSQL. Implementation approval does not authorize execution.

| File | Purpose |
| --- | --- |
| `01_roles.sql` | Create four restricted NOLOGIN/password-NULL roles and exactly two matching memberships in one cluster-role transaction, connected to development. |
| `02_dev_schema.sql` | Development-only schema, matching CONNECT/USAGE grants and global owner-only defaults in one transaction. |
| `03_test_schema.sql` | The equivalent testing-only transaction. |
| `04_verify.sql` | Read-only checks of shared authority and the selected database's empty bootstrap state; shared preflight/precommit guard for the first three scripts. |

Preconditions: the existing PostgreSQL 17 installation at
`C:\Program Files\PostgreSQL\17\bin\psql.exe`; server **17.11** (`170011`) at
**127.0.0.1:5432**; the approved `postgres` LOGIN superuser must still be the
bootstrap superuser (OID 10). Both existing databases must retain the NOLOGIN
`oaf_website_owner` as owner, allow connections, and have no PUBLIC database
privileges. Existing runtime accounts must be restricted LOGIN roles with only
matching database CONNECT, no database CREATE/TEMP or grant options, no schema
CREATE, no object ownership, no elevated parameter authority, and no unapproved memberships. Existing `public`
ownership/ACLs must remain intact, with no PUBLIC CREATE. The four proposed role
names and both application-schema names must be free as established by the
approved pre-bootstrap inspection. Each schema script checks its own collision
again. If any assumption differs, halt for review; these scripts never repair it.

Only these memberships are accepted (including grantor `postgres`): development
migrator to development schema owner, testing migrator to testing schema owner;
each has INHERIT FALSE, SET TRUE, ADMIN FALSE. All four new roles remain NOLOGIN,
NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, NOBYPASSRLS, NOINHERIT and
PASSWORD NULL. Runtime identities and database ownership are not altered.

After separate execution approval, use a fresh Windows PowerShell 5.1 terminal
in this repository with transcription/terminal recording disabled. Authenticate
only using psql's concealed `-W` administrator password prompt. SQL requests no
credentials and creates no passwords. Never set PGPASSWORD, use a secret-bearing connection
URL, put credentials in arguments/files, echo a password, or capture the prompt.
The commands reject every pre-existing PG* environment override by name without
printing values; use a fresh terminal rather than silently clearing settings.

Run one step at a time: **01, 02, development verification, 03, testing
verification, then development verification again**. Stop on any nonzero exit,
missing commit acknowledgement or failed independent verification. Do not use
`--single-transaction` on 01/02/03: each already owns its transaction. Never
combine them into one psql session or run them concurrently. A schema-owner
SET ROLE is local to the transaction and reset before administrator checks.

Prepare the command variables (no database connection or modification):

```powershell
Set-Location -LiteralPath 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
$ErrorActionPreference = 'Stop'
$psqlExe = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
$bootstrapDir = Join-Path (Get-Location).Path 'ops\local_postgres_bootstrap'
if (-not (Test-Path -LiteralPath $psqlExe -PathType Leaf)) { throw 'Expected psql installation missing' }
if (@(Get-ChildItem Env: | Where-Object { $_.Name -like 'PG*' }).Count -ne 0) {
    throw 'Use a clean terminal with no PG environment overrides'
}
```

**PROPOSED - DO NOT EXECUTE**

**SEPARATE OWNER APPROVAL REQUIRED** (database-modifying step 01):

```powershell
& $psqlExe -X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=oaf_website_dev --file (Join-Path $bootstrapDir '01_roles.sql')
if ($LASTEXITCODE -ne 0) { throw 'Roles failed or outcome uncertain; stop for reconciliation' }
```

**PROPOSED - DO NOT EXECUTE**

**SEPARATE OWNER APPROVAL REQUIRED** (database-modifying step 02):

```powershell
& $psqlExe -X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=oaf_website_dev --file (Join-Path $bootstrapDir '02_dev_schema.sql')
if ($LASTEXITCODE -ne 0) { throw 'Development bootstrap failed or outcome uncertain; stop' }
```

Proposed future read-only development verification (separately approved access;
also repeat after testing completes). The separate fresh transaction enforces
READ ONLY. `bootstrap_preflight=false` requires the completed local schema:

```powershell
& $psqlExe -X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=oaf_website_dev --set=ON_ERROR_STOP=on --set=expected_database=oaf_website_dev --set=bootstrap_preflight=false --single-transaction --command='SET TRANSACTION READ ONLY' --file (Join-Path $bootstrapDir '04_verify.sql')
if ($LASTEXITCODE -ne 0) { throw 'Development verification failed; stop' }
```

**PROPOSED - DO NOT EXECUTE**

**SEPARATE OWNER APPROVAL REQUIRED** (database-modifying step 03):

```powershell
& $psqlExe -X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=oaf_website_test --file (Join-Path $bootstrapDir '03_test_schema.sql')
if ($LASTEXITCODE -ne 0) { throw 'Testing bootstrap failed or outcome uncertain; stop' }
```

Proposed future read-only testing verification (separately approved access):

```powershell
& $psqlExe -X -W --host=127.0.0.1 --port=5432 --username=postgres --dbname=oaf_website_test --set=ON_ERROR_STOP=on --set=expected_database=oaf_website_test --set=bootstrap_preflight=false --single-transaction --command='SET TRANSACTION READ ONLY' --file (Join-Path $bootstrapDir '04_verify.sql')
if ($LASTEXITCODE -ne 0) { throw 'Testing verification failed; stop' }
```

Success requires psql exit 0, the appropriate `BOOTSTRAP_*_COMMIT_ACKNOWLEDGED`
marker following COMMIT, and `BOOTSTRAP_VERIFY_PASS` from independent read-only
verification of **each** database. A precommit pass alone proves no commit.
`bootstrap_preflight=true` is the internal pre-schema mode; its PREFLIGHT_PASS
never proves completed schema setup. The other database's matching migrator
CONNECT may be pending or complete during staged setup. A verifier checks both
database ACLs and ownership dependencies through shared catalogs, but does not
inspect the other database's local schema, objects or default ACLs. Both local
verification runs are mandatory.

On failure before COMMIT, ON_ERROR_STOP terminates psql; closing the fresh
connection rolls back that transaction. Earlier successful transactions remain
committed. A transport failure/cancellation during COMMIT or missing
acknowledgement is **uncertain**, not automatic rollback. Halt, record which
steps were acknowledged, and reconcile through separately authorized read-only
inspection. Do not blindly rerun 01 or recreate a schema: existing names always
halt. Only after verified state and owner-approved continuation may a remaining
step run; destructive recovery or drift correction needs separate authorization.

Keep a sanitized audit record outside Git at an owner-approved destination:
approval reference, reviewed file versions, fixed endpoint/admin/database,
ordered step/phase, preflight/precommit outcomes, exit codes, commit certainty,
separate verification outcomes, and failure/recovery classification. There is
no approved migration revision execution or advisory lock in this bootstrap;
mark both not applicable, rather than inventing outcomes. Record no passwords,
credential-provider errors, private SQL values, environment dumps or secret
URLs. Do not redirect raw psql errors or enable transcripts in the repository.
Only independently reviewed sanitized evidence may accompany an approved Git
checkpoint. Audit persistence, destination, retention and failed-write behavior
are not implemented or approved here; settle the operational evidence procedure
before authorizing execution. Local logs are not tamper-proof against processes
running under the same Windows account. Pre-existing owner-authored notes remain
included at the next approved Git checkpoint unless the owner excludes them.

Deterministic autonomy review: fixed identities, exact membership edges, effective
privilege/ownership checks, collision rejection, native transaction rollback and
explicit commit markers decide ordinary success/failure without AI. Reviewed
sequential commands and fixed evidence fields handle ordering and reporting.
Uncertain commits have a fixed halt-and-reconcile rule, not a retry heuristic.
Owner approval, administrative authentication, exceptional recovery, and choices
of audit destination/retention remain administrative controls. Once approved,
audit-write failure can use a fixed halt-before-next-step rule; no custom approval
engine is needed. Live success, negative paths and rollback still need validation.

Intentionally absent: migrator LOGIN/password activation, HBA changes, credential
provisioning, application objects, Alembic metadata/execution, automatic recovery,
audit infrastructure and production provisioning. Later activation requires
separate HBA/SCRAM review and concealed credential provisioning through the exact
approved Windows backend `keyring.backends.Windows.WinVaultKeyring`, with
services `OAF Website/development/PostgreSQL/Migrations` and
`OAF Website/testing/PostgreSQL/Migrations` and their matching migrator accounts.
Same-Windows-user credential access remains a trust-boundary limitation. The
existing migration validator expects activated migrator LOGIN roles later and
must not be invoked against this intentionally inactive bootstrap state.

Next checkpoint: owner review of these five files, preferably one independent
read-only review of Candidate C authority, PostgreSQL 17 syntax/semantics,
transaction/failure handling, secret handling and commands. Any administrative
execution is a separately authorized follow-up; Stage 5 remains separately gated.
Static checks cannot establish PostgreSQL behavior or operational readiness.

Syntax references: [PostgreSQL 17 GRANT](https://www.postgresql.org/docs/17/sql-grant.html),
[global default privileges](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html),
[shared ownership dependencies](https://www.postgresql.org/docs/17/catalog-pg-shdepend.html),
and [psql error/transaction behavior](https://www.postgresql.org/docs/17/app-psql.html).


## Production two-role compatibility asset (WU1, 2026-11-02)

`07_production_schema.sql` is proposed source only; it is not part of the local
01-06 execution sequence or authority. Local assumptions and scripts remain intact.
Use the existing separately authorized psql bootstrap workflow after independent
exact-artifact review. A local PostgreSQL installation path, loopback endpoint,
`postgres` administrator name and local DEVELOPMENT/TESTING databases are not
production prerequisites. Use the approved external DNS and provider-owner identity
from fixed nonsecret `config/local/production-postgres.toml`; no live values or
executable connection command are supplied by this task.

Preconditions: dedicated existing `oaf_website_prod` owned by the preserved provider
identity; separately provisioned LOGIN/NOINHERIT roles `oaf_website_prod_app` and
`oaf_website_prod_migrator`, no elevated attributes/unapproved membership/ownership;
provider owner can SET ROLE to the migrator; schema absent; required TLS/SCRAM.
Do not use Web/Cron credentials for bootstrap. No role creation, password, database
ownership transfer, feature table or Alembic metadata creation occurs in this asset.

One transaction restricts database ACLs to role-specific CONNECT, temporarily grants
migrator database CREATE, creates its schema and restrictive defaults, grants runtime
USAGE, then revokes CREATE before commit. Provider database ownership and public
schema ownership/ACL are preserved. An error rolls back the whole transaction,
including the temporary grant. A lost COMMIT response requires owner reconciliation;
do not retry automatically. Later independently authorized runner `verify` at base
must establish the full existing catalog/ACL/ownership contract before revision 0001.
Then separately authorize each existing one-revision transition through 0009. Existing
Windows durable evidence, approvals, claims and uncertain-outcome handling apply.

WU2 owner-approved production TLS uses `sslmode=require`, minimum TLS 1.2 and SNI
enabled, retaining existing SCRAM authentication. Windows migrations use the exact
approved Render external hostname; Web/Cron use its private internal endpoint.
Never replace external DNS with a resolved IP; preserve SNI. Restrict external
access to approved operator IP addresses during operational configuration. Require
mode encrypts traffic but does not independently verify server identity. No custom
certificate management is required; plaintext fallback, disable mode and arbitrary
connection overrides are prohibited. See [Render connections](https://render.com/docs/postgresql-creating-connecting).
Operational artifact approval, metadata/credentials, bootstrap/execution authority
and later live validation remain separate activation gates; none occurs here.

References checked as documentation only: [PostgreSQL 17 CREATE SCHEMA](https://www.postgresql.org/docs/17/sql-createschema.html),
[SSL verification](https://www.postgresql.org/docs/17/libpq-ssl.html), and
[privilege inquiries](https://www.postgresql.org/docs/17/functions-info.html).
This source/offline checkpoint does not certify live Render migration compatibility.

## Production restricted LOGIN preparation (2026-11-02)

`08_production_roles.py` is the single owner-operated credential/role entry point.
**Prepared offline only. Do not invoke it under this preparation approval.** It
does not run or replace `07_production_schema.sql`. The accepted Render 17.11
connectivity, two-role compatibility, rollback/absence, IP restriction, WU1/WU2
and source-review evidence is reused; none of those live investigations is rerun.

The helper reuses Step 06's pinned Psycopg/libpq and exact WinVault backend,
machine-local persistence, concealed administrator
prompt, exclusive flushed/fsynced JSON evidence and permanent activation claim.
No dependency or general credential/authorization framework is added. It reads
the existing nonsecret `config/local/production-postgres.toml` through the fixed
migration metadata validator, requiring owner `oaf_website_prod_user`.

Separate protected Generic Credential targets/accounts are:

| Target | Exact account | Reserved use |
| --- | --- | --- |
| `OAF Website/production/PostgreSQL` | `oaf_website_prod_app` | Application runtime credential custody on Windows; later separately provisioned as Render `runtime-db-password`. |
| `OAF Website/production/PostgreSQL/Migrations` | `oaf_website_prod_migrator` | Existing Windows migration loader only. Never supply to Web/Cron. |

Provider administrator authentication is prompted with echo disabled and is
never stored in either target. No passwords are accepted through arguments,
environment, files, command history or clipboard. For a later authorized run,
the helper generates two independent 32-byte `secrets.token_hex(32)` passwords
locally, stores them without keyring's rename/fallback behavior, and checks exact
target/account/type/persistence and canonical UTF-16LE readback. Only locally
derived SCRAM verifiers enter SQL over the required encrypted connection.
Neither plaintext nor verifiers enter OAF audit records or diagnostics; raw
provider errors, SQL commands and tracebacks are never emitted by the helper.

Before authorizing provisioning, the owner must approve the exact displayed
source hashes, external DNS/database/administrator, credential custody and the
existing BootstrapAudit destination/retention/failure policy. Keep evidence until
separately authorized archival/disposal; no automatic deletion. The reference to
that separate role-provisioning approval must be a canonical UUID. Interactive
confirmation records the owner's acknowledgement of existing authority; it does
not issue authorization, authenticate a different human, or authorize bootstrap.
The same Windows account and provider/OS administrators remain trusted.

Role and ACL prerequisites are **not established by this offline work**:

- PUBLIC must already confer no database CREATE/TEMP or schema CREATE (including
  grant options), and the new roles must have no effective elevated parameter
  privileges. Provisioning checks effective authority and halts on drift.
  Standard PostgreSQL database defaults include PUBLIC TEMP. If it is still
  present, `--provision-production` halts before password generation; 07 also
  requires the roles to exist. The owner has approved removing PUBLIC TEMPORARY
  only; the correction operation below prepares that exact ordering fix.
  Provisioning never repairs ACLs or copies/partially runs 07. Other unsafe
  PUBLIC privileges still require a separate owner decision.

The owner-approved managed-provider boundary assigns Render responsibility for
its server infrastructure, internal monitoring/extensions, preload libraries,
server logging and provider-controlled configuration. OAF does not inspect,
reconfigure or independently audit those mechanisms before provisioning roles.
No empty-preload/extension allowlist, server logging setting/readback or SET
authority prerequisite applies to this production procedure. Render and its
administrators remain trusted with the verifier-bearing SQL they receive.
OAF retains independent strong password generation, local SCRAM derivation,
protected Windows credential storage/readback, encrypted connections and sanitized
output/evidence. Effective parameter-privilege checks on the two OAF roles remain
required; they restrict role authority rather than audit provider internals.
Step 05/06 DEVELOPMENT/TESTING confidentiality policies are unchanged.

After those prerequisites and **separate operational authorization**, use a fresh
Windows PowerShell console in this repository, with recording/transcription
disabled, clean PG/database/OAF/TLS/keyring overrides, no redirection and no other
credential/database administration running. The website's existing Python 3.11
environment is required. The proposed single invocation is:

```powershell
& .\.venv\Scripts\python.exe -I -B .\ops\local_postgres_bootstrap\08_production_roles.py --provision-production
if ($LASTEXITCODE -ne 0) { throw 'Production role provisioning stopped; preserve evidence and reconcile before any retry.' }
```

The helper requires the existing approval reference and exact endpoint identity
confirmation before credential access or connection. Before generation/storage
and again before role DDL, it verifies the configured endpoint, SCRAM/TLS,
17.11 server, exact current/session user and provider database ownership, both
role names absent, application schema absent and safe PUBLIC privileges.
No IP substitution, plaintext fallback, existing-role adoption or password
rotation is available. A durable exclusive claim then prevents concurrent or
repeated cooperating runs; WinVault itself has no atomic create-only write, so
other administrators must stay idle.

Both LOGIN roles are created in one transaction with NOSUPERUSER, NOCREATEDB,
NOCREATEROLE, NOREPLICATION, NOBYPASSRLS and NOINHERIT. Neither receives outbound
membership, ownership, schema privileges or database CREATE. PostgreSQL 17's
two implicit creator ADMIN memberships are retained with SET/INHERIT FALSE;
only the migrator has a separate provider-granted SET TRUE, INHERIT/ADMIN FALSE
inbound membership, so the provider can later run 07. Grantors and all three
membership records are checked exactly. Provider attributes/ownership remain.

Success requires an acknowledged COMMIT, a fresh read-only catalog transaction,
exact vault readback and durable final PASS evidence under the existing
`BootstrapAudit/Step08-<execution_id>` destination. It establishes role creation
and matching stored credentials, not application login/service readiness.
07 alone remains authoritative for database CONNECT, application schema ownership
and defaults; later bootstrap, migration verification/execution and runtime
secret-file activation retain their separate authorization and durable-audit gates.

Any failure stops. Evidence distinguishes database rejection before COMMIT,
uncertain COMMIT delivery and acknowledged commit followed by verification/audit
failure. Credential writes independently record not-attempted, uncertain or
verified state. A failed evidence write can leave incomplete records; retain the
last durable phase and claim, treat missing acknowledgements as uncertain, and
reconcile through separately authorized read-only inspection. Closing the session
aborts an uncommitted transaction; there is no COMMIT retry, role/credential
cleanup, claim deletion, or undo of an acknowledged commit. An interruption after
the claim requires owner reconciliation even if no final record was written.
Local evidence is not tamper-proof against the same Windows user.

Focused offline validation uses synthetic approvals, passwords, vault and server;
the early `migration_offline` guard denies real credential/database/network and
operational audit/config access. Run only the changed tests and directly related
production metadata/credential contract tests, never a live helper invocation.
The canonical allowlist includes `tests/test_production_roles.py`; that metadata
addition does not request a full canonical run.

Original preparation validation: **138 focused tests PASS**, with zero unexpected external
access attempts (`tests/test_production_roles.py` and production-selected cases
from `tests/test_migration_config.py`). The bounded independent security review
is **PASS** after correcting PostgreSQL 17 grantor/membership handling, preserving
TLS environment denials, and fixing stderr/LOGIN negative-test coverage.
Reviewed helper SHA-256:
`b955799ac6c03bbfc4b7acf7fac23abde9c564738ce1c5e39bee1b0719722ee1`.
No live operation or real credential/authorization was created. This count/hash
remains historical evidence. Its former provider-inspection prerequisite and next
checkpoint are superseded by the managed-provider boundary above and the accepted
PUBLIC TEMPORARY correction below.

PostgreSQL 17 source references: [CREATE ROLE](https://www.postgresql.org/docs/17/sql-createrole.html),
[creator self grants](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-CREATEROLE-SELF-GRANT),
[logging controls](https://www.postgresql.org/docs/17/runtime-config-logging.html).

## Production PUBLIC TEMPORARY correction (2026-11-02)

**Prepared and validated offline only; no Render connection or REVOKE executed.**
The owner approved removing PUBLIC TEMPORARY on the temporary Render database
`oaf_website_prod`. Accepted evidence is retained without live re-investigation:

| Permission | Accepted before | Required after |
| --- | --- | --- |
| PUBLIC database CONNECT | True | True |
| PUBLIC database CREATE | False | False |
| PUBLIC database TEMPORARY | True | False |
| PUBLIC public-schema USAGE | True | True |
| PUBLIC public-schema CREATE | False | False |

The smallest procedure is the existing `08_production_roles.py` with the explicit
`--revoke-public-temporary` operation. It reuses the fixed metadata, installed
client checks, concealed administrator prompt, TLS/SCRAM connection, identity
checks, source hashes, owner approval reference/confirmation, exclusive flushed/
fsynced audit records and permanent claim policy. It never invokes provisioning,
07, migrations, credential generation or vault reads/writes. Role provisioning uses
the managed-provider confidentiality boundary above; this correction sends no
passwords/verifiers in SQL and does not change logging settings.

For the next owner operation, use the already approved TEMPORARY-only authority
with its canonical UUID reference and reviewed displayed source hashes. Use the
same fresh interactive Windows PowerShell console/interpreter and clean overrides
described above. The existing fixed `config/local/production-postgres.toml` must
identify the approved external DNS and owner `oaf_website_prod_user`; the existing
BootstrapAudit destination must be available, and the owner must supply concealed
administrator authentication. Keep other database/credential administration idle.
The prepared invocation, **not run in this offline phase**, is:

```powershell
& .\.venv\Scripts\python.exe -I -B .\ops\local_postgres_bootstrap\08_production_roles.py --revoke-public-temporary
if ($LASTEXITCODE -ne 0) { throw 'PUBLIC TEMPORARY correction stopped; preserve evidence and reconcile before any retry.' }
```

The scope-specific confirmation is
`AUTHORIZE REVOKE TEMPORARY <approved-external-DNS> oaf_website_prod oaf_website_prod_user`.
The reference acknowledges the existing owner approval; it does not issue a new
approval or authorize roles, credentials, bootstrap, migrations or deployment.

One transaction checks the configured endpoint, exact current/session/database
identities, preserved administrator database ownership, accepted PostgreSQL 17.11,
TLS/SCRAM and all five starting permissions before the sole mutation:

```sql
REVOKE TEMPORARY ON DATABASE oaf_website_prod FROM PUBLIC;
```

NULL ACLs are expanded using PostgreSQL defaults. Before COMMIT, the entire
expanded database ACL must equal its saved starting ACL minus PUBLIC TEMPORARY;
every other grantee, privilege, grantor and grant option remains. Database and
public-schema identities/owners and the entire expanded public-schema ACL must
remain equal. The five resulting permissions, metadata and source hashes are
verified before commit. No REVOKE ALL, CONNECT/CREATE change or schema mutation
is authorized. A COMMIT command acknowledgement, a fresh read-only catalog check
and durable final PASS evidence are required for success.

Evidence uses existing `BootstrapAudit/Step08-public-temporary-<execution_id>`
records, including before/after ACLs and separate uncertain/acknowledged commit
phases. The permanent exclusive claim is
`BootstrapAudit/Step08-production-public-temporary.claim.json`; it is independent
of the role-provisioning claim, so the correction cannot consume provisioning
authority. Retain all evidence/claims under the existing retention policy. Any
failure stops; close aborts an uncommitted transaction. Lost COMMIT replies remain
uncertain even if the server committed. Postcommit verification/audit failures
retain acknowledged commit status. No blind retry, claim deletion, automatic
repair or compensating GRANT is provided; reconcile incomplete/uncertain evidence
through separately authorized read-only inspection under the existing recovery
policy. Role provisioning remains a separate later owner operation.

Focused offline validation uses only `tests/test_production_roles.py` with the
existing early `migration_offline` guards, synthetic connections/ACLs, approvals,
vault and temporary audit paths. It covers exact scope and preservation, identity/
starting-state denials, transactional rollback, ACL drift, audit failures, source/
metadata changes, commit acknowledgement/loss and permanent retry claims. It
rechecks the affected provisioning path; no canonical suite or live readiness
claim is included.

Correction preparation validation: **125 tests PASS**, with zero unexpected
external-access attempts, using only the affected test file. The earlier
provisioning counts, reviewed hash and prerequisite investigation above remain
historical evidence; the accepted five PUBLIC permissions and TEMPORARY-only
owner approval now govern this correction. The next owner operation is the
single correction invocation above, followed by retention/review of its evidence.

## Managed-provider confidentiality simplification (2026-11-02)

**Source/offline PASS.** The owner-approved Render responsibility boundary above
replaces Step 08's provider-internal confidentiality inspection and logging
configuration prerequisites. No replacement provider audit is introduced.
OAF-controlled credential/verifier protections and existing role, TLS, identity,
authorization, durable audit/claim, transaction and recovery behavior remain.

Focused validation: **125 tests PASS**, native exit 0, zero unexpected
external-access attempts, using only `tests/test_production_roles.py` with the
existing early offline guards and synthetic credentials, RNG, vault and database.
Fresh-context independent security review **PASS**, no material finding.
Reviewed helper SHA-256:
`03c7958888c044d1d85a553de50c1d15a13103c6720a51a2a881a23bb6e26278`.
Evidence: `.pytest_cache/render-confidentiality-20261102/REPORT.txt`, focused log,
independent review, task-only diff and preservation identities. Earlier accepted
Render evidence is reused; no provider capability retest or canonical suite ran.
Step 05/06 DEVELOPMENT/TESTING, 07 schema bootstrap and the accepted PUBLIC
TEMPORARY correction executable logic are unchanged. No live provisioning,
credential generation/activation, external connection or Git delivery occurred.
This source review grants no operational artifact approval or execution authority.
The smallest next operational step remains the accepted PUBLIC TEMPORARY
correction under its existing owner approval, in a separate operational phase.

## Production schema execution handoff (2026-11-02)

**Offline preparation only. Do not run under preparation authority.** This
section supersedes the historical next-operation directions above. Reuse the
accepted PUBLIC TEMPORARY correction PASS
(`cf3ab910e8a2458c8c0bc341794e0f84`), restricted LOGIN provisioning and Windows
credential verification PASS (`b66bb955def44307831178b2e7638549`), and WU1/WU2
source/independent review PASS. No repetition of those investigations is needed.

The sole schema procedure remains the unchanged `07_production_schema.sql`.
Its exact-byte SHA-256 is
`cd1262528be07c8b1a75c81f7d9485e35b8df115e6dc424f47778a4c9476f780`.
The operation below uses the existing `psql -X -W --file` method. A preceding
guard in the **same connection** requires the exact administrator/database,
accepted PostgreSQL 17.11 and encrypted TLS 1.2/1.3 session. The SQL retains its
own transaction, role/authority checks, ownership/public-ACL preservation,
temporary CREATE grant/revocation and COMMIT marker. Do not add
`--single-transaction`, change 07, or invoke 08 again.

Before authorizing execution, the owner must approve the exact SQL and this
complete operation through the existing source/artifact review and owner approval
process. Supply the **existing separate schema-bootstrap execution approval UUID**
at the prompt; none is issued by this handoff. That approval must bind the displayed
SQL, handoff and client hashes, fixed external endpoint, database/administrator,
one execution, and the existing BootstrapAudit destination/retention/failure policy.
The accepted provisioning/correction execution IDs are evidence, not this approval.
No migration artifact registry or migration execution authorization is required
for this administrative psql step; later migration-runner operations retain their
own existing gates. A syntactically valid UUID and typed confirmation acknowledge
existing authority; they cannot establish its issuance or scope automatically.

Use a fresh **Windows PowerShell 5.1 ConsoleHost** in this repository, with
transcription, terminal recording and screen capture disabled, no redirection or
pipeline around the complete operation, and no competing database/credential
administration or source edits. The approved operator IP restriction must remain
in force. Have the provider **administrator** password available for psql's one
concealed `Password:` prompt; do not paste it into PowerShell or store it in a
file/environment/URL. Neither restricted-role credential is needed or read.
The nonsecret fixed metadata and installed psql are pinned below; changes require
review rather than editing pins to proceed. No network probe precedes execution.

The single operation uses the existing BootstrapAudit exclusive UTF-8/LF JSON,
flush-to-disk, numbered evidence and permanent claim conventions. Its small inline
writer is the PowerShell equivalent of Step 06/08's `save_json`, not another audit
service or approval registry. The parent must already exist; it is never created
or redirected. Retain all records/claims until separately authorized archival or
disposal. The durable dispatch record conservatively marks the outcome uncertain
before starting psql. Any failed write, interruption, nonzero/unknown exit or
missing COMMIT marker stops the operation. Do not remove the claim, rerun, or
attempt compensating changes; reconcile using separately authorized read-only
inspection. A lost final audit write leaves dispatch uncertainty even if COMMIT
was displayed. Same-Windows-user/OS administrators remain trusted; local evidence
is not tamper-proof and disk flush does not guarantee every hardware failure.

Paste the **entire block once**, only after that separate owner authorization.
It prompts for the approval UUID, then the exact confirmation displayed below,
then psql's concealed administrator password. All endpoints and security settings
are fixed; there is no connection-string or SQL-path input.

```powershell
& {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    $repo = 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or
        $Host.Name -ne 'ConsoleHost' -or [Console]::IsInputRedirected -or [Console]::IsOutputRedirected -or
        [Console]::IsErrorRedirected -or (Get-Location).Path -cne $repo) { throw 'Use the required fresh interactive PowerShell 5.1 console in the repository.' }
    if (@(Get-ChildItem Env: | Where-Object {
        $_.Name -match '^(PG|DB_|DATABASE_|OAF_)' -or
        $_.Name -match 'KEYRING_PROPERTY_' -or $_.Name -in @('SQLALCHEMY_DATABASE_URI', 'PSYCOPG_IMPL', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'SSLKEYLOGFILE', 'PYTHON_KEYRING_BACKEND')
    }).Count) { throw 'Use a clean console without database, OAF, TLS or keyring overrides.' }
    $psqlExe = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
    $sqlPath = Join-Path $repo 'ops\local_postgres_bootstrap\07_production_schema.sql'
    $metadataPath = Join-Path $repo 'config\local\production-postgres.toml'
    $endpoint = 'dpg-dbkd8m8n74is73etoh3g-a.ohio-postgres.render.com'
    $auditRoot = 'C:\Users\ovisa\AppData\Local\OAF Website\BootstrapAudit'
    $claimPath = Join-Path $auditRoot 'Step07-production-schema.claim.json'
    $pins = [ordered]@{
        $sqlPath = 'cd1262528be07c8b1a75c81f7d9485e35b8df115e6dc424f47778a4c9476f780'
        $metadataPath = '84663949b01956f1798602771b2c359d63085b4abd56275489bcef02b5980768'
        $psqlExe = 'c290c7f0a3335f290f8c18011a1e5afa03ee3cdd628697a5f3e767e5f1d3d10d'
    }
    foreach ($path in @($pins.Keys) + @($auditRoot)) {
        $item = Get-Item -LiteralPath $path
        while ($null -ne $item) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected procedure, client, metadata or audit path; stop for review.' }
            $item = if ($item -is [IO.FileInfo]) { $item.Directory } else { $item.Parent }
        }
    }
    if (-not (Test-Path -LiteralPath $auditRoot -PathType Container) -or (Test-Path -LiteralPath $claimPath)) { throw 'Audit destination unavailable or prior schema claim exists; owner reconciliation required.' }
    $sqlLock = [IO.File]::Open($sqlPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        foreach ($pin in $pins.GetEnumerator()) {
            if ((Get-FileHash -LiteralPath $pin.Key -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin.Value) { throw 'Reviewed SQL, metadata or psql bytes changed; stop for review.' }
        }
        $handoffHash = (Get-FileHash -LiteralPath (Join-Path $repo 'ops\local_postgres_bootstrap\README.md') -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "Endpoint=$endpoint`:5432; database=oaf_website_prod; administrator=oaf_website_prod_user"
        Write-Host ("Reviewed pins: " + ($pins | ConvertTo-Json -Compress))
        Write-Host "Handoff README SHA-256=$handoffHash; compare with the existing approval before confirming."
        $approval = Read-Host 'Existing separate schema-bootstrap execution approval UUID'
        $approvalId = [guid]::Empty
        if (-not [guid]::TryParseExact($approval, 'D', [ref]$approvalId) -or $approvalId.ToString('D') -cne $approval -or $approvalId -eq [guid]::Empty) { throw 'Existing canonical approval UUID required.' }
        $confirmation = "AUTHORIZE SCHEMA $endpoint oaf_website_prod oaf_website_prod_user"
        if ((Read-Host "Confirm approved artifacts, one execution and audit policy; type $confirmation") -cne $confirmation) { throw 'Owner acknowledgement missing.' }
        $persist = {
            param($path, $record)
            $bytes = [Text.UTF8Encoding]::new($false).GetBytes((($record | ConvertTo-Json -Depth 6).Replace("`r`n", "`n") + "`n"))
            $stream = $null
            try {
                $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                $stream.Write($bytes, 0, $bytes.Length)
                $stream.Flush($true)
            } catch { throw 'Durable audit write failed; preserve all evidence and hold for owner reconciliation.' }
            finally { if ($null -ne $stream) { $stream.Dispose() } }
        }
        $executionId = [guid]::NewGuid().ToString('N')
        $runDir = Join-Path $auditRoot ("Step07-" + $executionId)
        New-Item -ItemType Directory -Path $runDir | Out-Null
        $state = [ordered]@{
            execution_id = $executionId; operation = 'production_schema_bootstrap'; approval_reference = $approval
            endpoint = "$endpoint`:5432"; database = 'oaf_website_prod'; administrator = 'oaf_website_prod_user'
            source_hashes = $pins; handoff_sha256 = $handoffHash; source_review = 'WU1/WU2 PASS accepted'
            public_temporary_execution_id = 'cf3ab910e8a2458c8c0bc341794e0f84'; roles_execution_id = 'b66bb955def44307831178b2e7638549'
            phase = 'authorized'; commit = 'not_attempted'; psql_exit = $null; verification = 'pending_separate_authorized_verify_at_base'
            migration_revision = 'not_applicable'; advisory_lock = 'not_applicable'; utc = [DateTime]::UtcNow.ToString('o')
        }
        & $persist (Join-Path $runDir '01-authorized.json') $state
        & $persist $claimPath @{ execution_id = $executionId; approval_reference = $approval; database = 'oaf_website_prod'; status = 'owner_reconciliation_required_before_any_retry' }
        $guard = @'
DO $identity$
BEGIN
    IF pg_catalog.current_database() <> 'oaf_website_prod'
       OR current_user <> 'oaf_website_prod_user' OR session_user <> 'oaf_website_prod_user'
       OR pg_catalog.current_setting('server_version_num') <> '170011'
       OR pg_catalog.inet_server_port() <> 5432
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database WHERE datname = 'oaf_website_prod'
           AND pg_catalog.pg_get_userbyid(datdba) = 'oaf_website_prod_user' AND datallowconn AND NOT datistemplate)
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_stat_ssl WHERE pid = pg_catalog.pg_backend_pid()
           AND ssl AND version IN ('TLSv1.2', 'TLSv1.3'))
    THEN RAISE EXCEPTION 'Approved Render bootstrap identity or TLS rejected'; END IF;
END $identity$;
'@
        $connection = "host=$endpoint port=5432 dbname=oaf_website_prod user=oaf_website_prod_user sslmode=require ssl_min_protocol_version=TLSv1.2 sslsni=1 gssencmode=disable require_auth=scram-sha-256 passfile=NUL connect_timeout=10 application_name=OAF-Website-Step07 client_encoding=UTF8"
        $psqlArgs = @('-X', '-W', '--set=ON_ERROR_STOP=on', '--set=ON_ERROR_ROLLBACK=off', '--pset=pager=off', '--dbname', $connection, '--command', $guard, '--file', $sqlPath)
        $state.phase = 'dispatch'; $state.commit = 'outcome_uncertain'; $state.utc = [DateTime]::UtcNow.ToString('o')
        & $persist (Join-Path $runDir '02-dispatch.json') $state
        $commitTag = $false; $commitAcknowledged = $false; $nativeExit = $null
        try {
            & $psqlExe @psqlArgs | ForEach-Object {
                if ($_ -ceq 'COMMIT') { $commitTag = $true }
                if ($commitTag -and $_ -ceq 'BOOTSTRAP_PRODUCTION_SCHEMA_COMMIT_ACKNOWLEDGED') { $commitAcknowledged = $true }
                Write-Host $_
            }
            $nativeExit = $LASTEXITCODE
        } finally {
            $state.psql_exit = $nativeExit
            $state.commit = if ($commitAcknowledged) { 'acknowledged' } else { 'outcome_uncertain' }
            $state.phase = if ($nativeExit -eq 0 -and $commitAcknowledged) { 'schema_commit_acknowledged' } else { 'hold_owner_reconciliation' }
            $state.utc = [DateTime]::UtcNow.ToString('o')
            & $persist (Join-Path $runDir '03-result.json') $state
        }
        if ($nativeExit -ne 0 -or -not $commitAcknowledged) { throw 'Bootstrap failed or outcome uncertain; preserve claim/evidence and reconcile before any retry.' }
        Write-Host "Schema COMMIT acknowledged; execution_id=$executionId; evidence=$runDir. Separate authorized read-only verification at base remains required."
    } finally { $sqlLock.Dispose() }
}
```

Exit 0 plus the SQL's COMMIT marker and durable `03-result.json` establish only
acknowledged schema bootstrap. They do not establish completed production catalog
verification, migrations, application readiness or deployment. A nonzero exit
after acknowledgement retains `commit=acknowledged` and still requires a hold.
An interrupted result write may leave a partial file; retain it and the earlier
durable evidence. Later separately authorized runner `verify` at base must pass
before any revision execution, using its existing approvals and durable evidence.

Offline validation: PowerShell 5.1 AST parsing PASS; installed libpq 17.11
`PQconninfoParse` accepts all 13 fixed options without connecting; native argument
round trip preserves the connection string, guard and SQL path; 18 synthetic
command-boundary cases PASS. Cases cover success/acknowledgement, missing markers
or COMMIT tags, nonzero/unknown exit, invalid approval/confirmation,
environment overrides, SQL/metadata drift, unavailable audit destination,
prior/concurrent claims and each of the four evidence-write failures. SQL file
locking is checked during synthetic dispatch. Native database execution is
replaced before evaluation and all audit writes go to temporary test directories.
The original README prefix is byte-preserved and 07's hash is unchanged.
No Render connection, bootstrap, credential access or operational audit write
is part of validation. Existence/byte checks do not prove future endpoint
availability, administrator authentication, audit writeability or live success.
