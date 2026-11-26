export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "Not available";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export function formatRowCount(count: number | null, isEstimate: boolean, isCapped = false): string {
  if (count === null) return "Not available";
  if (isCapped) return "more than 20,000";
  const formatted = count.toLocaleString();
  return isEstimate ? `~${formatted}` : formatted;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}
