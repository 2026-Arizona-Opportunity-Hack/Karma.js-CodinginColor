import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";

import { api } from "../api/client";
import type { components } from "../api/types";
import { calendarDate } from "../lib/format";
import { ErrorState, LoadingLedger } from "./Workspace";
import "./message-templates.css";

type Template = components["schemas"]["TemplateOut"];
type TemplateList = components["schemas"]["TemplateListOut"];
const KEY = ["templates"] as const;
const KIND: Record<Template["kind"], string> = {
  thank_you: "Thank-you",
  quarterly_update: "Quarterly update",
  lapsed_nudge: "Lapsed-donor note",
  event_invite: "Event invitation",
};

function TemplateEditor({ t, editable }: { t: Template; editable: boolean }) {
  const client = useQueryClient();
  const id = useId();
  const [subject, setSubject] = useState(t.subject ?? "");
  const [body, setBody] = useState(t.body);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const save = useMutation({
    mutationFn: () =>
      api<Template>("/templates", {
        method: "PUT",
        body: {
          kind: t.kind,
          channel: t.channel,
          subject: t.channel === "email" ? subject : null,
          body,
        } satisfies components["schemas"]["TemplateIn"],
      }),
    onSuccess: (saved) => {
      client.setQueryData<TemplateList>(
        KEY,
        (list) => list && { items: list.items.map((x) => (x.id === saved.id ? saved : x)) },
      );
    },
  });
  const dirty = body !== t.body || (t.channel === "email" && subject !== (t.subject ?? ""));

  // Insert a merge field where the cursor is, then return focus to the text.
  const insert = (field: string) => {
    const el = bodyRef.current;
    const token = `{${field}}`;
    const at = el?.selectionStart ?? body.length;
    const end = el?.selectionEnd ?? at;
    setBody(body.slice(0, at) + token + body.slice(end));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + token.length, at + token.length);
    });
  };

  return (
    <li className="template-entry">
      <form
        aria-labelledby={`${id}-title`}
        onSubmit={(event) => {
          event.preventDefault();
          save.reset();
          save.mutate();
        }}
      >
        <header>
          <h3 id={`${id}-title`}>
            {KIND[t.kind]} <span>· {t.channel === "email" ? "Email" : "Text message"}</span>
          </h3>
          <small>Last changed {calendarDate(t.updated_at)}</small>
        </header>
        {t.channel === "email" && (
          <label className="template-field">
            <span>Subject</span>
            <input
              value={subject}
              maxLength={200}
              readOnly={!editable}
              onChange={(e) => setSubject(e.target.value)}
            />
          </label>
        )}
        <label className="template-field">
          <span>Message</span>
          <textarea
            ref={bodyRef}
            value={body}
            required
            maxLength={5000}
            rows={t.channel === "sms" ? 3 : 7}
            readOnly={!editable}
            onChange={(e) => setBody(e.target.value)}
          />
        </label>
        {editable && (
          <div className="merge-fields" role="group" aria-label="Insert a merge field">
            {t.merge_fields.map((f) => (
              <button key={f} type="button" onClick={() => insert(f)}>
                {`{${f}}`}
              </button>
            ))}
          </div>
        )}
        {save.isError && (
          <p className="template-error" role="alert">
            {save.error.message}
          </p>
        )}
        <p className="sr-only" role="status">
          {save.isSuccess && !dirty ? "Template saved." : ""}
        </p>
        {editable && (
          <div className="template-actions">
            <button className="button" type="submit" disabled={!dirty || save.isPending}>
              {save.isPending ? "Saving…" : "Save template"}
            </button>
            {dirty && (
              <button
                className="text-button"
                type="button"
                onClick={() => (setBody(t.body), setSubject(t.subject ?? ""), save.reset())}
              >
                Discard changes
              </button>
            )}
            {save.isSuccess && !dirty && <span className="template-saved">Saved</span>}
          </div>
        )}
      </form>
    </li>
  );
}

export function MessageTemplates({ editable }: { editable: boolean }) {
  const id = useId();
  const query = useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => api<TemplateList>("/templates", { signal }),
    retry: false,
  });
  return (
    <section className="template-ledger" aria-labelledby={`${id}-templates`}>
      <header className="members-heading">
        <div>
          <p className="eyebrow">Words we start from</p>
          <h2 id={`${id}-templates`}>Message templates</h2>
        </div>
      </header>
      <p className="quiet-note">
        New drafts start from these words. Merge fields such as {"{first_name}"} are filled in for
        each donor; gift amounts count the donor’s own gift, never an employer match. Every draft is
        still read and approved by a person before it is sent.
        {!editable && " Only the active super admin can change templates right now."}
      </p>
      {query.isPending ? (
        <LoadingLedger label="Loading templates" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <ul className="template-list">
          {query.data.items.map((t) => (
            <TemplateEditor key={t.id} t={t} editable={editable} />
          ))}
        </ul>
      )}
    </section>
  );
}
