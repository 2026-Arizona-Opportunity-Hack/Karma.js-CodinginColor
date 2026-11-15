import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { FileUp, ArrowRight, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { components } from "../api/types";
import { DonorUpdateReview } from "../components/DonorUpdateReview";
import { ImportError, ReconciliationSummary, SOURCES } from "../components/ImportWorkspace";
import { QuickNoteSheet } from "../components/QuickNoteSheet";
import { PageMasthead } from "../components/Workspace";
import { useMe } from "../hooks/useAuth";
import { approvals, toggleField, type Selection } from "../lib/donorUpdates";
import { validateImportFile } from "../lib/importReview";

type Preview = components["schemas"]["ImportPreviewOut"];
type Batch = components["schemas"]["ImportBatchOut"];

export function ImportPage() {
  const me = useMe();
  const client = useQueryClient();
  const [source, setSource] = useState<Batch["source"]>("spreadsheet");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saved, setSaved] = useState<Batch | null>(null);
  const [dialog, setDialog] = useState<"fields" | "confirm" | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const [localError, setLocalError] = useState<Error | null>(null);
  const [recovery, setRecovery] = useState<"check" | "reupload" | null>(null);
  const [filter, setFilter] = useState("");
  const lock = useRef(false);
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const history = useQuery({
    queryKey: ["imports", me.data?.id],
    queryFn: ({ signal }) => api<components["schemas"]["ImportListOut"]>("/imports", { signal }),
    enabled: !!me.data,
    retry: false,
  });
  useEffect(() => {
    document.title = "Import / CIC Compass";
  }, []);
  useEffect(() => {
    if (preview || saved) resultHeading.current?.focus();
  }, [preview, saved]);
  async function refresh() {
    await Promise.all(
      [
        "imports",
        "donors",
        "donor",
        "donor-timeline",
        "gifts",
        "reviews",
        "unattributed",
        "reminders",
        "reports",
      ].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
  }
  async function confirmed(result: Batch) {
    if (result.status !== "committed")
      throw new Error(`Server returned ${result.status}; import is not confirmed.`);
    setSaved(result);
    setPreview(null);
    setDialog(null);
    setRecovery(null);
    await refresh();
  }
  const upload = useMutation({
    retry: false,
    mutationFn: (body: FormData) => api<Preview>("/imports/preview", { method: "POST", body }),
    onSuccess: (result) => {
      setPreview(result);
      setSaved(null);
      setSelection({});
      setRecovery(null);
      setFilter("");
    },
    onSettled: () => {
      lock.current = false;
    },
  });
  const commit = useMutation({
    retry: false,
    mutationFn: async () => {
      try {
        await confirmed(
          await api<Batch>(`/imports/${preview!.batch.id}/commit`, {
            method: "POST",
            body: { approved_updates: approvals(preview!.updates ?? [], selection) },
          }),
        );
      } catch (error) {
        setRecovery("check");
        throw error;
      }
    },
    onSettled: () => {
      lock.current = false;
    },
  });
  const check = useMutation({
    retry: false,
    mutationFn: async () => {
      try {
        const result = await api<Batch>(`/imports/${preview!.batch.id}`);
        if (result.status === "committed") {
          await confirmed(result);
          commit.reset();
          return;
        }
        const status = commit.error instanceof ApiError ? commit.error.status : 0;
        setRecovery(result.status !== "previewed" || status === 409 ? "reupload" : null);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) setRecovery("reupload");
        throw error;
      }
    },
    onSettled: () => {
      lock.current = false;
    },
  });
  const busy = upload.isPending || commit.isPending || check.isPending;
  function choose(next: File | null) {
    setFile(next);
    setLocalError(next && validateImportFile(next) ? new Error(validateImportFile(next)!) : null);
    setPreview(null);
    setSaved(null);
    setSelection({});
    setRecovery(null);
    upload.reset();
    commit.reset();
    check.reset();
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || lock.current) return;
    const message = validateImportFile(file);
    if (message) {
      setLocalError(new Error(message));
      return;
    }
    lock.current = true;
    setLocalError(null);
    setPreview(null);
    setSaved(null);
    commit.reset();
    check.reset();
    const body = new FormData();
    body.set("source", source);
    body.set("file", file);
    upload.mutate(body);
  }
  function doCommit() {
    if (lock.current || !preview?.commit_allowed || !preview.summary.reconciles || recovery) return;
    lock.current = true;
    commit.mutate();
  }
  const invalid =
    preview?.invalid_rows.filter((row) =>
      `${row.row_number} ${row.reason}`.toLowerCase().includes(filter.toLowerCase()),
    ) ?? [];
  return (
    <div className="import-workspace">
      <PageMasthead eyebrow="Bring the story together" title="Import records">
        From spreadsheets to lasting relationships. Check the ledger before anything is saved.
      </PageMasthead>
      <nav className="import-tabs" aria-label="Import workspace">
        <Link aria-current="page" to="/import">
          Upload & reconcile
        </Link>
        <Link to="/review">
          Identity review <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </nav>
      <ol className="import-steps" aria-label="Import stages">
        {["Bring records in", "Check & commit", "Resolve identities"].map((label, i) => (
          <li key={label} aria-current={(saved ? 2 : preview ? 1 : 0) === i ? "step" : undefined}>
            <span>{String(i + 1).padStart(2, "0")}</span>
            {label}
          </li>
        ))}
      </ol>
      {!saved && (
        <form onSubmit={submit} className="import-panel upload-panel" aria-busy={upload.isPending}>
          <div>
            <p className="eyebrow">01 / The source</p>
            <h2>Bring records in.</h2>
            <p>CSV or XLSX - up to 5 MB - USD gifts only</p>
            <label className="import-field">
              Source
              <select
                value={source}
                disabled={busy || recovery === "check"}
                onChange={(event) => {
                  setSource(event.target.value as Batch["source"]);
                  choose(file);
                }}
              >
                {Object.entries(SOURCES).map(([value, label]) => (
                  <option value={value} key={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <p className="secondary-text">
              {source === "spreadsheet"
                ? "Donor records only. Existing fields change only with your approval."
                : source === "generic"
                  ? "Use the CIC generic gifts template for AZ Gives, United Way or other platforms."
                  : "Export layouts are assumed; check the preview against your source file."}
            </p>
            <details className="import-format-help">
              <summary>File layout & required columns</summary>
              <p>
                {source === "spreadsheet"
                  ? "Name is required. Optional: Contact ID, Type, First name, Last name, Organization, Email, Phone, Notes. No gifts are created."
                  : source === "zeffy"
                    ? "Payment ID, Date, Amount are required. Optional: Currency, Payment status, Refunded amount, Campaign, Contact ID, First name, Last name, Email, Phone."
                    : source === "benevity"
                      ? "Transaction ID, Donation Date, Donation Amount, Donation Currency are required. Optional: Match Amount, Company Name, Project Name, Donor First Name, Donor Last Name, Donor Email, Cause Support Fee, Merchant Fee."
                      : "Date, Amount, Platform are required. Platform: azgives, united_way or other. Optional: Donor name, Email, Phone, Organization, Campaign, Transaction ID, Fee, Notes."}
              </p>
              <p>
                Include a header row. CSV must be UTF-8; XLSX uses the first sheet. Amounts are
                dollars. Headers ignore case and surrounding spaces. Preserve the original file for
                row-by-row checks.
              </p>
            </details>
          </div>
          <div
            className="import-dropzone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              if (!busy && recovery !== "check") {
                if (event.dataTransfer.files.length !== 1)
                  setLocalError(new Error("Choose one file at a time."));
                else choose(event.dataTransfer.files[0] ?? null);
              }
            }}
          >
            <FileUp size={30} strokeWidth={1.3} aria-hidden="true" />
            <label htmlFor="import-file">
              {file ? file.name : "Choose a file, or drop it here"}
            </label>
            <input
              id="import-file"
              type="file"
              accept=".csv,.xlsx"
              required
              disabled={busy || recovery === "check"}
              onChange={(event) => choose(event.target.files?.[0] ?? null)}
            />
            {file && (
              <p className="secondary-text">
                {(file.size / 1024).toFixed(1)} KB - original file is not edited
              </p>
            )}
            <button
              className="button"
              disabled={busy || !file || !!localError || recovery === "check"}
            >
              {upload.isPending
                ? "Uploading & preparing preview..."
                : preview
                  ? "Preview file again"
                  : "Preview file"}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </div>
        </form>
      )}
      {upload.isPending && (
        <p className="import-notice" role="status">
          Uploading, validating and checking identities. No donor or gift records are saved yet.
        </p>
      )}
      <ImportError error={localError ?? upload.error} />
      {preview && (
        <>
          <header className="import-file-heading">
            <div>
              <p className="eyebrow">02 / Preview - {SOURCES[preview.batch.source]}</p>
              <h2 ref={resultHeading} tabIndex={-1}>
                {preview.batch.filename}
              </h2>
            </div>
            <span className="import-label">Not yet imported</span>
          </header>
          <ReconciliationSummary summary={preview.summary} />
          {!!preview.invalid_rows.length && (
            <section className="import-panel">
              <div className="import-section-heading">
                <div>
                  <p className="eyebrow">Keep the source intact</p>
                  <h2>Invalid source rows</h2>
                  <p>
                    Excluded from import. Correct the original file and preview it again to recover
                    these records.
                  </p>
                </div>
                <label className="import-field">
                  Find a row or reason
                  <input
                    type="search"
                    value={filter}
                    onChange={(event) => setFilter(event.target.value)}
                  />
                </label>
              </div>
              <ul className="invalid-rows">
                {invalid.map((row) => (
                  <li key={row.row_number}>
                    <strong>
                      File row {row.row_number + 1}
                      <span className="secondary-text">Ref. {row.row_number}</span>
                    </strong>
                    <span>{row.reason}</span>
                  </li>
                ))}
              </ul>
              {!invalid.length && <p>No matching invalid rows.</p>}
              <p className="secondary-text">
                Backend validation reasons are shown verbatim. Raw source cells are not returned by
                the preview API. File rows include the header; the original zero-based backend row
                reference is kept beneath each row number.
              </p>
            </section>
          )}
          <section className="import-panel import-next">
            <div>
              <h2>Ready to add these records?</h2>
              <p>
                {preview.summary.needs_review.count} source rows need identity review after commit.
                Their gifts remain pending and unattributed until a person decides.
              </p>
              <p>
                Preview expires after 20 minutes and may expire sooner after a server restart. No
                per-row exclusion action is available; edit the source and upload again to remove a
                valid row.
              </p>
            </div>
            <button
              className="button"
              disabled={
                busy || !!recovery || !preview.commit_allowed || !preview.summary.reconciles
              }
              onClick={() => {
                commit.reset();
                setDialog(preview.updates?.length ? "fields" : "confirm");
              }}
            >
              {preview.updates?.length ? "Review donor updates" : "Review & confirm"}
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          </section>
          {!preview.commit_allowed && (
            <p className="import-notice import-error" role="alert">
              The server blocked commit. Preview a corrected file; all source rows and cents must
              reconcile.
            </p>
          )}
        </>
      )}
      <ImportError error={check.error ?? commit.error} />
      {recovery && (
        <div className="import-notice" role="status">
          <p>
            {recovery === "check"
              ? "The commit outcome needs verification. Check server status before another commit or upload."
              : "This preview cannot safely be reused. Preview your original file again; review all approvals afresh."}
          </p>
          {recovery === "check" && (
            <button
              className="button button-secondary"
              disabled={busy}
              onClick={() => {
                if (!lock.current) {
                  lock.current = true;
                  setDialog(null);
                  check.mutate();
                }
              }}
            >
              {check.isPending ? "Checking..." : "Check import status"}
            </button>
          )}
        </div>
      )}
      {saved && (
        <>
          <section className="import-panel import-success" role="status">
            <CheckCircle2 size={28} aria-hidden="true" />
            <div>
              <p className="eyebrow">Server confirmed - Batch #{saved.id}</p>
              <h2 ref={resultHeading} tabIndex={-1}>
                Import complete
              </h2>
              <p>
                {saved.filename} - {saved.summary?.updated_count ?? 0} donors updated. Invalid and
                already-imported rows were skipped.
              </p>
              <p>
                Pending identities still need a separate decision. No donor messages have been sent.
              </p>
              <div className="import-actions">
                <Link className="button" to="/review">
                  Resolve identities <ArrowRight size={16} aria-hidden="true" />
                </Link>
                <button className="button button-secondary" onClick={() => choose(null)}>
                  Import another file
                </button>
              </div>
            </div>
          </section>
          {saved.summary && <ReconciliationSummary summary={saved.summary} committed />}
        </>
      )}
      {dialog === "fields" && preview && (
        <DonorUpdateReview
          updates={preview.updates ?? []}
          selection={selection}
          onToggle={(donor, field) => setSelection((current) => toggleField(current, donor, field))}
          onCancel={() => setDialog(null)}
          onConfirm={() => setDialog("confirm")}
          busy={false}
          confirmLabel="Review import confirmation"
        />
      )}
      <QuickNoteSheet
        open={dialog === "confirm"}
        title="Confirm import"
        donorName={preview?.batch.filename ?? ""}
        busy={commit.isPending}
        onClose={() => setDialog(null)}
      >
        <div className="import-confirm">
          <p>
            This saves valid records in one transaction. Invalid rows and existing gifts are
            skipped. New donors receive an owner automatically.
          </p>
          <p>
            <strong>{preview?.summary.needs_review.count ?? 0} source rows</strong> will enter
            identity review after commit; no candidate is silently selected.
          </p>
          <p>
            <strong>{approvals(preview?.updates ?? [], selection).length} donor identities</strong>{" "}
            have approved field changes. Unchecked fields and existing ownership stay unchanged.
          </p>
          <p>
            Donation and employer-match gifts are distinct records. Confirm against your original
            file before saving.
          </p>
          <ImportError error={commit.error} />
          {recovery && (
            <p role="status">Close this confirmation and check import status before retrying.</p>
          )}
          <div className="import-actions">
            <button
              className="button button-secondary"
              disabled={commit.isPending}
              onClick={() => setDialog(null)}
            >
              Back to preview
            </button>
            <button className="button" disabled={busy || !!recovery} onClick={doCommit}>
              {commit.isPending ? "Committing..." : "Confirm import"}
            </button>
          </div>
        </div>
      </QuickNoteSheet>
      <section className="import-history">
        <div className="import-section-heading">
          <div>
            <p className="eyebrow">The import register</p>
            <h2>Recent batches</h2>
          </div>
          <button
            className="text-button"
            disabled={history.isFetching}
            onClick={() => void history.refetch()}
          >
            Refresh register
          </button>
        </div>
        {history.isPending && <p role="status">Loading import register...</p>}
        <ImportError error={history.error} />
        {history.data?.items.length === 0 && (
          <p>No saved import batches yet. Start with a preview above.</p>
        )}
        <ul>
          {history.data?.items.slice(0, 10).map((batch) => (
            <li key={batch.id}>
              <span>
                <strong>{batch.filename}</strong>
                <span className="secondary-text">
                  #{batch.id} - {SOURCES[batch.source]} - {batch.summary?.rows_read ?? " - "} source
                  rows
                </span>
              </span>
              <span className="import-label">{batch.status}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
