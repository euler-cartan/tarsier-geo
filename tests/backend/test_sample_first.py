import json
from types import SimpleNamespace

import pytest

from tarsier import check_dataset, checks_sample, checks
from tarsier.connectors.base import DataItem
from tarsier.storage import connections, stats_cache, quality_cache
from tarsier.storage.run_timings import read_checkpoints
from tarsier.stats.engine import compute_table_stats


def payload(i):
    return json.dumps({"attributes":{"id":i,"value":i},"wkb":None,"identity":f"synthetic:{i}"})


class Result:
    def __init__(self, rows): self.rows,self.closed=rows,False
    def mappings(self): return iter(self.rows)
    def close(self): self.closed=True


class Connection:
    def __init__(self,rows): self.result=Result(rows)
    def execution_options(self,**options):
        assert options=={"stream_results":True,"max_row_buffer":1}
        return self
    def execute(self,*_):return self.result


def test_acquisition_cap_is_enforced_before_construction(monkeypatch):
    collector=check_dataset.Collector(cap=50000)
    conn=Connection([{"__payload":payload(i)} for i in range(1000)])
    monkeypatch.setattr(check_dataset.RawDataset,"construct",lambda *_:pytest.fail("Construction must not occur during acquisition"))
    result=collector.read(conn,"synthetic")
    assert 0<len(result)<1000 and collector.limited
    assert collector.accounted<=50000 and conn.result.closed


def test_server_rejected_oversize_record_is_not_accepted():
    collector=check_dataset.Collector(cap=10000)
    conn=Connection([{"__payload":None}])
    assert collector.read(conn,"synthetic")==[]
    assert collector.limited and collector.serialized==0 and conn.result.closed


def test_timeout_closes_source_result(monkeypatch):
    collector=check_dataset.Collector();collector.deadline=0
    conn=Connection([{"__payload":payload(1)}])
    with pytest.raises(Exception,match="deadline"):
        collector.read(conn,"synthetic")
    assert conn.result.closed


def fixture_source(tmp_path,monkeypatch):
    monkeypatch.setenv("TARSIER_HOME",str(tmp_path))
    saved=connections.create_connection("Synthetic","postgis",{"host":"unused","port":5434})
    item=DataItem("s","t","tabular")
    monkeypatch.setattr(checks_sample,"get_connector",lambda *_:SimpleNamespace(build_config=lambda *_:None,list_items=lambda *_:[item]))
    monkeypatch.setattr(connections,"get_connection_password",lambda *_:None)
    monkeypatch.setattr("tarsier.graph.engine.refresh_quietly",lambda:None)
    return saved.id,item


def test_one_dataset_supplies_statistics_and_quality_with_identical_identities(tmp_path,monkeypatch):
    cid,item=fixture_source(tmp_path,monkeypatch);calls=[];identities=[]
    details={"is_sample":False,"complete":True,"method":"complete","seed_vector":[],"row_count":5,"budget_limited":False}
    def acquire(*args,**kwargs):
        calls.append(1)
        return check_dataset.RawDataset([payload(i) for i in range(1,6)],details,item,("id","value"))
    monkeypatch.setattr(check_dataset,"acquire",acquire)
    quality_cache.create_rule(cid,"s","t",{"kind":"attribute","field":"value","operator":"gt","value":"0"})
    stats=checks_sample.compute_table_stats;quality=checks_sample.quality_from_dataset
    def observe_stats(frame,*args):
        identities.append(frame.attrs["sample_identities"])
        return stats(frame,*args)
    def observe_quality(item,check,frame,*args,**kwargs):
        identities.append(frame.attrs["sample_identities"])
        return quality(item,check,frame,*args,**kwargs)
    monkeypatch.setattr(checks_sample,"compute_table_stats",observe_stats)
    monkeypatch.setattr(checks_sample,"quality_from_dataset",observe_quality)
    job={"errors":[],"state":"running"}
    checks_sample.run(cid,job)
    assert calls==[1] and len(identities)==3 and all(v==identities[0] for v in identities)
    assert job["state"]=="completed" and job["completed"]==job["total"]==1
    assert stats_cache.get_stats(cid,"s","t").sample_details["method"]=="complete"
    assert read_checkpoints(connection_id=cid)[0]["state"]=="completed"


