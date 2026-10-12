# OAF Website Plan

## 1. Project Foundation

- Project name: OAF Website
- Repository: `oaf-website`
- Purpose: Public website for Ovis Alms Foundation and GraManna.
- Hosting target: Render.
- Site type: Primarily static public website with a separate Flask API for dynamic features.
- Technology: Plain HTML, CSS, and limited JavaScript for public pages; an independent Python 3.11 / Flask backend with SQLAlchemy database integration.
- Repository structure: Separate from the GraManna application repository.
- Development model: May be developed in parallel with GraManna using a separate VS Code window and separate Codex session.
- Python virtual environment: Dedicated website `.venv`, created with `C:\Program Files\Python311\python.exe`, independent of GraManna's virtual environment.

## 2. Initial Website Scope

The first public website will focus on:

- who Ovis Alms Foundation is;
- the Foundation's charitable mission and purpose;
- what GraManna is;
- the general idea behind the GraManna donation and assistance cycle;
- appropriate public contact and organization information;
- privacy, terms, and other appropriate public policy/disclosure pages.

The initial website will keep GraManna explanations general because the application is still being developed and some details may change.

The website should not imply that unfinished GraManna services or Tremendous production fulfillment are already operational.

## 3. Public Truthfulness Rule

- The website must accurately describe Ovis Alms Foundation and GraManna as they actually exist at the time of publication.
- GraManna may be described as being developed or prepared for launch where appropriate.
- The website must not present unfinished app capabilities, unavailable aid delivery, or unapproved Tremendous production fulfillment as already operational.
- Detailed feature-by-feature development status is not required on the public website.

## 4. Tremendous Readiness Purpose

- A live and fully functioning public website is a current prerequisite for Ovis Alms Foundation to seek Tremendous production-account/API reconsideration.
- Tremendous remains the current intended merchant eGift provider for GraManna.
- The website should be a genuine Foundation and program website, not a temporary placeholder created only for provider approval.
- The website does not need to imply that the GraManna application is finished or ready for immediate public use.
- After the website is live, Ovis Alms Foundation can return to Tremendous for production reconsideration.

## 5. Program-Rule and Content Authority

- The public website is an educational and presentation surface, not the authority that creates GraManna business rules.
- Website explanations should derive from authoritative GraManna Program Rules, cargo decisions, and approved user-facing policy sources wherever practical.
- The website should not create a separate conflicting version of GraManna rules.
- If a program rule is unsettled or likely to change, the website should remain general rather than inventing a detailed public rule.
- AI may assist with writing, organization, design, and review, but must not be required as a runtime authority for eligibility, policy, or program decisions.

## 6. Initial GraManna Content Direction

The first website release should emphasize the established charitable concept and donation cycle rather than detailed application functionality.

Initial GraManna explanations should focus on:

- the charitable purpose of GraManna;
- the relationship between Ovis Alms Foundation and the GraManna program;
- the general donor participation concept;
- the general recipient assistance concept;
- the movement from charitable donation to approved assistance;
- the role of gratitude within the overall GraManna concept;
- responsible-use and program safeguards at an appropriate public level.

Detailed social features, tier mechanics, internal workflows, exact thresholds, technical provider behavior, and other evolving application details are not required for the initial public website.

## 7. Relationship to the GraManna Application

- The public Foundation website and the GraManna application are separate projects.
- The website backend and database remain independent of GraManna's backend and database.
- The public website will explain Ovis Alms Foundation and GraManna to general visitors.
- The GraManna application will remain the operational environment for authenticated user functions.
- The existing GraManna application home page does not need to be removed simply because the public website exists.
- The app home page may later be simplified or adjusted so that the public website carries more of the general Foundation and program explanation.
- Future links between the public website and GraManna application should be designed deliberately when the application is ready for public access.

## 8. Development and Repository Model

- The OAF Website has its own local project folder and its own Git repository.
- GitHub repository: `oaf-website`.
- The website repository is separate from the GraManna application repository.
- Website work may proceed in parallel with GraManna development using separate VS Code windows and separate Codex sessions.
- Changes to the website repository must not alter or depend on the GraManna application working tree.
- Website planning documentation belongs under the `docs/` folder.
- Additional planning documents should be created only when the project becomes large enough to justify separating them from `WEBSITE_PLAN.md`.

## 9. Current Technical Direction

