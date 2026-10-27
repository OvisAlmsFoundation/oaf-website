"""Focused service HTTP/store checks under the existing early offline guard."""

import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL

from oaf_website import integrations as api, interest_reporting as reporting
from oaf_website import notifications, state_requests
from oaf_website.database_config import DatabaseConfig
from oaf_website.state_request_schema import STATE_CODES
from test_notifications import SubscriptionEngine, choices, post as public_subscribe, withdraw
from test_state_requests import ModelEngine, ORIGIN, SECRET, recognize, submit as public_request

SUBMISSION = "1" * 64  # Synthetic fixtures, never operational credentials.
REPORTING = "2" * 64
CONFIG = api.IntegrationConfig("testing", "gramanna", SUBMISSION, REPORTING)
STATE_PATH = api.PREFIX + "/state-requests"
NOTIFICATION_PATH = api.PREFIX + "/notifications"
REPORT_PATH = api.PREFIX + "/interest-summary"


class SummaryEngine:
    """Return modeled aggregates; inspect real compiled SQL without executing it."""
    def __init__(self, states, subscriptions):
        self.states, self.subscriptions = states, subscriptions
        self.statements, self.data_queries, self.transactions = [], 0, 0
        self.failure, self.after_snapshot = None, None
        self.reported_at = datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=-7)))
        self.override = {}

    @contextmanager
    def connect(self):
        if self.failure == "connect":
            raise RuntimeError("private@example.com password=synthetic-secret")
        engine = self

        class Connection:
            @contextmanager
            def begin(self):
                engine.transactions += 1
                yield
                if engine.failure == "commit":
                    raise RuntimeError("private@example.com synthetic commit details")

            def execute(self, statement):
                sql = str(statement.compile(dialect=postgresql.dialect()))
                engine.statements.append(sql)
                if sql == "SET TRANSACTION READ ONLY":
                    return SimpleNamespace()
                assert engine.statements[-2] == "SET TRANSACTION READ ONLY"
                assert sql.startswith("SELECT statement_timestamp()")
                assert "jsonb_object_agg" in sql and "FILTER (WHERE" in sql
                assert "unsubscribed_at IS NULL" in sql
                assert all(name not in sql for name in ("browser_key", "email", "unsubscribe_digest"))
                engine.data_queries += 1
                if engine.failure == "query":
                    raise RuntimeError("private@example.com synthetic SQL details")
                counts, availability = {}, {}
                for state, _key in engine.states.records:
                    counts[state] = counts.get(state, 0) + 1
                active = [deepcopy(row) for row in engine.subscriptions.records.values()
                          if row["unsubscribed_at"] is None]
                for row in active:
                    if row["state"] is not None:
                        availability[row["state"]] = availability.get(row["state"], 0) + 1
                result = dict(reported_at=engine.reported_at, states=counts, availability=availability,
                              active_total=len(active), state_availability=sum(availability.values()),
                              **{name: sum(row[name] for row in active) for name in reporting.PREFERENCES[:3]})
                result.update(engine.override)
                if engine.after_snapshot:
                    engine.after_snapshot()
                return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: result))

        yield Connection()


def application(states, subscriptions, summary, config=CONFIG, secret=SECRET,
                origin=ORIGIN, local=False):
    return state_requests._build_app(
        state_requests.RequestStore(states), state_requests.BrowserRecognition(secret), origin,
        subscription_store=notifications.SubscriptionStore(subscriptions),
        integration_config=config, reporting_store=summary,
        environment=config.environment if config is not None else None,
        allow_insecure_localhost=local,
    )


@pytest.fixture
def setup():
    states, subscriptions = ModelEngine(), SubscriptionEngine()
    engine = SummaryEngine(states, subscriptions)
    summary = reporting.InterestSummaryStore(engine, "testing")
    app = application(states, subscriptions, summary)
    return SimpleNamespace(states=states, subscriptions=subscriptions, engine=engine,
                           summary=summary, app=app, client=app.test_client(use_cookies=False))


def service(client, path=STATE_PATH, *, credential=SUBMISSION, data=None, method=None,
            headers=None, origin=ORIGIN, **options):
    supplied = {} if credential is None else {"Authorization": "Bearer " + credential}
    supplied.update(headers or {})
    if data is None and path == STATE_PATH:
        data = {"state": "CA", "visitor_token": "a" * 64}
    if data is not None:
        options["json"] = data
    return client.open(path, method=method or ("GET" if path == REPORT_PATH else "POST"),
                       base_url=origin, headers=supplied, **options)


def mobile(**overrides):
    return dict(dict(email=" Person+updates@Example.com ", android_launch=True,
                     ios_launch=False, consent=True, token="b" * 64), **overrides)


def test_unknown_service_route_is_private_and_does_not_query(setup):
    reply=service(setup.client,path=api.PREFIX+'/unknown',method='GET')
    assert reply.status_code==404
    assert setup.engine.data_queries==0


def test_summary_bad_request_is_classified_before_query(setup,monkeypatch):
    from werkzeug.exceptions import BadRequest
    from flask import Request
    monkeypatch.setattr(Request,'get_data',Mock(side_effect=BadRequest()))
    reply=service(setup.client,path=REPORT_PATH,credential=REPORTING)
    assert reply.status_code==400
    assert setup.engine.data_queries==0


