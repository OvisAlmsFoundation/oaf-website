# DEVELOPMENT integration credential handoff

## Android/iOS Release binding (WU1, 2026-10-26)

The existing ignored `config/local/integrations.toml` now declares:

```toml
[development]
client_id = "gramanna"
release_credential_service = "OAF Website/development/Integrations/Release"
release_credential_account = "gramanna"
```

The existing protected loader requires the exact DEVELOPMENT Release record
when this binding is present. Partial or conflicting bindings fail before any
credential access. Client-only configurations remain compatible with existing
Submission/Reporting operations. Loading the binding does not enable release
intake, processing or provider sending.

ONE owner provisioning procedure, from the OAF Website root in a separate
Windows PowerShell terminal under the existing application Windows user:

```powershell
& .\ops\Set-DevelopmentIntegrationCredentials.ps1 -Operation ProvisionDevelopmentRelease
```

Use a terminal without GraManna activation settings; `OAF_ENV` may be absent or
exactly `development`. This explicit operation creates only the DEVELOPMENT
Release credential for account `gramanna`: Generic Type 1, Persist 2, exactly
64 lowercase hexadecimal characters, canonical UTF-16LE with no BOM or NUL.
It generates a fresh independent 32-byte value internally, accepts no supplied
secret, verifies readback and never exports or prints the value. TESTING,
Submission, Reporting, Brevo, database, webhook and recognition credentials
are not read or modified by this operation. Matching existing Release records
are verified without replacement. A conflicting or uncertain result requires
owner reconciliation before retrying; the existing operator lock and native
create-only recheck are reused. Existing metadata is preserved byte for byte.
The unique sanitized transcript is retained in
`.pytest_cache/development-release-provision-*/execution.log`.

GraManna's accepted source/offline PASS is recorded in its `CHANGELOG.md`
under “Mobile Android/iOS automatic notification handoff” (2026-10-26).
Its existing `app/config.py`, `oaf_interest_service._configuration` and
`mobile_release_handoff._configuration` already define the DEVELOPMENT
interface: `OAF_INTEGRATION_ENVIRONMENT=development`,
`OAF_DEVELOPMENT_ORIGIN=http://127.0.0.1:5055`, and protected process injection
of the corresponding credential as `OAF_DEVELOPMENT_RELEASE_CREDENTIAL`.
Both `OAF_INTEGRATION_ENABLED` and `OAF_RELEASE_HANDOFF_ENABLED` require the
explicit value `1` for a future separately authorized activation. Both remain
OFF here. GraManna must run through its existing trusted DEVELOPMENT launcher
to accept this loopback origin. No GraManna source change is required; no
GraManna runtime/configuration or activation setting is changed by this task.

Provisioning does not inject process credentials, start either application,
approve a mobile release or enable any sender. The older activation procedures
below retain their separately authorized scope.

`ops/Set-DevelopmentIntegrationCredentials.ps1` is an operator helper for Windows
PowerShell 5.1 or later. Run it with `&`, in the terminal that needs the process
settings. It resolves the website paths from its own location, so the current
directory can be GraManna. No GraManna files are changed. The existing website
Python interpreter is required; nothing is installed.

Provision from a separate terminal without GraManna `OAF_*` activation settings:

```powershell
& 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website\ops\Set-DevelopmentIntegrationCredentials.ps1' -Operation Provision
```

This creates two distinct cryptographically random 32-byte values, represented
as 64 lowercase hexadecimal characters, directly in the current Windows user's
Credential Manager. It uses the exact DEVELOPMENT Submission and Reporting
targets documented in the website README, Generic type 1, Local Machine
persistence 2, and the configured `client_id` as the account. Blobs are canonical
UTF-16LE without a BOM or trailing NUL, matching the installed keyring Windows
writer. Only native Windows facilities and Python's standard TOML parser are used.

If absent, the ignored `config/local/integrations.toml` is created with
`[development]` and `client_id = "gramanna"`. An existing valid file, including
its comments and client ID, is preserved byte for byte. Existing complete pairs
are verified and left unchanged; missing halves, missing metadata with existing
credentials, conflicting accounts, types, persistence, encoding or equal secrets
block provisioning. There is no replace, repair, delete or rotation operation.

Only a successful readback of both records and metadata produces a provisioning
success message. Windows does not support an atomic pair write or a create-only
`CredWrite`: this helper takes an exclusive lock for cooperating invocations and
rechecks absence immediately before each write. Keep other Credential Manager
editors and provisioning tools idle. A write/readback failure can leave records
or metadata behind; the failure explicitly requires owner reconciliation. Do not
delete records or rerun blindly after an incomplete result. The ignored
`config/local/integrations.operator.lock` contains no secrets and can remain;
the operating system releases the exclusive handle when the invocation ends.

In the **GraManna DEVELOPMENT PowerShell terminal**, using the same Windows user:

```powershell
& 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website\ops\Set-DevelopmentIntegrationCredentials.ps1' -Operation ActivateReporting
# After the success message, use GraManna's existing DEVELOPMENT interpreter:
python .\dev_app.py
```

Activation reads **only** the reporting record and sets these values in the
current PowerShell process, inherited by subsequent children:

| Setting | Value |
| --- | --- |
| `OAF_INTEGRATION_ENABLED` | `1` |
| `OAF_INTEGRATION_ENVIRONMENT` | `development` |
| `OAF_DEVELOPMENT_ORIGIN` | `http://127.0.0.1:5055` |
| `OAF_DEVELOPMENT_REPORTING_CREDENTIAL` | Protected reporting value, held in process memory |

