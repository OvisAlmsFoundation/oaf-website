## Codex Execution Workflow

- Codex work for the OAF Website must be launched from the OAF Website repository so the website and GraManna workstreams remain isolated.
- Codex prompts should normally be provided as a one-step PowerShell block that the owner can paste directly into the OAF Website terminal.
- Use `Invoke-OAFCodex` for normal website Codex runs.
- In the current PowerShell helper configuration, `Invoke-OAFCodex` copies Codex's final report to the clipboard automatically after a successful run.
- `Invoke-OAFCodexClipboard` is not required merely to receive output on the clipboard; use it only when the prompt itself is being supplied through the clipboard.
- Do not default to the VS Code F4 shortcut for website work unless the owner specifically requests it.
- Every Codex prompt must clearly state that it is working only in the current OAF Website repository.
- Codex must not commit or push changes unless an explicit approved commit checkpoint has been reached.

### Current Supported Codex Modes

The current `Invoke-OAFCodex` helper accepts these modes:

- `SOL / HIGH`
- `SOL / EXTRA HIGH`
- `SOL / MAX`
- `ASTRA / EXTRA HIGH`
- `ASTRA / MAX`

Do not request unsupported modes such as `SOL / MEDIUM` unless the PowerShell helper is later updated to support them.

### Mandatory First-Failure Capture and Immediate Owner Reporting (Standing Rule)

This **permanent workflow requirement** applies to future OAF Website Codex work,
PowerShell/Python helpers, tests, migrations, integrations, scheduled jobs, and
approved operational runs, including the OAF Website side of shared services.
It supplements stricter feature-specific audit, privacy, authorization and
recovery contracts. A generic `BLOCKED`, `FAILED`, exception or exit code is
**not** a sufficient final diagnosis when a more specific result was observable.
Implement diagnostic capture **before** asking the owner to execute a new or
materially changed workflow; keep the implementation proportional to the task.

- **Prepare evidence before risky operations.** Establish the approved
  owner-controlled destination, a unique run/attempt identity, exclusively
  created evidence files, and live terminal plus simultaneous complete
  sanitized logging *before* the first step that could fail or cause side
  effects. Initialize the established OAF visual alert/reporting capability
  early enough to cover preflight failures. Never truncate, overwrite, or
  silently merge historical runs. If evidence initialization fails, stop
  safely and disclose the reporting limitation through any available channel.
- **Record exactly where execution stopped.** Emit and flush a `STARTED` record
  before each material gate or operation; finish it with `PASS`, `BLOCKED`
  (evaluated and rejected), `ERROR` (could not evaluate), or `NOT_RUN` (not
  reached because of a stated dependency). Include UTC timestamps, run and
  package/artifact identity, stage, stable operation/predicate identifier and
  relevant source/function. An unfinished `STARTED` record after interruption
  means `INTERRUPTED/UNKNOWN`, **not** success or proof of no side effects.
- **Retain actionable, sanitized details.** For every failed or blocked check,
  record the expected condition and observed condition or `UNAVAILABLE`, the
  exact constituent conflict code(s) rather than only an aggregate rejection,
  and a safe exception class plus SQLSTATE, HRESULT or exit code when present.
  Identify which prior checks passed, which dependent checks were not run, and
  which operational boundaries were reached: task/process actions, database
  mutation/commit certainty, provider submission/acceptance uncertainty, and
  cleanup. Distinguish verified facts, hypotheses, and missing visibility.
- **Persist before propagating failure.** Preserve reached-check results and
  known side effects in bounded structured evidence, flush/synchronize using
  the established durability mechanism, **then** raise or return the failure.
  A nonzero Python/child exit must not hide already-published validated safe
  diagnostics from its PowerShell/parent reporter. Validate evidence identity,
  source, format and privacy before consuming it. Missing or malformed evidence
  remains a failure with an explicit evidence gap, never implied success.
- **Report immediately to the owner.** At the end of **every** Codex, test, or
  authorized operational run, present a concise first-failure/blocked-step
  summary directly in the visible terminal and Codex final report. Preserve
  the complete sanitized simultaneous log and structured evidence location;
  automatically copy the report to the clipboard with read-back verification
  and display the existing OAF success/failure visual alert. Include run ID,
  exact stopped stage/predicate, reason, safe expected/observed information,
  completed/not-run steps, known or uncertain side effects, evidence path,
  and the **single next safe checkpoint**. Do not announce success until the
  required terminal evidence, log/transcript finalization and reporting checks
  are complete. If clipboard, alert or logging fails, show a safe fallback and
  explicitly label reporting **INCOMPLETE**; do not falsely claim delivery.
- **Protect confidential data.** Never put passwords, tokens, API/DPAPI keys,
  private capabilities/URLs, raw subscriber records, secret-bearing connection
  strings, raw SQL parameters, unrestricted process arguments/environment
  values, or unredacted exception text into terminal, clipboard, alerts, or
  ordinary logs. Use fixed codes, bounded metadata, fingerprints and restricted
  evidence locations where needed. Protect existing private evidence and ACLs.
- **Fail closed; keep authority separate.** Recording a failure or finishing a
  diagnostic collection does **not** authorize a retry, migration, worker,
  provider send, task change, or reuse of consumed authority. Preserve claims,
  outcomes, markers and uncertainty. Stop unsafe dependent operations, while
  allowing only separately safe read-only checks approved by the current
  contract. Do not fabricate missing observations or rewrite past failures.
- **Validate the real reporting boundary before approval.** Test the actual
  producer -> evidence writer -> child/parent consumer -> terminal/log/clipboard/
  alert path, including early initialization failures, aggregate rejects,
  nonzero child exits, partial logs, interrupted operations, publication errors
  and finalization failure. Mocks may isolate genuine operational side effects,
  but must not substitute away the reporting interface under test. An offline
  PASS is not live readiness. Use focused, proportionate checks; avoid a new
  framework, repeated broad test campaigns, or separate diagnosis for each
  successive error.
- **Codex instructions are mandatory.** Every future Codex prompt that builds,
  changes or runs executable workflows must carry these requirements forward.
  Review the captured diagnostic evidence immediately after a stop and supply
  its actual first blocking reason in the final clipboard report; if the exact
  cause is unknowable, identify the evidence gap and the smallest safe next
  observation instead of declaring a root cause. Continue one approved prompt
  and checkpoint at a time, without silently changing the established
  PowerShell/Codex execution method.

### End-to-End Deterministic Autonomy

This permanent rule applies to all current and future OAF Website features, including frontend and backend functionality, across every page and program.

- Design all website features for deterministic autonomy wherever practical. Prefer explicit server-side rules, registries, templates, state transitions, validation constraints, thresholds, scheduled jobs, and event-triggered processing.
- Ordinary operations must not require continuous manual intervention or AI participation.
- Frontend behavior must be deterministic, accessible, and consistent with authoritative backend decisions.
- Security, eligibility, validation, abuse prevention, duplicate controls, and data integrity must not depend solely on frontend enforcement.
- Implement autonomous lifecycle handling where applicable, including submission, confirmation, acceptance, rejection, expiry, dispatch, retries, suppression, and recovery.
- Provide appropriate audit logging, monitoring, and deterministic failure handling.
- Preserve authorized Foundation administrative authority for exceptional corrections, policy changes, geographic availability decisions, and announcement approvals.
- AI may optionally assist with recommendations, summaries, or improvements, but must not be an operational dependency unless explicitly authorized in a separate contract.

#### Deterministic Autonomy Review and Validation

- Before a feature design is considered near-final, perform a deterministic autonomy review identifying all decisions, governance areas, lifecycle transitions, failure paths, and operational dependencies.
- Confirm that each area is autonomous wherever practical. Document justified exceptions and required administrative controls.
- Validate autonomous behavior through deterministic tests, including negative cases, failure handling, and recovery. Use the automated browser validation guidance below for browser checks, with validation proportional to the change.

### Migration Authority, Approval Gates, and Operational Evidence

#### Standing migration troubleshooting and PostgreSQL catalog lessons — 2026-10-17

These lessons apply to future OAF Website migrations and unexplained migration
failures. They supplement the existing migration authority, audit, approval and
recovery policies (A–D); they do **not** grant execution authority or create a
new mandatory framework. The dated checkpoint entries below retain their
historical scope and status.

- **Start with the actual failed run.** Inspect the authorized run, claim,
  published terminal completion and existing source path. Distinguish the
  failure phase, PostgreSQL/database classification, commit certainty, rollback
  and cleanup. A PowerShell exit or success-colored message is not a substitute
  for `applied_and_verified` and acknowledged postcommit evidence. Do not
  automatically retry a failed or consumed authorization.
