export type Availability = "full" | "partial" | "none";

export interface ConnectionTypeInfo {
  id: string;
  label: string;
  change_tracking: Availability;
  quality_checks: Availability;
  statistics: Availability;
  notice: string | null;
}

export interface AboutInfo {
  version: string;
  license: string;
  links: Array<{ label: string; href: string }>;
}

export async function getAbout(): Promise<AboutInfo> {
  return getJson("/api/about", "Could not load About information.");
}

async function getJson<T>(url: string, errorMessage: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: errorMessage }));
    throw new Error(payload.detail ?? errorMessage);
  }
  return res.json();
}

export async function getConnectionTypes(): Promise<ConnectionTypeInfo[]> {
  return getJson("/api/connections/types", "Could not load connection types.");
}

export interface SavedConnection {
  id: string;
  name: string;
  type: string;
  config: Record<string, unknown>;
  last_checked_at: string | null;
  last_status: string | null;
}

export async function getConnections(): Promise<SavedConnection[]> {
  return getJson("/api/connections", "Could not load connections.");
}

export interface CreateConnectionRequest {
  name: string;
  type: string;
  config: Record<string, unknown>;
  password?: string;
}

export async function createConnection(body: CreateConnectionRequest): Promise<{ id: string }> {
  const res = await fetch("/api/connections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not create the connection." }));
    throw new Error(payload.detail ?? "Could not create the connection.");
  }
  return res.json();
}

export interface OverviewLayerRow {
  schema: string;
  name: string;
  kind: "vector" | "raster" | "tabular";
  geometry_type: string | null;
  srid: number | null;
  row_count: number | null;
  row_count_is_estimate: boolean;
  row_count_is_capped?: boolean;
  size_bytes: number | null;
  has_index: boolean | null;
  last_modified: string | null;
  is_stale: boolean;
  is_heavy: boolean;
  health_score: number | null;
  health_components: HealthComponents;
  health_is_sample?: boolean;
  readable?: boolean;
}

export interface HealthComponents {
  quality: number | null;
  freshness: number | null;
  completeness: number | null;
}

export interface ProjectionGroup {
  srid: number | null;
  layer_count: number;
  is_majority: boolean;
}

export interface OverviewSummary {
  connection_id: string;
  connection_name: string;
  connection_type: string;
  last_scanned_at: string | null;
  ever_scanned: boolean;
  total_layers: number;
  relationship_count: number;
  total_size_bytes: number | null;
  health_score: number | null;
  health_coverage_count: number;
  health_components: HealthComponents;
  health_is_sample?: boolean;
  no_permission_count: number;
  source_notice?: string | null;
  layers: OverviewLayerRow[];
  projections: ProjectionGroup[];
}

export async function getOverview(connectionId: string): Promise<OverviewSummary> {
  return getJson(`/api/connections/${connectionId}/overview`, "Could not load the overview.");
}

export interface FlowchartNode {
  schema: string;
  name: string;
  kind: "vector" | "raster" | "tabular";
  columns: string[];
  /** Only on items that live in another connection (PRD 14.10). */
  connection_id?: string;
  connection_name?: string;
}

export interface FlowchartLink {
  id: string;
  source_schema: string;
  source_name: string;
  source_column: string;
  target_schema: string;
  target_name: string;
  target_column: string;
  kind: "official" | "guessed" | "user";
  status: "confirmed" | "guessed" | "rejected";
  sample_based: boolean;
  source_connection_id?: string;
  target_connection_id?: string;
}

export interface FlowchartPayload {
  could_not_verify?: number;
  message?: string;
  nodes: FlowchartNode[];
  external_nodes?: FlowchartNode[];
  links: FlowchartLink[];
}

export async function getFlowchart(connectionId: string): Promise<FlowchartPayload> {
  return getJson(`/api/connections/${connectionId}/flowchart`, "Could not load the connection flowchart.");
}