The submission record is never read or activated by this operation. Provision
must first have verified the complete pair; reporting activation deliberately
cannot certify submission's presence. Conflicting `OAF_ENV`, integration
environment, origin, reporting value or unexpected `OAF_*` settings block the
handoff. Matching reactivation is allowed. Failure leaves the prior process
environment in place; do not start GraManna after a failure. A successful handoff
does not validate database readiness or prove that either application is running.

To activate **both submission and reporting** in the same GraManna DEVELOPMENT
PowerShell terminal, use the already provisioned pair:

```powershell
& 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website\ops\Set-DevelopmentIntegrationCredentials.ps1' -Operation ActivateSharedServices
```

`ActivateSharedServices` sets all four values above plus
`OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL`, using the protected submission value in
process memory. It reads only these exact Credential Manager targets:

| Process credential | Credential Manager target |
| --- | --- |
| `OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL` | `OAF Website/development/Integrations/Submission` |
| `OAF_DEVELOPMENT_REPORTING_CREDENTIAL` | `OAF Website/development/Integrations/Reporting` |

Both records must match the configured DEVELOPMENT `client_id`, Generic type 1,
Local Machine persistence 2 and canonical 64-character lowercase hexadecimal
UTF-16LE format. Their secrets must differ. Missing or inconsistent records,
metadata, environment, origin or existing process credentials block activation.
Both records and all conflicts are checked before changing any process setting;
failure restores the prior values of all five settings, including absent values.
Matching reactivation and upgrading a reporting-only terminal are supported.
The existing `ActivateReporting` operation retains its reporting-only behavior.
Shared activation never provisions, replaces or regenerates credentials, changes
metadata, starts applications or makes submissions. After success, launch GraManna
using its existing DEVELOPMENT interpreter in that same terminal.

Use `&` in the existing terminal; starting a separate `powershell.exe -File`
process would set only that child's environment. No secrets are accepted as
arguments, printed, copied to the clipboard, written to `.env`/TOML/log files, or
persisted as user/machine environment variables. Status and error messages are
fixed text. Do not print environment/credential objects or enable value tracing.
Closing the terminal drops its process settings. For early removal, after
stopping GraManna, run:

```powershell
Remove-Item Env:OAF_DEVELOPMENT_SUBMISSION_CREDENTIAL, Env:OAF_DEVELOPMENT_REPORTING_CREDENTIAL -ErrorAction SilentlyContinue
Remove-Item Env:OAF_INTEGRATION_ENABLED, Env:OAF_INTEGRATION_ENVIRONMENT, Env:OAF_DEVELOPMENT_ORIGIN -ErrorAction SilentlyContinue
```

Local Machine persistence remains scoped to this Windows user on this machine;
other processes running as that user share the existing credential trust boundary.
Activated secrets necessarily exist in GraManna's inherited process memory.

## Offline validation

From the OAF Website root:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\tests\Test-DevelopmentIntegrationCredentials.ps1
```

The standalone harness loads only helper function definitions through the
PowerShell AST, replaces native credential imports and operational randomness
with hard denials before compiling the codec, and uses fixed synthetic values
with an in-memory store. TOML fixtures and the lock/junction checks live in an
isolated temporary directory. It never invokes the helper's operational entry
point, reads private owner configuration, starts an application, contacts a
database or makes a network request. Tests verify permission separation, shared
activation and reporting-only compatibility, rejection of missing/invalid records
and environment conflicts, restoration after an injected post-assignment failure,
and diagnostics containing no synthetic secret/provider markers.

## First live read-only checkpoint (operator only)

1. Provision and obtain the verified success message. Resolve any incomplete
   setup before continuing. This Codex preparation run performs no provisioning.
2. In a separate website terminal, from the website root, run
   `.\ops\Start-DevelopmentWebsite.ps1 -EnableIntegrations -NoBrowser -NoAlert`.
   Its existing runtime and schema permission checks must succeed; this helper
   grants no database permissions and runs no migrations.
3. Activate reporting in the GraManna terminal and start its trusted `dev_app.py`
   using that application's existing DEVELOPMENT interpreter.
4. Make the initial authenticated backend
   `GET http://127.0.0.1:5055/api/integrations/v1/interest-summary` using the
   process reporting credential as a Bearer header, held in memory. Do not type
   the header value into a command or use a browser session. Check HTTP 200 and
   response `environment = development`; retain only non-secret result/status
   details. Do not exercise submission routes during this read-only checkpoint.

No live operation, application startup, database connection, Credential Manager
access or GraManna repository change is part of the offline validation above.


## WU1 Step 3 provisioning reconciliation (2026-10-26)

DEVELOPMENT Release provisioning is **COMPLETED AND VERIFIED**; the earlier
provisioning command is retained as historical procedure, not a pending next
action. Accepted sanitized evidence:
`.pytest_cache/development-release-provision-20261027T032650Z-f713faa0ac0d4116bacf6d597e3a399d/execution.log`.
No credential read, replacement, rotation or repeat provisioning is authorized
by this reconciliation.

GraManna's accepted DEVELOPMENT interface above remains the handoff contract.
The connected synthetic PASS is recorded in
`.pytest_cache/wu1-connected-20261027T033228Z-2573aadb/consolidated-report.txt`;
it does not establish process credential injection, live provider delivery,
scheduler certification or operational activation. **Activation remains OFF.**
Future runtime injection/activation and live certification require their existing
separate operational authorization. See WORKFLOW's WU1 Step 3 record for the
completed migrations, autonomous contract and retained conditional legacy finding.
