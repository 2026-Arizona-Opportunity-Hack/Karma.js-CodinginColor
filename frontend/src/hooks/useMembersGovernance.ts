import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { components } from "../api/types";

export type Governance = components["schemas"]["GovernanceDetail"];
export type Member = components["schemas"]["MemberOut"];
export type Invitation = components["schemas"]["InviteOut"];
export type Nomination = components["schemas"]["NominationOut"];
export type Scope = components["schemas"]["ScopeIn"]["reassign_scope"];

export function useMembersGovernance(actorId: number) {
  const client = useQueryClient();
  const members = useQuery({
    queryKey: ["members", actorId],
    queryFn: ({ signal }) => api<components["schemas"]["MemberListOut"]>("/members", { signal }),
    retry: false,
    staleTime: 0,
  });
  const governance = useQuery({
    queryKey: ["governance", actorId],
    queryFn: ({ signal }) => api<Governance>("/governance", { signal }),
    retry: false,
    staleTime: 0,
  });
  const nomination = useQuery({
    queryKey: ["nomination", actorId],
    queryFn: ({ signal }) => api<Nomination | null>("/governance/nominations", { signal }),
    retry: false,
    staleTime: 0,
  });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["members"] }),
      client.invalidateQueries({ queryKey: ["governance"] }),
      client.invalidateQueries({ queryKey: ["nomination"] }),
      client.invalidateQueries({ queryKey: ["auth", "me"] }),
      client.invalidateQueries({ queryKey: ["reminders"] }),
      // A governance change can remove contact access. Drop old projections before refetching.
      client.resetQueries({
        predicate: (q) =>
          ["donor", "donors", "donor-timeline", "owner-history"].includes(String(q.queryKey[0])),
      }),
    ]);
  };
  const change = useMutation({
    retry: false,
    mutationFn: async (
      action:
        | { kind: "deactivate"; memberId: number }
        | { kind: "scope"; scope: Scope }
        | { kind: "flatten" }
        | { kind: "nominate"; nomineeId: number }
        | { kind: "confirm"; id: number }
        | { kind: "cancel"; id: number }
        | { kind: "remove" },
    ) => {
      if (action.kind === "deactivate")
        await api<Member>(`/members/${action.memberId}/deactivate`, { method: "POST" });
      else if (action.kind === "scope")
        await api<Governance>("/governance/scope", {
          method: "PUT",
          body: { reassign_scope: action.scope } satisfies components["schemas"]["ScopeIn"],
        });
      else if (action.kind === "nominate")
        await api<Nomination>("/governance/nominations", {
          method: "POST",
          body: {
            nominee_user_id: action.nomineeId,
          } satisfies components["schemas"]["NominationIn"],
        });
      else if (action.kind === "confirm" || action.kind === "cancel")
        await api(`/governance/nominations/${action.id}/${action.kind}`, { method: "POST" });
      else if (action.kind === "remove")
        await api<Governance>("/governance/super-admin", {
          method: "DELETE",
          body: { confirm: "REMOVE" } satisfies components["schemas"]["RemoveSuperAdminIn"],
        });
      else await api<Governance>("/governance/flatten", { method: "POST" });
    },
    onSettled: refresh,
  });
  return { members, governance, nomination, change, refresh };
}
