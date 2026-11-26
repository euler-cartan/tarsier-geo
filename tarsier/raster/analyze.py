"""Reads one raster and summarises it for the detail page (PRD §8).

Every field is Optional: a missing tag (no sensor, no cloud cover) is a
normal answer shown as "Not available" (FSD §7), never an error.

Big rasters (TAD §8) are summarised from a decimated read  -  at most
SAMPLE_PIXEL_LIMIT pixels per band  -  and flagged `is_sample` so the UI can
label them (DVS §12). A full run (`full=True`) reads every pixel, band by
band, so memory stays bounded to one band at a time.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio

SAMPLE_PIXEL_LIMIT = 4_000_000
HISTOGRAM_BINS = 32

# Tag names seen in the wild for the optional PRD §8 fields (case-insensitive).
_ACQUISITION_TAGS = (
    "acquisitiondatetime", "acquisition_date", "acquisitiondate", "date_acquired",
    "sensing_time", "sensing_date", "datetime", "tifftag_datetime",
)
_SENSOR_TAGS = ("sensor", "sensor_id", "sensor_name", "instrument", "satellite", "platform", "spacecraft_id")
_CLOUD_TAGS = ("cloud_cover", "cloudcover", "cloud_coverage", "cloudy_pixel_percentage", "cloud_cover_assessment")


@dataclass
class HistogramBin:
    start: float
    end: float
    count: int


@dataclass
class BandStats:
    index: int  # 1-based, as GDAL numbers bands
    name: str
    dtype: str | None
    nodata: float | None
    minimum: float | None = None
    maximum: float | None = None
    average: float | None = None
    spread: float | None = None  # standard deviation
    nodata_percent: float | None = None
    valid_pixel_count: int = 0
    histogram: list[HistogramBin] = field(default_factory=list)


@dataclass
class RasterDetail:
    width: int | None = None
    height: int | None = None
    band_count: int | None = None
    pixel_size_x: float | None = None
    pixel_size_y: float | None = None
    pixel_size_unit: str | None = None
    crs: str | None = None
    srid: int | None = None
    footprint: tuple[float, float, float, float] | None = None  # in the raster's own CRS
    acquisition_date: str | None = None
    sensor: str | None = None
    cloud_cover: float | None = None
    dtype: str | None = None
    nodata: float | None = None
    has_overviews: bool | None = None
    is_sample: bool = False
    sample_note: str | None = None
    bands: list[BandStats] = field(default_factory=list)


def _first_tag(tag_sets: list[dict], names: tuple[str, ...]) -> str | None:
    lowered = [{k.lower(): v for k, v in tags.items()} for tags in tag_sets]
    for name in names:
        for tags in lowered:
            value = tags.get(name)
            if value not in (None, ""):
                return str(value)
    return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def summarize_values(values: np.ndarray, total_pixels: int) -> tuple[dict, list[HistogramBin]]:
    """Stats + histogram for the valid (non-nodata, finite) pixels of one band.

    `total_pixels` is how many pixels were looked at, valid or not  -  the
    denominator of the nodata percentage.
    """
    valid = values[np.isfinite(values)] if values.dtype.kind == "f" else values
    valid_count = int(valid.size)
    nodata_percent = round(100.0 * (total_pixels - valid_count) / total_pixels, 4) if total_pixels else None
    if valid_count == 0:
        return {"valid": 0, "nodata_percent": nodata_percent}, []

    minimum = float(valid.min())
    maximum = float(valid.max())
    stats = {
        "valid": valid_count,
        "minimum": minimum,
        "maximum": maximum,
        "average": float(valid.mean(dtype=np.float64)),
        "spread": float(valid.std(dtype=np.float64)),
        "nodata_percent": nodata_percent,
    }
    if minimum == maximum:
        return stats, [HistogramBin(minimum, maximum, valid_count)]
    counts, edges = np.histogram(valid, bins=HISTOGRAM_BINS, range=(minimum, maximum))
    bins = [HistogramBin(float(edges[i]), float(edges[i + 1]), int(counts[i])) for i in range(len(counts))]
    return stats, bins


def _read_band(dataset, band_index: int, *, full: bool) -> tuple[np.ndarray, int, bool]:
    """(valid-pixel array, pixels looked at, was it decimated)."""
    pixels = dataset.width * dataset.height
    shape = None
    decimated = False
    if not full and pixels > SAMPLE_PIXEL_LIMIT:
        scale = (SAMPLE_PIXEL_LIMIT / pixels) ** 0.5
        shape = (max(1, int(dataset.height * scale)), max(1, int(dataset.width * scale)))
        decimated = True
    masked = dataset.read(band_index, out_shape=shape, masked=True)
    total = int(masked.size)
    return masked.compressed(), total, decimated


def analyze_raster_file(path: str | Path, *, full: bool = False) -> RasterDetail:
    with rasterio.open(path) as dataset:
        tag_sets = [dataset.tags()] + [dataset.tags(i) for i in range(1, dataset.count + 1)]
        crs = dataset.crs
        srid = crs.to_epsg() if crs else None
        res_x, res_y = dataset.res
        bounds = dataset.bounds
        unit = None
        if crs:
            unit = "degrees" if crs.is_geographic else (crs.linear_units or None)

        detail = RasterDetail(
            width=dataset.width,
            height=dataset.height,
            band_count=dataset.count,
            pixel_size_x=float(res_x),
            pixel_size_y=float(res_y),
            pixel_size_unit=unit,
            crs=f"EPSG:{srid}" if srid else (crs.to_string() if crs else None),
            srid=srid,
            footprint=(bounds.left, bounds.bottom, bounds.right, bounds.top),
            acquisition_date=_first_tag(tag_sets, _ACQUISITION_TAGS),
            sensor=_first_tag(tag_sets, _SENSOR_TAGS),
            cloud_cover=_to_float(_first_tag(tag_sets, _CLOUD_TAGS)),
            dtype=dataset.dtypes[0] if dataset.dtypes else None,
            nodata=dataset.nodata,
            has_overviews=bool(dataset.overviews(1)) if dataset.count else None,
        )

        any_decimated = False
        for index in range(1, dataset.count + 1):
            values, total, decimated = _read_band(dataset, index, full=full)
            any_decimated = any_decimated or decimated
            stats, bins = summarize_values(values, total)
            description = dataset.descriptions[index - 1]
            detail.bands.append(
                BandStats(
                    index=index,
                    name=description or f"Band {index}",
                    dtype=dataset.dtypes[index - 1],
                    nodata=dataset.nodatavals[index - 1],
                    minimum=stats.get("minimum"),
                    maximum=stats.get("maximum"),
                    average=stats.get("average"),
                    spread=stats.get("spread"),
                    nodata_percent=stats["nodata_percent"],
                    valid_pixel_count=stats["valid"],
                    histogram=bins,
                )
            )
        if any_decimated:
            detail.is_sample = True
            detail.sample_note = f"Based on a sample (about {SAMPLE_PIXEL_LIMIT:,} pixels per band)"
    return detail
