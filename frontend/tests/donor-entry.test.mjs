import assert from "node:assert/strict";
import test from "node:test";
import { api, ApiError } from "../.test-build/api/client.js";
import {
  amountCents,
  canEditDonor,
  duplicateCandidates,
  entryError,
  serverFields,
  uncertainSave,
} from "../.test-build/lib/donorEntry.js";

test("currency preserves exact cents and rejects rounding, exponents and out-of-range values", () => {
  for (const [input, expected] of [
    ["0.29", 29],
    ["1.01", 101],
    ["12.3", 1230],
    ["10000000.00", 1_000_000_000],
    [" 75 ", 7500],
  ])
    assert.equal(amountCents(input), expected);
  for (const input of [
    "",
    "0",
    "0.00",
    "-1",
    "1.234",
    "1e3",
    "$20",
    "1,000",
    "10000000.01",
    "Infinity",
  ])
    assert.equal(amountCents(input), null, input);
});

test("duplicate response exposes only contract candidate fields and rejects unrelated conflicts", () => {
  const body = {
    error: { code: "possible_duplicate" },
    candidates: [
      {
        donor_id: 7,
        display_name: "Synthetic Alex",
        match_reason: "email",
        owner: null,
        email: "private@example.org",
      },
      { donor_id: "not-an-id", display_name: "Invalid", match_reason: "email" },
    ],
  };
  assert.deepEqual(duplicateCandidates(new ApiError(409, "Duplicate", body)), [
    { donor_id: 7, display_name: "Synthetic Alex", match_reason: "email", owner: null },
  ]);
  assert.deepEqual(
    duplicateCandidates(
      new ApiError(409, "Conflict", { ...body, error: { code: "other_conflict" } }),
    ),
    [],
  );
  assert.deepEqual(duplicateCandidates(new ApiError(422, "Invalid", body)), []);
});

test("permission hints require both contact visibility and donor action rights", () => {
  assert.equal(canEditDonor({ can_act: true, contact_visible: true }), true);
  assert.equal(canEditDonor({ can_act: true, contact_visible: false }), false);
  assert.equal(canEditDonor({ can_act: false, contact_visible: true }), false);
});

test("uncertain saves require review while validation and authorization failures remain distinct", () => {
  assert.equal(uncertainSave(new TypeError("Network failure")), true);
  assert.equal(uncertainSave(new ApiError(500, "Internal error")), true);
  for (const status of [400, 401, 403, 404, 409, 422, 501])
    assert.equal(uncertainSave(new ApiError(status, "Failure")), false);
  assert.match(entryError(new ApiError(403, "Forbidden")), /permission/);
  assert.match(entryError(new ApiError(404, "Missing")), /no longer available/);
  assert.match(entryError(new ApiError(409, "Conflict")), /No records were overwritten/);
  assert.deepEqual(
    serverFields(
      new ApiError(422, "Invalid", { detail: [{ loc: ["body", "email"], msg: "Invalid email." }] }),
    ),
    { email: "Invalid email." },
  );
});

test("authenticated client retains duplicate and field errors while sending CSRF and exact JSON", async (t) => {
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.headers["X-CSRF-Token"], "synthetic-token");
    assert.deepEqual(JSON.parse(options.body), { gift_date: "2026-11-14", gross_cents: 29 });
    return new Response(
      JSON.stringify({
        error: { code: "possible_duplicate", message: "Possible existing donor" },
        candidates: [{ donor_id: 7, display_name: "Synthetic", match_reason: "phone" }],
      }),
      { status: 409 },
    );
  });
  globalThis.document = { cookie: "cic_csrf=synthetic-token" };
  try {
    await assert.rejects(
      api("/donors/1/gifts", {
        method: "POST",
        body: { gift_date: "2026-11-14", gross_cents: 29 },
      }),
      (error) => {
        assert.equal(error.status, 409);
        assert.equal(duplicateCandidates(error)[0].donor_id, 7);
        return true;
      },
    );
  } finally {
    delete globalThis.document;
  }
});
