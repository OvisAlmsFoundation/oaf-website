"""Connected synthetic failure injection through real OAF boundaries and evidence sink."""
import migration_offline as isolation
isolation.require_early_registration()

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from oaf_website import database_config as config
from oaf_website import notification_dispatch as diagnostic
from oaf_website import state_requests as web
from oaf_website import brevo
from test_state_requests import ModelEngine, SECRET, ORIGIN
from test_notifications import choices, post
from test_public_confirmation import build, token, CONFIRM
from test_notification_delivery import Model

CANARY = 'PRIVATE-CREDENTIAL-BODY-subscriber@example.invalid'


@pytest.mark.parametrize('factory', ['webhook', 'database', 'delivery', 'summary', 'management', 'subscriptions'])
def test_invalid_store_configuration_precedes_external_access(sink, factory):
    from oaf_website.brevo_unsubscribe import BrevoWebhookConfig
    from oaf_website.database_config import DatabaseConfig
    from oaf_website.notification_delivery import NotificationDeliveryStore
    from oaf_website.notification_management import ManagementCapabilities
    from oaf_website.interest_reporting import InterestSummaryStore
    from oaf_website.notifications import SubscriptionStore
    calls = {
        'webhook': lambda: BrevoWebhookConfig('production', 'invalid'),
        'database': lambda: DatabaseConfig('production', None),
        'delivery': lambda: NotificationDeliveryStore(Model(), SECRET, 'testing', management_enabled=1),
        'summary': lambda: InterestSummaryStore(Model(), 'unknown'),
        'management': lambda: ManagementCapabilities(SECRET, 'production'),
        'subscriptions': lambda: SubscriptionStore(Model(), management_store=SimpleNamespace(engine=Model())),
    }
    with pytest.raises(ValueError):
        calls[factory]()


@pytest.mark.parametrize('renderer', ['message', 'footer', 'withdrawal'])
def test_management_templates_reject_malformed_capabilities(sink, renderer):
    from oaf_website import notification_messages as messages
    call = (lambda: messages.management_message(CANARY, ORIGIN + '/confirm-email.html')) if renderer == 'message' else (
        lambda: messages.management_footer(None, ORIGIN + '/confirm-email.html', token=CANARY)) if renderer == 'footer' else (
        lambda: messages.management_footer(None, ORIGIN + '/confirm-email.html', unsubscribe_token=CANARY))
    with pytest.raises(ValueError) as caught:
        call()
    assert CANARY not in str(caught.value)


@pytest.mark.parametrize('origin', ['ftp://example.invalid', 'https://user:private@example.invalid', 'https://[invalid', 'https://example.invalid:wrong'])
def test_invalid_request_origin_is_unusable(origin):
    assert web._origin(origin) is None


@pytest.mark.parametrize('field,value', [
    ('stage', 'private'), ('side_effects', 'private'), ('context', 'private'),
    ('provider_outcome', 'private'),
])
def test_failure_builder_rejects_unknown_server_codes(field, value):
    values = dict(stage='processor', operation='arguments')
    values[field] = value
    with pytest.raises(ValueError):
        diagnostic.safe_failure(**values)


@pytest.mark.parametrize('field,value', [
    ('timestamp_utc', '2026-10-25T00:00:00+01:00'), ('sqlstate', 'private'),
    ('hresult', 123), ('exit_code', True), ('evidence_ref', 'private'),
    ('dependent_not_run', ['private']), ('stage', 'private'),
])
def test_child_failure_rejects_untrusted_metadata(field, value):
    record = diagnostic.safe_failure('processor', 'arguments')
    record[field] = value
    with pytest.raises(ValueError):
        diagnostic.validate_failure(record)


@pytest.mark.parametrize('receipt', [None, {}, {'environment': 'production', 'receipt_digest': 'a'*64}])
def test_webhook_success_requires_valid_receipt(receipt):
    logger = Mock()
    with pytest.raises(ValueError):
        diagnostic.log_webhook_processed(logger, receipt, acknowledgement=False)
    logger.warning.assert_not_called()


def test_diagnostic_request_transaction_without_first_failure_is_a_noop():
    from flask import Flask, g
    app = Flask(__name__)
    with app.test_request_context('/'):
        diagnostic.request_transaction_outcome('database_committed')
        assert not hasattr(g, 'oaf_first_failure')


