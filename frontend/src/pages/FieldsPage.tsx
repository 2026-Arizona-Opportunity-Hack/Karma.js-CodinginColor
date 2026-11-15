import { ArrowDown, ArrowUp } from "lucide-react";
import { type FormEvent, useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { QuickNoteSheet } from "../components/QuickNoteSheet";
import { EmptyState, ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import {
  TYPE_LABELS,
  useFieldMutations,
  useFields,
  type Entity,
  type Field,
  type FieldType,
} from "../hooks/useFields";

const ENTITIES: { id: Entity; label: string }[] = [
  { id: "donor", label: "Donors" },
  { id: "gift", label: "Gifts" },
];
const CHOICE_TYPES: FieldType[] = ["choice", "multi_choice"];

type Editing = { field: Field } | { create: true } | null;

function FieldDialog({
  entity,
  editing,
  onClose,
}: {
  entity: Entity;
  editing: NonNullable<Editing>;
  onClose: () => void;
}) {
  const id = useId();
  const { create, patch } = useFieldMutations();
  const existing = "field" in editing ? editing.field : null;
  const [label, setLabel] = useState(existing?.label ?? "");
  const [type, setType] = useState<FieldType>(existing?.type ?? "text");
  const [choices, setChoices] = useState((existing?.choices ?? []).join("\n"));
  const [required, setRequired] = useState(existing?.is_required ?? false);
  const [contact, setContact] = useState(existing?.is_contact ?? false);
  const [inList, setInList] = useState(existing?.show_in_list ?? false);
  const mutation = existing ? patch : create;
  const hasChoices = CHOICE_TYPES.includes(type);
  const list = choices
    .split("\n")
    .map((c) => c.trim())
    .filter(Boolean);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (mutation.isPending) return;
    const done = { onSuccess: onClose };
    if (existing)
      patch.mutate(
        {
          id: existing.id,
          body: {
            label: label.trim(),
            show_in_list: inList,
            ...(existing.is_builtin
              ? {}
              : { is_required: required, ...(hasChoices ? { choices: list } : {}) }),
          },
        },
        done,
      );
    else
      create.mutate(
        {
          entity,
          label: label.trim(),
          type,
          choices: hasChoices ? list : undefined,
          is_required: required,
          is_contact: contact,
          show_in_list: inList,
        },
        done,
      );
  }

  return (
    <QuickNoteSheet
      open
      title={existing ? `Edit ${existing.label}` : "Add a field"}
      donorName={entity === "donor" ? "Donors" : "Gifts"}
      busy={mutation.isPending}
      onClose={onClose}
      eyebrow="Settings / Fields"
    >
      <form onSubmit={submit}>
        <div className="quick-note-body">
          <label className="note-field" htmlFor={`${id}-label`}>
            Label
            <input
              id={`${id}-label`}
              required
              maxLength={100}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>
          <label className="note-field" htmlFor={`${id}-type`}>
            Type
            <select
              id={`${id}-type`}
              value={type}
              disabled={!!existing}
              onChange={(e) => setType(e.target.value as FieldType)}
            >
              {Object.entries(TYPE_LABELS).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          {hasChoices && !existing?.is_builtin && (
            <label className="note-field" htmlFor={`${id}-choices`}>
              Choices, one per line
              <textarea
                id={`${id}-choices`}
                rows={4}
                value={choices}
                onChange={(e) => setChoices(e.target.value)}
              />
              <span className="secondary-text">
                Removing a choice keeps old values; they are flagged as no longer offered.
              </span>
            </label>
          )}
          <label className="ownership-confirm">
            <input type="checkbox" checked={inList} onChange={(e) => setInList(e.target.checked)} />
            <span>Show as a column in the donor list</span>
          </label>
          {!existing?.is_builtin && (
            <label className="ownership-confirm">
              <input
                type="checkbox"
                checked={required}
                onChange={(e) => setRequired(e.target.checked)}
              />
              <span>Required when adding a record</span>
            </label>
          )}
          {!existing && (
            <label className="ownership-confirm">
              <input
                type="checkbox"
                checked={contact}
                onChange={(e) => setContact(e.target.checked)}
              />
              <span>Contact detail: only the owner and the super admin see its value</span>
            </label>
          )}
          {mutation.error && (
            <p role="alert" className="save-error">
              {mutation.error.message}
            </p>
          )}
        </div>
        <footer className="quick-note-footer">
          <button className="button" disabled={mutation.isPending || !label.trim()}>
            {mutation.isPending ? "Saving…" : existing ? "Save field" : "Add field"}
          </button>
          <button
            type="button"
            className="text-button"
            disabled={mutation.isPending}
            onClick={onClose}
          >
            Cancel
          </button>
        </footer>
      </form>
    </QuickNoteSheet>
  );
}

function FieldTable({ entity }: { entity: Entity }) {
  const fields = useFields(entity);
  const { patch, remove } = useFieldMutations();
  const [editing, setEditing] = useState<Editing>(null);
  const items = fields.data ?? [];
  const busy = patch.isPending || remove.isPending;

  async function move(index: number, by: -1 | 1) {
    const a = items[index];
    const b = items[index + by];
    if (!a || !b) return;
    // Swap positions; give equal neighbours distinct slots so the order always changes.
    const [pa, pb] =
      a.position === b.position ? [b.position + by, a.position] : [b.position, a.position];
    await patch.mutateAsync({ id: a.id, body: { position: pa } });
    await patch.mutateAsync({ id: b.id, body: { position: pb } });
  }

  if (fields.isError)
    return <ErrorState error={fields.error} retry={() => void fields.refetch()} />;
  if (!fields.data) return <LoadingLedger label="Loading fields" />;
  return (
    <>
      <p>
        <button className="button" onClick={() => setEditing({ create: true })}>
          Add a field
        </button>
      </p>
      {items.length === 0 ? (
        <EmptyState title="No fields yet">Add the first one.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="member-table min-w-[44rem]">
            <caption className="sr-only">{entity} fields in display order</caption>
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Type</th>
                <th scope="col">In list</th>
                <th scope="col">Required</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((f, i) => (
                <tr key={f.id}>
                  <th scope="row">
                    {f.label}
                    {f.is_builtin && <span className="secondary-text">Built in</span>}
                    {f.is_contact && <span className="secondary-text">Contact detail</span>}
                  </th>
                  <td>{TYPE_LABELS[f.type]}</td>
                  <td>{f.show_in_list ? "Yes" : "No"}</td>
                  <td>{f.is_required ? "Yes" : "No"}</td>
                  <td>{f.is_active ? "Active" : "Inactive"}</td>
                  <td>
                    <div className="nomination-actions">
                      <button
                        className="text-button"
                        disabled={busy || i === 0}
                        aria-label={`Move ${f.label} up`}
                        onClick={() => void move(i, -1)}
                      >
                        <ArrowUp size={16} aria-hidden="true" />
                      </button>
                      <button
                        className="text-button"
                        disabled={busy || i === items.length - 1}
                        aria-label={`Move ${f.label} down`}
                        onClick={() => void move(i, 1)}
                      >
                        <ArrowDown size={16} aria-hidden="true" />
                      </button>
                      <button
                        className="text-button"
                        disabled={busy}
                        aria-label={`Edit ${f.label}`}
                        onClick={() => setEditing({ field: f })}
                      >
                        Edit
                      </button>
                      <button
                        className="text-button"
                        disabled={busy}
                        aria-label={`${f.is_active ? "Deactivate" : "Restore"} ${f.label}`}
                        onClick={() =>
                          patch.mutate({ id: f.id, body: { is_active: !f.is_active } })
                        }
                      >
                        {f.is_active ? "Deactivate" : "Restore"}
                      </button>
                      {!f.is_builtin && !f.has_values && (
                        <button
                          className="text-button danger-text"
                          disabled={busy}
                          aria-label={`Delete ${f.label}`}
                          onClick={() => {
                            if (window.confirm(`Delete "${f.label}"? It never held a value.`))
                              remove.mutate(f.id);
                          }}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(patch.error || remove.error) && (
        <p role="alert" className="save-error">
          {(patch.error ?? remove.error)?.message}
        </p>
      )}
      <p className="members-footnote">
        Deactivating hides a field everywhere but keeps its values; restore it any time. Built-in
        fields can be renamed, reordered and hidden, but not removed. Donor name, email, gift date
        and amount cannot be hidden.
      </p>
      {editing && (
        <FieldDialog entity={entity} editing={editing} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

export function FieldsPage() {
  const [entity, setEntity] = useState<Entity>("donor");
  useEffect(() => {
    document.title = "Fields · CIC Compass";
  }, []);
  return (
    <section>
      <PageMasthead eyebrow="Settings" title="Fields">
        Choose what Compass tracks about donors and gifts. Add, rename, reorder or hide fields
        without losing any data.
      </PageMasthead>
      <p>
        <Link to="/settings">Back to members &amp; governance</Link>
      </p>
      <div role="tablist" aria-label="Field type" className="nomination-actions">
        {ENTITIES.map((e) => (
          <button
            key={e.id}
            role="tab"
            id={`tab-${e.id}`}
            aria-selected={entity === e.id}
            aria-controls="fields-panel"
            className={entity === e.id ? "button" : "button button-secondary"}
            onClick={() => setEntity(e.id)}
          >
            {e.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="fields-panel" aria-labelledby={`tab-${entity}`}>
        <FieldTable key={entity} entity={entity} />
      </div>
    </section>
  );
}
