import { ArrowUpRight, CalendarDays, RefreshCw, UserRoundX } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { components } from "../api/types";
import { EmptyState, ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import { useMe } from "../hooks/useAuth";
import { useCreateDraft } from "../hooks/useMessages";
import { useReminders } from "../hooks/useReminders";
import { calendarDate } from "../lib/format";
import "./dashboard.css";

type Reminder = components["schemas"]["ReminderOut"];
const categories = {
  thank_you_due: "Thank-you reminders",
  quarterly_due: "Quarterly contacts",
  next_step_due: "Next steps",
} as const;
type Category = keyof typeof categories;

function ReminderRow({ reminder: r }: { reminder: Reminder }) {
  const reassignment = r.type === "needs_reassignment";
  // These are navigation actions. The dossier checks current permissions before writes.
  const destination =
    r.action === "open_next_step"
      ? "next-step"
      : r.action === "log_contact" || r.action === "draft_update"
        ? "log-contact"
        : r.action === "draft_thank_you"
          ? "gift-history"
          : "relationship-owner";
  const action =
    r.action === "open_next_step"
      ? "Open next step"
      : r.action === "log_contact" || r.action === "draft_update"
        ? "Log contact"
        : r.action === "draft_thank_you"
          ? "Review gift"
          : "View ownership";
  return (
    <li className={`todo-row${r.overdue ? " is-overdue" : ""}`}>
      <div className="todo-identity">
        <p className="todo-kind">
          {reassignment ? "Ownership exception" : categories[r.type as Category]}
        </p>
        <h3>{r.donor_name}</h3>
        <p className="todo-context">
          {reassignment
            ? `${r.owner?.display_name ?? "Previous owner"} · Inactive member`
            : `In the care of ${r.owner?.display_name ?? "an unassigned member"}`}
          {r.gift_id != null && <span> · Gift #{r.gift_id}</span>}
          {r.next_step_id != null && <span> · Next step #{r.next_step_id}</span>}
        </p>
      </div>
      <div className="todo-due">
        <span className={`todo-status${r.overdue || reassignment ? " needs-attention" : ""}`}>
          {reassignment ? "Needs an owner" : r.overdue ? "Overdue" : "Due soon"}
        </span>
        {r.due_date ? (
          <time dateTime={r.due_date}>Due {calendarDate(r.due_date)}</time>
        ) : (
          <span>{reassignment ? "Shared board queue" : "No due date provided"}</span>
        )}
      </div>
      <div className="todo-action">
        <Link
          className="button button-secondary"
          to={`/donors/${r.donor_id}#${destination}`}
          aria-label={`${action} for ${r.donor_name}`}
        >
          {action}
          <ArrowUpRight size={16} aria-hidden="true" />
        </Link>
        {(r.action === "draft_thank_you" || r.action === "draft_update") && <DraftButton r={r} />}
      </div>
    </li>
  );
}

// Creates (or reopens, MSG-2) an email draft for a person to read and approve; it never sends.
function DraftButton({ r }: { r: Reminder }) {
  const draft = useCreateDraft();
  const navigate = useNavigate();
  const thanks = r.action === "draft_thank_you";
  return (
    <>
      <button
        className="button"
        disabled={draft.isPending}
        aria-label={`Draft ${thanks ? "a thank-you" : "an update"} for ${r.donor_name}`}
        onClick={() =>
          draft.mutate(
            {
              donorId: r.donor_id,
              kind: thanks ? "thank_you" : "quarterly_update",
              channel: "email",
              gift_id: thanks ? r.gift_id : null,
            },
            { onSuccess: (m) => void navigate(`/messages?message=${m.id}`) },
          )
        }
      >
        {draft.isPending ? "Drafting…" : thanks ? "Draft thank-you" : "Draft update"}
      </button>
      {draft.isError && <small role="alert">{draft.error.message}</small>}
    </>
  );
}

export function DashboardPage() {
  const me = useMe();
  useEffect(() => {
    document.title = "To do · CIC Compass";
  }, []);
  return me.data ? <Dashboard key={me.data.id} actorId={me.data.id} /> : null;
}

function Dashboard({ actorId }: { actorId: number }) {
  const query = useReminders(actorId);
  const [category, setCategory] = useState<"all" | Category>("all");
  // Preserve the server's urgency ordering; never calculate a separate priority.
  const items = query.data?.items ?? [];
  const mine = items.filter((r) => r.type !== "needs_reassignment");
  const unassigned = items.filter((r) => r.type === "needs_reassignment");
  const visible = mine.filter((r) => category === "all" || r.type === category);
  const overdue = mine.filter((r) => r.overdue).length;
  return (
    <div className="stewardship-desk">
      <PageMasthead
        eyebrow="The stewardship ledger / Your working day"
        title="Care, carried forward."
      >
        A thank-you, a conversation, a promise kept. Start with the people who need your attention.
      </PageMasthead>
      <div className="desk-dateline">
        <span>
          <CalendarDays size={16} aria-hidden="true" />
          {new Intl.DateTimeFormat("en-US", {
            dateStyle: "full",
            timeZone: "America/Phoenix",
          }).format(new Date())}
          <small>Phoenix time</small>
        </span>
        <button
          className="text-button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {query.isFetching ? "Refreshing…" : "Refresh reminders"}
        </button>
      </div>
      {query.isPending ? (
        <LoadingLedger label="Loading your reminders" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <nav className="desk-queue-index" aria-label="Work queues">
            <a href="#todo-heading">
              Your to-do <strong>{mine.length}</strong>
            </a>
            <a href="#reassignment-heading">
              Needs reassignment <strong>{unassigned.length}</strong>
              <ArrowUpRight size={14} aria-hidden="true" />
            </a>
          </nav>
          <section className="todo-workspace" aria-labelledby="todo-heading">
            <header className="queue-heading">
              <div>
                <p className="eyebrow">01 / In your care</p>
                <h2 id="todo-heading" tabIndex={-1}>
                  To do <span>{mine.length}</span>
                </h2>
              </div>
              <p>{overdue ? `${overdue} overdue · ` : ""}Most urgent first</p>
            </header>
            <div className="todo-filters" role="group" aria-label="Reminder categories">
              {(
                [["all", "All reminders"], ...Object.entries(categories)] as [
                  "all" | Category,
                  string,
                ][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  aria-pressed={category === value}
                  onClick={() => setCategory(value)}
                >
                  {label}
                  <span>
                    {value === "all" ? mine.length : mine.filter((r) => r.type === value).length}
                  </span>
                </button>
              ))}
            </div>
            <p className="sr-only" role="status">
              {visible.length} reminders shown
            </p>
            {visible.length ? (
              <ol className="todo-list">
                {visible.map((r) => (
                  <ReminderRow
                    key={`${r.type}-${r.donor_id}-${r.gift_id ?? r.next_step_id ?? "donor"}`}
                    reminder={r}
                  />
                ))}
              </ol>
            ) : (
              <EmptyState
                title={mine.length ? "Nothing in this category" : "Your follow-ups are up to date"}
              >
                {mine.length
                  ? "Choose another category to see your other reminders."
                  : "No stewardship reminders are due for your donors. New reminders appear here when they need attention."}
              </EmptyState>
            )}
            <p className="queue-footnote">
              Reminders clear when the related action is saved. Reviewing a record does not complete
              a reminder.
            </p>
          </section>
          <section className="reassignment-workspace" aria-labelledby="reassignment-heading">
            <header className="queue-heading">
              <div>
                <p className="eyebrow">02 / Shared responsibility</p>
                <h2 id="reassignment-heading" tabIndex={-1}>
                  <UserRoundX size={23} aria-hidden="true" />
                  Needs reassignment <span>{unassigned.length}</span>
                </h2>
              </div>
              <p>Visible to every board member</p>
            </header>
            <p className="reassignment-intro">
              These donors are in the care of an inactive member. Review their ownership so the next
              conversation has someone to carry it forward.
            </p>
            {unassigned.length ? (
              <ul className="todo-list">
                {unassigned.map((r) => (
                  <ReminderRow key={r.donor_id} reminder={r} />
                ))}
              </ul>
            ) : (
              <EmptyState title="Every relationship has an active owner">
                No donors currently need reassignment.
              </EmptyState>
            )}
            <p className="queue-footnote">
              Open ownership to review history and reassign when permitted. Viewing this queue does
              not grant permission to change ownership.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
