from decimal import Decimal
from types import SimpleNamespace
import pandas as pd
import pytest
from tarsier import flowchart
from tarsier.connectors.base import DataItem, SampleResult, sample_frame


@pytest.mark.parametrize("text,number,match", [
    ("123",123,True),(" 123 ",123,True),("\t123\n",123,True),
    ("00123",123,False),("123.0",123,False),("+123",123,False),
    ("-123",-123,False),("123",-123,False),("１２３",123,False),
    ("١٢٣",123,False),("1,234",1234,False),("",0,False),
    ("0",0,True),("00",0,False),("1",True,False),
    ("123",123.0,False),("123",Decimal("123.0"),False),
])
def test_exact_digit_boundary_in_both_directions(text,number,match):
    for a,b in [({text},{number}),({number},{text})]:
        left,right=flowchart._matching_sets(a,b)
        assert bool(left & right)==match


def test_text_to_text_matching_does_not_gain_trimming_or_numeric_coercion():
    a,b=flowchart._matching_sets({" 123 "},{"123"})
    assert not a & b


def test_nullable_bigints_keep_exact_catalog_integer_values():
    big=9223372036854775807
    frame=sample_frame([{"code":big},{"code":None}],integer_columns=["code"])
    values=flowchart._values_for_column(frame,"code")
    assert values=={big} and next(iter(values))==big
    left,right=flowchart._matching_sets({str(big)},values)
    assert left==right


def test_normalized_minimum_and_overlap_are_still_required():
    a=DataItem("s","a","tabular");b=DataItem("s","b","tabular")
    assert not flowchart.guess_between(a,{"code":{"1","2","3","4"," 4 ","invalid"}},False,b,{"code":{1,2,3,4,5}},False)
    assert not flowchart.guess_between(a,{"code":{"1","2","3","8","9"}},False,b,{"code":{1,2,3,4,5}},False)


def test_shared_rule_applies_within_and_across_connections(monkeypatch):
    rows={"a":pd.DataFrame({"code":[" 1 ","2","3","4","5"]}),"b":pd.DataFrame({"code":[1,2,3,4,5]})}
    class Connector:
        def build_config(self,config,password):return config
        def list_items(self,config):return [DataItem("s",n,"tabular") for n in config["names"]]
        def sample_rows(self,config,item,limit,distinct_column=None):return SampleResult(rows[item.name],False)
    saved=[SimpleNamespace(id="one",name="one",type="fixture",config={"names":["a","b"]}),SimpleNamespace(id="two",name="two",type="fixture",config={"names":["b"]})]
    monkeypatch.setattr(flowchart,"get_connector",lambda _:Connector())
    monkeypatch.setattr(flowchart.connection_storage,"get_connection",lambda _:saved[0])
    monkeypatch.setattr(flowchart.connection_storage,"list_connections",lambda:saved)
    monkeypatch.setattr(flowchart.connection_storage,"get_connection_password",lambda _:None)
    _,within=flowchart.discover_links("one")
    cross,skipped=flowchart.discover_cross_connection_links()
    assert len(within)==1 and not skipped
    assert any(r["source_name"]=="a" and r["target_name"]=="b" for r in cross)