def test_diagnostic_evidence_redirect_and_both_sink_failure(sink, monkeypatch):
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == sink)
    with pytest.raises(OSError):
        diagnostic._append_failure({'operation': 'arguments'})
    monkeypatch.setattr(diagnostic.sys, 'stderr', SimpleNamespace(write=Mock(side_effect=OSError(CANARY))))
    detail = {'first_failure': diagnostic.safe_failure('processor', 'arguments')}
    diagnostic._emit(detail)
    assert detail['evidence_failure']['exception_class'] == 'OSError'
    assert not sink.exists()


@pytest.mark.parametrize('status', [True, 99, 600])
def test_notification_log_rejects_invalid_http_status(status):
    logger = Mock()
    with pytest.raises(ValueError):
        diagnostic.log_notification_failure(logger, 'signup_persistence', RuntimeError(CANARY), http_status=status)
    logger.warning.assert_not_called()


def test_unknown_webhook_database_boundary_never_claims_mutation(sink):
    first = diagnostic.safe_failure('notifications', 'database_begin')
    error = RuntimeError(CANARY)
    error.notification_failure = first
    diagnostic.log_notification_failure(Mock(), 'brevo_unsubscribe', error)
    assert first['dependent_not_run'] == ['event_correlation', 'database_transaction', 'database_mutation', 'provider_submission']


@pytest.mark.parametrize('option', ['management_enabled', 'brevo_webhook_config'])
def test_application_activation_rejects_before_database(sink, monkeypatch, option):
    from oaf_website.brevo_unsubscribe import BrevoWebhookConfig
    loader = Mock(side_effect=AssertionError('database must not be reached'))
    monkeypatch.setattr(web, 'load_testing_database_config', loader)
    values = {option: 1 if option == 'management_enabled' else BrevoWebhookConfig('testing', 's'*32)}
    with pytest.raises(ValueError):
        web.create_app(expected_profile='testing', recognition_secret=SECRET, public_origin=ORIGIN, **values)
    loader.assert_not_called()


@pytest.mark.parametrize('module', ['confirmation_processor', 'confirmation_schedule', 'local_development',
    'local_testing_https', 'migration_authority', 'webhook_guard'])
def test_module_cli_help_exits_without_runtime(sink, monkeypatch, capsys, module):
    import runpy
    monkeypatch.setattr(__import__('sys'), 'argv', [module, '--help'])
    monkeypatch.delitem(__import__('sys').modules, 'oaf_website.'+module, raising=False)
    with pytest.raises(SystemExit) as caught:
        runpy.run_module('oaf_website.'+module, run_name='__main__')
    assert caught.value.code == 0
    assert 'usage:' in capsys.readouterr().out.lower()


def test_application_build_failure_disposes_engine_and_preserves_origin(sink, monkeypatch):
    from sqlalchemy.engine import URL
    selected = config.DatabaseConfig('testing', URL.create('postgresql+psycopg',
        username='oaf_website_test_app', password='synthetic', host='127.0.0.1', port=5432, database='oaf_website_test'))
    engine = SimpleNamespace(dispose=Mock(side_effect=OSError(CANARY)))
    monkeypatch.setattr(web, 'load_testing_database_config', lambda: selected)
    monkeypatch.setattr(web, 'create_engine', lambda *a, **kw: engine)
    monkeypatch.setattr(web.event, 'listen', Mock(side_effect=RuntimeError(CANARY)))
    with pytest.raises(RuntimeError):
        web.create_app(expected_profile='testing', recognition_secret=SECRET, public_origin=ORIGIN)
    engine.dispose.assert_called_once()
    retained = records(sink)
    assert retained[-1]['first_failure'] == retained[-2]['first_failure']
    assert retained[-1]['cleanup_failure']['exception_class']=='OSError'


def test_contact_production_profile_is_rejected_before_metadata(sink):
    from oaf_website.contact_mail import load_contact_config, DeliveryUnavailable
    with pytest.raises(DeliveryUnavailable):
        load_contact_config(expected_profile='production', environ={'OAF_ENV':'production'})


def test_startup_diagnostics_before_flask_import(sink,monkeypatch):
    monkeypatch.delitem(diagnostic.sys.modules,'flask')
    diagnostic._request_record(diagnostic.safe_failure('startup','arguments'))
    diagnostic.request_transaction_outcome('database_committed')
    diagnostic.log_notification_failure(Mock(),'signup_persistence',RuntimeError(CANARY))
    assert records(sink)[0]['first_failure']['exception_class']=='RuntimeError'


