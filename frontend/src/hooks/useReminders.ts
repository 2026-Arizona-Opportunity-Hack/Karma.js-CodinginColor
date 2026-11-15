import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { components } from "../api/types";

export function useReminders(actorId: number) {
  return useQuery({
    queryKey: ["reminders", actorId, "mine"],
    queryFn: ({ signal }) =>
      api<components["schemas"]["ReminderListOut"]>("/reminders?scope=mine", { signal }),
    retry: false,
    // Reminders are derived and can change when another board member acts.
    staleTime: 0,
    refetchInterval: 60_000,
  });
}
