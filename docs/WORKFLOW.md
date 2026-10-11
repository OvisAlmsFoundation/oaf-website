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