export async function scanFlowchart(connectionId: string): Promise<FlowchartPayload> {
  const res = await fetch(`/api/connections/${connectionId}/flowchart/scan`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not scan connections." }));
    throw new Error(payload.detail ?? "Could not scan connections.");
  }
  return res.json();
}

export interface CrossScanResult {
  could_not_verify?: number;
  message?: string;
  guesses: number;
  skipped_connections: string[];
}

export async function scanCrossConnectionLinks(): Promise<CrossScanResult> {
  const res = await fetch("/api/flowchart/cross/scan", { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not compare your connections." }));
    throw new Error(payload.detail ?? "Could not compare your connections.");
  }
  return res.json();
}

export interface GraphItem {
  key?: string;
  connection_id: string;
  schema: string;
  name: string;
  kind: string;
  connection_name?: string | null;
}

export interface GraphStatus {
  available: boolean;
  built: boolean;
  message: string | null;
}

export interface GraphGroup {
  size: number;
  spans_connections: boolean;
  items: GraphItem[];
}

export interface GraphOverview {
  sources: number;
  items: number;
  relations: number;
  cross_connection_relations: number;
  all_items: GraphItem[];
  groups: GraphGroup[];
  unconnected_items: number;
}

export interface GraphNeighborhood {
  found: boolean;
  nodes: (GraphItem & { distance: number; degree: number; other_connection: boolean })[];
  edges: {
    source: string; target: string; link_id: string; source_column: string; target_column: string;
    kind: string; status: string; sample_based: boolean; cross_connection: boolean;
  }[];
}

export interface GraphPath {
  items: GraphItem[];
  links: { source_column: string; target_column: string; kind: string; status: string; cross_connection: boolean }[];
  length: number;
}

export async function getGraphStatus(): Promise<GraphStatus> {
  return getJson("/api/graph/status", "Could not check the relationship graph.");
}

export async function getGraphOverview(confirmedOnly: boolean): Promise<GraphOverview> {
  return getJson(`/api/graph/overview?confirmed_only=${confirmedOnly}`, "Could not load the relationship graph.");
}

export async function getGraphNeighborhood(
  connectionId: string, schema: string, name: string, hops: number, confirmedOnly: boolean
): Promise<GraphNeighborhood> {
  const params = new URLSearchParams({ connection_id: connectionId, schema, name, hops: String(hops), confirmed_only: String(confirmedOnly) });
  return getJson(`/api/graph/neighborhood?${params}`, "Could not load this item's neighbourhood.");
}

export async function getGraphPath(from: GraphItem, to: GraphItem, confirmedOnly: boolean): Promise<{ connected: boolean; path: GraphPath | null }> {
  const params = new URLSearchParams({
    from_connection_id: from.connection_id, from_schema: from.schema, from_name: from.name,
    to_connection_id: to.connection_id, to_schema: to.schema, to_name: to.name, confirmed_only: String(confirmedOnly),
  });
  return getJson(`/api/graph/path?${params}`, "Could not find a path.");
}

export async function addFlowchartLink(connectionId: string, link: Omit<FlowchartLink, "id" | "kind" | "status" | "sample_based">): Promise<FlowchartLink> {
  const res = await fetch(`/api/connections/${connectionId}/flowchart/links`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(link),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not add that connection." }));
    throw new Error(payload.detail ?? "Could not add that connection.");
  }
  return res.json();
}

export async function updateGuessedLink(connectionId: string, linkId: string, action: "confirm" | "reject"): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/flowchart/links/${linkId}/${action}`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not update that guessed connection." }));
    throw new Error(payload.detail ?? "Could not update that guessed connection.");
  }
}

export async function scanConnection(connectionId: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/scan`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not run the check." }));
    throw new Error(payload.detail ?? "Could not run the check.");
  }
}

export interface CachedItem extends OverviewLayerRow {
  connection_id: string;
  path: string | null;
  bbox: [number, number, number, number] | null;
  raster_width: number | null;
  raster_height: number | null;
  raster_band_count: number | null;
  raster_dtype: string | null;
  raster_nodata: number | null;
  scanned_at: string;
}

