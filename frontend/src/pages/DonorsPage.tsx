import { ArrowLeft, ArrowRight, ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import type { components } from "../api/types";
import { RelationshipRow } from "../components/RelationshipRow";
import { DonorEntry } from "../components/DonorEntry";
import {
  EmptyState,
  ErrorState,
  LoadingLedger,
  PageMasthead,
  STATUS_LABELS,
} from "../components/Workspace";
import { useMe } from "../hooks/useAuth";
import { useDirectoryOptions, useDonors, type DonorFilters } from "../hooks/useDonors";

type Member = components["schemas"]["MemberRef"];

export function DonorsPage() {
  const me = useMe();
  return me.data ? <Directory actor={me.data} /> : null;
}

function Directory({ actor }: { actor: { id: number; display_name: string } }) {
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [owner, setOwner] = useState<Member | null>(null);
  const [status, setStatus] = useState<DonorFilters["status"]>(undefined);
  const [program, setProgram] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const donors = useDonors(actor.id, {
    scope,
    q: search,
    owner: owner?.id,
    status,
    program,
    page,
    page_size: 20,
  });
  const { members, programs } = useDirectoryOptions(actor.id);
  const hasFilters = Boolean(search || owner || status || program);
  const ownerOptions = [
    ...new Map(
      [
        { id: actor.id, display_name: actor.display_name, is_active: true },
        ...(members.data?.items ?? []),
        ...(donors.data?.items.flatMap((donor) => (donor.owner ? [donor.owner] : [])) ?? []),
        ...(owner ? [owner] : []),
      ].map((member) => [member.id, member]),
    ).values(),
  ];

  useEffect(() => {
    document.title = "Relationships · CIC Compass";
  }, []);

  function reset() {
    setDraft("");
    setSearch("");
    setOwner(null);
    setStatus(undefined);
    setProgram(undefined);
    setPage(1);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setSearch(draft.trim());
    setPage(1);
  }

  const total = donors.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / 20));

  return (
    <>
      <PageMasthead eyebrow="The relationship index" title="Relationships">
        The people and organizations moving Coding in Color’s mission forward.
      </PageMasthead>
      <section className="directory" aria-label="Donor directory">
        <div className="directory-topline">
          <div className="segmented-control" role="group" aria-label="Donor scope">
            {(["mine", "all"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={scope === value}
                onClick={() => {
                  setScope(value);
                  setOwner(null);
                  setPage(1);
                }}
              >
                {value === "mine" ? "My donors" : "All donors"}
              </button>
            ))}
          </div>
          <p className="directory-count" role="status" aria-live="polite">
            {donors.isPending ? (
              "Loading relationships…"
            ) : donors.isError ? (
              "Records unavailable"
            ) : (
              <>
                <strong>{total.toLocaleString()}</strong>{" "}
                {total === 1 ? "relationship" : "relationships"}
                {hasFilters
                  ? " matching your filters"
                  : scope === "mine"
                    ? " in your care"
                    : " across the board"}
              </>
            )}
          </p>
          <DonorEntry mode="create" actorId={actor.id} />
        </div>
        <div className="directory-tools">
          <form className="search-form" role="search" onSubmit={submit}>
            <label className="sr-only" htmlFor="donor-search">
              Search donors by name, email, or organization
            </label>
            <Search size={18} aria-hidden="true" />
            <input
              id="donor-search"
              type="search"
              autoComplete="off"
              maxLength={100}
              placeholder="Search name, email, organization…"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
            <button className="search-submit" type="submit">
              Search
            </button>
          </form>
          <details
            className="filter-disclosure"
            open={filtersOpen}
            onToggle={(event) => setFiltersOpen(event.currentTarget.open)}
          >
            <summary>
              <SlidersHorizontal size={16} aria-hidden="true" />
              Refine relationships
              <ChevronDown className="filter-chevron" size={14} aria-hidden="true" />
            </summary>
            <div className="filter-fields">
              <label>
                Owner
                <select
                  value={owner?.id ?? ""}
                  onChange={(event) => {
                    setOwner(
                      ownerOptions.find((member) => member.id === Number(event.target.value)) ??
                        null,
                    );
                    setPage(1);
                  }}
                >
                  <option value="">Any owner</option>
                  {ownerOptions.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.display_name}
                      {member.id === actor.id ? " (you)" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  value={status ?? ""}
                  onChange={(event) => {
                    setStatus((event.target.value as DonorFilters["status"]) || undefined);
                    setPage(1);
                  }}
                >
                  <option value="">Any status</option>
                  {Object.entries(STATUS_LABELS).map(([key, label]) => (
                    <option
                      value={key}
                      key={key}
                      disabled={key === "thank_you_due" || key === "update_due"}
                    >
                      {label}
                      {key === "thank_you_due" || key === "update_due"
                        ? " (not available yet)"
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Program
                <select
                  value={program ?? ""}
                  disabled={!programs.data}
                  aria-describedby={!programs.data ? "filter-availability" : undefined}
                  onChange={(event) => {
                    setProgram(Number(event.target.value) || undefined);
                    setPage(1);
                  }}
                >
                  <option value="">Any program</option>
                  {programs.data?.items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </details>
          {(members.isError || programs.isError) && (
            <p id="filter-availability" className="filter-note" hidden={!filtersOpen}>
              {members.isError && "Owner choices include you and owners shown on this page. "}
              {programs.isError && "Program filtering is currently unavailable. "}
              <button
                className="text-button"
                onClick={() => {
                  void members.refetch();
                  void programs.refetch();
                }}
              >
                Retry filters
              </button>
            </p>
          )}
        </div>
        {hasFilters && (
          <div className="active-filters">
            <span>Filtered view</span>
            {search && <span>Search: {search}</span>}
            {owner && <span>Owner: {owner.display_name}</span>}
            {status && <span>{STATUS_LABELS[status]}</span>}
            {program && (
              <span>
                {programs.data?.items.find((item) => item.id === program)?.name ??
                  "Selected program"}
              </span>
            )}
            <button className="text-button" onClick={reset}>
              <X size={14} aria-hidden="true" />
              Clear filters
            </button>
          </div>
        )}
        <p className="directory-guidance">
          {scope === "all"
            ? "Gift history is shared across the board. Contact details stay with the owner and active super admin."
            : "A shared record of generosity. Select a relationship to see its recent gifts."}
        </p>
        <div className="ledger-head relationship-grid" aria-hidden="true">
          <span>Relationship</span>
          <span>Giving · 12 months</span>
          <span>Last contact</span>
          <span>Next step</span>
          <span>Steward</span>
          <span />
        </div>
        {donors.isPending ? (
          <LoadingLedger />
        ) : donors.isError ? (
          <ErrorState error={donors.error} retry={() => void donors.refetch()} />
        ) : donors.data.items.length === 0 ? (
          <EmptyState
            title={
              total > 0
                ? "This page has changed"
                : hasFilters
                  ? "No matching relationships"
                  : scope === "mine"
                    ? "Your relationship ledger starts here"
                    : "No relationships recorded yet"
            }
            action={
              total > 0 ? (
                <button className="button button-secondary" onClick={() => setPage(1)}>
                  Back to first page
                </button>
              ) : hasFilters ? (
                <button className="button button-secondary" onClick={reset}>
                  Clear filters
                </button>
              ) : scope === "mine" ? (
                <button
                  className="button button-secondary"
                  onClick={() => {
                    setScope("all");
                    setPage(1);
                  }}
                >
                  View all donors <ArrowRight size={16} aria-hidden="true" />
                </button>
              ) : undefined
            }
          >
            {total > 0
              ? "The directory changed while you were browsing. Return to the first page to see the latest records."
              : hasFilters
                ? "Try another name or adjust your filters."
                : scope === "mine"
                  ? "Donors assigned to you will appear here. You can also explore the board’s shared gift history."
                  : "Imported donor records will appear in this index."}
          </EmptyState>
        ) : (
          <div aria-label="Relationships">
            {donors.data.items.map((donor) => (
              <RelationshipRow
                key={donor.id}
                donor={donor}
                mine={donor.owner?.id === actor.id}
                fields={donors.data.fields}
              />
            ))}
          </div>
        )}
        {donors.isSuccess && total > 0 && (
          <nav className="pagination" aria-label="Donor pages">
            <span className="secondary-text">
              {donors.data.items.length > 0
                ? `${(page - 1) * 20 + 1}–${Math.min(page * 20, total)}`
                : "0 shown"}{" "}
              of {total.toLocaleString()}
            </span>
            <div>
              <button
                className="icon-button"
                aria-label="Previous donor page"
                disabled={page <= 1}
                onClick={() => setPage((value) => value - 1)}
              >
                <ArrowLeft size={18} aria-hidden="true" />
              </button>
              <span>
                Page {page} of {pages}
              </span>
              <button
                className="icon-button"
                aria-label="Next donor page"
                disabled={page >= pages}
                onClick={() => setPage((value) => value + 1)}
              >
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            </div>
          </nav>
        )}
      </section>
      <footer className="workspace-footer">
        <span>Coding in Color</span>
        <span>Every relationship has a story.</span>
      </footer>
    </>
  );
}
