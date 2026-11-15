import { ChevronDown } from "lucide-react";

import type { components } from "../api/types";
import { calendarDate, dollars, initials } from "../lib/format";
import { StatusPill } from "./Workspace";

export function RelationshipRow({
  donor,
  mine,
}: {
  donor: components["schemas"]["DonorCard"];
  mine: boolean;
}) {
  return (
    <article className="relationship-row">
      <details>
        <summary className="relationship-grid">
          <span className="relationship-identity">
            <span className={`identity-mark identity-${donor.kind}`} aria-hidden="true">
              {initials(donor.display_name)}
            </span>
            <span className="identity-copy">
              <span className="donor-name">{donor.display_name}</span>
              <span className="secondary-text">
                {donor.kind === "person"
                  ? "Individual"
                  : donor.kind === "funder"
                    ? "Funder"
                    : "Organization"}
                {donor.organization && ` · ${donor.organization}`}
              </span>
              {donor.statuses.length > 0 && (
                <span className="status-list">
                  {donor.statuses.map((status) => (
                    <StatusPill key={status} status={status} />
                  ))}
                </span>
              )}
            </span>
          </span>
          <span className="ledger-cell">
            <span className="mobile-label">Giving · 12 months</span>
            <strong className="numeric">{dollars(donor.total_12m_cents)}</strong>
            <span className="secondary-text">{dollars(donor.total_lifetime_cents)} lifetime</span>
            <span className="secondary-text">
              Last gift {calendarDate(donor.last_gift_date, "not recorded")}
            </span>
          </span>
          <span className="ledger-cell">
            <span className="mobile-label">Last contact</span>
            <span>{calendarDate(donor.last_contact_date)}</span>
          </span>
          <span className="ledger-cell">
            <span className="mobile-label">Next step</span>
            <span>{donor.next_step_title ?? "No next step set"}</span>
            {donor.next_step_due && (
              <span className="secondary-text">Due {calendarDate(donor.next_step_due)}</span>
            )}
          </span>
          <span className="ledger-cell owner-cell">
            <span className="mobile-label">Steward</span>
            <span>
              {donor.owner?.display_name ?? "Not assigned"}
              {mine && <span className="owner-you">You</span>}
            </span>
            {donor.owner && !donor.owner.is_active && (
              <span className="secondary-text">Inactive member</span>
            )}
          </span>
          <ChevronDown className="row-chevron" size={17} aria-hidden="true" />
          <span className="sr-only"> — show or hide recent gifts</span>
        </summary>
        <section className="gift-preview" aria-label={`Recent gifts from ${donor.display_name}`}>
          <div className="section-heading">
            <h2>Recent gifts</h2>
            <span className="secondary-text">Up to five most recent · USD</span>
          </div>
          <p className="secondary-text gift-credit-note">
            Giving totals reflect donor contributions. Employer matches appear separately below.
          </p>
          {donor.recent_gifts.length === 0 ? (
            <p className="quiet-note">No linked gifts recorded yet.</p>
          ) : (
            <ul className="gift-list">
              {donor.recent_gifts.map((gift) => (
                <li key={gift.id}>
                  <time dateTime={gift.gift_date}>{calendarDate(gift.gift_date)}</time>
                  <span>
                    {gift.program}
                    <span className="secondary-text">
                      {gift.source === "zeffy"
                        ? "Zeffy"
                        : gift.source === "benevity"
                          ? "Benevity"
                          : gift.source === "manual"
                            ? "Manual entry"
                            : "Generic import"}
                      {gift.is_matching_gift &&
                        ` · Employer match${gift.payer_name ? ` · ${gift.payer_name}` : ""}`}
                    </span>
                  </span>
                  <strong className="numeric">{dollars(gift.gross_cents)}</strong>
                </li>
              ))}
            </ul>
          )}
        </section>
      </details>
    </article>
  );
}
