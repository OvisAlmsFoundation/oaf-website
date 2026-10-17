"""Normal loopback DEVELOPMENT host; no migrations or database administration."""

import argparse
import os
from pathlib import Path
import re
import stat
import tomllib

from flask import send_file
from sqlalchemy import text
from werkzeug.serving import WSGIRequestHandler, make_server

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
        if path.exists() and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise IntegrationConfigurationError("Redirected integration configuration locations are prohibited.")
        if path.is_symlink():
            raise IntegrationConfigurationError("Redirected integration configuration locations are prohibited.")
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
            raise IntegrationConfigurationError("Invalid DEVELOPMENT integration metadata.")
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
        raise IntegrationConfigurationError("DEVELOPMENT integration credentials are unavailable.")
    raise IntegrationConfigurationError("DEVELOPMENT integration metadata is missing or invalid.")


class QuietHandler(WSGIRequestHandler):
    # Keep native PowerShell's stderr pipeline free of routine access logs.
    def log(self, *args, **kwargs):
        pass


def development_app(*, enable_integrations=False):
    if os.environ.get("OAF_ENV") != "development":
        raise RuntimeError("This launcher requires OAF_ENV=development; no profile fallback is permitted.")
    if type(enable_integrations) is not bool:
        raise IntegrationConfigurationError("Integration activation requires an explicit boolean.")
    # Preserve the existing protected key and explicit public-file allowlist.
    # Importing local_testing does not load its credential or connect to TESTING.
    for path in (ROOT, ROOT / "config", SECRET_PATH.parent, SECRET_PATH):
        if path.exists() and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError("Redirected workspace/configuration/key locations are prohibited.")
    integration_config = load_development_integration_config() if enable_integrations else None
    app = create_app(expected_profile="development", recognition_secret=recognition_secret(),
                     public_origin=ORIGIN, allow_insecure_localhost=True,
                     integration_config=integration_config)
    for number, name in enumerate(PUBLIC_FILES):
        if not (ROOT / name).is_file():
            raise RuntimeError("A required public website file is missing.")
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
            raise RuntimeError("DEVELOPMENT runtime requires schema USAGE and State Request SELECT/INSERT; "
                               "permission changes require separate owner approval.")
        powerful = connection.execute(text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        )).one()
        if create or any(powerful) or any(value for key, value in privileges.items()
                                        if key not in {"SELECT", "INSERT"}):
            raise RuntimeError("DEVELOPMENT runtime permissions exceed the approved application scope.")
        # Verify real table access without submitting a request or reading browser identifiers.
        connection.execute(text("SELECT count(*) FROM oaf_website.state_requests")).scalar_one()
    # Closing the connection rolls back the read-only transaction before normal use.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integrations", action="store_true",
                        help="Require protected DEVELOPMENT shared-service configuration.")
    options = parser.parse_args(argv)
    app = server = None
    try:
        if Path.cwd().resolve() != ROOT:
            raise RuntimeError("Run from the OAF Website repository root.")
        app = development_app(enable_integrations=options.integrations)
        verify_runtime(app)
        server = make_server(HOST, PORT, app, threaded=True, request_handler=QuietHandler)
        print("Runtime verified: oaf_website_dev / oaf_website_app; SCRAM; SELECT/INSERT only.", flush=True)
        print("Browser recognition: existing persistent Windows-user DPAPI key; HttpOnly; SameSite=Lax.", flush=True)
        print("Stop the server with Ctrl+C in this terminal.", flush=True)
        print(READY_LINE, flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print("DEVELOPMENT server stopped.", flush=True)
    except (DatabaseConfigurationError, IntegrationConfigurationError, RuntimeError) as error:
        print("BLOCKED: " + str(error), flush=True)
        return 2
    except Exception as error:
        # Driver errors can include private connection details; never print them.
        print("BLOCKED: DEVELOPMENT startup/server failed (" + type(error).__name__ + ").", flush=True)
        return 2
    finally:
        if server is not None:
            server.server_close()
        if app is not None:
            app.extensions["state_requests_engine"].dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
