import { useId, useState } from "react";
import {
  useMembersGovernance,
  type Governance,
  type Member,
  type Nomination,
} from "../hooks/useMembersGovernance";
import { QuickNoteSheet } from "./QuickNoteSheet";

type Change = ReturnType<typeof useMembersGovernance>["change"];

const phoenix = (iso: string) =>
  new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Phoenix",
  }).format(new Date(iso)) + " (Phoenix time)";

/** The pending-nomination banner, shown to every member (GOV-2). */
export function NominationBanner({
  nomination,
  actorId,
  busy,
  onAct,
}: {
  nomination: Nomination | null | undefined;
  actorId: number;
  busy: boolean;
  onAct: (kind: "confirm" | "cancel", n: Nomination) => void;
}) {
  if (!nomination) return null;
  const nominator = nomination.nominated_by.id === actorId;
  const nominee = nomination.nominee.id === actorId;
  return (
    <section className="quiet-note nomination-banner" aria-label="Pending super admin nomination">
      <p role="status">
        {nominator ? "You" : nomination.nominated_by.display_name} nominated{" "}
        {nominee ? "you" : nomination.nominee.display_name} as super admin. Confirm or cancel by{" "}
        {phoenix(nomination.expires_at)}.
      </p>
      <div className="nomination-actions">
        {!nominator && (
          <button className="button" disabled={busy} onClick={() => onAct("confirm", nomination)}>
            Confirm super admin
          </button>
        )}
        {(nominator || nominee) && (
          <button
            className="button button-secondary"
            disabled={busy}
            onClick={() => onAct("cancel", nomination)}
          >
            Cancel nomination
          </button>
        )}
      </div>
    </section>
  );
}

/** "Nominate super admin" (while flat) and "Remove my super admin role" (for the holder). */
export function SuperAdminActions({
  gov,
  members,
  actorId,
  hasPending,
  change,
  onDone,
}: {
  gov: Governance;
  members: Member[];
  actorId: number;
  hasPending: boolean;
  change: Change;
  onDone: (message: string) => void;
}) {
  const id = useId();
  const [sheet, setSheet] = useState<"nominate" | "remove" | null>(null);
  const [nominee, setNominee] = useState("");
  const [typed, setTyped] = useState("");
  const holder = gov.super_admin?.id === actorId;
  const active = members.filter((m) => m.is_active);
  const busy = change.isPending;
  const open = (next: "nominate" | "remove") => {
    change.reset();
    setNominee("");
    setTyped("");
    setSheet(next);
  };
  const submit = () => {
    if (busy) return;
    if (sheet === "nominate" && nominee)
      change.mutate(
        { kind: "nominate", nomineeId: Number(nominee) },
        {
          onSuccess: () => {
            setSheet(null);
            onDone("Nomination sent. A different board member must confirm it within 72 hours.");
          },
        },
      );
    else if (sheet === "remove" && typed === "REMOVE")
      change.mutate(
        { kind: "remove" },
        {
          onSuccess: () => {
            setSheet(null);
            onDone("Super admin role removed. The organization is flat again.");
          },
        },
      );
  };
  return (
    <>
      {gov.mode === "flat" && !hasPending && (
        <button
          className="button button-secondary"
          disabled={busy}
          onClick={() => open("nominate")}
        >
          Nominate super admin
        </button>
      )}
      {holder && (
        <button className="text-button danger-text" disabled={busy} onClick={() => open("remove")}>
          Remove my super admin role
        </button>
      )}
      {/* Mounted only while open, so the page keeps exactly one idle dialog. */}
      {sheet !== null && (
        <QuickNoteSheet
          open
          title={sheet === "remove" ? "Step back from super admin" : "Nominate a super admin"}
          donorName="Coding in Color"
          busy={busy}
          onClose={() => !busy && setSheet(null)}
          eyebrow="Members & governance / A considered change"
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="quick-note-body">
              {sheet === "remove" ? (
                <>
                  <p>
                    The organization becomes flat; you stay a board member. Reassignment scope
                    returns to <strong>anyone</strong> and you keep your donors.
                  </p>
                  <label className="note-field" htmlFor={`${id}-remove`}>
                    Type REMOVE to confirm
                    <input
                      id={`${id}-remove`}
                      autoComplete="off"
                      value={typed}
                      disabled={busy}
                      onChange={(e) => setTyped(e.target.value)}
                    />
                  </label>
                </>
              ) : (
                <>
                  <p>
                    Pick an active board member, yourself included. A different member must confirm
                    within 72 hours before the role is granted.
                  </p>
                  <label className="note-field" htmlFor={`${id}-nominee`}>
                    Board member
                    <select
                      id={`${id}-nominee`}
                      value={nominee}
                      disabled={busy}
                      onChange={(e) => setNominee(e.target.value)}
                    >
                      <option value="">Choose a member</option>
                      {active.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.display_name}
                          {m.id === actorId ? " (you)" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
              {change.error && (
                <p role="alert" className="save-error">
                  {change.error.message}
                </p>
              )}
            </div>
            <footer className="quick-note-footer">
              <button
                className={sheet === "remove" ? "button button-danger" : "button"}
                disabled={busy || (sheet === "remove" ? typed !== "REMOVE" : !nominee)}
              >
                {busy
                  ? "Recording change…"
                  : sheet === "remove"
                    ? "Remove my super admin role"
                    : "Send nomination"}
              </button>
              <button
                type="button"
                className="text-button"
                disabled={busy}
                onClick={() => setSheet(null)}
              >
                Cancel
              </button>
            </footer>
          </form>
        </QuickNoteSheet>
      )}
    </>
  );
}
