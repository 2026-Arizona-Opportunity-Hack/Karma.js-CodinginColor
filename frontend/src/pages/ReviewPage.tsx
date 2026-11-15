import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api } from "../api/client";
import type { components } from "../api/types";
import { ImportError } from "../components/ImportWorkspace";
import { QuickNoteSheet } from "../components/QuickNoteSheet";
import { EmptyState, ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import { useMe } from "../hooks/useAuth";
import { canAttachGift } from "../lib/importReview";
import { calendarDate, dollars } from "../lib/format";

type Review = components["schemas"]["ReviewOut"];
type Gift = components["schemas"]["GiftOut"];
type Command =
  | { review: Review; body: components["schemas"]["ReviewDecisionIn"]; label: string }
  | { gift: Gift; donorId: number; label: string };
const REASONS = {
  email_name_conflict: "Shared email, different name",
  phone: "Matching phone / verify identity",
  name_employer: "Similar name and employer / verify identity",
};

export function ReviewPage() {
  const me = useMe();
  const client = useQueryClient();
  const [tab, setTab] = useState<"open" | "decided" | "gifts">("open");
  const [command, setCommand] = useState<Command | null>(null);
  const [message, setMessage] = useState("");
  const [blocked, setBlocked] = useState(false);
  const lock = useRef(false);
  const reviews = useQuery({
    queryKey: ["reviews", me.data?.id, tab],
    queryFn: ({ signal }) =>
      api<components["schemas"]["ReviewListOut"]>(
        `/reviews?status=${tab === "decided" ? "decided" : "open"}`,
        { signal },
      ),
    enabled: !!me.data && tab !== "gifts",
    retry: false,
  });
  const gifts = useQuery({
    queryKey: ["unattributed", me.data?.id],
    queryFn: ({ signal }) =>
      api<components["schemas"]["GiftListOut"]>("/gifts/unattributed", { signal }),
    enabled: !!me.data && tab === "gifts",
    retry: false,
  });
  useEffect(() => {
    document.title = "Identity review / CIC Compass";
  }, []);
  const save = useMutation({
    retry: false,
    mutationFn: async (next: Command): Promise<Review | Gift> =>
      "review" in next
        ? api<Review>(`/reviews/${next.review.id}/decide`, { method: "POST", body: next.body })
        : api<Gift>(`/gifts/${next.gift.id}/attribute`, {
            method: "POST",
            body: { donor_id: next.donorId },
          }),
    onSuccess: async () => {
      setCommand(null);
      setBlocked(false);
      setMessage("Decision saved by the server. Related records have been refreshed.");
      await Promise.all(
        [
          "reviews",
          "unattributed",
          "donors",
          "donor",
          "donor-timeline",
          "gifts",
          "reminders",
          "reports",
        ].map((key) => client.invalidateQueries({ queryKey: [key] })),
      );
    },
    onError: () => {
      setBlocked(true);
    },
    onSettled: () => {
      lock.current = false;
    },
  });
  async function reload() {
    // Refresh before another decision after a conflict or an interrupted response.
    const results = await Promise.all([reviews.refetch(), gifts.refetch()]);
    if (results.every((result) => !result.isError)) {
      setBlocked(false);
      save.reset();
      setCommand(null);
    }
  }
  const query = tab === "gifts" ? gifts : reviews;
  function propose(next: Command) {
    save.reset();
    setCommand(next);
    setMessage("");
  }
  return (
    <div className="import-workspace">
      <PageMasthead eyebrow="People before assumptions" title="Identity review">
        A possible match is a question. Compare the evidence, then choose how these records belong.
      </PageMasthead>
      <nav className="import-tabs" aria-label="Import workspace">
        <Link to="/import">
          <ArrowLeft size={15} aria-hidden="true" /> Upload & reconcile
        </Link>
        <Link aria-current="page" to="/review">
          Identity review
        </Link>
      </nav>
      <div className="import-notice">
        <strong>Review happens after import.</strong>
        <p>
          Compare the incoming identity with possible donors. Pending gifts stay unattributed until
          you decide. Names alone never establish identity.
        </p>
        <details>
          <summary>How decisions affect records</summary>
          <p>
            A source row can represent multiple gifts, or a donor with no gift. Decisions apply to
            all pending gifts belonging to that review and are remembered for future matching.
            Marking anonymous retains gifts; it does not exclude a row.
          </p>
        </details>
      </div>
      <div className="import-review-toolbar">
        <div className="segmented-control" aria-label="Review view">
          {(
            [
              ["open", "Needs review"],
              ["decided", "Decided"],
              ["gifts", "Unattributed gifts"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              aria-pressed={tab === value}
              disabled={save.isPending}
              onClick={() => {
                setTab(value);
                setMessage("");
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="text-button"
          disabled={query.isFetching || save.isPending}
          onClick={() => void reload()}
        >
          Refresh records
        </button>
      </div>
      {message && (
        <p role="status" className="import-notice">
          {message}
        </p>
      )}
      {blocked && !command && (
        <ImportError error={save.error}>
          <button className="button button-secondary" onClick={() => void reload()}>
            Reload before retrying
          </button>
        </ImportError>
      )}
      {query.isPending ? (
        <LoadingLedger label="Loading review records" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : tab === "gifts" ? (
        <>
          <p className="import-result-count">
            {gifts.data?.items.length ?? 0} unattributed gifts returned - up to 500 records.
            Pending-review gifts use Needs review.
          </p>
          {gifts.data?.items.length === 0 && (
            <EmptyState title="No unattributed gifts">
              All available gifts have a donor relationship or are waiting in identity review.
            </EmptyState>
          )}
          {gifts.data?.items.map((gift) => (
            <article className="import-panel gift-review" key={gift.id}>
              <div>
                <p className="eyebrow">
                  Gift #{gift.id} - {gift.source} - {gift.attribution}
                </p>
                <h2>
                  {dollars(gift.gross_cents)}{" "}
                  <span className="secondary-text">
                    {gift.is_matching_gift ? "Employer match" : "Donation"} -{" "}
                    {calendarDate(gift.gift_date)} - {gift.program}
                  </span>
                </h2>
                <p>{gift.payer_name ? `Payer: ${gift.payer_name}` : "No payer provided"}</p>
              </div>
              {canAttachGift(gift) ? (
                <GiftMatch
                  disabled={blocked || save.isPending}
                  onChoose={(donorId, name) =>
                    propose({ gift, donorId, label: `Attach gift #${gift.id} to ${name}` })
                  }
                />
              ) : (
                <p className="import-notice">
                  {gift.source === "benevity" && gift.attribution === "anonymous"
                    ? "This donor chose to stay anonymous. This Benevity gift stays unattributed and still counts in organization revenue."
                    : "Pending identity decision. Use Needs review to resolve the related source record."}
                </p>
              )}
            </article>
          ))}
        </>
      ) : (
        <>
          <p className="import-result-count">
            {reviews.data?.items.length ?? 0}{" "}
            {tab === "open" ? "identity questions" : "saved decisions"} - not a gift count
          </p>
          {reviews.data?.items.length === 0 && (
            <EmptyState title={tab === "open" ? "The review desk is clear" : "No decisions yet"}>
              Import a file to surface possible matches. Every decision here is explicit and
              audited.
            </EmptyState>
          )}
          {reviews.data?.items.map((review) => (
            <ReviewCard
              key={review.id}
              review={review}
              disabled={blocked || save.isPending}
              onChoose={propose}
            />
          ))}
        </>
      )}
      <QuickNoteSheet
        open={!!command}
        title="Confirm identity decision"
        donorName={command?.label ?? ""}
        busy={save.isPending}
        onClose={() => setCommand(null)}
      >
        <div className="import-confirm">
          <p>
            {command && "review" in command
              ? command.body.decision === "anonymous"
                ? "All pending gifts for this review will remain unattributed. This does not exclude or delete a source row or its gifts."
                : command.body.decision === "create_new"
                  ? "Create a separate donor, assign an owner, and link the review's pending gifts to that donor."
                  : "Link the review's pending gifts to the selected existing donor. This does not merge donor records or overwrite their contact fields."
              : "Attach this anonymous gift to the selected donor. Check the identity evidence before proceeding."}
          </p>
          <p>
            This decision is saved immediately and audited. There is no undo action on this screen.
          </p>
          <ImportError error={save.error} />
          {blocked && (
            <p>
              Refresh the records before another attempt. An interrupted response may have followed
              a successful save.
            </p>
          )}
          <div className="import-actions">
            <button
              className="button button-secondary"
              disabled={save.isPending}
              onClick={() => setCommand(null)}
            >
              Back to comparison
            </button>
            {blocked ? (
              <button className="button" disabled={query.isFetching} onClick={() => void reload()}>
                Reload before retrying
              </button>
            ) : (
              <button
                className="button"
                disabled={save.isPending}
                onClick={() => {
                  if (!lock.current && command) {
                    lock.current = true;
                    save.mutate(command);
                  }
                }}
              >
                {save.isPending ? "Saving decision..." : "Save decision"}
              </button>
            )}
          </div>
        </div>
      </QuickNoteSheet>
    </div>
  );
}

function ReviewCard({
  review,
  disabled,
  onChoose,
}: {
  review: Review;
  disabled: boolean;
  onChoose: (command: Command) => void;
}) {
  const [choice, setChoice] = useState("");
  const incomingName =
    typeof review.incoming.display_name === "string"
      ? review.incoming.display_name
      : "Incoming donor";
  const entries = Object.entries(review.incoming).filter(([key]) => !key.startsWith("_"));
  const identityKeys = ["display_name", "email", "phone", "organization"];
  const primary = identityKeys.flatMap((key) => entries.filter(([field]) => field === key));
  const additional = entries.filter(([key]) => !identityKeys.includes(key));
  return (
    <article className="import-panel review-card">
      <div className="import-section-heading">
        <div>
          <p className="eyebrow">
            Review #{review.id} - {review.file ?? "Source file unavailable"}
            {review.row_number != null
              ? ` / file row ${review.row_number + 1} (source ref. ${review.row_number})`
              : ""}
          </p>
          <h2>{incomingName || "Incoming donor"}</h2>
        </div>
        <span className="import-label">
          {review.status === "open" ? "Needs review" : review.status.replaceAll("_", " ")}
        </span>
      </div>
      <div className="identity-comparison">
        <section>
          <h3>Incoming identity</h3>
          <p className="secondary-text">Normalized source fields - not a gift record</p>
          <IdentityFields entries={primary} />
          {!!additional.length && (
            <details className="import-format-help">
              <summary>Additional source fields ({additional.length})</summary>
              <IdentityFields entries={additional} />
            </details>
          )}
        </section>
        <section>
          <h3>Possible existing donors</h3>
          <p className="secondary-text">
            Candidate contacts are not provided by this API. Open a dossier to inspect details you
            can access.
          </p>
          <div className="candidate-list">
            {review.candidates.map((candidate) => (
              <div className="candidate" key={candidate.donor_id}>
                <strong>{candidate.display_name}</strong>
                <p>
                  Donor #{candidate.donor_id} - {candidate.owner?.display_name ?? "Unassigned"}
                </p>
                <p className="match-reason">{REASONS[candidate.match_reason]}</p>
                <Link to={`/donors/${candidate.donor_id}`} target="_blank" rel="noreferrer">
                  Open donor dossier <span className="sr-only">(new tab)</span>
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              </div>
            ))}
            {!review.candidates.length && (
              <p>No active candidates returned. Do not infer a match from a name.</p>
            )}
          </div>
        </section>
      </div>
      {review.status === "open" ? (
        <form
          className="review-decision"
          onSubmit={(event) => {
            event.preventDefault();
            if (!choice || disabled) return;
            const donorId = choice.startsWith("link:") ? Number(choice.slice(5)) : undefined;
            onChoose({
              review,
              body: donorId
                ? { decision: "link", donor_id: donorId }
                : { decision: choice as "create_new" | "anonymous" },
              label: donorId
                ? `Link to ${review.candidates.find((candidate) => candidate.donor_id === donorId)?.display_name}`
                : choice === "create_new"
                  ? `Create a separate donor for ${incomingName}`
                  : "Leave these gifts unattributed",
            });
          }}
        >
          <label className="import-field">
            Decision for review #{review.id}
            <select
              required
              value={choice}
              disabled={disabled}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">Choose after comparing</option>
              {review.candidates.map((candidate) => (
                <option key={candidate.donor_id} value={`link:${candidate.donor_id}`}>
                  Link to {candidate.display_name} (#{candidate.donor_id})
                </option>
              ))}
              <option value="create_new">Create a separate donor</option>
              <option value="anonymous">Leave unattributed (mark anonymous)</option>
            </select>
          </label>
          <button className="button" disabled={disabled || !choice}>
            Review decision <ArrowRight size={16} aria-hidden="true" />
          </button>
        </form>
      ) : (
        <p className="import-footnotes">
          Decided by {review.decided_by?.display_name ?? "a board member"} -{" "}
          {calendarDate(review.decided_at)}. This is a saved decision.
        </p>
      )}
    </article>
  );
}

function IdentityFields({ entries }: { entries: [string, unknown][] }) {
  return (
    <dl className="incoming-fields">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{key.replaceAll("_", " ")}</dt>
          <dd>
            {value === null || value === ""
              ? "Not provided"
              : typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function GiftMatch({
  disabled,
  onChoose,
}: {
  disabled: boolean;
  onChoose: (id: number, name: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const me = useMe();
  const donors = useQuery({
    queryKey: ["donors", me.data?.id, "attribute-search", search],
    queryFn: ({ signal }) =>
      api<components["schemas"]["DonorPage"]>(
        `/donors?scope=all&q=${encodeURIComponent(search)}&page=1&page_size=20`,
        { signal },
      ),
    enabled: !!search,
    retry: false,
  });
  return (
    <div className="gift-match">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setSelected("");
          setSearch(draft.trim());
        }}
      >
        <label className="import-field">
          Find an existing donor
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            required
            disabled={disabled}
          />
        </label>
        <button
          className="button button-secondary"
          disabled={disabled || !draft.trim() || donors.isFetching}
        >
          Search donors
        </button>
      </form>
      {donors.isFetching && <p role="status">Searching donors...</p>}
      <ImportError error={donors.error} />
      {donors.data && (
        <>
          <label className="import-field">
            Select a verified identity
            <select
              value={selected}
              disabled={disabled}
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Choose a donor</option>
              {donors.data.items.map((donor) => (
                <option value={donor.id} key={donor.id}>
                  {donor.display_name} (#{donor.id})
                </option>
              ))}
            </select>
          </label>
          <p className="secondary-text">
            Showing up to 20 of {donors.data.total} results. Refine your search if needed. Confirm
            identity in the donor dossier.
          </p>
          {selected && (
            <Link to={`/donors/${selected}`} target="_blank" rel="noreferrer">
              Open selected donor dossier (new tab)
            </Link>
          )}
          <button
            className="button"
            disabled={disabled || !selected || donors.isFetching}
            onClick={() => {
              const donor = donors.data.items.find((item) => item.id === Number(selected));
              if (donor) onChoose(donor.id, donor.display_name);
            }}
          >
            Attach to Donor
          </button>
        </>
      )}
    </div>
  );
}
