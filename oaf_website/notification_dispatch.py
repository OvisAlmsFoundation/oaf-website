"""Internal bounded release processor. No route, worker, scheduler or activation."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import os
import sys
from pathlib import Path
from threading import RLock
from uuid import uuid4



@dataclass(frozen=True)
class BatchResult:
    status: str
    processed: int = 0
    first_failure: dict | None = field(default=None, compare=False, repr=False)


FAILURE_OPERATIONS = frozenset({
    "arguments", "configuration", "provider_configuration", "database_configuration",
    "protected_key", "engine", "dispatcher", "dispose", "selection_recovery",
    "claim", "preparation", "outcome", "provider_submit", "recipient_scope",
    "database_begin", "advisory_lock", "database_clock", "transaction_commit",
    "template", "intent_scope", "processor_result", "terminal_publication",
    "transaction_body", "transaction_rollback", "audit_insert", "subscription_update",
    "management_view", "management_authority", "management_save", "management_recovery", "withdrawal_receipt",
    "withdrawal_ack", "legacy_unsubscribe", "brevo_unsubscribe",
    "webhook_configuration", "webhook_authentication", "webhook_media_type",
    "webhook_json", "webhook_event", "webhook_correlation",
})
FAILURE_CLASSES = frozenset({"ValueError", "RuntimeError", "OSError", "TimeoutError",
    "ConnectionError", "OperationalError", "IntegrityError", "ProgrammingError",
    "InterfaceError", "DatabaseError", "DatabaseConfigurationError", "BrevoConfigurationError",
    "ManagementIntentMismatch", "ManagementUnavailable", "KeyboardInterrupt",
    "JSONDecodeError", "UnicodeDecodeError", "RecursionError", "OverflowError",
    "BadRequest", "RequestEntityTooLarge", "TypeError", "KeyError", "TOMLDecodeError", "PermissionError", "FileNotFoundError", "CalledProcessError", "BrokenPipeError", "SSLError", "SMTPException", "SMTPAuthenticationError",
    "SMTPDataError", "SMTPRecipientsRefused", "DeliveryUnavailable", "DeliveryUncertain",
    "IntegrationConfigurationError", "ManagementConflict", "ManagementInputError"})
SIDE_EFFECTS = frozenset({"none", "database_transaction_unacknowledged",
    "database_commit_uncertain", "submission_not_started", "submission_possible",
    "acknowledged_outcomes_retained", "database_rolled_back", "database_rollback_uncertain", "database_committed"})
FAILURE_PREDICATES = frozenset({"operation_failed", "exact_intent_scope", "outcome_not_acknowledged", "invalid_result",
    "intent_purpose", "intent_revision", "intent_identity", "intent_lifecycle_binding", "intent_deadline", "intent_attempt",
    "management_unavailable", "management_request_shape", "management_cookie_missing",
    "capability_format", "capability_environment", "capability_signature", "capability_revision_range",
    "capability_not_yet_valid", "capability_expired", "capability_lifetime",
    "lifecycle_missing", "capability_predates_lifecycle", "lifecycle_withdrawn", "lifecycle_revision",
    "consent_unverified", "browser_format", "session_cookie_format", "session_cookie_signature",
    "session_shape", "session_browser", "session_not_yet_valid", "session_expired",
    "session_lifetime", "session_capability_expiry", "session_capability_issue",
    "webhook_config_present", "webhook_store_present", "webhook_https", "webhook_no_query",
    "webhook_authorization_ascii", "webhook_authorization_match", "webhook_json_media_type",
    "webhook_json_decode", "webhook_json_unique_keys", "webhook_json_finite_constants",
    "webhook_event_object", "webhook_required_fields", "webhook_allowed_fields", "webhook_event_name",
    "webhook_ts_event_integer", "webhook_ts_event_range", "webhook_ts_integer", "webhook_ts_range",
    "webhook_id_integer", "webhook_id_range", "webhook_template_id_integer", "webhook_template_id_range",
    "webhook_contact_id_integer", "webhook_contact_id_range", "webhook_ts_epoch_integer", "webhook_ts_epoch_range",
    "webhook_date_text", "webhook_date_length", "webhook_subject_text", "webhook_subject_length",
    "webhook_custom_text", "webhook_custom_length", "webhook_tag_text", "webhook_tag_length",
    "webhook_sending_ip_text", "webhook_sending_ip_length", "webhook_user_agent_text", "webhook_user_agent_length",
    "webhook_device_used_text", "webhook_device_used_length", "webhook_mirror_link_text", "webhook_mirror_link_length",
    "webhook_tags_array", "webhook_tags_count", "webhook_tags_text", "webhook_tags_length",
    "webhook_email_format", "webhook_message_id_text", "webhook_message_id_length", "webhook_message_id_format",
    "webhook_event_time_supported", "webhook_original_time_supported", "webhook_event_not_future", "webhook_time_order",
    "webhook_attempt_parent_present", "webhook_parent_accepted", "webhook_parent_outcome", "webhook_parent_message",
    "webhook_parent_accepted_at", "webhook_attempt_present", "webhook_attempt_outcome", "webhook_attempt_message",
    "webhook_attempt_submitting_at", "webhook_attempt_finished_at", "webhook_acceptance_time_match",
    "webhook_attempt_time_order", "webhook_latest_attempt_match", "webhook_release_present", "webhook_release_environment",
    "webhook_accepted_message_present", "webhook_accepted_message_unique", "webhook_subscriber_present",
    "webhook_recipient_match", "webhook_original_after_submission", "webhook_event_after_submission"})


PRECISE_PREDICATES = frozenset(['configuration_fields', 'configuration_identity', 'configuration_profiles', 'configuration_readable_toml', 'confirmation_activation_boolean', 'confirmation_authority', 'confirmation_enabled', 'confirmation_fields', 'confirmation_input', 'confirmation_lifecycle_active', 'confirmation_not_expired', 'confirmation_not_future', 'confirmation_not_suppressed', 'confirmation_persistence', 'confirmation_reservation', 'confirmation_template_token', 'confirmation_token_format', 'confirmation_token_present', 'contact_config_fields', 'contact_config_location', 'contact_config_profiles', 'contact_config_size', 'contact_controls', 'contact_email_length', 'contact_fields', 'contact_input', 'contact_message_length', 'contact_message_required', 'contact_not_submitted', 'contact_pending_or_full', 'contact_previous_uncertain', 'contact_profile', 'contact_rate_limit', 'contact_submission_unknown', 'contact_word_limit', 'credential_account_match', 'credential_backend_available', 'credential_backend_override', 'credential_present', 'credential_readable', 'credential_target_metadata', 'credential_windows_required', 'csrf_browser_missing', 'csrf_header_format', 'csrf_signature', 'database_connection_identity', 'database_excess_privileges', 'database_required_privileges', 'database_url_identity', 'email_ascii', 'email_length_and_separator', 'email_mailbox_syntax', 'environment_development_required', 'environment_override_prohibited', 'environment_profile_match', 'environment_profile_required', 'environment_testing_required', 'http_rejection', 'https_arguments', 'https_origin_page_match', 'https_origin_valid', 'integration_activation_boolean', 'integration_credentials', 'integration_location', 'integration_metadata', 'integration_metadata_read', 'interest_summary', 'key_dpapi_transform', 'key_existing', 'key_length', 'key_location_not_redirected', 'key_parent_existing', 'key_policy_boolean', 'key_windows_required', 'management_action_reused', 'management_action_shape', 'management_activation_boolean', 'management_consent', 'management_preference_fields', 'management_revision_conflict', 'management_revision_required', 'management_store_available', 'management_template_token', 'notification_page_https', 'processing_activation_boolean', 'processing_intent_scope', 'processing_profile_match', 'processor_arguments', 'processor_confirmation_scope', 'processor_recipient_scope', 'processor_scope_complete', 'processor_single_purpose', 'production_deferred', 'production_processing_deferred', 'production_secret_provider', 'provider_acceptance_status', 'provider_close', 'provider_connect', 'provider_http_rejection', 'provider_rate_limit', 'provider_response_contract', 'provider_response_encoding', 'provider_response_status', 'provider_response_unacknowledged', 'provider_tls_override', 'provider_transport_exception', 'provider_transport_result', 'public_file_present', 'recipient_testing_only', 'recovery_fields', 'release_template_platform', 'release_template_url', 'request_csrf', 'request_fetch_site', 'request_json_decode', 'request_json_media_type', 'request_origin', 'request_origin_missing', 'request_origin_or_csrf', 'request_referer', 'request_size', 'request_state', 'schedule_overlap', 'service_backend_only', 'service_bearer', 'service_json_decode', 'service_method', 'service_no_encoding', 'service_no_query', 'service_rate_limit', 'service_route', 'service_signup_fields', 'service_signup_validation', 'service_state_fields', 'service_summary_no_body', 'service_summary_request', 'service_transport', 'service_visitor_token', 'signup_consent', 'signup_fields', 'signup_input', 'signup_persistence', 'signup_preference_types', 'signup_receipt', 'signup_selection', 'signup_state', 'smtp_config_fields', 'smtp_config_valid', 'state_persistence', 'state_totals_query', 'tls_certificate_key_valid', 'tls_files_distinct_existing', 'tls_password_interaction_prohibited', 'unsubscribe_capability', 'unsubscribe_persistence', 'webhook_management_required', 'withdrawal_template_token', 'workspace_required'])
FAILURE_PREDICATES = FAILURE_PREDICATES | PRECISE_PREDICATES
FAILURE_OPERATIONS = FAILURE_OPERATIONS | frozenset(['__post_init__', '_read_settings', '_save', '_secure_page', '_validate_environment', '_windows_password', 'action_payload', 'application_startup', 'browser_session', 'confirm', 'confirmation_authority', 'confirmation_persistence', 'confirmation_reservation', 'contact_not_submitted', 'contact_submission_unknown', 'database_checkout', 'development_app', 'error', 'http_request', 'integration_request', 'interest_summary', 'load_contact_config', 'load_database_config', 'load_development_integration_config', 'main', 'management_footer', 'management_message', 'normalize_email', 'payload', 'preference_values', 'process_confirmations', 'recognition_secret', 'recover_link', 'release_message', 'request_confirmation', 'save_session', 'server_bind', 'server_execution', 'signup_persistence', 'state_persistence', 'state_totals_query', 'submit', 'submit_contact', 'subscribe', 'testing_app', 'testing_https_app', 'tls_context', 'too_large', 'totals', 'unsubscribe', 'validate_contact', 'validate_subscription', 'validate_testing_https', 'verification_message', 'verify_connection_identity', 'verify_runtime'])


PRECISE_PREDICATES |= frozenset({"release_event_available", "confirmation_global_budget", "confirmation_mailbox_budget",
    "confirmation_active_subscriber", "recovery_global_budget", "recovery_mailbox_budget", "recovery_active_subscriber",
    "recovery_not_suppressed", "smtp_rejected", "smtp_unacknowledged", "smtp_connection_or_authentication", "smtp_close"})
FAILURE_PREDICATES |= PRECISE_PREDICATES
FAILURE_OPERATIONS |= frozenset({"smtp_connect", "smtp_authenticate", "smtp_submit"})

PRECISE_PREDICATES |= frozenset(['configuration_credential_service', 'configuration_database', 'configuration_host', 'configuration_port', 'configuration_username', 'database_authenticated_identity', 'database_server_address', 'database_server_port', 'database_server_version', 'guard_authorization_spacing', 'guard_bearer_format', 'guard_body_limit', 'guard_complete_read', 'guard_content_length', 'guard_header_limit', 'guard_header_syntax', 'guard_header_unique', 'guard_host', 'guard_media_type', 'guard_method', 'guard_no_encoding', 'guard_path', 'guard_request_framing', 'guard_request_line', 'guard_startup_runtime', 'guard_upstream_no_body', 'guard_upstream_no_surplus', 'guard_upstream_retry_header', 'guard_upstream_status_line', 'guard_upstream_unknown', 'management_prior_audit_present', 'management_session_revision', 'management_withdrawn_selection', 'provider_credential_metadata', 'provider_key_format', 'webhook_credential_metadata', 'webhook_credential_read', 'webhook_environment_match', 'webhook_token_format', 'withdrawal_committed_audit', 'withdrawal_no_preferences', 'withdrawal_receipt_binding', 'withdrawal_receipt_format', 'withdrawal_receipt_signature', 'withdrawal_revision'])
FAILURE_PREDICATES |= PRECISE_PREDICATES
FAILURE_OPERATIONS |= frozenset(['webhook_guard'])

PRECISE_PREDICATES |= frozenset({"schedule_arguments", "schedule_option_once", "schedule_configuration", "schedule_credential_metadata"})
FAILURE_PREDICATES |= PRECISE_PREDICATES

PRECISE_PREDICATES |= frozenset({"integration_config_fields", "integration_credentials_distinct", "integration_environment_match", "integration_key_separation", "key_read_or_decrypt"})
FAILURE_PREDICATES |= PRECISE_PREDICATES

PRECISE_PREDICATES |= frozenset({"development_arguments", "guard_arguments"})
FAILURE_PREDICATES |= PRECISE_PREDICATES

PRECISE_PREDICATES |= frozenset({"release_enabled", "release_payload", "release_event_conflict", "release_acceptance"})
FAILURE_PREDICATES |= PRECISE_PREDICATES

# The existing webhook predicates name the actual rejected condition.
PRECISE_PREDICATES |= frozenset(p for p in FAILURE_PREDICATES if p.startswith("webhook_"))

# Extends the existing bounded notification record; no alternate logging framework.
FAILURE_STAGES = frozenset({"processor", "outbox", "schedule", "notifications", "startup", "request", "provider"})
EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "instance/failures.jsonl"
_EVIDENCE_LOCK = RLock()


def _not_run(stage, side_effects, provider_outcome, operation=None, context=None):
    if provider_outcome == "submission_unknown" or side_effects == "submission_possible":
        return ["automatic_retry"]
    if stage == "startup":
        return ["application_initialization", "database_mutation", "provider_submission"]
    if side_effects in {"database_commit_uncertain", "database_rollback_uncertain"}:
        return ["automatic_retry"]
    if stage == "notifications" and operation == "brevo_unsubscribe":
        if context in {"webhook_configuration", "webhook_authentication", "webhook_media_type",
                       "webhook_json", "webhook_event"}:
            return ["event_correlation", "database_transaction", "database_mutation", "provider_submission"]
        if context == "webhook_correlation":
            return ["database_mutation", "provider_submission"]
    if (stage in {"processor", "outbox"} and context != "outcome" and operation in {
            "configuration", "provider_configuration", "database_configuration", "protected_key", "engine",
            "selection_recovery", "claim", "preparation", "database_begin", "advisory_lock", "database_clock"}):
        return ["provider_submission"]
    if stage == "request" and side_effects == "none":
        return ["database_mutation", "provider_submission"]
    return []


def _request_record(failure, *, emitted=False):
    # Lazy Flask access keeps configuration failures independent of application setup.
    if "flask" not in sys.modules:
        return
    from flask import g, has_request_context
    if has_request_context():
        if not hasattr(g, "oaf_first_failure"):
            g.oaf_first_failure = failure
        if emitted:
            g.oaf_failure_emitted = True


def _append_failure(detail):
    # Same private instance directory and append/flush/fsync convention as the scheduler.
    # Never follow redirected evidence files or directories. No configuration values.
    import stat
    with _EVIDENCE_LOCK:
        for path in (EVIDENCE_PATH.parent.parent, EVIDENCE_PATH.parent, EVIDENCE_PATH):
            if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0)
                                     & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise OSError("Diagnostic location unavailable.")
        EVIDENCE_PATH.parent.mkdir(exist_ok=True)
        with EVIDENCE_PATH.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(detail, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def _emit(detail, logger=None, *, message="Notification operation failed"):
    # Secondary failures never replace first_failure or escape into public handlers.
    if logger is not None:
        try:
            logger.warning(message + ": %s", json.dumps(detail, sort_keys=True))
        except Exception as exc:
            detail["logging_failure"] = safe_failure("processor", "terminal_publication", exc)
    try:
        _append_failure(detail)
    except Exception as exc:
        detail["evidence_failure"] = safe_failure("processor", "terminal_publication", exc)
    if logger is None or "logging_failure" in detail or "evidence_failure" in detail:
        try:
            sys.stderr.write(message + ": " + json.dumps(detail, sort_keys=True) + "\n")
            sys.stderr.flush()
        except Exception:
            pass  # Both sinks unavailable: cannot safely recurse or change operation certainty.


def diagnostic_error(exc, operation, predicate, *, stage="request", side_effects="none"):
    """Attach the predicate before an outer sanitized exception can discard it."""
    if isinstance(exc, type) and issubclass(exc, BaseException):
        exc = exc()
    if stage == "startup" and "flask" in sys.modules:
        from flask import has_request_context
        if has_request_context():
            stage = "request"
    if getattr(exc, "notification_failure", None) is None:
        exc.notification_failure = safe_failure(stage, operation, exc, predicate=predicate, side_effects=side_effects)
    _request_record(exc.notification_failure)
    if stage == "startup":
        _emit(dict(operation=operation, first_failure=exc.notification_failure))
    return exc


def retain_failure(operation, predicate, exc=None, *, stage="request", side_effects="none", http_status=None):
    failure = safe_failure(stage, operation, exc, predicate=predicate, side_effects=side_effects)
    _request_record(failure)
    return failure


def report_failure(operation, exc=None, *, stage="startup", predicate="operation_failed", side_effects="none", first_failure=None):
    failure = safe_failure(stage, operation, exc, predicate=predicate, side_effects=side_effects)
    detail = dict(operation=operation, first_failure=first_failure or failure)
    if first_failure is not None:
        detail["cleanup_failure"] = failure
    _emit(detail)
    return first_failure or failure


def request_transaction_outcome(side_effects):
    if "flask" in sys.modules:
        from flask import g, has_request_context
        if has_request_context() and hasattr(g, "oaf_first_failure"):
            g.oaf_first_failure["side_effects"] = side_effects
            g.oaf_first_failure["dependent_not_run"] = ["provider_submission"]


def report_request_failure(response, logger):
    from flask import g
    if (response.status_code >= 400 or hasattr(g, "oaf_first_failure")) and not getattr(g, "oaf_failure_emitted", False):
        failure = getattr(g, "oaf_first_failure", None) or safe_failure(
            "request", "http_request", predicate="http_rejection")
        _emit(dict(operation=failure["operation"], first_failure=validate_failure(failure),
                   http_status=response.status_code), logger)
    return response


def _safe_field_name(name):
    # Conservative lower_snake_case only. Redact addresses, bearer strings,
    # punctuation, controls, Unicode, numeric identifiers and opaque names.
    # Webhook bearers are at least 32 characters, including underscore forms.
    return (type(name) is str and len(name) <= 31
            and re.fullmatch(r"[a-z]{1,24}(?:_[a-z]{1,24})*", name, re.ASCII) is not None)


def safe_failure(stage, operation, exc=None, *, side_effects="none", predicate="operation_failed", context=None, provider_outcome=None, preserve=True, field_names=None):
    """Bounded originating-boundary evidence. Never inspect exception text/args."""
    if stage not in FAILURE_STAGES or operation not in FAILURE_OPERATIONS:
        raise ValueError("Invalid diagnostic operation.")
    if side_effects not in SIDE_EFFECTS or predicate not in FAILURE_PREDICATES:
        raise ValueError("Invalid diagnostic condition.")
    if context is not None and context not in FAILURE_OPERATIONS:
        raise ValueError("Invalid diagnostic context.")
    if provider_outcome not in {None, "provider_accepted", "provider_rejected", "not_submitted", "retryable_rejection", "submission_unknown"}:
        raise ValueError("Invalid provider evidence.")
    retained = getattr(exc, "notification_failure", None)
    if preserve and retained is not None:
        return validate_failure(retained)
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(exc, "sqlstate", None)
    sqlstate = sqlstate if type(sqlstate) is str and re.fullmatch(r"[A-Z0-9]{5}", sqlstate) else None
    name = type(exc).__name__ if exc is not None else None
    hresult = getattr(exc, "hresult", None)
    exit_code = getattr(exc, "returncode", None)
    failure = dict(stage=stage, operation=operation, predicate=predicate,
        expected=(predicate + "_satisfied") if predicate in PRECISE_PREDICATES else "authorized_operation_acknowledged",
        observed=(predicate + "_failed") if predicate in PRECISE_PREDICATES else "unavailable_or_rejected",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        exception_class=name if name in FAILURE_CLASSES else "OtherError" if name else None,
        sqlstate=sqlstate, hresult=("0x%08X" % (hresult & 0xffffffff)) if type(hresult) is int else None,
        exit_code=exit_code if type(exit_code) is int and -2147483648 <= exit_code <= 2147483647 else None,
        side_effects=side_effects, context=context, provider_outcome=provider_outcome,
        evidence_ref=uuid4().hex, dependent_not_run=_not_run(stage, side_effects, provider_outcome, operation, context))
    if field_names is not None:
        if (stage, operation, context, predicate, side_effects) != (
                "notifications", "brevo_unsubscribe", "webhook_event", "webhook_allowed_fields", "none"):
            raise ValueError("Invalid field diagnostic context.")
        if type(field_names) is not set or not field_names:
            raise ValueError("Invalid field diagnostic names.")
        names = sorted(name for name in field_names if _safe_field_name(name))
        failure.update(expected="set(data) <= ALLOWED_FIELDS",
            observed="set(data) - ALLOWED_FIELDS is nonempty",
            field_validation=dict(offending_field_names=names[:32],
                offending_field_count=len(field_names), redacted_name_count=len(field_names) - len(names),
                omitted_name_count=max(0, len(names) - 32)),
            dependent_not_run=["event_correlation", "database_transaction", "database_mutation", "provider_submission"])
    return failure


def validate_failure(value):
    """Validate child evidence before a parent publishes it."""
    if type(value) is not dict or set(value) - {"field_validation"} != set(safe_failure("processor", "arguments")):
        raise ValueError("Invalid diagnostic fields.")
    fields = value.get("field_validation")
    if "field_validation" in value:
        if ((value["stage"], value["operation"], value["context"], value["predicate"], value["side_effects"]) != (
                "notifications", "brevo_unsubscribe", "webhook_event", "webhook_allowed_fields", "none")
                or type(fields) is not dict or set(fields) != {
                    "offending_field_names", "offending_field_count", "redacted_name_count", "omitted_name_count"}):
            raise ValueError("Invalid field diagnostic context.")
        names = fields["offending_field_names"]
        counts = [fields[key] for key in ("offending_field_count", "redacted_name_count", "omitted_name_count")]
        if (type(names) is not list or len(names) > 32 or any(not _safe_field_name(name) for name in names)
                or names != sorted(set(names)) or any(type(count) is not int or count < 0 for count in counts)
                or counts[0] == 0 or counts[0] != len(names) + counts[1] + counts[2]
                or (counts[2] and len(names) != 32)
                or value["dependent_not_run"] != [
                    "event_correlation", "database_transaction", "database_mutation", "provider_submission"]):
            raise ValueError("Invalid field diagnostic names.")
    expected = "set(data) <= ALLOWED_FIELDS" if fields is not None else (
        (value["predicate"] + "_satisfied") if value["predicate"] in PRECISE_PREDICATES else "authorized_operation_acknowledged")
    observed = "set(data) - ALLOWED_FIELDS is nonempty" if fields is not None else (
        (value["predicate"] + "_failed") if value["predicate"] in PRECISE_PREDICATES else "unavailable_or_rejected")
    if (value["stage"] not in FAILURE_STAGES
            or value["operation"] not in FAILURE_OPERATIONS
            or value["predicate"] not in FAILURE_PREDICATES
            or value["expected"] != expected
            or value["observed"] != observed
            or value["side_effects"] not in SIDE_EFFECTS
            or value["context"] not in FAILURE_OPERATIONS | {None}
            or value["provider_outcome"] not in {None, "provider_accepted", "provider_rejected", "not_submitted", "retryable_rejection", "submission_unknown"}
            or value["exception_class"] not in FAILURE_CLASSES | {"OtherError", None}):
        raise ValueError("Invalid diagnostic values.")
    timestamp = value["timestamp_utc"]
    if type(timestamp) is not str or len(timestamp) > 40 or datetime.fromisoformat(timestamp).utcoffset().total_seconds() != 0:
        raise ValueError("Invalid diagnostic timestamp.")
    for key, pattern in (("sqlstate", r"[A-Z0-9]{5}"), ("hresult", r"0x[A-F0-9]{8}")):
        if value[key] is not None and (type(value[key]) is not str or re.fullmatch(pattern, value[key]) is None):
            raise ValueError("Invalid diagnostic code.")
    if value["exit_code"] is not None and (type(value["exit_code"]) is not int or not -2147483648 <= value["exit_code"] <= 2147483647):
        raise ValueError("Invalid native exit code.")
    if type(value["evidence_ref"]) is not str or re.fullmatch(r"[0-9a-f]{32}", value["evidence_ref"]) is None:
        raise ValueError("Invalid evidence reference.")
    if (type(value["dependent_not_run"]) is not list or any(item not in {
            "application_initialization", "database_mutation", "provider_submission", "automatic_retry",
            "event_correlation", "database_transaction"
        } for item in value["dependent_not_run"])):
        raise ValueError("Invalid dependent operations.")
    return value


def _webhook_receipt(value):
    # This keyed audit identity is neither a mailbox digest nor a capability.
    if (type(value) is not dict or set(value) != {"environment", "receipt_digest"}
            or value["environment"] not in {"testing", "development"}
            or type(value["receipt_digest"]) is not str
            or re.fullmatch(r"[0-9a-f]{64}", value["receipt_digest"]) is None):
        raise ValueError("Invalid webhook receipt diagnostic.")
    return dict(value)


def log_webhook_processed(logger, receipt, *, acknowledgement):
    """Only called after the existing transaction context acknowledges commit."""
    detail = dict(operation="brevo_unsubscribe", stage="notifications", http_status=200,
        timestamp_utc=datetime.now(timezone.utc).isoformat(), evidence_ref=uuid4().hex,
        webhook_receipt=_webhook_receipt(receipt), side_effects="database_committed",
        event_outcome="idempotent_acknowledgement" if acknowledgement else "processed_withdrawal")
    _emit(detail, logger, message="Notification operation completed")


def log_notification_failure(logger, operation, exc, *, http_status=None, webhook_receipt=None):
    """Request-local evidence; never log exception text, SQL, or capabilities."""
    failure = getattr(exc, "notification_failure", None)
    failure = validate_failure(failure) if failure is not None else safe_failure(
        "notifications", operation, exc, side_effects="database_transaction_unacknowledged")
    detail = dict(operation=operation, first_failure=failure)
    if operation == "brevo_unsubscribe":
        if failure["side_effects"] in {"database_commit_uncertain", "database_rollback_uncertain"}:
            failure["dependent_not_run"] = ["automatic_retry"]
        elif failure["operation"] in {"database_begin", "advisory_lock", "database_clock"}:
            failure["dependent_not_run"] = ["event_correlation", "database_mutation", "provider_submission"]
            if failure["operation"] == "database_begin":
                failure["dependent_not_run"].insert(1, "database_transaction")
        detail["event_outcome"] = "rejected" if failure["context"] in {
            "webhook_configuration", "webhook_authentication", "webhook_media_type",
            "webhook_json", "webhook_event", "webhook_correlation"} else "unavailable"
        if webhook_receipt:
            detail["webhook_receipt"] = _webhook_receipt(webhook_receipt)
            detail["event_outcome"] = "accepted"
    if "flask" in sys.modules:
        from flask import g, has_request_context
        if has_request_context():
            if getattr(g, "oaf_failure_emitted", False):
                detail["secondary_failure"] = failure
                detail["first_failure"] = g.oaf_first_failure
            else:
                g.oaf_first_failure = failure
    if http_status is not None:
        if type(http_status) is not int or not 100 <= http_status <= 599:
            raise ValueError("Invalid diagnostic HTTP status.")
        detail["http_status"] = http_status
    rollback = getattr(exc, "notification_rollback_failure", None)
    if rollback is not None:
        detail["rollback_failure"] = validate_failure(rollback)
    transaction = getattr(exc, "notification_transaction_failure", None)
    if transaction is not None:
        detail["transaction_failure"] = validate_failure(transaction)
    _emit(detail, logger)
    _request_record(failure, emitted=True)


class ReleaseDispatcher:
    def __init__(self, store, config, notification_page, *, transport=None):
        from .brevo import BrevoAdapter, BrevoConfig, BrevoConfigurationError
        from .notification_messages import secure_page
        from .notifications import UnsubscribeCapabilities
        if type(config) is not BrevoConfig or config.environment != store.environment:
            raise BrevoConfigurationError("Brevo configuration must match the delivery environment.")
        self.store = store
        self.page = secure_page(notification_page)
        self.capabilities = UnsubscribeCapabilities(store.secret)
        self.adapter = BrevoAdapter(config, transport=transport, recipient_scope=store.recipient_scope)

    def process(self, event_id, *, limit=20):
        from .brevo import ProviderOutcome
        from .notification_messages import release_message
        # Validate before persistence or provider access. No recipient input is accepted.
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Release batches require 1 to 20 recipients.")
        processed = 0
        failure = None
        operation = "selection_recovery"
        try:
            self.store.recover_event(event_id)
            self.store.prepare_event(event_id)
            event, subscriptions = self.store.dispatch_batch(event_id, limit)
            if event is None:
                failure = report_failure("dispatcher", stage="processor", predicate="release_event_available")
                return BatchResult("unavailable", first_failure=failure)
            for subscription in subscriptions:
                operation = "claim"
                claim = self.store.claim(event_id, subscription)
                if claim is None:
                    continue
                # Commit and recheck immediately before the only possible HTTP call.
                def render(subscriber, now, current_event):
                    token = None
                    if self.store.management_enabled:
                        from .notification_management import ManagementCapabilities
                        token = ManagementCapabilities(self.store.secret, self.store.environment).issue(
                            subscription, subscriber["preferences_revision"], now)
                    return release_message(current_event, subscription, self.capabilities, self.page, management_token=token)
                operation = "preparation"
                prepared = self.store.begin_submission(event_id, subscription, claim, prepare=render)
                if prepared is None:
                    continue
                try:
                    operation = "provider_submit"
                    outcome = self.adapter.submit(*prepared)
                except Exception as exc:
                    failure = failure or report_failure("provider_submit", exc, stage="processor", side_effects="submission_possible")
                    # An injected adapter may already have posted; hold rather than repeat.
                    outcome = ProviderOutcome("submission_unknown")
                failure = failure or getattr(outcome, "first_failure", None)
                operation = "outcome"
                if not self.store.record_outcome(event_id, subscription, claim,
                                                outcome.outcome, outcome.message_id):
                    failure = failure or report_failure("outcome", stage="processor", predicate="outcome_not_acknowledged", side_effects="database_commit_uncertain")
                    return BatchResult("unavailable", processed, failure)
                processed += 1
            return BatchResult("processed", processed, failure)
        except Exception as exc:
            # Includes uncertain commits. Never post after a failed dispatch commit,
            # retry a POST here, or disclose email/token/SQL/credential/provider errors.
            failure = failure or report_failure(operation, exc, stage="processor", side_effects="database_transaction_unacknowledged")
            return BatchResult("unavailable", processed, failure)


from contextlib import contextmanager


@contextmanager
def diagnostic_transaction(engine):
    boundary, origin, failure = "database_begin", None, None
    try:
        with engine.begin() as connection:
            boundary = "transaction_body"
            try:
                yield connection
            except Exception as exc:
                origin = exc
                failure = safe_failure("notifications", boundary, exc)
                raise
            boundary = "transaction_commit"
    except Exception as exc:
        if failure is not None:
            failure["side_effects"] = "database_rolled_back" if exc is origin else "database_rollback_uncertain"
            if exc is not origin:
                exc.notification_rollback_failure = safe_failure("notifications", "transaction_rollback", exc,
                    side_effects="database_rollback_uncertain", preserve=False)
        else:
            failure = safe_failure("notifications", boundary, exc,
                side_effects="database_commit_uncertain" if boundary == "transaction_commit" else "none")
        exc.notification_failure = failure
        raise
