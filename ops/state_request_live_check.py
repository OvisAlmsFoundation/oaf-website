"""Guarded live TESTING coordinator. Run with the website Python interpreter.

Uses only the existing TESTING runtime credential; retains browser submissions.
Independent psycopg inspection, separate Flask processes and real Chromium.
No migration invocation, elevated database identity, reset or row cleanup.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oaf_website.database_config import load_testing_database_config
from oaf_website.local_testing import recognition_secret, testing_app
from oaf_website.state_request_schema import STATE_CODES
from oaf_website.state_requests import BrowserRecognition


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def server(port):
    from werkzeug.serving import WSGIRequestHandler, make_server

    class QuietHandler(WSGIRequestHandler):
        def log(self, *args, **kwargs):
            pass

    host = make_server("127.0.0.1", port, lambda env, start: [],
                       threaded=True, request_handler=QuietHandler)
    app = testing_app(host.server_port)
    # Real startup connection goes through the application's identity checkout.
    with app.extensions["state_requests_engine"].connect() as connection:
        from sqlalchemy import text
        connection.execute(text("SELECT count(*) FROM oaf_website.state_requests")).scalar_one()
    host.app = app
    print(json.dumps({"event": "ready", "port": host.server_port, "pid": os.getpid()}), flush=True)
    try:
        host.serve_forever()
    finally:
        host.server_close()
        app.extensions["state_requests_engine"].dispose()


class Child:
    def __init__(self, command):
        self.process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding="utf-8", bufsize=1)
        self.messages = queue.Queue()

        def read():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put({"event": "blocked", "reason": "Unexpected child output"})
            self.messages.put({"event": "closed"})

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, value):
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def receive(self, timeout=45):
        return self.messages.get(timeout=timeout)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        for stream in (self.process.stdin, self.process.stdout):
            if stream:
                stream.close()
        self.reader.join(timeout=2)


def counts(connection):
    result = {state: 0 for state in STATE_CODES}
    result.update(dict(connection.execute(
        "SELECT state, count(*) FROM oaf_website.state_requests GROUP BY state").fetchall()))
    return result


def rows(connection):
    return {(state, str(key)): created.isoformat() for state, key, created in
            connection.execute("SELECT state, browser_key, created_at "
                               "FROM oaf_website.state_requests").fetchall()}


def inventory():
    names = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
        text=True, encoding="utf-8").splitlines()
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in names if (ROOT / name).is_file()}


def run(browser_python):
    import psycopg

    report = {"started_utc": datetime.now(timezone.utc).isoformat(),
              "backend_integration": "BLOCKED", "playwright": "BLOCKED",
              "postgresql_persistence_counting": "BLOCKED", "checks": [],
              "records_preserved": True, "errors": []}
    destination = ROOT / ".pytest_cache" / ("state-request-live-" +
                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    destination.mkdir(parents=True, exist_ok=False)
    server_child = browser_child = connection = None
    original_files = inventory()
    phase = "TESTING preflight"
    try:
        require(Path.cwd().resolve() == ROOT, "Run only from the OAF Website repository.")
        require(sys.platform == "win32", "Native Windows execution is required.")
        require(os.environ.get("OAF_ENV") == "testing", "OAF_ENV must explicitly be testing.")
        require(browser_python.is_file(), "Existing shared Playwright interpreter is missing.")
        config = load_testing_database_config()
        # Independent direct driver access; never use the application's store to inspect rows.
        connection = psycopg.connect(
            host=config.url.host, port=config.url.port, dbname=config.url.database,
            user=config.url.username, password=config.url.password, autocommit=True,
            connect_timeout=5, require_auth="scram-sha-256",
            application_name="oaf_website_live_verification",
            options="-c statement_timeout=10000 -c lock_timeout=5000")
        identity = connection.execute("SELECT current_database(), current_user, session_user, "
                                      "host(inet_server_addr()), inet_server_port(), "
                                      "current_setting('server_version_num')::int / 10000").fetchone()
        config.verify_connection_identity(identity[0], identity[1])
        require(identity == ("oaf_website_test", "oaf_website_test_app", "oaf_website_test_app",
                             "127.0.0.1", 5432, 17), "Unexpected database connection identity.")
        privileges = dict(connection.execute("""
            SELECT p, has_table_privilege(current_user, 'oaf_website.state_requests', p)
            FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p
        """).fetchall())
        require(privileges == {"SELECT": True, "INSERT": True, "UPDATE": False, "DELETE": False,
                               "TRUNCATE": False, "REFERENCES": False, "TRIGGER": False},
                "Runtime State Request permissions differ from SELECT/INSERT only.")
        schema_privileges = connection.execute("SELECT has_schema_privilege(current_user, "
            "'oaf_website', 'USAGE'), has_schema_privilege(current_user, 'oaf_website', 'CREATE')").fetchone()
        require(schema_privileges == (True, False), "Runtime schema privileges are unexpected.")
        powerful = connection.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, "
            "rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        require(powerful == (False,) * 5, "Runtime role has unexpected powerful attributes.")
        initial_counts = counts(connection)
        initial_rows = rows(connection)
        report.update(identity={"database": identity[0], "effective_user": identity[1],
                                "session_user": identity[2], "host": identity[3],
                                "port": identity[4], "postgresql_major": identity[5]},
                      runtime_permissions=privileges, schema_usage=True, schema_create=False,
                      initial_counts=initial_counts, initial_total_rows=len(initial_rows))
        print("TESTING runtime identity and SELECT/INSERT-only permissions verified.", flush=True)

        phase = "Flask same-origin integration"
        secret = recognition_secret()
        server_child = Child([sys.executable, "-B", str(Path(__file__).resolve()), "--server", "0"])
        ready = server_child.receive()
        require(ready.get("event") == "ready", "Flask startup failed; exception=" +
                ready.get("exception_type", "child_closed_or_timeout"))
        port = ready["port"]
        origin = f"http://127.0.0.1:{port}"
        with urlopen(origin + "/api/state-requests/totals", timeout=10) as response:
            require(json.load(response)["totals"] == initial_counts, "Initial API and DB totals differ.")
        with urlopen(origin + "/gramanna.html", timeout=10) as response:
            require(response.status == 200 and b"state-request-form" in response.read(),
                    "Same-origin website is unavailable.")
        report.update(backend_integration="PASS", origin=origin,
                      recognition_storage="Windows current-user DPAPI; ignored local file",
                      local_http="Explicit loopback-only opt-in; HttpOnly, SameSite=Lax, one-year cookie",
                      server_processes=[ready["pid"]])
        print("Backend integration PASS: actual website and PostgreSQL API share", origin, flush=True)

        phase = "Chromium A-J"
        browser_child = Child([str(browser_python), "-B", str(ROOT / "tests/state_request_live_browser.py")])
        browser_child.send({"origin": origin, "baseline": initial_counts})
        while True:
            message = browser_child.receive()
            kind = message.get("event")
            if kind == "check":
                report["checks"].append(message["check"])
                print("Playwright", message["check"]["test"], "PASS:",
                      json.dumps(message["check"], sort_keys=True), flush=True)
            elif kind == "restart":
                before_restart = rows(connection)
                require(counts(connection) == message["counts"], "Pre-restart DB totals differ.")
                previous_pid = server_child.process.pid
                server_child.close()
                server_child = Child([sys.executable, "-B", str(Path(__file__).resolve()), "--server", str(port)])
                ready = server_child.receive()
                require(ready.get("event") == "ready" and ready["pid"] != previous_pid,
                        "A different Flask process did not restart.")
                require(recognition_secret() == secret, "Protected recognition key changed on restart.")
                require(rows(connection) == before_restart, "Rows changed during Flask restart.")
                report["server_processes"].append(ready["pid"])
                browser_child.send({"event": "restarted"})
            elif kind == "complete":
                completed = message
                require(browser_child.process.wait(timeout=15) == 0, "Chromium worker did not complete.")
                break
            else:
                require(False, "Browser worker blocked after " +
                        (report["checks"][-1]["test"] if report["checks"] else "startup") +
                        "; exception=" + message.get("exception_type", "child_closed_or_timeout"))
        require(len(report["checks"]) == 10, "The A-J checklist is incomplete.")
        report.update(playwright="PASS", chromium=completed["chromium"])

        phase = "Independent PostgreSQL persistence/counting"
        recognition = BrowserRecognition(secret)
        keys = {}
        for name, cookie in completed.pop("cookies").items():
            token = recognition.read(cookie)
            require(token is not None, "Browser recognition signature is invalid.")
            keys[name] = recognition.browser_key(token)
        require(len(set(keys.values())) == 3, "Independent contexts share a recognition identity.")
        final_counts = counts(connection)
        final_rows = rows(connection)
        expected_new = {("CA", str(keys["A"])), ("TX", str(keys["A"])),
                        ("CA", str(keys["B"])), ("CA", str(keys["C"]))}
        require(all(final_rows.get(key) == value for key, value in initial_rows.items()),
                "A pre-existing record changed.")
        require(set(final_rows) - set(initial_rows) == expected_new,
                "Persisted new records differ from the four browser submissions.")
        require(final_counts == completed["counts"], "Browser/API and independent DB counts differ.")
        delta = {state: final_counts[state] - initial_counts[state] for state in STATE_CODES}
        require({s: n for s, n in delta.items() if n} == {"CA": 3, "TX": 1},
                "Unexpected count changes.")
        require(not connection.execute("SELECT state, browser_key FROM oaf_website.state_requests "
            "GROUP BY state, browser_key HAVING count(*) > 1").fetchall(), "Duplicate persisted keys exist.")

        # An ordinary INSERT of a known own row must fail in PostgreSQL, independently of API code.
        try:
            with connection.transaction():
                connection.execute("INSERT INTO oaf_website.state_requests(state,browser_key) VALUES (%s,%s)",
                                   ("CA", keys["A"]))
                require(False, "Database accepted a duplicate key; probe rolled back.")
        except psycopg.errors.UniqueViolation as error:
            require(error.sqlstate == "23505" and error.diag.constraint_name == "state_requests_pk",
                    "Unexpected duplicate constraint failure.")
            report["duplicate_sqlstate"] = "23505"
        else:
            require(False, "Database accepted a duplicate key.")
        for invalid in ("ZZ", ""):
            try:
                with connection.transaction():
                    connection.execute("INSERT INTO oaf_website.state_requests(state,browser_key) VALUES (%s,%s)",
                                       (invalid, keys["A"]))
                    require(False, "Database accepted an invalid state; probe rolled back.")
            except psycopg.errors.CheckViolation as error:
                require(error.sqlstate == "23514" and error.diag.constraint_name == "state_requests_state_check",
                        "Unexpected invalid-state constraint failure.")
            else:
                require(False, "Database accepted an invalid state.")
        report["invalid_state_sqlstate"] = "23514"

        class RollbackProbe(Exception):
            pass

        rollback_key = uuid4()
        try:
            with connection.transaction():
                connection.execute("INSERT INTO oaf_website.state_requests(state,browser_key) VALUES (%s,%s)",
                                   ("WA", rollback_key))
                require(connection.execute("SELECT count(*) FROM oaf_website.state_requests "
                    "WHERE state='WA' AND browser_key=%s", (rollback_key,)).fetchone()[0] == 1,
                    "The rollback probe did not insert within its transaction.")
                require(not connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE,
                        "The probe did not enter a transaction.")
                raise RollbackProbe()
        except RollbackProbe:
            pass
        require(rows(connection) == final_rows, "A constraint/rollback probe changed persisted records.")
        require(connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE,
                "Independent connection did not return to idle after rollback.")
        report.update(postgresql_persistence_counting="PASS", final_counts=final_counts,
                      final_total_rows=len(final_rows), count_deltas=delta,
                      new_records=[{"browser": name, "state": state, "browser_key": str(key),
                                    "created_at": final_rows[(state, str(key))]}
                                   for name, key in keys.items()
                                   for state in (("CA", "TX") if name == "A" else ("CA",))],
                      rollback_probe="PASS; inserted within transaction then rolled back; no retained probe row",
                      constraints_preserved=True, initial_records_unchanged=True)
        print("PostgreSQL persistence/counting PASS: CA +3, TX +1; four retained browser records.", flush=True)
    except Exception as error:
        # Do not serialize raw exceptions, credentials, connection URLs, or SQL parameters.
        safe = str(error) if type(error) is RuntimeError else type(error).__name__
        report["errors"].append({"phase": phase, "reason": safe})
        print("BLOCKED:", phase, "-", safe, flush=True)
        if connection is not None:
            try:
                report["observed_counts_on_exit"] = counts(connection)
                if "initial_counts" in report:
                    report["observed_deltas_on_exit"] = {
                        s: report["observed_counts_on_exit"][s] - report["initial_counts"][s]
                        for s in STATE_CODES}
            except Exception:
                report["exit_database_inspection"] = "BLOCKED"
    finally:
        for child in (browser_child, server_child):
            if child:
                child.close()
        if connection:
            connection.close()
        current = inventory()
        changed = [name for name, digest in original_files.items() if current.get(name) != digest]
        report["repository_files_changed_during_run"] = changed
        if changed:
            report["errors"].append({"phase": "preservation", "reason": "Existing source files changed during execution"})
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["report_directory"] = str(destination)
        report["status"] = "PASS" if not report["errors"] and all(report[k] == "PASS" for k in
            ("backend_integration", "playwright", "postgresql_persistence_counting")) else "BLOCKED"
        report["next_checkpoint"] = ("Local TESTING integration complete; review the evidence and choose the next "
            "implementation scope. Production HTTPS routing/secret provisioning remain a separate checkpoint."
            if report["status"] == "PASS" else "Resolve the reported native blocker/defect, then rerun against the new baseline; preserve all records.")
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        (destination / "report.json").write_text(encoded, encoding="utf-8")
        (destination / "report.txt").write_text("OAF WEBSITE LIVE STATE REQUEST VALIDATION\n" + encoded, encoding="utf-8")
        print("Complete report:", destination / "report.txt", flush=True)
        print(encoded, flush=True)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=int)
    parser.add_argument("--browser-python", type=Path)
    arguments = parser.parse_args()
    if arguments.server is not None:
        try:
            server(arguments.server)
        except Exception as error:
            print(json.dumps({"event": "blocked", "exception_type": type(error).__name__}), flush=True)
            sys.exit(2)
    elif arguments.browser_python is not None:
        sys.exit(run(arguments.browser_python))
    else:
        parser.error("Use the guarded PowerShell launcher or provide --browser-python.")
