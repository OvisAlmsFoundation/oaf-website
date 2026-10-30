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


### Step 6G / Checkpoint 6G-1: approved persistence source (2026-10-15)

The owner approved the Step 6G direction and this bounded source/offline checkpoint.
The authoritative contract is the Checkpoint 6G-1 entry in `WORKFLOW.md`.
It preserves the current OAF/GraManna shared services, existing public behavior,
original notification subscriber/email/consent records and all owner-authored work.

- Additive `0004_notification_delivery`, parent `0003_notifications`, defines
  lifecycle-bound double opt-in verification, durable confirmation quotas,
  independent Android/iOS release events, per-lifecycle delivery ledgers, attempt
  audit and durable mailbox suppression. No existing subscriber is auto-verified.
- Internal unregistered services enforce a 24-hour protected confirmation token,
  bounded resends, stable event/payload/semantic deduplication, fixed template and
  audience cutoff, verified active platform eligibility, durable claims, final
  withdrawal/suppression checks, bounded safe retries and uncertain-submission holds.
  Provider acceptance never means final email delivery.
- No second subscriber list, separate admin app, free-form announcements, Cargo 29
  functionality, sender, live worker, release ingress or provider webhook is added.
  Public verification remains inactive until confirmation messages can be delivered.
- Source and offline validation do not establish live database, Brevo or deployment
  readiness. All 0001--0003 revision bytes and existing safeguards remain intact.
  Integrity hashes are not approval. Independent exact-artifact review and separate
  TESTING/DEVELOPMENT execution authorizations remain required before any application.
- Deterministic autonomy source review passes: routine decisions use explicit
  rules; approved launch provenance, policy changes and exceptional corrections
  remain governed controls. Uncertain outcomes never authorize another send.
- Next checkpoint is separately approved Brevo adapter source and synthetic outcome
  validation, including reliable confirmation handoff and provider reconciliation.
  Real credentials, provider setup, live sends, migrations, deployment and Git
  staging/commits/pushes remain outside this checkpoint.

6G-1 focused offline gate: 676 passed; new source/revision coverage 100% statements
and branches; changed migration-policy decisions fully covered. No live migration
or email occurred. See WORKFLOW.md for the exact file inventory and local evidence.


### Checkpoint 6G-2: Brevo adapter source / offline gate (2026-10-15)

The bounded adapter and release processor source is implemented and offline-tested;
the complete checkpoint remains open at the confirmation-outbox approval boundary.
See the authoritative 6G-2 entry in WORKFLOW.md for the exact contract and evidence.

- Direct fixed Brevo HTTPS transactional POST, verifying TLS, 5-second connect and
  10-second response inactivity timeouts, bounded response bodies, strict response
  validation, no redirects/proxies/ambient HTTP credentials or hidden POST retries.
- Existing exact-target pinned Windows credential convention; DEVELOPMENT target
  `OAF Website/development/Brevo/ApiKey`. No real key read; production remains gated.
- Approved From/Reply-To identities and deterministic verification/Android/iOS copy.
  Release links use the accepted official event URL and existing OAF withdrawal UI.
  Confirmation rendering is a seam only; its reserved fragment is not activated.
- Batches of at most 20 provider submissions use the existing durable claims,
  consent/verification cutoff, final withdrawal/suppression check, attempt history,
  bounded retry and uncertain-outcome hold. Acceptance is not mailbox delivery.
- Final scoped gate: 663 passed; zero unexpected external-access attempts;
  new source 202/202 statements and 56/56 branches, 100%. With the changed delivery
  service: 440/440 statements and 152/152 branches, 100%.
- Deterministic review passes for implemented operations, without AI or a second
  administrator Send action. Authenticated feedback/correlation remains deferred.
- Reliable confirmation handoff cannot be completed with the current digest-only
  reservation and release-only delivery tables. No persistence workaround or
  approved-artifact rewrite is introduced. Public verification/sending stays off.
- Exact next checkpoint, requiring approval: **6G-2A: confirmation outbox contract,
  additive successor source and focused offline validation**, parent 0004, with
  atomic durable intent/attempts and reviewed token recovery without raw storage.

All owner/Contact/shared-service work, initial document bytes, Git index and
0001--0004 artifacts are preserved. No GraManna change, real Brevo API request,
email, migration, production activation, deployment, staging, commit or push occurs.
This is source/offline evidence, not live delivery readiness.


### Checkpoint 6G-2A: durable confirmation outbox source (2026-10-15)

The owner authorizes this bounded OAF Website source/offline successor. The full
contract and exact file inventory are in the appended 6G-2A WORKFLOW.md entry;
prior entries and owner/Contact/shared-service work remain preserved.

- Every new confirmation reservation atomically commits the verification digest,
  original 24-hour expiry, unchanged global/mailbox quotas and pending intent.
  A restart can reconstruct the same bearer using HMAC-SHA256 with the existing
  persistent protected key and explicit recovery/version/environment/lifecycle
  domain separation plus a random persisted 256-bit context. No raw bearer is
  stored; old irreversible-only reservations are never falsely reconstructed.
- Additive `0005_confirmation_outbox`, parent `0004_notification_delivery`, adds
  only lifecycle/version intent and attempt history. Existing release tables
  cannot safely represent confirmation work; no earlier table/revision is changed.
  Exact manifest/catalog/ACL/dependency validation and narrow runtime column grants
  preserve independent review and separate TESTING/DEVELOPMENT execution gates.
- Internal bounded processing recovers pending links, enforces one-use durable
  claims, cancels obsolete resend versions and checks original consent, expiry,
  verification and suppression immediately before its committed dispatch boundary.
  Safe failures use unchanged 60/300-second backoff and three-attempt ceiling;
  uncertain submissions are held without blind retry. Audit identifiers cannot
  retain an echoed confirmation bearer. Provider acceptance never verifies email.
- The existing Brevo adapter/template and approved From/Reply-To identities are
  reused. Public confirmation UI/routes, scheduler/worker activation, live provider
  credentials/sends, migrations and production configuration are not activated.
  Ordinary lifecycle/recovery decisions require no AI or administrator intervention;
  policy changes and exceptional corrections retain human authority.
- Final focused counts/coverage and preservation evidence are appended to WORKFLOW
  and kept under ignored `.pytest_cache/checkpoint6g2a/`. Offline synthetic checks
  establish no PostgreSQL, provider or deployed delivery readiness.

Exact next checkpoint: **6G-2A independent exact-artifact/prerequisite review** of
0005 and changed manifest/helpers, with unexecuted 0004 retaining its own review
and exact-transition execution boundary. Separate TESTING execution must precede
separate DEVELOPMENT authorization. Public confirmation integration, processor
invocation and authenticated reconciliation/live activation remain separately
approved work. No staging, commits, pushes, GraManna edits or Cargo 29 features.

6G-2A SOURCE/OFFLINE PASS: **1,022 tests**, zero external-access attempts; new
source **206/206 statements, 68/68 branches**, complete changed feature
modules **577/577 statements, 216/216 branches**, all 100%. Changed migration
policy lines/decisions are covered. No live migration or delivery occurred.


### R38: public email confirmation integration (2026-10-17)

**SOURCE IMPLEMENTED / OFFLINE VALIDATED. LIVE EMAIL DELIVERY / OPERATIONAL
ACTIVATION: OFF.** The appended R38 WORKFLOW entry records the exact contract,
file inventory, preservation checks and validation evidence. The owner reports
migrations 0001--0005 applied and verified in TESTING and DEVELOPMENT; this
checkpoint performs no migration or live database/provider operation.

- Add strict same-origin/browser-CSRF POST `/api/notifications/confirmation`
  (`email` only) and `/api/notifications/confirm` (`token` only). All valid email
  request outcomes are generic. Tokens never enter public API responses. Existing
  expiry, supersession, safe-repeat, timestamp, withdrawal and suppression rules
  remain authoritative; only valid confirmation verifies mailbox ownership.
- Default-off factory injection `confirmation_enabled=False` enables persistence
  and public operations only when explicitly True. No existing environment or
  launcher enables it. OFF preserves signup/unsubscribe, performs no confirmation
  reservation/mutation and displays no email-sent claim. No sender, dispatcher or
  recurring processing is started by either flag state.