@pytest.mark.parametrize('names',[set(),[]])
def test_field_diagnostics_require_nonempty_set(names):
    with pytest.raises(ValueError):
        diagnostic.safe_failure('notifications','brevo_unsubscribe',context='webhook_event',
            predicate='webhook_allowed_fields',field_names=names)


def test_field_diagnostics_reject_unapproved_context():
    with pytest.raises(ValueError):
        diagnostic.safe_failure('processor','arguments',field_names={'field'})


def test_field_validation_rejects_malformed_child_shape():
    record=diagnostic.safe_failure('processor','arguments')
    record['field_validation']={}
    with pytest.raises(ValueError):diagnostic.validate_failure(record)


def test_field_validation_rejects_inconsistent_counts():
    record=diagnostic.safe_failure('notifications','brevo_unsubscribe',context='webhook_event',
        predicate='webhook_allowed_fields',field_names={'unknown_field'})
    record['field_validation']['offending_field_count']=2
    with pytest.raises(ValueError):diagnostic.validate_failure(record)


def test_startup_condition_inside_request_is_classified_as_request(sink):
    from flask import Flask
    app=Flask(__name__)
    with app.test_request_context('/'):
        error=diagnostic.diagnostic_error(ValueError(),'arguments','operation_failed',stage='startup')
        assert error.notification_failure['stage']=='request'
    assert not sink.exists()


def test_webhook_correlation_rejection_marks_mutation_not_reached():
    failure=diagnostic.safe_failure('notifications','brevo_unsubscribe',context='webhook_correlation')
    assert failure['dependent_not_run']==['database_mutation','provider_submission']
    assert diagnostic.safe_failure('notifications','brevo_unsubscribe')['dependent_not_run']==[]


@pytest.mark.parametrize('record',[None,{},dict(untrusted='private')])
def test_child_diagnostic_requires_complete_registered_shape(record):
    with pytest.raises(ValueError):diagnostic.validate_failure(record)


def test_dangling_integration_symlink_is_rejected_before_metadata_read(sink,monkeypatch,tmp_path):
    from oaf_website import local_development as development
    path=tmp_path/'integrations.toml'
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda p:p==path or original(p))
    with pytest.raises(development.IntegrationConfigurationError) as caught:
        development.load_development_integration_config(local_config_path=path,environ={'OAF_ENV':'development'})
    assert caught.value.notification_failure['predicate']=='integration_location'
    assert not path.exists()


def test_secondary_request_failure_keeps_original_record(sink):
    from flask import Flask,g
    app=Flask(__name__)
    first=diagnostic.safe_failure('request','http_request')
    with app.test_request_context('/'):
        g.oaf_first_failure=first
        g.oaf_failure_emitted=True
        diagnostic.log_notification_failure(Mock(),'signup_persistence',RuntimeError(CANARY))
    record=records(sink)[0]
    assert record['first_failure']==first
    assert record['secondary_failure']['exception_class']=='RuntimeError'


def test_protected_key_and_integration_redirects_are_rejected_before_reads(sink,monkeypatch,tmp_path):
    import stat
    from oaf_website import local_development as development
    path=tmp_path/'integrations.toml'
    monkeypatch.setattr(development,'ROOT',tmp_path)
    original=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda p:SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        if p==tmp_path else original(p))
    with pytest.raises(development.IntegrationConfigurationError):
        development.load_development_integration_config(local_config_path=path,environ={'OAF_ENV':'development'})
    monkeypatch.setenv('OAF_ENV','development')
    with pytest.raises(RuntimeError):development.development_app()


def test_development_default_credential_backend_is_used_with_exact_targets(sink,monkeypatch,tmp_path):
    from oaf_website import local_development as development
    path=tmp_path/'integrations.toml'
    path.write_text('[development]\nclient_id="synthetic"\n')
    loader=Mock(side_effect=['a'*64,'b'*64])
    monkeypatch.setattr(development,'_windows_password',loader)
    result=development.load_development_integration_config(local_config_path=path,environ={'OAF_ENV':'development'})
    assert result.environment=='development' and loader.call_count==2
    assert all(call.kwargs=={'exact_target':True} for call in loader.call_args_list)


@pytest.fixture
def sink(tmp_path, monkeypatch):
    path = tmp_path / 'instance/failures.jsonl'
    monkeypatch.setattr(diagnostic, 'EVIDENCE_PATH', path)
    yield path
    if path.exists():
        # Bounded synthetic examples for the one consolidated implementation report.
        target = Path(__file__).resolve().parents[1] / 'instance/validation-samples.jsonl'
        target.parent.mkdir(exist_ok=True)
        with target.open('a', encoding='utf-8') as stream:
            stream.write(path.read_text(encoding='utf-8'))


