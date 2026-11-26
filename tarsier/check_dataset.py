"""Bounded PostGIS acquisition before pandas or GEOS construction."""
from dataclasses import dataclass
from decimal import Decimal
import json
import sys
import time

from sqlalchemy import text

from tarsier.connectors.base import ConnectorError, sample_frame
from tarsier.connectors.geoms import geodataframe_from_wkb_rows
from tarsier.connectors import postgis
from tarsier.timing import timed_phase

DATASET_CAP = 64 * 1024 * 1024
ROW_WIRE_CAP = 1024 * 1024
# Reserve parsing/frame/geometry headroom before accepting a wire record.
# This is an acquisition accounting bound, not a worker RSS limit.
PARSE_RESERVE_MULTIPLIER = 64
ROW_RESERVE = 2048


class DatasetBudgetError(ConnectorError):
    def __init__(self, details):
        super().__init__("The table exceeded the bounded acquisition budget; previous caches are unchanged.")
        self.details = details


@dataclass
class RawDataset:
    payloads: list[str]
    details: dict
    item: object
    columns: tuple = ()
    crs: str | None = None

    @timed_phase("compute")
    def construct(self):
        decoded = [json.loads(value, parse_float=Decimal) for value in self.payloads]
        identities = tuple(row["identity"] for row in decoded)
        records = [row["attributes"] for row in decoded]
        self.payloads.clear()
        if self.item.kind == "vector":
            for attrs, row in zip(records, decoded):
                attrs["__wkb"] = bytes.fromhex(row["wkb"]) if row.get("wkb") else None
            frame = geodataframe_from_wkb_rows(records, self.item.srid, crs=self.crs)
        else:
            frame = sample_frame(records)
        for name in self.columns:
            if name not in frame.columns:
                import pandas as pd
                frame[name] = pd.Series(dtype=object)
        frame.attrs["sample_identities"] = identities
        return frame


class Collector:
    def __init__(self, cap=DATASET_CAP):
        if not 0 < cap <= DATASET_CAP:
            raise ValueError("Dataset cap must be positive and at most 64 MiB")
        self.cap, self.accounted, self.serialized = cap, 0, 0
        self.limited = False
        self.deadline = time.monotonic() + 30

    def read(self, conn, statement, params=None):
        rows = []
        result = conn.execution_options(stream_results=True, max_row_buffer=1).execute(statement, params or {})
        try:
            for row in result.mappings():
                if time.monotonic() > self.deadline:
                    raise ConnectorError("Sample acquisition exceeded its 30-second deadline; previous caches are unchanged.")
                payload = row["__payload"]
                if payload is None:
                    self.limited = True
                    break
                size = len(payload.encode("utf-8"))
                cost = max(size, sys.getsizeof(payload)) * PARSE_RESERVE_MULTIPLIER + ROW_RESERVE
                if self.accounted + cost > self.cap:
                    self.limited = True
                    break
                self.accounted += cost
                self.serialized += size
                rows.append(dict(row))
        finally:
            result.close()
        return rows


@timed_phase("fetch")
def acquire(config, item, *, cap=DATASET_CAP):
    collector = Collector(cap)
    engine = postgis._build_engine(config, statement_timeout_ms=5000)
    try:
        with engine.connect() as conn:
            columns = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name=:n AND column_name!=COALESCE(:g,'') ORDER BY ordinal_position"), {"s":item.schema,"n":item.name,"g":item.geometry_column}).scalars().all()
            crs = (conn.execute(text("SELECT srtext FROM spatial_ref_sys WHERE srid=:srid"), {"srid":item.srid}).scalar_one_or_none() if item.kind == "vector" and item.srid else None)
            quote = lambda v: '"'+v.replace('"','""')+'"'
            fields = ','.join(quote(c) for c in columns)
            attributes = f"(SELECT row_to_json(a) FROM (SELECT {fields}) a)" if fields else "'{}'::json"
            wkb = f"encode(ST_AsBinary({quote(item.geometry_column)}),'hex')" if item.kind == "vector" and item.geometry_column else "NULL"
            payload = f"jsonb_build_object('attributes',{attributes},'wkb',{wkb},'identity',tableoid::text||':'||ctid::text)::text"
            # An oversized cell never crosses the wire to the Python process.
            wire_cap = min(ROW_WIRE_CAP, cap)
            parts = [f"CASE WHEN octet_length({payload}) <= {wire_cap} THEN {payload} ELSE NULL END AS __payload"]
            rows, sampled, details = postgis._guarded_rows(conn,item,parts,read_rows=lambda sql,params=None:collector.read(conn,sql,params))
    except postgis.OperationalError as exc:
        raise postgis._clean_connection_error(config,exc) from exc
    finally:
        engine.dispose()
    details.update(dataset_cap_bytes=cap,acquisition_accounted_bytes=collector.accounted,
                   serialized_bytes=collector.serialized,accounting="64x payload storage plus 2048 bytes per row reserved before construction",
                   budget_limited=details["budget_limited"] or collector.limited)
    if collector.limited:
        sampled = True
        details["complete"] = False
    details.update(is_sample=sampled,row_count=len(rows))
    if not rows and collector.limited:
        raise DatasetBudgetError(details)
    from tarsier.timing import observe_acquisition
    observe_acquisition(details.get("drawn_rows",len(rows)),collector.serialized)
    return RawDataset([r["__payload"] for r in rows],details,item,tuple(columns),crs)


def statistics_view(frame, item):
    if item.kind != "vector":
        return frame, None, None
    attrs = frame.drop(columns=[frame.geometry.name]).copy()
    attrs.attrs["sample_identities"] = frame.attrs["sample_identities"]
    attrs["__geom_null"] = frame.geometry.isna()
    geometry_columns = None
    if frame.crs is not None:
        from shapely import centroid, get_x, get_y
        centers = centroid(frame.to_crs(4326).geometry.array)
        attrs["__cx"], attrs["__cy"] = get_x(centers), get_y(centers)
        geometry_columns = ("__cx","__cy")
    return attrs, geometry_columns, "__geom_null"
