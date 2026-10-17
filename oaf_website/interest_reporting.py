"""Read-only, single-statement PostgreSQL interest snapshot; no private columns."""

from datetime import datetime, timezone
import re

from sqlalchemy import cast, func, literal, select, text
from sqlalchemy.dialects.postgresql import JSONB

from .notification_schema import notifications
from .state_request_schema import STATE_CODES, state_requests

PREFERENCES = ("web_launch", "android_launch", "ios_launch", "state_availability")
ENVIRONMENTS = frozenset({"development", "testing", "production"})


def _count(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def _by_state(value):
    if (type(value) is not dict or not set(value).issubset(STATE_CODES)
            or not all(_count(count) for count in value.values())):
        raise ValueError("Invalid aggregate response.")
    return {state: value.get(state, 0) for state in STATE_CODES}


def validate_summary(value, environment):
    """Reject malformed/private data rather than forwarding it to the caller."""
    if (environment not in ENVIRONMENTS or type(value) is not dict
            or set(value) != {"environment", "reported_at_utc", "state_requests", "notifications"}
            or value["environment"] != environment):
        raise ValueError("Invalid aggregate response.")
    timestamp = value["reported_at_utc"]
    if (type(timestamp) is not str
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z",
                            timestamp, re.ASCII) is None):
        raise ValueError("Invalid aggregate response.")
    datetime.fromisoformat(timestamp[:-1] + "+00:00")
    states, subscriptions = value["state_requests"], value["notifications"]
    if (type(states) is not dict or set(states) != {"accepted_total", "by_state"}
            or not _count(states["accepted_total"])
            or _by_state(states["by_state"]) != states["by_state"]
            or sum(states["by_state"].values()) != states["accepted_total"]):
        raise ValueError("Invalid aggregate response.")
    if (type(subscriptions) is not dict
            or set(subscriptions) != {"active_total", "preferences", "state_availability_by_state"}
            or not _count(subscriptions["active_total"])):
        raise ValueError("Invalid aggregate response.")
    preferences = subscriptions["preferences"]
    if (type(preferences) is not dict or set(preferences) != set(PREFERENCES)
            or not all(_count(count) and count <= subscriptions["active_total"]
                       for count in preferences.values())
            or sum(preferences.values()) < subscriptions["active_total"]
            or _by_state(subscriptions["state_availability_by_state"])
               != subscriptions["state_availability_by_state"]
            or sum(subscriptions["state_availability_by_state"].values())
               != preferences["state_availability"]):
        raise ValueError("Invalid aggregate response.")
    return value


def summary_statement():
    states = select(state_requests.c.state, func.count().label("count")).group_by(
        state_requests.c.state).subquery()
    active = notifications.c.unsubscribed_at.is_(None)
    availability = (select(notifications.c.state, func.count().label("count"))
                    .where(active, notifications.c.state.is_not(None))
                    .group_by(notifications.c.state).subquery())
    categories = select(
        func.count().label("active_total"),
        *(func.count().filter(notifications.c[name].is_(True)).label(name)
          for name in PREFERENCES[:3]),
        func.count().filter(notifications.c.state.is_not(None)).label("state_availability"),
    ).select_from(notifications).where(active).subquery()

    def counts(table):
        return (select(func.coalesce(func.jsonb_object_agg(table.c.state, table.c.count),
                                     cast(literal("{}"), JSONB)))
                .select_from(table).scalar_subquery())

    return select(func.statement_timestamp().label("reported_at"),
                  counts(states).label("states"), counts(availability).label("availability"),
                  categories.c.active_total, *(categories.c[name] for name in PREFERENCES))


class InterestSummaryStore:
    def __init__(self, engine, environment):
        if environment not in ENVIRONMENTS:
            raise ValueError("An explicit verified environment is required.")
        self.engine, self.environment = engine, environment

    def summary(self):
        # Every aggregate is in ONE data SELECT: PostgreSQL's statement snapshot
        # is consistent even at READ COMMITTED, including concurrent withdrawals.
        # The shared runtime engine verifies identity on every pool checkout.
        with self.engine.connect() as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                row = connection.execute(summary_statement()).mappings().one()
        timestamp = row["reported_at"]
        if type(timestamp) is not datetime or timestamp.utcoffset() is None:
            raise ValueError("Invalid aggregate response.")
        states, availability = _by_state(row["states"]), _by_state(row["availability"])
        result = dict(
            environment=self.environment,
            reported_at_utc=timestamp.astimezone(timezone.utc).isoformat(
                timespec="microseconds").replace("+00:00", "Z"),
            state_requests=dict(accepted_total=sum(states.values()), by_state=states),
            notifications=dict(active_total=row["active_total"],
                               preferences={name: row[name] for name in PREFERENCES},
                               state_availability_by_state=availability),
        )
        return validate_summary(result, self.environment)
