# Contact SMTP readiness — Checkpoint 5B

The owner approved Namecheap Private Email and confirmed webmail access for
`contact@ovisalmsfoundation.org`. This checkpoint prepares DEVELOPMENT only.
It does not verify SMTP authentication, provider policy or inbox delivery.

## Existing contract and configured settings

The Contact implementation and its security controls remain unchanged. See
[`CONTACT.md`](CONTACT.md) for the Checkpoint 5A contract and validation history.
Its statements that configuration was absent describe that earlier checkpoint.

The existing lazy loader reads ignored `config/local/contact.toml`, requires an
explicit matching `OAF_ENV`, and accepts only `development` and `testing`
sections with exactly `host`, `port`, `tls_mode`, `username` and `from_email`.
Supported TLS modes are `ssl` (implicit TLS) and `starttls` (mandatory STARTTLS).
There are no SMTP credential environment-variable overrides or fallback targets.

The new local file contains only:

```toml
[development]
host = "mail.privateemail.com"
port = 465
tls_mode = "ssl"
username = "contact@ovisalmsfoundation.org"
from_email = "contact@ovisalmsfoundation.org"
```

Port 465 is supported, so the alternative 587/STARTTLS is unnecessary. Python's
existing `ssl.create_default_context()` verifies certificates and hostnames.
The configured account authenticates; `from_email` supplies both From and the
SMTP envelope sender. The fixed recipient remains
`contact@ovisalmsfoundation.org`; the subject remains `OAF General Contact Inquiry`.
The visitor address remains Reply-To. Recipient and subject are not config keys.

No TESTING SMTP section or credential is created. No production configuration,
launcher, runtime source, public page, integration or dependency is changed.
The existing DEVELOPMENT launcher already selects the development profile.

## Protected credential and owner procedure

Contact reads only the pinned `keyring.backends.Windows.WinVaultKeyring` backend
under the Windows user launching the website. Its required generic credential is:

- Exact target: `OAF Website/development/Contact/SMTP`
- Account/UserName: `contact@ovisalmsfoundation.org`
- Type: `1` (generic)
- Persist: `2` (local machine; accessible to this Windows user on this computer)

An exact-target, metadata-only native lookup found the DEVELOPMENT generic
credential **absent**. No password blob was copied or decoded. The owner must
provision the Namecheap mailbox password before the next controlled checkpoint.
No credential was created, replaced or activated by Codex.

Use an ordinary interactive Windows PowerShell console, as the same Windows
user that launches DEVELOPMENT. Keep other Credential Manager administration
idle during provisioning. Run this exact procedure yourself, outside Codex:

```powershell
Set-Location -LiteralPath 'C:\Users\ovisa\Documents\OAF_App\Development\OAF Website'
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\ops\Set-DevelopmentContactSmtpCredential.ps1
```

Type the Namecheap mailbox password at the two hidden prompts. Never put it in
the command, Codex prompt, clipboard, environment or a file. Do not redirect or
record the session. The password is read directly by the child console process;
it does not pass through PowerShell command history. The helper refuses
noninteractive/redirected streams and echoing password fallback. It creates only
the exact generic credential, uses local-machine persistence and checks the
stored metadata and password in memory without printing either.

The helper uses the already installed pinned keyring backend. The existing
integration helper remains unchanged because it generates integration-specific
secrets; those credentials must not be reused for SMTP. The operator helper
never calls the keyring convenience writer that can relocate existing records.
It checks absence twice, coordinates cooperating invocations with ignored
`config/local/contact.operator.lock`, and leaves every existing target unchanged.
Windows offers no atomic create-only credential write, so unrelated credential
writers must remain idle. If the target already exists, the helper requests no
password and makes no change; that message alone does not verify its readiness.
If a write outcome cannot be verified, stop and reconcile metadata; do not
delete, rotate or replace credentials merely to retry.

The lock file contains no password and may remain after execution. Passwords
exist transiently in process memory and Windows Credential Manager only, within
the existing Windows-user credential trust boundary. No GraManna/Gmail, Brevo,
PostgreSQL, recognition or integration credential is used or modified.

The helper starts no application, form submission, network connection, database
session or mail test. Provisioning does not authorize sending email. Live
authentication and delivery remain deferred to the separately authorized next
controlled test checkpoint.

## Offline verification record

Verified locally on 2026-10-15:

