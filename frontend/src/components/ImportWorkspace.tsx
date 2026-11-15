import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/client";
import type { components } from "../api/types";
import { useFieldMutations } from "../hooks/useFields";
import { dollars } from "../lib/format";
import "./import-workspace.css";

export const SOURCES = {
  spreadsheet: "CIC donor spreadsheet",
  zeffy: "Zeffy payments",
  benevity: "Benevity disbursements",
  generic: "Generic gifts",
};

export function ImportError({ error, children }: { error: Error | null; children?: ReactNode }) {
  if (!error) return null;
  const status = error instanceof ApiError ? error.status : 0;
  return (
    <div className="import-notice import-error" role="alert">
      <strong>
        {status === 403
          ? "Permission denied"
          : status === 401
            ? "Sign in required"
            : "Action could not be completed"}
      </strong>
      <p>{error.message}</p>
      {status === 401 && (
        <Link to="/login" reloadDocument>
          Sign in again
        </Link>
      )}
      {status === 403 && <p>Your work is kept here. Check your access before trying again.</p>}
      {status === 501 && <p>This action is not available on the server yet.</p>}
      {children}
    </div>
  );
}

export function ReconciliationSummary({
  summary: s,
  committed = false,
}: {
  summary: components["schemas"]["ImportSummary"];
  committed?: boolean;
}) {
  const classes = [
    ["New records", s.new_gifts],
    ["Already imported · skipped", s.already_imported],
    ["Identity review", s.needs_review],
    ["Invalid · excluded", s.invalid],
    ["Donor update rows", s.donor_updates],
  ] as const;
  return (
    <section className="import-panel" aria-labelledby="reconciliation-title">
      <div className="import-section-heading">
        <div>
          <p className="eyebrow">The reconciliation ledger</p>
          <h2 id="reconciliation-title">Every row accounted for.</h2>
        </div>
        <span className={`import-label ${s.reconciles ? "is-balanced" : ""}`}>
          {s.reconciles ? "Totals reconcile" : "Totals do not reconcile"}
        </span>
      </div>
      <div className="import-metrics numeric">
        <div>
          <strong>{s.rows_read}</strong>
          <span>Source rows read</span>
        </div>
        <div>
          <strong>{s.gift_count}</strong>
          <span>Valid gifts represented</span>
        </div>
        <div>
          <strong>{dollars(s.total_cents)}</strong>
          <span>Gross USD represented</span>
        </div>
      </div>
      <div
        className="reconciliation-table"
        role="table"
        aria-label="Source row and gift reconciliation"
      >
        <div className="reconciliation-row reconciliation-head" role="row">
          {[
            "Classification",
            "Source rows",
            "Gifts",
            "Donations",
            "Employer matches",
            "Gross USD",
          ].map((label) => (
            <span role="columnheader" key={label}>
              {label}
            </span>
          ))}
        </div>
        {classes.map(([label, value]) => (
          <div className="reconciliation-row numeric" role="row" key={label}>
            <strong role="rowheader">{label}</strong>
            {[
              ["Source rows", value?.count ?? 0],
              ["Gifts", value?.gift_count ?? 0],
              ["Donations", dollars(value?.donation_cents ?? 0)],
              ["Employer matches", dollars(value?.match_cents ?? 0)],
              ["Gross USD", dollars(value?.cents ?? 0)],
            ].map(([name, value]) => (
              <span role="cell" key={name} data-label={name}>
                {value}
              </span>
            ))}
          </div>
        ))}
      </div>
      <div className="import-footnotes">
        <p>
          <strong>{s.new_donors}</strong> new donor identities · <strong>{s.donors_matched}</strong>{" "}
          matched identities · <strong>{s.updated_count ?? 0}</strong> donors{" "}
          {committed ? "updated" : "proposed for updates"}.
        </p>
        <p>
          {s.anonymous.count} anonymous source rows ({s.anonymous.gift_count} gifts) are included in
          New records, not added again. Donor-only spreadsheet rows create no gifts. One Benevity
          row can generate a donation and an employer-match gift.
        </p>
        <p>
          Amounts are gross before fees. Employer matches count toward organization revenue, not
          employee giving. Already-imported records add no new gifts.
        </p>
        {!!s.unmapped_campaigns.length && (
          <p>Mapped to General: {s.unmapped_campaigns.join("; ")}</p>
        )}
      </div>
    </section>
  );
}

/** Columns that matched no field (ING-14). Each can become a field, then the file is re-uploaded. */
export function IgnoredColumns({ columns }: { columns: components["schemas"]["IgnoredColumn"][] }) {
  const { create } = useFieldMutations();
  const [made, setMade] = useState<string[]>([]);
  if (!columns.length) return null;
  return (
    <section className="import-panel" aria-labelledby="ignored-title">
      <div className="import-section-heading">
        <div>
          <p className="eyebrow">Not imported</p>
          <h2 id="ignored-title">Columns Compass ignored</h2>
          <p>
            These columns match no field, so their values are left out. Create a field from a
            column, then upload the file again to import it.
          </p>
        </div>
      </div>
      <ul className="invalid-rows">
        {columns.map((c) => (
          <li key={c.header}>
            <strong>{c.header}</strong>
            {made.includes(c.header) ? (
              <span role="status">Field created. Upload the file again.</span>
            ) : (
              <button
                className="button button-secondary"
                disabled={create.isPending}
                aria-label={`Create field from column ${c.header}`}
                onClick={() =>
                  create.mutate(
                    {
                      entity: c.suggested_entity,
                      label: c.header,
                      type: c.guessed_type,
                      is_contact: false,
                      is_required: false,
                      show_in_list: false,
                    },
                    { onSuccess: () => setMade((m) => [...m, c.header]) },
                  )
                }
              >
                Create field from this column
              </button>
            )}
          </li>
        ))}
      </ul>
      {create.error && (
        <p role="alert" className="save-error">
          {create.error.message}
        </p>
      )}
    </section>
  );
}