- Enabled NEW signup uses the same locked transaction for consent, applicable
  quotas, verification reservation and existing durable outbox intent. Duplicate
  email/receipt submissions leave original preferences, consent and pending work
  intact, including deliberate repeats after lost commit acknowledgements.
  Quota/suppression-denied signup may save consent without reserving email work;
  subsequent requests remain subject to the unchanged durable rules.
- Accessible request/resend and explicit confirmation controls reuse the current
  notification card and CSS. The reserved `#confirm-email=` capability is cleared
  before application requests; opening it never verifies automatically. Existing
  unsubscribe links, privacy, responsive layout and keyboard behavior are retained.
- Focused backend: 656 passing tests, then the expanded 80-test public file PASS
  (660 distinct cases across the selection), zero unexpected external access.
  Confirmation and preserved signup/unsubscribe Playwright checks PASS at 1280px
  and 390px, with zero page errors/external requests. Full PowerShell transcripts,
  failed harness history, screenshots and preservation evidence remain ignored
  under `.pytest_cache/r38/`. Established interpreters, test guards, clipboard
  workflow and visual completion/failure alerts are preserved.
- Deterministic autonomy source/offline review PASS. Ordinary eligibility,
  quotas, state transitions, token recovery, rollback and repeat handling require
  no AI or per-subscriber administrator decisions. Operational invocation remains
  an explicit next dependency, not a hidden manual subscriber workflow.

Next smallest recommended checkpoint: **R39 bounded dispatcher invocation and
restart recovery integration, source/offline only**. Reuse existing bounded
processing, protected configuration and durable recovery; specify recurring
invocation and sanitized monitoring without a new worker framework. Live provider
configuration/sends, capability-link tracking validation, authenticated feedback/
uncertainty reconciliation, bounded live API/transaction validation and production
activation retain separate approval boundaries. No live sending/readiness is
claimed. No GraManna source change, Git staging, commit or push occurs.


### R39: bounded confirmation processor invocation (2026-10-17)

**SOURCE/OFFLINE VALIDATED. LIVE PROVIDER DELIVERY / OPERATIONAL ACTIVATION:
OFF.** The appended R39 WORKFLOW entry defines the complete invocation,
scheduling, recovery, reporting and activation contract. Applied/verified
migrations 0001--0005 in TESTING and DEVELOPMENT remain closed per the owner.

- `python -u -B -m oaf_website.confirmation_processor --environment <profile>`
  runs one existing confirmation dispatcher batch only after the explicit
  `--enable-processing` switch. Default OFF returns a sanitized nonzero disabled
  result without configuration/credential/key/database/provider access. Explicit
  matching `OAF_ENV`, existing runtime database loaders/checkout identity checks,
  approved nonsecret Brevo account metadata and secure confirmation page are
  required. Production fails closed before credentials. There is no new settings
  file, environment authority or public/application-startup processing.
- The existing protected key loader gains `require_existing=True`: the processor
  never creates a missing/replacement DPAPI key. Existing hosts keep their
  create-once default. The existing Brevo loader/adapter, outbox, templates and
  durable intent/attempt authority are reused; no schema, queue or framework is
  added. Every invocation disposes its runtime engine.
- Work remains at most 20 selected due intents and 20 expired-claim recoveries
  per start, with five-minute leases, three attempts, 60/300-second safe retries
  and the original 24-hour token expiry. Database claims/transaction locks govern
  concurrency. Restart recovers the same pending token; expired claimed work can
  retry safely. Possibly submitted work becomes/remains uncertain and never
  blindly resends. Final lifecycle checks preserve expiry, supersession,
  withdrawal, suppression and verification. Provider acceptance never verifies
  ownership or establishes mailbox delivery.
- JSON output contains only existing `status` and `processed` fields; exit 0 is
  completed processing, 2 disabled/invalid arguments, 1 unavailable and 130
  interrupted. Zero processed does not prove an empty outbox; recoveries or
  ineligible/competing work may have been handled. Counts describe acknowledged
  outcome persistence, not delivery. Existing ledger evidence remains authoritative
  after interrupted/unacknowledged results; no private data or raw exceptions are
  reported. Uncertain/terminal provider outcomes can accompany completed processing.
- Future recurring invocation can use the approved host's existing scheduler.
  The local Windows proposal is one start per minute from the website root under
  the approved existing credential/DPAPI account, explicit matching environment,
  approved metadata/page and enable switch. Disable overlapping starts as an
  operational policy; database claims still protect concurrent invocations.
  Scheduled starts discover due retries and bounded restart recovery automatically;
  ordinary messages require no manual processing or AI. Capture JSON/exit status
  in existing host logs/alerts and later authorize sanitized ledger observation.
  No task, worker, background service, startup launcher or production setting is
  registered/activated. Existing network inactivity bounds are not a total
  wall-clock deadline; forced termination retains conservative uncertainty recovery.
- Focused gate: **621 passed in 15.62 seconds**, including **95 new processor
  cases**, zero unexpected external-access attempts. Guards, dedicated website
  interpreter, `-B`, explicit pytest isolation and visible logged PowerShell
  output/visual alerts are retained. The six selected files cover all R39
  invocation, bounds, restart/commit, retry, concurrency, lifecycle, redaction and
  R38 compatibility scenarios. No browser behavior changes, Playwright run,
  GraManna access, package installation or migration certification occurs.
- Deterministic autonomy source/offline review PASS. Ordinary decisions follow
  existing authoritative rules. Activation/configuration, policy/key changes,
  official approvals and exceptional evidence-backed corrections retain human
  authority. Provider feedback/correlation/reconciliation remains separately
  contracted; no lack of evidence permits a resend.

R38 and owner changes, historical document prefixes, migrations/schema/manifest,
runtime/deployment launchers and Git index are preserved. Exact R39 files are
`oaf_website/confirmation_processor.py` (new), `oaf_website/local_testing.py`,
`tests/test_confirmation_processor.py` (new), `tests/migration_offline.py`, and
both governing documents. Ignored evidence/logs/report are in `.pytest_cache/r39/`;
`Invoke-OAFCodex` and clipboard/completion workflow remain unchanged.

Smallest next checkpoint: **R40 separately owner-authorized bounded TESTING
end-to-end invocation and restart validation**, with a controlled mailbox and
approved actual host/account/origin/protected configuration. Verify the stated
activation prerequisites first and keep recurring scheduling and production
inactive. Public activation compatibility, sender/link confidentiality and live
API/claim/restart behavior remain within that future bounded authorization.
Authenticated provider feedback remains separately contracted; R39 does not
activate or certify live delivery or require another independent source review.


### R40-B: controlled recipient enforcement and TESTING HTTPS preparation (2026-10-17)

**SOURCE / OFFLINE VALIDATED. LIVE TESTING HTTPS / CONFIRMATION / PROVIDER
ACTIVATION: OFF.** The appended R40-B WORKFLOW entry governs the complete contract,
future startup procedure, exact inventory and evidence. R36 HEAD is unchanged;
R38/R39 and owner work remain preserved. Applied/verified 0001--0005 work stays closed.

- Enabled TESTING processor calls now require one deliberately supplied approved
  `--testing-recipient` / `testing_recipient`. Normalize using existing mailbox
  rules; reject missing/malformed/repeated CLI scope or enabled non-TESTING scope
  before protected runtime access. Default OFF remains inert. No mailbox is chosen
  or provisioned in this checkpoint; no new configuration authority is introduced.
- Existing SQL filters both due intents and expired-claim recovery through the
  authoritative subscriber's exact mailbox before stable ordering/LIMIT. Claims,
  final committed submission preparation, outcome persistence, dispatcher and
  Brevo adapter enforce the same scope. Never redirect another subscriber's message.
  Unrelated records/claims/attempts remain untouched, including expired work.
- Retain 20 due/20 recovery bounds, five-minute leases, three attempts, 60/300-second
  safe backoff, original 24-hour expiry, lifecycle/suppression checks, durable history
  and conservative uncertainty without automatic resend. Ordinary non-test
  processing contracts remain intact; production remains blocked.
- Add the explicit `oaf_website.local_testing_https` foreground host and HTTPS
  factory seam using existing Flask/Werkzeug and public-file allowlist. Bind only
  `127.0.0.1:443`, require explicit matching TESTING configuration, existing DPAPI key
  and verified runtime checkout. Public confirmation defaults OFF; its explicit
  enable switch never starts a processor. Existing HTTP TESTING and DEVELOPMENT/F2
  conventions and PowerShell execution remain compatible.
