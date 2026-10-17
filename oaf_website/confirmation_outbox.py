"""Internal confirmation outbox. No route, scheduler, credential lookup or activation."""

from datetime import timedelta
import hmac
import re
import secrets

from sqlalchemy import insert, select

from .notification_delivery import NotificationDeliveryStore, OUTCOMES
from .notification_delivery_schema import verification, suppressions
from .notification_schema import notifications
from .confirmation_outbox_schema import intents, confirmation_attempts
from .brevo import BrevoAdapter, BrevoConfig, BrevoConfigurationError, ProviderOutcome
from .notification_dispatch import BatchResult
from .notification_messages import secure_page, verification_message


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


def reserve_confirmation(store, connection, now, subscriber, record):
    subscription = subscriber["unsubscribe_digest"]
    context = secrets.token_hex(32)
    token = capability(store, subscription, context)
    values = dict(token_digest=store._digest("confirmation", token), issued_at=now,
                  expires_at=now + timedelta(hours=24), verified_at=None)
    if record:
        store._update(connection, verification, dict(subscription=subscription), **values)
    else:
        connection.execute(insert(verification).values(subscription=subscription, **values))
    # Do not hide a random-context collision: the whole reservation must roll back.
    connection.execute(insert(intents).values(intent=context, subscription=subscription,
        token_digest=values["token_digest"], status="pending", attempts=0, claim_digest=None, lease_until=None,
        next_attempt_at=now, outcome=None, provider_message_id=None,
        created_at=now, updated_at=now, accepted_at=None))
    for previous in store._rows(connection, intents, subscription=subscription):
        if previous["intent"] != context and previous["status"] in {"pending", "claimed", "failed"}:
            finish(store, connection, previous, now, "ineligible", "suppressed")
    # Compatibility-sensitive internal return; never used as the durable handoff.
    return token


class ConfirmationOutboxStore(NotificationDeliveryStore):
    def _eligible_confirmation(self, connection, record, now):
        subscriber = self._get(connection, notifications, unsubscribe_digest=record["subscription"])
        current = self._get(connection, verification, subscription=record["subscription"])
        token = capability(self, record["subscription"], record["intent"])
        if (subscriber is None or current is None or subscriber["unsubscribed_at"] is not None
                or current["verified_at"] is not None or now < current["issued_at"]
                or now >= current["expires_at"]
                or not hmac.compare_digest(current["token_digest"], record["token_digest"])
                or self._get(connection, suppressions,
                             mailbox_digest=self._digest("mailbox", subscriber["email"]))):
            return None
        if not hmac.compare_digest(record["token_digest"], self._digest("confirmation", token)):
            raise ValueError("Protected confirmation recovery unavailable.")
        return subscriber, token

    def _owns_confirmation(self, record, claim, status):
        return (record is not None and record["status"] == status and type(claim) is str
                and re.fullmatch(r"[0-9a-f]{64}", claim) is not None
                and hmac.compare_digest(record["claim_digest"], self._digest("confirmation-claim", claim)))

    def candidates(self, limit):
        with self._transaction() as (connection, now):
            # Bound recovery work too. Final claims/dispatch recheck authority.
            statement = select(intents).where(intents.c.status.in_(("claimed", "submitting")),
                intents.c.lease_until <= now).order_by(intents.c.intent).limit(limit)
            for record in connection.execute(statement).mappings():
                submitting = record["status"] == "submitting"
                finish(self, connection, record, now, "submission_unknown" if submitting else "claim_expired",
                       "uncertain" if submitting else "failed")
            statement = select(intents.c.intent).where(intents.c.status.in_(("pending", "failed")),
                intents.c.attempts < 3, intents.c.next_attempt_at <= now).order_by(intents.c.intent).limit(limit)
            return [row["intent"] for row in connection.execute(statement).mappings()]

    def claim_confirmation(self, intent):
        with self._transaction() as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if (record is None or record["status"] not in {"pending", "failed"} or record["attempts"] >= 3
                    or record["next_attempt_at"] is None or record["next_attempt_at"] > now):
                return None
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
        with self._transaction() as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if not self._owns_confirmation(record, claim, "claimed") or record["lease_until"] <= now:
                return None
            eligible = self._eligible_confirmation(connection, record, now)
            if eligible is None:
                finish(self, connection, record, now, "ineligible", "suppressed")
                return None
            subscriber, token = eligible
            try:
                message = verification_message(token, page)
            except Exception:
                finish(self, connection, record, now, "not_submitted", "failed")
                return None
            self._update(connection, intents, dict(intent=intent), status="submitting",
                         lease_until=now + timedelta(minutes=5), updated_at=now)
            self._update(connection, confirmation_attempts, dict(intent=intent, attempt=record["attempts"]),
                         submitting_at=now)
            return subscriber["email"], message

    def confirmation_outcome(self, intent, claim, outcome, message_id=None):
        if outcome not in OUTCOMES or (message_id is not None and (type(message_id) is not str
                or re.fullmatch(r"[A-Za-z0-9_.@<>:+/-]{1,200}", message_id) is None)):
            raise ValueError("Invalid sanitized confirmation outcome.")
        with self._transaction() as (connection, now):
            record = self._get(connection, intents, intent=intent)
            if not self._owns_confirmation(record, claim, "submitting"):
                return False
            # A provider must never turn an echoed bearer into durable correlation
            # data. Preserve the outcome but discard such a private identifier.
            if message_id is not None and capability(self, record["subscription"], intent) in message_id:
                message_id = None
            finish(self, connection, record, now, outcome, OUTCOMES[outcome], message_id)
            return True


class ConfirmationDispatcher:
    def __init__(self, store, config, confirmation_page, *, transport=None):
        if type(config) is not BrevoConfig or config.environment != store.environment:
            raise BrevoConfigurationError("Brevo configuration must match the confirmation environment.")
        self.store, self.page = store, secure_page(confirmation_page)
        self.adapter = BrevoAdapter(config, transport=transport)

    def process(self, *, limit=20):
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Confirmation batches require 1 to 20 recipients.")
        processed = 0
        try:
            for intent in self.store.candidates(limit):
                claim = self.store.claim_confirmation(intent)
                if claim is None:
                    continue
                prepared = self.store.prepare_confirmation(intent, claim, self.page)
                if prepared is None:
                    continue
                try:
                    outcome = self.adapter.submit(*prepared)
                except Exception:
                    outcome = ProviderOutcome("submission_unknown")
                if not self.store.confirmation_outcome(intent, claim, outcome.outcome, outcome.message_id):
                    return BatchResult("unavailable", processed)
                processed += 1
            return BatchResult("processed", processed)
        except Exception:
            # Includes uncertain commits and preparation failures. No private data,
            # immediate retry, or POST after a failed/unacknowledged dispatch commit.
            return BatchResult("unavailable", processed)