def test_accepted_duplicate_and_existing_public_totals(setup):
    first = service(setup.client)
    before = deepcopy(setup.states.records)
    second = service(setup.client)
    assert first.status_code == 201 and first.json["status"] == "accepted"
    assert second.status_code == 200 and second.json["status"] == "duplicate"
    assert set(first.json) == {"status", "state", "message"}
    assert setup.states.records == before
    assert setup.app.test_client().get("/api/state-requests/totals", base_url=ORIGIN).json["totals"]["CA"] == 1
    assert "a" * 64 not in first.text and "browser" not in first.json
    assert "Set-Cookie" not in first.headers


def test_repeat_and_distinct_tokens_from_same_outbound_ip_across_restart(setup):
    assert service(setup.client).status_code == 201
    restarted = application(setup.states, setup.subscriptions, setup.summary).test_client(use_cookies=False)
    assert service(restarted).status_code == 200
    assert service(restarted, data={"state": "CA", "visitor_token": "c" * 64}).status_code == 201
    assert service(restarted, data={"state": "NY", "visitor_token": "a" * 64}).status_code == 201
    assert len(setup.states.records) == 3
    assert len({key for _state, key in setup.states.records}) == 2


def test_identity_environment_and_public_browser_domains_are_separate():
    key = api.visitor_key(CONFIG, SECRET, "a" * 64)
    assert key == api.visitor_key(CONFIG, SECRET, "a" * 64)
    assert key != api.visitor_key(replace(CONFIG, client_id="other"), SECRET, "a" * 64)
    assert key != api.visitor_key(replace(CONFIG, environment="development"), SECRET, "a" * 64)
    assert key != api.visitor_key(CONFIG, b"different-persistent-protected-secret", "a" * 64)
    assert key != state_requests.BrowserRecognition(SECRET).browser_key("a" * 64)
    # Rotating service credentials preserves browser recognition.
    assert key == api.visitor_key(replace(CONFIG, submission_credential="3" * 64), SECRET, "a" * 64)


@pytest.mark.parametrize("state", STATE_CODES)
def test_all_fifty_states_accepted_including_nonpilot_states(setup, state):
    body = dict(state=state, visitor_token="a" * 64)
    assert service(setup.client, data=body).status_code == 201
    assert service(setup.client, data=body).status_code == 200


@pytest.mark.parametrize("state", [None, 4, True, [], {}, "ca", "DC", "PR", "ZZ", " CA", "California"])
def test_invalid_states(setup, state):
    assert service(setup.client, data=dict(state=state, visitor_token="a" * 64)).status_code == 400
    assert not setup.states.records


@pytest.mark.parametrize("token", [None, 42, True, {}, [], "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 63 + "\n"])
def test_invalid_visitor_tokens(setup, token):
    assert service(setup.client, data=dict(state="CA", visitor_token=token)).status_code == 400
    assert not setup.states.records


@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH, REPORT_PATH])
@pytest.mark.parametrize("credential", [None, "", "wrong", "3" * 64, "1" * 63, "1" * 65, "A" * 64])
def test_missing_or_invalid_credentials_never_reach_stores(setup, path, credential):
    response = service(setup.client, path, credential=credential, data=mobile() if path == NOTIFICATION_PATH else None)
    assert response.status_code == 401 and response.json["code"] == "unauthorized"
    assert "WWW-Authenticate" in response.headers
    assert not setup.states.statements and not setup.subscriptions.statements and not setup.engine.statements


@pytest.mark.parametrize("path,credential", [(STATE_PATH, REPORTING), (NOTIFICATION_PATH, REPORTING), (REPORT_PATH, SUBMISSION)])
def test_permission_separation(setup, path, credential):
    assert service(setup.client, path, credential=credential).status_code == 401
    assert not setup.states.records and not setup.subscriptions.records and not setup.engine.statements


@pytest.mark.parametrize("authorization", ["Basic " + SUBMISSION, "bearer " + SUBMISSION,
    "Bearer  " + SUBMISSION, "Bearer " + SUBMISSION + ", Bearer " + REPORTING, "Bearer " + SUBMISSION + " ", "Bearer é"])
def test_strict_authorization_header(setup, authorization):
    assert service(setup.client, headers={"Authorization": authorization}).status_code == 401


def test_authentication_uses_constant_time_comparison(setup, monkeypatch):
    compare = Mock(wraps=api.hmac.compare_digest)
    monkeypatch.setattr(api.hmac, "compare_digest", compare)
    assert service(setup.client).status_code == 201
    assert service(setup.client, credential=REPORTING).status_code == 401
    assert service(setup.client, credential=None).status_code == 401
    assert compare.call_args_list[0].args == (SUBMISSION, SUBMISSION)
    assert compare.call_args_list[1].args == (REPORTING, SUBMISSION)
    assert compare.call_args_list[2].args == ("0" * 64, SUBMISSION)


@pytest.mark.parametrize("headers", [{"Origin": ORIGIN}, {"Origin": "https://gramanna.example"},
    {"Origin": "null"}, {"Referer": ORIGIN + "/gramanna.html"}, {"Sec-Fetch-Site": "same-origin"},
    {"Sec-Fetch-Mode": "cors"}, {"Cookie": "private=synthetic"}])
def test_browser_context_rejected_without_cors(setup, headers):
    response = service(setup.client, headers=headers)
    assert response.status_code == 403 and response.json["code"] == "backend_only"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert not setup.states.records


@pytest.mark.parametrize("origin,headers", [("http://website.example", {}),
    ("http://website.example", {"X-Forwarded-Proto": "https"}),
    ("https://other.example", {}), ("https://website.example:8443", {})])
def test_https_and_configured_origin_required(setup, origin, headers):
    assert service(setup.client, origin=origin, headers=headers).status_code == 403
    assert not setup.states.records


