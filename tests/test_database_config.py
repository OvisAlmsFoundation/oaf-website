from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import URL, make_url

from oaf_website import database_config as db


FAKE_PASSWORD = "fake-only:@/ %?#[]\\unicode-é"
IDENTITIES = {
    "development": ("oaf_website_dev", "oaf_website_app"),
    "testing": ("oaf_website_test", "oaf_website_test_app"),
}


@pytest.fixture
def settings_path(tmp_path):
    path = tmp_path / "database.toml"
    path.write_bytes((Path(__file__).resolve().parents[1] / "config/database.example.toml").read_bytes())
    return path


def load(profile, path, provider=None, environ=None):
    return db.load_database_config(
        expected_profile=profile,
        environ={"OAF_ENV": profile} if environ is None else environ,
        local_config_path=path,
        credential_loader=Mock(return_value=FAKE_PASSWORD) if provider is None else provider,
    )


@pytest.mark.parametrize("profile", IDENTITIES)
def test_valid_profiles_retrieve_only_selected_credential(profile, settings_path):
    provider = Mock(return_value=FAKE_PASSWORD)
    config = load(profile, settings_path, provider)
    database, username = IDENTITIES[profile]
    provider.assert_called_once_with(
        f"OAF Website/{profile}/PostgreSQL", username, {"OAF_ENV": profile}
    )
    assert config.profile == profile
    assert config.url.database == database
    assert config.url.username == username
    assert config.url.host == "127.0.0.1"
    assert config.url.port == 5432
    assert config.url.drivername == "postgresql+psycopg"
    # Special characters remain a password, never SQLAlchemy URL components.
    assert config.url.password == FAKE_PASSWORD
    assert make_url(config.url.render_as_string(hide_password=False)) == config.url
    assert not config.url.query


@pytest.mark.parametrize("environ", [
    {}, {"OAF_ENV": ""}, {"OAF_ENV": "test"}, {"OAF_ENV": "Testing"},
    {"OAF_ENV": " testing"}, {"OAF_ENV": "development"}, {"OAF_ENV": "production"},
    {"OAF_ENV": FAKE_PASSWORD},
])
def test_testing_rejects_missing_or_incorrect_environment(environ, settings_path):
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError):
        db.load_testing_database_config(
            environ=environ, local_config_path=settings_path, credential_loader=provider
        )
    provider.assert_not_called()


def test_expected_profile_must_be_explicit_and_valid(settings_path):
    with pytest.raises(TypeError):
        db.load_database_config(environ={"OAF_ENV": "development"})
    with pytest.raises(db.DatabaseConfigurationError):
        load("unknown", settings_path)


@pytest.mark.parametrize("name", [
    "DATABASE_URL", "DATABASE_PASSWORD", "DB_HOST", "PGHOST", "PGPORT", "PGPASSWORD",
    "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGOPTIONS", "SQLALCHEMY_DATABASE_URI",
    "OAF_PROFILE", "OAF_DB_PASSWORD",
])
def test_conflicting_environment_is_rejected_before_credentials(name, settings_path):
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        load("testing", settings_path, provider, {"OAF_ENV": "testing", name: FAKE_PASSWORD})
    assert FAKE_PASSWORD not in str(caught.value)
    provider.assert_not_called()


@pytest.mark.parametrize("original,replacement", [
    ('database = "oaf_website_test"', 'database = "oaf_website_dev"'),
    ('database = "oaf_website_test"', 'database = "production"'),
    ('database = "oaf_website_dev"', 'database = "oaf_website_test"'),
    ('username = "oaf_website_test_app"', 'username = "oaf_website_app"'),
    ('username = "oaf_website_app"', 'username = "oaf_website_test_app"'),
    ('username = "oaf_website_test_app"', 'username = "postgres"'),
    ('host = "127.0.0.1"', 'host = "localhost"'),
    ('port = 5432', 'port = 5433'),
    ('port = 5432', 'port = "5432"'),
    ('port = 5432', 'port = true'),
    ('credential_service = "OAF Website/testing/PostgreSQL"',
     'credential_service = "OAF Website/development/PostgreSQL"'),
    ('credential_service = "OAF Website/development/PostgreSQL"',
     'credential_service = "OAF Website/testing/PostgreSQL"'),
    ('username = "oaf_website_test_app"', ''),
    ('[testing]', '[production]'),
    ('[testing]', '[unexpected]'),
])
def test_invalid_local_settings_are_rejected_before_credentials(original, replacement, settings_path):
    settings_path.write_text(settings_path.read_text().replace(original, replacement), encoding="utf-8")
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError):
        load("testing", settings_path, provider)
    provider.assert_not_called()