def records(sink):
    result = [json.loads(line) for line in sink.read_text(encoding='utf-8').splitlines()]
    assert result
    for record in result:
        first = diagnostic.validate_failure(record['first_failure'])
        assert datetime.fromisoformat(first['timestamp_utc']).utcoffset().total_seconds() == 0
        assert len(first['evidence_ref']) == 32
        assert CANARY not in json.dumps(record)
    return result


@pytest.mark.parametrize('environment,predicate', [({}, 'environment_profile_required'),
    ({'OAF_ENV':'development'}, 'environment_profile_match'),
    ({'OAF_ENV':'testing','PGPASSWORD':CANARY}, 'environment_override_prohibited')])
def test_testing_bootstrap_predicate_before_flask_and_credentials(sink, environment, predicate):
    provider = Mock(side_effect=AssertionError('credential dependency must not run'))
    with pytest.raises(config.DatabaseConfigurationError) as caught:
        config.load_testing_database_config(environ=environment, credential_loader=provider)
    provider.assert_not_called()
    record = records(sink)[0]['first_failure']
    assert record == caught.value.notification_failure
    assert record['predicate'] == predicate and record['stage'] == 'startup'
    assert record['side_effects'] == 'none'
    assert record['dependent_not_run'] == ['application_initialization','database_mutation','provider_submission']
    assert record['expected'] == predicate + '_satisfied' and record['observed'] == predicate + '_failed'


def test_testing_unreadable_configuration_preserves_native_first(sink, tmp_path):
    provider = Mock()
    with pytest.raises(config.DatabaseConfigurationError) as caught:
        config.load_testing_database_config(environ={'OAF_ENV':'testing'},
            local_config_path=tmp_path/'absent.toml', credential_loader=provider)
    provider.assert_not_called()
    first=records(sink)[0]['first_failure']
    assert first['predicate']=='configuration_readable_toml'
    assert first['exception_class']=='FileNotFoundError'
    assert caught.value.notification_failure == first


@pytest.mark.parametrize('phase,operation,effects', [('connect','database_begin','none'),
    ('insert','transaction_body','database_rolled_back'),('commit','transaction_commit','database_commit_uncertain'),
    ('uncertain','transaction_commit','database_commit_uncertain')])