def test_loopback_http_requires_explicit_opt_in_and_local_peer(setup):
    origin = "http://localhost:5055"
    local = application(setup.states, setup.subscriptions, setup.summary, origin=origin, local=True)
    client = local.test_client(use_cookies=False)
    assert service(client, origin=origin).status_code == 201
    assert service(client, origin=origin, environ_overrides={"REMOTE_ADDR": "203.0.113.1"}).status_code == 403
    with pytest.raises(ValueError):
        application(setup.states, setup.subscriptions, setup.summary, origin=origin)


@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH, REPORT_PATH])
@pytest.mark.parametrize("method", ["OPTIONS", "PUT", "DELETE", "HEAD"])
def test_unsupported_methods_are_sanitized_without_cors(setup, path, method):
    response = service(setup.client, path, method=method, credential=REPORTING if path == REPORT_PATH else SUBMISSION)
    assert response.status_code == 405
    assert "Access-Control-Allow-Origin" not in response.headers
    if method != "HEAD":
        assert response.json["code"] == "method_not_allowed"


@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH, REPORT_PATH])
def test_query_fields_cannot_select_environment_or_carry_tokens(setup, path):
    response = service(setup.client, path, credential=REPORTING if path == REPORT_PATH else SUBMISSION,
                       query_string={"environment": "production", "token": "private-do-not-reflect"})
    assert response.status_code == 400
    assert "production" not in response.text and "private-do-not-reflect" not in response.text
    assert not setup.engine.statements


@pytest.mark.parametrize("body,status", [("{}", 400), ("null", 400), ("[]", 400), ("{", 400),
    ('{"state":"CA","state":"NY","visitor_token":"' + "a" * 64 + '"}', 400),
    ('{"state":"CA","visitor_token":NaN}', 400),
    ('{"state":"CA","visitor_token":Infinity}', 400),
    (b"\xff", 400), ("[" * 1000, 400), ("x" * 1025, 413)])
@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH])
def test_strict_json_and_size_limit(setup, body, status, path):
    response = setup.client.post(path, base_url=ORIGIN, data=body, content_type="application/json",
                                 headers={"Authorization": "Bearer " + SUBMISSION})
    assert response.status_code == status and response.json["status"] == "error"
    assert not setup.states.records and not setup.subscriptions.records


@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH])
@pytest.mark.parametrize("body_type", ["text/plain", "application/x-www-form-urlencoded", "application/json; charset=utf-16"])
def test_content_type_and_encoding(setup, path, body_type):
    body = '{}' if "utf-16" not in body_type else '{}'.encode("utf-16")
    response = setup.client.post(path, base_url=ORIGIN, data=body, content_type=body_type,
                                 headers={"Authorization": "Bearer " + SUBMISSION})
    assert response.status_code in {400, 415}
    assert service(setup.client, path, headers={"Content-Encoding": "gzip"}).status_code == 415


@pytest.mark.parametrize("length,status", [(1024, 201), (1025, 413), (2000, 413)])
def test_chunked_state_body_cannot_accept_a_truncated_valid_prefix(setup, length, status):
    prefix = json.dumps(dict(state="CA", visitor_token="a" * 64)).encode()
    body = prefix + b" " * (length - len(prefix))
    response = setup.client.post(STATE_PATH, base_url=ORIGIN, content_type="application/json",
        headers={"Authorization": "Bearer " + SUBMISSION},
        environ_overrides={"wsgi.input": BytesIO(body), "wsgi.input_terminated": True, "CONTENT_LENGTH": ""})
    assert response.status_code == status
    assert len(setup.states.records) == (1 if status == 201 else 0)


def test_chunked_mobile_and_report_bodies_are_bounded(setup):
    prefix = json.dumps(mobile()).encode()
    for path, credential in ((NOTIFICATION_PATH, SUBMISSION), (REPORT_PATH, REPORTING)):
        response = setup.client.open(path, method="GET" if path == REPORT_PATH else "POST",
            base_url=ORIGIN, content_type="application/json", headers={"Authorization": "Bearer " + credential},
            environ_overrides={"wsgi.input": BytesIO(prefix + b" " * (1025 - len(prefix))),
                               "wsgi.input_terminated": True, "CONTENT_LENGTH": ""})
        assert response.status_code == 413
    assert not setup.subscriptions.records and not setup.engine.statements


@pytest.mark.parametrize("data", [{"state": "CA"}, {"visitor_token": "a" * 64},
    {"state": "CA", "visitor_token": "a" * 64, "client_id": "other"},
    {"state": "CA", "visitor_token": "a" * 64, "browser_key": "caller-selected"}])
def test_state_exact_fields(setup, data):
    assert service(setup.client, data=data).status_code == 400
    assert not setup.states.records


@pytest.mark.parametrize("android,ios", [(True, False), (False, True), (True, True)])
def test_mobile_combinations_reuse_normalization_consent_and_hashing(setup, android, ios):
    response = service(setup.client, NOTIFICATION_PATH, data=mobile(android_launch=android, ios_launch=ios))
    assert response.status_code == 200 and response.json["status"] == "received"
    record = next(iter(setup.subscriptions.records.values()))
    assert record["email"] == "person+updates@example.com"
    assert record["android_launch"] == android and record["ios_launch"] == ios
    assert record["web_launch"] is False and record["state"] is None
    assert record["consent_version"] == notifications.CONSENT_VERSION
    assert record["unsubscribe_digest"] == hashlib.sha256(("b" * 64).encode()).hexdigest()
    assert "b" * 64 not in response.text + repr(record)
    assert notifications.UnsubscribeCapabilities(SECRET).read(response.json["unsubscribe_token"]) == record["unsubscribe_digest"]
    assert response.json["message"] == "Your submission was processed. New subscriptions are saved; existing active preferences stay unchanged."


