import { Check, ExternalLink, Mail, MessageSquareText, PenLine, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { EmptyState, ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import {
  type Message,
  useDraftQuarterly,
  useMessageActions,
  useMessages,
} from "../hooks/useMessages";
import { calendarDate } from "../lib/format";
import "./messages.css";

const QUEUES = {
  draft: { label: "Needs approval", statuses: ["draft"] },
  approved: { label: "Ready to send", statuses: ["approved"] },
  sent: { label: "Sent", statuses: ["sent", "sent_manually"] },
  closed: { label: "Cancelled or failed", statuses: ["cancelled", "failed"] },
} as const satisfies Record<string, { label: string; statuses: readonly Message["status"][] }>;
type Queue = keyof typeof QUEUES;

const KIND: Record<Message["kind"], string> = {
  thank_you: "Thank-you",
  quarterly_update: "Quarterly update",
  lapsed_nudge: "Lapsed-donor note",
  event_invite: "Event invitation",
};

function queueOf(m: Message): Queue {
  return (Object.keys(QUEUES) as Queue[]).find((q) =>
    (QUEUES[q].statuses as readonly string[]).includes(m.status),
  )!;
}

// Three marks: drafted, approved by a person, sent by a person. Text carries the meaning, not colour.
function Stages({ m }: { m: Message }) {
  const reached = [true, m.approved_at != null || m.status !== "draft", m.sent_at != null];
  const closed = m.status === "cancelled" || m.status === "failed";
  return (
    <ol className="letter-stages" aria-label="Approval stages">
      {[
        "Drafted",
        "Approved",
        closed ? (m.status === "failed" ? "Failed" : "Cancelled") : "Sent",
      ].map((label, i) => (
        <li
          key={label}
          className={reached[i] ? "is-reached" : closed && i === 2 ? "is-closed" : ""}
        >
          <span aria-hidden="true" />
          {label}
          <span className="sr-only">{reached[i] ? " (done)" : " (not yet)"}</span>
        </li>
      ))}
    </ol>
  );
}

function DeliveryNote({ m }: { m: Message }) {
  if (m.status === "failed")
    return (
      <p className="delivery-note is-failed" role="status">
        Not delivered: {m.error ?? "the mail provider refused this message."}
      </p>
    );
  if (!m.sent_at) return null;
  const by = m.sent_by?.display_name ?? "a board member";
  const when = calendarDate(m.sent_at);
  if (m.delivery_mode === "dry_run")
    return (
      <p className="delivery-note">
        <span className="dry-run-badge">Dry run</span>
        Recorded {when} by {by}. Nothing was delivered to the donor.
      </p>
    );
  if (m.delivery_mode === "manual")
    return (
      <p className="delivery-note">
        Marked sent {when} by {by} from their own phone.
      </p>
    );
  return (
    <p className="delivery-note">
      Delivered by email {when}, sent by {by}
      {m.provider_ref ? ` · reference ${m.provider_ref}` : ""}.
    </p>
  );
}

function LetterDesk({ m }: { m: Message }) {
  const actions = useMessageActions();
  const [subject, setSubject] = useState(m.subject ?? "");
  const [body, setBody] = useState(m.body);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const editable = m.status === "draft" || m.status === "approved";
  const dirty = body !== m.body || (m.channel === "email" && subject !== (m.subject ?? ""));
  const pending = Object.values(actions).some((a) => a.isPending);
  const error = Object.values(actions).find((a) => a.isError)?.error;
  const reset = () => Object.values(actions).forEach((a) => a.reset());

  return (
    <article className="letter-desk" aria-labelledby="letter-heading">
      <header>
        <p className="eyebrow">
          {KIND[m.kind]} · {m.channel === "email" ? "Email" : "Text message"}
        </p>
        <h2 id="letter-heading" tabIndex={-1}>
          {m.donor_name}
        </h2>
        <p className="letter-meta">
          Drafted {calendarDate(m.created_at)}
          {m.approved_by && ` · approved by ${m.approved_by.display_name}`} ·{" "}
          <Link to={`/donors/${m.donor_id}`}>Open relationship</Link>
        </p>
        <Stages m={m} />
      </header>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          reset();
          actions.edit.mutate({
            id: m.id,
            subject: m.channel === "email" ? subject : undefined,
            body,
          });
        }}
      >
        {m.channel === "email" && (
          <label className="letter-field">
            <span>Subject</span>
            <input
              value={subject}
              maxLength={200}
              readOnly={!editable}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
        )}
        <label className="letter-field">
          <span>Message</span>
          <textarea
            value={body}
            required
            maxLength={5000}
            rows={10}
            readOnly={!editable}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        {m.status === "approved" && dirty && (
          <p className="letter-hint">
            Saving edits returns this message to draft for a new approval.
          </p>
        )}
        {error && (
          <p className="letter-error" role="alert">
            {error instanceof ApiError && error.status === 409
              ? `${error.message} The list has been refreshed.`
              : error.message}
          </p>
        )}
        {(actions.approve.isSuccess || actions.send.isSuccess || actions.markSent.isSuccess) && (
          <p className="sr-only" role="status">
            Saved. This message is now {m.status.replace("_", " ")}.
          </p>
        )}
        <DeliveryNote m={m} />
        {editable && (
          <div className="letter-actions">
            <button className="button button-secondary" type="submit" disabled={!dirty || pending}>
              <PenLine size={16} aria-hidden="true" />
              {actions.edit.isPending ? "Saving…" : "Save edits"}
            </button>
            {m.status === "draft" && (
              <button
                className="button"
                type="button"
                disabled={dirty || pending}
                onClick={() => (reset(), actions.approve.mutate(m.id))}
              >
                <Check size={16} aria-hidden="true" />
                {actions.approve.isPending ? "Approving…" : "Approve message"}
              </button>
            )}
            {m.status === "approved" && m.channel === "email" && (
              <button
                className="button"
                type="button"
                disabled={dirty || pending}
                onClick={() => (reset(), actions.send.mutate(m.id))}
              >
                <Send size={16} aria-hidden="true" />
                {actions.send.isPending ? "Sending…" : "Send email"}
              </button>
            )}
            {m.status === "approved" && m.channel === "sms" && (
              <>
                {m.sms_link && !dirty && (
                  <a className="button button-secondary" href={m.sms_link}>
                    <ExternalLink size={16} aria-hidden="true" />
                    Open in Messages app
                  </a>
                )}
                <button
                  className="button"
                  type="button"
                  disabled={dirty || pending}
                  onClick={() => (reset(), actions.markSent.mutate(m.id))}
                >
                  <Check size={16} aria-hidden="true" />
                  {actions.markSent.isPending ? "Saving…" : "I sent it, mark as sent"}
                </button>
              </>
            )}
            {confirmCancel ? (
              <span className="cancel-confirm" role="group" aria-label="Confirm cancellation">
                <button
                  className="text-button is-danger"
                  type="button"
                  disabled={pending}
                  onClick={() => (reset(), actions.cancel.mutate(m.id))}
                >
                  Yes, cancel this message
                </button>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => setConfirmCancel(false)}
                >
                  Keep it
                </button>
              </span>
            ) : (
              <button className="text-button" type="button" onClick={() => setConfirmCancel(true)}>
                <X size={14} aria-hidden="true" />
                Cancel message
              </button>
            )}
          </div>
        )}
        {m.status === "draft" && dirty && (
          <p className="letter-hint">Save your edits before approving.</p>
        )}
      </form>
    </article>
  );
}