- Owner must select a loopback-resolving HTTPS hostname/origin and exact matching
  `/gramanna.html` page, trusted valid matching certificate/noninteractive PEM key,
  absolute protected file paths and port-443 availability/privilege. Strict templates
  still reject HTTP/nonstandard HTTPS ports. TLS minimum 1.2, no certificate/trust
  provisioning; Secure HttpOnly/SameSite cookies, origin/CSRF protections remain.
- Focused gate: **737 passed in 20.67 seconds**, including **72 new recipient/HTTPS
  cases**, zero unexpected external access. All 20 requested behavioral areas are
  covered using existing early isolation guards, serialized SQL model, in-process
  Flask and mocked TLS/server/provider dependencies. No real TLS key, socket,
  PostgreSQL, credential, provider or email operation; no migration recertification
  or browser campaign. Logs/snapshots/report remain ignored in `.pytest_cache/r40b/`;
  existing visible PowerShell, clipboard and visual alert behavior is preserved.
- Deterministic autonomy source/offline review PASS: fixed server-side selection,
  scope/claim authorization, eligibility, retries, recovery and uncertainty hold.
  No ordinary AI or administrator intervention; exceptional corrections and
  operational/policy approvals retain existing authorized human controls.

Smallest next checkpoint: **R40-C owner selection and prerequisite review for one
bounded TESTING end-to-end operation**, followed only by separate explicit live
authorization. Actual mailbox/account/origin/certificate/port choices, compatible
public activation, sender/link confidentiality and live transaction/restart behavior
remain prerequisites. Recurring scheduling and production stay OFF. No staging,
commit/push, GraManna access or deployed/live delivery readiness is claimed.


### R41: dedicated email confirmation page (2026-10-17)

The approved source flow is now signup -> existing Brevo confirmation email ->
dedicated OAF Website confirmation page -> one explicit Confirm email action ->
existing authoritative verification POST -> success on the same page. No signup
form or second navigation follows success. See the appended R41 WORKFLOW entry
and final evidence for the exact implementation, inventory and validation status.

- `confirm-email.html` and `assets/email-confirmation.js` reuse shared navigation,
  typography, palette, card/button styles and responsive layout. Landing copy
  identifies OVIS ALMS FOUNDATION and the selected GraManna announcements. Success
  displays the green check, "Your email is confirmed!", the approved explanation
  and "Email verification complete", with the confirmation action removed.
- A head script clears the private fragment before API work. Existing session,
  CSRF, same-origin and POST `/api/notifications/confirm` protections remain in
  force. GET/page load/scanner previews never confirm. Fixed accessible busy,
  success, invalid/expired/unavailable and network/server states follow backend
  results, with one-action duplicate protection and deliberate safe retries.
  No subscriber existence or raw server diagnostic is disclosed.
- New emails use `/confirm-email.html#confirm-email=`. The narrow explicit runtime
  validator supports exactly the dedicated path and legacy `/gramanna.html`
  configuration, canonicalizing only the path on the same trusted HTTPS authority.
  Exact TESTING origin, standard port, no credentials/query/fragment and strict
  paths remain required. Existing issued legacy links forward their unchanged
  fragment to the dedicated page before confirmation. No token is regenerated.
  Unsubscribe links and their exact `/gramanna.html#unsubscribe=` contract remain.
- Both independent public-confirmation/processor switches still default OFF.
  Page serving starts no sender or scheduler. Endpoint authority, consent,
  eligibility, cryptography, original expiry, stable timestamps, durable outbox,
  safe retries/leases/uncertainty, Brevo, State Requests, Contact and shared-service
  contracts are preserved. No schema or migration change is required.
- The focused guarded backend gate passed **734 tests in 20.32 seconds**, zero
  unexpected external-access attempts. It covers the unchanged lifecycle/security
  rules plus trusted dedicated/legacy page configuration, new link rendering,
  exact origin restrictions and mutation-free static page GETs. Browser evidence
  is recorded separately in the final R41 validation entry. Existing PowerShell
  live output, complete logging, visual alerts and clipboard workflow are retained.
- Deterministic autonomy source review passes: fragment handling, explicit action,
  authoritative results, retry/expiry/revocation and fixed accessible messages
  require no AI or routine administrator decision. The capability stays transient;
  reopening the original email link is needed after a fresh reload. JavaScript
  and cookies are required. Resistance covers ordinary GET/page-load scanners,
  without claiming to distinguish a deliberate authorized POST by a script client.

The owner reports R40-F **END-TO-END TESTING CONFIRMATION PASS**, including Gmail
receipt, explicit confirmation and database timestamp validation, with HTTPS shut
down and port 443 released. R41 records that baseline only. Completed migrations
0001--0005 in TESTING/DEVELOPMENT remain closed. No new live email, credential,
database, provider, HTTPS, scheduler or production operation occurs. No GraManna
source access/modification, package install, staging, commit or push occurs.
Historical document bytes and owner notes remain intact. Operational activation,
approved recurring scheduling/monitoring, production deployment/secrets and future
authenticated feedback/reconciliation retain their separate gates. No production
readiness or new live confirmation certification is claimed.


R41 final status: **BLOCKED at the required Playwright desktop/mobile gate**.
Source, guarded backend tests, syntax, whitespace and preservation checks pass.
The current prohibition on GraManna paths conflicts with the established shared
Playwright interpreter location, and Playwright is absent from the website
interpreter. The interpreter-only clarification remains pending; no sibling path,
package install or alternate method is used. The two intercepted browser scripts
are prepared and syntax-checked but unexecuted, so responsive/keyboard/browser
results are not claimed. Exact evidence and limitations are in the final R41
WORKFLOW entry. Smallest next checkpoint: resolve that narrow tool boundary and
run only the dedicated-confirmation and preserved subscription/unsubscribe
browser checks at 1280px and 390px. Keep backend reruns proportional, live email,
migrations, HTTPS, recurring processing and production activation out of scope.


### R41 browser validation continuation PASS (2026-10-17)

**R41 - SOURCE / OFFLINE VALIDATED.** This supersedes the historical R41 browser
block above after the owner's explicit shared-interpreter clarification. Both
prepared intercepted Chromium scripts passed unchanged at **1280px and 390px**
using `..\GraManna\.venv\Scripts\python.exe`, installed Playwright **1.61.0** and
the established Chromium cache through the existing live/transcribed helper.

Dedicated confirmation, fragment privacy, explicit action, accessible busy/success
states, keyboard/focus, invalid/expired and network/API/session failures, safe
retries, default OFF, legacy links and existing request/signup/unsubscribe behavior
PASS. Zero page errors or unexpected page requests; confirmation checks also report
zero unexpected console errors. All six captured landing/success/unavailable
screens were visually reviewed. No source/test correction was needed; the prior
guarded **734-pass** backend evidence remains preserved without a redundant rerun.
Deterministic autonomy source/offline review PASS.

All 116 source paths matched the prior R41 hashes before execution. Only validation
entries are appended to the two governing documents; original bytes, R38-R41 and
owner work, backend/migration artifacts, HEAD and index are preserved. The exact
R41 inventory remains as recorded in WORKFLOW. Logs/screenshots are under ignored
`.pytest_cache/r41/`; continuation hashes, interpreter evidence and final clipboard
report are under `.pytest_cache/r41-continuation/`. Existing visual alerts and
clipboard/live-output/logging behavior are retained. No shared-environment writes,
GraManna application inspection, install, credentials, database/provider/email,
live activation, staging, commit or push. No material source/offline blocker
remains; operational and production activation retain their separate gates.


### R41-F1: repeat confirmation and final-state repair PASS (2026-10-17)

**R41-F1 - REPAIR / VALIDATION PASS (source/offline).** See the appended WORKFLOW
entry for the finding, complete contract, exact inventory and evidence. The backend
previously collapsed first/repeat success; it now distinguishes `already_verified`
only after the unchanged current-capability, original expiry, active lifecycle and
suppression checks. The endpoint retains `status=confirmed` and adds Boolean
`already_confirmed`. Valid repeats preserve the original `verified_at` and all
persisted records; invalid/expired/revoked links reveal no historical verification.

