import assert from "node:assert/strict";
import { test } from "node:test";
import { canAttachGift, validateImportFile } from "../.test-build/lib/importReview.js";
import { api, ApiError } from "../.test-build/api/client.js";

test("Benevity anonymous opt-out is precise; other anonymous sources remain attachable", () => {
  for (const source of ["benevity", "zeffy", "generic", "manual"]) {
    assert.equal(canAttachGift({ source, attribution: "anonymous" }), source !== "benevity");
    for (const attribution of ["linked", "pending_review"])
      assert.equal(canAttachGift({ source, attribution }), false);
  }
});
test("upload boundary accepts CSV/XLSX up to the backend 5 MiB limit", () => {
  for (const name of ["donors.csv", "gifts.XLSX"])
    assert.equal(validateImportFile({ name, size: 5 * 1024 * 1024 }), null);
  assert.match(validateImportFile({ name: "x.csv", size: 5 * 1024 * 1024 + 1 }), /5 MB/);
  assert.match(validateImportFile({ name: "x.csv", size: 0 }), /empty/);
  assert.match(validateImportFile({ name: "x.pdf", size: 100 }), /CSV or XLSX/);
});
test("API client preserves multipart boundaries, credentials and decoded CSRF", async () => {
  const original = globalThis.fetch;
  globalThis.document = { cookie: "cic_csrf=synthetic%2Dcsrf" };
  try {
    let count = 0;
    globalThis.fetch = async (url, options) => {
      count++;
      assert.equal(url, "/api/app/imports/preview");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.headers["X-CSRF-Token"], "synthetic-csrf");
      assert.equal(options.headers["Content-Type"], undefined);
      assert.ok(options.body instanceof FormData);
      return Response.json({ batch: { id: 22 } });
    };
    const body = new FormData();
    body.set("source", "generic");
    body.set("file", new Blob(["Date,Amount,Platform"]), "synthetic.csv");
    assert.deepEqual(await api("/imports/preview", { method: "POST", body }), {
      batch: { id: 22 },
    });
    assert.equal(count, 1);
  } finally {
    globalThis.fetch = original;
    delete globalThis.document;
  }
});
test("API client reports backend errors verbatim with status and does not retry commits", async () => {
  const original = globalThis.fetch;
  globalThis.document = { cookie: "" };
  try {
    for (const status of [400, 401, 403, 404, 409, 413, 415, 422, 500, 501]) {
      let count = 0;
      globalThis.fetch = async () => {
        count++;
        return Response.json({ error: { message: "Original backend reason" } }, { status });
      };
      await assert.rejects(
        api("/imports/22/commit", { method: "POST", body: { approved_updates: [] } }),
        (error) =>
          error instanceof ApiError &&
          error.status === status &&
          error.message === "Original backend reason",
      );
      assert.equal(count, 1);
    }
  } finally {
    globalThis.fetch = original;
    delete globalThis.document;
  }
});
