from fastapi.testclient import TestClient
from tarsier.api.app import create_app
from tarsier.changes import sync
from tarsier.storage import change_log, connections


def test_acknowledgement_is_local_monotonic_and_does_not_ack_future_failures(tmp_path,monkeypatch):
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    saved=connections.create_connection(name='fixture',type='postgis',config={})
    change_log.set_mode(saved.id,'triggers')
    raw={'status':'degraded','logging_failures':2,'possible_gaps':True}
    monkeypatch.setattr('tarsier.changes.triggers.tracking_health',lambda _:dict(raw))
    monkeypatch.setattr(sync,'_postgis_config',lambda _: (None,None,None))
    client=TestClient(create_app())
    url='/api/connections/'+saved.id+'/changes/acknowledge'
    assert client.post(url,json={'acknowledge_failures_up_to':3}).status_code==409
    assert client.post(url,json={'acknowledge_failures_up_to':-1}).status_code==422
    assert client.post(url,json={'acknowledge_failures_up_to':True}).status_code==422
    health=client.post(url,json={'acknowledge_failures_up_to':2}).json()['tracking_health']
    assert health['logging_failures']==2 and health['unacknowledged_failures']==0 and health['possible_gaps']
    stamp=health['acknowledged_at']
    assert client.post(url,json={'acknowledge_failures_up_to':1}).json()['tracking_health']['acknowledged_at']==stamp
    raw['logging_failures']=3
    assert sync.tracking_health(saved.id)['unacknowledged_failures']==1
    raw['logging_failures']=None
    assert client.post(url,json={'acknowledge_failures_up_to':2}).status_code==409