The approved dedicated success presentation now uses authoritative repeat wording:
"Your email is already confirmed!" and "Your email address has already been
verified. No further action is needed." First/repeat success clears the transient
capability, hides/disables the button, focuses the result and announces completion
on the same page. Opening a link still requires an explicit click; no GET mutation
or browser-storage inference is added. The owner-approved hidden landing heading
and all `confirm-email.html` bytes remain untouched.

Focused guarded backend **392 PASS**, plus **4 PASS** existing mutation-free static
GET/factory cases: **396 distinct cases**, zero unexpected external access.
Dedicated and preserved subscription/unsubscribe intercepted Playwright PASS at
**1280px and 390px**, including same-token repeat, terminal action removal, safe
failures, legacy links and OFF behavior. Eight screenshots visually reviewed.
Deterministic autonomy review PASS; no routine AI/administrator decision is needed.
Baseline Chromium already reached first-time success; the reported historical
post-click landing loop was not reproduced, so no live-runtime attribution is
claimed. Expected pre-repair regression failures and full final transcripts remain
under ignored `.pytest_cache/r41-f1/`, with preservation hashes/clipboard report.

Branch `main`, HEAD `ea85b65029f6f9927563b0e9e57134b0fb87787b`, empty index,
owner changes and unrelated source remain preserved; original document bytes are
exact prefixes. Existing logging, clipboard and visual alerts remain intact.
No material source/offline blocker. No R44 processing, GraManna source changes,
credentials, real provider/email operations, live database mutation, migrations,
production activation, staging, commit or push. Operational gates remain separate.


### R44: autonomous recurring confirmation processing (2026-10-17)

**R44 - SOURCE / OFFLINE VALIDATED. REGISTRATION / LIVE ACTIVATION: OFF.**
The appended R44 WORKFLOW entry governs the exact invocation, future activation/
deactivation procedure, deterministic review and evidence. Owner-approved R41
visuals, R41-F1, historical records, R40-F and closed migrations remain preserved.

- Added `oaf_website.confirmation_schedule plan` generates a deterministic disabled
  Windows task without registering anything or accessing secrets. One canonical
  task runs every minute, ignores overlapping starts, permits delayed missed-run
  startup, and has a four-minute execution budget. Its fixed literal PowerShell
  action calls `confirmation_schedule run`, which invokes the existing one-shot
  `confirmation_processor.main` once. No worker, queue, framework or public-GET
  processing is introduced. XML version/ordering pass Microsoft's published XSD.
- Task enablement and the action's explicit `--enable-processing` are separate;
  both default OFF. Require the approved existing Windows account SID, logged-on
  `InteractiveToken` session, matching explicit environment, stable protected key,
  exact runtime/Brevo credential targets and trusted confirmation page. No stored
  scheduler password or credential change. The host/account must be available;
  this local arrangement does not promise processing during logoff/sleep or
  real-time sending. Windows missed-start catch-up can add delay.
- TESTING retains its single explicitly approved mailbox restriction throughout
  selection/recovery/claims/preparation/adapter. DEVELOPMENT already supports
  ordinary eligible consent scope with its own credentials; no interface gap or
  fallback is added. Production stays blocked before protected access.
- One OS-released local wrapper lock also prevents conflicting task aliases or
  environment starts. PostgreSQL locking/claims remain authoritative. Existing
  20 due/20 recovery bounds, five-minute leases, three attempts, 60/300-second
  safe backoff, original 24-hour expiry and all lifecycle checks remain intact.
  Restart/missed runs never blindly resend possible submissions or reset limits.
- Minimal ignored, non-public JSONL reports persist start/completion UTC,
  environment, fixed status, safe processed count and exit code. Logging failure
  before processing blocks startup; ordinary failures are nonzero and sanitized.
  Task result/history covers action startup or unavailable logging. Durable attempt
  history remains authoritative; acceptance is not delivery or verification.
- Future owner activation imports only the reviewed disabled canonical task,
  verifies its identity/action/configuration, then deliberately enables it.
  Deactivation disables future starts; preserve running work/history for bounded
  completion or conservative restart recovery. No task is registered or enabled
  here; no existing registration is assumed. Host termination/missed-run behavior
  still needs separately authorized operational validation.
- Focused guarded gate: **557 PASS in 19.55s**, including **60 scheduler cases**,
  zero unexpected external-access attempts. Offline Microsoft XSD validation and
  decoded PowerShell syntax/literal-argument validation PASS. Fake providers and
  transactional models cover repeated ticks, missed runs, retries/exhaustion,
  restart/uncertainty, concurrent claims, lifecycle restrictions, environment/
  mailbox isolation, finite batches, logging and R41/R41-F1 compatibility. No
  scheduler service, real credentials/database/provider, browser, migration or
  unrelated broad suite is exercised. Existing live PowerShell/transcript,
  clipboard and visual-alert workflows are preserved.

Deterministic autonomy source/offline review **PASS** across invocation,
activation/environment, selection/claims, eligibility, retry timing/exhaustion,
expiry/revocation, consent/suppression, provider outcomes, restart/uncertainty and
sanitized reporting. No routine AI or per-message administrator action. Owner
activation/policy/exceptional correction authority remains. Authenticated feedback/
correlation and conclusive uncertainty reconciliation remain separately contracted.

Exact source delta: two additions (`oaf_website/confirmation_schedule.py`,
`tests/test_confirmation_schedule.py`), one additive test allowlist entry in
`tests/migration_offline.py`, and append-only entries in both governing documents.
All other 113 initial tracked paths, original document prefixes, HEAD and empty
index remain preserved. Ignored evidence/logs/report: `.pytest_cache/r44/`.
No live sending/activation, operational credentials, schema/migration, GraManna,
package install, production action, staging, commit or push. Recurring delivery
is **not operational** until separately authorized activation succeeds.

Smallest next checkpoint: separately approved bounded **TESTING scheduler
activation and deactivation**, under the approved logged-on account and existing
single-mailbox rule, after the R44 host/SID/configuration/public-origin/task/log
prerequisites. Keep DEVELOPMENT/production inactive and completed migrations and
R40-F closed. Ordinary DEVELOPMENT activation requires separate owner approval.


### R45: Windows task XML investigation (2026-10-17)

**R45 XML REPAIR - BLOCKED.** The appended WORKFLOW entry records the bounded
evidence, comparison and one proposed owner-context validation-only diagnostic.
The owner reports failed disabled registration (`COMException`), independent
confirmation of no canonical task, and Windows TASK_VALIDATE_ONLY failure
`0x8004131A`. The exact XML element/contract violation remains unestablished.

The unchanged approved plan reproduces the saved failed-trial XML. Microsoft XSD,
MSXML6 string parsing and decoded PowerShell action checks pass; **60 focused
scheduler tests pass in 3.05s**, zero unexpected external access. None establishes
Windows Task Scheduler compatibility. No speculative source/test change is made.
Version/namespace, recurrence, limits, owner SID/InteractiveToken/LeastPrivilege,
disabled defaults, encoded action and registration semantics were compared.
The declaration/COM transport hypothesis remains unconfirmed.

Prepared `.pytest_cache/r45-xml-repair/validate-only.ps1` requires the exact
repository/baseline/generator and `OAF-DELL5511\ovisa`. One bounded A/B diagnostic
submits original generated disabled TESTING XML and an otherwise identical
declaration-free copy using only TASK_VALIDATE_ONLY=1. It checks canonical task
absence before/after, reports sanitized HRESULTs, keeps full live logs and XML
evidence, and preserves clipboard/visual alerts. It was syntax/boundary-reviewed
offline and **not executed**. A diagnostic result must establish the cause before
a minimal source repair and corrected-generator Windows validation. Actual task
registration/enablement remains separately owner-authorized even after acceptance.

Deterministic autonomy source/offline review PASS: invocation/environment,
eligibility/retries, claims, expiry/revocation, provider outcomes, uncertainty,
restart recovery and sanitized reporting remain fixed rules without ordinary AI.
R41 visuals, R41-F1, all R44 implementation, owner notes, HEAD and empty index
are preserved. Only these two documents gain append-only entries; all 12 other
initially modified/untracked files remain unchanged. No GraManna, credentials,
database/migrations, provider/email, production, install, registration/activation,
staging, commit or push. Completed migrations/R40-F are not reopened. Evidence and
complete logs remain ignored in `.pytest_cache/r45-xml-repair/`.


