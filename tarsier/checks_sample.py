"""Sample-first backend mode; the existing full worker is intentionally separate."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from tarsier import check_dataset
from tarsier.connectors.base import ConnectorError, ItemMetadata, find_id_column
from tarsier.connectors.registry import get_connector
from tarsier.quality import engine as quality
from tarsier.stats.engine import compute_table_stats
from tarsier.storage import connections, item_cache, quality_cache, stats_cache
from tarsier.storage.paths import tarsier_home
from tarsier.storage.run_timings import save_checkpoint
from tarsier.timing import current_run_id, timed_run, record_outcome


class UnverifiedCheck(ConnectorError):
    pass


def quality_from_dataset(item, check, frame, details, rules, items, *, boundary=None):
    # Metadata-only and ruleless decisions must precede touching the frame.
    if check == "custom_rules" and not rules:
        return quality.check_custom_rules(None, [])
    inapplicable = quality.geometry_check_applicability(check,getattr(item,"geometry_type",None))
    if inapplicable is not None:
        return inapplicable
    if check == "projection":
        return quality.check_projection(item.srid,quality.majority_srid([i.srid for i in items]))
    sampled = details["is_sample"]
    if check == "completeness":
        column=find_id_column(list(frame.columns))
        if column is None:
            return quality.check_completeness(None,None)
        if sampled:
            raise UnverifiedCheck("A sample cannot verify sequence completeness; request a full-ID check.")
        return quality.check_completeness(frame[column] if column else None,column)
    if check == "custom_rules":
        return quality.check_custom_rules(frame,rules,is_sample=sampled)
    if check == "boundary":
        if boundary is None:
            return quality.check_boundary(None,None)
        reference, reference_details=boundary
        if reference_details["is_sample"]:
            raise UnverifiedCheck("A sampled reference cannot verify full boundary coverage.")
        return quality.check_boundary(frame,reference,is_sample=sampled)
    runners={"validity":quality.check_validity,"overlaps":quality.check_overlaps,"slivers":quality.check_slivers,"gaps":quality.check_gaps,"dangles":quality.check_dangles}
    return runners[check](frame,is_sample=sampled)


def _checkpoint(run_id, connection_id, item, payload):
    save_checkpoint(run_id,connection_id,item.schema,item.name,{"mode":"sample_first",**payload})


@timed_run("sample_first")
def run(connection_id, job):
    from tarsier.checks import _save
    saved=connections.get_connection(connection_id)
    if saved is None or saved.type != "postgis":
        raise ConnectorError("Sample-first bounded acquisition is available for PostGIS connections only.")
    connector=get_connector(saved.type)
    config=connector.build_config(saved.config,connections.get_connection_password(connection_id))
    items=connector.list_items(config)
    run_id=current_run_id()
    job.update(mode="sample_first",run_id=run_id,total=len(items),completed=0)
    _save(connection_id,job)
    stage=tarsier_home()/"sample-first-temp"
    stage.mkdir(exist_ok=True)
    registry={}
    # Temporary staged samples are not complete snapshots and are never published
    # through snapshot capture/analytics. They allow bounded reference reuse.
    with TemporaryDirectory(prefix="run-",dir=stage) as staging:
        for item in items:
            start=time.perf_counter()
            if item.kind == "raster":
                _checkpoint(run_id,connection_id,item,{"state":"skipped_raster","row_count":0,"operations":[]})
                job["completed"]+=1
                continue
            try:
                raw=check_dataset.acquire(config,item)
                filename=Path(staging)/(hashlib.sha256((item.schema+"\0"+item.name).encode()).hexdigest()+".json")
                with filename.open("w",encoding="utf-8") as stream:json.dump(raw.payloads,stream)
                registry[(item.schema,item.name)]={"path":filename,"details":raw.details,"item":item,"columns":raw.columns,"crs":raw.crs,"fetch_seconds":time.perf_counter()-start}
                _checkpoint(run_id,connection_id,item,{"state":"acquired",**raw.details,"operations":[{"check":"fetch","elapsed_seconds":time.perf_counter()-start}]})
            except Exception as exc:
                details=getattr(exc,"details",{})
                _checkpoint(run_id,connection_id,item,{"state":"budget_limited" if isinstance(exc,check_dataset.DatasetBudgetError) else "acquisition_failed","is_sample":True,"budget_limited":isinstance(exc,check_dataset.DatasetBudgetError),"row_count":0,**details,"error_type":type(exc).__name__,"caches_preserved":True,"operations":[{"check":"fetch","elapsed_seconds":time.perf_counter()-start}]})
                job["errors"].append({"schema":item.schema,"name":item.name,"check":"acquisition","message":"Acquisition unavailable; previous caches preserved."})
                job["completed"]+=1
            _save(connection_id,job)
        def load(key):
            record=registry.get(key)
            if record is None:
                raise UnverifiedCheck("The reference dataset is unavailable; previous cache preserved.")
            with record["path"].open(encoding="utf-8") as stream:payloads=json.load(stream)
            raw=check_dataset.RawDataset(payloads,record["details"],record["item"],record["columns"],record["crs"])
            return raw.construct(),record["details"]
        for key, record in registry.items():
            item=record["item"];details=record["details"];operations=[{"check":"fetch","elapsed_seconds":record["fetch_seconds"]}];unverified=[]
            try:
                start=time.perf_counter();frame,_=load(key);operations.append({"check":"construct","elapsed_seconds":time.perf_counter()-start})
                start=time.perf_counter();view,geometry_columns,null_geometry_column=check_dataset.statistics_view(frame,item)
                stats=compute_table_stats(view,details["is_sample"],geometry_columns,null_geometry_column)
                stats=replace(stats,sample_details=details)
                operations.append({"check":"statistics","elapsed_seconds":time.perf_counter()-start})
                results=[]
                rules=quality_cache.list_rules(connection_id,item.schema,item.name)
                for check in quality.applicable_checks(item.kind):
                    start=time.perf_counter()
                    try:
                        boundary=None
                        if check == "boundary":
                            settings=quality_cache.get_settings(connection_id,item.schema,item.name)
                            if settings is not None and settings.boundary_name:
                                boundary=load((settings.boundary_schema,settings.boundary_name))
                        result=quality_from_dataset(item,check,frame,details,rules,items,boundary=boundary)
                        results.append(replace(result,sample_details=details))
                    except Exception as exc:
                        unverified.append(check)
                        job["errors"].append({"schema":item.schema,"name":item.name,"check":check,"message":"This check could not be verified from the bounded dataset; previous cache preserved."})
                    operations.append({"check":check,"elapsed_seconds":time.perf_counter()-start})
                # Acquisition/construction/compute must finish before replacing any
                # prior table results. No notifications, automations or snapshots.
                start=time.perf_counter()
                stats_cache.save_stats(connection_id,item.schema,item.name,stats)
                for result in results:quality_cache.save_check(connection_id,item.schema,item.name,result)
                operations.append({"check":"cache_write","elapsed_seconds":time.perf_counter()-start})
                _checkpoint(run_id,connection_id,item,{"state":"budget_limited" if details["budget_limited"] else "completed_with_unverified" if unverified else "completed",**details,"unverified_checks":unverified,"operations":operations})
                del frame,view,stats,results
            except Exception as exc:
                _checkpoint(run_id,connection_id,item,{"state":"construction_or_compute_failed",**details,"error_type":type(exc).__name__,"caches_preserved":True,"operations":operations})
                job["errors"].append({"schema":item.schema,"name":item.name,"check":"construction","message":"The bounded dataset could not be processed; previous caches preserved."})
            job["completed"]+=1
            job["message"]=f"Checking {item.qualified_name}: sample-first."
            _save(connection_id,job)
    from tarsier.graph.engine import refresh_quietly
    refresh_quietly()
    job.update(state="completed_with_errors" if job["errors"] else "completed",message="Sample-first check finished.",finished_at=datetime.now(timezone.utc).isoformat())
    record_outcome(job["state"])
    _save(connection_id,job)
