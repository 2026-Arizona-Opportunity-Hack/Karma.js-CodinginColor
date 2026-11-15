import { ArrowUpRight, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import type { components } from "../api/types";

export function PageMasthead({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <header className="page-masthead">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p className="page-intro">{children}</p>
    </header>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="workspace-state">
      <span className="state-mark" aria-hidden="true">
        —
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  const status = error instanceof ApiError ? error.status : undefined;
  return (
    <div className="workspace-state error-state" role="alert">
      <p className="eyebrow">{status === 403 ? "Access restricted" : "Unable to load"}</p>
      <h2>
        {status === 401
          ? "Please sign in again"
          : status === 403
            ? "This view isn’t available to you"
            : "We couldn’t load these records"}
      </h2>
      <p>{status === 401 ? "Your session may have expired." : error.message}</p>
      {status === 401 ? (
        <Link className="button" to="/login" reloadDocument>
          Sign in <ArrowUpRight size={16} aria-hidden="true" />
        </Link>
      ) : (
        <button className="button button-secondary" onClick={retry}>
          <RefreshCw size={16} aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  );
}

export const STATUS_LABELS: Record<components["schemas"]["DonorCard"]["statuses"][number], string> =
  {
    new: "New relationship",
    thank_you_due: "Thank-you due",
    update_due: "Update due",
    lapsed: "Lapsed giving",
    owner_inactive: "Owner inactive",
    do_not_contact: "Do not contact",
  };

export function StatusPill({ status }: { status: keyof typeof STATUS_LABELS }) {
  return <span className={`status-pill status-${status}`}>{STATUS_LABELS[status]}</span>;
}

export function LoadingLedger() {
  return (
    <div role="status" aria-label="Loading relationships" className="loading-ledger">
      <span className="sr-only">Loading relationships…</span>
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="skeleton-row" aria-hidden="true">
          <span className="skeleton skeleton-name" />
          <span className="skeleton" />
          <span className="skeleton" />
        </div>
      ))}
    </div>
  );
}
