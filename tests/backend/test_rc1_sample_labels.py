from datetime import datetime, timezone
from dataclasses import asdict
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pandas as pd

from tarsier.api.app import create_app
from tarsier.quality.engine import CheckResult
from tarsier.health import quality_is_sample
from tarsier.alerts.engine import AlertContext, evaluate_rule
from tarsier.alerts.evaluate import SampleValues
from tarsier.storage import connections, item_cache, quality_cache
from tarsier.connectors.base import DataItem, ItemMetadata


def test_old_clean_sample_is_neutral_and_retains_provenance():
    check = CheckResult('validity', 'good', is_sample=True)
    assert check.status == 'sampled'
    assert check.message == 'none found in sample, not a full check'
    assert quality_is_sample({'validity': check})
    assert not quality_is_sample({'validity': CheckResult('validity', 'good')})


def test_sample_health_provenance_reaches_overview_and_detail(tmp_path, monkeypatch):
    monkeypatch.setenv('TARSIER_HOME', str(tmp_path))
    cid = connections.create_connection('fixture', 'files', {}).id
    item_cache.upsert_item(cid, DataItem('', 't', 'tabular'), ItemMetadata(row_count=100))
    quality_cache.save_check(cid, '', 't', CheckResult('custom_rules', 'good', is_sample=True))
    client = TestClient(create_app())
    body = client.get(f'/api/connections/{cid}/overview').json()
    assert body['health_is_sample'] and body['layers'][0]['health_is_sample']
    assert client.get(f'/api/connections/{cid}/item', params={'name': 't'}).json()['health_is_sample']


def context(**kwargs):
    return AlertContext(items=[], previous_items=[], events=[], quality_scores={},
                        previous_quality={}, now=datetime.now(timezone.utc), **kwargs)


def test_quality_alert_labels_previous_or_current_samples():
    ctx = context(previous_quality_samples={'s.t': True})
    ctx.quality_scores = {'s.t': 20}; ctx.previous_quality = {'s.t': 90}
    result = evaluate_rule('quality_score_drop', {}, ctx)[0]
    assert result.details['is_sample'] and 'sample-based' in result.message


def test_bounded_value_alert_labels_sample_but_not_recorded_edit():
    values = SampleValues({'value': [-1]}); values.is_sample = True
    ctx = context(sample_values=values)
    matches = evaluate_rule('banned_value', {'field': 'value', 'operator': 'lt', 'value': '0'}, ctx)
    assert 'sample-based' in matches[0].message
    ctx.sample_values = {};ctx.events = [{'id': 'event', 'name': 't', 'schema': 's', 'after': {'value': -1}}]
    matches = evaluate_rule('banned_value', {'field': 'value', 'operator': 'lt', 'value': '0'}, ctx)
    assert 'recorded edit' in matches[0].message and 'sample-based' not in matches[0].message


def test_sample_first_is_not_an_http_mode(tmp_path, monkeypatch):
    monkeypatch.setenv('TARSIER_HOME', str(tmp_path))
    cid = connections.create_connection('fixture', 'files', {}).id
    from tarsier import checks
    calls=[];monkeypatch.setattr(checks, 'start', lambda *a, **kw: calls.append(kw) or {})
    client=TestClient(create_app())
    assert client.post(f'/api/connections/{cid}/checks?mode=sample_first').status_code == 422
    assert not calls
    assert client.post(f'/api/connections/{cid}/checks').status_code == 202
    assert calls == [{'mode': 'full'}]


def test_automation_delivery_and_trace_label_sample_context(monkeypatch):
    from tarsier.automation.engine import RunContext
    from tarsier.automation import evaluate
    ctx=RunContext('c', [], [], [], [], {}, {}, datetime.now(timezone.utc), None, False, is_sample=True)
    sent=[];monkeypatch.setattr(evaluate, 'send_email', lambda *args: sent.append(args))
    result=evaluate._handle({'kind':'email','config':{'message':'Quality 80%'}}, ctx)
    assert 'sample-based' in sent[0][2] and 'sample-based' in result['message']
