import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DonorUpdateReview } from "../.test-build/components/DonorUpdateReview.js";
import { approvals, toggleField } from "../.test-build/lib/donorUpdates.js";

const updates = [
  {
    donor_id: 7,
    donor_name: "Ada Jones",
    changes: {
      email: { new_value: "new@example.org", old_hidden: true, old_value: "secret@example.org" },
      notes: { new_value: "New note", old_hidden: false, old_value: "Old note" },
    },
  },
];
const noOp = () => {};
function render(selection = {}) {
  return renderToStaticMarkup(
    createElement(DonorUpdateReview, {
      updates,
      selection,
      onToggle: noOp,
      onCancel: noOp,
      onConfirm: noOp,
      busy: false,
    }),
  );
}
test("all fields start unchecked and no update is approved by default", () => {
  assert.equal((render().match(/type="checkbox"/g) ?? []).length, 2);
  assert.equal(render().includes("checked="), false);
  assert.deepEqual(approvals(updates, {}), []);
});
test("only checked, offered fields enter the commit request", () => {
  let selection = toggleField({}, 7, "email");
  assert.deepEqual(approvals(updates, selection), [{ donor_id: 7, fields: ["email"] }]);
  assert.equal((render(selection).match(/checked=""/g) ?? []).length, 1);
  selection = toggleField(selection, 7, "email");
  assert.deepEqual(approvals(updates, selection), []);
  assert.deepEqual(approvals(updates, { 7: ["phone"] }), []);
});
test("hidden contact values never render, even if accidentally supplied", () => {
  assert.equal(render().includes("secret@example.org"), false);
  assert.ok(render().includes("Current value hidden"));
  assert.ok(render().includes("new@example.org"));
});
