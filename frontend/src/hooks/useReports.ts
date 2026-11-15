import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { components } from "../api/types";

export type Summary = components["schemas"]["ReportSummary"];
export type Retention = components["schemas"]["RetentionReport"];

export function useReportSummary() {
  return useQuery({
    queryKey: ["reports", "summary"],
    queryFn: ({ signal }) => api<Summary>("/reports/summary", { signal }),
    retry: false,
  });
}

export function useRetention(basis: Retention["basis"], asOf: string) {
  const params = new URLSearchParams({ basis });
  if (asOf) params.set("as_of", asOf);
  return useQuery({
    queryKey: ["reports", "retention", basis, asOf],
    queryFn: ({ signal }) => api<Retention>(`/reports/retention?${params}`, { signal }),
    retry: false,
    // Keep the previous ledger on screen while a new basis or date loads.
    placeholderData: keepPreviousData,
  });
}
