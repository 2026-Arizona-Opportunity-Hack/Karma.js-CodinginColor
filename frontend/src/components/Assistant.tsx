import { Mic, MicOff, Sparkles, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  useConfirmAction,
  useInterpret,
  type DonorChoice,
  type ProposedAction,
} from "../hooks/useAssistant";
import { useSpeech } from "../hooks/useSpeech";
import "./assistant.css";

/** Where the Edit button sends the person: the donor screen with the form pre-filled. */
export type AssistantEdit = { tool: ProposedAction["tool"]; body: Record<string, unknown> };

/** The assistant's proposed values for `tool`, if the person arrived here by pressing Edit. */
export function assistantEdit(state: unknown, tool: AssistantEdit["tool"]) {
  const edit = (state as { assistantEdit?: AssistantEdit } | null)?.assistantEdit;
  return edit?.tool === tool ? edit.body : undefined;
}

const OFF = "The assistant is turned off for your team.";

/** The floating assistant. It proposes; nothing is saved until a person presses Confirm. */
export function Assistant() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const fab = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState("");
  const interpret = useInterpret();
  const speech = useSpeech((heard) =>
    setText((t) => `${t}${t && !t.endsWith(" ") ? " " : ""}${heard}`.slice(0, 500)),
  );
  const titleId = useId();
  const visible = pathname === "/" || /^\/donors\/\d+/.test(pathname);

  useEffect(() => {
    if (open) field.current?.focus();
  }, [open]);
  if (!visible) return null;

  const close = () => {
    speech.stop();
    setOpen(false);
    fab.current?.focus();
  };
  const result = interpret.data;
  const error = interpret.error;
  const errorText =
    error instanceof ApiError && error.status === 404
      ? OFF
      : error instanceof ApiError && error.status === 429
        ? "That was a lot of requests. Wait a minute and try again."
        : error?.message;

  return (
    <>
      <button
        ref={fab}
        type="button"
        className="assistant-fab"
        aria-expanded={open}
        aria-controls="assistant-panel"
        onClick={() => (open ? close() : setOpen(true))}
      >
        <Sparkles size={20} aria-hidden="true" />
        <span>Assistant</span>
      </button>
      {open && (
        <section
          id="assistant-panel"
          className="assistant-panel"
          role="dialog"
          aria-labelledby={titleId}
          onKeyDown={(e) => e.key === "Escape" && close()}
        >
          <header>
            <h2 id={titleId}>Assistant</h2>
            <button
              type="button"
              className="icon-button"
              aria-label="Close assistant"
              onClick={close}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </header>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim() && !interpret.isPending) interpret.mutate(text.trim());
            }}
          >
            <label htmlFor="assistant-text">Tell me what to do</label>
            <textarea
              id="assistant-text"
              ref={field}
              rows={3}
              maxLength={500}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="assistant-chips" aria-label="Examples">
              {(result?.examples ?? DEFAULT_EXAMPLES).map((example) => (
                <button
                  key={example}
                  type="button"
                  className="chip"
                  onClick={() => setText(example)}
                >
                  {example}
                </button>
              ))}
            </div>
            <div className="assistant-send">
              {speech.supported && (
                <button
                  type="button"
                  className="button button-secondary"
                  aria-pressed={speech.listening}
                  onClick={speech.toggle}
                >
                  {speech.listening ? (
                    <MicOff size={16} aria-hidden="true" />
                  ) : (
                    <Mic size={16} aria-hidden="true" />
                  )}
                  {speech.listening ? "Stop listening" : "Speak"}
                </button>
              )}
              <button className="button" disabled={!text.trim() || interpret.isPending}>
                {interpret.isPending ? "Thinking…" : "Send"}
              </button>
            </div>
          </form>
          <div aria-live="polite" className="assistant-results">
            {errorText && <p className="save-error">{errorText}</p>}
            {result?.message && <p className="assistant-message">{result.message}</p>}
            {result?.actions.map((action, i) => (
              <ActionCard key={`${i}-${action.summary}`} action={action} onEdit={close} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

const DEFAULT_EXAMPLES = [
  "Log a call with Maria about the spring gala",
  "Remind me to follow up with Sam next Friday",
  "Draft a thank-you for Priya",
];

type CardState = "idle" | "done" | "cancelled";

function ActionCard({ action, onEdit }: { action: ProposedAction; onEdit: () => void }) {
  const [state, setState] = useState<CardState>("idle");
  const [picked, setPicked] = useState<number | null>(action.choices.length === 1 ? 0 : null);
  const confirm = useConfirmAction();
  const navigate = useNavigate();
  const name = useId();
  const choice: DonorChoice | undefined = picked === null ? undefined : action.choices[picked];

  if (state === "cancelled")
    return <p className="assistant-card is-muted">Cancelled: {action.summary}</p>;
  if (state === "done" && choice)
    return (
      <p className="assistant-card is-done">
        Done: {action.summary}.{" "}
        <Link to={`/donors/${choice.donor_id}`} onClick={onEdit}>
          Open {choice.donor_name}
        </Link>
      </p>
    );

  return (
    <article className="assistant-card">
      <p className="assistant-summary">{action.summary}</p>
      {action.status === "error" && <p className="save-error">{action.error}</p>}
      {action.status === "choose_donor" && (
        <fieldset>
          <legend>Which donor?</legend>
          {action.choices.map((c, i) => (
            <label key={c.donor_id}>
              <input
                type="radio"
                name={name}
                checked={picked === i}
                onChange={() => setPicked(i)}
              />
              {c.donor_name}
            </label>
          ))}
        </fieldset>
      )}
      {confirm.error && (
        <p className="save-error" role="alert">
          {confirm.error.message}
        </p>
      )}
      <div className="assistant-actions">
        {action.status !== "error" && (
          <>
            <button
              type="button"
              className="button"
              disabled={!choice || confirm.isPending}
              onClick={() =>
                choice && confirm.mutate(choice, { onSuccess: () => setState("done") })
              }
            >
              {confirm.isPending ? "Saving…" : "Confirm"}
            </button>
            <button
              type="button"
              className="button button-secondary"
              disabled={!choice}
              onClick={() => {
                if (!choice) return;
                const edit: AssistantEdit = { tool: action.tool, body: choice.request.body };
                onEdit();
                navigate(`/donors/${choice.donor_id}`, { state: { assistantEdit: edit } });
              }}
            >
              Edit
            </button>
          </>
        )}
        <button type="button" className="text-button" onClick={() => setState("cancelled")}>
          {action.status === "error" ? "Dismiss" : "Cancel"}
        </button>
      </div>
    </article>
  );
}
