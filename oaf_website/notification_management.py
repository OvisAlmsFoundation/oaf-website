"""Lifecycle-bound email capabilities and audited preference transitions."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets

from flask import jsonify, request
from itsdangerous import BadData, URLSafeSerializer
from sqlalchemy import insert

from .notification_delivery import NotificationDeliveryStore
from .notification_dispatch import safe_failure, log_notification_failure
from .notification_delivery_schema import verification, suppressions
from .notification_management_schema import notifications, intents, changes, PREFERENCE_COLUMNS, CONSENT_VERSION
from .notifications import normalize_email
from .state_request_schema import STATE_CODES

UNAVAILABLE = "This link is unavailable. Use your latest email or request a new link."
RECOVERY_RECEIVED = "If a link is needed and permitted, we'll email it. Check your inbox."
MANAGEMENT_SESSION_AGE = 30 * 60
WITHDRAWAL_RECEIPT_AGE = 10 * 60
TOKEN = re.compile(r"m2\.(testing|development)\.([0-9a-f]{64})\.([0-9]{1,10})\.([0-9]{1,12})\.([0-9]{1,12})\.([0-9a-f]{64})\.([0-9a-f]{64})", re.ASCII)


class ManagementUnavailable(ValueError):
    def __init__(self, message=UNAVAILABLE, *, predicate="management_unavailable"):
        super().__init__(message)
        # Fixed diagnostic codes only; the existing transaction boundary adds
        # rollback certainty and the handler keeps the public response generic.
        self.notification_failure = safe_failure(
            "notifications", "management_authority", self, predicate=predicate)


class ManagementConflict(ValueError):
    pass


class ManagementInputError(ValueError):
    pass


class ManagementCapabilities:
    """Separate purpose/environment/revision/expiry; V1 cannot be promoted."""
    def __init__(self, secret, environment):
        from .notifications import UnsubscribeCapabilities
        UnsubscribeCapabilities(secret)
        if environment not in {"testing", "development"}:
            raise ValueError("An explicit management environment is required.")
        self.secret, self.environment = secret, environment

    def _sign(self, body):
        return hmac.new(self.secret, b"oaf-notification-management-v2:" + body.encode("ascii"), hashlib.sha256).hexdigest()

    def issue(self, subscription, revision, now, *, lifetime=timedelta(days=30), context=None):
        if (type(subscription) is not str or re.fullmatch(r"[0-9a-f]{64}", subscription) is None
                or type(revision) is not int or not 0 <= revision < 2147483647
                or now.tzinfo is None or not timedelta(0) < lifetime <= timedelta(days=30)):
            raise ValueError("Invalid management authority.")
        # Lifetimes are elapsed seconds; local calendar arithmetic can cross DST.
        now = now.astimezone(timezone.utc)
        issued, expires = int(now.timestamp()), int((now + lifetime).timestamp())
        context = secrets.token_hex(32) if context is None else context
        if type(context) is not str or re.fullmatch(r"[0-9a-f]{64}", context) is None:
            raise ValueError("Invalid management authority.")
        body = f"m2.{self.environment}.{subscription}.{revision}.{issued}.{expires}.{context}"
        return body + "." + self._sign(body)

    def read(self, token, now):
        match = TOKEN.fullmatch(token) if type(token) is str else None
        if match is None:
            raise ManagementUnavailable(predicate="capability_format")
        if match[1] != self.environment:
            raise ManagementUnavailable(predicate="capability_environment")
        body, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(self._sign(body), signature):
            raise ManagementUnavailable(predicate="capability_signature")
        revision, issued, expires = map(int, match.group(3, 4, 5))
        if revision >= 2147483647:
            raise ManagementUnavailable(predicate="capability_revision_range")
        if now.timestamp() < issued:
            raise ManagementUnavailable(predicate="capability_not_yet_valid")
        if now.timestamp() >= expires:
            raise ManagementUnavailable(predicate="capability_expired")
        if not 0 < expires - issued <= 30 * 86400:
            raise ManagementUnavailable(predicate="capability_lifetime")
        return dict(subscription=match[2], revision=revision, issued=issued, expires=expires, context=match[6])

    def continuation(self, token, revision):
        parts = token.split(".")
        parts[3] = str(revision)
        body = ".".join(parts[:-1])
        return body + "." + self._sign(body)


class ManagementSessions:
    """Management-only signed HttpOnly transport; no sliding expiry or new key."""
    def __init__(self, capabilities):
        self.capabilities = capabilities
        self.serializer = URLSafeSerializer(
            capabilities.secret, salt="oaf-notification-management-session-v1:" + capabilities.environment,
            signer_kwargs={"digest_method": hashlib.sha256},
        )

    def _browser(self, token):
        if type(token) is not str or re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise ManagementUnavailable(predicate="browser_format")
        return hmac.new(self.capabilities.secret, b"oaf-notification-management-session-browser-v1:"
                        + token.encode("ascii"), hashlib.sha256).hexdigest()

    def issue(self, token, browser, now):
        authority = self.capabilities.read(token, now)
        started = int(now.timestamp())
        return dict(token=token, browser=self._browser(browser), started=started,
                    expires=min(started + MANAGEMENT_SESSION_AGE, authority["expires"]))

    def read(self, cookie, browser, now):
        if type(cookie) is not str or not cookie or len(cookie) > 2048:
            raise ManagementUnavailable(predicate="session_cookie_format")
        try:
            state = self.serializer.loads(cookie)
        except BadData:
            raise ManagementUnavailable(predicate="session_cookie_signature") from None
        if (type(state) is not dict or set(state) != {"token", "browser", "started", "expires"}
                or type(state["started"]) is not int or type(state["expires"]) is not int
                or type(state["browser"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", state["browser"]) is None):
            raise ManagementUnavailable(predicate="session_shape")
        if not hmac.compare_digest(state["browser"], self._browser(browser)):
            raise ManagementUnavailable(predicate="session_browser")
        if now.timestamp() < state["started"]:
            raise ManagementUnavailable(predicate="session_not_yet_valid")
        if now.timestamp() >= state["expires"]:
            raise ManagementUnavailable(predicate="session_expired")
        if not 0 < state["expires"] - state["started"] <= MANAGEMENT_SESSION_AGE:
            raise ManagementUnavailable(predicate="session_lifetime")
        authority = self.capabilities.read(state["token"], now)
        if state["expires"] > authority["expires"]:
            raise ManagementUnavailable(predicate="session_capability_expiry")
        if state["started"] < authority["issued"]:
            raise ManagementUnavailable(predicate="session_capability_issue")
        return state

    def cookie(self, state, now):
        return dict(value=self.serializer.dumps(state),
                    max_age=max(0, int(state["expires"] - now.timestamp())),
                    expires=datetime.fromtimestamp(state["expires"], timezone.utc))


def preference_values(data):
    if (type(data) is not dict or set(data) != {*PREFERENCE_COLUMNS, "consent"}
            or any(type(data[n]) is not bool for n in PREFERENCE_COLUMNS[:3])
            or data["state"] is not None and (type(data["state"]) is not str or data["state"] not in STATE_CODES)
            or type(data["consent"]) is not bool):
        raise diagnostic_error(ManagementInputError("Choose valid notification preferences."), "preference_values", "management_preference_fields", stage="request")
    selected = any(data[n] for n in PREFERENCE_COLUMNS)
    if selected and not data["consent"]:
        raise diagnostic_error(ManagementInputError("Consent is required to save the selected announcements."), "preference_values", "management_consent", stage="request")
    return {n: data[n] for n in PREFERENCE_COLUMNS}, selected


def grant_times(subscriber, previous):
    return {n + "_granted_at": (previous[n + "_granted_at"] if previous else subscriber["created_at"])
            if subscriber[n] else None for n in PREFERENCE_COLUMNS}


def action_payload(action_id, revision, preferences):
    if (type(action_id) is not str or re.fullmatch(r"[0-9a-f]{64}", action_id) is None
            or type(revision) is not int or not 0 <= revision < 2147483647):
        raise diagnostic_error(ManagementInputError("Reload your private link and try again."), "action_payload", "management_action_shape", stage="request")
    values, selected = preference_values(preferences) if preferences is not None else (None, False)
    payload = hashlib.sha256(json.dumps(dict(revision=revision, preferences=preferences),
                                       sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return values, selected, payload


class NotificationManagementStore(NotificationDeliveryStore):
    def __init__(self, engine, secret, environment):
        super().__init__(engine, secret, environment, management_enabled=True)
        self.capabilities = ManagementCapabilities(secret, environment)
        self.sessions = ManagementSessions(self.capabilities)
        self.withdrawal_signer = URLSafeSerializer(
            secret, salt="oaf-notification-withdrawal-ack-v1:" + environment,
            signer_kwargs={"digest_method": hashlib.sha256},
        )

    def _authorized(self, connection, token, now, *, verified=True, current=True):
        authority = self.capabilities.read(token, now)
        subscriber = self._get(connection, notifications, unsubscribe_digest=authority["subscription"])
        if subscriber is None:
            raise ManagementUnavailable(predicate="lifecycle_missing")
        if subscriber["created_at"].timestamp() > authority["issued"] + 1:
            raise ManagementUnavailable(predicate="capability_predates_lifecycle")
        if current and subscriber["unsubscribed_at"] is not None:
            raise ManagementUnavailable(predicate="lifecycle_withdrawn")
        if current and subscriber["preferences_revision"] != authority["revision"]:
            raise ManagementUnavailable(predicate="lifecycle_revision")
        if verified:
            record = self._get(connection, verification, subscription=authority["subscription"])
            if record is None or record["verified_at"] is None:
                raise ManagementUnavailable(predicate="consent_unverified")
        return authority, subscriber

    def preferences(self, token):
        with self._transaction() as (connection, now):
            return self._preferences(connection, token, now)

    def _preferences(self, connection, token, now):
        authority, subscriber = self._authorized(connection, token, now)
        return dict(status="preferences", revision=authority["revision"],
                    preferences={n: subscriber[n] for n in PREFERENCE_COLUMNS})

    def open_session(self, token, browser):
        with self._transaction() as (connection, now):
            authority, _ = self._authorized(connection, token, now, verified=False)
            record = self._get(connection, verification, subscription=authority["subscription"])
            if record is None or record["verified_at"] is None:
                return dict(status="withdrawal_only", revision=authority["revision"],
                    message="You can unsubscribe now. Confirm your email before viewing or changing preferences."), None
            result = self._preferences(connection, token, now)
            return result, self.sessions.cookie(self.sessions.issue(token, browser, now), now)

    def session_preferences(self, cookie, browser):
        with self._transaction() as (connection, now):
            state = self.sessions.read(cookie, browser, now)
            return self._preferences(connection, state["token"], now)

    def save_session(self, cookie, browser, action_id, expected_revision, preferences=None):
        with self._transaction() as (connection, now):
            state = self.sessions.read(cookie, browser, now)
            authority, subscriber = self._authorized(connection, state["token"], now, verified=False, current=False)
            if subscriber["preferences_revision"] not in {authority["revision"], authority["revision"] + 1}:
                raise ManagementUnavailable(UNAVAILABLE, predicate="management_session_revision")
            if (type(expected_revision) is not int
                    or expected_revision not in {authority["revision"], authority["revision"] - 1}):
                raise diagnostic_error(ManagementConflict("Preferences changed. Reopen your latest link or request a new one."), "save_session", "management_revision_conflict", stage="request")
            # A response can install its cookie before its JSON body is lost.
            # Derive only the immediately preceding action authority for retry;
            # _save still requires the exact committed action/payload or current revision.
            token = self.capabilities.continuation(state["token"], expected_revision)
            if subscriber["unsubscribed_at"] is not None:
                _, selected, payload = action_payload(action_id, expected_revision, preferences)
                if selected:
                    raise ManagementUnavailable(UNAVAILABLE, predicate="management_withdrawn_selection")
                return self._withdrawal_ack(connection, authority["subscription"],
                    self._digest("management-action", token + ":" + action_id), payload, expected_revision,
                    max(state["started"], now.timestamp() - WITHDRAWAL_RECEIPT_AGE), now.timestamp()), None
            self._authorized(connection, state["token"], now, current=False)
            result = self._save(connection, now, token, action_id, expected_revision, preferences)
            if result["status"] == "unsubscribed":
                return result, None
            # Never revive a stale receipt after another save/withdrawal/revocation.
            self._authorized(connection, result["token"], now)
            state["token"] = result.pop("token")
            return result, self.sessions.cookie(state, now)

    def prepare_withdrawal(self, cookie, browser, action_id, revision, preferences=None, *, token=None):
        """Pre-mutation acknowledgment authority; never a mutation capability."""
        _, selected, payload = action_payload(action_id, revision, preferences)
        if selected:
            raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_no_preferences")
        with self._transaction() as (connection, now):
            state = self.sessions.read(cookie, browser, now) if token is None else None
            token = state["token"] if state else token
            authority, _ = self._authorized(connection, token, now, verified=False)
            if authority["revision"] != revision:
                raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_revision")
            started = int(now.timestamp())
            expires = min(started + WITHDRAWAL_RECEIPT_AGE, authority["expires"],
                          state["expires"] if state else authority["expires"])
            receipt = dict(environment=self.environment, browser=self.sessions._browser(browser),
                subscription=authority["subscription"], revision=revision,
                action_digest=self._digest("management-action", token + ":" + action_id),
                action_id_digest=self._digest("withdrawal-action-id", action_id), payload_digest=payload,
                started=started, expires=expires)
            return dict(receipt=self.withdrawal_signer.dumps(receipt))

    def _withdrawal_ack(self, connection, subscription, action, payload, revision, since, until):
        audit = self._get(connection, changes, action_digest=action)
        subscriber = self._get(connection, notifications, unsubscribe_digest=subscription)
        if (audit is None or subscriber is None or audit["subscription"] != subscription
                or audit["source"] != "management" or audit["outcome"] != "unsubscribed"
                or audit["payload_digest"] != payload or audit["previous_revision"] != revision
                or audit["revision"] != revision + 1 or subscriber["preferences_revision"] != audit["revision"]
                or subscriber["unsubscribed_at"] != audit["created_at"]
                or not since <= audit["created_at"].timestamp() <= until):
            raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_committed_audit")
        return dict(status="unsubscribed", revision=audit["revision"])

    def acknowledge_withdrawal(self, receipt, browser, action_id, revision, preferences=None):
        """Only read an exact committed audit; no management authority is returned."""
        _, selected, payload = action_payload(action_id, revision, preferences)
        if selected or type(receipt) is not str or not receipt or len(receipt) > 1536:
            raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_receipt_format")
        try:
            state = self.withdrawal_signer.loads(receipt)
        except BadData:
            raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_receipt_signature") from None
        with self._transaction() as (connection, now):
            if (type(state) is not dict or set(state) != {"environment", "browser", "subscription", "revision",
                    "action_digest", "action_id_digest", "payload_digest", "started", "expires"}
                    or state["environment"] != self.environment or type(state["revision"]) is not int
                    or state["revision"] != revision or type(state["started"]) is not int
                    or type(state["expires"]) is not int
                    or not state["started"] <= now.timestamp() < state["expires"]
                    or not 0 < state["expires"] - state["started"] <= WITHDRAWAL_RECEIPT_AGE
                    or any(type(state[n]) is not str or re.fullmatch(r"[0-9a-f]{64}", state[n]) is None
                           for n in ("browser", "subscription", "action_digest", "action_id_digest", "payload_digest"))
                    or not hmac.compare_digest(state["browser"], self.sessions._browser(browser))
                    or not hmac.compare_digest(state["action_id_digest"], self._digest("withdrawal-action-id", action_id))
                    or not hmac.compare_digest(state["payload_digest"], payload)):
                raise ManagementUnavailable(UNAVAILABLE, predicate="withdrawal_receipt_binding")
            return self._withdrawal_ack(connection, state["subscription"], state["action_digest"], payload,
                                        revision, state["started"], min(state["expires"], now.timestamp()))

    def _previous(self, connection, subscriber):
        revision = subscriber["preferences_revision"]
        if revision == 0:
            return None
        previous = self._get(connection, changes, subscription=subscriber["unsubscribe_digest"], revision=revision)
        if previous is None:
            raise ManagementUnavailable(UNAVAILABLE, predicate="management_prior_audit_present")
        return previous

    def _change(self, connection, now, subscriber, action, payload, source, values=None, *,
                message_id=None, event_at=None):
        selected = values is not None and any(values.values())
        previous = self._previous(connection, subscriber)
        times = grant_times(subscriber, previous)
        after = values if selected else {n: subscriber[n] for n in PREFERENCE_COLUMNS}
        for n in PREFERENCE_COLUMNS:
            if after[n] != subscriber[n]:
                times[n + "_granted_at"] = now if after[n] else None
        revision = subscriber["preferences_revision"] + 1
        audit = dict(action_digest=action, subscription=subscriber["unsubscribe_digest"],
                     payload_digest=payload, source=source, previous_revision=subscriber["preferences_revision"],
                     revision=revision, **{"before_" + n: subscriber[n] for n in PREFERENCE_COLUMNS},
                     **{"after_" + n: after[n] for n in PREFERENCE_COLUMNS}, **times,
                     consent_version=CONSENT_VERSION if selected else None,
                     outcome="saved" if selected else "unsubscribed", created_at=now,
                     provider_message_id=message_id, provider_event_at=event_at)
        # INSERT must succeed; uniqueness/transaction failure may never be hidden.
        try:
            connection.execute(insert(changes).values(**audit))
        except Exception as exc:
            exc.notification_failure = safe_failure("notifications", "audit_insert", exc)
            raise
        update = dict(preferences_revision=revision)
        if selected:
            update.update(after)
        elif subscriber["unsubscribed_at"] is None:
            update["unsubscribed_at"] = max(now, subscriber["created_at"])
        try:
            self._update(connection, notifications, dict(unsubscribe_digest=subscriber["unsubscribe_digest"]), **update)
        except Exception as exc:
            exc.notification_failure = safe_failure("notifications", "subscription_update", exc)
            raise
        return audit

    def save(self, token, action_id, expected_revision, preferences=None):
        with self._transaction() as (connection, now):
            return self._save(connection, now, token, action_id, expected_revision, preferences)

    def _save(self, connection, now, token, action_id, expected_revision, preferences):
        values, selected, payload = action_payload(action_id, expected_revision, preferences)
        authority, subscriber = self._authorized(connection, token, now, verified=False, current=False)
        action = self._digest("management-action", token + ":" + action_id)
        if expected_revision != authority["revision"]:
            raise diagnostic_error(ManagementConflict("Reopen your latest link before saving."), "_save", "management_revision_required", stage="request")
        previous_action = self._get(connection, changes, action_digest=action)
        if previous_action is not None:
            if previous_action["payload_digest"] != payload:
                raise diagnostic_error(ManagementConflict("This action has already been used. Reopen your latest link."), "_save", "management_action_reused", stage="request")
            result = previous_action
        else:
            if (subscriber["unsubscribed_at"] is not None or subscriber["preferences_revision"] != expected_revision):
                raise diagnostic_error(ManagementConflict("Preferences changed. Reopen your latest link or request a new one."), "_save", "management_revision_conflict", stage="request")
            if selected:
                self._authorized(connection, token, now)
            result = self._change(connection, now, subscriber, action, payload, "management", values)
        response = dict(status=result["outcome"], revision=result["revision"])
        if result["outcome"] == "saved":
            response["token"] = self.capabilities.continuation(token, result["revision"])
        return response

    def unsubscribe_legacy(self, digest):
        with self._transaction() as (connection, now):
            subscriber = self._get(connection, notifications, unsubscribe_digest=digest)
            if subscriber is None or subscriber["unsubscribed_at"] is not None:
                return
            action = self._digest("legacy-withdrawal", digest)
            self._change(connection, now, subscriber, action, action, "legacy")

    def request_recovery(self, email):
        email = normalize_email(email)
        with self._transaction() as (connection, now):
            if not self._budget(connection, self._digest("budget", "global"), now, 1000, 0):
                retain_failure("management_recovery", "recovery_global_budget")
                return
            mailbox = self._digest("mailbox", email)
            if not self._budget(connection, mailbox, now, 5, 60):
                retain_failure("management_recovery", "recovery_mailbox_budget")
                return
            subscriber = self._get(connection, notifications, email=email, unsubscribed_at=None)
            if subscriber is None:
                retain_failure("management_recovery", "recovery_active_subscriber")
                return
            if self._get(connection, suppressions, mailbox_digest=mailbox):
                retain_failure("management_recovery", "recovery_not_suppressed")
                return
            record = self._get(connection, verification, subscription=subscriber["unsubscribe_digest"])
            if record is None or record["verified_at"] is None:
                from .confirmation_outbox import reserve_confirmation
                reserve_confirmation(self, connection, now, subscriber, record)
                return
            from .confirmation_outbox import pending_recovery
            if pending_recovery(self, connection, now, subscriber["unsubscribe_digest"],
                    purpose="management", revision=subscriber["preferences_revision"]):
                return
            context = secrets.token_hex(32)
            token = self.capabilities.issue(subscriber["unsubscribe_digest"], subscriber["preferences_revision"], now,
                                            lifetime=timedelta(hours=24), context=context)
            connection.execute(insert(intents).values(intent=context, subscription=subscriber["unsubscribe_digest"],
                token_digest=self._digest("management-recovery", token), purpose="management",
                management_revision=subscriber["preferences_revision"], status="pending", attempts=0,
                claim_digest=None, lease_until=None, next_attempt_at=now, outcome=None, provider_message_id=None,
                created_at=now, updated_at=now, accepted_at=None))


def register_management(app, store, payload, error, *, recognition, browser_cookie_name, secure):
    cookie_name = "__Host-oaf-notification-management" if secure else "oaf-notification-management"

    def browser():
        return recognition.read(request.cookies.get(browser_cookie_name))

    def clear_session(response):
        response.delete_cookie(cookie_name, secure=secure, httponly=True, samesite="Lax", path="/")
        return response

    def session_response(result, cookie):
        response = jsonify(result)
        if cookie is None:
            return clear_session(response)
        response.set_cookie(cookie_name, **cookie, secure=secure, httponly=True, samesite="Lax", path="/")
        return response

    def denied():
        response, status = error(UNAVAILABLE, 400)
        return clear_session(response), status

    def unavailable():
        retain_failure("management_view", "management_store_available")
        return error("Notification management is currently unavailable.", 503)

    @app.post("/api/notifications/manage")
    def view_preferences():
        data, failure = payload()
        if failure is not None:
            return failure
        if store is None:
            return unavailable()
        if type(data) is not dict or set(data) not in ({"token"}, set()):
            log_notification_failure(app.logger, "management_view",
                ManagementUnavailable(predicate="management_request_shape"), http_status=400)
            return error(UNAVAILABLE, 400)
        try:
            if "token" in data:
                return session_response(*store.open_session(data["token"], browser()))
            if not request.cookies.get(cookie_name):
                raise ManagementUnavailable(predicate="management_cookie_missing")
            return jsonify(store.session_preferences(request.cookies.get(cookie_name), browser()))
        except ManagementUnavailable as exc:
            log_notification_failure(app.logger, "management_view", exc, http_status=400)
            return denied()
        except Exception as exc:
            log_notification_failure(app.logger, "management_view", exc, http_status=503)
            return unavailable()

    @app.post("/api/notifications/manage/save")
    def save_preferences():
        data, failure = payload()
        if failure is not None:
            return failure
        if store is None:
            return unavailable()
        if type(data) is not dict or set(data) not in ({"token", "action", "revision", "preferences"},
                {"token", "action", "revision"}, {"action", "revision", "preferences"}, {"action", "revision"}):
            return error("Submit your preferences using this page.", 400)
        if "preferences" in data and type(data["preferences"]) is not dict:
            return error("Choose valid notification preferences.", 400)
        try:
            if "token" not in data:
                if not request.cookies.get(cookie_name):
                    return denied()
                return session_response(*store.save_session(request.cookies.get(cookie_name), browser(),
                    data["action"], data["revision"], data.get("preferences")))
            result = store.save(data["token"], data["action"], data["revision"], data.get("preferences"))
            response = jsonify(result)
            return clear_session(response) if result["status"] == "unsubscribed" else response
        except ManagementUnavailable as exc:
            log_notification_failure(app.logger, "management_save", exc, http_status=400)
            return denied()
        except ManagementConflict as conflict:
            log_notification_failure(app.logger, "management_save", conflict, http_status=409)
            return error(str(conflict), 409)
        except ManagementInputError as invalid:
            log_notification_failure(app.logger, "management_save", invalid, http_status=400)
            return error(str(invalid), 400)
        except Exception as exc:
            log_notification_failure(app.logger, "management_save", exc)
            return error("We could not confirm this action. Retry the same action with this link.", 503)

    @app.post("/api/notifications/manage/recovery")
    def recover_link():
        data, failure = payload()
        if failure is not None:
            return failure
        if store is None:
            return unavailable()
        try:
            if type(data) is not dict or set(data) != {"email"}:
                raise diagnostic_error(ValueError("Enter only your email address."), "recover_link", "recovery_fields", stage="request")
            email = normalize_email(data["email"])
        except ValueError as invalid:
            return error(str(invalid), 400)
        try:
            store.request_recovery(email)
        except Exception as exc:
            log_notification_failure(app.logger, "management_recovery", exc)
            return unavailable()
        return jsonify(status="received", message=RECOVERY_RECEIVED)

    @app.post("/api/notifications/manage/withdrawal-receipt")
    @app.post("/api/notifications/manage/withdrawal-ack")
    def withdrawal_receipt():
        data, failure = payload()
        if failure is not None:
            return failure
        if store is None:
            return unavailable()
        acknowledge = request.path.endswith("/withdrawal-ack")
        authority = "receipt" if acknowledge else "token"
        fields = {"action", "revision"}
        allowed = (fields | {authority}, fields | {authority, "preferences"}) if acknowledge else (
            fields, fields | {"preferences"}, fields | {"token"}, fields | {"token", "preferences"})
        if (type(data) is not dict or set(data) not in allowed
                or "preferences" in data and type(data["preferences"]) is not dict):
            return error(UNAVAILABLE, 400)
        try:
            if acknowledge:
                return clear_session(jsonify(store.acknowledge_withdrawal(data["receipt"], browser(),
                    data["action"], data["revision"], data.get("preferences"))))
            return jsonify(store.prepare_withdrawal(request.cookies.get(cookie_name), browser(),
                data["action"], data["revision"], data.get("preferences"), token=data.get("token")))
        except (ManagementUnavailable, ManagementInputError) as exc:
            log_notification_failure(app.logger, "withdrawal_receipt", exc, http_status=400)
            return error(UNAVAILABLE, 400)
        except Exception as exc:
            log_notification_failure(app.logger, "withdrawal_ack" if acknowledge else "withdrawal_receipt", exc)
            return unavailable()

from .notification_dispatch import diagnostic_error

from .notification_dispatch import retain_failure
