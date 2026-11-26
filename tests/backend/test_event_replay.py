from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text

from tarsier.storage import alerts, automations, change_log, connections
from tarsier.storage.db import get_engine, _cached_engine_for
from tarsier.alerts import evaluate


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return connections.create_connection("Synthetic", "files", {}).id


def event(cid, number=1, *, when=None, after=None):
    change_log.insert_events(cid,[{"occurred_at":when or datetime.now(timezone.utc),"db_user":"editor","action":"update","schema":"s","name":"t","source":"trigger","source_log_id":number,"after":after}],{})


def rule(cid, kind="specific_user", **config):
    return alerts.create_rule(cid,{"kind":kind,"config":{"user":"editor","notify":"log",**config}})


def test_repeated_evaluation_new_event_and_reload_send_once(source, monkeypatch):
    rule(source);event(source)
    sends=[]
    monkeypatch.setattr(evaluate,"_deliver",lambda *args:(sends.append(args[2]["id"]) or ("logged","test")))
    assert len(evaluate.evaluate_connection(source))==1
    assert evaluate.evaluate_connection(source)==[]
    _cached_engine_for.cache_clear()
    assert evaluate.evaluate_connection(source)==[]
    event(source,2)
    assert len(evaluate.evaluate_connection(source))==1
    assert len(sends)==2 and len(set(sends))==2


def test_concurrent_evaluators_cannot_deliver_twice(source, monkeypatch):
    rule(source);event(source);sends=[]
    monkeypatch.setattr(evaluate,"_deliver",lambda *args:(sends.append(1) or ("logged","test")))
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda _:evaluate.evaluate_connection(source),range(2)))
    assert sum(map(len,result))==1 and len(sends)==1


def test_upgrade_preserves_history_and_seeds_existing_consumers(source):
    r=rule(source);event(source)
    assert len(evaluate.evaluate_connection(source))==1
    # Reconstruct a legacy schema state, retaining its existing historical fire.
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM event_receipts"));c.execute(text("DELETE FROM event_replay_upgrade"))
        c.execute(text("UPDATE alert_rules SET event_checkpoint=NULL, source_log_checkpoint=NULL WHERE id=:id"), {"id": r["id"]})
    _cached_engine_for.cache_clear()
    assert evaluate.evaluate_connection(source)==[]
    with get_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM alert_fires")).scalar_one()==1
    event(source,2)
    assert len(evaluate.evaluate_connection(source))==1


def test_new_rule_starts_after_creation(source):
    event(source); rule(source)
    assert evaluate.evaluate_connection(source) == []
    event(source, 2)
    assert len(evaluate.evaluate_connection(source)) == 1
    assert evaluate.evaluate_connection(source) == []


def test_reimported_source_log_id_is_not_a_new_event(source):
    rule(source);event(source)
    assert len(evaluate.evaluate_connection(source))==1
    with get_engine().begin() as c:c.execute(text("DELETE FROM change_events"))
    event(source)
    assert evaluate.evaluate_connection(source)==[]


def test_legacy_banned_after_images_are_claimed_per_event(source, monkeypatch):
    rule(source,"banned_value",field="value",operator="lt",value="0")
    monkeypatch.setattr(evaluate,"_banned_samples",lambda *_:{})
    monkeypatch.setattr(evaluate,"_banned_rows",lambda *_:{})
    event(source,after={"value":-1})
    assert len(evaluate.evaluate_connection(source))==1
    assert evaluate.evaluate_connection(source)==[]
    event(source,2,after={"value":-2})
    assert len(evaluate.evaluate_connection(source))==1


def test_automation_claims_survive_reload_and_late_arriving_events(source, monkeypatch):
    from tarsier.automation import evaluate as auto
    graph={"nodes":[{"id":"trigger","role":"trigger","kind":"any_change","config":{}},{"id":"send","role":"action","kind":"webhook","config":{}}],"edges":[{"from":"trigger","to":"send"}]}
    automations.create_automation(source,{"title":"Synthetic","graph":graph})
    sends=[];monkeypatch.setattr(auto,"send_webhook",lambda *_:sends.append(1))
    event(source)
    assert len(auto.evaluate_connection(source))==1
    assert auto.evaluate_connection(source)==[]
    _cached_engine_for.cache_clear()
    assert auto.evaluate_connection(source)==[]
    event(source,2,when=datetime.now(timezone.utc)-timedelta(days=1))
    assert len(auto.evaluate_connection(source))==1
    assert sends==[1,1]


def test_concurrent_automation_evaluators_cannot_repeat_delivery(source, monkeypatch):
    from tarsier.automation import evaluate as auto
    graph={"nodes":[{"id":"t","role":"trigger","kind":"any_change","config":{}},{"id":"a","role":"action","kind":"webhook","config":{}}],"edges":[{"from":"t","to":"a"}]}
    automations.create_automation(source,{"title":"Concurrent","graph":graph})
    sends=[];monkeypatch.setattr(auto,"send_webhook",lambda *_:sends.append(1))
    event(source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda _:auto.evaluate_connection(source),range(2)))
    assert sum(map(len,result))==1 and sends==[1]


def test_upgrade_does_not_hide_history_from_freshness_state_checks(source, monkeypatch):
    rule(source,"freshness");event(source)
    with get_engine().begin() as c:
        c.execute(text("DELETE FROM event_replay_upgrade"))
    _cached_engine_for.cache_clear()
    observed=[]
    monkeypatch.setattr(evaluate,"evaluate_rule",lambda kind,config,ctx:(observed.append(len(ctx.events)) or []))
    evaluate.evaluate_connection(source)
    assert observed==[1]


def test_concurrent_snapshot_creation_and_replacement(source):
    from threading import Barrier

    for phase in range(2):
        barrier = Barrier(8)
        payloads = [{"writer": i, "phase": phase, "values": [i] * 50,
                     "scanned_at": datetime.now(timezone.utc).isoformat()} for i in range(8)]

        def save(payload):
            barrier.wait(timeout=10)
            alerts.save_snapshot(source, payload)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(save, payloads))
        assert alerts.get_snapshot(source) in payloads
        with get_engine().connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM alert_snapshots WHERE connection_id=:id"), {"id": source}).scalar_one() == 1
