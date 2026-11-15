import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, ApiError } from "../api/client";
import type { components } from "../api/types";
import { calendarDate } from "../lib/format";
import { QuickNoteSheet } from "./QuickNoteSheet";
import { ErrorState, LoadingLedger } from "./Workspace";
import "./donor-ownership.css";

type Donor = components["schemas"]["DonorDetail"];
const methods = {
  manual: "Manual handoff",
  round_robin: "Initial assignment",
  bulk: "Bulk move",
  merge: "Donor merge",
};

export function DonorOwnership({ donor, actorId }: { donor: Donor; actorId: number }) {
  const client = useQueryClient();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState("");
  const history = useQuery({
    queryKey: ["owner-history", actorId, donor.id],
    queryFn: ({ signal }) =>
      api<components["schemas"]["OwnerHistoryOut"]>(`/donors/${donor.id}/owner-history`, {
        signal,
      }),
    retry: false,
  });
  const members = useQuery({
    queryKey: ["members", actorId],
    queryFn: ({ signal }) => api<components["schemas"]["MemberListOut"]>("/members", { signal }),
    enabled: open,
    staleTime: 0,
    retry: false,
  });
  const refresh = () =>
    Promise.all(
      [
        ["donor", actorId, donor.id],
        ["donor-timeline", actorId, donor.id],
        ["owner-history", actorId, donor.id],
        ["donors", actorId],
        ["reminders"],
        ["members", actorId],
      ].map((queryKey) => client.invalidateQueries({ queryKey })),
    );
  const save = useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["ReassignIn"]) =>
      api<Donor>(`/donors/${donor.id}/reassign`, { method: "POST", body }),
    onSuccess: async () => {
      // Refetch through the existing privacy boundary; never cache a stale contact projection.
      await refresh();
      setOpen(false);
      setNotice("Ownership updated. The handoff is recorded below.");
    },
    onError: () => {
      setConfirmed(false);
      void refresh();
    },
  });
  const forbidden = save.error instanceof ApiError && save.error.status === 403;
  const eligible = members.isError
    ? []
    : (members.data?.items ?? []).filter((m) => m.is_active && m.id !== donor.owner?.id);
  const selected = eligible.find((m) => m.id === Number(target));
  const ready = donor.can_reassign && !forbidden && !!selected && !members.isFetching;
  return (
    <>
      {donor.can_reassign ? (
        <button
          className="button button-secondary"
          onClick={() => {
            save.reset();
            setTarget("");
            setReason("");
            setConfirmed(false);
            setNotice("");
            setOpen(true);
          }}
        >
          Reassign donor
        </button>
      ) : (
        <p className="secondary-text">
          Your current permissions do not allow reassignment of this donor.
        </p>
      )}
      <p className="save-notice" role="status">
        {notice}
      </p>
      <details className="owner-history">
        <summary>Ownership history</summary>
        {history.isError ? (
          <ErrorState error={history.error} retry={() => void history.refetch()} />
        ) : history.isPending ? (
          <LoadingLedger label="Loading ownership history" />
        ) : !history.data.items.length ? (
          <p className="quiet-note">No ownership changes recorded.</p>
        ) : (
          <ol className="relationship-timeline">
            {history.data.items.map((entry) => (
              <li className="trail-event trail-owner_change" key={entry.id}>
                <div className="trail-meta">
                  <span>{methods[entry.method]}</span>
                  <time dateTime={entry.changed_at}>{calendarDate(entry.changed_at)}</time>
                </div>
                <h3>
                  {entry.from_user?.display_name ?? "Unassigned"} → {entry.to_user.display_name}
                </h3>
                <p className="secondary-text">
                  Recorded by {entry.changed_by?.display_name ?? "the system"} ·{" "}
                  {new Intl.DateTimeFormat("en-US", {
                    timeStyle: "short",
                    timeZone: "America/Phoenix",
                  }).format(new Date(entry.changed_at))}{" "}
                  Phoenix time
                </p>
                {entry.reason && <p className="trail-detail">{entry.reason}</p>}
              </li>
            ))}
          </ol>
        )}
      </details>
      <QuickNoteSheet
        open={open}
        title="Carry the care forward"
        donorName={donor.display_name}
        busy={save.isPending}
        onClose={() => setOpen(false)}
        eyebrow="Ownership / A considered handoff"
      >
        <form
          aria-busy={save.isPending}
          onSubmit={(event) => {
            event.preventDefault();
            if (ready && confirmed && !save.isPending)
              save.mutate({ to_user_id: selected.id, reason: reason.trim() || null });
          }}
        >
          <div className="quick-note-body">
            <div className="ownership-transfer">
              <p className="eyebrow">From</p>
              <strong>{donor.owner?.display_name ?? "Unassigned"}</strong>
              <p className="secondary-text">
                {donor.owner && !donor.owner.is_active
                  ? "Inactive member · Needs reassignment"
                  : "Current relationship owner"}
              </p>
            </div>
            {members.isError ? (
              <ErrorState error={members.error} retry={() => void members.refetch()} />
            ) : members.isPending || members.isFetching ? (
              <LoadingLedger label="Loading eligible owners" />
            ) : (
              <>
                <label className="note-field" htmlFor={`${id}-owner`}>
                  New owner
                  <select
                    id={`${id}-owner`}
                    required
                    value={selected ? target : ""}
                    disabled={save.isPending || forbidden || !donor.can_reassign}
                    onChange={(e) => {
                      setTarget(e.target.value);
                      setConfirmed(false);
                    }}
                  >
                    <option value="">Choose an active board member</option>
                    {eligible.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name}
                      </option>
                    ))}
                  </select>
                  <span className="secondary-text">
                    Active members only. The current owner is excluded.
                  </span>
                </label>
                {!eligible.length && (
                  <p role="status">
                    No other active members are available. Try refreshing after a member becomes
                    active.
                  </p>
                )}
              </>
            )}
            <label className="note-field" htmlFor={`${id}-reason`}>
              Reason{" "}
              <span className="secondary-text">
                Optional · Visible to all board members in ownership history.
              </span>
              <textarea
                id={`${id}-reason`}
                rows={3}
                maxLength={2000}
                value={reason}
                disabled={save.isPending}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <label className="ownership-confirm">
              <input
                type="checkbox"
                required
                checked={confirmed}
                disabled={!ready || save.isPending}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              <span>
                I confirm the handoff to{" "}
                <strong>{selected?.display_name ?? "the new owner"}</strong>. Donor access and
                reminders will follow the new ownership.
              </span>
            </label>
            {save.error && (
              <p role="alert" className="save-error">
                {forbidden
                  ? "Permission changed. You cannot reassign this donor. Your reason is kept here; close to review current ownership."
                  : save.error instanceof ApiError && save.error.status === 409
                    ? "This member already owns the donor. Ownership has been refreshed. Choose another owner and confirm again."
                    : `${save.error.message} Review current ownership before retrying; your reason is kept here.`}
              </p>
            )}
            {!donor.can_reassign && !forbidden && (
              <p role="alert">Your current permissions no longer allow this handoff.</p>
            )}
          </div>
          <footer className="quick-note-footer">
            <p className="secondary-text">
              One donor, one intentional handoff. No other relationships will move.
            </p>
            <button className="button" disabled={!ready || !confirmed || save.isPending}>
              {save.isPending ? "Recording handoff…" : "Confirm reassignment"}
            </button>
            <button
              type="button"
              className="text-button"
              disabled={save.isPending}
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </footer>
        </form>
      </QuickNoteSheet>
    </>
  );
}
