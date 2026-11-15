import { useState } from "react";
import { Check, Mail, MessageCircle, NotebookPen, Phone, Users } from "lucide-react";

import { ApiError } from "../api/client";
import type { components } from "../api/types";
import { useStewardshipMutation } from "../hooks/useStewardshipMutation";
import { calendarDate } from "../lib/format";
import { phoenixToday, QuickNoteSheet, SaveError } from "./QuickNoteSheet";

type Donor = components["schemas"]["DonorDetail"];
type Timeline = components["schemas"]["TimelineOut"];
const kinds = [
  ["call", "Call", Phone],
  ["text", "Text", MessageCircle],
  ["email", "Email", Mail],
  ["meeting", "Meeting", Users],
  ["note", "Note", NotebookPen],
] as const;

export function LogContact({ donor, actorId }: { donor: Donor; actorId: number }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<components["schemas"]["InteractionCreate"]["kind"]>();
  const [date, setDate] = useState(phoenixToday);
  const [summary, setSummary] = useState("");
  const [notice, setNotice] = useState("");
  const save = useStewardshipMutation(actorId, donor.id);
  const allowed =
    donor.can_act &&
    donor.contact_visible &&
    !(save.error instanceof ApiError && save.error.status === 403);
  return (
    <div className="contact-log-action">
      {allowed && (
        <button
          className="button"
          onClick={() => {
            setOpen(true);
            setNotice("");
          }}
        >
          <NotebookPen size={16} aria-hidden="true" /> Log contact
        </button>
      )}
      <span className="save-notice" role="status">
        {notice}
      </span>
      <QuickNoteSheet
        open={open}
        title="Log a contact"
        donorName={donor.display_name}
        busy={save.isPending}
        onClose={() => setOpen(false)}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!allowed || save.isPending || !kind) return;
            save.mutate(
              {
                action: "contact",
                body: { kind, occurred_on: date, summary: summary.trim() || null },
              },
              {
                onSuccess: () => {
                  setOpen(false);
                  setKind(undefined);
                  setSummary("");
                  setDate(phoenixToday());
                  setNotice("Contact logged.");
                },
              },
            );
          }}
          aria-busy={save.isPending}
        >
          <div className="quick-note-body">
            {donor.do_not_contact && (
              <p className="quiet-note">
                Do not contact: record past contact or an internal note only.
              </p>
            )}
            <fieldset className="contact-kind" disabled={save.isPending || !allowed}>
              <legend>How did you connect?</legend>
              <div className="contact-kind-options">
                {kinds.map(([value, label, Icon]) => (
                  <label key={value}>
                    <input
                      type="radio"
                      name="contact-kind"
                      value={value}
                      required
                      checked={kind === value}
                      onChange={() => setKind(value)}
                    />
                    <span>
                      <Icon size={21} aria-hidden="true" />
                      {label}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="note-field">
              Contact date
              <input
                type="date"
                required
                max={phoenixToday()}
                value={date}
                disabled={save.isPending}
                onChange={(event) => setDate(event.target.value)}
              />
              <span className="secondary-text">Today by default · Phoenix time</span>
            </label>
            <label className="note-field">
              A note for the record <span className="secondary-text">Optional</span>
              <textarea
                rows={4}
                maxLength={2000}
                value={summary}
                disabled={save.isPending}
                onChange={(event) => setSummary(event.target.value)}
                placeholder="What would help the next conversation?"
              />
            </label>
            <SaveError error={save.error} />
            {!allowed && !save.error && (
              <p role="alert" className="save-error">
                Your access has changed. This entry cannot be saved.
              </p>
            )}
          </div>
          <footer className="quick-note-footer">
            <p className="secondary-text">An entry in the timeline. Nothing is sent.</p>
            <button className="button" disabled={save.isPending || !allowed || !kind}>
              {save.isPending ? "Saving contact…" : "Save contact"}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={save.isPending}
              onClick={() => setOpen(false)}
            >
              Close · keep draft
            </button>
          </footer>
        </form>
      </QuickNoteSheet>
    </div>
  );
}

export function NextStep({
  donor,
  actorId,
  timeline,
  timelineReady,
}: {
  donor: Donor;
  actorId: number;
  timeline?: Timeline;
  timelineReady: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState(phoenixToday);
  const [notice, setNotice] = useState("");
  const save = useStewardshipMutation(actorId, donor.id);
  const allowed =
    donor.can_act &&
    donor.contact_visible &&
    !(save.error instanceof ApiError && save.error.status === 403);
  // The detail contract has no step ID. The timeline supplies the actual entity ID.
  // Replacements create new IDs; only the newest step may match the current summary.
  const latest = timeline?.items
    .filter((e) => e.kind === "next_step" && e.entity_id != null)
    .sort((a, b) => b.entity_id! - a.entity_id!)[0];
  const stepId =
    timelineReady &&
    donor.next_step_title &&
    latest?.title === `Next step: ${donor.next_step_title}` &&
    latest.detail === `Due ${donor.next_step_due}`
      ? latest.entity_id
      : null;
  return (
    <section className="next-step-workspace">
      <p className="eyebrow">The next act of care</p>
      <h2>Next step</h2>
      <p className="next-step-title">{donor.next_step_title ?? "No next step set"}</p>
      {donor.next_step_due && (
        <p className="secondary-text">Due {calendarDate(donor.next_step_due)}</p>
      )}
      {allowed && (
        <div className="next-step-actions">
          {donor.next_step_title && (
            <button
              className="button"
              disabled={!stepId || save.isPending}
              onClick={() => {
                if (!stepId || save.isPending) return;
                setNotice("");
                save.mutate(
                  { action: "complete", stepId },
                  {
                    onSuccess: () => setNotice("Next step completed and recorded in the timeline."),
                  },
                );
              }}
            >
              <Check size={16} aria-hidden="true" />
              {save.isPending && !open ? "Completing…" : "Mark complete"}
            </button>
          )}
          <button
            className="text-button"
            disabled={save.isPending}
            onClick={() => {
              setOpen(true);
              setNotice("");
            }}
          >
            {donor.next_step_title ? "Set a new next step" : "Set next step"}
          </button>
          {donor.next_step_title && !stepId && (
            <p className="secondary-text">
              Completion needs the latest timeline entry. If it is unavailable, refresh the timeline
              below.
            </p>
          )}
        </div>
      )}
      <p className="save-notice" role="status">
        {notice}
      </p>
      {!open && <SaveError error={save.error} />}
      <QuickNoteSheet
        open={open}
        title="Set a next step"
        donorName={donor.display_name}
        busy={save.isPending}
        onClose={() => setOpen(false)}
      >
        <form
          aria-busy={save.isPending}
          onSubmit={(event) => {
            event.preventDefault();
            if (!allowed || save.isPending || !title.trim()) return;
            save.mutate(
              { action: "set", body: { title: title.trim(), due_date: due } },
              {
                onSuccess: () => {
                  setOpen(false);
                  setTitle("");
                  setDue(phoenixToday());
                  setNotice("Next step saved.");
                },
              },
            );
          }}
        >
          <div className="quick-note-body">
            <p className="quiet-note">One clear commitment keeps the relationship moving.</p>
            <label className="note-field">
              What happens next?
              <input
                required
                maxLength={200}
                value={title}
                disabled={save.isPending}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Share the student showcase invitation"
              />
            </label>
            <label className="note-field">
              Due date
              <input
                type="date"
                required
                value={due}
                disabled={save.isPending}
                onChange={(event) => setDue(event.target.value)}
              />
            </label>
            {donor.next_step_title && (
              <p className="quiet-note">
                Saving replaces “{donor.next_step_title}”. The previous step stays in the timeline.
              </p>
            )}
            <SaveError error={save.error} />
            {!allowed && !save.error && (
              <p role="alert" className="save-error">
                Your access has changed. This entry cannot be saved.
              </p>
            )}
          </div>
          <footer className="quick-note-footer">
            <button className="button" disabled={save.isPending || !allowed || !title.trim()}>
              {save.isPending ? "Saving next step…" : "Save next step"}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={save.isPending}
              onClick={() => setOpen(false)}
            >
              Close · keep draft
            </button>
          </footer>
        </form>
      </QuickNoteSheet>
    </section>
  );
}