def test_http_store_transaction_certainty_and_public_privacy(sink, phase, operation, effects):
    model=ModelEngine(); model.failure=phase
    app=web._build_app(web.RequestStore(model),web.BrowserRecognition(SECRET),ORIGIN)
    client=app.test_client(); csrf=client.get('/api/state-requests/session',base_url=ORIGIN).json['csrf_token']
    response=client.post('/api/state-requests',base_url=ORIGIN,json={'state':'CA'},headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
    assert response.status_code==503
    first=records(sink)[0]['first_failure']
    assert first['operation']==operation and first['side_effects']==effects
    assert first['predicate'] not in response.text and 'synthetic-private' not in response.text
    assert len(model.records)==int(phase=='uncertain')


def test_csrf_rejected_at_predicate_before_persistence(sink):
    store=Mock();app=web._build_app(store,web.BrowserRecognition(SECRET),ORIGIN)
    response=app.test_client().post('/api/state-requests',base_url=ORIGIN,json={'state':'CA'},headers={'Origin':ORIGIN})
    assert response.status_code==403;store.submit.assert_not_called()
    first=records(sink)[0]['first_failure']
    assert first['predicate']=='csrf_browser_missing'
    assert first['dependent_not_run']==['database_mutation','provider_submission']
    assert 'csrf_browser_missing' not in response.text


def test_signup_precise_consent_rejection_without_write(sink):
    model=Model(); delivery,store,app,client,csrf=build(model)
    response=post(client,csrf,choices(consent=False))
    assert response.status_code==400 and all(not rows for rows in model.records.values())
    first=records(sink)[0]['first_failure']
    assert first['predicate']=='signup_consent'
    assert first['exception_class']=='ValueError'


def test_confirmation_expiry_at_store_with_committed_read_transaction(sink):
    model=Model();delivery,store,app,client,csrf=build(model)
    assert post(client,csrf,choices()).status_code==200
    capability=token(model,delivery);model.elapse(days=2)
    response=post(client,csrf,{'token':capability},CONFIRM)
    assert response.status_code==400
    first=records(sink)[-1]['first_failure']
    assert first['predicate']=='confirmation_not_expired'
    assert first['side_effects']=='database_committed'
    assert capability not in sink.read_text() and capability not in response.text


def test_secondary_rollback_and_logger_failure_do_not_replace_origin(sink):
    class OperationalError(Exception):pass
    original=OperationalError(CANARY);original.sqlstate='23505';original.hresult=-2147467259;original.returncode=7
    @contextmanager
    def begin():
        try:yield object()
        except OperationalError:raise RuntimeError(CANARY) from None
    with pytest.raises(RuntimeError) as caught:
        with diagnostic.diagnostic_transaction(SimpleNamespace(begin=begin)):
            raise diagnostic.diagnostic_error(original,'transaction_body','signup_consent')
    logger=Mock();logger.warning.side_effect=OSError(CANARY)
    diagnostic.log_notification_failure(logger,'signup_persistence',caught.value,http_status=503)
    result=records(sink)[0];first=result['first_failure']
    assert first['predicate']=='signup_consent' and first['exception_class']=='OperationalError'
    assert first['sqlstate']=='23505' and first['hresult']=='0x80004005' and first['exit_code']==7
    assert first['side_effects']=='database_rollback_uncertain'
    assert result['rollback_failure']['exception_class']=='RuntimeError'
    assert result['logging_failure']['exception_class']=='OSError'
    assert first['evidence_ref']==original.notification_failure['evidence_ref']


def test_secondary_evidence_failure_falls_back_without_recursion(sink, monkeypatch, capsys):
    def unavailable(_):raise OSError(CANARY)
    monkeypatch.setattr(diagnostic,'_append_failure',unavailable)
    original=diagnostic.diagnostic_error(ValueError(CANARY),'configuration','environment_profile_required')
    first=diagnostic.report_failure('configuration',original)
    output=capsys.readouterr().err
    detail=json.loads(output.split(': ',1)[1])
    assert detail['first_failure']==first
    assert detail['evidence_failure']['operation']=='terminal_publication'
    assert CANARY not in output


def test_provider_uncertainty_keeps_first_and_forbids_blind_retry(sink):
    from test_brevo import CONFIG
    # Real adapter, fixed message, and exactly one synthetic failing transport invocation.
    transport=Mock(side_effect=TimeoutError(CANARY))
    result=brevo.BrevoAdapter(CONFIG,transport=transport).submit('synthetic@example.invalid',
        SimpleNamespace(subject='synthetic',text='synthetic',html='<p>synthetic</p>'))
    transport.assert_called_once()
    assert result.outcome=='submission_unknown'
    first=records(sink)[0]['first_failure']
    assert result.first_failure==first and first['predicate']=='provider_transport_exception'
    assert first['side_effects']=='submission_possible' and first['dependent_not_run']==['automatic_retry']


def test_uncaught_http_exception_does_not_log_private_path_or_traceback(sink):
    app=web._build_app(None,web.BrowserRecognition(SECRET),ORIGIN)
    @app.get('/synthetic-failure')
    def broken():raise RuntimeError(CANARY)
    response=app.test_client().get('/synthetic-failure?private='+CANARY,base_url=ORIGIN)
    assert response.status_code==500 and CANARY not in response.text
    assert records(sink)[0]['first_failure']['exception_class']=='RuntimeError'


def test_provider_timeout_and_close_failure_keep_same_origin(sink, monkeypatch):
    from test_brevo import Connection, KEY
    connection=Connection()
    connection.getresponse=Mock(side_effect=TimeoutError(CANARY))
    connection.close=Mock(side_effect=OSError(CANARY))
    monkeypatch.setattr(brevo,'HTTPSConnection',Mock(return_value=connection))
    outcome=brevo.BrevoHTTPS()(KEY,b'{}')
    result=records(sink)
    assert outcome.outcome=='submission_unknown'
    assert result[-1]['first_failure']==result[0]['first_failure']==outcome.first_failure
    assert result[-1]['first_failure']['predicate']=='provider_response_unacknowledged'
    assert result[-1]['cleanup_failure']['predicate']=='provider_close'
    assert result[-1]['cleanup_failure']['exception_class']=='OSError'
    connection.getresponse.assert_called_once();connection.close.assert_called_once()


def test_outbox_lock_failure_survives_failed_rollback(sink):
    from oaf_website.confirmation_outbox import ConfirmationOutboxStore
    class OperationalError(Exception):pass
    first=OperationalError(CANARY);first.sqlstate='55P03'
    @contextmanager
    def begin():
        try:yield SimpleNamespace(execute=Mock(side_effect=first))
        except OperationalError:raise RuntimeError(CANARY) from None
    store=ConfirmationOutboxStore(SimpleNamespace(begin=begin),SECRET,'testing')
    with pytest.raises(RuntimeError) as caught:
        with store._transaction():
            pytest.fail('failed advisory lock must not yield to dependent operations')
    diagnostic.log_notification_failure(Mock(),'dispatcher',caught.value)
    failure=records(sink)[0]['first_failure']
    assert failure['operation']=='advisory_lock' and failure['exception_class']=='OperationalError'
    assert failure['sqlstate']=='55P03' and failure['side_effects']=='database_rollback_uncertain'
    assert store.first_failure==failure


def test_before_application_credential_native_error_is_retained(sink, tmp_path):
    source=Path(__file__).resolve().parents[1]/'config/database.example.toml'
    settings=tmp_path/'database.toml';settings.write_bytes(source.read_bytes())
    native=OSError(CANARY);native.hresult=-2147024891
    provider=Mock(side_effect=native)
    with pytest.raises(config.DatabaseConfigurationError) as caught:
        config.load_testing_database_config(environ={'OAF_ENV':'testing'},local_config_path=settings,credential_loader=provider)
    failure=records(sink)[0]['first_failure']
    assert failure['predicate']=='credential_readable' and failure['hresult']=='0x80070005'
    assert failure['exception_class']=='OSError' and caught.value.notification_failure==failure
    provider.assert_called_once()


def test_report_cleanup_failure_retains_origin_and_native_code(sink):
    original=diagnostic.report_failure('configuration',ValueError(CANARY),predicate='environment_profile_required')
    cleanup=OSError(CANARY);cleanup.returncode=9
    result=diagnostic.report_failure('dispose',cleanup,stage='processor',first_failure=original)
    evidence=records(sink)[-1]
    assert result==original==evidence['first_failure']
    assert evidence['cleanup_failure']['exit_code']==9


@pytest.mark.parametrize('stage,operation,effects,context,expected', [
    ('outbox','advisory_lock','none','claim',['provider_submission']),
    ('outbox','transaction_commit','database_commit_uncertain','outcome',['automatic_retry']),
    ('processor','protected_key','none',None,['provider_submission']),
    ('outbox','database_begin','none','outcome',[]),
])
def test_dependent_actions_reflect_reached_worker_boundary(stage,operation,effects,context,expected):
    first=diagnostic.safe_failure(stage,operation,side_effects=effects,context=context)
    assert diagnostic.validate_failure(first)['dependent_not_run']==expected


def test_protected_integration_key_separation_has_its_own_predicate(sink):
    from oaf_website.integrations import IntegrationConfig, IntegrationConfigurationError
    with pytest.raises(IntegrationConfigurationError) as caught:
        IntegrationConfig('testing','synthetic','1'*64,'1'*64)
    first=records(sink)[0]['first_failure']
    assert first['predicate']=='integration_credentials_distinct'
    assert first['stage']=='startup' and first['side_effects']=='none'
    assert caught.value.notification_failure==first


@pytest.mark.parametrize('entry,predicate',[('development','development_arguments'),('guard','guard_arguments')])
def test_early_cli_failure_never_echoes_unknown_arguments(sink,monkeypatch,capsys,entry,predicate):
    from oaf_website import local_development,webhook_guard
    if entry=='development':
        assert local_development.main(['--unknown',CANARY])==2
    else:
        monkeypatch.setattr('sys.argv',['guard','--unknown',CANARY])
        assert webhook_guard.main()==2
    output=capsys.readouterr()
    assert CANARY not in output.out+output.err
    first=records(sink)[0]['first_failure']
    assert first['predicate']==predicate and first['side_effects']=='none'


def test_json_rejection_retains_parser_exception_class(sink):
    app=web._build_app(None,web.BrowserRecognition(SECRET),ORIGIN)
    client=app.test_client();csrf=client.get('/api/state-requests/session',base_url=ORIGIN).json['csrf_token']
    response=client.post('/api/state-requests',base_url=ORIGIN,data='{',content_type='application/json',
        headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
    assert response.status_code==400
    first=records(sink)[0]['first_failure']
    assert first['predicate']=='request_json_decode' and first['exception_class']=='BadRequest'
