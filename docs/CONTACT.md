# General Contact — Checkpoint 5A

The Foundation's `contact.html` is the permanent General Contact page. Header
Contact links on all six public pages and the homepage Learn More / Contact Us
link lead here. No GraManna repository or integration change is included.

`GET /api/contact/session` reuses the existing signed HttpOnly, SameSite=Lax
browser cookie and browser-bound CSRF token. `POST /api/contact` accepts exactly
two JSON fields: `email` and `message`. It never writes State Requests,
subscriptions, reporting, private messages, or any database record.

Success means the authenticated SMTP transport acknowledged message acceptance;
it does not establish inbox delivery. The fixed recipient is
`contact@ovisalmsfoundation.org` and the fixed subject is
`OAF General Contact Inquiry`. Neither can be supplied by a visitor or changed
through Contact configuration. The validated visitor address is Reply-To; the
separate configured sending address is From and the SMTP envelope sender.
The recipient address is absent from public HTML and JavaScript.

## Configuration for a later authorized checkpoint

No credentials were read, created, copied, or activated during implementation.
No real email was sent. Live delivery and the Foundation's outgoing reply
identity still require separate owner authorization and verification.

The existing runtime factory installs a lazy Contact SMTP transport. It reads
configuration only when a Contact submission is attempted. Missing or invalid
configuration returns a sanitized HTTP 503; other site features remain usable.
The existing DEVELOPMENT launcher needs no new switch or environment variable.
Do not populate/activate these settings as part of this source checkpoint.

Supply the ignored, non-secret file `config/local/contact.toml` with a
`[development]` or `[testing]` section matching the existing explicit `OAF_ENV`.
Both sections may coexist. Each section must have exactly these keys:

| Key | Owner-supplied value |
| --- | --- |
| `host` | Approved SMTP server hostname |
| `port` | Approved SMTP TLS submission port, integer 1–65535 |
| `tls_mode` | `ssl` for implicit TLS, or `starttls` for mandatory STARTTLS |
| `username` | The separate authenticated SMTP account, ASCII, maximum 254 characters |
| `from_email` | Provider-authorized sending mailbox in lowercase ASCII syntax |

No SMTP host, account, port, or From address has been selected or invented.
The authenticated account, From address and recipient mailbox need not be the
same. The owner must confirm the provider-authorized sending identity and the
Foundation identity used for subsequent outgoing replies before live testing.
Production configuration/deployment remains under the existing production gate.

Store the password only in the existing pinned Windows Credential Manager
backend, under the launching Windows user. Use the exact generic credential
target `OAF Website/<profile>/Contact/SMTP`, with Account/UserName equal to the
configured `username`, generic Type 1 and local-machine Persist 2. No fallback
target, alternate credential backend or environment-variable overrides are
supported. Do not put passwords in TOML, browser code, source, command arguments
or documentation. Do not reuse GraManna, PostgreSQL or integration credentials.
This implementation only reads an externally provisioned credential; it never
provisions one. Redirected configuration files/directories are rejected.

SMTP uses Python's standard library, certificate and hostname verification,
mandatory TLS before authentication, and a five-second socket timeout per
operation. It attempts a submission once. Acknowledged acceptance remains
success even if local connection cleanup fails. Known refusal/configuration/
pre-send failures return a safe failure and permit deliberate retry. A lost
acknowledgment or unexpected send failure returns an uncertain error and
temporarily suppresses the same submission; no success is claimed.

## Limits and operational boundaries

- Required email uses the existing common ASCII mailbox syntax validator,
  rejects controls/header injection and caps input at 254 characters.
- Required message permits 200 whitespace-separated words and 6,000 characters.
  Control characters other than ordinary line breaks/tabs are rejected.
- Contact JSON is limited to 32 KiB per request. Existing State Request and
  notification limits stay at 1 KiB. Unexpected JSON fields are rejected.
- Same-origin checks and the existing browser-bound CSRF header are required.
  HTTPS cookies remain Secure; the existing explicit loopback HTTP exception
  is unchanged. No credentialed cross-origin access is enabled.
- Per process: at most five Contact attempts per browser and peer IP in ten
  minutes, and 60 total attempts per ten minutes. Forwarded IP headers are
  ignored. The maps have a 4,096-entry capacity each and fail closed when full.
- A thread lock reserves identical browser/email/message submissions before
  SMTP. Accepted and uncertain submissions are retained for 15 minutes as keyed
  digests and states; content, email and raw IP are not retained in these maps.
  Pending duplicates cannot send concurrently. The UI also disables controls
  during submission, performs no automatic retry, and retains failed inputs.
- These limits and duplicate records are process-local and expire or disappear
  on restart. They do not provide cross-worker or permanent deduplication.
  The current local deployment runs one process with threads. Before a future
  multi-worker/proxy deployment, review aggregate limits and trusted peer IP
  handling; no shared limiter or new infrastructure is added here.
- Logs contain only fixed unavailable/uncertain event messages. No raw mail,
  visitor address, passwords or exception details are logged. Validation and
  response text is inserted using `textContent`, never interpreted as HTML.

