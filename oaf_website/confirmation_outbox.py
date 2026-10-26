"""Internal confirmation outbox. No route, scheduler, credential lookup or activation."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets

from sqlalchemy import insert, select, text, func

from .notification_delivery import NotificationDeliveryStore, OUTCOMES
from .notification_delivery_schema import verification, suppressions
from .notification_schema import notifications
from .confirmation_outbox_schema import intents, confirmation_attempts
from .brevo import BrevoAdapter, BrevoConfig, BrevoConfigurationError, ProviderOutcome
from .brevo import validate_recipient_scope
from .notification_dispatch import BatchResult, safe_failure
from .notification_messages import secure_confirmation_page, verification_message, management_message


def capability(store, subscription, intent):
    # Fixed-width lifecycle/context, explicit purpose/version/environment. The
    # persisted random 256-bit context is NOT a bearer without the protected key.
    return store._digest("confirmation-recovery", store.environment + ":" + subscription + ":" + intent)


def finish(store, connection, record, now, outcome, status, message_id=None):
    retry = now + timedelta(seconds=60 * 5 ** (record["attempts"] - 1)) if status == "failed" and record["attempts"] < 3 else None
    store._update(connection, intents, dict(intent=record["intent"]), status=status,
                  claim_digest=None, lease_until=None, next_attempt_at=retry,
                  outcome=outcome, provider_message_id=message_id, updated_at=now,
                  accepted_at=now if status == "accepted" else None)
    if record["status"] in {"claimed", "submitting"}:
        store._update(connection, confirmation_attempts,
                      dict(intent=record["intent"], attempt=record["attempts"]),
                      finished_at=now, outcome=outcome, provider_message_id=message_id)


def pending_recovery(store, connection, now, subscription, *, purpose="confirmation", revision=None, issued_at=None):
    """Coalesce still-bounded work without renewing its expiry or retry budget."""
    for previous in sorted(store._rows(connection, intents, subscription=subscription),
                           key=lambda row: row["created_at"], reverse=True):
        if (previous.get("purpose", "confirmation") == purpose
                and previous.get("management_revision") == revision
                and previous["created_at"] <= now < previous["created_at"] + timedelta(hours=24)
                and (issued_at is None or previous["created_at"] >= issued_at)
                and (previous["status"] in {"pending", "claimed", "submitting", "uncertain"}
                     or previous["status"] == "failed" and previous["attempts"] < 3
                     and previous["next_attempt_at"] is not None)):
            return previous
    return None


def reserve_confirmation(store, connection, now, subscriber, record):
    subscription = subscriber["unsubscribe_digest"]
    previous = pending_recovery(store, connection, now, subscription,
                                issued_at=record["issued_at"] if record else None)
    if previous is not None:
        return capability(store, subscription, previous["intent"])
    context = secrets.token_hex(32)
    token = capability(store, subscription, context)
    values = dict(token_digest=store._digest("confirmation", token), issued_at=now,
                  expires_at=now + timedelta(hours=24), verified_at=None)
    # A replacement is reserved separately. Keep the current confirmation's
    # original authority/expiry until a still-eligible replacement is accepted.
    if record is None:
        connection.execute(insert(verification).values(subscription=subscription, **values))
    # Do not hide a random-context collision: the whole reservation must roll back.
    connection.execute(insert(intents).values(intent=context, subscription=subscription,
        token_digest=values["token_digest"], status="pending", attempts=0, claim_digest=None, lease_until=None,
        next_attempt_at=now, outcome=None, provider_message_id=None,
        created_at=now, updated_at=now, accepted_at=None))
    for previous in store._rows(connection, intents, subscription=subscription):
        if (previous.get("purpose", "confirmation") == "confirmation"
                and previous["intent"] != context and previous["status"] in {"pending", "claimed", "failed"}):
            finish(store, connection, previous, now, "ineligible", "suppressed")
    # Compatibility-sensitive internal return; never used as the durable handoff.
    return token


def intent_fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=lambda item: item.astimezone(timezone.utc).isoformat(timespec="microseconds")).encode()).hexdigest().upper()


def intent_identity(record):
    return intent_fingerprint({key: record[key] for key in
        ("intent", "subscription", "token_digest", "purpose", "management_revision", "created_at")})


class ManagementIntentMismatch(ValueError):
    """The exceptional batch cannot acquire authority over this work."""
    def __init__(self, predicate="exact_intent_scope"):
        self.predicate = predicate
        super().__init__("Exceptional intent scope differs.")


@dataclass(frozen=True, repr=False)
class ManagementIntentScope:
    # Additional constraints on the existing queue, never execution authorization.
    intent_fingerprint: str = field(repr=False)
    identity_fingerprint: str = field(repr=False)
    deadline: datetime
    revision: int = 0
    attempt: int = 1

    @property
    def purpose(self):
        return "management"

    def _valid_revision(self):
        return type(self.revision) is int and self.revision >= 0

    def __post_init__(self):
        if (any(type(value) is not str or re.fullmatch(r"[A-F0-9]{64}", value) is None
                for value in (self.intent_fingerprint, self.identity_fingerprint))
                or type(self.deadline) is not datetime or self.deadline.utcoffset() != timedelta(0)
                or not self._valid_revision()
                or type(self.attempt) is not int or self.attempt != 1):
            raise ValueError("Invalid exceptional intent scope.")

    def require(self, record, now, *, submission=True):
        if record is None:
            raise ManagementIntentMismatch()
        conditions = (
            (record.get("purpose") == self.purpose, "intent_purpose"),
            (record.get("management_revision") == self.revision, "intent_revision"),
            (intent_fingerprint(record["intent"]) == self.intent_fingerprint, "intent_identity"),
            (intent_identity(record) == self.identity_fingerprint, "intent_lifecycle_binding"),
            (self.deadline <= record["created_at"] + timedelta(hours=24) and record["created_at"] <= now
                and (not submission or now < self.deadline), "intent_deadline"),
            (record["attempts"] <= self.attempt and not (record["status"] in {"pending", "failed"}
                and record["attempts"] >= self.attempt), "intent_attempt"),
        )
        for allowed, predicate in conditions:
            if not allowed:
                raise ManagementIntentMismatch(predicate)


@dataclass(frozen=True, repr=False)
class ConfirmationIntentScope(ManagementIntentScope):
    # Same exceptional constraint, with explicit original verification anchors.
    revision: None = None
    issued_at: datetime = field(kw_only=True)

    @property
    def purpose(self):
        return "confirmation"

    def _valid_revision(self):
        return self.revision is None

    def __post_init__(self):
        super().__post_init__()
        if (type(self.issued_at) is not datetime or self.issued_at.utcoffset() != timedelta(0)
                or self.deadline != self.issued_at + timedelta(hours=24)):
            raise ValueError("Original confirmation issuance and expiry required.")

    def require(self, record, now, *, submission=True):
        super().require(record, now, submission=submission)
        if record["created_at"] != self.issued_at:
            raise ManagementIntentMismatch("intent_lifecycle_binding")


class ConfirmationOutboxStore(NotificationDeliveryStore):
    def __init__(self, engine, secret, environment, *, recipient_scope=None, management_enabled=False, intent_scope=None):
        validate_recipient_scope(recipient_scope, environment)
        super().__init__(engine, secret, environment, management_enabled=management_enabled)
        self.recipient_scope = recipient_scope
        if intent_scope is not None and (type(intent_scope) not in (ManagementIntentScope, ConfirmationIntentScope)
                or environment != "testing" or recipient_scope is None or not management_enabled):
            raise ValueError("Exceptional intent scope requires controlled TESTING management.")
        self.intent_scope = intent_scope
        self.first_failure = None

    def _failure(self, operation, exc=None, *, side_effects="database_transaction_unacknowledged", predicate="operation_failed", context=None):
        if self.first_failure is None:
            self.first_failure = safe_failure("outbox", operation, exc, side_effects=side_effects, predicate=predicate,
                context=context, provider_outcome=getattr(self, "_observed_provider_outcome", None) if context == "outcome" else None)

    @contextmanager
    def _transaction(self, operation="selection_recovery"):
        boundary = "database_begin"
        origin = failure = None
        try:
            with self.engine.begin() as connection:
                try:
                    boundary = "advisory_lock"
                    connection.execute(text("SELECT pg_catalog.pg_advisory_xact_lock(67210401)"))
                    boundary = "database_clock"
                    now = connection.execute(select(func.clock_timestamp())).scalar_one()
                    boundary = operation
                    yield connection, now
                    if operation == "preparation" and self.intent_scope is not None:
                        if connection.execute(select(func.clock_timestamp())).scalar_one() >= self.intent_scope.deadline:
                            raise ManagementIntentMismatch("intent_deadline")
                except Exception as exc:
                    origin = exc
                    failure = safe_failure("outbox", boundary, exc,
                        predicate=exc.predicate if type(exc) is ManagementIntentMismatch else "operation_failed", context=operation)
                    raise
                boundary = "transaction_commit"
        except Exception as exc:
            if failure is not None:
                failure["side_effects"] = "database_rolled_back" if exc is origin else "database_rollback_uncertain"
                exc.notification_failure = failure
                if exc is not origin:
                    exc.notification_rollback_failure = safe_failure("outbox", "transaction_rollback", exc,
                        side_effects="database_rollback_uncertain", preserve=False)
            self._failure(boundary, exc, side_effects="database_commit_uncertain" if boundary == "transaction_commit"
                else "database_transaction_unacknowledged", predicate=exc.predicate if type(exc) is ManagementIntentMismatch else "operation_failed", context=operation)
            raise

    def _require_scoped_record(self, connection, record, now=None, *, submission=True):
        if self.recipient_scope is not None:
            subscriber = self._get(connection, notifications,
                                   unsubscribe_digest=record["subscription"])
            self.recipient_scope.require(None if subscriber is None else subscriber["email"])
        if self.intent_scope is not None:
            if now is None:
                now = connection.execute(select(func.clock_timestamp())).scalar_one()
            self.intent_scope.require(record, now, submission=submission)
            if type(self.intent_scope) is ConfirmationIntentScope and submission:
                current = self._get(connection, verification, subscription=record["subscription"])
                if (current is None or current["issued_at"] != self.intent_scope.issued_at
                        or current["expires_at"] != self.intent_scope.deadline
                        or current["token_digest"] != record["token_digest"]):
                    raise ManagementIntentMismatch("intent_lifecycle_binding")

    def _resolve_intent_scope(self, connection, now, item):
        if self.intent_scope is None:
            return None
        # Resolve only the approved fingerprint through the existing authoritative
        # mailbox/queue. No recovered private context enters invocation or logs.
        statement = select(item).where(item.c.subscription.in_(select(notifications.c.unsubscribe_digest).where(
            notifications.c.email == self.recipient_scope.mailbox))).order_by(item.c.intent).limit(257)
        rows = list(connection.execute(statement).mappings())
        if len(rows) > 256:
            raise ManagementIntentMismatch()
        found = [row for row in rows if intent_fingerprint(row["intent"]) == self.intent_scope.intent_fingerprint]
        if len(found) != 1:
            raise ManagementIntentMismatch()
        self._require_scoped_record(connection, found[0], now)
        return found[0]

    def _scoped(self, statement, table=intents, exact=None, *, recovery=False):
        if self.recipient_scope is not None:
            # Filter BEFORE ordering/LIMIT. No unrelated claim/attempt is recovered.
            statement = statement.where(table.c.subscription.in_(
                select(notifications.c.unsubscribe_digest).where(
                    notifications.c.email == self.recipient_scope.mailbox)))
        if self.intent_scope is not None:
            if exact is None:
                raise ManagementIntentMismatch()
            statement = statement.where(table.c.intent == exact["intent"], table.c.subscription == exact["subscription"],
                table.c.token_digest == exact["token_digest"], table.c.created_at == exact["created_at"],
                table.c.purpose == self.intent_scope.purpose, table.c.management_revision == self.intent_scope.revision,
                table.c.attempts <= self.intent_scope.attempt if recovery else table.c.attempts < self.intent_scope.attempt)
        return statement

    def _eligible_confirmation(self, connection, record, now):
        if record.get("purpose", "confirmation") == "management":
            return self._eligible_management(connection, record, now)
        subscriber = self._get(connection, notifications, unsubscribe_digest=record["subscription"])
        current = self._get(connection, verification, subscription=record["subscription"])
        token = capability(self, record["subscription"], record["intent"])
        same = current is not None and hmac.compare_digest(current["token_digest"], record["token_digest"])
        if (subscriber is None or current is None or subscriber["unsubscribed_at"] is not None
                or current["verified_at"] is not None or now < current["issued_at"]
                or not record["created_at"] <= now < record["created_at"] + timedelta(hours=24)
                or (now >= current["expires_at"] if same else record["created_at"] <= current["issued_at"])
                or self._get(connection, suppressions,
                             mailbox_digest=self._digest("mailbox", subscriber["email"]))):
            return None
        if not hmac.compare_digest(record["token_digest"], self._digest("confirmation", token)):
            raise ValueError("Protected confirmation recovery unavailable.")
        return subscriber, token

    def _eligible_management(self, connection, record, now):
        if not self.management_enabled:
            return None
        subscriber = self._get(connection, notifications, unsubscribe_digest=record["subscription"])
        verified = self._get(connection, verification, subscription=record["subscription"])
        if (subscriber is None or subscriber["unsubscribed_at"] is not None
                or subscriber["preferences_revision"] != record["management_revision"]
                or verified is None or verified["verified_at"] is None
                or now < record["created_at"] or now >= record["created_at"] + timedelta(hours=24)
                or self._get(connection, suppressions, mailbox_digest=self._digest("mailbox", subscriber["email"]))):
            return None
        token = self._management_token(record)
        if not hmac.compare_digest(record["token_digest"], self._digest("management-recovery", token)):
            raise ValueError("Protected management recovery unavailable.")
        return subscriber, token

    def _management_token(self, record):
        from .notification_management import ManagementCapabilities
        return ManagementCapabilities(self.secret, self.environment).issue(record["subscription"],
            record["management_revision"], record["created_at"], lifetime=timedelta(hours=24), context=record["intent"])

    def _owns_confirmation(self, record, claim, status):
        return (record is not None and record["status"] == status and type(claim) is str
                and re.fullmatch(r"[0-9a-f]{64}", claim) is not None
                and hmac.compare_digest(record["claim_digest"], self._digest("confirmation-claim", claim)))

    def candidates(self, limit):
        # A V2-aware processor is explicitly enabled only after migration 0006.
        # The old projection stays safe while V2 is OFF, and can process only
        # confirmation-purpose records created before activation.
        item = intents
        if self.management_enabled:
            from .notification_management_schema import intents as item
        with self._transaction() as (connection, now):
            exact = self._resolve_intent_scope(connection, now, item)
            # Bound recovery work too. Final claims/dispatch recheck authority.
            statement = select(item).where(item.c.status.in_(("claimed", "submitting")),
                item.c.lease_until <= now).order_by(item.c.intent).limit(limit)
            for record in connection.execute(self._scoped(statement, table=item, exact=exact, recovery=True)).mappings():
                self._require_scoped_record(connection, record)
                submitting = record["status"] == "submitting"
                finish(self, connection, record, now, "submission_unknown" if submitting else "claim_expired",
                       "uncertain" if submitting else "failed")
            statement = select(item.c.intent).where(item.c.status.in_(("pending", "failed")),
                item.c.attempts < 3, item.c.next_attempt_at <= now).order_by(item.c.intent).limit(limit)
            return [row["intent"] for row in connection.execute(self._scoped(statement, table=item, exact=exact)).mappings()]

    def claim_confirmation(self, intent):
        with self._transaction("claim") as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if (record is None or record["status"] not in {"pending", "failed"} or record["attempts"] >= 3
                    or record["next_attempt_at"] is None or record["next_attempt_at"] > now):
                return None
            self._require_scoped_record(connection, record)
            if self._eligible_confirmation(connection, record, now) is None:
                finish(self, connection, record, now, "ineligible", "suppressed")
                return None
            claim = secrets.token_hex(32)
            self._update(connection, intents, dict(intent=intent), status="claimed",
                         attempts=record["attempts"] + 1,
                         claim_digest=self._digest("confirmation-claim", claim),
                         lease_until=now + timedelta(minutes=5), next_attempt_at=None, updated_at=now)
            self._insert(connection, confirmation_attempts, dict(intent=intent,
                attempt=record["attempts"] + 1, claimed_at=now, submitting_at=None,
                finished_at=None, outcome=None, provider_message_id=None))
            return claim

    def prepare_confirmation(self, intent, claim, page):
        # Render before the committed submitting boundary. A preparation failure
        # records conclusive non-submission and uses the bounded safe retry policy.
        with self._transaction("preparation") as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if not self._owns_confirmation(record, claim, "claimed") or record["lease_until"] <= now:
                return None
            self._require_scoped_record(connection, record)
            eligible = self._eligible_confirmation(connection, record, now)
            if eligible is None:
                finish(self, connection, record, now, "ineligible", "suppressed")
                return None
            subscriber, token = eligible
            try:
                if record.get("purpose", "confirmation") == "management":
                    message = management_message(token, page)
                else:
                    management_token = None
                    if self.management_enabled:
                        from .notification_management import ManagementCapabilities
                        management_token = ManagementCapabilities(self.secret, self.environment).issue(
                            record["subscription"], subscriber["preferences_revision"], now)
                    from .notifications import UnsubscribeCapabilities
                    message = verification_message(token, page, management_token=management_token,
                        unsubscribe_token=UnsubscribeCapabilities(self.secret).issue(record["subscription"]))
            except Exception as exc:
                self._failure("template", exc, side_effects="submission_not_started")
                finish(self, connection, record, now, "not_submitted", "failed")
                return None
            # Recheck the locked authoritative row immediately before authorization.
            self._require_scoped_record(connection, record)
            if self.intent_scope is not None:
                # Use a fresh DB clock at the final locked submission boundary,
                # after rendering and immediately before the submitting UPDATE.
                now = connection.execute(select(func.clock_timestamp())).scalar_one()
                self._require_scoped_record(connection, record, now)
                if record["lease_until"] <= now:
                    raise ManagementIntentMismatch("intent_deadline")
            self._update(connection, intents, dict(intent=intent), status="submitting",
                         lease_until=now + timedelta(minutes=5), updated_at=now)
            self._update(connection, confirmation_attempts, dict(intent=intent, attempt=record["attempts"]),
                         submitting_at=now)
            return subscriber["email"], message

    def confirmation_outcome(self, intent, claim, outcome, message_id=None):
        if outcome not in OUTCOMES or (message_id is not None and (type(message_id) is not str
                or re.fullmatch(r"[A-Za-z0-9_.@<>:+/-]{1,200}", message_id) is None)):
            raise ValueError("Invalid sanitized confirmation outcome.")
        self._observed_provider_outcome = outcome
        with self._transaction("outcome") as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if not self._owns_confirmation(record, claim, "submitting"):
                return False
            self._require_scoped_record(connection, record, now, submission=False)
            # A provider must never turn an echoed bearer into durable correlation
            # data. Preserve the outcome but discard such a private identifier.
            private_token = (self._management_token(record) if record.get("purpose", "confirmation") == "management"
                             else capability(self, record["subscription"], intent))
            if message_id is not None and private_token in message_id:
                message_id = None
            if (outcome == "provider_accepted" and record.get("purpose", "confirmation") == "confirmation"
                    and self._eligible_confirmation(connection, record, now) is not None):
                # The accepted outcome and authority switch commit atomically.
                # A concurrent confirmation/withdrawal or expired intent wins;
                # delivery evidence never revives verified or withdrawn consent.
                self._update(connection, verification, dict(subscription=record["subscription"]),
                    token_digest=record["token_digest"], issued_at=record["created_at"],
                    expires_at=record["created_at"] + timedelta(hours=24))
            finish(self, connection, record, now, outcome, OUTCOMES[outcome], message_id)
            return True


class ConfirmationDispatcher:
    def __init__(self, store, config, confirmation_page, *, transport=None):
        if type(config) is not BrevoConfig or config.environment != store.environment:
            raise BrevoConfigurationError("Brevo configuration must match the confirmation environment.")
        self.store, self.page = store, secure_confirmation_page(confirmation_page)
        self.adapter = BrevoAdapter(config, transport=transport, recipient_scope=store.recipient_scope)

    def process(self, *, limit=20):
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Confirmation batches require 1 to 20 recipients.")
        processed = 0
        self.store.first_failure = None
        operation = "selection_recovery"
        failure = None
        try:
            for intent in self.store.candidates(limit):
                operation = "claim"
                claim = self.store.claim_confirmation(intent)
                if claim is None:
                    continue
                operation = "preparation"
                prepared = self.store.prepare_confirmation(intent, claim, self.page)
                if prepared is None:
                    continue
                if self.store.recipient_scope is not None:
                    self.store.recipient_scope.require(prepared[0])
                try:
                    operation = "provider_submit"
                    outcome = self.adapter.submit(*prepared)
                except Exception as exc:
                    failure = failure or safe_failure("outbox", operation, exc, side_effects="submission_possible")
                    outcome = ProviderOutcome("submission_unknown")
                failure = failure or getattr(outcome, "first_failure", None)
                operation = "outcome"
                if not self.store.confirmation_outcome(intent, claim, outcome.outcome, outcome.message_id):
                    return BatchResult("unavailable", processed, failure or self.store.first_failure or
                        safe_failure("outbox", operation, side_effects="submission_possible", predicate="outcome_not_acknowledged"))
                processed += 1
            return BatchResult("processed", processed, failure or self.store.first_failure)
        except KeyboardInterrupt as exc:
            exc.acknowledged_processed = processed
            raise
        except Exception as exc:
            # Includes uncertain commits and preparation failures. No private data,
            # immediate retry, or POST after a failed/unacknowledged dispatch commit.
            return BatchResult("unavailable", processed, failure or self.store.first_failure or
                safe_failure("outbox", operation, exc, side_effects="submission_possible" if operation == "outcome" else "submission_not_started"))
