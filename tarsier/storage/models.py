"""ORM models for Tarsier's own SQLite store (TAD §5)."""

import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timestamp that is always UTC, and says so.

    SQLite has no timezone-aware column, so a plain DateTime came back naive
    and was sent to the browser without an offset  -  which the browser then
    read as local time, showing "last scanned" hours off for anyone not on UTC.
    Values are normalised to UTC on the way in and tagged as UTC on the way out.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class ConnectionRecord(Base):
    """A saved connection definition. Credentials are never stored here  -
    only a reference; the actual secret lives in tarsier.storage.secrets.
    """

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    last_checked_at: Mapped[datetime.datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    # Distinct from last_checked_at (set when the connection itself is
    # tested, e.g. at Add-Connection time)  -  this tracks whether a full
    # Overview item-metadata scan (TAD §8) has ever run.
    last_scanned_at: Mapped[datetime.datetime | None] = mapped_column(
        UtcDateTime, nullable=True
    )


class FlowchartLink(Base):
    """A discovered or user-declared relationship for the connection flowchart."""

    __tablename__ = "flowchart_links"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_schema: Mapped[str] = mapped_column(String, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_column: Mapped[str] = mapped_column(String, nullable=False)
    target_schema: Mapped[str] = mapped_column(String, default="")
    target_name: Mapped[str] = mapped_column(String, nullable=False)
    target_column: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    sample_based: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set only for a cross-connection guess (PRD §14.10): the target item lives
    # in this *other* connection; connection_id is then the source side's.
    peer_connection_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class FlowchartNode(Base):
    """Last discovered item snapshot and joinable columns for one connection."""

    __tablename__ = "flowchart_nodes"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    columns_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class ItemMetadataCache(Base):
    """Cached Overview/detail metadata for one item of a connection (TAD §8:
    "compute on demand/schedule, then cache... so dashboards load instantly"  -
    never recomputed on every page load, only when a scan runs).
    """

    __tablename__ = "item_metadata_cache"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)

    kind: Mapped[str] = mapped_column(String, nullable=False)
    geometry_type: Mapped[str | None] = mapped_column(String, nullable=True)
    srid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[str | None] = mapped_column(String, nullable=True)

    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count_is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count_is_capped: Mapped[bool] = mapped_column(Boolean, default=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_index: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String, nullable=True)

    raster_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_band_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raster_dtype: Mapped[str | None] = mapped_column(String, nullable=True)
    raster_nodata: Mapped[float | None] = mapped_column(Float, nullable=True)

    scanned_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class StatsCache(Base):
    """Cached statistics (PRD §7.2) for one item  -  same caching rule as
    ItemMetadataCache: computed on demand, never on page load (TAD §8).
    Stored as one JSON blob (TableStats, via dataclasses.asdict) rather
    than a normalized per-column schema  -  simpler, and nothing here is
    ever queried by column name from SQL.
    """

    __tablename__ = "stats_cache"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)

    stats_json: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class RasterDetailCache(Base):
    """Cached raster detail (PRD §8) for one raster item  -  computed on demand,
    never on page load (TAD §8). One JSON blob (RasterDetail via asdict)."""

    __tablename__ = "raster_detail_cache"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)

    detail_json: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class MapPreviewCache(Base):
    __tablename__ = "map_preview_cache"
    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    preview_json: Mapped[str] = mapped_column(Text)


