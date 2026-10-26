"""Frozen offline snapshot fixture; no owner entry point or live authority.

Snapshot, classification and reporting functions retain the reviewed Step 3
helper behavior. Only identities and checkout/contract inputs are synthetic.
The original Windows operational package is unchanged. Tests must explicitly
supply checkout trust and a temporary contract before snapshot can proceed.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
PACKAGE_ID = 'a' * 32
AUTHORIZATION_ID = 'b' * 32
ORIGINAL_INTENT = 'A' * 64
MAILBOX = 'subscriber1@example.invalid'
PRIMARY_MAILBOX = 'primary@example.invalid'
CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)
EXPIRES = CREATED + timedelta(hours=24)
SUBSCRIBED = CREATED - timedelta(days=1)
VERIFIED = CREATED - timedelta(hours=1)
CONFIRM_CREATED = SUBSCRIBED
CONFIRM_ACCEPTED = VERIFIED
CONTEXT = {}
PHASES = {'preflight', 'initial', 'before-enable', 'worker-before', 'after', 'readiness'}

# Entry gates are deliberately unavailable outside an explicit synthetic test.
def verify_checkout_files():
    raise Stop('synthetic_checkout_required')


def original_contract():
    raise Stop('synthetic_contract_required')




STATUSES = {"pending", "claimed", "submitting", "accepted", "rejected", "failed", "suppressed", "uncertain"}


OUTCOMES = {None, "provider_accepted", "provider_rejected", "not_submitted", "retryable_rejection",
            "submission_unknown", "claim_expired", "suppressed", "ineligible"}


NON_SUBMISSION = {"not_submitted", "claim_expired", "suppressed", "ineligible"}


REJECTIONS = {"provider_rejected", "retryable_rejection"}


def fp(value):
    # Same canonical fingerprint as the original inert preflight helper.
    return hashlib.sha256(canonical(value).encode()).hexdigest().upper()


def classify(parent, history, now):
    """Pure ledger classification; expiry/eligibility are reported separately."""
    issues = []
    status, outcome = parent["status"], parent["outcome"]
    if status not in STATUSES or outcome not in OUTCOMES:
        issues.append("unknown_state")
    if parent["attempts"] != len(history) or [a["attempt"] for a in history] != list(range(1, len(history) + 1)):
        issues.append("attempt_count_or_sequence")
    if not 0 <= parent["attempts"] <= 3 or not parent["created_at"] <= parent["updated_at"] <= now:
        issues.append("parent_timing_or_budget")
    inflight = status in {"claimed", "submitting"}
    if inflight != (parent["claim_digest"] is not None and parent["lease_until"] is not None):
        issues.append("claim_fields")
    if not inflight and (parent["claim_digest"] is not None or parent["lease_until"] is not None):
        issues.append("residual_claim_fields")
    if parent["next_attempt_at"] is not None and (status not in {"pending", "failed"} or parent["attempts"] >= 3):
        issues.append("retry_fields")
    if (status == "accepted") != (parent["accepted_at"] is not None):
        issues.append("acceptance_fields")
    if status in {"accepted", "failed", "rejected", "uncertain"} and not history:
        issues.append("missing_attempt_history")
    accepted = [a for a in history if a["outcome"] == "provider_accepted"]
    acceptance_recorded = bool(accepted or status == "accepted" or outcome == "provider_accepted" or parent["accepted_at"])
    unresolved = False
    for index, a in enumerate(history):
        finished, submitting = a["finished_at"], a["submitting_at"]
        if a["outcome"] not in OUTCOMES or not parent["created_at"] <= a["claimed_at"] <= now:
            issues.append("attempt_state_or_time")
        if submitting is not None and not a["claimed_at"] <= submitting <= now:
            issues.append("submission_time")
        if finished is not None and not (a["claimed_at"] <= finished <= now and
                                         (submitting is None or submitting <= finished)):
            issues.append("finish_time")
        if (finished is None) != (a["outcome"] is None):
            issues.append("attempt_completion")
        if finished is None and (index != len(history) - 1 or not inflight):
            issues.append("unfinished_attempt")
        if index and (history[index - 1]["finished_at"] is None or
                      history[index - 1]["finished_at"] > a["claimed_at"]):
            issues.append("attempt_order")
        if a["outcome"] in {"claim_expired", "suppressed", "ineligible"} and submitting is not None:
            issues.append("pre_submission_outcome_conflict")
        if a["outcome"] in {"provider_accepted", *REJECTIONS, "submission_unknown"} and submitting is None:
            issues.append("missing_submission_boundary")
        if a["provider_message_id"] is not None and a["outcome"] not in {"provider_accepted", "submission_unknown"}:
            issues.append("unexpected_attempt_provider_reference")
        unresolved |= a["outcome"] == "submission_unknown" or (submitting is not None and finished is None)
    for reference in [parent["provider_message_id"], *(a["provider_message_id"] for a in history)]:
        if reference is not None and (type(reference) is not str or re.fullmatch(r"[A-Za-z0-9_.@<>:+/-]{1,200}", reference) is None):
            issues.append("invalid_provider_reference")
    last = history[-1] if history else None
    if inflight:
        if (last is None or last["finished_at"] is not None or outcome is not None or
                (status == "submitting") != (last["submitting_at"] is not None)):
            issues.append("inflight_attempt_binding")
        elif parent["updated_at"] != (last["claimed_at"] if status == "claimed" else last["submitting_at"]):
            issues.append("inflight_timestamp_binding")
    elif status != "suppressed" and last is not None:
        if last["outcome"] != outcome or last["finished_at"] != parent["updated_at"]:
            issues.append("terminal_attempt_binding")
    if status == "accepted":
        if (outcome != "provider_accepted" or len(accepted) != 1 or last not in accepted or
                last["finished_at"] != parent["accepted_at"] or
                last["provider_message_id"] != parent["provider_message_id"] or unresolved):
            issues.append("contradictory_acceptance")
    elif acceptance_recorded:
        issues.append("acceptance_parent_mismatch")
    elif status == "uncertain" and outcome == "submission_unknown":
        if last is None or last["provider_message_id"] != parent["provider_message_id"]:
            issues.append("uncertain_provider_reference_binding")
    elif parent["provider_message_id"] is not None:
        issues.append("unexpected_parent_provider_reference")
    if status == "pending" and (outcome is not None or history or parent["attempts"] != 0):
        issues.append("nonpristine_pending")
    if status == "pending" and (parent["next_attempt_at"] != parent["created_at"] or parent["updated_at"] != parent["created_at"]):
        issues.append("pending_schedule")
    if status == "failed" and outcome not in {"not_submitted", "retryable_rejection", "claim_expired"}:
        issues.append("failed_outcome")
    if status == "rejected" and outcome != "provider_rejected":
        issues.append("rejected_outcome")
    if status == "suppressed" and (outcome not in {"suppressed", "ineligible"} or unresolved or accepted):
        issues.append("suppression_outcome_conflict")
    if status == "uncertain" and outcome != "submission_unknown":
        issues.append("uncertain_outcome")
    if issues:
        category = "missing_or_contradictory_evidence"
    elif status == "accepted":
        category = "provider_accepted_submission"
    elif unresolved or status in {"submitting", "uncertain"}:
        category = "submission_uncertainty"
    elif status == "claimed":
        category = "claimed_pre_submission"
    elif status == "pending" or all(a["outcome"] in NON_SUBMISSION for a in history):
        category = "conclusively_recorded_non_submission"
    else:
        category = "recorded_provider_rejection"
    return dict(classification=category, issues=sorted(set(issues)), provider_acceptance_recorded=acceptance_recorded,
                submission_records=sum(a["submitting_at"] is not None for a in history),
                lease_expired=parent["lease_until"] is not None and parent["lease_until"] <= now)


def safe_attempt(a):
    return dict(attempt=a["attempt"], claimed_at=a["claimed_at"], submitting_at=a["submitting_at"],
                finished_at=a["finished_at"], outcome=a["outcome"] if a["outcome"] in OUTCOMES else "unknown",
                provider_reference_fingerprint=fp(a["provider_message_id"]) if a["provider_message_id"] else None,
                record_fingerprint=fp(a))


def work_summary(parent, history, now, purpose, expiry=None):
    result = classify(parent, history, now)
    result.update(purpose=purpose, status=parent["status"] if parent["status"] in STATUSES else "unknown",
                  outcome=parent["outcome"] if parent["outcome"] in OUTCOMES else "unknown",
                  attempts=parent["attempts"], next_attempt_at=parent["next_attempt_at"],
                  created_at=parent["created_at"], updated_at=parent["updated_at"], accepted_at=parent["accepted_at"],
                  lease_until=parent["lease_until"], claim_recorded=parent["claim_digest"] is not None,
                  expiry=expiry, expired=None if expiry is None else now >= expiry,
                  provider_reference_fingerprint=fp(parent["provider_message_id"]) if parent["provider_message_id"] else None,
                  record_fingerprint=fp(parent), attempt_records=[safe_attempt(a) for a in history])
    return result


def limits():
    contract = json.loads((BASE / "package-contract.json").read_text())
    return contract["schedule"], contract["timing"]


def check(operation, work, *, expected=True, required=True):
    """One Step 3 observation; a savepoint keeps independent SQL reads usable."""
    CONTEXT["operation"] = operation
    started=dict(stage=CONTEXT.get("phase"),operation=operation,status="STARTED",timestamp_utc=utc_now())
    if CONTEXT.get("event_directory"):
        index=CONTEXT.get("event_index",0)+1
        CONTEXT["event_index"]=index
        write_new(CONTEXT["event_directory"]/("check-%04d-started.json" % index),started)
    try:
        value = work()
    except Exception as exc:
        CONTEXT.setdefault("checks", []).append(dict(stage=CONTEXT.get("phase"), operation=operation,
            status="FAIL" if type(exc) is Stop else "ERROR", timestamp_utc=utc_now(), expected=expected, observed=None,
            reason="observation_failed", **safe_failure(exc)))
        if CONTEXT.get("event_directory"):
            write_new(CONTEXT["event_directory"]/("check-%04d-terminal.json" % index),CONTEXT["checks"][-1])
        CONTEXT["checks_failed"] = True
        if required:
            raise
        return None
    CONTEXT.setdefault("checks", []).append(dict(stage=CONTEXT.get("phase"), operation=operation,
        status="PASS", timestamp_utc=utc_now(), expected=expected, observed=True, reason="observed", predicate=None,
        exception_class=None, sqlstate=None))
    if CONTEXT.get("event_directory"):
        write_new(CONTEXT["event_directory"]/("check-%04d-terminal.json" % index),CONTEXT["checks"][-1])
    return value


def not_run(operation, reason="trust_missing"):
    CONTEXT.setdefault("checks", []).append(dict(stage=CONTEXT.get("phase"), operation=operation,
        status="NOT_RUN", expected=True, observed=None, reason=reason, predicate=None,
        exception_class=None, sqlstate=None))


class Stop(RuntimeError):
    pass


def require(ok, stage):
    if not ok:
        raise Stop(stage)


def canonical(value):
    def encode(item):
        if isinstance(item, datetime):
            require(item.tzinfo is not None, "aware_timestamp")
            return item.astimezone(timezone.utc).isoformat(timespec="microseconds")
        raise TypeError()
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest().upper()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def utc_now():
    return datetime.now(timezone.utc)


def plain(path):
    path = Path(path)
    require(path.is_absolute() and path.exists(), "existing_absolute_path")
    for parent in [path, *path.parents]:
        require(not parent.is_symlink() and not getattr(parent.lstat(), "st_file_attributes", 0) & 1024,
                "unredirected_path")
    return path


def snapshot_bindings(pins, contract, system, baseline, phase, now, pins_sha):
    """Pure comparison. A historical snapshot binds identity, never permission."""
    require(fingerprint(pins["source"]) == contract["current_reviewed_source_fingerprint"], "current_reviewed_source")
    if phase in {"after", "readiness"}:
        return  # Outcome observation has no submission/isolation permission.
    require(system["owner_sid"] == pins["owner_sid"] and system["isolated"] is True, "owner_system_evidence")
    require(system["host_trust_assumption"] == "existing_trusted_windows_host_account", "host_trust_boundary")
    if baseline:
        require(baseline["package_id"] == PACKAGE_ID and baseline["expected_authorization_id"] == AUTHORIZATION_ID
                and baseline.get("evidence_role") == "authorizing_preflight"
                and baseline["ok"] is True and baseline["phase"] == ("preflight" if phase == "initial" else "initial"),
                "fresh_independent_baseline")
        require(baseline["review_pins_sha256"] == pins_sha
                and baseline["isolation_fingerprint"] == fingerprint(system["relevant_tasks"])
                and baseline["https_fingerprint"] == fingerprint(system["https"])
                and baseline["reviewed_source_fingerprint"] == fingerprint(pins["source"]), "matching_reviewed_system")
        if phase != "after":
            observed = datetime.fromisoformat(baseline["observed_at"])
            _, timing = limits()
            require(timedelta(0) <= now - observed <= timedelta(seconds=timing["evidence_freshness_seconds"]), "fresh_owner_evidence")
    else:
        require(phase == "preflight", "execution_requires_fresh_baseline")


def window(now, start, end, phase, baseline=None):
    if phase == "after":
        return
    schedule, timing = limits()
    require(CREATED <= now < EXPIRES and end - start == timedelta(seconds=schedule["trigger_window_seconds"]), "original_expiry")
    # A running invocation may start at the very end of the trigger window.
    # Cover its entire four-minute budget plus a conservative 30-second margin.
    require(end + timedelta(seconds=schedule["execution_limit_seconds"] + schedule["expiry_margin_seconds"]) < EXPIRES, "expiry_covers_execution")
    if phase in {"preflight", "initial", "before-enable", "readiness"}:
        require(now < start and (phase != "before-enable" or start - now >= timedelta(seconds=timing["before_enable_lead_seconds"])), "future_window")
    elif phase == "worker-before":
        require(start <= now < end, "child_in_trigger_window")
    require(abs((utc_now() - now).total_seconds()) <= timing["database_clock_agreement_seconds"], "database_clock_agreement")
    if baseline is not None:
        observed = datetime.fromisoformat(baseline["observed_at"])
        require(end + timedelta(seconds=timing["snapshot_allowance_seconds"]) <
                observed + timedelta(seconds=timing["evidence_freshness_seconds"]), "freshness_covers_scheduled_child")


def accepted(parent, history):
    if len(history) != 1:
        return False
    attempt = history[0]
    message = parent["provider_message_id"]
    return (parent["status"] == "accepted" and parent["outcome"] == "provider_accepted"
            and parent["attempts"] == 1 and parent["accepted_at"] is not None
            and all(parent[k] is None for k in ("claim_digest", "lease_until", "next_attempt_at"))
            and isinstance(message, str) and re.fullmatch(r"[A-Za-z0-9_.@<>:+/-]{1,200}", message) is not None
            and attempt["attempt"] == 1 and attempt["outcome"] == "provider_accepted"
            and attempt["provider_message_id"] == message and attempt["claimed_at"] is not None
            and attempt["submitting_at"] is not None and attempt["finished_at"] == parent["accepted_at"]
            and attempt["claimed_at"] <= attempt["submitting_at"] <= attempt["finished_at"]
            and parent["updated_at"] == parent["accepted_at"])


def evaluate(data, store, phase, baseline=None, anchor=None, *, now=None):
    """Pure authority checks; data never reaches a diagnostic or evidence serializer."""
    if phase == "after":
        return observe(data, store, now, anchor)
    subscribers, verifications, parents, history, releases, release_history, changes = data
    active = [s for s in subscribers if s["unsubscribed_at"] is None]
    require(len(active) == 1 and len(subscribers) == 1, "one_original_lifecycle")
    subscriber = active[0]
    require(subscriber["created_at"] == SUBSCRIBED and subscriber["preferences_revision"] == 0,
            "original_active_revision_zero")
    require(subscriber["email"] == MAILBOX, "authoritative_mailbox")
    current = [v for v in verifications if v["subscription"] == subscriber["unsubscribe_digest"]]
    require(len(current) == 1 and current[0]["verified_at"] == VERIFIED, "original_durable_confirmation")
    current = current[0]
    require(current["issued_at"] <= VERIFIED < current["expires_at"] and VERIFIED < CREATED,
            "confirmation_timing")
    managed = [p for p in parents if p["purpose"] == "management"]
    confirmations = [p for p in parents if p["purpose"] == "confirmation"]
    require(len(managed) == 1 and len(confirmations) == 1 and len(parents) == 2,
            "exact_mailbox_intent_inventory")
    require(not releases and not release_history and not changes, "zero_release_or_preference_work")
    target, confirmation = managed[0], confirmations[0]
    require(confirmation["subscription"] == subscriber["unsubscribe_digest"]
            and confirmation["token_digest"] == current["token_digest"]
            and confirmation["created_at"] == CONFIRM_CREATED
            and confirmation["accepted_at"] == CONFIRM_ACCEPTED, "original_confirmation_identity")
    previous_attempts = [a for a in history if a["intent"] == confirmation["intent"]]
    require(accepted(confirmation, previous_attempts), "consistent_confirmation_acceptance")
    require(target["subscription"] == subscriber["unsubscribe_digest"] and target["management_revision"] == 0
            and target["created_at"] == CREATED and target["created_at"] + timedelta(hours=24) == EXPIRES,
            "original_management_identity_expiry")
    require(re.fullmatch(r"[0-9a-f]{64}", target["intent"]) is not None, "intent_context")
    token = store._management_token(target)
    require(hmac.compare_digest(target["token_digest"], store._digest("management-recovery", token)),
            "protected_recovery_digest")
    del token
    target_history = [a for a in history if a["intent"] == target["intent"]]
    require(len(history) == len(previous_attempts) + len(target_history), "no_orphan_attempts")
    identity = {"subscriber_fingerprint": fingerprint(subscribers),
                "verification_fingerprint": fingerprint(verifications),
                "confirmation_fingerprint": fingerprint([confirmation, previous_attempts]),
                "immutable_fingerprint": fingerprint({k: target[k] for k in
                    ("intent", "subscription", "token_digest", "purpose", "management_revision", "created_at")}),
                "intent_ids": [fingerprint(target["intent"])],
                "target_release_change_fingerprint": fingerprint([releases, release_history, changes]),
                "lifecycle_count": len(subscribers)}
    require(anchor is not None and identity["intent_ids"] == [ORIGINAL_INTENT], "exact_original_intent")
    for name, value in identity.items():
        require(anchor[name] == value, "original_" + name)
    if baseline:
        for name, value in identity.items():
            require(baseline[name] == value, "matching_" + name)
    if phase != "after":
        require(target["status"] == "pending" and target["attempts"] == 0 and not target_history,
                "pristine_unattempted_intent")
        require(target["next_attempt_at"] == CREATED and target["updated_at"] == CREATED,
                "original_due_time")
        require(all(target[k] is None for k in ("claim_digest", "lease_until", "outcome", "provider_message_id", "accepted_at")),
                "no_prior_submission")
    else:
        require(accepted(target, target_history), "exactly_one_consistent_provider_acceptance")
    identity.update(subscriber_unchanged=True, accepted_confirmation_unchanged=True,
        outcomes=[dict(intent=identity["intent_ids"][0], status=target["status"], outcome=target["outcome"],
            attempts=target["attempts"], submission_records=sum(a["submitting_at"] is not None for a in target_history),
            provider_acceptance_recorded=False, provider_reference_fingerprint=None)],
        outstanding=1, uncertain=0, release_deliveries=0, observation_complete=True,
        submission_eligible=True, execution_success=False, delivery_or_retry_authorized=False)
    return identity


def observe(data, store, now, anchor):
    """Use the reviewed reconciliation classifier; observation never authorizes send."""
    subscribers, verifications, parents, history, releases, release_history, changes = data
    targets = [p for p in parents if fingerprint(p["intent"]) == ORIGINAL_INTENT]
    identity = dict(subscriber_fingerprint=fingerprint(subscribers),
        verification_fingerprint=fingerprint(verifications),
        target_release_change_fingerprint=fingerprint([releases, release_history, changes]),
        lifecycle_count=len(subscribers), intent_ids=[fingerprint(p["intent"]) for p in targets])
    confirmations = [p for p in parents if p["purpose"] == "confirmation"]
    identity["confirmation_fingerprint"] = fingerprint([confirmations[0],
        [a for a in history if a["intent"] == confirmations[0]["intent"]]]) if len(confirmations) == 1 else None
    identity["immutable_fingerprint"] = fingerprint({k: targets[0][k] for k in
        ("intent", "subscription", "token_digest", "purpose", "management_revision", "created_at")}) if len(targets) == 1 else None
    checks = {k: value == anchor.get(k) for k, value in identity.items()}
    key_matches = None if store is None else False
    if len(targets) == 1 and store is not None:
        try:
            token = store._management_token(targets[0])
            key_matches = hmac.compare_digest(targets[0]["token_digest"], store._digest("management-recovery", token))
            del token
        except Exception:
            pass  # No capability or private exception enters observation.
    outcomes = []
    for target in targets:
        attempts = [a for a in history if a["intent"] == target["intent"]]
        outcome = work_summary(target, attempts, now, "management", EXPIRES)
        outcome["intent"] = fingerprint(target["intent"])
        if outcome["classification"] == "conclusively_recorded_non_submission" and now >= EXPIRES:
            outcome["classification"] = "expired_intent"
        outcomes.append(outcome)
    complete = len(targets) == 1
    exact_inventory = (len(parents)==2 and len(confirmations)==1 and not releases and not release_history and not changes
        and len(history)==sum(a["intent"] in {targets[0]["intent"],confirmations[0]["intent"]} for a in history)) if complete and len(confirmations)==1 else False
    identity.update(observation_complete=complete, submission_eligible=False,
        execution_success=bool(complete and exact_inventory and all(checks.values()) and
            accepted(targets[0], [a for a in history if a["intent"] == targets[0]["intent"]]) and
            targets[0]["accepted_at"] < EXPIRES and
            outcomes[0]["classification"] == "provider_accepted_submission"),
        predicate=None if complete else "exact_original_intent", identity_checks=checks,
        protected_key_matches_original=key_matches,
        subscriber_unchanged=checks["subscriber_fingerprint"],
        accepted_confirmation_unchanged=checks["confirmation_fingerprint"], outcomes=outcomes,
        expired=now >= EXPIRES, uncertain=sum(o["classification"] == "submission_uncertainty" for o in outcomes),
        outstanding=sum(o["status"] in {"pending", "failed", "claimed", "submitting"} for o in outcomes),
        release_deliveries=len(releases), delivery_or_retry_authorized=False)
    return identity


def snapshot(phase, directory, start, end, baseline):
    CONTEXT.update(operation="reviewed_checkout", phase=phase, database_identity_verified=False)
    try:
        pins = check("reviewed_checkout", verify_checkout_files)
        contract = check("original_contract", original_contract)
        require(phase in PHASES, "phase")
        plain(directory)
        require(directory.parent == BASE and re.fullmatch(r"(?:preflight|run|readiness)-[0-9a-f]{32}", directory.name), "evidence_directory")
        system = json.loads(plain(directory / (phase + "-system.json")).read_text(encoding="utf-8-sig"))
        check("owner_source_trust", lambda: require(system.get("trust_established") is True
              and system.get("owner_sid") == pins["owner_sid"], "owner_source_trust"))
        check("snapshot_bindings", lambda: snapshot_bindings(pins, contract, system, baseline, phase, utc_now(), sha(BASE / "review-pins.json")))
    except Exception:
        for operation in ("protected_configuration", "readonly_engine", "database_inventory", "primary_inventory"):
            not_run(operation)
        raise
    # Protected imports/loaders remain inside the separately gated owner entry.
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine, event, select, text, func, bindparam
    from oaf_website.database_config import load_testing_database_config, _read_settings, _validate_environment
    from oaf_website.state_requests import _verify_checkout
    from oaf_website.local_testing import recognition_secret
    from oaf_website.brevo import load_brevo_config, TestingRecipientScope
    from oaf_website.confirmation_outbox import ConfirmationOutboxStore
    from oaf_website.notification_management_schema import notifications, intents, changes, NOTIFICATION_MUTABLE
    from oaf_website.confirmation_outbox_schema import confirmation_attempts, MUTABLE as OUTBOX_MUTABLE
    from oaf_website.notification_delivery_schema import verification, suppressions, deliveries, attempts, events, MUTABLE as DELIVERY_MUTABLE
    try:
        def configuration():
            for path in ((ROOT / "config/local/database.toml",) if phase in {"after", "readiness"} else (ROOT / "config/local/database.toml", ROOT / "config/local/state-request-recognition.dpapi")):
                plain(path)
            # Validate all nonsecret settings and environment BEFORE credentials.
            _validate_environment(dict(os.environ), "testing")
            _read_settings(ROOT / "config/local/database.toml", "testing")
            config = load_testing_database_config()
            require(config.profile == "testing" and config.url.database == "oaf_website_test"
                and config.url.username == "oaf_website_test_app" and config.url.host == "127.0.0.1"
                and config.url.port == 5432, "testing_config_identity")
            return config
        config = check("configuration_settings", configuration)
    except Exception:
        for operation in ("readonly_engine", "database_inventory", "primary_inventory"):
            not_run(operation)
        raise
    engine = None
    result = dict(observation_complete=False, submission_eligible=False, execution_success=False,
                  delivery_or_retry_authorized=False)
    try:
        engine = check("readonly_engine", lambda: create_engine(config.url, echo=False, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "require_auth": "scram-sha-256", "application_name": "oaf_step3_readonly",
                "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000"}))
        event.listen(engine, "checkout", lambda dbapi, record, proxy: _verify_checkout(config, dbapi, record, proxy))
        with engine.connect().execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True) as c:
            tx = c.begin()
            try:
                # Trust failures stop dependent SQL. Rollback/disposal always run.
                check("readonly_repeatable_read", lambda: require(c.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
                    and c.execute(text("SHOW transaction_isolation")).scalar_one() == "repeatable read", "readonly_repeatable_read"))
                check("exact_database_identity", lambda: require(tuple(c.execute(text("SELECT current_database(), current_user, session_user, host(inet_server_addr()), inet_server_port(), current_setting('server_version_num')::int / 10000")).one()) ==
                    ("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app", "127.0.0.1", 5432, 17), "exact_database_identity"))
                CONTEXT["database_identity_verified"] = True
                def protected_configuration():
                    # Only the runtime DB credential was needed for identity.
                    # Other protected material remains inaccessible until then.
                    provider = load_brevo_config("testing", credential_account="brevo-api")
                    secret = recognition_secret(require_existing=True)
                    protected = fingerprint([hashlib.sha256(secret).hexdigest(), hashlib.sha256(provider.api_key.encode()).hexdigest(),
                        sha(ROOT / "config/local/database.toml"), sha(ROOT / "config/local/state-request-recognition.dpapi")])
                    require(protected == contract["current_configuration_fingerprint"], "current_protected_configuration")
                    if baseline and phase not in {"after", "readiness"}:
                        require(protected == baseline["configuration_fingerprint"], "protected_configuration_unchanged")
                    return secret, protected
                observing = phase in {"after", "readiness"}
                if observing:
                    # A verified read-only DB identity is sufficient to observe
                    # acknowledged outcomes. No provider key or DPAPI key is read.
                    secret, protected, store = None, None, None
                    not_run("protected_configuration", "send_readiness_not_required")
                else:
                    secret, protected = check("protected_configuration", protected_configuration)
                    store = ConfirmationOutboxStore(engine, secret, "testing", recipient_scope=TestingRecipientScope("testing", MAILBOX), management_enabled=True)
                CONTEXT["protected_configuration_verified"]=not observing
                def read(operation, work):
                    def isolated_read():
                        with c.begin_nested():
                            return work()
                    return check(operation, isolated_read, required=False)
                now = read("database_clock", lambda: c.execute(select(func.clock_timestamp())).scalar_one())
                timeout_values = read("session_timeouts", lambda: tuple(c.execute(text("SELECT current_setting('statement_timeout'),current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout')")).one()))
                check("bounded_session_timeouts",lambda:require(timeout_values==("10s","5s","30s"),"bounded_session_timeouts"),required=False)
                # Expiry and eligibility never suppress independent read-only checks.
                if observing:
                    not_run("database_clock_and_window", "send_readiness_not_required")
                elif now is None:
                    not_run("database_clock_and_window", "database_clock_unknown")
                else:
                    check("database_clock_and_window", lambda: window(now, start, end, phase, baseline), required=False)
                mailbox = select(notifications.c.unsubscribe_digest).where(notifications.c.email == bindparam("mailbox"))
                intent_refs = select(intents.c.intent).where(intents.c.subscription.in_(mailbox))
                def rows(table, predicate, order, params):
                    found = [dict(r) for r in c.execute(select(table).where(predicate).order_by(*order).limit(257), params).mappings()]
                    require(len(found) <= 256, "mailbox_inventory_bound")
                    return found
                specifications = (
                    (notifications, notifications.c.email == bindparam("mailbox"), [notifications.c.unsubscribe_digest]),
                    (verification, verification.c.subscription.in_(mailbox), [verification.c.subscription]),
                    (intents, intents.c.subscription.in_(mailbox), [intents.c.intent]),
                    (confirmation_attempts, confirmation_attempts.c.intent.in_(intent_refs), [confirmation_attempts.c.intent, confirmation_attempts.c.attempt]),
                    (deliveries, deliveries.c.subscription.in_(mailbox), [deliveries.c.event_id, deliveries.c.subscription]),
                    (attempts, attempts.c.subscription.in_(mailbox), [attempts.c.event_id, attempts.c.subscription, attempts.c.attempt]),
                    (changes, changes.c.subscription.in_(mailbox), [changes.c.action_digest]))
                data = [read("inventory_"+table.name, lambda table=table,predicate=predicate,order=order: rows(table,predicate,order,{"mailbox":MAILBOX}))
                        for table,predicate,order in specifications]
                inventory_complete = all(item is not None for item in data)
                if inventory_complete and now is not None:
                    result = check("ledger_classification", lambda: evaluate(data, store, "after" if phase == "readiness" else phase,
                        baseline, contract["original_identities"], now=now), required=False) or result
                    CONTEXT["known_result"] = dict(result)
                else:
                    not_run("ledger_classification", "database_clock_unknown" if now is None else "incomplete_inventory")
                # Independently scoped primary preservation, never a target alias.
                primary = [read("primary_"+table.name, lambda table=table,predicate=predicate,order=order: rows(table,predicate,order,{"mailbox":PRIMARY_MAILBOX}))
                           for table,predicate,order in specifications]
                def suppression(address):
                    return rows(suppressions, suppressions.c.mailbox_digest == bindparam("digest"), [suppressions.c.mailbox_digest], {"digest":store._digest("mailbox",address)})
                if observing:
                    not_run("primary_suppression", "send_readiness_not_required")
                    not_run("durable_suppression", "send_readiness_not_required")
                    blocked = None
                else:
                    primary.append(read("primary_suppression",lambda:suppression(PRIMARY_MAILBOX)))
                    blocked = read("durable_suppression",lambda:suppression(MAILBOX))
                release_ids = select(deliveries.c.event_id).where(deliveries.c.subscription.in_(mailbox))
                releases = read("release_event_inventory", lambda:rows(events, events.c.event_id.in_(release_ids),[events.c.event_id],{"mailbox":MAILBOX}))
                competitors = read("database_session_visibility", lambda:c.execute(text("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE datname=current_database() AND usename=current_user AND pid<>pg_backend_pid() AND (state IS NULL OR state <> :idle OR application_name = :processor)"),
                    {"idle":"idle","processor":"oaf_website_confirmation_processor"}).scalar_one())
                relevant_activity = read("relevant_database_activity", lambda:c.execute(text("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE pid<>pg_backend_pid() AND (datname IN (:testing,:development) OR usename IN (:runtime,:migrator,:owner)) AND (state IS NULL OR state<>:idle)"),
                    {"testing":"oaf_website_test","development":"oaf_website_dev","runtime":"oaf_website_test_app","migrator":"oaf_website_test_migrator","owner":"oaf_website_test_schema_owner","idle":"idle"}).scalar_one())
                # Catalog observations use public catalogs/privilege functions only.
                # No Alembic row, SET ROLE, DDL or write-privilege experiment.
                schema_ok = read("application_schema", lambda:c.execute(text("SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oaf_website' AND r.rolname='oaf_website_test_schema_owner') AND has_schema_privilege(current_user,'oaf_website','USAGE') AND NOT has_schema_privilege(current_user,'oaf_website','CREATE')")).scalar_one())
                privileges = []
                mutable = {**DELIVERY_MUTABLE, **OUTBOX_MUTABLE, notifications.name:NOTIFICATION_MUTABLE,changes.name:()}
                for table, _, _ in (*specifications, (suppressions,None,None),(events,None,None)):
                    privileges.append(read("privilege_"+table.name, lambda table=table:c.execute(text("SELECT has_table_privilege(current_user,:relation,'SELECT') AND has_table_privilege(current_user,:relation,'INSERT') AND NOT has_table_privilege(current_user,:relation,'UPDATE') AND NOT has_table_privilege(current_user,:relation,'DELETE') AND NOT has_table_privilege(current_user,:relation,'TRUNCATE') AND NOT has_table_privilege(current_user,:relation,'REFERENCES') AND NOT has_table_privilege(current_user,:relation,'TRIGGER') AND NOT has_table_privilege(current_user,:relation,'SELECT WITH GRANT OPTION') AND NOT has_table_privilege(current_user,:relation,'INSERT WITH GRANT OPTION') AND COALESCE((SELECT bool_and(has_column_privilege(current_user,:relation,a.attname,'UPDATE') = (a.attname::text = ANY(CAST(:updates AS text[]))) AND NOT has_column_privilege(current_user,:relation,a.attname,'UPDATE WITH GRANT OPTION')) FROM pg_catalog.pg_attribute a WHERE a.attrelid=to_regclass(:relation) AND a.attnum>0 AND NOT a.attisdropped),false)"),
                        {"relation":"oaf_website."+table.name,"updates":list(mutable[table.name])}).scalar_one()))
                check("schema_and_privilege_predicates",lambda:require(schema_ok is True and all(v is True for v in privileges),"schema_and_privilege_predicates"),required=False)
                primary_complete = not observing and all(item is not None for item in primary) and result.get("protected_key_matches_original", True)
                primary_fp = fingerprint(primary) if primary_complete else None
                primary_matches = None if baseline is None or not primary_complete else primary_fp == baseline.get("primary_preservation_fingerprint")
                if phase not in {"after","readiness"}:
                    check("no_durable_oaf_suppression", lambda:require(blocked == [],"no_durable_oaf_suppression"), required=False)
                    check("no_competing_database_activity",lambda:require(competitors == 0,"no_competing_database_activity"),required=False)
                    if baseline:
                        check("primary_preservation",lambda:require(primary_matches is True,"primary_preservation"),required=False)
                _, timing = limits()
                if now is None:
                    not_run("bounded_snapshot_duration", "database_clock_unknown")
                    not_run("scoped_intent_classification", "database_clock_unknown")
                else:
                    check("bounded_snapshot_duration",lambda:require(timedelta(0) <= utc_now()-now < timedelta(seconds=timing["snapshot_allowance_seconds"]),"bounded_snapshot_duration"),required=False)
                complete = bool(now is not None and inventory_complete and primary_complete and blocked is not None and releases is not None and competitors is not None and relevant_activity is not None and timeout_values is not None
                    and schema_ok is not None and all(v is not None for v in privileges))
                if observing:
                    complete = now is not None and inventory_complete
                eligible = phase not in {"after","readiness"} and complete and not CONTEXT.get("checks_failed",False)
                result.update(ok=eligible if phase not in {"after","readiness"} else True,
                    observation_complete=complete and bool(result.get("observation_complete",False)),
                    submission_eligible=eligible, execution_success=bool(phase=="after" and result.get("execution_success")
                        and complete and primary_matches is True and system.get("isolated") is True),
                    phase=phase,package_id=PACKAGE_ID,expected_authorization_id=AUTHORIZATION_ID,
                    evidence_role="readiness_diagnostic" if phase=="readiness" else "outcome_observation" if phase=="after" else "authorizing_preflight",
                    observed_at=now,environment="testing",recipient=MAILBOX,database="oaf_website_test",current_user="oaf_website_test_app",
                    session_user="oaf_website_test_app",host="127.0.0.1",port=5432,postgresql_major=17,scram_required=True,read_only=True,
                    isolation="repeatable read",owner_sid=pins["owner_sid"],owner_name="synthetic-owner",intent_created_at=CREATED,
                    original_expires_at=EXPIRES,preference_revision=0,reviewed_source_fingerprint=fingerprint(pins["source"]),
                    review_pins_sha256=sha(BASE/"review-pins.json"),configuration_fingerprint=protected,current_configuration_matches=None if observing else True,
                    system_fingerprint=fingerprint(system),isolation_fingerprint=fingerprint(system.get("relevant_tasks")),https_fingerprint=fingerprint(system.get("https")),
                    primary_preservation_fingerprint=primary_fp,primary_preservation_matches=primary_matches,primary_preservation_complete=primary_complete,
                    durable_suppression_present=None if blocked is None else bool(blocked),suppression_lookup_authoritative=blocked is not None,
                    host_execution_boundary_established=system.get("isolated",False),competing_database_sessions=competitors,
                    database_identity_verified=True,all_mailbox_lifecycles_included=inventory_complete,mailbox_delivery="NOT_OBSERVED",
                    release_events_count=None if releases is None else len(releases),release_events_fingerprint=None if releases is None else fingerprint(releases),
                    application_schema_matches=schema_ok,runtime_privileges_observed=all(v is not None for v in privileges),
                    runtime_privileges_match=all(v is True for v in privileges),planned_start=start,planned_end=end,
                    latest_execution_end=end+timedelta(seconds=contract["schedule"]["execution_limit_seconds"]+contract["schedule"]["expiry_margin_seconds"]),
                    fresh_until=None if now is None else now+timedelta(seconds=timing["evidence_freshness_seconds"]),
                    latest_owner_entry=None if now is None else min(now+timedelta(seconds=timing["evidence_freshness_seconds"]-contract["schedule"]["lead_seconds"]-contract["schedule"]["trigger_window_seconds"]-timing["snapshot_allowance_seconds"]),
                        EXPIRES-timedelta(seconds=contract["schedule"]["lead_seconds"]+contract["schedule"]["trigger_window_seconds"]+contract["schedule"]["execution_limit_seconds"]+contract["schedule"]["expiry_margin_seconds"])),
                    owner_preparation_budget_seconds=contract["schedule"]["lead_seconds"]-timing["before_enable_lead_seconds"],
                    relevant_database_activity=relevant_activity,
                    inventories=[dict(scope=scope,table=specifications[index][0].name,count=None if rows_ is None else len(rows_),
                        record_fingerprint=None if rows_ is None else fingerprint(rows_))
                        for scope,contents in (("target",data),("primary",primary[:len(specifications)])) for index,rows_ in enumerate(contents)],
                    scoped_intent_outcomes=[] if now is None or data[2] is None or data[3] is None else [dict(work_summary(parent,[a for a in data[3] if a["intent"]==parent["intent"]],now,parent["purpose"],parent["created_at"]+timedelta(hours=24)),intent=fingerprint(parent["intent"])) for parent in data[2]],
                    delivery_or_retry_authorized=False)
                if not schema_ok or not all(v is True for v in privileges):
                    result.update(ok=phase in {"after","readiness"},submission_eligible=False,execution_success=False)
                CONTEXT["known_result"] = dict(result)
            except Exception:
                if not CONTEXT.get("database_identity_verified") or not CONTEXT.get("protected_configuration_verified"):
                    for operation in ("database_inventory","primary_inventory","application_schema","database_session_visibility"):
                        not_run(operation)
                raise
            finally:
                check("rollback",tx.rollback)
                CONTEXT["rollback_completed"]=True
    finally:
        if engine is not None:
            check("dispose",engine.dispose)
            CONTEXT["connection_disposed"]=True
    return result


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def safe_failure(exc):
    predicate = str(exc) if type(exc) is Stop and re.fullmatch(r"[a-z0-9_]{1,80}", str(exc)) else None
    wrapped = getattr(exc, "orig", None)
    sqlstate = getattr(wrapped, "sqlstate", None) or getattr(exc, "sqlstate", None)
    return dict(predicate=predicate,
        exception_class=type(exc).__name__ if type(exc).__name__ in SAFE_CLASSES else "Exception",
        sqlstate=sqlstate if type(sqlstate) is str and re.fullmatch(r"[A-Z0-9]{5}", sqlstate) else None)


SAFE_CLASSES = {"Exception", "Stop", "RuntimeError", "ValueError", "TypeError", "KeyError", "OSError", "IOError",
    "PermissionError", "FileExistsError", "FileNotFoundError", "OperationalError", "ProgrammingError", "DBAPIError",
    "DatabaseError", "InterfaceError", "TimeoutError", "KeyboardInterrupt", "SystemExit", "JSONDecodeError"}