@pytest.mark.parametrize("change", [dict(android_launch=False), dict(android_launch=1), dict(ios_launch="true"),
    dict(consent=False), dict(consent=1), dict(consent="yes"), dict(email="invalid"),
    dict(email="private@example.com\n"), dict(email="é@example.com"), dict(email="a" * 255 + "@example.com"),
    dict(token=None), dict(token="b" * 63), dict(token="B" * 64)])
def test_mobile_validation_and_consent(setup, change):
    assert service(setup.client, NOTIFICATION_PATH, data=mobile(**change)).status_code == 400
    assert not setup.subscriptions.records


@pytest.mark.parametrize("field,value", [("web_launch", True), ("web_launch", False), ("state", "CA"),
    ("state", None), ("environment", "production"), ("consent_version", "caller-selected")])
def test_mobile_rejects_caller_selected_nonmobile_fields(setup, field, value):
    assert service(setup.client, NOTIFICATION_PATH, data=dict(mobile(), **{field: value})).status_code == 400
    assert not setup.subscriptions.records


def test_missing_mobile_fields(setup):
    for field in mobile():
        body = mobile()
        del body[field]
        assert service(setup.client, NOTIFICATION_PATH, data=body).status_code == 400
    assert not setup.subscriptions.records


def test_active_public_email_immutable_and_private_capability_not_disclosed(setup):
    public = setup.app.test_client()
    csrf = recognize(public)
    original = public_subscribe(public, csrf, choices(android_launch=False, state="TX"))
    before = deepcopy(setup.subscriptions.records)
    duplicate = service(setup.client, NOTIFICATION_PATH, data=mobile(ios_launch=True))
    assert duplicate.status_code == 200
    assert setup.subscriptions.records == before
    assert original.json["message"] == duplicate.json["message"]
    assert original.json["unsubscribe_token"] != duplicate.json["unsubscribe_token"]
    assert notifications.UnsubscribeCapabilities(SECRET).read(duplicate.json["unsubscribe_token"]) not in before
    assert public_subscribe(public, csrf, {"token": duplicate.json["unsubscribe_token"]},
                            "/api/notifications/unsubscribe").status_code == 200
    assert setup.subscriptions.records == before


def test_new_mobile_lifecycle_uses_existing_private_unsubscribe_and_replay_protection(setup):
    first = service(setup.client, NOTIFICATION_PATH, data=mobile())
    public = setup.app.test_client()
    csrf = recognize(public)
    assert public_subscribe(public, csrf, {"token": first.json["unsubscribe_token"]},
                            "/api/notifications/unsubscribe").status_code == 200
    before = deepcopy(setup.subscriptions.records)
    assert service(setup.client, NOTIFICATION_PATH, data=mobile()).status_code == 200
    assert setup.subscriptions.records == before
    newer = service(setup.client, NOTIFICATION_PATH, data=mobile(token="c" * 64, ios_launch=True))
    assert newer.status_code == 200 and len(setup.subscriptions.records) == 2
    assert public_subscribe(public, csrf, {"token": first.json["unsubscribe_token"]},
                            "/api/notifications/unsubscribe").status_code == 200
    active = [row for row in setup.subscriptions.records.values() if row["unsubscribed_at"] is None]
    assert len(active) == 1 and active[0]["ios_launch"]
    assert public_subscribe(public, csrf, {"token": newer.json["unsubscribe_token"][:-1] + "x"},
                            "/api/notifications/unsubscribe").status_code == 400
    assert [row for row in setup.subscriptions.records.values() if row["unsubscribed_at"] is None] == active


def test_receipt_replay_cannot_create_or_withdraw_another_email(setup):
    first = service(setup.client, NOTIFICATION_PATH, data=mobile())
    before = deepcopy(setup.subscriptions.records)
    replay = service(setup.client, NOTIFICATION_PATH, data=mobile(email="other@example.com"))
    assert replay.json == first.json and setup.subscriptions.records == before
    assert service(setup.client, NOTIFICATION_PATH, data=mobile(email="other@example.com", token="d" * 64)).status_code == 200
    public = setup.app.test_client()
    csrf = recognize(public)
    withdraw(public, csrf, "b" * 64)
    assert [row["email"] for row in setup.subscriptions.records.values() if row["unsubscribed_at"] is None] == ["other@example.com"]


@pytest.mark.parametrize("phase", ["connect", "insert", "commit", "uncertain"])
def test_state_failures_and_uncertain_repeat(setup, caplog, phase):
    setup.states.failure = phase
    response = service(setup.client)
    assert response.status_code == 503 and response.json["code"] == "submission_unconfirmed"
    assert len(setup.states.records) == (1 if phase == "uncertain" else 0)
    assert "synthetic-private" not in response.text + caplog.text
    setup.states.failure = None
    assert service(setup.client).status_code == (200 if phase == "uncertain" else 201)
    assert len(setup.states.records) == 1


@pytest.mark.parametrize("phase", ["connect", "execute", "commit", "uncertain"])
def test_notification_failures_and_uncertain_repeat(setup, caplog, phase):
    setup.subscriptions.failure = phase
    response = service(setup.client, NOTIFICATION_PATH, data=mobile())
    assert response.status_code == 503 and response.json["code"] == "submission_unconfirmed"
    assert "unsubscribe_token" not in response.json
    assert len(setup.subscriptions.records) == (1 if phase == "uncertain" else 0)
    assert "private@example.com" not in response.text + caplog.text
    setup.subscriptions.failure = None
    assert service(setup.client, NOTIFICATION_PATH, data=mobile()).status_code == 200
    assert len(setup.subscriptions.records) == 1


