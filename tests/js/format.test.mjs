import test from "node:test";
import assert from "node:assert/strict";

import { formatStatus } from "../../web/js/app.mjs";

test("formatStatus trims leading and trailing spaces", () => {
  assert.equal(formatStatus(" open "), "open");
});

test("formatStatus trims tabs and returns empty for empty input", () => {
  assert.equal(formatStatus("\tclosed\t"), "closed");
  assert.equal(formatStatus("   "), "");
});
