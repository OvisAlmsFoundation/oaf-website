"""Explicit, default-off finite notification processing; never runs on import."""

from .notification_dispatch import diagnostic_error

import argparse
import json
import os
from datetime import datetime

from sqlalchemy import create_engine, event

from .brevo import load_brevo_config, TestingRecipientScope
from .confirmation_outbox import ConfirmationDispatcher, ConfirmationOutboxStore, ManagementIntentScope, ConfirmationIntentScope
from .database_config import (
    DatabaseConfig, DatabaseConfigurationError, _validate_environment,
    load_database_config, load_testing_database_config,
)
from .local_testing import recognition_secret
from .notification_dispatch import BatchResult, safe_failure, validate_failure
from .notification_messages import secure_confirmation_page
from .state_requests import _verify_checkout


def process_confirmations(*, expected_profile, enabled=False, credential_account=None,
                          confirmation_page=None, testing_recipient=None, environ=None, management_enabled=False,
                          intent_scope=None, releases_enabled=False):
    """Run exactly one existing batch, then dispose its runtime engine.

    Call only after operational authorization. Tests replace the existing loaders,
    engine and provider transport with guarded synthetic dependencies. Activation
    is independent of the public create_app(confirmation_enabled=...) flag.
    No secret is loaded while disabled or before environment/page validation.
    """
    engine = None
    result = BatchResult("unavailable")
    operation = "configuration"
    try:
        if type(enabled) is not bool or type(management_enabled) is not bool or type(releases_enabled) is not bool:
            raise diagnostic_error(ValueError("Processing activation requires an explicit boolean."), "process_confirmations", "processing_activation_boolean", stage="processor")
        if releases_enabled and not management_enabled:
            raise ValueError("Release processing requires current preference lifecycle controls.")
        environment = dict(os.environ if environ is None else environ)
        profile = _validate_environment(environment, expected_profile)
        if profile == "production":
            raise diagnostic_error(DatabaseConfigurationError("Production processing is deferred."), "process_confirmations", "production_processing_deferred", stage="processor")
        if not enabled:
            return BatchResult("disabled")
        # TESTING has no unscoped enabled invocation. Other profiles retain their
        # ordinary contract and cannot consume TESTING recipient configuration.
        if profile == "testing":
            scope = TestingRecipientScope(profile, testing_recipient)
        elif testing_recipient is not None:
            raise diagnostic_error(ValueError("Controlled recipients require TESTING."), "process_confirmations", "recipient_testing_only", stage="processor")
        else:
            scope = None
        if intent_scope is not None and (type(intent_scope) not in (ManagementIntentScope, ConfirmationIntentScope) or
                profile != "testing" or scope is None or not management_enabled or releases_enabled):
            raise diagnostic_error(ValueError("Exceptional scope requires controlled TESTING management."), "process_confirmations", "processing_intent_scope", stage="processor")
        page = secure_confirmation_page(confirmation_page)
        operation = "provider_configuration"
        provider = load_brevo_config(profile, credential_account=credential_account,
                                     environ=environment)
        operation = "database_configuration"
        config = (load_testing_database_config(environ=environment) if profile == "testing"
                  else load_database_config(expected_profile=profile, environ=environment))
        if type(config) is not DatabaseConfig or config.profile != profile:
            raise diagnostic_error(DatabaseConfigurationError("Runtime configuration must match the selected profile."), "process_confirmations", "processing_profile_match", stage="processor")
        # Never generate a replacement key on restart: existing capabilities and
        # durable intent recovery require the same protected key as the public API.
        operation = "protected_key"
        secret = recognition_secret(require_existing=True)
        operation = "engine"
        engine = create_engine(
            config.url, echo=False, hide_parameters=True, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "require_auth": "scram-sha-256",
                          "application_name": "oaf_website_confirmation_processor",
                          "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
        )
        event.listen(engine, "checkout", lambda dbapi, record, proxy:
                     _verify_checkout(config, dbapi, record, proxy))
        store_options = dict(recipient_scope=scope)
        if management_enabled:
            store_options["management_enabled"] = True
        if intent_scope is not None:
            store_options["intent_scope"] = intent_scope
        store = ConfirmationOutboxStore(engine, secret, profile, **store_options)
        operation = "dispatcher"
        result = ConfirmationDispatcher(store, provider, page).process(limit=10 if releases_enabled else 20)
        if releases_enabled and result.status == "processed":
            from .notification_delivery import NotificationDeliveryStore
            from .notification_dispatch import ReleaseDispatcher
            release_store = NotificationDeliveryStore(engine, secret, profile, management_enabled=management_enabled,
                releases_enabled=True, recipient_scope=scope,
                web_launch_url=environment.get("GRAMANNA_WEB_LAUNCH_URL"))
            dispatcher = ReleaseDispatcher(release_store, provider, page.rsplit("/", 1)[0] + "/manage-notifications.html")
            for event_id in release_store.pending_release_events():
                batch = dispatcher.process(event_id, limit=3)
                result = BatchResult(batch.status, result.processed + batch.processed,
                                     result.first_failure or batch.first_failure)
                if batch.status != "processed":
                    break
    except Exception as exc:
        # Never serialize driver/provider/configuration exceptions or retry here.
        result = BatchResult("unavailable", result.processed, result.first_failure or safe_failure("processor", operation, exc))
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as exc:
                # Preserve acknowledged progress even when local cleanup fails.
                result = BatchResult("unavailable", result.processed, result.first_failure or
                    safe_failure("processor", "dispose", exc, side_effects="acknowledged_outcomes_retained"))
    if result.first_failure is not None:
        from .notification_dispatch import _emit
        _emit(dict(operation="dispatcher", first_failure=validate_failure(result.first_failure)))
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes supplied values, including unknown arguments.
        raise diagnostic_error(ValueError("Invalid confirmation processor arguments."), "error", "processor_arguments", stage="processor")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--environment", required=True,
                        choices=("testing", "development", "production"))
    parser.add_argument("--enable-processing", action="store_true",
                        help="Explicit operational activation; omitted means OFF.")
    parser.add_argument("--enable-management", action="store_true",
                        help="Enable V2 outbox purposes only after migration 0006 and owner activation.")
    parser.add_argument("--enable-releases", action="store_true",
                        help="Include approved launch announcements only after matching migrations and owner activation.")
    parser.add_argument("--brevo-account", help="Existing protected credential account metadata.")
    parser.add_argument("--confirmation-page", help="Approved HTTPS /confirm-email.html page (legacy /gramanna.html accepted).")
    parser.add_argument("--testing-recipient", action="append",
                        help="One explicitly approved TESTING mailbox; supply exactly once.")
    for name in ("management-intent-fingerprint", "management-identity-fingerprint", "management-deadline"):
        parser.add_argument("--" + name, action="append")
    for name in ("confirmation-intent-fingerprint", "confirmation-identity-fingerprint", "confirmation-issued-at", "confirmation-expires-at"):
        parser.add_argument("--" + name, action="append")
    try:
        options = parser.parse_args(argv)
        if options.testing_recipient is not None and len(options.testing_recipient) != 1:
            raise diagnostic_error(ValueError("Exactly one controlled recipient is required."), "main", "processor_recipient_scope", stage="processor")
        values = [options.management_intent_fingerprint, options.management_identity_fingerprint, options.management_deadline]
        confirmation_values = [options.confirmation_intent_fingerprint, options.confirmation_identity_fingerprint,
                               options.confirmation_issued_at, options.confirmation_expires_at]
        intent_scope = None
        if any(value is not None for value in values) and any(value is not None for value in confirmation_values):
            raise diagnostic_error(ValueError("Exactly one exceptional purpose required."), "main", "processor_single_purpose", stage="processor")
        if any(value is not None for value in values):
            if any(value is None or len(value) != 1 for value in values):
                raise diagnostic_error(ValueError("Complete exceptional intent scope required once."), "main", "processor_scope_complete", stage="processor")
            intent_scope = ManagementIntentScope(values[0][0], values[1][0], datetime.fromisoformat(values[2][0].replace("Z", "+00:00")))
        if any(value is not None for value in confirmation_values):
            if any(value is None or len(value) != 1 for value in confirmation_values):
                raise diagnostic_error(ValueError("Complete original confirmation scope required once."), "main", "processor_confirmation_scope", stage="processor")
            intent_scope = ConfirmationIntentScope(confirmation_values[0][0], confirmation_values[1][0],
                datetime.fromisoformat(confirmation_values[3][0].replace("Z", "+00:00")),
                issued_at=datetime.fromisoformat(confirmation_values[2][0].replace("Z", "+00:00")))
    except ValueError as exc:
        print(json.dumps({"status": "unavailable", "processed": 0,
            "first_failure": safe_failure("processor", "arguments", exc)}), flush=True)
        return 2
    try:
        management_options = {"management_enabled": True} if options.enable_management else {}
        if options.enable_releases:
            management_options["releases_enabled"] = True
        if intent_scope is not None:
            management_options["intent_scope"] = intent_scope
        result = process_confirmations(
            expected_profile=options.environment, enabled=options.enable_processing,
            credential_account=options.brevo_account, confirmation_page=options.confirmation_page,
            testing_recipient=options.testing_recipient[0] if options.testing_recipient else None,
            **management_options,
        )
    except KeyboardInterrupt as exc:
        print(json.dumps({"status": "unavailable", "processed": getattr(exc, "acknowledged_processed", 0),
            "first_failure": safe_failure("processor", "dispatcher", exc, side_effects="submission_possible")}), flush=True)
        return 130
    output = {"status": result.status, "processed": result.processed}
    if result.first_failure is not None:
        output["first_failure"] = validate_failure(result.first_failure)
    print(json.dumps(output), flush=True)
    return {"processed": 0, "disabled": 2, "unavailable": 1}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())