def test_state_store_invalid_acceptance_result_is_unconfirmed(setup, monkeypatch):
    monkeypatch.setattr(state_requests.RequestStore, "submit", lambda *_args: "accepted")
    response = service(setup.client)
    assert response.status_code == 503 and response.json["code"] == "submission_unconfirmed"


@pytest.mark.parametrize("change", [dict(unsubscribe_token="invalid-private-capability"),
    dict(email="private@example.com"), dict(status="created")])
def test_invalid_notification_response_is_not_disclosed_and_same_receipt_can_retry(setup, monkeypatch, change):
    original = api.subscription_response
    def malformed(values, capabilities):
        response = original(values, capabilities)
        body = response.get_json()
        body.update(change)
        return setup.app.json.response(body)
    monkeypatch.setattr(api, "subscription_response", malformed)
    response = service(setup.client, NOTIFICATION_PATH, data=mobile())
    assert response.status_code == 503
    assert "unsubscribe_token" not in response.json
    assert "private@example.com" not in response.text and "invalid-private-capability" not in response.text
    assert len(setup.subscriptions.records) == 1
    monkeypatch.setattr(api, "subscription_response", original)
    assert service(setup.client, NOTIFICATION_PATH, data=mobile()).status_code == 200
    assert len(setup.subscriptions.records) == 1


def test_concurrent_model_duplicates_are_atomic(setup):
    def state_attempt(_index):
        return service(setup.app.test_client(use_cookies=False)).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(state_attempt, range(16)))
    assert responses.count(201) == 1 and responses.count(200) == 15

    def mobile_attempt(index):
        return service(setup.app.test_client(use_cookies=False), NOTIFICATION_PATH,
                       data=mobile(token=f"{index:064x}", ios_launch=bool(index % 2))).status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(mobile_attempt, range(16))) == {200}
    assert len(setup.subscriptions.records) == 1


def populate(setup):
    public = setup.app.test_client()
    csrf = recognize(public)
    public_request(public, csrf, "CA")
    service(setup.client)
    service(setup.client, data=dict(state="NY", visitor_token="a" * 64))
    public_subscribe(public, csrf, choices(email="all@example.com", android_launch=True, ios_launch=True, state="CA"))
    public_subscribe(public, csrf, choices(email="state@example.com", token="d" * 64, web_launch=False, state="TX"))
    public_subscribe(public, csrf, choices(email="withdrawn@example.com", token="e" * 64, android_launch=True, ios_launch=True, state="CA"))
    withdraw(public, csrf, "e" * 64)
    service(setup.client, NOTIFICATION_PATH, data=mobile(email="mobile@example.com", ios_launch=True))


def test_aggregate_counts_combined_sources_with_overlap_and_withdrawals(setup):
    populate(setup)
    response = service(setup.client, REPORT_PATH, credential=REPORTING)
    assert response.status_code == 200
    result = response.json
    assert result["environment"] == "testing" and result["reported_at_utc"] == "2026-10-12T19:00:00.000000Z"
    assert result["state_requests"]["accepted_total"] == 3
    assert result["state_requests"]["by_state"]["CA"] == 2
    assert result["state_requests"]["by_state"]["NY"] == 1
    active = result["notifications"]
    assert active["active_total"] == 3
    assert active["preferences"] == dict(web_launch=1, android_launch=2, ios_launch=2, state_availability=2)
    assert active["state_availability_by_state"]["CA"] == active["state_availability_by_state"]["TX"] == 1
    assert sum(active["preferences"].values()) == 7  # Never used as unique subscribers.
    assert len(result["state_requests"]["by_state"]) == len(active["state_availability_by_state"]) == 50
    assert setup.engine.data_queries == setup.engine.transactions == 1
    assert len(setup.engine.statements) == 2


def test_empty_verified_report_is_zero_only_after_successful_query(setup):
    response = service(setup.client, REPORT_PATH, credential=REPORTING)
    assert response.status_code == 200 and setup.engine.data_queries == 1
    assert response.json["state_requests"]["accepted_total"] == response.json["notifications"]["active_total"] == 0


def test_single_statement_snapshot_does_not_mix_concurrent_changes(setup):
    populate(setup)
    def change():
        setup.states.records.clear()
        for record in setup.subscriptions.records.values():
            record["unsubscribed_at"] = datetime.now(timezone.utc)
    setup.engine.after_snapshot = change
    response = service(setup.client, REPORT_PATH, credential=REPORTING)
    assert response.json["state_requests"]["accepted_total"] == response.json["notifications"]["active_total"] == 3
    setup.engine.after_snapshot = None
    later = service(setup.client, REPORT_PATH, credential=REPORTING)
    assert later.json["state_requests"]["accepted_total"] == later.json["notifications"]["active_total"] == 0
    assert setup.engine.data_queries == 2


@pytest.mark.parametrize("phase", ["connect", "query", "commit"])
def test_reporting_failure_never_fabricates_zeros(setup, caplog, phase):
    populate(setup)
    setup.engine.failure = phase
    response = service(setup.client, REPORT_PATH, credential=REPORTING)
    assert response.status_code == 503 and response.json["code"] == "service_unavailable"
    assert set(response.json) == {"status", "code", "message"}
    assert "private@example.com" not in response.text + caplog.text and "synthetic-secret" not in response.text + caplog.text
    setup.engine.failure = None
    assert service(setup.client, REPORT_PATH, credential=REPORTING).json["notifications"]["active_total"] == 3


