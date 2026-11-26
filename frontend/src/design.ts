/** The v2 design palette for pieces that paint to a canvas (graphs, maps, charts)
 * and so cannot use CSS variables. Keep in step with tokens.css. */
export const palette = {
  ink: "#0c0a09",
  primary: "#292524",
  body: "#4e4e4e",
  muted: "#777169",
  faint: "#a8a29e",
  hairline: "#e7e5e4",
  hairlineStrong: "#d6d3d1",
  canvas: "#f5f5f5",
  canvasSoft: "#fafafa",
  card: "#ffffff",
  surfaceStrong: "#f0efed",
  mint: "#a7e5d3",
  peach: "#f4c5a8",
  lavender: "#c8b8e0",
  sky: "#a8c8e8",
  rose: "#e8b8c4",
  warning: "#b45309",
  danger: "#dc2626",
  success: "#16a34a",
} as const;
