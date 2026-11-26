from types import SimpleNamespace
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.quality import engine, scan
from tarsier.quality.engine import check_custom_rules
from tarsier.quality.rule_validation import validate
from tarsier.connectors.base import ConnectorError, SampleResult
from tarsier.storage import connections
from tarsier.alerts.engine import AlertContext, evaluate_rule


def test_column_comparison_and_null_behavior():
    frame=pd.DataFrame({'total':[10,2,None],'land':[5,3,1]})
    result=check_custom_rules(frame,[{'field':'total','operator':'column_gte','value':'land'}])
    assert result.fail_count==1 and result.failing_rows[0]['total']==2
    assert result.skipped_count==1 and result.message=='1 rows skipped, value empty'
    for op in ('gt','gte','lt','lte','eq','ne'):
        result=check_custom_rules(pd.DataFrame({'a':[1],'b':[2]}),[{'field':'a','operator':'column_'+op,'value':'b'}])
        assert result.fail_count==(0 if op in ('lt','lte','ne') else 1)
    with pytest.raises(ConnectorError,match='compatible types'):
        validate({'field':'duration','operator':'column_gt','value':'count'}, {'duration':'interval','count':'integer'})


def test_unique_marks_original_and_every_duplicate_but_not_nulls():
    frame=pd.DataFrame({'pin':['duplicate']*21+['unique',None,None]})
    result=check_custom_rules(frame,[{'field':'pin','operator':'is_unique'}])
    assert result.fail_count==21 and result.skipped_count==2


def test_patterns_and_bad_regex():
    frame=pd.DataFrame({'zip':['12345','12X45',None]})
    for operator in ('matches','not_matches'):
        result=check_custom_rules(frame,[{'field':'zip','operator':operator,'value':r'^[0-9]{5}$'}])
        assert result.fail_count==1 and result.skipped_count==1
    with pytest.raises(ConnectorError,match='Invalid regular expression'):
        check_custom_rules(frame,[{'field':'zip','operator':'matches','value':'['}])


def test_regex_worker_is_bounded(monkeypatch):
    monkeypatch.setattr(engine,'PATTERN_TIMEOUT_SECONDS',0.01)
    with pytest.raises(ConnectorError,match='five-minute limit'):
        engine._pattern_mask(pd.Series(['a'*100000+'!']),r'(a+)+$')


@pytest.mark.parametrize('rule',[
    {'field':'x','operator':'column_gt','value':'text'},
    {'field':'x','operator':'column_gt','value':'x; DROP TABLE users'},
    {'field':'missing','operator':'is_unique'},
    {'field':'x','operator':'matches','value':'.'},
    {'field':'text','operator':'matches','value':'['},
    {'field':'text','operator':'is_unique','value':'unwanted'},
])
def test_catalog_type_and_value_validation(rule):
    with pytest.raises(ConnectorError):validate(rule,{'x':'integer','text':'text'})


def test_extended_rule_api_rejects_invalid_before_persisting(tmp_path,monkeypatch):
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    saved=connections.create_connection(name='fixture',type='postgis',config={})
    monkeypatch.setattr('tarsier.api.quality.columns_for',lambda *args:{'total':'numeric','land':'integer','zip':'text'})
    client=TestClient(create_app());url=f'/api/connections/{saved.id}/item/quality/rules'
    body={'schema':'qa','name':'fixture','field':'total','operator':'column_gte','value':'land'}
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json={**body,'value':'zip'}).status_code==400
    bad=client.post(url,json={**body,'field':'zip','operator':'matches','value':'['})
    assert bad.status_code==400 and 'regular expression' in bad.text
    assert client.post(url,json={**body,'operator':'is_unique','value':None}).status_code==200


def test_huge_custom_rule_full_request_is_still_labelled_sample(tmp_path,monkeypatch):
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    observed=[]
    class Connector:
        def sample_rows(self,config,item,limit):
            observed.append(limit)
            return SampleResult(dataframe=pd.DataFrame({'id':[1,1]}),is_sample=True)
    monkeypatch.setattr(scan,'_load_context',lambda *args:(SimpleNamespace(type='postgis'),Connector(),None,[],SimpleNamespace(kind='tabular')))
    monkeypatch.setattr('tarsier.quality.rule_validation.columns_for',lambda *args:{'id':'integer'})
    monkeypatch.setattr('tarsier.storage.quality_cache.list_rules',lambda *args:[{'field':'id','operator':'is_unique'}])
    result=scan.scan_check('fixture','qa','huge','custom_rules',full=True)
    assert observed==[scan.FULL_RUN_LIMIT] and result.is_sample and result.fail_count==2


def test_banned_alert_uses_shared_operator_with_aligned_target_rows():
    context=AlertContext(items=[],previous_items=None,events=[],quality_scores={},previous_quality={},
        now=datetime.now(timezone.utc),sample_rows={'qa.fixture':{'rows':[{'total':2,'land':3},{'total':9,'land':3}],'is_sample':True}})
    matches=evaluate_rule('banned_value',{'field':'total','operator':'column_lt','value':'land','target_schema':'qa','target_name':'fixture'},context)
    assert matches[0].details['count']==1 and matches[0].details['is_sample']


