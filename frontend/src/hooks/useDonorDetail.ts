import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";
import type { components } from "../api/types";

type Donor = components["schemas"]["DonorDetail"];

export function useDonorDetail(actorId: number, id: number) {
  const options = {
    enabled: Number.isSafeInteger(id) && id > 0,
    retry: (count: number, error: Error) =>
      !(error instanceof ApiError && error.status < 500) && count < 1,
  };
  const donor = useQuery({
    ...options,
    queryKey: ["donor", actorId, id],
    queryFn: async ({ signal }) => {
      const data = await api<Donor>(`/donors/${id}`, { signal });
      // Keep restricted contact fields out of the query cache as well as the DOM.
      return data.contact_visible ? data : { ...data, email: null, phone: null, notes: null };
    },
  });
  const timeline = useQuery({
    ...options,
    enabled: options.enabled && donor.isSuccess && !donor.isError,
    queryKey: ["donor-timeline", actorId, id],
    queryFn: ({ signal }) =>
      api<components["schemas"]["TimelineOut"]>(`/donors/${id}/timeline`, { signal }),
  });
  return { donor, timeline };
}