export async function getItem(connectionId: string, schema: string, name: string): Promise<CachedItem> {
  const params = new URLSearchParams({ schema, name });
  return getJson(
    `/api/connections/${connectionId}/item?${params}`,
    "Could not load this item  -  it may not have been scanned yet."
  );
}

export interface RasterBand {
  index: number;
  name: string;
  dtype: string | null;
  nodata: number | null;
  minimum: number | null;
  maximum: number | null;
  average: number | null;
  spread: number | null;
  nodata_percent: number | null;
  valid_pixel_count: number;
  histogram: HistogramBin[];
}

export interface RasterDetail {
  width: number | null;
  height: number | null;
  band_count: number | null;
  pixel_size_x: number | null;
  pixel_size_y: number | null;
  pixel_size_unit: string | null;
  crs: string | null;
  srid: number | null;
  footprint: [number, number, number, number] | null;
  acquisition_date: string | null;
  sensor: string | null;
  cloud_cover: number | null;
  dtype: string | null;
  nodata: number | null;
  has_overviews: boolean | null;
  is_sample: boolean;
  sample_note: string | null;
  bands: RasterBand[];
  scanned_at: string;
}

export async function getItemRaster(connectionId: string, schema: string, name: string): Promise<RasterDetail> {
  const params = new URLSearchParams({ schema, name });
  return getJson(`/api/connections/${connectionId}/item/raster?${params}`, "Raster detail hasn't been read for this item yet.");
}

export async function scanItemRaster(connectionId: string, schema: string, name: string, full = false): Promise<void> {
  const params = new URLSearchParams({ schema, name });
  if (full) params.set("full", "true");
  const res = await fetch(`/api/connections/${connectionId}/item/raster/scan?${params}`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not read this raster." }));
    throw new Error(payload.detail ?? "Could not read this raster.");
  }
}

export interface TabularPreview {
  columns: { name: string; type: string }[];
  rows: Record<string, string | number | boolean | null>[];
  scanned_at: string;
}

export async function getItemPreview(connectionId: string, schema: string, name: string): Promise<TabularPreview> {
  const params = new URLSearchParams({ schema, name });
  return getJson(`/api/connections/${connectionId}/item/preview?${params}`, "Sample rows haven't been loaded for this item yet.");
}

export async function scanItemPreview(connectionId: string, schema: string, name: string): Promise<void> {
  const params = new URLSearchParams({ schema, name });
  const res = await fetch(`/api/connections/${connectionId}/item/preview/scan?${params}`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not load sample rows." }));
    throw new Error(payload.detail ?? "Could not load sample rows.");
  }
}

export interface AiSettings {
  provider: "ollama" | "external" | null;
  endpoint_url: string | null;
  model: string | null;
  api_key_set: boolean;
  configured: boolean;
  privacy_warning: string | null;
  ollama_default_endpoint: string;
}

export async function getAiSettings(): Promise<AiSettings> {
  return getJson("/api/settings/ai", "Could not load AI settings.");
}

export async function saveAiSettings(body: {
  provider: "ollama" | "external";
  endpoint_url: string;
  model: string;
  api_key?: string;
  clear_api_key?: boolean;
}): Promise<AiSettings> {
  const res = await fetch("/api/settings/ai", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save AI settings." }));
    throw new Error(payload.detail ?? "Could not save AI settings.");
  }
  return res.json();
}

export interface NotificationSettings {
  host: string | null;
  port: string | null;
  security: string | null;
  sender: string | null;
  username_set: boolean;
  password_set: boolean;
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  return getJson("/api/settings/notifications", "Could not load notification settings.");
}

