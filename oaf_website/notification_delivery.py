"""Transactional notification persistence; no sender or runtime processor.

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
WEB_CONTENT_VERSION = "web-launch-v1"
ENVIRONMENTS = {"development", "testing", "production"}
OUTCOMES = {"provider_accepted": "accepted", "provider_rejected": "rejected",
            "not_submitted": "failed", "retryable_rejection": "failed",
            "submission_unknown": "uncertain"}
HEX = re.compile(r"[0-9a-f]{64}")
EVENT_FIELDS = {"event_id", "source_approval_id", "environment", "platform", "release_id",
                "release_url", "approved_at", "audience_cutoff", "content_version"}


class EventConflict(ValueError):
    """An accepted event or semantic platform launch cannot be replaced."""


def canonical_web_url(value):
    """Server-approved public HTTPS reference syntax; no DNS or HTTP access."""
    return (type(value) is str and len(value) <= 300 and re.fullmatch(
        r"https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?:/[A-Za-z0-9_./~-]*)?", value) is not None
        and not re.search(r"\.(?:localhost|local|internal|lan|home|arpa|onion|test|invalid|example)(?:/|$)", value)
        and value.split("/", 3)[2] not in ("play.google.com", "apps.apple.com"))


def official_release_reference(platform, release_id, url, *, web_launch_url=None):
    """Bounded store references only; never resolve a URL or follow a redirect."""
    if type(release_id) is not str or type(url) is not str or len(url) > 300:
        return False
    if platform == "web":
        return release_id == "gramanna-web" and canonical_web_url(web_launch_url) and url == web_launch_url
    if platform == "android":
        return (len(release_id) <= 150 and re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", release_id) is not None
            and url == "https://play.google.com/store/apps/details?id=" + release_id)
    if platform == "ios":
        return (re.fullmatch(r"[1-9][0-9]{5,19}", release_id) is not None and re.fullmatch(
            r"https://apps\.apple\.com/(?:[a-z]{2}/)?app/(?:[a-z0-9]+(?:-[a-z0-9]+)*/)?id" + release_id,
            url) is not None)
    return False


def release_payload(payload, environment, now, *, web_launch_url=None):
    if type(payload) is not dict or set(payload) != EVENT_FIELDS:
        raise ValueError("Invalid release contract.")
    values = dict(payload)
    for name in ("event_id", "source_approval_id"):
        if type(values[name]) is not str or str(UUID(values[name])) != values[name]:
            raise ValueError("Invalid release identity.")
    if (values["environment"] != environment or values["platform"] not in ("android", "ios", "web")
            or values["content_version"] != (WEB_CONTENT_VERSION if values["platform"] == "web" else CONTENT_VERSION)):
        raise ValueError("Invalid release scope.")
    release_id, url = values["release_id"], values["release_url"]
    if not official_release_reference(values["platform"], release_id, url, web_launch_url=web_launch_url):
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
    def __init__(self, engine, secret, environment, *, management_enabled=False,
                 releases_enabled=False, recipient_scope=None, web_launch_url=None):
        UnsubscribeCapabilities(secret)  # Same persistent protected-key requirement; separate HMAC domains.
        if environment not in ENVIRONMENTS:
            raise ValueError("An explicit matching environment is required.")
        self.engine, self.secret, self.environment = engine, secret, environment
        if type(management_enabled) is not bool or type(releases_enabled) is not bool:
            raise ValueError("Management activation must be an explicit boolean.")
        self.management_enabled = management_enabled
        from .brevo import validate_recipient_scope
        validate_recipient_scope(recipient_scope, environment)
        self.releases_enabled, self.recipient_scope = releases_enabled, recipient_scope
        if web_launch_url is not None and not canonical_web_url(web_launch_url):
            raise ValueError("Invalid configured public web launch URL.")
        self.web_launch_url = web_launch_url

    def _digest(self, domain, value):
        return hmac.new(self.secret, ("oaf-notification-" + domain + "-v1:").encode()
                        + value.encode("ascii"), hashlib.sha256).hexdigest()

    @contextmanager
    def _transaction(self):
        from .notification_dispatch import safe_failure
        boundary, origin, failure = "database_begin", None, None
        try:
            with self.engine.begin() as connection:
                try:
                    # The existing subsystem lock serializes reservations and withdrawal.
                    boundary = "advisory_lock"
                    connection.execute(text("SELECT pg_catalog.pg_advisory_xact_lock(67210401)"))
                    boundary = "database_clock"
                    now = connection.execute(select(func.clock_timestamp())).scalar_one()
                    boundary = "transaction_body"
                    yield connection, now
                except Exception as exc:
                    origin = exc
                    failure = getattr(exc, "notification_failure", None) or safe_failure(
                        "notifications", boundary, exc)
                    raise
                boundary = "transaction_commit"
            request_transaction_outcome("database_committed")
        except Exception as exc:
            if failure is not None:
                failure["side_effects"] = "database_rolled_back" if exc is origin else "database_rollback_uncertain"
                if exc is not origin:
                    exc.notification_rollback_failure = safe_failure("notifications", "transaction_rollback", exc,
                        side_effects="database_rollback_uncertain")
            else:
                failure = safe_failure("notifications", boundary, exc, side_effects=
                    "database_commit_uncertain" if boundary == "transaction_commit" else "none")
            exc.notification_failure = failure
            raise

    def _rows(self, connection, item, **keys):
        if self.management_enabled:
            from .notification_management_schema import notifications as managed, intents
            if item.name == notifications.name:
                item = managed
            elif item.name == intents.name:
                item = intents
        statement = select(item).where(*(item.c[key] == value for key, value in keys.items()))
        # Append-only evidence has SELECT/INSERT grants only. The existing
        # transaction advisory lock serializes its checks/inserts; FOR UPDATE
        # would unnecessarily require UPDATE authority on that history.
        if item.name not in {suppressions.name, "notification_preference_changes", "notification_release_approvals"}:
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
        """Internal sensitive return only. Public callers discard it for a generic receipt.

        Unknown, verified, suppressed and throttled addresses all return None.
        All requests consume the global budget; mailbox limits survive resubscription.
        """
        email = normalize_email(email)
        with self._transaction() as (connection, now):
            return self._request_confirmation(connection, now, email)

    def _request_confirmation(self, connection, now, email):
        """Share the caller's locked transaction, including a newly inserted signup."""
        if not self._budget(connection, self._digest("budget", "global"), now, 1000, 0):
            retain_failure("confirmation_reservation", "confirmation_global_budget")
            return None
        mailbox = self._digest("mailbox", email)
        if not self._budget(connection, mailbox, now, 5, 60):
            retain_failure("confirmation_reservation", "confirmation_mailbox_budget")
            return None
        subscriber = self._get(connection, notifications, email=email, unsubscribed_at=None)
        if subscriber is None:
            retain_failure("confirmation_reservation", "confirmation_active_subscriber")
            return None
        if self._get(connection, suppressions, mailbox_digest=mailbox):
            retain_failure("confirmation_reservation", "confirmation_not_suppressed")
            return None
        key = dict(subscription=subscriber["unsubscribe_digest"])
        record = self._get(connection, verification, **key)
        if record and record["verified_at"] is not None:
            return None
        from .confirmation_outbox import reserve_confirmation
        return reserve_confirmation(self, connection, now, subscriber, record)

    def confirm(self, token):
        """Verified/already_verified/unavailable; valid replay only until original expiry."""
        if type(token) is not str or not HEX.fullmatch(token):
            retain_failure("confirmation_authority", "confirmation_token_format")
            return "unavailable"
        with self._transaction() as (connection, now):
            record = self._get(connection, verification, token_digest=self._digest("confirmation", token))
            if record is None:
                retain_failure("confirmation_authority", "confirmation_token_present")
                return "unavailable"
            subscriber = self._get(connection, notifications, unsubscribe_digest=record["subscription"])
            if subscriber["unsubscribed_at"] is not None:
                retain_failure("confirmation_authority", "confirmation_lifecycle_active")
                return "unavailable"
            if now >= record["expires_at"]:
                retain_failure("confirmation_authority", "confirmation_not_expired")
                return "unavailable"
            if now < record["issued_at"]:
                retain_failure("confirmation_authority", "confirmation_not_future")
                return "unavailable"
            if self._get(connection, suppressions, mailbox_digest=self._digest("mailbox", subscriber["email"])):
                retain_failure("confirmation_authority", "confirmation_not_suppressed")
                return "unavailable"
            # Classify only after the same capability, expiry and lifecycle checks.
            if record["verified_at"] is not None:
                return "already_verified"
            self._update(connection, verification, dict(subscription=record["subscription"]), verified_at=now)
            return "verified"

    def accept_event(self, payload):
        """Persist an authenticated approval; repeat the original identity on retry."""
        with self._transaction() as (connection, now):
            values = release_payload(payload, self.environment, now, web_launch_url=self.web_launch_url)
            existing = self._get(connection, events, event_id=values["event_id"])
            if existing:
                if existing["payload_digest"] != values["payload_digest"]:
                    raise EventConflict("Release event conflict.")
                return existing["event_id"]
            if self._get(connection, events, environment=self.environment, platform=values["platform"]):
                raise EventConflict("Platform launch already recorded.")
            self._insert(connection, events, dict(values, status="received", created_at=now, updated_at=now))
            return values["event_id"]

    def accept_release_change(self, payload):
        """Compare-and-append authority under the same dispatch transaction lock."""
        from .release_approval_schema import revisions
        if (not self.releases_enabled or type(payload) is not dict
                or set(payload) != EVENT_FIELDS | {"action", "previous_approval_id"}
                or payload["action"] not in ("correct", "withdraw")):
            raise ValueError("Invalid release change contract.")
        previous = payload["previous_approval_id"]
        if type(previous) is not str or str(UUID(previous)) != previous:
            raise ValueError("Invalid preceding approval identity.")
        with self._transaction() as (connection, now):
            values = release_payload({k: payload[k] for k in EVENT_FIELDS}, self.environment, now,
                                     web_launch_url=self.web_launch_url)
            digest = hashlib.sha256((values["payload_digest"] + payload["action"] + previous).encode("ascii")).hexdigest()
            existing = self._get(connection, revisions, source_approval_id=values["source_approval_id"])
            if existing:
                if existing["payload_digest"] != digest:
                    raise EventConflict("Release approval conflict.")
                return existing["event_id"]
            event = self._event(connection, values["event_id"])
            if (event is None or event.get("withdrawn", False)
                    or event["source_approval_id"] != previous or values["source_approval_id"] == previous
                    or values["platform"] != event["platform"]
                    or values["audience_cutoff"] != event["audience_cutoff"]
                    or values["approved_at"] <= event["approved_at"]):
                raise EventConflict("Release approval chain conflict.")
            self._insert(connection, revisions, dict(event_id=values["event_id"],
                source_approval_id=values["source_approval_id"], previous_approval_id=previous,
                action=payload["action"], release_id=values["release_id"], release_url=values["release_url"],
                approved_at=values["approved_at"], payload_digest=digest, created_at=now))
            if payload["action"] == "withdraw":
                for record in self._rows(connection, deliveries, event_id=values["event_id"]):
                    if record["status"] in {"pending", "failed", "claimed"}:
                        self._finish(connection, record, now, "suppressed", "suppressed")
                # Even an unprepared withdrawal is terminal; replay cannot reopen it.
                self._refresh(connection, values["event_id"], now)
            return values["event_id"]

    def _event(self, connection, event_id):
        event = self._get(connection, events, event_id=event_id, environment=self.environment)
        if event is not None and self.releases_enabled:
            from .release_approval_schema import revisions
            history = self._rows(connection, revisions, event_id=event_id)
            if history:
                latest = max(history, key=lambda row: row["approved_at"])
                event = dict(event, **{k: latest[k] for k in (
                    "source_approval_id", "release_id", "release_url", "approved_at")},
                    withdrawn=latest["action"] == "withdraw")
        return event

    def pending_release_events(self):
        """At most the three independent platform launches, recovered from persistence."""
        with self._transaction() as (connection, now):
            statement = select(events.c.event_id).where(events.c.environment == self.environment,
                events.c.status.in_(("received", "ready", "attention"))).order_by(
                    events.c.created_at, events.c.event_id).limit(3)
            return [row["event_id"] for row in connection.execute(statement).mappings()]

    def _eligible(self, connection, subscriber, event):
        if (event.get("withdrawn", False) or subscriber["unsubscribed_at"] is not None or subscriber["created_at"] > event["audience_cutoff"]
                or not subscriber[event["platform"] + "_launch"]):
            return False
        if self.management_enabled:
            from .notification_management_schema import changes
            current = self._get(connection, notifications, unsubscribe_digest=subscriber["unsubscribe_digest"])
            revision = current["preferences_revision"]
            audit = self._get(connection, changes, subscription=current["unsubscribe_digest"], revision=revision) if revision else None
            name = event["platform"] + "_launch"
            granted = audit[name + "_granted_at"] if audit else current["created_at"]
            if (revision and audit is None or not current[name] or granted is None
                    or granted > event["audience_cutoff"]):
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
            if self.recipient_scope is not None:
                statement = statement.where(deliveries.c.subscription.in_(select(
                    notifications.c.unsubscribe_digest).where(notifications.c.email == self.recipient_scope.mailbox)))
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
            if self.recipient_scope is not None:
                self.recipient_scope.require(subscriber["email"])
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

    def begin_submission(self, event_id, subscription, claim, *, prepare=None):
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
            if self.recipient_scope is not None:
                self.recipient_scope.require(subscriber["email"])
            if not self._eligible(connection, subscriber, event):
                self._finish(connection, record, now, "ineligible", "suppressed")
                return None
            # Render lifecycle/revision-bound links under the same final lock.
            message = prepare(subscriber, now, event) if prepare is not None else None
            key = dict(event_id=event_id, subscription=subscription)
            self._update(connection, deliveries, key, status="submitting", updated_at=now,
                         lease_until=now + timedelta(minutes=5))
            self._update(connection, attempts, dict(key, attempt=record["attempts"]), submitting_at=now)
            return (subscriber["email"], message) if prepare is not None else subscriber["email"]

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

from .notification_dispatch import retain_failure, request_transaction_outcome
