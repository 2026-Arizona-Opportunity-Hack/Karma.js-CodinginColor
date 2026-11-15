import { useId } from "react";
import { useFields, type Entity, type Field, type FieldMeta } from "../hooks/useFields";
import { calendarDate, dollars } from "../lib/format";

/** Value as the form holds it: text for most types, booleans for yes/no, arrays for multi-choice. */
export type FormValue = string | boolean | string[];
export type FormValues = Record<string, FormValue>;
type Stored = unknown;

/** Custom fields people can fill in: active, and not one of the built-ins with their own inputs. */
export function useCustomFields(entity: Entity): Field[] {
  const fields = useFields(entity);
  return (fields.data ?? []).filter((f) => !f.is_builtin && f.is_active);
}

export function fromStored(fields: { key: string; type: string }[], stored: Stored): FormValues {
  const values: FormValues = {};
  const data = (stored ?? {}) as Record<string, unknown>;
  for (const f of fields) {
    const v = data[f.key];
    if (v === undefined || v === null) continue;
    if (f.type === "money" && typeof v === "number") values[f.key] = (v / 100).toFixed(2);
    else if (f.type === "bool") values[f.key] = v === true;
    else if (f.type === "multi_choice" && Array.isArray(v)) values[f.key] = v.map(String);
    else values[f.key] = String(v);
  }
  return values;
}

/** The `custom` object to send. Edits send null for a cleared field so the value is removed. */
export function toPayload(
  fields: { key: string; type: string }[],
  values: FormValues,
  clear: boolean,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = values[f.key];
    const empty = v === undefined || v === "" || (Array.isArray(v) && !v.length);
    if (f.type === "bool") {
      if (v !== undefined || clear) out[f.key] = v === undefined ? null : v;
    } else if (empty) {
      if (clear) out[f.key] = null;
    } else out[f.key] = v;
  }
  return out;
}

export function CustomInputs({
  fields,
  values,
  onChange,
  errors = {},
}: {
  fields: Field[];
  values: FormValues;
  onChange: (key: string, value: FormValue) => void;
  errors?: Record<string, string>;
}) {
  const id = useId();
  return (
    <>
      {fields.map((f) => {
        const inputId = `${id}-${f.key}`;
        const value = values[f.key];
        const label = `${f.label}${f.is_required ? " *" : ""}`;
        const hint = errors[f.key] ?? (f.is_contact ? "Contact detail · owner only" : undefined);
        const common = {
          id: inputId,
          required: f.is_required && f.type !== "bool",
          "aria-invalid": !!errors[f.key],
        };
        if (f.type === "bool")
          return (
            <label className="entry-check entry-wide" key={f.key}>
              <input
                type="checkbox"
                checked={value === true}
                onChange={(e) => onChange(f.key, e.target.checked)}
              />
              <span>{label}</span>
            </label>
          );
        if (f.type === "multi_choice")
          return (
            <fieldset className="note-field entry-wide" key={f.key}>
              <legend>{label}</legend>
              {(f.choices ?? []).map((c) => {
                const picked = Array.isArray(value) ? value : [];
                return (
                  <label className="entry-check" key={c}>
                    <input
                      type="checkbox"
                      checked={picked.includes(c)}
                      onChange={(e) =>
                        onChange(
                          f.key,
                          e.target.checked ? [...picked, c] : picked.filter((p) => p !== c),
                        )
                      }
                    />
                    <span>{c}</span>
                  </label>
                );
              })}
            </fieldset>
          );
        return (
          <label className="note-field" htmlFor={inputId} key={f.key}>
            {label}
            {f.type === "choice" ? (
              <select
                {...common}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(f.key, e.target.value)}
              >
                <option value="">{f.is_required ? "Choose one" : "None"}</option>
                {/* A value that is no longer offered stays visible so it is not lost silently. */}
                {typeof value === "string" && value && !(f.choices ?? []).includes(value) && (
                  <option value={value}>{value} (no longer offered)</option>
                )}
                {(f.choices ?? []).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : f.type === "long_text" ? (
              <textarea
                {...common}
                rows={3}
                maxLength={5000}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            ) : (
              <input
                {...common}
                type={f.type === "date" ? "date" : "text"}
                inputMode={
                  f.type === "number" ? "decimal" : f.type === "money" ? "decimal" : undefined
                }
                placeholder={f.type === "money" ? "0.00" : undefined}
                maxLength={500}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => onChange(f.key, e.target.value)}
              />
            )}
            {hint && (
              <span className={errors[f.key] ? "entry-field-error" : "secondary-text"}>{hint}</span>
            )}
          </label>
        );
      })}
    </>
  );
}

/** One stored value as text. Choices that were later removed are flagged, not hidden. */
export function formatValue(f: FieldMeta, v: Stored): string {
  if (v === undefined || v === null || v === "") return "";
  if (f.type === "money" && typeof v === "number") return dollars(v);
  if (f.type === "bool") return v ? "Yes" : "No";
  if (f.type === "date" && typeof v === "string") return calendarDate(v);
  if (f.type === "multi_choice" && Array.isArray(v))
    return v.map((c) => flag(f, String(c))).join(", ");
  if (f.type === "choice") return flag(f, String(v));
  return String(v);
}

const flag = (f: FieldMeta, choice: string) =>
  f.choices && !f.choices.includes(choice) ? `${choice} (no longer offered)` : choice;

/** Read-only list of the custom values a record has, in field order. */
export function CustomValues({
  fields,
  custom,
  title,
}: {
  fields: FieldMeta[];
  custom: Record<string, unknown> | undefined;
  title: string;
}) {
  const shown = fields.filter((f) => !f.is_builtin && formatValue(f, custom?.[f.key]));
  if (!shown.length) return null;
  return (
    <div className="dossier-notes">
      <h3>{title}</h3>
      <dl>
        {shown.map((f) => (
          <div key={f.key}>
            <dt>{f.label}</dt>
            <dd>{formatValue(f, custom?.[f.key])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