export async function saveNotificationSettings(body: {
  host: string; port: number; security: "starttls" | "ssl" | "none";
  username: string; sender: string; password?: string; clear_credentials?: boolean;
}): Promise<NotificationSettings> {
  const res = await fetch("/api/settings/notifications", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save notification settings." }));
    throw new Error(payload.detail ?? "Could not save notification settings.");
  }
  return res.json();
}

export async function testNotificationEmail(recipient: string): Promise<{ status: string; message: string }> {
  const res = await fetch("/api/settings/notifications/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Test email could not be sent." }));
    throw new Error(payload.detail ?? "Test email could not be sent.");
  }
  return res.json();
}

export interface HistogramBin {
  start: number;
  end: number;
  count: number;
}

export interface ColumnStats {
  name: string;
  is_numeric: boolean;
  minimum: number | string | null;
  maximum: number | string | null;
  average: number | null;
  empty_count: number;
  unique_count: number;
  top_values: [string, number][];
  messy_groups: string[][];
  out_of_range_count: number | null;
  histogram: HistogramBin[] | null;
}

export type StatsRow = Record<string, string | number | boolean | null>;

export interface TableStats {
  sampled_row_count: number;
  is_sample: boolean;
  columns: ColumnStats[];
  duplicate_row_count: number;
  null_geometry_count: number | null;
  spatial_outlier_count: number | null;
  messy_category_rows: StatsRow[];
  out_of_range_rows: StatsRow[];
  duplicate_rows: StatsRow[];
  map_outlier_rows: StatsRow[];
  null_geometry_rows: StatsRow[];
}

export interface ConnectionStatisticsLayer {
  schema: string;
  name: string;
  kind: "vector" | "raster" | "tabular";
  is_scanned: boolean;
  is_sample: boolean | null;
  sampled_row_count: number | null;
  messy_category_count: number | null;
  duplicate_count: number | null;
  out_of_range_count: number | null;
  map_outlier_count: number | null;
  null_geometry_count: number | null;
}

export async function getConnectionStatistics(connectionId: string): Promise<{ connection_id: string; layers: ConnectionStatisticsLayer[] }> {
  return getJson(`/api/connections/${connectionId}/statistics/summary`, "Could not load connection statistics.");
}

export async function getItemStats(connectionId: string, schema: string, name: string): Promise<TableStats> {
  const params = new URLSearchParams({ schema, name });
  return getJson(`/api/connections/${connectionId}/item/stats?${params}`, "Statistics haven't been run for this item yet.");
}

export async function scanItemStats(connectionId: string, schema: string, name: string, full = false): Promise<void> {
  const params = new URLSearchParams({ schema, name });
  if (full) params.set("full", "true");
  const res = await fetch(`/api/connections/${connectionId}/item/stats/scan?${params}`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not run statistics." }));
    throw new Error(payload.detail ?? "Could not run statistics.");
  }
}

export interface AiQueryResult {
  caption: string;
  rows: StatsRow[];
  is_sample: boolean;
}

