from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import text
from tarsier.storage import alerts, automations, change_log, connections
from tarsier.storage.db import get_engine
from tarsier.alerts import evaluate as alert_eval
from tarsier.automation import evaluate as auto_eval


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return connections.create_connection("Synthetic", "files", {}).id

def _old_rows(count):
    stamp = datetime.now(timezone.utc) - timedelta(days=30)
    return [{'occurred_at': stamp, 'db_user': 'editor', 'action': 'update',
             'schema': 's', 'name': 't', 'source': 'trigger', 'source_log_id': n}
            for n in range(1, count + 1)]


def _new_row(source_id):
    return {'occurred_at': datetime.now(timezone.utc), 'db_user': 'editor',
            'action': 'update', 'schema': 's', 'name': 't',
            'source': 'trigger', 'source_log_id': source_id}


def test_new_alert_checkpoint_skips_large_history_and_old_log_reimport(source, monkeypatch):
    change_log.insert_events(source, _old_rows(10_000), {})
    rule = alerts.create_rule(source, {'kind': 'specific_user', 'config': {'user': 'editor', 'notify': 'log'}})
    assert rule['event_checkpoint'] == 10_000
    assert rule['source_log_checkpoint'] == 10_000
    attempts = []
    monkeypatch.setattr(alert_eval, '_deliver', lambda *args: (attempts.append(args[2]['id']) or ('logged', 'test')))
    assert alert_eval.evaluate_connection(source) == []
    assert attempts == []
    change_log.insert_events(source, [_new_row(10_001)], {})
    assert len(alert_eval.evaluate_connection(source)) == 1
    assert alert_eval.evaluate_connection(source) == []
    with get_engine().begin() as conn:
        conn.execute(text('DELETE FROM change_events WHERE connection_id=:cid AND source_log_id=1'), {'cid': source})
    change_log.insert_events(source, [_old_rows(1)[0]], {})
    assert alert_eval.evaluate_connection(source) == []
    assert len(attempts) == 1
    assert len(alerts.list_fires(source)) == 1


def test_new_automation_checkpoint_skips_large_history_and_old_log_reimport(source, monkeypatch):
    change_log.insert_events(source, _old_rows(3_000), {})
    graph = {'nodes': [
        {'id': 't', 'role': 'trigger', 'kind': 'any_change', 'config': {}},
        {'id': 'a', 'role': 'action', 'kind': 'webhook', 'config': {}},
    ], 'edges': [{'from': 't', 'to': 'a'}]}
    auto = automations.create_automation(source, {'title': 'After creation', 'graph': graph})
    assert auto['event_checkpoint'] == 3_000
    assert auto['source_log_checkpoint'] == 3_000
    attempts = []
    monkeypatch.setattr(auto_eval, 'send_webhook', lambda *args: attempts.append(1))
    assert auto_eval.evaluate_connection(source) == []
    assert attempts == []
    change_log.insert_events(source, [_new_row(3_001)], {})
    assert len(auto_eval.evaluate_connection(source)) == 1
    assert auto_eval.evaluate_connection(source) == []
    with get_engine().begin() as conn:
        conn.execute(text('DELETE FROM change_events WHERE connection_id=:cid AND source_log_id=1'), {'cid': source})
    change_log.insert_events(source, [_old_rows(1)[0]], {})
    assert auto_eval.evaluate_connection(source) == []
    assert attempts == [1]
    assert len(automations.list_runs(source)) == 1


def test_crash_after_alert_claim_does_not_repeat_delivery(source, monkeypatch):
    rule = alerts.create_rule(source, {'kind': 'specific_user', 'config': {'user': 'editor', 'notify': 'log'}})
    change_log.insert_events(source, [_new_row(1)], {})
    attempts = []
    def crash(*args):
        attempts.append(1)
        raise RuntimeError('simulated crash before delivery result')
    monkeypatch.setattr(alert_eval, '_deliver', crash)
    import pytest
    with pytest.raises(RuntimeError):
        alert_eval.evaluate_connection(source)
    monkeypatch.setattr(alert_eval, '_deliver', lambda *args: (attempts.append(1) or ('logged', 'late')))
    assert alert_eval.evaluate_connection(source) == []
    assert attempts == [1]
    assert len(alerts.list_fires(source)) == 1


def test_upgraded_automation_keeps_runs_and_does_not_replay(source, monkeypatch):
    from tarsier.storage.db import _cached_engine_for
    graph = {'nodes': [
        {'id': 't', 'role': 'trigger', 'kind': 'any_change', 'config': {}},
        {'id': 'a', 'role': 'action', 'kind': 'webhook', 'config': {}},
    ], 'edges': [{'from': 't', 'to': 'a'}]}
    auto = automations.create_automation(source, {'title': 'Legacy', 'graph': graph})
    attempts = []
    monkeypatch.setattr(auto_eval, 'send_webhook', lambda *args: attempts.append(1))
    change_log.insert_events(source, [_new_row(1)], {})
    assert len(auto_eval.evaluate_connection(source)) == 1
    with get_engine().begin() as conn:
        conn.execute(text('DELETE FROM event_receipts'))
        conn.execute(text('DELETE FROM event_replay_upgrade'))
        conn.execute(text('UPDATE automations SET event_checkpoint=NULL, source_log_checkpoint=NULL WHERE id=:id'), {'id': auto['id']})
    _cached_engine_for.cache_clear()
    assert auto_eval.evaluate_connection(source) == []
    assert len(automations.list_runs(source)) == 1
    change_log.insert_events(source, [_new_row(2)], {})
    assert len(auto_eval.evaluate_connection(source)) == 1
    assert attempts == [1, 1]
