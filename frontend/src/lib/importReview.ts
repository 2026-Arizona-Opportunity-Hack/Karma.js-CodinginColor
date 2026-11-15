import type { components } from "../api/types";

export function canAttachGift(
  gift: Pick<components["schemas"]["GiftOut"], "source" | "attribution">,
) {
  return gift.attribution === "anonymous" && gift.source !== "benevity";
}

export function validateImportFile(file: Pick<File, "size" | "name">) {
  if (!/\.(csv|xlsx)$/i.test(file.name)) return "Choose a CSV or XLSX file.";
  if (file.size > 5 * 1024 * 1024) return "File must be at most 5 MB.";
  if (!file.size) return "This file is empty. Choose a file with a header and records.";
  return null;
}