export async function runAiQuery(
  connectionId: string,
  schema: string,
  name: string,
  question: string
): Promise<AiQueryResult> {
  const res = await fetch(`/api/connections/${connectionId}/item/ai-query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, schema, name }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not run that question." }));
    throw new Error(payload.detail ?? "Could not run that question.");
  }
  return res.json();
}

export type CheckStatus = "good" | "sampled" | "warning" | "danger" | "not_applicable" | "never_run";

export interface QualityCheckResult {
  skipped_count?: number;
  check_id: string;
  status: CheckStatus;
  fail_count: number;
  message: string | null;
  failing_rows: StatsRow[];
  is_sample: boolean;
  scanned_at: string | null;
}

export interface QualityRule {
  id: string;
  kind: "attribute" | "geometry_type" | string;
  field: string;
  operator: string;
  value: string | null;
  geometry_type: string | null;
}

export interface QualityReport {
  columns?: { name: string; type: string }[];
  checks: Record<string, QualityCheckResult>;
  rules: QualityRule[];
  boundary_schema: string | null;
  boundary_name: string | null;
  vector_layers: { schema: string; name: string; geometry_type: string | null }[];
}

export async function getItemQuality(
  connectionId: string,
  schema: string,
  name: string,
  kind: string
): Promise<QualityReport> {
  const params = new URLSearchParams({ schema, name, kind });
  return getJson(`/api/connections/${connectionId}/item/quality?${params}`, "Could not load quality checks.");
}

export async function scanItemQuality(
  connectionId: string,
  schema: string,
  name: string,
  check: string,
  full = false
): Promise<QualityCheckResult> {
  const params = new URLSearchParams({ schema, name, check });
  if (full) params.set("full", "true");
  const res = await fetch(`/api/connections/${connectionId}/item/quality/scan?${params}`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not run that quality check." }));
    throw new Error(payload.detail ?? "Could not run that quality check.");
  }
  const body = await res.json();
  return body.check;
}

export async function saveQualityBoundary(
  connectionId: string,
  schema: string,
  name: string,
  boundarySchema: string | null,
  boundaryName: string | null
): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/item/quality/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema, name, boundary_schema: boundarySchema, boundary_name: boundaryName }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save the boundary layer." }));
    throw new Error(payload.detail ?? "Could not save the boundary layer.");
  }
}

export async function createQualityRule(
  connectionId: string,
  schema: string,
  name: string,
  body: { kind: string; field: string; operator: string; value?: string | null; geometry_type?: string | null }
): Promise<QualityRule> {
  const res = await fetch(`/api/connections/${connectionId}/item/quality/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema, name, ...body }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save that rule." }));
    throw new Error(payload.detail ?? "Could not save that rule.");
  }
  return res.json();
}

export async function updateQualityRule(
  connectionId: string,
  ruleId: string,
  schema: string,
  name: string,
  body: { kind: string; field: string; operator: string; value?: string | null; geometry_type?: string | null }
): Promise<QualityRule> {
  const res = await fetch(`/api/connections/${connectionId}/item/quality/rules/${ruleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schema, name, ...body }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not update that rule." }));
    throw new Error(payload.detail ?? "Could not update that rule.");
  }
  return res.json();
}

export async function deleteQualityRule(connectionId: string, ruleId: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/item/quality/rules/${ruleId}`, { method: "DELETE" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not delete that rule." }));
    throw new Error(payload.detail ?? "Could not delete that rule.");
  }
}

export async function testAiSettings(body: {
  provider: "ollama" | "external";
  endpoint_url: string;
  model: string;
  api_key?: string;
}): Promise<{ status: string; reply: string; model: string }> {
  const res = await fetch("/api/settings/ai/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not reach the AI endpoint." }));
    throw new Error(payload.detail ?? "Could not reach the AI endpoint.");
  }
  return res.json();
}

export interface ChangeEvent {
  id: string;
  occurred_at: string;
  db_user: string | null;
  action: string;
  schema: string;
  name: string;
  feature_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  txid: string | null;
  source: string;
  is_mass: boolean;
  changed_fields: string[];
}

export interface VolumeBar {
  date: string;
  count: number;
  insert: number;
  update: number;
  delete: number;
  schema: number;
  is_spike: boolean;
}

export interface ChangeReport {
  total: number;
  by_action: Record<string, number>;
  mass_batches: number;
  schema_changes: number;
  unknown_who: number;
  period_start?: string;
  period_end?: string;
  generated_at?: string;
  interval?: string;
  id?: string;
}

export interface ChangesPayload {
  tracking_health?: TrackingHealth;
  available: boolean;
  mode: string;
  reason: string | null;
  events: ChangeEvent[];
  /** Everything the filters match. `events` holds only the newest page of it. */
  total_events?: number;
  action_counts?: Record<string, number>;
  truncated?: boolean;
  volume: VolumeBar[];
  report?: ChangeReport | null;
  report_interval?: string | null;
}

