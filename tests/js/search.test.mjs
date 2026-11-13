import test from "node:test";
import assert from "node:assert/strict";

import {
  buildQuery,
  parseQuery,
  matchesFilters,
  filterAssets,
  sanitizeSearchText,
} from "../../web/js/search.mjs";

test("buildQuery percent-encodes &, = and spaces in keys and values", () => {
  const result = buildQuery({ q: "a b&c=d", tag: "pump 1" });
  assert.equal(result, "q=a%20b%26c%3Dd&tag=pump%201");
});

test("buildQuery skips undefined/null/empty but keeps 0 and false", () => {
  const result = buildQuery({
    a: 0,
    b: false,
    c: undefined,
    d: null,
    e: "",
    f: "x",
  });
  assert.equal(result, "a=0&b=false&f=x");
});

test("buildQuery encodes unicode and decodeURIComponent round-trips", () => {
  const result = buildQuery({ q: "résumé ✓" });
  assert.equal(result, `q=${encodeURIComponent("résumé ✓")}`);
  assert.equal(decodeURIComponent(result.slice(2)), "résumé ✓");
});

test("buildQuery returns empty string when nothing remains", () => {
  assert.equal(buildQuery({}), "");
  assert.equal(buildQuery({ a: null, b: "" }), "");
});

test("parseQuery is the inverse of buildQuery with string values", () => {
  const params = { q: "a b&c=d", cost: 0, active: false, tag: "pump 1" };
  const roundTripped = parseQuery(buildQuery(params));
  assert.deepEqual(roundTripped, {
    q: "a b&c=d",
    cost: "0",
    active: "false",
    tag: "pump 1",
  });
  assert.equal(typeof roundTripped.cost, "string");
  assert.equal(typeof roundTripped.active, "string");
});

test("parseQuery handles empty, bare ?, empty segments and encoded values", () => {
  assert.deepEqual(parseQuery(""), {});
  assert.deepEqual(parseQuery("?"), {});
  assert.deepEqual(parseQuery("?a=1&&b=2"), { a: "1", b: "2" });
  assert.deepEqual(parseQuery("novalue"), { novalue: "" });
  assert.deepEqual(parseQuery("q=%26%3D%20x"), { q: "&= x" });
});

test("matchesFilters: case-insensitive substrings, unset filters, 0/false semantics", () => {
  const asset = {
    tag: "PUMP-1",
    name: "Main Pump",
    criticality: "high",
    site_id: "s1",
    archived_at: null,
  };
  assert.equal(matchesFilters(asset, { tag: "pump" }), true);
  assert.equal(matchesFilters(asset, { tag: "PUMP" }), true);
  assert.equal(matchesFilters(asset, { name: "main" }), true);
  assert.equal(matchesFilters(asset, {}), true);
  assert.equal(matchesFilters(asset, { tag: undefined }), true);
  assert.equal(matchesFilters(asset, { tag: null }), true);
  assert.equal(matchesFilters(asset, { tag: "" }), true);
  assert.equal(matchesFilters(asset, { tag: "valve" }), false);
  assert.equal(matchesFilters(asset, { criticality: "high" }), true);
  assert.equal(matchesFilters(asset, { criticality: "low" }), false);
  assert.equal(matchesFilters({ ...asset, criticality: "high" }, { criticality: "high" }), true);
  assert.equal(matchesFilters({ ...asset, archived_at: "2026-01-01T00:00:00Z" }, {}), false);
});

test("matchesFilters archived semantics and empty criticality filter", () => {
  const live = { tag: "PUMP-1", name: "Main Pump", criticality: "high", site_id: "s1", archived_at: null };
  const archived = { tag: "PUMP-2", name: "Old Pump", criticality: "low", site_id: "s2", archived_at: "2026-01-01T00:00:00Z" };
  assert.equal(matchesFilters(archived, {}), false);
  assert.equal(matchesFilters(archived, { includeArchived: true }), true);
  assert.equal(matchesFilters(archived, { includeArchived: false }), false);
  assert.equal(matchesFilters(live, { includeArchived: false }), true);
  assert.equal(matchesFilters(archived, { criticality: "" }), false);
  assert.equal(matchesFilters(archived, { criticality: "", includeArchived: true }), true);
  assert.equal(matchesFilters({ ...archived, archived_at: null }, { site_id: "s2" }), true);
});

test("filterAssets preserves order, subset only, empty filters return all", () => {
  const a = { tag: "PUMP-1", name: "Main Pump", criticality: "high", site_id: "s1", archived_at: null };
  const b = { tag: "VALVE-1", name: "Inlet Valve", criticality: "low", site_id: "s2", archived_at: null };
  const c = { tag: "PUMP-2", name: "Backup Pump", criticality: "medium", site_id: "s1", archived_at: "2026-01-01T00:00:00Z" };
  const list = [a, b, c];
  assert.deepEqual(filterAssets(list, { tag: "pump", includeArchived: true }), [a, c]);
  assert.deepEqual(filterAssets(list, { includeArchived: true }), list);
  assert.deepEqual(filterAssets(list, {}), [a, b]);
  assert.deepEqual(filterAssets([], {}), []);
  assert.deepEqual(filterAssets(list, { tag: "pumpzzz" }), []);
  assert.deepEqual(filterAssets(list, { tag: "valve", includeArchived: true }), [b]);
});

test("sanitizeSearchText trims, collapses runs, lowercases, handles undefined", () => {
  assert.equal(sanitizeSearchText("  A   B  "), "a b");
  assert.equal(sanitizeSearchText(undefined), "");
  assert.equal(sanitizeSearchText(null), "");
  assert.equal(sanitizeSearchText("A\tB\nC"), "a b c");
  assert.equal(sanitizeSearchText("  RÉSUMÉ  "), "résumé");
});
