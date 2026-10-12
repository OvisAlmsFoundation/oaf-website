"""Live TESTING coordinator; reuse the existing Flask host and child protocol.

Only the authorized runtime credential is used. All submitted rows are retained.
Subscriber addresses, receipt hashes and capabilities stay in process memory.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from state_request_live_check import Child, counts, inventory, require, rows
from oaf_website.database_config import load_testing_database_config
from oaf_website.local_testing import recognition_secret
from oaf_website.notification_schema import CONSENT_VERSION
from oaf_website.state_requests import BrowserRecognition


def notification_rows(connection):
    return {row[0]: tuple(row[1:]) for row in connection.execute("""
        SELECT unsubscribe_digest,email,web_launch,android_launch,ios_launch,state,
               consent_version,created_at,unsubscribed_at
        FROM oaf_website.notifications
    """).fetchall()}


def summary(snapshot):
    active = sum(row[-1] is None for row in snapshot.values())
    return dict(total=len(snapshot), active=active, withdrawn=len(snapshot) - active)


def database_probes(connection):
    """Probe actual constraints in rollback-only transactions; never remove rows."""
    import psycopg

    class RollbackProbe(Exception):
        pass

    base = dict(digest=hashlib.sha256(uuid4().bytes).hexdigest(),
                email="probe-" + uuid4().hex + "@example.invalid", web=True,
                android=False, ios=False, state=None, consent=CONSENT_VERSION)
    statement = """INSERT INTO oaf_website.notifications
        (unsubscribe_digest,email,web_launch,android_launch,ios_launch,state,consent_version)
        VALUES (%(digest)s,%(email)s,%(web)s,%(android)s,%(ios)s,%(state)s,%(consent)s)"""
    checks = [
        (dict(digest="broken"), "23514", "notifications_token_check"),
        (dict(email=base["email"].upper()), "23514", "notifications_email_check"),
        (dict(email=" " + base["email"]), "23514", "notifications_email_check"),
        (dict(email="x"), "23514", "notifications_email_check"),
        (dict(web=False), "23514", "notifications_preferences_check"),
        (dict(state="ZZ"), "23514", "notifications_state_check"),
        (dict(consent="unapproved"), "23514", "notifications_consent_check"),
        (dict(email=None), "23502", None),
        (dict(web=None), "23502", None),
        (dict(android=None), "23502", None),
        (dict(ios=None), "23502", None),
        (dict(consent=None), "23502", None),
        (dict(digest=None), "23502", None),
        (dict(email="x" * 255), "22001", None),
    ]
    evidence = []
    for changes, code, constraint in checks:
        try:
            with connection.transaction():
                connection.execute(statement, dict(base, **changes))
                raise RollbackProbe()
        except psycopg.Error as error:
            require(error.sqlstate == code and
                    (constraint is None or error.diag.constraint_name == constraint),
                    "A PostgreSQL validation probe returned an unexpected rejection.")
            evidence.append(dict(sqlstate=code, constraint=constraint,
                                 fields=sorted(changes)))
        except RollbackProbe:
            raise RuntimeError("PostgreSQL accepted an invalid constraint probe.")

    def rejected(sql, params, code, constraint=None, setup=False):
        try:
            with connection.transaction():
                if setup:
                    connection.execute(statement, base)
                connection.execute(sql, params)
                raise RollbackProbe()
        except psycopg.Error as error:
            require(error.sqlstate == code and
                    (constraint is None or error.diag.constraint_name == constraint),
                    "A PostgreSQL uniqueness/permission probe returned an unexpected rejection.")
        except RollbackProbe:
            raise RuntimeError("PostgreSQL accepted a forbidden database probe.")
        evidence.append(dict(sqlstate=code, constraint=constraint))

    rejected(statement, base, "23505", "notifications_pk", setup=True)
    rejected(statement, dict(base, digest=hashlib.sha256(uuid4().bytes).hexdigest()),
             "23505", "notifications_active_email", setup=True)
    rejected("UPDATE oaf_website.notifications SET unsubscribed_at=created_at - interval '1 second' "
             "WHERE unsubscribe_digest=%s", (base["digest"],), "23514",
             "notifications_lifecycle_check", setup=True)
    rejected("UPDATE oaf_website.notifications SET email=email WHERE false", (), "42501")
    rejected("UPDATE oaf_website.notifications SET consent_version=consent_version WHERE false", (), "42501")
    try:
        with connection.transaction():
            connection.execute(statement, base)
            require(connection.execute("SELECT count(*) FROM oaf_website.notifications "
                    "WHERE unsubscribe_digest=%s", (base["digest"],)).fetchone()[0] == 1,
                    "Rollback probe was not visible inside its transaction.")
            raise RollbackProbe()
    except RollbackProbe:
        pass
    require(connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE,
            "Verification connection did not return to idle.")
    return evidence


def run(browser_python):
    import psycopg

    destination = ROOT / ".pytest_cache" / ("notification-live-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    destination.mkdir(parents=True, exist_ok=False)
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(),
                  flask_integration="BLOCKED", playwright="BLOCKED",
                  postgresql_verification="BLOCKED", checks=[], database_checkpoints=[],
                  errors=[], synthetic_addresses_only=True, email_delivery="None configured or invoked")
    source_before = inventory()
    connection = server_child = browser_child = None
    phase = "TESTING preflight"
    observed = {}
    try:
        require(Path.cwd().resolve() == ROOT and sys.platform == "win32",
                "Run from the website workspace under native Windows.")
        require(os.environ.get("OAF_ENV") == "testing", "Explicit TESTING environment required.")
        require(browser_python.is_file(), "Existing shared Playwright interpreter missing.")
        config = load_testing_database_config()
        connection = psycopg.connect(host=config.url.host, port=config.url.port,
            dbname=config.url.database, user=config.url.username, password=config.url.password,
            autocommit=True, connect_timeout=5, require_auth="scram-sha-256",
            application_name="oaf_notification_live_verification",
            options="-c statement_timeout=10000 -c lock_timeout=5000")
        identity = connection.execute("SELECT current_database(),current_user,session_user,"
            "host(inet_server_addr()),inet_server_port(),"
            "current_setting('server_version_num')::int / 10000").fetchone()
        config.verify_connection_identity(identity[0], identity[1])
        require(identity == ("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app",
                             "127.0.0.1", 5432, 17), "Unexpected TESTING connection identity.")
        privileges = dict(connection.execute("""
            SELECT p,has_table_privilege(current_user,'oaf_website.notifications',p)
            FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) p
        """).fetchall())
        require(privileges == {p: p in {"SELECT", "INSERT"} for p in privileges},
                "Notification table privileges differ from approved runtime access.")
        column_update = dict(connection.execute("""
            SELECT attname,has_column_privilege(current_user,'oaf_website.notifications',attname,'UPDATE')
            FROM pg_attribute WHERE attrelid='oaf_website.notifications'::regclass
            AND attnum>0 AND NOT attisdropped
        """).fetchall())
        require(all(allowed == (name == "unsubscribed_at") for name, allowed in column_update.items()),
                "Runtime column UPDATE privileges differ from withdrawal only.")
        require(connection.execute("SELECT has_schema_privilege(current_user,'oaf_website','USAGE'),"
            "has_schema_privilege(current_user,'oaf_website','CREATE')").fetchone() == (True, False),
            "Unexpected runtime schema privileges.")
        require(connection.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user").fetchone() == (False,) * 5,
            "Unexpected powerful runtime role attributes.")
        # Revision metadata is intentionally private to migration authority.
        # Reuse the owner's settled 0003 result; do not change identity to read it.
        require(not connection.execute("SELECT has_table_privilege(current_user,"
            "'oaf_website.alembic_version','SELECT')").fetchone()[0],
            "Runtime unexpectedly has access to private migration metadata.")
        state_privileges = dict(connection.execute("""
            SELECT p,has_table_privilege(current_user,'oaf_website.state_requests',p)
            FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p
        """).fetchall())
        require(state_privileges == {p: p in {'SELECT', 'INSERT'} for p in state_privileges},
                "State Request permissions differ from SELECT/INSERT only.")
        require(not any(connection.execute("SELECT has_table_privilege(current_user,"
            "'oaf_website.notifications',%s)", (p + " WITH GRANT OPTION",)).fetchone()[0]
            for p in privileges), "Runtime has an unexpected notification grant option.")
        initial_notifications = notification_rows(connection)
        initial_states = rows(connection)
        initial_counts = counts(connection)
        report.update(identity=dict(database=identity[0], effective_user=identity[1],
            session_user=identity[2], host=identity[3], port=identity[4], postgresql_major=identity[5]),
            initial_notifications=summary(initial_notifications), initial_state_requests=len(initial_states),
            runtime_table_permissions=privileges, runtime_column_update=column_update,
            state_request_permissions=state_privileges, grant_options=False,
            migration_revision="0003_notifications CLOSED/PASS; owner-confirmed, private metadata not read",
            schema_usage=True, schema_create=False, powerful_role_attributes=False)
        print("TESTING runtime identity PASS; initial notifications=" +
              json.dumps(summary(initial_notifications)) + "; State Requests=" + str(len(initial_states)), flush=True)

        phase = "Flask integration"
        secret = recognition_secret()
        server_command = [sys.executable, "-B", str(ROOT / "ops/state_request_live_check.py"), "--server"]
        server_child = Child(server_command + ["0"])
        ready = server_child.receive()
        require(ready.get("event") == "ready", "Existing TESTING Flask host could not start.")
        port = ready["port"]
        origin = f"http://127.0.0.1:{port}"
        for path, marker in [("/gramanna.html", b"notification-form"),
                             ("/assets/notifications.js", b"/api/notifications"),
                             ("/api/notifications/session", b"csrf_token")]:
            with urlopen(origin + path, timeout=10) as response:
                require(response.status == 200 and marker in response.read(),
                        "Actual Flask notification integration is unavailable.")
        report.update(origin=origin, server_processes=[ready["pid"]],
                      recognition_storage="Existing current-user DPAPI key; preserved across restart",
                      transport="Explicit HTTP loopback testing; production HTTPS not validated")

        def verify(expected, label):
            current = notification_rows(connection)
            require(all(current.get(key) == value for key, value in initial_notifications.items()),
                    "A pre-existing notification row changed.")
            added = set(current) - set(initial_notifications)
            expected_keys = set()
            winners = {}
            for item in expected:
                candidates = item.get("candidates", [item["token"]] if "token" in item else [])
                digests = [hashlib.sha256(value.encode("ascii")).hexdigest() for value in candidates]
                matches = [key for key in digests if key in added]
                require(len(matches) == 1, "A lifecycle has other than one persisted receipt.")
                key = matches[0]
                expected_keys.add(key)
                winners[item["label"]] = digests.index(key)
                value = current[key]
                require(value[:6] == (item["email"].strip(" ").lower(), item["web_launch"],
                    item["android_launch"], item["ios_launch"], item["state"], CONSENT_VERSION),
                    "Persisted email normalization, consent or preferences differ from the browser submission.")
                require(value[6].tzinfo is not None and value[6] <= datetime.now(timezone.utc),
                        "Server-created consent timestamp is invalid.")
                require((value[7] is None) == item["active"], "Persisted withdrawal state differs.")
                require(value[7] is None or value[7] >= value[6], "Withdrawal predates consent.")
                if key in observed:
                    require(value[:7] == observed[key][:7], "An existing receipt's original data changed.")
                    if observed[key][7] is not None:
                        require(value[7] == observed[key][7], "Repeated withdrawal changed its original timestamp.")
                observed[key] = value
            require(added == expected_keys, "Unexpected notification records were committed.")
            report["database_checkpoints"].append(dict(test=label, status="PASS", **summary(current)))
            print("Independent PostgreSQL", label, "PASS:", json.dumps(summary(current)), flush=True)
            return winners

        phase = "Real Chromium lifecycle validation"
        browser_child = Child([str(browser_python), "-B", str(ROOT / "tests/notification_live_browser.py")])
        browser_child.send(dict(origin=origin, baseline=initial_counts, evidence_directory=str(destination)))
        while True:
            message = browser_child.receive(timeout=60)
            kind = message.get("event")
            if kind == "check":
                report["checks"].append(message["check"])
                print("Playwright PASS:", json.dumps(message["check"], sort_keys=True), flush=True)
            elif kind == "verify":
                winners = verify(message["lifecycles"], message["test"])
                browser_child.send(dict(event="verified", winners=winners))
            elif kind == "restart":
                before = notification_rows(connection)
                before_states = rows(connection)
                old_pid = server_child.process.pid
                server_child.close()
                server_child = Child(server_command + [str(port)])
                ready = server_child.receive()
                require(ready.get("event") == "ready" and ready["pid"] != old_pid,
                        "A different Flask process did not restart on the same port.")
                require(recognition_secret() == secret, "Protected key changed on restart.")
                require(notification_rows(connection) == before and rows(connection) == before_states,
                        "Database records changed during application restart.")
                report["server_processes"].append(ready["pid"])
                browser_child.send(dict(event="restarted"))
            elif kind == "complete":
                complete = message
                require(browser_child.process.wait(timeout=15) == 0, "Chromium worker failed to exit.")
                break
            else:
                raise RuntimeError("Chromium blocked in " + message.get("phase", "startup") +
                                   "; exception=" + message.get("exception_type", "closed_or_timeout") +
                                   "; assertion_line=" + str(message.get("assertion_line", "unknown")))
        require(len(report["checks"]) == 15, "Live browser checklist incomplete.")
        report.update(flask_integration="PASS", playwright="PASS", chromium=complete["chromium"],
                      screenshots=complete["screenshots"], browser_errors=0, external_requests=0)

        phase = "Independent final PostgreSQL verification"
        verify(complete["lifecycles"], "final")
        final_notifications = notification_rows(connection)
        require(summary(final_notifications) == dict(total=len(initial_notifications) + 8,
            active=summary(initial_notifications)["active"] + 6,
            withdrawn=summary(initial_notifications)["withdrawn"] + 2), "Final lifecycle counts differ.")
        final_states = rows(connection)
        require(all(final_states.get(key) == value for key, value in initial_states.items()),
                "A pre-existing State Request changed.")
        recognition = BrowserRecognition(secret)
        cookie_token = recognition.read(complete["state_cookie"])
        require(cookie_token is not None, "State Request browser recognition invalid.")
        key = str(recognition.browser_key(cookie_token))
        require(set(final_states) - set(initial_states) == {("CA", key), ("TX", key)},
                "Focused State Request regression persisted unexpected rows.")
        final_counts = counts(connection)
        require(final_counts == complete["state_counts"], "Independent State Request counts differ from browser/API.")
        require({s: final_counts[s] - initial_counts[s] for s in final_counts
                 if final_counts[s] != initial_counts[s]} == {"CA": 1, "TX": 1},
                "State Request regression deltas differ.")
        report["constraint_probes"] = database_probes(connection)
        require(notification_rows(connection) == final_notifications and rows(connection) == final_states,
                "Rollback-only verification probes changed persisted records.")
        require(not connection.execute("SELECT email FROM oaf_website.notifications "
            "WHERE unsubscribed_at IS NULL GROUP BY email HAVING count(*)>1").fetchall(),
            "Duplicate active subscriptions exist.")
        report.update(postgresql_verification="PASS", final_notifications=summary(final_notifications),
            notification_delta=dict(total=8, active=6, withdrawn=2),
            final_state_requests=len(final_states), state_request_delta=dict(CA=1, TX=1),
            initial_records_unchanged=True, rollback_probes_retained_rows=0,
            persisted_lifecycles=[dict(label=item["label"], web_launch=item["web_launch"],
                android_launch=item["android_launch"], ios_launch=item["ios_launch"],
                state=item["state"], consent_version=CONSENT_VERSION, active=item["active"])
                for item in complete["lifecycles"]], material_defects=[])
        print("PostgreSQL PASS: eight retained notification lifecycles (+6 active/+2 withdrawn); "
              "State Requests CA +1/TX +1; constraint and rollback probes retained zero rows.", flush=True)
    except Exception as error:
        safe = str(error) if type(error) is RuntimeError else type(error).__name__
        report["errors"].append(dict(phase=phase, reason=safe))
        print("BLOCKED:", phase, safe, flush=True)
    finally:
        for child in (browser_child, server_child):
            if child:
                child.close()
        if connection:
            try:
                report["observed_notifications_on_exit"] = summary(notification_rows(connection))
                report["observed_state_requests_on_exit"] = sum(counts(connection).values())
            except Exception:
                report["exit_inspection"] = "BLOCKED"
            connection.close()
        current_sources = inventory()
        changed = [name for name, digest in source_before.items() if current_sources.get(name) != digest]
        report["source_files_changed_during_execution"] = changed
        if changed:
            report["errors"].append(dict(phase="source preservation", reason="Existing source files changed."))
        report.update(finished_utc=datetime.now(timezone.utc).isoformat(),
            records_retained=True, migration_execution="None", role_or_credential_changes="None",
            git_writes="None", next_development_checkpoint=
            "Bind successful TESTING evidence to the unchanged approved 0003 artifacts and verify DEVELOPMENT "
            "0002 prerequisites; obtain separate owner authorization for the single DEVELOPMENT transition "
            "0002_state_requests -> 0003_notifications. No authorization issued or migration run here.")
        report["status"] = "PASS" if not report["errors"] and all(report[key] == "PASS" for key in
            ("flask_integration", "playwright", "postgresql_verification")) else "BLOCKED"
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        (destination / "report.json").write_text(encoded, encoding="utf-8")
        (destination / "report.txt").write_text("OAF WEBSITE LIVE NOTIFICATION VALIDATION\n" + encoded, encoding="utf-8")
        print("Complete sanitized report:", destination / "report.txt", flush=True)
        print("OVERALL:", report["status"], flush=True)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser-python", type=Path, required=True)
    arguments = parser.parse_args()
    sys.exit(run(arguments.browser_python))
