"""UTC storage and calendar boundaries with America/New_York source offsets."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.changes.engine import volume_by_day
from tarsier.storage import change_log, connections
from tarsier.storage.db import get_session
from tarsier.storage.models import ChangeEvent


def test_source_offset_round_trip_inclusive_days_and_spike(tmp_path,monkeypatch):
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    monkeypatch.setenv('TZ','America/New_York')
    monkeypatch.setattr('tarsier.changes.sync.tracking_health',lambda _: {})
    saved=connections.create_connection(name='UTC fixture',type='postgis',config={})
    today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    stamps=[today-timedelta(microseconds=1),today,today+timedelta(days=1,microseconds=-1)]
    stamps += [today-timedelta(days=i)+timedelta(hours=12) for i in range(2,8)]
    stamps += [today+timedelta(seconds=i) for i in range(1,3)]
    rows=[dict(occurred_at=s.astimezone(ZoneInfo('America/New_York')),schema='qa',name='events',
               action='update',source_log_id=i) for i,s in enumerate(stamps)]
    change_log.insert_events(saved.id,rows,{})
    change_log.insert_events(saved.id,rows,{})
    events=change_log.list_events(saved.id)
    assert len(events)==len(rows)
    assert {e.occurred_at for e in events}==set(stamps)
    response=TestClient(create_app()).get('/api/connections/'+saved.id+'/changes',params={'start':today.date().isoformat(),'end':today.date().isoformat()})
    assert response.status_code==200
    assert len(response.json()['events'])==4
    bar=volume_by_day(events,days=8)[-1]
    assert bar['date']==today.date().isoformat() and bar['count']==4 and bar['is_spike']
    # Three is exactly 3 * the seven-day mean, so it must not be a spike.
    reduced=[e for e in events if e.occurred_at!=today+timedelta(seconds=2)]
    assert not volume_by_day(reduced,days=8)[-1]['is_spike']


def test_resync_replaces_old_naive_cache_timestamp_from_authoritative_source(tmp_path,monkeypatch):
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    source=datetime(2026,10,17,20,0,tzinfo=ZoneInfo('America/New_York'))
    row=dict(occurred_at=source,schema='qa',name='events',action='update',source_log_id=1)
    change_log.insert_events('c',[row],{})
    with get_session() as session:
        session.query(ChangeEvent).one().occurred_at=source.replace(tzinfo=None)
        session.commit()
    change_log.insert_events('c',[row],{})
    assert change_log.list_events('c')[0].occurred_at==datetime(2026,10,18,tzinfo=timezone.utc)
