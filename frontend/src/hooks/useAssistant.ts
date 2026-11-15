import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { components } from "../api/types";

export type Interpretation = components["schemas"]["InterpretOut"];
export type ProposedAction = components["schemas"]["ProposedAction"];
export type DonorChoice = components["schemas"]["DonorChoice"];

/** Asks the server to turn one sentence into proposed actions. Nothing is saved. */
export function useInterpret() {
  return useMutation({
    retry: false,
    mutationFn: (text: string) =>
      api<Interpretation>("/assistant/interpret", { method: "POST", body: { text } }),
  });
}

/** Runs the existing endpoint the server proposed, only after the person pressed Confirm. */
export function useConfirmAction() {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: (choice: DonorChoice) =>
      api<unknown>(choice.request.path.replace(/^\/api\/app/, ""), {
        method: choice.request.method,
        body: choice.request.body,
      }),
    onSuccess: async () => {
      await Promise.all(
        ["donor", "donor-timeline", "donors", "reminders", "messages"].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
}
