"""Fail-closed database configuration. No engines, connections, or secret writes."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
import tomllib
from typing import Callable

from sqlalchemy.engine import URL


LOCAL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/local/database.toml"
WINDOWS_BACKEND = "keyring.backends.Windows.WinVaultKeyring"
_PROFILES = frozenset({"development", "testing", "production"})
_LOCAL_IDENTITIES = {
    "development": ("oaf_website_dev", "oaf_website_app"),
    "testing": ("oaf_website_test", "oaf_website_test_app"),
}


class DatabaseConfigurationError(ValueError):
    """Safe, fixed-message configuration failure, suitable for startup reporting."""


def _approved_settings(profile: str) -> dict[str, str | int]:
    database, username = _LOCAL_IDENTITIES[profile]
    return {
        "host": "127.0.0.1",
        "port": 5432,
        "database": database,
        "username": username,
        "credential_service": f"OAF Website/{profile}/PostgreSQL",
    }


def _validate_environment(environ: Mapping[str, str], expected_profile: str) -> str:
    profile = environ.get("OAF_ENV")
    if expected_profile not in _PROFILES or profile not in _PROFILES:
        raise DatabaseConfigurationError("An explicit approved OAF_ENV profile is required.")
    if profile != expected_profile:
        raise DatabaseConfigurationError("OAF_ENV conflicts with the required application profile.")
    # There is one configuration authority; reject alternate URLs and libpq overrides.
    for name in environ:
        if (
            (name.startswith("OAF_") and name != "OAF_ENV")
            or name.startswith(("PG", "DB_", "DATABASE_"))
            or name == "SQLALCHEMY_DATABASE_URI"
        ):
            raise DatabaseConfigurationError("Unexpected or conflicting database environment settings.")
    return profile


def _read_settings(path: Path, profile: str) -> dict[str, str | int]:
    try:
        with path.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, ValueError):
        # Raise outside the handler: parser errors can contain supplied secret text.
        pass
    else:
        if (
            profile not in document
            or not document
            or not set(document).issubset(_LOCAL_IDENTITIES)
        ):
            raise DatabaseConfigurationError("Local configuration contains missing or unexpected profiles.")
        for section, settings in document.items():
            approved = _approved_settings(section)
            if not isinstance(settings, dict) or set(settings) != set(approved):
                raise DatabaseConfigurationError("Local configuration contains missing or unexpected settings.")
            if any(
                type(settings[name]) is not type(value) or settings[name] != value
                for name, value in approved.items()
            ):
                raise DatabaseConfigurationError("Local configuration does not match the approved profile identity.")
        return document[profile]
    raise DatabaseConfigurationError("Local database configuration is unavailable or invalid.")


def _windows_password(
    service: str, username: str, environ: Mapping[str, str], *, exact_target: bool = False,
) -> str:
    """Bind only the approved backend; never discover plugins or read keyringrc.cfg."""
    if sys.platform != "win32":
        raise DatabaseConfigurationError("The approved Windows credential backend is unavailable.")
    if (
        environ.get("PYTHON_KEYRING_BACKEND", WINDOWS_BACKEND) != WINDOWS_BACKEND
        # keyring 25.7.0 recognizes this substring anywhere in a variable name.
        or any("KEYRING_PROPERTY_" in name for name in environ)
    ):
        raise DatabaseConfigurationError("Unexpected credential backend configuration.")
    try:
        from keyring.backends.Windows import WinVaultKeyring

        backend = WinVaultKeyring()
        if type(backend) is not WinVaultKeyring or backend.priority <= 0:
            raise RuntimeError
    except Exception:
        pass
    else:
        try:
            if exact_target:
                # Stage 4C migrators use one generic, machine-local service
                # target. WinVault's get_credential may silently try a compound
                # username@service target on absence/account mismatch. Read the
                # exact target through the same pinned backend as activation.
                credential = backend._read_credential(service)
                if credential is not None and (
                    credential.get("TargetName") != service
                    or credential.get("UserName") != username
                    or credential.get("Type") != 1
                    or credential.get("Persist") != 2
                ):
                    raise RuntimeError
                account = None if credential is None else credential["UserName"]
                password = None if credential is None else credential.value
            else:
                credential = backend.get_credential(service, username)
                account = None if credential is None else credential.username
                password = None if credential is None else credential.password
        except Exception:
            pass
        else:
            if credential is None:
                raise DatabaseConfigurationError("The selected database credential is missing.")
            if account != username:
                raise DatabaseConfigurationError("The selected credential account does not match the profile.")
            if not isinstance(password, str) or not password:
                raise DatabaseConfigurationError("The selected database credential is missing.")
            return password
        raise DatabaseConfigurationError("The selected database credential could not be retrieved.")
    raise DatabaseConfigurationError("The approved Windows credential backend is unavailable.")


@dataclass(frozen=True)
class DatabaseConfig:
    """URL stays in memory and is excluded from diagnostic representations."""

    profile: str
    url: URL = field(repr=False)

    def __post_init__(self) -> None:
        if self.profile not in _LOCAL_IDENTITIES:
            raise DatabaseConfigurationError("Production database configuration is deferred.")
        approved = _approved_settings(self.profile)
        if (
            not isinstance(self.url, URL)
            or self.url.drivername != "postgresql+psycopg"
            or self.url.host != approved["host"]
            or type(self.url.port) is not int
            or self.url.port != approved["port"]
            or self.url.database != approved["database"]
            or self.url.username != approved["username"]
            or self.url.query
            or not isinstance(self.url.password, str)
            or not self.url.password
        ):
            raise DatabaseConfigurationError("Database URL does not match the approved profile identity.")

    def verify_connection_identity(self, database: str, username: str) -> None:
        """Later integration passes current_database() and current_user before any work.

        This pure check performs no query. Future connection setup must call it on
        every connection before application queries, including pooled connections.
        """
        approved = _approved_settings(self.profile)
        if database != approved["database"] or username != approved["username"]:
            raise DatabaseConfigurationError("Connected database identity does not match the selected profile.")


def load_database_config(
    *,
    expected_profile: str,
    environ: Mapping[str, str] | None = None,
    local_config_path: Path = LOCAL_CONFIG_PATH,
    credential_loader: Callable[[str, str, Mapping[str, str]], str] | None = None,
) -> DatabaseConfig:
    """Validate before retrieving one credential; never connect or select a fallback.

    expected_profile is required so each entry point declares its intended profile.
    Injection arguments are for deterministic tests, not environment overrides.
    Production deliberately fails before local files or Windows secret access.
    """
    environment = dict(os.environ if environ is None else environ)
    profile = _validate_environment(environment, expected_profile)
    if profile == "production":
        raise DatabaseConfigurationError("Production requires an independently approved secret provider; configuration is deferred.")
    settings = _read_settings(local_config_path, profile)
    provider = _windows_password if credential_loader is None else credential_loader
    try:
        password = provider(settings["credential_service"], settings["username"], environment)
    except Exception:
        pass
    else:
        if isinstance(password, str) and password:
            url = URL.create(
                "postgresql+psycopg",
                username=settings["username"],
                password=password,
                host=settings["host"],
                port=settings["port"],
                database=settings["database"],
            )
            return DatabaseConfig(profile, url)
        raise DatabaseConfigurationError("The selected database credential is missing.")
    raise DatabaseConfigurationError("The selected database credential could not be retrieved.")


def load_testing_database_config(**kwargs) -> DatabaseConfig:
    """Mandatory entry point for future database tests; OAF_ENV must be testing."""
    return load_database_config(expected_profile="testing", **kwargs)