export interface TrackingHealth {
  status: string;
  logging_failures?: number | null;
  logger_version?: string;
  missing_trigger_count?: number | null;
  acknowledged_failures?: number;
  acknowledged_at?: string | null;
  unacknowledged_failures?: number | null;
}

export async function acknowledgeTrackingFailures(connectionId: string, value: number): Promise<void> {
  await postChangeAction(`/api/connections/${connectionId}/changes/acknowledge`, "Could not mark tracking failures as reviewed.", { acknowledge_failures_up_to: value });
}

export async function getChanges(
  connectionId: string,
  params: Record<string, string> = {}
): Promise<ChangesPayload> {
  const search = new URLSearchParams(params);
  return getJson(`/api/connections/${connectionId}/changes?${search}`, "Could not load changes.");
}

async function postChangeAction(url: string, errorMessage: string, body?: unknown): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: errorMessage }));
    throw new Error(payload.detail ?? errorMessage);
  }
}

export async function syncChanges(connectionId: string): Promise<void> {
  await postChangeAction(`/api/connections/${connectionId}/changes/sync`, "Could not sync changes.");
}

export async function installChangeTriggers(connectionId: string): Promise<void> {
  await postChangeAction(
    `/api/connections/${connectionId}/changes/install-triggers`,
    "Could not install the history log."
  );
}

export async function enableChangePolling(connectionId: string): Promise<void> {
  await postChangeAction(`/api/connections/${connectionId}/changes/enable-polling`, "Could not enable polling.");
}

export async function generateChangeReport(connectionId: string, interval: string): Promise<ChangeReport> {
  const res = await fetch(`/api/connections/${connectionId}/changes/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interval }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not generate the report." }));
    throw new Error(payload.detail ?? "Could not generate the report.");
  }
  return res.json();
}

export async function saveReportSchedule(connectionId: string, interval: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/changes/report/schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interval }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save the schedule." }));
    throw new Error(payload.detail ?? "Could not save the schedule.");
  }
}

export interface AlertKind {
  id: string;
  label: string;
}

export interface AlertRule {
  id: string;
  kind: string;
  title: string;
  target_schema: string;
  target_name: string;
  config: Record<string, string | number | boolean | null>;
  paused: boolean;
  last_triggered_at: string | null;
  last_message: string | null;
  status: string;
}

export interface AlertFire {
  id: string;
  rule_id: string;
  fired_at: string;
  message: string;
  channel: string;
  delivery_status: string;
  delivery_message: string | null;
}

export interface AlertsPayload {
  rules: AlertRule[];
  fires: AlertFire[];
  kinds: AlertKind[];
}

export async function getAlerts(connectionId: string): Promise<AlertsPayload> {
  return getJson(`/api/connections/${connectionId}/alerts`, "Could not load alerts.");
}

export async function createAlert(connectionId: string, body: Record<string, unknown>): Promise<AlertRule> {
  const res = await fetch(`/api/connections/${connectionId}/alerts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save that alert." }));
    throw new Error(payload.detail ?? "Could not save that alert.");
  }
  return res.json();
}

