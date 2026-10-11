"""Small, explicit State Request schema; importing never creates database objects."""

from sqlalchemy import (
    CheckConstraint, Column, DateTime, MetaData, PrimaryKeyConstraint, String,
    Table, text,
)
from sqlalchemy.dialects.postgresql import UUID

STATE_REQUESTS = "0002_state_requests"
STATE_CODES = tuple("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
STATE_CHECK = "state IN (" + ", ".join(repr(code) for code in STATE_CODES) + ")"
metadata = MetaData(schema="oaf_website")
state_requests = Table(
    "state_requests", metadata,
    Column("state", String(2), nullable=False),
    Column("browser_key", UUID(as_uuid=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    PrimaryKeyConstraint("state", "browser_key", name="state_requests_pk"),
    CheckConstraint(STATE_CHECK, name="state_requests_state_check"),
)
REQUEST_OBJECTS = [
    {"kind": "table", "name": "state_requests"},
    {"kind": "index", "name": "state_requests_pk"},
    {"kind": "row_type", "name": "state_requests"},
    {"kind": "array_type", "name": "_state_requests"},
    {"kind": "primary_key", "name": "state_requests_pk"},
    {"kind": "check", "name": "state_requests_state_check"},
    {"kind": "default", "name": "state_requests.created_at"},
]
REQUEST_GRANTS = [
    {"object": "oaf_website.state_requests", "role": "matching_runtime",
     "privileges": ["SELECT", "INSERT"], "grant_option": False},
]
REQUEST_EDGES = [
    ["request_table", 0, "schema", 0, "n"],
    ["request_row_type", 0, "request_table", 0, "i"],
    ["request_array_type", 0, "request_row_type", 0, "i"],
    ["request_primary_key", 0, "request_table", 1, "a"],
    ["request_primary_key", 0, "request_table", 2, "a"],
    ["request_index", 0, "request_primary_key", 0, "i"],
    ["request_check", 0, "request_table", 1, "a"],
    ["request_check", 0, "request_table", 1, "n"],
    ["request_default", 0, "request_table", 3, "a"],
]


def upgrade_state_requests(connection):
    """Only the matching schema owner can create and grant this feature."""
    from sqlalchemy.schema import CreateTable
    from .migration_config import IDENTITIES, Failure, MigrationError

    owner = connection.execute(text("SELECT current_user")).scalar_one()
    identity = next((i for i in IDENTITIES.values() if i.owner == owner), None)
    if identity is None:
        raise MigrationError(Failure.WRONG_IDENTITY)
    connection.execute(CreateTable(state_requests))
    # Arrays use element privileges. No new PUBLIC generated-type exception.
    connection.execute(text("REVOKE ALL ON TYPE oaf_website.state_requests FROM PUBLIC"))
    connection.execute(text(
        f'GRANT SELECT, INSERT ON TABLE oaf_website.state_requests TO "{identity.runtime}"'
    ))
