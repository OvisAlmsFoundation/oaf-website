# OAF Website

Start the local DEVELOPMENT website from this repository in Windows PowerShell 5.1:

```powershell
.\ops\Start-DevelopmentWebsite.ps1
```

Chrome opens **http://127.0.0.1:5055/gramanna.html** after the runtime checks pass.
Keep the terminal open. Press **Ctrl+C in that terminal** to stop the server;
closing Chrome does not stop it. Startup details are copied to the clipboard,
and the existing OAF visual alert shows readiness or a blocker. For an automated
check without opening Chrome or an alert, use `-NoBrowser -NoAlert`.

The launcher uses the website `.venv` and only `oaf_website_dev` as
`oaf_website_app`, with the existing Windows Credential Manager reference
`OAF Website/development/PostgreSQL`. It rejects a conflicting `OAF_ENV` and
retains the existing fail-closed database configuration and SCRAM identity checks.
Startup checks schema USAGE and State Request SELECT/INSERT permissions using
read-only queries; it performs no migrations or request submissions.
Missing credentials or permissions require separate owner provisioning/approval;
the launcher supplies no replacement identity and changes no grants.

Browser recognition reuses the existing current-user DPAPI-protected key at
`config/local/state-request-recognition.dpapi` (ignored by Git). Keep this file
across restarts; do not delete or replace it. Its shared helper creates a protected
random key once if absent and never uses the database password as the key.
Recognition uses the existing one-year HttpOnly, SameSite=Lax cookie and CSRF/origin
checks. HTTP is explicitly allowed only for this loopback DEVELOPMENT address.
Use the same Chrome profile and address for repeat visits. Clearing cookies,
changing browsers/profiles, or replacing the key permits a new browser identity.
Other processes running as the same Windows user can access its protected secrets.

## Optional DEVELOPMENT shared services

Ordinary startup and the existing F2 task keep integration routes disabled and
do not read integration metadata or credentials. Future explicitly configured
activation uses the same launcher with an optional switch:

```powershell
.\ops\Start-DevelopmentWebsite.ps1 -EnableIntegrations
```

The switch passes `--integrations` to `oaf_website.local_development`. The Python
entry point still requires `OAF_ENV=development`; the PowerShell launcher sets
and restores that variable as before. No additional `OAF_*` variables are
accepted. F2 and the launcher without the switch retain their existing behavior.
This source checkpoint does not configure or launch a real integration.

Before a future authorized activation, supply the ignored **non-secret** file
`config/local/integrations.toml` with exactly this structure:

```toml
[development]
client_id = "gramanna"
```

The client ID must remain stable across credential rotations and match
`[a-z][a-z0-9_-]{0,63}`. The DEVELOPMENT section fixes the environment; TESTING,
PRODUCTION, extra sections/keys, plaintext credential fields and redirects
(including Windows reparse points) are rejected. There are no alternate file
locations or environment-variable overrides in the launcher.

The only supported integration secret locations are these two **Windows
Credential Manager generic credentials**, under the launching Windows user:

| Permission | Exact target | Account/UserName |
| --- | --- | --- |
| Submission | `OAF Website/development/Integrations/Submission` | The configured `client_id` |
| Reporting | `OAF Website/development/Integrations/Reporting` | The configured `client_id` |

Both entries must have generic type (`Type=1`) and local-machine persistence
(`Persist=2`). The existing pinned `keyring.backends.Windows.WinVaultKeyring`
backend reads only the exact targets; it does not try compound `account@target`
names, another environment, another account or another credential backend.
Each externally provisioned credential must be a distinct 32-byte random value
encoded as exactly 64 lowercase hexadecimal characters. Neither may equal the
existing DPAPI recognition key. Do not put credential values in TOML, source,
environment variables, browser code or command arguments. Same-user processes
remain within the existing Windows trust boundary.

Requested activation fails closed if metadata or either protected credential is
missing/invalid, the environment conflicts, or credentials reuse a permission
or recognition key. Startup reports fixed errors without secret values. A valid
configuration is injected into the existing `create_app` and registers:

- `POST /api/integrations/v1/state-requests` (submission credential)
- `POST /api/integrations/v1/notifications` (submission credential)
- `GET /api/integrations/v1/interest-summary` (reporting credential)

Binding and origin remain `http://127.0.0.1:5055`. Integration HTTP requests must
originate on loopback and use backend Bearer authentication without browser
cookies, Origin/Referer or fetch metadata. Existing public APIs, cookie/CSRF
checks, recognition key and public-file allowlist are preserved. Metadata and
protected secrets are never served as public files. Production is deferred.

Focused offline validation (synthetic values only; the early guard denies real
credentials, private configuration reads, database access and network access):

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = "$PWD;$PWD/tests"
$env:PYTEST_ADDOPTS = ''; $env:PYTEST_PLUGINS = ''
.venv/Scripts/python.exe -B -m pytest -p migration_offline -q -p no:cacheprovider tests/test_development_integrations.py tests/test_integrations.py tests/test_database_config.py tests/test_state_requests.py tests/test_notifications.py
```

Live use still requires separately authorized credential provisioning in both
applications, GraManna backend configuration for this origin/client and separate
permission credentials, and confirmation that the DEVELOPMENT schema/runtime
permissions support the existing notification and reporting contracts. Any
database changes or live verification require a separate checkpoint; this
launcher performs no migrations, grants or provisioning.