### R45: XML declaration repair source/offline PASS (2026-10-17)

**R45 XML REPAIR - SOURCE / OFFLINE PASS. Corrected-generator Windows validation
pending; registration/activation OFF.** The appended WORKFLOW continuation controls
this repair; earlier investigation evidence and owner notes remain historical.

Owner-context A/B evidence establishes the declaration compatibility problem:
TASK_VALIDATE_ONLY rejected the original XML with `0x8004131A` and accepted its
otherwise identical declaration-free form. Scheduler version `0x00010006`;
canonical task NONE before/after; no processor/provider operation. This supplied
evidence does not yet certify the corrected generator on Windows Task Scheduler.

One production argument changes: `task_xml` serializes with
`xml_declaration=False`, preserving Unicode output and all remaining source bytes.
Normal `plan` output now omits the declaration. **63 focused scheduler tests PASS
in 3.20s**, zero unexpected external access, using unchanged early offline guards.
Four environment/activation definitions match the preserved generator exactly
after declaration removal. Microsoft XSD, well-formedness, decoded PowerShell and
normal disabled owner-SID plan comparisons PASS. No action is executed; no broader
backend/browser/migration/live-email campaign is repeated.

Disabled defaults, PT1M/PT4M, IgnoreNew, InteractiveToken/LeastPrivilege, owner SID,
encoded action, explicit TESTING, processing OFF for the trial, recipient enforcement
and all existing processor/recovery/security/provider rules remain unchanged.
Deterministic autonomy review PASS; no new operational/manual/AI decision or gate
relaxation. Prepared owner-only `validate-corrected-only.ps1` under ignored
`.pytest_cache/r45-declaration-repair/` checks exact repository/account/artifact,
requires corrected declaration-free XML and canonical absence, submits only
TASK_VALIDATE_ONLY=1, reports sanitized acceptance/HRESULT and final absence, and
preserves live logs, clipboard read-back and OAF alerts. Syntax/boundary-reviewed
offline; **not executed**. Separate registration/activation authorization remains.

Only the scheduler source, scheduler regression file and append-only governing
documents change. All other R41/R41-F1/R44/owner work, original document prefixes,
`main`, expected HEAD and empty index are preserved. No GraManna, credentials,
database/migrations, real provider/email, production, install, scheduled invocation,
registration/activation, staging, commit or push. No source/offline blocker remains;
corrected-generator owner-context Windows acceptance is still pending.


### Notification Management V2: source ready (2026-10-19)

**NOTIFICATION MANAGEMENT V2 — SOURCE READY.** The appended WORKFLOW entry defines
the exact implementation, focused evidence, preservation and next owner gate.
This supersedes only the immutable-preferences management experience, ordinary
signup-page unsubscribe destination and deferral of the specific authenticated
Brevo unsubscribe event. Historical evidence and unrelated decisions remain intact.

- One `/manage-notifications.html` page uses existing OAF styles and permits
  authorized viewing, adding/removing web/Android/iOS/state preferences, changing
  state, explicit save and full withdrawal. Signup remains on `gramanna.html`;
  existing private unsubscribe links forward to the dedicated page without
  gaining read/edit authority. No accounts, passwords or dashboard are added.
- Separate protected-key HMAC capabilities bind purpose, explicit environment,
  original lifecycle, revision, issue/expiry and random context. Email links last
  at most 30 days; recovery links 24 hours. Viewing/editing still requires verified
  active consent. Opening GET/HEAD never changes consent. Same-origin browser
  CSRF, strict JSON, fragment clearing, no-store/no-referrer and private responses
  remain mandatory. Anonymous email requests disclose no subscription status.
- Explicit audited saves preserve original consent/verification evidence, use
  revision/action idempotence and return a same-expiry continuation to the authorized
  caller. Unselecting everything withdraws consent, preserving prior selections.
  Added/re-added preferences must satisfy release cutoffs. Old links/events cannot
  withdraw a newer independently verified consent lifecycle.
- Relevant V2 emails contain **Manage Preferences / Unsubscribe**. Lost-link
  recovery reuses the existing durable quotas, outbox/attempts, processor, adapter
  and fixed templates, adding a management purpose for verified subscribers.
  Existing confirmation remains independent; recovery never removes suppression,
  resets uncertainty or automatically restores a deliberately blocked sender.
- One HTTPS bearer-authenticated POST `/api/notifications/brevo/unsubscribed`
  accepts only the transactional event. Match accepted provider `message-id`,
  recipient, exact database/environment, original lifecycle and consistent parent/
  attempt evidence across both confirmation/recovery and release ledgers. Webhook
  `id` is never a message ID. Atomically commit a deduplicated receipt, original
  lifecycle withdrawal and permanent provider suppression. Invalid/ambiguous/
  uncorrelated events cannot change consent; transient failures use documented
  429 retries. Provider suppression alone never establishes OAF synchronization.
- The owner's completed Gmail → Brevo experiment resolves the ignored draft's
  provider-path blocker. Brevo → OAF remains operationally unverified. No experiment,
  email, unblock, provider API call or live registration is repeated here.
- Additive **0006_notification_management**, parent 0005, prepares one append-only
  change/receipt table, subscription revision and existing-outbox purpose/revision
  fields. Only four preference columns/revision gain UPDATE; audit receives
  SELECT/INSERT only. Earlier revisions/schema helpers and role isolation remain.
  No duplicate subscriber database, email queue, scheduler, service or framework.
- V2 public/processor activation is explicit and defaults OFF. Existing factories,
  protected configuration and one-shot invocation are reused; default R45 XML is
  preserved. No migration, credential provisioning, live mutation, sending, task
  change, deployment, staging, commit, push or GraManna modification occurs.
- **1,132 distinct offline cases PASS**, overlapping reruns excluded. The three
  focused Chromium scripts PASS at 1280px/390px, covering management, signup/legacy
  withdrawal and confirmation; zero page errors/unexpected external requests.
  Existing early guards, visible simultaneous logging, OAF alerts and clipboard
  workflow remain. Deterministic autonomy source/offline review PASS: all ordinary
  decisions are backend rules, with no AI or manual per-subscriber approval.

**Exact next owner checkpoint:** independent 0006 exact-artifact/prerequisite
review, then separate single-use TESTING **0005 → 0006** authorization and bounded
real catalog/ACL/concurrency validation. DEVELOPMENT requires matching TESTING
success and its own authorization. Provider-reachable HTTPS, protected bearer,
webhook registration and actual authenticated correlation/withdrawal validation
remain a later explicit operational checkpoint. No guaranteed historical callback
redelivery is assumed; keep the controlled mailbox blocked and send no new email.
No live webhook or production PASS is claimed. Original governing-document bytes,
owner changes, HEAD/index, closed migrations and R45/R46 evidence are preserved.


### Step 3 consolidated repair: approved contract refinements (2026-10-20)

The owner authorizes one connected source/helper repair and offline validation.
Historical entries remain history. This grants no live preflight, credential,
database, scheduler, provider, HTTPS reload, email, unsubscribe exercise, migration,
execution authorization or Git operation.

1. Replace historical whole-host task XML equality with OAF-scoped isolation:
   discover broadly; inspect execution/resource relationships, encoded actions and
   known wrappers; pin relevant existing OAF definitions and disabled/idle states
   and the exact single-use task/action. Keep process visibility, competing-worker,
   wrapper-lock, session, durable-claim and final eligibility checks. Unrelated XML
   drift is observational. Opaque actions remain unresolved observations under the
   existing trusted Windows host/account boundary, which does not certify arbitrary
   privileged internals. Demonstrated OAF conflicts and unresolved relationships
   needed to establish that boundary block execution. Names, SYSTEM, vendors and
   signatures confer no trust; the unidentified COM handler remains unconfirmed.
   Historical provenance, current reviewed source/configuration and HTTPS process
   bindings are distinct from subscriber/lifecycle/intent identity.