- Hosting target: Render.
- Public-page deployment target: Render Static Site; the public-facing website remains primarily static.
- Public-page technology: plain HTML, CSS, and limited JavaScript.
- Dynamic features will be supported by a separate, independent Python 3.11 / Flask API with SQLAlchemy database integration and the Psycopg PostgreSQL driver.
- Backend dependencies are installed only in the website's dedicated `.venv`; the backend and database remain independent of GraManna.
- Local development and database integration testing use PostgreSQL 17.11 at `127.0.0.1:5432`, with separate development and testing databases and application accounts.
- Production-relevant database behavior must be validated against PostgreSQL before launch; deterministic unit tests alone are insufficient.
- Continue using the existing shared Playwright test environment documented in `WORKFLOW.md` for browser tests. Do not install Playwright in the website `.venv`.
- Backend hosting and production database provisioning remain separate from local development readiness and require approval before activating paid resources.

### Secure Database Configuration Foundation

- `oaf_website/database_config.py` requires explicit `OAF_ENV` selection and an application entry point's matching `expected_profile`; there is no default profile or database fallback. Approved profiles are `development`, `testing`, and `production`.
- Development identity is fixed to database `oaf_website_dev` and username `oaf_website_app`. Testing identity is fixed to database `oaf_website_test` and username `oaf_website_test_app`. Both require the exact local host and port above.
- Nonsecret settings will reside in repository-relative, Git-ignored `config/local/database.toml`. `config/database.example.toml` is the shareable template; this foundation creates no actual local configuration or credential files. Passwords and database URLs are prohibited in local settings. Every present section is validated, and the selected section must exist.
- Local credential references are fixed to service `OAF Website/development/PostgreSQL` or `OAF Website/testing/PostgreSQL`, paired with that profile's application username. Only the selected reference is retrieved. The adapter uses Python keyring's exact `keyring.backends.Windows.WinVaultKeyring` class directly, checks availability and the returned account, and performs no backend discovery, plugin selection, or keyring configuration-file loading.
- Unexpected `PYTHON_KEYRING_BACKEND` values and all environment names containing `KEYRING_PROPERTY_` are rejected. Alternate database environment settings (`OAF_*` other than `OAF_ENV`, `PG*`, `DB_*`, `DATABASE_*`, and `SQLALCHEMY_DATABASE_URI`) are rejected rather than merged or silently ignored.
- Passwords are held only in memory in SQLAlchemy `URL` objects using the Psycopg driver. Configuration loading creates no engine or connection, logs nothing, and writes no credentials. Diagnostic representations exclude passwords; errors omit supplied values and underlying provider/parser exception details. Callers must not serialize passwords or render URLs with password hiding disabled in diagnostics.
- Test entry points must use `load_testing_database_config()`, which requires `OAF_ENV=testing` and rejects development/production selection before credential access. Unit tests use temporary fake settings and mocked credential modules, with real keyring, database, and network access blocked.
- `DatabaseConfig.verify_connection_identity(database, username)` is a pure reusable seam for later integration. Future connection setup must pass the server's `current_database()` and `current_user` on every connection, including pooled connections, before application queries. The foundation performs no identity query itself.
- Production is recognized but fails closed before reading local configuration or Windows credentials. Production identities and an independent secret provider require a separately approved deployment design; there is no reuse of local accounts or secret handling.
- Deterministic autonomy review: profile selection, validation, credential lookup, URL construction, and identity decisions use explicit rules. Missing settings, mismatches, unavailable backends, and missing credentials halt startup without fallback or retry against another identity. Tests cover negative paths, redaction, and recovery after explicit correction. Owner-controlled provisioning, account grants, backend installation, and production approval are administrative prerequisites; AI and paid services are not runtime dependencies.
- Real credential provisioning and PostgreSQL integration validation remain future steps. Migration accounts, schema initialization, migrations, API endpoints, and form activation remain deferred.
- Run offline validation with the website interpreter: `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; $env:PYTHONPATH="$PWD;$PWD/tests"; $env:PYTEST_ADDOPTS=""; $env:PYTEST_PLUGINS=""; .venv\Scripts\python.exe -B -m pytest -p migration_offline -q tests/test_migration_config.py tests/test_migration_artifacts.py tests/test_migration_authorization.py tests/test_migration_catalog.py tests/test_migration_runner.py tests/test_migration_provenance.py tests/test_database_config.py`. Do not invoke the real configuration loader during unit-test or import validation.

### PostgreSQL Migration Authority Contract — Checkpoint 4

#### Stage 5 current status: operational adapter source

This entry supersedes the historical Stage 1 implementation/provisioning and unresolved-audit-policy status language below. Stage 4C development and testing migrators are **CLOSED / DELIVERED / PASS** per the owner-provided baseline; no new live verification is performed here. The existing Stage 5 offline implementation baseline passed 685 tests before these adapter changes.

