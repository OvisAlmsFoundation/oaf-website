"""Normal loopback DEVELOPMENT host; no migrations or database administration."""

from .notification_dispatch import diagnostic_error

import argparse
import os
from pathlib import Path
import re
import stat
import tomllib

from flask import send_file
from sqlalchemy import text
from werkzeug.serving import WSGIRequestHandler, make_server

from .notification_dispatch import report_failure
from .database_config import DatabaseConfigurationError, _validate_environment, _windows_password
from .integrations import IntegrationConfig, IntegrationConfigurationError
from .local_testing import PUBLIC_FILES, ROOT, SECRET_PATH, recognition_secret
from .state_requests import create_app

HOST = "127.0.0.1"
PORT = 5055
ORIGIN = f"http://{HOST}:{PORT}"
ADDRESS = ORIGIN + "/gramanna.html"
READY_LINE = "DEVELOPMENT READY: " + ADDRESS
INTEGRATION_PATH = ROOT / "config/local/integrations.toml"
INTEGRATION_SERVICES = (
    "OAF Website/development/Integrations/Submission",
    "OAF Website/development/Integrations/Reporting",
)


def load_development_integration_config(*, local_config_path=INTEGRATION_PATH,
                                        environ=None, credential_loader=None):
    """Load requested DEVELOPMENT configuration; never provision or use a fallback.

    Only non-secret client metadata belongs in TOML. Credentials come from the
    existing pinned Windows backend, using exact machine-local generic targets.
    Injection arguments support offline tests, not runtime location overrides.
    """
    environment = dict(os.environ if environ is None else environ)
    _validate_environment(environment, "development")
    for path in (ROOT, ROOT / "config", local_config_path.parent, local_config_path):
        if path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise diagnostic_error(IntegrationConfigurationError("Redirected integration configuration locations are prohibited."), "load_development_integration_config", "integration_location", stage="startup")
        if path.is_symlink():
            raise diagnostic_error(IntegrationConfigurationError("Redirected integration configuration locations are prohibited."), "load_development_integration_config", "integration_location", stage="startup")
    try:
        with local_config_path.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, ValueError):
        # Parser/IO exceptions may contain private supplied text; discard them.
        pass
    else:
        settings = document.get("development")
        if (set(document) != {"development"} or type(settings) is not dict
                or set(settings) != {"client_id"} or type(settings["client_id"]) is not str
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", settings["client_id"], re.ASCII) is None):
            raise diagnostic_error(IntegrationConfigurationError("Invalid DEVELOPMENT integration metadata."), "load_development_integration_config", "integration_metadata", stage="startup")
        provider = _windows_password if credential_loader is None else credential_loader
        try:
            submission, reporting = (
                provider(service, settings["client_id"], environment, exact_target=True)
                for service in INTEGRATION_SERVICES
            )
        except Exception:
            pass
        else:
            return IntegrationConfig("development", settings["client_id"], submission, reporting)
        raise diagnostic_error(IntegrationConfigurationError("DEVELOPMENT integration credentials are unavailable."), "load_development_integration_config", "integration_credentials", stage="startup")
    raise diagnostic_error(IntegrationConfigurationError("DEVELOPMENT integration metadata is missing or invalid."), "load_development_integration_config", "integration_metadata_read", stage="startup")


class QuietHandler(WSGIRequestHandler):
    # Keep native PowerShell's stderr pipeline free of routine access logs.
    def log(self, *args, **kwargs):
        pass


def development_app(*, enable_integrations=False):
    if os.environ.get("OAF_ENV") != "development":
        raise diagnostic_error(RuntimeError("This launcher requires OAF_ENV=development; no profile fallback is permitted."), "development_app", "environment_development_required", stage="startup")
    if type(enable_integrations) is not bool:
        raise diagnostic_error(IntegrationConfigurationError("Integration activation requires an explicit boolean."), "development_app", "integration_activation_boolean", stage="startup")
    # Preserve the existing protected key and explicit public-file allowlist.
    # Importing local_testing does not load its credential or connect to TESTING.
    for path in (ROOT, ROOT / "config", SECRET_PATH.parent, SECRET_PATH):
        if (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) or path.is_symlink():
            raise diagnostic_error(RuntimeError("Redirected workspace/configuration/key locations are prohibited."), "development_app", "key_location_not_redirected", stage="startup")
    integration_config = load_development_integration_config() if enable_integrations else None
    app = create_app(expected_profile="development", recognition_secret=recognition_secret(),
                     public_origin=ORIGIN, allow_insecure_localhost=True,
                     integration_config=integration_config)
    for number, name in enumerate(PUBLIC_FILES):
        if not (ROOT / name).is_file():
            raise diagnostic_error(RuntimeError("A required public website file is missing."), "development_app", "public_file_present", stage="startup")
        app.add_url_rule("/" + name, f"public_{number}",
                         lambda filename=name: send_file(ROOT / filename))
    app.add_url_rule("/", "home", lambda: send_file(ROOT / "index.html"))
    return app


def verify_runtime(app):
    """Read-only startup check using the application's verified runtime checkout."""
    with app.extensions["state_requests_engine"].connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        usage, create = connection.execute(text(
            "SELECT has_schema_privilege(current_user, 'oaf_website', 'USAGE'), "
            "has_schema_privilege(current_user, 'oaf_website', 'CREATE')"
        )).one()
        privileges = dict(connection.execute(text(
            "SELECT p, has_table_privilege(current_user, 'oaf_website.state_requests', p) "
            "FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p"
        )).all())
        if not usage or not privileges["SELECT"] or not privileges["INSERT"]:
            raise diagnostic_error(RuntimeError("DEVELOPMENT runtime requires schema USAGE and State Request SELECT/INSERT; "
                               "permission changes require separate owner approval."), "verify_runtime", "database_required_privileges", stage="startup")
        powerful = connection.execute(text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        )).one()
        if create or any(powerful) or any(value for key, value in privileges.items()
                                        if key not in {"SELECT", "INSERT"}):
            raise diagnostic_error(RuntimeError("DEVELOPMENT runtime permissions exceed the approved application scope."), "verify_runtime", "database_excess_privileges", stage="startup")
        # Verify real table access without submitting a request or reading browser identifiers.
        connection.execute(text("SELECT count(*) FROM oaf_website.state_requests")).scalar_one()
    # Closing the connection rolls back the read-only transaction before normal use.


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise diagnostic_error(ValueError("Invalid DEVELOPMENT arguments."), "arguments", "development_arguments", stage="startup")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--integrations", action="store_true",
                        help="Require protected DEVELOPMENT shared-service configuration.")
    app = server = None
    result = 0
    first_failure = None
    operation = "arguments"
    try:
        options = parser.parse_args(argv)
        operation = "application_startup"
        if Path.cwd().resolve() != ROOT:
            raise diagnostic_error(RuntimeError("Run from the OAF Website repository root."), "main", "workspace_required", stage="startup")
        app = development_app(enable_integrations=options.integrations)
        operation = "database_checkout"
        verify_runtime(app)
        operation = "server_bind"
        server = make_server(HOST, PORT, app, threaded=True, request_handler=QuietHandler)
        print("Runtime verified: oaf_website_dev / oaf_website_app; SCRAM; SELECT/INSERT only.", flush=True)
        print("Browser recognition: existing persistent Windows-user DPAPI key; HttpOnly; SameSite=Lax.", flush=True)
        print("Stop the server with Ctrl+C in this terminal.", flush=True)
        print(READY_LINE, flush=True)
        operation = "server_execution"
        server.serve_forever()
    except KeyboardInterrupt:
        print("DEVELOPMENT server stopped.", flush=True)
    except (DatabaseConfigurationError, IntegrationConfigurationError, RuntimeError) as error:
        first_failure = report_failure(operation, error,
            stage="processor" if operation == "server_execution" else "startup",
            side_effects="database_transaction_unacknowledged" if operation == "server_execution" else "none")
        print("BLOCKED: DEVELOPMENT configuration unavailable.", flush=True)
        result = 2
    except Exception as error:
        # Driver errors can include private connection details; never print them.
        first_failure = report_failure(operation, error,
            stage="processor" if operation == "server_execution" else "startup",
            side_effects="database_transaction_unacknowledged" if operation == "server_execution" else "none")
        print("BLOCKED: DEVELOPMENT startup/server failed.", flush=True)
        result = 2
    finally:
        for close in (server.server_close if server is not None else None,
                      app.extensions["state_requests_engine"].dispose if app is not None else None):
            if close is not None:
                try:
                    close()
                except Exception as exc:
                    cleanup = report_failure("dispose", exc, stage="processor",
                        side_effects="database_transaction_unacknowledged", first_failure=first_failure)
                    first_failure = first_failure or cleanup
                    result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())