2. Add browser-bound withdrawal acknowledgment receipts with acknowledgment-only
   authority. Before withdrawal, the protected same-origin/CSRF POST issues a
   domain-separated signature using the existing key over environment, browser
   binding, original lifecycle, expected revision, exact action/payload digests,
   issue time and expiry. Lifetime is at most ten minutes and cannot exceed the
   original management token/session expiry. The page keeps the receipt only in
   its closure, obtaining it before the mutation. Thus it survives lost response
   bodies even when deletion headers clear the management cookie. Repetition can
   acknowledge only an exact committed management-withdrawal audit transition;
   it cannot mutate, read/edit preferences, reactivate, request mail or restore
   management access. Exact repeats preserve the first withdrawal timestamp and
   single audit entry; changed, forged, expired or misbound receipts fail generically.
   Successful withdrawal/acknowledgment clears the management cookie. No capability
   enters URLs, logs or browser storage. Origin, CSRF and privacy protections apply.

Preimplementation deterministic-autonomy review: fixed server rules govern scope,
eligibility, observations, claims, outcomes, receipt issuance/replay and recovery.
Ordinary processing and withdrawal need neither AI nor per-message administrator
approval. This exceptional TESTING procedure is not production policy. Existing
operational activation and exceptional evidence reconciliation retain owner control.
Expiry prevents later execution of the original intent; offline repair may finish
without renewing, replacing or extending that intent. Integrity is not permission.

Step 3 consolidated source/offline result: six repair areas implemented together.
Focused management backend **150 PASS**, connected helper **37 PASS**, PowerShell
**125 assertions PASS**, intercepted Chromium **1280px/390px PASS**. Both cookie
retention/deletion body-loss paths acknowledge without another mutation. Uncertain
provider references retain the no-resend hold; primary preservation is demonstrated
only with synthetic records. No real subscriber query or live operation occurred.
Postimplementation deterministic-autonomy review PASS for this bounded source
scope. Ordinary processing, withdrawal and recovery require no AI or per-message
administrator approval. The exceptional TESTING procedure is not production policy.
Exact six-file source delta, prior evidence reuse, hashes, logs and limitations are
in `.pytest_cache/r47-step3-consolidated-20261020/`. Original document prefixes,
owner work, reviewed helpers, consumed records and evidence remain preserved.
One next checkpoint: coherent exact-artifact/prerequisite review of this revision.
Fresh live preflight, new execution authorization, any required HTTPS reload,
delivery and actual unsubscribe remain separate and unperformed. No current
eligibility, delivery, production readiness or Step 3 PASS is claimed.

### Accepted operational safeguard correction — current direction (2026-10-21)

The owner accepted the audit dispositions for one coherent source/offline batch.
The appended current `WORKFLOW.md` contract governs; Project Settings add no approval
gate. Historical outcomes and consumed evidence remain unchanged.

- Bind runtime integrity/locks to executed helpers, imports, interpreter/configuration,
  security-sensitive assets, original intent anchors and permanent consumed authority.
  Documentation, Git bookkeeping and unused test/editor/historical/migration artifacts
  remain preservation inventory. Keep controlled import/source/cache behavior.
- Discover broadly and classify actual execution/resource relationships. Ordinary
  terminals, navigation, venv activation and supported read-only development pass.
  Workers/descendants, relevant unresolved execution, unsafe tasks, active wrapper
  locks and genuine database conflicts still block.
- Use one temporary effect-based Python child policy across HTTPS, delivery/preflight,
  preserving PYTHONSTARTUP handling, harmless supported inherited settings, exact
  interpreter, protected DB configuration, fresh cache and caller restoration. Do not
  modify profiles/persistent environment or bypass actual Windows execution policy.
- Recognize the current reviewed HTTPS launcher/listener through fresh exclusive
  startup evidence, owner/PID/creation/ancestry and TLS/loopback/origin checks. Historical
  startup equality and exact readiness prose are not authority. Check current state
  after mutex abandonment.
- Close M01 in the existing processor/store: exact original lifecycle/intent, management
  purpose, revision, attempt, deadline and TESTING recipient at selection, recovery and
  locked submission. A second same-mailbox intent never joins the exceptional batch.
  The original **2026-10-21T03:28:14.153915Z** expiry is permanent; no new permission or
  replacement intent is created. Separately approved recurring behavior is preserved.
- Close M02/M03 through existing result/evidence/wrapper/parent mechanisms: preserve
  originating sanitized first failure, side-effect certainty and acknowledged outcomes;
  observe the read-only ledger independently of provider/key send-readiness. Mark
  unavailable key-dependent checks incomplete. Reduce static rehashing/history scans
  while retaining mutable-state checks and interruption evidence. Preserve established
  terminal/log/clipboard/read-back/OAF alerts.

Successor: `.pytest_cache/operational-safeguards-v1-20261021/`. Its manifest/dependencies,
focused receipts and consolidated report identify exact sources and future invocation.
One consolidated autonomy review covers changed decisions; ordinary operation needs
no AI, per-subscriber approval or second Send action. No new queue, table, provider,
authorization framework, package, paid infrastructure or review campaign is introduced.
Source/offline validation grants no operational execution or production authority.


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

### Step 5 confirmation-specific one-use source/offline handoff (2026-10-23)

The appended WORKFLOW contract governs the single authoritative package at
`.pytest_cache/step5-confirmation-once-v1-20261023/`. It prepares explicit owner
issuance at the actual future action time and permanent confirmation-only
consumption using existing local evidence/helpers and the unchanged sealed caller.
No Step 3 authority is repurposed and no real record was issued or consumed.
Original issuance 2026-10-23T20:17:13.754265Z and immutable expiry
2026-10-24T20:17:13.754265Z, exact original TESTING intent/lifecycle/recipient and
attempt ONE remain fixed. No renewal, replacement, retry or additional email.
34 focused Python cases and 26 PowerShell assertions PASS, native exits 0;
source/offline readiness is distinct from live eligibility or operational PASS.
Exact SHA256 identities and the complete unexecuted owner command are in the
package. No live preflight/database/provider/service/Git operation occurred.
Tunnel/guard shutdown and approved signup UI work follow operational completion;
they remain untouched in this batch. No extra review/approval gate is introduced.
### Step 5 safe authorization supersession preparation v1 (2026-10-23)

The current WORKFLOW supersession suffix governs the focused source/offline package
`.pytest_cache/step5-authorization-supersession-v1-20261023/` and its ONE
`FUTURE-PROCEDURE.txt`. The original mechanism has no retirement action; the narrow
adapter extends its existing permanent create-only reservation and completed
publication interfaces without editing the issued authority or accepted packages.

A future explicit owner action must win the ORIGINAL consumption slot and publish
terminal SUPERSEDED evidence before issuing one successor in a fixed child namespace.
Old execution wins OR retirement wins. Pending/partial/contradictory evidence denies
successor execution; old execution remains denied once its slot is reserved.
Original identity/history, intent/lifecycle/recipient, confirmation purpose, attempt
ONE, original issuance and `2026-10-24T20:17:13.754265Z` expiry remain immutable.
Current DB-clock pristine eligibility, final locked backend checks, deterministic
claims/outcomes and uncertainty/no-retry holds remain authoritative. Source hashes
are integrity evidence only. Exceptional owner issuance/reconciliation is separate
from autonomous ordinary processing; no AI/per-message administrator dependency.

The package records focused synthetic validation, unchanged evidence reuse,
source/dependency SHA256, failure/publication/interruption behavior and reporting.
This preparation performs NO real retirement, issuance, consumption, live DB query,
processor/provider submission, email/signup/resend, service/tunnel/guard/webhook,
credential/scheduler/migration/Git or frontend operation. Both implemented UI
improvements and the queued post-Step-5/post-shutdown signup refinement are preserved.

### Step 5 closure and next roadmap dependency (2026-10-25)

