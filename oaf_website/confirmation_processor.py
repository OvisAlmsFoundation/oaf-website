"""Explicit, default-off one-shot confirmation processing; never runs on import."""

import argparse
import json
import os

from sqlalchemy import create_engine, event

from .brevo import load_brevo_config, TestingRecipientScope
from .confirmation_outbox import ConfirmationDispatcher, ConfirmationOutboxStore
from .database_config import (
    DatabaseConfig, DatabaseConfigurationError, _validate_environment,
    load_database_config, load_testing_database_config,
)
from .local_testing import recognition_secret
from .notification_dispatch import BatchResult
from .notification_messages import secure_confirmation_page
from .state_requests import _verify_checkout


def process_confirmations(*, expected_profile, enabled=False, credential_account=None,
                          confirmation_page=None, testing_recipient=None, environ=None):
    """Run exactly one existing batch, then dispose its runtime engine.

    Call only after operational authorization. Tests replace the existing loaders,
    engine and provider transport with guarded synthetic dependencies. Activation
    is independent of the public create_app(confirmation_enabled=...) flag.
    No secret is loaded while disabled or before environment/page validation.
    """
    engine = None
    result = BatchResult("unavailable")
    try:
        if type(enabled) is not bool:
            raise ValueError("Processing activation requires an explicit boolean.")
        environment = dict(os.environ if environ is None else environ)
        profile = _validate_environment(environment, expected_profile)
        if profile == "production":
            raise DatabaseConfigurationError("Production processing is deferred.")
        if not enabled:
            return BatchResult("disabled")
        # TESTING has no unscoped enabled invocation. Other profiles retain their
        # ordinary contract and cannot consume TESTING recipient configuration.
        if profile == "testing":
            scope = TestingRecipientScope(profile, testing_recipient)
        elif testing_recipient is not None:
            raise ValueError("Controlled recipients require TESTING.")
        else:
            scope = None
        page = secure_confirmation_page(confirmation_page)
        provider = load_brevo_config(profile, credential_account=credential_account,
                                     environ=environment)
        config = (load_testing_database_config(environ=environment) if profile == "testing"
                  else load_database_config(expected_profile=profile, environ=environment))
        if type(config) is not DatabaseConfig or config.profile != profile:
            raise DatabaseConfigurationError("Runtime configuration must match the selected profile.")
        # Never generate a replacement key on restart: existing capabilities and
        # durable intent recovery require the same protected key as the public API.
        secret = recognition_secret(require_existing=True)
        engine = create_engine(
            config.url, echo=False, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "require_auth": "scram-sha-256",
                          "application_name": "oaf_website_confirmation_processor",
                          "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
        )
        event.listen(engine, "checkout", lambda dbapi, record, proxy:
                     _verify_checkout(config, dbapi, record, proxy))
        store = ConfirmationOutboxStore(engine, secret, profile, recipient_scope=scope)
        result = ConfirmationDispatcher(store, provider, page).process(limit=20)
    except Exception:
        # Never serialize driver/provider/configuration exceptions or retry here.
        result = BatchResult("unavailable")
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                # Preserve acknowledged progress even when local cleanup fails.
                result = BatchResult("unavailable", result.processed)
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes supplied values, including unknown arguments.
        raise ValueError("Invalid confirmation processor arguments.")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--environment", required=True,
                        choices=("testing", "development", "production"))
    parser.add_argument("--enable-processing", action="store_true",
                        help="Explicit operational activation; omitted means OFF.")
    parser.add_argument("--brevo-account", help="Existing protected credential account metadata.")
    parser.add_argument("--confirmation-page", help="Approved HTTPS /confirm-email.html page (legacy /gramanna.html accepted).")
    parser.add_argument("--testing-recipient", action="append",
                        help="One explicitly approved TESTING mailbox; supply exactly once.")
    try:
        options = parser.parse_args(argv)
        if options.testing_recipient is not None and len(options.testing_recipient) != 1:
            raise ValueError("Exactly one controlled recipient is required.")
    except ValueError:
        print(json.dumps({"status": "unavailable", "processed": 0}), flush=True)
        return 2
    try:
        result = process_confirmations(
            expected_profile=options.environment, enabled=options.enable_processing,
            credential_account=options.brevo_account, confirmation_page=options.confirmation_page,
            testing_recipient=options.testing_recipient[0] if options.testing_recipient else None,
        )
    except KeyboardInterrupt:
        print(json.dumps({"status": "unavailable", "processed": 0}), flush=True)
        return 130
    print(json.dumps({"status": result.status, "processed": result.processed}), flush=True)
    return {"processed": 0, "disabled": 2, "unavailable": 1}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
