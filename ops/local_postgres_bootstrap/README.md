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