@pytest.mark.parametrize("content", [
    "", '[development]\nhost = "127.0.0.1"',
    'password = "fake-secret"', 'bad = "unterminated fake-secret',
    '[testing]\ndatabase = "fake-secret"\ndatabase = "fake-secret"',
    '[testing]\npassword = "fake-secret"',
])
def test_missing_unexpected_and_invalid_local_settings_are_redacted(content, settings_path):
    settings_path.write_text(content, encoding="utf-8")
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        load("testing", settings_path, provider)
    assert "fake-secret" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    provider.assert_not_called()


def test_missing_file_does_not_fall_back_to_template_or_another_profile(tmp_path):
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError):
        load("development", tmp_path / "missing.toml", provider)
    provider.assert_not_called()


def test_unexpected_extra_setting_is_rejected(settings_path):
    with settings_path.open("a") as source:
        source.write('\npassword = "fake-secret"\n')
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        load("testing", settings_path)
    assert "fake-secret" not in str(caught.value)


@pytest.mark.parametrize("password", [None, "", 123, b"fake-password"])
def test_missing_or_invalid_credentials(password, settings_path):
    with pytest.raises(db.DatabaseConfigurationError):
        load("testing", settings_path, Mock(return_value=password))


@pytest.mark.parametrize("error_type", [RuntimeError, db.DatabaseConfigurationError])
def test_provider_errors_do_not_leak_secrets(error_type, settings_path, capsys, caplog):
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        load("testing", settings_path, Mock(side_effect=error_type(FAKE_PASSWORD)))
    assert FAKE_PASSWORD not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    captured = capsys.readouterr()
    import json
    from oaf_website.notification_dispatch import validate_failure
    detail = json.loads(captured.err.split(": ", 1)[1])
    first = validate_failure(detail["first_failure"])
    assert first["predicate"] == "credential_readable" and first["stage"] == "startup"
    assert first["side_effects"] == "none" and first["exception_class"] == error_type.__name__
    assert FAKE_PASSWORD not in captured.out + captured.err
    assert not caplog.records


def fake_windows_backend(monkeypatch, *, credential=None, priority=5, error=None):
    getter = Mock(return_value=credential, side_effect=error)
    class FakeWinVaultKeyring:
        def get_credential(self, service, username):
            return getter(service, username)
    FakeWinVaultKeyring.priority = priority
    module = ModuleType("keyring.backends.Windows")
    module.WinVaultKeyring = FakeWinVaultKeyring
    monkeypatch.setitem(sys.modules, "keyring.backends.Windows", module)
    monkeypatch.setattr(db.sys, "platform", "win32")
    return getter


def test_windows_adapter_uses_only_exact_selected_reference(monkeypatch):
    getter = fake_windows_backend(monkeypatch, credential=SimpleNamespace(
        username="oaf_website_test_app", password=FAKE_PASSWORD
    ))
    assert db._windows_password("OAF Website/testing/PostgreSQL", "oaf_website_test_app", {}) == FAKE_PASSWORD
    getter.assert_called_once_with("OAF Website/testing/PostgreSQL", "oaf_website_test_app")


@pytest.mark.parametrize("environment", [
    {"PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring"},
    {"PYTHON_KEYRING_BACKEND": "keyring.backends.chainer.ChainerBackend"},
    {"PYTHON_KEYRING_BACKEND": "keyrings.alt.file.PlaintextKeyring"},
    {"PYTHON_KEYRING_BACKEND": ""}, {"KEYRING_PROPERTY_PASSWORD": FAKE_PASSWORD},
    {"OTHER_KEYRING_PROPERTY_GET_CREDENTIAL": FAKE_PASSWORD},
])
def test_unexpected_backend_settings_are_rejected(monkeypatch, environment):
    getter = fake_windows_backend(monkeypatch)
    with pytest.raises(db.DatabaseConfigurationError):
        db._windows_password("service", "username", environment)
    getter.assert_not_called()


@pytest.mark.parametrize("priority", [0, -1])
def test_unavailable_backend_rejected_before_retrieval(monkeypatch, priority):
    getter = fake_windows_backend(monkeypatch, priority=priority)
    with pytest.raises(db.DatabaseConfigurationError):
        db._windows_password("service", "username", {})
    getter.assert_not_called()


def test_missing_backend_or_dependency_is_redacted(monkeypatch):
    monkeypatch.setattr(db.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "keyring.backends.Windows", None)
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        db._windows_password("service", "username", {})
    assert caught.value.__context__ is None


def test_unexpected_backend_object_is_rejected(monkeypatch):
    fake_windows_backend(monkeypatch)
    getter = Mock()
    class WrongBackend:
        def __new__(cls):
            return SimpleNamespace(get_credential=getter, priority=5)
    monkeypatch.setattr(sys.modules["keyring.backends.Windows"], "WinVaultKeyring", WrongBackend)
    with pytest.raises(db.DatabaseConfigurationError):
        db._windows_password("service", "username", {})
    getter.assert_not_called()


def test_non_windows_platform_cannot_use_local_credentials(monkeypatch):
    monkeypatch.setattr(db.sys, "platform", "linux")
    with pytest.raises(db.DatabaseConfigurationError):
        db._windows_password("service", "username", {})


