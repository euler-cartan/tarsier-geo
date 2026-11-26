import { useEffect, useRef } from "react";
import { Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { palette } from "../design";
import type { FeatureCollection } from "geojson";

/** FSD §14 "Map preview" component  -  MapLibre (locked, TAD §3). No base
 * map/tile server is configured (none is required by TAD/PRD and none is
 * guaranteed reachable offline per TAD §2's offline-first goal), so this
 * draws the item's bounding box directly on a plain canvas and fits the
 * view to it  -  enough to show extent and shape at a glance.
 */
function MapPreview({
  bbox,
  points = [],
  height = 160,
  geometry,
}: {
  bbox: [number, number, number, number] | null;
  points?: { x: number; y: number }[];
  height?: number;
  geometry?: FeatureCollection;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const usablePoints = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  const pointsKey = JSON.stringify(usablePoints);
  const geometryKey = JSON.stringify(geometry);
  const bboxKey = JSON.stringify(bbox);

  useEffect(() => {
    if (!containerRef.current) return;
    const pts: { x: number; y: number }[] = pointsKey ? JSON.parse(pointsKey) : [];
    let xmin: number, ymin: number, xmax: number, ymax: number;
    if (bbox && bbox.every(Number.isFinite) && Math.abs(bbox[0]) <= 180 && Math.abs(bbox[2]) <= 180 && Math.abs(bbox[1]) <= 90 && Math.abs(bbox[3]) <= 90) {
      [xmin, ymin, xmax, ymax] = bbox;
    } else if (pts.length) {
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      xmin = Math.min(...xs);
      xmax = Math.max(...xs);
      ymin = Math.min(...ys);
      ymax = Math.max(...ys);
      if (xmin === xmax) {
        xmin -= 0.001;
        xmax += 0.001;
      }
      if (ymin === ymax) {
        ymin -= 0.001;
        ymax += 0.001;
      }
    } else {
      return;
    }
    if (xmin === xmax) {xmin -= .001; xmax += .001;}
    if (ymin === ymax) {ymin -= .001; ymax += .001;}

    const map = new MapLibreMap({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "bg", type: "background", paint: { "background-color": palette.canvasSoft } }],
      },
      bounds: [
        [xmin, ymin],
        [xmax, ymax],
      ],
      fitBoundsOptions: { padding: 20 },
      interactive: false,
      attributionControl: false,
    });
    mapRef.current = map;

    map.on("load", () => {
      map.resize();
      if (geometryKey) {
        map.addSource("layer-features", {type: "geojson", data: JSON.parse(geometryKey)});
        map.addLayer({id:"layer-polygons",type:"fill",source:"layer-features",filter:["==",["geometry-type"],"Polygon"],paint:{"fill-color":palette.primary,"fill-opacity":.25}});
        map.addLayer({id:"layer-lines",type:"line",source:"layer-features",paint:{"line-color":palette.primary,"line-width":2}});
        map.addLayer({id:"layer-points",type:"circle",source:"layer-features",filter:["==",["geometry-type"],"Point"],paint:{"circle-color":palette.primary,"circle-radius":4}});
      }
      map.addSource("extent", {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [xmin, ymin],
                [xmax, ymin],
                [xmax, ymax],
                [xmin, ymax],
                [xmin, ymin],
              ],
            ],
          },
        },
      });
      map.addLayer({
        id: "extent-fill",
        type: "fill",
        source: "extent",
        paint: { "fill-color": palette.primary, "fill-opacity": 0.15 },
      });
      map.addLayer({
        id: "extent-line",
        type: "line",
        source: "extent",
        paint: { "line-color": palette.primary, "line-width": 1.5 },
      });
      if (pts.length) {
        map.addSource("points", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: pts.map((p) => ({
              type: "Feature",
              properties: {},
              geometry: { type: "Point", coordinates: [p.x, p.y] },
            })),
          },
        });
        map.addLayer({
          id: "flag-points",
          type: "circle",
          source: "points",
          paint: { "circle-radius": 5, "circle-color": palette.danger, "circle-stroke-width": 1, "circle-stroke-color": "#ffffff" },
        });
      }
    });

    return () => map.remove();
  }, [bboxKey, pointsKey, geometryKey]);

  if (!bbox && usablePoints.length === 0) {
    return (
      <div
        style={{
          height,
          background: "var(--canvas-soft)",
          border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--ink-faint)",
        }}
        className="t-caption"
      >
        No map preview available
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ height, borderRadius: "var(--radius-md)", border: "1px solid var(--hairline)", overflow: "hidden" }}
    />
  );
}

export default MapPreview;