The single current Step 5 acceptance record and reconciled diagnostic improvement
register are in [WORKFLOW.md](WORKFLOW.md#step-5-final-acceptance-and-closure-2026-10-25).
Reuse its accepted website/Brevo evidence and stated correlation/coverage limits;
earlier notes remain historical and owner-authored work is preserved.

The existing sequence is Step 5 completion -> planned temporary tunnel/guard
shutdown -> remaining queued signup paragraph refinement -> **Step 6**.
`cloudflare-webhook-guard-v1-20261022/README.md` under `.pytest_cache/` identifies
Step 6; the Step 5 confirmation/supersession notes establish the shutdown and
refinement order. Both already implemented UI improvements remain completed.
The available records do not define Step 6's full scope; do not substitute the
separate historical Step 6G work or invent deployment prerequisites.

**ONE next roadmap action:** owner-authorize the planned temporary Cloudflare
tunnel/forwarding-guard shutdown checkpoint. This documentation closure performs
no shutdown, UI/runtime/database/test change or Git delivery. Git delivery remains
subject to separate owner authorization.

### Remaining diagnostics before Step 6 — staged candidate (2026-10-25)

The appended current WORKFLOW reconciliation records one diagnostic-only candidate
at `.pytest_cache/remaining-diagnostics-20261026T004941Z/candidate/`: direct keyed
webhook audit-receipt correlation, safe predicate facts and accurate dependent
NOT_RUN. Accepted Step 5 results and installed improvements remain closed. Runtime
source locks are preserved; installation awaits a controlled authorized shutdown.
Connected tests: 496 PASS. Full canonical suite and whole-application 100% coverage
do not pass; exact results, baseline comparison and source identities are retained
with the candidate. No Git delivery or live operation occurred. The existing
shutdown/refinement/Step 6 roadmap remains; WORKFLOW holds the sole improvement
register and the one next controlled-installation action.


### Step 4 CLOSED / PASS and approved UI refinements (recorded 2026-10-26)

The owner accepted **Step 4 CLOSED / PASS** from October 25, 2026 live
Eyes & Clicks with CloudCake's original management link after withdrawal.
The page showed "This link is unavailable. Use your latest email or request a
new link." with no editable preferences, Save control, reactivation capability
or protected-preference disclosure. This browser observation is distinct from
the earlier accepted source/test evidence for expiration, revocation, lifecycle
binding, session deadlines and stale authority. A screenshot does not
independently establish backend timestamps or database mutations.

The current detailed closure, UI installation and evidence record is in
[WORKFLOW.md](WORKFLOW.md#step-4-owner-closure-and-approved-ui-refinements-recorded-2026-10-26).
The approved presentation batch is complete: active-management instructions
follow available authorized editing; verified withdrawal keeps its exact
success message; generic-link privacy and recovery remain intact; shared
success/error/information/processing feedback is reused with an empty-border
correction; and the redundant signup paragraph is removed while one feedback
area remains beneath Subscribe. Newer installed safeguards and all historical
documentation are preserved.

Focused installed-source Chromium validation: **60 PASS**, 30 checks each at
1280 x 844 and 390 x 844, native exit 0; full-page captures reviewed. Intercepted
synthetic APIs only, no backend/operational certification. No full pytest/CI
campaign, server/tunnel/guard restart, Brevo activation/email/provider request,
credential/database/migration operation, GraManna write or Git delivery.
Evidence: `.pytest_cache/step4-ui-closure-20261026T161838Z-2669eded/`.

The previously queued signup refinement is completed by this batch. The existing
remaining-diagnostics candidate and its canonical/coverage limitations remain
separate; Step 6 is not started or assigned an invented scope.
**ONE next action:** resume the existing remaining-diagnostics installation
checkpoint within its separate scope.


### Notification Management V2 Step 6 - DEVELOPMENT Migration 0006 closure (2026-10-26)

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


### Notification Management V2 Step 7 - final verification and Git readiness (2026-10-26)

**VERIFICATION PASS / GIT READY; owner closure and Git delivery pending.**
Steps 1-6 remain CLOSED / PASS. Accepted migration, focused 209-test,
60-check UI, owner Eyes & Clicks and historical Linux CI evidence is reused.
The current manifest and revision 0006 match the accepted Step 6 hashes.
No completed migration, live operation or browser acceptance was repeated.

The exact Git-normalized candidate based on `main` at
`3f3099df9582065213941c431527fee975b648ab` passes the existing canonical
CI shard/combination procedure locally: **3,592 tests PASS**, zero failures,
errors or skips; **5,671/5,671 statements and 2,004/2,004 branches, 100%**
across all 33 application modules. Historical canonical/coverage blockers
and pending repair-installation descriptions above retain their historical
scope; installed repairs and this current evidence govern final readiness.
The older Linux CI GREEN is not attributed to these uncommitted changes.

The scoped security/deterministic-autonomy review passes. Existing server
authority, lifecycle isolation, audit, suppression and recovery remain intact;
AI is not an operational dependency. This batch only appends documentation.
All owner source changes, prior document bytes, HEAD and the empty index are
preserved. The complete final candidate inventory, preservation checks and
logs are under `.pytest_cache/s7-20261026T195026Z-f4ccc056/`; details are in
WORKFLOW's matching Step 7 record. No genuine delivery blocker remains.

**ONE next action:** owner decision on the separate final Git delivery.
Step 7 is not declared CLOSED, and no staging, commit or push occurred.


### Notification Management V2 Step 7 - final closure and Git delivery (2026-10-26)

**Step 7 - CLOSED / PASS - October 26, 2026.** Steps 1-6 remain CLOSED / PASS.
The owner accepts final verification and explicitly authorizes delivery of the
nine accepted changes plus these append-only Step 7 closure records on `main`.
This current closure supersedes the earlier pending owner-decision wording;
all historical content and owner notes are retained.

Accepted final evidence is reused from
`.pytest_cache/s7-20261026T195026Z-f4ccc056/verification-final.json`:
**3,592 tests PASS; 5,671/5,671 statements and 2,004/2,004 branches covered**;
both shards and combiner exit 0; UTF-8, Git equivalence, security and
deterministic autonomy PASS. Executable, test, configuration and asset inputs
remain identical to that tested candidate. No test campaign is repeated.

Delivery validates the documentation delta and exact staged candidate, reviews
the complete staged diff and preserves all nine accepted changes. The authorized
commit message is `Close Notification Management V2 Step 7`; delivery uses the
existing `origin` remote and `main` without force or history rewrite. Actual
commit/tree identities, native exits and push outcome belong in the final
consolidated delivery report. The owner independently checks GitHub CI;
this delivery does not query or monitor it. Exit after successful push/report.


### Work Unit 1 - Android/iOS notifications: OAF source complete (2026-10-26)

The OAF side now accepts official mobile approvals through the existing protected
backend integration at `POST /api/integrations/v1/release-events`, using separate
release authorization, strict environment/identity/store-reference validation and
existing durable event acceptance. Existing confirmation processing/scheduling
also drives the ReleaseDispatcher behind default-off `--enable-releases` and
current preference controls. There is no new worker, queue or administrator Send
action. Android/iOS budgets and audience lifecycles remain independent.

Original IDs, audience cutoffs, deduplication and attempt history stay intact.
The final locked submission reads corrections; official withdrawal suppresses
unsent work and preserves acknowledged/submitting/uncertain outcomes. A minimal
append-only approval-history successor, `0007_release_approvals`, is prepared under
the existing pending-independent-review artifact contract. No migration is run.

Focused guarded validation passed 1,292 cases plus 12/13/15/2 targeted follow-up
executions; no external-access attempts occurred. New/changed application logic
and the new revision have 100% coverage: 266 statements and 176 branches. Security
and deterministic autonomy review passed. Full logs and scoped evidence are in
`.pytest_cache/wu1-resume-20261026T213359Z-4b74332a/`; the precise protocol,
correction/withdrawal semantics and preserved operational gates are appended to
WORKFLOW. Historical source/evidence and owner work are preserved.

All real activation remains OFF. No live credentials, databases, providers, emails,
servers, tasks, production configuration, GraManna source or Git delivery was
accessed or changed. Existing Invoke-OAFCodex final reporting remains unchanged.

ONE next action: implement the GraManna approval-to-OAF handoff in its separately
authorized operation. Independent migration review/execution and operational
activation remain later gates; no live end-to-end readiness is claimed.


### WU1 - Step 3 final completion and delivery readiness (2026-10-26)

**STEP 3 READINESS PASS; Git delivery and live activation are not completed.**
This current append supersedes earlier WU1 pending implementation, migration and
DEVELOPMENT provisioning directions while preserving all historical owner notes.

OAF and GraManna source/offline implementation PASS; OAF migration
`0007_release_approvals` is APPLIED_AND_VERIFIED in TESTING and DEVELOPMENT;
GraManna DEVELOPMENT `afmobout01` is APPLIED AND VERIFIED; DEVELOPMENT Release
credential is PROVISIONED AND VERIFIED. Exact accepted receipts and source
references are in WORKFLOW's matching Step 3 record.

Accepted evidence:
`.pytest_cache/wu1-connected-20261027T033228Z-2573aadb/consolidated-report.txt`
and `validation-summary.json`: nine areas/five synthetic scenarios plus five
guarded worker checks PASS. One official mobile approval durably creates the
original handoff; existing scheduled processing, eligible-subscriber selection,
bounded OAF batches, deduplication, consent/verification, suppression, retry and
uncertainty holds progress without a separate Send action or AI dependency.
All 140 OAF files matched that accepted evidence before these append-only
documentation changes; validation is reused, not rerun.

**Notification activation remains OFF.** Live runtime/origin/credential injection,
listing provenance, deployed environment and scheduler certification, and provider
delivery remain separately authorized operational work. Completed migrations and
provisioning are not pending. The owner's hypothetical legacy-withdrawal/
no-prior-handoff finding remains excluded, uncorrected and outside accepted proof.

This batch changes only the three necessary OAF documentation records.
GraManna's `.notes_cargo_ledger` and `CHANGELOG.md` require a separate append-only
WU1 reconciliation; its owner/Cargo work and delivery boundary remain untouched.
Final candidate inventory/hashes, consistency, preservation and whitespace
evidence: `.pytest_cache/wu1-step3-20261027T034450Z-f135daed/`. Historical CI GREEN does not
certify this uncommitted candidate. Actual staged-diff review remains at the
separately authorized delivery checkpoint; nothing is staged here.

**ONE next action:** obtain separate authorization for the OAF Git delivery
checkpoint. Step 3 PASS establishes readiness only; stop without delivery or
activation.


### WU2 - final evidence and documentation reconciliation (2026-10-27)

**READINESS PASS / READY FOR OWNER CLOSURE; NOT CLOSED.** This current append
supersedes historical pending WU2 implementation, review, migration and integration
directions while preserving prior entries and owner notes. Detailed evidence,
receipt paths and the single deterministic autonomy review are in
[WORKFLOW.md](WORKFLOW.md#wu2---final-evidence-and-documentation-reconciliation-2026-10-27).

- OAF WU2 implementation PASS; corrective commit
  `5c4bba88064b50d9e717bc3e9a7ecf1cd59d6ce3` delivered and CI GREEN,
  owner-confirmed. Canonical 3,915 tests PASS, 5,932/5,932 statements and
  2,138/2,138 branches covered, 100% each; accepted evidence is reused.
- GraManna WU2 implementation/focused evidence PASS; commit `55dbeb46` CI GREEN,
  owner-confirmed. Its separate Git-thread handoff remains required; the distinct
  connected source snapshot is not certified by that earlier CI result.
- OAF `0008_web_launch`: TESTING and DEVELOPMENT **APPLIED_AND_VERIFIED**, each
  native exit 0. GraManna DEVELOPMENT `agweb01`: **PASS / COMPLETED**, native exit
  0; data/schema/integrity/foreign keys and guards preserved. Neither migration
  remains pending; no database access or repeat execution occurs here.
- Connected evidence:
  `.pytest_cache/wu2-connected-20261027T233203Z-ff7b89a7/consolidated-report.txt`
  and `source-dependency-identities.json`: 10 distinct scenarios PASS (5 web,
  5 mobile), 11 guarded OAF checks PASS, zero unexpected external access and no
  unresolved failures. Earlier fixture failures and native exits remain preserved.
  Official approval, atomic durable handoff, audience selection, retries, recovery,
  suppression and uncertainty handling pass the accepted synthetic autonomy review.

No source, migration or validation defect remains demonstrated. This task updates
only WORKFLOW and this plan; the new documentation delta awaits separately
authorized OAF Git delivery. Preserve the separate GraManna Git-thread handoff.

**Canonical public GraManna HTTPS URL: NOT YET OWNER-APPROVED.**
`https://gramanna.example.org/app` remains solely a synthetic fixture. Live URL
configuration, real notification/external activation, production deployment and
real provider delivery are separate operational gates, not requirements for the
current WU2 owner closure decision. **Activation remains OFF.** Synthetic proof
does not certify deployed runtime/scheduler behavior, live PostgreSQL integration
or actual delivery. Accepted historical limits and excluded findings are retained.

**ONE smallest next checkpoint:** owner decision on formal WU2 closure using the
reconciled evidence and explicit remaining Git obligations. Owner closure and Git
delivery are not performed here. Existing `Invoke-OAFCodex` reporting is unchanged;
no completed campaign is rerun.


### WU2 - owner-approved formal closure (2026-10-27)

**WU2 CLOSED / PASS - Development and Synthetic Integration.** The owner's
formal closure supersedes the earlier pending owner-closure status; all prior
content and owner work remain. Accepted final readiness, migration, canonical,
owner-confirmed GitHub CI and connected evidence are reused within their recorded
limits; see [WORKFLOW closure](WORKFLOW.md#wu2---owner-approved-formal-closure-2026-10-27).

- OAF `0008_web_launch`: TESTING **PASS** and DEVELOPMENT **PASS**,
  both **APPLIED_AND_VERIFIED**.
- GraManna `agweb01`: DEVELOPMENT **PASS / COMPLETED**.
- Connected synthetic integration: **10 scenarios PASS** plus **11 guarded
  checks PASS**.

**OPEN Git obligations:** OAF documentation delivery and the separate GraManna
Git-thread handoff; neither is completed by this closure. Canonical public URL
approval/configuration, live activation, provider delivery and deployment remain
outside this completed development scope. **Activation remains OFF.**

Validation is documentation-only: delta, consistency, preservation and whitespace.
No accepted campaign is rerun. Existing reporting and clipboard mechanisms remain
unchanged; no Git staging, commit, push, reset or cleanup occurs.


### WU3 - OAF state availability source implementation (2026-10-27)

**OAF source / focused offline validation PASS; activation remains OFF.**
The existing authenticated release-event contract now supports `platform=state`,
one validated U.S. state code as `release_id`, and fixed `state-availability-v1`.
It reuses the configured approved canonical GraManna HTTPS destination, consent,
verification, state-grant cutoff, final locked eligibility checks, immutable
identity, ordered corrections/terminal withdrawal, existing Brevo templates,
claims, audit, retries and uncertainty recovery. State Requests remain separate
from official approval; no GraManna approval hook or production URL is invented.

The prepared `0009_state_availability` successor adds state-specific uniqueness
while retaining Android/iOS/web uniqueness and exact catalog/dependency/owner/ACL
validation. No applied revision or historical manifest entry is rewritten; artifact
status remains pending independent review. Existing processing fairly rotates one
state batch alongside the three original launch budgets: at most 10 confirmation
plus 3 each Android/iOS/web/state submissions, **22 total**. No new worker, queue,
table, Send action, AI dependency, scheduler/service change or routine second
administrator decision is added.

Focused guarded checks: **1,558 PASS + 32 final audit/artifact checks PASS**, zero
unexpected external access; changed logic/revision coverage **146/146 statements,
128/128 branches**, no exclusions. One focused security/deterministic-autonomy
review PASS. Exact contract, source identities, limitations and evidence are in
WORKFLOW's matching WU3 entry and `.pytest_cache/wu3-state-20261028T002520Z/`.
Accepted WU1/WU2 evidence and all prior document bytes/owner work are preserved.
No live PostgreSQL/provider/deployed-runtime proof, current CI, migration execution,
operational authorization, activation, deployment or Git delivery is claimed.

**ONE smallest next checkpoint:** independent review of the exact OAF 0009
migration artifacts and manifest; stop before execution or activation.


### Mandatory legal-page deployment-readiness requirement

Before public launch, both `privacy-policy.html` and `terms-of-use.html` must
display actual Effective Date and Last Updated dates; no date placeholders may
remain. Confirm the remaining applicable legal review, provider privacy/payment/
email requirements, and publication checks against the services and practices
actually being launched, including approved wording, working legal/contact links,
and any required notices or interaction-specific acceptance reviewed separately.
Development retains the owner-approved date placeholders until publication dates
are established. Historical governing content and owner notes remain in force.
