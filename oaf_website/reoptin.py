"""Fresh subscription authority only; provider work stays in the Cron outbox."""

from datetime import timedelta
from sqlalchemy import insert

from .notification_schema import notifications, CONSENT_VERSION
from .notification_delivery_schema import suppressions, verification
from .reoptin_schema import intents


def authorization(store, connection, subscriber):
    if not store.management_enabled:
        return None
    return store._get(connection, intents,
                      intent=store._digest("reoptin", subscriber["unsubscribe_digest"]),
                      subscription=subscriber["unsubscribe_digest"], purpose="reoptin")


def permitted(store, connection, subscriber):
    """A historical suppression exception belongs only to this accepted lifecycle."""
    record = authorization(store, connection, subscriber)
    block = store._get(connection, suppressions, mailbox_digest=store._digest("mailbox", subscriber["email"]))
    return (record is not None and record["status"] == "accepted" and record["revoked_at"] is None
            and (block is None or block["reason"] in {"provider_block", "complaint"}
                 and block["reoptin_blocked_at"] is None))


def suppressed(store, connection, subscriber):
    block = store._get(connection, suppressions, mailbox_digest=store._digest("mailbox", subscriber["email"]))
    return block is not None and not permitted(store, connection, subscriber)


def needs_authorization(store, connection, subscriber):
    """Recover a prior stalled lifecycle only on another explicit signup."""
    if not store.management_enabled or authorization(store, connection, subscriber) is not None:
        return False
    return any(row["unsubscribed_at"] is not None for row in
               store._rows(connection, notifications, email=subscriber["email"]))


def reserve(store, connection, now, subscriber):
    """Called only for a validated explicit signup's own active receipt."""
    if not store.management_enabled:
        return None
    previous = store._rows(connection, notifications, email=subscriber["email"])
    if not any(row["unsubscribed_at"] is not None for row in previous):
        return None
    record = authorization(store, connection, subscriber)
    if record is not None:
        return record
    # Fresh consent supersedes prior withdrawal/complaint. Local hard-bounce and
    # owner-policy restrictions still require their existing resolution.
    block = store._get(connection, suppressions, mailbox_digest=store._digest("mailbox", subscriber["email"]))
    if block is not None and (block["reason"] not in {"provider_block", "complaint"}
                              or block["reoptin_blocked_at"] is not None):
        return None
    values = dict(intent=store._digest("reoptin", subscriber["unsubscribe_digest"]),
        subscription=subscriber["unsubscribe_digest"],
        token_digest=store._digest("reoptin-consent", subscriber["unsubscribe_digest"]),
        purpose="reoptin", management_revision=None, revoked_at=None,
        status="pending", attempts=0, claim_digest=None, lease_until=None,
        next_attempt_at=now, outcome=None, provider_message_id=None,
        created_at=now, updated_at=now, accepted_at=None)
    connection.execute(insert(intents).values(**values))
    return values


def eligible(store, connection, record, now):
    subscriber = store._get(connection, notifications, unsubscribe_digest=record["subscription"])
    verified = store._get(connection, verification, subscription=record["subscription"])
    block = (store._get(connection, suppressions, mailbox_digest=store._digest("mailbox", subscriber["email"]))
             if subscriber is not None else None)
    if (subscriber is None or subscriber["unsubscribed_at"] is not None
            or subscriber["consent_version"] != CONSENT_VERSION or record["revoked_at"] is not None
            or record["intent"] != store._digest("reoptin", record["subscription"])
            or record["token_digest"] != store._digest("reoptin-consent", record["subscription"])
            or verified is None or verified["verified_at"] is not None
            or block is not None and (block["reason"] not in {"provider_block", "complaint"}
                                      or block["reoptin_blocked_at"] is not None)
            or not subscriber["created_at"] <= record["created_at"] <= now < record["created_at"] + timedelta(hours=24)):
        return None
    return subscriber


def revoke(store, connection, now, email):
    """New suppression revokes exceptions without rewriting old send evidence."""
    if not store.management_enabled:
        return
    for subscriber in store._rows(connection, notifications, email=email):
        record = authorization(store, connection, subscriber)
        if record is not None and record["revoked_at"] is None:
            store._update(connection, intents, dict(intent=record["intent"]), revoked_at=now)
