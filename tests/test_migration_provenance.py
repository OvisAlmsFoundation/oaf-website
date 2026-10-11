"""Final J9 physical-session identity/lifecycle evidence, cases A through L."""

import migration_offline as isolation
isolation.require_early_registration()

import pytest

from migration_offline import DriverError, FakeConnection
from oaf_website.migration_config import Failure
from test_migration_runner import failed


def replacement(conn, same_pid=True):
    # The SQLAlchemy wrapper and backend PID can stay the same while identity changes.
    conn.replace_physical_session(same_pid=same_pid)


def assert_original_cleanup_queries(conn, original):
    queries = [record for record in conn.physical_calls if
               "pg_advisory_unlock" in record[0] or
               ("AND granted" in record[0] and "pid=pg_catalog.pg_backend_pid()" in record[0])]
    assert len(queries) == 2
    for _, proxy, driver, pgconn in queries:
        assert proxy is original[0] and driver is original[1] and pgconn is original[2]


def test_j9_a_original_valid_unlock_succeeds(runner):
    conn = runner.connection
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    assert runner.run()["lock_outcome"] == "release_confirmed"
    assert_original_cleanup_queries(conn, original)
    assert not original[1].advisory_lock
    assert conn.reconnect_attempts == 0


@pytest.mark.parametrize("case,acknowledged", [("B", False), ("C", True)])
def test_j9_bc_unacknowledged_acquisition_original_absence(runner, case, acknowledged):
    conn = runner.connection
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    # Driver acknowledgment can be lost after the server acquired the lock.
    def acquisition(conn):
        conn.lock = acknowledged
        raise DriverError("08006")
    runner.connection.hooks["acquire"] = acquisition
    result = failed(runner, Failure.CONNECTION)
    assert result["lock_outcome"] == ("release_confirmed" if acknowledged else "absence_confirmed")
    assert not result["database_commit_confirmed"]
    assert_original_cleanup_queries(conn, original)
    assert result["cleanup"]["advisory_unlock"] == "confirmed_successful"
    assert result["secondary_failures"] == []
    assert not original[1].advisory_lock


@pytest.mark.parametrize("case", ["D", "E", "F", "G", "H", "dbapi", "driver", "pgconn", "closed", "broken", "pid"])
def test_j9_d_through_h_replacement_or_invalid_original_never_proves_release(runner, case):
    conn = runner.connection
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    conn.reconnect_on_access = True
    def invalidate(c):
        c.calls.append("invalidate_session")
        if case == "D":
            c.invalidated = True
        elif case in {"E", "F", "G"}:
            replacement(c, same_pid=case != "E")
        elif case == "H":
            c.proxy.is_valid = False
        elif case == "dbapi":
            c.proxy.dbapi_connection = object()
        elif case == "driver":
            c.proxy.driver_connection = object()
        elif case == "pgconn":
            c.driver.pgconn = object()
        elif case in {"closed", "broken"}:
            setattr(c.driver, case, True)
        else:
            c.driver.info.backend_pid = 999
    # Cleanup rollback returns normally but changes the physical lifecycle.
    conn.hooks["revision"] = DriverError("40P01")
    conn.hooks["rollback"] = [None, invalidate]
    result = failed(runner, Failure.DEADLOCK)
    assert result["lock_outcome"] == "release_unconfirmed"
    assert "unlock" not in conn.calls
    assert result["cleanup"]["advisory_unlock"] == "failed"
    assert not result["database_commit_confirmed"]
    assert result["failed_phase"] == "revision"
    assert result["secondary_failures"] == [
        {"component": component, "classification": Failure.CONNECTION}
        for component in ("rollback", "advisory_unlock", "rollback")]
    assert conn.reconnect_attempts == 0
    if case in {"D", "H"}:
        assert "physical_proxy" not in conn.calls[conn.calls.index("invalidate_session") + 1:]
    if case in {"E", "F", "G"}:
        assert not conn.driver.advisory_lock and original[1].advisory_lock
        assert conn.proxy is not original[0] and conn.driver is not original[1]
        if case in {"F", "G"}:
            assert conn.driver.info.backend_pid == original[1].info.backend_pid == 701


def test_j9_i_false_unlock_after_confirmed_acquisition(runner):
    runner.connection.hooks["unlock"] = lambda c: False
    result = failed(runner, Failure.TRANSACTION)
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["database_commit_confirmed"]
    assert result["classification"] == Failure.TRANSACTION
    assert result["secondary_failures"] == [{"component": "advisory_unlock", "classification": Failure.TRANSACTION}]


