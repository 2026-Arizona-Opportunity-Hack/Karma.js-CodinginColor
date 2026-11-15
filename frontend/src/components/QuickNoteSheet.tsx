import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

import { ApiError } from "../api/client";
import "./quick-note.css";

export function phoenixToday() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Phoenix",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const part = (name: string) => parts.find((p) => p.type === name)?.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function SaveError({ error }: { error: Error | null }) {
  if (!error) return null;
  const status = error instanceof ApiError ? error.status : 0;
  const message =
    status === 403
      ? "You no longer have permission to update this donor. Your entry is kept here. Contact the donor’s owner."
      : status === 401
        ? "Your session has ended. Sign in again before saving. Your entry is kept here."
        : status === 409
          ? "This next step has changed. Review the refreshed details before trying again."
          : status === 501
            ? "Saving is not available yet. Your entry is kept here."
            : status === 0
              ? "The connection was interrupted. Check the timeline before retrying; your entry is kept here."
              : error.message;
  return (
    <p className="save-error" role="alert">
      {message}
    </p>
  );
}

export function QuickNoteSheet({
  open,
  title,
  donorName,
  busy,
  onClose,
  children,
  className = "",
  eyebrow = "A moment of stewardship",
}: {
  open: boolean;
  title: string;
  donorName: string;
  busy: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  eyebrow?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  useEffect(() => {
    const node = dialog.current!;
    if (!open) {
      node.close();
      return;
    }
    const overflow = document.body.style.overflow;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = "hidden";
    node.showModal();
    heading.current?.focus();
    return () => {
      node.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected && !opener.matches(":disabled"))
        opener.focus({ preventScroll: true });
      else document.getElementById("main")?.focus({ preventScroll: true });
    };
  }, [open]);
  return (
    <dialog
      ref={dialog}
      className={`quick-note-sheet ${className}`}
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-donor`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          if (!busy) onClose();
          return;
        }
        if (event.key !== "Tab") return;
        const controls = [
          ...event.currentTarget.querySelectorAll<HTMLElement>(
            "button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href]",
          ),
        ].filter((node) => {
          if (node instanceof HTMLInputElement && node.type === "radio") {
            const group = [
              ...event.currentTarget.querySelectorAll<HTMLInputElement>("input[type=radio]"),
            ];
            return node === (group.find((radio) => radio.checked) ?? group[0]);
          }
          return node.getClientRects().length > 0;
        });
        const first = controls[0];
        const last = controls.at(-1);
        if (!first) {
          event.preventDefault();
          heading.current?.focus();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first || document.activeElement === heading.current)
        ) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <header className="quick-note-header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2 id={`${id}-title`} ref={heading} tabIndex={-1}>
            {title}
          </h2>
          <p id={`${id}-donor`}>
            For <strong>{donorName}</strong>
          </p>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Close sheet"
          disabled={busy}
          onClick={onClose}
        >
          <X size={20} aria-hidden="true" />
        </button>
      </header>
      {children}
    </dialog>
  );
}