class ItemPreviewCache(Base):
    """Cached column schema + first rows of a tabular item (FSD §7's "sample
    rows table"), read gently once and reused (TAD §8)."""

    __tablename__ = "item_preview_cache"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)

    preview_json: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class QualityCheckCache(Base):
    """Cached result of one quality check on one item (TAD §8)."""

    __tablename__ = "quality_check_cache"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    check_id: Mapped[str] = mapped_column(String, primary_key=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class QualityRule(Base):
    """User-defined attribute or geometry-type rule (PRD §7.3, FSD §9)."""

    __tablename__ = "quality_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    schema: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # attribute | geometry_type
    field: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    geometry_type: Mapped[str | None] = mapped_column(String, nullable=True)


class QualitySettings(Base):
    """Per-item quality options  -  currently the user-picked boundary layer."""

    __tablename__ = "quality_settings"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    boundary_schema: Mapped[str | None] = mapped_column(String, nullable=True)
    boundary_name: Mapped[str | None] = mapped_column(String, nullable=True)


class ChangeEvent(Base):
    """Synced change log (PRD §7.4)  -  Tarsier's copy, not the user DB."""

    __tablename__ = "change_events"
    # The Changes screen, alerts and reports all read "this connection, newest
    # first" or a date window; without this every read scans the whole history.
    __table_args__ = (Index("ix_change_events_connection_time", "connection_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    occurred_at: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)
    db_user: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    schema: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    feature_id: Mapped[str | None] = mapped_column(String, nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    txid: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # trigger | poll
    is_mass: Mapped[bool] = mapped_column(Boolean, default=False)
    source_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EventCaptureCursor(Base):
    """Monotonic local capture order, retained when cached events are pruned."""

    __tablename__ = "event_capture_cursors"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class ChangeFingerprint(Base):
    """Last polling snapshot of one row (TAD Phase 5 fallback)."""

    __tablename__ = "change_fingerprints"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    feature_id: Mapped[str] = mapped_column(String, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String, nullable=False)


class ChangeFingerprintSnapshot(Base):
    """Distinguish an empty baseline from a table never polled."""
    __tablename__ = "change_fingerprint_snapshots"
    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    schema: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)


class ChangeTrackingState(Base):
    """Per-connection capture mode, sync cursor, and report schedule."""

    __tablename__ = "change_tracking_state"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)  # triggers | polling | none
    last_source_log_id: Mapped[int] = mapped_column(Integer, default=0)
    utc_cache_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_failures: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_sync_at: Mapped[datetime.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    report_interval: Mapped[str | None] = mapped_column(String, nullable=True)  # daily | weekly
    last_report_at: Mapped[datetime.datetime | None] = mapped_column(UtcDateTime, nullable=True)


class ChangeReport(Base):
    """Generated daily/weekly change summary (PRD §7.4)."""

    __tablename__ = "change_reports"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    interval: Mapped[str] = mapped_column(String, nullable=False)
    period_start: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)
    period_end: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)


class AlertRule(Base):
    """User-defined alert (PRD §7.5, FSD §11.1)."""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    target_schema: Mapped[str] = mapped_column(String, default="")
    target_name: Mapped[str] = mapped_column(String, default="")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_triggered_at: Mapped[datetime.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_checkpoint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_log_checkpoint: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AlertFire(Base):
    """One firing of an alert rule."""

    __tablename__ = "alert_fires"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    fired_at: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    channel: Mapped[str] = mapped_column(String, default="log")
    delivery_status: Mapped[str | None] = mapped_column(String, default="logged", nullable=True)
    delivery_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertSnapshot(Base):
    """Previous item/quality snapshot so alerts can diff (TAD Phase 6)."""

    __tablename__ = "alert_snapshots"

    connection_id: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    taken_at: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)


class Automation(Base):
    """When → if → do graph (PRD §7.6)."""

    __tablename__ = "automations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    graph_json: Mapped[str] = mapped_column(Text, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_checkpoint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_log_checkpoint: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AutomationRun(Base):
    """One real or test walk of an automation graph."""

    __tablename__ = "automation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    automation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    ran_at: Mapped[datetime.datetime] = mapped_column(UtcDateTime, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str] = mapped_column(Text, default="")
    trace_json: Mapped[str] = mapped_column(Text, default="[]")


class AppSetting(Base):
    """Non-secret app settings (TAD §5), including AI config minus the key.
    The API key itself is never stored here  -  see tarsier.storage.secrets.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class FlowchartScanOutcome(Base):
    __tablename__ = "flowchart_scan_outcomes"
    scope: Mapped[str] = mapped_column(String, primary_key=True)
    could_not_verify: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text)


class RunTiming(Base):
    __tablename__ = "run_timings"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str | None] = mapped_column(String, index=True)
    started_utc: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class EventReceipt(Base):
    __tablename__ = "event_receipts"
    consumer_kind: Mapped[str] = mapped_column(String, primary_key=True)
    consumer_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_key: Mapped[str] = mapped_column(String, primary_key=True)


class EventReplayUpgrade(Base):
    __tablename__ = "event_replay_upgrade"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)


class RunCheckpoint(Base):
    __tablename__ = "run_checkpoints"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    item_schema: Mapped[str] = mapped_column(String, primary_key=True)
    item_name: Mapped[str] = mapped_column(String, primary_key=True)
    connection_id: Mapped[str] = mapped_column(String, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ChatMessage(Base):
    """One saved AI assistant message, grouped into conversations per connection."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
