import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";
import type { components, paths } from "../api/types";

export type DonorFilters = NonNullable<paths["/api/app/donors"]["get"]["parameters"]["query"]>;

export function useDonors(actorId: number, filters: DonorFilters) {
  return useQuery({
    queryKey: ["donors", actorId, filters],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== "") params.set(key, String(value));
      });
      return api<components["schemas"]["DonorPage"]>(`/donors?${params}`, { signal });
    },
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
  });
}

export function useDirectoryOptions(actorId: number) {
  const members = useQuery({
    queryKey: ["members", actorId],
    queryFn: ({ signal }) => api<components["schemas"]["MemberListOut"]>("/members", { signal }),
    retry: false,
    staleTime: 60_000,
  });
  const programs = useQuery({
    queryKey: ["programs", actorId],
    queryFn: ({ signal }) => api<components["schemas"]["ProgramListOut"]>("/programs", { signal }),
    retry: false,
    staleTime: 60_000,
  });
  return { members, programs };
}
