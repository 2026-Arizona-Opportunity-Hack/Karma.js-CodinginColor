import { ArrowLeft, ArrowDown, Mail, Phone } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { CustomValues, formatValue } from "../components/CustomFields";
import { LogContact, NextStep } from "../components/DonorStewardship";
import { DonorEntry } from "../components/DonorEntry";
import { DonorOwnership } from "../components/DonorOwnership";
import {
  EmptyState,
  ErrorState,
  LoadingLedger,
  PageMasthead,
  StatusPill,
} from "../components/Workspace";
import { useMe } from "../hooks/useAuth";
import { useDonorDetail } from "../hooks/useDonorDetail";
import { calendarDate, dollars } from "../lib/format";
import "./donor-detail.css";

const eventLabels = {
  gift: "Gift",
  contact: "Contact",
  message: "Message",
  note: "Note",
  next_step: "Next step",
  owner_change: "Ownership",
};

export function DonorDetailPage() {
  const { donorId } = useParams();
  const me = useMe();
  return me.data ? <Dossier key={donorId} id={Number(donorId)} actorId={me.data.id} /> : null;
}

function Dossier({ id, actorId }: { id: number; actorId: number }) {
  const { donor, timeline } = useDonorDetail(actorId, id);
  const { hash } = useLocation();
  useEffect(() => {
    if (donor.isSuccess && hash) {
      const target = document.getElementById(hash.slice(1));
      target?.focus();
      target?.scrollIntoView({ block: "center" });
    }
  }, [donor.isSuccess, hash]);
  const heading = useRef<HTMLDivElement>(null);
  useEffect(() => {
    document.title = `${donor.data?.display_name ?? "Donor detail"} · CIC Compass`;
  }, [donor.data?.display_name]);
  useEffect(() => {
    if (!hash) heading.current?.focus();
  }, [hash]);
  const missing =
    !Number.isSafeInteger(id) ||
    id <= 0 ||
    (donor.error instanceof ApiError && donor.error.status === 404);
  const d = donor.data;
  const events = [...(timeline.data?.items ?? [])].sort(
    (a, b) => Date.parse(b.at) - Date.parse(a.at),
  );
  return (
    <div className="donor-dossier">
      <Link className="dossier-back" to="/donors">
        <ArrowLeft size={16} aria-hidden="true" /> All relationships
      </Link>
      <div ref={heading} tabIndex={-1}>
        <PageMasthead
          eyebrow="The stewardship ledger / Relationship dossier"
          title={d?.display_name ?? "Donor detail"}
        >
          {d
            ? `${d.kind === "person" ? "Individual" : d.kind === "funder" ? "Funder" : "Organization"}${d.organization ? ` · ${d.organization}` : ""}`
            : "A record of care, connection and giving."}
        </PageMasthead>
      </div>
      {missing ? (
        <EmptyState title="Donor not found">
          This relationship may have been removed or is no longer available. Return to the directory
          to find another donor.
        </EmptyState>
      ) : donor.isError ? (
        <ErrorState error={donor.error} retry={() => void donor.refetch()} />
      ) : !d ? (
        <LoadingLedger label="Loading donor detail" />
      ) : (
        <>
          <div className="dossier-toolbar">
            <div className="status-list">
              {d.statuses.map((status) => (
                <StatusPill key={status} status={status} />
              ))}
            </div>
            <LogContact donor={d} actorId={actorId} />
            <DonorEntry mode="edit" donor={d} actorId={actorId} />
            <DonorEntry mode="gift" donor={d} actorId={actorId} />
            <a className="button button-secondary" href="#relationship-timeline">
              Read the timeline <ArrowDown size={16} aria-hidden="true" />
            </a>
          </div>
          <dl className="giving-summary">
            <div>
              <dt>Giving · 12 months</dt>
              <dd className="numeric">{dollars(d.total_12m_cents)}</dd>
            </div>
            <div>
              <dt>Lifetime giving</dt>
              <dd className="numeric">{dollars(d.total_lifetime_cents)}</dd>
            </div>
            <div>
              <dt>Last gift</dt>
              <dd>{calendarDate(d.last_gift_date)}</dd>
            </div>
            <div>
              <dt>Last contacted</dt>
              <dd>{calendarDate(d.last_contact_date)}</dd>
            </div>
          </dl>
          <p className="secondary-text">
            Giving totals reflect donor contributions. Employer matches are recorded separately.
          </p>
          <div className="dossier-columns">
            <aside className="dossier-steward" aria-label="Relationship stewardship">
              <section id="relationship-owner" tabIndex={-1}>
                <p className="eyebrow">In the care of</p>
                <h2>{d.owner?.display_name ?? "Not assigned"}</h2>
                {d.owner && !d.owner.is_active && <p>Inactive member</p>}
                <p className="secondary-text">Relationship added {calendarDate(d.created_at)}</p>
                <DonorOwnership donor={d} actorId={actorId} />
              </section>
              <section>
                <h2>Contact & context</h2>
                {!d.contact_visible ? (
                  <p className="contact-via">
                    Contact via {d.contact_via ?? d.owner?.display_name ?? "the stewardship team"}
                  </p>
                ) : (
                  <>
                    <dl className="contact-details">
                      <dt>Email</dt>
                      <dd>{d.email ?? "Not provided"}</dd>
                      <dt>Phone</dt>
                      <dd>{d.phone ?? "Not provided"}</dd>
                    </dl>
                    {d.can_act && !d.do_not_contact && (
                      <div className="contact-actions">
                        {d.email && (
                          <a className="button button-secondary" href={`mailto:${d.email}`}>
                            <Mail size={16} aria-hidden="true" /> Email donor
                          </a>
                        )}
                        {d.phone && (
                          <a className="button button-secondary" href={`tel:${d.phone}`}>
                            <Phone size={16} aria-hidden="true" /> Call donor
                          </a>
                        )}
                      </div>
                    )}
                    {d.notes && (
                      <div className="dossier-notes">
                        <h3>Stewardship notes</h3>
                        <p>{d.notes}</p>
                      </div>
                    )}
                  </>
                )}
                <CustomValues
                  fields={d.fields ?? []}
                  custom={d.custom}
                  title="Additional details"
                />
                {d.do_not_contact && (
                  <p className="contact-via">
                    Do not contact. This donor has asked not to receive outreach.
                  </p>
                )}
              </section>
              <NextStep
                donor={d}
                actorId={actorId}
                timeline={timeline.data}
                timelineReady={timeline.isSuccess && !timeline.isFetching && !donor.isFetching}
              />
              <a className="dossier-back" href="#gift-history">
                View recent gifts <ArrowDown size={16} aria-hidden="true" />
              </a>
            </aside>
            <div className="dossier-story">
              <section id="relationship-timeline" tabIndex={-1} aria-labelledby="timeline-title">
                <div className="section-heading">
                  <h2 id="timeline-title">The correspondence trail</h2>
                  <span className="secondary-text">Newest first</span>
                </div>
                <p className="quiet-note">Gifts, conversations and the care in between.</p>
                {timeline.isError ? (
                  <ErrorState error={timeline.error} retry={() => void timeline.refetch()} />
                ) : timeline.isPending ? (
                  <LoadingLedger label="Loading relationship timeline" />
                ) : events.length === 0 ? (
                  <EmptyState title="The story starts here">
                    No relationship events have been recorded yet.
                  </EmptyState>
                ) : (
                  <ol className="relationship-timeline">
                    {events.map((event, index) => (
                      <li
                        key={`${event.kind}-${event.entity_id ?? index}-${event.at}`}
                        className={`trail-event trail-${event.kind}`}
                      >
                        <div className="trail-meta">
                          <span>{eventLabels[event.kind]}</span>
                          <time dateTime={event.at}>{calendarDate(event.at)}</time>
                        </div>
                        <h3>{event.title}</h3>
                        {event.amount_cents != null && (
                          <p className="trail-amount numeric">{dollars(event.amount_cents)}</p>
                        )}
                        {event.detail && <p className="trail-detail">{event.detail}</p>}
                        {event.by && <p className="secondary-text">Recorded by {event.by}</p>}
                      </li>
                    ))}
                  </ol>
                )}
                <p className="secondary-text">
                  Showing up to 500 recent events. Older history may not be included.
                </p>
              </section>
              <section
                id="gift-history"
                tabIndex={-1}
                aria-labelledby="gifts-title"
                className="dossier-gifts"
              >
                <div className="section-heading">
                  <h2 id="gifts-title">Gift history</h2>
                  <span className="secondary-text">Five most recent · USD</span>
                </div>
                {d.recent_gifts.length === 0 ? (
                  <p className="quiet-note">No linked gifts recorded yet.</p>
                ) : (
                  <ul className="gift-list">
                    {d.recent_gifts.map((gift) => (
                      <li key={gift.id}>
                        <time dateTime={gift.gift_date}>{calendarDate(gift.gift_date)}</time>
                        <span>
                          {gift.program}
                          <span className="secondary-text">
                            {gift.source === "manual"
                              ? "Manual entry"
                              : gift.source === "generic"
                                ? "Generic import"
                                : gift.source === "zeffy"
                                  ? "Zeffy"
                                  : "Benevity"}
                            {gift.is_matching_gift
                              ? ` · Employer match${gift.payer_name ? ` · ${gift.payer_name}` : ""}`
                              : ""}
                            {(d.gift_fields ?? [])
                              .filter((f) => !f.is_builtin && formatValue(f, gift.custom?.[f.key]))
                              .map((f) => ` · ${f.label}: ${formatValue(f, gift.custom?.[f.key])}`)
                              .join("")}
                          </span>
                        </span>
                        <strong className="numeric">{dollars(gift.gross_cents)}</strong>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="secondary-text">
                  Earlier gifts appear in the correspondence trail above. Gift editing is not
                  available yet.
                </p>
              </section>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
