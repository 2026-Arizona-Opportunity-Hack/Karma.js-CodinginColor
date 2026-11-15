import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Plus, Pencil } from "lucide-react";
import { ApiError } from "../api/client";
import type { components } from "../api/types";
import { useEntryMutation } from "../hooks/useEntryMutation";
import { useDirectoryOptions } from "../hooks/useDonors";
import {
  amountCents,
  canEditDonor,
  duplicateCandidates,
  entryError,
  serverFields,
  uncertainSave,
  type Candidate,
  type Donor,
} from "../lib/donorEntry";
import { dollars } from "../lib/format";
import { phoenixToday, QuickNoteSheet } from "./QuickNoteSheet";
import "./donor-entry.css";

type Mode = "create" | "edit" | "gift";
const titles = { create: "Create donor", edit: "Edit donor", gift: "Add gift" };

export function DonorEntry({
  actorId,
  donor,
  mode,
}: {
  actorId: number;
  donor?: Donor;
  mode: Mode;
}) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<{ text: string; id?: number }>();
  if (!open && mode !== "create" && (!donor || !canEditDonor(donor))) return null;
  return (
    <div className="entry-action">
      <button
        className={mode === "create" ? "button" : "button button-secondary"}
        onClick={() => {
          setNotice(undefined);
          setOpen(true);
        }}
      >
        {mode === "edit" ? (
          <Pencil size={16} aria-hidden="true" />
        ) : (
          <Plus size={16} aria-hidden="true" />
        )}
        {titles[mode]}
      </button>
      <span className="save-notice" role="status">
        {notice?.text} {notice?.id && <Link to={`/donors/${notice.id}`}>Open donor</Link>}
      </span>
      {open && (
        <EntryForm
          actorId={actorId}
          donor={donor}
          mode={mode}
          onClose={() => setOpen(false)}
          onSaved={(id) => {
            setOpen(false);
            setNotice({
              text:
                mode === "gift"
                  ? "Gift recorded."
                  : mode === "edit"
                    ? "Donor saved."
                    : "Donor created. Ownership assigned by the board’s rotation.",
              id: mode === "create" ? id : undefined,
            });
          }}
        />
      )}
    </div>
  );
}

function EntrySection({
  number,
  title,
  children,
}: {
  number: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="entry-section">
      <legend>
        <span>{number}</span>
        {title}
      </legend>
      <div className="entry-grid">{children}</div>
    </fieldset>
  );
}

