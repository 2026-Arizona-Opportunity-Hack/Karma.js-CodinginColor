import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { components } from "../api/types";

type Command =
  | { action: "create"; body: components["schemas"]["DonorCreate"] }
  | { action: "edit"; donorId: number; body: components["schemas"]["DonorUpdate"] }
  | { action: "gift"; donorId: number; body: components["schemas"]["GiftCreate"] };

export function useEntryMutation(actorId: number) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: async (command: Command) =>
      command.action === "gift"
        ? api<components["schemas"]["GiftOut"]>(`/donors/${command.donorId}/gifts`, {
            method: "POST",
            body: command.body,
          })
        : api<components["schemas"]["DonorDetail"]>(
            command.action === "create" ? "/donors" : `/donors/${command.donorId}`,
            { method: command.action === "create" ? "POST" : "PATCH", body: command.body },
          ),
    onSuccess: async (_data, command) => {
      const keys: unknown[][] = [
        ["donors", actorId],
        ["reminders"],
        ["gifts"],
        ["reports"],
        ["dashboard"],
      ];
      if (command.action !== "create")
        keys.push(
          ["donor", actorId, command.donorId],
          ["donor-timeline", actorId, command.donorId],
        );
      await Promise.all(keys.map((queryKey) => client.invalidateQueries({ queryKey })));
    },
    onError: (error, command) => {
      if (error instanceof ApiError && error.status === 403 && command.action !== "create") {
        client.setQueryData<components["schemas"]["DonorDetail"]>(
          ["donor", actorId, command.donorId],
          (donor) =>
            donor
              ? {
                  ...donor,
                  can_act: false,
                  contact_visible: false,
                  email: null,
                  phone: null,
                  notes: null,
                }
              : donor,
        );
      }
    },
  });
}
