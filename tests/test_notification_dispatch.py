"""Durable release orchestration with the existing serialized offline model."""
import migration_offline as isolation
isolation.require_early_registration()

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from unittest.mock import Mock

import pytest

from oaf_website import notification_dispatch as d, notification_delivery as service
from oaf_website import brevo as b
from oaf_website.notification_delivery_schema import deliveries, attempts, verification, events
from oaf_website.notifications import SubscriptionStore
from oaf_website.notification_messages import verification_message
from test_notification_delivery import Model, NOW, SECRET, EVENT, subscribe, payload, ready
from test_brevo import CONFIG, KEY, PAGE, ACCEPTED, response


@pytest.mark.parametrize("change", ["none", "preference", "withdrawal", "suppression", "official_withdrawal"])
def test_web_fixed_template_and_final_eligibility_recheck(setup, monkeypatch, change, caplog):
    from test_notification_delivery import WEB_URL, web_store, web_payload
    from oaf_website.notification_management import NotificationManagementStore
    model, _, transport, _ = setup
    store = web_store(model)
    digest = verified(model, store, web_launch=True)
    store.accept_event(web_payload())
    original = store.begin_submission
    def boundary(*args, **kwargs):
        if change == "preference":
            management = NotificationManagementStore(model, SECRET, "testing")
            management.save(management.capabilities.issue(digest, 0, model.now), "a" * 64, 0,
                            dict(web_launch=False, android_launch=True, ios_launch=True, state=None, consent=True))
        if change == "withdrawal": SubscriptionStore(model).unsubscribe(digest)
        if change == "suppression": store.suppress("subscriber1@example.invalid", "complaint")
        if change == "official_withdrawal":
            model.elapse(seconds=1)
            store.accept_release_change(web_payload(action="withdraw", previous_approval_id=payload()["source_approval_id"],
                source_approval_id="00000000-0000-0000-0000-000000000003", approved_at=model.now.isoformat()))
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "begin_submission", boundary)
    dispatcher = d.ReleaseDispatcher(store, CONFIG, PAGE, transport=transport)
    assert dispatcher.process(EVENT).processed == int(change == "none")
    assert transport.call_count == int(change == "none")
    if change == "none":
        body = json.loads(transport.call_args.args[1])
        assert body["subject"] == "GraManna is now available on the web"
        assert body["sender"] == dict(name=b.FROM_NAME, email=b.FROM_EMAIL)
        for key in ("textContent", "htmlContent"):
            assert WEB_URL in body[key] and "Manage Preferences" in body[key]
            assert "#manage=" in body[key]
        assert WEB_URL not in repr(dispatcher) + caplog.text
        assert "subscriber1@example.invalid" not in caplog.text and KEY not in caplog.text
    assert dispatcher.process(EVENT).processed == 0


def test_web_template_revalidates_config_and_keeps_safe_uncertain_recovery(setup):
    from test_notification_delivery import WEB_URL, web_store, web_payload
    from oaf_website.notification_messages import release_message
    from oaf_website.notifications import UnsubscribeCapabilities
    model, _, transport, _ = setup
    store = web_store(model); digest = verified(model, store, web_launch=True)
    capabilities = UnsubscribeCapabilities(SECRET)
    with pytest.raises(ValueError): release_message(web_payload(), digest, capabilities, PAGE)
    message = release_message(web_payload(), digest, capabilities, PAGE, web_launch_url=WEB_URL)
    assert message.subject == "GraManna is now available on the web"
    assert "Unsubscribe" in message.text and "#unsubscribe=" in message.text
    assert WEB_URL not in repr(message) and digest not in repr(message)
    store.accept_event(web_payload())
    transport.side_effect = TimeoutError("synthetic private URL and recipient")
    dispatcher = d.ReleaseDispatcher(store, CONFIG, PAGE, transport=transport)
    assert dispatcher.process(EVENT).processed == 1
    model.elapse(minutes=10)
    recovered = d.ReleaseDispatcher(web_store(model), CONFIG, PAGE, transport=transport)
    assert recovered.process(EVENT).processed == 0
    assert transport.call_count == 1 and model.rows(deliveries)[0]["status"] == "uncertain"


def test_web_template_extension_keeps_unknown_platforms_rejected():
    from test_notification_delivery import WEB_URL
    from oaf_website.notification_messages import release_message
    from oaf_website.notifications import UnsubscribeCapabilities
    with pytest.raises(ValueError, match="Invalid approved release template"):
        release_message(dict(payload(), platform="desktop"), "a" * 64,
                        UnsubscribeCapabilities(SECRET), PAGE, web_launch_url=WEB_URL)


