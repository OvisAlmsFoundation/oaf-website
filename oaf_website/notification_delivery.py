"""Offline-tested persistence foundation; deliberately unregistered, with no sender.

Callers inject an already verified OAF engine and protected persistent secret.
Every transition is transactional. Exceptions escape without logging private data;
callers must use a fixed unavailable response and never automatically retry a
submission after commit uncertainty. No method constitutes release approval.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from .notification_schema import notifications
from .notification_delivery_schema import verification, limits, events, deliveries, attempts, suppressions
from .notifications import normalize_email, UnsubscribeCapabilities

CONTENT_VERSION = "mobile-launch-v1"
ENVIRONMENTS = {"development", "testing", "production"}
OUTCOMES = {"provider_accepted": "accepted", "provider_rejected": "rejected",
            "not_submitted": "failed", "retryable_rejection": "failed",
            "submission_unknown": "uncertain"}
HEX = re.compile(r"[0-9a-f]{64}")
EVENT_FIELDS = {"event_id", "source_approval_id", "environment", "platform", "release_id",
                "release_url", "approved_at", "audience_cutoff", "content_version"}


class EventConflict(ValueError):
    """An accepted event or semantic platform launch cannot be replaced."""


def release_payload(payload, environment, now):
    if type(payload) is not dict or set(payload) != EVENT_FIELDS:
        raise ValueError("Invalid release contract.")
    values = dict(payload)
    for name in ("event_id", "source_approval_id"):
        if type(values[name]) is not str or str(UUID(values[name])) != values[name]:
            raise ValueError("Invalid release identity.")
    if (values["environment"] != environment or values["platform"] not in ("android", "ios")
            or values["content_version"] != CONTENT_VERSION):
        raise ValueError("Invalid release scope.")
    release_id, url = values["release_id"], values["release_url"]
    if type(release_id) is not str or type(url) is not str:
        raise ValueError("Invalid official release reference.")
    if values["platform"] == "android":
        valid = (len(release_id) <= 150 and re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", release_id)
                 and url == "https://play.google.com/store/apps/details?id=" + release_id)
    else:
        valid = (re.fullmatch(r"[1-9][0-9]{5,19}", release_id)
                 and url == "https://apps.apple.com/app/id" + release_id)
    if not valid:
        raise ValueError("Invalid official release reference.")
    for name in ("approved_at", "audience_cutoff"):
        value = values[name]
        if type(value) is not str:
            raise ValueError("A timezone-aware release timestamp is required.")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("A timezone-aware release timestamp is required.")
        values[name] = parsed.astimezone(timezone.utc)
    if not values["audience_cutoff"] <= values["approved_at"] <= now:
        raise ValueError("Invalid release timestamps.")
    canonical = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in values.items()}
    values["payload_digest"] = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    return values


class NotificationDeliveryStore:
    def __init__(self, engine, secret, environment):
        UnsubscribeCapabilities(secret)  # Same persistent protected-key requirement; separate HMAC domains.
        if environment not in ENVIRONMENTS:
            raise ValueError("An explicit matching environment is required.")
        self.engine, self.secret, self.environment = engine, secret, environment

    def _digest(self, domain, value):
        return hmac.new(self.secret, ("oaf-notification-" + domain + "-v1:").encode()
                        + value.encode("ascii"), hashlib.sha256).hexdigest()

    @contextmanager
    def _transaction(self):
        with self.engine.begin() as connection:
            # Deliberately coarse bounded subsystem lock, cross-process and rollback-safe.
            # No worker or infrastructure is introduced. Existing withdrawal also
            # serializes at the subscriber row lock used before dispatch.
            connection.execute(text("SELECT pg_catalog.pg_advisory_xact_lock(67210401)"))
            now = connection.execute(select(func.clock_timestamp())).scalar_one()
            yield connection, now

    @staticmethod
    def _rows(connection, item, **keys):
        statement = select(item).where(*(item.c[key] == value for key, value in keys.items()))
        if item is not suppressions:
            statement = statement.with_for_update()
        return list(connection.execute(statement).mappings())

    def _get(self, connection, item, **keys):
        records = self._rows(connection, item, **keys)
        return records[0] if records else None

    @staticmethod
    def _insert(connection, item, values):
        connection.execute(insert(item).values(**values).on_conflict_do_nothing())

    @staticmethod
    def _update(connection, item, keys, **values):
        connection.execute(update(item).where(*(item.c[key] == value for key, value in keys.items())).values(**values))

    def _budget(self, connection, bucket, now, maximum, cooldown):
        record = self._get(connection, limits, bucket=bucket)
        start, count = (record["window_start"], record["requests"]) if record else (now, 0)
        if now >= start + timedelta(days=1):
            start, count = now, 0
        if record and (now < record["last_requested_at"] + timedelta(seconds=cooldown) or count >= maximum):
            return False
        values = dict(window_start=start, last_requested_at=now, requests=count + 1)
        if record:
            self._update(connection, limits, dict(bucket=bucket), **values)
        else:
            self._insert(connection, limits, dict(bucket=bucket, **values))
        return True

    def request_confirmation(self, email):
        """Internal sensitive return only. A future endpoint MUST return a generic receipt.

        No endpoint calls this until confirmation delivery is approved/available.
        Unknown, verified, suppressed and throttled addresses all return None.
        All requests consume the global budget; mailbox limits survive resubscription.
        """
        email = normalize_email(email)
        with self._transaction() as (connection, now):
            if not self._budget(connection, self._digest("budget", "global"), now, 1000, 0):
                return None
            mailbox = self._digest("mailbox", email)
            if not self._budget(connection, mailbox, now, 5, 60):
                return None
            subscriber = self._get(connection, notifications, email=email, unsubscribed_at=None)
            if subscriber is None or self._get(connection, suppressions, mailbox_digest=mailbox):
                return None
            key = dict(subscription=subscriber["unsubscribe_digest"])
            record = self._get(connection, verification, **key)
            if record and record["verified_at"] is not None:
                return None
            from .confirmation_outbox import reserve_confirmation
            return reserve_confirmation(self, connection, now, subscriber, record)

    def confirm(self, token):
        """Fixed outcomes, no address disclosure; replay allowed only until original expiry."""
        if type(token) is not str or not HEX.fullmatch(token):
            return "unavailable"
        with self._transaction() as (connection, now):
            record = self._get(connection, verification, token_digest=self._digest("confirmation", token))
            if record is None:
                return "unavailable"
            subscriber = self._get(connection, notifications, unsubscribe_digest=record["subscription"])
            if (subscriber["unsubscribed_at"] is not None or now >= record["expires_at"]
                    or now < record["issued_at"]
                    or self._get(connection, suppressions, mailbox_digest=self._digest("mailbox", subscriber["email"]))):
                return "unavailable"
            if record["verified_at"] is None:
                self._update(connection, verification, dict(subscription=record["subscription"]), verified_at=now)
            return "verified"

    def accept_event(self, payload):
        """Trusted internal seam only; approval authentication/handoff is a later checkpoint."""
        with self._transaction() as (connection, now):
            values = release_payload(payload, self.environment, now)
            existing = self._get(connection, events, event_id=values["event_id"])
            if existing:
                if existing["payload_digest"] != values["payload_digest"]:
                    raise EventConflict("Release event conflict.")
                return existing["event_id"]
            if self._get(connection, events, environment=self.environment, platform=values["platform"]):
                raise EventConflict("Platform launch already recorded.")
            self._insert(connection, events, dict(values, status="received", created_at=now, updated_at=now))
            return values["event_id"]

    def _event(self, connection, event_id):
        return self._get(connection, events, event_id=event_id, environment=self.environment)

    def _eligible(self, connection, subscriber, event):
        if (subscriber["unsubscribed_at"] is not None or subscriber["created_at"] > event["audience_cutoff"]
                or not subscriber[event["platform"] + "_launch"]):
            return False
        record = self._get(connection, verification, subscription=subscriber["unsubscribe_digest"])
        return (record is not None and record["verified_at"] is not None
                and record["verified_at"] <= event["audience_cutoff"]
                and self._get(connection, suppressions,
                              mailbox_digest=self._digest("mailbox", subscriber["email"])) is None)

    def prepare_event(self, event_id):
        with self._transaction() as (connection, now):
            event = self._event(connection, event_id)
            if event is None:
                return None
            if event["status"] != "received":
                return event["status"]
            # A cutoff never expands on retry/recovery. This complete operation is atomic.
            statement = select(notifications).where(notifications.c.unsubscribed_at.is_(None),
                notifications.c.created_at <= event["audience_cutoff"],
                notifications.c[event["platform"] + "_launch"].is_(True)).with_for_update()
            for subscriber in connection.execute(statement).mappings():
                if self._eligible(connection, subscriber, event):
                    self._insert(connection, deliveries, dict(event_id=event_id,
                        subscription=subscriber["unsubscribe_digest"], status="pending", attempts=0,
                        claim_digest=None, lease_until=None, next_attempt_at=now, outcome=None,
                        provider_message_id=None, created_at=now, updated_at=now, accepted_at=None))
            return self._refresh(connection, event_id, now)

    def dispatch_batch(self, event_id, limit=20):
        """Bounded candidate references only; claim and final dispatch recheck still required."""
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Release batches require 1 to 20 recipients.")
        with self._transaction() as (connection, now):
            event = self._event(connection, event_id)
            if event is None:
                return None, []
            statement = select(deliveries.c.subscription).where(
                deliveries.c.event_id == event_id,
                deliveries.c.status.in_(("pending", "failed")), deliveries.c.attempts < 3,
                deliveries.c.next_attempt_at <= now).order_by(deliveries.c.subscription).limit(limit)
            return dict(event), [row["subscription"] for row in connection.execute(statement).mappings()]

    def _refresh(self, connection, event_id, now):
        records = self._rows(connection, deliveries, event_id=event_id)
        statuses = {record["status"] for record in records}
        status = "attention" if "uncertain" in statuses else "ready" if any(
            r["status"] in {"pending", "claimed", "submitting"} or
            r["status"] == "failed" and r["next_attempt_at"] is not None for r in records) else "completed"
        self._update(connection, events, dict(event_id=event_id), status=status, updated_at=now)
        return status

    def _finish(self, connection, record, now, outcome, status, message_id=None):
        key = dict(event_id=record["event_id"], subscription=record["subscription"])
        retry = now + timedelta(seconds=60 * 5 ** (record["attempts"] - 1)) if status == "failed" and record["attempts"] < 3 else None
        self._update(connection, deliveries, key, status=status, claim_digest=None, lease_until=None,
                     next_attempt_at=retry, outcome=outcome, provider_message_id=message_id,
                     updated_at=now, accepted_at=now if status == "accepted" else None)
        if record["status"] in {"claimed", "submitting"}:
            self._update(connection, attempts, dict(key, attempt=record["attempts"]),
                         finished_at=now, outcome=outcome, provider_message_id=message_id)
        self._refresh(connection, record["event_id"], now)

    def claim(self, event_id, subscription):
        with self._transaction() as (connection, now):
            event = self._event(connection, event_id)
            record = self._get(connection, deliveries, event_id=event_id, subscription=subscription)
            if event is None or record is None:
                return None
            if (record["status"] not in {"pending", "failed"} or record["attempts"] >= 3
                    or record["next_attempt_at"] is None or record["next_attempt_at"] > now):
                return None
            subscriber = self._get(connection, notifications, unsubscribe_digest=subscription)
            if not self._eligible(connection, subscriber, event):
                self._finish(connection, record, now, "ineligible", "suppressed")
                return None
            token = secrets.token_hex(32)
            key = dict(event_id=event_id, subscription=subscription)
            self._update(connection, deliveries, key, status="claimed", attempts=record["attempts"] + 1,
                         claim_digest=self._digest("claim", token), lease_until=now + timedelta(minutes=5),
                         next_attempt_at=None, updated_at=now)
            self._insert(connection, attempts, dict(key, attempt=record["attempts"] + 1, claimed_at=now,
                         submitting_at=None, finished_at=None, outcome=None, provider_message_id=None))
            self._refresh(connection, event_id, now)
            return token

    def begin_submission(self, event_id, subscription, claim):
        """One-use dispatch boundary; return authoritative email only to future adapter.

        Caller must persist this transition successfully before attempting a send.
        A lost commit response means no automatic send/retry, even with this claim.
        """
        with self._transaction() as (connection, now):
            event = self._event(connection, event_id)
            record = self._get(connection, deliveries, event_id=event_id, subscription=subscription)
            if (event is None or not self._owns(record, claim, "claimed") or record["lease_until"] <= now):
                return None
            subscriber = self._get(connection, notifications, unsubscribe_digest=subscription)
            if not self._eligible(connection, subscriber, event):
                self._finish(connection, record, now, "ineligible", "suppressed")
                return None
            key = dict(event_id=event_id, subscription=subscription)
            self._update(connection, deliveries, key, status="submitting", updated_at=now,
                         lease_until=now + timedelta(minutes=5))
            self._update(connection, attempts, dict(key, attempt=record["attempts"]), submitting_at=now)
            return subscriber["email"]

    def _owns(self, record, claim, status):
        return (record is not None and record["status"] == status and type(claim) is str
                and HEX.fullmatch(claim) is not None
                and hmac.compare_digest(record["claim_digest"], self._digest("claim", claim)))

    def record_outcome(self, event_id, subscription, claim, outcome, message_id=None):
        if outcome not in OUTCOMES or (message_id is not None and
            (type(message_id) is not str or re.fullmatch(r"[A-Za-z0-9_.@<>:+/-]{1,200}", message_id) is None)):
            raise ValueError("Invalid sanitized delivery outcome.")
        with self._transaction() as (connection, now):
            record = self._get(connection, deliveries, event_id=event_id, subscription=subscription)
            if self._event(connection, event_id) is None or not self._owns(record, claim, "submitting"):
                return False
            self._finish(connection, record, now, outcome, OUTCOMES[outcome], message_id)
            return True

    def recover_event(self, event_id):
        with self._transaction() as (connection, now):
            event = self._event(connection, event_id)
            if event is None:
                return None
            if event["status"] == "received":
                return "received"
            for record in self._rows(connection, deliveries, event_id=event_id):
                if record["status"] in {"claimed", "submitting"} and record["lease_until"] <= now:
                    submitting = record["status"] == "submitting"
                    self._finish(connection, record, now,
                                 "submission_unknown" if submitting else "claim_expired",
                                 "uncertain" if submitting else "failed")
            return self._refresh(connection, event_id, now)

    def suppress(self, email, reason):
        if reason not in {"hard_bounce", "complaint", "provider_block", "owner_policy"}:
            raise ValueError("Invalid suppression reason.")
        mailbox = self._digest("mailbox", normalize_email(email))
        with self._transaction() as (connection, now):
            self._insert(connection, suppressions, dict(mailbox_digest=mailbox, reason=reason, created_at=now))
        # Permanent across lifecycle changes; never rewrite original evidence.
        # Pending/claimed work is stopped by the mandatory dispatch recheck.