function EntryForm({
  actorId,
  donor,
  mode,
  onClose,
  onSaved,
}: {
  actorId: number;
  donor?: Donor;
  mode: Mode;
  onClose: () => void;
  onSaved: (id: number) => void;
}) {
  const initial = {
    kind: donor?.kind ?? "person",
    display_name: donor?.display_name ?? "",
    first_name: donor?.first_name ?? "",
    last_name: donor?.last_name ?? "",
    organization: donor?.organization ?? "",
    email: donor?.email ?? "",
    phone: donor?.phone ?? "",
    notes: donor?.notes ?? "",
    do_not_contact: donor?.do_not_contact ?? false,
    amount: "",
    gift_date: phoenixToday(),
    program_id: "",
  };
  const [original] = useState(initial);
  const [values, setValues] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<Error | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [confirmNew, setConfirmNew] = useState(false);
  const [checkedRecord, setCheckedRecord] = useState(false);
  const summary = useRef<HTMLDivElement>(null);
  const lock = useRef(false);
  const save = useEntryMutation(actorId);
  const denied = error instanceof ApiError && [401, 403, 404, 501].includes(error.status);
  const allowed = mode === "create" || (!!donor && canEditDonor(donor));
  const dirty = JSON.stringify(values) !== JSON.stringify(original);
  function close() {
    if (!lock.current && (!dirty || window.confirm("Discard this unsaved entry?"))) onClose();
  }
  function change<K extends keyof typeof values>(key: K, value: (typeof values)[K]) {
    setValues((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => {
      const next = { ...previous };
      delete next[key];
      return next;
    });
    setCandidates([]);
    setConfirmNew(false);
  }
  function focusSummary() {
    requestAnimationFrame(() => summary.current?.focus());
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || !allowed || denied || (uncertainSave(error) && !checkedRecord)) return;
    const invalid: Record<string, string> = {};
    for (const input of event.currentTarget.elements) {
      if (!(
        input instanceof HTMLInputElement ||
        input instanceof HTMLSelectElement ||
        input instanceof HTMLTextAreaElement
      ))
        continue;
      if (!input.validity.valid)
        invalid[input.name] = input.validity.valueMissing
          ? "Please complete this field."
          : input.validity.typeMismatch
            ? "Enter a valid email address."
            : "Check the format and allowed range for this field.";
    }
    if (mode !== "gift" && !values.display_name.trim())
      invalid.display_name = "Enter a donor name.";
    const cents = amountCents(values.amount);
    if (mode === "gift" && cents === null)
      invalid.amount = "Enter $0.01 to $10,000,000.00, with at most two decimal places.";
    if (mode === "gift" && (!values.gift_date || values.gift_date > phoenixToday()))
      invalid.gift_date = "Choose today or an earlier date (Arizona time).";
    if (Object.keys(invalid).length) {
      setErrors(invalid);
      focusSummary();
      return;
    }
    lock.current = true;
    setError(null);
    setErrors({});
    setCheckedRecord(false);
    try {
      const optional = (value: string) => value.trim() || null;
      const common = {
        display_name: values.display_name.trim(),
        first_name: optional(values.first_name),
        last_name: optional(values.last_name),
        organization: optional(values.organization),
        email: optional(values.email),
        phone: optional(values.phone),
        notes: optional(values.notes),
        do_not_contact: values.do_not_contact,
      } satisfies components["schemas"]["DonorUpdate"];
      const result = await save.mutateAsync(
        mode === "gift"
          ? {
              action: "gift",
              donorId: donor!.id,
              body: {
                gift_date: values.gift_date,
                gross_cents: cents!,
                program_id: values.program_id ? Number(values.program_id) : null,
              },
            }
          : mode === "edit"
            ? { action: "edit", donorId: donor!.id, body: common }
            : {
                action: "create",
                body: {
                  ...common,
                  kind: values.kind,
                  display_name: values.display_name.trim(),
                  confirm_new: candidates.length > 0 && confirmNew,
                },
              },
      );
      onSaved(result.id);
    } catch (caught) {
      const failure =
        caught instanceof Error ? caught : new Error("Saving could not be confirmed.");
      setError(failure);
      setErrors(serverFields(failure));
      setCandidates(mode === "create" ? duplicateCandidates(failure) : []);
      setConfirmNew(false);
      focusSummary();
    } finally {
      lock.current = false;
    }
  }
  function field(
    key: "display_name" | "first_name" | "last_name" | "organization" | "email" | "phone",
    label: string,
    type = "text",
    helper?: string,
  ) {
    return (
      <label
        className={`note-field ${key === "display_name" || key === "organization" ? "entry-wide" : ""}`}
        htmlFor={`entry-${key}`}
      >
        {label}
        {key === "display_name" && " *"}
        <input
          id={`entry-${key}`}
          name={key}
          type={type}
          required={key === "display_name"}
          maxLength={key === "email" ? 254 : key === "phone" ? 40 : 200}
          pattern={key === "phone" ? "[0-9+\\(\\)\\-.\\s]{7,40}" : undefined}
          autoComplete={
            key === "email"
              ? "email"
              : key === "phone"
                ? "tel"
                : key === "first_name"
                  ? "given-name"
                  : key === "last_name"
                    ? "family-name"
                    : "off"
          }
          value={values[key]}
          onChange={(event) => change(key, event.target.value)}
          aria-invalid={!!errors[key]}
          aria-describedby={errors[key] || helper ? `entry-${key}-help` : undefined}
        />
        {(errors[key] || helper) && (
          <span
            className={errors[key] ? "entry-field-error" : "secondary-text"}
            id={`entry-${key}-help`}
          >
            {errors[key] ?? helper}
          </span>
        )}
      </label>
    );
  }
  return (
    <QuickNoteSheet
      open
      title={titles[mode]}
      donorName={donor?.display_name ?? "Coding in Color"}
      eyebrow="The stewardship ledger / Careful entry"
      className="entry-desk"
      busy={save.isPending}
      onClose={close}
    >
      <form onSubmit={submit} noValidate aria-busy={save.isPending}>
        <div className="quick-note-body">
          <p className="entry-intro">
            {mode === "gift"
              ? "Record generosity with care. Confirm the donor, date and amount before adding this gift."
              : mode === "edit"
                ? "Keep the relationship’s details accurate, and its preferences respected."
                : "Begin with a name. Add the details that will help the board care for this relationship."}{" "}
            <span className="secondary-text">* Required fields</span>
          </p>
          {(error || Object.keys(errors).length > 0) && (
            <div className="save-error" role="alert" tabIndex={-1} ref={summary}>
              <strong>
                {candidates.length ? "Check these possible matches" : "Your entry needs attention"}
              </strong>
              <p>
                {candidates.length
                  ? "A relationship may already exist. Compare before creating a separate record."
                  : error
                    ? entryError(error)
                    : "Review the highlighted fields below."}
              </p>
              {Object.entries(errors).length > 0 && (
                <ul>
                  {Object.entries(errors).map(([name, message]) => (
                    <li key={name}>
                      <a href={`#entry-${name === "gross_cents" ? "amount" : name}`}>
                        {name.replaceAll("_", " ")}: {message}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {candidates.length > 0 && (
            <section className="entry-conflicts" aria-label="Possible existing donors">
              <p className="eyebrow">Your entry</p>
              <h3>{values.display_name}</h3>
              <p className="secondary-text">{values.organization || "No organization provided"}</p>
              <p className="eyebrow">Existing relationships</p>
              {candidates.map((candidate) => (
                <article key={candidate.donor_id}>
                  <Link target="_blank" rel="noreferrer" to={`/donors/${candidate.donor_id}`}>
                    {candidate.display_name} <span className="sr-only">(opens in a new tab)</span>
                  </Link>
                  <p className="secondary-text">
                    Same{" "}
                    {candidate.match_reason === "name_employer"
                      ? "name and employer"
                      : candidate.match_reason}{" "}
                    · In the care of {candidate.owner?.display_name ?? "the board"}
                  </p>
                </article>
              ))}
              <label className="entry-check">
                <input
                  type="checkbox"
                  checked={confirmNew}
                  onChange={(event) => setConfirmNew(event.target.checked)}
                />
                I reviewed the matches. This is a separate donor.
              </label>
            </section>
          )}
          {uncertainSave(error) && (
            <label className="entry-check">
              <input
                type="checkbox"
                checked={checkedRecord}
                onChange={(event) => setCheckedRecord(event.target.checked)}
              />
              <span>
                I checked{" "}
                <Link
                  target="_blank"
                  rel="noreferrer"
                  to={donor ? `/donors/${donor.id}` : "/donors"}
                >
                  the saved records (new tab)
                </Link>{" "}
                and this entry was not saved. Allow another attempt.
              </span>
            </label>
          )}
          <fieldset className="entry-controls" disabled={save.isPending || denied || !allowed}>
            {mode === "gift" ? (
              <GiftFields
                actorId={actorId}
                donor={donor!}
                values={values}
                change={change}
                errors={errors}
              />
            ) : (
              <>
                <EntrySection number="01" title="The relationship">
                  <label className="note-field entry-wide" htmlFor="entry-kind">
                    Donor kind *
                    <select
                      id="entry-kind"
                      name="kind"
                      disabled={mode === "edit"}
                      value={values.kind}
                      onChange={(event) => change("kind", event.target.value as typeof values.kind)}
                    >
                      <option value="person">Individual</option>
                      <option value="organization">Organization</option>
                      <option value="funder">Funder</option>
                    </select>
                    {mode === "edit" && (
                      <span className="secondary-text">
                        Donor kind cannot be changed after creation.
                      </span>
                    )}
                  </label>
                  {field(
                    "display_name",
                    "Display name",
                    "text",
                    "The name shown throughout the relationship ledger.",
                  )}
                  {field("first_name", "First name")}
                  {field("last_name", "Last name")}
                  {field("organization", "Organization or employer")}
                </EntrySection>
                <EntrySection number="02" title="Contact & context">
                  {field("email", "Email", "email")}
                  {field(
                    "phone",
                    "Phone",
                    "tel",
                    "Include a country code for international numbers.",
                  )}
                  <p className="secondary-text entry-wide">
                    Contact details and notes are visible only to the donor’s owner and active super
                    admin.
                  </p>
                  <label className="note-field entry-wide" htmlFor="entry-notes">
                    Stewardship notes
                    <textarea
                      id="entry-notes"
                      name="notes"
                      rows={3}
                      maxLength={2000}
                      value={values.notes}
                      onChange={(event) => change("notes", event.target.value)}
                      aria-invalid={!!errors.notes}
                      aria-describedby="entry-notes-help"
                    />
                    <span
                      id="entry-notes-help"
                      className={errors.notes ? "entry-field-error" : "secondary-text"}
                    >
                      {errors.notes ??
                        "Optional · Up to 2,000 characters. Keep sensitive payment information out."}
                    </span>
                  </label>
                </EntrySection>
                <EntrySection number="03" title="Care & preferences">
                  <label className="entry-check entry-wide">
                    <input
                      name="do_not_contact"
                      type="checkbox"
                      checked={values.do_not_contact}
                      onChange={(event) => change("do_not_contact", event.target.checked)}
                    />
                    <span>
                      Do not contact
                      <span className="secondary-text">
                        Keep the giving history, and pause donor outreach.
                      </span>
                    </span>
                  </label>
                  <p className="secondary-text entry-wide">
                    {mode === "create"
                      ? "An owner is assigned automatically by round-robin. Creating a donor does not send a message."
                      : `In the care of ${donor?.owner?.display_name ?? "the board"}. Saving details does not change ownership.`}
                  </p>
                </EntrySection>
              </>
            )}
          </fieldset>
        </div>
        <footer className="quick-note-footer entry-footer">
          <p className="secondary-text">
            {mode === "gift"
              ? "This records a gift already received. No payment is collected."
              : "A careful record today makes the next conversation easier."}
          </p>
          <div>
            <button
              type="button"
              className="button button-secondary"
              disabled={save.isPending}
              onClick={close}
            >
              Cancel
            </button>
            <button
              className="button"
              type="submit"
              disabled={
                save.isPending ||
                denied ||
                !allowed ||
                (candidates.length > 0 && !confirmNew) ||
                (uncertainSave(error) && !checkedRecord)
              }
            >
              {save.isPending
                ? "Saving…"
                : candidates.length > 0 && confirmNew
                  ? "Create separate donor"
                  : mode === "gift"
                    ? "Record gift"
                    : mode === "edit"
                      ? "Save donor"
                      : "Create donor"}
            </button>
          </div>
        </footer>
      </form>
    </QuickNoteSheet>
  );
}

function GiftFields({
  actorId,
  donor,
  values,
  change,
  errors,
}: {
  actorId: number;
  donor: Donor;
  values: { amount: string; gift_date: string; program_id: string };
  change: (key: "amount" | "gift_date" | "program_id", value: string) => void;
  errors: Record<string, string>;
}) {
  const { programs } = useDirectoryOptions(actorId);
  const cents = amountCents(values.amount);
  return (
    <>
      <section className="entry-receipt" aria-label="Gift attribution">
        <p className="eyebrow">A gift for the mission</p>
        <h3>{donor.display_name}</h3>
        <strong className="numeric">{cents === null ? "$—" : dollars(cents)}</strong>
        <dl>
          <div>
            <dt>Source</dt>
            <dd>Manual entry</dd>
          </div>
          <div>
            <dt>Attribution</dt>
            <dd>Linked to this donor</dd>
          </div>
        </dl>
        <p className="secondary-text">
          Imported gifts keep their original source and attribution. Anonymous Benevity gifts cannot
          be attached to a donor.
        </p>
      </section>
      <EntrySection number="01" title="The gift">
        <label className="note-field" htmlFor="entry-amount">
          Amount (USD) *
          <input
            id="entry-amount"
            name="amount"
            inputMode="decimal"
            placeholder="0.00"
            required
            value={values.amount}
            onChange={(event) => change("amount", event.target.value)}
            aria-invalid={!!(errors.amount || errors.gross_cents)}
            aria-describedby="entry-amount-help"
          />
          <span
            id="entry-amount-help"
            className={errors.amount || errors.gross_cents ? "entry-field-error" : "secondary-text"}
          >
            {errors.amount ?? errors.gross_cents ?? "Dollars and cents · No fees deducted."}
          </span>
        </label>
        <label className="note-field" htmlFor="entry-gift_date">
          Gift date *
          <input
            id="entry-gift_date"
            name="gift_date"
            type="date"
            required
            max={phoenixToday()}
            value={values.gift_date}
            onChange={(event) => change("gift_date", event.target.value)}
            aria-invalid={!!errors.gift_date}
            aria-describedby="entry-date-help"
          />
          <span
            id="entry-date-help"
            className={errors.gift_date ? "entry-field-error" : "secondary-text"}
          >
            {errors.gift_date ?? "Date received · Arizona business date."}
          </span>
        </label>
        <label className="note-field entry-wide" htmlFor="entry-program_id">
          Program
          <select
            id="entry-program_id"
            name="program_id"
            value={values.program_id}
            onChange={(event) => change("program_id", event.target.value)}
            aria-invalid={!!errors.program_id}
            aria-describedby="entry-program-help"
          >
            <option value="">General (default)</option>
            {programs.data?.items
              .filter((program) => program.is_active && program.slug !== "general")
              .map((program) => (
                <option key={program.id} value={program.id}>
                  {program.name}
                </option>
              ))}
          </select>
          <span
            id="entry-program-help"
            className={errors.program_id ? "entry-field-error" : "secondary-text"}
          >
            {errors.program_id ??
              (programs.isError
                ? "Program choices are unavailable. General remains the server default."
                : programs.isPending
                  ? "Loading additional programs…"
                  : "Choose the program this gift supports.")}
          </span>
        </label>
        {programs.isError && (
          <button type="button" className="text-button" onClick={() => void programs.refetch()}>
            Retry programs
          </button>
        )}
      </EntrySection>
      <p className="quiet-note">
        Gift editing and gift notes are not available yet. For context, use stewardship notes or log
        a contact on the donor’s record.
      </p>
    </>
  );
}
