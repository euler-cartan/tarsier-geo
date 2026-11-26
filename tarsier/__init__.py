import os

__version__ = "1.0.0rc1"

# GIS admins' machines (Tarsier's own target users) very often have other
# geospatial software installed  -  QGIS, ArcGIS, a separate PostGIS install  -
# that sets PROJ_LIB/PROJ_DATA/GDAL_DATA system-wide. Those point at a
# *different* PROJ/GDAL version than the one bundled with Tarsier's pinned
# rasterio/pyogrio, and silently hijacking resolution breaks CRS lookups in
# ways that are very hard to diagnose (found via a plain "write a GeoTIFF
# with EPSG:4326" failing locally, traced to this exact conflict). Tarsier
# always uses the PROJ/GDAL data bundled with its own dependencies.
for _var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    os.environ.pop(_var, None)
