import { ApiError } from "../api/client.js";
import type { components } from "../api/types";

export type Donor = components["schemas"]["DonorDetail"];
export type Candidate = components["schemas"]["DuplicateCandidate"];

/** Decimal text to cents, without floating-point multiplication or rounding. */
export function amountCents(value: string): number | null {
  if (!/^\d{1,8}(\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return cents > 0 && cents <= 1_000_000_000 ? cents : null;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function duplicateCandidates(error: Error): Candidate[] {
  if (!(error instanceof ApiError) || error.status !== 409 || !record(error.body)) return [];
  if (!record(error.body.error) || error.body.error.code !== "possible_duplicate") return [];
  const items = error.body.candidates;
  if (!Array.isArray(items)) return [];
  return items.flatMap((item) => {
    if (
      !record(item) ||
      !Number.isSafeInteger(item.donor_id) ||
      Number(item.donor_id) <= 0 ||
      typeof item.display_name !== "string" ||
      !["email", "phone", "name_employer"].includes(String(item.match_reason))
    )
      return [];
    return [
      {
        donor_id: Number(item.donor_id),
        display_name: item.display_name,
        match_reason: item.match_reason as Candidate["match_reason"],
        owner:
          record(item.owner) && typeof item.owner.display_name === "string"
            ? {
                id: Number(item.owner.id),
                display_name: item.owner.display_name,
                is_active: item.owner.is_active !== false,
              }
            : null,
      },
    ];
  });
}

export function serverFields(error: Error): Record<string, string> {
  if (!(error instanceof ApiError) || !record(error.body) || !Array.isArray(error.body.detail))
    return {};
  return Object.fromEntries(
    error.body.detail.flatMap((item) => {
      if (!record(item) || !Array.isArray(item.loc) || typeof item.msg !== "string") return [];
      return [[String(item.loc.at(-1)), item.msg]];
    }),
  );
}

export function entryError(error: Error): string {
  if (!(error instanceof ApiError))
    return "The connection was interrupted. Saving may have completed. Check the record before trying again. Your entry is kept here.";
  if (error.status === 401)
    return "Your session has ended. Sign in again before saving. Your entry is kept here.";
  if (error.status === 403)
    return "You do not have permission to save this entry. Contact the donor’s owner. Your entry is kept here.";
  if (error.status === 404)
    return "This donor is no longer available. Return to Relationships to check the record. Your entry is kept here.";
  if (error.status === 409)
    return "This entry conflicts with an existing record. Review the details before saving again. No records were overwritten.";
  if (error.status === 501) return "Saving is not available yet. Your entry is kept here.";
  if (error.status >= 500)
    return "The server could not confirm the save. Check the record before trying again. Your entry is kept here.";
  return error.message;
}

export function uncertainSave(error: Error | null) {
  return (
    error !== null &&
    (!(error instanceof ApiError) || (error.status >= 500 && error.status !== 501))
  );
}

export function canEditDonor(donor: Donor) {
  // Backend donor.edit has the same owner/active-super-admin rule as donor.act.
  return donor.can_act && donor.contact_visible;
}