export function MessagesPage() {
  const query = useMessages();
  const quarterly = useDraftQuarterly();
  const [params, setParams] = useSearchParams();
  const selectedId = Number(params.get("message")) || undefined;
  const items = query.data?.items ?? [];
  const selected = items.find((m) => m.id === selectedId);
  // Until a tab is chosen, the queue follows the open message, so it moves with each action.
  const [chosen, setChosen] = useState<Queue | null>(null);
  const queue = chosen ?? (selected ? queueOf(selected) : "draft");
  const visible = items.filter((m) => queueOf(m) === queue);
  const deskRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = "Messages · CIC Compass";
  }, []);
  const open = (m: Message) => {
    setChosen(null);
    setParams({ message: String(m.id) });
    requestAnimationFrame(() => deskRef.current?.querySelector<HTMLElement>("h2")?.focus());
  };

  return (
    <div className="approval-desk">
      <PageMasthead eyebrow="The stewardship ledger / Correspondence" title="Words worth sending.">
        Every message starts as a draft. A board member reads it, approves it and sends it; nothing
        goes to a donor on its own.
      </PageMasthead>
      <div className="desk-toolbar">
        <button
          className="button"
          disabled={quarterly.isPending}
          onClick={() => quarterly.mutate()}
        >
          <Mail size={16} aria-hidden="true" />
          {quarterly.isPending ? "Drafting…" : "Draft quarterly updates for my due donors"}
        </button>
        <p role="status">
          {quarterly.isSuccess &&
            `${quarterly.data.created} new ${quarterly.data.created === 1 ? "draft" : "drafts"}` +
              (quarterly.data.skipped_existing
                ? ` · ${quarterly.data.skipped_existing} already had an open draft`
                : "")}
        </p>
        {quarterly.isError && (
          <p className="letter-error" role="alert">
            {quarterly.error.message}
          </p>
        )}
      </div>
      {query.isPending ? (
        <LoadingLedger label="Loading messages" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <div className="desk-columns">
          <section aria-labelledby="queue-heading">
            <h2 id="queue-heading" className="sr-only">
              Message queues
            </h2>
            <div className="todo-filters" role="group" aria-label="Message status">
              {(Object.keys(QUEUES) as Queue[]).map((q) => (
                <button key={q} aria-pressed={queue === q} onClick={() => setChosen(q)}>
                  {QUEUES[q].label}
                  <span>{items.filter((m) => queueOf(m) === q).length}</span>
                </button>
              ))}
            </div>
            {visible.length ? (
              <ol className="letter-list">
                {visible.map((m) => (
                  <li key={m.id}>
                    <button
                      className="letter-row"
                      aria-current={m.id === selected?.id ? "true" : undefined}
                      onClick={() => open(m)}
                    >
                      {m.channel === "email" ? (
                        <Mail size={16} aria-label="Email" />
                      ) : (
                        <MessageSquareText size={16} aria-label="Text message" />
                      )}
                      <span>
                        <strong>{m.donor_name}</strong>
                        <small>
                          {KIND[m.kind]} · {calendarDate(m.sent_at ?? m.created_at)}
                        </small>
                      </span>
                      {m.delivery_mode === "dry_run" && (
                        <span className="dry-run-badge">Dry run</span>
                      )}
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState title={items.length ? "Nothing in this queue" : "No messages yet"}>
                {items.length
                  ? "Choose another queue to see the rest of your correspondence."
                  : "Draft quarterly updates above, or draft a thank-you from your to-do list."}
              </EmptyState>
            )}
          </section>
          <div ref={deskRef} className="desk-panel">
            {selected ? (
              <LetterDesk key={selected.id} m={selected} />
            ) : (
              <p className="desk-placeholder">Choose a message to read, edit or approve it.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