Deterministic autonomy review: validation, origin/CSRF decisions, bounded abuse
controls, duplicate reservation, SMTP acceptance, safe failure, uncertain-send
suppression and expiry are automatic. No AI or routine manual review is needed.
Owner-controlled exceptions are SMTP provisioning, sending/reply identity,
provider policy, deployment topology and separately authorized live testing.
There is no background retry queue, delivery tracking, ticket system or inbox.

## Focused validation

Backend tests use the dedicated website interpreter and the existing early
offline guard, which denies real network, credentials and database access:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = "$PWD;$PWD/tests"
$env:PYTEST_ADDOPTS = ''
$env:PYTEST_PLUGINS = ''
.venv/Scripts/python.exe -B -m pytest -p migration_offline -q -p no:cacheprovider tests/test_contact.py tests/test_state_requests.py tests/test_notifications.py
```

The focused Chromium check uses the existing shared Playwright interpreter,
intercepts every HTTP request and passes allowed requests through Flask's test
client, including real browser cookie/CSRF handling. SMTP and unrelated stores
are mocked. It starts no live application or database session:

```powershell
..\GraManna\.venv\Scripts\python.exe -B tests/contact_browser_check.py
```

Screenshots are stored only in ignored `.pytest_cache/contact-checkpoint5a/`.
Existing intercepted State Request and notification browser checks remain
available for focused preservation checks. None of these checks verifies live
delivery, PostgreSQL behavior or a deployed environment.

## Checkpoint 5A validation record ? 2026-10-15

**SOURCE IMPLEMENTED**

**MOCKED TESTS PASSED**

**LIVE EMAIL DELIVERY NOT YET VERIFIED**

- Focused offline backend run: **275 passed in 2.79 seconds**, zero unexpected
  external-access attempts. This includes Contact, State Request and notification
  tests; no shared-services integration lifecycle campaign was run.
- Contact Playwright/Chromium with Flask test-client routing: **PASS at 1280,
  390 and 320 pixels**. All six public pages, both Contact entry points, labels,
  required/email/word validation, actual cookies/CSRF, rate limits, duplicate
  suppression, mocked mail acceptance/refusal, safe text rendering, network/HTML
  failures, keyboard/focus, eleven pilot cards, Donorbox and no overflow passed.
  Zero page errors and external HTTP requests. Desktop/mobile screenshots were
  visually inspected and retained in the ignored test cache.
- Existing State Request and notification intercepted Chromium checks: **PASS
  at 1280 and 390 pixels**, zero page errors and external requests.
- Compared task diffs against captured initial workspace bytes and SHA-256
  hashes, including initially untracked files. All pre-existing files outside
  the nine intentional edits remain byte-identical. Existing page changes are
  limited to the approved Contact links; CSS adds Contact to shared styles and
  provides scoped textarea/feedback rules. Approved content and owner-authored
  documentation remain intact.
- `git diff --check` for the task's tracked files passes. The repository-wide
  check identifies only pre-existing Markdown hard-break whitespace on lines
  196?198 of `docs/WORKFLOW.md`; that owner-authored file was left byte-identical.
- Metadata-only inspection confirmed `config/local/contact.toml` is absent.
  No protected SMTP credential was inspected. The owner must supply/authorize
  SMTP host, port, TLS mode, account, authorized From identity and protected
  password, and separately confirm the Foundation's outgoing reply identity.
- No new dependency, database/migration, Contact record store, background queue,
  staging, commit, push, credential provisioning or live email occurred. No
  GraManna repository edits or integration activation occurred.

Created: `contact.html`, `assets/contact.js`, `oaf_website/contact.py`,
`oaf_website/contact_mail.py`, `tests/test_contact.py`,
`tests/contact_browser_check.py`, `docs/CONTACT.md`.

Modified from the initial workspace: `index.html`, `about.html`, `gramanna.html`,
`faq.html`, `support.html`, `styles.css`, `oaf_website/state_requests.py`,
`oaf_website/local_testing.py`, `tests/migration_offline.py`. The last file adds
only Contact to the existing offline test-file allowlist; its guards are intact.

Initial Git status: 13 modified tracked files, 13 untracked files; staging empty.

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
?? docs/DEVELOPMENT_CREDENTIAL_HANDOFF.md
?? faq.html
?? oaf_website/integrations.py
?? oaf_website/interest_reporting.py
?? ops/Record-Development0002Prerequisites.ps1
?? ops/Record-Development0003Prerequisites.ps1
?? ops/Record-Testing0003Approvals.ps1
?? ops/Record-Testing0003Reconciliation.ps1
?? ops/Set-DevelopmentIntegrationCredentials.ps1
?? support.html
?? tests/Test-DevelopmentIntegrationCredentials.ps1
?? tests/test_development_integrations.py
?? tests/test_integrations.py
```

Final Git status: 13 modified tracked files, 20 untracked files; staging empty.

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
?? ops/Set-DevelopmentIntegrationCredentials.ps1
?? support.html
?? tests/Test-DevelopmentIntegrationCredentials.ps1
?? tests/contact_browser_check.py
?? tests/test_contact.py
?? tests/test_development_integrations.py
?? tests/test_integrations.py
```