- Actual ignored configuration passed the existing `load_contact_config` with
  an injected synthetic password provider: exact schema, provider, port, TLS
  mode, account, From, fixed recipient and exact DEVELOPMENT credential target.
  TESTING and production were rejected before credential lookup. No SMTP
  transport was invoked. Runtime checks confirmed hostname verification and
  `ssl.CERT_REQUIRED`. Network/native credential/database access was denied;
  no external-access attempt occurred in the completed check.
- Existing focused Contact configuration/TLS tests: **16 passed, 69 deselected
  in 0.49 seconds**, with the existing early offline guard and zero unexpected
  external-access attempts. This checkpoint did not repeat the 275-test campaign
  or submit a Contact form. The TLS tests used mocked SMTP objects only.
- Operator helper PowerShell syntax: **PASS**. A real invocation with redirected
  input refused execution before credential access. The embedded Python was
  checked using **27 passing synthetic scenarios**, including exact target and
  persistence, confirmation, no overwrite, concurrent target appearance,
  conflicting environments/configuration, redirection, unavailable locking,
  echo fallback refusal and sanitized write/readback failure. No real credential
  writer or network/database interface was used in those scenarios.
- SHA-256 preservation check: **all 93 pre-existing files byte-identical**,
  including every public page, Contact implementation, State Requests,
  notifications, integrations, owner-authored documentation and existing local
  configuration/protected recognition file. No GraManna or Brevo change.
- `.gitignore` already excludes `/config/local/`, `/secrets/` and `.env` files.
  `git ls-files` showed no tracked file in those locations. The new SMTP config
  and prospective operator lock are ignored. Neither contains a password.
  No mailbox password was entered, retrieved, printed or written to a file.
- Task-scoped tracked whitespace checks passed. The two new shareable files and
  new local config contain no trailing whitespace. Pre-existing unrelated work
  was preserved. No full repository whitespace cleanup was performed.

Created by this checkpoint:

- `config/local/contact.toml` (ignored, non-secret).
- `ops/Set-DevelopmentContactSmtpCredential.ps1` (operator-only; not run with a
  password or real credential writer).
- `docs/CONTACT_SMTP_SETUP.md` (this report and exact owner procedure).
- Ignored `.pytest_cache/contact-checkpoint5b/` preservation manifest, initial
  Git status and synthetic validation artifacts; no real password data.

No pre-existing file was modified. No new dependency, database/migration,
application startup, integration activation, staging, commit, push or live
email occurred. No production or TESTING configuration or credential changed.

**Readiness:** non-secret DEVELOPMENT configuration is ready. The exact SMTP
credential is absent and owner provisioning is required. SMTP authentication,
remote TLS negotiation and delivery remain unverified and require the next
separately authorized controlled test checkpoint. There is no configuration or
protected-storage mechanism blocker.

## Final Git status

13 pre-existing modified tracked files; 22 untracked files (20 pre-existing,
plus this report and the operator helper). The index is empty. Ignored local
configuration and validation artifacts do not appear below.

```text
 M .vscode/settings.json
 M README.md
 M about.html
 M docs/WORKFLOW.md
 M gramanna.html
 M index.html
 M oaf_website/local_development.py
 M oaf_website/local_testing.py
 M oaf_website/notifications.py
 M oaf_website/state_requests.py
 M ops/Start-DevelopmentWebsite.ps1
 M styles.css
 M tests/migration_offline.py
?? assets/contact.js
?? contact.html
?? docs/CONTACT.md
?? docs/CONTACT_SMTP_SETUP.md
?? docs/DEVELOPMENT_CREDENTIAL_HANDOFF.md
?? faq.html
?? oaf_website/contact.py
?? oaf_website/contact_mail.py
?? oaf_website/integrations.py
?? oaf_website/interest_reporting.py
?? ops/Record-Development0002Prerequisites.ps1
?? ops/Record-Development0003Prerequisites.ps1
?? ops/Record-Testing0003Approvals.ps1
?? ops/Record-Testing0003Reconciliation.ps1
?? ops/Set-DevelopmentContactSmtpCredential.ps1
?? ops/Set-DevelopmentIntegrationCredentials.ps1
?? support.html
?? tests/Test-DevelopmentIntegrationCredentials.ps1
?? tests/contact_browser_check.py
?? tests/test_contact.py
?? tests/test_development_integrations.py
?? tests/test_integrations.py
```
