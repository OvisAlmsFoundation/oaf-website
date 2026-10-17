"""Explicit loopback TESTING HTTPS host. No processor, migration or certificate setup."""

import argparse
import os
from pathlib import Path
import ssl

from werkzeug.serving import make_server

from .database_config import _validate_environment
from .local_development import QuietHandler
from .local_testing import ROOT, testing_https_app, validate_testing_https


def tls_context(certificate, private_key):
    """Use owner-provided existing PEM files only; no adhoc TLS or trust changes."""
    try:
        paths = tuple(Path(value) for value in (certificate, private_key))
        if (any(not path.is_absolute() or not path.is_file() for path in paths)
                or paths[0].resolve() == paths[1].resolve()):
            raise ValueError
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        def no_password_prompt():
            raise ValueError("Interactive TLS key passwords are unavailable.")
        context.load_cert_chain(str(paths[0]), str(paths[1]), password=no_password_prompt)
        return context
    except Exception:
        raise ValueError("Existing valid TLS certificate and private key are required.") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("Invalid TESTING HTTPS arguments.")


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
    app = server = None
    result = 0
    try:
        options = parser.parse_args(argv)
        if Path.cwd().resolve() != ROOT:
            raise ValueError("Run from the website repository.")
        _validate_environment(dict(os.environ), options.environment)
        # Validate page/origin/activation before protected key/database access.
        # TLS file loading is explicit runtime work, never performed on import.
        validate_testing_https(public_origin=options.public_origin,
            confirmation_page=options.confirmation_page,
            confirmation_enabled=options.enable_confirmation)
        context = tls_context(options.tls_certificate, options.tls_private_key)
        app = testing_https_app(public_origin=options.public_origin,
            confirmation_page=options.confirmation_page,
            confirmation_enabled=options.enable_confirmation)
        # Checkout invokes the existing exact TESTING identity verifier before bind.
        with app.extensions["state_requests_engine"].connect():
            pass
        server = make_server("127.0.0.1", 443, app, threaded=True,
                             ssl_context=context, request_handler=QuietHandler)
        print("TESTING HTTPS READY: loopback port 443; confirmation " +
              ("ON" if options.enable_confirmation else "OFF") + "; processor OFF.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print("TESTING HTTPS stopped.", flush=True)
    except Exception:
        print("BLOCKED: TESTING HTTPS configuration or startup unavailable.", flush=True)
        result = 2
    finally:
        for close in (server.server_close if server is not None else None,
                      app.extensions["state_requests_engine"].dispose if app is not None else None):
            if close is not None:
                try:
                    close()
                except Exception:
                    print("BLOCKED: TESTING HTTPS cleanup unavailable.", flush=True)
                    result = 2
    return result


if __name__ == "__main__":
    raise SystemExit(main())
