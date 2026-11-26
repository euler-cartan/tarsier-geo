from datetime import datetime, timezone
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from tarsier.api.app import create_app
from tarsier.alerts.engine import AlertContext, evaluate_rule
from tarsier.connectors.base import ConnectorError
from tarsier.quality.engine import check_custom_rules
from tarsier.storage import connections


def context(rows):
    return AlertContext([], None, [], {}, {}, datetime.now(timezone.utc), sample_rows={"s.t":{"rows":rows,"is_sample":False}})


def test_engine_rejects_unique_even_with_no_rows():
    with pytest.raises(ConnectorError, match="only for quality rules"):
        evaluate_rule("banned_value", {"field":"a","operator":"is_unique"}, context([]))


@pytest.mark.parametrize("action", ("create", "update", "preview"))
def test_api_rejects_unique_with_clear_message(tmp_path, monkeypatch, action):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved=connections.create_connection("fixture","files",{"folder":"unused"})
    monkeypatch.setattr("tarsier.quality.rule_validation.columns_for",lambda *args:{"a":"text"})
    monkeypatch.setattr("tarsier.api.alerts.preview_rule",lambda *args:{"matches":[]})
    client=TestClient(create_app());url=f"/api/connections/{saved.id}/alerts"
    body={"kind":"banned_value","target_schema":"s","target_name":"t","config":{"field":"a","operator":"eq","value":"x"}}
    existing=client.post(url,json=body);assert existing.status_code==200
    body["config"]["operator"]="is_unique"
    if action=="create":response=client.post(url,json=body)
    elif action=="update":response=client.put(url+"/"+existing.json()["id"],json=body)
    else:response=client.post(url+"/preview",json=body)
    assert response.status_code==400 and "only for quality rules" in response.json()["detail"]


@pytest.mark.parametrize("op,count", (("gt",0),("gte",1),("lt",1),("lte",2),("eq",1),("ne",1)))
def test_other_extended_column_alerts_still_match(op,count):
    result=evaluate_rule("banned_value",{"field":"a","operator":"column_"+op,"value":"b","target_schema":"s","target_name":"t"},context([{"a":1,"b":2},{"a":2,"b":2}]))
    assert sum(r.details["count"] for r in result)==count


@pytest.mark.parametrize("op", ("matches", "not_matches"))
def test_pattern_alerts_still_match(op):
    result=evaluate_rule("banned_value",{"field":"a","operator":op,"value":"^x$","target_schema":"s","target_name":"t"},context([{"a":"x"},{"a":"y"}]))
    assert result[0].details["count"]==1


def test_quality_unique_is_still_available():
    result=check_custom_rules(pd.DataFrame({"a":["x","x",None,"", "   "]}),[{"field":"a","operator":"is_unique"}])
    assert result.fail_count==2 and result.skipped_count==3
