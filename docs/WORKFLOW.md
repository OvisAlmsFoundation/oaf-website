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