def test_acquisition_failure_preserves_previous_cache(tmp_path,monkeypatch):
    import pandas as pd
    cid,item=fixture_source(tmp_path,monkeypatch)
    old=compute_table_stats(pd.DataFrame({"value":[7]}),False)
    stats_cache.save_stats(cid,"s","t",old)
    from tarsier.quality.engine import CheckResult
    prior_check=CheckResult("custom_rules","danger",fail_count=7)
    quality_cache.save_check(cid,"s","t",prior_check)
    def fail(*args,**kwargs):raise check_dataset.DatasetBudgetError({"budget_limited":True,"is_sample":True,"row_count":0})
    monkeypatch.setattr(check_dataset,"acquire",fail)
    job={"errors":[],"state":"running"};checks_sample.run(cid,job)
    assert stats_cache.get_stats(cid,"s","t")==old
    assert quality_cache.get_checks(cid,"s","t")["custom_rules"]==prior_check
    point=read_checkpoints(connection_id=cid)[0]
    assert point["caches_preserved"] and point["budget_limited"] and point["is_sample"]


def test_known_inapplicability_and_absent_rules_never_touch_dataset():
    item=DataItem("s","points","vector",geometry_type="Point")
    assert checks_sample.quality_from_dataset(item,"overlaps",None,{},[],[item]).status=="not_applicable"
    assert checks_sample.quality_from_dataset(item,"custom_rules",None,{},[],[item]).status=="not_applicable"


def test_default_and_explicit_full_mode_keep_original_worker(tmp_path,monkeypatch):
    monkeypatch.setenv("TARSIER_HOME",str(tmp_path));submitted=[]
    monkeypatch.setattr(checks._pool,"submit",lambda *args:submitted.append(args))
    for mode in (None,"full"):
        cid=f"synthetic-{mode}"
        try:
            checks.start(cid,**({} if mode is None else {"mode":mode}))
            assert submitted[-1][0] is checks._run
        finally:checks._active.discard(cid)


def test_explicit_sample_mode_dispatches_separate_worker(tmp_path,monkeypatch):
    monkeypatch.setenv("TARSIER_HOME",str(tmp_path));submitted=[]
    monkeypatch.setattr(checks._pool,"submit",lambda *args:submitted.append(args))
    try:
        checks.start("synthetic",mode="sample_first")
        assert submitted[0][0] is checks._run_sample
    finally:checks._active.discard("synthetic")


def test_vector_statistics_and_all_topology_checks_share_the_captured_identities(tmp_path,monkeypatch):
    from shapely.geometry import Polygon
    cid,_=fixture_source(tmp_path,monkeypatch)
    item=DataItem("s","polygons","vector",geometry_type="Polygon",srid=3857,geometry_column="geom")
    monkeypatch.setattr(checks_sample,"get_connector",lambda *_:SimpleNamespace(build_config=lambda *_:None,list_items=lambda *_:[item]))
    calls=[];seen=[]
    details={"is_sample":True,"complete":False,"method":"multi_seed_system","seed_vector":list(range(719,729)),"row_count":5,"budget_limited":False}
    def acquire(*args,**kwargs):
        calls.append(1)
        payloads=[json.dumps({"attributes":{"id":i,"value":i},"wkb":Polygon([(i*3,0),(i*3+1,0),(i*3+1,1),(i*3,1)]).wkb_hex,"identity":f"synthetic:{i}"}) for i in range(1,6)]
        return check_dataset.RawDataset(payloads,details,item,("id","value"))
    monkeypatch.setattr(check_dataset,"acquire",acquire)
    original_stats=checks_sample.compute_table_stats
    def stats(frame,*args):
        seen.append(frame.attrs["sample_identities"])
        return original_stats(frame,*args)
    monkeypatch.setattr(checks_sample,"compute_table_stats",stats)
    for name in ("check_validity","check_overlaps","check_slivers","check_gaps"):
        original=getattr(checks_sample.quality,name)
        def wrapped(frame,*args,_original=original,**kwargs):
            seen.append(frame.attrs["sample_identities"])
            return _original(frame,*args,**kwargs)
        monkeypatch.setattr(checks_sample.quality,name,wrapped)
    checks_sample.run(cid,{"state":"running","errors":[]})
    assert calls==[1] and len(seen)==5 and all(v==seen[0] for v in seen)
    results=quality_cache.get_checks(cid,"s","polygons")
    assert results["validity"].is_sample
    assert results["validity"].sample_details["seed_vector"]==list(range(719,729))