@pytest.mark.parametrize('op',('gt','gte','lt','lte','eq','ne'))
def test_column_null_on_either_side_is_skipped(op):
    frame=pd.DataFrame({'a':[None,1,None,1],'b':[2,None,None,2]})
    result=check_custom_rules(frame,[{'field':'a','operator':'column_'+op,'value':'b'}])
    assert result.skipped_count==3
    assert result.fail_count==(0 if op in ('lt','lte','ne') else 1)


def test_skips_count_distinct_rows_without_hiding_another_rule_failure():
    frame=pd.DataFrame({'a':[None,None,2],'b':[1,None,1],'zip':['bad',None,'12345']})
    result=check_custom_rules(frame,[{'field':'a','operator':'column_gte','value':'b'},
        {'field':'zip','operator':'matches','value':r'^[0-9]{5}$'}])
    assert result.skipped_count==2 and result.fail_count==1
    assert result.failing_rows[0]['zip']=='bad'


def test_empty_string_and_whitespace_are_skipped():
    result=check_custom_rules(pd.DataFrame({'zip':['', ' ', None]}),
        [{'field':'zip','operator':'matches','value':r'^[0-9]{5}$'}])
    assert result.fail_count==0 and result.skipped_count==3


@pytest.mark.parametrize('operator,value,expected',[
    ('gte','1',[False,False,True]),('is_null',None,[True,True,False]),
    ('is_not_null',None,[False,False,True]),('eq','2',[False,False,True]),
    ('ne','2',[True,True,False]),
])
def test_legacy_quality_operators_and_banned_alerts_keep_null_behavior(operator,value,expected):
    frame=pd.DataFrame({'a':[None,'',2]})
    assert engine._when_mask(frame.a,operator,value).tolist()==expected
    result=check_custom_rules(frame,[{'field':'a','operator':operator,'value':value}])
    assert result.fail_count==sum(not x for x in expected)
    assert result.skipped_count==0 and result.message is None
    context=AlertContext(items=[],previous_items=None,events=[],quality_scores={},previous_quality={},
        now=datetime.now(timezone.utc),sample_values={'a':frame.a.tolist()})
    matches=evaluate_rule('banned_value',{'field':'a','operator':operator,'value':value,
        'target_schema':'qa','target_name':'fixture'},context)
    assert sum(m.details['count'] for m in matches)==sum(expected)


@pytest.mark.parametrize('operator,value,expected',[
    ('column_lt','b',[False,True,False]),('matches','^x$',[False,True,False]),
    ('not_matches','^x$',[False,False,True]),('is_unique',None,[True,True,True]),
])
def test_extended_banned_predicates_are_unchanged(operator,value,expected):
    frame=pd.DataFrame({'a':[None,'x','y'],'b':['z','z','a']})
    assert engine._when_mask(frame.a,operator,value,frame=frame).tolist()==expected


def test_skipped_count_survives_cache_and_old_cache_defaults_to_zero(tmp_path,monkeypatch):
    from tarsier.storage import quality_cache
    monkeypatch.setenv('TARSIER_HOME',str(tmp_path))
    saved=connections.create_connection(name='fixture',type='postgis',config={})
    result=check_custom_rules(pd.DataFrame({'a':[None,1,1]}),[{'field':'a','operator':'is_unique'}])
    quality_cache.save_check(saved.id,'qa','fixture',result)
    assert quality_cache.get_checks(saved.id,'qa','fixture')['custom_rules'].skipped_count==1
    assert engine.CheckResult(**{'check_id':'custom_rules','status':'good'}).skipped_count==0


@pytest.mark.parametrize("operator", ("matches", "not_matches", "is_unique"))
def test_extended_text_families_skip_all_existing_empty_values(operator):
    frame = pd.DataFrame({"a": [None, "", "   ", "", "   ", "x", "x", "y"]})
    rule = {"field": "a", "operator": operator}
    if operator != "is_unique":
        rule["value"] = "^x$"
    result = check_custom_rules(frame, [rule])
    assert result.skipped_count == 5
    assert result.fail_count == (1 if operator == "matches" else 2)
    assert all(row["a"] and row["a"].strip() for row in result.failing_rows)


@pytest.mark.parametrize("operator", ("gt", "gte", "lt", "lte", "eq", "ne"))
def test_column_families_skip_empty_on_either_side_before_comparing(operator):
    frame = pd.DataFrame({"a": [None, "", "   ", 1, 1, 1, 1],
                          "b": [2, 2, 2, None, "", "   ", 2]})
    result = check_custom_rules(frame, [{"field": "a", "operator": "column_" + operator, "value": "b"}])
    assert result.skipped_count == 6
    assert result.fail_count == (0 if operator in ("lt", "lte", "ne") else 1)
