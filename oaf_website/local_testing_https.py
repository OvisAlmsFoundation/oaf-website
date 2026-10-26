"""Explicit loopback TESTING HTTPS host. No processor, migration or certificate setup."""

from .notification_dispatch import diagnostic_error

import argparse
import os
from pathlib import Path
import ssl

from werkzeug.serving import make_server

from .notification_dispatch import report_failure
from .database_config import _validate_environment
from .local_development import QuietHandler
from .local_testing import ROOT, testing_https_app, validate_testing_https


def tls_context(certificate, private_key):
    """Use owner-provided existing PEM files only; no adhoc TLS or trust changes."""
    try:
        paths = tuple(Path(value) for value in (certificate, private_key))
        if (any(not path.is_absolute() or not path.is_file() for path in paths)
                or paths[0].resolve() == paths[1].resolve()):
            raise diagnostic_error(ValueError, "tls_context", "tls_files_distinct_existing", stage="startup")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        def no_password_prompt():
            raise diagnostic_error(ValueError("Interactive TLS key passwords are unavailable."), "tls_context", "tls_password_interaction_prohibited", stage="startup")
        context.load_cert_chain(str(paths[0]), str(paths[1]), password=no_password_prompt)
        return context
    except Exception:
        raise diagnostic_error(ValueError("Existing valid TLS certificate and private key are required."), "tls_context", "tls_certificate_key_valid", stage="startup") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise diagnostic_error(ValueError("Invalid TESTING HTTPS arguments."), "error", "https_arguments", stage="startup")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--environment", required=True, choices=("testing",))
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--confirmation-page", required=True,
                        help="Approved HTTPS /confirm-email.html page (legacy /gramanna.html accepted).")
    parser.add_argument("--tls-certificate", required=True)
    parser.add_argument("--tls-private-key", required=True)
    parser.add_argument("--enable-confirmation", action="store_true",
                        help="Explicit public confirmation activation; default OFF. No processing.")
    parser.add_argument("--enable-management", action="store_true",
                        help="Explicit V2 activation after approved migration 0006; default OFF.")
    parser.add_argument("--brevo-webhook-account", help="Protected bearer credential account metadata; never the token.")
    app = server = None
    result = 0
    first_failure = None
    operation = "arguments"
    try:
        options = parser.parse_args(argv)
        if Path.cwd().resolve() != ROOT:
            raise diagnostic_error(ValueError("Run from the website repository."), "main", "workspace_required", stage="startup")
        operation = "configuration"
        _validate_environment(dict(os.environ), options.environment)
        # Validate page/origin/activation before protected key/database access.
        # TLS file loading is explicit runtime work, never performed on import.
        validate_testing_https(public_origin=options.public_origin,
            confirmation_page=options.confirmation_page,
            confirmation_enabled=options.enable_confirmation)
        management_options = {}
        if options.enable_management:
            management_options["management_enabled"] = True
        if options.brevo_webhook_account is not None:
            if not options.enable_management:
                raise diagnostic_error(ValueError("Webhook processing requires management activation."), "main", "webhook_management_required", stage="startup")
            from .brevo_unsubscribe import load_brevo_webhook_config
            management_options["brevo_webhook_config"] = load_brevo_webhook_config("testing",
                credential_account=options.brevo_webhook_account)
        operation = "tls_context"
        context = tls_context(options.tls_certificate, options.tls_private_key)
        operation = "application_startup"
        app = testing_https_app(public_origin=options.public_origin,
            confirmation_page=options.confirmation_page,
            confirmation_enabled=options.enable_confirmation, **management_options)
        # Checkout invokes the existing exact TESTING identity verifier before bind.
        operation = "database_checkout"
        with app.extensions["state_requests_engine"].connect():
            pass
        operation = "server_bind"
        server = make_server("127.0.0.1", 443, app, threaded=True,
                             ssl_context=context, request_handler=QuietHandler)
        print("TESTING HTTPS READY: loopback port 443; confirmation " +
              ("ON" if options.enable_confirmation else "OFF") + "; processor OFF.", flush=True)
        operation = "server_execution"
        server.serve_forever()
    except KeyboardInterrupt:
        print("TESTING HTTPS stopped.", flush=True)
    except Exception as exc:
        first_failure = report_failure(operation, exc,
            stage="processor" if operation == "server_execution" else "startup",
            side_effects="database_transaction_unacknowledged" if operation == "server_execution" else "none")
        print("BLOCKED: TESTING HTTPS configuration or startup unavailable.", flush=True)
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
                    print("BLOCKED: TESTING HTTPS cleanup unavailable.", flush=True)
                    result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())