@pytest.fixture
def setup():
    model=Model()
    store=service.NotificationDeliveryStore(model,SECRET,"testing")
    transport=Mock(return_value=response())
    dispatcher=d.ReleaseDispatcher(store,CONFIG,PAGE,transport=transport)
    return model,store,transport,dispatcher


def verified(model,store,number=1,**changes):
    digest=subscribe(model,number,**changes)
    token=store.request_confirmation(f"subscriber{number}@example.invalid")
    assert store.confirm(token)=="verified"
    return digest


def test_verification_request_template_and_provider_acceptance_do_not_verify_mailbox(setup):
    # This proves the sensitive rendering/adapter seam, NOT a crash-safe handoff.
    # No production helper connects these operations until outbox approval.
    model,store,transport,_=setup
    digest=subscribe(model)
    token=store.request_confirmation("subscriber1@example.invalid")
    assert b.BrevoAdapter(CONFIG,transport=transport).submit("subscriber1@example.invalid",
        verification_message(token,PAGE))==ACCEPTED
    assert model.rows(verification)[0]["verified_at"] is None
    assert token not in repr(model.records)
    assert store.request_confirmation("subscriber1@example.invalid") is None
    assert store.confirm(token)=="verified"
    assert store.confirm(token)=="already_verified"
    assert not model.rows(deliveries) and not model.rows(attempts)


@pytest.mark.parametrize("platform",["android","ios"])
def test_release_uses_approved_event_and_persisted_attempt_then_never_repeats(setup,platform):
    model,store,transport,dispatcher=setup
    digest=verified(model,store)
    store.accept_event(payload(platform))
    def post(key,body):
        assert model.rows(deliveries)[0]["status"]=="submitting"
        assert model.rows(attempts)[0]["submitting_at"]==model.now
        assert model.rows(attempts)[0]["finished_at"] is None
        data=json.loads(body)
        assert data["to"]==[{"email":"subscriber1@example.invalid"}]
        assert payload(platform)["release_url"] in data["textContent"]
        assert PAGE.replace('/gramanna.html','/manage-notifications.html')+"#unsubscribe=" in data["textContent"]
        return response()
    transport.side_effect=post
    assert dispatcher.process(EVENT)==d.BatchResult("processed",1)
    assert model.rows(deliveries)[0]["status"]=="accepted"
    assert model.rows(deliveries)[0]["provider_message_id"]==ACCEPTED.message_id
    assert model.rows(attempts)[0]["outcome"]=="provider_accepted"
    assert dispatcher.process(EVENT)==d.BatchResult("processed",0)
    assert transport.call_count==1 and KEY not in repr(model.records)


def test_android_and_ios_events_have_independent_durable_audiences(setup):
    model,store,transport,dispatcher=setup
    verified(model,store,1,ios_launch=False)
    verified(model,store,2,android_launch=False)
    ios="00000000-0000-0000-0000-000000000003"
    store.accept_event(payload())
    store.accept_event(payload("ios",event_id=ios))
    assert dispatcher.process(EVENT).processed==1
    assert dispatcher.process(ios).processed==1
    bodies=[json.loads(call.args[1]) for call in transport.call_args_list]
    assert {body["subject"] for body in bodies}=={"GraManna is available for Android","GraManna is available for Apple iOS"}
    assert {body["to"][0]["email"] for body in bodies}=={"subscriber1@example.invalid","subscriber2@example.invalid"}


@pytest.mark.parametrize("ineligible",["unverified","withdrawn","suppressed","preference","late_consent","late_verification","new_lifecycle"])
def test_announcement_audience_excludes_ineligible_lifecycles(setup,ineligible):
    model,store,transport,dispatcher=setup
    digest=subscribe(model)
    if ineligible!="unverified":
        assert store.confirm(store.request_confirmation("subscriber1@example.invalid"))=="verified"
    if ineligible in {"withdrawn","new_lifecycle"}: SubscriptionStore(model).unsubscribe(digest)
    if ineligible=="new_lifecycle": subscribe(model,2,email="subscriber1@example.invalid")
    if ineligible=="suppressed": store.suppress("subscriber1@example.invalid","hard_bounce")
    if ineligible=="preference": model.rows(service.notifications)[0]["android_launch"]=False
    if ineligible=="late_consent": model.rows(service.notifications)[0]["created_at"]+=timedelta(seconds=1)
    if ineligible=="late_verification": model.rows(verification)[0]["verified_at"]+=timedelta(seconds=1)
    store.accept_event(payload())
    assert dispatcher.process(EVENT)==d.BatchResult("processed",0)
    transport.assert_not_called()


