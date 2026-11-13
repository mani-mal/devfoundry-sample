// Pure ES module with query encoding and in-memory search/filter helpers.
// Zero DOM access anywhere in this module: every exported function takes
// plain values and returns plain values, so the tests assert on plain
// values only. No fetch/API calls here; no browser storage APIs anywhere.

export function buildQuery(params) {
  const segments = [];
  for (const key of Object.keys(params)) {
    const value = params[key];
    if (value === undefined || value === null || value === "") {
      continue;
    }
    segments.push(
      `${encodeURIComponent(key)}=${encodeURIComponent(value)}`,
    );
  }
  return segments.join("&");
}

export function parseQuery(query) {
  const result = {};
  if (!query || typeof query !== "string") {
    return result;
  }
  const trimmed = trimmedQuery(query);
  if (trimmed === "") {
    return result;
  }
  for (const segment of trimmed.split("&")) {
    if (segment === "") {
      continue;
    }
    const eq = segment.indexOf("=");
    if (eq === -1) {
      const key = decodeURIComponent(segment);
      if (!(key in result)) {
        result[key] = "";
      }
      continue;
    }
    const key = decodeURIComponent(segment.slice(0, eq));
    const value = decodeURIComponent(segment.slice(eq + 1));
    result[key] = value;
  }
  return result;
}

function trimmedQuery(query) {
  return query.startsWith("?") ? query.slice(1) : query;
}

function isUnset(value) {
  return value === undefined || value === null || value === "";
}

function containsText(haystack, needle) {
  return String(haystack ?? "")
    .toLowerCase()
    .includes(String(needle).toLowerCase());
}

export function matchesFilters(asset, filters) {
  const spec = filters ?? {};
  if (!isUnset(spec.tag) && !containsText(asset.tag, spec.tag)) {
    return false;
  }
  if (!isUnset(spec.name) && !containsText(asset.name, spec.name)) {
    return false;
  }
  if (!isUnset(spec.criticality) && asset.criticality !== spec.criticality) {
    return false;
  }
  if (!isUnset(spec.site_id) && asset.site_id !== spec.site_id) {
    return false;
  }
  if (!spec.includeArchived && asset.archived_at) {
    return false;
  }
  return true;
}

export function filterAssets(assets, filters) {
  return (assets ?? []).filter((asset) => matchesFilters(asset, filters));
}

export function sanitizeSearchText(text) {
  if (text === undefined || text === null) {
    return "";
  }
  return String(text).trim().replace(/\s+/g, " ").toLowerCase();
}