@pytest.mark.parametrize("override", [dict(active_total=-1), dict(active_total=True), dict(web_launch=1),
    dict(states={"ZZ": 1}), dict(states={"CA": "1"}), dict(states=None),
    dict(availability={"CA": 1}), dict(reported_at=datetime(2026, 10, 12)), dict(reported_at="invalid")])
def test_malformed_database_aggregate_fails_closed(setup, override):
    setup.engine.override = override
    assert service(setup.client, REPORT_PATH, credential=REPORTING).status_code == 503


@pytest.mark.parametrize("change", [dict(environment="development"), dict(email="private@example.com"),
    dict(reported_at_utc="not-a-utc-time"), dict(state_requests={"accepted_total": 99, "by_state": {}}),
    dict(notifications={"active_total": 0, "preferences": {}, "state_availability_by_state": {}})])
def test_reporting_response_allowlist_rejects_private_extra_or_mismatched_data(setup, change):
    report = setup.summary.summary()
    report.update(change)
    broken = application(setup.states, setup.subscriptions, SimpleNamespace(summary=lambda: report))
    response = service(broken.test_client(use_cookies=False), REPORT_PATH, credential=REPORTING)
    assert response.status_code == 503 and "private@example.com" not in response.text


@pytest.mark.parametrize("value", ["20261012Z", "2026-10-12Z", "2026-10-12T00:00:00+00:00", "2026-10-12T00:00:00Z"])
def test_report_time_must_be_canonical_utc(setup, value):
    report = setup.summary.summary()
    report["reported_at_utc"] = value
    with pytest.raises(ValueError):
        reporting.validate_summary(report, "testing")


@pytest.mark.parametrize("body,status", [("{}", 400), ("x" * 1025, 413)])
def test_reporting_rejects_body(setup, body, status):
    response = setup.client.get(REPORT_PATH, base_url=ORIGIN, data=body,
                                headers={"Authorization": "Bearer " + REPORTING})
    assert response.status_code == status and not setup.engine.statements


def test_private_values_absent_from_reporting_logs_and_urls(setup, caplog):
    populate(setup)
    response = service(setup.client, REPORT_PATH, credential=REPORTING)
    serialized = response.text + caplog.text + repr(setup.engine.statements)
    for private in (SUBMISSION, REPORTING, SECRET.decode(), "all@example.com", "state@example.com",
                    "mobile@example.com", "withdrawn@example.com", "browser_key", "unsubscribe_digest", "unsubscribe_token"):
        assert private not in serialized
    for digest in setup.subscriptions.records:
        assert digest not in serialized
    assert "Location" not in response.headers and "Set-Cookie" not in response.headers


@pytest.mark.parametrize("path", [STATE_PATH, NOTIFICATION_PATH, REPORT_PATH])
def test_service_response_privacy_headers(setup, path):
    response = service(setup.client, path, credential=REPORTING if path == REPORT_PATH else SUBMISSION,
                       data=mobile() if path == NOTIFICATION_PATH else None)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in response.headers and "Location" not in response.headers


def test_credential_budgets_and_reset_are_deterministic_and_separate():
    now = [10.0]
    limits = api.ServiceLimits(lambda: now[0])
    assert all(limits.allow("submission") for _ in range(120))
    assert not limits.allow("submission")
    assert all(limits.allow("reporting") for _ in range(30))
    assert not limits.allow("reporting")
    assert set(limits.windows) == {"submission", "reporting"}
    now[0] += 60
    assert limits.allow("submission") and limits.allow("reporting")


def test_rate_limit_does_not_call_database_and_reporting_budget_is_separate(setup):
    for _ in range(120):
        assert service(setup.client).status_code in {200, 201}
    before = len(setup.states.statements)
    limited = service(setup.client)
    assert limited.status_code == 429 and limited.headers["Retry-After"] == "60"
    assert len(setup.states.statements) == before
    assert service(setup.client, REPORT_PATH, credential=REPORTING).status_code == 200


@pytest.mark.parametrize("overrides", [dict(environment="unknown"), dict(client_id=""), dict(client_id="../client"),
    dict(client_id="é"), dict(submission_credential="short-private"), dict(reporting_credential=None),
    dict(reporting_credential=SUBMISSION), dict(submission_credential="A" * 64)])
def test_invalid_configuration_fixed_messages_and_hidden_secrets(overrides):
    values = dict(environment="testing", client_id="gramanna", submission_credential=SUBMISSION,
                  reporting_credential=REPORTING)
    values.update(overrides)
    with pytest.raises(api.IntegrationConfigurationError) as failure:
        api.IntegrationConfig(**values)
    assert "short-private" not in str(failure.value) and SUBMISSION not in str(failure.value)
    assert SUBMISSION not in repr(CONFIG) and REPORTING not in repr(CONFIG)


@pytest.mark.parametrize("config,environment", [(CONFIG, "development"), (None, "testing"), ({}, "testing")])
def test_configuration_mismatch_fails_before_credentials(monkeypatch, config, environment):
    loader = Mock(side_effect=AssertionError("Credential loader must not run"))
    monkeypatch.setattr(state_requests, "load_database_config", loader)
    monkeypatch.setattr(state_requests, "load_testing_database_config", loader)
    # None means intentionally disabled, tested separately below.
    if config is None:
        with pytest.raises(api.IntegrationConfigurationError):
            api.validate_configuration(config, environment, SECRET)
    else:
        with pytest.raises(api.IntegrationConfigurationError):
            state_requests.create_app(expected_profile=environment, recognition_secret=SECRET,
                                      public_origin=ORIGIN, integration_config=config)
    loader.assert_not_called()


