"""The Round 4 native-build failure must stay fixed through the real cache."""
from datetime import date
from decimal import Decimal
import json
import pandas as pd
from tarsier.quality.engine import check_custom_rules
from tarsier.storage import connections, quality_cache


def test_decimal_flagged_rows_save_and_reload_natively(tmp_path,monkeypatch):
    monkeypatch.setenv("TARSIER_HOME",str(tmp_path))
    saved=connections.create_connection("synthetic","files",{"folder":"unused"})
    frame=pd.DataFrame({"key":["duplicate","duplicate"],"amount":[Decimal("12.50"),Decimal("13.75")],"day":[date(2026,1,1),date(2026,1,2)]})
    result=check_custom_rules(frame,[{"field":"key","operator":"is_unique"}])
    quality_cache.save_check(saved.id,"fixture","values",result)
    cached=quality_cache.get_checks(saved.id,"fixture","values")["custom_rules"]
    assert cached.fail_count==2
    assert [row["amount"] for row in cached.failing_rows]==[12.5,13.75]
    assert cached.failing_rows[0]["day"]=="2026-01-01"
    json.dumps(cached.failing_rows)
