import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/client";
import type { components } from "../api/types";
import { DonorUpdateReview } from "../components/DonorUpdateReview.js";
import { approvals, toggleField } from "../lib/donorUpdates.js";
import type { Selection } from "../lib/donorUpdates.js";

type Preview = components["schemas"]["ImportPreviewOut"];
type Batch = components["schemas"]["ImportBatchOut"];
type Source = Batch["source"];

export function ImportPage() {
  const [source, setSource] = useState<Source>("spreadsheet");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saved, setSaved] = useState<Batch | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [selection, setSelection] = useState<Selection>({});
  const upload = useMutation({
    mutationFn: (body: FormData) => api<Preview>("/imports/preview", { method: "POST", body }),
    onSuccess: (result) => {
      setPreview(result);
      setSaved(null);
      setSelection({});
    },
  });
  const commit = useMutation({
    mutationFn: () =>
      api<Batch>(`/imports/${preview!.batch.id}/commit`, {
        method: "POST",
        body: { approved_updates: approvals(preview!.updates ?? [], selection) },
      }),
    onSuccess: (result) => {
      setSaved(result);
      setReviewOpen(false);
      setPreview(null);
    },
  });
  const busy = upload.isPending || commit.isPending;
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setPreview(null);
    setSaved(null);
    commit.reset();
    const body = new FormData();
    body.set("source", source);
    body.set("file", file);
    upload.mutate(body);
  }
  return (
    <section className="mx-auto max-w-3xl space-y-5 p-4">
      <h1 className="text-2xl font-semibold">Import donors and gifts</h1>
      <p>
        Preview a CSV or XLSX file before importing. Files must be at most 5 MB. Source layouts are
        assumed.
      </p>
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-300 bg-white p-4">
        <label className="block">
          Source
          <select
            value={source}
            disabled={busy}
            className="mt-1 block w-full rounded border border-slate-400 p-2"
            onChange={(event) => {
              setSource(event.target.value as Source);
              setPreview(null);
            }}
          >
            <option value="spreadsheet">CIC donor spreadsheet</option>
            <option value="zeffy">Zeffy payments</option>
            <option value="benevity">Benevity disbursements</option>
            <option value="generic">Generic gifts</option>
          </select>
        </label>
        <label className="block">
          File
          <input
            type="file"
            accept=".csv,.xlsx"
            required
            disabled={busy}
            className="mt-1 block w-full"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setPreview(null);
            }}
          />
        </label>
        <button
          disabled={busy || !file}
          className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
        >
          {upload.isPending ? "Reading file…" : "Preview file"}
        </button>
      </form>
      {(upload.error || (commit.error && !reviewOpen)) && (
        <p role="alert" className="text-red-800">
          {(upload.error ?? commit.error)?.message}
        </p>
      )}
      {saved && (
        <p role="status" className="rounded border border-green-700 p-4">
          Import committed. {saved.summary?.updated_count ?? 0} donors updated.
        </p>
      )}
      {preview && (
        <div className="space-y-3 rounded-xl border border-slate-300 bg-white p-4">
          <h2 className="text-xl font-semibold">Preview: {preview.batch.filename}</h2>
          <p>
            {preview.summary.rows_read} source rows · {preview.summary.gift_count} gifts ·{" "}
            {preview.summary.updated_count ?? 0} donor updates
          </p>
          <p>
            {preview.summary.reconciles
              ? "Rows and cents reconcile."
              : "Totals do not reconcile. Upload a corrected file."}
          </p>
          <p>
            {preview.summary.new_donors} new donors · {preview.summary.needs_review.count} rows
            needing identity review · {preview.summary.invalid.count} invalid rows
          </p>
          {preview.invalid_rows.length > 0 && (
            <details>
              <summary>Invalid rows</summary>
              <ul className="list-disc pl-5">
                {preview.invalid_rows.map((row) => (
                  <li key={row.row_number}>
                    Row {row.row_number}: {row.reason.replaceAll("_", " ")}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <button
            disabled={busy || !preview.commit_allowed}
            className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
            onClick={() => {
              commit.reset();
              setSelection({});
              if (preview.updates?.length) setReviewOpen(true);
              else commit.mutate();
            }}
          >
            {preview.updates?.length ? "Review donor updates" : "Commit import"}
          </button>
        </div>
      )}
      {reviewOpen && preview && (
        <DonorUpdateReview
          updates={preview.updates ?? []}
          selection={selection}
          onToggle={(donor, field) => setSelection((current) => toggleField(current, donor, field))}
          onCancel={() => setReviewOpen(false)}
          onConfirm={() => commit.mutate()}
          busy={commit.isPending}
          error={commit.error?.message}
        />
      )}
    </section>
  );
}