def test_credentials_cannot_reuse_persistent_key():
    config = replace(CONFIG, submission_credential=(b"s" * 32).hex())
    with pytest.raises(api.IntegrationConfigurationError):
        api.validate_configuration(config, "testing", b"s" * 32)


def test_factory_uses_verified_existing_engine_without_startup_connection(monkeypatch):
    config = DatabaseConfig("testing", URL.create("postgresql+psycopg", username="oaf_website_test_app",
        password="synthetic-only", host="127.0.0.1", port=5432, database="oaf_website_test"))
    engine = SimpleNamespace(connect=Mock(side_effect=AssertionError("No startup connection")))
    loader, creator, listener = Mock(return_value=config), Mock(return_value=engine), Mock()
    monkeypatch.setattr(state_requests, "load_testing_database_config", loader)
    monkeypatch.setattr(state_requests, "create_engine", creator)
    monkeypatch.setattr(state_requests.event, "listen", listener)
    app = state_requests.create_app(expected_profile="testing", recognition_secret=SECRET,
                                    public_origin=ORIGIN, integration_config=CONFIG)
    assert app.extensions["state_requests_engine"] is engine
    assert {STATE_PATH, NOTIFICATION_PATH, REPORT_PATH}.issubset({rule.rule for rule in app.url_map.iter_rules()})
    engine.connect.assert_not_called()
    loader.assert_called_once_with()
    assert creator.call_args.kwargs["hide_parameters"] is True
    assert listener.call_args.args[1] == "checkout"


def test_disabled_integration_and_preserved_public_cookie_csrf_and_origin(setup):
    disabled = application(setup.states, setup.subscriptions, setup.summary, config=None)
    assert service(disabled.test_client(use_cookies=False)).status_code == 404
    public = setup.app.test_client()
    assert service(public, path="/api/state-requests", data={"state": "CA"}).status_code == 403
    assert service(public, path="/api/notifications", data=choices()).status_code == 403
    csrf = recognize(public)
    assert public_request(public, csrf).status_code == 201
    assert public_request(public, csrf).status_code == 200
    assert public_subscribe(public, csrf, choices()).status_code == 200
    assert public_request(public, csrf, "NY", headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf}).status_code == 403
    assert setup.app.config["MAX_CONTENT_LENGTH"] == 1024
    assert len(setup.states.records) == 1 and len(setup.subscriptions.records) == 1


RELEASE_PATH = api.PREFIX + "/release-events"
RELEASE_KEY = "4" * 64


@pytest.fixture
def release_api():
    from test_notification_delivery import Model
    from oaf_website.notification_delivery import NotificationDeliveryStore
    model = Model()
    store = NotificationDeliveryStore(model, SECRET, "testing", releases_enabled=True, management_enabled=True)
    config = replace(CONFIG, release_credential=RELEASE_KEY)
    app = state_requests._build_app(None, state_requests.BrowserRecognition(SECRET), ORIGIN,
        integration_config=config, environment="testing", release_store=store)
    return SimpleNamespace(model=model, store=store, config=config, app=app, client=app.test_client(use_cookies=False))


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("compact", [False, True])
def test_authenticated_release_acceptance_persists_once_with_stable_wire_identity(release_api, platform, compact):
    from test_notification_delivery import payload
    from oaf_website.notification_delivery_schema import events
    values = payload(platform)
    if compact:
        for name in ("event_id", "source_approval_id"): values[name] = values[name].replace("-", "")
    first = service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=values)
    second = service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=values)
    assert first.status_code == second.status_code == 200
    assert first.json == second.json == dict(status="accepted", event_id=payload()["event_id"])
    assert len(release_api.model.rows(events)) == 1
    assert not any("brevo" in sql.lower() for sql in release_api.model.statements)


@pytest.mark.parametrize("credential", [None, SUBMISSION, REPORTING, "5" * 64])
def test_signup_and_reporting_permissions_cannot_approve_a_release(release_api, credential):
    from test_notification_delivery import payload
    assert service(release_api.client, RELEASE_PATH, credential=credential, data=payload()).status_code == 401
    assert not release_api.model.statements


@pytest.mark.parametrize("changes,status", [
    (dict(headers={"Origin": ORIGIN}), 403), (dict(origin="https://wrong.invalid"), 403),
    (dict(origin=ORIGIN.replace("https:", "http:")), 403), (dict(method="GET"), 405),
    (dict(headers={"Content-Encoding":"gzip"}), 415), (dict(query_string="x=1"), 400),
])
def test_release_intake_reuses_backend_transport_and_request_guards(release_api, changes, status):
    from test_notification_delivery import payload
    assert service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload(), **changes).status_code == status
    assert not release_api.model.statements


@pytest.mark.parametrize("override", [dict(event_id="bad"), dict(source_approval_id=3),
    dict(environment="development"), dict(recipients=["private@example.invalid"]), dict(action="send"),
    dict(action="withdraw", previous_approval_id="bad"), dict(release_url="https://evil.invalid/")])
def test_release_fields_and_identity_fail_before_database_access(release_api, override):
    from test_notification_delivery import payload
    assert service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload(**override)).status_code == 400
    assert not release_api.model.statements


@pytest.mark.parametrize("body,media,status", [('{}', 'text/plain', 415),
    ('{"event_id":"a","event_id":"b"}', 'application/json', 400),
    ('x' * 1025, 'application/json', 413), ('[]', 'application/json', 400)])