@pytest.mark.parametrize("when",["claim","begin_submission"])
@pytest.mark.parametrize("change",["withdrawal","suppression"])
def test_eligibility_changes_immediately_before_dispatch_prevent_post(setup,monkeypatch,when,change):
    model,store,transport,dispatcher=setup
    digest=ready(model,store)
    original=getattr(store,when)
    def intervene(*args, **kwargs):
        if change=="withdrawal": SubscriptionStore(model).unsubscribe(digest)
        else: store.suppress("subscriber1@example.invalid","complaint")
        return original(*args, **kwargs)
    monkeypatch.setattr(store,when,intervene)
    assert dispatcher.process(EVENT)==d.BatchResult("processed",0)
    assert model.rows(deliveries)[0]["status"]=="suppressed"
    transport.assert_not_called()


@pytest.mark.parametrize("outcome,status",[("not_submitted","failed"),("retryable_rejection","failed"),
    ("provider_rejected","rejected"),("submission_unknown","uncertain")])
def test_retry_classification_attempt_limits_and_uncertain_hold(setup,outcome,status):
    model,store,transport,dispatcher=setup
    ready(model,store)
    transport.return_value=b.ProviderOutcome(outcome)
    assert dispatcher.process(EVENT).processed==1
    assert model.rows(deliveries)[0]["status"]==status
    assert dispatcher.process(EVENT).processed==0
    if status=="failed":
        for delay in [60,300]:
            model.elapse(seconds=delay-1)
            assert dispatcher.process(EVENT).processed==0
            model.elapse(seconds=1)
            assert dispatcher.process(EVENT).processed==1
        assert len(model.rows(attempts))==3
        assert model.rows(deliveries)[0]["next_attempt_at"] is None
        expected_calls=3
    else: expected_calls=1
    model.elapse(days=7)
    assert dispatcher.process(EVENT).processed==0 and transport.call_count==expected_calls
    assert model.rows(events)[0]["status"]==("attention" if status=="uncertain" else "completed")


def test_transport_timeout_is_uncertain_without_loop_retry(setup):
    model,store,transport,dispatcher=setup
    ready(model,store)
    transport.side_effect=TimeoutError(KEY)
    assert dispatcher.process(EVENT)==d.BatchResult("processed",1)
    assert model.rows(deliveries)[0]["status"]=="uncertain"
    assert dispatcher.process(EVENT).processed==0
    assert transport.call_count==1


@pytest.mark.parametrize("phase",["recover_event","prepare_event","dispatch_batch","claim","begin_submission"])
@pytest.mark.parametrize("failure",["commit","uncertain"])
def test_persistence_failures_before_post_do_not_send_or_leak(setup,monkeypatch,phase,failure):
    model,store,transport,dispatcher=setup
    ready(model,store)
    original=getattr(store,phase)
    def fail(*args,**kwargs):
        model.failure=failure
        return original(*args,**kwargs)
    monkeypatch.setattr(store,phase,fail)
    result=dispatcher.process(EVENT)
    assert result==d.BatchResult("unavailable") and KEY not in repr(result)
    transport.assert_not_called()
    monkeypatch.setattr(store,phase,original)
    model.failure=None
    if phase=="begin_submission" and failure=="uncertain":
        assert dispatcher.process(EVENT).processed==0
        model.elapse(minutes=5)
        assert dispatcher.process(EVENT).processed==0
        assert model.rows(deliveries)[0]["status"]=="uncertain"
        transport.assert_not_called()


@pytest.mark.parametrize("failure",["commit","uncertain"])
def test_outcome_persistence_failure_cannot_duplicate_accepted_post(setup,monkeypatch,failure):
    model,store,transport,dispatcher=setup
    ready(model,store)
    original=store.record_outcome
    def fail(*args):
        model.failure=failure
        return original(*args)
    monkeypatch.setattr(store,"record_outcome",fail)
    assert dispatcher.process(EVENT)==d.BatchResult("unavailable")
    assert transport.call_count==1
    monkeypatch.setattr(store,"record_outcome",original)
    model.failure=None
    assert dispatcher.process(EVENT).processed==0
    model.elapse(minutes=5)
    assert dispatcher.process(EVENT).processed==0
    assert model.rows(deliveries)[0]["status"]==("uncertain" if failure=="commit" else "accepted")
    assert transport.call_count==1


def test_failed_outcome_ownership_and_unexpected_adapter_exception_are_safe(setup,monkeypatch):
    model,store,transport,dispatcher=setup
    ready(model,store)
    monkeypatch.setattr(dispatcher.adapter,"submit",Mock(side_effect=RuntimeError(KEY)))
    monkeypatch.setattr(store,"record_outcome",Mock(return_value=False))
    assert dispatcher.process(EVENT)==d.BatchResult("unavailable")
    assert model.rows(deliveries)[0]["status"]=="submitting"
    assert store.record_outcome.call_args.args[3]=="submission_unknown"


