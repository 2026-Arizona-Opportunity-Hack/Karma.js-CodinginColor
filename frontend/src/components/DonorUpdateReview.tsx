import { useEffect, useRef } from "react";
import { fieldLabels } from "../lib/donorUpdates.js";
import type { Field, Selection, Update } from "../lib/donorUpdates.js";

type Props = {
  updates: Update[];
  selection: Selection;
  onToggle: (donor: number, field: Field) => void;
  onCancel: () => void;
  onConfirm: () => void;
  busy: boolean;
  error?: string;
};

export function DonorUpdateReview(props: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby="update-review-title"
      className="m-auto max-h-[85vh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-xl border border-slate-300 bg-white p-5 shadow-xl backdrop:bg-slate-900/50"
      onCancel={(event) => {
        event.preventDefault();
        if (!props.busy) props.onCancel();
      }}
    >
      <h2 id="update-review-title" className="text-xl font-semibold">
        Confirm donor updates
      </h2>
      <p className="my-3 text-slate-700">
        Choose each field to update. Unchecked fields keep their current values.
      </p>
      {props.updates.map((update) => (
        <fieldset
          key={update.donor_id}
          className="my-4 rounded-lg border border-slate-300 p-3"
          disabled={props.busy}
        >
          <legend className="px-1 font-semibold">{update.donor_name}</legend>
          {Object.entries(update.changes).map(([key, change]) => {
            const field = key as Field;
            return (
              <label key={field} className="my-3 flex items-start gap-3 break-words">
                <input
                  type="checkbox"
                  className="mt-1 h-5 w-5 shrink-0"
                  aria-label={`Update ${fieldLabels[field]} for ${update.donor_name}`}
                  checked={props.selection[update.donor_id]?.includes(field) ?? false}
                  onChange={() => props.onToggle(update.donor_id, field)}
                />
                <span className="min-w-0">
                  <span className="block font-medium">{fieldLabels[field]}</span>
                  <span className="block text-sm text-slate-600">
                    {change.old_hidden
                      ? "Current value hidden"
                      : `Current: ${change.old_value || "(empty)"}`}
                  </span>
                  <span className="block whitespace-pre-wrap">
                    New: {change.new_value || "(empty)"}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>
      ))}
      {props.error && (
        <p role="alert" className="my-3 text-red-800">
          {props.error}
        </p>
      )}
      <div className="mt-5 flex flex-wrap justify-end gap-3">
        <button
          type="button"
          onClick={props.onCancel}
          disabled={props.busy}
          className="rounded border border-slate-400 px-4 py-2"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={props.onConfirm}
          disabled={props.busy}
          className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
        >
          {props.busy ? "Committing…" : "Commit import"}
        </button>
      </div>
    </dialog>
  );
}
