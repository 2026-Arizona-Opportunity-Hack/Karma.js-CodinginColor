import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { components } from "../api/types";

export type Message = components["schemas"]["MessageOut"];
type MessageList = components["schemas"]["MessageListOut"];
type DraftBatch = components["schemas"]["DraftBatchOut"];
type MessageCreate = components["schemas"]["MessageCreate"];

const KEY = ["messages"] as const;

export function useMessages() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => api<MessageList>("/messages", { signal }),
    retry: false,
    staleTime: 0,
  });
}

// Every write returns the server's copy of the message; only that copy is shown, never a guess.
function useMessageWrite<T>(run: (input: T) => Promise<Message>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    // A 409 means the message changed elsewhere; show the server's current state.
    onError: () => void client.invalidateQueries({ queryKey: KEY }),
    onSuccess: (saved) => {
      client.setQueryData<MessageList>(KEY, (list) =>
        list
          ? {
              items: list.items.some((m) => m.id === saved.id)
                ? list.items.map((m) => (m.id === saved.id ? saved : m))
                : [saved, ...list.items],
            }
          : list,
      );
      void client.invalidateQueries({ queryKey: KEY });
      // Sending writes a timeline interaction and clears the matching reminder (MSG-7).
      if (saved.status === "sent" || saved.status === "sent_manually") {
        void client.invalidateQueries({ queryKey: ["reminders"] });
        void client.invalidateQueries({
          predicate: (q) =>
            ["donor", "donor-timeline"].includes(String(q.queryKey[0])) &&
            q.queryKey[2] === saved.donor_id,
        });
      }
    },
  });
}

export function useMessageActions() {
  const post = (id: number, action: string) =>
    api<Message>(`/messages/${id}/${action}`, { method: "POST" });
  return {
    edit: useMessageWrite(({ id, subject, body }: { id: number; subject?: string; body: string }) =>
      api<Message>(`/messages/${id}`, { method: "PATCH", body: { subject, body } }),
    ),
    approve: useMessageWrite((id: number) => post(id, "approve")),
    send: useMessageWrite((id: number) => post(id, "send")),
    markSent: useMessageWrite((id: number) => post(id, "mark-sent")),
    cancel: useMessageWrite((id: number) => post(id, "cancel")),
  };
}

export function useCreateDraft() {
  return useMessageWrite(({ donorId, ...body }: MessageCreate & { donorId: number }) =>
    api<Message>(`/donors/${donorId}/messages`, { method: "POST", body }),
  );
}

export function useDraftQuarterly() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api<DraftBatch>("/messages/draft-quarterly", { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY }),
  });
}