- **Make the first failure diagnosable, without exposing private data.** Where
  the approved evidence mechanism allows it, capture a stable validator
  operation/predicate identifier, sanitized exception class and SQLSTATE
  (including a wrapped driver's `.orig.sqlstate`), and narrowly bounded
  expected-versus-observed catalog metadata. Never log credentials, connection
  strings, raw SQL parameters, subscriber data or unredacted exceptions. If the
  failed operation was not captured, state that the historical cause remains
  unconfirmed; use a separately authorized bounded diagnostic rather than
  inventing or retroactively rewriting audit evidence.
- **Follow the real execution path.** Compare the actual SQLAlchemy `text()`
  binding and psycopg execution with the validator's SQL; direct-driver or
  synthetic probes can behave differently. In the `0004` incident, reusing one
  `:table` parameter in both `regclass` and `regtype` contexts reproduced
  PostgreSQL SQLSTATE `42846` (`CannotCoerce`). Explicitly converting the
  parameter through `text` before the separate catalog lookups fixed that
  incompatibility while retaining the exact Boolean identity assertion.
- **Validate PostgreSQL-generated metadata when it matters.** Offline tests
  built from expected catalog graphs cannot independently prove what PostgreSQL
  generates. The `0004` incident exposed an internal TOAST relation for
  `notification_release_events` and a `pg_depend` edge absent from the
  validator's expected labels. Recognize such an edge only through positive
  catalog checks: exact `pg_class` identities, the managed parent's
  `reltoastrelid`, internal whole-object dependency (`deptype='i'`, subobject
  numbers zero), and required ownership, persistence and ACL properties.
  Never broadly ignore unknown `pg_toast` objects or relax ordinary dependency
  comparison.
- **Use the smallest decisive reproduction.** If real generated objects are
  needed and existing TESTING state cannot supply them, use an expressly
  authorized, isolated local PostgreSQL instance with current schema/role
  parity. Run the relevant DDL and unchanged validation within an uncommitted
  transaction; observe the **first** failing predicate, then verify rollback,
  shutdown and cleanup. Do not turn this into a standing requirement for every
  small migration or introduce paid infrastructure.
- **Keep diagnostics reliable and proportional.** On Windows, descendants may
  retain captured subprocess output pipes after a PostgreSQL launcher exits;
  use appropriately bounded waits and file-backed output for such launchers.
  Check exact disposable instance identity before touching its processes or
  files. Prefer one focused harness correction and a few relevant tests over
  repeated broad investigations or new process-management frameworks.
- **Preserve formal recovery and artifact boundaries.** Even a confirmed
  rollback may require owner reconciliation when mutation began. Keep claims,
  failed outcomes, previous approvals and consumed authorizations intact.
  A validator or manifest hash change requires the applicable independent
  review, updated exact-artifact approval, current environment-specific
  prerequisites and fresh single-use authorization before a new execution.
  Validate TESTING first; DEVELOPMENT and successor revisions remain separate.

**Recorded outcome:** The repaired `0003_notifications` →
`0004_notification_delivery` TESTING run (`b25e584d-2629-48b7-8303-021132162ed9`)
reported `applied_and_verified`, confirmed commit and passed postcommit
validation. Both validator defects were independently reproduced, but the
original failed operational runs did not retain their exact first failing
predicate; do not portray historical attribution as conclusively proven.

#### Launch and availability subscription source checkpoint — 2026-10-11

Owner baseline: State Request **CLOSED / PASS**, both local databases at 0002, working DEVELOPMENT launcher/F2 and pgAdmin, Git checkpoint `f95db80`. Notification source/offline work supersedes historical notification deferral statements. No live database access/migration, real approval/authorization issuance, provider setup, production email, separate administration system or Git staging/commit/push is part of this task.

The only new transition is `0002_state_requests -> 0003_notifications`; a later separately authorized no-op may start at 0003. Preserve revisions 0001/0002 byte-for-byte. No base/0001 jump to 0003, multi-revision upgrade, downgrade or stamp is supported. Exact-artifact independent approval remains pending; changed hashes are integrity evidence only and do not reuse prior approvals or execution authorizations.

The existing `oaf_website.state_requests.create_app(...)` now registers `/api/notifications/session`, POST `/api/notifications`, and POST `/api/notifications/unsubscribe` alongside the preserved State Request routes, using the same verified runtime engine and protected persistent key with a separate signing domain. Startup performs no migrations or schema creation. The explicit public-file allowlist adds `assets/notifications.js`; DEVELOPMENT's F2 launcher and its 0002 startup checks remain unchanged. Subscription writes return a sanitized unavailable response until the separately authorized 0003 migration is applied.

Signup requires strict JSON fields `email`, `web_launch`, `android_launch`, `ios_launch`, `state` (null or a registered code), `consent=true` and a fresh 32-byte browser-generated hex receipt `token`. The server validates every field and stores only the receipt hash. Repeated active email submissions never overwrite preferences or consent; receipt replays never reactivate withdrawn records. Responses disclose no subscriber existence or existing preferences. The returned signed capability controls only a lifecycle created by that receipt; a duplicate from another receipt cannot yield the original link. The page explains this and tells visitors to save the private link.

Unsubscribe links use `/gramanna.html#unsubscribe=<hash>.<signature>`. Fragments stay out of HTTP paths/query logs, are removed from the address bar immediately, and require explicit user action. POST the signed token with the same origin and browser CSRF protections. No email address is needed to withdraw; invalid signatures cannot mutate, and successful repeated/unknown valid receipts produce a generic confirmation. Future approved delivery can recreate links with `UnsubscribeCapabilities.issue(stored_digest)` using the same protected key. No email delivery/verification is implemented or claimed.

Offline validation adds `tests/test_notifications.py` and `tests/test_notification_migration.py` to the ten-file suite, preserving `-B`, the dedicated website interpreter, empty pytest plugin/options settings and `-p migration_offline`. Select all twelve test files explicitly. Synthetic operational approvals/authorizations remain restricted to test temporary directories; they are not owner issuance. Browser checks use `..\GraManna\.venv\Scripts\python.exe -B tests/notification_browser_check.py` and the existing State Request browser check, with intercepted requests and no database access or GraManna repository edits.

Deterministic autonomy review: fixed server eligibility, validation, consent, atomic duplicate suppression, permanent lifecycle receipts, signature verification, withdrawal, sanitization and idempotent repeat rules; no AI or manual per-submission decision. Foundation announcement/geographic approval, future delivery/verification and separately gated migration/deployment remain administrative controls. Offline model/Chromium results do not establish PostgreSQL catalog/ACL/concurrency semantics or deployed readiness.

Next checkpoint: independent exact-artifact/prerequisite review for 0003, separately owner-authorized TESTING validation starting at 0002, then successful matching-artifact evidence before separate DEVELOPMENT authorization. Preserve all previous audit/approval evidence and Stage 5 failure/recovery boundaries; this source checkpoint creates no real operational records.

Source validation results: all twelve offline regression files passed **1,204 tests** in **58.06 seconds**, with zero unexpected external-access attempts. The focused notification/migration/authorization run passed **248 tests**. Notification and preserved State Request intercepted Chromium checks passed at **1280px and 390px**, with zero page errors or external requests. Revision 0001 and 0002 bytes match HEAD; shared CSS and State Request JavaScript are unchanged. Pre-existing README, VS Code, DEVELOPMENT launcher and prerequisite-helper changes were preserved. Staging remains empty. These results establish tested source/model/UI behavior only; no live PostgreSQL or production readiness is claimed.

Task file inventory: `gramanna.html`, `assets/notifications.js`; `oaf_website/notifications.py`, `oaf_website/notification_schema.py`, `oaf_website/notification_validation.py`, `oaf_website/state_requests.py`, `oaf_website/local_testing.py`; `migrations/versions/0003_notifications.py`, `migrations/manifest.json`, `oaf_website/migration_validation.py`, `oaf_website/migration_authority.py`; `tests/test_notifications.py`, `tests/test_notification_migration.py`, `tests/notification_browser_check.py`, `tests/migration_offline.py`, `tests/test_migration_artifacts.py`, `tests/test_migration_authorization.py`, `tests/state_request_browser_check.py`; `docs/WEBSITE_PLAN.md`, `docs/WORKFLOW.md`. No task edits to pre-existing owner changes or approved revisions were made.

#### State Request source checkpoint — 2026-10-10

Both baseline migrations are CLOSED / PASS per the owner. State Request implementation and focused offline validation are authorized; prior baseline-only/feature-deferral language is historical for this task. Preserve owner changes and all Stage 5 controls. No live database, credentials, real audit/approval/authorization records, paid provisioning, or Git staging/commit/push are authorized.

The supported new transition is exactly `0001_migration_baseline -> 0002_state_requests`; a separately authorized no-op may start at 0002. A `base -> 0002` jump, downgrade, stamp, or multi-revision execution remains prohibited. Revision 0001 stays unchanged. Matching hashes remain integrity evidence, not artifact approval. New artifact hashes do not reuse baseline execution authorizations or rewrite old evidence.

Offline checks add `tests/test_state_requests.py` and `tests/test_state_request_migration.py` to the existing eight explicitly selected files with the same early isolation plugin and website interpreter. Tests use Flask's in-process client, compiled PostgreSQL SQL, temporary synthetic approval evidence and a transactional database model. These checks cannot establish actual PostgreSQL concurrency, catalog/ACL semantics or browser-cookie behavior.

Runtime setup after approval: use `oaf_website.state_requests.create_app(expected_profile=..., recognition_secret=..., public_origin=...)`. Pass a protected persistent random secret of at least 32 bytes, shared by every worker/restart; no generated startup secret or database-credential reuse is provided. The existing database loader still requires the explicit matching `OAF_ENV`; testing uses its testing-only loader and production remains blocked by the existing deployment gate. Flask startup never creates schema or runs Alembic. Each runtime connection checkout verifies database/user/host/port/PostgreSQL 17 identity and requests SCRAM authentication.

Serve the static site and `/api/state-requests`, `/api/state-requests/session`, and `/api/state-requests/totals` through the same configured public HTTPS origin. The independent API can sit behind a same-origin reverse proxy; cross-origin credentialed CORS is intentionally absent. Local HTTP is permitted only by explicit `allow_insecure_localhost=True` for localhost. Cookie recognition expires after one year; retaining the secret preserves recognition within the cookie lifetime. Clearing cookies or changing browsers permits a new recognized identity. Production routing, secret provisioning and launch remain separately approved deployment work.

Next database checkpoint: independent exact-artifact/prerequisite review for 0002, then separate owner issuance for the testing database starting at 0001. Authorized live checks must cover creation/grants/type ACLs/dependencies, concurrent duplicate inserts, rollback and uncertain-result handling, persisted timestamps/totals across restarts, API runtime identity, and browser success/duplicate/error/cookie/origin/accessibility behavior. Development requires the same artifacts' completed successful testing run plus its own authorization. Preserve all existing approvals and audit evidence; do not treat this source checkpoint as execution approval.

Source validation results: the ten-file offline regression run passed **1,031 tests** with zero unexpected external-access attempts. After final origin/JavaScript race fixes, the two feature test files passed **111 tests** with the same isolation. `tests/state_request_browser_check.py` passed intercepted-API Chromium checks at 1280px and 390px, including keyboard use, duplicate/multiple-state messages, failures, disabled controls during submission and stale totals responses; zero page errors and zero external browser requests. `git diff --check` passed. These results validate source and synthetic behavior, not live PostgreSQL or the deployed browser/API flow. Revision 0001 and shared CSS are unchanged; pre-existing governing-document content is retained.

#### Stage 5 current operational policies and source implementation

**Current scope supersedes historical Stage 1 status statements below.** The four policies A-D are owner-approved. Stage 4C development/testing migrators are CLOSED / DELIVERED / PASS as reported by the owner; this source task does not repeat live verification. Stage 5 operational adapter source and offline validation are authorized. Independent artifact approval is **pending**; owner-issued execution authorization is **pending**; live migration execution is **not authorized**. No real authorization record is issued by this task. No live credentials, PostgreSQL changes, package installation, staging, commits, or pushes are authorized.

- **Policy A - destination and evidence:** Use `%LOCALAPPDATA%\OAF Website\BootstrapAudit\MigrationAudit\`, separate from Stage 4C records. The existing BootstrapAudit parent must be available; the adapter may create only its MigrationAudit child. Reject missing, relative, redirected, or unavailable destinations. JSON issuance, claim, denial, execution, and terminal records use exclusive creation, UTF-8/LF, flush, and file `fsync`, following the existing Windows implementation. Never overwrite history, including partial writes. Authorization issuance and terminal finalization also require completion evidence: exclusively write, flush, fsync, and close a pending completion record, then publish its completed name by an exclusive hard link. No synchronization follows that publication. If publication returns an error after creating the exact link, a read-only same-file check recognizes completed publication without retry. Retain both names; pending records are never accepted as completion. Unsupported publication fails closed. File synchronization does not promise protection against every filesystem, hardware, or power-loss failure. Record authorization, denial, execution phases, success, failure, and commit uncertainty. Allowlisted evidence excludes passwords, credential values, complete database URLs, private SQL parameters, raw exception text, and environment dumps.
- **Policy B - retention:** Preserve approval, authorization, claim, and audit records until separate owner authorization permits archival or disposal. No automatic deletion, expiry cleanup, rotation, or claim removal. Expired authorizations remain evidence and cannot execute.
- **Policy C - authorization:** Require a distinct, deliberate owner-issued record with a unique UUID, UTC issuance and expiry, and lifetime of at most 24 hours. Bind the exact environment, operation, expected starting state, target revision, independently approved manifest/revision hashes, applicable prerequisite approvals, and predecessor claim. Reject missing, malformed, future-dated, expired, reused, mismatched, or stale records. Revalidate the exact bound authorization UUID, bytes, and UTC validity at the final runner and Alembic pre-mutation boundaries and immediately before commit, after required audit persistence. Matching hashes prove integrity only. The runner consumes records and never issues or approves them. Issuance is separate from artifact approval, and neither authorizes another environment or a later no-op.
- **Policy D - failure and recovery:** Required audit-write failure before mutation blocks execution. Authorization denial fails closed, with sanitized persistent evidence whenever the destination is available. An unavailable audit destination never permits continuation. Preserve an acknowledged commit as committed even if postcommit verification or audit fails; uncertainty stops without retry. Claims survive every failure and interruption. Complete, consistent evidence of verified success, verified no-op, or conclusive safe premutation failure permits a distinct newly authorized operation without exceptional reconciliation. Uncertain outcomes, postcommit audit failures, and incomplete or contradictory evidence require owner reconciliation before new authorization. Never delete claims, rotate credentials, stamp, repair, or blindly retry as automatic recovery.

`FileOperationalAuthority` implements the existing `OperationalAuthority.authorize(request, run_id, artifacts) -> AuditSink` contract. The exact class is registered in `_OPERATIONAL_ADAPTER_TYPES`; protocol-shaped objects and subclasses cannot authorize work. The migration CLI accepts only an existing `--authorization-id`. Direct runner calls require the same concrete authority, and Alembic requires the runner's single-use context and the authority's actual request/run/sink binding. There is no fallback engine or direct Alembic execution permission. Repository-only `plan` performs integrity checks and grants no execution authority.

The transition remains `base -> 0001_migration_baseline`, with the revision unchanged and metadata-only. A no-op must separately authorize `expected_start=0001_migration_baseline`; an authorization for `base` cannot silently adopt an already-applied state. Testing is the first future live target. Development requires its own authorization and a prerequisite approval citing a successful testing baseline validation run for the same artifact hashes. Existing environment/DB/role matching, exact WinVault targets, SCRAM expectations, owner assumption, schema-qualified metadata, transaction, lock, timeout, drift, and manifest checks remain required.

##### Local record format and future deliberate issuance

These are source interface instructions for a later separately authorized owner action, not permission to create real approvals or execute now. All operational records stay outside Git in MigrationAudit. The issuer is `python -m oaf_website.migration_authority issue --specification <absolute-owner-specification-path> --owner-issue`; it never connects to PostgreSQL or reads credentials. It returns a UUID only after completed issuance is published; a readable authorization payload alone cannot be consumed. Publication is the completion point even if the process stops before delivering its response; never blindly reissue after an interrupted response. `python -m oaf_website.migrate` uses `--authorization-id <issued-uuid>` with its existing explicit request arguments. Do not run a live upgrade/downgrade during source validation.

The minimal issuer reads a UTF-8 JSON specification with exactly four keys: `request`, `artifact_approval`, `prerequisite_approval`, and `expires_utc`. `request` has exactly `action` (`verify` or `upgrade`), `environment`, `expected_start`, `target`, `manifest_hash`, and `revision_hash`. Both approval references have exactly `id` (canonical UUID) and `sha256` (SHA-256 of the approval file's exact bytes). `expires_utc` must be UTC, later than issuance, and no more than 24 hours later. Manifest/framework/revision hashes retain the existing `sha256-utf8-lf` normalization; approval-file and predecessor-claim hashes use exact bytes.

The issuer verifies separately supplied local approval records; it has no action for generating or approving them:

- `artifact-approval-<uuid>.json`: exactly `format` (integer 1), `kind` (`artifact_approval`), `id`, `reviewer_id` (canonical UUID), `approved_utc` (UTC), `decision` (`approved`), `manifest_hash`, and `revision_hash`. Approval must precede authorization issuance and match the independently reviewed artifacts. The repository manifest remains `pending_independent_review`; a future independent approval is a separate evidence record, never a change inferred from digest matching.
- `prerequisite-approval-<uuid>.json`: the same six common fields, with `kind=prerequisite_approval`, plus `environment`, `expected_start`, `approvals`, `predecessor`, `owner_reconciliation`, and `testing_validation_run`. `approvals` maps exactly `dependency_acceptance`, `bootstrap_validation`, `lock_and_timeouts`, `search_path_and_postconditions`, `recovery_procedure`, and `audit_policies` to UUID references to applicable reviewed approvals. These are explicit local attestations of those reviews, not automated proof of their substantive correctness. For testing, `testing_validation_run` is null; for development, it references a completed successful testing `upgrade` run with matching artifact hashes: either acknowledged commit with verified postconditions or a fully verified target no-op. Require published terminal completion bound to that run, authorization, claim, and exact acknowledged event bytes. A partial or success-looking terminal record never qualifies. After an exceptional testing outcome, the existing owner reconciliation prerequisite must bind the exact testing predecessor and verified DB state, followed by a fresh separately authorized testing operation and completed target validation. Reconciliation alone never rewrites a failed result or substitutes for testing validation or independent artifact approval.
- `predecessor` has exactly `sequence` and `sha256`: initially integer 0 and null; thereafter the latest environment claim's integer sequence and exact-byte hash. Initially `owner_reconciliation=not_applicable`. After a claim, every new prerequisite approval binds that exact predecessor and expected DB state and is approved after the claim was written. Complete, consistent published evidence of verified success, verified no-op, or conclusive safe premutation failure permits `owner_reconciliation=not_applicable`; the proven continuation state must match the new expected start. Uncertain commits, postcommit audit failures, missing/incomplete evidence, contradictions, and unresolved drift require `owner_reconciliation=completed`. The owner must reconcile the outcome and verify database state under the approved lock/recovery procedure before making that exceptional attestation. Every successor still requires a distinct explicit single-use owner authorization; no existing record authorizes a retry or later no-op.

The issuer exclusively writes `authorization-<uuid>.json` containing the bound request and approval references, UTC issuance/expiry, and predecessor. Execution exclusively writes `claim-<environment>-<eight-digit-sequence>.json` before credentials or engines. All contenders for the same environment/predecessor, including different authorization UUIDs, compete for the same deterministic file; only one can succeed. A stale authorization cannot advance to another slot. Partial claims remain evidence and can be reconciled by their exact-byte hash without being repaired or reused. Successful claim creation is followed by exclusively created numbered run events and `terminal-<run-uuid>.json`; denials use separate unique JSON records. Completion records use `pending-authorization-<uuid>.json` / `completed-authorization-<uuid>.json` and `pending-terminal-<run-uuid>.json` / `completed-terminal-<run-uuid>.json`. Their exact fields are `format=1`, `kind=record_completion`, `record` (payload filename), `sha256` (exact payload bytes), `authorization_id`, `run_id` (null for issuance), and `evidence` (empty for issuance; exact-byte claim and acknowledged event hashes for finalization). Only the completed name qualifies; publication never overwrites another record. No failed or uncertain operation is automatically retried.

Local files controlled by the same Windows account are **not tamper-proof** against that account. UUID reviewer/authorization references, explicit issuance, and hashes do not provide signatures, cryptographic identity assurance, or proof that a different human performed review. Trusted Python code and the credential-holding account remain the security boundary; modifying private process state, deleting evidence, or using credentials for arbitrary SQL is outside the adapter's protection. Preserve independent review and owner control as administrative prerequisites.

##### Stage 5 offline validation and deterministic autonomy

Run the dedicated website `.venv` interpreter with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, empty `PYTEST_ADDOPTS`/`PYTEST_PLUGINS`, repository plus tests on `PYTHONPATH`, and `-B -m pytest -p migration_offline -q`. Explicitly select all eight test files: `tests/test_database_config.py`, `tests/test_migration_config.py`, `tests/test_migration_artifacts.py`, `tests/test_migration_authorization.py`, `tests/test_migration_catalog.py`, `tests/test_migration_runner.py`, `tests/test_migration_provenance.py`, and `tests/test_migration_operational.py`. The plugin blocks credential/network/database access before collection, guards real BootstrapAudit file reads, and redirects operational file tests to temporary directories. Approval and authorization records in tests are synthetic. No live Alembic operation or real owner issuance is part of these checks.

Deterministic autonomy review: environment/request selection, approval/hash binding, UTC expiry, claim competition, denial persistence, audit transitions, transaction/commit classification, no-op checks, and recovery blocking use fixed rules without AI. Independent review, deliberate owner issuance, prerequisite attestation, and exceptional reconciliation remain the approved administrative boundaries. Offline success proves tested source behavior only; live PostgreSQL semantics, operational validation, independent artifact approval, and a later testing-only execution authorization remain separate gates.

##### Historical Stage 1 contract context

The following Stage 1 approval/status and unresolved-policy wording is preserved as checkpoint history. For migration policies, source implementation, Stage 4C delivery, and the current authorization boundary, the Stage 5 entry above is controlling; it does not reopen policies A-D or grant live execution.

**APPROVED DESIGN / NOT IMPLEMENTED:** The owner approved the Checkpoint 4 Candidate C migration-authority contract with three refinements: one approved revision per execution in one transaction; migration credential services ending in `/Migrations`; and deterministic, sanitized audit evidence. The specific architecture and staged sequence are governed by the "PostgreSQL Migration Authority Contract — Checkpoint 4" section in `WEBSITE_PLAN.md`.

#### Authorization and Preservation

- Stage 1 authorizes contract documentation only, limited to `docs/WORKFLOW.md` and `docs/WEBSITE_PLAN.md`. It authorizes no backend implementation, database provisioning/bootstrap, credential changes, package installation, staging, commit, or push.
- Every future implementation stage requires separate explicit owner authorization. Completing a stage does not authorize the next stage. Design approval does not authorize execution or establish operational readiness.
- No Request Your State feature tables or endpoints, email notification implementation, or production provisioning are authorized by this migration contract.
- Before editing, read both governing documents completely, confirm the repository and branch, record HEAD, inventory staged/unstaged/untracked changes, and inspect existing target-document changes.
- Preserve all pre-existing owner-authored modifications without renewed confirmation. They must accompany approved work at the next authorized commit checkpoint unless the owner explicitly excludes them. Do not discard, revert, overwrite, or stage them during documentation work.
- Stage 1 validation is bounded: confirm only the authorized documents were changed by the task and previous changes remain intact; inspect the documentation diff; check consistency of role, credential, transaction, authorization, and status language; check for sensitive values; and run `git --no-pager diff --check`. Do not run broad tests for this stage.

#### Security and Execution Boundaries

- Keep runtime configuration restricted to runtime identities. Migration configuration must be separate, explicit, and fail closed; production must be rejected before credential access. Flask startup must never run migrations.
- Migration execution requires one approved revision per execution and one transaction encompassing that revision's DDL, applicable grants, Alembic version advancement, and required precommit postconditions. Automatic multi-revision upgrades require later explicit design and authorization.
- Initially prohibit nontransactional operations, revision-controlled commits, autocommit blocks, ordinary downgrade, stamp, automatic destructive repair, and blind retries after uncertain commits.
- Missing authority, identity mismatch, unexplained drift, ownership/grant mismatch, lock failure, or failed checks must halt safely. Unexpected existing roles or schemas must not be silently adopted, repaired, renamed, or replaced.
- Retain Windows Credential Manager for local secrets. The existing local Windows account may remain the trust boundary; other processes running as that same user can access its credentials. This limitation must remain documented. Never embed passwords in documentation or examples. Future production credentials require separate authorization and protection.
- Existing trusted administrative authority remains available for exceptional changes, destructive recovery, ownership corrections, and unexplained drift. Ordinary operation must not rely on AI.

#### Operational Evidence

- Require deterministic, sanitized evidence distinguishing run authorization; selected environment and verified identity; approved revision and artifact hashes; execution phases; advisory lock outcomes; preflight and postcondition outcomes; commit certainty; and failure/recovery classification.
- Exclude passwords, connection URLs containing secrets, raw credential-provider errors, private SQL parameter values, and unredacted environment dumps from evidence and diagnostics.
- Raw operational logs stay outside Git. Only independently reviewed, sanitized validation evidence may accompany an authorized Git checkpoint.
- Local logs accessible to the same Windows account are not tamper-proof. Do not claim audit persistence is implemented or invent a retention period.
- **UNRESOLVED OPERATIONAL PREREQUISITES:** The precise audit destination, retention policy, failed-write behavior, and operational evidence procedure must be established and owner-approved before migration execution is authorized. No new paid logging service is authorized.

#### Migration Deterministic Autonomy Review

- **Design PASS:** The Checkpoint 4 contract specifies deterministic environment/identity selection, approved artifact verification, one-revision execution, ownership/search-path controls, locks/timeouts, schema/grant and drift checks, rollback, uncertain-commit classification, verified repeat execution, and sanitized evidence/recovery boundaries. Exceptional administrative intervention is a documented control.
- **Implementation and behavior awaiting validation:** Framework implementation, negative-path tests, authorized bootstrap, PostgreSQL validation, independent security review, and deterministic autonomy implementation review remain separately gated. Documentation completion does not prove migration behavior or production readiness.
- Future validation must test failure handling and recovery as well as successful execution, including lock contention, drift, privilege/identity mismatch, rollback, uncertain commits, and verified already-applied targets. Resolve the operational prerequisites in `WEBSITE_PLAN.md` before seeking execution authorization.

### Development Cost Control

This permanent rule applies to all current and future OAF Website development.

- Prefer local implementation and validation using existing development tools and infrastructure.
- Do not provision or activate paid hosting, databases, email services, external subscriptions, or cloud resources without explicit owner approval.
- Separate local development readiness from production provisioning and public launch readiness.
- Identify expected recurring charges and usage-based costs before requesting approval.
- Do not treat design or implementation approval as authorization to incur expenses.

### Website Visual-Iteration Rule

- Ordinary visual website work does not require app-style validation overhead.
- For small HTML/CSS visual changes, use `SOL / HIGH` with a narrow, lightweight prompt.
- Examples include spacing, colors, image placement, typography, responsive layout, hover effects, button styling, and section arrangement.
- For these changes, owner Eyes & Clicks review in the browser at relevant window sizes remains the primary validation for subjective visual and usability judgments.
- Do not ask Codex to perform extensive validation for simple visual edits unless there is a specific reason.
- Reserve heavier reasoning and validation for structural, cross-page, accessibility, deployment, security, forms, or higher-risk interactive changes.

#### Automated Browser Validation

- Prefer Playwright for automated website browser validation, with checks proportional to the change.
- Keep the working directory in the OAF Website repository and use the verified sibling Python interpreter: `..\GraManna\.venv\Scripts\python.exe`. GraManna's virtual environment contains Playwright 1.61.0, and the shared Chromium browser cache is available. No additional installation is needed for local testing.
- A live smoke test confirmed successful Playwright import, Chromium launch, localhost HTTP 200, and GraManna page load. Browser and temporary server cleanup also passed.
- Serve website pages through localhost when browser testing requires it, and clean up browsers and temporary servers after testing.
- Check responsive layouts, navigation, keyboard behavior, interactive controls, and browser errors as appropriate for the change.
- If the shared interpreter or browser becomes unavailable, report the specific failure before using an alternative validation method. Do not assume Playwright is unavailable simply because the default Python or Node environment cannot import it.
- Automated browser checks complement owner Eyes & Clicks review for subjective visual and usability judgments.

### After Each Codex Run

- Review the Codex final report returned to the clipboard.
- Visually inspect the affected website area in the browser where applicable.
- Request refinements as needed.
- Do not commit or push during active visual iteration unless an approved checkpoint has been reached.

10/12/26

## OAF Website and GraManna — Shared Public Services and Admin Integration

**Planning date:** 2026-10-12  
**Status:** OWNER-APPROVED DESIGN DIRECTION — IMPLEMENTATION PENDING  
**Repositories:** OAF Website and GraManna (separate repositories)  
**Purpose:** Establish a coordinated approach for public State Requests, Launch & Availability Notifications, mobile application release links, and unified administrative reporting.

### 1. Background and Existing Foundation

The OAF Foundation website currently provides two working public features:

1. **State Requests:** Visitors can express interest in GraManna becoming available in their state.
2. **Launch & Availability Notifications:** Visitors can subscribe to announcements concerning the web application, Android application, Apple iOS application, or availability in their state.

These features have been implemented and verified using Flask, PostgreSQL, automated testing, and live DEVELOPMENT validation.

OAF Website PostgreSQL migrations `0001`, `0002`, and `0003` are complete in TESTING and DEVELOPMENT.

The completed implementation was committed and pushed to GitHub:

`adaa14909d94dd3b8bc710b2f4aefaffdbe7ea3c`

The current notification system records subscriptions and consent, but actual outgoing email delivery has not yet been implemented.

The GraManna application is currently being developed primarily as an online web application. Android and Apple iOS versions are potential future releases.

These two public systems should operate as complementary entry points rather than developing unnecessary duplicate services.

### 2. Primary Integration Objective

A visitor may discover GraManna through either:

- The OAF Foundation website.
- The GraManna web application's public homepage.

Visitors should not have to know which organization website or application they should visit to express interest in GraManna.

Both public entry points should provide the appropriate features while relying on one authoritative backend for each shared service.

The GraManna admin dashboard should provide a combined view of activity from both entry points.

**Governing principle: Two public entry points, shared authoritative services, one administrative reporting destination.**

### 3. State Requests — Both Public Homepages

#### OAF Foundation Website

Preserve the existing State Request interface and behavior.

Visitors can select a state and submit a request expressing interest in GraManna availability.

Existing validation, duplicate-recognition rules, privacy protections, and deterministic counting behavior remain authoritative unless a future approved contract explicitly changes them.

#### GraManna Web Application Homepage

Add a State Request feature to the public-facing GraManna homepage.

This serves people who discover GraManna directly without first visiting the foundation website.

The feature should be accessible without requiring unnecessary account registration or a subscription to another service.

The public-facing experience should remain simple:

1. Visitor chooses the state.
2. Visitor submits a request.
3. The system validates the request.
4. The request enters the shared authoritative State Request system.
5. The visitor receives appropriate confirmation.

#### Shared State Request System

Both homepages must ultimately use the same authoritative State Request service and reporting rules.

The preferred initial architecture is to retain the existing OAF Website PostgreSQL State Request system as the source of truth.

GraManna should communicate through an appropriately secured server-side integration, rather than accessing OAF PostgreSQL directly from the public browser.

Do not create a second independent GraManna State Request database that later requires synchronization or reconciliation.

Preserve existing duplicate-recognition rules. Because browsers and cookies across different domains do not automatically share identity, any proposed cross-site deduplication change requires explicit inspection and privacy-aware design. Do not claim that requests from the same person on two websites can already be reliably identified as duplicates.

#### Source Attribution

Where practical, record the public entry point:

- `oaf_website`
- `gramanna_web`

This allows reporting by source while maintaining combined state totals.

If capturing source attribution requires a schema change, use a new approved migration. Do not rewrite applied migrations `0001` through `0003`.

Source attribution is useful for reporting but must not delay the essential shared State Request functionality unnecessarily.

#### State Availability Rules

When a state becomes officially available, public interfaces should follow the authoritative state availability rules.

For example, a state already available for the applicable service should not continue inviting requests for that same pending availability.

Any suppression or replacement behavior must be deterministic and based on approved state availability records.

Do not confuse the State Request feature with GraManna user eligibility or social feature access. This integration must not introduce unintended eligibility restrictions.

### 4. Android and Apple iOS — Adaptive GraManna Homepage

The GraManna online web application should include dedicated sections for its future mobile versions.

Each mobile platform must be managed independently.

#### Before Android Release

Display:

**GraManna for Android — Coming Soon**

Provide a **Notify Me** option.

Interested visitors can enter their email address, explicitly consent, and subscribe to the Android release announcement.

The subscription is recorded in the existing authoritative OAF Website notification system.

#### After Android Release

Once the Android application is officially released and its verified Google Play Store URL has been configured, automatically replace the Android Notify Me option with:

**Get GraManna on Google Play**

The displayed download link must point to the approved official application listing.

#### Before Apple iOS Release

Display:

**GraManna for Apple iOS — Coming Soon**

Provide a **Notify Me** option.

Interested visitors can enter their email address, explicitly consent, and subscribe to the Apple iOS release announcement.

The subscription is recorded in the same authoritative notification system.

#### After Apple iOS Release

Once the Apple iOS application is officially released and its verified Apple App Store URL has been configured, automatically replace the iOS Notify Me option with:

**Download GraManna on the App Store**

The link must point to the approved official application listing.

#### Independent Release Behavior

Android and Apple iOS must not be coupled.

Examples:

- Neither released: both display Notify Me.
- Android released, iOS pending: Android displays Google Play; iOS displays Notify Me.
- iOS released, Android pending: iOS displays App Store; Android displays Notify Me.
- Both released: both display their official download links.

No website code change should be needed merely to switch an already-supported platform from notification signup to its verified download link.

### 5. Deterministic Release Status Management

Provide a minimal authoritative server-side configuration or registry for each application platform:

- Platform identity: Web, Android, or Apple iOS.
- Approved public release status.
- Official release/download URL when applicable.
- Release or activation timestamp when needed.
- Authorized administrator control.
- Audit record for significant release status changes.

The baseline behavior must use deterministic rules.

**If a platform is not released:**
Display the appropriate notification signup or Coming Soon state.

**If a platform is officially released and has a verified download URL:**
Display the corresponding official download link.

**If release status or the official URL is incomplete, invalid, or inconsistent:**
Do not display an unverified download link.

If an official store listing becomes unavailable, the system must support an authorized administrative correction or suspension rather than continuing to advertise an invalid link.

Routine behavior should be autonomous through server-side rules and configuration.

AI must not be required to determine release status, approve URLs, switch homepage content, or deliver ordinary operational behavior.

### 6. Shared Notification Subscription System

The OAF Foundation website remains the authoritative service for Launch & Availability Notification subscriptions.

The GraManna web homepage should reuse that service rather than creating a separate mailing list or subscriber database.

#### OAF Foundation Website

Continue supporting relevant subscription categories:

- Web application launch.
- Android application release.
- Apple iOS application release.
- Availability in a selected state.

As releases occur, the interface may adapt to stop offering obsolete release notifications and show the appropriate available application links.

#### GraManna Web Homepage

Initially expose only the notification options relevant to its public homepage:

- Android release notification while Android is pending.
- Apple iOS release notification while iOS is pending.

A state availability notification option may be added later if warranted, but it should not be duplicated automatically merely because the foundation website offers it.

The web application launch notification generally serves prelaunch visitors on the foundation website. Once the web version is publicly available, its homepage should direct people to the actual web application instead.

#### Shared Subscription Rules

Regardless of entry point:

- Use the same authoritative subscriber records.
- Preserve explicit consent requirements.
- Preserve existing subscription preference rules.
- Preserve unsubscribe functionality.
- Prevent unnecessary duplicate active subscriptions.
- Do not expose private unsubscribe identifiers.
- Do not transfer subscriber email addresses into GraManna merely for admin statistics.
- Keep provider-based outgoing email delivery separate from the subscription collection feature until the delivery capability is implemented and approved.

When a mobile platform launches, subscribed users may receive its release announcement through the future authorized email delivery system.

Do not claim that an email was sent until the delivery system actually records the appropriate delivery outcome.

### 7. Unified GraManna Admin Dashboard

The existing GraManna admin dashboard should become the primary location for viewing aggregate activity from both public entry points.

Provide an appropriately named section such as:

**OAF Website & GraManna Public Interest**

#### State Request Statistics

Display:

- Combined total of accepted State Requests.
- State-by-state request counts.
- Optional breakdown by OAF Website versus GraManna homepage.
- Appropriate activity timestamps or reporting date where useful.

The combined totals must come from the authoritative State Request system.

Do not add together independently generated figures that might double-count the same underlying records.

Use the system's established counting semantics. Do not misrepresent accepted requests as verified unique people.

#### Notification Statistics

Display:

- Total active notification subscriptions.
- Active Web launch subscriptions.
- Active Android release subscriptions.
- Active Apple iOS release subscriptions.
- Active state availability subscriptions.
- Optional state breakdown for availability subscriptions.

A subscriber may select multiple categories.

Therefore, category counts must be identified as preference counts and must not be summed and presented as the number of unique subscribers.

#### Administrative Access

Only appropriately authorized GraManna administrators may access these statistics.

Access enforcement must occur on the server, not merely through hidden frontend controls.

The integration should normally transfer aggregate reporting data only.

No subscriber emails, private unsubscribe credentials, browser-recognition secrets, or sensitive operational records are required for this reporting interface.

Prefer GraManna's existing admin dashboard layout and navigation conventions rather than introducing a separate admin application.

Follow existing GraManna admin pagination requirements wherever individual tabular records are involved.

### 8. Recommended Technical Integration

Keep the OAF Website and GraManna repositories and their application responsibilities separate.

Proposed data flow:

**Public State Requests**

OAF Website Homepage
    -> Authoritative OAF State Request Service

GraManna Public Homepage
    -> GraManna Backend
    -> Authorized OAF State Request Service

**Public Mobile Release Notifications**

OAF Website Homepage
    -> Authoritative OAF Notification Service

GraManna Public Homepage
    -> GraManna Backend
    -> Authorized OAF Notification Service

**Administrative Reporting**

Authoritative OAF PostgreSQL Data
    -> Secure Read-Only Aggregate Interface
    -> GraManna Backend
    -> Existing GraManna Admin Dashboard

Choose the simplest secure implementation supported by the existing applications.

Key requirements:

- Server-side authentication and authorization for cross-application requests where applicable.
- No public exposure of PostgreSQL credentials.
- No direct public-browser access to administrative database functionality.
- Validation and abuse controls for public submissions.
- Existing deterministic request and subscription rules remain authoritative.
- No duplicate data synchronization infrastructure without a demonstrated need.
- Predictable and privacy-safe error handling.
- Clear separation of TESTING, DEVELOPMENT, and eventual production data.
- Safe behavior when the remote service is unavailable.
- Auditable administrative overrides for official availability and release decisions.

Use proportionate security mechanisms based on the actual inspected architecture. Avoid unnecessary frameworks and infrastructure.

### 9. DEVELOPMENT and Production Separation

The currently completed OAF Website features are verified in local TESTING and DEVELOPMENT.

Until public deployment, the recorded request and subscription numbers represent development/testing activity, not production public interest.

The GraManna admin dashboard must clearly identify the environment from which statistics are being retrieved.

Never silently combine DEVELOPMENT or TESTING records with production totals.

Production connection details and credentials must be configured separately through approved secure configuration.

Do not run migrations, provision new credentials, or activate public integrations without the applicable approved checkpoints.

### 10. Deterministic Autonomy Requirements

The integration should operate with minimal routine administrator intervention once correctly configured.

The following must be deterministic wherever practical:

1. State Request validation and acceptance.
2. Existing duplicate-recognition and counting behavior.
3. Combined aggregate reporting.
4. Notification subscription validation and consent recording.
5. Subscription preference management and unsubscribe behavior.
6. Independent Android and Apple iOS release-state evaluation.
7. Automatic homepage substitution of Notify Me with official download links.
8. State availability recognition and associated public interface behavior.
9. Authorization and privacy filtering for admin statistics.
10. Error handling, safe fallback states, and release-state correction.
11. Future scheduled or event-triggered announcement processing, once email delivery is contracted.

Authorized administrators retain control over official state availability decisions, platform release approvals, official store links, and exceptional corrections.

Significant administrative changes must be auditable.

AI may optionally assist with summaries or recommendations but must not be a required component of the operational baseline.

Before finalizing the implementation contract, perform the required deterministic autonomy review across all applicable governance and decision-making areas.

### 11. Implementation Scope and Sequencing

This is a planned cross-application integration, not authorization to modify either repository immediately.

Recommended execution sequence:

**Phase A — Bounded Inspection**

Inspect only the relevant existing systems:

- OAF Website State Request backend and PostgreSQL schema.
- OAF Website notification backend and PostgreSQL schema.
- Existing OAF Website API/server capabilities.
- GraManna public homepage structure.
- GraManna backend integration conventions.
- Existing GraManna admin dashboard and authorization model.
- Existing authoritative state availability and release-related registries, if any.

Identify the smallest compatible integration without duplicating existing services.

**Phase B — Focused Integration Contract**

Establish:

- The shared service boundaries.
- Required public request endpoints.
- Required aggregate read-only reporting endpoints.
- Validation, authentication, authorization, and privacy protections.
- Any necessary source attribution changes.
- Deterministic release-status configuration.
- Exact admin display requirements.
- Failure handling and essential validation criteria.

Preserve existing governing contracts and implemented behaviors unless an explicit approved change is necessary.

**Phase C — State Requests and Admin Reporting**

Implement the shared State Request entry point on the GraManna homepage.

Connect the GraManna admin dashboard to combined authoritative State Request statistics.

Add notification aggregate reporting using the existing subscription records.

Keep this work focused on essential functionality.

**Phase D — Adaptive Mobile Release Sections**

Add Android and Apple iOS sections to the GraManna public homepage.

Connect their Notify Me forms to the authoritative OAF notification service.

Implement deterministic platform-specific switching to official download links after authorized release.

Do not create a second notification system.

**Phase E — Focused Verification**

Validate:

- Requests from both public homepages.
- Shared authoritative persistence and counting.
- Preservation of existing duplicate-recognition behavior.
- Notification preferences and consent.
- Correct admin totals and category breakdowns.
- Admin-only access.
- Android/iOS independent release switching.
- Safe behavior for missing or invalid store links.
- Cross-application failures and environment isolation.
- No regressions to completed OAF Website features or GraManna workflows.

Use Playwright and relevant backend/database tests as primary objective validation tools.

Do not require repeated owner Eyes & Clicks approval for already approved interfaces unless material new subjective UI changes warrant it.

Do not repeat completed migration validation or unrelated test campaigns without a concrete reason.

### 12. Scope Control and Workflow Requirements

This integration must remain proportionate.

Prioritize:

- Working public features.
- One authoritative record system.
- Secure aggregate administrative visibility.
- Deterministic autonomous behavior.
- Minimal necessary integration code.
- Focused validation.

Avoid:

- Separate duplicate subscriber lists.
- Separate duplicate State Request databases.
- Unnecessary data replication.
- New admin frameworks.
- Optional analytics platforms.
- Elaborate event infrastructure without a demonstrated need.
- Repeated theoretical design rounds.
- AI-dependent operational decisions.
- Unnecessary modification of already closed Cargo work.

GraManna Cargo 22 and other existing Cargo commitments must not be interrupted or silently expanded.

Any necessary changes to existing GraManna contracts should follow the applicable contract-first workflow and owner approval requirements.

Use the established Cargo workflow only where the inspected change genuinely requires a Cargo contract or slice. Do not create a new Cargo merely for organizational convenience.

Retain all pre-existing owner-authored documentation changes for the next approved Git checkpoint unless the owner explicitly excludes a change.

No staging, committing, pushing, production activation, or database migration may occur without the appropriate owner approval.

### 13. Intended Final Experience

A visitor discovers GraManna through the foundation website or directly through the GraManna web application.

If GraManna is not yet available in the visitor's state, the visitor can submit a State Request through either public entry point.

That request enters one authoritative system.

The GraManna admin dashboard displays the combined request totals by state.

On the GraManna web homepage, Android and Apple iOS each initially offer release notifications.

As each mobile application is officially released, the corresponding notification option automatically changes to its verified official store download link.

The two mobile release transitions are independent.

All subscription activity is maintained by one authoritative notification system, and aggregate subscription statistics are viewable from the GraManna admin dashboard.

The result is a coordinated OAF Website and GraManna experience without duplicate services, unnecessary administrative work, or conflicting statistics.

**Standing design direction:** Two public entry points, shared authoritative services, one administrative reporting destination, and deterministic lifecycle-driven homepage behavior.


## Step 6G / Checkpoint 6G-1: notification contract and persistence source (2026-10-15)

Owner approval authorizes this bounded OAF Website source/offline checkpoint.
This current entry supersedes earlier deferral statements only for this scope.
It creates no real migration approval/authorization, applies no migration, accesses
no real credential/provider, and enables no outgoing email or public verification
workflow. No GraManna source, deployed service, Git index, commit or remote is changed.
The approved shared-service architecture and current public behavior remain intact.
The existing `notifications` record is the only authoritative recipient email and
consent source. No duplicate mailing list, account system or admin app is added.

### Internal contract and verification lifecycle

`NotificationDeliveryStore(engine, protected_secret, environment)` is an internal,
unregistered persistence service. Inject the existing verified OAF runtime engine,
its explicit matching environment, and the persistent protected key. There is no
startup schema creation, credential lookup, route registration, scheduled worker,
Brevo adapter, GraManna release transport, webhook or sender. Existing browser and
backend integration subscription responses still truthfully say no email was sent.

A missing verification record means unverified, including every existing 0003
subscriber. The additive revision does not backfill or promote verification.
Existing explicit consent validation and active-email/preference immutability are
unchanged. `subscription` always references the original permanent
`notifications.unsubscribe_digest`; a new consent lifecycle requires its own
verification. Original receipt and unsubscribe signing behavior are preserved.

`request_confirmation(email)` is a sensitive internal seam for the future adapter,
not a public response. It generates a random 256-bit confirmation token only for
an active, unverified, unsuppressed lifecycle. It stores a domain-separated HMAC
SHA-256 digest, issue time and fixed 24-hour expiry. Only the transient caller
receives the raw token; never log, persist or return it in a public API response.
The same protected key uses distinct confirmation, mailbox, budget and claim
signing domains, separate from existing recognition/unsubscribe domains. All
workers/restarts must retain the key; rotation needs separately reviewed handling
because suppression keys and outstanding capability digests depend on it.

Server-side limits are durable: one eligible mailbox request per 60 seconds and
at most five per rolling 24-hour window across consent lifecycles; a shared
1,000-request rolling 24-hour budget includes unknown/verified/suppressed valid
addresses. Limits never rely on browser controls. Normalized mailbox HMACs retain
no second email list. These conservative source constants are backend policy;
changing them requires source review. Future activation must preserve existing
origin/CSRF/transport protections and fixed generic responses for every valid
address, including unknown, verified, throttled and suppressed addresses. Invalid
syntax can retain the existing fixed validation response. No endpoint exposes the
internal token-or-None result or subscription existence.

Resend replaces the current digest and revokes the older token. `confirm(token)`
is single-purpose and returns only `verified` or `unavailable`. An exact-token
repeat is permitted only while that same lifecycle remains active/unsuppressed
and the original token has not expired; it neither renews expiry nor moves the
original verified timestamp. Wrong, malformed, expired, future-issued, superseded
or withdrawn tokens cannot verify. Concurrent confirmation serializes to one
original timestamp. Withdrawing invalidates old links without deleting evidence;
resubscription neither revives old verification nor resets mailbox abuse limits.

### Additive persistence inventory

All six new tables are schema-qualified under `oaf_website`. Every table has a
named primary key and named checks; foreign keys are immediate, nondeferrable,
without cascading lifecycle deletion or updates. Dates are timezone-aware UTC.
No historical 0003 column, helper, index, grant or migration byte is changed.

| Table | Authoritative fields and constraints |
| --- | --- |
| `notification_verification` | PK/FK `subscription`; unique `token_digest`; `issued_at`, `expires_at`, nullable `verified_at`; digest and ordered-time checks. No row means unverified. |
| `notification_confirmation_limits` | PK `bucket` (HMAC); `window_start`, `last_requested_at`, `requests`; digest, time and bounded-count checks. One global bucket plus per-mailbox buckets. |
| `notification_release_events` | PK `event_id`; `source_approval_id`, `environment`, `platform`, `release_id`, `release_url`, `approved_at`, `audience_cutoff`, fixed `content_version`, canonical `payload_digest`, `status`, `created_at`, `updated_at`; UNIQUE `(environment, platform)` forbids a second semantic launch announcement even under another event ID. |
| `notification_deliveries` | Composite PK `(event_id, subscription)`; FKs to original event and consent lifecycle; `status`, bounded `attempts`, `claim_digest`, `lease_until`, `next_attempt_at`, allowlisted `outcome`, nullable `provider_message_id`, `created_at`, `updated_at`, nullable `accepted_at`; status/claim/retry/acceptance/time checks; `(status, next_attempt_at)` and `(status, lease_until)` recovery indexes. |
| `notification_delivery_attempts` | Composite PK `(event_id, subscription, attempt)`; composite delivery FK; `claimed_at`, nullable `submitting_at`, `finished_at`, allowlisted `outcome`, nullable `provider_message_id`; attempts 1--3 and timestamp checks. Previous completed attempts remain evidence. |
| `notification_suppressions` | PK `mailbox_digest` (HMAC of authoritative normalized email); first `reason` and `created_at`; fixed reasons `hard_bounce`, `complaint`, `provider_block`, `owner_policy`; INSERT-only suppression survives every lifecycle. No automatic removal or routine override. |

There are no stored API keys, raw confirmation/claim/unsubscribe tokens, free-form
provider errors, duplicated recipient emails, arbitrary recipient arrays, subject
lines or message bodies. Provider identifiers accept only a bounded ASCII allowlist.
Delivery eligibility/audit is represented by immutable event/lifecycle references,
cutoff and template version plus per-attempt timestamps and sanitized outcomes.

### Release-event authority, selection and deduplication

The internal acceptance contract takes exactly the nine event fields above,
excluding persistence-derived digest/status/timestamps. Event and source-approval
identities are canonical UUIDs. Environment must match the injected runtime;
Android and iOS are independent. Approval cannot be future-dated and the audience
cutoff cannot exceed approval. Supported template/content is exactly
`mobile-launch-v1`; no release payload supplies email copy or recipients.

For this bounded source version Android release identity is the package ID, with
its exact `https://play.google.com/store/apps/details?id=<package>` reference.
iOS identity is its numeric app ID with exact
`https://apps.apple.com/app/id<id>` reference. Alternative localized/marketing URLs
require deliberate contract review rather than relaxed arbitrary URL acceptance.
These checks validate the reference shape; they do not prove a listing exists or
that GraManna owns it. The later authenticated handoff must establish the actual
authorized official listing and approval provenance. No actual GraManna handoff
interface or existing release registry is assumed here.

A repeated event ID with identical normalized payload is idempotent; any changed
payload conflicts. A different ID for an already accepted environment/platform
also conflicts, including a changed release identity. Content and source identity
cannot be updated through runtime column grants. Preparation atomically selects
only active subscribers with that platform preference, consent created by the
cutoff, verification completed by the cutoff and no durable mailbox suppression.
Later verification or resubscription cannot enlarge that audience. The event and
per-lifecycle unique delivery keys prevent repeated preparation from duplicating
work. A rollback leaves `received` and no partial audience; recovery never marks
an unprepared event complete merely because it has no deliveries yet.

The future single GraManna administrator approval action must produce its durable
source approval identity and stable event ID, then hand off automatically under
separately approved server-side authentication. Ordinary notifications require no
second administrator announcement decision. This checkpoint adds no public or
administrator event ingestion endpoint and no general announcement capability.

### Claims, outcomes and deterministic recovery

A transaction-scoped PostgreSQL advisory lock serializes this bounded subsystem
across workers. Subscription row locks also serialize the final eligibility check
with the existing withdrawal UPDATE. The lock is database-local, fixed and
transactional; no lock service or process-local claim authority is introduced.
Offline tests model serialization, but cannot certify PostgreSQL locking semantics.

Delivery transitions are explicit:

- `pending` or retry-eligible `failed` -> `claimed`: a fresh random claim, stored
  only as a separate HMAC, five-minute lease and a new immutable attempt identity.
- `claimed` -> `submitting`: matching one-use claim, unexpired lease and another
  authoritative lifecycle/preference/cutoff/suppression check. Only this committed
  dispatch boundary returns the existing subscriber email to the future adapter.
  A consumed claim cannot authorize a second submission. Withdrawal or suppression
  that linearizes before this boundary prevents dispatch; an already in-flight
  provider submission cannot be recalled by a later withdrawal.
- `submitting` -> `accepted`, `rejected`, `failed` or `uncertain` using only fixed
  provider-neutral evidence classifications. Acceptance records a provider ID when
  supplied and `accepted_at`; it never claims final inbox delivery.
- `not_submitted` and `retryable_rejection` may permit `failed` retries only where
  the future adapter has conclusive evidence that the provider did not accept the
  attempt. Delays are 60 seconds after attempt 1 and 300 after attempt 2; attempt
  3 exhausts the budget. Every retry repeats eligibility checks.
- Expired `claimed` work becomes `failed` under the same bounded backoff. Expired
  `submitting` becomes `uncertain`; timeout/connection loss after possible submission
  is `submission_unknown`, never an automatic resend. Lost dispatch-commit
  acknowledgement also forbids repeating the submission.
- Ineligible/withdrawn/suppressed pending or claimed work becomes `suppressed`
  before dispatch. Old queued work always references its original lifecycle.
  Suppressing a pending retry never rewrites a previously completed attempt.

Event status is `received`, `ready`, `completed` or `attention`. `completed` means
no eligible work remains, not that every message was delivered. Any uncertain
recipient makes the event `attention`; other independently eligible recipients can
still proceed. Empty eligible audiences complete deterministically. Retrying event
acceptance/preparation after an uncertain acknowledgement converges on the same
immutable records. Ordinary persistence failures roll back; no private exception
or raw provider body is written to outcome fields or public responses.

There is deliberately no retry/override/reset API for uncertain or terminal work.
Uncertainty is durable until a separately implemented adapter can reconcile
conclusive provider evidence under the same original event/attempt identity.
Absence of evidence is not permission to send again. This source checkpoint does
not implement reconciliation transport or claim that provider lookup capabilities
exist. No routine AI or administrator decision can bypass these boundaries.

### Revision and approval boundaries

`0004_notification_delivery` has parent `0003_notifications`. Its only new upgrade
transition is exact 0003 -> 0004; a distinct authorization can later permit an exact
0004 no-op. Earlier single-revision contracts remain supported. Base/0001/0002
jumps to 0004, downgrade, stamp, repair, automatic fallback and multi-revision
execution remain prohibited. Revisions 0001--0003 are byte-for-byte preserved.

The manifest includes the successor, its exact object/grant/dependency inventory
and hashes of the schema/catalog helpers. Approval stays
`pending_independent_review`; changed hashes are integrity, not approval. Old
approval or execution records do not authorize these new artifacts. Catalog checks
cover exact definitions, parsed boolean grouping, indexes, named FKs and internal
RI triggers, dependency edges, ownership, private generated types, explicit column
ACLs and effective privileges for every registered role. PostgreSQL rendering and
trigger/dependency expectations still require later authorized live certification.

Only the matching schema owner can execute DDL. Matching runtime roles receive
SELECT/INSERT on the six feature tables and UPDATE only on lifecycle/status/audit
columns listed in `notification_delivery_schema.MUTABLE`; event identities/content,
recipient references and suppression evidence cannot be updated. No DELETE,
blanket UPDATE, REFERENCES, TRIGGER, schema CREATE, nonowner type USAGE or grant
options are added. Existing notification grants and migration metadata protections
remain unchanged. No new credential, role, service or package is provisioned.
Existing independent review, TESTING-before-DEVELOPMENT evidence, single-use
owner-issued authorization, audit, locking, transaction and uncertain-commit gates
remain mandatory. No migration is applied, stamped, downgraded or repaired here.

### Deterministic autonomy review and next gate

Source review covers consent, mailbox ownership, expiry/replay/revocation, lifecycle
binding, immutable preference preservation, event deduplication, fixed audience,
concurrent claims, withdrawal/suppression, bounded retry, uncertain outcomes and
audit rollback/recovery. All ordinary decisions are explicit backend rules; no AI,
per-subscriber review or repeated administrator approval is required.

Genuine governance exceptions are official launch approval/URL provenance, future
policy/secret changes, independently reviewed migration execution and exceptional
suppression corrections. This checkpoint exposes no administrative override for
these. Provider uncertainty is a deterministic hold pending conclusive evidence,
not a routine administrator resend queue. Coarse locking and atomic audience
preparation suit this bounded foundation; capacity must be measured before a live
worker is separately approved. No unapproved scaling infrastructure is added.

Next implementation checkpoint: the separately authorized Brevo adapter source
and offline fake-provider validation. It must use fixed reviewed templates, protect
the provider secret, map responses to conclusive/retryable/uncertain evidence,
persist before dispatch, handle rate limits and reconcile uncertainty safely. It
must also design reliable confirmation-message handoff before registering a public
verification/resend workflow. Requesting a replacement token is not by itself a
durable confirmation-email outbox; that adapter must explicitly close the crash
gap between token issuance and message submission without storing raw bearer
material in these records. Do not expose an unusable public confirmation workflow.
GraManna authenticated release delivery, a live worker, real webhooks, provider
setup, actual migration application and live email remain separate approvals.

Existing aggregate reporting continues to count active consent/preference records;
this checkpoint does not relabel those totals as verified recipients or expose
subscriber identities to GraManna. Verified release-audience eligibility is separate.


### Checkpoint 6G-1 offline validation evidence

Final bounded gate: **676 passed in 35.71 seconds**, zero unexpected external-access
attempts. Four new production modules/revision: **408/408 executable statements and
164/164 branches, 100%**. Diff coverage for existing migration policy modules:
**38/38 changed executable lines, no missing branches on changed decisions**.
This is scoped coverage of the checkpoint, not a claim of whole-repository coverage.
Unrelated suites and completed live migration campaigns were not run.

Explicit file selection (using the dedicated website interpreter, `-B`, disabled
plugin autoload, empty `PYTEST_ADDOPTS`/`PYTEST_PLUGINS`, repository/tests on
`PYTHONPATH`, and the unchanged early `-p migration_offline` isolation guards):

```
tests/test_notification_delivery.py
tests/test_notification_delivery_migration.py
tests/test_notifications.py
tests/test_integrations.py
tests/test_migration_artifacts.py
tests/test_migration_authorization.py
tests/test_notification_migration.py::test_exact_catalog_includes_preserved_state_requests
```

New-file tests include minimal synthetic catalog dispatch for prior states solely
to prove the changed validator preserves them. Synthetic migration/authorization
records live only in guarded test temporary directories. There is no PostgreSQL,
Credential Manager, Brevo, SMTP or external network access. Coverage tooling is
reused read-only from the existing shared environment under the website interpreter
without installation or GraManna writes. The test process exports tracer arcs to
JSON; a separate metadata-only report process writes coverage's SQLite data, so
the test process never disables its database/network/credential guards.

Terminal progress was simultaneously logged and the established OAF visual
completion/failure alert was reused with an accurate OFFLINE title. Local ignored
evidence is under `.pytest_cache/checkpoint6g1/`: `initial.json`, `final.json`,
`focused-final.log`, `coverage-final.log`, `coverage.json`, `diff-coverage.json`,
`measure.py`, `report_coverage.py`, `alert.ps1`, and preserved `before/` snapshots.

All initial owner-authored files are preserved; original document bytes remain
exact prefixes. Original 0001--0003 revision bytes match the initial inventory.
Task-added whitespace checks pass. Repository-wide `git diff --check` still flags
three pre-existing Markdown hard-break lines in the owner's WORKFLOW addition
(lines 196--198); those original bytes were deliberately retained.

Exact task file inventory:

- `docs/WEBSITE_PLAN.md`
- `docs/WORKFLOW.md`
- `migrations/manifest.json`
- `migrations/versions/0004_notification_delivery.py`
- `oaf_website/migration_authority.py`
- `oaf_website/migration_validation.py`
- `oaf_website/notification_delivery.py`
- `oaf_website/notification_delivery_schema.py`
- `oaf_website/notification_delivery_validation.py`
- `tests/migration_offline.py`
- `tests/test_migration_artifacts.py`
- `tests/test_migration_authorization.py`
- `tests/test_notification_delivery.py`
- `tests/test_notification_delivery_migration.py`


**SOURCE IMPLEMENTATION / OFFLINE VALIDATION: complete. MIGRATION APPLIED / LIVE
EMAIL DELIVERY: not performed or authorized.** This checkpoint establishes no
live delivery readiness. The next adapter checkpoint and separate operational
approval gates above remain required. Git staging, commits and pushes are absent.


## Checkpoint 6G-2: Brevo adapter source and offline validation (2026-10-15)

Bounded adapter/release implementation and its offline gate PASS. The complete
confirmation-delivery requirement remains BLOCKED at the explicitly required
schema/contract approval boundary below. This entry does not declare the whole
checkpoint complete or authorize live delivery. It supplements the preserved 6G-1
contract; no prior feature, owner documentation or Contact integration is removed.

### Repository and preservation evidence

OAF Website only: `C:/Users/ovisa/Documents/OAF_App/Development/OAF Website`.
Initial and final branch: `main`; HEAD:
`adaa14909d94dd3b8bc710b2f4aefaffdbe7ea3c`. Initial inventory: 19 unstaged tracked
paths, 28 untracked paths, no staged paths. Final inventory: the same 19 tracked
paths and 33 untracked paths, no staged paths. Index SHA-256 remains
`755cbdad6334f845525279370fcdc3b3e7c3b6bbd750f57f36af433c4ad9772b`.
All unrelated initial files retain their initial hashes. Both original governing
documents remain exact byte prefixes of their extended versions. Revisions
0001--0004, the manifest and migration authority/catalog code retain their initial
hashes. No GraManna edit, staging, commit, push, reset, cleaning, migration or
operational database access occurs.

### Adapter and protected configuration

`brevo.py` implements one transactional email POST to the fixed
`https://api.brevo.com/v3/smtp/email`. Python's direct HTTPS client uses no proxy,
netrc, cookies, ambient HTTP authorization, redirects or hidden POST retries.
TLS requires certificate and hostname verification with system trust. Custom CA
file/directory overrides fail before connection. Explicit TLS context construction
ignores ambient session-key logging. Connect/TLS timeout is 5 seconds; request and
response socket inactivity timeout is 10 seconds. Response bodies are read only
up to 8,193 bytes, and anything exceeding 8,192 bytes is uncertain. These are socket
inactivity bounds, not a claim of a wall-clock DNS or whole-response deadline.
Compressed bodies, malformed UTF-8/JSON, duplicate fields, nonstandard constants,
unexpected shapes/media types and invalid identifiers are rejected conservatively.

Configuration is injected, with the key excluded from diagnostic representations.
`load_brevo_config` reuses `_validate_environment` and the existing pinned
`_windows_password(..., exact_target=True)` convention. It never performs keyring
backend discovery, provisions records or uses an environment API key. DEVELOPMENT
target is exactly `OAF Website/development/Brevo/ApiKey`; TESTING is separate.
The existing record's nonsecret account metadata must be supplied explicitly by
future protected runtime configuration; it was not discovered or guessed here.
Production is rejected before credential access and requires a separate contract.
No real configuration loader or credential record was accessed during validation.

Fixed request identities:

- From name: `Ovis Alms Foundation`
- From email: `communications@updates.ovisalmsfoundation.org`
- Reply-To: `contact@ovisalmsfoundation.org`

No key, recipient, token, request body, raw provider body or underlying exception is
logged or placed in result/audit diagnostics by the integration. Only allowlisted
outcomes and validated bounded provider identifiers enter the existing ledger.
An echoed API key cannot be persisted as a provider identifier.

### Fixed templates and bounded release processing

`notification_messages.py` contains deterministic text/HTML copy for verification,
Android and Apple iOS. Store URLs must exactly match the approved event's existing
platform/identity contract; source supplies no official listing. Only trusted
server-configured HTTPS `/gramanna.html` pages are accepted, without credentials,
queries, pre-existing fragments or nonstandard ports. Release withdrawal reuses
`UnsubscribeCapabilities.issue(original_subscription)` and the existing
`#unsubscribe=` UI. Original lifecycle identity is never replaced by an email key.

The verification template uses a reserved `#confirm-email=` fragment and states the
existing 24-hour expiry. Rendering is an internal seam only. No browser fragment
consumer, confirmation endpoint or request-to-provider orchestration is registered.
This fragment is currently inactive and must not be sent publicly. A later approved
UI must clear it immediately and POST under existing origin/CSRF controls. Actual
provider link rewriting/tracking and capability confidentiality require separately
authorized live validation; no undocumented tracking-control header is invented.
Provider acceptance never sets `verified_at`.

`NotificationDeliveryStore.dispatch_batch` selects at most 20 due lifecycle
references in stable subscription order using a database LIMIT. `ReleaseDispatcher`
uses existing event recovery/preparation, one-use durable claims and the committed
`begin_submission` boundary. Eligibility is rechecked there immediately before the
HTTP operation: active original consent, platform preference, consent/verification
cutoff and permanent mailbox suppression. Concurrent candidates must still win
the claim. Original atomic audience preparation and its existing capacity boundary
are preserved; the limit bounds provider processing per invocation, not the total
audience preparation scan.

After dispatch, the existing attempt/result transaction records the sanitized
outcome and provider ID. A failed or unacknowledged dispatch commit authorizes no
POST. Failed outcome persistence leaves submitting work for conservative recovery,
without another POST. Results expose only a fixed batch status and processed count;
processed does not mean delivered. No route, scheduler, worker, event ingress,
admin Send action or general-announcement/Cargo 29 capability is added.
The eventual authenticated GraManna release handoff must start automatic processing
from the one authorized approval action, with no second administrator Send action.

### Explicit provider outcomes and deferred feedback

| Evidence | Durable outcome and rule |
| --- | --- |
| Valid 201 and bounded single `messageId` | `provider_accepted` / accepted; no mailbox-delivery claim |
| Valid structured 400/401/402/403/404/405/406/409/410/413/415/422 rejection | `provider_rejected` / terminal rejected; sender/configuration errors never create mailbox suppression |
| Valid structured 429 rejection | `retryable_rejection`; existing 60/300-second schedule, at most three total attempts |
| Failure conclusively before HTTP request submission, including connect/TLS failure | `not_submitted`; same bounded retry and renewed eligibility checks |
| Possible POST followed by timeout/network/TLS loss; 408/5xx, redirects, malformed/oversized/unrecognized response | `submission_unknown` / uncertain; no automatic resend |

A valid message ID accompanying an unexpected status is retained for correlation
without upgrading uncertainty to acceptance. Local close failure cannot erase an
acknowledged acceptance. Existing suppression persists across consent lifecycles.
No provider idempotency key is used or assumed to provide indefinite protection.

Brevo documents delivery/failure webhooks, but this checkpoint implements no
feedback listener, reconciliation lookup or authenticated feedback processing.
The precise later dependency is an approved authenticated, replay/deduplication-safe
feedback contract, durable correlation to the original event/lifecycle/attempt,
allowlisted evidence/state transitions and atomic suppression/feedback persistence.
Uncertain submissions without an acknowledged message ID also require a durable
opaque request/attempt correlation design before reliable reconciliation can be
claimed. Lack of a lookup result is never evidence permitting another send.

Provider references reviewed as documentation only:
[transactional API](https://developers.brevo.com/reference/send-transac-email),
[rate limits](https://developers.brevo.com/docs/api-limits),
[transactional feedback](https://developers.brevo.com/docs/transactional-webhooks).
No actual Brevo API endpoint was called.

### Reliable confirmation handoff: approval boundary and exact next checkpoint

6G-1 `request_confirmation` commits only an irreversible token digest and quota
updates, returning the sole raw random token transiently. A process failure between
that commit and HTTP submission loses the required message. Sending before commit
would instead allow a message for a rolled-back or superseded reservation.
The six approved tables contain no confirmation-message intent/claim/attempt
record. Release deliveries require an actual release-event FK and cannot be reused
as synthetic confirmation events without violating the approved release contract.

No alternate file queue, second subscriber store, raw-token column, token-recovery
shortcut or modification to the approved 0004 artifact is introduced. Verification
sending/public request integration stops at this boundary, as the owner required.
Cooldowns, quotas, expiry, single-purpose confirmation and lifecycle binding remain
unchanged. Tests demonstrate only the explicit synthetic rendering/provider seam,
not a reliable runtime verification-email request.

Exact next implementation checkpoint, requiring owner approval:
**6G-2A: confirmation outbox contract, additive successor source and focused offline
validation.** The smallest approval is for one additive successor revision with
parent `0004_notification_delivery`, defining lifecycle-bound confirmation intent
and attempt history committed atomically with token reservation, plus a reviewed
recoverable token construction that stores no raw bearer material. Its contract
must cover replacement/cancellation, quotas, leases, uncertain commits/submissions,
expiry and bounded retry. The exact artifact inventory must be reviewed before
implementation; no schema for this successor is implemented here. This approval
would remain source/offline only, with no migration or live delivery authorization.

### Focused validation and deterministic autonomy review

Final gate: **663 passed in 18.36 seconds**, zero unexpected external-access
attempts and no skips, errors or xfails. Three new integration modules:
**202/202 executable statements and 56/56 branches, 100%**. Including the changed
complete delivery service: **440/440 statements and 152/152 branches, 100%**.
Every changed candidate-selection decision is covered. No coverage exclusions or
weakened assertions were added.

Explicit test selection:

```
tests/test_brevo.py
tests/test_notification_dispatch.py
tests/test_notification_delivery.py
tests/test_notifications.py
tests/test_integrations.py
```

The dedicated website interpreter, `-B`, empty pytest plugin/options settings,
repository/tests PYTHONPATH, disabled plugin autoload and early
`-p migration_offline` guards are preserved. Only the two new test files were added
to the allowlist. Existing transactional-model SQL support was extended to model
ordered LIMIT, due comparisons and status membership. Tests use synthetic keys,
mock HTTP connections/transports, synthetic recipient mailboxes and the existing
model; no SMTP, HTTP, real credentials or operational database connections occur.
Coverage tracer arcs and its separate metadata-only reporting preserve all guards;
the existing shared coverage installation is read only, with no GraManna writes.
Terminal progress/errors/results remain visible with simultaneous complete logs.
The supported PowerShell alert helper is retained with a 6G-2 OFFLINE title.

Deterministic source review PASS for the implemented scope: verification eligibility
uses unchanged 6G-1 rules; template choice/content, candidate ordering, consent and
suppression, fixed request construction, outcome classification, retry versus hold,
claims/transitions, audit persistence and conservative recovery all use explicit
rules. Ordinary operation requires no AI. This does not certify the missing durable
confirmation handoff or deferred feedback. Official store verification and launch
approval remain authorized GraManna administrator decisions. Source/offline success
does not establish live database, provider or deployment readiness.

Exact task file inventory:

- `oaf_website/brevo.py` (new)
- `oaf_website/notification_messages.py` (new)
- `oaf_website/notification_dispatch.py` (new)
- `oaf_website/notification_delivery.py`
- `tests/test_brevo.py` (new)
- `tests/test_notification_dispatch.py` (new)
- `tests/test_notification_delivery.py`
- `tests/migration_offline.py`
- `docs/WORKFLOW.md`
- `docs/WEBSITE_PLAN.md`

Ignored local evidence: `.pytest_cache/checkpoint6g2/initial.json`, `final.json`,
`before/` preservation snapshots, `coverage-final.log`, `coverage-final-report.log`,
`coverage.json`, `coverage-arcs.json`, `.coverage`, `diff-coverage.json`, `measure.py`,
`report_coverage.py`, `alert.ps1` and the initial development logs. Task-added
whitespace checks pass; pre-existing owner whitespace is preserved.

**SOURCE IMPLEMENTATION / OFFLINE VALIDATION ONLY. LIVE BREVO DELIVERY: NOT
PERFORMED. MIGRATION APPLIED: NO. PUBLIC SENDING/PRODUCTION READINESS: NOT CLAIMED.**


## Checkpoint 6G-2A: durable confirmation outbox source (2026-10-15)

Owner authorization covers bounded OAF Website source, additive migration source,
contract updates and focused offline validation. This entry supersedes the 6G-2
confirmation-outbox implementation deferral for this scope. Existing historical
entries and their evidence remain intact. Source/offline work does not authorize
migration execution, operational credential/database access, live email, running
application changes, public activation, deployment or Git staging/commit/push.

### Atomic reservation and protected recovery

`NotificationDeliveryStore.request_confirmation` keeps its existing internal
sensitive token-or-None return for compatibility, but that return is no longer the
durable handoff. The existing transaction/advisory lock commits the verification
HMAC, original issue time, fixed 24-hour expiry, global/mailbox budget changes and
one pending `notification_confirmation_intents` row together. A failed insertion,
including a random-context uniqueness collision, rolls the entire reservation
back. No send precedes commitment. Lost reservation-commit acknowledgement leaves
the same recoverable committed intent if the transaction actually committed;
callers do not repeat a provider operation based on a missing response.

Each intent has an independent `secrets.token_hex(32)` random 256-bit context.
The recovered 64-character bearer is HMAC-SHA256 with the existing injected
persistent protected key over these exact ASCII bytes:

```
oaf-notification-confirmation-recovery-v1:<environment>:<subscription>:<intent>
```

The environment is the explicitly matched runtime environment; subscription is
the original 64-character consent-lifecycle receipt digest; intent is the random
64-character version context. Fixed-width components and delimiters make the
binding unambiguous. The existing separate
`oaf-notification-confirmation-v1:` HMAC still protects the verification lookup.
Persist only the context, lifecycle reference and that irreversible lookup digest,
never the recovered bearer, raw claim, email copy, provider key or message body.
An intent context alone is not a confirmation credential. Distinct recovery,
lookup, confirmation-claim, release-claim, mailbox, budget, recognition and
unsubscribe domains prevent cross-purpose capabilities.

The existing persistent random key requirement (at least 32 bytes) applies across
all workers/restarts. No new key store, startup secret, credential reuse, encryption
scheme or runtime key lookup is introduced. Missing/invalid keys fail construction
before persistence. A key/environment recovery mismatch against the immutable
intent digest returns sanitized unavailable through the dispatcher and preserves
the pending intent for correction; it is not misclassified as a superseded link.
Key rotation/provisioning remains a separately reviewed policy/operational action.
Legacy digest-only verification rows receive no fabricated intent or bearer:
there is no way to recover their original tokens. A deliberate fresh request may
replace them under the unchanged quotas; old original tokens otherwise retain
only their existing expiry/revocation semantics.

### Intent, claim, retry and lifecycle contract

`ConfirmationOutboxStore` and `ConfirmationDispatcher` are internal, unregistered
seams. No route, scheduler, running worker, public fragment consumer, administrator
Send action or automatic application-startup work is added. The public signup and
unsubscribe behavior, origin/CSRF safeguards, Contact integration and existing
shared services remain unchanged. Existing public responses still do not claim
that a confirmation email was sent.

Processing selects at most 20 due intent references in stable context order and
recovers at most 20 expired claims per invocation. Each candidate must separately
win a durable claim under the existing transaction-scoped advisory lock and the
subscriber row lock. Claims use a fresh random bearer, persisted only through the
separate `confirmation-claim` HMAC domain, a five-minute lease and a new attempt
number. Context and attempt identities are immutable. Concurrent workers and
resends cannot authorize repeated submissions of the same attempt.

Eligibility requires the authoritative original lifecycle to exist, remain active,
be unverified and unsuppressed, and have the same current verification digest.
The database clock must be within the original issue/expiry interval. Recovery
must reproduce the immutable intent digest with the protected key. A superseded,
verified, expired, withdrawn or suppressed intent cannot dispatch. Resend revokes
the previous verification digest and cancels earlier pending/failed/claimed
intents atomically; completed attempts remain unchanged and a cancelled live claim
receives its terminal ineligible audit. In-flight submitting/uncertain/accepted
history is retained. Resubscription never revives an earlier lifecycle.

Preparation and its final eligibility check occur inside the one-use claimed ->
submitting transaction. The fixed verification template is rendered before that
commit; only its successful acknowledgement returns the authoritative subscriber
email and transient message to the adapter. No caller supplies a recipient. A
preparation failure records `not_submitted`, finishes the attempt and follows the
bounded safe backoff. Withdrawal/resend/suppression that linearizes before this
committed boundary prevents dispatch; a provider operation already authorized or
in flight cannot be recalled by a later lifecycle change. This preserves the
existing 6G-1 dispatch boundary rather than claiming impossible recall semantics.

| Interruption or evidence | Deterministic durable handling |
| --- | --- |
| Failure before reservation commit | No new verification, intent or quota mutation commits. |
| Restart after reservation commit | Recover the same bearer from protected key, lifecycle and persisted context. |
| Crash after claim, before submitting commit | On five-minute lease expiry, `claim_expired` and bounded safe backoff. |
| Failed template preparation | Audited `not_submitted`; no provider operation, bounded safe retry. |
| Failed/unacknowledged submitting commit | No provider call; an actually committed submitting state becomes uncertain on lease expiry. |
| Confirmed provider rejection | Terminal `rejected`; no automatic retry or mailbox suppression for sender/configuration rejection. |
| Conclusive non-submission or structured 429 rejection | Retry after 60 then 300 seconds; at most three total attempts with fresh eligibility checks. |
| Possible acceptance, timeout, ambiguous response or injected adapter exception | `submission_unknown` / `uncertain`; never automatically retry that intent. |
| Crash or failed outcome persistence after possible POST | Preserve submitting claim/history; expired submitting becomes uncertain without another POST. |
| Pending/retry work expires, is revoked, verified, withdrawn or suppressed | Terminal ineligible/suppressed before any dispatch. |
| Provider acceptance | Accepted request only; `verified_at` remains unchanged and no mailbox-delivery claim is made. |

Safe retries reuse the same token and original expiry; they neither reserve a new
verification version nor bypass any budget or attempt limit. Ordinary deliberate
resends remain separate quota-limited reservations of a new version, never resets
of an uncertain or terminal attempt. The existing 60-second mailbox cooldown,
five requests per mailbox/day across lifecycles and 1,000 global requests/day are
unchanged. A resend cannot promote earlier withdrawal or superseded consent.

The existing Brevo adapter supplies the fixed From name `Ovis Alms Foundation`,
From `communications@updates.ovisalmsfoundation.org` and Reply-To
`contact@ovisalmsfoundation.org`. Messages use the configured secure notification
page and reserved `#confirm-email=` fragment. No active public consumer is claimed;
its future implementation must clear fragments and POST under existing controls.
The adapter's exact-target protected credential convention and production gate
are unchanged; no real configuration loader or credential is used here.

Only fixed outcomes, bounded validated provider IDs and timestamps enter intent
and attempt history. A provider identifier containing the recovered bearer is
discarded while preserving the provider outcome. Raw provider responses, exception
text, email addresses, capabilities and keys never enter result diagnostics or
outbox audit fields. Batch results contain only status and processed count.
Processing/acceptance never verifies ownership: only the existing `confirm` method
can set the verification timestamp after its unchanged capability/lifecycle checks.

### Minimal additive persistence and execution boundary

Revision `0005_confirmation_outbox`, parent `0004_notification_delivery`, adds only
two schema-qualified tables. The 0004 release delivery ledger cannot represent a
confirmation without inventing a release-event FK; its verification row is a
mutable current-version pointer and cannot retain obsolete versions/attempts.
Consequently the narrow intent plus attempt tables are necessary here. All
0001--0004 revision files and the 0004 schema helper remain byte-for-byte intact.
No historical table is altered, backfilled, auto-verified or repurposed.

- `notification_confirmation_intents`: immutable PK random `intent`, original
  subscription FK, verification lookup `token_digest`, creation time; existing
  delivery status/claim/lease/retry/acceptance/outcome fields. Named context/digest,
  claim/status/retry/attempt/time checks; indexes for due retries, expired leases
  and subscription/version cancellation. There is no duplicated recipient list.
- `notification_confirmation_attempts`: PK `(intent, attempt)` and immediate
  intent FK; immutable attempt identity and claim time, submitting/finished times,
  allowlisted outcome and bounded provider correlation. Previous completed
  attempts survive resend, recovery and withdrawal.

Matching runtime roles receive SELECT/INSERT plus UPDATE only on explicit
state/audit columns. No UPDATE authority on context, lifecycle, lookup digest,
creation/claim time or attempt identity; no DELETE, blanket UPDATE, REFERENCES,
TRIGGER, nonowner type USAGE, schema CREATE or grant option is granted. Existing
catalog/ACL validation is reused with an explicit combined table/trigger inventory
at 0005; earlier exact-state inventories remain distinct. The manifest includes
exact revision, helper, object, privilege and dependency contracts and hashes.

Only exact `0004_notification_delivery -> 0005_confirmation_outbox` is a new upgrade;
a later exact 0005 no-op needs a distinct authorization. Earlier single-revision
transitions remain supported. No jump, downgrade, stamp, repair, fallback or
multi-revision migration is enabled. Manifest status remains
`pending_independent_review`; updated hashes confer integrity only, not approval.
Independent exact-artifact review, owner-issued single-use TESTING authorization,
successful matching-artifact TESTING evidence, then separate DEVELOPMENT
execution authorization remain required. No real operational approval is issued.

### Deterministic autonomy review

Source review PASS: reservation eligibility, random version creation, cryptographic
binding/recovery, atomic persistence, expiry/revocation, quotas/cooldown, candidate
selection, concurrent claims, preparation, bounded safe retry, uncertain holds,
crash recovery and audit/privacy decisions all use explicit backend rules. Ordinary
processing requires no AI, per-subscriber administrator judgment or second Send
action. Internal processing awaits a separately approved invocation/activation;
no unnecessary background infrastructure is introduced. Policy/key changes,
exceptional administrative corrections, independent artifact review and migration/
activation approvals remain human authority. Uncertainty is a deterministic hold;
future authenticated reconciliation must establish conclusive evidence before
any exceptional transition, and lack of evidence never permits another send.

### Focused offline evidence and next checkpoint

Final results, preservation inventory and exact scoped coverage are recorded in
`.pytest_cache/checkpoint6g2a/final.json`, `coverage-final.log`,
`coverage-final-report.log`, `coverage.json` and `diff-coverage.json`.
The website interpreter, `-B`, disabled plugin autoload, empty pytest plugin/options
settings, repository/tests PYTHONPATH and early `-p migration_offline` guards are
preserved. The bounded test selection adds the two outbox files to the directly
affected verification, delivery, adapter, integration and migration-contract tests.
No unrelated full suite or completed live certification campaign is repeated.
Coverage exports tracer arcs under the guards; a separate metadata-only report
process uses the existing coverage installation read-only. Visible PowerShell
progress/errors/results, simultaneous complete logs and the existing visual
success/failure alert function are preserved with a 6G-2A OFFLINE title.

Exact task file inventory (relative to the preserved initial working tree):

```
docs/WORKFLOW.md
docs/WEBSITE_PLAN.md
migrations/manifest.json
migrations/versions/0005_confirmation_outbox.py
oaf_website/confirmation_outbox.py
oaf_website/confirmation_outbox_schema.py
oaf_website/migration_authority.py
oaf_website/migration_validation.py
oaf_website/notification_delivery.py
oaf_website/notification_delivery_validation.py
oaf_website/notification_messages.py
tests/migration_offline.py
tests/test_confirmation_outbox.py
tests/test_confirmation_outbox_migration.py
tests/test_migration_artifacts.py
tests/test_migration_authorization.py
tests/test_notification_delivery.py
```

Exact next checkpoint: **6G-2A independent exact-artifact/prerequisite review** of
0005 and the changed manifest/helpers, preserving the separate review/execution
boundary for unexecuted 0004. Only after matching review and separate owner issuance
may TESTING validate exact 0004 -> 0005, starting at verified 0004; applying 0004
itself requires its own separately authorized predecessor transition. DEVELOPMENT
follows only matching successful TESTING evidence and its own authorization.
Public confirmation request/consume UI, approved processor invocation, authenticated
provider feedback/reconciliation and any live activation remain separate source/
operational checkpoints. No GraManna handoff, administrator announcement feature,
Cargo 29 work, deployment, staging, commit or push is part of 6G-2A.

**SOURCE IMPLEMENTATION / OFFLINE VALIDATION only. MIGRATION APPLIED / LIVE EMAIL
DELIVERY: not performed or authorized.**

6G-2A final gate: **1,022 passed in 64.81 seconds**, no skips/errors/xfails,
zero unexpected external-access attempts. New source: **206/206 statements
and 68/68 branches, 100%**. Including complete changed feature modules:
**577/577 statements and 216/216 branches, 100%**. The two existing
migration-policy modules have **45/45 changed executable lines covered**,
with no missing branches on changed decisions. Unrelated historical policy
logic is outside this focused coverage claim; no coverage exclusions or
weakened assertions are used. Synthetic transaction/catalog tests do not
certify real PostgreSQL locking, rendering, dependency or privilege semantics.


## R38: public notification email confirmation integration (2026-10-17)

**SOURCE IMPLEMENTED / OFFLINE VALIDATED. LIVE EMAIL DELIVERY / OPERATIONAL
ACTIVATION: OFF, not performed or authorized.** This entry supersedes earlier
public confirmation integration deferrals only for this source checkpoint.
The owner reports migrations 0001--0005 applied and verified in TESTING and
DEVELOPMENT; R38 does not reopen or revalidate those campaigns.

Repository: OAF Website, branch `main`; starting/final HEAD
`b2f0069be87741b21a054f9ced5411bdb90afd03`. The initial index and working tree
were clean. All work remains unstaged. No commit or push is performed. No
GraManna source is accessed or modified; only the already approved shared
Playwright interpreter/installation is executed, from the OAF Website directory.

### Implemented public contract and activation control

- `create_app(..., confirmation_enabled=False)` is the server activation seam.
  Only an explicit Boolean `True` injects `NotificationDeliveryStore` using the
  existing verified engine, matching environment and persistent protected key.
  Invalid flag types fail before configuration/credential access. No environment
  default, local launcher, protected configuration or deployment setting changes.
  This flag enables persistence/public confirmation only; it never constructs a
  provider adapter, reads a Brevo key or invokes a dispatcher.
- `/api/notifications/session` retains the browser cookie and CSRF contract and
  adds the nonprivate `confirmation_enabled` Boolean. Other session responses
  retain their prior shape. The browser hides request/resend controls while off.
  Both new POST routes return sanitized 503 unavailability while off, including
  for previously valid tokens, without touching verification, quotas or intents.
  Existing subscription/unsubscribe behavior and truthful no-email-sent copy
  remain intact.
- `POST /api/notifications/confirmation` accepts exactly `{"email":"..."}`.
  It reuses same-origin/fetch-metadata enforcement, browser-bound CSRF, the 1 KiB
  body bound, strict UTF-8 JSON parsing and existing email normalization. Reused
  strict JSON hooks reject duplicate keys and nonstandard constants; the shared
  notification parser also hardens signup/unsubscribe consistently. Valid known,
  unknown, verified, withdrawn, suppressed and quota-limited addresses receive
  identical HTTP 200/status/message: "If confirmation is needed and permitted,
  we'll email a link." The sensitive internal token return is discarded. There
  is no existence, eligibility, quota or email lookup response.
- `POST /api/notifications/confirm` accepts exactly `{"token":"..."}` and
  delegates to the unchanged lifecycle-bound `confirm` operation. Successful
  ownership confirmation returns "Your email is confirmed." Malformed,
  unknown, expired, future-issued, superseded, withdrawn or suppressed links
  receive a sanitized unavailable response: "This link is unavailable. Request
  a new confirmation link." Persistence/commit uncertainty returns sanitized
  503 and permits a deliberate safe repeat. No provider result sets verification.
- The existing notification card provides a separately labeled request/resend
  form and an explicit Confirm email button. `#confirm-email=` and preserved
  `#unsubscribe=` capabilities are removed at notification-script entry before
  DOM work or application requests; the notification script precedes the State
  Request script. Opening a link performs no mutation. Capabilities remain in
  memory and POST bodies, never query/path/local storage. Keyboard focus, live
  status/alert messages, shared busy controls, CSRF refresh and session/network/
  invalid-JSON errors are handled. Existing CSS and public file inventory stay
  unchanged. A failed initial session can be deliberately retried from the link.

### Atomic signup and existing persistence

With confirmation enabled, `SubscriptionStore` uses the existing delivery
transaction/advisory lock, the same engine/connection and `INSERT ... ON CONFLICT
DO NOTHING RETURNING` to recognize a genuinely new consent lifecycle. Only that
new row enters the existing reservation rules within the same transaction.
Subscription creation, applicable global/mailbox quota updates, verification
version and protected recoverable intent commit together. A failure in either
reservation insert rolls back the subscription and quotas as well. A second
engine is rejected at construction.

Quota exhaustion, cooldown or suppression still prevents reservation; it does
not reject otherwise valid subscription consent. Such a saved subscription
remains unverified and can later request confirmation under the same public
rules. No deferred parallel queue or quota bypass is created. The existing
60-second/five-per-mailbox/day and 1,000-global/day policy is unchanged, including
unknown-address budget use and cross-lifecycle limits.

Repeated active-email signup or receipt reuse never changes preferences, consent,
verification, quota counters or pending intent. A repeat after an actually
committed but unacknowledged signup converges on the same lifecycle/intent, even
after cooldown. The public response remains generic and its private unsubscribe
capability still derives only from the submitted receipt. Existing shared-service
subscription callers reuse this same store and retain their response contract.
The existing outbox, token recovery, dispatcher, Brevo templates and suppression
systems are reused; no schema, migration, second recipient list or queue is added.

### Focused validation evidence

The six-file backend run passed **656 tests in 10.50 seconds**. After adding four
final lifecycle/OFF assertions, the complete public integration file passed
**80 tests in 1.83 seconds**. There are **660 distinct passing tests** across this
selection; overlapping reruns are not additive. Both runs report zero unexpected
external-access attempts. Selected files: `test_public_confirmation.py`,
`test_notifications.py`, `test_notification_delivery.py`,
`test_confirmation_outbox.py`, `test_integrations.py`, `test_state_requests.py`.
No migration campaign, provider call or unrelated broad suite is run.

Coverage includes strict shape/JSON/media/body checks, origin/CSRF, generic
response equivalence, atomic new signup, concurrent/duplicate/receipt recognition,
rollback, lost commit acknowledgement, quota/suppression-denied reservations,
resend supersession, original expiry, stable verification timestamps, safe repeats,
withdrawal/resubscription, default-off and factory activation without processing.
Existing outbox tests retain fake-provider acceptance-without-verification and
bounded claim/restart/uncertainty behavior.

`tests/confirmation_browser_check.py` and the preserved
`tests/notification_browser_check.py` both PASS at **1280px and 390px**, with zero
page errors or external requests. They cover fragment removal before the first
application fetch, no automatic confirmation, explicit keyboard action, accessible
messages, busy controls, session/CSRF/network/HTML-response errors and retries,
invalid/expired links, OFF behavior, signup and unsubscribe. Intercepted Chromium
and serialized transaction models do not certify live PostgreSQL concurrency or
deployed provider/browser behavior.

The dedicated website interpreter, `-B`, disabled pytest autoload, empty plugin/
options settings, explicit file selection and early `-p migration_offline` guards
remain unchanged. Only the new public test file is added to the existing guard
allowlist. Browser checks use the established shared interpreter without installs.
PowerShell startup/progress/errors/results are simultaneously transcribed under
ignored `.pytest_cache/r38/`, with the existing OAF completion/failure alert helper.
`Invoke-OAFCodex` and its automatic final-report clipboard behavior are unchanged.
Initial failed harness runs and logs are retained: four synthetic signing-key
fixture failures, one browser fresh-document navigation issue, and one rejected
single-file PowerShell argument expansion. Their corrections did not weaken the
isolation guards or application assertions. Final checks pass.

### Deterministic autonomy and preservation review

Source/offline review PASS: eligibility/normalization and consent remain fixed
server rules; uniqueness and locked transactions govern new-versus-repeat signup;
durable budgets govern requests; existing lifecycle/digest binding governs expiry,
supersession, withdrawal and suppression; only valid explicit confirmation creates
the original stable verification timestamp. Atomic persistence, protected token
recovery, durable attempt history and sanitized failures preserve deterministic
rollback/restart handling. Ordinary operations require no AI or per-subscriber
administrator decision. Official release approvals, policy/key changes and
exceptional corrections remain existing human governance boundaries.

All earlier migration/revision/schema/catalog/manifest artifacts, deployment and
launcher configuration, shared CSS, State Request JavaScript, Contact source,
owner-authored historical documentation and the Git index are preserved. The
original governing-document bytes remain prefixes of these appended versions.
No operational credentials, live PostgreSQL, live Brevo, actual email, recurring
processor or production activation is accessed or performed. `git diff --check`
passes. Scope/hashes and final inventory are retained in `.pytest_cache/r38/`.

### Remaining operational dependencies and next smallest checkpoint

Recommend **R39: bounded dispatcher invocation and restart recovery integration,
source/offline only**, reusing `ConfirmationDispatcher` and its existing bounded
batches. Define the recurring invocation owner/host/cadence, consistent activation
configuration across workers, protected persistent key/environment and existing
Brevo configuration injection, shutdown/restart handling, and sanitized health/
backlog/expired-claim/uncertain-outcome monitoring. Prove pending-intent recovery,
expired claimed-work backoff and submitting-to-uncertain recovery with fake
dependencies. Never retry uncertain submissions on restart; no second Send action
or new worker framework is required by this recommendation.

Any actual processor invocation, provider credential access, delivery validation
or public activation requires a separate explicit operational authorization.
Provider link rewriting/tracking confidentiality and sender configuration still
need approved live validation. Authenticated feedback/correlation/reconciliation
for uncertain provider outcomes remains a separate implementation dependency;
lack of evidence never permits another send. New API/signup transaction behavior
still needs later bounded authorized live validation without reopening migrations.
Production deployment/activation remains separately gated. R38 establishes no
live email delivery or production readiness.

Exact changed files: `assets/notifications.js`, `gramanna.html`,
`oaf_website/notification_delivery.py`, `oaf_website/notifications.py`,
`oaf_website/state_requests.py`, `tests/migration_offline.py`,
`tests/test_notification_delivery.py`, `docs/WORKFLOW.md`, `docs/WEBSITE_PLAN.md`.
Added: `tests/test_public_confirmation.py`, `tests/confirmation_browser_check.py`.
Ignored local evidence/helpers/logs/screenshots are confined to `.pytest_cache/r38/`.


## R39: bounded confirmation processor invocation (2026-10-17)

**SOURCE/OFFLINE VALIDATED. LIVE PROVIDER DELIVERY / OPERATIONAL ACTIVATION:
OFF, not performed or authorized.** This source entry connects the existing R38
public reservations to an independently invokable, default-off processor. The
owner reports migrations 0001--0005 applied and verified in TESTING and DEVELOPMENT;
no migration, schema or completed migration validation is repeated. Historical
contracts and owner notes above remain intact.

### Invocation and configuration contract

`python -u -B -m oaf_website.confirmation_processor --environment <profile>`
is the one-shot entry point. `process_confirmations(...)` is its explicit callable
seam. Importing either module, creating a Flask application, and handling a public
HTTP request never start processing. The module creates no application or server.
Without the exact `--enable-processing` switch (or callable `enabled=True`), the
result is disabled and no local configuration, protected key, credential, engine,
outbox query or provider is accessed. Non-Boolean callable activation is rejected.
The independent R38 `confirmation_enabled` factory flag still defaults off and
only controls public persistence/confirmation; it does not activate this processor.

Every invocation requires explicit `--environment` and matching `OAF_ENV` under
the existing `_validate_environment` rules. Conflicting database settings are
rejected. No new environment-variable authority or local settings file is added.
Enabled operation also requires `--brevo-account` with the existing credential's
approved nonsecret account metadata, and `--confirmation-page` with the approved
HTTPS `/gramanna.html` page. Invalid environment, production or page is rejected
before any secret loader. No account or origin is discovered or guessed.

Enabled runtime construction reuses `load_testing_database_config` for TESTING,
the existing runtime loader for DEVELOPMENT, and `load_brevo_config` with its
pinned exact-target Windows credential convention. Production is rejected before
local configuration/credentials, even with the enable switch. The engine uses
the established SCRAM requirement, 5-second connect timeout, 10-second statement
timeout, 5-second lock timeout, hidden SQL parameters and verification on every
checkout of database, effective/authenticated user, host, port and PostgreSQL 17.
It imports the existing `_verify_checkout` authority rather than replacing it.

`recognition_secret(require_existing=True)` reuses the existing current-user
DPAPI key without creating a missing/replacement file. Missing, invalid or
redirected key locations fail closed. Other existing hosts retain their original
default create-once behavior. Every public worker and scheduled invocation must
use the same protected key, consent database and environment; wrong-key recovery
preserves the pending intent as unavailable. Changing key policy is an exceptional
administrative action. No real local configuration, protected key or credential
was read during R39; enabled tests inject synthetic loaders and transports only.

The processor constructs the existing `ConfirmationOutboxStore` and
`ConfirmationDispatcher`, calls `process(limit=20)` exactly once, and disposes its
engine. There is no loop, daemon, new queue, subscriber authority, schema,
framework, credential provider or dependency. A later scheduler repeats this same
invocation without changing the processing algorithm.

### Bounds, restart semantics and reporting

Each invocation selects at most **20 due intents** in the existing stable order
and recovers at most **20 expired claims**, independently. The existing database
transaction-scoped advisory lock and lifecycle row locks govern ownership across
processes. Candidate selection is not submission permission: every candidate must
win a fresh durable claim and pass the committed final preparation boundary.
Five-minute leases, three total attempts, 60/300-second safe retry delays and the
original 24-hour token expiry remain unchanged. There is no attempt reset,
automatic replacement token, quota bypass or in-memory ownership authority.

| Persisted condition / failure | Next invocation behavior |
| --- | --- |
| Pending intent after restart | Recover the same protected bearer and process when eligible. |
| Live claimed/submitting lease | Leave ownership intact until expiry; no competing submission. |
| Expired claim before submission | Finish `claim_expired`; safe retry after the existing delay if attempts remain. |
| Conclusive non-submission or structured retryable rejection | Honor persisted due time; recheck eligibility; exhaust after attempt three. |
| Failed submitting commit | No provider call; rolled-back claim can recover safely after lease expiry. |
| Unacknowledged submitting commit that actually committed | No provider call from the failed invocation; expiry conservatively holds it uncertain. |
| Crash during submission or failed outcome persistence | Expired submitting becomes `submission_unknown` / uncertain; never blindly resend. |
| Acknowledged or unacknowledged committed acceptance outcome | Existing accepted history prevents another submission. |
| Expired, superseded, withdrawn, suppressed or verified lifecycle | Existing claim/final preparation checks prevent dispatch; retain audit history. |
| Uncertain submission | Preserve the hold; ordinary invocations never retry or ask an administrator to resend. |

Provider acceptance is acceptance of a submission, not mailbox delivery or
verification. Only the public capability consumption contract verifies ownership.
No authenticated provider feedback/reconciliation transport is implemented here.
Conclusive evidence and a separately approved transition remain prerequisites for
exceptional uncertainty reconciliation; absence of evidence never permits resend.
Withdrawal/resend/suppression before the committed preparation boundary prevents
dispatch; a later lifecycle change cannot recall an already authorized operation.

The CLI flushes one JSON result containing only existing `BatchResult` fields:
`status` and `processed`. Exit **0** is `processed` (invocation completed), **2**
is `disabled` or sanitized argument rejection, **1** is `unavailable` (including
configuration, persistence or cleanup failure), and **130** is interruption.
Argument errors never echo supplied values. `processed` counts submissions whose
outcome persistence was acknowledged, across all provider outcome classes; it is
not an accepted/delivered/verified count. Zero is a successful no-dispatch result,
which may include recovery, ineligibility or competing claims; it does not prove
an empty outbox. An unavailable result can retain prior acknowledged progress.
Interruption reports zero acknowledged results returned to the invocation, not
proof that no side effect occurred; the durable ledger remains authoritative.

Only these fixed fields reach invocation output. Email addresses, confirmation
bearers, claim secrets, API keys, message bodies, database credentials, provider
responses and raw exceptions are excluded. Detailed state/outcome/attempt evidence
remains in the existing intent/attempt ledger. Completion alone does not imply
absence of uncertain/rejected work. Future approved operational observation may
use sanitized aggregates of that ledger; no dashboard/platform or live query is
added or run in this checkpoint.

### Future recurring scheduling boundary — documentation only

Use the approved host's existing operating-system/deployment scheduler. For the
current local Windows runtime, Task Scheduler can invoke the website's absolute
`.venv\Scripts\python.exe` from the OAF Website working directory under the same
approved Windows account that can decrypt the existing DPAPI key and read the
selected runtime/Brevo credentials. Configure the explicit matching `OAF_ENV` in
the task's PowerShell invocation; inherit no alternate database settings. Proposed
cadence: once per minute, one batch per invocation, with overlapping starts
disabled in scheduler policy. Correctness still relies on database claims when
invocations overlap. The host, account, cadence, task limits, output destination
and failure notification require separate operational authorization.

This is an invocation specification for later approval, **not a command to run
during source validation**. Nonsecret placeholders require approved actual values:

```powershell
# FUTURE AUTHORIZED OPERATION ONLY; start in the OAF Website repository.
$env:OAF_ENV = 'testing'
& '.venv\Scripts\python.exe' -u -B -m oaf_website.confirmation_processor `
    --environment testing --enable-processing `
    --brevo-account '<approved-existing-account>' `
    --confirmation-page 'https://<approved-origin>/gramanna.html'
exit $LASTEXITCODE
```

No administrator should manually process ordinary messages. Each scheduled start
discovers durable pending/retry work; delayed retries become selectable only at
their stored database due time. Recovery is bounded and resumes automatically on
later starts, including remaining expired claims beyond the first 20. Disabled or
unavailable operation exits nonzero without fallback, automatic activation or a
second Send action. Stop scheduling by removing the enable switch/approved task
activation; live leases and durable history remain for safe restart. Do not reset
claims/attempts or issue replacement tokens as a shutdown procedure.

Capture stdout/stderr and process exit status using existing scheduler/host logs;
observe missed starts and nonzero exits with the host's normal alert facilities.
Retain privacy-safe ledger aggregates for uncertain outcomes and backlog as a
future authorized observation task. This checkpoint adds no automatic monitor.
Work is finite in count; the existing provider's socket inactivity timeouts are
not a guaranteed total DNS/HTTP wall-clock deadline. An approved scheduler time
limit or forced termination must retain the same conservative lease/uncertainty
recovery; termination never grants a resend. No task is registered and no worker,
startup launcher, production setting or background service is activated here.

### Focused validation and deterministic autonomy

**621 passed in 15.62 seconds**, zero unexpected external-access attempts, with
no skips/errors/xfails. This includes **95 new processor cases**; their initial
standalone run also passed (6.59 seconds), and overlapping reruns are not additive.
Explicit files: `test_confirmation_processor.py`, `test_confirmation_outbox.py`,
`test_public_confirmation.py`, `test_notification_delivery.py`,
`test_notifications.py`, `test_brevo.py`. The website interpreter, `-B`, disabled
pytest autoload, empty plugin/options settings, explicit file selection and early
`-p migration_offline` guards remain intact. Only the new test file is added to
the existing allowlist; no guard is relaxed. No packages or shared GraManna
interpreter/files are accessed. Browser behavior is unchanged; no Playwright run
or repeated migration certification is needed.

Behavioral coverage includes default OFF, synthetic enablement, environment/
production/metadata rejection, empty processing, exact identity verification,
separate candidate/recovery bounds, fake acceptance without verification, retry
timing/exhaustion/original expiry, pending/claimed/submitting restart recovery,
failed and unacknowledged commits at each transition, outcome persistence failure,
eight competing fresh invocations, withdrawal/suppression/expiry/supersession/
verification checks, no repeat after uncertainty, sanitized CLI failures and
interrupts, cleanup failure with acknowledged progress, existing-key-only DPAPI
loading with fake native functions, and R38 signup -> dispatch -> explicit confirm.
These are behavioral coverage findings, not a whole-repository coverage percentage
or certification of real PostgreSQL/process/provider behavior.

| Operational decision | Deterministic authority / finding |
| --- | --- |
| Candidates and claim acquisition | Existing ordered, bounded SQL and transaction/row locks; concurrent losers skip. |
| Lease expiry and restart | Database timestamps and durable five-minute claims; fixed recovery classification. |
| Submission authorization | One-use claimed -> submitting commit plus final original-lifecycle eligibility. |
| Retry eligibility, timing and exhaustion | Conclusive non-submission/retryable rejection only; persisted 60/300-second due times; maximum three attempts. |
| Token expiry and version | Same original 24-hour verification reservation and current digest; no automatic renewal. |
| Verification, withdrawal, suppression | Existing authoritative records checked at claim/preparation; acceptance never verifies. |
| Provider classification and uncertainty | Existing conservative adapter mapping; uncertain is a permanent automatic resend hold. |
| Recovery and failure reporting | Fresh invocation over durable state; sanitized result/exit code; failed commits never authorize POST. |

**Deterministic autonomy source/offline review PASS.** Ordinary selection,
claims, eligibility, retries, recovery and reporting require no AI, per-subscriber
administrator decision or repeated Send approval. Host/configuration activation,
key/policy changes, official release governance and exceptional conclusive-evidence
corrections remain authorized administrative controls. The missing feedback
transport is a deferred capability, not permission to weaken uncertainty holds.

### Preservation, evidence and remaining gates

Repository `oaf-website`, branch `main`, starting/final HEAD
`b2f0069be87741b21a054f9ced5411bdb90afd03`; the index stays empty and unchanged.
The eleven initial R38 changed/added files are inventoried and snapshotted under
ignored `.pytest_cache/r39/before/` with initial hashes. All R38 source/browser
files remain byte-for-byte unchanged except the explicitly additive test allowlist
entry; the initial governing-document bytes remain exact prefixes. No R38 or
owner change is removed. Unrelated tracked/untracked initial files, all migration/
schema/manifest artifacts and startup/deployment configuration retain their hashes.
`git diff --check` passes. No staging, commit, push, PostgreSQL connection/write,
operational credential access, real provider call, email, scheduler activation,
GraManna access or production configuration change occurs.

Exact R39 file inventory: added `oaf_website/confirmation_processor.py` and
`tests/test_confirmation_processor.py`; modified `oaf_website/local_testing.py`,
`tests/migration_offline.py`, `docs/WORKFLOW.md`, `docs/WEBSITE_PLAN.md`.
Complete visible PowerShell test transcripts, run helper, preservation snapshots,
initial/final inventory and final report remain ignored under `.pytest_cache/r39/`.
The existing OAF visual completion/failure alert helper is reused. `Invoke-OAFCodex`
and automatic clipboard reporting remain unchanged; no execution-workflow setting
is altered.

Remaining activation prerequisites: separate explicit owner approval for the
selected environment/host/account and live processor operation; approved actual
secure page/origin and compatible public confirmation activation; existing stable
protected key and matched runtime identities; approved protected Brevo account/
sender configuration and live link tracking/confidentiality validation; bounded
authorized live API/transaction/claim/restart validation; approved scheduling and
log/alert settings. Production secret/deployment design remains separately gated.
No migration work is reopened. Authenticated provider feedback/correlation and
uncertainty reconciliation remain a separate source/operational contract.

Smallest next checkpoint: **R40: separately owner-authorized, bounded TESTING
end-to-end invocation and restart validation**, with an approved controlled
mailbox, actual host/account/origin and protected configuration, after verifying
the prerequisites above. Keep recurring scheduling and production inactive.
R39 itself establishes neither live provider delivery nor operational
activation/readiness; no additional independent source review loop is required.


## R40-B: controlled recipient enforcement and TESTING HTTPS preparation (2026-10-17)

**SOURCE / OFFLINE VALIDATED. LIVE TESTING HTTPS, PUBLIC CONFIRMATION AND
PROVIDER PROCESSING ACTIVATION: OFF.** Owner authorization covers bounded source,
necessary documentation and focused synthetic validation only. R36 HEAD remains
`b2f0069be87741b21a054f9ced5411bdb90afd03` on `main`. R38/R39 and owner changes
are preserved. The owner reports 0001--0005 applied/verified in both databases;
this checkpoint does not reopen migrations or inspect their live state.

### Recipient-enforcement contract

- Every enabled TESTING processor invocation now requires exactly one deliberate
  `--testing-recipient` (callable `testing_recipient`). This supplements the R39
  invocation contract and supersedes its unscoped TESTING command example.
  Existing normalization trims ordinary outer spaces and lowercases the complete
  ASCII mailbox, without DNS requests or provider-specific address rewriting.
  Missing/malformed scope fails before protected loaders, engine construction or
  processing. Repeated CLI scope options are rejected, even if identical. Scope
  on an enabled non-TESTING invocation is rejected before runtime access.
- Immutable `TestingRecipientScope` carries the normalized mailbox with its value
  excluded from diagnostic representation. A supplied scope must be that exact
  validated type and match TESTING at both store and adapter construction. The
  owner supplies the actually approved mailbox at a later operational checkpoint;
  no real recipient or configuration is created here. Configuration is supplied
  through existing explicit invocation arguments, not another settings authority.
- The existing intent queries filter subscription references through the existing
  authoritative `notifications.email` before stable ordering and SQL LIMIT. Both
  due selection and expired-claim recovery use the exact same mailbox predicate.
  There is no redirected recipient, duplicate email list, queue, schema, database,
  delivery ledger or worker framework. A batch bound or an empty queue is never
  used as recipient authorization.
- Recovery rechecks the authoritative subscriber before mutating intent/attempt
  history. Claim, preparation and outcome persistence also enforce the scope.
  Preparation repeats the locked authoritative mailbox check immediately before
  the committed claimed-to-submitting authorization boundary. A mismatch raises
  a fixed safe error, rolls back that transaction and prevents submission.
  The dispatcher checks the prepared recipient; the Brevo adapter independently
  checks it before payload construction/transport. It never replaces an address
  with the approved mailbox. A failed earlier selection/preparation check therefore
  cannot cause another subscriber's message to be sent to the test recipient.
- Unrelated subscribers, verification, quotas, intents, claims and attempts remain
  untouched by controlled processing, including unrelated expired claims. Existing
  consent, current verification/version, suppression, withdrawal and expiry checks
  remain mandatory. Withdrawal/verification that linearizes before authorization
  prevents sending; already authorized/in-flight submissions cannot be recalled.
- Internal ordinary store/adapter contracts remain usable without a scope for
  existing separately authorized non-test processing. Enabled TESTING through the
  operational processor has no unscoped path. DEVELOPMENT gets no TESTING scope or
  fallback, and production stays blocked before protected access. Default OFF
  remains inert: no configuration/key/database/provider loading or processing.

### Bounds, uncertainty and deterministic autonomy

The unchanged limits remain 20 due intents and 20 expired-claim recoveries per
invocation, five-minute claim/submission leases, three attempts, 60/300-second
conclusive-safe retry delays, the original 24-hour verification expiry, and durable
claim/attempt history. Database advisory/subscriber locks and one-use claims govern
concurrency. Safe retries recover the same token and original state; no reset,
renewal, replacement-token workaround or fabricated delivery evidence is added.

Possible provider submission, unacknowledged submitting commits and interrupted
outcome persistence retain conservative uncertainty with no automatic resend.
A prepared-recipient mismatch returns unavailable without transport; if submitting
was already committed, its eventual recovery conservatively holds it uncertain.
Provider acceptance still establishes neither delivery nor verification.
The processor exposes only fixed `status`/`processed` JSON and existing exit codes;
no mailbox, capability, credential, TLS key path, raw exception or provider body
is emitted. Processed counts are acknowledged outcome persistence, not deliveries.

**Deterministic autonomy source/offline review PASS:** exact SQL predicate/order,
claims, final lifecycle/scope authorization, retry timing/limits, restart recovery,
uncertainty holds and sanitized outcomes are fixed server rules. Ordinary approved
processing requires no AI, per-message administrator action or second Send action.
Host/account/mailbox activation approval, policy/key changes, official governance
and exceptional evidence-backed corrections retain authorized human control.
Authenticated provider feedback/correlation/reconciliation remains separately
contracted; absent evidence never authorizes another send.

### Minimal HTTPS TESTING startup and operational prerequisites

The existing HTTP `testing_app(port)` remains compatible. The added
`testing_https_app(public_origin=..., confirmation_page=...,
confirmation_enabled=False)` reuses the same Flask factory and exact public-file
allowlist. The host entry point is `oaf_website.local_testing_https`, following the
existing foreground Werkzeug/quiet-handler convention. It has no reload, scheduler,
processor startup or automatic activation. DEVELOPMENT/F2 and PowerShell helpers
are unchanged.

- Explicit `--environment testing` and matching `OAF_ENV=testing` are required.
  Existing TESTING-only database loading and SCRAM/exact identity checks are reused;
  startup performs a verified connection checkout before binding. There are no
  migrations, schema setup, DEVELOPMENT fallback or Brevo credential reads.
- Require the existing persistent current-user DPAPI key through
  `recognition_secret(require_existing=True)`; never create a replacement.
  Public confirmation defaults OFF. Only `--enable-confirmation` explicitly enables
  the existing public persistence/consume flow, and never starts processing.
- The owner selects the HTTPS origin without a trailing slash; its exact matching
  page is that origin plus `/gramanna.html`. Both must satisfy the existing strict
  template contract: HTTPS, no userinfo/query/fragment and only port 443 (implicit
  or explicit). Host labels are validated. HTTP and a nonstandard local HTTPS port
  such as 5443 are rejected. Processor and browser must use this same chosen page.
- Bind only `127.0.0.1:443`. The chosen hostname must resolve to that loopback
  listener on the owner browser's machine. The owner must supply an already
  trusted, currently valid certificate with a matching hostname/IP SAN and its
  matching existing PEM private key, using absolute, distinct existing paths.
  Certificate chain loading must succeed. Browser trust/validity/hostname matching
  is an operational prerequisite, not certified by mocked tests. Store private
  material outside Git with appropriate owner-controlled file access.
- TLS uses an explicit server context, minimum TLS 1.2, with no adhoc certificate,
  CA creation, trust-store change or ambient TLS key logging. Encrypted PEM keys
  requiring an interactive password are rejected without prompting; an approved
  noninteractive usable key arrangement is required. The owner must establish
  availability and any required privilege for port 443. Startup never chooses a
  different port or kills another listener. No public hostname is selected here.
- HTTPS uses the existing `__Host-` Secure, HttpOnly, SameSite=Lax browser cookie,
  same-origin/fetch-metadata checks, browser-bound CSRF, bounded strict JSON and
  privacy response headers. Existing link generation remains HTTPS-only. Private
  configuration/source/audit paths are absent from the public-file allowlist.
  Startup/configuration/cleanup failures emit only fixed sanitized messages.

Future procedure, **only after separate operational authorization**: verify the
approved browser hostname/loopback resolution, trusted certificate/key paths and
port-443 availability/privilege, actual TESTING runtime identity, persistent key,
and approved isolated Brevo account/sender/mailbox metadata. Populate the following
variables from owner-approved operational choices; these examples provide no
actual values and are not commands executed by R40-B:

```powershell
# FUTURE AUTHORIZED OPERATION ONLY, from the OAF Website repository.
$env:OAF_ENV = 'testing'
$taskConfirmationPage = $taskApprovedOrigin + '/gramanna.html'
& '.venv\Scripts\python.exe' -u -B -m oaf_website.local_testing_https `
    --environment testing --public-origin $taskApprovedOrigin `
    --confirmation-page $taskConfirmationPage `
    --tls-certificate $taskApprovedCertificatePath `
    --tls-private-key $taskApprovedPrivateKeyPath
# The command above leaves public confirmation OFF. Enabling it requires the
# separately approved --enable-confirmation switch; no processor starts with it.
```

After compatible public activation is separately authorized, the single bounded
processor command must use the same page and its own deliberate scope/enablement:

```powershell
# FUTURE SEPARATELY AUTHORIZED SINGLE BATCH ONLY. Never log supplied mailbox values.
& '.venv\Scripts\python.exe' -u -B -m oaf_website.confirmation_processor `
    --environment testing --enable-processing `
    --testing-recipient $taskApprovedMailbox --brevo-account $taskApprovedBrevoAccount `
    --confirmation-page $taskConfirmationPage
```

Keep the existing visible PowerShell/log/clipboard/alert workflow. No actual host,
certificate/private-key access, credentials, mailbox, provider request, email or
recurring task is activated by this source checkpoint. Sender configuration and
confirmation-link tracking/confidentiality need later bounded live validation.
Production remains separately gated.

### Focused offline evidence and preservation

Final focused gate: **737 passed in 20.67 seconds**, zero unexpected external-access
attempts, no failures/skips/xfails. This includes **72 new recipient/HTTPS cases**,
the existing 95 processor cases and directly relevant R38/R39/store/Brevo/release
regressions. The earlier narrow 164-case gate also passed; overlapping runs are
not additive. Behavioral coverage includes all 20 requested validation areas:
default OFF, missing/invalid/non-TESTING scope, exact selection, unrelated pending
and expired work, selection/preparation bypasses and independent adapter guard,
concurrent claims, withdrawal/verification/suppression/expiry, retries/attempt bounds,
interruption/uncertainty/no resend, sanitized results, strict matching HTTPS/TLS,
Secure cookie/origin/CSRF, and R38/R39 compatibility. No statement/branch percentage
is claimed. Serialized SQL models do not certify real PostgreSQL concurrency.

Explicit file selection: `test_controlled_confirmation.py`, `test_testing_https.py`,
`test_confirmation_processor.py`, `test_confirmation_outbox.py`,
`test_public_confirmation.py`, `test_notification_delivery.py`,
`test_notifications.py`, `test_brevo.py`, `test_notification_dispatch.py`.
The dedicated website interpreter, `-B`, disabled pytest plugin autoload, empty
pytest options/plugins, repository/tests PYTHONPATH and early `-p migration_offline`
guards remain intact. Only the two new test paths are added to the allowlist.
The existing transactional model gains generic SELECT-subquery evaluation; guards
are not weakened. No browser-facing HTML/JavaScript changes require Playwright.
No completed migration certification or unrelated broad test suite is repeated.

Exact R40-B modified inventory relative to its starting tree:
`oaf_website/brevo.py`, `oaf_website/confirmation_outbox.py`,
`oaf_website/confirmation_processor.py`, `oaf_website/local_testing.py`,
`tests/migration_offline.py`, `tests/test_notification_delivery.py`,
`tests/test_confirmation_processor.py`, `docs/WORKFLOW.md`, `docs/WEBSITE_PLAN.md`.
Added: `oaf_website/local_testing_https.py`, `tests/test_controlled_confirmation.py`,
`tests/test_testing_https.py`. All prior document bytes remain exact prefixes.
All initial paths are retained; unrelated initial hashes, migration/schema/manifest
artifacts, deployment/launcher configuration, HEAD and empty index are unchanged.
`git diff --check` passes. No staging, commit, push, GraManna access, operational
credential/database/provider access, TLS installation or live activation occurs.

Ignored snapshots, inventories, full visible PowerShell transcripts, run helper,
verification metadata and report are under `.pytest_cache/r40b/`. Existing visual
success/failure alerts and clipboard reporting are reused; `Invoke-OAFCodex` and
PowerShell execution settings are unchanged.

Smallest next checkpoint: **R40-C owner selection and prerequisite review for one
bounded TESTING end-to-end operation**, with actual mailbox/account/origin,
loopback hostname, certificate/key/port arrangements and separate explicit live
authorization. Keep recurring scheduling and production inactive. This result
establishes SOURCE / OFFLINE VALIDATED only, not live delivery or deployed readiness.


## R41: dedicated email confirmation experience (2026-10-17)

Owner authorization covers the dedicated scanner-resistant page, narrow trusted
page/runtime-interface changes and focused offline validation. Repository:
`C:/Users/ovisa/Documents/OAF_App/Development/OAF Website`, branch `main`, HEAD
`b2f0069be87741b21a054f9ced5411bdb90afd03`. R38, R39, R40-B and owner notes
remain preserved. The owner reports **R40-F END-TO-END TESTING CONFIRMATION PASS**:
Brevo processed the email, Gmail received it, the private link opened, explicit
confirmation completed and the PostgreSQL timestamp was validated; the temporary
HTTPS server was shut down and port 443 released. This is owner-supplied baseline
evidence, not a new live test by R41. Migrations 0001--0005 in TESTING and
DEVELOPMENT remain closed; R41 performs no migration or operational certification.

### Implemented page and link contract

- `confirm-email.html` is a standalone public page using the existing navigation,
  Arial typography, foundation palette, shared interface card/button components
  and responsive styles. Its centered content identifies OVIS ALMS FOUNDATION,
  explains the selected GraManna announcements and presents one Confirm email
  button. There is no signup form, marketing section or application framework.
- `assets/email-confirmation.js` runs synchronously in the head. It reads only
  `#confirm-email=`, validates the existing lowercase 64-hex capability shape and
  removes the fragment with `history.replaceState(null, ...)` before application
  requests. The capability stays inside a closure and the explicit confirmation
  POST body, never HTML, queries, paths, analytics, logs, history state or browser
  storage. There are no third-party resources or requests. The dedicated page
  uses no-referrer policy, including on its API fetches, and noindex/nofollow.
- The existing session endpoint supplies the browser-bound CSRF token and exact
  Boolean `confirmation_enabled`. Session discovery does not verify ownership.
  Only the explicit button handler can POST `{token}` to the existing
  `/api/notifications/confirm`, using same-origin credentials, JSON, no-store,
  CSRF header and a bounded request timeout. No GET, page load, preview or ordinary
  scanner visit can confirm. An in-memory busy guard plus disabled controls
  prevents simultaneous frontend submissions. The backend remains authoritative.
- A successful HTTP response must also carry `status=confirmed`. Success clears
  the in-memory token, removes the action, displays a green check, focuses
  "Your email is confirmed!", thanks the visitor for confirming their selected
  GraManna announcements and announces "Email verification complete". It stays
  on this page; there is no further navigation or confirmation action.
- Malformed/missing capabilities and backend HTTP 400 show generic unavailable
  copy and a link to the existing notification request/resend experience.
  Expired, revoked, suppressed and unknown links disclose no subscriber status.
  Network, server, malformed-response and session failures use fixed safe copy;
  they never echo server diagnostics or capabilities. A deliberate retry uses the
  same transient capability; a 403 clears CSRF so the next explicit attempt
  discovers a fresh session. Busy/status/alert semantics, keyboard focus,
  responsive card sizing and shared reduced-motion styling are retained.
- The template's separate `secure_confirmation_page` accepts exactly the approved
  `/confirm-email.html` and legacy `/gramanna.html` paths and always renders the
  dedicated destination on the same configured HTTPS authority. Existing explicit
  legacy processor/factory arguments therefore remain usable without touching
  protected configuration or regenerating tokens. Host labels, standard port 443,
  no userinfo/query/fragment and exact path restrictions fail closed. The existing
  `secure_page` withdrawal contract still accepts only `/gramanna.html`.
- The existing processor, dispatcher and TESTING HTTPS validation/help interfaces
  use that narrow confirmation-page validator. TESTING factory validation still
  requires the exact explicitly configured origin before protected runtime access.
  The shared public-file allowlist adds only the page and its JavaScript; both
  local hosts inherit it. No private files or directory serving are exposed.
- Already issued `/gramanna.html#confirm-email=` links are captured by the shared
  head script, cleared from that address and forwarded with the unchanged fragment
  to the dedicated page, where it is cleared again before API work. Navigation is
  before confirmation, never after success. The notification script retains the
  same fixed forwarding behavior for a later hashchange. No server redirect,
  query-string handoff, storage handoff, token renewal or new authority is added.
  The obsolete confirmation block is removed from the signup form. Request/resend,
  subscription and `#unsubscribe=` handling keep their existing purpose.

### Focused evidence and deterministic autonomy

The guarded eight-file backend gate passed **734 tests in 20.32 seconds**, with
zero unexpected external-access attempts and no failures/skips/xfails. Selected:
`test_public_confirmation.py`, `test_notification_delivery.py`,
`test_confirmation_outbox.py`, `test_confirmation_processor.py`,
`test_testing_https.py`, `test_brevo.py`, `test_notification_dispatch.py`,
`test_notifications.py`. Coverage includes existing endpoint/origin/CSRF/strict
request compatibility, original expiry/supersession, withdrawal/suppression,
stable verification timestamps, generic failures, default OFF, trusted paths and
origins, legacy configuration, new rendered links, restart recovery and preserved
release/unsubscribe behavior. Static GETs for both pages and the new script cause
no transactional model operation, with confirmation enabled or disabled.

The established website interpreter, `-B`, disabled pytest plugin autoload, empty
options/plugins, explicit file selection, repository/tests PYTHONPATH and early
`-p migration_offline` guards remain unchanged. No guard allowlist change or package
installation is needed. Full live PowerShell progress/errors/results are retained
simultaneously in `.pytest_cache/r41/backend-20261017-155445.log`; existing native
visual alerts and Invoke-OAFCodex/clipboard reporting are preserved.

Browser validation status is recorded in the final R41 evidence below.

Deterministic autonomy source review: fragment parsing/clearing, explicit-action
submission, activation discovery, busy control and safe messages use fixed rules.
Success follows the existing backend's confirmed result. The endpoint, token
cryptography, original 24-hour expiry, idempotence/timestamp stability, consent,
eligibility, budgets, suppression, outbox/attempt history, retries, leases and
uncertainty holds are unchanged. No ordinary AI or administrator intervention is
required. Deployment/activation and exceptional policy/evidence corrections retain
their existing human authority. A script-capable scanner that deliberately invokes
the confirmation POST is outside the ordinary GET/preview resistance claim; no
claim is made to distinguish such a client from an explicit browser action.

Privacy limitation: capabilities intentionally do not survive a fresh reload after
fragment removal. Reopening the original email link restores the explicit action
under the same original server expiry. JavaScript and browser cookies are required;
the noscript state explains this. No persistence workaround is introduced.

### Preservation, activation boundaries and exact inventory

The validated verification endpoint/store, subscriber rules, token construction,
provider adapter, State Requests, Contact, shared-service contracts, all migration/
schema/manifest artifacts, real configuration and launchers retain their initial
bytes. Existing document bytes remain exact prefixes. The Git index and HEAD are
unchanged; no stage/commit/push occurs. No GraManna source, operational credential,
TLS key, live PostgreSQL, Brevo, outgoing email, HTTPS host, scheduler or production
activation is accessed or changed. Existing R40-F evidence is not repeated.

Both independent activation flags still default OFF. Serving the page and creating
an app never starts processing. Future activation still needs separately approved
environment/host/account/origin and protected configuration, compatible public
confirmation and processor enablement, approved scheduling/monitoring if desired,
and separate production secret/deployment design. Authenticated provider feedback/
correlation/reconciliation remains separately contracted; uncertainty never permits
a blind resend. These gates do not reopen completed migrations or R40-F.

Exact R41 added files: `confirm-email.html`, `assets/email-confirmation.js`.
Exact R41 modified files relative to the initial working tree:
`gramanna.html`, `styles.css`, `assets/notifications.js`,
`oaf_website/notification_messages.py`, `oaf_website/confirmation_outbox.py`,
`oaf_website/confirmation_processor.py`, `oaf_website/local_testing.py`,
`oaf_website/local_testing_https.py`, `tests/test_brevo.py`,
`tests/test_confirmation_outbox.py`, `tests/test_confirmation_processor.py`,
`tests/test_testing_https.py`, `tests/confirmation_browser_check.py`,
`tests/notification_browser_check.py`, `docs/WORKFLOW.md`, `docs/WEBSITE_PLAN.md`.
Previously untracked R38/R39/R40-B files retain that Git status. The exact inventory
is scoped to R41, not all accumulated work since HEAD. Ignored helper/evidence,
initial hashes/snapshots, complete transcripts, source delta and final report are
under `.pytest_cache/r41/`.


### R41 final validation status and smallest next checkpoint

**R41 — BLOCKED: required Playwright validation is not executed.** Source
implementation, the guarded 734-test backend gate, Python syntax review,
`git diff --check` and preservation checks pass. Desktop/mobile browser behavior
and visual presentation remain unvalidated; no R41 browser screenshots or browser
PASS are claimed.

The established browser method uses only the existing shared
`..\GraManna\.venv\Scripts\python.exe` and installed Playwright packages, from
the OAF Website working directory. The current R41 instruction prohibits access
to GraManna repository paths. A website-interpreter inspection returned
`importlib.util.find_spec('playwright') == None`. No sibling path has been accessed,
no package is installed and no alternative execution method is substituted.
A narrow clarification permitting only the established shared test interpreter
and its installed packages, without any GraManna source access/modification, was
requested and remains unanswered at this checkpoint.

`tests/confirmation_browser_check.py` is updated for the dedicated page and legacy
forwarding, and `tests/notification_browser_check.py` retains subscription/
unsubscribe coverage with the new same-origin script in its intercepted inventory.
Both pass Python syntax checks but are not executed. Planned checks use only
intercepted/fake APIs and synthetic capabilities at 1280px and 390px: responsive
layout, keyboard/focus/reduced motion, immediate fragment clearing, no automatic
POST, explicit action, busy/duplicate protection, same-page success, invalid/
expired/unavailable links, network/server/session/CSRF failures and deliberate
retry, no capability storage/DOM leakage, browser/external-request errors and
preserved request/resend/signup/unsubscribe behavior. This prepared coverage is
not browser evidence until those two scripts run successfully.

Smallest next checkpoint: resolve the shared-test-interpreter boundary, then run
only these two already prepared intercepted browser checks through the existing
visible/transcribed PowerShell helper. Fix any demonstrated failure and update
this status. Do not repeat the backend campaign without a new relevant change,
R40-F live email testing, completed migrations or operational activation. Owner
Eyes & Clicks review of the resulting page/screenshots can follow; no new design
approval, live email or production-readiness claim is implied.

Final source inventory: 16 modified initial paths and two added files, as listed
above; the other 98 initial source paths retain their initial hashes. Every
initial path remains, both original governing-document byte prefixes and the
original Git index are preserved, and HEAD/branch are unchanged. Ignored evidence
is under `.pytest_cache/r41/`, including complete backend transcript, initial and
final hashes/inventory, source delta, helper and final clipboard report. The
existing native alert reports this browser-validation block separately from the
successful backend checks. Invoke-OAFCodex and all execution settings are unchanged.


### R41 browser validation continuation completed (2026-10-17)

**R41 - SOURCE / OFFLINE VALIDATED.** This continuation supersedes only the
earlier R41 browser-gate block above. The owner expressly permits read-only
execution of the established sibling interpreter, its installed dependencies and
shared Chromium cache. No GraManna application source, configuration, database,
Cargo files or Git state was inspected or changed.

Repository and branch remain `C:/Users/ovisa/Documents/OAF_App/Development/OAF Website`,
`main`, HEAD `b2f0069be87741b21a054f9ced5411bdb90afd03`. Before execution, all
116 current source paths matched the saved R41 final hashes. The prepared
`tests/confirmation_browser_check.py` and `tests/notification_browser_check.py`
were inspected and executed unchanged with
`..\GraManna\.venv\Scripts\python.exe -u -B` through the existing
`.pytest_cache/r41/run-tests.ps1 -Browser` / `-PreservedBrowser` helper.
Interpreter import PASS, Playwright **1.61.0**, shared Chromium launch PASS;
there was no sandbox restriction, alternate interpreter, install or shared-env
modification.

Both intercepted Chromium scripts PASS at **1280px and 390px**, with exit 0.
Dedicated-page loading, fragment removal before application requests, no automatic
confirmation, explicit keyboard/button confirmation, busy/duplicate protection,
focus and reduced motion, same-page accessible success, invalid/expired links,
network/API/session/CSRF failures, deliberate retries, default OFF, unchanged
legacy-link forwarding, request/resend, signup and unsubscribe are validated.
Synthetic capabilities and intercepted APIs only; no live application server,
database, credential, provider or email operation. Zero page errors and unexpected
page requests in both scripts; the confirmation script also reports zero unexpected
console errors. Injected failing HTTP/network responses produce expected Chromium
resource diagnostics. Landing/success/unavailable screenshots were captured at
both widths; visual inspection of all six confirms responsive presentation, the
green success check, approved copy and completion message without a second action.

No browser failure or source/test correction was required. The prior guarded
backend result remains **734 passed in 20.32 seconds**, zero unexpected external
access; its log and all backend source/tests are preserved. No backend rerun or
broad regression campaign was necessary. Ordinary frontend decisions continue to
use fixed parsing, explicit action, busy guards, authoritative backend outcomes
and deliberate safe retry. Deterministic autonomy source/offline review PASS;
no AI or routine administrator decision is introduced.

Complete live-output transcripts remain under `.pytest_cache/r41/`:
`confirmation-browser-20261017-162322.log` and
`subscription-unsubscribe-browser-20261017-162346.log`. Screenshots are
`landing-1280.png`, `success-1280.png`, `unavailable-1280.png` and their 390px
equivalents. Continuation interpreter evidence, before/final hashes, preservation
checks and final clipboard report are under `.pytest_cache/r41-continuation/`.
The established visual PASS alerts, complete logging and clipboard reporting are
retained. Browser cleanup completes before the existing dismissible alert dialogs.

The exact R41 source inventory remains the two added and sixteen modified paths
listed above. This continuation adds validation evidence to these two governing
documents only; every prior document byte is preserved as an exact prefix, and
the other 114 initial paths retain their hashes. HEAD, branch and Git index remain
unchanged. No staging, commit or push. R38-R41, owner work and completed migrations
remain preserved. No material blocker remains for R41 source/offline validation;
live activation, scheduling and production retain their existing separate gates.


## R41-F1: confirmation repeat and terminal-state repair (2026-10-17)

**R41-F1 - REPAIR / VALIDATION PASS (source/offline).** OAF Website only,
branch `main`, starting/final HEAD `ea85b65029f6f9927563b0e9e57134b0fb87787b`.
The initial index is empty. Its bytes, all unrelated source and the owner's
uncommitted `confirm-email.html` hidden-heading refinement are preserved.
R43 PUSHED/PASS and R40-F live verification are owner-supplied baselines;
no live verification is repeated and R44 processing work is not begun.

### Finding and minimal response refinement

The store previously returned `verified` for both a newly verified record and a
valid repeat; the endpoint mapped both to `status=confirmed`. The frontend could
not distinguish prior verification. Reopening the original link legitimately
returns to the initial explicit-action state: GET must not verify or disclose
historical verification. Baseline intercepted Chromium reached the existing
terminal success; the owner's reported post-click landing loop was not reproduced
from these checked source bytes. Its historical runtime cause remains unproven.
The new repeat regression failed before repair because the frontend displayed
the first-time wording even when given an authoritative repeat result. The
backend contract regression also failed before repair. Both logs are retained.

`NotificationDeliveryStore.confirm` now returns `already_verified` only after the
unchanged current token HMAC lookup, original issue/expiry checks, locked active
consent lifecycle and mailbox suppression checks. A first confirmation writes
`verified_at` once and returns `verified`; a valid repeat changes no persisted
record. The HTTP contract retains `status=confirmed` for existing clients and adds
the Boolean `already_confirmed`, with fixed first/repeat messages. Failures retain
the same privacy-safe unavailable response and never include this indicator.
Email request responses remain indistinguishable across subscriber states.

The dedicated script follows that Boolean for "Your email is already confirmed!"
and "Your email address has already been verified. No further action is needed."
Both success outcomes use the approved green check, clear the transient capability,
hide/disable the action, hide request-link help, focus the result heading and
announce "Email verification complete" on the same page. Existing `confirmed`
responses without the new field remain terminal success for compatibility;
malformed indicator values fail safely. No storage-based classification, automatic
POST, redirect after success, HTML/CSS redesign or new capability is introduced.

### Focused validation and autonomy

- Guarded backend: **392 passed in 13.91s** across `test_public_confirmation.py`,
  `test_notification_delivery.py`, `test_confirmation_outbox.py`,
  `test_notifications.py` and `test_notification_dispatch.py`.
- Four separately selected existing static GET/factory cases in
  `test_testing_https.py::test_factory_persistent_key_testing_identity_allowlist_and_no_processing`
  passed in **0.57s**, proving no store statement/mutation for dedicated/legacy
  pages or script GETs with public confirmation enabled or default OFF.
  **396 distinct backend cases pass**, zero unexpected external-access attempts.
  Website `.venv`, `-B`, disabled plugin autoload, empty pytest options/plugins,
  explicit file selection and early `-p migration_offline` guards are unchanged.
- Dedicated and preserved subscription/unsubscribe intercepted Playwright scripts
  PASS at **1280px and 390px** using only the approved sibling interpreter and
  installed Chromium. Same-original-link reopening requires a click; first/repeat
  terminal wording, stable action removal, forced extra-click rejection, keyboard,
  focus/live messages, fragment privacy, legacy forwarding, old-response
  compatibility, invalid/expired links, malformed results, API/network/session/CSRF
  failures, safe retry and OFF behavior pass. Zero page errors, unexpected console
  errors or external requests in the dedicated check; zero page errors/external
  requests in the preserved check. All eight desktop/mobile landing, success,
  already-confirmed and unavailable screenshots were visually reviewed.
- Backend negative cases include invalid/unknown/expired/future/superseded tokens,
  verified-then-expired/withdrawn/suppressed lifecycles, unsubscribe/resubscription,
  privacy-safe response equality, origin/CSRF, commit failures and idempotence.
  Eight concurrent confirmations classify exactly one first and seven repeats;
  later valid repeats preserve the original timestamp and all persisted records.

**Deterministic autonomy review PASS:** backend rules exclusively establish the
classification after capability eligibility; frontend rendering follows that
result, explicit-action and busy guards prevent loops, invalid/expired capabilities
cannot disclose historical state, and ordinary operation requires no AI or
administrator action. Existing human deployment/policy/key governance remains.
GET/page-load/email previews never confirm. No claim distinguishes a script client
deliberately invoking the protected POST from a person pressing the button.

Exact task-changed tracked files (10): `assets/email-confirmation.js`,
`oaf_website/notification_delivery.py`, `oaf_website/notifications.py`,
`tests/confirmation_browser_check.py`, `tests/test_public_confirmation.py`,
`tests/test_notification_delivery.py`, `tests/test_confirmation_outbox.py`,
`tests/test_notification_dispatch.py`, `docs/WORKFLOW.md`, `docs/WEBSITE_PLAN.md`.
`confirm-email.html` remains an additional pre-existing owner change, byte-for-byte
untouched by R41-F1. Original governing-document bytes remain exact prefixes.
Ignored evidence/helpers, initial/final hashes, eight screenshots, complete live
PowerShell transcripts (including expected regression failures) and final clipboard
report are under `.pytest_cache/r41-f1/`. Existing alerts/clipboard reporting are
retained. `git diff --check` passes; HEAD/index and unrelated hashes are unchanged.

No material source/offline blocker remains. Historical live-page behavior is not
certified by intercepted tests. No GraManna source access/modification, shared-env
write, credentials, real Brevo call, outgoing email, live database mutation, schema
or migration change, production operation, staging, commit or push occurs. Existing
outbox, legacy/unsubscribe links, independent default-OFF switches and original
expiry/revocation/privacy controls remain intact. R44 and operational activation
retain their separate authorization boundaries.


## R44: autonomous recurring confirmation invocation (2026-10-17)

**R44 - SOURCE / OFFLINE VALIDATED. SCHEDULER REGISTRATION / LIVE ACTIVATION:
NOT PERFORMED.** This source checkpoint implements the earlier recurring-invocation
proposal without changing its deterministic delivery authority. OAF Website only,
branch `main`, HEAD `ea85b65029f6f9927563b0e9e57134b0fb87787b`, empty index.
All 11 initially modified paths, including owner-approved R41 visuals and R41-F1
repairs, are preserved. Migrations 0001--0005 and R40-F remain closed.

`oaf_website.confirmation_schedule` adds two explicit modes:

- `plan` returns a deterministic **disabled** Windows Task Scheduler XML definition.
  It never contacts the scheduler, starts processing, reads protected settings or
  credentials, or creates an operational file. Even `--enable-processing` in plan
  mode only configures the future action; the task remains disabled.
- `run` calls the unchanged `confirmation_processor.main(...)` one-shot CLI once,
  with validated explicit arguments. Processing defaults OFF. It adds a local
  overlap guard and sanitized reporting, without a worker/polling/retry loop.
  Imports, application factories and public GETs never invoke either mode.

### Actual task and environment contract

Use exactly one canonical root task, `\OAF Website Confirmation Processor`, for
one approved environment at a time. The definition uses the absolute current
website interpreter/root, native Windows PowerShell with `-NoProfile`,
`-NonInteractive`, hidden window and correctly quoted UTF-16 encoded literal
action. Encoding is transport quoting, not encryption. The action explicitly
supplies the selected `OAF_ENV` only when absent; a conflicting inherited value
is retained and rejected by existing runtime validation, never silently replaced.

The fixed time trigger starts from local `2026-01-01T00:00:00` and repeats every
minute indefinitely. `IgnoreNew` prevents queued overlapping starts; no scheduler
restart-on-failure policy is installed. `StartWhenAvailable=true` allows delayed
missed-run startup, with no wrapper replay of missed minutes. Windows can delay
catch-up (its documented default is ten minutes). Every actual start discovers
only current database-due work. No wake, public-request trigger or real-time
dispatch promise is made. Backlog, running time, sleep and logoff can add delay;
work may expire under its original 24-hour limit.

The task is always disabled in exported XML, cannot start on demand, and has a
four-minute execution budget. The scheduler setting is a host termination policy,
not a newly claimed network deadline. Existing socket inactivity bounds remain.
Before activation, verify actual child-process termination and scheduler behavior
on the approved host; no registration/runtime scheduler certification occurred.

An explicit approved Windows account SID is required. `InteractiveToken` and
`LeastPrivilege` use that account's existing logged-on session and protected
Credential Manager/DPAPI access; no scheduler password, service account or S4U
credential workaround is introduced. **This local arrangement does not process
while the approved account is logged off or the host is asleep/off.** Always-on
processing would require a separately approved host/account arrangement.

TESTING requires exactly one normalized, explicitly approved `--testing-recipient`.
All existing SQL/recovery/claim/preparation/dispatcher/adapter restrictions remain.
No mailbox redirection or broader TESTING scope exists. DEVELOPMENT uses its
already supported ordinary eligible consent population and rejects TESTING scope.
Its runtime/database/Brevo loaders select only DEVELOPMENT credentials. There was
no DEVELOPMENT interface gap requiring a change. Production fails before secret
access. Existing matching `OAF_ENV`, forbidden alternate environment settings,
exact credential targets, verified runtime checkouts, existing stable protected
key and trusted HTTPS confirmation-page rules remain mandatory.

### Later deliberate activation and deactivation

The following is a **future owner-authorized plan/export example**, not an
activation command executed by R44. Supply approved existing nonsecret metadata;
never pass passwords, provider keys or confirmation tokens. Use the account SID
that already holds the matching runtime/Brevo credentials and protected key.

```powershell
# FUTURE OWNER-AUTHORIZED PREPARATION ONLY, from the OAF Website root.
$taskXml = & '.venv/Scripts/python.exe' -u -B -m oaf_website.confirmation_schedule plan `
    --environment testing --windows-user $taskApprovedWindowsSid `
    --enable-processing --brevo-account $taskApprovedBrevoAccount `
    --confirmation-page $taskApprovedConfirmationPage `
    --testing-recipient $taskApprovedMailbox
if ($LASTEXITCODE -ne 0) { throw 'Confirmation schedule plan rejected.' }
# Write with matching UTF-8 encoding, outside tracked/public files.
$taskExportPath = Join-Path $PWD 'instance/confirmation-task.xml'
[IO.File]::WriteAllText($taskExportPath, ($taskXml -join "`n"), (New-Object Text.UTF8Encoding($false)))
# No registration or enablement follows this example.
```

For future ordinary DEVELOPMENT preparation, select `development` and its approved
metadata and omit `--testing-recipient`. Omitting `--enable-processing` makes the
future action itself inert in addition to the disabled task. Plan output contains
configured account/page/mailbox metadata; keep its local export private and out
of Git. It contains no operational credential. The existing ignored `instance`
directory must exist before writing an export; plan mode creates no directory.

After **separate explicit owner authorization**, inspect existing tasks for this
action before importing the reviewed XML in Windows Task Scheduler under the
canonical name. Do not overwrite/adopt an unexplained existing task or register
TESTING and DEVELOPMENT copies. Confirm disabled state, matching SID, decoded
literal action, interval, execution budget and public confirmation/origin
compatibility. A separate deliberate Enable action starts recurring processing
only when its stored action also includes `--enable-processing`. Registration
must never be coupled to a test run or automatic send. R44 neither assumes nor
checks an existing registration and provides no registration/startup side effect.

Deactivate through **Disable** on the canonical task. This stops future starts;
allow an already running bounded invocation to finish. Disabling cannot recall an
already authorized/in-flight submission. If exceptional stopping is necessary,
retain all history/leases and accept conservative submitting-to-uncertain recovery.
Do not delete/reset claims, attempts, tokens, lock files or logs. Remove the stored
processing flag as additional protection when updating a disabled definition.
Re-enable only under the approved activation policy after configuration correction;
resumption discovers persisted due work without a per-subscriber Send action.

### Bounds, coordination, reporting and deterministic autonomy

The existing dispatcher/store remain byte-for-byte unchanged. Per invocation:
20 due intents, 20 expired-claim recoveries, five-minute leases, three attempts,
60/300-second conclusive-safe backoff and original 24-hour token expiry. Restart
recovers the same protected token. Missed runs never refresh expiry or reset due
times/attempt budgets. Final eligibility preserves consent, current version,
withdrawal, verification and mailbox suppression. Expired claimed work follows
safe backoff; expired submitting work becomes uncertain. Possibly submitted or
unacknowledged work is never blindly resent. Acceptance does not prove delivery
or verification. Resend supersession preserves completed history.

The Windows OS-held byte lock on ignored `instance/confirmation-processor.lock`
rejects a second local wrapper, including task aliases or another environment;
the OS releases ownership on process exit. Do not delete the file to unlock it.
`IgnoreNew` is the scheduler's first overlap control. PostgreSQL transaction/row
locks and durable one-use claims remain the authoritative coordination across
all processors, including direct CLI starts or other hosts. The local guard
does not substitute for them. Redirected runtime/log/lock paths fail closed.

Each started wrapper persists and flushes/fsyncs a sanitized start record before
calling the processor and a terminal record afterward in ignored, non-public
`instance/confirmation-processor.jsonl`. Fields are only UTC timestamp,
allowlisted environment/status, acknowledged processed count and exit code.
Stdout emits the sanitized terminal record. Fixed classifications include
`disabled`, `invalid_configuration`, `overlap`, `unavailable`, `reporting_failed`,
`interrupted` and `processed`; only completed processing returns 0. Exit 2 means
disabled/invalid/overlap, 1 failure/reporting failure, 130 interruption. Failure
to persist the start blocks processing; terminal-log failure returns nonzero and
retains known acknowledged progress in stdout. Overlap/unavailable file access
may prevent log persistence; Task Scheduler's nonzero Last Run Result remains
available. A start with no terminal record indicates interruption, not permission
to resend. Interpreter/action startup failures precede wrapper logging and require
the existing scheduler result/history. No private exception, subscriber address,
bearer, credential, link/body or raw provider response enters invocation records.

Processed counts mean acknowledged outcome persistence, not accepted, delivered
or verified mail. Zero does not prove an empty outbox. The existing durable intent/
attempt ledger retains detailed allowlisted provider outcomes; completed invocation
can include terminal rejection or uncertainty. Later operational review must
establish normal host-log/history observation, stale/missing-run handling and
sanitized ledger observation. There is no new monitoring platform, log deletion/
rotation policy, automatic pop-up per message or claimed tamper-proof local audit.
Existing Codex PowerShell/clipboard/visual-alert behavior is unchanged.

Deterministic autonomy source/offline review **PASS**: task cadence/invocation,
explicit activation and environment, SQL selection/order, concurrent claims,
retry eligibility/due times/exhaustion, expiry/revocation, consent/suppression,
provider classification, restart recovery, uncertainty holds and failure reporting
all use fixed rules. No routine AI or per-subscriber administrator dependency.
Owner authority remains for activation/deactivation, host/policy/key changes and
exceptional evidence-backed corrections. Authenticated provider feedback, durable
attempt correlation and conclusive uncertainty reconciliation remain a separate
contract; lack of feedback is never evidence permitting another submission.

### Focused evidence and remaining checkpoint

Final guarded gate: **557 passed in 19.55 seconds**, zero unexpected external-access
attempts, no failures/skips/xfails, including **60 new scheduler cases**. Earlier
53/60-case development runs passed; overlapping reruns are not additive. Selection:
`test_confirmation_schedule.py`, `test_confirmation_processor.py`,
`test_controlled_confirmation.py`, `test_confirmation_outbox.py`,
`test_public_confirmation.py`, `test_brevo.py`, plus the four existing
`test_testing_https.py::test_factory_persistent_key_testing_identity_allowlist_and_no_processing`
cases. The website interpreter, `-B`, early `-p migration_offline`, explicit file
selection, disabled autoload and empty pytest options/plugins remain. Only the
new test path is added to the guard allowlist; no isolation guard is relaxed.

Synthetic minute ticks, missed runs/restarts, interrupted submission, bounded
recovery, eight competing database-model invocations, recipient/environment
isolation, DEVELOPMENT batches, all lifecycle holds, retries/exhaustion, lock
release/overlap, safe deactivation/reactivation, reporting failures/redaction and
R41/R41-F1 backend/static-GET compatibility pass. The actual Windows byte lock
is exercised only on temporary files. Microsoft's published Task Scheduler XSD
validates the synthetic XML offline, and PowerShell independently parses the
decoded literal action (including an apostrophe in its synthetic path). No action
is executed and no scheduler service is contacted. These checks do not certify
live scheduler/process termination, PostgreSQL concurrency or provider behavior.

Reference for offline XML and delayed missed starts:
[Microsoft schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[StartWhenAvailable](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-startwhenavailable).
The schema review corrected the initial unregistered definition's version/trigger
element ordering before final validation. No failed live operation occurred.

Exact R44 source inventory: added `oaf_website/confirmation_schedule.py` and
`tests/test_confirmation_schedule.py`; modified `tests/migration_offline.py`
(one allowlist entry), `docs/WORKFLOW.md` and `docs/WEBSITE_PLAN.md` (append only).
All other 113 initial tracked paths retain their starting hashes; original
document bytes remain exact prefixes, and HEAD/index are unchanged. Ignored
evidence, preservation inventories/snapshots, synthetic XML, reference XSD,
complete visible PowerShell transcripts/helper and final report are confined
to `.pytest_cache/r44/`. Native completion/failure alerts remain in place.
No browser-facing behavior changes, so no browser campaign is repeated.

No operational credential/configuration read, real PostgreSQL/Brevo/email operation,
migration/schema change, package install, GraManna access/modification, task
registration/activation, production action, staging, commit or push occurs.
No material source/offline blocker remains; recurring email is **not operational**.

Smallest next operational checkpoint: separately authorize one bounded **TESTING
scheduler activation** under the approved logged-on account, retaining the single
R40 mailbox restriction. Confirm the exact host/SID, stable existing protected
key/credentials, approved page/origin/public activation, task uniqueness, private
log permissions/observation, import-disabled state and host termination/missed-run
behavior before enabling. Validate a small recurring lifecycle and deactivation,
then disable again. Do not repeat migrations or the completed R40-F campaign.
Ordinary DEVELOPMENT scheduling requires its own explicit operational approval;
production remains separately blocked. Feedback/reconciliation remains deferred.


## R45: Windows task XML investigation (2026-10-17)

**R45 XML REPAIR - BLOCKED. No demonstrated source defect or source correction.**
OAF Website only; branch `main`, HEAD
`ea85b65029f6f9927563b0e9e57134b0fb87787b`; index empty. The owner reports
the disabled registration trial failed with `COMException`, independent read-only
inspection found no canonical task, and a subsequent Windows validation-only call
returned `0x8004131A`. Microsoft identifies this as `SCHED_E_MALFORMEDXML`; that
HRESULT alone does not identify an offending element or prove a particular cause.
These operational findings are owner-supplied; this investigation does not repeat
registration, connect to Task Scheduler, or execute Windows TASK_VALIDATE_ONLY.
The R44 source/offline result remains historical evidence, not Windows acceptance.

### Bounded findings and source decision

Read both governing documents fully and inspect the existing scheduler source,
focused tests, processor contract and early offline guards. Relevant historical
inspection is limited to `disabled-task.xml`, `report.txt` and `terminal.log` in
`instance/r45-e2fee0e84f984046ab15ca9e6f1e2cd9/`. The unchanged approved `plan`
CLI generates disabled TESTING XML matching that saved failed-trial definition
after line-ending/final-newline normalization. Processing activation is omitted.

| Contract area | Observed XML / bounded finding |
| --- | --- |
| Schema and namespace | Task version `1.3`, namespace `http://schemas.microsoft.com/windows/2004/02/mit/task`; conforms to the published Microsoft XSD. Host-supported version and actual parser acceptance remain Windows observations. |
| Trigger and repetition | One TimeTrigger; Enabled, StartBoundary, Repetition ordering matches the published XSD; local `2026-01-01T00:00:00`, `PT1M`, no Duration, StopAtDurationEnd=false. Microsoft documents omitted Duration as indefinite repetition. |
| Settings and limits | Disabled task, AllowStartOnDemand=false, `PT4M`, IgnoreNew, StartWhenAvailable=true, WakeToRun=false; no scheduler restart policy. No demonstrated defect in these settings. |
| Principal | Explicit saved owner SID, InteractiveToken, LeastPrivilege; action Context=Owner matches Principal id=Owner. The documented XML run-level value is LeastPrivilege; replacing it with the numeric COM enum is unwarranted. No password, S4U or elevation workaround. |
| Action | Absolute native PowerShell and website interpreter/root; NoProfile, NonInteractive, Hidden; UTF-16LE Base64 literal action parses in PowerShell 5.1. It supplies explicit TESTING and calls the existing one-shot wrapper with no enable flag. No action is executed. |
| Declaration and transport | Existing declaration is `<?xml version='1.0' encoding='utf-8'?>`. Offline MSXML6 loadXML accepts the original string (parse code 0). A declaration/COM transport incompatibility remains a hypothesis, not a demonstrated cause. |
| Windows registration contract | RegisterTask receives XML as BSTR; flag 1 is TASK_VALIDATE_ONLY and does not register a task. Actual owner-context parsing is still required; generic XML parsing and XSD success cannot substitute. |

References reviewed as documentation only:
[Microsoft Task Scheduler XSD](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema),
[common trigger elements](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/a0cf999f-aa47-4821-a46a-00fd28431f65),
[repetition duration](https://learn.microsoft.com/en-us/windows/win32/taskschd/repetitionpattern-duration),
[XML run-level values](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-runleveltype-simpletype),
[RegisterTask contract](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/nf-taskschd-itaskfolder-registertask),
[HRESULT definitions](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-error-and-success-constants).

There is insufficient evidence to identify a precise incompatibility. Changing
version, trigger ordering, principal, execution budget or XML declaration now
would be speculative. Scheduler source and tests therefore remain byte-for-byte
unchanged. No corrected generator or Windows acceptance is claimed.

### Focused offline evidence and deterministic autonomy

Only `tests/test_confirmation_schedule.py` was executed: **60 passed in 3.05s**,
zero unexpected external-access attempts. The dedicated website interpreter,
`-u -B`, early `-p migration_offline`, disabled plugin autoload, empty pytest
options/plugins and explicit repository/tests PYTHONPATH are preserved.
Published Microsoft XSD validation and decoded disabled-action PowerShell AST /
exact literal arguments PASS. These are baseline source/offline findings only.
The initial local harness AST assertion was corrected to include command-parameter
nodes; its failed output is retained. No product or test assertion was changed.

Existing scheduler cases cover disabled defaults and no plan/import activation,
environment rejection/isolation, TESTING recipient restrictions, one-minute ticks,
safe retry due times/exhaustion, missed starts, lease/restart recovery, lifecycle
expiry/revocation/withdrawal/verification/suppression, provider classification and
uncertainty holds, OS lock overlap/release, finite batches, sanitized failures and
reporting. PostgreSQL claims remain authoritative. Source autonomy review PASS:
all these decisions remain deterministic and require no ordinary AI participation.
There is no new live scheduler, database or provider certification. No broad suite,
browser campaign, migration repeat, Brevo/email test or package installation occurs.

### One proposed owner-context validation-only diagnostic

Prepared, **not executed**:
`.pytest_cache/r45-xml-repair/validate-only.ps1`. Its complete copy-and-paste
launcher is in the final report. Require the exact repository, branch/HEAD,
inspected generator hash and `OAF-DELL5511\ovisa`, plus the existing loaded
Show-OAFPowerShellAlert function. Generate the same disabled TESTING plan with
the current account SID and no processing enablement. Compare two strings:
the original output and a diagnostic copy with only its optional XML declaration
removed. Require identical task element trees and unchanged inert TESTING action.
This is one bounded A/B diagnostic, not a source correction or registration trial.

Connect read-only, confirm absence of the exact canonical task (including hidden
tasks through exact GetTask lookup), print HighestVersion, and call RegisterTask
with **only TASK_VALIDATE_ONLY=1**, InteractiveToken=3 and no password for each
string. Check canonical absence before and after each call and in finalization.
Only the exact task-not-found HRESULT is treated as absence; other lookup failures
stop closed. Report sanitized per-case HRESULTs, preserve complete live terminal
transcript and both XML files in a unique ignored instance directory, copy/read
back the sanitized report, and reuse the existing visual alert convention.
No RegisterTask CREATE/UPDATE flags, task Run/enable/disable/delete, processor or
provider invocation occurs. PowerShell 5.1 syntax and the literal flags/method
boundary were inspected offline; the owner procedure itself was not executed.

Original failure with declaration-free acceptance would isolate the declaration
path for a minimal follow-up repair; it would not distinguish quoting from encoding
or certify a corrected source generator. If both fail, this hypothesis is not
established and no repair is justified. If the original passes, the historical
failure is not reproduced. Preserve all results without automatic registration,
fallback variants or activation. Actual registration still requires separate
explicit owner authorization, even after a later corrected-generator validation.

### Preservation and exact task delta

Only `docs/WORKFLOW.md` and `docs/WEBSITE_PLAN.md` are appended by this task.
Original document bytes remain exact prefixes. All other 12 initially changed /
untracked files retain their hashes, including R41 visuals, R41-F1, R44 source,
tests and test allowlist; owner notes remain intact. HEAD, branch and index stay
unchanged. No staging, commit, push, operational credential/configuration/key
access, database operation/migration, provider/email, GraManna access, production
operation or scheduler registration/activation occurs. Completed 0001--0005 and
R40-F work stays closed. Invoke-OAFCodex and automatic clipboard reporting remain
unchanged; the diagnostic uses the already loaded alert function without loading
or modifying the owner's profile.

Ignored local snapshots, inventories, unchanged generated XML, complete offline
PowerShell/pytest logs, harness and owner procedure are under
`.pytest_cache/r45-xml-repair/`. The unresolved gate is precise owner-context
Windows XML compatibility evidence; **R45 XML REPAIR - BLOCKED**.


## R45: demonstrated XML declaration repair (2026-10-17)

**R45 XML REPAIR - SOURCE / OFFLINE PASS. Corrected-generator owner-context
Windows validation remains pending; registration/activation stays OFF.** This
continuation supersedes the earlier undemonstrated-cause/source-repair block only.
All historical evidence and owner notes above remain intact.

The owner supplies the decisive Windows A/B result: original generated XML was
rejected by TASK_VALIDATE_ONLY=1 with HRESULT `0x8004131A`; identical XML without
its declaration was accepted. Scheduler HighestVersion was `0x00010006`, canonical
task before/after was NONE, and no processor/provider operation occurred. This
isolates declaration handling as the compatibility problem without claiming its
underlying parser/transport mechanism or corrected-generator Windows acceptance.

The entire production source correction is the final serialization argument in
`confirmation_schedule.task_xml`: `xml_declaration=True` -> `False`, retaining
`encoding="unicode"`. The normal `plan` CLI now emits declaration-free XML directly;
no caller stripping, alternate task definition or scheduler redesign is added.
All other production source bytes match the initial R44 generator.

Focused guarded gate: **63 passed in 3.20 seconds**, zero unexpected external-access
attempts. Only `tests/test_confirmation_schedule.py` runs, through the dedicated
website interpreter, `-u -B`, disabled plugin autoload, empty pytest options/plugins,
explicit file selection and unchanged early `-p migration_offline` guards. Updated
function/CLI regressions cover both environments and processing configurations,
requiring declaration-free well-formed XML and disabled tasks. Existing recipient,
environment, activation, retry, lifecycle, recovery and reporting cases pass.

Under the same guards, preserved-versus-corrected generators produce exactly
identical XML content after declaration removal for all four environment/activation
configurations. Namespace, version/attributes, trigger/settings, owner identity,
and encoded action remain identical. Offline Microsoft XSD and decoded PowerShell
syntax/literal checks pass for those four definitions and the apostrophe-path
synthetic definition. A normal disabled TESTING plan also matches the saved R45
owner-SID XML exactly after declaration removal, validates against the same XSD,
and matches the prepared block's exact inert action. No decoded action is executed.
Original R44 synthetic evidence is restored after retaining the corrected copy.

Deterministic autonomy review **PASS**: this serialization-only correction changes
no ordinary cadence, eligibility, consent/suppression, selection, claim, retry,
expiry, recovery, security, environment/recipient or provider decision. Preserve
disabled-by-default registration, PT1M recurrence, PT4M execution limit, IgnoreNew,
InteractiveToken/LeastPrivilege, approved SID, explicit TESTING and independent
processing OFF in this trial. Existing deterministic processing and exceptional
owner activation/policy authority remain unchanged; no safety gate is weakened.

Prepared, **not executed**:
`.pytest_cache/r45-declaration-repair/validate-corrected-only.ps1`. It requires the
exact website repository, `main`, expected HEAD, corrected generator SHA-256 and
`OAF-DELL5511\ovisa` with the approved SID. It generates the corrected disabled
TESTING plan without processing enablement, requires no declaration and the exact
inert action, checks canonical absence, invokes one RegisterTask call with only
TASK_VALIDATE_ONLY=1 / InteractiveToken=3 and no password, and checks absence
again after validation and in finalization. It reports sanitized acceptance or
HRESULT, retains live output/full transcript/XML/report in a unique ignored
directory, reads back the clipboard report and uses the already loaded OAF visual
alert. PowerShell 5.1 syntax, exact action assertion and literal validation-only
method boundary pass offline. It contains no old A/B expected-failure assumption.
No registration, activation or scheduler-service call is performed by this repair.

Exact source/document delta: `oaf_website/confirmation_schedule.py`,
`tests/test_confirmation_schedule.py`, and append-only `docs/WORKFLOW.md` /
`docs/WEBSITE_PLAN.md`. Repository `C:/Users/ovisa/Documents/OAF_App/Development/OAF Website`,
branch `main`, HEAD `ea85b65029f6f9927563b0e9e57134b0fb87787b`, empty index and
all unrelated initial paths are preserved. R41/R41-F1, owner visuals/notes and R44
processing remain intact. Ignored snapshots, complete live offline logs, XML,
comparison harness, procedure review and clipboard report are under
`.pytest_cache/r45-declaration-repair/`. Existing Codex/helper settings are unchanged.
No GraManna access, operational credentials, database/migration, real provider/email,
production action, package install, scheduled invocation, staging, commit or push.
No source/offline blocker remains. Corrected-generator owner-context Windows
TASK_VALIDATE_ONLY acceptance is the remaining validation boundary; actual task
registration and activation still require separate explicit owner authorization.


## Notification Management V2: focused source implementation (2026-10-19)

**NOTIFICATION MANAGEMENT V2 — SOURCE READY. Source/offline evidence only.**
This owner-authorized checkpoint implements the dedicated management page, email
management authority, recovery and narrow Brevo unsubscribe receiver. No live
PostgreSQL, migration, credential, provider API/email, webhook registration,
scheduler, deployment or production action is performed. Existing migrations
0001–0005 remain applied/verified per the owner and are not rewritten or reapplied.

Both governing documents and all four ignored drafts in
`instance/notification-management-v2-draft-20261018/` were read. The focused gap
pass confirms the existing database, protected key, Flask security, delivery
ledgers and outbox can supply V2. The owner's controlled experiment establishes
signup → automatic Windows processing → Brevo confirmation delivery → Gmail
Unsubscribe → Brevo Unsubscribed event. This resolves the drafts' Gmail-to-Brevo
blocker. It does **not** establish Brevo-to-OAF synchronization. The experiment
was not repeated, no email was sent, and the controlled mailbox was not unblocked.
Drafts and existing R45/R46 evidence remain unchanged.

### Bounded supersession and implemented contract

Only the old immutable-preferences user experience, ordinary signup-page
unsubscribe destination, and deferral of this specific provider event are
superseded. Historical statements remain evidence of their original checkpoints.
Anonymous duplicate signup still cannot retrieve or replace existing preferences,
consent, verification or another lifecycle's capability. Unrelated shared-service,
State Request, Contact, release approval and migration policies remain governing.

- `/manage-notifications.html` and `assets/notification-management.js` reuse the
  existing navigation, palette, cards, fields and buttons. Authorized subscribers
  view web/Android/iOS/state selections, add/remove categories, change the state,
  explicitly save or unsubscribe completely. There is no account, password,
  dashboard, email-address change or public subscriber lookup. The signup page
  links here; legacy `gramanna.html#unsubscribe=` links forward here with unchanged
  unsubscribe-only authority. Dedicated confirmation visuals remain untouched.
- Browser POST routes are `/api/notifications/manage` (authorized read),
  `/api/notifications/manage/save` and `/api/notifications/manage/recovery`.
  Existing same-origin/fetch-metadata, browser-bound CSRF, strict JSON, 1 KiB
  browser body bound and protected HttpOnly/SameSite cookie conventions apply.
  Static GET/HEAD never changes consent or preferences. Fragments are cleared at
  head-script entry; capabilities remain in closures and authorized POST bodies.
  No query, browser storage, third-party resource or logged token is introduced.
- Separate HMAC-SHA256 `oaf-notification-management-v2:` capabilities bind the
  explicit TESTING/DEVELOPMENT environment, original subscription digest,
  preference revision, issuance, expiry and random 256-bit context. Normal email
  links last at most 30 days; recovery links last 24 hours. V1 unsubscribe,
  confirmation, signup receipts, recognition and CSRF confer no preference access.
  Viewing/editing requires the original active, verified lifecycle. An emailed V2
  capability may withdraw unverified consent without verifying it. Confirmation
  still requires its existing explicit action and current, unexpired capability.
- Save requires fixed Boolean categories, registered state/null, explicit consent
  for retained selections, expected revision and random action ID. All selections
  OFF means withdrawal; malformed/null preferences are rejected. Advisory and
  subscription row locks serialize revision comparison, mutation and append-only
  audit insertion. Identical action retries converge after lost commit responses;
  changed payloads or stale revisions fail without writing. Successful saves return
  a continuation only to that authorized caller, preserving original expiry.
  Old revisions cannot disclose newer preferences or reactivate withdrawn consent.
- Original consent version/time and verification history remain intact. Audit rows
  retain before/after selections, consent evidence, revisions, selection grant
  times and fixed outcomes. Withdrawal sets the first timestamp and retains prior
  selections, preserving the existing at-least-one-selection database constraint.
  New consent lifecycles still require fresh signup and their own verification.
  Added/re-added category grant time must satisfy the announcement cutoff at both
  audience preparation and final submission. Links render under that final lock.
  Later withdrawal cannot recall an already authorized/in-flight submission.
- Recovery returns the same status/message for every valid address, including
  unknown, withdrawn, suppressed and throttled mailboxes. It reuses normalization,
  the durable shared quotas/cooldown, existing confirmation intents/attempts,
  processor, Brevo adapter and fixed templates. Unverified records use the existing
  confirmation purpose; verified records use a separate management purpose.
  Requests do not revoke usable management links, verify ownership, clear blocks
  or reset uncertainty. A suppressed sender may be unable to deliver recovery.
- V2-enabled confirmation/release/recovery emails include the visible text/HTML
  **Manage Preferences / Unsubscribe** link to the dedicated page. Management
  authority is minted only for email preparation or an authorized continuation,
  never an anonymous signup/recovery response. OFF-mode confirmation/release
  messages retain unsubscribe-only links using the dedicated destination.
  Brevo's automatic Gmail unsubscribe headers are untouched.

### Authenticated Brevo event and deterministic transaction

POST `/api/notifications/brevo/unsubscribed` requires HTTPS and an exact bearer
header checked in constant time. Browser cookies, Origin and CSRF are not provider
authentication. The dedicated `BrevoWebhookConfig` excludes the token from repr;
its explicit loader uses the pinned exact-target Windows convention at
`OAF Website/<environment>/Brevo/UnsubscribeWebhook`. This is separate from the
Brevo API key. No secret is provisioned, stored in a file/URL or printed here.
Production fails closed through the existing environment/configuration gate.
[Brevo documents this bearer contract](https://developers.brevo.com/docs/secured-webhooks).

The webhook alone has a 16 KiB strict single-event JSON allowance. Require
`event=unsubscribed`, normalized recipient, bounded `message-id` and UTC
`ts_event`; validate optional documented metadata and timestamps. `id` is the
webhook definition ID and is never used as message or occurrence identity.
Correlation examines **both confirmation/recovery and release parents/attempts**:
one accepted provider message identity, consistent accepted outcome/timestamps,
authoritative recipient, exact injected database/environment, and original
lifecycle. Only one enclosing angle-bracket pair may differ; case/interior bytes
remain exact. Release event environment must also match. No email-only, subject,
tag, contact-ID or uncertain-message fallback exists.
[The provider payload contract supplies these fields](https://developers.brevo.com/docs/transactional-webhooks).

One existing locked database transaction inserts the unique HMAC event receipt
into the notification change audit, withdraws that original lifecycle and inserts
permanent `provider_block` suppression while preserving first suppression evidence.
Duplicate callbacks are harmless. Delayed events cannot withdraw newer consent;
mailbox suppression can still prevent its delivery and is reported separately.
Prior delivery/attempt/verification history is not rewritten. Correlation failures,
contradictions and malformed/forged events never mutate consent. Missing accepted
correlation and transaction/commit uncertainty return 429, with safe duplicate
handling on retry. Brevo documents finite retries and discards ordinary 5xx;
there is no guaranteed historical redelivery or invented reconciliation worker.
[Brevo retry behavior](https://developers.brevo.com/docs/retry-mechanism).
Provider blocking is not reported as synchronized OAF withdrawal before commit.

### Minimal additive migration and explicit activation

Prepared `0006_notification_management`, parent `0005_confirmation_outbox`:

1. Add `notifications.preferences_revision`, default zero, with a nonnegative check.
2. Add one append-only `notification_preference_changes` table for typed preference,
   consent/action and correlated unsubscribe receipts; no duplicated email list.
3. Add immutable intent purpose (historical default `confirmation`) and management
   revision binding to the existing outbox. No second queue/worker/scheduler.

Runtime UPDATE expands only to the four preference columns and revision. Audit
receives SELECT/INSERT only. Its reads use the existing advisory lock without
FOR UPDATE, which would otherwise require an unnecessary UPDATE privilege.
[PostgreSQL's locking privilege rule](https://www.postgresql.org/docs/17/sql-select.html).
No DELETE, blanket UPDATE, email/identity/original-consent update, audit rewrite,
role change, metadata grant or suppression removal is added. Historical schema
helpers and revision files are preserved; validators support both original exact
states and the successor. Manifest review remains `pending_independent_review`.
Integrity hashes issue no execution authority.

`create_app(management_enabled=False, brevo_webhook_config=None)` defaults OFF.
Explicit V2 activation enables management persistence, never sending or schema
creation. The existing TESTING HTTPS entry point accepts `--enable-management`
and optional protected bearer-account metadata through `--brevo-webhook-account`.
The existing processor/scheduler accept `--enable-management` separately from
`--enable-processing`. All ordinary tasks remain disabled in generated XML; their
default XML/action remains identical to the preserved R45 generator. No task is
registered, changed or activated. After migration, configure all participating
public workers and processors consistently; do not mix OFF/V2 processors with
management-purpose work. Default 0005 confirmation behavior remains compatible.

### Focused evidence and autonomy

**1,132 distinct offline cases PASS**, excluding overlapping reruns. The new core
passed 184 cases in 17.42s; the subsequent 14-case targeted gate adds new
append-only-lock and database-error sanitization assertions and rechecks API, recovery, accepted callbacks,
rollback/uncertain commits and old-lifecycle behavior after final source changes.
The 946 directly relevant existing regression cases all pass across the initial
run and the 366-case focused correction run; the eight initial failures were old
destination assertions and callback test-hook signatures. New-fixture failures
and every complete progress/error/result log remain preserved.

Coverage includes all 18 requested areas: link generation; environment/lifecycle/
revision/purpose access; rejection before disclosure; every preference and state;
full withdrawal; original consent/verification and append-only history; concurrent
edits/claims/withdrawal; legacy safety; authenticated confirmation/release callbacks;
forgeries; recipient/message mismatch; old lifecycle; duplicates; absent/uncertain/
contradictory correlation; transaction/commit failures; environment/recipient scope;
no unintended sends; and existing confirmation/R41-F1/R45 scheduler behavior.
No whole-repository coverage percentage or live PostgreSQL certification is claimed.

All three intercepted Chromium scripts PASS at **1280px and 390px**: V2 management,
preserved signup/legacy withdrawal, and dedicated confirmation. They cover explicit
action, consent, keyboard/focus, busy controls, fragment/storage/referrer privacy,
lost-commit identical retries, stale conflicts, recovery, errors and OFF behavior.
Zero page errors or unexpected external requests; V2 and confirmation also report
zero unexpected console errors. Management screenshots were visually reviewed.
Only the established shared Playwright interpreter/packages were used read-only.

Dedicated website interpreter, `-u -B`, explicit pytest file selection, disabled
autoload/empty options/plugins, and early `-p migration_offline` guards are retained.
Every guarded run reports zero unexpected external-access attempts. Terminal-visible
progress and complete simultaneous logs, preservation snapshots and final report
reside under ignored `.pytest_cache/notification-management-v2/`; existing OAF
visual alerts and clipboard reporting are reused. No broad historical campaign
or R45/R46 operational test is repeated.

Deterministic autonomy review **PASS for source/offline scope**: authentication,
authorization, revision checks, validation, consent, cutoff eligibility, quotas,
claims, bounded retry, uncertainty holds, correlated withdrawal, suppression,
idempotence and rollback use fixed backend rules. No routine AI, moderator,
subscriber approval, second Send action or reconciliation operator is introduced.
Official release/state decisions, exceptional corrections, secret policy and
separately approved migration/deployment/activation retain owner authority.

### Preservation and exact next checkpoint

Branch `main` and HEAD `ea85b65029f6f9927563b0e9e57134b0fb87787b` are preserved.
The original index remains empty and byte-identical. All initial paths remain;
owner confirmation-page bytes and unrelated changes are preserved. Both governing
documents retain their entire starting bytes as prefixes. Revisions 0001–0005,
their schema helpers, ignored drafts and existing R45/R46 evidence are unchanged.
The initial/final hash inventory records the exact source delta. Nothing is staged,
committed or pushed, and no GraManna application file is changed.

**Exact next owner checkpoint:** independent exact-artifact/prerequisite review
of 0006 and its changed manifest/catalog helpers, followed only by a separate
single-use **TESTING 0005 → 0006** execution authorization. Validate real generated
catalog/default/dependency/ACL behavior, runtime privileges, rollback and concurrent
transactions there. Separate DEVELOPMENT authorization requires matching successful
TESTING evidence; no earlier migration is rerun.

Webhook activation/provisioning remains a subsequent explicit operational checkpoint:
approve a provider-reachable TESTING HTTPS endpoint, separate protected bearer and
registration, consistent public/processor V2 activation, and actual authenticated
callback/message-ID correlation and committed withdrawal. Existing loopback hosting
alone is not provider-reachable. Respect the already recorded unsubscribe and keep
the mailbox blocked; do not repeat Gmail's experiment or send another email.
Historical-event availability/redelivery must be established before claiming that
specific live callback is proven. Live link tracking/fragment confidentiality and
provider retries also remain operational validation. No unresolved source/provider
contract blocker remains, and no live webhook or production PASS is claimed.

## Permanent Responsive UI/UX Visual Review

- Use Chrome DevTools Device Toolbar for lightweight responsive visual review of website interfaces.
- Review representative viewport sizes: mobile phone (e.g. 390 x 844), tablet where relevant, and desktop.
- Inspect the full page, not just the initial viewport. Check layout, headings, text wrapping, spacing, form controls, scrolling and horizontal overflow.
- Use browser screenshots for owner visual approval.
- Keep checks proportional to the actual visual change. Do not require broad test campaigns for CSS-only work.

This rule supplements existing workflow requirements. Preserve existing Playwright automation guidance, previous owner approvals and Eyes & Clicks rules.


## Step 3 consolidated repair: approved forward contract (2026-10-20)

Record these owner-approved refinements before implementation; retain all earlier
entries, helpers, consumed authorizations and run evidence unchanged. Scope is one
coherent source/helper repair with guarded offline and intercepted-browser checks.
No live database/credential/registry/Task Scheduler access, provider/email/worker,
subscriber mutation, new management-link request, operational issuance/reuse,
HTTPS reload, migration, activation, paid resource or Git mutation is authorized.

**OAF execution boundary.** Broad task discovery remains mandatory. Relevance is
established through action execution and resource relationships, decoding bounded
inspectable actions and examining reviewed known wrappers. Exact reviewed relevant
OAF task XML and required disabled/idle states remain pinned, as does the exact new
single-use definition/action. Keep process visibility, competing execution, local
wrapper lock, database sessions, durable claims and final recipient/intent checks.
Unrelated inventory/XML drift is recorded, not blocked solely by historical hashes.
Record opaque unresolved actions and the explicit reliance on the existing trusted
Windows host/account boundary; this test cannot certify arbitrary privileged Windows
internals. Block demonstrated OAF conflicts and unresolved relationships needed for
the actual OAF boundary. Never trust names, SYSTEM, vendors or signatures by themselves.
The unidentified COM handler is not declared harmless. No further COM/registry or
historical host investigation is prerequisite, and no task may be modified here.
Historical provenance, current reviewed source/configuration and HTTPS process
identity must be separate bindings; source review/reload is not subscriber drift.

**Acknowledgment-only withdrawal recovery.** Add a narrow pre-mutation POST under
the existing origin/fetch-metadata, browser recognition and CSRF guards. It accepts
the exact withdrawal action/revision/payload using current management token/session
authority and returns an opaque signed receipt; issuance neither withdraws nor
appends an audit row. Reuse the persistent protected key with a distinct signing
domain. Bind environment, browser HMAC, original lifecycle, expected revision,
original management-action digest, action-ID digest, canonical payload digest,
issuance and finite expiry. Maximum age: 600 seconds, capped by the original token
and (when used) session expiry, with no renewal during replay. Only withdrawal
payloads qualify (explicit unsubscribe or all preferences off).

The frontend obtains this receipt before submitting the mutation and keeps it only
in the page closure with its exact action. A retry sends the same body/receipt even
when management-cookie deletion headers arrived without the response body. Both
the original-cookie-retained and cookie-deleted cases therefore retain bounded
acknowledgment authority without restoring management authority. The receipt alone
can only return `unsubscribed` for a matching append-only management audit row and
the same withdrawn lifecycle/revision. It never permits a new withdrawal or another
action. Exact browser-cookie repeats may recognize the same committed withdrawal
within that bound; all ordinary reads/edits still reject revoked access. Preserve
the first timestamp and exactly one audit transition under existing transaction/
row locks. Always clear management cookies on successful withdrawal/acknowledgment.
Forged, expired, wrong-browser/environment/lifecycle and changed-action/payload
receipts fail with generic unavailable responses. No subscriber state is revealed
without authority. No private URL, log, DOM or browser-storage persistence is added.
Fresh reload loses the transient receipt; expiry never restores access. No schema,
migration, account, queue or generalized receipt framework is introduced.

**Connected evidence.** Submission permission remains strict; read-only outcome
observation separately publishes pending/accepted/rejected/expired/failed/claimed/
uncertain and incomplete results after verified TESTING database identity. Original
expiry, acceptance or historical whole-host equality must not suppress observations.
Record completeness separately from success; retain known phase/predicate and safe
exception class/SQLSTATE. An uncertain provider reference is correlation only and
never permits resend. Establish shared-log boundaries before early failures; absent
boundaries imply no attribution. Preserve historical logs, exclusive scheduler/
observer files, terminal persistence, consumed reservations and exact-task cleanup.
Reporting failures preserve acknowledged outcomes and prohibit another invocation.

Rename the forward `other_mailbox_fingerprint` to
`target_release_change_fingerprint`; historical evidence retains its old spelling.
Add a separate private-data-free preservation digest for the primary Foundation
mailbox, covering its lifecycle and related ledgers; validate with two synthetic
mailboxes only. Keep the original CloudCake TESTING recipient, revision 0,
canonical-JSON intent fingerprint and creation/expiry timestamps in the existing
private authoritative evidence; do not copy those identifying values into Git.
Resolve the private context only through authoritative evidence/canonicalization.
Never renew or replace it, reuse consumed authority or confuse new hashes with
permission. Preserve PowerShell 5.1, website interpreter, Invoke-R45Python,
scheduled child, create-only task/principal/bounds/overlap, both enable flags,
mailbox restriction, repeated safety checks, durable attempts and no blind retry.

Precontract deterministic-autonomy review: scope and identity predicates, eligibility,
claims, finite expiry, outcome classification, bounded receipt issuance/replay and
failure recovery are explicit server rules. No ordinary runtime AI, administrator
per-message approval or second Send action is introduced. This exceptional TESTING
procedure is not production policy. Activation/secret policy and exceptional
evidence-backed corrections remain existing owner governance. Finish and report
this offline revision together; fresh live preflight, authorization, required HTTPS
reload, delivery and actual unsubscribe remain separate and unperformed.

### Consolidated implementation and connected offline result

All six areas are repaired in one ignored successor package:
`.pytest_cache/r47-step3-consolidated-20261020/`, package identity
`c4d89d330b934eeca504f5ba8eac0874`. Its expected future authorization slot is
preparation metadata only; no operational authorization is issued or reusable.

- Scoped task discovery retains exact relevant definitions, disabled/idle checks,
  exact child/action verification, process visibility, wrapper lock, database
  sessions, durable claims and final eligibility. Unrelated XML/removal drift is
  observational; opaque COM remains unresolved under the explicit host boundary.
- The existing preflight helper separately observes all outcome classes and
  publishes incomplete sanitized phase/operation/predicate/class/SQLSTATE evidence.
  Wrong database identity never supplies observations. Expiry or failed acceptance
  cannot suppress a valid read-only outcome. Current reviewed source/configuration
  and HTTPS process bindings are distinct from original lifecycle/intent provenance.
- The forward existing classifier accepts bounded consistent references with
  `submission_unknown` as uncertainty. Acceptance is never inferred from a reference;
  contradictory evidence and automatic-resend holds remain enforced.
- Launcher boundaries precede early failures, explicitly handle missing/partial
  logs and retain history. Exclusive scheduler/observer files and terminal records,
  flush/finalization, clipboard and alert error handling preserve acknowledged
  outcomes and permanently consumed reservations. Scheduled execution is unchanged.
- `notification_management.py` adds only pre-withdrawal receipt issuance and exact
  audit acknowledgment routes, plus bounded cookie acknowledgment. The page retains
  the receipt in its closure before mutation, covering both lost-body cases without
  granting read/edit or restoring a cleared management cookie. No schema changes.
- Forward evidence names target release/change preservation accurately and queries
  the primary's separate scoped lifecycle/ledger fingerprint. Tests use two synthetic
  mailboxes, including untouched primary pending work; no real primary was queried.

Executed gates: **150 management backend cases**, **37 helper cases** and **125
PowerShell assertions**, with **zero unexpected external-access attempts in the
final guarded runs**. Counts exclude overlapping reruns. The helper module uses the
unchanged early guard with one exact temporary allowlist extension and the existing
conftest fixture. Native read-only Git/file identity checks run in PowerShell;
Python guards remain active. Earlier failed harness runs and their blocked Git
subprocess attempt are retained. They establish no credential/database/network
access. No skips, xfails or weakened assertions are used; pytest reports one
assertion-rewrite warning because the guard is deliberately imported first.

Focused intercepted Chromium passes at **1280px and 390px**, using the shared
Playwright interpreter/packages read-only from the website root. Real browser
cookie deletion precedes an unusable response body; the next explicit action
acknowledges without another mutation. Zero page errors, unexpected console errors
or external requests. Eight screenshots retained; desktop preferences and mobile
withdrawal screens inspected. Existing confirmation/signup browser campaigns and
all live PostgreSQL, host/COM, provider and production certification were not run.

Postimplementation deterministic-autonomy review PASS: fixed signing, browser/
revision/action binding, finite expiry, append-only evidence, eligibility, claims,
outcome/uncertainty and recovery rules govern ordinary operation without AI or
per-message administrator decisions. Existing activation/secret policy and exceptional
evidence reconciliation remain owner controls; TESTING procedure is not production
policy. Receipt loss on fresh reload or expiry gives no renewed authority.

Exact task source delta: `oaf_website/notification_management.py`,
`assets/notification-management.js`, `tests/test_notification_management.py`,
`tests/notification_management_browser_check.py`, and these two governing documents.
All other initial source paths, original document byte prefixes, prior reviewed
packages/run evidence, branch/HEAD/index, migrations and owner changes are preserved.
The successor `FILE-IDENTITIES.json`, preservation result, validation results and
consolidated report record the exact artifacts and reused evidence. Hashes confer
integrity only. No demonstrated material blocker remains for this offline revision.
One smallest next checkpoint: coherent exact-artifact/prerequisite review together.
No fresh live preflight, execution authority, required HTTPS reload, email delivery
or actual unsubscribe exercise occurred; no current eligibility or Step 3 PASS.

## Accepted operational safeguard correction — current contract (2026-10-21)

The owner accepted the necessity audit dispositions for one connected source/offline
batch. This entry refines the current contract without reopening that audit or adding
a Project Settings approval. Earlier outcomes, consumed authority and evidence remain
history. The authoritative successor is
`.pytest_cache/operational-safeguards-v1-20261021/`; its manifest, dependency inventory,
focused receipts and consolidated report identify the exact sources and invocation.
Previously accepted packages remain unchanged.

- **Execution integrity:** Pin selected imported runtime modules, executed helpers,
  relevant configuration/interpreter and security-sensitive served assets. Retain
  original intent anchors and permanent consumed-authority evidence. Documentation,
  README/history, Git branch/HEAD/index, unused tests/editor files, archives and
  migration sources are preservation inventory, not runtime equality predicates.
  Redundant module-membership assertions add no authority. Long-lived source locks
  cover actual execution dependencies; immutable locked bytes need not be repeatedly
  rehashed. Relevant mutable configuration, import shadows, process/task/lock state,
  consent, claims and expiry still require checks before consequential operations.
- **Current execution relationships:** Discover broadly; classify actual execution
  and resource relationships. Ordinary PowerShell startup, repository navigation,
  venv activation and supported read-only inspection are not notification processing.
  They need neither historical-parent recovery nor editor-file hashes. Unrelated
  Python processes do not compete merely by name. Direct/encoded workers, proven
  worker descendants, relevant unresolved execution, unsafe relevant tasks, active
  wrapper locks and genuine database conflicts still block. No blanket shell/Python
  exemption exists. Preserve exact relevant task definitions, disabled/idle states
  and create-only single-use actions.
- **Python children:** HTTPS and `Invoke-R45Python` share an explicit effect-based
  noninteractive policy. Remove PYTHONSTARTUP only temporarily; permit supported
  UTF-8/output, unbuffered-output and bounded hash-seed settings. Reject interpreter,
  import/cache, optimization, inspection, keyring and database overrides. Establish
  the exact interpreter, no user site/bytecode writes and a fresh empty cache prefix.
  Restore all changed Process values on every exit. Offline pytest retains its
  separately controlled repository/tests path and early isolation plugin. Do not
  modify profiles or User/Machine environment. Windows enforces actual execution
  policy; an exact RemoteSigned label is not another readiness predicate.
- **HTTPS provenance:** Bind the reviewed current launcher/manifest to exclusive
  current invocation/startup evidence, current owner/PID/creation identity, proven
  interpreter/redirector/launcher relationships and the actual single TLS loopback
  listener with approved origin and flags. Obsolete startup equality cannot replace
  these checks or prevent recognition of a freshly verified listener. Readiness
  prose is only a cue for verification. An abandoned mutex requires current-state
  checking and does not itself prove continuing competition.
- **Exact exceptional intent (M01):** The existing outbox/processor accepts an
  optional immutable `ManagementIntentScope`, an additional constraint rather than
  an issuer. Bind the original canonical intent fingerprint and immutable identity
  fingerprint, including original lifecycle, token digest, management purpose,
  revision zero and creation time; restrict to attempt one, the original deadline
  and approved TESTING recipient. Resolve private context only from authoritative
  scoped records. Filter candidates and expired-claim recovery to that exact context
  before LIMIT, then enforce scope at claim and final locked submission with a fresh
  DB clock after rendering and before commit. Another intent for the mailbox,
  including a late concurrent intent, gains no exceptional authority. Record already
  authorized outcomes after expiry without erasing acceptance. Ordinary separately
  approved recurring processing retains its existing behavior without this scope.
- **Originating failures (M02):** Carry the first bounded sanitized stage/operation,
  stable predicate, safe expected/observed conditions, UTC, safe exception class,
  wrapped SQLSTATE, HRESULT/native exit when present, and side-effect certainty
  through existing `BatchResult`, optional `first_failure` JSON, wrapper and parent.
  Validate exact fields/allowlisted values before display. Preserve acknowledged
  counts through provider, cleanup and reporting failure. Never serialize raw
  exceptions, SQL parameters, credentials, capabilities or recipient records.
- **Observation (M03):** Verified TESTING DB identity and a read-only transaction
  permit outcome observation independently of provider send-readiness, provider key
  and protected application key. Retain ledger acceptance/rejection/expiry/pending/
  uncertainty even when other checks fail. Key-dependent suppression/full-preservation
  checks remain explicitly unavailable without their inputs; infer neither absence
  nor complete preservation. Existing exclusive durable STARTED/terminal evidence
  records distinguish incomplete observation from submission permission.
- **Reporting cost and continuity:** Capture historical log-prefix identity once at
  the run boundary and check it at finalization. Poll file identity/length and the
  bounded already observed current tail, including interrupted partial records.
  Preserve old logs, exclusive evidence, consumed reservations, native exit codes,
  visible simultaneous sanitized output, automatic clipboard/read-back and existing
  OAF visual alerts. Reporting failure is INCOMPLETE and grants no retry authority.

Original intent fingerprint
`original intent fingerprint retained in private authoritative evidence`
expired permanently at **2026-10-21T03:28:14.153915Z**. Never renew, extend, replace,
reuse or retarget it. This source batch creates no intent or operational authority.
No second queue, table, email service, authorization framework or Send action is added.

Validate the changed boundaries together with focused synthetic cases; reuse accepted
evidence for unchanged features. One consolidated deterministic-autonomy review covers
eligibility, selection, isolation, scope, lifecycle, retry/expiry, recovery and reporting.
Ordinary decisions remain explicit server rules without AI, per-subscriber approval or
a second Send decision. Existing Foundation activation, policy/secret decisions and
exceptional evidence-backed corrections retain authorized administrative control.

This is source/offline only: no HTTPS startup/reload, existing process action, scheduler
change, real processing, live database/credential/provider access, email/recovery,
lifecycle mutation, authorization issuance/consumption, migration, production, GraManna
edit or Git mutation. Offline PASS establishes source behavior, not live readiness.


### Step 5: HTTPS launcher webhook configuration source/offline PASS (2026-10-22)

Authoritative future HTTPS source:
`.pytest_cache/step5-https-webhook-v1-20261022/Restart-TestingHttps.ps1`.
SHA256 `3CC0D910D1313693B094A51F3C227D7848FDAC702772A53A49987A648F6D56B2`;
`FILE-IDENTITIES.json` SHA256
`422035C08E7B689AC62DC6EC3E637D3C569BA4B705B6EAC326BD33EF20746C48` in that directory.
This is a minimal successor of the accepted operational-safeguards launcher
(`513464FB679B502171414C1B4ACFC96AA3F356D8A4B47D7DFD55E57191BD5020`);
the original package, reviewed manifest and historical evidence remain intact.

Optional `-BrevoWebhookAccount` validates the existing Python ASCII account
contract and forwards `--brevo-webhook-account=<account>` as one literal argument.
Omission preserves webhook OFF; explicit empty/invalid metadata fails through
existing sanitized first-failure reporting before process/listener operations.
Management and confirmation remain ON as in the accepted launcher. Recognized
webhook options require management and fresh exact argv agreement. Reporting
distinguishes REQUESTED from verified startup ON; listener evidence carries the
actual webhook configuration flag. No Python/Flask implementation change occurs.
TESTING enforcement, protected loader, runtime/interpreter/TLS pins, foreground
PowerShell pipeline, complete simultaneous logging, native status capture,
clipboard read-back and OAF alerts are retained.

Focused final validation: **74 PowerShell assertions and seven existing Python
parser cases PASS**, native exits zero; only pure AST-extracted functions/parser
definitions execute. Failed preparation/fixture attempts and complete logs remain
preserved. `DEPENDENCIES.json`, `validation-results.json`, `source-delta.diff` and
`preservation-result.json` identify dependencies, checks and preservation.
Exact future invocation is saved and syntax/identity checked in
`FUTURE-HTTPS-COMMAND.txt` beside the source; do not reconstruct it from history.

SOURCE/OFFLINE ONLY. Existing HTTPS service untouched; no launcher invocation,
credential/TLS-secret read, webhook activation, guard/tunnel, provider/email/event,
subscriber/database/migration, scheduled task, GraManna or Git write occurred.
Accepted Steps 1-4, migration 0006, listener/TLS and eight guard tests are reused.
One next action: securely provision the separate TESTING Generic Credential at
exact target `OAF Website/testing/Brevo/UnsubscribeWebhook` under the owner account,
with chosen matching account metadata and a fresh protected bearer; keep its value
out of commands, environment, clipboard and logs. Provisioning does not activate
webhooks; the latest owner-supplied finding that this credential is absent is
accepted without repeating preflight. No additional approval gate is introduced.

## Step 5 confirmation-only one-use handoff: source/offline (2026-10-23)

Authoritative prepared source: `.pytest_cache/step5-confirmation-once-v1-20261023/`.
`Invoke-ConfirmationOnce.ps1 -Action OwnerIssue` explicitly expresses the existing
owner approval as a new local confirmation-only record at the actual issuance time;
`-Action Execute` consumes its completed bytes permanently before the unchanged
sealed `execute-bound-v1.py` is entered. Both require the exact identities hash in
`FUTURE-EXECUTION-COMMAND.txt`. No Step 3 authority is reused. The fixed namespace
is `instance/step5-confirmation-authority-b143c3389ba54b7d96991f9b23ab2976/`.
Exclusive issuance-start and consumed markers survive partial writes, failure and
interruption; issuance uses the existing fsync/completed-hard-link helpers. No
source/binding/hash alone is issued authority. Same-account local evidence retains
its established trust/durability limits; this is no general authorization service.

The exact accepted binding and sealed source are unchanged. Original confirmation
issuance remains 2026-10-23T20:17:13.754265Z, immutable expiry remains
2026-10-24T20:17:13.754265Z. Only that TESTING recipient/lifecycle/intent/current
consent version and attempt ONE can run. Existing processor selection-before-LIMIT,
claim/final locked scope, consent/suppression, durable attempts/outcomes, shared
wrapper lock, current host isolation, uncertainty and no-blind-retry remain.
Independent read-only outcome observation uses the existing reconciliation helper
without provider/application-key send readiness. Missing outcome evidence grants
no retry. No authority was issued/consumed and no live preflight, DB or provider
operation occurred in this batch. Focused synthetic evidence: 34 Python cases and
26 PowerShell assertions, native harness exits 0; native probes 0/2/130 retained.
The accepted 56-case source evidence is reused, not repeated as a broad campaign.

Deterministic autonomy review: fixed scope, expiry, one-time publication/consumption,
locks, eligibility, uncertainty and reporting rules; no AI/per-subscriber decision,
new queue/table/worker/scheduler/framework or review gate. Owner issuance is the
explicit exceptional boundary for the already-approved operation, not another
approval request. Runtime/helper/source/dependency SHA256 identities and the exact
prepared command are in the package. Only tests and these governing-document
suffixes accompany the new local source; existing runtime/UI/services stay intact.
Next operational action is the saved owner issuance-and-consumption command before
original expiry; it was NOT executed here. After operational Step 5 completes,
perform the requested temporary tunnel/guard shutdown, then the approved signup UI
refinement. Neither later action belongs to this source/offline batch.
## Step 5 safe confirmation authorization supersession — source/offline v1 (2026-10-23)

The owner-approved preparation is `.pytest_cache/step5-authorization-supersession-v1-20261023/`.
Its `FUTURE-PROCEDURE.txt` is the ONE future procedure for this correction. No
operational retirement, issuance or consumption is performed by preparation.
The original package, accepted corrected helper, authority, completion names,
failed invocation, claims and evidence remain unchanged. Existing issuance has
no retirement action; this bounded local adapter is the necessary extension.
It is not a general authorization service or a rebind of the old authorization.

- The original authorization UUID remains `0376f1cb-b3e8-4a75-bb63-ebc4672ce4cf`.
  The old consumer permanently checks and exclusively creates the fixed original
  `single-shot-used.json` before entering the sealed processor. Future exceptional
  `OwnerSupersede` reserves that EXACT slot with terminal SUPERSEDED evidence,
  using the existing exclusive/fsync and completed-hard-link helpers. The original
  authorization and completion bytes are never edited, renamed or deleted.
- Old consumption and retirement compete for one atomic CreateNew slot. If old
  consumption wins, retirement and successor issuance fail. If retirement wins,
  an old reader that already passed its existence check still fails CreateNew.
  A partial marker blocks old execution, and missing/malformed/uncompleted
  retirement evidence blocks new execution. No parallel executable authorities.
- Only after completed, identity-bound terminal retirement can the SAME owner
  action issue ONE distinct confirmation authority in the fixed `supersession-v1`
  child namespace. It binds the original identity/hash, terminal evidence hash,
  exact new source manifest and unchanged original binding/sealed processor.
  Both terminal evidence and successor consumption are checked permanently.
  Owner issuance and exceptional reconciliation remain separate from ordinary
  processing. Hashes establish integrity; the explicit owner action is authority.
- Before retirement and before execution, retain corrected current host isolation,
  the existing shared local lock, exact historical no-child boundary and current
  read-only DB-clock eligibility/pristine attempt-one observation. Backend selection,
  locked claims/submission, deterministic outcomes, suppression and uncertainty
  holds remain unchanged. No prior or uncertain submission may be retried.
- The original intent/lifecycle/recipient, confirmation purpose, attempt ONE,
  issuance `2026-10-23T20:17:13.754265Z` and expiry
  `2026-10-24T20:17:13.754265Z` are immutable. Recheck expiry across publication and
  consumption; the existing backend also uses its current DB clock. A different
  intent, extended deadline, replacement signup or second attempt gains no authority.
- Failure/interruption never deletes, repairs or retries a reservation. Before the
  retirement marker, old authority may remain executable; after it, old authority
  is denied permanently. Completed publication with a lost acknowledgment is
  distinguished read-only using the existing hard-link completion mechanism.
  Any other partial, contradictory or stopped operational run requires bounded
  exceptional reconciliation; no recovery send or reissuance command is supplied.
- Source locks, import/environment policy, privacy, originating failures, exact
  native exits, STARTED/terminal/NOT_RUN evidence, acknowledged outcomes, visible
  sanitized simultaneous logs, verified clipboard and OAF alerts are retained.
  The source/evidence/dependency manifests identify exact bytes and focused results.
  Same-account/local-filesystem durability and trust limits remain those already
  documented; offline tests do not certify live eligibility or power-loss behavior.

Focused validation reuses the accepted 58 preflight assertions and 11 static
checks. New synthetic checks cover only supersession and its affected execution/
reporting boundary. Deterministic autonomy: fixed issuance/retirement/consumption,
expiry, identity, exclusivity and failure rules; no AI or per-message owner decision.
No database/provider/service/scheduler/credential/migration/frontend/Git mutation
belongs to this batch. Preserve both UI improvements; the separately approved
signup paragraph removal still follows Step 5 and tunnel shutdown.

## Step 5 final acceptance and closure (2026-10-25)

**STEP 5 — ACCEPTED / PASS.** Owner-authorized documentation closure only;
accepted operational results are reused without retesting or reconstructing
investigations. This is the single current Step 5 acceptance entry. Historical
entries, owner notes, consumed authority and evidence remain intact. OAF 5P:
SIMPLE. DIRECT. SUFFICIENT. EFFICIENT. SAFE. EXISTING FIRST. NO REINVENTION.

| Accepted pathway | Result and retained evidence |
| --- | --- |
| Website-origin unsubscribe | PASS. `.pytest_cache/step5-withdrawal-verification-20261024T231628Z-57a7b0ed/REPORT.txt`, `result.json`, `database-native-exit.json` and `completion.json`: PostgreSQL snapshot `2026-10-24T23:18:39.860363+00:00`; management-origin withdrawal, revision 0 -> 1, exactly one matching management/unsubscribed audit, selections preserved as consent history, zero active lifecycles, historical records and Foundation complete-record fingerprint preserved; database native exit 0. |
| Brevo-origin unsubscribe | PASS. Genuine Brevo one-click request and authenticated webhook; Brevo acknowledgement HTTP 200 and OAF forwarded callback HTTP 200 accepted by the owner. Final owner-context SELECT-only evidence: `.pytest_cache/step5-final-brevo-withdrawal-selectonly-20261025T233552Z-v1/REPORT-current-97ba1b47-v1.txt`, `result-current-97ba1b47-v1.json`, `check-*.json`, `database-native-exit.json` and `completion.json`. |

Final TESTING PostgreSQL observation: `2026-10-25T23:51:57.939603+00:00`.
Latest CloudCake lifecycle **WITHDRAWN**, source **brevo**, revision **1**;
matching withdrawal audit **1**, durable `provider_block` suppression **1**,
active CloudCake lifecycles **0**. Five historical CloudCake lifecycles and
prior confirmation/provider history are preserved. Foundation complete-record
fingerprint **PASS**. Database native exit **0**; read-only rollback and disposal
completed. No duplicate withdrawal or revision was observed. These are retained
observations at the stated snapshot, not fresh queries by this closure batch.

**Acceptance precision:** `newly_processed_withdrawal` is the accepted inference
from the persisted correlated provider receipt, matching withdrawal audit and
callback timing (callback `2026-10-25T23:35:52Z`; audit/withdrawal
`2026-10-25T23:35:52.542172+00:00`). A shared callback message ID was not retained
for direct transport-to-subscriber attribution. The persisted provider-message
correlation does not establish that stronger transport linkage. Duplicate callback
count is unverified. No replay was performed; replay behavior is **NOT_RUN**.
Comprehensive post-delivery coverage and production readiness are not demonstrated.
Missing historical observations remain missing; accepted repairs are not reopened.

### Diagnostic improvement register — current reconciliation

This suffix reconciles the retained diagnostic/installation records in the existing
governing notes. No separate improvement-register file was located in the available
project records; no owner-authored register or historical report is replaced.

| Work | Current disposition and evidence |
| --- | --- |
| Initial Brevo webhook first-failure diagnostics | **COMPLETED / INSTALLED.** `.pytest_cache/step5-brevo-diagnostics-install-20261025-v1/REPORT.txt` records installed identities, backups, accepted focused validation and startup-integrity checks. Retain original historical rejection visibility limits. |
| End-to-end originating failure retention and parent reporting | **COMPLETED / INSTALLED.** `.pytest_cache/step5-install-end-to-end-failure-diagnostics-20261025/REPORT.txt`, `application-result.json`, `verification-results.json`, `preservation-result.json` and `reporting-completion.json`. The earlier source-lock blocker in `.pytest_cache/end-to-end-failure-diagnostics-20261025/report.txt` is resolved by the accepted installation; that historical report is preserved. |
| Sanitized offending-field diagnostics and dependent NOT_RUN | **COMPLETED / INSTALLED.** `.pytest_cache/step5-webhook-field-install-20261025/REPORT.txt` and its installation/verification evidence. Historical unrecorded field names are not retroactively inferred. |
| Observed Brevo optional metadata compatibility | **COMPLETED / INSTALLED.** `.pytest_cache/step5-observed-brevo-fields-install-20261025-v1/REPORT.txt` and `verification-results.json`; only `link`, `sender_email`, `source`, `uuid` are optional ignored metadata. Existing authentication, correlation, withdrawal, audit, suppression and idempotence remain authoritative; final accepted Brevo withdrawal evidence above closes the operational Step 5 path. |
| Direct transport-to-subscriber diagnostic linkage | **OUTSTANDING visibility improvement; not an acceptance blocker.** Final SELECT-only result explicitly records `temporal_and_persisted_receipt_only_callback_message_id_not_retained`. Any future improvement must reuse existing sanitized correlation/evidence mechanisms during separately scoped ordinary work; no retrospective linkage or new campaign is authorized. |

No other demonstrated Step 5 diagnostic repair remains open in these accepted
records. Comprehensive post-delivery coverage is an unproven scope limit, not a
claim of complete diagnostics or an instruction to repeat tests. Abrupt termination
before evidence persistence or loss of both evidence sinks retains the accepted
durability limits. Continue the existing first-failure contract: UTC, operation,
stage, actual safe cause, expected/observed facts, outcome certainty, correlation
and dependent **NOT_RUN**. No new diagnostic framework, launcher or wrapper.

### Closure boundaries and existing roadmap dependency

Closure batch/evidence: `.pytest_cache/step5-final-closure-20261025T235742Z-v1/`.
Its single `REPORT.txt` is the consolidated owner report; preservation identities,
sanitized live log, terminal transcripts and reporting receipt accompany it.
This batch changes governing documentation only. No application/test/runtime
configuration/database changes, repeated acceptance tests, email, webhook replay,
unsubscribe, service stop/restart or Git delivery occur. TESTING HTTPS, Cloudflare,
forwarding guard and Brevo are left untouched. Git stage/commit/push/reset/clean
remain unauthorized; delivery requires separate owner authorization.

The next numbered roadmap stage is **Step 6**, as referenced by
`.pytest_cache/cloudflare-webhook-guard-v1-20261022/README.md`; its full scope is
not defined by the available current records and is not inferred from the separate
historical Step 6G checkpoints. The established prerequisites are completion of
Step 5, the planned temporary tunnel/guard shutdown, and the remaining queued
signup paragraph refinement. The two already implemented UI improvements stay
completed and preserved. The refinement's order is established by the Step 5
confirmation/supersession notes above and
`.pytest_cache/step5-authorization-supersession-v1-20261023/REPORT.txt`.

**ONE next roadmap action:** owner-authorize the previously planned temporary
Cloudflare tunnel/forwarding-guard shutdown checkpoint. No shutdown is performed
or authorized by this closure; queued UI work and Step 6 are not started.

### Remaining diagnostic improvements — candidate reconciliation (2026-10-25)

Owner scope: finish demonstrated diagnostic gaps before Step 6, existing first,
one connected source batch, offline validation only, no Git stage/commit/push.
Baseline remains `main` at `d6def3033570de893100982329de96d094fb7301`.
The Step 5 acceptance, historical/Foundation preservation, comprehensive failure
reporting, field-name diagnostics and four-field Brevo compatibility remain closed.
Their accepted evidence above is reused; no callback or live acceptance is repeated.

**SOURCE/OFFLINE CANDIDATE; NOT INSTALLED.** The single candidate is
`.pytest_cache/remaining-diagnostics-20261026T004941Z/candidate/`. Both required
runtime sources have normal Windows sharing locks (`IOException`, `0x80070020`).
No replacement or service restart was attempted. Original tracked bytes, HEAD,
index, owner notes, TESTING HTTPS, guard, Cloudflare and Brevo settings remain intact.

The webhook now carries the already-computed keyed `action_digest` as a bounded
`webhook_receipt.receipt_digest`, with environment and a request/evidence reference.
It directly selects the existing audit row, which binds the persisted provider
message and original subscriber lifecycle. No additional table, identity algorithm,
credential, provider request, launcher or framework is added. Identity is attached
only after all existing correlation predicates pass. Rejections before matching
have no fabricated receipt. A matched event with failed processing is `accepted`
with explicit transaction certainty; `processed_withdrawal` and
`idempotent_acknowledgement` are emitted only after the transaction acknowledges
commit. Public HTTP bodies/statuses, matching, uniqueness and mutation order stay
unchanged. The existing logger, append/flush/fsync sink and sanitized fallback
retain outcomes and secondary failures. The original first-failure reference is
preserved through later transaction/reporting errors.

The current improvement register is reconciled here, without a separate register:

| Review category | Disposition and evidence |
| --- | --- |
| Direct transport-to-subscriber linkage | **DEMONSTRATED GAP; FIXED IN CANDIDATE.** Exact keyed audit receipt on accepted/processed/duplicate callbacks; deterministic bracket normalization and no pre-match identity. Installation remains pending. |
| Safe expected/observed rejection facts | **DEMONSTRATED WEBHOOK GAP; FIXED IN CANDIDATE.** Existing webhook predicates now supply condition-specific safe satisfied/failed facts instead of generic operation prose. Installed bounded offending-field facts remain intact. Other reviewed entry points retain accepted evidence. |
| Configuration/credential first-failure specificity | **ALREADY SATISFIED.** Installed native credential/configuration predicate capture, accepted installation/parent evidence and existing connected failure tests retained. No implementation reopened. |
| Dependent NOT_RUN | **DEMONSTRATED WEBHOOK GAP; FIXED IN CANDIDATE.** Early rejection/begin/lock/clock failures distinguish correlation, transaction and mutation not reached. Commit/rollback uncertainty retains `automatic_retry` NOT_RUN. Installed offending-field behavior retained. |
| Cross-boundary failure correlation | **ALREADY SATISFIED** for originating failure references and Python/parent propagation. The distinct webhook receipt gap is covered above. |
| Operational PowerShell/Python consistency | **ALREADY SATISFIED** within accepted installed interfaces. Reused `step5-install-end-to-end-failure-diagnostics-20261025` installation/reporting receipts and `end-to-end-failure-diagnostics-20261025/parent-validation-02.json` (child exit 2 retained by parent exit 0). No wrapper/launcher change. |
| Secondary failure preservation | **ALREADY SATISFIED; CONNECTED EXTENSION VERIFIED.** Original first failure plus rollback, transaction, logger and evidence failures retained; a reporting failure cannot change acknowledged withdrawal or invite replay. |
| First-failure completeness at existing entry points | **ALREADY SATISFIED in reviewed installed paths.** Existing bootstrap, HTTP, processor, scheduler and provider evidence reused. Universal completeness and live verification of the new candidate are **NOT ESTABLISHED**, not invented defects. |

Validation uses the existing website `.venv`, disabled plugin autoload, explicit
33-file `APPROVED_TESTS` inventory and early `-p migration_offline`; all external
access guards remain. Final connected validation: **496 PASS**, native exit 0,
including 18 new receipt/failure cases and strengthened existing rejection checks.
The final full canonical run on exact intended Git bytes: **3,366 PASS, 39 FAIL,
zero errors**, native exit 1. The first
failure is `test_controlled_confirmation.py::test_cli_missing_and_duplicate_scope_are_private_failures`:
the old expected CLI object omits the installed sanitized `first_failure` field.
The initial full run (3,344 PASS, 41 FAIL, 20 ERROR) remains preserved. One bounded
comparison of all its 61 failing/error cases with shorter temporary paths
produced **39 FAIL, 22 PASS, zero errors on BOTH baseline and candidate** (exit 1
each). This resolves the 22 Windows path-length artifacts without source changes.
The remaining baseline failures include outdated diagnostic silence/CLI shape and
0005-head expectations, plus existing safeguard fixture/observation expectations.
They are not new webhook defects; no working behavior or unrelated tests were
altered to make them pass. Candidate-only CRLF-to-LF normalization matched existing
Git storage; the final full run used those exact bytes and the short temporary
path. Its failure set exactly matches the 39 reproduced baseline failures. No
Git objects or index were written. This does not turn the full run into a PASS.

No whole-application 100% command/configuration was found. The existing
`checkpoint6g2/measure.py` and `report_coverage.py` technique was reused with the
installed coverage 7.13.2 tool read-only, all 33 `oaf_website` modules, and branch
measurement. Guarded tests export arcs; a separate metadata-only process reports
them. All-Python-application result: **95.5084% combined**, statements **96.3511%**,
branches **93.1275%**, threshold exit 2. There are 207 missing statements and 138
missing branches; five pre-existing exclusions remain, with none added. The
recorded older 100% claims were explicitly scoped; no whole-application PASS is
claimed. Exact test selection, raw evidence and missing-line detail are retained
in `test-protocol.json`, `full-final.xml`, `failure-reconciliation.json`, `coverage-final.json`
and logs beside the candidate. `CANDIDATE-SHA256.json` and `candidate.patch` identify
the complete intended delta; `validated-final-inputs.json` seals tested executable bytes.

Privacy/autonomy: no address, raw message ID, token, payload value or private URL
is added to application diagnostics. All ordinary authority remains deterministic
and server-owned. No database/provider connection, unsubscribe, email, replay,
credential/permission/configuration change, operational authority issuance,
service action or GraManna write occurred. Abrupt termination before persistence
and loss of both sinks retain the accepted durability limitations. This cannot
retroactively correlate the historical Step 5 callback.

**ONE next action:** install this candidate at the next authorized controlled
shutdown, matching its baseline hashes and using the existing startup-integrity
procedure. No shutdown is authorized here. Before any later Git push, resolve the
baseline validation failures and meet the full canonical zero-failure and 100%
application coverage gates on the exact final Git candidate. Step 6 remains later.


## Step 4 owner closure and approved UI refinements (recorded 2026-10-26)

**STEP 4 CLOSED / PASS.** On October 25, 2026, the owner performed live
Eyes & Clicks using CloudCake's original management link after the subscription
had been withdrawn. The owner reported this browser message:

> This link is unavailable. Use your latest email or request a new link.

The owner observed no editable subscription preferences, no Save control, no
reactivation capability and no disclosure of protected preferences, and accepted
Step 4 CLOSED / PASS. This is the accepted owner browser observation, recorded
here without repeating the live exercise. It does not independently establish
backend timestamps, database mutations or every backend enforcement condition.
Earlier accepted source/test evidence separately covers expiration, revocation,
lifecycle binding, session deadlines and stale authority. That accepted evidence
is reused; those properties are not newly inferred from the screenshot.

### One approved presentation correction batch

Compared the current five frontend files with
`.pytest_cache/global-action-feedback-16abb8e4d8f44c9d8ab4d49368e866e7/proposed-changes.patch`
and its candidate files before editing. The shared action-feedback CSS, existing
status/alert elements, status categories, icons, colors and live announcements
were already installed. Preserved the newer management withdrawal-only,
authority-rejection, receipt/acknowledgment, conditional legacy-message and
recovery behavior instead of overwriting it with the historical candidate.

- Both active-management instructions are hidden initially and when authorized
  editable preferences are unavailable: "Choose the GraManna announcements you
  want to receive." and "Opening a link makes no changes." They remain visible
  for valid authorized active preference management.
- The existing verified withdrawal/acknowledgment path retains exactly:
  "You have unsubscribed from all notifications for this subscription." Invalid
  or unauthenticated links retain generic unavailable feedback; legacy
  conditional acknowledgments do not assert subscriber withdrawal status.
  Existing recovery eligibility, visibility and request behavior are preserved.
- Reused the global success checkmark/subtle green, error warning/subtle red,
  neutral information icon and processing hourglass/dashed styling. Corrected
  the empty processing region's leftover dashed border with zero border width;
  the existing empty live region remains in the DOM.
- Removed the explanatory paragraph immediately below "Choose your updates",
  its obsolete description references and its JavaScript text update. Kept
  one existing action-feedback area directly beneath Subscribe. Announcement
  choices, consent, labels, controls and confirmation-request behavior remain.

### Focused validation, preservation and limits

Evidence: `.pytest_cache/step4-ui-closure-20261026T161838Z-2669eded/`.
Reused the existing prepared Playwright audit/interception procedure against
installed files with the approved sibling interpreter, read-only packages and
Chromium. One connected focused validation covers **60 PASS checks**, **30 each
at 1280 x 844 and 390 x 844**, native exit **0**. Invalid/malformed/revoked-link
privacy, authorized editing/save, stale authority, verified withdrawal and
acknowledgment without a second save, conditional legacy responses, recovery,
signup/confirmation ON and OFF, processing and errors pass. Keyboard/focus,
busy controls, live semantics, valid ARIA references, forced colors, wrapping
and page/message overflow pass. Text contrast remains success 10.03:1,
information/processing 15.05:1 and error 6.81:1. Zero page errors or unexpected
requests. Full-page desktop/mobile captures were visually reviewed.

The initial focused browser iteration also exited 0; its visual review exposed
the empty processing-border artifact at `styles.css:.action-message:empty`.
That actual expected/observed mismatch is preserved in `stages.jsonl`; the final
connected iteration verifies its correction. Earlier captures with sticky-header
overlays remain historical; final full-page captures avoid that capture artifact.
No canonical pytest or GitHub Linux CI campaign was repeated.

Only five frontend files and these two governing documents change. Complete
original documentation bytes remain prefixes; prior owner changes and historical
evidence are retained. HEAD/index, backend, routes, consent/authority/lifecycle
contracts, database, email, webhook and API source remain unchanged. All browser
API responses were intercepted and synthetic; these checks establish frontend
behavior, not new backend or deployment certification. No manual screen-reader
certification is claimed.

The owner reports all four terminals were closed overnight. This batch did not
require or restart TESTING HTTPS, Cloudflare or the forwarding guard. Brevo
outbound processing was not enabled or invoked. No email, provider request,
credential access, migration, operational database action, GraManna repository
change or Git stage/commit/push occurred. Existing sanitized logging,
first-failure evidence, clipboard read-back and OAF alert reporting are retained
with the consolidated report and reporting receipt.

The queued signup refinement is complete; earlier pending-refinement statements
remain historical. The separately prepared remaining-diagnostics candidate and
its recorded canonical/coverage limitations are outside this UI batch and retain
their existing disposition. Step 6 scope is not invented or started.

**ONE next action:** resume the existing remaining-diagnostics installation
checkpoint within its separate scope.


## Routine DEVELOPMENT website viewing (2026-10-26)

In the OAF Website VS Code workspace, use **Terminal > Run Task... >
OAF Website: Start DEVELOPMENT** (or **Ctrl+Shift+P > Tasks: Run Task**,
then select that task). It runs the existing launcher in a visible dedicated
PowerShell terminal and opens Chrome at **http://127.0.0.1:5055/gramanna.html**.
Direct equivalent from the repository root in Windows PowerShell 5.1:

```powershell
.\ops\Start-DevelopmentWebsite.ps1
```

Use the existing launcher without `-EnableIntegrations`. Ordinary HTML, CSS and
JavaScript edits need no TESTING HTTPS source-hash reconciliation; refresh the
local page after saving. The task leaves an occupied port/existing server alone.
Keep its terminal open while viewing. Leave the running TESTING HTTPS server,
its launcher/hash safeguards, Cloudflare and forwarding guard untouched.

DEVELOPMENT binds only to 127.0.0.1:5055 and requires the existing
`oaf_website_dev` / `oaf_website_app` identity and DEVELOPMENT Credential Manager
reference. Conflicting environment/database settings fail closed; startup checks
use read-only queries. Integrations, confirmation and management are disabled by
default; webhook processing fails closed without its configuration. The existing
recognition key, cookies, CSRF/origin checks, sanitized simultaneous log,
first-failure diagnostics, verified clipboard and OAF alert remain in use.

For visual inspection, browse without submitting Contact, subscription or State
Request forms, and without using live email links. Contact SMTP is loaded only
on submission; it is not globally disabled by DEVELOPMENT. This viewing procedure
does not authorize email delivery, provider processing, operational writes or
migrations. Existing development form behavior is preserved.


## Notification Management V2 Step 6 - DEVELOPMENT Migration 0006 closure (2026-10-26)

**Step 6 - CLOSED / PASS - October 26, 2026.** Owner-authorized completion
of Notification Management V2 Step 6 - DEVELOPMENT Migration 0006, recorded
from accepted evidence without repeating validation or live operations.
5P: SIMPLE. DIRECT. SUFFICIENT. EFFICIENT. SAFE.

Migration `0006_notification_management` is applied and verified in both
**TESTING and DEVELOPMENT**. This current closure updates the earlier pending
Step 6 direction; every historical entry and owner-authored note is preserved.

Accepted artifact and focused validation evidence:

- Artifact correction: **PASS**; exactly two migration integrity files corrected.
- Focused validation: **209 tests PASS**, accepted prior evidence; not rerun here.
- Corrected artifact approval: `32144895-ddad-4083-bece-6a2287a0f719`.
- Manifest SHA256:
  `dc44f7d95e9f63a498bbb004472de710bcc8d445a0f32280140cf9e53134e212`.
- Revision 0006 SHA256:
  `12c5721415d543cced10edf1c54028bbca675bff4db7e8cb8b36994543643801`.

Accepted environment outcomes:

- **TESTING - PASS**, run `3a1e54fb-4bf0-494e-9c0c-f4066eb7ae07`:
  outcome `verified_noop`; authoritative identity/catalog checks **PASS**;
  no database mutation; rollback, audit and cleanup confirmed.
- **DEVELOPMENT - PASS**, transition
  `0005_confirmation_outbox` -> `0006_notification_management`;
  run `038d48d8-c5e6-42fd-9c4b-5060451385af`;
  authorization reference `eef90020-e111-459b-a09d-ce3997f211b7`;
  outcome `applied_and_verified`; database commit confirmed; postcommit
  validation, audit publication, lock release and cleanup **PASS**;
  native exit **0**; first failure **NONE**.

All existing historical audit records, claims, migration evidence, project
files, Git index and owner changes were preserved in the accepted work.
This documentation-only closure appends to `docs/WEBSITE_PLAN.md` and
`docs/WORKFLOW.md`, preserving all prior document bytes and existing Git state.
No source, test, configuration or migration edits, credential/live database
access, authorization issuance/consumption, provider/email/service changes,
GraManna modification or Git staging/commit/push/reset/clean/stash occur here.
No production deployment or new whole-suite coverage certification is claimed.
`Invoke-OAFCodex` remains the sole final clipboard delivery, verified read-back
and visual-alert mechanism; no unobserved final delivery is asserted and no
reporting machinery is changed.

**ONE next existing roadmap milestone: Step 7 - Final Verification / Git
Checkpoint - NOT STARTED.** This closure does not start that milestone.


## Notification Management V2 Step 7 - final verification and Git readiness (2026-10-26)

**VERIFICATION PASS / GIT READY; Step 7 owner closure and Git delivery pending.**
One focused final-verification batch, confined to OAF Website. Steps 1-6 remain
CLOSED / PASS. Earlier staged-diagnostics, source-lock and canonical/coverage
failure descriptions remain historical; accepted installation and subsequent
committed repairs are present in current HEAD and are not reopened.

Candidate and preservation:

- Repository: `C:/Users/ovisa/Documents/OAF_App/Development/OAF Website`;
  branch `main`, HEAD `3f3099df9582065213941c431527fee975b648ab`.
  Local tracking reference `origin/main` has the same HEAD; no fetch/push.
- Nine pre-existing unstaged files were inventoried and backed up. All seven
  non-document changes remain byte-for-byte intact; both documents retain their
  complete original bytes as prefixes. This batch appends only these two records.
  No source, test, configuration, migration or owner-note correction was needed.
- The 138 tracked inputs (136 UTF-8 text files and two exact binary images) were
  copied into an ignored snapshot. Existing CRLF-to-LF candidate normalization
  was checked against read-only `git hash-object --path ... --stdin` for every
  file, without `-w`, staging, object writes or index changes. The snapshot uses
  the existing website environment and installed shared coverage package read-only.
- `candidate-before.json` seals the tested inputs; `candidate-final.json` identifies
  the final documentation-inclusive Git candidate and proves unchanged executable,
  test, asset and configuration bytes. Final document changes are append-only;
  the tests do not consume their content. Final UTF-8, Git whitespace/conflict and
  preservation checks apply to that complete candidate. HEAD/index stay unchanged.

Accepted evidence reused without repeating its historical operations:

- DEVELOPMENT `038d48d8-c5e6-42fd-9c4b-5060451385af`, `applied_and_verified`;
  TESTING `3a1e54fb-4bf0-494e-9c0c-f4066eb7ae07`, `verified_noop`.
- Corrected approval `32144895-ddad-4083-bece-6a2287a0f719`; manifest
  `dc44f7d95e9f63a498bbb004472de710bcc8d445a0f32280140cf9e53134e212`;
  revision 0006 `12c5721415d543cced10edf1c54028bbca675bff4db7e8cb8b36994543643801`.
  Current normalized bytes match both accepted hashes.
- Focused migration integrity **209 PASS**, installed-source browser **60 PASS**,
  owner Eyes & Clicks **PASS**, accepted repair/installation evidence and prior
  GitHub Linux CI **GREEN**. The older Linux result is historical, not proof of
  the current uncommitted candidate. No separate focused/browser/live rerun.

Required final gates actually executed:

- Reused unchanged `ops/ci_pytest.py` and `.github/workflows/linux-tests.yml`:
  `shard --shard 0`, `shard --shard 1`, then `combine`, on Git-equivalent bytes.
  Dedicated website Python 3.11, `-u -B`, explicit canonical inventory, early
  `-p migration_offline`, disabled autoload, empty pytest options/plugins, explicit
  TESTING and unique short synthetic temporary roots retain existing safeguards.
- Shard 0: **1,796 PASS**, 192.11 seconds, exit 0. Shard 1: **1,796 PASS**,
  187.40 seconds, exit 0. Each reports zero unexpected external-access attempts.
  Each shard's 1,796 deselections are the intentional disjoint partition.
- Existing combiner: **3,592 tests exactly once**, zero failures/errors/skips/xfails;
  all 33 application modules, **5,671/5,671 statements and 2,004/2,004 branches,
  exactly 100%**; zero missing statements/branches; exit 0. No exclusions added.
  New GitHub execution is not claimed; these are current local candidate results.

One proportional security/autonomy review **PASS**: signed purpose/environment/
lifecycle/revision/expiry authority, CSRF/origin/HTTPS, authoritative consent,
verification, atomic idempotence, append-only audit, exact callback correlation,
suppression, quota/recovery and uncertain-commit rules remain intact. Ordinary
operations have deterministic server decisions and no AI dependency.

Actual first stop, retained with its resolution: candidate-seal gate started
`2026-10-26T19:51:38.8343524Z`; `UnicodeDecodeError`, native exit 1, because the
verification setup tried to decode a PNG as UTF-8. Expected: strict UTF-8 for text
and exact binary copies. Observed: PNG signature rejected by a blanket decoder.
The partial ignored snapshot is retained. No application defect or external side
effect occurred. Tests and coverage were NOT_RUN at that stop; after the single
setup correction, the seal and every required final gate passed. No test failure
or remaining dependent NOT_RUN gate blocks readiness. See `first-failure.json`.

Evidence: `.pytest_cache/s7-20261026T195026Z-f4ccc056/` contains the sealed inputs,
owner backups, security/evidence review, simultaneous `execution.log`, both shard
logs and `coverage-combine.log`; snapshot `.pytest_cache/ci/` retains manifests,
coverage arcs and complete coverage report. `verification-final.json` records
final preservation and Git checks. Existing evidence is never overwritten.

No database/credential access, migration/authority issuance, provider/email/Brevo
request, service restart/disruption, scheduler change, GraManna modification or
Git stage/commit/push/reset/clean/stash occurs. Existing `Invoke-OAFCodex` remains
the sole final clipboard/read-back/visual-alert mechanism, unchanged. No interim
clipboard write, completion alert or unobserved final delivery is asserted.

**ONE next action:** owner decision on the separate final Git delivery.
Step 7 remains open for that decision; no Git delivery or closure is declared.


## Notification Management V2 Step 7 - final closure and Git delivery (2026-10-26)

**Step 7 - CLOSED / PASS - October 26, 2026.** Steps 1-6 remain CLOSED / PASS.
The owner accepts final verification and explicitly authorizes the accepted
candidate plus these two append-only closure records for commit and push.
This entry supersedes the earlier pending owner-decision wording while retaining
all prior document content and owner notes.

Accepted baseline: `main`, HEAD `3f3099df9582065213941c431527fee975b648ab`;
Git-equivalent candidate tree `7e1a430b403d7139f22497d20f98de5053308ec2`;
candidate SHA256
`2c3727a1086d07ceeacd0d07f9d6bd5c7868e07c7ed47fd5224d2ea5b1f98708`.
Evidence: `.pytest_cache/s7-20261026T195026Z-f4ccc056/verification-final.json`.
Reuse **3,592 tests PASS**, **5,671/5,671 statements**, **2,004/2,004 branches**,
both shards/combiner exit 0, UTF-8/Git-equivalence and security/autonomy PASS.
The earlier setup decoder failure and its accepted resolution remain historical.
Only closure documentation is newly added; every non-document input is unchanged.
No repeat test campaign is required for this documentation delta.

The approved inventory remains nine files: `assets/notification-management.js`,
`assets/notifications.js`, `docs/WEBSITE_PLAN.md`, `docs/WORKFLOW.md`,
`gramanna.html`, `manage-notifications.html`, `migrations/manifest.json`,
`oaf_website/migration_validation.py` and `styles.css`. Preserve all accepted owner
work, verify the document prefixes, validate the exact Git-equivalent staged
candidate and review its complete diff for content, privacy, whitespace and scope.
Commit with `Close Notification Management V2 Step 7`, then push `main` to the
existing authorized `origin` without force or history rewrite. Record the actual
commit SHA, tree SHA, push result and native exits in the final delivery report.

No migration, database operation, provider/email request, service change or
GraManna repository edit is included. GitHub Actions is checked independently
by the owner; do not query, poll, wait for or monitor CI. Existing visible logging
and unchanged `Invoke-OAFCodex` final clipboard/read-back/visual alert remain in
use, with one consolidated report and no interim delivery. Exit immediately
after successful push verification and reporting.

5P: SIMPLE. DIRECT. SUFFICIENT. EFFICIENT. SAFE.


## Work Unit 1 - OAF mobile release integration source (2026-10-26)

OAF implementation and focused offline validation are complete. Operational
activation remains OFF. This entry extends the earlier bounded release handoff
contract; historical evidence and revision 0001--0006 source remain intact.

The existing authenticated backend integration now supports
`POST /api/integrations/v1/release-events`. It uses the existing HTTPS origin,
backend-only headers, strict bounded JSON, rate limit, environment validation,
constant-time bearer comparison and sanitized first-failure reporting. The optional
`IntegrationConfig.release_credential` must be a separate protected 32-byte
credential encoded as lowercase hex, distinct from signup, reporting and the
persistent recognition key. Existing signup/reporting credentials cannot approve
releases. No credentials are provisioned or read by the intake. Missing release
credential or persistence keeps the route disabled.

The explicit application factory flag `releases_enabled=True` injects release
persistence using the same engine, protected key and environment. It requires
`management_enabled=True` for current preference grant/cutoff controls. Neither
startup nor intake constructs a provider adapter, sends or launches processing.
All default arguments remain OFF; no operational configuration was changed.

Wire approval contract:

- Initial approval takes exactly `event_id`, `source_approval_id`, `environment`,
  `platform`, `release_id`, `release_url`, `approved_at`, `audience_cutoff`, and
  `content_version`. Environment is explicit; platform is `android` or `ios`;
  content version is exactly `mobile-launch-v1`.
- Event/approval identities accept canonical lowercase UUIDs or their lowercase
  32-hex spelling at the authenticated boundary; both normalize to the same
  canonical durable UUID. The sender must reuse its original event and approval
  identities, timestamps, cutoff and payload on retries. OAF generates no new event
  identity and accepts no caller-selected recipients, content or email copy.
- Android `release_id` is its case-sensitive dotted package identity and must
  exactly match the ID in `https://play.google.com/store/apps/details?id=<id>`.
  Apple `release_id` is its numeric app ID and must exactly match an App Store URL
  of the form `https://apps.apple.com/[country/]app/[slug/]id<id>`. Country is two
  lowercase letters; an optional slug uses lowercase letters, digits and hyphens.
  No userinfo, port, query, fragment, lookalike host, redirect or arbitrary URL is
  accepted. These checks validate references; the authenticated official approval
  source retains responsibility for listing ownership/provenance. No store lookup
  occurs. Native GraManna release record identity must not be substituted for the
  package/app identity in `release_id`.
- Corrections/withdrawals add exactly `action` (`correct` or `withdraw`) and
  `previous_approval_id`. Keep the original `event_id`, platform and audience
  cutoff, use a new source approval UUID and a strictly later nonfuture approval
  timestamp, and reference the current approval UUID. Submit the approved current
  store reference even on withdrawal. Duplicate identical approvals acknowledge
  idempotently; identity/payload conflicts and stale/forked authority return 409.
  The original approved event and cutoff remain immutable. Withdrawal is terminal;
  later initial-event retries cannot reactivate it.
- HTTP 200 acknowledges durable acceptance, including a duplicate. A fixed 503
  leaves acceptance unconfirmed; retry the exact same identity and payload. No
  provider submission occurs in this request. Authentication/transport/field
  rejections retain the existing fixed responses and safe diagnostics.

One additive `0007_release_approvals` table is necessary to retain official
correction/withdrawal history without rewriting original events or widening their
runtime UPDATE grants. Runtime receives SELECT/INSERT only on this new table;
there is no UPDATE/DELETE, broad grant or new role. The existing manifest, exact
revision-shape validator, catalog/ACL/dependency checks and audit revision allowlist
include the successor. Its artifact status remains `pending_independent_review`.
Only exact 0006 -> 0007 or a separately authorized exact 0007 no-op is supported.
No migration is executed. Existing independent artifact approval, single-use
operational authorization and TESTING-before-DEVELOPMENT gates still apply;
previous approvals cannot authorize these changed artifacts.

The existing `confirmation_processor` and `confirmation_schedule` accept the
additional default-off `--enable-releases` flag, requiring `--enable-management`.
The same finite invocation, engine identity checks, local overlap lock, scheduler
name, logs and disabled task definition are reused. With releases enabled, each
invocation allows 10 confirmation submissions and 5 for each of at most two mobile
launch events; the existing total maximum remains 20. Platform slots prevent a
confirmation backlog or one mobile platform from consuming the other's budget.
Persistence selects original received/ready/attention events after restart.
Existing subscriber consent, verification, preference-grant cutoff, resubscription,
mailbox suppression, claim, lease, retry and attempt-history rules still apply.
TESTING remains restricted to its one explicitly approved recipient in selection,
claim, submission and the Brevo adapter; exceptional one-intent scopes cannot
silently include releases. Production processing remains deferred by the existing
runtime policy.

The final locked submission boundary rereads current official approval and renders
its current URL. A correction before that boundary changes only future unsent
messages. Withdrawal atomically suppresses pending, failed and claimed work;
completed attempts, acknowledged outcomes and submitting/uncertain work retain
original evidence. Already committed submission authority cannot be recalled.
Lease recovery preserves uncertainty and never treats missing provider evidence as
permission to resend. The single original official approval therefore drives
persistence -> recurring existing processing -> eligibility -> ReleaseDispatcher
-> existing Brevo adapter without a second Send action or routine AI involvement,
once separately authorized operational prerequisites are in place.

Focused evidence is retained under
`.pytest_cache/wu1-resume-20261026T213359Z-4b74332a/`. The main guarded run passed
1,292 cases; targeted follow-ups passed 12, 13, 15 and 2 cases (including intentional
rechecks). Every run reported zero unexpected external-access attempts. Coverage
of new/changed application statements and decision branches, plus the new revision,
is 100%: 266 statements and 176 branches, with no exclusions or lowered thresholds.
Unchanged code retains its accepted historical validation. Only the prior catalog
snapshots needed for the materially extended revision dispatch were rerun; no full
canonical, browser or live migration campaign occurred. The proportionate security
and deterministic-autonomy review passed. Complete logs, arcs, scoped coverage,
first-failure details and preservation evidence are retained in that directory.

The first resumed source write succeeded. Two initial synthetic-fixture mistakes
and a Windows path spelling in the metadata-only coverage reporter were corrected;
the original failed logs are retained and all required final gates passed. No live
credentials/database, provider requests, mail, server/process changes, task
registration/activation, production configuration, GraManna edits or Git delivery
occurred. `Invoke-OAFCodex` remains the only final clipboard/read-back/visual-alert
mechanism and is unchanged; no interim delivery or alert was invoked.

The remaining separately authorized GraManna operation must connect its existing
official administrator approval/correction/withdrawal governance to this strict
OAF contract, preserving original stable IDs/cutoff and automatically retrying
unconfirmed delivery. It must map native release record identity to the explicit
package/app reference, without adding routine administrator or AI involvement.
No cross-repository inspection was repeated here. Live migration/activation and
end-to-end provider certification remain later operational gates.

ONE next action: implement the GraManna approval-to-OAF handoff in the separately
authorized GraManna operation.

## WU1 - TESTING Release credential configuration resumed (2026-10-26)

Credential configuration is complete; provisioning and operational activation
remain OFF. The interrupted credential attempt recorded inspection only. Its
24 saved baseline hashes matched at recovery; earlier release implementation,
validation and accepted migration evidence are retained without rerunning them.

The existing protected integration loader now also exposes
`oaf_website.local_development.load_testing_integration_config()`. It requires
`OAF_ENV=testing`, uses only `config/local/integrations.testing.toml`, and injects
the existing `IntegrationConfig.release_credential`. This ignored nonsecret file
contains exactly:

```toml
[testing]
client_id = "gramanna"
release_credential_service = "OAF Website/testing/Integrations/Release"
release_credential_account = "gramanna"
```

The existing pinned WinVaultKeyring exact-target loader reads the separate
TESTING Submission, Reporting and Release targets, with Generic Type 1 and
Persist 2 metadata. Release is required and must be exactly 64 lowercase hex
characters, separate from Submission/Reporting and the recognition key. No
DEVELOPMENT, production, compound-target, account or backend fallback is allowed.
Brevo, webhook, database and recognition credential mechanisms are unchanged.
Loading configuration alone never enables release intake or processing. Existing
application activation flags and provider/email operations remain OFF.

ONE owner provisioning procedure, from the OAF Website root in Windows PowerShell:

```powershell
& .\ops\Set-DevelopmentIntegrationCredentials.ps1 -Operation ProvisionTestingRelease
```

This new explicit operation reuses the existing native credential API, UTF-16LE
codec, random generator and operator lock. It creates only the exact TESTING
Release entry for `gramanna`, verifies target/account/type/persistence/format and
read-back, and never overwrites an existing record. Matching existing records are
verified without replacement. Conflicts or uncertain writes stop for owner
reconciliation, with sanitized UTC/predicate/side-effect evidence. A unique local
transcript is retained under `.pytest_cache/testing-release-provision-*/`.
It does not activate features, export a secret, start services or contact GraManna.
GraManna continues to consume the corresponding environment-specific Release
credential through its existing contract; no GraManna source change is required
by this OAF configuration, and its runtime was not inspected or exercised here.

Focused guarded validation passed 108 Python cases and 138 PowerShell cases.
New/materially changed application logic covered 21/21 statements and 8/8 branches
(100% each, no exclusions), with zero unexpected external-access attempts. The
PowerShell harness loads AST function definitions only and replaces native
credential APIs and operational RNG with hard denials before compilation.
A fixture closure-scope/output-capture failure was corrected; original failed
logs remain in the evidence directory. The final procedure SHA256 and exact
preservation/security/autonomy findings are in the consolidated report under
`.pytest_cache/wu1-credentials-resume-20261027T023403Z/`.

No live credential read/generation/provisioning, database connection/migration,
release submission, provider/email request, service/scheduler change, GraManna
edit or Git delivery occurred. Existing `Invoke-OAFCodex` is unchanged and remains
the sole final clipboard/read-back/visual-alert mechanism; no interim delivery or
alert was invoked. The owner provisioning command above is the one next action.

## WU1 - DEVELOPMENT Android/iOS Release integration configuration (2026-10-26)

Implementation and focused offline validation PASS; real provisioning and all
activation/sending remain OFF. Accepted OAF/GraManna source and migration results
were reused; no accepted migration or broad validation campaign was repeated.

The existing ignored `config/local/integrations.toml` now binds DEVELOPMENT
Release to `OAF Website/development/Integrations/Release`, account `gramanna`.
The existing protected integration loader accepts this exact nonsecret binding,
loads the separate third permission with the pinned exact-target Windows backend,
and rejects partial/mismatched bindings or missing Release credentials. Existing
client-only Submission/Reporting configuration remains compatible. Generic Type
1, Persist 2, strict 64-character lowercase hexadecimal format and existing
permission/recognition separation remain enforced. Configuration alone does not
activate release intake or processing.

`ops/Set-DevelopmentIntegrationCredentials.ps1` adds only the explicit
`ProvisionDevelopmentRelease` operation, reusing the existing Release provisioner,
native credential API, encoding, generator and operator lock. The shared TESTING
operation retains its environment-specific behavior. The one owner procedure and
confirmed GraManna DEVELOPMENT interface are recorded in
`docs/DEVELOPMENT_CREDENTIAL_HANDOFF.md`. No GraManna source change is needed.

Focused validation passed 53 Python cases and 51 PowerShell cases. New/materially
changed application logic covered 11/11 statements and 8/8 branch outcomes (100%
each, no exclusions). Existing early guards recorded zero unexpected external
access. The AST-based PowerShell harness disabled native credential APIs and
operational RNG before compilation, used synthetic stores/secrets, and exercised
the actual owner parameter/dispatch/transcript text with operational leaves
replaced. Both DEVELOPMENT and the directly affected TESTING dispatch dependency
finalized their isolated transcripts. Default-OFF, exact target/account/type/
persistence/format, redaction, mismatch rejection, readback, no replacement,
cross-environment isolation and client-only parser compatibility passed.

Evidence: `.pytest_cache/wu1-development-release-20261027T031443Z-4ce848d1/`.
No validation failure occurred. Initial historical-evidence directory discovery
encountered pre-existing unrelated ACL denials (OS error 5); the required named
accepted evidence was readable. No historical evidence or ACL was altered.

No real credential read/generation/provisioning/replacement, database access or
migration, provider/email request, mobile approval, service start/stop/restart,
scheduled-task change, GraManna write or Git stage/commit/push/reset/clean/stash
occurred. The excluded legacy-withdrawal correction remains untouched. Existing
`Invoke-OAFCodex` remains the sole final clipboard/read-back/visual-alert delivery
mechanism; no interim clipboard report or completion alert was issued. The one
next owner action is the documented DEVELOPMENT Release provisioning command.


## WU1 - Step 3 final completion and delivery readiness (2026-10-26)

**STEP 3 READINESS PASS; Git delivery and operational activation pending.**
This append-only reconciliation supersedes the earlier pending WU1 handoff,
migration and DEVELOPMENT Release provisioning directions. Historical entries,
owner notes and accepted evidence remain intact. 5P: SIMPLE. DIRECT. SUFFICIENT.
EFFICIENT. SAFE.

Accepted implementation/operational facts:

- OAF authenticated Android/iOS intake, durable processing and existing scheduler
  integration: SOURCE/OFFLINE PASS. GraManna approval-to-OAF durable handoff:
  SOURCE/OFFLINE PASS. Reuse the OAF source evidence in
  `.pytest_cache/wu1-resume-20261026T213359Z-4b74332a/` and GraManna's existing
  `logs/mobile_handoff_wu1_20261026/`; no new implementation or independent
  certification is asserted.
- OAF `0007_release_approvals`: TESTING and DEVELOPMENT
  **APPLIED_AND_VERIFIED**, confirmed commit, postcommit validation and cleanup.
  Accepted TESTING run `abe723ea-654f-4ade-9ee3-af2753447add`, receipt
  `.pytest_cache/wu1-testing-0007-v1/owner-20261026T233412Z-57aef837cb12450bbf0ea411ed7b4147-completion.json`;
  DEVELOPMENT run `77d854b3-683b-4d7f-85f8-d6c5f2f118f2`, receipt
  `.pytest_cache/wu1-development-0007-v1/owner-20261026T234121Z-681224e3bc23405b8b56b1789ff1c20f-completion.json`.
- GraManna DEVELOPMENT `afmobout01`: APPLIED AND VERIFIED, carried forward from
  the owner's accepted Step 3 baseline; no live database recheck.
- DEVELOPMENT Release credential: PROVISIONED AND VERIFIED. Accepted sanitized
  transcript:
  `.pytest_cache/development-release-provision-20261027T032650Z-f713faa0ac0d4116bacf6d597e3a399d/execution.log`.
  No credential value is read or reproduced here.

Autonomy acceptance reuses
`.pytest_cache/wu1-connected-20261027T033228Z-2573aadb/consolidated-report.txt`
and its `validation-summary.json`, `connected-run-4.log`, `oaf-worker.log`
and `evidence-manifest.json`: nine requested areas across five connected
synthetic scenarios and five guarded worker checks PASS; all child exits 0,
zero unexpected external access. One official Android or iOS approval durably
creates the original handoff in its approval transaction. Existing scheduled
processing retries that original identity/payload, OAF durably accepts it,
selects eligible subscribers and processes bounded batches. The existing OAF
invocation reserves 10 confirmations and up to 5 submissions for each platform,
maximum 20 total. There is no separate administrator Send action or AI runtime
dependency. Consent, verification, preferences/cutoff, suppression, deduplication,
correction/withdrawal, retry, restart/lease recovery and uncertainty holds remain
authoritative; uncertain provider outcomes never imply permission to resend.

These are demonstrated synthetic/source results, not live PostgreSQL connected
certification, OS scheduler certification, live provider delivery or activation.
**Notification activation remains OFF.** Genuine deferred live requirements are
the existing environment-specific runtime/origin and credential injection,
official listing ownership/provenance, deployed schema/identity/permissions,
existing scheduler environment/enablement, and separately authorized live
end-to-end/provider validation. Completed migrations and provisioning need no
repeat operation. No new framework, service, monitor, routine administrator
intervention or approval gate is introduced.

The owner's conditional hypothetical legacy-withdrawal/no-prior-handoff finding
is retained, uncorrected and excluded from implementation. The accepted PASS does
not establish coverage or repair of that case.

Readiness baseline: OAF `main`, HEAD and local `origin/main`
`b034c880d003453608b0c8d87e4da5425e0390f6`; empty index; 24 modified tracked
files and two untracked WU1 source files. All 140 candidate files matched the
accepted connected evidence before this documentation-only append. Existing
source, tests, configuration, migrations, assets and owner work are reused
unchanged. Final inventory, hashes, append-only/preservation and Git whitespace
checks are recorded under `.pytest_cache/wu1-step3-20261027T034450Z-f135daed/`.
Existing GitHub canonical requirements remain two disjoint shards, complete test
inventory and exactly 100% combined statement/branch coverage. No historical
CI GREEN is attributed to current uncommitted changes; no new whole-candidate
canonical or hosted CI result is claimed. Unchanged accepted validation is reused.
The actual staged-diff review belongs to the separately authorized Git delivery
checkpoint; no staged state or completed staged review is manufactured here.

GraManna read-only follow-up: append a WU1 reconciliation to
`.notes_cargo_ledger` (existing WU1 completion record) and `CHANGELOG.md`
("Mobile Android/iOS automatic notification handoff"). Record the accepted
migration, provisioning/interface and connected evidence, autonomous contract,
activation OFF, live limits and retained conditional finding. Preserve its
source-only historical statements, owner notes, concurrent Cargo/diagnostic work
and independent readiness/delivery boundary. No GraManna file is changed here.

The proportional security/autonomy review reuses accepted authentication,
environment isolation, transactions, consent, append-only audit, durable outbox,
scheduling, suppression and recovery evidence. No outstanding Step 3 blocker is
identified. No credential/database/provider/service/task operation or Git
stage/commit/push/reset/clean/stash is performed. The existing outer
`Invoke-OAFCodex` alone owns final clipboard delivery, verified read-back and
one visual alert; no interim delivery or unobserved helper result is asserted.

**ONE next action:** obtain separate authorization for the OAF Git delivery
checkpoint, including review of the actual staged candidate. Stop after Step 3.