def test_release_body_remains_strict_and_bounded(release_api, body, media, status):
    reply = release_api.client.post(RELEASE_PATH, base_url=ORIGIN, headers={"Authorization":"Bearer " + RELEASE_KEY}, data=body, content_type=media)
    assert reply.status_code == status
    assert not release_api.model.statements


def test_release_conflict_and_transaction_failure_are_safe_and_no_provider_is_constructed(release_api, caplog):
    from test_notification_delivery import payload
    from oaf_website.notification_delivery_schema import events
    assert service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload()).status_code == 200
    conflict = payload(release_id="org.oaf.other", release_url="https://play.google.com/store/apps/details?id=org.oaf.other")
    assert service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=conflict).status_code == 409
    release_api.model.failure = "connect"
    reply = service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload())
    assert reply.status_code == 503 and reply.json["code"] == "acceptance_unconfirmed"
    assert len(release_api.model.rows(events)) == 1
    assert RELEASE_KEY not in caplog.text + reply.get_data(as_text=True)
    assert "synthetic private" not in caplog.text + reply.get_data(as_text=True)


def test_release_intake_is_off_by_default(setup):
    from test_notification_delivery import payload
    assert service(setup.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload()).status_code == 503


@pytest.mark.parametrize("value", ["bad", 4, SUBMISSION, REPORTING])
def test_separate_release_credential_validation(value):
    with pytest.raises(api.IntegrationConfigurationError): replace(CONFIG, release_credential=value)


def test_release_credential_cannot_reuse_the_persistent_key():
    persistent = bytes.fromhex("ab" * 32)
    config = replace(CONFIG, release_credential=persistent.hex())
    with pytest.raises(api.IntegrationConfigurationError): api.validate_configuration(config, "testing", persistent)


@pytest.mark.parametrize("mismatch", ["environment", "secret", "disabled", "management", "credential", "type"])
def test_release_store_binding_rejects_cross_environment_and_wrong_authority(release_api, mismatch):
    store, config = release_api.store, release_api.config
    if mismatch == "environment": store.environment = "development"
    if mismatch == "secret": store.secret = b"different-protected-secret-12345678"
    if mismatch == "disabled": store.releases_enabled = False
    if mismatch == "management": store.management_enabled = False
    if mismatch == "credential": config = CONFIG
    if mismatch == "type": store = object()
    with pytest.raises(api.IntegrationConfigurationError):
        state_requests._build_app(None, state_requests.BrowserRecognition(SECRET), ORIGIN,
            integration_config=config, environment="testing", release_store=store)


def test_http_release_correction_and_withdrawal_are_idempotent(release_api):
    from test_notification_delivery import payload, changed_release
    from oaf_website.release_approval_schema import revisions
    service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=payload())
    release_api.model.elapse(seconds=1)
    values = changed_release(release_api.model)
    for _ in range(2):
        assert service(release_api.client, RELEASE_PATH, credential=RELEASE_KEY, data=values).status_code == 200
    assert len(release_api.model.rows(revisions)) == 1



@pytest.mark.parametrize("options", [dict(releases_enabled=1), dict(releases_enabled=True),
    dict(releases_enabled=True, management_enabled=True),
    dict(releases_enabled=True, management_enabled=True, integration_config=CONFIG)])
def test_release_factory_rejects_invalid_activation_before_runtime(monkeypatch, options):
    forbidden = Mock(side_effect=AssertionError("No runtime configuration access"))
    monkeypatch.setattr(state_requests, "load_testing_database_config", forbidden)
    with pytest.raises(ValueError):
        state_requests.create_app(expected_profile="testing", recognition_secret=SECRET, public_origin=ORIGIN, **options)
    forbidden.assert_not_called()


def test_release_factory_injects_matching_persistence_and_never_starts_a_sender(monkeypatch):
    from test_notification_delivery import Model, payload
    from oaf_website.notification_dispatch import ReleaseDispatcher
    model = Model()
    monkeypatch.setattr(state_requests, "load_testing_database_config", lambda:SimpleNamespace(profile="testing",url="synthetic"))
    monkeypatch.setattr(state_requests, "create_engine", lambda *a,**kw:model)
    monkeypatch.setattr(state_requests.event, "listen", lambda *a:None)
    forbidden = Mock(side_effect=AssertionError("No send on intake or startup"))
    monkeypatch.setattr(ReleaseDispatcher, "process", forbidden)
    app = state_requests.create_app(expected_profile="testing", recognition_secret=SECRET, public_origin=ORIGIN,
        integration_config=replace(CONFIG, release_credential=RELEASE_KEY), management_enabled=True, releases_enabled=True)
    assert not model.statements
    assert service(app.test_client(use_cookies=False), RELEASE_PATH, credential=RELEASE_KEY, data=payload()).status_code == 200
    forbidden.assert_not_called()


def test_direct_wire_contract_rejects_non_object_and_unknown_action():
    from test_notification_delivery import payload
    for value in (None, [], dict(payload(), action="send", previous_approval_id="0"*32)):
        with pytest.raises(ValueError): api.release_request(value,"testing")



@pytest.mark.parametrize("timestamp", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_release_timestamp_overflow_is_a_fixed_rejection_before_persistence(release_api, timestamp):
    from test_notification_delivery import payload
    reply=service(release_api.client,RELEASE_PATH,credential=RELEASE_KEY,data=payload(approved_at=timestamp))
    assert reply.status_code==400
    assert not release_api.model.statements