export async function updateAlert(
  connectionId: string,
  ruleId: string,
  body: Record<string, unknown>
): Promise<AlertRule> {
  const res = await fetch(`/api/connections/${connectionId}/alerts/${ruleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not update that alert." }));
    throw new Error(payload.detail ?? "Could not update that alert.");
  }
  return res.json();
}

export async function deleteAlert(connectionId: string, ruleId: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/alerts/${ruleId}`, { method: "DELETE" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not delete that alert." }));
    throw new Error(payload.detail ?? "Could not delete that alert.");
  }
}

export async function evaluateAlerts(connectionId: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/alerts/evaluate`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not evaluate alerts." }));
    throw new Error(payload.detail ?? "Could not evaluate alerts.");
  }
}

export interface AutoNode {
  id: string;
  role: "trigger" | "condition" | "action";
  kind: string;
  config: Record<string, unknown>;
  position?: {x: number; y: number};
}

export interface AutoGraph {
  nodes: AutoNode[];
  edges: { from: string; to: string; branch?: "true" | "false" }[];
}

export interface Automation {
  id: string;
  title: string;
  graph: AutoGraph;
  paused: boolean;
  last_run_at: string | null;
}

export interface AutoCatalog {
  triggers: { id: string; label: string; description?: string }[];
  conditions: { id: string; label: string; description?: string }[];
  actions: { id: string; label: string; description?: string }[];
  templates: { id: string; title: string; blurb: string }[];
}

export interface AutoRun {
  id?: string;
  automation_id?: string;
  ran_at?: string;
  ok: boolean;
  message: string;
  dry_run: boolean;
  trace: { node_id: string; role: string; kind: string; ok: boolean; message?: string }[];
}

export async function getAutomations(connectionId: string): Promise<{ automations: Automation[]; runs: AutoRun[] }> {
  return getJson(`/api/connections/${connectionId}/automations`, "Could not load automations.");
}

export async function getAutomationCatalog(connectionId: string): Promise<AutoCatalog> {
  return getJson(`/api/connections/${connectionId}/automations/catalog`, "Could not load the automation palette.");
}

export async function createAutomation(
  connectionId: string,
  body: Record<string, unknown>
): Promise<Automation> {
  const res = await fetch(`/api/connections/${connectionId}/automations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not save that automation." }));
    throw new Error(payload.detail ?? "Could not save that automation.");
  }
  return res.json();
}

export async function updateAutomation(
  connectionId: string,
  id: string,
  body: Record<string, unknown>
): Promise<Automation> {
  const res = await fetch(`/api/connections/${connectionId}/automations/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not update that automation." }));
    throw new Error(payload.detail ?? "Could not update that automation.");
  }
  return res.json();
}

export async function deleteAutomation(connectionId: string, id: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/automations/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not delete that automation." }));
    throw new Error(payload.detail ?? "Could not delete that automation.");
  }
}

export async function testAutomation(connectionId: string, id: string): Promise<AutoRun> {
  const res = await fetch(`/api/connections/${connectionId}/automations/${id}/test-run`, { method: "POST" });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not test that automation." }));
    throw new Error(payload.detail ?? "Could not test that automation.");
  }
  return res.json();
}

export interface AiChatResult {
  job: string;
  text: string;
  title?: string;
  graph?: AutoGraph;
  facts?: Record<string, unknown>;
  questions?: string[];
}

export async function runAiChat(
  connectionId: string,
  body: { job: string; message?: string; schema?: string; name?: string; check_id?: string; conversation_id?: string }
): Promise<AiChatResult> {
  const res = await fetch(`/api/connections/${connectionId}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: "Could not reach the AI assistant." }));
    throw new Error(payload.detail ?? "Could not reach the AI assistant.");
  }
  return res.json();
}

export async function previewAutomation(connectionId: string, body: {title: string; graph: AutoGraph}): Promise<AutoRun> {
  const response = await fetch(`/api/connections/${connectionId}/automations/preview`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw Error(data.detail || "Could not test automation.");
  return data;
}

export interface AiConversation { id: string; title: string; updated_at: string }
export interface AiMessage { role: "user" | "ai"; text: string }

export async function listAiConversations(connectionId: string): Promise<AiConversation[]> {
  const res = await fetch(`/api/connections/${connectionId}/ai/conversations`);
  if (!res.ok) throw new Error("Could not load past conversations.");
  return (await res.json()).conversations ?? [];
}

export async function getAiConversation(connectionId: string, id: string): Promise<AiMessage[]> {
  const res = await fetch(`/api/connections/${connectionId}/ai/conversations/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error("Could not load that conversation.");
  return (await res.json()).messages ?? [];
}

export async function deleteAiConversation(connectionId: string, id: string): Promise<void> {
  const res = await fetch(`/api/connections/${connectionId}/ai/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Could not delete that conversation.");
}