@pytest.mark.parametrize("credential", [
    None, SimpleNamespace(username="username", password=""),
    SimpleNamespace(username="other-account", password=FAKE_PASSWORD),
])
def test_backend_missing_or_swapped_credential_is_rejected(monkeypatch, credential):
    fake_windows_backend(monkeypatch, credential=credential)
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        db._windows_password("service", "username", {})
    assert FAKE_PASSWORD not in str(caught.value)


@pytest.mark.parametrize("error_type", [RuntimeError, db.DatabaseConfigurationError])
def test_backend_error_is_redacted(monkeypatch, error_type):
    fake_windows_backend(monkeypatch, error=error_type(FAKE_PASSWORD))
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        db._windows_password("service", "username", {})
    assert FAKE_PASSWORD not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


def test_default_provider_is_mocked_end_to_end(monkeypatch, settings_path):
    getter = fake_windows_backend(monkeypatch, credential=SimpleNamespace(
        username="oaf_website_test_app", password=FAKE_PASSWORD
    ))
    config = db.load_testing_database_config(environ={"OAF_ENV": "testing"}, local_config_path=settings_path)
    assert config.profile == "testing"
    getter.assert_called_once_with("OAF Website/testing/PostgreSQL", "oaf_website_test_app")


def test_process_environment_is_used_without_a_default_profile(monkeypatch, settings_path):
    monkeypatch.setattr(db.os, "environ", {"OAF_ENV": "testing"})
    config = db.load_testing_database_config(
        local_config_path=settings_path, credential_loader=Mock(return_value=FAKE_PASSWORD)
    )
    assert config.profile == "testing"
    monkeypatch.setattr(db.os, "environ", {})
    provider = Mock()
    with pytest.raises(db.DatabaseConfigurationError):
        db.load_testing_database_config(local_config_path=settings_path, credential_loader=provider)
    provider.assert_not_called()


def test_production_never_reads_local_config_or_windows_credentials(monkeypatch):
    read = Mock(side_effect=AssertionError("Production touched a local file"))
    credential = Mock(side_effect=AssertionError("Production touched Windows credentials"))
    monkeypatch.setattr(db, "_read_settings", read)
    monkeypatch.setattr(db, "_windows_password", credential)
    with pytest.raises(db.DatabaseConfigurationError, match="independently approved"):
        db.load_database_config(expected_profile="production", environ={"OAF_ENV": "production"})
    read.assert_not_called()
    credential.assert_not_called()


@pytest.mark.parametrize("database,username", [
    ("oaf_website_dev", "oaf_website_app"),
    ("oaf_website_test", "oaf_website_app"),
    ("oaf_website_dev", "oaf_website_test_app"), (FAKE_PASSWORD, FAKE_PASSWORD),
])
def test_connection_identity_seam_rejects_mismatches(database, username, settings_path):
    config = load("testing", settings_path)
    with pytest.raises(db.DatabaseConfigurationError) as caught:
        config.verify_connection_identity(database, username)
    assert FAKE_PASSWORD not in str(caught.value)


def test_connection_identity_seam_accepts_exact_identity(settings_path):
    config = load("testing", settings_path)
    config.verify_connection_identity("oaf_website_test", "oaf_website_test_app")


def test_diagnostics_do_not_display_secrets(settings_path, capsys, caplog):
    config = load("testing", settings_path)
    for diagnostic in (str(config), repr(config), str(config.url), repr(config.url)):
        assert FAKE_PASSWORD not in diagnostic
    assert capsys.readouterr() == ("", "")
    assert not caplog.records


@pytest.mark.parametrize("change", [
    {"database": "oaf_website_dev"}, {"username": "oaf_website_app"},
    {"host": "localhost"}, {"query": {"host": "production"}},
    {"drivername": "sqlite"}, {"password": None},
])
def test_configuration_object_cannot_hold_an_unapproved_url(change, settings_path):
    config = load("testing", settings_path)
    values = dict(drivername="postgresql+psycopg", username="oaf_website_test_app",
                  password=FAKE_PASSWORD, host="127.0.0.1", port=5432, database="oaf_website_test")
    values.update(change)
    with pytest.raises(db.DatabaseConfigurationError):
        db.DatabaseConfig("testing", URL.create(**values))


def test_configuration_location_is_repository_relative():
    assert db.LOCAL_CONFIG_PATH == Path(__file__).resolve().parents[1] / "config/local/database.toml"


def test_failure_recovers_only_after_explicit_correction(settings_path):
    provider = Mock(side_effect=[None, FAKE_PASSWORD])
    with pytest.raises(db.DatabaseConfigurationError):
        load("testing", settings_path, provider)
    config = load("testing", settings_path, provider)
    assert config.profile == "testing"
    assert config.url.database == "oaf_website_test"
    assert provider.call_count == 2
