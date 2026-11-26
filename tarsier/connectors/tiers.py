"""Tiered-feature notices per connection type (PRD §5).

Single source of truth for which features are unavailable per connection
type, and the exact notice text shown before a connection is saved
(FSD §5 step 3). Used by the API; later, by the "Other connections"
connectors themselves (PRD Phase 1.3) once they exist.
"""

from dataclasses import dataclass
from typing import Literal

Availability = Literal["full", "partial", "none"]


@dataclass(frozen=True)
class ConnectionTypeInfo:
    id: str
    label: str
    change_tracking: Availability
    quality_checks: Availability
    statistics: Availability
    notice: str | None  # None only when every feature is fully available


_TYPES: dict[str, ConnectionTypeInfo] = {
    "postgis": ConnectionTypeInfo(
        id="postgis",
        label="PostGIS / PostgreSQL",
        change_tracking="full",
        quality_checks="full",
        statistics="full",
        notice=None,
    ),
    "oracle": ConnectionTypeInfo(
        id="oracle",
        label="Oracle Spatial",
        change_tracking="partial",
        quality_checks="full",
        statistics="full",
        notice=(
            "Change tracking for Oracle Spatial depends on your database's existing "
            "audit setup  -  Tarsier can't guarantee who/when for every change. "
            "Quality checks and statistics are fully supported."
        ),
    ),
    "sqlserver": ConnectionTypeInfo(
        id="sqlserver",
        label="SQL Server",
        change_tracking="partial",
        quality_checks="full",
        statistics="full",
        notice=(
            "Change tracking for SQL Server depends on your database's existing "
            "audit setup  -  Tarsier can't guarantee who/when for every change. "
            "Quality checks and statistics are fully supported."
        ),
    ),
    "files": ConnectionTypeInfo(
        id="files",
        label="Files in folders",
        change_tracking="none",
        quality_checks="full",
        statistics="full",
        notice=(
            "Files connections don't support change tracking  -  Tarsier takes no "
            "snapshots of files in folders. You'll still get statistics and "
            "quality checks."
        ),
    ),
    "arcgis": ConnectionTypeInfo(
        id="arcgis",
        label="ArcGIS Enterprise",
        change_tracking="partial",
        quality_checks="partial",
        statistics="full",
        notice=(
            "Change tracking depends on what your ArcGIS Enterprise instance "
            "exposes. Quality checks are partial  -  only what ArcGIS Enterprise "
            "surfaces is available. Statistics are fully supported."
        ),
    ),
    "geoserver": ConnectionTypeInfo(
        id="geoserver",
        label="Geoserver",
        change_tracking="partial",
        quality_checks="partial",
        statistics="full",
        notice=(
            "Change tracking depends on what your Geoserver instance exposes. "
            "Quality checks are partial  -  only what Geoserver surfaces is "
            "available. Statistics are fully supported."
        ),
    ),
}

# Display order matches PRD §5's table.
_ORDER = ["postgis", "oracle", "sqlserver", "files", "arcgis", "geoserver"]


def list_connection_types() -> list[ConnectionTypeInfo]:
    return [_TYPES[type_id] for type_id in _ORDER]


def get_connection_type_info(type_id: str) -> ConnectionTypeInfo:
    try:
        return _TYPES[type_id]
    except KeyError:
        raise ValueError(f"Unknown connection type: {type_id!r}") from None