def test_j9_j_unlock_true_but_absence_verification_fails(runner):
    runner.connection.hooks["absence"] = DriverError("08006")
    result = failed(runner, Failure.CONNECTION)
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["secondary_failures"] == [{"component": "advisory_unlock", "classification": Failure.CONNECTION}]


def test_j9_k_cleanup_interrupted_after_primary_failure(runner):
    runner.connection.hooks["revision"] = DriverError("40P01")
    runner.connection.hooks["unlock"] = KeyboardInterrupt()
    result = failed(runner, Failure.DEADLOCK)
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["cleanup"]["advisory_unlock"] == "unconfirmed"
    assert result["interruption_phase"] == "cleanup_advisory_unlock"
    assert result["secondary_failures"] == [{"component": "advisory_unlock", "classification": Failure.INTERRUPTED}]


def test_j9_l_commit_uncertain_cleanup_cannot_confirm_release(runner):
    runner.connection.hooks["commit"] = DriverError("08006")
    result = failed(runner, Failure.UNCERTAIN_COMMIT)
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["cleanup"]["connection_close"] == "confirmed_successful"
    assert result["cleanup"]["engine_dispose"] == "confirmed_successful"
    assert not result["database_commit_confirmed"]
    assert "unlock" not in runner.connection.calls
    assert result["commit_certainty"] == "uncertain"
    assert result["transaction_outcome"] == "unknown"
    assert result["secondary_failures"] == [{"component": "commit", "classification": Failure.CONNECTION}]
    assert runner.connection.calls.count("commit") == 1


@pytest.mark.parametrize("invalidity", ["connection", "original_proxy"])
def test_j9_synthetic_property_reconnect_trap_is_effective(invalidity):
    conn = FakeConnection()
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    conn.lock = True
    conn.reconnect_on_access = True
    if invalidity == "connection":
        conn.invalidated = True
    else:
        conn.proxy.is_valid = False
    # Model check only: no production call and no driver/network access.
    assert conn.connection is conn.proxy
    assert conn.reconnect_attempts == 1
    assert conn.proxy is not original[0] and conn.driver is not original[1]
    assert conn.driver.info.backend_pid == original[1].info.backend_pid == 701
    assert original[1].advisory_lock and not conn.lock


def test_j9_successful_unlock_response_with_lock_present_is_unconfirmed(runner):
    conn = runner.connection
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    conn.hooks["revision"] = DriverError("40P01")
    conn.retain_lock_on_unlock = True
    conn.hooks["unlock"] = lambda c: True
    result = failed(runner, Failure.DEADLOCK)
    assert result["failed_phase"] == "revision"
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["secondary_failures"] == [{"component": "advisory_unlock", "classification": Failure.TRANSACTION}]
    assert conn.lock  # Successful unlock response cannot replace absence proof.
    assert_original_cleanup_queries(conn, original)


@pytest.mark.parametrize("boundary", ["unlock", "absence", "verification"])
def test_j9_physical_replacement_during_cleanup_verification(runner, boundary):
    conn = runner.connection
    original = (conn.proxy, conn.driver, conn.driver.pgconn)
    conn.hooks["revision"] = DriverError("40P01")
    def replace(c):
        replacement(c, same_pid=True)
    if boundary == "verification":
        def unlock(c):
            c.hooks["physical_proxy"] = replace
            return True
        conn.hooks["unlock"] = unlock
    else:
        conn.hooks[boundary] = replace
    result = failed(runner, Failure.DEADLOCK)
    assert result["failed_phase"] == "revision"
    assert result["lock_outcome"] == "release_unconfirmed"
    assert result["commit_certainty"] == "not_invoked"
    assert not result["database_commit_confirmed"]
    assert result["secondary_failures"] == [
        {"component": "advisory_unlock", "classification": Failure.CONNECTION},
        {"component": "rollback", "classification": Failure.CONNECTION}]
    assert conn.driver.info.backend_pid == original[1].info.backend_pid == 701
    assert not conn.lock
    assert conn.driver is not original[1]
    queries = [record for record in conn.physical_calls if
               "pg_advisory_unlock" in record[0] or
               ("AND granted" in record[0] and "pid=pg_catalog.pg_backend_pid()" in record[0])]
    assert len(queries) == (2 if boundary == "absence" else 1)
    for _, proxy, driver, pgconn in queries:
        assert proxy is original[0] and driver is original[1] and pgconn is original[2]
