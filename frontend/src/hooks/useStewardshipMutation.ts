import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";
import type { components } from "../api/types";

type Command =
  | { action: "contact"; body: components["schemas"]["InteractionCreate"] }
  | { action: "set"; body: components["schemas"]["NextStepIn"] }
  | { action: "complete"; stepId: number };

export function useStewardshipMutation(actorId: number, donorId: number) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (command: Command) => {
      if (command.action === "contact")
        return api<components["schemas"]["InteractionOut"]>(`/donors/${donorId}/interactions`, {
          method: "POST",
          body: command.body,
        });
      if (command.action === "set")
        return api<components["schemas"]["NextStepOut"]>(`/donors/${donorId}/next-step`, {
          method: "PUT",
          body: command.body,
        });
      return api<components["schemas"]["NextStepOut"]>(`/next-steps/${command.stepId}/done`, {
        method: "POST",
      });
    },
    onSuccess: async () => {
      await Promise.all(
        [
          ["donor", actorId, donorId],
          ["donor-timeline", actorId, donorId],
          ["donors", actorId],
          ["reminders"],
        ].map((queryKey) => client.invalidateQueries({ queryKey })),
      );
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 403) {
        client.setQueryData<components["schemas"]["DonorDetail"]>(
          ["donor", actorId, donorId],
          (donor) => (donor ? { ...donor, can_act: false } : donor),
        );
      }
      // A concurrent completion/replacement needs fresh server state before another attempt.
      if (error instanceof ApiError && [404, 409].includes(error.status)) {
        void client.invalidateQueries({ queryKey: ["donor", actorId, donorId] });
        void client.invalidateQueries({ queryKey: ["donor-timeline", actorId, donorId] });
      }
    },
  });
}