The owner has granted policies A-D: (A) uniquely and exclusively created, sanitized migration JSON evidence under `%LOCALAPPDATA%\OAF Website\BootstrapAudit\MigrationAudit\`, separate from Stage 4C, with flush and file fsync; (B) retention until separately authorized archival/disposal, with no automatic deletion; (C) distinct deliberate owner-issued, environment/operation/revision/start-state/artifact/prerequisite-bound UTC authorizations, unique and single-use, expiring within 24 hours; and (D) fail-closed denial/audit handling, preservation of acknowledged commits, no uncertain retries, permanent claims, deterministic progression after fully verified success or conclusive safe premutation failure, and exceptional owner reconciliation for uncertain outcomes, postcommit audit failures, or incomplete/contradictory evidence. The exact local record/issuer procedure, durability limits, and same-account security boundary are documented in `WORKFLOW.md` under the Stage 5 entry. These policies are approved and must not be reopened as unresolved policy questions.

Five gates remain distinct:

1. **Policy approval: granted** for the four policies above.
2. **Source implementation: this task**, using the existing runner, `OperationalAuthority`/`AuditSink`, manifest checks, transactions, and Alembic controls. Source/offline validation only; no new service, database table, dependency, or bootstrap-helper change.
3. **Independent artifact approval: pending.** The manifest remains `pending_independent_review`. Only hashes of changed framework files and the necessary new authority-module entry are updated. Hash equality is not approval; independent approval must be separately recorded.
4. **Owner-issued execution authorization: pending.** No real record is created during this task. The separate issuer verifies reviewed local evidence and does not issue from the execution runner.
5. **Live migration execution: not authorized.** No credential access, database changes, live upgrade/downgrade, role/schema/grant/HBA/credential changes, staging, commits, or pushes are authorized by this source task.

`oaf_website/migration_authority.py` supplies the concrete file adapter and minimum deliberate issuer. The migration CLI consumes an existing authorization UUID; direct runner calls and Alembic enforce the same gate and run binding. Fixed environment claim slots prevent concurrent consumption even across different authorization IDs. All claims remain evidence, including partial writes. Completed issuance and terminal evidence use synchronized pending records and exclusive completion publication, bound to exact authorization/run UUIDs and evidence hashes; residual JSON alone never qualifies. Fully verified success, verified no-op, and conclusive safe premutation failure permit a new separately owner-authorized operation without exceptional reconciliation. Uncertain commits, postcommit audit failures, or incomplete/contradictory evidence require an explicit owner reconciliation attestation bound to the exact predecessor bytes and verified state. Development still requires completed successful testing validation of matching artifacts and its own authorization; reconciliation alone cannot supply that result. Exact authorization validity is rechecked after audit persistence immediately before mutation and commit. The migration connection explicitly requires `require_auth="scram-sha-256"`.

The only initial transition remains `base -> 0001_migration_baseline`; the approved revision remains metadata-only and unchanged. Testing is the first future live target. Development requires separate owner authorization after successful testing validation of the same artifacts. A later no-op is separately authorized for an exact starting state of `0001_migration_baseline` and cannot reuse a consumed authorization. Preserve all existing identity, WinVault, restricted authority, SCRAM, ownership, schema-qualified tracking, transactional, sanitization, and manifest controls.

Offline validation uses temporary records, fake clocks/connections, and guarded credential/database interfaces; it includes concurrency, negative paths, durable/exclusive writes, denial persistence, expiry/retention, artifact/prerequisite separation, direct/Alembic bypass checks, acknowledged and uncertain commit outcomes, and recovery blocking. Deterministic autonomy review finds no AI in ordinary authorization, expiry, audit, execution, or recovery decisions. Owner review, issuance, and reconciliation remain explicit administrative controls. Offline tests do not establish live operational or production readiness; independent artifact review and a later separately authorized testing-only baseline validation are still required.

#### Historical Stage 1 contract context

The following contract/status descriptions are preserved as checkpoint history. The Stage 5 entry above controls current migration-policy approval, source implementation, Stage 4C delivery, and execution boundaries; unrelated feature scope and separate stage gates remain intact.

#### Status and Verified Current Foundation

**VERIFIED CURRENT FOUNDATION:** Checkpoint 1 repository reconciliation passed; Checkpoint 2 Candidate C architecture was approved; Checkpoint 3 PostgreSQL catalog inspection passed. These are prior checkpoint findings, not new live database checks performed by Stage 1.

- Preserve the independent website backend: Python 3.11, Flask, SQLAlchemy / Psycopg 3, PostgreSQL 17, separate website and GraManna databases, explicit environment selection, fail-closed configuration, and local Windows Credential Manager credentials.
- Existing development database/runtime: `oaf_website_dev` / `oaf_website_app`. Existing testing database/runtime: `oaf_website_test` / `oaf_website_test_app`. Do not recreate these databases or runtime roles.
- Existing shared database owner: `oaf_website_owner` (`NOLOGIN`). It retains existing database ownership for exceptional trusted database administration. Neither runtime nor migration accounts may assume it. It cannot authenticate directly.
- Preserve existing `public`-schema ownership and permissions unless a demonstrated requirement receives separate authorization. Catalog inspection does not establish migration execution readiness.

**APPROVED DESIGN / NOT IMPLEMENTED:** Checkpoint 4 bootstrap contract and implementation design are owner-approved with refinements A (transaction granularity), B (credential references), and C (audit evidence). The proposed migration roles, application schemas, Alembic framework/revisions, migration credentials, and dedicated migration tests have not been created or provisioned by this contract.

#### Candidate C Role and Ownership Registry

| Environment | Existing database | Existing runtime LOGIN | Proposed migration LOGIN | Proposed NOLOGIN schema owner |
| --- | --- | --- | --- | --- |
| development | `oaf_website_dev` | `oaf_website_app` | `oaf_website_dev_migrator` | `oaf_website_dev_schema_owner` |
| testing | `oaf_website_test` | `oaf_website_test_app` | `oaf_website_test_migrator` | `oaf_website_test_schema_owner` |

- Application schema in each database: `oaf_website`, owned by that environment's schema-owner role. All migration-managed objects and metadata, including Alembic version metadata, must have the matching schema owner.
- Required attributes for each proposed role: `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT`, plus `LOGIN` for migrators or `NOLOGIN` for schema owners.
- Grant each migrator membership only in its matching schema owner with explicit PostgreSQL membership options `INHERIT FALSE`, `SET TRUE`, `ADMIN FALSE`. Before any migration-managed DDL, the migrator must explicitly `SET ROLE` to that matching owner and verify the effective identity.
- Prohibit cross-environment schema-owner membership, migration membership in the shared database owner, runtime membership in schema-owner roles, runtime schema `CREATE` authority, unapproved grant options, and broad `PUBLIC` application permissions. Verify effective membership paths and privileges, not merely direct grants.
- The shared administrative owner retains database ownership; schema owners own the application schema and migration-managed objects, not the databases.

#### Administrative Bootstrap Contract

**FUTURE AUTHORIZED IMPLEMENTATION:** Bootstrap may occur only under separate Stage 4 authorization, using an existing trusted PostgreSQL administrator. Do not provision another permanent administrator. The administrator's authentication/authority path is a future verified prerequisite; do not assume direct login as the existing NOLOGIN database owner.

The future bootstrap must proceed through these checks and actions:

1. Verify existing database and role identities, database ownership, runtime privileges, and preserved infrastructure.
2. Verify that all proposed role and application-schema names are available. An unexpected existing role or schema halts the process; do not silently adopt, repair, rename, or replace it.
3. Verify administrator authentication, required authority, and membership grantor arrangements, accounting for PostgreSQL 17 role-creation and membership/grantor semantics. Do not assume role creation alone establishes the required membership administration authority.
4. Create the two NOLOGIN schema-owner roles with the required restrictive attributes.
5. Create the two migration LOGIN roles with the required restrictive attributes; handle credentials only through a separately authorized secure provisioning procedure.
6. Establish only the matching migrator-to-owner memberships with `INHERIT FALSE`, `SET TRUE`, and `ADMIN FALSE`, using the verified grantor arrangements.
7. Grant each migrator `CONNECT` only to its matching database; verify effective connection authority and cross-environment isolation, including indirect or `PUBLIC` paths.
8. Create `oaf_website` in each database under its matching schema owner.
9. Establish restrictive default privileges under the schema-owner authority as specified below.
10. Grant the corresponding runtime account application-schema `USAGE`, without schema `CREATE` or blanket object grants.
11. Verify object/schema ownership, defaults and effective privileges, membership paths, environment isolation, and preservation of existing databases, runtime roles, shared database ownership, and public-schema ownership/permissions.

Cluster-wide role changes and database-local schema changes do not constitute one atomic transaction across both databases. Failures must halt safely, record the verified completed/uncertain state, and require verified recovery before continuation. If isolation cannot be achieved while preserving existing infrastructure, report the demonstrated conflict and obtain separate authorization for the required change.

#### Default Privileges and Runtime Grants

- Each schema-owner authority must establish owner-only table/sequence defaults, no default `PUBLIC EXECUTE` on future routines, and no default `PUBLIC USAGE` on future types/domains. No blanket runtime table, sequence, or routine grants are approved.
- Use role-specific, database-wide default privilege controls where necessary to remove PostgreSQL's built-in `PUBLIC` defaults. Schema-specific default revocations cannot remove global built-in default grants and must not be relied upon for that purpose.
- Runtime permissions must be object-specific, reviewed for the feature that requires them, and explicitly established and verified by future revisions. Verify actual privileges as well as defaults and ownership.
- Runtime accounts must have no privileges on Alembic version metadata. Schema `USAGE` does not authorize access to that metadata.

**Owner-approved generated-type clarification (Stage 2 remediation):** Ordinary explicitly managed application types/domains retain restrictive `PUBLIC` permissions and owner-specific defaults. The sole baseline exception is PostgreSQL's automatically generated `oaf_website.alembic_version` row type and its `_alembic_version` array type, internally dependent on the exact migration version table and row type respectively. For this pair only, NULL type ACLs represent PostgreSQL's built-in owner and `PUBLIC USAGE` defaults, not absence of access; the array's effective privilege check uses its element type. Validate exact generated identity/dependencies, schema and matching ownership, effective `USAGE` and absence of nonowner grant options. This exception grants no schema `USAGE`/`CREATE`, table/view data access, or runtime metadata access, and approves no other managed types or explicit type grants. Restrictive global and application-schema defaults remain required. Actual generated ACL, dependency, and effective privilege behavior must still pass separately authorized Stage 5 PostgreSQL validation; unexpected semantics halt without a permissive fallback.

#### Standalone Alembic and Configuration Design

Standalone Alembic is the approved framework. Validate compatibility and approve the exact dependency pin during future implementation; no package installation is authorized in Stage 1.

Proposed future components (do not create them during documentation):

- `requirements-migrations.txt`
- `alembic.ini`
- `migrations/env.py`
- `migrations/script.py.mako`
- `migrations/versions/`
- `migrations/manifest.json`
- `oaf_website/migration_config.py`
- `oaf_website/migrate.py`
- `oaf_website/migration_validation.py`
- Dedicated migration tests

The migration entry point must require explicit `development` or `testing` selection, matching `OAF_ENV`, the fixed database/role registry above, the exact expected starting revision, the exact target revision, and approved revision/artifact hashes verified against the approved manifest. Reject production before credential access. Permit no arbitrary database URL or username override.

The existing runtime configuration loader remains restricted to runtime accounts. Migration identities require their own separate, fail-closed configuration path using the preserved Windows Credential Manager backend and selected matching credential reference. Alembic `env.py` must not construct a fallback engine; Flask startup must never run migrations.

The initial metadata-only revision is `0001_migration_baseline`. It establishes Alembic revision tracking under the matching schema owner, without creating Request Your State feature tables or endpoints and without runtime privileges on version metadata.

#### Migration Credential References — Refinement B

| Environment | Approved service identity | Account |
| --- | --- | --- |
| development | `OAF Website/development/PostgreSQL/Migrations` | `oaf_website_dev_migrator` |
| testing | `OAF Website/testing/PostgreSQL/Migrations` | `oaf_website_test_migrator` |

The standardized suffix is plural: `/Migrations`. These are approved design identities; migration credentials have **NOT been provisioned**. Existing runtime service references in the configuration foundation remain separate. Preserve Windows Credential Manager and the same-user access limitation documented in `WORKFLOW.md`; do not embed passwords in documentation or examples. Future production credentials require separate authorization and protection.

#### Deterministic Migration Lifecycle — Refinement A

**One approved revision per execution. One transaction for that revision.** The transaction encompasses approved revision DDL, applicable privilege grants, Alembic version advancement, and required precommit postconditions. Do not automatically execute multi-revision upgrades; multi-revision execution requires later explicit design and authorization.

The future runner must enforce the following deterministic lifecycle:

1. Verify run authorization, explicit environment/`OAF_ENV`, fixed credential/role/database selection, exact expected starting and target revisions, and approved manifest/revision/artifact hashes. Fail closed on discrepancies.
2. Verify the connected database and authenticated migrator; explicitly assume and verify the matching schema owner for migration-managed DDL. Enforce a controlled `search_path` for the intended application schema and qualified object access without relying on caller/session defaults or writable unintended schemas.
3. Acquire the approved advisory lock before authoritative migration-state checks. Define and validate lock identity/scope and lifetime, covering authoritative checks, execution, and the commit outcome; contention or acquisition failure must halt without unsafe continuation.
4. Under the lock, verify revision state, schema and object ownership, approved grants/defaults, and absence of unexplained drift. If the target is already applied, permit only the fully verified no-op described below. Otherwise require the exact expected starting revision and single approved revision transition. Reject missing, unexpected, or mismatched state.
5. Execute exactly that revision in one transaction, including applicable object-specific grants, version advancement, and required precommit ownership/schema/grant/revision postconditions. Failed checks or statements require rollback and sanitized failure classification.
6. Record commit certainty and release resources deterministically. An uncertain commit requires classification and verified state reconciliation under the approved lock/recovery procedure; do not blindly retry, stamp, or repair it.
7. A verified already-applied target is a no-op only if all required revision, ownership, schema, grant, and drift checks pass. Repeat execution must never infer success from the version marker alone.
8. Produce sanitized phase, lock, validation, outcome, and recovery evidence under the approved operational evidence procedure in `WORKFLOW.md`. Ordinary operation must not require AI.

Proposed initial timeouts: lock timeout **5 seconds**; statement timeout **60 seconds**. Validate their enforcement, including advisory-lock waiting behavior, before operational acceptance. Locking and timeout details are implementation/validation obligations, not existing behavior.

Initially prohibit nontransactional migration operations, revision-controlled commits, autocommit blocks, ordinary downgrade, stamp, automatic destructive repair, and blind retries after uncertain commits. Authorized administrative intervention remains appropriate for exceptional changes, destructive recovery, ownership corrections, and unexplained drift.

#### Operational Prerequisites and Evidence — Refinement C

**UNRESOLVED OPERATIONAL PREREQUISITES:** Before seeking migration execution authorization, verify the existing administrator authentication/authority and PostgreSQL 17 grantor path; separately authorize/provision migration credentials; validate the Alembic pin and artifact manifest approval process; and establish and approve advisory-lock scope/lifetime, controlled search-path details, timeout enforcement, postcondition/drift checks, and verified recovery/uncertain-commit procedures.

Establish and owner-approve the precise audit destination, retention policy, failed-write behavior, and operational evidence procedure before migration execution is authorized. Follow the sanitized evidence categories, exclusions, independent review, and same-account log limitations in `WORKFLOW.md`. Raw operational logs stay outside Git; only independently reviewed, sanitized validation evidence may accompany an authorized Git checkpoint. Audit persistence is not implemented; no retention period or new paid logging service is approved.

**Deterministic autonomy review: design PASS; implementation and operational behavior awaiting validation.** The lifecycle covers explicit identities, artifact approval, one-revision transactions, ownership, search path, locks/timeouts, drift/grant checks, rollback, uncertain commits, repeat execution, and evidence. Administrative bootstrap, approval decisions, and exceptional recovery remain justified administrative boundaries. PostgreSQL behavior and negative/recovery paths require future validation; neither catalog inspection nor Stage 1 documentation proves operational or production readiness.

#### Separately Gated Implementation Sequence

Each stage requires separate explicit owner authorization. Completion of any stage does not automatically authorize a subsequent stage.

| Stage | Scope | Authorization boundary |
| --- | --- | --- |
| 1 | Contract/documentation updates | Only this stage is authorized now; edit the two governing documents and perform bounded documentation validation. |
| 2 | Migration framework implementation | Requires separate authorization; implement the proposed components and validate the exact Alembic dependency pin. |
| 3 | Offline unit and negative-path testing | Requires separate authorization; validate deterministic logic, isolation, redaction, and failure paths without live credentials or PostgreSQL access. |
| 4 | PostgreSQL role/schema bootstrap | Requires separate authorization and verified administrator/grantor and secure credential arrangements; follow the bootstrap contract. |
| 5 | Controlled PostgreSQL migration validation | Requires separate authorization and approved operational prerequisites/evidence procedure; validate baseline, grants, locks/timeouts, rollback, repeat execution, drift, and uncertain-commit recovery. |
| 6 | Independent security review | Requires separate authorization; assess effective authority, isolation, secrets, artifacts, execution, and evidence/recovery controls. |
| 7 | Deterministic autonomy implementation review | Requires separate authorization; classify implemented behavior using validated success, negative, failure, and recovery evidence. |
| 8 | Final validation and approved Git checkpoint | Requires separate authorization; complete final review and bounded validation. Stage/commit/push only within an explicitly approved Git checkpoint's scope. |

Stage 1 completion stops at documentation and validation for owner review. The exact next recommended approval checkpoint is **Checkpoint 4 / Stage 2 — migration framework implementation**, with scope and dependency actions expressly authorized before work begins. This sequence authorizes no Request Your State feature tables/endpoints, email notification implementation, or production provisioning.

### Request Your State and Notification Signup

#### Launch and availability subscription source checkpoint — 2026-10-11

State Request is **CLOSED / PASS**, and TESTING and DEVELOPMENT are at revision `0002_state_requests`, per the owner. This checkpoint authorizes notification source implementation and offline validation, superseding earlier notification deferral wording. It authorizes no live migrations, migration authorization issuance, credentials, email provider integration, production sending, separate administration system, or Git staging/commit/push. Preserve the F2 launcher, existing development environment, approved revisions 0001/0002 and owner-authored changes.

- Keep the existing notification card and shared styling. Optional signup remains separate from anonymous State Requests; neither an account nor login is required. Choices are web launch, Android release, iOS release, and one of the 50 U.S. states for availability announcements. Selecting a state does not assert current availability or guarantee expansion.
- Server eligibility requires a supported email address, at least one preference and explicit consent. Support common ASCII dot-atom email syntax with a DNS-style domain; trim outer ordinary spaces and lowercase the entire address for deduplication. Reject control characters, quoted/internationalized mailboxes and invalid/oversized inputs. Do not perform DNS requests or provider-specific dot/plus rewriting. Syntax validation does not verify mailbox ownership.
- Use strict bounded JSON, configured same-origin checks, existing HttpOnly/SameSite browser recognition and browser-bound CSRF. No public subscriber listing, email lookup, subscriber count or preference retrieval exists. New and duplicate submissions receive the same status/message; any returned private capability derives only from that submission's random receipt, never from an existing subscriber record.
- Revision `0003_notifications` follows unchanged 0002. The schema-qualified notification table stores normalized email, three launch preferences, optional state, fixed consent version, server consent timestamp, unsubscribe timestamp and a SHA-256 receipt hash. A partial unique email index permits at most one active subscription; the receipt-hash primary key prevents replay of a withdrawn lifecycle. Atomic conflict suppression preserves existing preferences, consent timestamps and tokens, including concurrent duplicates. Preference changes require the existing private unsubscribe link followed by fresh consent and a new receipt.
- Store no bearer token. Domain-separated HMAC-SHA256 capabilities combine the stored hash with the existing persistent protected application key; future delivery can recreate the same unsubscribe link. Frontend receipts use browser cryptographic randomness. Links carry the capability only in a URL fragment, remove it from the address bar on opening, and mutate only after an explicit same-origin/CSRF-protected POST. Verify the signature before lookup; forged links are rejected, and unknown valid links or repeated withdrawal return a generic response. Keep the key stable across workers/restarts; replacement invalidates existing links.
- Withdrawal sets the timestamp once and suppresses all preferences for that lifecycle. Old receipts never reactivate it, and old links cannot affect later subscriptions. Retain consent/withdrawal records; no automatic deletion or invented retention period is implemented. Only committed successful writes produce confirmation. Failed or uncertain outcomes return sanitized messages and allow deliberate idempotent repeats with the same receipt/link; do not log emails, tokens, SQL values or underlying exception details.
- Runtime grants are exactly SELECT/INSERT on the notification table and UPDATE on its `unsubscribed_at` column. Generated feature types remain private. Extend exact catalog/constraint/index/dependency/ACL validation, manifest inventory and audit state vocabulary for 0003 while preserving all Stage 5 review, testing-before-development, single-revision transaction, authorization, lock and recovery controls. The manifest stays `pending_independent_review`.
- Email delivery is deferred. The UI confirms storage processing and explicitly states that no email has been sent; it never claims mailbox verification or a delivered confirmation. Future approved delivery must honor active consent/preferences and suppression, and establish mailbox verification and provider handling before dispatch. Announcement approval and geographic readiness remain Foundation decisions, with no AI runtime dependency.
- Deterministic autonomy review: **source/offline PASS**. Eligibility, normalization, preference/state validation, consent, duplicate suppression, receipt/signature checks, withdrawal and repeat handling use fixed rules. Negative/failure/recovery paths are tested. No ordinary operation requires AI or per-submission administrative review. Artifact approval, separately authorized migrations, public deployment and future announcement/delivery governance remain explicit administrative boundaries.
- Next database checkpoint: independent review of exact 0003 artifacts/prerequisites, then a separate owner-authorized **TESTING** `0002_state_requests -> 0003_notifications` validation. Verify real PostgreSQL partial-index races, constraints, dependency/type ACL and column-grant semantics, runtime identity, persistence, rollback/uncertain outcomes and real API/browser behavior. DEVELOPMENT requires successful TESTING evidence for matching artifacts and its own authorization. No live readiness is claimed by offline success.

#### State Request implementation checkpoint — 2026-10-10

The owner reports both PostgreSQL baseline migrations CLOSED / PASS and the frontend inspection complete. The current bounded task authorizes State Request source implementation and focused offline validation. It supersedes earlier feature-deferral and baseline-only source scope statements for this feature. It authorizes no credential access, real approvals/authorizations, live migrations, paid provisioning, or Git staging/commit/push.

- Preserve the existing 50-state card and shared CSS. Activate anonymous requests through same-origin Flask API routes; notification signup remains separate and deferred.
- Server-signed HttpOnly browser recognition, a browser-bound CSRF token, configured-origin checks, fetch metadata, strict JSON/body limits, and the exact 50-state registry govern submissions. Recognition identifies a cookie-bearing browser, not a person; cookie deletion, expiry, secret replacement, or a different browser can permit another count.
- Revision `0002_state_requests` follows unchanged `0001_migration_baseline`. A schema-qualified table stores `(state, browser_key, created_at)` with a composite primary key, state check and server timestamp. Atomic `ON CONFLICT DO NOTHING` permits different states and suppresses concurrent duplicates. Public totals use grouped committed rows and never return browser keys.
- Extend the manifest, exact catalog definitions/dependencies, private feature type ACLs, explicit matching-runtime SELECT/INSERT grants, and authorization evidence state vocabulary only as required for 0002. Preserve the Stage 5 single-revision transaction, independent review, owner issuance, testing-before-development, lock/session identity, audit and recovery controls. The manifest remains `pending_independent_review`.
- Deterministic autonomy: state validation, anonymous eligibility, recognition, deduplication, persistence and counting use fixed rules with no AI or manual per-request decision. Failures return sanitized messages; an unconfirmed commit can converge on a deliberate repeat using the same browser recognition.
- Live functionality remains unvalidated. Next checkpoint: independent review of the exact 0002 artifacts and prerequisites, followed by a separate owner-issued **testing** authorization for `0001_migration_baseline -> 0002_state_requests`. Successful authorized PostgreSQL/API/browser validation precedes separate development authorization.

- Request Your State uses anonymous submissions and does not require email or account creation.
- Multiple states per browser are permitted. Each recognized browser contributes at most one counted request per state.
- Duplicate controls and request counting must be enforced by authoritative, deterministic backend rules rather than solely by frontend behavior.
- Request withdrawal and reversal are not supported.
- Notification signup is optional and separate from state requests.
- These rules define future implementation; local environment setup does not activate forms or implement API endpoints.

### Deterministic Autonomy and Development Cost Control

- Deterministic autonomy is required end to end across frontend and backend features, following the permanent rules in `WORKFLOW.md`.
- Prefer explicit rules, validation constraints, state transitions, and deterministic lifecycle and failure handling. Ordinary operations must not require continuous manual intervention or AI participation.
- Review and test autonomous decisions, negative cases, failure handling, and recovery before feature designs are considered near-final. Preserve authorized Foundation administrative authority for exceptional corrections and policy decisions.
- Develop and validate locally first using existing tools and infrastructure.
- No paid external resources may be provisioned or activated without explicit owner approval, including hosting, databases, email services, subscriptions, and cloud resources.
- Identify expected recurring and usage-based costs before requesting approval. Design or implementation approval does not authorize expenses.

## 10. Planning Before Implementation

Before substantial page coding begins, the project should establish:

- website goals and primary audiences;
- initial site map and navigation;
- page-by-page purpose;
- required public content;
- Foundation identity and organization information;
- GraManna public explanation;
- privacy, terms, and other appropriate policy/disclosure surfaces;
- visual and brand direction;
- accessibility expectations;
- domain and deployment arrangement;
- contact method;
- launch-readiness criteria.

The website should be designed deliberately before Codex is asked to build the full site.

## 11. Global Design System and Responsive Behavior

- The entire website must be responsive and adapt cleanly across desktop, tablet, and mobile widths.
- Responsive behavior applies to all page elements, including navigation, typography, images, section spacing, columns, cards, buttons, forms, and footer content.
- Images must resize and crop gracefully without distortion.
- Text should reflow and scale appropriately as available screen space changes.
- Reusable interface elements must use shared global styles rather than page-specific duplicate styling.
- Components of the same type should behave consistently across the website.
- Examples include buttons, links, headings, cards, navigation elements, form controls, and content sections.
- If a shared component has hover, focus, pressed, disabled, animation, or transition behavior, that behavior should remain consistent wherever that component appears.
- Global design values such as colors, spacing, typography, border radius, shadows, and transition behavior should be centrally defined wherever practical.
- Page-specific exceptions should be introduced only when there is a clear design reason.



## 12. Next is About the Foundation.
For this section, I’d actually keep the layout fairly simple rather than adding another image immediately.
My suggestion:
- keep the white band;
- keep the content in a narrower centered column;
- keep the small green eyebrow text;
- larger “About the Foundation” heading;
- eventually 1–2 short paragraphs underneath;
- no button and no image for now.
That gives the page some breathing room after the visually heavy hero and before the GraManna section.
