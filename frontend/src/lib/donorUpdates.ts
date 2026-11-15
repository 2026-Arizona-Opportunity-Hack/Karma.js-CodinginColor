import type { components } from "../api/types.js";

export type Update = components["schemas"]["SpreadsheetDonorUpdate"];
export type Approval = components["schemas"]["ApprovedDonorUpdate"];
export type Field = Approval["fields"][number];
export type Selection = Record<number, Field[]>;

export const fieldLabels: Record<Field, string> = {
  name: "Name",
  organization: "Organization",
  email: "Email",
  phone: "Phone",
  notes: "Notes",
};

export function toggleField(selection: Selection, donor: number, field: Field): Selection {
  const fields = selection[donor] ?? [];
  return {
    ...selection,
    [donor]: fields.includes(field)
      ? fields.filter((value) => value !== field)
      : [...fields, field],
  };
}

export function approvals(updates: Update[], selection: Selection): Approval[] {
  return updates.flatMap((update) => {
    const fields = [...new Set(selection[update.donor_id] ?? [])].filter((field) =>
      Object.hasOwn(update.changes, field),
    );
    return fields.length ? [{ donor_id: update.donor_id, fields }] : [];
  });
}