def test_concurrent_workers_use_one_durable_claim(setup):
    model,store,transport,dispatcher=setup
    ready(model,store)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:dispatcher.process(EVENT),range(8)))
    assert sum(result.processed for result in results)==1
    assert transport.call_count==1 and len(model.rows(attempts))==1


def test_batches_are_bounded_ordered_and_resume_without_second_admin_action(setup):
    model,store,transport,dispatcher=setup
    for number in range(1,25): verified(model,store,number)
    store.accept_event(payload())
    store.prepare_event(EVENT)
    event,selected=store.dispatch_batch(EVENT,3)
    expected=sorted(row["subscription"] for row in model.rows(deliveries))
    assert selected==expected[:3]
    assert len(store.dispatch_batch(EVENT,20)[1])==20
    assert dispatcher.process(EVENT,limit=3).processed==3
    assert dispatcher.process(EVENT).processed==20
    assert dispatcher.process(EVENT).processed==1
    assert dispatcher.process(EVENT).processed==0
    assert transport.call_count==24
    query=next(sql for sql in model.statements if "ORDER BY" in sql)
    assert "LIMIT" in query and "notification_deliveries.next_attempt_at <=" in query


@pytest.mark.parametrize("limit",[None,True,0,-1,21,1.5,"20"])
def test_bad_batch_limits_rejected_before_io(setup,limit):
    model,store,transport,dispatcher=setup
    with pytest.raises(ValueError): dispatcher.process(EVENT,limit=limit)
    with pytest.raises(ValueError): store.dispatch_batch(EVENT,limit=limit)
    assert not model.statements
    transport.assert_not_called()


def test_unknown_event_and_environment_mismatch_fail_closed(setup):
    model,store,transport,dispatcher=setup
    assert store.dispatch_batch(EVENT)==(None,[])
    assert dispatcher.process(EVENT)==d.BatchResult("unavailable")
    for config in [None,b.BrevoConfig("development",KEY)]:
        with pytest.raises(b.BrevoConfigurationError): d.ReleaseDispatcher(store,config,PAGE,transport=transport)
    transport.assert_not_called()


def test_previously_consumed_claim_never_posts(setup,monkeypatch):
    model,store,transport,dispatcher=setup
    ready(model,store)
    original=store.claim
    def consume(*args):
        claim=original(*args)
        assert store.begin_submission(*args,claim)
        return claim
    monkeypatch.setattr(store,"claim",consume)
    assert dispatcher.process(EVENT).processed==0
    transport.assert_not_called()



@pytest.mark.parametrize("action", ["correct", "withdraw"])
def test_official_change_between_candidate_selection_and_submission_is_authoritative(setup, monkeypatch, action):
    from test_notification_delivery import changed_release
    from oaf_website.release_approval_schema import revisions
    model,store,transport,dispatcher=setup
    store.releases_enabled=True
    ready(model,store)
    original=store.begin_submission
    def intervene(*args,**kwargs):
        model.elapse(seconds=1)
        values=changed_release(model)
        values.update(action=action,release_id="org.oaf.corrected",release_url="https://play.google.com/store/apps/details?id=org.oaf.corrected")
        store.accept_release_change(values)
        return original(*args,**kwargs)
    monkeypatch.setattr(store,"begin_submission",intervene)
    result=dispatcher.process(EVENT)
    assert result.processed == int(action=="correct")
    assert transport.call_count == int(action=="correct")
    if action=="correct":
        assert "id=org.oaf.corrected" in json.loads(transport.call_args.args[1])["textContent"]
    assert len(model.rows(revisions))==1


def test_release_recipient_scope_prevents_claim_and_submission_for_other_mailbox(setup):
    model,store,transport,dispatcher=setup
    first=verified(model,store)
    second=verified(model,store,2)
    store.accept_event(payload())
    store.prepare_event(EVENT)
    claim=store.claim(EVENT,second)
    store.recipient_scope=b.TestingRecipientScope("testing","subscriber1@example.invalid")
    with pytest.raises(b.BrevoConfigurationError): store.begin_submission(EVENT,second,claim)
    model.elapse(minutes=6)
    store.recover_event(EVENT)
    model.elapse(seconds=60)
    with pytest.raises(b.BrevoConfigurationError): store.claim(EVENT,second)
    scoped=d.ReleaseDispatcher(store,CONFIG,PAGE,transport=transport)
    assert scoped.process(EVENT).processed==1
    assert transport.call_count==1
    assert next(r for r in model.rows(deliveries) if r["subscription"]==first)["status"]=="accepted"
